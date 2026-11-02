"""apply_unity_items.py - haengt den Tab UNITY > ITEMS in ein vorhandenes ReaperPy ein, OHNE Dateien zu ersetzen.

Aufruf (im ReaperPy-Ordner, dorthin sind die neuen Dateien schon entpackt):   python apply_unity_items.py [Ordner]

Es werden nur kleine Zeilen in vier vorhandene Dateien EINGEFUEGT (tools_gui.py, tools_start_gui.py, tools_i18n_en.py,
CHANGELOG.md), je mit Sicherungskopie (*.bak_unity_items).  Ist etwas schon eingefuegt, wird es uebersprungen (mehrfach
ausfuehrbar).  Findet das Skript eine Stelle nicht (weil die Datei anders aussieht), bricht es VOR dem Schreiben ab und
aendert nichts.
"""
import os
import shutil
import sys

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))

CHANGELOG_BLOCK = """### Added
- **UNITY > ITEMS tab** - the same three steps as the Unreal ITEMS tab, for Unity (IL2CPP) games: pick the game folder, click **FIND ITEMS**, click **SAVE TRAINER**. The tool picks the item list (the `ItemID`-style enum from `dump.cs`), the method that gives items (`AddItem`, `GiveItem` ... with an item-ID parameter and an optional amount) and an entry point (an `Update`/`LateUpdate`/`FixedUpdate` method of the inventory class, or of a class with a field that points to the inventory, or any `Update` for static methods) on its own, and shows what it chose in drop-downs. The trainer is written like the Unreal one: categories split into packages of 14, several projects when the cave does not fit, preview before writing, `LIESMICH_TRAINER.txt`, **CHECK TRAINER** for the version anchors. Finding the items needs no console connection.
- How it works (`unity_items.py`): a `jmp` at the start of the chosen `Update` method; its first instructions are moved into the cave (rip-relative addresses and `jcc`/`call`/`jmp` are re-encoded). The cave checks one switch byte per entry, clears it atomically and calls the game's give method once per item (System V call, `MethodInfo* = 0`), then runs the moved instructions. Raw machine code, no assembler needed to apply it.
- The leftover-cave fix (cave left behind after BASIS is switched off / loaded via GoldHEN) also covers the Unity cave: it is recognised by its code signature, the space is reused, the base patch gets `VerifyAlso`, a free-space `0 bytes` is explained.
- START tab card and English texts for the new tab.
- Tests: `tests/test_unity_items.py` (finding, relocation, encoding checked against GNU `as`, **the cave is executed on an x86-64 CPU**: arguments, `this` modes, stack alignment, callee-saved registers, switch reset, original code still runs, leftover cave) and `tests/test_gui_unity_items.py`.

### Known limits
- **Not tested on a real game or console yet.** Needs an item-ID parameter that is a number or enum; methods that take an item object/string are listed with the reason and skipped (use WERTE/EXPERTE then).
- With a `this` taken from a field of the hooked class (e.g. `Player.inventory`) the items go to the first such object that runs after the click.

"""

# (Datei, Marker der zeigt "schon eingefuegt", Anker, ob vor/nach dem Anker eingefuegt wird, Text)
EDITS = [
    ("tools_gui.py", '("★ UNITY ITEMS", "ITEMS")',
     '("★ WERTE UNITY", "SCHNELL")', "before", '("★ UNITY ITEMS", "ITEMS"), '),
    ("tools_gui.py", '"UnityItemsTab", "★ UNITY ITEMS")',
     '                 ("tools_values_gui", "ValuesTab", "★ WERTE UNITY", {"engine": "unity"}),',
     "before", '                 ("tools_unity_items_gui", "UnityItemsTab", "★ UNITY ITEMS"),\n'),
    ("tools_gui.py", "self.unity_items_tab = None",
     "        self.values_tab_unity = None\n", "after", "        self.unity_items_tab = None\n"),
    ("tools_gui.py", "self.unity_items_tab = t",
     "                if clsname == \"UnityTab\":\n                    self.unity_tab = t\n", "after",
     "                if clsname == \"UnityItemsTab\":\n                    self.unity_items_tab = t\n"),
    ("tools_start_gui.py", '"unity_items_tab"',
     '    ("Unreal-Engine-Spiel: Leben, Gold, Erfahrung, Munition",', "before",
     '    ("Unity-Spiel: Items als Trainer", "Alle Items eines Unity-Spiels automatisch finden und als fertigen Trainer "\n'
     '     "speichern - in drei Klicks (Reiter UNITY, Unterreiter ITEMS).", "ZU UNITY ▸ ITEMS", "unity_items_tab"),\n'),
    ("tools_i18n_en.py", "tools_i18n_unity_items",
     "from tools_i18n_unity import EN_UNITY  # noqa: E402\nEN.update(EN_UNITY)\n", "after",
     "from tools_i18n_unity_items import EN_UNITY_ITEMS  # noqa: E402\nEN.update(EN_UNITY_ITEMS)\n"),
    ("CHANGELOG.md", "UNITY > ITEMS tab", "## Unreleased\n\n", "after", CHANGELOG_BLOCK),
]
NEW_FILES = ["unity_items.py", "tools_unity_items_gui.py", "tools_i18n_unity_items.py",
             "tests/test_unity_items.py", "tests/test_gui_unity_items.py"]


def main():
    missing = [f for f in NEW_FILES if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        sys.exit("Fehlende neue Dateien (erst die ZIP in den ReaperPy-Ordner entpacken): " + ", ".join(missing))
    texts, crlf = {}, {}
    for f in {e[0] for e in EDITS}:
        path = os.path.join(ROOT, f)
        if not os.path.isfile(path):
            sys.exit(f"{f} nicht gefunden in {ROOT} - ist das der ReaperPy-Ordner?")
        raw = open(path, encoding="utf-8", newline="").read()
        crlf[f] = "\r\n" in raw
        texts[f] = raw.replace("\r\n", "\n")
    todo, done = [], 0
    for f, marker, anchor, where, ins in EDITS:
        if marker in texts[f]:
            done += 1
            continue
        if texts[f].count(anchor) != 1:
            sys.exit(f"Abbruch, nichts geaendert: In {f} wurde die Stelle {anchor.strip()[:60]!r} "
                     f"{'nicht' if texts[f].count(anchor) == 0 else 'mehrfach'} gefunden.")
        todo.append((f, where, anchor, ins))
    for f, where, anchor, ins in todo:
        texts[f] = texts[f].replace(anchor, ins + anchor if where == "before" else anchor + ins, 1)
    for f in sorted({t[0] for t in todo}):
        path = os.path.join(ROOT, f)
        shutil.copy2(path, path + ".bak_unity_items")
        out = texts[f].replace("\n", "\r\n") if crlf[f] else texts[f]
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(out)
    print(f"Fertig: {len(todo)} Einfuegung(en) gemacht, {done} waren schon da. Geaendert: "
          + (", ".join(sorted({t[0] for t in todo})) or "nichts"))


if __name__ == "__main__":
    main()
