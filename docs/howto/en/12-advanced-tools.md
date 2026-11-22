# Advanced tools

Everything here is under **ADVANCED**. You do not need these for the simple tools.

## MEMORY
A hex view of any address with a *value inspector* (click a byte to see it as number, float and text), snapshot and compare, saving a region to a file and loading a file into memory.

## DISASSEMBLER
Shows the game's code as readable instructions from any address. Page forward, follow jumps and calls with a double-click. See [Assembler for beginners](howto:assembler-basics).

## CONVERTER
Turns assembler text (x86-64, Intel syntax) into hex bytes and back.

## CALL FUNCTION
Calls a function of the game with up to six arguments: `base+0x1234`, numbers, text in quotes, or buffers in the game. It shows the result (RAX) as hex, signed number, float and text. It never repeats on its own.

> **Warning:** Calling a function that expects other arguments can crash the game.

## PYTHON SCRIPT
A script editor with the `ps5` object:

```
base = ps5.module()                               # start of the game's program
hp = ps5.pointer(base + 0x4A1C00, 0x20, 0x1C4)    # follow a pointer path
if hp:
    ps5.write_u32(hp, 999, undo=True)             # write, can be undone
```

Also available: `ps5.aob()`, `ps5.nop()`, `ps5.call()`, `ps5.foreground()`, `ps5.write_many()`, `ps5.log_calls()`, `ps5.alloc()`.

## JOURNAL / UNDO
Every write the tools make is recorded with the old bytes. Undo single entries or everything with **UNDO ALL**.

## KERNEL LOG
Shows the console's messages live. **Errors and crashes are red**, warnings yellow. It helps when the game suddenly closes after a patch: look at what was logged just before.
1. Press **START** (connects to the console, turns into **STOP**).
2. Keep playing until the problem happens.
3. Use the **Filter** to search for a word, **SAVE…** to store the log as a file (handy when asking for help), **CLEAR** to tidy up.

> **Tip:** If nothing shows up, the log service is not running on the console or you are not connected. Nothing else is affected.

## FUNCTION LOGGER
Shows **when a game function is called** and with which values. Useful to find out which function runs when you buy something or take damage.
1. Enter the **address** at the start of the function (from the DISASSEMBLER).
2. Press **START**. Trigger the action in the game. Every call shows up as a row.
3. Press **STOP**. That puts the game back exactly as it was.

> **Warning:** The logger replaces the first bytes of the function with a jump (at least 5 bytes). If a jump lands in the middle of them the game can crash, so ReaperPy asks first. Do not forget **STOP** before closing the window.

## AOB / UPDATE
After a **game update** the addresses of your cheats are wrong. An **AOB** (byte pattern) lets ReaperPy find the spot again.
1. Load your cheats with **LOAD LIST**, then **CREATE SIGNATURES (missing)**. Best done *before* the update, while the cheats still fit.
2. After the update start the new game and press **UPDATE SCAN**. The *FOUND* column shows which cheats have their spot back, *NEW OFFSET* the new address.
3. **APPLY OFFSETS** writes the new addresses in.

At the top you can also search a **PATTERN** by hand (**SERVER SCAN** on the console, **LOCAL (ALL)** in loaded files) or build a pattern from an address (**CREATE**).

> **Tip:** If the scan cannot find a spot, the game's code has changed. Then rebuild the cheat.

## Sessions
The buttons **LOAD SESSION…** and **SAVE SESSION…** at the top of the tools window store your cheat list and pointer results so you can continue later.
