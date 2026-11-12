# Einen Wert finden

Der Cheat-Sucher findet, wo ein Spiel eine Zahl wie dein Leben oder dein Geld ablegt. Du suchst die Zahl, änderst sie im Spiel, suchst erneut und wiederholst das, bis nur noch wenige Adressen übrig sind. Dann kannst du den Wert ändern oder einfrieren.

## Schritt für Schritt
1. Öffne den Tab **WERT SUCHEN**.
2. Gib die Zahl, die du im Spiel siehst, bei **Wert** ein (zum Beispiel `100`). Lass den Typ bei einer ganzen 4-Byte-Zahl (Int32) und den Vergleich bei *Genau*.
3. Drücke **ERSTER SCAN**. Die Treffer erscheinen links.
4. Ändere die Zahl im Spiel (Schaden nehmen, Geld ausgeben, einen Schuss abgeben). Gib die neue Zahl ein und drücke **NÄCHSTER SCAN**.
5. Wiederhole Schritt 4, bis nur eine Handvoll Treffer übrig ist.
6. Wähle die Treffer aus und drücke **→ AUSGEWÄHLTE HINZUFÜGEN** (oder doppelklicke einen). Sie wandern in die **Adressliste** unten.
7. Wähle einen Eintrag und drücke **WERT SETZEN**, oder **FREEZE**, um ihn festzuhalten.

> **Tipp:** Zeigt das Spiel 100, der erste Scan findet aber nichts, probiere den Typ *Float*. Viele Spiele speichern Leben als Dezimalzahl.

## Wenn du die Zahl nicht sehen kannst
Lebensbalken und Prozentwerte haben keine Zahl zum Eintippen. Nimm beim ersten Scan den Vergleich *Unbekannter Startwert*. Danach, wenn im Spiel etwas passiert ist, nimmst du *Größer geworden*, *Kleiner geworden*, *Verändert* oder *Unverändert*.

> **Hinweis:** Ein Scan mit unbekanntem Startwert merkt sich eine Kopie des Spielspeichers. Unter **OPTIONEN …** stellst du ein, wie viel davon im RAM der Konsole bleibt und wohin der Rest geht.

## Gerundete Zahlen: Fuzzy-Suche
Spiele zeigen oft eine gerundete Zahl (Leben 75, im Spiel steht 74,6) - eine genaue Suche findet dann nichts. Tippe die Zahl stattdessen mit Toleranz: **75~5** heißt „75 plus/minus 5“, **75~10%** „innerhalb von zehn Prozent“, **~75** oder **ca. 75** nimmt die Standard-Toleranz von 5 %. Im Tab **WERT SUCHEN** wählst du den Vergleich *Fuzzy (± Toleranz)*; das Feld **TOLERANZ** nimmt `5` oder `5%`. Ganze Zahlen bekommen immer mindestens plus/minus 1, `ca. 10` findet also auch 9 und 11. Im **ASSISTENT** hakst du **Ungefähr (Fuzzy)** an oder tippst einfach `75~5`; **EINGRENZEN** versteht dieselben Formen.

Siehst du gar keine Zahl, wähle „Zahl unbekannt“ (bei einer Kommazahl zusätzlich **Kommazahl** anhaken) und grenze nach jeder Änderung im Spiel mit **GEFALLEN**, **GESTIEGEN**, **GLEICH GEBLIEBEN** oder **VERÄNDERT** ein.

## Weniger scannen, schneller finden
Der Bereich **SPEICHERBEREICHE** zeigt, was im Spielspeicher liegt und was gescannt wird. Jede Zeile hat ein Kästchen.
- Standardmäßig sind die System-Bibliotheken ausgeblendet. Für Spielwerte ist das normalerweise sicher.
- **ALLE**, **KEINE**, **NUR EBOOT** und **NUR SPIEL** schalten viele Zeilen auf einmal um.
- Wird ein Wert nicht gefunden, stelle den Filter auf *ALLE* und scanne erneut.

## Nach dem Fund
- **WER SCHREIBT?** findet den Befehl, der den Wert ändert. [Cheats bearbeiten](howto:edit-cheats) macht daraus einen Patch.
- **→ POINTER-SCAN** hilft, wenn sich die Adresse nach einem Neustart ändert - siehe [Pointer](howto:pointers).
- **→ HEX** zeigt die Adresse in der Speicheransicht.

## Wenn nichts gefunden wird
- Die Zahl ist vielleicht anders gespeichert. Probiere *Float* oder eine andere Ganzzahl-Größe.
- Angezeigte Zahlen können gerundet sein. Nimm *Zwischen* oder *Ungefähr (Float)*.
- Prüfe, ob sich der Wert zwischen zwei Scans wirklich geändert hat und das Spiel nicht pausiert war.
- Stelle den Speicherfilter auf *ALLE* und versuche es noch einmal.
