# Unity (IL2CPP) games

Items as a trainer, live values, method patches and enum names.

[← Back to the README](../../README.md)

---

## Unity (IL2CPP) games

ReaperPy reads the output of [Il2CppDumper](https://github.com/TetzkatLipHoka/Il2CppDumper) (the TetzkatLipHoka fork, which also
works on console memory dumps). The tab is called **UNITY**.

Your folder should contain `dump.cs` and `script.json` (the `DummyDll` folder is optional - it holds the same information as
.NET stubs for dnSpy/ILSpy; the offsets and addresses ReaperPy needs are in `dump.cs`). Nested folders, e.g. unzipped
archives, are fine - the files are searched for.

**Items as a trainer - tab UNITY -> ITEMS.** The same three steps as in the Unreal tab: choose the folder, **FIND ITEMS**,
**SAVE TRAINER**. ReaperPy picks the item list (the `ItemID`-style enum in `dump.cs`), the method that gives items (`AddItem`,
`GiveItem` ... with an item-ID parameter and an optional amount) and an entry point (an `Update` method of the inventory class) on
its own. Categories, several projects, preview before writing and **CHECK TRAINER** work as in the Unreal tab. Finding items needs
no console connection; saving does. Not tried on a real game yet - methods that take an item object or string are listed with the
reason and skipped (use the other pages then).

**Values, methods and names - the other pages**

1. **UNITY -> GAME FOLDER...** choose the folder, loading takes about 10 s for a large game.
2. Start the game on the console and load a save, connect ReaperPy, press **(2) DETECT MODULE**. ReaperPy takes the module
   base from the process map (`Il2CppUserAssemblies.prx`, like `il2mem.py` does) and checks it against class names read from
   memory - nothing is guessed. On failure the log shows what was found. If it fails you can type the
   base address in by hand.
3. The info box under the buttons explains the numbers (classes = blueprints from the dump, objects = what really exists in
   the game); the log at the bottom can be resized by dragging its handle, and every divider (list / values) can be dragged.
4. Use the three pages:
   - **VALUES** - press **(3) SCAN GAME** once: ReaperPy counts the real objects per class and the list shows only fields of
     classes that exist in memory (with the object count). Then search `Class.field` (gold, hp, money ...), click it, ReaperPy finds all live objects of that class
     and shows the value. After the scan, clicking a field shows its objects instantly; INSTANCES REFRESH rescans (use it for objects created after the scan). Double-click changes it (`+100` and `*2` work), **FREEZE** holds it. Static fields (singletons,
     save data) have exactly one row. Classes without a pointer in `script.json` are found by their name in memory.
   - **METHODS (cheats)** - search a method (`AddMoney`, `IsDead`, `Damage`), then *always returns TRUE / FALSE*,
     *returns value...* (int, float, bool ...) or *make method empty* (void methods). Takes effect immediately; **REMOVE**
     restores the original bytes, **ON / OFF** toggles. The tool refuses patches that would crash (e.g. emptying a method
     that returns a value). **EXPORT .reapproj** saves the patches (offset = RVA in the IL2CPP module); set ReaperPy's image base
     to the module base shown in the tab when you load them in EDIT CHEATS.
   - **NAMES (items, IDs)** - search all enums (`Item Apple`); double-click copies the numeric value for give/set functions.

Notes: object addresses change on every game start, classes/offsets/RVAs stay valid for the same game version. Use a dump of
the exact version you play. Static fields assume `Il2CppClass.static_fields` at `0xB8` (Unity 2018.3 - 6); the STATIC OFFSET
box changes that. As with UE: use this for single-player/offline games on your own console.
