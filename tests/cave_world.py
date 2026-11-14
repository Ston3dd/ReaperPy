"""cave_world.py - Test-Unterbau fuer Hook/Cave-Tests OHNE Konsole, aber mit echtem Maschinencode.

  GasBackend   assemble() mit GNU as + ld (Basisadresse stimmt, absolute Sprungziele werden aufgeloest wie bei Keystone),
               read/write/find_cave/set_rwx/get_maps auf einem ausfuehrbaren mmap-Bereich (nur Linux x86-64)
  patch_disasm ersetzt asm_tools.disassemble_lines durch objdump (Capstone ist in der Testumgebung nicht noetig)
  run_isolated fuehrt Maschinencode in einem Kindprozess aus - ein Absturz laesst nur diesen Test scheitern
"""
import ctypes
import mmap
import os
import platform
import re
import shutil
import subprocess
import tempfile
from unittest import mock

import asm_tools

TOOLCHAIN = (platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")
             and all(shutil.which(t) for t in ("as", "ld", "objdump")))


def assemble_at(text, addr):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "a.s"), "w", encoding="utf-8") as f:
        f.write(".intel_syntax noprefix\n.text\n.globl _start\n_start:\n" + text + "\n")
    subprocess.run(["as", "--64", "-o", os.path.join(d, "a.o"), os.path.join(d, "a.s")],
                   check=True, capture_output=True)
    subprocess.run(["ld", f"-Ttext={addr:#x}", "--oformat", "binary", "-e", "_start", "-o", os.path.join(d, "a.bin"),
                    os.path.join(d, "a.o")], check=True, capture_output=True)
    with open(os.path.join(d, "a.bin"), "rb") as f:
        out = f.read()
    shutil.rmtree(d, ignore_errors=True)
    return out


def _norm_ops(ops):
    ops = ops.split("#")[0].strip()
    ops = re.sub(r"\b(BYTE|WORD|DWORD|QWORD|XMMWORD) PTR", lambda m: m.group(1).lower() + " ptr", ops)
    ops = re.sub(r"\[([^\]]+)\]", lambda m: "[" + re.sub(r"\s*([+-])\s*", r" \1 ", m.group(1)).strip() + "]", ops)
    ops = ops.replace(",", ", ").replace(",  ", ", ")
    return ops


def objdump_lines(data, addr, max_insn=None):
    """Wie asm_tools.disassemble_lines (Capstone-Schreibweise), aber mit objdump."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.bin")
    with open(p, "wb") as f:
        f.write(bytes(data))
    out = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel", f"--adjust-vma={addr:#x}", p],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout
    shutil.rmtree(d, ignore_errors=True)
    lines = []
    for ln in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t((?:[0-9a-f]{2} )+)\s*(.*)", ln)
        if not m:
            continue
        raw = bytes.fromhex(m.group(2).replace(" ", ""))
        text = m.group(3).strip()
        if lines and not text:                                   # Fortsetzungszeile eines langen Befehls
            lines[-1]["size"] += len(raw)
            lines[-1]["bytes"] += raw
            continue
        mn, _, ops = text.partition(" ")
        ops = _norm_ops(ops)
        if (mn == "call" or mn.startswith("j")) and re.fullmatch(r"[0-9a-f]+(?: <.*>)?", ops):
            ops = "0x" + ops.split()[0]
        lines.append({"addr": int(m.group(1), 16), "size": len(raw), "bytes": raw, "mnemonic": mn.lower(),
                      "op_str": ops, "insn": None})
        if max_insn is not None and len(lines) >= max_insn:
            break
    return lines


def patch_disasm():
    """with-Block: asm_tools nutzt objdump statt Capstone."""
    return mock.patch.multiple(asm_tools, disassemble_lines=objdump_lines, HAVE_CAPSTONE=True)


class GasBackend:
    """Backend wie ps5_backend.PS5Backend (Teilmenge), der Speicher ist ein echter, ausfuehrbarer mmap-Bereich."""

    SIZE = 0x40000

    def __init__(self):
        self.mm = mmap.mmap(-1, self.SIZE, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
        self.base = ctypes.addressof(ctypes.c_char.from_buffer(self.mm))
        self.cave_next = self.base + 0x20000
        self.writes = []
        self.client = None

    # --- Speicher ---
    def _off(self, addr, n):
        o = addr - self.base
        if o < 0 or o + n > self.SIZE:
            raise RuntimeError(f"{addr:#x} ausserhalb des Testspeichers")
        return o

    def read(self, addr, n):
        o = self._off(addr, n)
        return bytes(self.mm[o:o + n])

    def write(self, addr, data):
        o = self._off(addr, len(data))
        self.mm[o:o + len(data)] = bytes(data)
        self.writes.append((addr, bytes(data)))

    def put(self, addr, data):
        self.write(addr, data)

    def find_cave(self, hook_addr, size=0x4000):
        a = self.cave_next
        self.cave_next += (size + 0xFFF) & ~0xFFF if size < 0x1000 else 0x1000
        return a

    def set_rwx(self, addr, size):
        return True

    def get_maps(self, force=False):
        return [(self.base, self.base + self.SIZE, 7)]

    def assemble(self, text, addr=0, syntax=0):
        return assemble_at(text, addr)

    # --- Ausfuehren ---
    def call(self, addr, *args):
        """Maschinencode an `addr` aufrufen (ganzzahlige Argumente), Rueckgabe eax (int32)."""
        types = [ctypes.c_float if isinstance(a, float) else ctypes.c_uint64 for a in args]
        fn = ctypes.CFUNCTYPE(ctypes.c_int32, *types)(addr)
        return fn(*args)


def run_isolated(fn, timeout=20):
    """fn() in einem Kindprozess ausfuehren -> (ok, Wert|Fehlertext).  Absturz (SIGSEGV) = (False, 'Absturz ...')."""
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(r)
            val = fn()
            os.write(w, repr(val).encode())
            os._exit(0)
        except BaseException as e:  # noqa: BLE001
            os.write(w, ("ERR " + repr(e)).encode())
            os._exit(1)
    os.close(w)
    data = b""
    while True:
        chunk = os.read(r, 4096)
        if not chunk:
            break
        data += chunk
    os.close(r)
    _p, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        return False, f"Absturz (Signal {os.WTERMSIG(status)})"
    txt = data.decode()
    if txt.startswith("ERR "):
        return False, txt[4:]
    return True, eval(txt)       # noqa: S307 - eigene Ausgabe des Kindprozesses
