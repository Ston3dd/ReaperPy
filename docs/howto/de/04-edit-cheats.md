# Cheats bearbeiten

Der Tab **CHEATS BEARBEITEN** schreibt einen Patch: eine Änderung am Code des Spiels, die du ein- und ausschalten kannst. Du kommst von **WER SCHREIBT?** aus [Einen Wert finden](howto:find-value) hierher, oder du startest mit einer Adresse, die du schon kennst.

## Einfach und erweitert
CHEATS BEARBEITEN startet in der **einfachen** Ansicht: **Name**, **Offset**, **Originalbytes** und **neue Bytes** - mehr braucht ein normaler Patch nicht, und die Felder füllen sich meist von selbst, wenn du vom Tab **ASSISTENT**, von **WER SCHREIBT?** oder vom Disassembler kommst. Probiere ihn mit **TEST AN**, dann **SPEICHERN**.

Wenn du verbunden speicherst, erzeugt ReaperPy die **Signatur** für dich. Mit der Signatur findet der Cheat nach einem Spiel-Update seinen Platz wieder. Klappt es nicht, steht das im Protokoll, und der Cheat wird trotzdem gespeichert.

Hake **ERWEITERTE OPTIONEN** an, um Patch-Art, **OriginReturn**, Cave-Code und Signatur zu sehen und selbst zu bestimmen. Die Wahl wird gemerkt. Ein Cheat mit Code-Cave (zum Beispiel aus einem Preset) funktioniert auch in der einfachen Ansicht; ein Hinweis sagt dir, wie viele Zeilen die Cave hat.

## Woraus ein Patch besteht
- **Name** und **Autor** - was du in der Patch-Liste siehst.
- **Offset** - der Abstand vom Anfang des Spielprogramms (der *Image-Basis*), damit der Cheat nach einem Neustart weiter funktioniert.
- **Originalbytes** und **neue Bytes** - was jetzt da ist und was dort stehen soll.

## Zwei Arten von Patch
- **Einfacher Patch / NOP** - ersetzt die Originalbytes durch neue. Ein NOP ist ein Befehl, der nichts tut; so verhinderst du am schnellsten, dass sich ein Wert ändert, zum Beispiel dass er sinkt.
- **Code-Cave** - ein eigenes kleines Stück Assembler-Code in einem separaten Feld. Das Spiel springt hinein, es erledigt seine Arbeit, und `jmp OriginReturn` geht zurück. Nimm eine Cave, wenn ein NOP nicht reicht, zum Beispiel um einen Wert zu setzen.

Du kannst Assembler-Text oder rohe Hex-Bytes eingeben. [Assembler für Einsteiger](howto:assembler-basics) erklärt die Befehle und hat ein durchgerechnetes Beispiel.

## Vom gefundenen Wert zum Cheat
1. Füge in **WERT SUCHEN** die Adresse hinzu und drücke **WER SCHREIBT?**. Der Debugger wartet, bis das Spiel den Wert schreibt.
2. ReaperPy zeigt den Befehl, der es getan hat. Die Stelle, an der das Spiel angehalten hat, liegt *hinter* dem schreibenden Befehl - der davor ist der Schreiber.
3. Schicke ihn an **CHEATS BEARBEITEN**. Wähle NOP oder Code-Cave.
4. Speichere (die Signatur ergänzt ReaperPy selbst). Das Projekt liegt als `.reapproj`-Datei vor und erscheint als Karte im Hauptfenster.
5. Schalte die Karte ein und teste sie im Spiel.

> **Achtung:** Ein falscher Patch kann das Spiel schließen. Speichere vorher im Spiel. **FORTGESCHRITTEN → JOURNAL / UNDO** nimmt die Änderung zurück, und **FORTGESCHRITTEN → KERNEL-LOG** zeigt, was passiert ist.

## Weitergeben
Exportiere deine Patches für GoldHEN / etaHEN - siehe [Export](howto:export).
