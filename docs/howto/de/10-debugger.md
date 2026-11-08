# Der Debugger

Der Debugger hält das Spiel an einer Stelle deiner Wahl an, damit du hineinsehen kannst. Einsteiger brauchen meist nur eines: **WER SCHREIBT?** - und das richtet ReaperPy für dich ein.

## Attach
In **FORTGESCHRITTEN → DEBUGGER** gibst du die Prozessnummer ein und drückst **ATTACH**. **DETACH** lässt das Spiel wieder los. Solange ein Thread angehalten ist, steht das Spiel.

## Breakpoints und Watchpoints
- Ein **Breakpoint** hält das Spiel an, wenn der Prozessor eine Adresse erreicht. Bis zu 30.
- Ein **Watchpoint** hält es an, wenn etwas eine Adresse liest oder schreibt (4 Plätze; schreiben, lesen/schreiben oder ausführen).

Wenn das Spiel anhält, siehst du Threads, Register (du kannst sie ändern) und den Stack.

## Weitermachen
- **WEITER** - das Spiel laufen lassen.
- **STEP** - ein Befehl.
- **STEP OVER** - einen Funktionsaufruf als Ganzes ausführen.
- **STEP OUT** - laufen, bis die Funktion zurückkehrt.
- **ANHALTEN** - das Spiel sofort anhalten.

> **Hinweis:** Wenn ein Watchpoint auf Schreiben trifft, zeigt `rip` *hinter* den schreibenden Befehl. Der davor ist der Schreiber.

## KERNEL-LOG
**FORTGESCHRITTEN → KERNEL-LOG** zeigt das Protokoll der Konsole mit hervorgehobenen Abstürzen, Seitenfehlern und Fehlern. Öffne es, wenn ein Patch das Spiel schließt.

## FUNKTIONS-LOGGER
**FORTGESCHRITTEN → FUNKTIONS-LOGGER** schreibt jeden Aufruf einer Funktion auf (Register, Rücksprungadresse, Argumente), ohne das Spiel anzuhalten. **STOP** stellt die Originalbytes wieder her.

> **Achtung:** Lass das Spiel nicht lange angehalten. Drücke **WEITER**, wenn du fertig geschaut hast.

Mehr zum Lesen der Befehle steht in [Assembler für Einsteiger](howto:assembler-basics).
