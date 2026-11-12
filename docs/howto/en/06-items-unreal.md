# Items in Unreal Engine games

The tab **UNREAL → ITEMS** gives you every item of an Unreal Engine game as a ready-made trainer in three steps. You do not need to know tables, FNames or item IDs.

## Before you start
- ReaperPy needs the output of the **ps4-unreal-dumper** for your game (a folder with `offsets.json`, `SDK/SDK_HEADERS`, optionally `dump.bin`, `dump.json`, `GObjects.txt`).
- Connect in the main window, start the game and load a save.

## Step 1 - Game
Press **CHOOSE GAME FOLDER …** and pick the dumper's folder. ReaperPy remembers it.

## Step 2 - Find items
Press **FIND ITEMS**. ReaperPy rates every table and function of the game, picks the item table(s) and a give-function it can build a trainer for, reads all items from the running game and sorts them into categories. Tick or untick items (click the box, double-click, or press Space), search by name, filter by category. **ALL ON** and **ALL OFF** work on the rows you see.

- **Filter** *strict / normal / off* - how strictly tables and functions are filtered. If nothing is found, the log tells where the filter dropped things.
- Only advanced users need *Change the choice myself*: it lets you pick the item list and the give-function.

## No item list found?
ReaperPy first recognises the item table by its **name** (Item, Weapon, Loot ...). If the game uses other names, it then looks at the **content** of every table: how many entries, whether the names form groups like `Sword_Iron`, `Potion_Small`, and whether they sound like items. A list found this way is marked with a warning sign and the first names, so you can see at once whether it really contains items.

If nothing is found, a line appears under the buttons:
- **Type the name of an item you can see in the game** (for example *Potion*) and press **SEARCH IN ALL LISTS**. ReaperPy looks for that name in every table and takes the one it is in as the item list. In games that are translated, the name on screen can differ from the internal one - then try the English name or just a part of it.
- **CHECK ALL LISTS** rates every table by content and offers the best ones under *Possible item lists*, each with its size and the first names so you can recognise it.

If the strict filter finds no give-function, ReaperPy loosens the filter once by itself and tells you so. Check such a function with **TEST 1 ITEM**.

## Step 3 - Save the trainer
Press **SAVE TRAINER**, enter the amount per item and save. The amount is cut to the game's own limit where the table has one. The result is a normal ReaperPy project:
1. Choose the folder as a project.
2. Switch on `00 BASE` once.
3. Click the entries.

Saving only reads the game. Nothing changes until you switch on BASE.

> **Tip:** Large lists are split into several projects (`Items 1`, `Items 2` ...). Activate only **one** at a time.

## Test or give right away
- **TEST 1 ITEM** - gives one item and asks whether it arrived. The answer is remembered for this game.
- **GIVE NOW** - gives all ticked items immediately, without a trainer. Save in the game to keep them.
- **TEST CHECKED ITEMS** - checks the trainer before you save it: image base, give-function, cave space and every item's name.
- **INVENTORY TO MAX** - only shown if the game has an inventory-expansion function. Click it yourself if you need more room; GIVE NOW and SAVE TRAINER do not unlock slots.

> **Warning:** Stay in the game while you test (not in the main menu) and save first.

## Only the first item arrives?
The game refuses an item without a free slot. Run **INVENTORY TO MAX**, give fewer items or categories at a time, or choose the warehouse function under *Change the choice myself*.

## After a game restart
Trainers saved with ReaperPy 6.0.1 or newer find their objects again by themselves. A trainer saved with an older version keeps a fixed address and only works until the game is closed: load a save, press **FIND ITEMS** and **SAVE TRAINER** again.

## Check a trainer from someone else
**CHECK / ADAPT TRAINER …** compares a trainer folder with your running game ("matches the game version" or "built for a DIFFERENT version - do not activate"). If only the item numbers differ, it offers to adapt the trainer for your game.

## Image base
ReaperPy checks the image base against the console's memory map. If they differ it offers **ADOPT BASE**. It never guesses a number.

If your game has no give-function that fits, see [Values, live values and the cheat menu](howto:values-and-live). More help: [Troubleshooting](howto:troubleshooting).
