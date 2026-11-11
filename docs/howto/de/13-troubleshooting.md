# Fehlersuche

## Ich kann nicht verbinden
- Drücke **WERKZEUGE → START → VERBINDUNG PRÜFEN**: Es sagt dir in einfachen Worten, ob die IP, die Konsole, der Payload oder das Spiel das Problem ist.
- Ist der Payload geladen und das Spiel gestartet? Prüfe die IP bei **PS5 IP**.
- PC und Konsole müssen im selben Netzwerk sein. Erlaube ReaperPy in der Firewall (Port **755** für den Debugger).
- Hake **AUTO-RECONNECT** im Hauptfenster an, wenn die Verbindung ab und zu abbricht.

## Der Scan findet nichts
Siehe das Ende von [Einen Wert finden](howto:find-value): probiere *Float*, stelle den Speicherfilter auf *ALLE* und prüfe, ob sich der Wert zwischen zwei Scans wirklich geändert hat.

## Das Spiel schließt sich, wenn ich etwas einschalte
1. Öffne **FORTGESCHRITTEN → KERNEL-LOG** und lies die hervorgehobenen Zeilen.
2. Nimm die Änderung mit **FORTGESCHRITTEN → JOURNAL / UNDO** zurück.
3. Probiere eine kleinere Änderung: ein NOP statt einer Cave, einen Eintrag statt vieler.
4. Prüfe, ob die Image-Basis stimmt: **BASIS ÜBERNEHMEN** im ITEMS-Tab setzt sie aus der Speicherkarte der Konsole.

## Items kommen nicht an
- Bleibe im Spiel, nicht im Hauptmenü, und lade einen Spielstand.
- Nur das erste Item kommt an: Der Rucksack ist voll. Nutze **INVENTAR AUF MAX** oder gib weniger Items - siehe [Items in Unreal-Spielen](howto:items-unreal).
- Der Trainer ging gestern und heute nicht: Ein mit altem ReaperPy gespeicherter Trainer hat eine feste Objektadresse. Drücke **ITEMS FINDEN** und **TRAINER SPEICHERN** erneut (ab Version 6.0.1 finden Trainer das Objekt selbst).
- Das Spiel wurde aktualisiert: Nimm einen Dump der neuen Version, finde und speichere neu.

## Knöpfe sind abgegraut
Knöpfe, die am laufenden Spiel arbeiten (zum Beispiel **LESEN**, **SCHREIBEN**, **TEST AN**), sind abgegraut, solange das Hauptfenster nicht mit der Konsole verbunden ist. Fahre mit der Maus darüber: Der Tooltip sagt, warum. Klicke im Hauptfenster auf **VERBINDEN** - die Knöpfe werden von selbst frei und die Werkzeuge verbinden nach, du musst sie nicht neu öffnen. Knöpfe für Dateien und Exporte sind nie abgegraut.

## Was bedeuten das kleine „?“ und der Fragezeichen-Mauszeiger?
Fahre mit der Maus über einen Begriff wie OFFSET, SIGNATUR, OriginReturn oder NOP: Nach einem Moment erscheint eine kurze Erklärung. Ein „?“ neben einem Feld tut dasselbe.

## Der Cheat erscheint nicht in GoldHEN / etaHEN
- Liegt die Datei im richtigen Ordner? Siehe [Export](howto:export).
- Passen Titel-ID und Version genau zum Spiel? Nutze **TITEL-ID/VERSION VOM SPIEL**.

## Unity: Das Modul wird nicht gefunden
Lade zuerst einen Spielstand, verbinde und drücke **MODUL ERKENNEN**. Klappt es nicht, zeigt das Protokoll, was gefunden wurde; du kannst die Basisadresse auch von Hand eintippen.

## ReaperPy zeigt Deutsch und Englisch gemischt
Schalte mit **DE / EN** im Hauptfenster um. Texte, die das Programm während des Laufs erzeugt, werden sofort übersetzt; siehst du trotzdem einen, melde ihn bitte.

## Wo sind die Protokolle?
Im Programmordner: `logs/reaperpy.log`. Die Knöpfe **LOG-ORDNER ÖFFNEN** und **AUF UPDATES PRÜFEN** liegen im Tab START.
