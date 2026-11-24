# ReaperPy 6.5.0

**Smarter finding for Unity and Unreal, a much clearer debugger and disassembler, game names and covers from the console, and a patch library that sets itself up.**

Nothing changes for existing projects.

### Added (smart finding, `smart_find.py`)
- **Names in other languages, abbreviations and typos:** `Vida`, `Salud`, `Gesundheit`, `Municion`, `Dinero`, `Kinsen`, `m_Hp`, `curMp`, `Gld`, `Immotal` and similar are found (Spanish, German, French, Italian, Portuguese, romaji, pinyin). Matching is fuzzy (plural, one typo, start of a long word) but never for short words, so `Magnitude` or `Armature` are not mistaken for ammo or armor.
- **The class can carry the meaning:** `Wallet.Pay(int)`, `Geldbeutel.amount` or `Purse.Take(int)` are found although the method or field name alone says nothing. Verbs (spend / add / check / damage) are read in several languages; `GetDamage` and `CanTakeDamage` are not mistaken for "takes damage".
- **Give methods by shape (Unity ITEMS):** a give method with an unhelpful name (`Obtener`, `Zorp` ...) is found when a *remove* method with the same parameters sits next to it. With real evidence (sibling or an "add" verb) it appears from filter level *normal*; anything weaker only at *off*, flagged as a fallback exactly like before - test it with **TEST 1 ITEM**.
- **Item lists in other languages:** enum names like `Objeto` or `Gegenstand` and item rows like `espada_hierro` / `Schwert_Eisen` count as item lists (also by content).
- **Unity VALUES and CHEAT MENU** offer the extra methods and fields. They are never pre-ticked, rows say *how* they were recognised ("recognised: ...") and enemy-looking classes are warned about. Only safe actions are patched automatically (spending / damage made empty, "can I afford" checks return yes, "is dead" returns no); *add* and *set* methods are never patched by this.
- **Unreal:** members and functions use the same fuzzy / multilingual matching (scored a little lower, with the reason shown), e.g. `GastarMunicion`, `m_Hp`, `Healt`.
- **Obfuscated games:** when most names are unreadable the VALUES tab now says so and what helps (search a visible value in memory, change it, search again) instead of only "nothing found".
- New tests: `tests/test_smart_find.py` (32 tests, including the integration into VALUES, CHEAT MENU, ITEMS and Unreal).

### Added (Debugger and disassembler)
- **CONTEXT view in the debugger tab:** under the hit list, the instructions around a hit with the writer (green) and RIP (yellow) marked. For a watchpoint hit ReaperPy finds the writer itself (RIP stands *behind* the access). Double-click opens the Disassembler tab with that line selected; right-click copies or starts a PRESET.
- **Register diff:** registers that changed since the last stop of the same thread are highlighted and show the old value (new **PREVIOUS** column).
- **Writer column:** the hit list has a new **INSTRUCTION** column naming the writer (watchpoints) or the instruction at RIP, e.g. `0x100a  mov dword ptr [rdi + 0x1c], eax`. Hit contexts are cached, so clicking an older hit does not read memory again.
- **Disassembler tab restyled** like the context view: marker column, LENGTH column, zebra rows, calls and jumps tinted, padding dimmed, compact addresses. Opening it from the debugger marks the writer and RIP and centers the list; the Assistant's "open writer in Disassembler" now shows a few instructions *before* the writer instead of putting it at the very top.
- **Beginner help in the debugger:** a step-by-step guide and a plain-language explanation of every hit.
- **Code cave hook overview:** the cave text shows exactly how the hook works (which bytes are overwritten, what stays, where it returns).

### Added (Game name and cover from the console)
- On connect, ReaperPy now fetches the running game's **exact title** (`param.json`) and its **cover** (`pic0.png`, fallback `icon0.png`) over FTP (ports 2121 / 1337, anonymous) and shows both in the header, above the patch list. Cached in `covers/`, so it only asks the console once per game.
- Name priority: `param.json` > name reported by the console > library title > title ID. Process names like `eboot.bin` are never used as a name.
- Optional `config.json` keys: `ftp_ports`, `meta_dirs` (extra folders, `{id}` = title ID), `ftp_timeout`, `game_meta` (`false` = off). The log lists every FTP path that was tried when something is missing.

### Added (Library from the console, version check)
- **LIBRARY → FETCH FROM CONSOLE** lists all installed games over FTP and caches their cover (`icon0.png` for the cards, `pic0.png` for the header) and exact title. Games without patches show up too; the exact title replaces the folder name.
- On connect, the game version reported by the console is compared with the versions found in the patch file / folder names. If none match, the log shows a **version warning** (silent when no version is found in the names).

### Added (Patch library)
- **A patch folder per game:** the library creates a folder `Game name - TITLEID` for every game it knows by ID. Games without patches get it as their project folder, so a click on the card opens it.
- **Blank start with automatic code detection:** ReaperPy starts with an empty patch list and loads the codes of the running game by title ID when you connect.
- **Patch import by game ID with drag and drop:** drop patch files onto the library window to import them (needs the optional package `tkinterdnd2`; without it the PATCH button works as before).
- **Editable cheat values** on the patch cards (settings gear).
- **Version banner** for the running game, next to the version check above.

### Changed
- **Code cave hooks start at 5 bytes** (`jmp rel32`) instead of 8, so short instructions can be hooked; longer ones are still copied whole, and the rest is padded with NOPs.
- Breakpoint, watchpoint and hit tables sit a few rows lower to make room for the context view.
- Enemy / player class detection also knows *Feind, Gegner, Enemigo, Ennemi, Spieler, Jugador* and similar words.
- Test fixtures in `tests/test_unity_items_find.py` used the Japanese words *kusuri / buki / tate / yoroi* as examples of "unknown names"; those are known now, so the fixtures use invented words.

### Fixed
- **Breakpoints showed up as `int3` (0xCC) in disassembly.** The Disassembler tab, the debugger context view and the Assistant's writer search read memory raw, so a set breakpoint hid the real instruction and every address behind it was misaligned. PRESET and CAVE-HOOK even copied the `0xCC` as the "original instruction" when a breakpoint sat on the hooked address. The original bytes are now put back everywhere.
- **Wrong target after a base-register change:** when the writing instruction changes its own base register (e.g. `mov rax, [rax+8]`), the hit target now follows the watchpoint address.
- **Debugger crash in the auto-continue error path:** a `NameError` (exception variable used after the `except` block) hid the real error.

### Fixed (test suite / CI)
- Windows CI: `FiveByteEngine` tests need an executable `mmap` and are now skipped where it does not exist (like all other tests that use the fake console).
- `test_default_min_len_is_unchanged` expected the old 8-byte hook; the default is 5 bytes, the test now says so.
- The fake console in `tests/cave_world.py` gained `set_rw`, so restoring a cave in tests no longer logs `no attribute 'set_rw'`.
- Removed a stale translation entry (`': Schreiben fehlgeschlagen'`) that made `test_every_key_is_a_text_in_the_code` fail; a test card stub gained `lbl_vars`; an unused variable in `gui.py` was removed (ruff).
- New tests: `tests/test_smart_find.py` (32), `tests/test_hit_context.py`, `tests/test_read_code.py`, `tests/test_disasm_view.py`.
