# Items in Unity games

The tab **UNITY → ITEMS** works like the Unreal one: all items of a Unity (IL2CPP) game as a trainer in three steps.

> **Note:** This part is new. Finding items works from the dump alone, but giving items has not been tried on many real games yet. If a method cannot be used, the list tells you why.

## Before you start
- Run **Il2CppDumper** (the TetzkatLipHoka fork, which also works on console memory dumps) on your game. Your folder needs `dump.cs` and `script.json`. Nested folders are fine - the files are searched for.
- Use a dump of **exactly the game version you play**.
- Finding items needs no console connection. Saving does.

## Step 1 - Game
Press **CHOOSE GAME FOLDER …** and pick the Il2CppDumper folder. Loading takes about ten seconds for a large game.

## Step 2 - Find items
Press **FIND ITEMS**. ReaperPy picks the item list (the enum with the item IDs), the method that gives items (`AddItem`, `GiveItem` ... with an item ID and optionally an amount) and an entry point on its own. Tick the items you want.

## Step 3 - Save the trainer
Press **SAVE TRAINER**. The result is a normal ReaperPy project, just like in [Items in Unreal games](howto:items-unreal): switch on `00 BASE` once, then click the entries. Categories, several projects and **CHECK TRAINER …** work the same way.

> **Tip:** Methods that need an item object or a text instead of an ID are listed with the reason and skipped.

## Other Unity pages
For single values and method patches see [Values, live values and the cheat menu](howto:values-and-live).

## Good to know
- Object addresses change with every game start. Classes, offsets and RVAs stay valid for the same game version.
- Set ReaperPy's image base to the IL2CPP module base shown in the tab when you load exported patches in **EDIT CHEATS**.
