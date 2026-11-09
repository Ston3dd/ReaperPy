# Export for GoldHEN and etaHEN

You can take your cheats out of ReaperPy and use them in the cheat menu of GoldHEN or etaHEN.

## Formats
- `.json` - the GoldHEN cheat format.
- `.shn` - SHN XML. On / off only: buttons are exported as switches.
- `.mc4` - SHN, encrypted, with the file name `TITLEID_VERSION.mc4`.

## Export
1. Open your project in the main window and switch on what you want to export.
2. Press **GOLDHEN-JSON** and choose the format.
3. Use **TITLE ID/VERSION FROM GAME** so both values come from the running game.

The title ID and the version must match the game. The exporter only knows mods in section 0 of the GoldHEN JSON; other sections are skipped, not imported half. You can also **import** such files.

## Put it on the console
Copy the file to the console:
- GoldHEN: `/user/data/GoldHEN/cheats/json/`
- etaHEN: `/data/etaHEN/cheats/json/`

Then start the game and open the cheat menu.

## Item trainers
An item trainer is exported as several switches. Switch them on in this order:
1. `00a BASIS 1 - Cave`
2. `00b BASIS 2 - Haken`
3. then the items

(The two switches are named like this in the file; *Haken* is German for hook.)

Good to know:
- The files only fit **this game version**. Export again after a game update.
- The item numbers (FNames) come from the game session. If they change between game starts, the trainer only works until the next restart: restart the game once and test it again.
- BASE and the tool's own hook (**ITEMS → GIVE NOW**) exclude each other: switch BASE off before you use GIVE NOW.

> **Warning:** Exported cave trainers have been tested on a processor, not on every game. Save first and try one switch at a time.

If a cheat does not show up in the menu, see [Troubleshooting](howto:troubleshooting).
