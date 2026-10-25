"""ps5_backend.py – Wrapper um PS5DebugClient."""
import re

import asm_tools
from ps5_client import PS5DebugClient

PAGE_ALIGN = 0x4000          # PS5-Seitengranularität (16 KB); gilt auch für 4-KB-Seiten


class PS5Backend:
    def __init__(self, host="192.168.178.25", port=744):
        self.host = host
        self.port = port
        self.client = None
        self.pid = None
        self.process_name = "eboot.bin"
        self._maps_cache = None
        self._notify_ok = True  # Notify-Fehler → abschalten

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------
    def reset_cache(self):
        self._maps_cache = None

    def connect(self):
        """Neue Verbindung aufbauen; eine alte wird sauber geschlossen (kein Socket-Leck)."""
        old = self.client
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self.client = PS5DebugClient(self.host, self.port)
        self.client.connect()
        self.reset_cache()
        self._notify_ok = True          # neue Verbindung: Meldungen wieder versuchen
        return self.client.protocol_version

    def reconnect(self):
        """Verbindung neu aufbauen und den Prozess neu suchen. Rückgabe: PID."""
        self.connect()
        return self.find_pid(self.process_name)

    def find_pid(self, name=None):
        if name:
            self.process_name = name
        self.pid = self.client.find_pid(self.process_name)
        self.reset_cache()           # neue PID = neue Memory-Map
        return self.pid

    def lookup_pid(self):
        """PID des Spiels, ohne etwas zu verändern (None = läuft nicht)."""
        return self.client.lookup_pid(self.process_name)

    def adopt_pid(self, pid):
        """Neue PID übernehmen (Watchdog), inkl. Client und Cache."""
        self.pid = pid
        if self.client:
            self.client.pid = pid
        self.reset_cache()

    def notify(self, message):
        """Sendet Notification. Schlägt sie fehl, wird sie deaktiviert."""
        if not self.client or not self._notify_ok:
            return False
        try:
            return self.client.send_notification(message)
        except Exception as e:
            print(f"[backend] notify: {e}")
            self._notify_ok = False
            return False

    # ------------------------------------------------------------------
    # Speicher
    # ------------------------------------------------------------------
    def read(self, address, length):
        return self.client.read_memory(address, length)

    def write(self, address, data):
        return self.client.write_memory(address, bytes(data))

    def assemble(self, asm_text, base_addr=0, syntax=0):
        """Keystone lokal; fehlt es, wird der Assembler im Payload auf der PS5 benutzt."""
        return asm_tools.assemble(asm_text, base_addr, self.client)

    def get_maps(self, force=False):
        if self._maps_cache is not None and not force:
            return self._maps_cache
        try:
            maps = self.client.get_maps()
        except Exception:
            return self._maps_cache or []      # Fehler NICHT dauerhaft cachen
        self._maps_cache = maps
        return maps

    def _align_in_region(self, address, length):
        """Seitengenau ausrichten, aber nie über die Region hinaus (sonst würden
        Nachbar-Regionen, z.B. Code, versehentlich mitverändert)."""
        for start, end, _prot in self.get_maps():
            if start <= address < end:
                a = max(start, address & ~(PAGE_ALIGN - 1))
                b = min(end, (address + length + PAGE_ALIGN - 1) & ~(PAGE_ALIGN - 1))
                if b > a:
                    return a, b - a
        return address, length

    def set_prot(self, address, length, want_rwx=True):
        prot = 7 if want_rwx else 3
        a, n = self._align_in_region(address, length)
        return self.client.change_protection(a, n, prot)

    def set_rwx(self, address, length):
        return self.set_prot(address, length, True)

    def set_rw(self, address, length):
        try:
            return self.set_prot(address, length, False)
        except Exception:
            return None

    def alloc_mem(self, size):
        return self.client.allocate_memory(size)

    # ------------------------------------------------------------------
    # Code-Cave
    # ------------------------------------------------------------------
    def _scan_zeros(self, start, end, need):
        """Sucht einen Block aus `need` aufeinanderfolgenden Nullbytes (16-Byte-ausgerichtet).
        Der GANZE Block wird geprüft - nicht nur ein Teil davon."""
        CHUNK = 0x20000
        rx = re.compile(b"\x00{%d,}" % need)
        pos = start
        while pos + need <= end:
            size = min(CHUNK + need, end - pos)
            try:
                data = self.read(pos, size)
            except Exception:
                pos += CHUNK
                continue
            if data:
                best = None
                for m in rx.finditer(data):
                    run_start, run_end = pos + m.start(), pos + m.end()
                    cave = (run_end - need) & ~0xF          # ans Ende der Lücke legen
                    if cave < run_start:
                        cave = (run_start + 0xF) & ~0xF
                    if cave + need <= run_end:
                        best = cave
                if best is not None:
                    return best
            pos += CHUNK
        return None

    def find_cave(self, hook_addr, size=0x4000):
        LIMIT = 0x7F000000
        maps = self.get_maps(force=True)
        if not maps:
            raise RuntimeError("Keine Memory-Maps verfügbar")

        cands = []
        for start, end, prot in maps:
            sz = end - start
            if sz < 0x400:
                continue
            if abs(start - hook_addr) > LIMIT and abs(end - hook_addr) > LIMIT:
                continue
            if not (prot & 0x2) or (prot & 0x4):
                continue
            cands.append((start, end, prot))
        cands.sort(key=lambda t: min(abs(t[0] - hook_addr), abs(t[1] - hook_addr)))
        print(f"[cave] {len(cands)} RW-Regionen im ±2GB-Bereich")

        for try_size in (size, 0x2000, 0x1000, 0x800, 0x400, 0x200, 0x100, 0x80):
            if try_size > size:
                continue
            for start, end, prot in cands[:40]:
                if end - start < try_size:
                    continue
                cave = self._scan_zeros(start, end, try_size)
                if cave is None:
                    continue
                if abs(cave - hook_addr) > LIMIT:
                    continue
                print(f"[cave]   Kandidat {cave:#x} ({try_size:#x} B)")
                try:
                    self.set_rwx(cave, try_size)
                    return cave
                except Exception as e:
                    print(f"[cave]   set_rwx: {e}")
                    continue

        # Fallback: neuen Speicher anfordern - bevorzugt nahe am Hook (rel32-Reichweite)
        for label, fn in (("alloc_hinted", lambda: self.client.allocate_memory_hinted(hook_addr, size)),
                          ("alloc", lambda: self.alloc_mem(size))):
            print(f"[cave]   Fallback: {label}({size:#x})")
            try:
                cave = fn()
                if cave and abs(cave - hook_addr) < LIMIT:
                    print(f"[cave]   {label}: {cave:#x}")
                    self.set_rwx(cave, size)
                    return cave
                if cave:
                    print(f"[cave]   {label}: {cave:#x} zu weit vom Hook entfernt")
                    try:
                        self.client.free_memory(cave, size)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[cave]   {label}: {e}")

        raise RuntimeError("Keine freie Cave-Adresse gefunden")
