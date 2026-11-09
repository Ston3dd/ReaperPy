# Edit cheats

The tab **EDIT CHEATS** writes a patch: a change to the game's code that you can switch on and off. You get there from **WHO WRITES?** in [Find a value](howto:find-value), or you start from an address you already know.

## What a patch consists of
- **Name** and **author** - what you see in the patch list.
- **Offset** - the distance from the start of the game's program (the *image base*), so the cheat keeps working after a restart.
- **Original bytes** and **new bytes** - what is there now and what should be there.

## Two kinds of patch
- **Simple patch / NOP** - replace the original bytes with new ones. A NOP is an instruction that does nothing; it is the quickest way to stop a value from changing, for example to stop it from dropping.
- **Code cave** - your own small piece of assembly code in a separate box. The game jumps into it, it does its work, and `jmp OriginReturn` goes back. Use a cave when a NOP is not enough, for example to set a value.

You can type assembler text or raw hex bytes. [Assembler for beginners](howto:assembler-basics) explains the instructions and has a worked example.

## From a found value to a cheat
1. In **FIND VALUE**, add the address and press **WHO WRITES?**. The debugger waits until the game writes the value.
2. ReaperPy shows the instruction that did it. The place where the game stopped is *behind* the writing instruction - the one before it is the writer.
3. Send it to **EDIT CHEATS**. Choose NOP or code cave.
4. Save. The project is stored as a `.reapproj` file and appears as a card in the main window.
5. Switch the card on and test it in the game.

> **Warning:** A patch can close the game when it is wrong. Save the game first. **ADVANCED → JOURNAL / UNDO** takes the change back, and **ADVANCED → KERNEL LOG** shows what happened.

## Share it
Export your patches for GoldHEN / etaHEN - see [Export](howto:export).
