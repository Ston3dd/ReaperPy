# The debugger

The debugger stops the game at a place you choose so you can look inside. Beginners mostly need one thing: **WHO WRITES?** - and ReaperPy sets it up for you.

## Attach
In **ADVANCED → DEBUGGER** enter the process number and press **ATTACH**. **DETACH** lets go of the game again. While a thread is stopped, the game is paused.

## Breakpoints and watchpoints
- A **breakpoint** stops the game when the processor reaches an address. Up to 30.
- A **watchpoint** stops it when something reads or writes an address (4 slots; write, read/write or execute).

When the game stops you see threads, registers (you can edit them) and the stack.

## Moving on
- **CONTINUE** - let the game run.
- **STEP** - one instruction.
- **STEP OVER** - run a function call as a whole.
- **STEP OUT** - run until the function returns.
- **PAUSE** - stop the game right now.

> **Note:** After a watchpoint on a write hits, `rip` points *behind* the writing instruction. The one before it is the writer.

## You and the enemies share one HP bar?
The instruction that writes HP usually serves you **and** every enemy, so a breakpoint on it hits you one time and an enemy the next. The **TARGETS** table separates them: each target address is its own object (Z1, Z2 ...) with value, previous value and change.
1. Set a breakpoint on the writing instruction, turn **AUTO-CONTINUE** on and fight for a moment.
2. Type your current HP into **MY VALUE** and press **FIND** - the matching target is highlighted. Or watch which target changes when you get hit and press **THAT'S ME**.
3. **ONLY THIS TARGET**: hits on other objects continue automatically. **WATCH THIS TARGET** sets a write watchpoint on exactly your address.

## KERNEL LOG
**ADVANCED → KERNEL LOG** shows the console's log with crashes, page faults and errors highlighted. Open it when a patch closes the game.

## FUNCTION LOGGER
**ADVANCED → FUNCTION LOGGER** writes down every call of a function (registers, return address, arguments) without pausing the game. **STOP** puts the original bytes back.

> **Warning:** Do not leave the game stopped for long. Press **CONTINUE** when you are done looking.

More about reading the instructions in [Assembler for beginners](howto:assembler-basics).

## Step by step (for beginners)
A **help line** at the top of the debugger always tells you what comes next:
1. Press **ATTACH** (game running).
2. Set a **WATCHPOINT** on the address of your value (type *write*).
3. Do something in the game that changes the value - the game stops and a **HIT** appears.
4. The **green line** in KONTEXT is the instruction that changes your value. Below it ReaperPy explains in plain words what it does and which cheat idea fits. Right-click → **open in disassembler**, select the line, **BUILD CHEAT**.

If the same instruction hits many objects (you *and* enemies), pick the row with your value in **TARGETS** and press **THAT'S ME**.

## What a cave cheat does
When you create a cave cheat, ReaperPy shows the **whole picture** at the top of the cave text:
1. Which original instructions (and how many bytes) are overwritten in the game - at least **5 bytes** (one `jmp rel32`), the rest NOPs.
2. What the cave does in order: **your code**, then the **copied original instructions**, then `jmp OriginReturn` back into the game.
3. That switching off writes the original bytes back.
