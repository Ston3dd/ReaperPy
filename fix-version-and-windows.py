#!/usr/bin/env python3
"""Im Ordner deines ReaperPy-Klons ausfuehren:  python fix-version-and-windows.py
- entfernt veraltete Versionsangaben (5.7 / 5.0) aus Code-Kommentaren
- macht die as/objdump-Tests in tests/test_assist.py nur noch unter Linux aktiv (wie alle anderen Toolchain-Tests)
Zeilenenden (LF/CRLF) bleiben unveraendert.  Danach:  git add -A && git commit -m "..."  (Vorschlag steht unten im Skript)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
EDITS = {
    "gui.py": [(b"gui.py - ReaperPy v5.7 (PS5) - ", b"gui.py - ReaperPy (PS5) - ")],
    "tools_extra_gui.py": [(b"tools_extra_gui.py - neue Tabs in ReaperPy 5.0: ", b"tools_extra_gui.py - Tabs ")],
    "script_api.py": [(b"# -- ReaperPy 5.0: Funktionsaufruf", b"# -- Funktionsaufruf")],
    "tests/test_assist.py": [
        (b"import os\nimport re\nimport shutil\n", b"import os\nimport platform\nimport re\nimport shutil\n"),
        (b'TOOLS = shutil.which("as") and', b'NATIVE = platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64")\n'
                                            b'# Nur Linux: unter Windows liefert objcopy fuer .o-Dateien (COFF) keine Bytes\n'
                                            b'TOOLS = NATIVE and shutil.which("as") and'),
        (b'"GNU as/objdump fehlen"', b'"braucht Linux x86-64 mit GNU as/objdump/objcopy"'),
    ],
}
changed = 0
for rel, edits in EDITS.items():
    p = ROOT / rel
    if not p.is_file():
        print("FEHLT:", rel)
        continue
    data = p.read_bytes()
    crlf = b"\r\n" in data
    text = data.replace(b"\r\n", b"\n")
    for old, new in edits:
        if old in text:
            text = text.replace(old, new)
            changed += 1
        elif new not in text:
            print(f"Nicht gefunden in {rel}: {old[:50]!r}")
    p.write_bytes(text.replace(b"\n", b"\r\n") if crlf else text)
print(f"{changed} Aenderung(en). Jetzt: python -m unittest discover -s tests  und dann committen.")
sys.exit(0)

# Commit-Vorschlag:
#   Remove stale version mentions; run as/objdump tests only on Linux
#
#   - gui.py, tools_extra_gui.py, script_api.py: no hard-coded old version numbers (5.7 / 5.0).
#   - tests/test_assist.py: the Writer tests assemble with GNU as and objcopy -O binary; on the Windows runner
#     (COFF objects) that returns no bytes, so the writer search only saw padding ('nop'). Gate them to Linux x86-64
#     like the other toolchain tests (test_cave_trainer, test_ue_cavegen).
