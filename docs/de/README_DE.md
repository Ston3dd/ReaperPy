<div align="center">

<img src="../../assets/reaperpy.png" alt="ReaperPy" width="120">

# ReaperPy

**Cheats, Trainer und Debugging für die PS5 – in einer übersichtlichen Desktop-App.**

Patches und Code Caves · Speicher-Scanner · Pointer-Scan · Debugger · Item-Trainer für Unreal und Unity · Export für GoldHEN / etaHEN

[English](../../README.md) · **Deutsch**

</div>

ReaperPy ist ein Werkzeugkasten auf Basis des [ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)-Payloads. Wert finden, daraus
einen Patch oder eine Code Cave machen, sich in drei Klicks Items geben und alles als Cheat-Datei für GoldHEN / etaHEN exportieren.

> **Nur an deiner eigenen Konsole, mit deinen eigenen Spielen und im Einzelspieler- bzw. Offline-Modus verwenden.**
> Schreiben in ein laufendes Spiel kann es abstürzen lassen oder den Spielstand beschädigen – vorher sichern. Keine Gewähr (siehe [LICENSE](../../LICENSE)).
> ReaperPy enthält keine Spieldaten, keine Schlüssel für geschützte Inhalte und keinen Weg an Online-Schutzmaßnahmen vorbei.

## Das kann ReaperPy

| | |
|---|---|
| 🎯 **Cheat-Suche** | Scans wie in CheatEngine direkt auf der Konsole (genau, Float, zwischen, verändert, unbekannter Startwert), Adressliste mit Einfrieren und „Wer schreibt hier?“ |
| 🧩 **Patches und Code Caves** | Byte-Patch / NOP oder x86-64-Assembler (Keystone) in freiem Platz des Spiel-Images, gespeichert als `.reapproj`-Projekt |
| 🎒 **Items als Trainer** | Unreal- **und** Unity-Spiele: alle Items finden, Give-Funktion testen, **sofort geben** oder als fertigen Trainer speichern – drei Klicks |
| 🐞 **Debugger** | Breakpoints, Hardware-Watchpoints, Register, Stack, Threads, Einzelschritt (into / over / out) |
| 🔎 **Speicher und Disassembler** | Hex-Ansicht mit Werte-Inspektor, Snapshots, x86-64-Disassembler, AOB-Signaturen, die Spiel-Updates überstehen |
| 🧭 **Pointer-Scan** | Pointer-Pfade zu einem Wert, auch als schneller Scan Ebene für Ebene auf der Konsole |
| 📤 **Export / Import** | `.json`, `.shn` und `.mc4` für GoldHEN / etaHEN |
| 🛟 **Sicherheitsnetz** | Journal / Rückgängig für jede Änderung der Werkzeuge |
| 🐍 **Skripte** | Ein `ps5`-Objekt für Python-Skripte: Pointer, AOB-Scans, Schreiben mit Undo, Funktionsaufrufe |
| 🎓 **Einsteigerfreundlich** | START-Tab, Assembler in einfachen Worten, **ANLEITUNGEN** direkt im Programm, Deutsch und Englisch |

## Installation

**Voraussetzungen**

- Eine gejailbreakte PS5 mit dem **[ps5debug-NG](https://github.com/Pharaoh2k/ps5debug-NG)**-Payload (Befehlsport `744`, Kernel-Log `3232`, Debugger-Rückkanal `755`).
- Ein PC im selben Netzwerk. Die Firewall muss **Port 755** für die App erlauben (die Konsole verbindet sich *zurück*, um Breakpoint-Treffer zu melden).
- Python **3.10+** mit `tkinter` – oder die fertige Windows-Version.

**Aus dem Quellcode**

```bash
pip install -r requirements.txt     # keystone-engine, capstone, pillow
python gui.py                       # Windows: start.bat doppelklicken (prüft Python, tkinter und Pakete)
```

Unter Linux vorher `python3-tk` installieren.

**Fertige Windows-Version:** `ReaperPy_v<Version>_win64.zip` von der GitHub-Seite **Releases** laden, mit der `.sha256`-Datei
prüfen, entpacken und `ReaperPy.exe` starten. Ab 5.9.1 aktualisiert sich das Programm selbst.

## Schnellstart

1. **Verbinden.** Spiel starten, Payload laden, die Konsolen-IP im Hauptfenster eintragen und **CONNECT** drücken. ReaperPy erkennt
   das Spiel (Title-ID) und lädt passende Codes aus deiner Bibliothek.
2. **Wert finden.** **TOOLS → FIND VALUE**: Zahl aus dem Spiel eintippen, **FIRST SCAN**, im Spiel ändern, neue Zahl eintippen,
   **NEXT SCAN** – wiederholen, bis nur noch wenige Adressen übrig sind. Einfrieren oder setzen, oder mit „Wer schreibt hier?“
   die Anweisung finden und in **EDIT CHEATS** zum Patch machen.
3. **Items als Trainer.** Unreal: **UNREAL → ITEMS**. Unity: **UNITY → ITEMS**. Spielordner wählen, **FIND ITEMS**, dann
   **SAVE TRAINER** – oder Items anhaken und **GIVE NOW** drücken.
4. **Debuggen.** **TOOLS → ADVANCED → DEBUGGER**: PID, **ATTACH**, Breakpoint setzen, Spiel laufen lassen, untersuchen, **STEP**.

Neu dabei? Der Knopf **ANLEITUNGEN** im Hauptfenster (oder **? HILFE** im Werkzeug-Fenster) erklärt jedes Werkzeug Schritt für Schritt.

## Dokumentation

| Thema | Wo |
|---|---|
| Anleitungen für Einsteiger (auch im Programm) | [docs/howto/de](../howto/de) |
| Alle Tabs, Cheat-Suche, Debugger, Cheat-Menü (Englisch) | [docs/en/TOOLS.md](../en/TOOLS.md) |
| Unreal-Engine-Spiele (Englisch) | [docs/en/UNREAL.md](../en/UNREAL.md) |
| Unity-Spiele (Englisch) | [docs/en/UNITY.md](../en/UNITY.md) |
| Export und Benachrichtigungen (Englisch) | [docs/en/EXPORT.md](../en/EXPORT.md) |
| Skripte, Tests, Releases (Englisch) | [docs/en/SCRIPTING.md](../en/SCRIPTING.md) · [docs/en/DEVELOPMENT.md](../en/DEVELOPMENT.md) |
| Änderungen | [CHANGELOG.md](../../CHANGELOG.md) |
| Frühere deutsche Hinweise (Stand 5.7) | [docs/history/README_5.7_de.md](../history/README_5.7_de.md) |

## Einstellungen

Die Einstellungen stehen in `reaperpy_config.json` neben dem Programm (Vorlage: `reaperpy_config.example.json`).

| Einstellung | Wirkung |
|---|---|
| `REAPERPY_HOME=<Ordner>` (Umgebungsvariable) | Konfiguration, Profile und Logs an anderer Stelle ablegen, z. B. auf einem USB-Stick |
| `"auto_codes": false` | Automatische Code-Erkennung per Title-ID ausschalten |
| `"ps5_notifications": false` | Keine Meldungen auf dem PS5-Bildschirm |
| `"ps5_notify_hits": true` | Auch bei jedem Breakpoint-Treffer eine Meldung |
| `"auto_update_check": false` | Beim Start nicht nach Updates suchen |
| `"splash": false` oder `REAPERPY_NO_SPLASH=1` | Kein Startbild |

Das Protokoll liegt in `logs/reaperpy.log` (rotierend) und enthält auch unbehandelte Fehler der Oberfläche – bitte bei Fehlermeldungen anhängen.

## Lizenz und Dank

ReaperPy steht unter der **[MIT-Lizenz](../../LICENSE)**. Dank an **ps5debug-NG** (OSR, Pharaoh2k u. a.), **ps4-unreal-dumper** und
**Il2CppDumper** (TetzkatLipHoka) sowie **PS5Debug-studio** (alfizari). Die vollständige Liste und die Lizenzen der verwendeten
Pakete stehen in der [README](../../README.md#credits-and-licenses) und in [NOTICE](../../NOTICE).
