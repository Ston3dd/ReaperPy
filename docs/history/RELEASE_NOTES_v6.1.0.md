# ReaperPy 6.1.0

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


## Update

- Use the in-program update, or download `ReaperPy_v6.1.0_win64.zip` from this page and check it against the `.sha256` file.
