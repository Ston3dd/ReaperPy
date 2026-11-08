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

## Sessions
The buttons **LOAD SESSION…** and **SAVE SESSION…** at the top of the tools window store your cheat list and pointer results so you can continue later.
