# Find a value

The cheat searcher finds where a game keeps a number such as your health or money. You search for the number, change it in the game, search again, and repeat until only a few addresses are left. Then you can change or freeze the value.

## Step by step
1. Open the tab **FIND VALUE**.
2. Type the number you see in the game into **Value** (for example `100`). Leave the type on a 4-byte whole number (Int32) and the compare mode on *Exact*.
3. Press **FIRST SCAN**. The hits appear on the left.
4. Change the number in the game (take damage, spend money, fire a shot). Type the new number and press **NEXT SCAN**.
5. Repeat step 4 until only a handful of hits are left.
6. Select the hits and press **→ ADD SELECTED** (or double-click one). They move to the **address list** at the bottom.
7. Select an entry and press **SET VALUE**, or **FREEZE** to hold it.

> **Tip:** If the game shows 100 but the first scan finds nothing, try the type *Float*. Many games store health as a decimal number.

## When you cannot see the number
Health bars and percentages have no number you can type. Use the compare mode *Unknown initial value* for the first scan. Then, after something happened in the game, use *Increased*, *Decreased*, *Changed* or *Unchanged* for the next scans.

> **Note:** An unknown-value scan keeps a copy of the game's memory. Under **OPTIONS …** you choose how much of it stays in the console's RAM and where the rest goes.

## Scan less, find faster
The area **MEMORY SECTIONS** shows what is in the game's memory and what gets scanned. Every row has a checkbox.
- By default the system libraries are hidden, which is normally safe for game values.
- **ALL**, **NONE**, **EBOOT ONLY** and **GAME ONLY** switch many rows at once.
- If a value is not found, switch the filter to *ALL* and scan again.

## After you found it
- **WHO WRITES?** finds the instruction that changes the value. [Edit cheats](howto:edit-cheats) can turn it into a patch.
- **→ POINTER SCAN** helps when the address changes after a restart - see [Pointers](howto:pointers).
- **→ HEX** shows the address in the memory view.

## If nothing is found
- The number may be stored differently. Try *Float* or a different integer size.
- Displayed numbers can be rounded. Use *Between* or *Approx. (float)*.
- Make sure the value really changed between two scans and the game was not paused.
- Switch the memory filter to *ALL* and try again.
