# Export formats and console notifications

Cheat files for GoldHEN / etaHEN and the messages ReaperPy shows on the PS5.

[← Back to the README](../../README.md)

---

## Export formats

| Format | Notes |
|---|---|
| `.json` | GoldHEN cheat format (name, hook offset, cave bytes, on/off). |
| `.shn` | SHN XML (Trainer / Cheat / Cheatline). On/off only - buttons are exported as switches. |
| `.mc4` | SHN + AES-256-CBC + base64, file name `TITLEID_VERSION.ext`. `& < > "` in names are replaced because some readers resolve XML entities blindly. |

**TITLE ID / VERSION FROM GAME** reads both values from the running game. Import (`.json`, `.shn`, `.mc4` -> patches) skips mods in
sections other than 0 instead of importing them half.

## Notifications on the console

ReaperPy uses the payload's notification command to show short messages on the PS5 screen, so you see what happened
without alt-tabbing out of the game:

| Event | Message (example) |
|---|---|
| Connected / reconnected | `ReaperPy connected (PID 1234)` |
| Cheat switched on / off | `ON: Infinite HP` / `OFF: Infinite HP` |
| Cheat switched while the debugger is attached | `ON: Infinite HP (debugger attached)` |
| ALL ON / ALL OFF / restore after a reconnect | one summary: `ON: 12 cheats (A, B, C +9)` instead of 12 messages |
| Debugger attached / detached / connection lost | `Debugger attached (PID 1234)`, `Debugger detached`, `Debugger: connection lost` |
| Breakpoint / watchpoint hit (off by default) | `Debugger: breakpoint at 0x401000` (at most one message every 5 s) |

Messages follow the language switch (DE / EN). They are sent in the background and never block the app; if sending
fails, they pause until the next connect. Switch them off completely with
`"ps5_notifications": false`, switch on hit messages with `"ps5_notify_hits": true` (see [Configuration](../../README.md#configuration)).
