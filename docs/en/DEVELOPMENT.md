# Development, tests and releases

Running the tests, code style, CI, making a release and the project layout.

[← Back to the README](../../README.md)

---

## Development and tests

```bash
python -m unittest discover -s tests -t .
```

The tests run without a console and without a display: a fake payload server, simulated process memory, a synthetic Unreal
world and a Tk stand-in for the GUI. Tests that need Keystone or a native toolchain are skipped when it is missing.

**What is not covered:** the real console with a real payload, the real look of the Tk windows, and real games. Behaviour on
hardware depends on your console, payload and game - try new features with a single-player game and a backup first.
Please include the log (`logs/reaperpy.log`) in bug reports.

Code style: `ruff` (configured in `pyproject.toml`, line length 120). The enabled rules are deliberately small - `F`
(real errors: unused imports/variables, undefined names) and `E711` / `E712` / `E721` / `E731`:

```bash
ruff check .          # must report "All checks passed!"
```

Careful with `ruff check --fix`: it removes imports that are only used as a re-export (`ps5_ext.STATUS_*` is read by
`debugger.py`). Such lines carry `# noqa: F401` and a comment; run the tests after every auto-fix.

**Continuous integration** (`.github/workflows/ci.yml`): the tests run on every push and pull request (Linux with Python 3.10
and 3.12, Windows with 3.12, with Keystone and Capstone installed); `ruff` runs as an informational job.

**Making a release**

1. Raise `version.py` (and `version_info.txt`), add a `## <version> - <date>` section to `CHANGELOG.md`
   (`python scripts/changelog_from_git.py <last tag> <version>` drafts it from the commit messages), write
   `docs/history/RELEASE_NOTES_v<version>.md`.
2. `python scripts/release_notes.py <version>` prints the text that goes into the GitHub release.
3. Tag and push: `git tag v<version> && git push origin v<version>`. The release workflow checks that the tag equals
   `version.py`, runs the tests, builds the Windows zip with its `.sha256` and publishes the release. Building by hand
   instead: name the file `ReaperPy_v<version>_win64.zip` and upload the `.sha256` file as well - the self-updater needs both.

## Project layout

| Path | Contents |
|---|---|
| `gui.py`, `branding.py`, `i18n.py` | Main window, splash screen, main-window texts (DE/EN) |
| `tools_*.py` | Tools window and its tabs; `tools_i18n*.py` translates them at runtime (also texts set later, context menus, headings) |
| `theme.py` | The one colour palette of the whole interface |
| `asm_explain.py`, `asm_help.py`, `asm_recipes.py`, `tools_asm_easy_gui.py` | Instruction explanations, friendly errors, recipes, assembler dialogs |
| `whois.py`, `tools_who_gui.py` | PLAYER / ENEMY: recording stub, analysis, guarded cave |
| `howto.py`, `tools_howto_gui.py`, `docs/howto/` | How-to guides: files, small Markdown parser and search, the HOW TO window |
| `ps5_client.py`, `ps5_ext.py`, `ps5_more.py`, `ps5_backend.py` | Payload protocol client |
| `ps5_notify.py` | Notifications on the PS5 screen (connect, cheats, debugger) |
| `scanner.py`, `pointerscan.py`, `ptrscan_server.py` | Scanner and pointer scan |
| `debugger.py`, `unwind.py` | Debug session, stack unwinder |
| `patch_engine.py`, `reapatch.py`, `cave_trainer.py`, `export_goldhen.py`, `cheatfmt.py` | Patches, caves, trainers and export |
| `ue_*.py`, `uesdk.py`, `uecheat.py`, `cheatmenu.py` | Unreal Engine support and the cheat menu logic (`ue_items.py`: rating of tables and functions, items, amount limits, inventory expansion) |
| `item_check.py` | Tests for items: pre-check (read only), live test with a short cave, give-now and expansion through the cave |
| `il2cpp_dump.py`, `tools_unity_gui.py` | Unity (IL2CPP) support: Il2CppDumper output, live instances, method patches |
| `unity_items.py`, `tools_unity_items_gui.py` | Unity ITEMS: items as a trainer for IL2CPP games |
| `updater.py`, `update_ui.py`, `version.py` | Self-update from GitHub Releases (download, SHA-256 check, backup + rollback), update dialog, program version |
| `imagebase.py` | Checks the image base against the console's memory map (never guesses) |
| `scripts/`, `.github/workflows/` | Changelog / release-note helpers; CI (tests, lint) and the release build |
| `docs/` | `howto/` the beginner guides (`de/`, `en/`), `en/` reference pages, `de/` German README and notes, `history/` old release notes, `screenshots/` |
| `tests/` | Unit tests |


---

## Windows build and updates

A Windows folder build (no Python needed) is created with `build_exe.bat` (PyInstaller, no `--onefile`: configuration,
profiles and logs stay next to the EXE).

**Ready-made Windows build.** Download `ReaperPy_v<version>_win64.zip` from the GitHub **Releases** page, check it against the
`.sha256` file next to it, unpack it and start `ReaperPy.exe`. Releases from 5.9.1 on can update themselves (see **Auto-update**
below); 5.9.0 and older have to be replaced by hand once. The updater of 5.9.1 cannot replace files that the running program has
open - if the update from 5.9.1 ends with `[WinError 32]` and "rolled back" (nothing changed), unpack the 6.0.0 zip over the folder
once; from 6.0.0 on files in use are applied when ReaperPy has closed.

The updater itself (checks GitHub Releases on start, shows the notes, downloads, verifies SHA-256, backs up and can roll back) is switched off with `"auto_update_check": false`; a different repository is set with `"update_repo": "owner/name"`. A git checkout is never overwritten (use `git pull`). Your config, profiles and logs are kept.
