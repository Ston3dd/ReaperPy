# Spieler oder Gegner?

Viele Spiele benutzen für Spieler **und** Gegner denselben Code, um das Leben zu ändern. Patchst du dort "Leben sinkt nicht", werden alle unsterblich - auch die Gegner, und das Spiel ist kaputt. Dieser Tab findet heraus, woran man den Spieler erkennt, und baut einen Cheat, der nur für den Spieler (oder nur für Gegner) gilt.

## Vorher: die Adresse des Befehls
Du brauchst die Adresse des Befehls, der das Leben ändert, zum Beispiel aus **WER SCHREIBT?** im [Debugger](howto:debugger). Im **DISASSEMBLER** markierst du die Zeile und klickst **SPIELER / GEGNER…** - die Adresse wird übernommen.

## Schritt für Schritt
1. Öffne **FORTGESCHRITTEN → SPIELER / GEGNER** und prüfe die Adresse bei **BEFEHL @**.
2. Klicke **AUFZEICHNEN STARTEN**. ReaperPy hängt eine kleine Code-Cave an den Befehl und schreibt bei jedem Durchlauf auf, was gerade im Prozessor steht. Das Spiel wird nicht angehalten.
3. Klicke **PHASE A: NUR ICH WERDE GETROFFEN** und lass dich von einem Gegner treffen, mindestens 5 Mal. Greife in dieser Zeit nicht selbst an.
4. Klicke **PHASE B: NUR GEGNER WERDEN GETROFFEN** und greife Gegner an, am besten verschiedene. Lass dich nicht treffen.
5. Klicke **AUSWERTEN**. Unten stehen die Merkmale, die in A immer anders sind als in B. Das oberste ist das sicherste.
6. Wähle bei **CHEAT** ein Preset, bei **GILT FUER** "nur den Spieler" oder "nur Gegner" und klicke **→ CHEAT-EDITOR**.
7. Im Cheat-Editor testest du mit **TEST AN** und speicherst. Mit **STOPP** beendest du die Aufzeichnung.

**Tipp:** Je sauberer die Phasen getrennt sind, desto sicherer das Ergebnis. Ein Treffer in der falschen Phase wird als Ausreißer ignoriert, aber viele nicht.

## Woran ReaperPy den Spieler erkennt
- **AUFRUFER** - Spieler und Gegner kommen aus verschiedenen Stellen im Spielcode. Das ist das beste Merkmal, denn es bleibt nach einem Neustart des Spiels gleich.
- **FELD** - im Objekt steht ein fester Wert, zum Beispiel eine Team-Nummer. Das bleibt ebenfalls gleich.
- **OBJEKT** - die Adresse des Spieler-Objekts selbst. Sie gilt nur, bis du das Spiel beendest. Nach jedem Start musst du neu aufzeichnen.

In der Tabelle zeigt die Spalte **NACH NEUSTART GLEICH**, welche Merkmale dauerhaft sind. Die **SICHERHEIT** ist "niedrig", wenn nur wenige Gegner aufgezeichnet wurden.

## Wenn nichts gefunden wird
- Nimm in jeder Phase mehr Treffer auf und achte darauf, dass in Phase A wirklich nur du getroffen wirst.
- Nutze verschiedene Gegner in Phase B.
- Manche Spiele rufen den Code für Spieler und Gegner genau gleich auf. Dann hilft nur ein anderer Befehl: suche mit **WER SCHREIBT?** nach einem Befehl, der nur beim Spieler läuft.

> **Achtung:** Der Cheat prüft Speicher, der bei Gegnern anders aussehen kann. Teste immer zuerst mit **TEST AN**, bevor du speicherst, und halte **JOURNAL / UNDO** bereit.
