# ReaperPy 6.0.0

**Items for everyone.** Get items into an Unreal or Unity game in three clicks - without knowing tables, FNames, IDs or functions.

## What's new

### ITEMS tab for Unreal games - rebuilt
- **Only what matters is shown.** ReaperPy rates every table and every function of the game: item lists such as `DT_ItemParam` stay,
  effect, UI, sound, enemy and text tables go; the best *give* function is picked automatically. The choice boxes are hidden behind
  *Change the choice myself (advanced users only)* - a beginner never has to open them.
- **Filter levels** *strict / normal / off* (normal is the default, it keeps things like `DT_ItemSkill` or `RequestAddItem`; off hides
  nothing). If nothing is found, the log says exactly where the filter dropped things.
- **All item lists are read together** and sorted into categories, instead of only the first table.
- **Give items right away - no trainer needed.**
  - **TEST 1 ITEM** gives one item and asks whether it arrived; the result is remembered for the game, tested functions move to the
    top.
  - **GIVE NOW** gives everything you ticked immediately.
  - Both run on the game's own thread through a short code cave (the same safe way as a saved trainer). **They no longer hang or
    freeze the game**; the hook is removed afterwards.
- **TEST CHECKED ITEMS** checks the whole trainer *before* you save it (image base, give function, native code, object, hook, free
  space, every item's name) and - optionally - triggers each item once in the running game. Failed items are unticked for you.
- **Inventory limits are respected.** The amount per item is cut to the game's own limit from the item table
  (`OwnLimitByBackPack`, `OwnLimitByWarehouse` ...), so the game doesn't refuse or discard the rest. Fill the **warehouse** instead of
  the backpack by choosing the `...ToWarehouse` function in the advanced choice.
- **Hooks that actually fire.** If the game rarely calls ProcessEvent on the player controller (message *"the cave was not executed"*),
  ReaperPy now also hooks pawn, HUD, player state, game state and game mode - items arrive without wandering around.
- **No automatic slot unlock when giving items.** GIVE NOW and SAVE TRAINER no longer expand the inventory on their own; use the
  manual **INVENTORY TO MAX** button if you need more room (a game refuses an item that has no free slot).
- **INVENTORY TO MAX.** Games that ship an inventory-expansion function (for example
  `DevExpansionEnableSlotByMaxLevel`) get a button that runs it once. **The button only shows up for games that have such a
  function.**
- **Works for more games.** Functions whose class has no object in shipping builds, game-instance subsystems that the player
  controller does not reach (called through their fixed address - valid until the game is closed), functions with unusual
  parameters (`AddItemToBackPack(FName ItemId, int32 Add, FName WorkId, bool bCallEvent)`) and games without room in the image
  padding (cave in a nearby module) are handled.

### ITEMS tab for Unity (IL2CPP) games - new
Same three steps: choose the game folder (with `dump.cs` + `script.json`), **FIND ITEMS**, **SAVE TRAINER**. ReaperPy picks the item
enum, the give method and a safe entry point itself. Categories, several projects when the cave doesn't fit, preview before writing,
**CHECK TRAINER** - just like the Unreal tab. Finding items needs no console connection.

### Self-update copes with files in use
Windows does not allow replacing a file that the running program has open (`base_library.zip`), and OneDrive or a virus scanner can
hold files for a moment. The updater now retries, parks the new version of such a file next to the old one and finishes the job when
ReaperPy has closed: **Restart now** applies the parked files and starts ReaperPy again (closing it yourself works too - the next
start finishes the update). Everything else is still installed with a backup and rolled back on errors.

### Trainers on other consoles
- Fixed: *"does not fit into the largest free code gap (0 bytes)"* when an earlier trainer's cave was still in memory. Leftover
  ReaperPy caves are recognised and reused (also for Unity).
- **CHECK / ADAPT TRAINER** shows examples of changed item numbers and writes every change to the log.

## Update
- **From 5.9.1:** ReaperPy offers the update (dialog with these notes -> *Install now*). **Heads-up:** the updater of 5.9.1 cannot replace
  files that are open in the running program. If it ends with *"installation failed and was rolled back: [WinError 32] ... base_library.zip"*,
  nothing was changed - unpack `ReaperPy_v6.0.0_win64.zip` over your folder once by hand (see below). **From 6.0.0 on this is fixed**
  (see *Self-update* above). Your config, profiles, logs, library and `applied.json` are kept either way.
- **From 5.9.0 or older:** download `ReaperPy_v6.0.0_win64.zip` from this page, check it against the `.sha256` file and unpack it over
  your old folder (copy `reaperpy_config.json`, `profiles/`, `library/` over if you unpack into a new folder).
- Trainers saved with older versions keep working; saved *test results* of older versions are dropped and have to be redone once.
- **Fixed-address trainers** (games where the inventory object is a subsystem) are valid for one game session: after every game start load
  a save, **FIND ITEMS**, **SAVE TRAINER** again. The tab tells you when this applies.

## Known limitations
- Developed and tested against a **simulated console** (932 automated tests on Linux and Windows) plus two real Unreal games. The real
  console, the real look of the windows and other games are not covered - try with a savegame you don't need and attach
  `logs/reaperpy.log` to bug reports.
- **Unity ITEMS has not been tried on a real game yet.** It needs an item-ID parameter that is a number or enum.
- Value patches apply to **all** objects that use the patched code (enemies too). Only one items project should be active at a time.
- Whether an item really appears in the inventory is judged by you (TEST 1 ITEM asks); some games enforce limits elsewhere.

## Requirements
Python 3.10+ (or the Windows build), a PS5 with a ps5debug-NG compatible payload. See the [README](../../README.md).

## Credits
ps5debug-NG (OSR / Pharaoh2k, GPL-3.0). See `NOTICE` and the README.

**Full changelog:** [`CHANGELOG.md`](../../CHANGELOG.md)
