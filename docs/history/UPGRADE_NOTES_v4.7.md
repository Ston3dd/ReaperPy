# ReaperPy v4.7 — Unreal All-in-One (static discovery)

- Added **UNREAL ALL-IN-ONE** tab in Tools.
- Scans SDK/dump folders and ZIP files locally; does not require uploading a large raw dump.
- Groups static matches into health/survival, money/economy, weapons/combat, inventory/items, movement, debug/cheat menus, progression/unlocks, world/AI, vehicles/equipment, and miscellaneous systems.
- Excludes lines that only indicate building/construction/crafting/material costs.
- Exports JSON and CSV reports with file path, line number, evidence snippet, candidate priority, and category.
- Static candidates are not confirmed working cheats. No automatic memory writes, runtime calls, or code patches are performed by this tab.

## Test
Run `python -m unittest discover -s tests -v`.
