# ReaperPy 6.0.1

**Item trainer hotfix.** Please update if you use the ITEMS tab or export item trainers to GoldHEN/etaHEN.

## Fixed
- **Trainers keep working after the game is restarted.** The cave no longer stores a fixed object address; it finds the object
  itself through the game's object list (`GObjects`). If the object does not exist yet (e.g. main menu), the call is skipped and the
  game carries on.
- **Crash right after activating BASIS.** The cave now goes into the game's own code padding first; the small extra region `(aux)`
  is only used when the game code has less than 2 KB free.
- **GoldHEN/etaHEN export:** BASIS is split into two switches (`00a BASIS 1 - Cave` first, `00b BASIS 2 - Haken` second), so a hook
  can no longer point at empty memory. A second cave can no longer overwrite the end of the item trainer's cave.
- **Your own file names are used.** Renaming a trainer file is respected; saving into the same folder no longer leaves stale copies
  with old cave addresses behind.
- **Smaller caves** (about 30 % less code), so a big trainer fits into one project.

## Update
- **From 6.0.0:** ReaperPy offers the update itself (dialog -> *Install now*, then *Restart now*).
- **From 5.9.1 or older:** download `ReaperPy_v6.0.1_win64.zip` from this page, check it against the `.sha256` file and unpack it
  over your folder (see the notes of 6.0.0 for details).
- **Trainers saved with an older version:** open ITEMS, **FIND ITEMS**, **SAVE TRAINER** once more so they get the new cave.
