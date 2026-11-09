# The main window and the Tools window

Every tab explained: cheat searcher, patches, debugger, memory, cheat menu.

[← Back to the README](../../README.md)

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
- **Auto-update** - checks GitHub Releases on start; a newer release is offered with its notes, downloaded, unpacked into the program folder and you are asked to restart (files that are still in use are put in place by a small helper while ReaperPy restarts). Your config, profiles and logs are kept. Off: `"auto_update_check": false`; other repo: `"update_repo": "owner/name"`. A git checkout is never overwritten (use `git pull`).

## The Tools window - every tab explained

### Simple tabs

The Unreal and Unity tools are grouped: the tab **★ UNREAL** holds ITEMS, VALUES, LIVE, CHEAT MENU, DISCOVERER and EXPERT (the
static UE-AUTO tools), the tab **★ UNITY** holds ITEMS, QUICK (values) and MANUAL. Below they are listed by their short names.

| Tab | What it does |
|---|---|
| **START** | Three big steps for beginners with plain-language status: connected? codes found? Leads to the simple tools. |
| **FIND VALUE** | The cheat searcher. Layout: found addresses on the left, scan controls on the right, your **address list** at the bottom. See [below](#find-value-the-cheat-searcher). |
| **EDIT CHEATS** | Write a patch: name, author, offset from the image base. *Simple patch / NOP* (original bytes -> new bytes) or *Code cave* (assembly in a separate box, `jmp OriginReturn` goes back). Assembler or hex bytes are accepted; saved as `.reapproj`. |
| **VALUES** | Health, stamina, gold, experience, ammo ... as ready-made patches, for **Unreal Engine and Unity**, in three steps (game folder -> FIND THE IMPORTANT STUFF -> SAVE PATCHES). See [Unreal Engine games](UNREAL.md). |
| **ITEMS** (Unreal) | The easy way for Unreal Engine games: **all items as a ready-made trainer in three steps** (game folder -> FIND ITEMS -> SAVE TRAINER), plus **TEST 1 ITEM**, **GIVE NOW**, **TEST CHECKED ITEMS** and **INVENTORY TO MAX**. See [Unreal Engine games](UNREAL.md). |
| **UE-LIVE** | Live values of an Unreal Engine game: pick a member, see all live instances, change / freeze them. |
| **UE DISCOVERER** | Analyses the SDK and tells you what is there to find: item structs, item tables, give-functions, stat enums, cheat managers - with a check whether a cave trainer can be built for each ("✔" / "✗ not possible: reason"). |
| **UNITY** | The same idea for Unity (IL2CPP) games: **ITEMS** (all items as a trainer in three steps), then, from the Il2CppDumper folder, live values, method patches (always true, fixed return value, skip) and enum names (item IDs). See [Unity games](UNITY.md). |
| **CHEAT MENU** | Switches and values for the player character, generated from the SDK. Works in shipping builds without a CheatManager. |

### How-to guides for beginners

The **HOW TO** button (German: **ANLEITUNGEN**) in the top bar of the main window opens a window that explains every tool step by step, in plain words. The language
follows the **DE / EN** switch: switch it and the open guide is shown in the other language at once. The **? HELP** button in the
header of the Tools window opens the guide that belongs to the tab you are looking at; the search box finds words in all guides.

| Guide | Covers |
|---|---|
| First steps | Connecting, the START tab, which tool for which job, staying safe |
| Find a value | FIND VALUE: scans, unknown values, memory sections, what to do next |
| Edit cheats | EDIT CHEATS: NOP or code cave, from a found value to a cheat |
| Assembler for beginners | Registers, the common instructions, reading a "who writes" line, a first cave line by line |
| Items in Unreal / Unity games | The three-step item trainers, test and give buttons, what to do when only one item arrives |
| Values, live values and the cheat menu | VALUES, LIVE, CHEAT MENU, DISCOVERER, EXPERT, Unity QUICK / MANUAL |
| Export | `.json` / `.shn` / `.mc4`, where the files go on the console, switch order of item trainers |
| Pointers and game updates | POINTER and AOB / UPDATE |
| The debugger | Breakpoints, watchpoints, stepping, KERNEL LOG, FUNCTION LOGGER |
| Advanced tools | MEMORY, CONVERTER, CALL FUNCTION, PYTHON SCRIPT, JOURNAL / UNDO, sessions |
| Troubleshooting, Glossary | Common problems and plain-language explanations of the terms |

The guides are plain Markdown files in [`docs/howto/en`](../howto/en) and [`docs/howto/de`](../howto/de) (file name
`NN-name.md`, `NN` = order), so you can also read them here on GitHub. The program shows the same files. To add a guide, put a file
with the same name into both folders; tests check that both languages have the same structure, that every link and every button
name used in a guide really exists in the program, and that every tab has a guide to open.

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
| **PYTHON SCRIPT** | A script editor with the `ps5` object; run, stop, undo. See [Scripting](SCRIPTING.md). |
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
