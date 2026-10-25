"""journal.py - Schreib-Journal: jede Speicher-Aenderung der Tools ist rueckgaengig machbar.

`WriteJournal.attach(client)` ersetzt client.write_memory durch eine Variante, die vorher die
alten Bytes liest.  Alles, was ueber diesen Client schreibt (Hex-Editor, Scanner, Patcher, Skripte,
Caller), landet im Journal; `undo()` schreibt die alten Bytes zurueck (neueste zuerst).
Nicht protokolliert: Schreibzugriffe > 64 KiB und Freeze-Ticks (write_multi).
"""
import threading
import time

MAX_ENTRIES = 3000
MAX_SIZE = 0x10000


class Entry:
    __slots__ = ("t", "addr", "old", "new", "source", "undone")

    def __init__(self, addr, old, new, source):
        self.t, self.addr, self.old, self.new = time.time(), addr, old, new
        self.source, self.undone = source, False

    def line(self):
        n = len(self.new)
        h = lambda b: b[:8].hex(" ").upper() + (" .." if len(b) > 8 else "")
        return (time.strftime("%H:%M:%S", time.localtime(self.t)), f"{self.addr:#x}", n,
                h(self.old), h(self.new), self.source)


class WriteJournal:
    def __init__(self):
        self.entries = []
        self.lock = threading.RLock()
        self.client = None
        self._orig = None
        self.source = "Tool"
        self.enabled = True

    def attach(self, client):
        if self.client is client:
            return
        self.detach()
        self.client, self._orig = client, client.write_memory
        orig = self._orig

        def journaled(address, data, *a, **k):
            data = bytes(data)
            old = None
            if self.enabled and 0 < len(data) <= MAX_SIZE:
                try:
                    old = bytes(client.read_memory(address, len(data)))
                except Exception:
                    old = None
            res = orig(address, data, *a, **k)
            if old is not None and old != data:
                with self.lock:
                    if not (self.entries and self.entries[-1].addr == address
                            and self.entries[-1].new == data):
                        self.entries.append(Entry(address, old, data, self.source))
                        del self.entries[:-MAX_ENTRIES]
            return res
        client.write_memory = journaled

    def detach(self):
        if self.client is not None and self._orig is not None:
            self.client.write_memory = self._orig
        self.client = self._orig = None

    def clear(self):
        with self.lock:
            self.entries.clear()

    def undo(self, entry):
        """Eine Aenderung zurueck.  Der Rueckschreib-Vorgang selbst wird nicht erneut protokolliert."""
        if entry.undone:
            return False
        self._orig(entry.addr, entry.old)
        entry.undone = True
        return True

    def undo_all(self, upto=None):
        """Alles (oder alles ab `upto` bis heute) rueckgaengig, neueste zuerst -> Anzahl."""
        n = 0
        with self.lock:
            todo = [e for e in reversed(self.entries) if not e.undone]
            if upto is not None:
                todo = todo[:todo.index(upto) + 1] if upto in todo else []
        for e in todo:
            if self.undo(e):
                n += 1
        return n
