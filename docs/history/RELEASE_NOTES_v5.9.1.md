# ReaperPy 5.9.1

**Hotfix: connecting works again.** Everyone on 5.9.0 should update.

## What was wrong
In 5.9.0, pressing **CONNECT** ended with

```
[net] ERROR module 'imagebase' has no attribute 'check_base'
```

The image base check that runs right after the connection is made called a function that no longer existed, so ReaperPy
could not be used with a console. 5.9.1 fixes this; the check behaves as designed again:

- **Image base matches the console's memory map** - one info line in the log.
- **Image base is shifted** - warning, and the image base is set to the value found in the memory map (so trainers find their cave
  and patches hit the right addresses).
- **The memory map has no module names** - warning with the list of modules; nothing is guessed.

## Update from 5.9.0
5.9.0 has no self-update. Download `ReaperPy_v5.9.1_win64.zip` from this page, check it against `ReaperPy_v5.9.1_win64.zip.sha256`
and unpack it over your old folder (or into a new one). Your `reaperpy_config.json`, profiles, logs, library and `applied.json`
are in the program folder, so copy them over if you unpack into a new folder.
**From 5.9.1 on, ReaperPy offers updates by itself** (see below).

## Also new since 5.9.0
- **Self-update from GitHub Releases.** 4 seconds after start ReaperPy checks for a newer release and shows its notes with
  **Install now / Later / Skip this version**. The download is checked with SHA-256, the old files are backed up and restored
  automatically if something goes wrong, and your config, profiles, logs, library and `applied.json` are never overwritten.
  START tab -> *Check for updates* runs the same check by hand. Turn it off with `"auto_update_check": false`.
- **Trainers survive small game updates.** Trainers store function starts as signatures with wildcards. If a function only moved,
  the ITEMS tab offers to adapt the trainer to the new addresses; if it is gone or ambiguous it still says "other game version".
- **Preview before saving a trainer.** The ITEMS tab shows where the cave and the switch will land (region, `r-x` / `rwx`, warning
  for writable caves) and writes nothing until you confirm.
- **Safer code caves:** the cave prefers non-writable code regions; on disable only the hook is restored and the cave stays
  (zeroing it could crash a thread that is still running inside).
- Fixes: a crash in `spec_document()` with signature-style anchors, missing English texts for the UE-LIVE connection messages,
  file handles left open in the Unreal dump loader, long byte dumps in the patch log are cut to 32 bytes.

## Known limitations
- Developed and tested against a **simulated console** (737 automated tests, run on Linux and Windows in CI). The real console, the
  real look of the windows and real games are not covered - please test with a savegame you do not need and attach
  `logs/reaperpy.log` to bug reports.
- Value patches apply to **all** objects that use the patched code (enemies too). Only one items project should be active at a time.

## Requirements
Python 3.10+ (or the Windows build), a PS5 with a ps5debug-NG compatible payload. See the [README](../../README.md).

## Credits
ps5debug-NG (OSR / Pharaoh2k, GPL-3.0). See `NOTICE` and the README.

**Full changelog:** [`CHANGELOG.md`](../../CHANGELOG.md)
