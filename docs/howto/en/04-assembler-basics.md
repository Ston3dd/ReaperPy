# Assembler for beginners

Assembler is the language of the processor. You do not have to learn it to use ReaperPy, but a few ideas make the **DISASSEMBLER**, the **CONVERTER** and code caves much easier to understand. The PS5 uses x86-64; ReaperPy writes it in Intel syntax.

## What the tools do
- The **DISASSEMBLER** turns the bytes in memory into readable instructions.
- The **CONVERTER** turns assembler text into bytes and back.
- **EDIT CHEATS** puts the bytes into the game.

## Registers: the processor's boxes
A register is a small box that holds one number. You will see `rax`, `rbx`, `rcx`, `rdx`, `rsi`, `rdi`, `r8` to `r15` (64 bit). `eax` is the lower half of `rax` (32 bit). `xmm0` to `xmm15` hold decimal numbers (float). `rip` is the place the processor is working on right now.

Square brackets mean *the memory at*: `[rbx+0x120]` is the memory at the address in `rbx` plus 0x120. A game's character is often a block of memory, and `0x120` could be the place of its health.

## The instructions you will meet most
- `mov a, b` - copy b into a. `mov [rbx+0x120], eax` writes eax into memory - often the line that sets your health.
- `add a, b` and `sub a, b` - add or subtract. `sub [rbx+0x120], ecx` makes the value go down.
- `inc a` and `dec a` - add or subtract 1.
- `cmp a, b` - compare two values. It only sets flags that the next jump looks at.
- `je`, `jne`, `jl`, `jg` ... - jump if equal, not equal, less, greater.
- `jmp` - always jump. `call` - run a function and come back. `ret` - leave a function.
- `push` and `pop` - put a register on the stack and take it back.
- `lea a, [b+c]` - calculate an address without reading memory.
- `movss`, `addss`, `subss` - the same for decimal numbers (float).
- `nop` - do nothing (one byte, `90`).

## Reading a "who writes" line
Say **WHO WRITES?** found this line for your health:

```
sub [rbx+0x120], eax
```

It means: *take the number in eax away from the memory at rbx+0x120* - damage. Replace it with NOP bytes and the health no longer drops (but enemies' health might not drop either if they use the same code - see the note below). If the line is `mov [rbx+0x120], eax`, the game *sets* the value, and a code cave can set it to what you like.

## Two ways to change it
1. **NOP**: replace the instruction with `90` bytes, as many as the instruction had. The instruction then does nothing. Keep the byte count equal, otherwise the next instruction breaks.
2. **Code cave**: the game jumps into your code, which sits in free space. At the end `jmp OriginReturn` jumps back to where the game continues.

## A first cave, line by line
Goal: health can never drop below 1. The original line was `sub [rbx+0x120], eax`.

```
sub [rbx+0x120], eax          ; keep the original line
cmp dword ptr [rbx+0x120], 1  ; compare health with 1
jge fine                      ; 1 or more: nothing to do
mov dword ptr [rbx+0x120], 1  ; lower than 1: set it back to 1
fine:
jmp OriginReturn              ; go back to the game
```

If health is a *float*, you set a float. 1000.0 is `0x447A0000`: `mov dword ptr [rbx+0x120], 0x447A0000`.

> **Note:** A patch applies to **every** object that uses this code - enemies too. If enemies become unkillable as well, compare the base register (here `rbx`) with the player first, or use ReaperPy's ready-made tools in [Values, live values and the cheat menu](howto:values-and-live).

## Rules that keep the game alive
- Only change registers the game no longer needs there. If unsure, save them: `push rax` at the start, `pop rax` before `jmp OriginReturn`.
- `cmp` and `sub` change the *flags*. Keep the original instruction in the cave unless you want it gone.
- Start with a NOP or a tiny cave. Test. Then make it bigger.
- **JOURNAL / UNDO** takes any change back.
