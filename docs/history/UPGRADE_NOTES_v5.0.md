# ReaperPy v5.0 — Unreal Intelligence Profiles

## Added
- Evidence-based per-class capability profiles for health/survival, economy, weapons/ammo, inventory/items, debug/console, movement, progression, world/AI, equipment/vehicles, and save/settings.
- Ranked item catalog separates likely item definitions, inventory/item flow, unclassified item-related symbols, and likely UI/recipe/build noise.
- `add_flow_signal` is only a static signature clue; it is not proof that the game accepts an item ID or that the operation is safe/supported.
- JSON reports include `capability_profiles` and `item_catalog` alongside existing candidate evidence and class summaries.
- New unit test verifies profile/catalog generation.

## Constraints
- Analysis is static and read-only. No live memory writes, code patching, runtime invocation, or automatic activation.
- Every result is unvalidated until checked against a controlled runtime and game-specific semantics.
- Build/crafting cost lines are excluded from candidate findings; classes related to recipes/building may still appear in the noise-separated item catalog to explain why they were rejected.
- The raw multi-gigabyte memory dump is not needed for SDK/header indexing. Runtime validation of addresses and behavior requires a separate, explicitly configured authorized test environment.

## Test
`python -m unittest discover -s tests -v`
