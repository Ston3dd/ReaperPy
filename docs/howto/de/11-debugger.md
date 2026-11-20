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

## Gegner und du teilen sich eine HP-Leiste?
Der Befehl, der die HP schreibt, gilt oft für dich **und** alle Gegner. Ein Breakpoint darauf trifft dann mal dich, mal einen Gegner. Die Tabelle **ZIELE** trennt das: jede Zieladresse ist ein eigenes Objekt (Z1, Z2 …) mit Wert, Vorher-Wert und Änderung.
1. Breakpoint auf den schreibenden Befehl setzen, **AUTO-WEITER** an, kurz im Spiel kämpfen.
2. Bei **MEIN WERT** deine aktuellen HP eintippen und **FINDEN** drücken - das passende Ziel wird markiert. Oder schauen, welches Ziel sich bei dir ändert, und **DAS BIN ICH** drücken.
3. **NUR DIESES ZIEL**: Treffer auf andere Objekte laufen automatisch weiter. **WATCH AUF ZIEL** setzt einen Schreib-Watchpoint genau auf deine Adresse.

## KERNEL-LOG
**FORTGESCHRITTEN → KERNEL-LOG** zeigt das Protokoll der Konsole mit hervorgehobenen Abstürzen, Seitenfehlern und Fehlern. Öffne es, wenn ein Patch das Spiel schließt.

## FUNKTIONS-LOGGER
**FORTGESCHRITTEN → FUNKTIONS-LOGGER** schreibt jeden Aufruf einer Funktion auf (Register, Rücksprungadresse, Argumente), ohne das Spiel anzuhalten. **STOP** stellt die Originalbytes wieder her.

> **Achtung:** Lass das Spiel nicht lange angehalten. Drücke **WEITER**, wenn du fertig geschaut hast.

Mehr zum Lesen der Befehle steht in [Assembler für Einsteiger](howto:assembler-basics).

## Schritt für Schritt (für Einsteiger)
Oben im Debugger steht eine **Hilfezeile**, die dir immer sagt, was als Nächstes dran ist:
1. **ATTACH** drücken (Spiel läuft).
2. **WATCHPOINT** auf die Adresse deines Werts setzen (Typ *schreiben*).
3. Im Spiel etwas tun, das den Wert ändert - das Spiel hält an, es erscheint ein **TREFFER**.
4. Die **grüne Zeile** im KONTEXT ist der Befehl, der deinen Wert ändert. Darunter erklärt ReaperPy in einfachen Worten, was er tut und welche Cheat-Idee passt. Rechtsklick → **IM DISASSEMBLER ÖFFNEN**, Zeile markieren, **CHEAT BAUEN**.

Trifft derselbe Befehl viele Objekte (du *und* Gegner), nimmst du in **ZIELE** die Zeile mit deinem Wert und drückst **DAS BIN ICH**.

## Was beim Cave-Cheat passiert
Beim Anlegen eines Cave-Cheats zeigt ReaperPy oben im Cave-Text das **ganze Bild**:
1. Welche Original-Befehle (und wie viele Bytes) im Spiel überschrieben werden - mindestens **5 Bytes** (ein `jmp rel32`), Rest NOPs.
2. Was die Cave der Reihe nach macht: **dein Code**, dann die **kopierten Original-Befehle**, dann `jmp OriginReturn` zurück ins Spiel.
3. Dass beim Ausschalten die Original-Bytes zurückgeschrieben werden.
