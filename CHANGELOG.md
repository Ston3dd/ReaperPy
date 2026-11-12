# Changelog

Older release notes (German) are in [`docs/history/`](docs/history/).

## Unreleased

### Fixed (Unity scanning itself to death)
- Every field click in **UNITY → MANUAL** started its own full memory scan, several at once. The memory is now scanned **once** (progress in %, **CANCEL SCAN**), after that all fields are instant; classes with an `Instance` field need no scan at all. The live give and the cheat menu use the same finder (`unity_objects.py`).

### Added
- **UNITY → ITEMS:** select all or many items (Ctrl+A, INVERT, ALL ITEMS ON) and set an amount for them at once (new QUANTITY column; SELECTION / VISIBLE / TICKED / ALL, CLEAR AMOUNTS). Works for the trainer and for GIVE NOW.
- **UNITY → MANUAL:** CAVE WITH AMOUNT + BUILD CODE CAVE builds a permanent cave for the selected field with a fixed value such as 999.

## 6.3.0 - 2026-11-12

**Easier from the first number to a finished cheat: a guided assistant, fuzzy value search, items found without relying on names, Unity on par with Unreal, and a calmer tools window.** Please update - nothing else changes for existing projects.

### Added (fuzzy value search)
Games often show rounded numbers (health 75 while the game holds 74.6) or only a bar. The exact search finds nothing then.
- **Approximate numbers with a tolerance.** Type `75~5` (75 plus or minus 5), `75~10%`, `~75` or `ca. 75` (standard tolerance 5 %). In **FIND VALUE** there
  is a new comparison **Fuzzy (± tolerance)** (the second field becomes **TOLERANCE**, `5` or `5%`); in the **ASSISTANT** tick **Approximate (fuzzy)**
  or just type the range - **NARROW DOWN** accepts the same forms. It runs as the scanner's existing range compare, so the console payload needs
  nothing new. Whole numbers always get at least plus or minus 1; bounds are clamped to the value type (`UInt8` never goes below 0 or above 255).
- **Unknown number as a decimal number.** The ASSISTANT can start an unknown-value search as *Float* (tick **Decimal number**), and has a new
  **CHANGED** button next to DROPPED / ROSE / STAYED THE SAME.
- New module `fuzzy.py`; `scanner.check_values()` validates the inputs before a scan with a readable message. Tests: `tests/test_fuzzy.py` and five new
  cases in `tests/test_gui_assist.py`. New section "Rounded numbers: fuzzy search" in the how-to guide "Find a value" (German and English).

### Added (guided assistant and ReapPatch export)
The ASSISTANT tab guides from a number in the game to a finished cheat (see the how-to guide "Cheat in four steps"); cheats can be saved as `.ReapPatch`.

### Added (finding items without relying on names - UNREAL and UNITY ITEMS)
Before, the item list was recognised **only by its name** (`DT_ItemParam`, `ItemID` ...). Games with other names (`Mst_Buki`, `E_Obj`,
`DT_Param001`) found nothing, and the manual choice was a list of technical names nobody could judge. Now, inside the existing ITEMS cards
(no new window):
- **Recognised by content.** If no table / enum is found by name, ReaperPy reads the rows of every table (names only, capped, with a time limit
  and a cache) and rates them: number of entries, groups of names like `Sword_*` / `Potion_*`, item words, and effect / UI / sound words as a
  minus. A list found this way is used but flagged with a warning sign and its first names; one uniform prefix alone ("Mst_Buki_0001 ...")
  is never enough. New module `item_finder.py`.
- **"Type the name of an item you can see in the game"** + **SEARCH IN ALL LISTS**: the list that contains the name becomes the item list;
  lists that look like items rank before accidental hits (an effect table with 40 `Potion_Splash_*` does not beat the real item list).
  All hits are offered under **Possible item lists** (name, size, first names). **CHECK ALL LISTS** does the content rating on demand.
- **Unity: a give method identifies the item enum even if its name says nothing** (`Put(E_Obj id, int n)`): `give_enum_types()` finds the enum
  types of give-named methods; before, such an enum was dropped before the give bonus was even considered (chicken-and-egg in
  `classify_give`). Content-only enums rank below any name match; noise (colours, `UIButtonKind` with B0..B29) stays out.
- **Filter loosened once automatically** when the strict filter finds no give function / method; the result is marked "fallback - please check
  with TEST 1 ITEM" instead of silently showing nothing.
- **Plain reasons instead of a bare "not recognised".** The message says how many tables / lists were checked (and whether the time limit hit)
  and what to do next. (The two new buttons are deliberately not greyed out without a console: UNITY works from the dump alone, and in UNREAL
  a clear message says to press FIND ITEMS first.)

### Fixed
- **One unreadable table aborted UNREAL FIND ITEMS** with a memory error (most likely with the filter on "off", where every table is a
  candidate). Unreadable tables are now skipped with a log line and the next one is tried.

### Added (look and feel of the tools window)
- **Status lights on START.** "Connected?" and "Codes loaded?" show a green / red / grey dot instead of a ✓/✗ character in running text.
- **CHECK CONNECTION in colour.** Each step of the result is green (ok), red (problem), yellow (note) or grey (skipped); the explanation sits
  indented under the failed step.
- **Buttons that need the console are greyed out while the main window is not connected** (READ, WRITE, DISASM, TEST ON, FIRST SCAN, WATCH,
  debugger and live-game buttons ...); the tooltip says why. They unlock by themselves when you press CONNECT: the tools window now follows the
  main window and **reconnects automatically** (before, you had to reopen it). File and export buttons are never greyed out. The list is
  `tools_ui.NET_BUTTONS`; a test checks that every name in it still exists.
- **Tooltips for technical terms** (OFFSET (from image base), OriginReturn, SIGNATURE, PATTERN, CAVE CODE, NOP, SNAPSHOT, UPDATE SCAN, WATCHPOINT,
  pointer depth ...): hover for a moment, German and English. Labels with an explanation show a question-mark cursor; EDIT CHEATS has small "?"
  chips next to OFFSET, OriginReturn, CAVE CODE and SIGNATURE.
- **Empty tables explain what to do** ("No hits yet. Enter a value and click FIRST SCAN.") in the scanner, the address list, the assistant, the
  pointer tab and the pattern search; the hint disappears with the first row.
- **"working ..." indicator** with a thin progress bar in the tools window header while a background job runs (shown after 0.25 s so short
  jobs do not flicker).
- **Keyboard:** buttons show a bright focus ring when reached with the Tab key, and Return presses the focused button (before: only Space).

### Changed
- Explanation texts (START, ASSISTANT, the hint line in EDIT CHEATS, tooltips) use a proportional font (Segoe UI); Consolas stays for addresses,
  bytes and code (`FONT_TEXT` in `tools_common.py`).
- **One spacing scale.** All `padx` / `pady` values in the tools windows now come from 0, 2, 4, 8, 12 and 16 px (before: 1, 3, 5, 6, 7, 10, 14,
  18 ... mixed). A test keeps it that way. Gaps change by at most 2 px.

### Fixed
- **OriginReturn was a fixed 8 unless the disassembler filled it.** A cave written by hand (or loaded without the value) returned to the wrong
  place whenever the overwritten instructions did not end exactly at byte 8 - the game then crashed or ran garbage. The field is now **empty =
  automatic**: ReaperPy derives it from the ORIGINAL bytes (whole instructions covering at least 8 bytes, the same rule as the disassembler
  template; plain byte count if no disassembler is available) and logs `OriginReturn automatisch: N Bytes` on SAVE and TEST ON. If ORIGINAL has
  fewer than 8 bytes, it uses 8 and warns. A typed value is still honoured, but values below 8 and non-numbers are rejected with a clear message
  (a cave hook always overwrites 8 bytes, so a smaller return lands inside the hook).

### Added (EDIT CHEATS for beginners)
- **Simple / advanced view in EDIT CHEATS.** The tab opens in the **simple** view: NAME, AUTHOR, OFFSET, ORIGINAL and NEW - the patch type,
  OriginReturn, cave code and signature row are hidden. The new **ADVANCED OPTIONS** checkbox shows them again; the choice is remembered
  (`cheat_editor_advanced` in the config). A line at the top explains the current view; a cheat that uses a code cave (for example from a
  preset) says so with its line count instead of showing the code.
- **Signature on SAVE.** In the simple view, SAVE creates a missing signature itself (so the cheat survives a game update). If the signature is
  not unique, or the console is not connected, the log says so and the cheat is saved anyway. Advanced view and entered signatures are not touched.

### Added (easier start)
- **START tab: CHECK CONNECTION (VERBINDUNG PRÜFEN).** One button checks, one step after the other, whether the **IP** is valid (typical
  slips are named: empty, `ip:port`, `192.168.1`, a URL), whether the **PS5 answers** (timeout / refused / no route / unknown name), whether the
  **payload** speaks ps5debug-NG and whether a **game is running** - and says in plain words where it stops and what to do (for example "payload
  not loaded - send it again after every PS5 restart"). If the entered port is closed but the payload answers on another common port, that port
  is used and named. Read-only: it opens its own short connection and closes it. After a green check it reminds you of firewall port 755. New
  module `conncheck.py`, German and English.
- **Hints in the log when CONNECT fails.** Under the error line the main window now adds a `[net]` hint with the likely cause and the next step.
  The cause of the last failed port is kept (`connect_auto` re-raises it with `from`), so the hint also works after the automatic port search.
- **SHOW MAIN WINDOW** (START, step 1) now also puts the cursor into the **PS5 IP** field and selects it.

### Changed
- **START tab leads to the ASSISTANT.** Step 2 is now **GO TO ASSISTANT** ("Find a value and build a cheat"); step 3 points to EDIT CHEATS, where the
  assistant puts the finished cheat. The full searcher stays reachable as **GO TO FIND VALUE** under "More". The how-to guides "First steps" and
  "Troubleshooting" mention both changes.

### Removed
- The **SPIELER / GEGNER (PLAYER / ENEMY)** tab and its button in the DISASSEMBLER tab from 6.2.0: too complicated in use. The how-to guide
  "Player or enemy?" is gone too (guides are now 14 with the new "Cheat in four steps").

### Added (Unity catches up with Unreal)
- **UNITY ITEMS: give and test live.** New buttons **TEST 1 ITEM**, **TEST CHECKED ITEMS** and **GIVE NOW** call the give method in the
  running game (live object from the IL2CPP scan, item value and amount in the argument registers) - no trainer file needed. After a
  single test the tool asks whether the item arrived and remembers the answer (**tested** ranking: +4 / -8, a failed method is replaced
  by the next one). Calls are never repeated and stop at the first error.
- **UNITY ITEMS: more give methods.** New **filter** for the give methods: *strict* (Add/Give/Grant ...), *normal* (also Put/Insert/Craft/
  Equip/Unlock ...) and *off* (every method with an item parameter). Only integer/enum/bool parameters can be passed; methods taking
  names, objects or decimals are still listed with the reason why they cannot be called. New module `unity_live.py`.
- **New tab UNITY > CHEAT MENU** (same operation as the Unreal one): ready switches and values from `dump.cs` - method patches (damage,
  spending money, stamina use ...) and fields (health, gold, stamina, EXP, hunger ...). ON/OFF, set value, hold (rewritten every
  250 ms), ALL OFF restores the originals. **BUILD CODE CAVE** (fields) finds the instruction that writes the field and saves the cave as
  `.reapproj`; **SAVE PATCH** (methods) saves the ready patch. New modules `unity_cheatmenu.py`, `tools_unity_cheatmenu_gui.py`.

### Added (both engines)
- **More values are found** (Unreal SDK and Unity dump): hunger/thirst/sanity/oxygen ("Hunger/Durst" category), more currencies
  (diamonds, crystals, shards, rupees ...), more experience words (skill/perk/stat points, rank, reputation ...), more stamina words
  (vigor, oxygen, fuel ...). Skill points now count as experience, not money.

### Changed
- **Unreal CHEAT MENU: building a code cave from a cheat is visible now.** Buttons **BUILD CODE CAVE** and **CAVE: CHOOSE HIT** sit next to
  SET VALUE (before it only worked via right-click). Without an active project the tool now asks for a folder instead of refusing.

### Added
- **New tab ASSISTANT (first tab)**: four steps without assembler knowledge.
  1. **Find the value** - type a number from the game (or choose "Number unknown" for bars) and press **SEARCH**.
  2. **Narrow down** - change the value in the game and press **NARROW DOWN** with the new number, or **DROPPED / ROSE / STAYED THE SAME**
     when the number is unknown. At 50 hits or fewer the addresses with live values are listed, with advice what to do next.
  3. **Who changes the value?** - **WATCH** sets a write watchpoint on the chosen hit (attaching the debugger if needed). Every hit is
     resolved to the instruction that really wrote the value (the one before the reported RIP, chosen by checking its memory operand
     against the watched address) and resumed at once, so the game keeps running. The table shows the instruction, a plain-words
     explanation and how often it ran.
  4. **Create the cheat** - **PRESET...** for the marked instruction, or open it in the disassembler.
  - New how-to guide "Cheat in four steps". New modules `assist.py`, `tools_assist_gui.py`.
- **ReapPatch export** for Reaper: **SAVE** in the cheat editor tab now also offers `*.ReapPatch`, written in the exact format Reaper uses
  (byte-identical to a real Reaper file, checked by a test). Reaper turns it into a `.ShnExt` itself. New module `reappatch_fmt.py`.
  - New button **SAVE AS REAPPATCH ...** in the GoldHEN / etaHEN export window writes the marked patches (any source format) as
    `.ReapPatch` files into a folder of your choice - no console connection needed, existing files are never overwritten.

## 6.2.0 - 2026-11-09

**The assembler is easier for beginners, and the tool can tell the player from enemies.** Please update - nothing else changes for existing projects.

### Added
- **Assembler without assembler knowledge** (DISASSEMBLER tab):
  - New column **EXPLANATION** says in plain words what the selected instruction does (about 70 instructions, German and English).
  - New button **PRESET...**: ready-made changes instead of typing asm - switch the instruction off, always set the value to a number,
    end the function right away. Writes a patch or builds the code cave for you.
  - **CHANGE...** now shows a live preview while you type (size, fits or not, padded with NOPs) and explains errors in plain
    sentences with the line and an example (the original message stays in brackets). The live preview needs `keystone-engine`.
  - The CONVERTER tab uses the same friendly error messages.
- **New tab SPIELER / GEGNER (PLAYER / ENEMY)** for games where the player and enemies share the same health code (a normal
  cheat would make everybody immortal). Record a few hits in phase A (only you are hit) and phase B (only enemies are hit); the tool
  compares them and finds what tells the player apart: the **caller on the stack**, a **field in the object** (team / type) or the
  **object address**. Results are ranked (stable after restart, confidence). **-> CHEAT EDITOR** builds a cave that applies the cheat
  only to the player (or only to enemies). Red-zone safe, flags preserved. New button **PLAYER / ENEMY...** in the DISASSEMBLER tab.
  - New how-to guide "Player or enemy?" (guides are now 14).
- New modules `asm_explain.py`, `asm_help.py`, `asm_recipes.py`, `whois.py`, `tools_who_gui.py`, `tools_asm_easy_gui.py`.

### Fixed
- Rip-relative operands in caves (`[rip + @hook+N]`) were placed wrongly when a jump to a label further down came before them
  (the size of an assembled forward jump differs). They are now measured on the finished code.
- Removed an unused import in `tools_gui.py`.

## 6.1.0 - 2026-11-08

**How-to guides for beginners, built into the program.** Please update - nothing else changes for existing projects.

### Added
- **How-to guides for beginners.** 13 step-by-step guides in German and English (first steps, find a value, edit cheats, assembler for
  beginners, items in Unreal / Unity games, values and live values, export, pointers, debugger, advanced tools, troubleshooting,
  glossary). They are plain Markdown files in `docs/howto/de` and `docs/howto/en`, so they can be read on GitHub as well. The program
  shows them in the language of the DE / EN switch (the open guide switches at once), with a search box and links between guides.
  - New **HOW TO** button (German: ANLEITUNGEN) in the top bar of the main window opens the guides in their own window - no console
    connection needed.
  - **? HELP** in the tools window and the entry in the START tab open the same window at the guide that belongs to the current tab.
  - Tests check that both languages have the same structure, that every link and every button name used in a guide really exists in the
    program, that every tab has a guide, and that the guides contain no game names and no emoji or symbol characters.
- **English texts appear at once.** Texts set later (`configure(text=...)`, new widgets, context menus, table headings and tab titles) are
  translated when they are set, instead of showing German until the next 2-second pass (new `install_text_hooks` in `tools_i18n.py`, test
  `test_i18n_text_hooks.py`).
- `theme.py`: colour for the warning boxes in the guides (`CALLOUT_WARN_BG`), covered by a contrast test.

### Changed
- `ReaperPy.spec` packs `docs/howto` into the build.
- README: new section "How-to guides for beginners", file overview extended.

## 6.0.2 - 2026-11-07

**Richer colours, general item table detection and complete English texts.** Please update if you use the ITEMS tab or the English interface.

### Added
- `theme.py`: one central colour palette for the whole interface (main window, tools window, update dialog, splash screen). A test
  fails if a hard-coded colour code sneaks into another interface file.

### Changed
- **Richer colours:** deeper blue surfaces in four steps, clearly visible borders, brighter secondary text, a green OK colour that is
  no longer the same as the accent, and a strong blue selection colour in lists and drop-downs. Horizontal scroll bars, pane
  dividers and plain ttk frames are dark now as well.
- **Item table detection works the same for every game:** run-together or upper-case names (`ITEMPARAM`, `MSTITEM`) are split into
  known words instead of searching for substrings, so `Software`, `Hardware`, `Toolbar`, `ToolTip` or `Awareness` are no longer
  taken for item tables. Presentation tables next to an item word (`ItemIcon`, `ItemTooltipText`, `ItemShopUI`) are dropped,
  render words (`PhysicalMaterial`, `SurfaceMaterial`, `MaterialInstance`) are no item tables, and common abbreviations (`Itm`,
  `Wpn`, `Eqp`, `Armr`, `Cosmetics`) are recognised.

### Fixed
- **English mode:** about 110 messages (ITEMS and VALUES tabs, the trainer README, the GoldHEN/etaHEN export, the image base check
  and more) were only half translated and now have complete English texts. A new test keeps the entries in sync with the code.
- The Unity ITEMS GUI test no longer needs the GNU assembler (it failed on Windows); it is skipped when no disassembler is found.

### Removed
- `lager_slots.py`, a stand-alone script for a single game that the program never used, and its English texts.

## 6.0.1 - 2026-11-05

**Item trainer hotfix.** Trainers keep working after a game restart, the GoldHEN/etaHEN export of the item trainer no longer crashes the game, and renamed trainer files are respected. **Trainers saved with an older version still hold fixed addresses - save them once more (ITEMS: FIND ITEMS, SAVE TRAINER).**

### Fixed
- **Item trainers: the names you give the files are used, and loading/saving refreshes the files instead of trusting the old
  `_trainer_spec.json`.** Renaming a trainer file (e.g. `10_FOD 4.reapproj` -> `Food Item 1.reapproj`) only changed the file
  name; the list kept showing the old name stored inside the file, and "check / adjust" or saving into the same folder wrote
  fresh files under the generated names next to the renamed ones, so stale copies with the old cave and switch addresses stayed
  behind (this also happened to a renamed BASIS file). Now:
  the list shows your file name; entries are matched to their files by content (switch byte), so renaming is safe; a file you
  deleted is no longer an entry; saving rewrites every file of the trainer under the name you chose (BASIS included), removes
  only this trainer's superseded files and never touches your own files; new items of a category go into the entry you renamed
  (`origin` is remembered in the spec) and existing entries keep their name, order and file name. The BASIS preflight also
  recognises a renamed BASIS file.
- **GoldHEN/etaHEN export of the item trainer: BASIS is split into two switches** (`1/2` writes the cave and keeps it when
  switched off, `2/2` sets/removes the vtable hooks). One switch with cave and hooks could point a hook at empty memory
  (crash with a read-permission violation). Names are now `00a BASIS 1 - Cave (ZUERST)` / `00b BASIS 2 - Haken (DANACH)`.
- **GoldHEN/etaHEN export: a second cave could overwrite the end of the item trainer's cave** (same free space handed out twice,
  e.g. `250 Warehouse Slot Unlock` at `0x64A7FC0` inside the BASIS cave). The BASIS cave is now reserved first.
- **Item trainer crashed the game right after activating BASIS.** On a freshly started game the largest free code gap was the
  small extra region `(aux)` (e.g. `0x918c000`, 16 KB), which also holds the cave pool of other tools; the 13 KB cave was put
  there. The cave now goes into the game's own code padding first; extra regions are used only when the game code has less
  than 2 KB free.
- **Smaller caves.** Per item the cave uses shorter encodings with the same effect (`xor ecx,ecx` instead of `mov rcx,0`,
  `mov esi,imm32` for 32-bit values, short `jz`), about 30 % less code, so a big trainer fits in one project.
- **Item trainers (Unreal) keep working after the game is restarted.** Trainers that call a game object which the cave cannot
  reach on its own (e.g. `UDMXInventorySubsystem.AddItemToWarehouse`) used to store the object's memory address. That address
  changes with every game start, so after a restart the cave found something else there and silently did nothing. The cave now
  finds the object itself: a small routine walks the game's object list (`GObjects`), picks the live object with the right
  vtable (class default objects are skipped) and remembers it in an 8-byte cell behind the switch bytes. If the object does not
  exist yet (e.g. main menu) the call is skipped and the game carries on. **Trainers saved with an older version still hold the
  fixed address - save them once more (ITEMS FIND, SAVE TRAINER).**
- CI: the German texts of `lager_slots.py` have English translations again, and a test opened a file without an explicit
  encoding (both made the i18n and encoding-policy tests fail on all three test jobs).

## 6.0.0 - 2026-11-01

**Items for everyone.** The ITEMS tab for Unreal games was rebuilt so that a beginner gets items into the game without knowing
tables, FNames or functions; items can now be given **right away** (no trainer needed), the amount respects the game's
inventory limits, and there is a one-click **INVENTORY TO MAX** for games that offer it. Unity (IL2CPP) games get their own
ITEMS tab. Release notes for GitHub: [`docs/history/RELEASE_NOTES_v6.0.0.md`](docs/history/RELEASE_NOTES_v6.0.0.md).
**Updating from 5.9.1:** the updater of 5.9.1 cannot replace files that are open in the running program (`WinError 32`,
e.g. `_internal\base_library.zip`). It then rolls back and says "Your previous version was not changed" - if you see this, unpack
the 6.0.0 zip over the folder once by hand. From 6.0.0 on the updater copes with such files (see *Fixed*).

### Highlights
- **Unreal ITEMS tab shows only what matters.** Every table of the game is rated; only item lists are offered, the best give
  function is picked on its own, and the game-specific choices are hidden behind "Change the choice myself (advanced users only)".
- **Items arrive on the game thread.** TEST 1 ITEM and GIVE NOW run through a short cave that the game executes itself - the
  same safe way the trainer works. They no longer hang or freeze the game.
- **Limits and bigger inventories.** The amount per item is cut to the game's own limit (`OwnLimitByBackPack`, ...), and
  **INVENTORY TO MAX** runs the game's own expansion function (e.g. `DevExpansionEnableSlotByMaxLevel`) - the button only
  appears for games that have one.
- **UNITY > ITEMS** - the same three steps for Unity (IL2CPP) games.

### Added
- **ITEMS tab (Unreal): only suitable item lists and give functions are shown.** Every table is rated by name and row struct
  (`DT_ItemParam`, `DT_WeaponParam` count as item lists; effect, UI, sound, enemy or text tables do not). Give functions are rated by
  whether the trainer can reach their object, and functions that remove / select / preview items, belong to a display actor or
  give key items are ranked down. "Also show unsuitable ones" shows the rest with the reason. If the best function cannot be
  reached, the status line and the save preview say so.
- **Filter levels** `streng` (strict) / `normal` (default) / `aus` (off) for tables and give functions. `normal` keeps tables like
  `DT_ItemSkill` or `DT_CharacterItem` and functions like `RequestAddItem` / `AddToBag`; `aus` hides nothing. Changing the level
  searches again.
- **All item lists are read and merged** instead of only the first table (up to 12; tables without their own grouping are named
  after the table). *Read all item lists together* can be switched off.
- When nothing is found, the log and the status say where the filter dropped things (tables seen / relevant / with rows,
  functions found / rejected and why).
- **TEST 1 ITEM** gives ONE item through the chosen function, **GIVE NOW** gives all ticked items immediately (no trainer, no
  BASIS). Both run through a short cave on the game thread, ask before they start, remove the hook afterwards and reuse a cave
  that is still there. TEST 1 ITEM asks whether the item arrived; the answer is remembered per game
  (`discover.verified` in the game profile): tested functions are ranked up and marked "tested", failed ones are ranked down and never
  count as suitable - in every filter level. Test results of older program versions are dropped (`verified_v`).
- **TEST CHECKED ITEMS** (German: `ANGEHAKTE TESTEN`) checks everything that is ticked before a trainer is made. Stage 1 is
  read only: image base, give function found, native code executable, `this` object reachable, ProcessEvent hook slots, free cave
  space, and per item a name / FName / ID check against the live name pool. Stage 2 (optional, asks first) puts a short test hook
  into the game, triggers each item once and waits until the cave clears its switch - proof that hook, cave and game function
  really run; the hook is always removed again, even on errors. One question at the end ("did it arrive?") flags the whole set if
  not. Results show in a TEST column; failed items are unchecked automatically (switchable); saving after a failed test asks
  first. Logic in `item_check.py`.
- **Amount limits.** The amount is cut per item to the limit stored in the item table (columns such as `OwnLimitByBackPack` /
  `OwnLimitByWarehouse`; the one that matches the give function - backpack or warehouse - is used). The save dialog explains this.
- **INVENTORY TO MAX** - runs a parameterless inventory-expansion function of the game once (found in the SDK by name, e.g.
  `UDMXInventorySubsystem.DevExpansionEnableSlotByMaxLevel`) through the cave. The button is shown only when the game has such a
  function.
- **One folder per game, saving adds to it.** SAVE TRAINER now adds the ticked items to what is already saved for the game
  (same item = replaced, everything else kept, categories rejoined and re-split), so everything stays in one project with one
  cave and one set of hooks as long as it fits. The checkbox **Neu beginnen** saves only the ticked items; the old state is
  then backed up in a single `<game>/_alt/` folder (no new folder per save).
- **Fixed: entries turning red on ALL ON.** A trainer entry sets a one-shot switch byte that the cave resets right away; the
  read-back check could see the reset byte and report a failed write. A byte already consumed by the game now counts as success.
- **Saved trainer folders carry the game ID** (`PPSA06929 Items 1`, `PPSA06929 Items 2` ...) so projects of different games
  no longer share the same folder name and the wrong game's codes are not loaded any more.
- **No automatic slot unlock when giving items.** GIVE NOW no longer runs the inventory expansion first, SAVE TRAINER no longer
  adds an **Inventar erweitern** entry, and the checkbox *Expand inventory first* is gone. **INVENTORY TO MAX** stays as a manual
  button. Note: a game refuses an item that has no free slot, so with a small warehouse only the first item(s) arrive.
- **Objects the trainer cannot reach through the PlayerController** (e.g. a game-instance subsystem like
  `UDMXInventorySubsystem`) are called through their fixed address (`this` mode `abs`: address plus vtable check, skipped when the
  object is gone). This is valid only until the game is closed: after every game start load a save, FIND ITEMS and SAVE TRAINER
  again. The status line, the pre-check and the save dialog say so.
- **UNITY > ITEMS tab** - the same three steps as the Unreal ITEMS tab, for Unity (IL2CPP) games: pick the game folder, click
  **FIND ITEMS**, click **SAVE TRAINER**. The tool picks the item list (the `ItemID`-style enum from `dump.cs`), the method that
  gives items (`AddItem`, `GiveItem` ... with an item-ID parameter and an optional amount) and an entry point (an `Update` /
  `LateUpdate` / `FixedUpdate` method of the inventory class, of a class with a field that points to the inventory, or any
  `Update` for static methods) on its own and shows what it chose. The trainer is written like the Unreal one: categories in
  packages of 14, several projects when the cave does not fit, preview before writing, `LIESMICH_TRAINER.txt`, **CHECK TRAINER**
  for the version anchors. Finding the items needs no console connection.
- How the Unity trainer works (`unity_items.py`): a `jmp` at the start of the chosen `Update` method; its first instructions are moved
  into the cave (rip-relative addresses and `jcc` / `call` / `jmp` are re-encoded). The cave checks one switch byte per entry,
  clears it atomically and calls the game's give method once per item (System V call, `MethodInfo* = 0`), then runs the moved
  instructions. Raw machine code, no assembler needed to apply it.
- START tab card and English texts for the new tabs.
- Tests: `tests/test_unity_items.py` (finding, relocation, encoding checked against GNU `as`, **the cave is executed on an x86-64
  CPU**), `tests/test_gui_unity_items.py`, `tests/test_item_check.py`, `tests/test_gui_items_check.py`, `tests/test_this_analysis.py`,
  more cases in `tests/test_ue_items.py` (real signatures such as `AddItemToBackPack`, amount limits, inventory expansion),
  `tests/test_gui_items.py` and `tests/test_ue_cavegen.py` (the `abs` mode is executed on a real CPU).

### Changed
- When several give functions rate equally, the backpack function is preferred over the warehouse one (and over functions with a
  slot index). Pick `AddItemToWarehouse` under "Change the choice myself" to fill the warehouse instead.
- Give functions are rated higher when the trainer can reach their object (hooked +3, member +2.5, fixed address +1) and lower
  when it cannot (-5); a name or class that does not fit (remove, preview, display actor) costs points.
- Test suite: 932 tests (CI: Linux Python 3.10 / 3.12, Windows Python 3.12; `ruff check .` clean).

### Fixed
- **"The cave was not executed (the game does not call ProcessEvent right now)" - nothing arrives.** The hook sat only in the
  PlayerController's vtable, and some games hardly call ProcessEvent on it. When no entry needs the PlayerController as `this`
  (fixed-address and `this`-less functions), the hook now also goes into the vtables of Pawn, HUD, PlayerState, GameState and
  GameMode, so the cave runs at the next ProcessEvent of any of them. After the first missed pack the rest is no longer waited for
  one by one, and the message says what to do (walk around, no menu).
- **Items were given but landed in a full backpack / the amount was refused.** The amount is now cut to the game's limit (see
  Added) and the warehouse and the expansion function are available as alternatives.
- **GIVE NOW and TEST 1 ITEM no longer hang after 1-2 items ("Giving aborted: timed out") or freeze the game.** They called the
  give function from a foreign thread; a function that creates items can wait for the game thread there and never return. Both now use
  the cave on the game thread (see Added). Only when that is impossible (nothing has been changed then) the old direct call is tried.
  If the game never runs the cave, the message says so.
- **Items are given even when the give function's class has no object in the game (e.g. `USBCheatManager` in a shipping
  build).** The cave took `this` from `PlayerController.CheatManager`; when that pointer is 0 it skipped the call - everything was
  green, nothing arrived. The native function is now read (read only) and followed for `this`: if it never reads or passes on
  `this`, the trainer calls it with `this = 0` always, the pre-check says so, and TEST 1 ITEM / GIVE NOW use the PlayerController as
  caller. Unclear code keeps the old behaviour. If the ProcessEvent slot already points into game code (a cheat loaded earlier,
  e.g. by GoldHEN/etaHEN), the check says so.
- **Give functions with an unusual signature** (e.g. `AddItemToBackPack(FName ItemId, int32 Add, FName WorkId, bool bCallEvent)`):
  `Add` is recognised as the amount, a slot index (`SlotIndex`) is no longer taken for the item ID, and further FName IDs such as
  `WorkId` stay empty instead of getting the item (TEST 1 ITEM) or aborting with "FName missing" (SAVE TRAINER). Earlier wrong
  test results ("nothing arrived" because the amount was 0) are dropped automatically.
- **Cave outside the game image when the image has no room in reach.** If the padding at the end of the image is more than
  +-2 GB (rel32) away from the give function, ProcessEvent or the switches, the trainer now looks for free padding in other modules
  (`cave_trainer.far_span`) that is in reach of **all** targets, and warns that this only holds while the module is loaded at the
  same place. Before, SAVE TRAINER stopped with "no free code space".
- **Trainer on another console: "does not fit into the largest free code gap of the game (0 bytes)".** The cave of an earlier
  trainer stays at the end of the code region after BASIS is switched off (or when it was loaded through GoldHEN/etaHEN). The
  free-space scan saw that end as occupied and reported 0 bytes. Leftover ReaperPy caves (also several stacked ones) are now
  recognised by their code signature and the space is reused; the base patch gets a `VerifyAlso` list so it activates on that
  console and on a clean one; old switch bytes are left alone. If there is really no space the message says so and the log lists
  why. The scan also looks through the last 64 KB of each executable region for zero / `0xCC` runs, so a foreign cave at the end of
  the padding no longer hides the free part in front of it. With 0 bytes the log shows a map of the region end (`.` = 00, `c` = CC,
  `#` = data). Test: `tests/test_cave_trainer.py` (`LeftoverCaveTests`).
- **CHECK / ADAPT TRAINER shows examples of changed item numbers** (up to 5 `saved -> now`, up to 3 missing entries, the number of
  matching items) and lists every change in the log (`[fname]`).
- The leftover-cave fix also covers the Unity cave: it is recognised by its code signature, the space is reused, the base patch
  gets `VerifyAlso`, a free space of `0 bytes` is explained.

- **Self-update: "installation failed and was rolled back: [WinError 32] ... base_library.zip".** A file that the running
  program has open cannot be renamed on Windows (and OneDrive or a virus scanner can hold files for a moment). The updater now
  retries such a file a few times, then stores the new version next to it (`<name>.update_new`) and finishes the job when ReaperPy
  has closed: **Restart now** starts a small helper that waits until the program has ended, moves the waiting files into place and starts
  ReaperPy again; if you close the program yourself, the next start does the same (at most 3 attempts, then the waiting files are
  dropped and the old ones stay). Folder names with `&`, `%` or spaces are safe (paths go through environment variables, never
  into the script). Everything else is still installed with backup and rollback. Tests: `tests/test_updater.py` (`LockedFiles`).

### Known limits
- **Unity ITEMS is not tested on a real game or console yet.** It needs an item-ID parameter that is a number or enum; methods that
  take an item object / string are listed with the reason and skipped (use VALUES / EXPERT then). With a `this` taken from a field of
  the hooked class (e.g. `Player.inventory`) the items go to the first such object that runs after the click.
- Unreal ITEMS was tried on two real games, but not on every engine layout. Whether an item shows up in the inventory is judged by
  you (TEST 1 ITEM asks); a function that "runs" without effect is flagged only by your answer.
- Fixed-address trainers (`abs`) are valid for one game session only. The inventory limits come from the item table; a game that
  enforces a limit somewhere else can still cap the amount.

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
