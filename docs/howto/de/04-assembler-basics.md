# Assembler für Einsteiger

Assembler ist die Sprache des Prozessors. Du musst sie nicht lernen, um ReaperPy zu benutzen, aber ein paar Ideen machen den **DISASSEMBLER**, den **KONVERTER** und Code-Caves viel verständlicher. Die PS5 nutzt x86-64; ReaperPy schreibt es in Intel-Syntax.

## Hilfen für den Einstieg
- Im **DISASSEMBLER** steht in der Spalte **ERKLÄRUNG** zu jeder Zeile in einfachen Worten, was sie tut. Markierst du eine Zeile, steht die ganze Erklärung unter der Tabelle.
- Mit **PRESET…** änderst du eine Zeile, ohne Assembler zu schreiben: zum Beispiel "Befehl abschalten" oder "Wert immer auf eine Zahl setzen". ReaperPy baut den Code selbst.
- Bei **ÄNDERN…** zeigt eine Vorschau, wie groß dein Code ist und ob er passt. Fehler erklärt ReaperPy auf Deutsch, mit der Zeile und einem Beispiel.

## Was die Werkzeuge tun
- Der **DISASSEMBLER** macht aus den Bytes im Speicher lesbare Befehle.
- Der **KONVERTER** macht aus Assembler-Text Bytes und zurück.
- **CHEATS BEARBEITEN** schreibt die Bytes ins Spiel.

## Register: die Kästchen des Prozessors
Ein Register ist ein kleines Kästchen, in dem eine Zahl liegt. Du siehst `rax`, `rbx`, `rcx`, `rdx`, `rsi`, `rdi`, `r8` bis `r15` (64 Bit). `eax` ist die untere Hälfte von `rax` (32 Bit). `xmm0` bis `xmm15` halten Dezimalzahlen (Float). `rip` ist die Stelle, an der der Prozessor gerade arbeitet.

Eckige Klammern heißen *der Speicher bei*: `[rbx+0x120]` ist der Speicher an der Adresse in `rbx` plus 0x120. Die Spielfigur ist oft ein Speicherblock, und `0x120` könnte der Platz ihres Lebens sein.

## Die Befehle, die du am häufigsten triffst
- `mov a, b` - kopiere b nach a. `mov [rbx+0x120], eax` schreibt eax in den Speicher - oft die Zeile, die dein Leben setzt.
- `add a, b` und `sub a, b` - addieren oder abziehen. `sub [rbx+0x120], ecx` lässt den Wert sinken.
- `inc a` und `dec a` - 1 addieren oder abziehen.
- `cmp a, b` - zwei Werte vergleichen. Es setzt nur Flags, die der nächste Sprung ansieht.
- `je`, `jne`, `jl`, `jg` ... - springe, wenn gleich, ungleich, kleiner, größer.
- `jmp` - immer springen. `call` - eine Funktion ausführen und zurückkehren. `ret` - eine Funktion verlassen.
- `push` und `pop` - ein Register auf den Stapel legen und zurückholen.
- `lea a, [b+c]` - eine Adresse berechnen, ohne Speicher zu lesen.
- `movss`, `addss`, `subss` - dasselbe für Dezimalzahlen (Float).
- `nop` - nichts tun (ein Byte, `90`).

## Eine „Wer schreibt"-Zeile lesen
Angenommen, **WER SCHREIBT?** hat für dein Leben diese Zeile gefunden:

```
sub [rbx+0x120], eax
```

Das heißt: *ziehe die Zahl in eax vom Speicher bei rbx+0x120 ab* - Schaden. Ersetzt du sie durch NOP-Bytes, sinkt das Leben nicht mehr (aber das Leben von Gegnern vielleicht auch nicht, wenn sie denselben Code nutzen - siehe Hinweis unten). Lautet die Zeile `mov [rbx+0x120], eax`, dann *setzt* das Spiel den Wert, und eine Code-Cave kann ihn auf etwas Beliebiges setzen.

## Zwei Wege, es zu ändern
1. **NOP**: ersetze den Befehl durch `90`-Bytes, so viele, wie der Befehl hatte. Der Befehl tut dann nichts. Die Byte-Anzahl muss gleich bleiben, sonst geht der nächste Befehl kaputt.
2. **Code-Cave**: das Spiel springt in deinen Code, der in freiem Platz liegt. Am Ende springt `jmp OriginReturn` dorthin zurück, wo das Spiel weitermacht.

## Eine erste Cave, Zeile für Zeile
Ziel: Das Leben kann nie unter 1 sinken. Die Originalzeile war `sub [rbx+0x120], eax`.

```
sub [rbx+0x120], eax          ; Originalzeile behalten
cmp dword ptr [rbx+0x120], 1  ; Leben mit 1 vergleichen
jge fine                      ; 1 oder mehr: nichts zu tun
mov dword ptr [rbx+0x120], 1  ; kleiner als 1: auf 1 zurücksetzen
fine:
jmp OriginReturn              ; zurück ins Spiel
```

Ist das Leben ein *Float*, musst du einen Float setzen. 1000.0 ist `0x447A0000`: `mov dword ptr [rbx+0x120], 0x447A0000`.

> **Hinweis:** Ein Patch gilt für **jedes** Objekt, das diesen Code benutzt - auch für Gegner. Werden auch die Gegner unbesiegbar, hilft der Tab **SPIELER / GEGNER**: Er findet selbst heraus, woran man den Spieler erkennt. Siehe [Spieler oder Gegner?](howto:player-or-enemy). Oder nimm die fertigen Werkzeuge aus [Werte, Live-Werte und das Cheat-Menü](howto:values-and-live).

## Regeln, die das Spiel am Leben halten
- Ändere nur Register, die das Spiel an dieser Stelle nicht mehr braucht. Im Zweifel sichere sie: `push rax` am Anfang, `pop rax` vor `jmp OriginReturn`.
- `cmp` und `sub` ändern die *Flags*. Lass den Originalbefehl in der Cave, außer du willst ihn loswerden.
- Fange mit einem NOP oder einer winzigen Cave an. Teste. Dann baue aus.
- **JOURNAL / UNDO** nimmt jede Änderung zurück.
