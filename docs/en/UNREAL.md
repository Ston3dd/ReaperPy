# Unreal Engine games

Items as a trainer, values, trainer check, cave space, the manual way.

[← Back to the README](../../README.md)

---

## Unreal Engine games

ReaperPy reads the output of [ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper): `offsets.json`,
`SDK/SDK_HEADERS`, optionally `dump.bin`, `dump.json`, `GObjects.txt`. UE 4.23+ and UE 5 (FNamePool) are supported.

**Items as a trainer (the easy way) - tab UNREAL -> ITEMS**

1. **Game** - choose the game folder (remembered) and connect in the main window; start the game and load a save.
2. **FIND ITEMS** - ReaperPy rates every table and function of the game, picks the item table(s) and a give-function it can
   build a trainer for, reads all items live and sorts them into categories (from a category/type column or the item names,
   e.g. `Item_Fish_Trout` -> *Fish*). Only suitable entries are offered; effect, UI, sound, enemy and text tables are left out.
   Tick or untick items (click the box, double-click, Space, right-click menu), search by name, filter by category, **ALL ON /
   ALL OFF** act on the visible rows.
   - **Filter** *strict / normal / off* - how strictly tables and functions are filtered (default *normal*; *off* hides nothing).
     If nothing is found, the log tells where the filter dropped things.
   - **Read all item lists together** - merges all item tables (up to 12) into one list.
   - **Change the choice myself (advanced users only)** shows *Item list* and *Give function*; *also show unsuitable ones* adds the
     rest with the reason. Functions that were tested successfully are marked "tested".
3. **SAVE TRAINER** - enter the amount per item and save. The amount is cut to the game's own limit per item where the item table
   has one (`OwnLimitByBackPack`, ...). Items become entries of 14 per category (*Fish 1*, *Fish 2* ...). Very large lists are
   spread over several projects (`Items 1`, `Items 2` ...; at most 400 items and 64 entries per project) - activate only **one**
   at a time. The folder is a normal ReaperPy project: choose it, activate `00 BASIS` once, then click entries. Saving only
   reads the game; nothing is changed until you activate BASIS.

**Test it, or give items right away.** All of these run through a short code cave that the game executes itself on its own thread
(the same safe way as a saved trainer); the hook is removed afterwards. Save the game first and stay in the game (not in the main
menu).

| Button | What it does |
|---|---|
| **TEST 1 ITEM** | Gives ONE item through the chosen function and asks whether it arrived. The answer is remembered for this game: tested functions are ranked up and marked "tested", failed ones are ranked down. |
| **GIVE NOW** | Gives all ticked items immediately (no trainer, no BASIS). The items arrive like picked-up ones; save in the game to keep them. |
| **TEST CHECKED ITEMS** | Checks the trainer *before* you save it: image base, give function, native code, object, hook, free cave space, and every item's name against the game. Optionally (asks first) triggers each item once in the running game. Failed items are unticked. |
| **INVENTORY TO MAX** | Only shown if the game has an inventory-expansion function (found in the SDK, for example `DevExpansionEnableSlotByMaxLevel`). Runs it once; close and reopen the inventory afterwards. GIVE NOW and SAVE TRAINER do **not** unlock slots on their own - click this button yourself if you need more room. |

**Only the first item arrives / backpack full?** The game refuses an item that has no free slot, and every different item needs its own
slot. Run **INVENTORY TO MAX** before you give items if you need more room. Items land where the give function puts them - usually the backpack, which has a limit. ReaperPy cuts the amount to
that limit; for more room use **INVENTORY TO MAX**, or choose the warehouse function (`...ToWarehouse`) under *Change the choice
myself*, or give fewer items / categories at a time.

**Objects the trainer cannot reach.** Some games keep the inventory in a game-instance subsystem that the player controller does not
reach. ReaperPy then calls the object through its fixed address (checked against its vtable, skipped if the object is gone). This
is valid until the game is closed: after every game start load a save, **FIND ITEMS** and **SAVE TRAINER** again. The status line
and the save dialog tell you when this applies.

**Health, gold, experience, ammo (tab VALUES).** One tab for both engines; same three steps.
- *Unreal Engine:* the values of the player character come from the SDK (health, stamina, mana, shield, ammo, money,
  experience) and are checked on the running character. SAVE PATCHES searches the game code for the instructions that write
  each ticked value and builds a code cave per value: **value cannot drop**; if the game uses a subtract instruction
  (`sub`/`dec`) that instruction is switched off instead (ammo and gold stop dropping, picking things up still works);
  otherwise the value is fixed to a number. **Experience** is fixed to the number you enter (default 99999 = level-up).
- *Unity (IL2CPP):* methods are recognised by name from `dump.cs` (`TakeDamage`, `SpendMoney`, `UseStamina`, `UseAmmo`,
  `get_ExpToNextLevel` ...). Each row says in plain words what happens (method made empty / always returns yes / returns 1).
  Enemy-looking classes are marked and not pre-ticked. The patches read the original bytes live and carry `"Verify"`, so a
  different game version refuses them. Set the image base to the shown IL2CPP module base before activating.
- Patches apply to **all** objects that use the code (enemies too). Unity name recognition is a heuristic - check the list;
  XP can only be handled when the game has a "needed XP for next level" method.

**Using a trainer made on another console / checking one.** The item numbers (FNames) inside a trainer come from the game
session it was built in and can differ on another console; a different game version changes the code addresses. Click
**CHECK / ADAPT TRAINER ...** and choose the trainer folder: ReaperPy compares the trainer's function fingerprints with your
running game ("matches the game version" / "built for a DIFFERENT version - do not activate") and the item numbers with
your game. If only the item numbers differ it offers to **adapt** the trainer (rewrites the files for your game; its BASIS
must be off). Trainers made by ReaperPy are also protected when activated: if the memory at the patch site is neither the
expected original nor the patch, activation is refused instead of overwriting something else.

**Space for the cave.** The cave is placed in unused padding at the end of the game's code regions. ITEMS reads how much
room your game has and splits the trainer into as many projects as needed. If there is still no room, the message shows the
numbers (needed bytes, largest gap, regions whose end is occupied by another cheat or a still active cave).

**Image base.** ITEMS checks the base set in the main window against the console's memory map (module `eboot.bin`). If they
differ it says so, shows the base from the map and offers **ADOPT BASE**; it never guesses a number.

Not every game works: if the SDK has no give-function the trainer can build (the tab tells you why), use **UE DISCOVERER ->
SEARCH INVENTORY ENTRIES** to set quantities directly in memory.

**Manual way (special cases)**

1. In **UE-LIVE** choose the game folder and connect. The object index is built once per game start.
2. **UE DISCOVERER** -> **ANALYZE** for a plain-language summary and next step; **READ TABLE LIVE** lists item rows by name
   (search box above the list - you never need to know numeric IDs; an ID column is picked up automatically).
3. **CHEAT MENU** for switches; **UE-LIVE** for any value; **UE-AUTO** for static patches.

Instance addresses change with every game start; classes, offsets and the SDK stay valid. Functions that create objects
(spawning actors, widgets) can crash the game when called from a helper thread - prefer functions that read and write values.
