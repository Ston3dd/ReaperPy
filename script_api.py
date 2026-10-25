"""script_api.py - `ps5`-Objekt fuer den Python-Skript-Tab.

    base = ps5.module()                         # Basis von eboot.bin
    hp   = ps5.pointer(base + 0x4A1C00, 0x20, 0x1C4)   # Pfad aufloesen (wie Pointer-Tab)
    ps5.write_u32(hp, 999, undo=True)           # wird mit undo_all() zurueckgesetzt
    site = ps5.aob("48 8B 05 ?? ?? ?? ?? 8B 40 1C")
    ps5.nop(site, 6)                            # NOP mit Undo
    buf  = ps5.alloc("stats", 64, init=b"\\x63" * 64)

pointer(): jede Zahl nach der Wurzel ist ein Offset; vor JEDEM Offset wird 8 Byte gelesen
(Root -> [Root]+o1 -> [[Root]+o1]+o2 ...).  Liefert None, wenn ein Zeiger ungueltig ist.
"""
import struct
import time
import traceback

import aob as AOB
import asm_tools
import pointerscan as PS


class ScriptStopped(Exception):
    pass


def _bytes(data):
    if isinstance(data, str):
        return asm_tools.parse_hex_bytes(data)
    return bytes(data)


class Ps5Api:
    def __init__(self, client, backend=None, image_base=0x400000, lock=None, out=print):
        self.client = client
        self.backend = backend
        self.image_base = image_base
        self._lock = lock
        self._out = out
        self._undo = []                # [(addr, original_bytes)]
        self._allocs = {}
        self._mods = None
        self._stop = False

    # -- intern ------------------------------------------------------------
    def _io(self, fn, *a):
        self.check()
        if self._lock:
            with self._lock:
                return fn(*a)
        return fn(*a)

    def check(self):
        if self._stop:
            raise ScriptStopped("Skript gestoppt")

    def stop(self):
        self._stop = True

    def reset(self):
        self._stop = False

    # -- Ausgabe / Zeit ------------------------------------------------------
    def log(self, *a):
        self._out(" ".join(str(x) for x in a))

    def sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.check()
            time.sleep(min(0.05, max(0.0, end - time.time())))

    def notify(self, message):
        if self.backend:
            return self.backend.notify(str(message))
        return False

    # -- Speicher --------------------------------------------------------------
    def read(self, addr, n):
        d = self._io(self.client.read_memory, addr, n)
        if d is None or len(d) < n:
            raise RuntimeError(f"read {addr:#x}+{n} fehlgeschlagen")
        return bytes(d)

    def write(self, addr, data, undo=False):
        data = _bytes(data)
        if undo:
            self._undo.append((addr, self.read(addr, len(data))))
        self._io(self.client.write_memory, addr, data)

    def undo_all(self):
        n = 0
        while self._undo:
            addr, orig = self._undo.pop()
            if self._lock:
                with self._lock:
                    self.client.write_memory(addr, orig)
            else:
                self.client.write_memory(addr, orig)
            n += 1
        return n

    def _rd(self, fmt, addr):
        return struct.unpack("<" + fmt, self.read(addr, struct.calcsize("<" + fmt)))[0]

    def _wr(self, fmt, addr, value, undo):
        self.write(addr, struct.pack("<" + fmt, value), undo=undo)

    def read_u8(self, a): return self._rd("B", a)
    def read_u16(self, a): return self._rd("H", a)
    def read_u32(self, a): return self._rd("I", a)
    def read_u64(self, a): return self._rd("Q", a)
    def read_i32(self, a): return self._rd("i", a)
    def read_f32(self, a): return self._rd("f", a)
    def read_f64(self, a): return self._rd("d", a)

    def write_u8(self, a, v, undo=False): self._wr("B", a, v & 0xFF, undo)
    def write_u16(self, a, v, undo=False): self._wr("H", a, v & 0xFFFF, undo)
    def write_u32(self, a, v, undo=False): self._wr("I", a, v & 0xFFFFFFFF, undo)
    def write_u64(self, a, v, undo=False): self._wr("Q", a, v & 0xFFFFFFFFFFFFFFFF, undo)
    def write_i32(self, a, v, undo=False): self._wr("i", a, v, undo)
    def write_f32(self, a, v, undo=False): self._wr("f", a, v, undo)
    def write_f64(self, a, v, undo=False): self._wr("d", a, v, undo)

    # -- Module / Pointer / AOB ----------------------------------------------------
    def module(self, name="eboot.bin"):
        if self._mods is None:
            import ps5_ext
            self._mods = self._io(ps5_ext.maps_named, self.client)
        starts = [m["start"] for m in self._mods if m["name"].lower() == name.lower()]
        if starts:
            return min(starts)
        if name.lower() == "eboot.bin":
            return self.image_base
        raise RuntimeError(f"Modul {name!r} nicht gefunden")

    def pointer(self, root, *offsets):
        return self._io(PS.resolve, self.client, root, offsets)

    def aob(self, pattern, nth=1):
        """Erster (nth-ter) Treffer in ausfuehrbaren Regionen, sonst None."""
        pat, mask = AOB.parse_pattern(pattern)
        maps = self._io(self.client.get_maps)
        regions = AOB.exec_regions(maps)
        if nth == 1:
            r = self._io(AOB.find_first, self.client, regions, pat, mask)
            return r or None
        import ps5_ext
        seen = 0
        for s, e in regions:
            pos = s
            while pos < e:
                a = self._io(ps5_ext.aob_scan, self.client, pos, min(e - pos, 0xFFFFFFFF), pat, mask, 1)
                if not a:
                    break
                seen += 1
                if seen == nth:
                    return a
                pos = a + 1
        return None

    # -- Code ----------------------------------------------------------------------
    def asm(self, text, addr=0):
        return asm_tools.assemble(text, addr, self.client)

    def patch_asm(self, addr, text, undo=True):
        data = self.asm(text, addr)
        self.write(addr, data, undo=undo)
        return len(data)

    def nop(self, addr, n=1, undo=True):
        self.write(addr, b"\x90" * n, undo=undo)

    # -- Speicher anfordern -----------------------------------------------------------
    def alloc(self, name, size, init=None):
        """Benannter Puffer (bleibt zwischen Laeufen bestehen, gleicher Name = gleiche Adresse)."""
        if name in self._allocs:
            return self._allocs[name][0]
        addr = self._io(self.client.allocate_memory, size)
        if self.backend:
            try:
                self._io(self.backend.set_rwx, addr, size)
            except Exception:
                pass
        self._allocs[name] = (addr, size)
        if init is not None:
            self.write(addr, init)
        return addr

    # -- ReaperPy 5.0: Funktionsaufruf, Spiel-Erkennung, Bulk-Schreiben, Logger ----------------
    def call(self, addr, *args, safe=True):
        """Funktion im Spiel aufrufen (bis 6 Ganzzahl-/Zeiger-Argumente) -> RAX.
        Argumente: Zahlen, oder str -> wird als C-String im Spiel abgelegt."""
        import ps5_more
        vals = []
        for a in args[:6]:
            if isinstance(a, str):
                vals.append(self.alloc(f"_str_{abs(hash(a)) & 0xFFFFFF:x}", len(a.encode()) + 1,
                                       a.encode() + b"\0"))
            else:
                vals.append(int(a))
        return self._io(lambda: ps5_more.call(self.client, addr, *vals, safe=safe))

    def foreground(self):
        """-> (pid, titel_id, name, version) des Spiels im Vordergrund."""
        import ps5_more
        return self._io(ps5_more.foreground_app, self.client)

    def write_many(self, entries):
        """[(adresse, bytes), ...] in einem Austausch schreiben (nicht rueckgaengig-fuehrend)."""
        import ps5_more
        return self._io(ps5_more.write_multi, self.client, entries)

    def log_calls(self, addr, seconds=5.0, ring=1024):
        """Funktion `seconds` lang protokollieren -> Liste von dicts (rdi, rsi, rdx, rcx, r8, r9,
        ret, rax, rsp, s7, s8, xmm0, xmm1).  Braucht das Backend (Cave-Suche/Assembler)."""
        import logger
        if not self.backend:
            raise RuntimeError("log_calls braucht das Backend (nur im Tools-Fenster)")
        sess = logger.LoggerSession(self.backend, addr, ring)
        out = []
        self._io(sess.start)
        try:
            t0 = time.time()
            while time.time() - t0 < seconds:
                self.check()
                time.sleep(0.2)
                out += self._io(sess.poll)
        finally:
            self._io(sess.stop)
        return out


def run_script(code, api, out=print):
    """Fuehrt `code` mit `ps5` aus. Gibt True bei Erfolg zurueck; Fehler landen in `out`."""
    api.reset()

    def _print(*a, **k):
        out(" ".join(str(x) for x in a))

    env = {"ps5": api, "print": _print, "struct": struct, "time": time, "__name__": "__script__"}
    try:
        exec(compile(code, "<script>", "exec"), env)
        return True
    except ScriptStopped:
        out("-- gestoppt --")
    except SystemExit:
        out("-- beendet --")
    except Exception:
        tb = traceback.format_exc().splitlines()
        out("\n".join(l for l in tb if "script_api.py" not in l))
    return False
