# Glossar

**AOB** - Array of Bytes: ein Byte-Muster mit Platzhaltern (`??`), das ein Stück Code findet, auch wenn seine Adresse wandert. Siehe [Pointer und Spiel-Updates](howto:pointers).

**Assembler** - die Sprache des Prozessors. Siehe [Assembler für Einsteiger](howto:assembler-basics).

**BASIS (00 BASIS)** - der erste Schalter eines ReaperPy-Trainers. Er schreibt Cave und Haken einmal; die Einträge nutzen sie dann.

**Breakpoint** - hält das Spiel an, wenn der Prozessor eine Adresse erreicht. Siehe [Der Debugger](howto:debugger).

**Cave (Code-Cave)** - ein kleines Stück eigener Code in freiem Platz im Spiel. Das Spiel springt hinein und zurück.

**Disassembler** - macht aus Bytes lesbare Befehle.

**eboot.bin** - das Hauptprogramm des Spiels. Sein Anfang im Speicher ist die *Image-Basis*.

**Float** - eine Dezimalzahl. Viele Spiele speichern Leben als Float.

**FName** - die Zahl, die ein Unreal-Engine-Spiel für einen Namen benutzt. Item-Trainer sagen damit, welches Item gemeint ist.

**Freeze (Einfrieren)** - immer wieder denselben Wert schreiben, damit er sich nicht ändern kann.

**GObjects** - die Liste aller Objekte eines Unreal-Engine-Spiels.

**Haken (Hook)** - eine Stelle, an der der Code des Spiels auf deinen Code umgeleitet wird.

**Il2CppDumper** - ein Werkzeug, das die Klassen und Methoden eines Unity-Spiels ausliest. ReaperPy liest seine Ausgabe.

**Image-Basis** - die Startadresse des Spielprogramms im Speicher. Offsets werden von ihr aus gezählt.

**Instanz** - ein echtes Objekt einer Klasse im laufenden Spiel (deine Figur, ein Gegner).

**Int32** - eine ganze Zahl in 4 Bytes.

**NOP** - ein Befehl, der nichts tut (`90`).

**Offset** - ein Abstand von einem Startpunkt, zum Beispiel von der Image-Basis.

**Payload** - das Programm auf der Konsole, mit dem ReaperPy spricht (ps5debug-NG).

**PID** - die Prozessnummer des Spiels.

**Pointer** - eine im Speicher abgelegte Adresse, die auf eine andere Adresse zeigt.

**Register** - eines der kleinen Kästchen des Prozessors (`rax`, `rbx` ...).

**RIP** - das Register, das die Stelle hält, an der der Prozessor gerade arbeitet.

**SDK-Dump** - die Liste der Klassen und Member eines Unreal-Engine-Spiels, die der Dumper schreibt.

**Titel-ID** - der Code eines Spiels auf der PS5, zum Beispiel `PPSA01234`.

**Watchpoint** - hält das Spiel an, wenn etwas eine Adresse liest oder schreibt.
