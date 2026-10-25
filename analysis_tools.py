"""Static x86-64 analysis helpers for ReaperPy.

Works on a byte buffer acquired by the user. It never executes code or writes target memory.
Capstone is optional; disassembly-derived features require it.
"""
from __future__ import annotations
import re
from collections import defaultdict

_ARG_REGS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")


def extract_strings(data: bytes, base: int = 0, min_length: int = 4):
    """Extract printable ASCII runs and aligned-looking UTF-16LE runs from bytes."""
    data = bytes(data)
    out = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % max(1, int(min_length)), data):
        out.append({"address": base + m.start(), "encoding": "ascii", "text": m.group().decode("ascii")})
    # Scan UTF-16LE separately; require printable ASCII codepoints and NUL high bytes.
    i = 0
    while i + 2 * min_length <= len(data):
        start = i
        chars = []
        while i + 1 < len(data) and data[i] in range(0x20, 0x7f) and data[i + 1] == 0:
            chars.append(chr(data[i])); i += 2
        if len(chars) >= min_length:
            out.append({"address": base + start, "encoding": "utf-16le", "text": "".join(chars)})
        i = max(i + 1, start + 1) if not chars else i + 2
    out.sort(key=lambda x: (x["address"], x["encoding"]))
    return out


def _parse_target(line):
    op = (line.get("op_str") or "").strip()
    mnem = line.get("mnemonic", "").lower()
    if mnem not in ("call", "jmp") and not (mnem.startswith("j") and len(mnem) <= 4):
        return None
    m = re.fullmatch(r"(?:short\s+)?(0x[0-9a-fA-F]+)", op)
    return int(m.group(1), 16) if m else None


def build_call_graph(data: bytes, base: int = 0, max_instructions: int = 100000):
    """Build a conservative static direct-call graph from a code buffer.

    Nodes are the buffer entry plus direct call targets inside the decoded range.
    This is a heuristic, not a full function-boundary recovery algorithm.
    """
    import asm_tools
    lines = asm_tools.disassemble_lines(data, base, max_insn=max_instructions)
    end = base + len(data)
    targets = []
    for line in lines:
        if line.get("mnemonic", "").lower() == "call":
            target = _parse_target(line)
            if target is not None and base <= target < end:
                targets.append({"source": line["addr"], "target": target})
    nodes = sorted({base} | {x["target"] for x in targets})
    edges = sorted(targets, key=lambda x: (x["source"], x["target"]))
    incoming = defaultdict(int); outgoing = defaultdict(int)
    for e in edges:
        outgoing[e["source"]] += 1; incoming[e["target"]] += 1
    return {"base": base, "end": end, "instruction_count": len(lines),
            "nodes": [{"address": n, "incoming_calls": incoming[n], "outgoing_calls_at_address": outgoing[n]}
                      for n in nodes], "edges": edges,
            "limitations": "Nur direkte, dekodierbare CALL-Ziele innerhalb des Puffers; indirekte Calls und echte Funktionsgrenzen werden nicht zuverlässig erkannt."}


def infer_call_arguments(lines, call_index: int, lookback: int = 8):
    """Heuristic argument-register hints for x86-64 SysV calls; never claims exact types."""
    if not 0 <= call_index < len(lines) or lines[call_index].get("mnemonic", "").lower() != "call":
        raise ValueError("call_index muss auf eine CALL-Instruktion zeigen")
    prior = lines[max(0, call_index - max(1, lookback)):call_index]
    hints = {}
    for reg in _ARG_REGS:
        for line in reversed(prior):
            mnem = line.get("mnemonic", "").lower()
            ops = [x.strip() for x in (line.get("op_str") or "").split(",", 1)]
            if not ops or not re.search(rf"(?:^|\W){reg}(?:\W|$)", ops[0]):
                continue
            value = "unknown"
            if mnem == "lea": value = "pointer/address candidate"
            elif mnem == "mov" and len(ops) > 1:
                src = ops[1]
                if src.startswith("0x") or re.fullmatch(r"-?\d+", src): value = "integer/immediate candidate"
                elif "[" in src: value = "memory/pointer candidate"
                else: value = "register/value candidate"
            elif mnem.startswith("mov") and "xmm" in " ".join(ops): value = "possible floating-point/vector candidate"
            hints[reg] = {"instruction": line.get("addr"), "mnemonic": mnem,
                          "operand": line.get("op_str", ""), "hint": value}
            break
    return hints
