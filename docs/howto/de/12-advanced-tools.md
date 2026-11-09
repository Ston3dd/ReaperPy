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

## Sitzungen
Die Knöpfe **SESSION LADEN…** und **SESSION SPEICHERN…** oben im Werkzeug-Fenster speichern deine Cheat-Liste und Pointer-Ergebnisse, damit du später weitermachen kannst.
