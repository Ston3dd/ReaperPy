# First steps

ReaperPy changes numbers and code in a game while it runs on your jailbroken PS5 - health, ammo, money, items and more. For the simple tools you need no programming knowledge. This page takes you from zero to a connected tool.

## What you need
- A jailbroken PS5 with the **ps5debug-NG** payload loaded.
- Your PC in the same network as the console. Allow ReaperPy through the firewall for port **755**: the console connects back to your PC to report breakpoint hits.
- The game running with a save loaded (not the main menu).

> **Tip:** Use ReaperPy for single-player games on your own console.

## 1. Connect
1. Start the game on the console and load your save.
2. Load the payload on the console.
3. Type the console's IP address into **PS5 IP** in the main window.
4. Press **CONNECT**. When it works, the status line shows the process number (`connected - PID ...`) and the console usually shows a short notification.
5. ReaperPy recognises the game by its title ID and loads matching codes from your library automatically.

## 2. Open the tools
Press **TOOLS** in the main window. The first tab, **START**, tells you in plain words whether you are connected and which codes are loaded, and it has big buttons for the beginner steps. The **? HELP** button at the top opens the how-to article that belongs to the tab you are looking at. You can also open all guides at any time with the **HOW TO** button in the main window, even without a connection.

## 3. Which tool for which job
- **A number I can see** (health, ammo, money): [Find a value](howto:find-value).
- **All items of an Unreal Engine game**: [Items in Unreal games](howto:items-unreal).
- **All items of a Unity game**: [Items in Unity games](howto:items-unity).
- **Health, gold, experience, ammo as ready-made patches**, or live values: [Values, live values and the cheat menu](howto:values-and-live).
- **Turn a found address into a cheat**: [Edit cheats](howto:edit-cheats) and [Assembler for beginners](howto:assembler-basics).
- **Use the cheats in GoldHEN / etaHEN**: [Export](howto:export).
- **Something stopped working**: [Troubleshooting](howto:troubleshooting).

## 4. Stay safe
- **Save the game first.** A change only lives in the game's memory; restarting the game brings the original back.
- Every write the tools make is recorded. **ADVANCED → JOURNAL / UNDO** undoes single changes or everything.
- If the game closes after a change, open **ADVANCED → KERNEL LOG**. It shows crashes and errors and often tells you why.
- Change one thing at a time. If something goes wrong you know what caused it.
- Words you do not know are explained in the [glossary](howto:glossary).
