# ReaperPy

**A toolkit for the PS5 on top of the [ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG) payload: patches and code caves, memory scanner,
pointer scan, debugger, disassembler, Unreal Engine live tools and a cheat menu - with export to GoldHEN/etaHEN cheat
formats (`.json`, `.shn`, `.mc4`).**

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

> **Use it only on your own console, with your own games, in single-player/offline modes.**
> Writing to a running game can crash it or corrupt your save game - back up first. No warranty (see [LICENSE](LICENSE)).
> ReaperPy contains no game data, no keys for protected content and no way around online protections.

---

## Contents

- [Features at a glance](#features-at-a-glance)
- [Screenshots](#screenshots)
- [Install and start](#install-and-start)
- [Quick start](#quick-start)
- [The main window](#the-main-window)
- [The Tools window - every tab explained](#the-tools-window---every-tab-explained)
- [Unreal Engine games](#unreal-engine-games)
- [Export formats](#export-formats)
- [Scripting](#scripting)
- [Configuration](#configuration)
- [Development and tests](#development-and-tests)
- [Project layout](#project-layout)
- [Credits and licenses](#credits-and-licenses)

---

## Features at a glance

| Area | What you get |
|---|---|
| **Patches and caves** | Edit patches as `.reapproj` projects: simple byte patch / NOP, or a code cave written in x86-64 Intel assembly (Keystone). Caves are placed in free padding of the game image. |
| **Cheat searcher** | CheatEngine-style scanner running on the console: first / next scan, exact, approximate (float), greater / less / between, increased / decreased by, changed / unchanged, unknown initial value. Address list with freeze, set value, "who writes this?". |
| **Pointer scan** | Build pointer paths to a value (with a map, or the fast on-console scan level by level). |
| **Debugger** | Attach, software breakpoints, hardware watchpoints, registers, stack, threads, step into / over / out, run to. |
| **Disassembler / memory** | Hex view with value inspector, snapshots and compare, save a region to file; x86-64 disassembly; AOB signatures. |
| **Unreal Engine tools** | Live object browser, value editing and freezing, an *Entdecker* ("Discoverer") that finds item tables and give-functions, and a **cheat menu** generated from the game's SDK. |
| **Calling and logging** | Call any game function with arguments; log every call of a function through a code cave. |
| **Safety net** | Journal / undo for every write the tools make. |
| **Console notifications** | On-screen messages on the PS5 when ReaperPy connects, when a cheat is switched on/off (also while the debugger is attached) and when the debugger attaches / detaches. |
| **Export / import** | `.json`, `.shn` and `.mc4` cheat files for GoldHEN/etaHEN; import them back into patches. |
| **Python scripting** | A `ps5` object for scripts: pointers, AOB scans, writes with undo, function calls. |
| **Per-game profiles** | Notes, favourites, groups and hotkeys per game; automatic code detection by title ID. |
| **Languages** | German and English (switch at runtime, including all tool tabs). |

## Screenshots

Screenshots go into [`docs/screenshots/`](docs/screenshots/README.md) (the list of shots to take is there). Once the files exist,
uncomment the block below.

<!--
| Main window | Cheat searcher |
|---|---|
| ![Main window](docs/screenshots/01-main-window.png) | ![Find value](docs/screenshots/02-find-value.png) |

| Edit cheats (code cave) | Debugger |
|---|---|
| ![Edit cheats](docs/screenshots/03-edit-cheats.png) | ![Debugger](docs/screenshots/04-debugger.png) |

| UE-LIVE | UE Discoverer | Cheat menu |
|---|---|---|
| ![UE-LIVE](docs/screenshots/05-ue-live.png) | ![UE Discoverer](docs/screenshots/06-ue-discoverer.png) | ![Cheat menu](docs/screenshots/07-cheat-menu.png) |
-->

---

## Install and start

**Requirements**

- A jailbroken PS5 running the **[ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)** payload by OSR / Pharaoh2k (command port `744`, kernel log `3232`, debugger back channel `755`).
- Python **3.10+** with `tkinter` (included in the Windows installer; on Linux install `python3-tk`).
- A PC in the same network. Allow the app through the firewall for **port 755** (the console connects *back* to your PC to
  report breakpoint hits).

```bash
pip install -r requirements.txt     # keystone-engine, capstone, pillow
python gui.py                       # Windows: double-click start.bat (checks Python, tkinter and packages first)
```

A Windows folder build (no Python needed) is created with `build_exe.bat` (PyInstaller, no `--onefile`: configuration,
profiles and logs stay next to the EXE).

## Quick start

**1. Connect.** Start the game on the console, load the payload, enter the console IP in the main window and press
**CONNECT**. The app detects the foreground game (title ID) and loads the matching codes from your library.

**2. Find a value and make a cheat.** Open **TOOLS -> FIND VALUE**: type the number you see in the game (health, ammo,
money), press **FIRST SCAN**, change the number in the game, type the new one, press **NEXT SCAN**. Repeat until a few
addresses are left. Add them to the address list, set or freeze the value. *Who writes this?* shows the instruction
that changes it - **EDIT CHEATS** turns it into a NOP patch or a code cave.

**3. Unreal Engine game - all items as a trainer.** Open **ITEMS**, choose the game folder (step 1), click **FIND ITEMS**
(step 2), then **SAVE TRAINER** (step 3). No tables, FNames or IDs to know - see [below](#unreal-engine-games).

**3b. Unreal Engine game - single values.** Open **UE-LIVE**, choose the game's SDK folder (output of
[ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper)), click a value such as
`UHealthComponent.Health`, see the live value on the right and change or freeze it. Or let **UE DISCOVERER** analyse the
game and **CHEAT MENU** build switches for health, stamina, fly, speed ...

**4. Debug.** **TOOLS -> ADVANCED -> DEBUGGER**: PID, **ATTACH**, set a breakpoint on an address, let the game run, inspect
the registers when it stops, **STEP** / **STEP OVER** / **STEP OUT**, **CONTINUE**.

---

## The main window

- **Patch cards** - every patch of the open project is a card: switch on/off, favourite star, group, hotkey, author, info,
  copy name, show the patch file in its folder (right-click menu).
- **FOLDER / LIBRARY** - open a project folder or pick a game from your patch library. Codes are found automatically by
  title ID when you connect.
- **GOLDHEN-JSON** - export your patches as cheat files (`.json` / `.shn` / `.mc4`), or import such files.
- **CONNECT** - connects to the payload, with a watchdog that reconnects when the console drops (optional). A notification on the PS5 confirms the connection.
- **DE / EN** - language switch (also switches all tool tabs).
- **Notes per game** - free text that is shown again when you open the same game.
- **Update check** - optional; set `update_url` in the configuration to a small JSON file (`{"version": "...", "url": "..."}`).

## The Tools window - every tab explained

### Simple tabs

| Tab | What it does |
|---|---|
| **START** | Three big steps for beginners with plain-language status: connected? codes found? Leads to the simple tools. |
| **FIND VALUE** | The cheat searcher. Layout: found addresses on the left, scan controls on the right, your **address list** at the bottom. See [below](#find-value-the-cheat-searcher). |
| **EDIT CHEATS** | Write a patch: name, author, offset from the image base. *Simple patch / NOP* (original bytes -> new bytes) or *Code cave* (assembly in a separate box, `jmp OriginReturn` goes back). Assembler or hex bytes are accepted; saved as `.reapproj`. |
| **ITEMS** | The easy way for Unreal Engine games: **all items as a ready-made trainer in three steps** (game folder -> FIND ITEMS -> SAVE TRAINER). See [below](#unreal-engine-games). |
| **UE-LIVE** | Live values of an Unreal Engine game: pick a member, see all live instances, change / freeze them. |
| **UE DISCOVERER** | Analyses the SDK and tells you what is there to find: item structs, item tables, give-functions, stat enums, cheat managers - with a check whether a cave trainer can be built for each ("✔" / "✗ not possible: reason"). |
| **UNITY** | The same idea for Unity (IL2CPP) games: load the Il2CppDumper folder, then change / freeze live values, patch methods (always true, fixed return value, skip) and look up enum names (item IDs). See [below](#unity-il2cpp-games). |
| **CHEAT MENU** | Switches and values for the player character, generated from the SDK. Works in shipping builds without a CheatManager. |

### FIND VALUE (the cheat searcher)

Layout: **hits** (left) | **scan** (middle) | **memory sections** (right), the **address list** below. Everything is also
available through right-click menus; rarely used settings are in the **OPTIONS** dialog.

- **Value / Value type / Compare / To** - the number to look for (*To* = upper bound for "between"). Compare: *Exact*,
  *Approx. (float)*, *Greater than*, *Less than*, *Between*, *Increased / Decreased*, *Increased by / Decreased by*,
  *Changed / Unchanged*, *Unknown initial value*. Types: signed/unsigned 8 / 16 / 32 / 64-bit integers, float, double.
- **Range** - *Data (rw, no code)*, everything writable, everything readable.
- **MEMORY SECTIONS** (new) - shows what is in the game's memory and what gets scanned:
  - **eboot.bin is split up** into its code, read-only and data sections (one row each, with address, size and rights);
    game modules (`.prx`, not system), **system libraries** (one row per library), heap / anonymous memory, shared
    memory and stacks follow. Heap regions of 1 MB or more get their own row, smaller ones are summarised in one row.
  - Every row has a **checkbox** (click the box, double-click the row, or press Space). Category rows switch a whole group.
  - **HIDE** - presets (*all system libraries*, *libSce\**, *libc / libkernel / libm*, *shared memory*, *stacks*) plus
    **own patterns** (`libSce*, SDL, Shm` - with `*` a wildcard, without it a part of the name). Default: system libraries
    hidden. Right-click a module -> *Hide module* adds it to the patterns.
  - **ALL / NONE / EBOOT ONLY / GAME ONLY** buttons; right-click: switch selection on/off, scan only this selection, copy
    start address, show in memory.
  - The summary shows *selected / total* regions and size (and the saved percentage). After one scan it also estimates the
    read time from the speed of that scan. Fewer MB to read = faster scan, especially for **Unknown initial value**.
  - The filter is applied on a **fresh memory map at scan start** (the heap grows), and it is remembered between sessions
    (`scan_filter.json` in the data folder). Hiding libraries is normally safe for game values; if a value is not found,
    switch the filter to *ALL* and scan again.
- **OPTIONS ...** - speed filter (skip slow regions), simplify float, parallel, aliasing (experimental), skip small
  segments, **snapshot RAM** (how much of the unknown-value snapshot stays in console RAM; more = much faster but uses
  console memory) and where the rest is spilled (internal `/data`, M.2 expansion, USB), plus SELF-TEST and REGION REPORT.
- **Snapshot RAM limit:** the PS5 supports **up to 2048 MB**. From **3072 MB** upwards the payload reports that the PS5
  does not have enough memory. The drop-down therefore offers 512 / 1024 / 2048 MB (default 2048 MB); the rest of the snapshot is spilled to the chosen storage.
- **FIRST SCAN / NEXT SCAN / CANCEL / NEW SCAN** - self-test (in OPTIONS) checks protocol and payload capabilities.
- **Hits** - paged list with address, current, previous and first value. Double-click or **ADD SELECTED / ADD ALL
  (PAGE)** moves them to the address list; right-click also offers *show in memory* and *copy address*.
- **Address list** - **SET VALUE**, **FREEZE**, description, remove, **WHO WRITES?** (hardware watchpoint through
  the debugger), **-> HEX**, **-> POINTER SCAN**, copy address. Freezing uses one bulk write per tick.

### Advanced tabs

| Tab | What it does |
|---|---|
| **MEMORY** | Hex view of any address with a value **inspector** (click a byte), **snapshot / compare**, save a region to a file / load a file into memory, copy hexdump. |
| **DISASSEMBLER** | x86-64 disassembly (Capstone) of live memory from any address or `base`; page forward, follow jumps and calls, double-click to follow. |
| **POINTER** | Pointer scan with a map, or the **fast scan** that runs level by level on the console (needs a payload with `PTRSCAN`). |
| **CONVERTER** | Assembler <-> hex bytes (x86-64, Intel syntax), also from disassembled lines (`-> ASSEMBLER`). |
| **AOB / UPDATE** | Byte patterns with wildcards (`48 8B 05 ?? ?? ?? ??`), scans, signatures per patch. After a game update the **update scan** re-finds each patch and recomputes its offset. |
| **DEBUGGER** | See [Debugger](#debugger). |
| **KERNEL LOG** | The console's kernel log with crashes, page faults and errors highlighted - handy when a patch or cave closes the game. Reconnects by itself. |
| **PYTHON SCRIPT** | A script editor with the `ps5` object; run, stop, undo. See [Scripting](#scripting). |
| **CALL FUNCTION** | Call a game function with up to 6 arguments: `base+0x1234`, numbers, text (`"abc"`), buffers in the game (`@buf+8`). Shows RAX as hex / signed / float / string. Never repeats automatically. |
| **FUNCTION LOGGER** | Replaces the first bytes of a function with a jump into a cave that writes every call (registers, return address, stack arguments, xmm0/1, optional thread) into a ring buffer. Group by caller, export CSV; the game is not paused. **STOP** restores the original bytes. |
| **JOURNAL / UNDO** | Every write the tools make is recorded with the old bytes - undo single entries or everything. |
| **UE-AUTO** | The static side of the UE tools: candidates from SDK headers, instruction search in the dump, NOP / cave patches with AOB signatures, native functions, call a UFunction through ProcessEvent. Also a command-line tool (`python ue_auto.py --help`). |

### Debugger

- **ATTACH / DETACH** - attaches on its own connection (or borrows the main one). The back channel on port 755 is bound
  *before* attaching; an "already being debugged" state is cleared and retried automatically.
- **Breakpoints** (up to 30) and **watchpoints** (4 hardware slots: write, read/write or execute; execute watchpoints are always 1 byte). Hit counters per address; disable/remove while stopped is applied when you continue.
- **Stop view** - threads, registers (editable), stack with a frame-pointer chain or **stack scan** without frame pointers.
- **CONTINUE** is a plain `continue` (the payload steps over the breakpoint itself). **STEP** goes one instruction (or reports the
  state when the console already ran it), **STEP OVER** runs a `call` as a whole, **STEP OUT** runs to the return address,
  *run to* uses temporary breakpoints in reserved slots.
- **HALT** pauses the game. The keep-alive never rebuilds the connection while a thread is stopped (that would destroy the stop).

### CHEAT MENU

A table of switches and values for the character you currently control. Click **BUILD MENU** after loading the game in
UE-LIVE; every entry shows whether it is reachable on your character (✔) or why not (✗).

Because shipping builds strip the CheatManager, nothing here calls cheat functions. Every entry writes plain memory values
and holds them (like freezing):

1. **Engine values every UE game has** - *Invulnerable* (`bCanBeDamaged` off), *Fly* (`MovementMode = Flying` + `bCheatFlying`),
   walk / fly speed, jump height, gravity, time dilation for the character or the whole game.
2. **Game-specific values from the SDK** - health, stamina, mana, shield, ammo, money and cheat switches found by the
   candidate heuristic. Only objects that belong to your character are touched (enemies with the same class are not);
   *auto* sets the matching "Max…" value.

**ON / OFF** (or double-click) switches an entry and restores the original value when you switch it off. If the character
changes (death, loading screen), all entries are released instead of writing into freed memory. Fly and invulnerability
depend on how the game implements movement and damage - if a game ignores them, use the *health* entries.

---

## Unreal Engine games

ReaperPy reads the output of [ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper): `offsets.json`,
`SDK/SDK_HEADERS`, optionally `dump.bin`, `dump.json`, `GObjects.txt`. UE 4.23+ and UE 5 (FNamePool) are supported.

**Items as a trainer (the easy way) - tab ITEMS**

1. **Game** - choose the game folder (remembered) and connect in the main window; start the game and load a save.
2. **FIND ITEMS** - ReaperPy picks the item table and a give-function it can build a trainer for, reads all items live and
   sorts them into categories (from a category/type column or the item names, e.g. `Item_Fish_Trout` -> *Fish*). Tick or
   untick items (click the box, double-click, Space, right-click menu), search by name, filter by category, **ALL ON / ALL
   OFF** act on the visible rows. If the automatic choice looks wrong, change *Item table* / *Give function* above the list.
3. **SAVE TRAINER** - enter the amount per item and save. Items become entries of 14 per category (*Fish 1*, *Fish 2* ...,
   no "Item" in the names). Very large lists are spread over several projects (`Items 1`, `Items 2` ...; at most 400 items
   and 64 entries per project) - activate only **one** at a time. The folder is a normal ReaperPy project: choose it,
   activate `00 BASIS` once, then click entries. Saving only reads the game; nothing is changed until you activate BASIS.

Not every game works: if the SDK has no give-function the trainer can build (the tab tells you why), use **UE DISCOVERER ->
SEARCH INVENTORY ENTRIES** to set quantities directly in memory.

**Manual way (special cases)**

1. In **UE-LIVE** choose the game folder and connect. The object index is built once per game start.
2. **UE DISCOVERER** -> **ANALYZE** for a plain-language summary and next step; **READ TABLE LIVE** lists item rows by name
   (search box above the list - you never need to know numeric IDs; an ID column is picked up automatically).
3. **CHEAT MENU** for switches; **UE-LIVE** for any value; **UE-AUTO** for static patches.

Instance addresses change with every game start; classes, offsets and the SDK stay valid. Functions that create objects
(spawning actors, widgets) can crash the game when called from a helper thread - prefer functions that read and write values.

## Unity (IL2CPP) games

ReaperPy reads the output of [Il2CppDumper](https://github.com/TetzkatLipHoka/Il2CppDumper) (the TetzkatLipHoka fork, which also
works on console memory dumps). The tab is called **UNITY**.

Your folder should contain `dump.cs` and `script.json` (the `DummyDll` folder is optional - it holds the same information as
.NET stubs for dnSpy/ILSpy; the offsets and addresses ReaperPy needs are in `dump.cs`). Nested folders, e.g. unzipped
archives, are fine - the files are searched for.

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

## Export formats

| Format | Notes |
|---|---|
| `.json` | GoldHEN cheat format (name, hook offset, cave bytes, on/off). |
| `.shn` | SHN XML (Trainer / Cheat / Cheatline). On/off only - buttons are exported as switches. |
| `.mc4` | SHN + AES-256-CBC + base64, file name `TITLEID_VERSION.ext`. `& < > "` in names are replaced because some readers resolve XML entities blindly. |

**TITLE ID / VERSION FROM GAME** reads both values from the running game. Import (`.json`, `.shn`, `.mc4` -> patches) skips mods in
sections other than 0 instead of importing them half.

## Notifications on the console

ReaperPy uses the payload's notification command to show short messages on the PS5 screen, so you see what happened
without alt-tabbing out of the game:

| Event | Message (example) |
|---|---|
| Connected / reconnected | `ReaperPy connected (PID 1234)` |
| Cheat switched on / off | `ON: Infinite HP` / `OFF: Infinite HP` |
| Cheat switched while the debugger is attached | `ON: Infinite HP (debugger attached)` |
| ALL ON / ALL OFF / restore after a reconnect | one summary: `ON: 12 cheats (A, B, C +9)` instead of 12 messages |
| Debugger attached / detached / connection lost | `Debugger attached (PID 1234)`, `Debugger detached`, `Debugger: connection lost` |
| Breakpoint / watchpoint hit (off by default) | `Debugger: breakpoint at 0x401000` (at most one message every 5 s) |

Messages follow the language switch (DE / EN). They are sent in the background and never block the app; if sending
fails, they pause until the next connect. Switch them off completely with
`"ps5_notifications": false`, switch on hit messages with `"ps5_notify_hits": true` (see [Configuration](#configuration)).

## Scripting

```python
base = ps5.module()                                  # base of eboot.bin
hp   = ps5.pointer(base + 0x4A1C00, 0x20, 0x1C4)     # resolve a pointer path
if hp:
    ps5.write_u32(hp, 999, undo=True)                # undo_all() restores it
site = ps5.aob("48 8B 05 ?? ?? ?? ?? 8B 40 1C")
if site:
    ps5.nop(site, 6)                                 # NOP with undo
```

Also available: `ps5.call()`, `ps5.foreground()`, `ps5.write_many()`, `ps5.log_calls()`, `ps5.alloc()`.

## Configuration

Settings are stored in `reaperpy_config.json` next to the program (see `reaperpy_config.example.json`). Set
`REAPERPY_HOME=<folder>` to keep configuration, profiles and logs elsewhere (e.g. on a USB stick). Logs (`logs/reaperpy.log`,
rotating) include uncaught errors from the GUI. `"auto_codes": false` disables automatic code detection, `"ps5_notifications": false` all console notifications, `"ps5_notify_hits": true` also a message for every breakpoint hit, `"splash": false`
or `REAPERPY_NO_SPLASH=1` the start screen.

## Development and tests

```bash
python -m unittest discover -s tests -t .
```

The tests run without a console and without a display: a fake payload server, simulated process memory, a synthetic Unreal
world and a Tk stand-in for the GUI. Tests that need Keystone or a native toolchain are skipped when it is missing.

**What is not covered:** the real console with a real payload, the real look of the Tk windows, and real games. Behaviour on
hardware depends on your console, payload and game - try new features with a single-player game and a backup first.
Please include the log (`logs/reaperpy.log`) in bug reports.

Code style: `ruff` (configured in `pyproject.toml`, line length 120).

## Project layout

| Path | Contents |
|---|---|
| `gui.py`, `branding.py`, `i18n.py` | Main window, splash screen, main-window texts (DE/EN) |
| `tools_*.py` | Tools window and its tabs; `tools_i18n*.py` translates them at runtime |
| `ps5_client.py`, `ps5_ext.py`, `ps5_more.py`, `ps5_backend.py` | Payload protocol client |
| `ps5_notify.py` | Notifications on the PS5 screen (connect, cheats, debugger) |
| `scanner.py`, `pointerscan.py`, `ptrscan_server.py` | Scanner and pointer scan |
| `debugger.py`, `unwind.py` | Debug session, stack unwinder |
| `patch_engine.py`, `reapatch.py`, `cave_trainer.py`, `export_goldhen.py`, `cheatfmt.py` | Patches, caves, trainers and export |
| `ue_*.py`, `uesdk.py`, `uecheat.py`, `cheatmenu.py` | Unreal Engine support and the cheat menu logic |
| `il2cpp_dump.py`, `tools_unity_gui.py` | Unity (IL2CPP) support: Il2CppDumper output, live instances, method patches |
| `docs/` | `de/` German notes, `history/` old release notes, `screenshots/` |
| `tests/` | Unit tests |

## Credits and licenses

ReaperPy is released under the **[MIT License](LICENSE)**.

**Thanks to**

- **[ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)** - the payload ReaperPy is built for. Author **OSR (OpenSourcereR)**,
  maintained and extended by **Pharaoh2k** (with EchoStretch and Sonic-Iso), licensed under GPL-3.0. ReaperPy is only a client
  of its published wire protocol (`PROTOCOL.md`, v1.3.2) and contains none of its code; the payload is a separate program
  with its own license. ps5debug-NG in turn is inspired by `ps5debug` (Ctn, SiSTRo) and `ps4debug` (jogolden) and uses
  the [ps5-payload-sdk](https://github.com/ps5-payload-dev/sdk) by John Törnblom.
- **[ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper)** by TetzkatLipHoka (MIT) - ReaperPy's Unreal
  Engine tools read the output of this dumper; calling a UFunction follows the method of its `uecall`. No code was copied.
- **[Il2CppDumper](https://github.com/TetzkatLipHoka/Il2CppDumper)** by TetzkatLipHoka (MIT, fork of Perfare's Il2CppDumper) - the
  UNITY tab reads its `dump.cs` and `script.json`. No code was copied.
- **[PS5Debug-studio](https://github.com/alfizari/PS5Debug-studio)** by alfizari (Apache-2.0) - ReaperPy has its own
  architecture and code; only a few tweaks (small ideas and format details such as the `.shn` / `.mc4` layout) were taken over.

See [NOTICE](NOTICE) for the details of what was taken from where, and for the licenses of the packages ReaperPy uses
(Capstone BSD-3-Clause, Keystone GPL-2.0, Pillow HPND). Binary builds bundle these packages - read the note in `NOTICE`
before you distribute one.

German documentation of earlier versions is kept in [`docs/de/`](docs/de/) and [`docs/history/`](docs/history/).
