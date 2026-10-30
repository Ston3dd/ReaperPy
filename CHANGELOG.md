# Changelog

Older release notes (German) are in [`docs/history/`](docs/history/).

## Unreleased

### Added
- **UNITY > ITEMS tab** - the same three steps as the Unreal ITEMS tab, for Unity (IL2CPP) games: pick the game folder, click **FIND ITEMS**, click **SAVE TRAINER**. The tool picks the item list (the `ItemID`-style enum from `dump.cs`), the method that gives items (`AddItem`, `GiveItem` ... with an item-ID parameter and an optional amount) and an entry point (an `Update`/`LateUpdate`/`FixedUpdate` method of the inventory class, or of a class with a field that points to the inventory, or any `Update` for static methods) on its own, and shows what it chose in drop-downs. The trainer is written like the Unreal one: categories split into packages of 14, several projects when the cave does not fit, preview before writing, `LIESMICH_TRAINER.txt`, **CHECK TRAINER** for the version anchors. Finding the items needs no console connection.
- How it works (`unity_items.py`): a `jmp` at the start of the chosen `Update` method; its first instructions are moved into the cave (rip-relative addresses and `jcc`/`call`/`jmp` are re-encoded). The cave checks one switch byte per entry, clears it atomically and calls the game's give method once per item (System V call, `MethodInfo* = 0`), then runs the moved instructions. Raw machine code, no assembler needed to apply it.
- The leftover-cave fix (cave left behind after BASIS is switched off / loaded via GoldHEN) also covers the Unity cave: it is recognised by its code signature, the space is reused, the base patch gets `VerifyAlso`, a free-space `0 bytes` is explained.
- START tab card and English texts for the new tab.
- Tests: `tests/test_unity_items.py` (finding, relocation, encoding checked against GNU `as`, **the cave is executed on an x86-64 CPU**: arguments, `this` modes, stack alignment, callee-saved registers, switch reset, original code still runs, leftover cave) and `tests/test_gui_unity_items.py`.

### Known limits
- **Not tested on a real game or console yet.** Needs an item-ID parameter that is a number or enum; methods that take an item object/string are listed with the reason and skipped (use WERTE/EXPERTE then).
- With a `this` taken from a field of the hooked class (e.g. `Player.inventory`) the items go to the first such object that runs after the click.

### Fixed
- **Trainer on another console: "does not fit into the largest free code gap of the game (0 bytes)".** The cave of an earlier trainer stays at the end of the code region after BASIS is switched off (or when it was loaded through GoldHEN/etaHEN). The free-space scan saw that region end as occupied and reported 0 bytes, so SAVE TRAINER and CHECK / ADAPT TRAINER failed on that console although game and version were identical. Leftover ReaperPy caves (also several stacked ones) are now recognised by their code signature and the space is reused; the base patch gets a `VerifyAlso` list so it activates both on that console and on a clean one; old switch bytes are left alone (new switches are placed in front of them). If there is really no space (foreign data at the region end), the message now says so and the log lists why. The free-space scan also looks through the last 64 KB of each executable region for zero/0xCC runs, not only at the very end, so a foreign cave (GoldHEN/etaHEN cheat, plugin) sitting at the end of the page padding no longer hides the free part in front of it. With 0 bytes the log now shows a map of the region end (`.` = 00, `c` = CC, `#` = data). Tests: `tests/test_cave_trainer.py` (`LeftoverCaveTests`).

## 5.9.1 - 2026-10-30

**Hotfix - please update if you are on 5.9.0.** In 5.9.0 the connect step failed with
`[net] ERROR module 'imagebase' has no attribute 'check_base'`, so ReaperPy could not be used at all. 5.9.1 fixes this and
also brings the self-updater, version anchors for trainers and the trainer preview (all listed below). 5.9.0 builds have **no**
self-update: download 5.9.1 once by hand (see the release page); from then on ReaperPy offers updates itself.
Release notes for GitHub: [`docs/history/RELEASE_NOTES_v5.9.1.md`](docs/history/RELEASE_NOTES_v5.9.1.md).

### Added
- **Self-update from GitHub Releases.** On start (4 s after the window opens) ReaperPy asks GitHub for the latest release. If it is newer, a dialog shows the release notes and offers **Install now / Later / Skip this version**. *Install now* downloads the release zip, checks its SHA-256, unpacks it into a staging folder, replaces the program files with a backup + automatic rollback, and then says that ReaperPy has to be restarted (with a **Restart now** button). Config, profiles, logs, library and `applied.json` are never overwritten. A git checkout is never touched (it only tells you to `git pull`). START tab -> *Check for updates* runs the same flow manually. Turn it off with `"auto_update_check": false`; use another repository with `"update_repo": "owner/name"`. The old `update_url` (own JSON file) still works and only shows a hint. Tests: `tests/test_updater.py`.
- **Version anchors as signatures.** Trainers now store the start of each function as an AOB signature with wildcards instead of fixed bytes, so they survive small game updates. If a function only moved (exactly one hit elsewhere), the ITEMS tab offers to adapt the trainer to the new addresses; if it is gone or ambiguous it still says "other game version".
- **Preview before saving a trainer.** The ITEMS tab shows where the cave and the switch would land (region and `r-x`/`rwx`, warning for writable caves) and writes nothing until you confirm.
- GitHub Actions: tests on every push/PR (Linux + Windows, with keystone and capstone) and a release build on `v*` tags (Windows zip + `.sha256`, notes from this file). The updater uses the `.sha256` of the release when GitHub gives no digest.
- `scripts/changelog_from_git.py` drafts a changelog section from the commit messages (`Added` / `Changed` / `Fixed` blocks).
- Guard tests: no test files in the repo root, explicit encoding for all text files.

### Fixed
- **Connecting failed with `module 'imagebase' has no attribute 'check_base'`.** The image base check that runs on connect
  (`gui._check_image_base`) called a function that had been renamed to `imagebase.check_image_base` (with a new result type).
  The check now works again: matching base -> info line, shifted base -> warning and the image base is set to the one found in
  the console's memory map, no module names in the map -> warning with the module list. Test: `tests/test_gui_imagebase_check.py`.
- `cave_trainer.check_anchors()` / `anchor_problem()` were used by the GUI and the tests but did not exist; `spec_document()` crashed with signature-style anchors.
- Export: the code cave now prefers non-writable code regions (`r-x`); writable (`rwx`) regions are only a fallback and log a warning. The report names the region. On disable only the hook is restored and the cave stays (zeroing it could crash a thread still running inside).
- Missing English texts for the UE-LIVE connection fallback messages.
- Test files had landed in the repo root (`module incorrectly imported` in CI); `F402` loop variable shadowing an import in `tools_gui.py`.
- File handles left open in `ue_auto.load_dump` / `main_game`; the test suite no longer produces `ResourceWarning`s.
- Long byte dumps in the patch log are cut to 32 bytes plus `... (+N bytes)`.

### Changed
- Lint: `ruff check .` is clean (rules `F`, `E711`, `E712`, `E721`, `E731`; style families stay off until the code base is
  cleaned up). Unused imports and variables removed, lambda assignments turned into functions, dead code in `tests/ue_world.py`
  removed. `ps5_ext` keeps `STATUS_ALREADY_DEBUG` / `STATUS_INVALID_INDEX` as explicit re-exports used by `debugger.py`.
- Test suite: 737 tests (CI: Linux Python 3.10 / 3.12, Windows Python 3.12).

## 5.9.0 - 2026-10-29

Collects everything since 5.7.0, including the UE-LIVE work that was tracked as "5.8" in
[`docs/history/CHANGES_5.8_uelive_de.txt`](docs/history/CHANGES_5.8_uelive_de.txt). Release notes for GitHub:
[`docs/history/RELEASE_NOTES_v5.9.0.md`](docs/history/RELEASE_NOTES_v5.9.0.md); German summary:
[`docs/history/CHANGES_5.9_de.txt`](docs/history/CHANGES_5.9_de.txt).

### Highlights
- **ITEMS tab** - all items of an Unreal game as a ready-made trainer in three steps.
- **VALUES tab** - health, stamina, mana, shield, ammo, gold and experience as patches, for Unreal Engine and Unity.
- **Cheat searcher** - memory sections panel (eboot.bin split up, hide system libraries for faster scans) and a new layout.
- **Trainers on other consoles / game versions** - version guard, check/adapt trainer, cave size matched to the free space,
  image base check.

### Added
- **New tab ITEMS - all items as a trainer in three steps** (`ue_items.py`, `tools_items_gui.py`). Choose the game folder -> **FIND
  ITEMS** (automatically picks the item table and a buildable give-function, reads all items live, sorts them into
  categories) -> **SAVE TRAINER** (amount per item; entries of 14 per category such as *Fish 1*, *Fish 2*; more than 400 items
  are spread over several projects). Checkbox list with search, category filter, right-click menu. Replaces the former
  five manual steps across UE-LIVE / UE DISCOVERER. START tab gets a card for it. Tests: `tests/test_ue_items.py`,
  `tests/test_gui_items.py`.
- **New tab VALUES - health, stamina, mana, shield, ammo, gold, experience as patches, for Unreal Engine and Unity**
  (`values_auto.py`, `tools_values_gui.py`). Unreal: values of the player character from the SDK, one code cave per ticked
  value (value cannot drop / subtract instruction switched off / fixed number; experience fixed to a chosen value). Unity:
  methods recognised by name from `dump.cs`, patched empty or to a fixed return value, with live-read original bytes and
  `"Verify"`. Cheat menu gets the category *Experience/Level*. Tests: `tests/test_values_auto.py`, `tests/test_gui_values.py`.
- **Cheat searcher: MEMORY SECTIONS panel** (`regionfilter.py`, `tools_sections_gui.py`, `scanner.py`). The tab now lists what is
  in the game's memory - **eboot.bin split into its code / read-only / data sections**, game modules, one row per system
  library, heap, shared memory, stacks - with a checkbox per row and a **HIDE filter** (presets such as *all system
  libraries*, *libSce\**, *libc / libkernel / libm* plus own wildcard patterns, right-click *Hide module*). Only the
  selected regions are scanned (`Scanner.regions(pick=...)`), so **Unknown initial value** has less to read. The summary shows
  regions / MB / saved percentage and, after a scan, an estimated read time. The filter uses a fresh memory map at scan start
  and is saved in `scan_filter.json`. Tests: `tests/test_regionfilter.py`, `tests/test_scan_sections_gui.py`.
- **Trainers on other consoles / game versions (ITEMS tab).** Trainer projects now carry a version fingerprint and are
  written with `"Verify": true`; activating such a patch is refused when the memory at the patch site is neither the expected
  original nor the patch (previously the bytes were written blindly, which looked like "already active" or "nothing happens"
  on another game version). New **CHECK / ADAPT TRAINER**: compares fingerprint and item numbers (FNames) with the running
  game and can rewrite a trainer with your game's item numbers. The cave size is matched to the free code space of the game
  (`cave_trainer.capacity` / `fit_options`), so large trainers split into several projects instead of failing with "no space";
  the "no free code space" message now shows the numbers and why. **Image base check** (`imagebase.py`) against the console's
  memory map with ADOPT BASE (never guessed). Tests: `tests/test_trainer_portability.py`, `tests/test_imagebase.py`.
- **UNITY tab for Unity (IL2CPP) games** (`il2cpp_dump.py`, `tools_unity_gui.py`): loads the Il2CppDumper output (`dump.cs`,
  `script.json`; nested folders are found), detects the IL2CPP module base by checking class names in memory, lists live
  instances by their class pointer (name-scan fallback when `script.json` has none), edits/freezes values, patches methods
  (return TRUE/FALSE/value, make void empty - refused when the return type does not fit) with restore and `.reapproj` export,
  and searches enum names (item IDs). Module detection uses the module names of the process map (like `il2mem.py`) and
  treats execute-only code regions as valid module starts (PS5); on failure the log shows what is in memory.
  UNITY tab layout: the three steps are large buttons, an info box explains the numbers, the status line wraps, the log
  is part of the tab and resizable, and the list/values divider moves freely. All Unity messages are translated (also those with
  inserted numbers); `tests/test_unity_i18n.py` guards this. **SCAN GAME** counts the real objects per class in one heap pass (subclass objects count for their base class) and the field
  list then shows only classes that exist in memory; compiler-generated closure/iterator fields are hidden and
  `<X>k__BackingField` is shown as `X`. The scan also remembers the object addresses, so clicking a field afterwards finds its
  instances instantly (each address is re-checked); INSTANCES REFRESH rescans the heap, skipping module regions (.prx/eboot). Tests: `tests/test_il2cpp.py`, `tests/test_unity_tab.py`.
- **Cheat menu: right-click -> build matching code cave** (`cheatmenu_cave.py`, `tools_cheatmenu_gui.py`). Finds the instructions
  that write the selected value (from the game folder's `dump.bin`, otherwise read live from the console), picks the best hit
  and saves a `.reapproj` in the project's patch folder. Cave types: *Value cannot decrease*, *Fix value* (new,
  `ue_instr.force_cave_patch`) and *NOP*. "Choose hit" lists all hits with the reasons why a cave is or is not possible.
  Offsets below 0x80 are refused (search would be unreliable). Applies to ALL objects using that code (enemies too).
- **Console notifications** (`ps5_notify.py`): messages on the PS5 screen when ReaperPy connects, when a cheat is switched
  on/off (with a "debugger attached" note while a debug session exists), and when the debugger attaches / detaches / loses the
  connection; optional message per breakpoint hit. Bulk actions send one summary. Configurable with `ps5_notifications` and
  `ps5_notify_hits`. The notification texts that already existed in `i18n.py` were never sent before.
- Credits for the **ps5debug-NG** payload (OSR / Pharaoh2k, GPL-3.0) in `README.md`, `NOTICE` and the German README.
- **CHEAT MENU tab** (`cheatmenu.py`, `tools_cheatmenu_gui.py`): switches and values for the player character, built from the
  SDK. Works without a CheatManager (shipping builds): engine values (`bCanBeDamaged`, `MovementMode` fly, walk/fly speed,
  jump, gravity, time dilation) and game values found by the candidate heuristic (health, stamina, ammo, money ...). Only
  objects owned by the character are written; everything is released when the character changes.
- **Debugger:** STEP OVER, STEP OUT and run-to (temporary breakpoints in reserved slots), detection of "console already
  executed the instruction", step waits for the step event with a clear error if it never arrives.
- **UE Discoverer:** every give-function is checked up front (✔ / ✗ with the reason), item name search in the table list,
  the ID number is taken from the selected row, and a "next step" hint is shown after the analysis.
- **Tools i18n:** drop-down lists are translated too; the code keeps receiving the original (German) values from
  `get()`. About 450 previously untranslated texts added.
- `LICENSE` (MIT), `NOTICE`, English `README.md`, `CHANGELOG.md`, `.gitignore`, `.gitattributes`, `reaperpy_config.example.json`.

### Changed
- **Cheat searcher layout** redesigned: three columns (hits | scan | sections) with card headers, filled primary buttons,
  right-click menus for hits and address list, rarely used settings moved to an **OPTIONS** dialog (self-test and region
  report are there too). No functions removed.
- **Snapshot RAM** is limited to **2048 MB** (the PS5 reports "not enough memory" from 3072 MB). The FIND VALUE drop-down
  offers 512 / 1024 / 2048 MB, 2048 MB is the default (it was 4608 MB), and the scan log never recommends more than 2048 MB.
- Credits: PS5Debug-studio is described as what it is (a few tweaks, no code).
- **Debugger flow** now follows the server-managed breakpoint step: CONTINUE is a plain continue (no RIP rewind, no
  remove/re-arm), breakpoints removed while stopped are applied on the next continue, and the keep-alive never rebuilds
  the connection while a thread is stopped.
- Build: `ReaperPy.spec` bundles `LICENSE`, `NOTICE`, `README.md` and `licenses/`.

### Fixed
- English mode: the GoldHEN/etaHEN export dialog, the status line ("connected"), the main log and about 250 error messages
  from the modules were still German. New windows are now translated automatically (`tools_i18n.install_toplevel_hook`).
- The English dictionary failing to load is no longer silent: a warning appears in the log.
- Cave allocator logs a warning when the image base lies in no memory region and falls back to regions above it; the
  matching tests use the current API (`image_base=`, `cave_trainer.image_span`).
- Keep-alive reconnect counted a reconnect before the state was reported (flaky test).

### Removed
- Silent Hill specific module `silent_hill_ai_profile.py`, its test, its button in the (unused) `universal_gui.py` and the
  matching translations. `cheat_testbench.py` now names the game after the folder / ZIP instead of guessing "Palworld" or
  "Silent Hill"; the category "Stealth / AI detection" is now the generic "AI / perception".
- Stellar Blade specific modules and tests (`sb_*.py`, `tools_sb_gui.py`, `combine_add_items.py`); the generic replacements
  `cave_trainer.py`, `ue_tables.py` and `ue_hook.py` were already in place.
- Unused tabs `tools_ueeasy_gui.py` (replaced by UE-LIVE), `tools_hex_gui.py`, `tools_watch_gui.py`, `tools_rpc_gui.py`.
- Duplicate test files in the project root, `__pycache__`, a stray empty text file, and your personal
  `reaperpy_config.json` (console IP and local paths; the app creates a new one).
- 285 unused entries in the English dictionary.

## 5.7.0

See [`docs/history/CHANGES_5.7_de.txt`](docs/history/CHANGES_5.7_de.txt) (German): keep-alive and reconnect for the debug
connection, automatic code detection by title ID, new icon and splash screen, START tab and simple/advanced tab split,
right-click menus everywhere, English for all tool tabs, game profiles (notes, favourites, groups, hotkeys), update check,
PyInstaller build.
