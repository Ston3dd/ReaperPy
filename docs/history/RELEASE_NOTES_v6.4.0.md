# ReaperPy 6.4.0

**Trainer release cards, CAVEMAKER for Unity and Unreal, faster Unity scanning and original Reaper patches that finally load.**

The idea of the trainer release cards comes from **Pharaoh2k** (also credited for the ps5debug-NG payload) - thank you!

### Fixed (Unity scanning itself to death)
- Every field click in **UNITY → MANUAL** started its own full memory scan, several at once. The memory is now scanned **once** (progress in %, **CANCEL SCAN**), after that all fields are instant; classes with an `Instance` field need no scan at all. The live give and the cheat menu use the same finder (`unity_objects.py`).

### Added (Release card)
- Credit: The idea of the trainer release cards comes from **Pharaoh2k** (also credited for the ps5debug-NG payload) - thank you!
- **Release card at export:** the GoldHEN / etaHEN export dialog can now create a release card (PNG, 1920x1080) next to the cheat file: game name, title ID, version, all cheats with Roman numerals, the count in a seal and your credits. The cover is looked up in the library (`TITLEID.png`, `TITLEID_icon0.jpg`) or chosen by hand; the accent colour is taken from the cover. **CARD ONLY ...** makes the card without a console, `export_goldhen.py --card` does it on the command line. A problem with the card never stops the export.
- The card is drawn nicer than the stand-alone script: square covers (icon0) are shown whole instead of cropped, floor reflection and aura, film grain, long titles on two lines, many cheats end with a readable "+ N MORE" line instead of tiny text.

### Added (CAVEMAKER)
- **UNITY → CAVEMAKER:** the stand-alone `cavemaker.py` is now a tab. Pick any method or field from `dump.cs`, choose what should happen (set the return value, change a parameter, set a field of the passed object, hold an instance or static field) and add it to a COLLECTION; **TEST ON / OFF** on the console; **FIND HOOK AUTOMATICALLY** tries methods live until a static field is really set. It uses the game, connection and module base of the MANUAL tab, so nothing is loaded twice. `cavemaker.py` is now the logic only (no window of its own).
- **UNREAL → CAVEMAKER:** the cheat menu with the same collection - **BUILD CODE CAVE** puts the cave in the COLLECTION instead of writing it straight away; test it, then take it over into the project.
- **Hooks ReaperPy always understands:** before anything is saved, every hook is checked with ReaperPy's own parser and cave assembler (`cave_check.py`): patch site, `OriginTarget`, matching `OriginReturn`, all jumps lead to labels, the cave ends with the jump back, it assembles. The file is written, read back and added as a normal card; a hook ReaperPy would not understand is rejected with a reason instead of being silently ignored.
- Tests assemble the caves with a real assembler and **run them** (parameter, object field, instance/static field, return value, health that cannot drop, automatic hook search against a running loop).

### Added (original Reaper patch format)
- **`.ReapPatch` files in the original Reaper format now load and run.** Such files have no `OriginSource`: every patch site is named `XSource`
  and carries its address as a signature in `offsetFinder` (base64 bytes + mask), the way back is an `XReturn` entry. ReaperPy reported
  "no patch address in file - nothing to activate" for all of them. Now supported: several sites per patch (each with its own signature),
  several code caves in one patch (all labels together in one cave, fall-through between labels kept), one `XReturn` per site, and
  variables (`type 2` integer, `type 7` decimal) that live in the cave and are used as `[Name]` in the code. A patch is applied all or
  nothing (rolled back if one site fails). Tested against 12 real patches (Build Anything, Craft Anything, Master Code, Infinite HP, ...).
- `OriginSource` is also accepted with other spellings (`Origin Source`, `origin_source`). A file without a patch site is still loaded
  (card visible, nothing to activate) and the log lists what the file contains.
- Known limits: all variables of a patch are set to their `newValue` when it is activated (no per-variable choice yet); a patch whose
  signature consists only of the patched bytes is not recognised as active after ReaperPy was restarted while the game kept running.

### Added
- **UNITY → ITEMS:** select all or many items (Ctrl+A, INVERT, ALL ITEMS ON) and set an amount for them at once (new QUANTITY column; SELECTION / VISIBLE / TICKED / ALL, CLEAR AMOUNTS). Works for the trainer and for GIVE NOW.
- **UNITY → MANUAL:** CAVE WITH AMOUNT + BUILD CODE CAVE builds a permanent cave for the selected field with a fixed value such as 999.

## Credits

- **Pharaoh2k** - the idea of the **trainer release cards**. Pharaoh2k is also the maintainer of the **[ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)** payload (with EchoStretch and Sonic-Iso, original author OSR) that ReaperPy is built for. Thank you!
- Everyone who tested the original Reaper patches (Build Anything, Craft Anything, Master Code and the others).

Full credits and licenses: [README](../../README.md#credits-and-licenses) and [NOTICE](../../NOTICE).
