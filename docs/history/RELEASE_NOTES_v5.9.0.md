# ReaperPy 5.9.0

**Items, health, gold and experience as ready-made trainers - in three clicks, for Unreal Engine and Unity - and a cheat searcher
that skips system libraries.** This release also makes trainers safe to share: a trainer built on one console no longer
overwrites random memory on another game version.

> 5.9.0 collects everything since 5.7.0, including the UE-LIVE work that was tracked as "5.8" during development.

## Highlights

### ★ ITEMS tab - all items as a trainer
Choose the game folder, click **FIND ITEMS**, click **SAVE TRAINER**. ReaperPy picks the item table and a give-function it can build
a trainer for, reads all items live, sorts them into categories (from a category/type column or the item names) and writes entries
of 14 items per category (*Fish 1*, *Fish 2* ...). Checkbox list with search, category filter and right-click menu. Large lists are
split into several projects automatically.

### ★ VALUES tab - health, stamina, mana, shield, ammo, gold, experience
One tab for **Unreal Engine and Unity**.
- **Unreal:** the values of the player character come from the SDK and are checked on the running character. For every ticked value
  ReaperPy finds the instructions that write it and builds a code cave: *value cannot drop*, or - for subtract instructions - the
  subtract is switched off (ammo and gold stop dropping, picking things up still works). Experience is fixed to a number you choose.
- **Unity (IL2CPP):** methods such as `TakeDamage`, `SpendMoney`, `UseStamina`, `UseAmmo`, `get_ExpToNextLevel` are recognised by
  name from `dump.cs`; every row says in plain words what will happen. Enemy-looking classes are marked and not pre-ticked.

### Cheat searcher: memory sections + new layout
- **MEMORY SECTIONS** panel: `eboot.bin` split into its code / read-only / data sections, game modules, one row per system
  library, heap, shared memory, stacks - each with a checkbox.
- **HIDE filter** (all system libraries, libSce\*, libc/libkernel/libm, shared memory, stacks, own wildcard patterns). Only selected
  regions are scanned, so **Unknown initial value** has less to read. Live summary of regions / MB / saved percentage.
- New three-column layout (hits | scan | sections), right-click menus, rarely used settings in an **OPTIONS** dialog.

### Trainers on other consoles and game versions
- **Version guard:** trainer patches carry `"Verify": true`. If the memory at a patch site is neither the expected original nor the
  patch, activation is refused with a clear message - instead of silently overwriting something on another game version.
- **CHECK / ADAPT TRAINER:** compares a trainer's version fingerprint and its item numbers (FNames) with your running game and can
  rewrite the trainer with your game's item numbers.
- **Cave size matched to the free code space** of your game; the "no free code space" message now shows needed bytes, the largest
  gap and which region ends are occupied.
- **Image base check** against the console's memory map (module `eboot.bin`) with **ADOPT BASE**. It never guesses a number.

## Also in this release
- **UNITY tab** for Unity (IL2CPP) games: dump loading, module base detection, live instances, value editing/freezing, method patches
  with `.reapproj` export, enum search.
- **Cheat menu:** switches and values for the player character from the SDK; right-click -> build the matching code cave
  (*value cannot decrease*, *fix value*, *NOP*).
- **Debugger:** step over, step out, run-to.
- **Console notifications** on the PS5 screen (connect, cheat on/off, debugger events).
- **English mode:** about 700 previously German texts and messages translated, new windows translated automatically.
- Snapshot RAM limited to 2048 MB (the PS5 reports "not enough memory" from 3072 MB).

## Upgrade notes
- **Trainers built with an older version** have no version fingerprint; **CHECK / ADAPT TRAINER** will tell you to rebuild them with
  ITEMS. They keep working as before (the version guard only applies to patches that carry `"Verify"`).
- Community `.reapproj` patches are unchanged: the guard is opt-in per patch.
- The cheat searcher stores its filter in `scan_filter.json` in the data folder; delete the file to reset it.
- Image base: if ITEMS reports a mismatch, use **ADOPT BASE** (value taken from the memory map) or set it in the main window.
- Removed: Silent Hill / Stellar Blade specific modules, the unused tabs `tools_ueeasy_gui`, `tools_hex_gui`, `tools_watch_gui`,
  `tools_rpc_gui`. Your personal `reaperpy_config.json` is no longer part of the repository (the app creates a new one).

## Known limitations
- The new tabs were developed and tested against a **simulated console** (654 automated tests, including real machine code for the
  cave builder). Please test with a savegame you do not need and report problems.
- Unity method recognition is a **name heuristic** - check the list. Experience can only be handled when the game has a "needed XP for
  next level" method.
- Value patches apply to **all** objects that use the patched code (enemies too).
- Only one items project should be active at a time (they share the same hook).

## Requirements
Python 3.10+ (or the Windows build), a PS5 with a ps5debug-NG compatible payload. See the [README](../../README.md).

## Credits
ps5debug-NG (OSR / Pharaoh2k, GPL-3.0). See `NOTICE` and the README.

**Full changelog:** [`CHANGELOG.md`](../../CHANGELOG.md)
