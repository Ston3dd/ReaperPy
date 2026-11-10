# Troubleshooting

## I cannot connect
- Press **TOOLS → START → CHECK CONNECTION**: it tells you in plain words whether the IP, the console, the payload or the game is the problem.
- Is the payload loaded and the game running? Check the IP in **PS5 IP**.
- The PC and the console must be in the same network. Allow ReaperPy through the firewall (port **755** for the debugger).
- Tick **AUTO-RECONNECT** in the main window if the connection drops now and then.

## The scan finds nothing
See the end of [Find a value](howto:find-value): try *Float*, switch the memory filter to *ALL*, and make sure the value really changed between two scans.

## The game closes after I switch something on
1. Open **ADVANCED → KERNEL LOG** and read the highlighted lines.
2. Use **ADVANCED → JOURNAL / UNDO** to take the change back.
3. Try a smaller change: a NOP instead of a cave, one entry instead of many.
4. Make sure the image base is right: **ADOPT BASE** in the ITEMS tab fixes it from the console's memory map.

## Items do not arrive
- Stay in the game, not in the main menu, and load a save.
- Only the first item arrives: the backpack is full. Use **INVENTORY TO MAX** or give fewer items - see [Items in Unreal games](howto:items-unreal).
- The trainer worked yesterday and not today: a trainer saved with an old ReaperPy keeps a fixed object address. Press **FIND ITEMS** and **SAVE TRAINER** again (version 6.0.1 and newer find the object by themselves).
- The game was updated: use a dump of the new version, find and save again.

## The cheat does not show up in GoldHEN / etaHEN
- Is the file in the right folder? See [Export](howto:export).
- Do title ID and version match the game exactly? Use **TITLE ID/VERSION FROM GAME**.

## Unity: the module is not found
Load a save first, connect, and press **DETECT MODULE**. If it fails, the log shows what was found; you can also type the base address in by hand.

## ReaperPy shows a mix of German and English
Switch with **DE / EN** in the main window. Texts that the program creates while it runs are translated at once; if you still see one, please report it.

## Where are the logs?
In the program folder: `logs/reaperpy.log`. The buttons **OPEN LOG FOLDER** and **CHECK FOR UPDATES** are on the START tab.
