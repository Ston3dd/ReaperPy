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

## KERNEL LOG
**ADVANCED → KERNEL LOG** shows the console's log with crashes, page faults and errors highlighted. Open it when a patch closes the game.

## FUNCTION LOGGER
**ADVANCED → FUNCTION LOGGER** writes down every call of a function (registers, return address, arguments) without pausing the game. **STOP** puts the original bytes back.

> **Warning:** Do not leave the game stopped for long. Press **CONTINUE** when you are done looking.

More about reading the instructions in [Assembler for beginners](howto:assembler-basics).
