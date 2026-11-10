# Values, live values and the cheat menu

These tools are for single values: health, stamina, gold, experience, ammo. Pick the one that fits your game.

## VALUES: ready-made patches in three steps
The tab **VALUES** (under **UNREAL** and **UNITY**) is the easiest way. The three steps are the same as for items:
1. Choose the game folder.
2. **FIND THE IMPORTANT STUFF**
3. **SAVE PATCHES**

- **Unreal Engine:** the values of your character come from the SDK and are checked on the running character. For each ticked value ReaperPy builds a cave that stops it from dropping. If the game uses a subtract instruction, that instruction is switched off (ammo and gold stop dropping, picking things up still works). Experience is fixed to the number you enter.
- **Unity (IL2CPP):** methods are recognised by their names (`TakeDamage`, `SpendMoney`, `UseAmmo` ...). Each row says in plain words what happens. Enemy-looking classes are marked and not pre-ticked.

> **Warning:** These patches apply to **all** objects that use the code - enemies too. The Unity name recognition is a heuristic: look through the list before you save.

## LIVE: see and change values while you play
In **UNREAL → LIVE** you choose the game's SDK folder, click a value such as `UHealthComponent.Health` and see the live value on the right. Right-click a row to change the value, freeze or unfreeze it, show it in memory or find who writes it. Instance addresses change with every game start; classes and offsets stay valid.

## CHEAT MENU: switches for your character
Press **BUILD MENU** after loading the game in LIVE. Each entry shows whether it can be reached on your character (check mark) or why not (cross). **ON / OFF** (or double-click) switches an entry and puts the original value back when you switch it off. If your character changes (death, loading screen), all entries are released. **BUILD CODE CAVE** turns the selected entry into a permanent cheat: ReaperPy searches the game code for the instruction that writes the value and saves a cave as a `.reapproj` patch (without an active project it asks for a folder). **CAVE: CHOOSE HIT** lets you pick the instruction yourself.

## DISCOVERER: what is there to find?
**UNREAL → DISCOVERER** analyses the SDK and tells you in plain words what the game offers: item tables, give-functions, stat enums, cheat managers - and whether a trainer can be built for each. Start with **ANALYZE**. **READ TABLE LIVE** lists the rows of a table by name. **SEARCH INVENTORY ENTRIES** sets quantities directly in memory when no give-function fits.

## EXPERT
**UNREAL → EXPERT** holds the static tools: candidates from the SDK headers, instruction search in the dump, NOP and cave patches. It is also a command-line tool (`python ue_auto.py --help`).

## Unity: CHEAT MENU
**UNITY → CHEAT MENU** works like the Unreal one, built from `dump.cs`: method patches (taking damage, spending money, using stamina) and fields (health, gold, stamina, EXP, hunger ...). Load the game folder in MANUAL, connect, load a save and press **BUILD MENU**. **ON / OFF** switches an entry, **SET VALUE** writes a number and holds it, **ALL OFF** restores the originals. For fields **BUILD CODE CAVE** creates a permanent cave; for methods **SAVE PATCH** saves the ready patch.

## Unity: QUICK and MANUAL
In **UNITY → MANUAL**:
1. Choose the Il2CppDumper folder.
2. Start the game, load a save, connect, and press **DETECT MODULE**.
3. Press **SCAN GAME** once. Then you can search `Class.field` (gold, hp, money ...), see all live objects and change or freeze the value. *Methods* lets you make a method return true / false / a fixed number or empty. *Names* lists enums such as item IDs.

All of this is for single-player games on your own console. For the next step see [Export](howto:export).
