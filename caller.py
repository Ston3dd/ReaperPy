"""caller.py - Logik fuer den Funktions-Aufrufer (Argumente, Puffer, Ergebnis-Anzeige).

Argument-Schreibweisen (bis zu 6 Stueck, SysV: rdi rsi rdx rcx r8 r9):
    0x1234  123  -5              Zahl
    @name  @name+0x10            Adresse eines angelegten Puffers (+Offset)
    "text"                       Text -> wird automatisch als C-String im Spiel abgelegt
    eboot+0x1000  / Ausdruck     alles, was der uebergebene `resolver` versteht
"""
import re
import struct

import ps5_more

_U64 = 2**64 - 1


class ArgError(ValueError):
    pass


class RemoteBuffers:
    """Puffer im Spiel-Speicher, die Argumente der aufgerufenen Funktion sein koennen."""

    def __init__(self, client):
        self.client = client
        self.items = {}                 # name -> (addr, size)
        self._auto = 0

    def alloc(self, name, size=0x1000):
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ArgError(f"ungueltiger Puffer-Name '{name}'")
        if name in self.items:
            raise ArgError(f"Puffer '{name}' gibt es schon")
        size = (max(16, size) + 0xF) & ~0xF
        addr = self.client.allocate_memory(size)
        self.client.write_memory(addr, bytes(size))
        self.items[name] = (addr, size)
        return addr

    def put_text(self, text):
        raw = text.encode("utf-8") + b"\0"
        self._auto += 1
        name = f"_str{self._auto}"
        addr = self.alloc(name, len(raw))
        self.client.write_memory(addr, raw)
        return addr

    def write(self, name, data, offset=0):
        addr, size = self.items[name]
        if offset + len(data) > size:
            raise ArgError(f"{len(data)} Byte passen nicht in '{name}' ({size:#x})")
        self.client.write_memory(addr + offset, bytes(data))

    def read(self, name, n=None, offset=0):
        addr, size = self.items[name]
        return self.client.read_memory(addr + offset, n if n is not None else size - offset)

    def free_all(self):
        for name, (addr, size) in list(self.items.items()):
            try:
                self.client.free_memory(addr, size)
            except Exception:
                pass
        self.items.clear()


def parse_arg(text, bufs=None, resolver=None):
    t = text.strip()
    if not t:
        return 0
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        if bufs is None:
            raise ArgError("Text-Argumente brauchen verbundene Puffer")
        return bufs.put_text(t[1:-1].encode().decode("unicode_escape"))
    m = re.fullmatch(r"@([A-Za-z_]\w*)\s*(?:([+-])\s*(0x[0-9A-Fa-f]+|\d+))?", t)
    if m:
        if bufs is None or m.group(1) not in bufs.items:
            raise ArgError(f"Puffer '{m.group(1)}' gibt es nicht")
        v = bufs.items[m.group(1)][0]
        if m.group(2):
            off = int(m.group(3), 0)
            v = v + off if m.group(2) == "+" else v - off
        return v & _U64
    try:
        return int(t, 0) & _U64
    except ValueError:
        pass
    if re.fullmatch(r"[0-9A-Fa-f]{5,16}", t):             # nackte Hex-Adresse wie im Hex-Editor
        return int(t, 16)
    if resolver:
        try:
            return int(resolver(t)) & _U64
        except Exception as e:
            raise ArgError(f"'{t}' nicht aufloesbar: {e}") from None
    raise ArgError(f"'{t}' ist keine Zahl")


def parse_args(texts, bufs=None, resolver=None):
    args = [parse_arg(t, bufs, resolver) for t in texts]
    if len(args) > 6:
        raise ArgError("maximal 6 Argumente (Register-Aufruf)")
    return args + [0] * (6 - len(args))


def do_call(client, rip, args, safe=True):
    return ps5_more.call(client, rip, *args, safe=safe)


def describe_result(client, rax):
    """RAX als Hex / vorzeichenbehaftet / Zeiger-Inhalt / Float - fuer die Ergebnis-Anzeige."""
    lines = [("hex", f"{rax:#x}"), ("u64", str(rax)),
             ("i64", str(rax - (1 << 64) if rax >> 63 else rax)),
             ("i32", str(struct.unpack("<i", struct.pack("<I", rax & 0xFFFFFFFF))[0])),
             ("float", f"{struct.unpack('<f', struct.pack('<I', rax & 0xFFFFFFFF))[0]:.9g}"),
             ("double", f"{struct.unpack('<d', struct.pack('<Q', rax))[0]:.17g}")]
    if 0x10000 <= rax < 0x800000000000:
        try:
            raw = bytes(client.read_memory(rax, 48))
            s = raw.split(b"\0", 1)[0]
            if len(s) >= 2 and all(32 <= c < 127 for c in s):
                lines.append(("String @rax", s.decode()))
            lines.append(("Bytes @rax", raw[:16].hex(" ").upper()))
        except Exception:
            pass
    return lines
