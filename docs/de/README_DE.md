# ReaperPy 5.7

PS5-Werkzeugkasten für **ps5debug-NG**: Patches/Caves (ReapProj), Cheat-Searcher, Pointer-Scan,
Debugger, Disassembler, Python-Skripte und Export in die Cheat-Menü-Formate.
Läuft auf Windows/Linux mit Python 3.10+ (`pip install -r requirements.txt`, Start: `start.bat` bzw. `python gui.py`).

---

## Credits / Danksagung

**ps5debug-NG** von **OSR (OpenSourcereR)**, weiterentwickelt von **Pharaoh2k** (mit EchoStretch und Sonic-Iso) –
<https://github.com/Pharaoh2k/ps5debug-NG> (GPL-3.0). Das ist das Payload, für das ReaperPy gebaut ist. ReaperPy ist nur ein
Client für das veröffentlichte Protokoll (`PROTOCOL.md`, v1.3.2) und enthält keinen Code des Payloads; das Payload ist ein
eigenes Programm mit eigener Lizenz. ps5debug-NG selbst ist inspiriert von `ps5debug` (Ctn, SiSTRo) und `ps4debug` (jogolden)
und nutzt das ps5-payload-sdk von John Törnblom.

**PS5Debug-studio** von **alfizari** – <https://github.com/alfizari/PS5Debug-studio> (Apache-2.0).
ReaperPy hat eine eigene Architektur und eigenen Code; von dort wurden nur ein paar Kniffe übernommen (kleine Ideen und
Format-/Protokolldetails, kein Code), z. B. der Aufbau der **.shn- und .mc4-Dateien**. Lizenztext: `licenses/Apache-2.0.txt`,
Herkunftsvermerke: `NOTICE`.

**ps4-unreal-dumper** von **TetzkatLipHoka** (MIT, <https://github.com/TetzkatLipHoka/ps4-unreal-dumper>) erzeugt die Dumps, die UE-AUTO einliest (`dump.bin`, `dump.json`, `SDK/offsets.json`, `SDK/GObjects.txt`, `SDK_HEADERS`). Der UFunction-Aufruf über ProcessEvent folgt dem Verfahren seines `uecall`; Code wurde nicht übernommen. `uediff --xref` (Stoned) macht Ähnliches wie die Instruktionssuche hier.

---

## Neu in 5.7: UE-EINFACH (für Einsteiger) und UE-LIVE (Profi)

### ★ UE-EINFACH – ohne Vorwissen
Der Tab öffnet sich beim Start der Werkzeuge als erster. Vier Schritte:

1. **SPIEL-ORDNER WÄHLEN** (der Ordner mit `offsets.json` und `SDK_HEADERS`; wird gemerkt).
2. **Was?** Leben, Munition, Geld, Ausdauer … auswählen.
3. **Die Zahl eintippen, die du gerade im Spiel siehst**, und **FINDEN** drücken. Das Tool liest selbst alle passenden
   Werte im Spiel und zeigt nur die, die diese Zahl haben. Beim ersten Mal liest es das Spiel ein (ca. 1–2 Minuten,
   Fortschritt steht oben), danach geht es schnell. Zu viele Treffer? Im Spiel die Zahl ändern (z. B. Schaden nehmen),
   neue Zahl eintippen, **EINGRENZEN**.
4. **Neuer Wert** eintippen, **SETZEN** oder **DAUERHAFT HALTEN**. Ohne Auswahl in der Liste wirkt es auf alle Treffer.
   Ändert sich im Spiel nichts, einen anderen Treffer anklicken.

Alle Meldungen sind in einfachem Deutsch und sagen, was als Nächstes zu tun ist.

**Fehler aus Version 5.7 (erste Fassung) behoben:** Beim Suchen von Instanzen brach `'Q' format requires 0 <= number <=
18446744073709551615` ab, weil tote Spielobjekte kaputte Klassenzeiger haben. `ue_live.py` prüft Zeiger jetzt, cacht die
Eltern-Klassen und sucht viele Klassen in einem Durchlauf (auch UE-AUTO profitiert).

### Turbo-Scan schneller machen (5.7)
**Ursache langsamer "Unbekannter Startwert"-Scans** (laut `PROTOCOL.md` von ps5debug-NG): Der Snapshot-Speicher darf
standardmäßig nur **512 MiB im RAM** liegen, der Rest wird auf `/data` (verschlüsselt, ~35-240 MB/s) ausgelagert. Ein
Float-Scan mit ~370 Mio. Treffern braucht 12 Byte je Treffer (≈ 4,4 GB) - gemessen: 88 s bei 109 MB/s statt ~11 s.

Neue Zeile im Scanner-Tab:
- **SNAPSHOT-RAM** (`CMD_PROC_TURBOSCAN_CONFIG`, 0xBDAACC15): wie viel des Snapshots im PS5-RAM bleibt
  ("512 MB (Standard)" setzt das Payload zurück). **Die PS5 unterstützt nur bis zu 2048 MB. Ab 3072 MB meldet das Payload,
  dass die PS5 nicht genug Speicher hat** - deshalb bietet die Auswahl nur 512 / 1024 / 2048 MB an (Standard 2048 MB). **Das belegt PS5-Speicher, während
  das Spiel läuft**: bei Instabilität/Spielabsturz kleiner stellen. Reicht der Speicher nicht, fällt das Payload laut Doku
  sicher auf die Datei zurück.
- **AUSLAGERN NACH**: wohin der Rest geht - `/data` (intern, langsam), `/mnt/ext1` (M.2-Erweiterung, ~240 MB/s) oder
  `/mnt/usb0` (USB, ~550 MB/s), nur falls vorhanden.
- Nach jedem Snapshot-Scan loggt das Tool die Snapshot-Größe und, falls nötig, welchen RAM-Wert du einstellen solltest.
Die Einstellung gilt im Payload global bis zur nächsten Änderung (jeder Snapshot-Scan sendet sie neu).

Weitere Punkte: Lückenlos aneinandergrenzende Regionen werden zu einem Segment zusammengefasst (Lücken werden nie
überbrückt; 20 894 Regionen -> 2 014 Segmente, 137 s -> 88 s). `Parallel (schneller)` wirkt laut Doku **nur** bei einem
exakten Erst-Scan mit eingeschaltetem Aliasing (kein Snapshot) und wird nur dann angefordert. Die Tempo-Filter und
`kleine Segmente auslassen` bringen bei den gemessenen Spielen kaum etwas. Das Log nennt beim Verbinden Payload-Name und
Version, unterscheidet "Payload kann …" von "ANGEFORDERT: …", und der Fortschritts-Stream wird in Blöcken gelesen.
Alle Scan-Konstanten des Clients wurden gegen `common/include/protocol.h` des Payloads (ps5debug-NG) geprüft.

### UE-LIVE (Profi)

Tab **⚡ UE-LIVE** – gedacht für „anklicken, Live-Wert sehen, ändern“. Kein Dump nötig, nur der Spiel-Ordner mit
`offsets.json` und `SDK_HEADERS` (und optional `dump.bin.engine.json`).

1. **SPIEL-ORDNER…** wählen (wird gemerkt und beim nächsten Start automatisch geladen).
2. Links einen Wert **anklicken** (z. B. `UHealthComponent.Health`). Suche und Kategorie filtern die Liste; mit
   *alle Member* werden nicht nur Cheat-Kandidaten, sondern jeder Zahlen-/Bool-Member angeboten.
3. Rechts erscheinen sofort alle **Live-Instanzen** mit dem aktuellen Wert, der sich ~2,5× pro Sekunde selbst
   aktualisiert. Instanzen mit Wert ≠ 0 stehen oben; *nur Wert ≠ 0* und das Filterfeld grenzen weiter ein.
4. **Ändern:** Doppelklick auf eine Zeile, oder Wert eintippen + `SETZEN` (Enter). Schnellknöpfe: `×2 ×10 +10 +100 +1000 0 99999`
   bzw. `AN / AUS` bei Schaltern. Eingabe `+100` oder `*2` rechnet vom aktuellen Wert der jeweiligen Instanz aus.
   `= MAX` übernimmt den passenden Max-Wert der Instanz (Health ← MaxHealth). Ziel: *Auswahl* oder *alle sichtbaren*.
5. **❄ EINFRIEREN** hält den Wert (ein Bulk-Write pro Tick), `AUFTAUEN` löst ihn. Setzt man einen Wert neu, während er
   eingefroren ist, wird der neue Wert gehalten.

Bool-Schalter mit Bitfeld (`BitIndex`) werden per Lesen-Ändern-Schreiben gesetzt – die anderen Bits im Byte bleiben
unberührt. `FFixedPoint64` wird als Anzeigewert eingegeben (Palworld: ×1000 wird intern gerechnet).
`→ SCHREIBER FINDEN` und `→ SPEICHER` springen direkt in Debugger bzw. Speicher-Tab.

Dateien: `ue_quick.py` (Logik, ohne Oberfläche testbar), `tools_uelive_gui.py` (Tab), `tests/test_ue_quick.py`,
`tests/ue_world.py` (synthetische UE-Welt). Der Objekt-Index wird einmal je Spielstart gebaut; nach Levelwechsel
`↻ INSTANZEN NEU`.

**Grenzen:** Wie bei UE-AUTO an synthetischem UE-Speicher und echtem Tk (Xvfb) geprüft, **nicht an einer echten Konsole
oder einem echten Spiel**. Mehrere Instanzen derselben Klasse sind normal (Gegner, NPCs, Default-Objekte): die eigene
Spieler-Instanz erkennt man am Wert bzw. daran, dass sich die Zahl im Spiel mitändert. Nur Einzelspieler/eigene Konsole.

---

## Neu in 5.0

| Bereich | Was | Datei |
|---|---|---|
| Export | **.json / .shn / .mc4** aus deinen ReapPatches (Format-Auswahl im Export-Dialog), Prüfung vorab (Titel-ID, Version, on/off-Länge) | `cheatfmt.py`, `export_goldhen.py` |
| Export | Button **TITEL-ID/VERSION VOM SPIEL** – liest das laufende Spiel von der Konsole | `ps5_more.py` |
| Import | Cheat-Dateien **.json/.shn/.mc4** → ReapPatches (Mods in anderer Section als 0 werden übersprungen, nie halb übernommen) | `gh_import.py` |
| Tab | **FUNKTION AUFRUFEN** – beliebige Spiel-Funktion mit bis zu 6 Argumenten, Text-Argumente (`"abc"`), Puffer im Spiel (`@puffer+8`), RAX als hex/signed/float/String | `caller.py`, `tools_extra_gui.py` |
| Tab | **FUNKTIONS-LOGGER** – schreibt jeden Aufruf (rdi…r9, Rückkehradresse, Stack-Args, xmm0/1, optional Thread) in einen Ringpuffer; Gruppierung nach Aufrufer, CSV-Export, Spiel wird nicht angehalten | `logger.py` |
| Tab | **JOURNAL / UNDO** – jeder Schreibzugriff der Werkzeuge wird mit den alten Bytes gemerkt, einzeln oder komplett rückgängig | `journal.py` |
| Pointer | **⚡ SCHNELL-SCAN (Konsole)** – Pfade ohne Karte (braucht Payload mit `0xBDAACC30`) | `ptrscan_server.py` |
| Searcher | Freeze über **einen** Bulk-Write pro Tick statt einem Paket je Wert | `ps5_more.py` |
| Debugger | **STACK-SCAN** – Aufrufkette auch ohne Frame-Pointer | `unwind.py` |
| Speicher | Werte-**Inspektor** (Klick aufs Byte), **SNAPSHOT/VERGLEICH**, Region **als Datei sichern / Datei → Speicher**, Hexdump kopieren | `memtools.py` |
| Skripte | `ps5.call()`, `ps5.foreground()`, `ps5.write_many()`, `ps5.log_calls()` | `script_api.py` |

### Kurzanleitung

**Export:** Patches laden → Spiel läuft, verbunden → `GOLDHEN-JSON` → Format wählen → *TITEL-ID/VERSION VOM SPIEL* → EXPORTIEREN.
`.shn`/`.mc4` kennen nur An/Aus: Buttons werden als Schalter exportiert (Warnung im Log). Bei `.mc4` werden `& < > "` in Namen durch `+ ( ) '` ersetzt, weil ältere mc4-Leser XML-Entities blind auflösen.

**Funktion aufrufen:** `FUNKTION` = `base+0x1234`, Argumente z. B. `0x10`, `-1`, `base+0x20`, `@buf`, `"Hallo"`. Der Aufruf hält kurz einen Spiel-Thread an und wird **nie automatisch wiederholt**. Nicht benutzen, solange der Debugger das Spiel angehalten hat. Float-Argumente gehen nicht (nur Ganzzahl-Register).

**Logger:** Adresse = Funktionsanfang. Die ersten ≥ 8 Byte werden durch `jmp` in eine Cave ersetzt, **STOP** (oder Fenster schließen) stellt sie zurück. Liegt mitten in diesen Bytes ein Sprungziel, kann das Spiel abstürzen – deshalb die Rückfrage. Der Ring hat 256/1024/4096 Einträge; „VERLOREN“ heißt: Ring zu klein.

**Journal:** zeichnet alles auf, was über die Tools-Verbindung schreibt (nicht: Freeze-Ticks, Schreibzugriffe > 64 KB).

---

## Neu in 5.3: UE-AUTO (Unreal-Engine-Spiele)

Tab **UE-AUTO** (und `ue_auto.py` für die Kommandozeile). Entwickelt anhand echter Dumps (Palworld/PS5: `offsets.json`, `dump.json`, `GObjects.txt`, `SDK_HEADERS`).

**Ablauf**
1. **SPIEL-ORDNER** wählen – `offsets.json`, `dump.json`, `dump.bin`, `GObjects.txt` und `SDK/SDK_HEADERS` werden automatisch gefunden (`*_parameters.hpp` werden übersprungen). Ohne `dump.bin` gibt es Kandidaten und Funktionsliste, aber keine Instruktionssuche.
2. **Kandidaten** aus den Headern: Leben, Ausdauer, Munition, Währung, Erfahrung, Item-Menge … und **Cheat-Schalter** (`bIsEnableMuteki`, `bIsInfinitySP`, `IsInfinityMagazine`, `NoDamage` …). `FFixedPoint64` (Palworld-HP) wird erkannt (Wert = Anzeige × 1000). Daten-Tabellen, UI-/Blueprint-/Engine-Hilfsklassen und `LifeTime`-Treffer werden abgewertet.
3. **INSTRUKTIONEN → SUCHEN**: Byte-Suche nach dem Displacement im Code-Bereich des Dumps (kein Voll-Disassemble), Ranking nach schreibt / Ko-Zugriff auf andere Member derselben Klasse / `SUB` davor / Mehrdeutigkeit.
4. **NOP-PATCH** und **CAVE „kann nicht sinken“** als `.reapproj` mit eindeutiger AOB-Signatur aus dem Dump.
5. **FUNKTIONEN**: Die Header enthalten die nativen Adressen (`native 0x…`). Angezeigt werden cheat-typische Funktionen (AddHP, ConsumeItem, SpendMoney …). **IMPL. AUFLÖSEN** findet hinter dem Exec-Thunk die C++-Implementierung (Aufrufziele, die nicht in vielen Thunks vorkommen). **FUNKTIONS-PATCH** lässt sie sofort zurückkehren (`ret`, `false`, `true`, `1`, `0.0`). Geteilte Stubs (≥ 25 Funktionen, gleiche Adresse = Blueprint/Delegates) sind nicht patchbar. Ob die Header-Adressen RVAs oder virtuelle Adressen sind, wird am Dump automatisch erkannt (Funktionsgrenzen), per Auswahl überschreibbar.
6. **UFUNKTION AUFRUFEN (live)**: Funktion über ProcessEvent mit Parametern per Namen (`TimeDilation=0.3 WorldContextObject=0x…`). Parameter-Layouts kommen aus den `*_parameters.hpp` (Eingabe/Ausgabe/Rückgabe per CPF-Flags, Rückgabewerte werden angezeigt, `FVector` als Doubles). Objekt = gewählte Instanz, bei statischen Funktionen das Default-Objekt; ProcessEvent aus der vtable (sonst `process_event` aus `offsets.json`). Der Aufruf läuft auf einem Hilfs-Thread: gut für Funktionen, die Werte lesen/schreiben – **Funktionen, die Objekte erzeugen (SpawnActor, Widgets), können abstürzen**. Struct/String/Name-Parameter nur als `hex:AABB…`.
7. **INSTANZEN**: *LIVE FINDEN* liest GObjects/GNames aus dem laufenden Spiel (Layout aus `offsets.json`: `UObject_Class`, `fuobjectitem_size` …), *AUS DUMP* liest dieselben Objekte offline aus dem Dump (nur zum Ansehen). Werte setzen, Speicher öffnen und *SCHREIBER FINDEN* (Watchpoint im Debugger).

`python ue_auto.py --game SPIELORDNER --top 15 --functions 20 --out Patches` und `--func-patch Klasse.Funktion:false` erledigen dasselbe ohne Oberfläche; Bericht in `ue_report.json`.

**Objekt-Erkennung prüfen / Fehlersuche:** `python ue_auto.py --game ORDNER --check-objects` liest GObjects/GNames offline aus der `dump.bin` und zeigt bei Misserfolg pro Versuch, was gelesen wurde (z. B. `objs=… num=… -> Elementzahl unplausibel`). Erkannt werden `offsets.json` mit RVAs **oder** absoluten Adressen sowie beide Name-Pool-Eintragsformate (UE4: Länge in 15 Bit, UE5: 10 Bit). Im Live-Modus werden mehrere Basisadressen probiert (Dump-Basis, Basis aus der Prozess-Speicherkarte, Projektbasis) sowie die absoluten Adressen und das Layout aus `dump.bin.engine.json`.

**Grenzen – bitte lesen**
- `dump.bin` lag bei meinen Beispieldaten nicht bei: **Instruktionssuche, AOB-Erzeugung, Thunk-Auflösung und die RVA/VA-Erkennung sind nur an echtem, selbst assembliertem x86-Code und synthetischen Dumps getestet, nicht an einem echten Spiel-Dump.** Parser, Kandidaten, Funktionsliste und Offsets sind an echten Ausschnitten und am kompletten Palworld-SDK geprüft.
- Instanz-Adressen im Heap ändern sich bei **jedem Spielstart** (so auch laut ps4-unreal-dumper); Klassen, Offsets und SDK bleiben gültig. „AUS DUMP“ zeigt deshalb nur den Zustand zur Dump-Zeit, für Schreibzugriffe LIVE FINDEN benutzen.
- Der UFunction-Aufruf ist gegen synthetische Speicherabbilder und Attrappen getestet, nicht gegen ProcessEvent in einem echten Spiel.
- Offsets sind nicht eindeutig (derselbe Offset steckt in vielen Klassen). Statische Treffer sind Kandidaten; der Watchpoint auf einer Live-Instanz ist die Gegenprobe.
- Patches gelten für **alle Objekte**, die den Code nutzen (auch Gegner derselben Klasse).
- Cave nur bei Stores ≥ 5 Byte aus xmm/Register mit verschiebbaren Folge-Instruktionen, sonst NOP-Patch.
- Live-/Offline-Objektleser: UE 4.23+ / UE5 (FNamePool). Disassembler: `pip install capstone` (Ersatz: `objdump`).
- Der Ordner „Siltent Hill“ in deinem Beispiel enthält nur `SdkHeaders.hpp` (Include-Liste), keine `*_classes.hpp` – dafür gibt es keine Kandidaten, bis die SDK-Header-Dateien dabei sind.

---

## Tests – was geprüft wurde und was nicht

`python -m unittest discover -s tests` (alle grün):

- **AES-256-CBC** gegen FIPS-197-Vektoren und die `cryptography`-Bibliothek
- **SHN / MC4 / JSON**: Round-Trips, Prüfregeln, Export → Datei → Import
- **Logger-Stub**: wird mit `gcc/as/ld` **nativ auf x86-64 ausgeführt** (Register- und Flag-Erhalt, Stack-Argumente, xmm0/1, Ring-Überlauf, halbfertige Einträge) – nur auf Linux mit Toolchain, sonst übersprungen
- **Protokoll** (`foreground`, `write_multi`, `call`, `ptrscan`) gegen einen Fake-Server; Trampolin per `objdump` gegengelesen
- **Pointer-Scan-Logik, Journal, Stack-Unwinder, Caller-Parser** mit simuliertem Speicher
- **GUI-Tabs**: Smoke-Tests mit einem Tk-Ersatz (Logik der Handler, keine Optik)
- **UE-AUTO**: SDK-Parser/Filter mit **echten Palworld-Ausschnitten** (Header, offsets.json, GObjects); Spielordner-Erkennung; Instruktions-Scan gegen echten, mit `as` gebauten x86-64-Code (int3-Padding); die erzeugten Caves werden **nativ ausgeführt** (Float/Int, mitgenommene Folge-Instruktion); die Patch-Dateien werden von ReaperPys eigenem Loader gelesen; GObjects/GNames-Reader gegen ein **synthetisch aufgebautes** UE-Speicherabbild (bildet mein Verständnis der Layouts ab, nicht ein echtes Spiel)

**Nicht geprüft** (ich hatte weder PS5 noch Display): Lauf auf einer echten Konsole mit echtem Payload, das tatsächliche Aussehen/Layout der neuen Tabs in Tk, und der Keystone-Assembler-Pfad des Loggers (Stub ist in GNU-as-Intel-Syntax verifiziert, Keystone nimmt dieselbe Syntax). Bitte zuerst an einem Test-Spiel ausprobieren; Rückmeldungen zu Fehlern gern mit dem Log aus dem Tools-Fenster.

---

## Benachrichtigungen auf der PS5

ReaperPy zeigt kurze Meldungen auf dem PS5-Bildschirm (Notification-Befehl des Payloads): beim **Verbinden**, wenn ein
**Cheat an-/ausgeschaltet** wird (mit Zusatz „Debugger attached“, solange der Debugger hängt), bei **Debugger attached /
detached / Verbindung verloren** und – abgeschaltet als Standard – bei jedem **Breakpoint-Treffer** (höchstens alle 5 s).
Sammelaktionen (ALLE AN/AUS, Wiederherstellen nach Reconnect) senden eine Zusammenfassung statt vieler Meldungen.
In `reaperpy_config.json`: `"ps5_notifications": false` schaltet alles aus, `"ps5_notify_hits": true` aktiviert die Treffer-Meldungen.

## Hinweise

- Nur für die eigene Konsole und eigene Spiele. Kein Einsatz in Online-Modi.
- Alle bisherigen Funktionen (Bibliothek, Session, Projekte, DE/EN) sind unverändert.
- EXE bauen: `build_exe.bat`.
