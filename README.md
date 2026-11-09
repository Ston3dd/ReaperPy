<div align="center">

<img src="assets/reaperpy.png" alt="ReaperPy" width="120">

# ReaperPy

**Cheats, trainers and debugging for the PS5 – in one friendly desktop app.**

Patches and code caves · memory scanner · pointer scan · debugger · Unreal & Unity item trainers · GoldHEN / etaHEN export

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

**English** · [Deutsch](docs/de/README_DE.md)

</div>

ReaperPy is a toolkit on top of the [ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG) payload. Find a value, turn it into a
patch or a code cave, give yourself items in three clicks, and export everything as cheat files for GoldHEN / etaHEN.

> **Use it only on your own console, with your own games, in single-player / offline modes.**
> Writing to a running game can crash it or corrupt your save game – back up first. No warranty (see [LICENSE](LICENSE)).
> ReaperPy contains no game data, no keys for protected content and no way around online protections.

<!--
Screenshots: see docs/screenshots/README.md. Once the files exist, remove the comment markers around this block.

| Main window | Cheat searcher |
|---|---|
| ![Main window](docs/screenshots/01-main-window.png) | ![Find value](docs/screenshots/02-find-value.png) |

| Edit cheats (code cave) | Debugger |
|---|---|
| ![Edit cheats](docs/screenshots/03-edit-cheats.png) | ![Debugger](docs/screenshots/04-debugger.png) |
-->

## Contents

[Highlights](#highlights) · [Install](#install) · [Quick start](#quick-start) · [Documentation](#documentation) · [Configuration](#configuration) · [Credits](#credits-and-licenses)

## Highlights

| | |
|---|---|
| 🎯 **Cheat searcher** | CheatEngine-style scans on the console (exact, float, between, changed, unknown initial value), address list with freeze and *who writes this?* |
| 🧩 **Patches & code caves** | Byte patch / NOP or x86-64 assembly (Keystone) in free padding of the game image, saved as `.reapproj` projects |
| 🎒 **Items as a trainer** | Unreal **and** Unity games: find all items, test the give function, **give now** or save a ready-made trainer – three clicks |
| 🐞 **Debugger** | Breakpoints, hardware watchpoints, registers, stack, threads, step into / over / out |
| 🔎 **Memory & disassembly** | Hex view with value inspector, snapshots, x86-64 disassembler, AOB signatures that survive game updates |
| 🧭 **Pointer scan** | Pointer paths to a value, also as a fast level-by-level scan on the console |
| 📤 **Export / import** | `.json`, `.shn` and `.mc4` for GoldHEN / etaHEN |
| 🛟 **Safety net** | Journal / undo for every write the tools make |
| 🐍 **Scripting** | A `ps5` object for Python scripts: pointers, AOB scans, writes with undo, function calls |
| 🎓 **Beginner-friendly** | START tab, plain-words assembler explanations, step-by-step **HOW TO** guides inside the program, German and English |

More: Unreal object browser and cheat menu, Unity method patches, player-or-enemy detection, per-game profiles with notes and
hotkeys, notifications on the PS5 screen.

## Install

**You need**

- A jailbroken PS5 running the **[ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)** payload (command port `744`, kernel log `3232`, debugger back channel `755`).
- A PC in the same network. Allow the app through the firewall for **port 755** (the console connects *back* to report breakpoint hits).
- Python **3.10+** with `tkinter` – or the ready-made Windows build below.

**From source**

```bash
pip install -r requirements.txt     # keystone-engine, capstone, pillow
python gui.py                       # Windows: double-click start.bat (checks Python, tkinter and packages first)
```

On Linux install `python3-tk` first.

**Ready-made Windows build** – download `ReaperPy_v<version>_win64.zip` from the GitHub **Releases** page, check it against the
`.sha256` file next to it, unpack it and start `ReaperPy.exe`. Releases from 5.9.1 on update themselves. Details and the
update-from-5.9.1 note: [docs/en/DEVELOPMENT.md](docs/en/DEVELOPMENT.md).

## Quick start

1. **Connect.** Start the game, load the payload, enter the console IP in the main window and press **CONNECT**. ReaperPy
   detects the game (title ID) and loads matching codes from your library.
2. **Find a value.** **TOOLS → FIND VALUE**: type the number you see in the game, **FIRST SCAN**, change it in the game, type
   the new number, **NEXT SCAN** – repeat until a few addresses are left. Freeze or set them, or use *Who writes this?* and
   turn the result into a patch in **EDIT CHEATS**.
3. **Items as a trainer.** Unreal: **UNREAL → ITEMS**. Unity: **UNITY → ITEMS**. Choose the game folder, **FIND ITEMS**, then
   **SAVE TRAINER** – or tick items and press **GIVE NOW**.
4. **Debug.** **TOOLS → ADVANCED → DEBUGGER**: PID, **ATTACH**, set a breakpoint, let the game run, inspect, **STEP**.

New to this? Press **HOW TO** in the main window (or **? HELP** in the Tools window) for guides in plain words.

## Documentation

| Topic | Where |
|---|---|
| Every tab explained, the cheat searcher, debugger, cheat menu | [docs/en/TOOLS.md](docs/en/TOOLS.md) |
| Unreal Engine games: items, values, trainer check, cave space | [docs/en/UNREAL.md](docs/en/UNREAL.md) |
| Unity (IL2CPP) games | [docs/en/UNITY.md](docs/en/UNITY.md) |
| Export formats and console notifications | [docs/en/EXPORT.md](docs/en/EXPORT.md) |
| Python scripting | [docs/en/SCRIPTING.md](docs/en/SCRIPTING.md) |
| Tests, CI, releases, project layout | [docs/en/DEVELOPMENT.md](docs/en/DEVELOPMENT.md) |
| Beginner guides (also inside the program) | [docs/howto/en](docs/howto/en) · [Deutsch](docs/howto/de) |
| Changes | [CHANGELOG.md](CHANGELOG.md) |

## Configuration

Settings live in `reaperpy_config.json` next to the program (template: `reaperpy_config.example.json`).

| Setting | Effect |
|---|---|
| `REAPERPY_HOME=<folder>` (environment) | Keep configuration, profiles and logs elsewhere, e.g. on a USB stick |
| `"auto_codes": false` | Switch off automatic code detection by title ID |
| `"ps5_notifications": false` | No notifications on the PS5 screen |
| `"ps5_notify_hits": true` | Also a message for every breakpoint hit |
| `"auto_update_check": false` | Do not check GitHub Releases on start |
| `"splash": false` or `REAPERPY_NO_SPLASH=1` | No start screen |

Logs are written to `logs/reaperpy.log` (rotating) and include uncaught GUI errors – please attach it to bug reports.

## Credits and licenses

ReaperPy is released under the **[MIT License](LICENSE)**.

**Thanks to**

- **[ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)** – the payload ReaperPy is built for. Author **OSR (OpenSourcereR)**,
  maintained and extended by **Pharaoh2k** (with EchoStretch and Sonic-Iso), GPL-3.0. ReaperPy is only a client of its published
  wire protocol (`PROTOCOL.md`, v1.3.2) and contains none of its code. ps5debug-NG is inspired by `ps5debug` (Ctn, SiSTRo) and
  `ps4debug` (jogolden) and uses the [ps5-payload-sdk](https://github.com/ps5-payload-dev/sdk) by John Törnblom.
- **[ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper)** by TetzkatLipHoka (MIT) – the Unreal tools read its
  output; calling a UFunction follows the method of its `uecall`. No code was copied.
- **[Il2CppDumper](https://github.com/TetzkatLipHoka/Il2CppDumper)** by TetzkatLipHoka (MIT, fork of Perfare's) – the UNITY tab
  reads its `dump.cs` and `script.json`. No code was copied.
- **[PS5Debug-studio](https://github.com/alfizari/PS5Debug-studio)** by alfizari (Apache-2.0) – ReaperPy has its own
  architecture and code; only a few small ideas and format details (such as the `.shn` / `.mc4` layout) were taken over.

See [NOTICE](NOTICE) for what was taken from where and for the licenses of the packages used (Capstone BSD-3-Clause,
Keystone GPL-2.0, Pillow HPND). Binary builds bundle these packages – read the note in `NOTICE` before you distribute one.
