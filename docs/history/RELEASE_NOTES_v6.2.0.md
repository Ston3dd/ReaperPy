# ReaperPy 6.2.0

**The assembler is easier for beginners, and the tool can tell the player from enemies.** Please update - nothing else changes for existing projects.

### Added
- **Assembler without assembler knowledge** (DISASSEMBLER tab):
  - New column **EXPLANATION** says in plain words what the selected instruction does (about 70 instructions, German and English).
  - New button **PRESET...**: ready-made changes instead of typing asm - switch the instruction off, always set the value to a number,
    end the function right away. Writes a patch or builds the code cave for you.
  - **CHANGE...** now shows a live preview while you type (size, fits or not, padded with NOPs) and explains errors in plain
    sentences with the line and an example (the original message stays in brackets). The live preview needs `keystone-engine`.
  - The CONVERTER tab uses the same friendly error messages.
- **New tab SPIELER / GEGNER (PLAYER / ENEMY)** for games where the player and enemies share the same health code (a normal
  cheat would make everybody immortal). Record a few hits in phase A (only you are hit) and phase B (only enemies are hit); the tool
  compares them and finds what tells the player apart: the **caller on the stack**, a **field in the object** (team / type) or the
  **object address**. Results are ranked (stable after restart, confidence). **-> CHEAT EDITOR** builds a cave that applies the cheat
  only to the player (or only to enemies). Red-zone safe, flags preserved. New button **PLAYER / ENEMY...** in the DISASSEMBLER tab.
  - New how-to guide "Player or enemy?" (guides are now 14).
- New modules `asm_explain.py`, `asm_help.py`, `asm_recipes.py`, `whois.py`, `tools_who_gui.py`, `tools_asm_easy_gui.py`.

- **ReapPatch export** for Reaper: **SAVE** in the cheat editor tab now also offers `*.ReapPatch`, written in the exact format Reaper uses
  (byte-identical to a real Reaper file, checked by a test). Reaper turns it into a `.ShnExt` itself. New module `reappatch_fmt.py`.
  - New button **SAVE AS REAPPATCH ...** in the GoldHEN / etaHEN export window writes the marked patches (any source format) as
    `.ReapPatch` files into a folder of your choice - no console connection needed, existing files are never overwritten.

### Fixed
- Rip-relative operands in caves (`[rip + @hook+N]`) were placed wrongly when a jump to a label further down came before them
  (the size of an assembled forward jump differs). They are now measured on the finished code.
- Removed an unused import in `tools_gui.py`.
