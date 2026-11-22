# Fortgeschrittene Werkzeuge

Alles hier liegt unter **FORTGESCHRITTEN**. Für die einfachen Werkzeuge brauchst du es nicht.

## SPEICHER
Eine Hex-Ansicht jeder Adresse mit einem *Werte-Inspektor* (Byte anklicken, um es als Zahl, Float und Text zu sehen), Snapshot und Vergleich, Speichern einer Region in eine Datei und Laden einer Datei in den Speicher.

## DISASSEMBLER
Zeigt den Code des Spiels als lesbare Befehle ab jeder Adresse. Blättere vor, folge Sprüngen und Aufrufen per Doppelklick. Siehe [Assembler für Einsteiger](howto:assembler-basics).

## KONVERTER
Macht aus Assembler-Text (x86-64, Intel-Syntax) Hex-Bytes und zurück.

## FUNKTION AUFRUFEN
Ruft eine Funktion des Spiels mit bis zu sechs Argumenten auf: `base+0x1234`, Zahlen, Text in Anführungszeichen oder Puffer im Spiel. Es zeigt das Ergebnis (RAX) als Hex, Zahl mit Vorzeichen, Float und Text. Es wiederholt sich nie von selbst.

> **Achtung:** Eine Funktion mit falschen Argumenten aufzurufen kann das Spiel abstürzen lassen.

## PYTHON-SKRIPT
Ein Skript-Editor mit dem Objekt `ps5`:

```
base = ps5.module()                               # Anfang des Spielprogramms
hp = ps5.pointer(base + 0x4A1C00, 0x20, 0x1C4)    # einem Pointer-Pfad folgen
if hp:
    ps5.write_u32(hp, 999, undo=True)             # schreiben, rückgängig machbar
```

Außerdem gibt es: `ps5.aob()`, `ps5.nop()`, `ps5.call()`, `ps5.foreground()`, `ps5.write_many()`, `ps5.log_calls()`, `ps5.alloc()`.

## JOURNAL / UNDO
Jeder Schreibzugriff der Werkzeuge wird mit den alten Bytes aufgezeichnet. Mache einzelne Einträge oder alles mit **ALLES ZURUECK** rückgängig.

## KERNEL-LOG
Zeigt die Meldungen der Konsole live an. **Fehler und Abstürze stehen rot**, Warnungen gelb. Das hilft dir, wenn das Spiel nach einem Patch plötzlich schließt: Schau nach, was kurz davor im Log stand.
1. **START** drücken (verbindet sich mit der Konsole, ändert sich zu **STOP**).
2. Spiel weiterspielen, bis das Problem kommt.
3. Mit dem **Filter** nach einem Wort suchen, mit **SPEICHERN…** das Log als Datei sichern (praktisch für Hilfe-Anfragen), mit **LEEREN** aufräumen.

> **Tipp:** Wenn nichts erscheint, läuft auf der Konsole der Log-Dienst nicht oder du bist nicht verbunden. Das stört nichts anderes.

## FUNKTIONS-LOGGER
Zeigt, **wann eine Funktion des Spiels aufgerufen wird** und mit welchen Werten. Gut, um herauszufinden, welche Funktion z. B. beim Kauf oder bei Schaden läuft.
1. Die **Adresse** am Anfang der Funktion eintragen (aus dem DISASSEMBLER).
2. **START** drücken. Im Spiel die Aktion auslösen. Jeder Aufruf erscheint als Zeile.
3. **STOP** drücken. Das stellt das Spiel wieder genau so her, wie es war.

> **Achtung:** Der Logger ersetzt die ersten Bytes der Funktion durch einen Sprung (mindestens 5 Byte). Liegt mitten darin ein Sprungziel, kann das Spiel abstürzen, darum fragt ReaperPy vorher nach. **STOP** nicht vergessen, bevor du das Fenster schließt.

## AOB / UPDATE
Nach einem **Spiel-Update** stimmen die Adressen deiner Cheats nicht mehr. Mit einem **AOB** (Byte-Muster) findet ReaperPy die Stelle wieder.
1. Cheats mit **LISTE LADEN** holen, dann **SIGNATUREN ERZEUGEN (fehlende)**. Das machst du am besten *vor* dem Update, solange die Cheats noch passen.
2. Nach dem Update das neue Spiel starten, **UPDATE-SCAN** drücken. Die Spalte *GEFUNDEN* zeigt, welche Cheats ihre Stelle wiederhaben, *NEUER OFFSET* die neue Adresse.
3. **OFFSETS ÜBERNEHMEN** trägt die neuen Adressen ein.

Oben kannst du außerdem von Hand ein **MUSTER** suchen (**SERVER-SCAN** auf der Konsole, **LOKAL (ALLE)** in geladenen Dateien) oder aus einer Adresse ein Muster bauen (**ERZEUGEN**).

> **Tipp:** Findet der Scan eine Stelle nicht, hat sich der Code im Spiel verändert. Dann den Cheat neu bauen.

## Sitzungen
Die Knöpfe **SESSION LADEN…** und **SESSION SPEICHERN…** oben im Werkzeug-Fenster speichern deine Cheat-Liste und Pointer-Ergebnisse, damit du später weitermachen kannst.
