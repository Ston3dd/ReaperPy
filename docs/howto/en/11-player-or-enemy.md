# Player or enemy?

Many games use the same code to change the health of the player **and** of enemies. If you patch "health does not drop" there, everybody becomes immortal - enemies too, and the game is spoiled. This tab finds out how to recognise the player and builds a cheat that applies only to the player (or only to enemies).

## First: the address of the instruction
You need the address of the instruction that changes health, for example from **WHO WRITES?** in the [debugger](howto:debugger). In the **DISASSEMBLER** select the line and click **PLAYER / ENEMY…** - the address is taken over.

## Step by step
1. Open **ADVANCED → PLAYER / ENEMY** and check the address at **INSTRUCTION @**.
2. Click **START RECORDING**. ReaperPy attaches a small code cave to the instruction and writes down what the processor holds each time it runs. The game is not paused.
3. Click **PHASE A: ONLY I GET HIT** and let an enemy hit you, at least 5 times. Do not attack yourself during this time.
4. Click **PHASE B: ONLY ENEMIES GET HIT** and attack enemies, preferably different ones. Do not get hit.
5. Click **EVALUATE**. Below you see the features that are always different in A than in B. The top one is the safest.
6. At **CHEAT** choose a preset, at **APPLIES TO** "only the player" or "only enemies", and click **→ CHEAT EDITOR**.
7. In the cheat editor test with **TEST ON** and save. **STOP** ends the recording.

**Tip:** The cleaner the phases are separated, the safer the result. One hit in the wrong phase is ignored as an outlier, but many are not.

## How ReaperPy recognises the player
- **CALLER** - player and enemies come from different places in the game code. This is the best feature because it stays the same after restarting the game.
- **FIELD** - the object holds a fixed value, for example a team number. This stays the same as well.
- **OBJECT** - the address of the player object itself. It is only valid until you close the game. You have to record again after every start.

In the table the column **SAME AFTER RESTART** shows which features are permanent. The **CONFIDENCE** is "low" when only a few enemies were recorded.

## If nothing is found
- Record more hits in each phase and make sure that in phase A only you get hit.
- Use different enemies in phase B.
- Some games call the code exactly the same for player and enemies. Then only another instruction helps: look with **WHO WRITES?** for one that runs only for the player.

> **Warning:** The cheat reads memory that can look different for enemies. Always test with **TEST ON** before you save, and keep **JOURNAL / UNDO** ready.
