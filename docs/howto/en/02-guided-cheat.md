# Cheat in four steps

The **ASSISTANT** takes you from a number in the game to a finished cheat. You do not need to know assembler: ReaperPy searches the value, finds the instruction that changes it, and builds a preset from it.

## Step by step
1. **Find the value:** Read a number in the game, for example your health, and type it into **NUMBER**. If you only see a bar, choose **Number unknown**. Press **SEARCH**.
2. **Narrow down:** Change the value in the game, for example lose some health. Type the new number into **NEW NUMBER** and press **NARROW DOWN**. If the number is unknown, press **DROPPED**, **ROSE** or **STAYED THE SAME** instead. Repeat until at most 30 hits are left. The list then shows the addresses with their current value, and **REFRESH VALUES** reads them again.
3. **Who changes the value?** Select the hit whose value follows the game and press **WATCH**. The first time, the debugger is attached to the game. Now trigger the change in the game, for example take damage. The game keeps running. The table shows the instruction that wrote the value, with an explanation in plain words and a count.
4. **Create the cheat:** Select the instruction and press **PRESET…**. Choose for example "Switch the instruction off" so the value stops dropping. The cheat lands in the cheat editor. There you test it with **TEST ON** and save it.

**STOP** ends the watching. **PRESET…** ends it by itself.

## When the table lists several instructions
The one with the highest **COUNT** is usually the right one. To see what an instruction does, read the column **WHAT HAPPENS**. An instruction that raises the value when you take damage is not the right one.

## When enemies are affected too
A preset applies to **every** object that uses the code. If the player and enemies share it, enemies become unkillable too. Use ReaperPy's ready-made tools in [Values, live values and the cheat menu](howto:values-and-live) then.

## When nothing happens
- No hits: for decimal numbers, type the number with a dot. Some games store 100 as 100.0.
- Too many hits: change the value in the game once more and narrow down again.
- No instruction in the table: check that the address belongs to the value that really changed in the game. Otherwise pick another hit.

> **Warning:** The debugger stops the game briefly when it evaluates a hit. End the watching with **STOP** before you play on.

More about the single steps: [Find a value](howto:find-value), [Debugger](howto:debugger), [Assembler for beginners](howto:assembler-basics).
