# ReaperPy 6.0.2

**Richer colours, general item table detection and complete English texts.**

## Changed
- **Richer colours.** Deeper blue surfaces in four steps, clearly visible borders, brighter secondary text, a green OK colour that is
  no longer the same as the accent, and a strong blue selection colour in lists and drop-downs. Horizontal scroll bars, pane
  dividers and plain ttk frames are dark now as well. All colours come from one place (`theme.py`).
- **Item table detection works the same for every game.** Run-together or upper-case names (`ITEMPARAM`, `MSTITEM`) are split into
  known words instead of searching for substrings, so `Software`, `Hardware`, `Toolbar`, `ToolTip` or `Awareness` are no longer
  taken for item tables. Presentation tables next to an item word (`ItemIcon`, `ItemTooltipText`, `ItemShopUI`) are dropped,
  render words (`PhysicalMaterial`, `SurfaceMaterial`, `MaterialInstance`) are no item tables, and common abbreviations (`Itm`,
  `Wpn`, `Eqp`, `Armr`, `Cosmetics`) are recognised.

## Fixed
- **English mode.** About 110 messages (ITEMS and VALUES tabs, the trainer README, the GoldHEN/etaHEN export, the image base check
  and more) were only half translated and now have complete English texts.
- The Unity ITEMS GUI test no longer needs the GNU assembler (it failed on Windows).

## Removed
- `lager_slots.py`, a stand-alone script for a single game that the program never used.

## Update
- **From 6.0.0 or 6.0.1:** ReaperPy offers the update itself (dialog -> *Install now*, then *Restart now*).
- **From 5.9.1 or older:** download `ReaperPy_v6.0.2_win64.zip` from this page, check it against the `.sha256` file and unpack it
  over your folder (see the notes of 6.0.0 for details).
- Trainers you saved with 6.0.1 keep working; nothing has to be saved again.
