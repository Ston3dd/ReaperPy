# Pointers and game updates

The address of your health usually changes every time the game starts. Two tools help.

## POINTER: find the way to the value
A pointer is a stored address that leads to another one. A *pointer path* starts at something fixed (the game's program) and ends at your value, so it keeps working after a restart.

In **ADVANCED → POINTER**:
1. Choose the address of your value and press **1) CREATE MAP**.
2. Press **2) FIND PATHS**.
3. Restart the game, find the value again, and press **3) CHECK (new target)** to keep only the paths that still lead to it.
4. Press **TOP 10 → CHEAT LIST** to use the best ones.

**QUICK SCAN (console)** runs level by level on the console and is much faster (it needs a payload that supports it). From **FIND VALUE** you reach the tool with **→ POINTER SCAN**.

> **Tip:** The ready-made trainers for [Unreal](howto:items-unreal) and [Unity](howto:items-unity) games do not need a pointer scan.

## AOB / UPDATE: patches after a game update
An **AOB** is a byte pattern with wildcards, for example `48 8B 05 ?? ?? ?? ??`. It describes a piece of code that stays the same even when its address moves.

After a game update, the **update scan** looks for each patch's pattern again and works out its new offset. Patches the scan finds in more than one place are marked as ambiguous and not changed.

A patch that has a pattern saved (see **AOB / UPDATE**) survives most updates.
