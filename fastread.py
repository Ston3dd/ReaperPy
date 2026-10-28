"""fastread.py - schnelles, paralleles Lesen aus dem Spiel (gemeinsame Bausteine fuer den Unreal-Objekt-Index).

Dieselbe Technik wie beim Unity-Scan (il2cpp_dump.ChunkStream): mehrere zusaetzliche Verbindungen zum Payload
lesen gleichzeitig, und waehrend der Aufrufer den vorigen Block auswertet, laeuft das Lesen des naechsten schon.

  open_readers   weitere Verbindungen zum Payload -> (read-Funktionen, close-Funktionen)
  stream         [(adresse, laenge, tag)] -> (tag, bytes | None) in der urspruenglichen Reihenfolge
  plan_windows   viele kleine Lesestellen zu wenigen grossen Fenstern zusammenlegen
"""
import queue
from concurrent.futures import ThreadPoolExecutor

EXTRA_READERS = 3                      # zusaetzliche Verbindungen (zusammen mit der Hauptverbindung also 4)


def open_readers(client, count=EXTRA_READERS, timeout=15):
    """Weitere Verbindungen zum Payload -> (readers, closers, fehler).  `fehler` ist None oder ein Text, wenn nicht
    alle Verbindungen aufgingen (es wird dann mit den vorhandenen gelesen - nur langsamer).  Clients ohne
    host/port (Tests, Offline-Dump) bekommen keine zusaetzlichen Verbindungen und keinen Fehler."""
    host, port = getattr(client, "host", None), getattr(client, "port", None)
    if not host or not port or count <= 0:
        return [], [], None
    readers, closers, error = [], [], None
    try:
        from ps5_client import PS5DebugClient
        for _ in range(count):
            c = PS5DebugClient(host, port, timeout=timeout)
            c.connect()
            c.pid = client.pid
            readers.append(c.read_memory)
            closers.append(c.close)
    except Exception as e:  # noqa: BLE001 - dann eben weniger Verbindungen
        error = str(e)
    return readers, closers, error


def stream(readers, jobs, cancel=None):
    """jobs = [(addr, length, tag)] -> liefert (tag, bytes) in Auftragsreihenfolge; bytes ist None, wenn der Read
    fehlschlug.  Die Auftraege laufen auf allen `readers` gleichzeitig (jeder Reader immer nur ein Auftrag);
    mit nur einem Reader laeuft das Lesen in einem Hilfsthread weiter, waehrend der Aufrufer den vorigen Block
    auswertet.  cancel() -> True beendet den Strom."""
    readers = list(readers)
    jobs = list(jobs)
    workers = max(1, len(readers))
    free = queue.Queue()
    for r in readers:
        free.put(r)

    def work(job):
        addr, length, _tag = job
        r = free.get()
        try:
            data = bytes(r(addr, length))
            return data if len(data) >= length else None
        except Exception:  # noqa: BLE001 - Aufrufer entscheidet, was bei einem Fehlschlag passiert
            return None
        finally:
            free.put(r)

    window = workers + 1
    pending = []
    it = iter(jobs)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        try:
            while True:
                while len(pending) < window:
                    job = next(it, None)
                    if job is None:
                        break
                    pending.append((job, ex.submit(work, job)))
                if not pending:
                    return
                if cancel and cancel():
                    return
                job, fut = pending.pop(0)
                yield job[2], fut.result()
        finally:
            for _j, f in pending:
                f.cancel()


def plan_windows(addrs, need, gap=0x400, maxlen=0x80000):
    """addrs = AUFSTEIGEND sortierte Adressen, von denen je `need` Byte gebraucht werden.
    -> [(start, laenge, lo, hi)]: ein Fenster liest ab `start` `laenge` Byte und deckt addrs[lo:hi] ab.
    Liegt die naechste Adresse hoechstens `gap` Byte hinter dem Ende der letzten und das Fenster bleibt unter
    `maxlen`, gehoert sie zum selben Fenster - so wird aus Hunderttausenden Einzel-Reads eine Handvoll grosser."""
    out = []
    n = len(addrs)
    lo = 0
    while lo < n:
        start = addrs[lo]
        end = start + need
        hi = lo + 1
        while hi < n:
            a = addrs[hi]
            if a - end > gap or a + need - start > maxlen:
                break
            if a + need > end:
                end = a + need
            hi += 1
        out.append((start, end - start, lo, hi))
        lo = hi
    return out
