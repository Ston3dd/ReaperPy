# Glossary

**AOB** - array of bytes: a byte pattern with wildcards (`??`) that finds a piece of code even when its address moves. See [Pointers and game updates](howto:pointers).

**Assembler** - the processor's language. See [Assembler for beginners](howto:assembler-basics).

**BASE (00 BASE)** - the first switch of a ReaperPy trainer. It writes the cave and the hook once; the entries then use it.

**Breakpoint** - stops the game when the processor reaches an address. See [The debugger](howto:debugger).

**Cave (code cave)** - a small piece of your own code in free space in the game. The game jumps into it and back.

**Disassembler** - turns bytes into readable instructions.

**eboot.bin** - the game's main program. Its start in memory is the *image base*.

**Float** - a decimal number. Many games store health as float.

**FName** - the number that an Unreal Engine game uses for a name. Item trainers use it to say which item they mean.

**Freeze** - write the same value again and again so it cannot change.

**GObjects** - the list of all objects of an Unreal Engine game.

**Hook** - a place where the game's code is redirected to your code.

**Il2CppDumper** - a tool that dumps the classes and methods of a Unity game. ReaperPy reads its output.

**Image base** - the start address of the game's program in memory. Offsets are counted from it.

**Instance** - one real object of a class in the running game (your character, an enemy).

**Int32** - a whole number stored in 4 bytes.

**NOP** - an instruction that does nothing (`90`).

**Offset** - a distance from a start, for example from the image base.

**Payload** - the program on the console that ReaperPy talks to (ps5debug-NG).

**PID** - the process number of the game.

**Pointer** - an address stored in memory that points to another address.

**Register** - one of the processor's small boxes (`rax`, `rbx` ...).

**RIP** - the register that holds the place the processor is working on.

**SDK dump** - the list of an Unreal Engine game's classes and members that the dumper writes.

**Title ID** - the code of a game on the PS5, for example `PPSA01234`.

**Watchpoint** - stops the game when something reads or writes an address.
