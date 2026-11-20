"""tools_debug_gui.py – Debugger-Tab für das Werkzeug-Fenster."""
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import debug_guide as DG
import hit_context as HC
import hit_targets as TG
import ps5_ext as X
from debugger import DebugSession
from disasm_view import DisasmView
from tools_common import (BG, BG_CARD, ACCENT, ERROR, TEXT, TEXT_DIM, WARN, FONT_MONO, FONT_LABEL, BaseTab, button, label,
                          entry, tree, with_scroll)

WP_TYPES = {"schreiben": X.WP_WRITE, "lesen/schreiben": X.WP_RDWR, "ausführen": X.WP_EXEC}


_AUTO = object()                # _fill_regs: 'vergleiche mit dem, was zuletzt fuer diesen Thread gezeigt wurde'


class DebugTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.sess = None
        self.hit_items = {}          # iid -> hit-Paket
        self._ctx_token = 0          # nur die zuletzt angeforderte Kontext-Ansicht wird gezeigt
        self._ctx_cache = {}         # iid -> Kontext (Klick auf einen alten Treffer liest nichts neu)
        self._shown_regs = {}        # lwpid -> zuletzt gezeigte Register (fuer die Hervorhebung geaenderter)
        self.book = TG.TargetBook()  # Ziele (Objekte), die der Befehl bei den Treffern angefasst hat
        self.only_ea = None          # Filter: nur Treffer auf dieses Ziel zeigen, alle anderen laufen automatisch weiter
        self._insn_cache = {}        # (Art, RIP) -> Befehlszeile: damit der Filter ohne Speicherlesen entscheiden kann
        self._target_iid = {}        # Zieladresse -> iid in der ZIELE-Tabelle

        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 4))
        button(top, "ATTACH", self.attach, accent=True).pack(side="left", padx=2)
        button(top, "DETACH", self.detach).pack(side="left", padx=2)
        self.lbl = label(top, "nicht attached"); self.lbl.pack(side="left", padx=12)

        self.lbl_guide = tk.Label(self, text="", bg=BG_CARD, fg=ACCENT, anchor="w", justify="left", wraplength=1100,
                                  font=FONT_LABEL, padx=8, pady=4)
        self.lbl_guide.pack(fill="x", padx=8, pady=(0, 4))

        run = tk.Frame(self, bg=BG); run.pack(fill="x", padx=8, pady=2)
        button(run, "▶ WEITER", lambda: self._do(lambda: self.sess.resume()), accent=True).pack(side="left", padx=2)
        button(run, "⤵ STEP", lambda: self._do(lambda: self.sess.step())).pack(side="left", padx=2)
        button(run, "⤼ STEP OVER", lambda: self._do(lambda: self.sess.step_over())).pack(side="left", padx=2)
        button(run, "⤴ STEP OUT", lambda: self._do(lambda: self.sess.step_out())).pack(side="left", padx=2)
        button(run, "■ ANHALTEN", lambda: self._do(lambda: self.sess.halt())).pack(side="left", padx=2)
        label(run, "THREAD").pack(side="left", padx=(16, 4))
        self.v_thr = tk.StringVar()
        self.cb_thr = ttk.Combobox(run, textvariable=self.v_thr, width=26, state="readonly")
        self.cb_thr.pack(side="left")
        self.cb_thr.bind("<<ComboboxSelected>>", lambda _e: self.refresh_regs())
        button(run, "THREADS", self.refresh_threads).pack(side="left", padx=2)
        button(run, "REGISTER", self.refresh_regs).pack(side="left", padx=2)
        button(run, "STACK", self.show_stack).pack(side="left", padx=2)
        button(run, "STACK-SCAN", self.show_stack_scan).pack(side="left", padx=2)

        mid = tk.Frame(self, bg=BG); mid.pack(fill="both", expand=True, padx=8, pady=4)
        left = tk.Frame(mid, bg=BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(mid, bg=BG); right.pack(side="left", fill="both", padx=(8, 0))

        # Breakpoints
        row = tk.Frame(left, bg=BG); row.pack(fill="x")
        label(row, "BREAKPOINT @").pack(side="left")
        self.v_bp = tk.StringVar()
        entry(row, self.v_bp, 20).pack(side="left", padx=8)
        button(row, "SETZEN", self.add_bp, accent=True).pack(side="left", padx=2)
        button(row, "ENTFERNEN", self.del_bp).pack(side="left", padx=2)
        self.bpt = tree(left, [("i", "#"), ("a", "ADRESSE"), ("o", "OFFSET"), ("on", "AN")],
                        [40, 170, 100, 50], height=3)
        self.bpt.pack(fill="x", pady=(2, 8))

        # Watchpoints
        row = tk.Frame(left, bg=BG); row.pack(fill="x")
        label(row, "WATCHPOINT @").pack(side="left")
        self.v_wp = tk.StringVar()
        entry(row, self.v_wp, 20).pack(side="left", padx=8)
        self.v_wsize = tk.StringVar(value="4")
        ttk.Combobox(row, textvariable=self.v_wsize, values=["1", "2", "4", "8"],
                     width=3, state="readonly").pack(side="left")
        self.v_wtype = tk.StringVar(value="schreiben")
        ttk.Combobox(row, textvariable=self.v_wtype, values=list(WP_TYPES), width=14,
                     state="readonly").pack(side="left", padx=4)
        button(row, "SETZEN", self.add_wp, accent=True).pack(side="left", padx=2)
        button(row, "ENTFERNEN", self.del_wp).pack(side="left", padx=2)
        self.wpt = tree(left, [("i", "#"), ("a", "ADRESSE"), ("s", "GRÖSSE"), ("t", "TYP")],
                        [40, 170, 70, 130], height=3)
        self.wpt.pack(fill="x", pady=(2, 8))

        # Treffer
        label(left, "TREFFER (Klick = Register dieses Treffers)").pack(anchor="w")
        fr = tk.Frame(left, bg=BG); fr.pack(fill="x")
        self.hits = tree(fr, [("t", "ZEIT"), ("k", "ART"), ("a", "ADRESSE"), ("th", "THREAD"), ("n", "ANZAHL"),
                              ("z", "ZIEL"), ("w", "WERT"), ("ins", "BEFEHL")],
                         [74, 56, 150, 62, 62, 130, 90, 260], height=4)
        with_scroll(fr, self.hits)
        self.hits.bind("<<TreeviewSelect>>", self._hit_sel)
        self.hits.tag_configure("newt", foreground=ACCENT)                 # neues Ziel (anderes Objekt als bisher)
        self.hits.tag_configure("chg", foreground=WARN)                    # gleiches Ziel, anderer Wert als beim letzten Mal

        # Ziele: gleicher Befehl, aber verschiedene Objekte (du, Gegner A, Gegner B ...)
        label(left, "ZIELE (eine Zeile pro Objekt - so findest du die HP-Leiste, die nur dich betrifft)").pack(
            anchor="w", pady=(8, 2))
        trow = tk.Frame(left, bg=BG); trow.pack(fill="x")
        button(trow, "NUR DIESES ZIEL", self.filter_target, accent=True).pack(side="left", padx=2)
        button(trow, "ALLE ZEIGEN", self.filter_off).pack(side="left", padx=2)
        button(trow, "DAS BIN ICH", self.mark_me).pack(side="left", padx=2)
        button(trow, "WATCH AUF ZIEL", self.watch_target).pack(side="left", padx=2)
        button(trow, "LEEREN", self.clear_targets).pack(side="left", padx=2)
        self.v_auto = tk.BooleanVar(value=False)
        tk.Checkbutton(trow, text="AUTO-WEITER", variable=self.v_auto, bg=BG, fg=TEXT_DIM, selectcolor=BG_CARD,
                       activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL).pack(side="left", padx=8)
        label(trow, "MEIN WERT").pack(side="left", padx=(8, 2))
        self.v_myval = tk.StringVar()
        entry(trow, self.v_myval, 9).pack(side="left")
        button(trow, "FINDEN", self.find_mine).pack(side="left", padx=2)
        self.lbl_filter = label(left, "")
        self.lbl_filter.pack(anchor="w")
        self.tgt = tree(left, [("l", "Z"), ("a", "ZIEL-ADRESSE"), ("o", "OBJEKT"), ("v", "WERT"), ("p", "VORHER"),
                               ("d", "Δ"), ("h", "TREFFER"), ("c", "ÄNDERUNGEN"), ("m", "")],
                        [44, 140, 140, 90, 90, 70, 64, 90, 50], height=4)
        self.tgt.pack(fill="x", pady=(2, 0))
        self.tgt.tag_configure("me", foreground=ACCENT, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self.tgt.tag_configure("match", foreground=WARN)
        self.tgt.tag_configure("live", foreground=WARN)

        # Kontext: Befehle rund um den Treffer, Schreiber und RIP markiert
        label(left, "KONTEXT (Befehle um den Treffer - grün = Schreiber, gelb = RIP)").pack(anchor="w", pady=(8, 2))
        self.ctxv = DisasmView(left, on_open=self._ctx_open, on_preset=self._ctx_preset, height=8)
        self.ctxv.pack(fill="both", expand=True)
        self.lbl_explain = tk.Label(left, text="", bg=BG, fg=TEXT, anchor="w", justify="left", wraplength=700,
                                    font=FONT_LABEL)
        self.lbl_explain.pack(fill="x", pady=(4, 0))
        self._guide()

        # Register
        label(right, "REGISTER (Doppelklick = ändern, gelb = geändert)").pack(anchor="w")
        self.regs = tree(right, [("r", "REG"), ("v", "WERT"), ("o", "VORHER")], [64, 150, 150], height=20)
        self.regs.pack(fill="y", expand=True)
        self.regs.tag_configure("chg", foreground=WARN, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self.regs.bind("<Double-1>", self._edit_reg)
        self.lbl_stack = label(right, "")

    # ---- Hilfen ----
    def _guide(self):
        """Hilfezeile oben: was ist als Naechstes zu tun (fuer Einsteiger)."""
        try:
            n_t = len(self.book.groups) if hasattr(self.book, "groups") else 0
            text = DG.next_step(self.sess is not None, len(getattr(self.sess, "bps", {}) or {}),
                                len(getattr(self.sess, "wps", {}) or {}), len(self.hit_items), n_t)
            self.lbl_guide.configure(text=text)
        except Exception:  # noqa: BLE001
            pass

    def _need(self):
        if not self.sess or not self.sess.attached:
            self.log("Erst ATTACH", "warn")
            return False
        return True

    def _do(self, fn):
        if not self._need():
            return
        self.bg(fn, lambda _r: None)

    def _lwp(self):
        t = self.v_thr.get()
        return int(t.split()[0]) if t else None

    # ---- Attach / Detach ----
    def attach(self):
        if self.sess and self.sess.attached:
            return self.log("Schon attached", "warn")
        be = self.win.app.backend
        if be.pid is None:
            return self.log("Haupt-Fenster nicht verbunden", "err")
        if not messagebox.askyesno(
                "Debugger", "Debugger an das Spiel hängen?\n\n• Das Spiel kann dabei kurz hängen.\n"
                            "• Windows-Firewall muss eingehend Port 755 erlauben.\n"
                            "• Beim Beenden bitte DETACH benutzen."):
            return
        sess = DebugSession(be.host, be.port, be.pid, on_hit=self._on_hit_thread,
                            on_log=lambda m: self.win.ui(lambda: self.log(m, "info")),
                            on_state=lambda st: self.win.ui(lambda: self._state(st)))
        self.win.app.debug_busy = True            # Waechter des Hauptfensters pausiert, solange attached wird / attached ist

        def job():
            sess.attach()
            return sess

        def failed(e):
            self.win.app.debug_busy = False
            self.log(str(e), "err")
        self.bg(job, self._attached, failed)

    def _state(self, st):
        """Rueckmeldungen der Session (Keep-Alive / Wiederaufbau) ins Label."""
        self._notify_state(st)
        if st == "attached" and self.sess is not None:
            self.lbl.configure(text=f"attached  PID {self.sess.pid}", fg=ACCENT)
        elif st == "reconnecting":
            self.lbl.configure(text="Verbindung wird neu aufgebaut …", fg=TEXT_DIM)
        elif st == "lost":
            self.win.app.debug_busy = False
            self.lbl.configure(text="Verbindung verloren - DETACH, dann neu attachen", fg=ERROR)
        elif st == "detached":
            self.win.app.debug_busy = False

    def _notify_state(self, st):
        """Debugger-Zustand auf dem PS5-Bildschirm melden (ps5_notify.py; Fehler bleiben folgenlos)."""
        try:
            pid = self.sess.pid if self.sess is not None else getattr(self.win.app.backend, "pid", None)
            self.win.app.notifier.debugger(st, pid)
        except Exception:  # noqa: BLE001
            pass

    def _attached(self, sess):
        self.sess = sess
        self.clear_targets()
        self.lbl.configure(text=f"attached  PID {sess.pid}", fg=ACCENT)
        self._guide()
        self.refresh_threads()
        self._self_test(0.5)
        self._self_test(3.0)

    def _self_test(self, delay):
        """Nach dem Attach zweimal pruefen und ins Log schreiben, welche Verbindung antwortet (Diagnose bei Abbruechen)."""
        def run():
            time.sleep(delay)
            s = self.sess
            if not s or not s.attached:
                return None
            return s.health(getattr(self.win.app.backend, "client", None))

        def show(h):
            if h is None:
                return
            self.log("Selbsttest: Debug-Verbindung " + ("OK" if h["debug_ping"] else "ANTWORTET NICHT")
                     + ", Haupt-Verbindung " + {True: "OK", False: "ANTWORTET NICHT", None: "-"}[h["main_ping"]]
                     + ", Rueckkanal " + ("steht" if h["back_channel"] else "fehlt (Firewall Port 755?)")
                     + (f", {h['reconnects']}x neu aufgebaut" if h["reconnects"] else ""),
                     "info" if h["debug_ping"] and h["main_ping"] is not False else "err")
        self.bg(run, show)

    def detach(self):
        s = self.sess
        if not s:
            return
        self.win.app.debug_busy = False
        self.bg(s.detach, lambda _r: (self.lbl.configure(text="nicht attached", fg=TEXT_DIM),
                                      self.bpt.delete(*self.bpt.get_children()),
                                      self.wpt.delete(*self.wpt.get_children()),
                                      self.lbl_guide.configure(text=DG.next_step(False))))

    def shutdown(self):
        if self.sess and self.sess.attached:
            try:
                self.sess.detach()
            except Exception:
                pass

    # ---- Breakpoints ----
    def add_bp(self):
        if not self._need():
            return
        try:
            a = self.addr(self.v_bp.get())
            idx = self.sess.free_bp_index()
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(lambda: self.sess.set_breakpoint(idx, a), lambda _r: self._fill_bps())

    def del_bp(self):
        sel = self.bpt.selection()
        if not sel or not self._need():
            return
        idx = int(self.bpt.item(sel[0], "values")[0])
        self.bg(lambda: self.sess.clear_breakpoint(idx), lambda _r: self._fill_bps())

    def _fill_bps(self):
        self.bpt.delete(*self.bpt.get_children())
        for i, b in sorted(self.sess.bps.items()):
            self.bpt.insert("", "end", values=(i, f"{b['addr']:016X}", f"+{b['addr'] - self.base:X}",
                                               "ja" if b["enabled"] else "nein"))
        self._guide()

    # ---- Watchpoints ----
    def add_wp(self):
        if not self._need():
            return
        try:
            a = self.addr(self.v_wp.get())
            idx = self.sess.free_wp_index()
            size = int(self.v_wsize.get())
            typ = WP_TYPES[self.v_wtype.get()]
            if typ == X.WP_EXEC:
                size = 1                      # x86: Ausführungs-Watchpoints sind immer 1 Byte
            if a % size:
                raise ValueError(f"Adresse {a:#x} muss auf {size} Byte ausgerichtet sein (Hardware-Watchpoint)")
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(lambda: self.sess.set_watchpoint(idx, a, size, typ), lambda _r: self._fill_wps())

    def del_wp(self):
        sel = self.wpt.selection()
        if not sel or not self._need():
            return
        idx = int(self.wpt.item(sel[0], "values")[0])
        self.bg(lambda: self.sess.clear_watchpoint(idx), lambda _r: self._fill_wps())

    def _fill_wps(self):
        self.wpt.delete(*self.wpt.get_children())
        names = {v: k for k, v in WP_TYPES.items()}
        for i, w in sorted(self.sess.wps.items()):
            self.wpt.insert("", "end", values=(i, f"{w['addr']:016X}", w["size"], names.get(w["type"], "?")))
        self._guide()

    # ---- Treffer (kommen aus dem Listener-Thread) ----
    def _on_hit_thread(self, hit):
        if self._filtered_out(hit):
            return
        try:
            self.win.app.notifier.hit(hit["kind"], hit["addr"])
        except Exception:  # noqa: BLE001
            pass
        self.win.ui(lambda: self._show_hit(hit))

    def _show_hit(self, hit):
        iid = self.hits.insert("", 0, values=(
            time.strftime("%H:%M:%S", time.localtime(hit["time"])), hit["kind"],
            f"{hit['addr']:016X}", hit["lwpid"], hit["count"], ""))
        self.hit_items[iid] = hit
        self._trim_hits()
        self.hits.selection_set(iid)
        self._fill_regs(hit["regs"], prev=self._prev_hit_regs(iid), lwp=hit["lwpid"])
        self._load_context(hit, iid)
        self.log(f"{hit['kind']} @ {hit['addr']:#x}  Thread {hit['lwpid']}  (#{hit['count']})", "warn")
        self._guide()
        self.refresh_threads(select=hit["lwpid"])

    def _trim_hits(self, keep=300):
        """Bei AUTO-WEITER kommen viele Treffer: nur die letzten `keep` behalten."""
        rows = self.hits.get_children()
        for iid in rows[keep:]:
            self.hits.delete(iid)
            self.hit_items.pop(iid, None)
            self._ctx_cache.pop(iid, None)

    def _hit_sel(self, _e):
        sel = self.hits.selection()
        if sel and sel[0] in self.hit_items:
            hit = self.hit_items[sel[0]]
            self._fill_regs(hit["regs"], prev=self._prev_hit_regs(sel[0]), lwp=hit["lwpid"])
            self._load_context(hit, sel[0])

    def _prev_hit_regs(self, iid):
        """Register des Treffers davor (gleicher Thread; die Liste ist neueste zuerst) - oder None."""
        rows = list(self.hits.get_children())
        me = self.hit_items.get(iid)
        if me is None or iid not in rows:
            return None
        for other in rows[rows.index(iid) + 1:]:
            h = self.hit_items.get(other)
            if h and h["lwpid"] == me["lwpid"]:
                return h["regs"]
        return None

    # ---- Kontext-Ansicht ----
    def _wp_info(self, hit):
        """Der ausgeloeste Watchpoint (Adresse, Groesse, Art) - bestimmt, ob RIP HINTER dem Zugriff steht."""
        w = self.sess.wps.get(hit.get("index")) if self.sess and hit.get("kind") == "WP" else None
        if not w:
            return None
        access = {X.WP_WRITE: "write", X.WP_RDWR: "rw", X.WP_EXEC: "exec"}.get(w["type"], "rw")
        return {"addr": w["addr"], "size": w["size"], "access": access}

    def _load_context(self, hit, iid=None):
        cached = self._ctx_cache.get(iid)
        self._ctx_token += 1
        tok = self._ctx_token
        if cached:
            return self.ctxv.show(cached)
        read, wp = self.win.read_code, self._wp_info(hit)
        self.ctxv.show_message("Lese Befehle um den Treffer …")

        def ok(ctx):
            if iid is not None and self.hits.exists(iid):
                self._ctx_cache[iid] = ctx
                self.hits.set(iid, "ins", HC.describe(ctx))
                self._note_target(hit, ctx, iid)
            if tok == self._ctx_token:
                self.ctxv.show(ctx)
                try:
                    from tools_i18n import lang as _lang
                    self.lbl_explain.configure(text=DG.explain_hit(ctx, _lang()))
                except Exception:  # noqa: BLE001
                    pass
            self._auto_continue(hit)

        def err(e):
            if iid is not None and self.hits.exists(iid):
                self.hits.set(iid, "ins", "?")
            if tok == self._ctx_token:
                self.ctxv.show_message(f"Kontext nicht lesbar: {e}")
            self._auto_continue(hit)
        self.bg(lambda: HC.build_context(read, hit, wp), ok, err)

    def _ctx_open(self, line):
        """Im Disassembler-Tab öffnen - ab dem Anfang des Kontexts, die gewählte Zeile ist dort markiert."""
        start = self.ctxv.lines[0]["addr"] if self.ctxv.lines else line["addr"]
        self.win.goto_disasm(start, focus=line["addr"], marks=self.ctxv.marks)

    def _ctx_preset(self, line):
        self.win.t_dis.recipe_at(line["addr"], f"{line['mnemonic']} {line['op_str']}".strip())

    # ---- Ziele: gleicher Befehl, verschiedene Objekte ----
    def _note_target(self, hit, ctx, iid):
        """Ziel eines Treffers in Trefferliste und ZIELE-Tabelle eintragen; Befehl fuer den Filter merken."""
        insn, t = ctx.get("insn"), ctx.get("target")
        if insn is not None and hit.get("kind") in ("BP", "WP"):
            self._insn_cache[(hit["kind"], hit["regs"]["rip"])] = insn
        if not t:
            return
        g, is_new, changed = self.book.add(t, t.get("value"), insn=t.get("writer"), when=hit.get("time"))
        self.hits.set(iid, "z", f"{g['label']}  {t['ea']:X}")
        self.hits.set(iid, "w", TG.format_value(t.get("value"), t["width"]))
        tag = "newt" if is_new else ("chg" if changed else None)
        if tag:
            self.hits.item(iid, tags=(tag,))
        self._fill_targets()
        self._guide()

    def _filtered_out(self, hit):
        """True = Treffer gehoert zu einem anderen Ziel als dem gewaehlten: nicht zeigen, Spiel laeuft sofort weiter."""
        want = self.only_ea
        if want is None or hit.get("kind") not in ("BP", "WP"):
            return False
        insn = self._insn_cache.get((hit["kind"], hit["regs"]["rip"]))
        t = TG.target_of(insn, hit["regs"]) if insn else None
        if t is None or t["ea"] == want:                      # unbekannt oder das gesuchte Ziel: ganz normal zeigen
            return False
        self.book.skipped += 1
        self.win.ui(self._show_filter_label)
        self._resume_async()
        return True

    def _resume_async(self):
        sess = self.sess

        def run():
            try:
                if sess and sess.attached:
                    sess.resume()
            except Exception as e:  # noqa: BLE001
                self.win.ui(lambda: self.log(f"Auto-Weiter: {e}", "err"))
        threading.Thread(target=run, daemon=True).start()

    def _auto_continue(self, hit):
        """AUTO-WEITER: nach dem Eintragen des Treffers das Spiel selbst weiterlaufen lassen."""
        if self.v_auto.get() and self.sess and self.sess.attached and hit.get("kind") in ("BP", "WP"):
            self._resume_async()

    def _sel_group(self):
        sel = self.tgt.selection()
        if not sel:
            self.log("Erst eine Zeile in ZIELE wählen", "warn")
            return None
        return self.book.groups.get(self._target_iid.get(sel[0]))

    def _show_filter_label(self):
        if self.only_ea is None:
            self.lbl_filter.configure(text="", fg=TEXT_DIM)
            return
        g = self.book.groups.get(self.only_ea)
        self.lbl_filter.configure(
            text=f"FILTER AKTIV: nur {g['label'] if g else ''} @ {self.only_ea:X} - {self.book.skipped} andere Treffer "
                 f"übersprungen", fg=ACCENT)

    def filter_target(self):
        g = self._sel_group()
        if g is None:
            return
        self.only_ea = g["ea"]
        self.book.skipped = 0
        self._show_filter_label()
        self.log(f"Filter: nur Ziel {g['label']} @ {g['ea']:#x} - Treffer auf andere Objekte laufen automatisch weiter", "info")

    def filter_off(self):
        self.only_ea = None
        self._show_filter_label()

    def mark_me(self):
        g = self._sel_group()
        if g is not None:
            self.book.toggle_me(g["ea"])
            self._fill_targets()

    def watch_target(self):
        """Schreib-Watchpoint genau auf das gewaehlte Ziel: trifft nur dieses Objekt."""
        g = self._sel_group()
        if g is None:
            return
        size = g["width"] if g["ea"] % g["width"] == 0 else 1
        self.v_wp.set(f"{g['ea']:X}")
        self.v_wsize.set(str(size))
        self.v_wtype.set("schreiben")
        self.add_wp()

    def find_mine(self):
        """Ziel markieren, dessen Wert dem eingegebenen entspricht (z. B. deine aktuellen HP)."""
        found = self.book.find_value(self.v_myval.get())
        ids = {g["ea"] for g in found}
        self._fill_targets(match=ids)
        if len(found) == 1:
            self.log(f"{found[0]['label']} hat den Wert {self.v_myval.get().strip()} - das ist sehr wahrscheinlich dein Ziel", "ok")
        elif found:
            self.log(f"{len(found)} Ziele haben diesen Wert - lass dir HP abziehen/heilen und suche erneut", "warn")
        else:
            self.log("Kein Ziel mit diesem Wert - erst Treffer sammeln (AUTO-WEITER) oder Wert prüfen", "warn")

    def clear_targets(self):
        self.book.reset()
        self.only_ea = None
        self._insn_cache.clear()
        self.tgt.delete(*self.tgt.get_children())
        self._target_iid.clear()
        self._show_filter_label()

    def _fill_targets(self, match=()):
        sel = self.tgt.selection()
        keep = self._target_iid.get(sel[0]) if sel else None       # Adresse merken (Tk macht aus "1E5" gern eine Zahl)
        self.tgt.delete(*self.tgt.get_children())
        self._target_iid.clear()
        for g in self.book.rows():
            tags = []
            if g["me"]:
                tags.append("me")
            if g["ea"] in match:
                tags.append("match")
            iid = self.tgt.insert("", "end", tags=tuple(tags), values=(
                g["label"], f"{g['ea']:X}", f"{g['base_val']:X}" if g["base_val"] is not None else "-",
                TG.format_value(g["value"], g["width"]), TG.format_value(g["prev"], g["width"]),
                TG.delta_text(g["prev"], g["value"], g["width"]), g["hits"], g["changes"],
                "ICH" if g["me"] else ""))
            self._target_iid[iid] = g["ea"]
            if g["ea"] == keep:
                self.tgt.selection_set(iid)
        if self.only_ea is not None:
            self._show_filter_label()

    # ---- Threads / Register / Stack ----
    def refresh_threads(self, select=None):
        if not self._need():
            return

        def ok(ths):
            vals = [f"{t['lwpid']}  {t['name']}" for t in ths]
            self.cb_thr["values"] = vals
            pick = next((v for v in vals if select and v.startswith(str(select))), None)
            if pick:
                self.v_thr.set(pick)
            elif not self.v_thr.get() and vals:
                self.v_thr.set(vals[0])
        self.bg(lambda: self.sess.threads(), ok)

    def refresh_regs(self):
        if not self._need() or self._lwp() is None:
            return
        lw = self._lwp()
        self.bg(lambda: self.sess.regs(lw), lambda r: self._fill_regs(r, lwp=lw))

    def _fill_regs(self, regs, prev=_AUTO, lwp=None):
        """Register zeigen; was sich gegenueber `prev` geaendert hat, wird gelb und mit dem alten Wert (VORHER) gezeigt.

        prev=_AUTO: mit dem vergleichen, was zuletzt fuer diesen Thread gezeigt wurde (REGISTER-Knopf, nach Aendern);
        prev=None: kein Vergleich (erster Treffer eines Threads)."""
        if prev is _AUTO:
            prev = self._shown_regs.get(lwp)
        self._shown_regs[lwp] = dict(regs)
        self.regs.delete(*self.regs.get_children())
        changed = HC.reg_changes(prev, regs, X.REG_SHOW_ORDER)
        for n in X.REG_SHOW_ORDER:
            self.regs.insert("", "end", tags=("chg",) if n in changed else (),
                             values=(n, f"{regs[n]:016X}", f"{changed[n]:016X}" if n in changed else ""))

    def _edit_reg(self, _e):
        sel = self.regs.selection()
        if not sel or not self._need() or self._lwp() is None:
            return
        name, cur = self.regs.item(sel[0], "values")[:2]
        txt = simpledialog.askstring("Register ändern", f"{name} = (hex)", initialvalue=cur, parent=self)
        if not txt:
            return
        try:
            val = int(txt, 16)
        except ValueError:
            return self.log("Ungültiger Hex-Wert", "err")
        lw = self._lwp()
        self.bg(lambda: self.sess.set_reg(lw, name, val), lambda _r: self.refresh_regs())

    def show_stack(self):
        if not self._need() or self._lwp() is None:
            return
        lw = self._lwp()

        def ok(frames):
            d = tk.Toplevel(self); d.title("Call-Stack"); d.configure(bg=BG)
            tv = tree(d, [("n", "#"), ("ret", "RÜCKSPRUNG"), ("off", "OFFSET"), ("rbp", "RBP")],
                      [40, 170, 110, 170], height=16)
            tv.pack(fill="both", expand=True, padx=8, pady=8)
            for i, f in enumerate(frames):
                tv.insert("", "end", values=(i, f"{f['ret']:016X}", f"+{f['ret'] - self.base:X}",
                                             f"{f['rbp']:016X}"))
            tv.bind("<Double-1>", lambda _e: tv.selection() and self.win.goto_disasm(
                int(tv.item(tv.selection()[0], "values")[1], 16)))
        self.bg(lambda: self.sess.stack(lw), ok)

    def show_stack_scan(self):
        """Aufrufkette auch ohne Frame-Pointer: Stack nach Rueckkehradressen hinter CALLs absuchen."""
        if not self._need() or self._lwp() is None:
            return
        lw = self._lwp()
        import aob as AOB
        import unwind

        def job():
            rsp = self.sess.regs(lw)["rsp"]
            cl = self.win.client
            ex = AOB.exec_regions(cl.get_maps(), 0x1000)
            def in_code(a):
                return any(s <= a < e for s, e in ex)
            return rsp, unwind.unwind(cl.read_memory, rsp, in_code, depth=0x1000, max_frames=48)

        def ok(res):
            rsp, frames = res
            d = tk.Toplevel(self); d.title("Call-Stack (Stack-Scan)"); d.configure(bg=BG)
            label(d, "Kandidaten - Treffer koennen auch alte Rahmen sein. Doppelklick = Disassembler an der "
                     "Aufrufstelle.").pack(anchor="w", padx=8, pady=(8, 0))
            tv = tree(d, [("n", "#"), ("slot", "STACK +RSP"), ("ret", "RUECKSPRUNG"), ("off", "OFFSET"),
                          ("call", "AUFRUFSTELLE")], [40, 100, 170, 110, 170], height=18)
            tv.pack(fill="both", expand=True, padx=8, pady=8)
            for i, f in enumerate(frames):
                tv.insert("", "end", values=(i, f"+{f['slot'] - rsp:X}", f"{f['ret']:016X}",
                                             f"+{f['ret'] - self.base:X}", f"{f['callsite']:016X}"))
            tv.bind("<Double-1>", lambda _e: tv.selection() and self.win.goto_disasm(
                int(tv.item(tv.selection()[0], "values")[4], 16)))
            self.log(f"Stack-Scan: {len(frames)} Rueckkehr-Kandidaten", "ok")
        self.bg(job, ok)
