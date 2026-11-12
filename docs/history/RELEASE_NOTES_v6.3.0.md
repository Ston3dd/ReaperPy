# ReaperPy 6.3.0

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


## Update

- Use the in-program update, or download `ReaperPy_v6.3.0_win64.zip` from this page and check it against the `.sha256` file.
