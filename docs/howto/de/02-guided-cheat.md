# Cheat in vier Schritten

Der **ASSISTENT** führt dich von einer Zahl im Spiel bis zum fertigen Cheat. Du musst keinen Assembler können: ReaperPy sucht den Wert, findet den Befehl, der ihn ändert, und baut daraus ein Preset.

## Schritt für Schritt
1. **Wert finden:** Lies im Spiel eine Zahl ab, zum Beispiel dein Leben, und trage sie bei **ZAHL** ein. Siehst du nur eine Leiste, wähle **Zahl unbekannt**. Klicke **SUCHEN**.
2. **Eingrenzen:** Ändere den Wert im Spiel, zum Beispiel ein Leben verlieren. Trage die neue Zahl bei **NEUE ZAHL** ein und klicke **EINGRENZEN**. Bei unbekannter Zahl klickst du stattdessen **GEFALLEN**, **GESTIEGEN** oder **GLEICH GEBLIEBEN**. Wiederhole das, bis höchstens 30 Treffer übrig sind. Die Liste zeigt dann die Adressen mit ihrem aktuellen Wert, und **WERTE AKTUALISIEREN** liest sie neu.
3. **Wer ändert den Wert?** Markiere den Treffer, dessen Wert im Spiel mitgeht, und klicke **BEOBACHTEN**. Beim ersten Mal wird der Debugger an das Spiel gehängt. Löse jetzt im Spiel die Änderung aus, zum Beispiel Schaden nehmen. Das Spiel läuft weiter. In der Tabelle erscheint der Befehl, der den Wert geschrieben hat, mit einer Erklärung in normalen Worten und einer Anzahl.
4. **Cheat erstellen:** Markiere den Befehl und klicke **PRESET…**. Wähle zum Beispiel "Befehl abschalten", damit der Wert nicht mehr sinkt. Der Cheat landet im Cheat-Editor. Dort testest du mit **TEST AN** und speicherst.

Mit **STOPP** beendest du die Beobachtung. **PRESET…** beendet sie von selbst.

## Wenn mehrere Befehle in der Tabelle stehen
Der mit der höchsten **ANZAHL** ist meistens der gesuchte. Willst du wissen, was ein Befehl tut, lies die Spalte **WAS PASSIERT**. Ein Befehl, der den Wert erhöht, wenn du Schaden nimmst, ist nicht der richtige.

## Wenn auch Gegner betroffen sind
Ein Preset gilt für **jedes** Objekt, das diesen Code benutzt. Teilen sich Spieler und Gegner den Code, werden auch Gegner unbesiegbar. Nimm dann die fertigen Werkzeuge aus [Werte, Live-Werte und das Cheat-Menü](howto:values-and-live).

## Wenn nichts passiert
- Keine Treffer: Bei Kommazahlen die Zahl mit Punkt eintragen. Manche Spiele speichern 100 als 100.0.
- Zu viele Treffer: Ändere den Wert im Spiel noch einmal und grenze erneut ein.
- Kein Befehl in der Tabelle: Prüfe, ob die Adresse zum Wert gehört, der sich im Spiel wirklich geändert hat. Wähle sonst einen anderen Treffer.

> **Achtung:** Der Debugger hält das Spiel kurz an, wenn er den Treffer auswertet. Beende die Beobachtung mit **STOPP**, bevor du weiterspielst.

Mehr zu den einzelnen Schritten: [Wert suchen](howto:find-value), [Debugger](howto:debugger), [Assembler ohne Vorkenntnisse](howto:assembler-basics).
