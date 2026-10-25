"""debugger.py – Debugger-Session für ps5debug-NG (ohne GUI).

Eigene TCP-Verbindung (oder die ausgeliehene Haupt-Verbindung) plus der Async-Kanal auf
Port 755, auf dem die PS5 Breakpoint-/Watchpoint-Treffer meldet.

Ablauf wie im PS5 Debug Toolkit (dort läuft er stabil):
  * Der Server verwaltet den Breakpoint-Schritt selbst.  WEITER ist deshalb nur ein einfaches
    CONTINUE - kein manuelles RIP-Zurücksetzen, kein Entfernen/Neusetzen des Breakpoints.
  * Ein Treffer meldet RIP = Breakpoint-Adresse.  Danach werden die LIVE-Register der Konsole
    gelesen; steht der Thread schon weiter ("prestepped"), ist der Befehl bereits gelaufen und
    STEP meldet einfach diesen Zustand (kein zweiter Einzelschritt, der nie ankommen würde).
  * STEP wartet über einen Waiter direkt auf das Step-Ereignis des Rückkanals (max. 8 s).
  * Breakpoints, die während eines Stopps entfernt/abgeschaltet werden, bleiben auf der Konsole
    bis zum nächsten WEITER/STEP ("deferred disarm") - der angehaltene Thread steht sonst
    mitten in einem überschriebenen Befehl.
  * STEP OVER / STEP OUT / RUN TO laufen über temporäre Breakpoints in reservierten Slots.
  * Der Keep-Alive pingt und baut nur auf, solange kein Thread angehalten ist: ein
    Wiederaufbau (Detach/Attach) bei angehaltenem Spiel würde den Stopp zerstören.
"""
import queue
import socket
import threading
import time

from ps5_client import PS5DebugClient, STATUS_SUCCESS
import ps5_ext as X

STEP_TIMEOUT = 8.0           # so lange wartet STEP auf das Step-Ereignis der Konsole
RUN_SLOTS = (28, 29)         # reservierte Breakpoint-Slots für STEP OVER / STEP OUT / RUN TO


class DebugError(RuntimeError):
    pass


class DebugSession:
    def __init__(self, host, port, pid, on_hit=None, on_log=None, listener_port=755, client=None, on_state=None):
        """client: bereits verbundene Haupt-Verbindung ausleihen (wird nie geschlossen).
        Ohne client baut die Session eine eigene Verbindung auf und schliesst sie wieder."""
        self.host, self.port, self.pid = host, port, pid
        self.listener_port = listener_port
        self._borrowed = client
        self.on_hit = on_hit or (lambda hit: None)
        self.on_log = on_log or (lambda msg: None)
        self.on_state = on_state or (lambda state: None)     # 'attached' | 'reconnecting' | 'lost' | 'detached'
        self.keepalive_s = 2.0       # Ping auf der Debug-Verbindung (sonst ist sie nach dem Attach still und bricht ab)
        self.keepalive_misses = 2    # so viele Fehlschlaege in Folge, dann Wiederaufbau
        self.retry_delay = 2.0       # Pause zwischen Detach und erneutem Attach ('bereits debuggt')
        self._ka_stop = threading.Event()
        self._ka_thread = None
        self.reconnects = 0
        self.client = None
        self.listener = None
        self.attached = False
        self.lock = threading.RLock()
        self.bps = {}            # index -> {"addr", "enabled", "orig"}
        self.wps = {}            # index -> {"addr", "size", "type", "enabled"}
        self.hit_counts = {}     # Adresse -> Anzahl
        self.last_hit = None
        self.stopped = {}        # lwpid -> Treffer-Paket (Threads, die noch angehalten sind)
        self.rearm_enabled = True            # nur noch aus Kompatibilität da - der Server macht den Schritt selbst
        self._waiter = None      # queue.Queue, solange STEP auf das Step-Ereignis wartet
        self._temp = None        # {"index","addr","min_rsp","done"}: STEP OVER / OUT / RUN TO
        self._to_clear = {}      # Index -> Adresse: Breakpoints, die erst beim nächsten WEITER entfernt werden
        self._busy = 0           # >0 solange WEITER/STEP/Attach laufen (Keep-Alive pausiert)

    # ------------------------------------------------------------------
    def _release(self, close_client=True):
        """Listener und (eigene) Verbindung freigeben - der Rueckkanal-Port ist danach sofort wieder frei."""
        if self.listener is not None:
            try:
                self.listener.close()
            except Exception:
                pass
            self.listener = None
        if close_client and self.client is not None and self._borrowed is None:
            try:
                self.client.close()
            except Exception:
                pass

    def attach(self):
        with self.lock:
            if self.attached:
                return
            # Zuerst den Rueckkanal binden (die PS5 verbindet sich beim Attach selbst dorthin);
            # ist der Port belegt, wird gar keine Verbindung aufgebaut.
            try:
                self.listener = X.InterruptListener(self._on_packet, port=self.listener_port)
            except OSError as e:
                raise DebugError(f"Port {self.listener_port} nicht verfügbar (Firewall/belegt?): {e}")
            self.listener.start()
            try:
                if self._borrowed is not None:
                    self.client = self._borrowed
                else:
                    self.client = PS5DebugClient(self.host, self.port)
                    self.client.connect()
                    self.client.pid = self.pid
                st = X.dbg_attach(self.client, self.pid)
                if st == X.STATUS_ALREADY_DEBUG:
                    self.on_log("Prozess wird bereits debuggt - alter Zustand wird gelöst, dann neuer Versuch")
                    try:
                        X.dbg_detach(self.client)
                    except Exception as e:
                        self.on_log(f"Detach vor erneutem Attach: {e}")
                    if self.retry_delay:
                        time.sleep(self.retry_delay)         # die Konsole braucht einen Moment zum Aufräumen
                    st = X.dbg_attach(self.client, self.pid)
            except (TimeoutError, socket.timeout) as e:
                self._release()
                raise DebugError("Attach: keine Antwort der PS5 (Zeitüberschreitung) - Windows-Firewall "
                                 f"(Port {self.listener_port}) und Verbindung prüfen: {e}")
            except Exception as e:
                self._release()
                raise DebugError(f"Attach fehlgeschlagen: {e}")
            if st != STATUS_SUCCESS:
                self._release()
                if st == X.STATUS_ALREADY_DEBUG:
                    raise DebugError("Prozess wird bereits debuggt "
                                     "(anderer Client oder alter Zustand)")
                raise DebugError(f"Attach fehlgeschlagen: Status 0x{st:08X}")
            self.attached = True
        self._start_keepalive()
        self.on_state("attached")
        if not self.listener.connected.wait(5.0):
            self.on_log(f"WARNUNG: PS5 hat den Async-Kanal (Port {self.listener_port}) nicht aufgebaut "
                        "- Windows-Firewall prüfen. Treffer werden evtl. nicht angezeigt.")
        self.on_log(f"Attach OK (PID {self.pid})")

    def detach(self):
        self._stop_keepalive()
        with self.lock:
            if not self.attached:
                return
            self._abort_waiter()
            self._drop_temp()
            try:
                self._flush_disarm()                     # aufgeschobene Entfernungen + temporaerer Breakpoint
            except Exception:
                pass
            for idx, b in list(self.bps.items()):
                try:
                    X.dbg_set_breakpoint(self.client, idx, 0, b["addr"])
                except Exception:
                    pass
            for idx, w in list(self.wps.items()):
                try:
                    X.dbg_set_watchpoint(self.client, idx, 0, w["size"], w["type"], w["addr"])
                except Exception:
                    pass
            self._to_clear.clear()
            try:
                X.dbg_detach(self.client)
            except Exception as e:
                self.on_log(f"Detach: {e}")
            self.attached = False
            self.stopped.clear()
            self.bps.clear()
            self.wps.clear()
            self.last_hit = None
            self._release()
        self.on_state("detached")
        self.on_log("Detached")

    # ------------------------------------------------------------------
    # Keep-Alive / Wiederaufbau / Selbsttest
    # ------------------------------------------------------------------
    def _start_keepalive(self):
        self._stop_keepalive()
        self._ka_stop = threading.Event()
        self._ka_thread = threading.Thread(target=self._keepalive_loop, args=(self._ka_stop,), name="dbg-keepalive", daemon=True)
        self._ka_thread.start()

    def _stop_keepalive(self):
        self._ka_stop.set()
        t = self._ka_thread
        if t is not None and t is not threading.current_thread():
            t.join(1.0)
        self._ka_thread = None

    def _quiet(self):
        """True, wenn ein Ping/Wiederaufbau die Konsole nicht stoeren darf (Thread angehalten / Befehl laeuft)."""
        return bool(self.stopped) or self._busy > 0 or self._waiter is not None

    def _keepalive_loop(self, stop):
        misses = 0
        while not stop.wait(self.keepalive_s):
            cl = self.client
            if not self.attached or cl is None:
                return
            if self._quiet():
                misses = 0               # angehaltenes Spiel: kein Ping, schon gar kein Neuaufbau
                continue
            try:
                ok = cl.ping()
            except Exception:
                ok = False
            misses = 0 if ok else misses + 1
            if misses >= self.keepalive_misses:
                misses = 0
                if self._quiet():
                    continue
                if not self._reconnect(stop):
                    return

    def _reconnect(self, stop):
        """Debug-Verbindung weg: eigene Verbindung neu aufbauen, erneut attachen, Breakpoints/Watchpoints wiederherstellen.
        Eine ausgeliehene Haupt-Verbindung kann nicht neu aufgebaut werden (das macht dann der Waechter des Hauptfensters)."""
        if self._borrowed is not None:
            self.on_log("Debug-Verbindung (Haupt-Verbindung) antwortet nicht mehr")
            self.attached = False
            self.on_state("lost")
            return False
        self.on_state("reconnecting")
        self.on_log("Debug-Verbindung antwortet nicht mehr - baue sie neu auf …")
        with self.lock:
            old = self.client
            for attempt in range(1, 4):
                if stop.is_set():
                    return False
                try:
                    cl = PS5DebugClient(self.host, self.port)
                    cl.connect()
                    cl.pid = self.pid
                    st = X.dbg_attach(cl, self.pid)
                    if st == X.STATUS_ALREADY_DEBUG:
                        try:
                            X.dbg_detach(cl)
                        except Exception:
                            pass
                        st = X.dbg_attach(cl, self.pid)
                    if st != STATUS_SUCCESS:
                        raise DebugError(f"Status 0x{st:08X}")
                except Exception as e:
                    self.on_log(f"Wiederaufbau {attempt}/3 fehlgeschlagen: {e}")
                    stop.wait(1.0)
                    continue
                if old is not None:
                    try:
                        old.close()
                    except Exception:
                        pass
                self.client = cl
                for idx, b in list(self.bps.items()):
                    try:
                        X.dbg_set_breakpoint(cl, idx, b.get("enabled", True), b["addr"])
                    except Exception as e:
                        self.on_log(f"Breakpoint {idx} nicht wiederhergestellt: {e}")
                for idx, w in list(self.wps.items()):
                    try:
                        X.dbg_set_watchpoint(cl, idx, w.get("enabled", True), w["size"], w["type"], w["addr"])
                    except Exception as e:
                        self.on_log(f"Watchpoint {idx} nicht wiederhergestellt: {e}")
                self.on_log("Debug-Verbindung wiederhergestellt (neu attached, Breakpoints neu gesetzt)")
                self.on_state("attached")
                self.reconnects += 1             # erst zaehlen, wenn alles wiederhergestellt und gemeldet ist
                return True
            self.attached = False
            self.on_log("Debug-Verbindung konnte nicht wiederhergestellt werden - bitte DETACH und neu attachen")
            self.on_state("lost")
            return False

    def health(self, main_client=None):
        """Selbsttest fuer das Log: antwortet die Debug-Verbindung (und die Haupt-Verbindung), steht der Rueckkanal?"""
        out = {"debug_ping": False, "main_ping": None, "back_channel": bool(self.listener and self.listener.connected.is_set()),
               "reconnects": self.reconnects}
        try:
            out["debug_ping"] = bool(self.client and self.client.ping())
        except Exception:
            pass
        if main_client is not None:
            try:
                out["main_ping"] = bool(main_client.ping())
            except Exception:
                out["main_ping"] = False
        return out

    def _need(self):
        if not self.attached:
            raise DebugError("Nicht attached")

    # ------------------------------------------------------------------
    # Breakpoints / Watchpoints
    # ------------------------------------------------------------------
    def _read_orig(self, addr):
        """Originalbyte unter dem Breakpoint (fuer den Disassembler: der Server liefert dort sonst 0xCC)."""
        try:
            return bytes(self.client.read_memory(addr, 1))
        except Exception:
            return b""

    def set_breakpoint(self, index, addr, enabled=True):
        with self.lock:
            self._need()
            orig = self._read_orig(addr)
            st = X.dbg_set_breakpoint(self.client, index, enabled, addr)
            if st == X.STATUS_INVALID_INDEX:
                raise DebugError(f"Ungültiger Breakpoint-Index (0..{X.MAX_BREAKPOINTS - 1})")
            if st != STATUS_SUCCESS:
                raise DebugError(f"Breakpoint: Status 0x{st:08X}")
            self._to_clear.pop(index, None)
            self.bps[index] = {"addr": addr, "enabled": bool(enabled), "orig": orig if orig != b"\xcc" else b""}

    def set_breakpoint_enabled(self, index, enabled):
        """An/aus. Waehrend eines Stopps wird das Abschalten erst beim naechsten WEITER/STEP ausgefuehrt."""
        with self.lock:
            self._need()
            b = self.bps.get(index)
            if not b:
                return
            if enabled:
                if index in self._to_clear:
                    del self._to_clear[index]
                    b["enabled"] = True
                    return
                st = X.dbg_set_breakpoint(self.client, index, 1, b["addr"])
                if st != STATUS_SUCCESS:
                    raise DebugError(f"Breakpoint: Status 0x{st:08X}")
                b["enabled"] = True
                return
            b["enabled"] = False
            if self.stopped:
                self._to_clear[index] = b["addr"]
            else:
                X.dbg_set_breakpoint(self.client, index, 0, b["addr"])

    def clear_breakpoint(self, index):
        with self.lock:
            b = self.bps.get(index)
            if not b:
                return
            self._need()
            if self.stopped:
                # Thread steht (evtl.) auf diesem Breakpoint - die Konsole raeumt erst beim WEITER auf.
                self._to_clear[index] = b["addr"]
            else:
                X.dbg_set_breakpoint(self.client, index, 0, b["addr"])
            del self.bps[index]

    def _flush_disarm(self):
        """Aufgeschobene Breakpoint-Entfernungen jetzt ausfuehren (vor WEITER / STEP)."""
        pend, self._to_clear = self._to_clear, {}
        for idx, addr in pend.items():
            if idx < 0:
                continue
            try:
                X.dbg_set_breakpoint(self.client, idx, 0, addr)
            except Exception as e:
                self.on_log(f"Breakpoint {idx} (0x{addr:X}) nicht entfernt: {e}")

    def free_bp_index(self):
        for i in range(X.MAX_BREAKPOINTS):
            if i in RUN_SLOTS or i in self.bps or i in self._to_clear:
                continue
            return i
        raise DebugError(f"Keine freien Breakpoint-Slots (max. {X.MAX_BREAKPOINTS - len(RUN_SLOTS)})")

    def bp_overrides(self):
        """{Adresse: Originalbyte} - damit ein Disassembler nicht das 0xCC des Breakpoints sieht."""
        return {b["addr"]: b["orig"] for b in self.bps.values() if b.get("orig")}

    def set_watchpoint(self, index, addr, size, breaktype, enabled=True):
        with self.lock:
            self._need()
            st = X.dbg_set_watchpoint(self.client, index, enabled, size, breaktype, addr)
            if st == X.STATUS_INVALID_INDEX:
                raise DebugError("Ungültiger Watchpoint-Index (0..3)")
            if st != STATUS_SUCCESS:
                raise DebugError(f"Watchpoint: Status 0x{st:08X}")
            self.wps[index] = {"addr": addr, "size": size, "type": breaktype,
                               "enabled": bool(enabled)}

    def clear_watchpoint(self, index):
        with self.lock:
            w = self.wps.get(index)
            if not w:
                return
            self._need()
            X.dbg_set_watchpoint(self.client, index, 0, w["size"], w["type"], w["addr"])
            del self.wps[index]

    def free_wp_index(self):
        for i in range(X.MAX_WATCHPOINTS):
            if i not in self.wps:
                return i
        raise DebugError("Keine freien Watchpoint-Slots (max. 4)")

    # ------------------------------------------------------------------
    # Threads / Register
    # ------------------------------------------------------------------
    def threads(self):
        with self.lock:
            self._need()
            out = []
            for t in X.dbg_thread_list(self.client):
                try:
                    out.append(X.dbg_thread_info(self.client, t))
                except Exception:
                    out.append({"lwpid": t, "priority": 0, "name": "?"})
            return out

    def regs(self, lwpid):
        with self.lock:
            self._need()
            return X.parse_regs(X.dbg_get_regs_raw(self.client, lwpid))

    def set_reg(self, lwpid, name, value):
        with self.lock:
            self._need()
            r = X.parse_regs(X.dbg_get_regs_raw(self.client, lwpid))     # frisch von der Konsole (nicht aus dem Treffer-Paket)
            if name not in r:
                raise DebugError(f"Unbekanntes Register: {name}")
            r[name] = value & 0xFFFFFFFFFFFFFFFF
            X.dbg_set_regs_raw(self.client, lwpid, X.pack_regs(r))
            hit = self.stopped.get(lwpid)
            if hit is not None:
                hit["live_regs"] = r

    def stack(self, lwpid, depth=32):
        with self.lock:
            self._need()
            r = X.parse_regs(X.dbg_get_regs_raw(self.client, lwpid))
            return X.read_stack(self.client, r["rbp"], r["rsp"], depth)

    # ------------------------------------------------------------------
    # Ausführung
    # ------------------------------------------------------------------
    def _bp_at(self, rip):
        """Aktiver Breakpoint genau an dieser Adresse (der Server meldet RIP = Breakpoint-Adresse)."""
        for idx, b in self.bps.items():
            if b["enabled"] and b["addr"] == rip:
                return idx, b["addr"]
        return None

    def _bp_at_hit(self, hit):
        """Breakpoint zu einem Treffer: erst exakt (RIP == Adresse), dann - fuer Server, die RIP hinter dem
        0xCC melden - RIP-1.  Temporaere Run-To-Breakpoints zaehlen hier nicht."""
        rip = hit["regs"]["rip"]
        bp = self._bp_at(rip)
        if bp:
            return bp
        if hit.get("signal") == 5:
            for idx, b in self.bps.items():
                if b["enabled"] and b["addr"] == rip - 1:
                    return idx, b["addr"]
        return None

    def _begin(self):
        self._busy += 1

    def _end(self):
        self._busy = max(0, self._busy - 1)

    def _go(self):
        """Gemeinsamer Teil von WEITER: Stopp-Zustand verwerfen, aufgeschobene Entfernungen ausfuehren, CONTINUE."""
        self._flush_disarm()
        self.last_hit = None
        self.stopped.clear()
        st = X.dbg_continue(self.client, 0)
        if st != STATUS_SUCCESS:
            raise DebugError(f"Continue: Status 0x{st:08X}")

    def resume(self):
        with self.lock:
            self._need()
            self._begin()
            try:
                self._drop_temp()
                self._go()
            finally:
                self._end()

    def _drop_temp(self):
        t, self._temp = self._temp, None
        if t is not None:
            self._to_clear[t["index"]] = t["addr"]

    def _live_hit(self, hit, kind="STEP"):
        """Treffer-Paket aus dem aktuellen (Live-)Zustand des Threads - fuer 'prestepped' und STEP."""
        regs = self.regs(hit["lwpid"])
        pkt = dict(hit)
        pkt["regs"] = regs
        pkt["kind"], pkt["index"], pkt["addr"] = kind, None, regs["rip"]
        pkt["prestepped"] = False
        pkt["time"] = time.time()
        pkt["count"] = self.hit_counts.get(regs["rip"], 0)
        return pkt

    def _announce(self, pkt):
        self.last_hit = pkt
        self.stopped[pkt["lwpid"]] = pkt
        self.on_hit(pkt)

    def step(self):
        """Ein Befehl weiter (Step Into)."""
        with self.lock:
            self._need()
            self._begin()
            try:
                self._drop_temp()
                hit = self.last_hit
                if hit is not None and hit.get("prestepped"):
                    # Die Konsole hat den Befehl schon ausgefuehrt: der Zustand 'nach dem Schritt' ist der Live-Zustand.
                    self._flush_disarm()
                    self._announce(self._live_hit(hit))
                    return
                self._flush_disarm()
                waiter = self._arm_waiter()
                try:
                    if hit is not None:
                        st = X.dbg_step_thread(self.client, hit["lwpid"])
                    else:
                        st = X.dbg_step(self.client)
                except Exception:
                    self._abort_waiter()
                    raise
                if st != STATUS_SUCCESS:
                    self._abort_waiter()
                    raise DebugError(f"Step: Status 0x{st:08X}")
                self.last_hit = None
                self.stopped.clear()
            finally:
                self._end()
        # ausserhalb des Locks warten: der Listener-Thread braucht ihn, um das Ereignis zu verarbeiten
        self._begin()
        try:
            try:
                pkt = waiter.get(timeout=STEP_TIMEOUT)
            except queue.Empty:
                self._abort_waiter()
                raise DebugError("Nach dem Step kam kein Stopp-Ereignis zurück. Die Konsole verbindet sich auf "
                                 f"Port {self.listener_port} dieses PCs - Firewall prüfen. "
                                 "Die Konsole steppt nur ein Spiel, das an einem Ereignis angehalten ist.")
        finally:
            self._end()
        with self.lock:
            pkt["kind"], pkt["index"], pkt["addr"] = "STEP", None, pkt["regs"]["rip"]
            pkt["time"] = time.time()
            self.hit_counts[pkt["addr"]] = self.hit_counts.get(pkt["addr"], 0) + 1
            pkt["count"] = self.hit_counts[pkt["addr"]]
            pkt["prestepped"] = False
            self._announce(pkt)

    def _arm_waiter(self):
        self._waiter = queue.Queue()
        return self._waiter

    def _abort_waiter(self):
        self._waiter = None

    def halt(self):
        with self.lock:
            self._need()
            st = X.dbg_continue(self.client, 1)
            if st != STATUS_SUCCESS:
                raise DebugError(f"Stop: Status 0x{st:08X}")

    # ---- Step Over / Step Out / Run To (temporaere Breakpoints) ----
    def _decode_at(self, hit):
        """(Adresse, Laenge, Mnemonic) des Befehls an RIP - mit den Originalbytes unter Breakpoints."""
        import asm_tools
        rip = hit["regs"]["rip"]
        data = bytearray(self.client.read_memory(rip, 16))
        for a, ob in self.bp_overrides().items():
            if rip <= a < rip + len(data):
                data[a - rip] = ob[0]
        ins, _pos = asm_tools.disassemble(bytes(data), rip)
        if not ins:
            raise DebugError("Befehl an RIP nicht lesbar")
        i = ins[0]
        return (i["addr"], i["size"], i["mnemonic"])

    def step_over(self):
        """Wie STEP, aber ein CALL wird komplett ausgefuehrt (temporaerer Breakpoint hinter dem Aufruf)."""
        with self.lock:
            self._need()
            hit = self.last_hit
            if hit is None:
                raise DebugError("Das Spiel läuft - erst anhalten (oder an einem Breakpoint stoppen)")
            if not hit.get("prestepped"):
                try:
                    _a, size, mnem = self._decode_at(hit)
                except Exception as e:
                    self.on_log(f"Step Over: Befehl nicht entschluesselbar ({e}) - normaler Step")
                    mnem, size = "", 0
                if mnem.lower().startswith("call"):
                    self._run_to_locked(hit["regs"]["rip"] + size, hit["regs"]["rsp"])
                    return
        self.step()

    def step_out(self):
        """Bis zur Rueckkehr in den Aufrufer (ueber die RBP-Kette)."""
        with self.lock:
            self._need()
            hit = self.last_hit
            if hit is None:
                raise DebugError("Das Spiel läuft - erst anhalten (oder an einem Breakpoint stoppen)")
            regs = self.regs(hit["lwpid"])
            frames = X.read_stack(self.client, regs["rbp"], regs["rsp"], 4)
            ret = next((f["ret"] for f in frames if f.get("ret")), 0)
            if not ret:
                raise DebugError("Step Out: keine Rücksprungadresse (Funktion ohne Frame-Pointer?) - "
                                 "STACK-SCAN benutzen und 'Bis hierher' auf die Rücksprungadresse")
            self._run_to_locked(ret, regs["rbp"] + 16 if regs["rbp"] else 0)

    def run_to(self, addr, min_rsp=0):
        with self.lock:
            self._need()
            self._run_to_locked(addr, min_rsp)

    def _run_to_locked(self, addr, min_rsp):
        self._begin()
        try:
            self._drop_temp()
            busy = set(self._to_clear)
            slot = next((s for s in RUN_SLOTS if s not in busy and s not in self.bps), None)
            if slot is None:
                raise DebugError("Temporäre Breakpoint-Slots belegt - einmal WEITER drücken und erneut versuchen")
            self._flush_disarm()
            st = X.dbg_set_breakpoint(self.client, slot, 1, addr)
            if st != STATUS_SUCCESS:
                raise DebugError(f"Temporärer Breakpoint: Status 0x{st:08X}")
            self._temp = {"index": slot, "addr": addr, "min_rsp": min_rsp, "done": False}
            self._go()
        finally:
            self._end()

    # ------------------------------------------------------------------
    # Async-Kanal
    # ------------------------------------------------------------------
    def _classify(self, pkt):
        regs = pkt["regs"]
        dr6 = pkt["dbregs"][6]
        bp = self._bp_at_hit(pkt)
        if bp:
            return "BP", bp[0], bp[1]
        for i in range(4):
            if dr6 & (1 << i) and i in self.wps:
                return "WP", i, self.wps[i]["addr"]
        if pkt["signal"] == 5:
            return "STEP", None, regs["rip"]
        return f"SIG{pkt['signal']}", None, regs["rip"]

    def _on_packet(self, pkt):
        with self.lock:
            w = self._waiter
            if w is not None:                       # STEP wartet genau auf dieses Ereignis
                self._waiter = None
                w.put(pkt)
                return
            tmp = self._temp
            rip = pkt["regs"]["rip"]
            # Temporaerer Breakpoint (STEP OVER/OUT, RUN TO): in tieferer Rekursion einfach weiterlaufen
            if tmp is not None and rip == tmp["addr"] and not self._bp_at(rip) \
                    and tmp["min_rsp"] and pkt["regs"]["rsp"] < tmp["min_rsp"]:
                try:
                    X.dbg_continue(self.client, 0)
                except Exception as e:
                    self.on_log(f"Weiter nach Run-To: {e}")
                return
            kind, idx, addr = self._classify(pkt)
            if tmp is not None and rip == tmp["addr"] and not self._bp_at(rip):
                kind, idx, addr = "STEP", None, rip          # Ziel von STEP OVER / OUT / RUN TO erreicht
                tmp["done"] = True
            pkt["kind"], pkt["index"], pkt["addr"] = kind, idx, addr
            pkt["time"] = time.time()
            self.hit_counts[addr] = self.hit_counts.get(addr, 0) + 1
            pkt["count"] = self.hit_counts[addr]
            pkt["prestepped"] = False
            pkt["live_regs"] = None
            # Live-Zustand lesen: steht der Thread schon hinter dem gemeldeten RIP, hat die Konsole den Befehl bereits ausgefuehrt
            try:
                live = X.parse_regs(X.dbg_get_regs_raw(self.client, pkt["lwpid"]))
                pkt["live_regs"] = live
                if kind in ("BP", "WP") and live["rip"] != rip:
                    pkt["prestepped"] = True
                    self.on_log(f"Konsole hat den Befehl schon ausgeführt (Thread steht bei 0x{live['rip']:X}) - "
                                "Step geht von dort weiter")
            except Exception as e:
                self.on_log(f"Live-Register Thread {pkt['lwpid']}: {e}")
            self.last_hit = pkt
            self.stopped[pkt["lwpid"]] = pkt
        self.on_hit(pkt)
