# Items in Unreal-Engine-Spielen

Der Tab **UNREAL → ITEMS** gibt dir alle Items eines Unreal-Engine-Spiels als fertigen Trainer in drei Schritten. Du musst keine Tabellen, FNames oder Item-IDs kennen.

## Bevor du anfängst
- ReaperPy braucht die Ausgabe des **ps4-unreal-dumper** für dein Spiel (ein Ordner mit `offsets.json`, `SDK/SDK_HEADERS`, optional `dump.bin`, `dump.json`, `GObjects.txt`).
- Verbinde im Hauptfenster, starte das Spiel und lade einen Spielstand.

## Schritt 1 - Spiel
Drücke **SPIEL-ORDNER WÄHLEN …** und wähle den Ordner des Dumpers. ReaperPy merkt ihn sich.

## Schritt 2 - Items finden
Drücke **ITEMS FINDEN**. ReaperPy bewertet jede Tabelle und Funktion des Spiels, wählt die Item-Tabelle(n) und eine Geben-Funktion, für die es einen Trainer bauen kann, liest alle Items aus dem laufenden Spiel und sortiert sie in Kategorien. Hake Items an oder ab (Kästchen anklicken, Doppelklick oder Leertaste), suche nach Namen, filtere nach Kategorie. **ALLE AN** und **ALLE AUS** wirken auf die sichtbaren Zeilen.

- **Filter** *streng / normal / aus* - wie streng Tabellen und Funktionen gefiltert werden. Wird nichts gefunden, sagt das Protokoll, wo der Filter etwas verworfen hat.
- Nur Fortgeschrittene brauchen *Auswahl selbst ändern*: Damit wählst du die Item-Liste und die Geben-Funktion selbst.

## Keine Item-Liste gefunden?
ReaperPy erkennt die Item-Tabelle zuerst am **Namen** (Item, Weapon, Loot ...). Benutzt das Spiel andere Namen, schaut es danach auf den **Inhalt** jeder Tabelle: wie viele Einträge, ob die Namen Gruppen wie `Sword_Iron`, `Potion_Small` bilden und ob sie nach Items klingen. Eine so gefundene Liste ist mit einem Warnzeichen und den ersten Namen markiert, damit du sofort siehst, ob wirklich Items drin sind.

Wird nichts gefunden, erscheint unter den Knöpfen eine Zeile:
- **Tippe den Namen eines Items, das du im Spiel siehst** (zum Beispiel *Potion*), und drücke **IN ALLEN LISTEN SUCHEN**. ReaperPy sucht den Namen in jeder Tabelle und nimmt die, in der er steht, als Item-Liste. Bei übersetzten Spielen kann der Name auf dem Bildschirm vom internen abweichen - probiere dann den englischen Namen oder nur einen Teil davon.
- **ALLE LISTEN PRÜFEN** bewertet jede Tabelle nach Inhalt und bietet die besten unter *Mögliche Item-Listen* an, mit Größe und den ersten Namen zum Wiedererkennen.

Findet der strenge Filter keine Geben-Funktion, lockert ReaperPy ihn einmal selbst und sagt es dazu. Prüfe so eine Funktion mit **1 ITEM TESTEN**.

## Schritt 3 - Trainer speichern
Drücke **TRAINER SPEICHERN**, gib die Menge pro Item ein und speichere. Die Menge wird auf das eigene Limit des Spiels gekürzt, wenn die Tabelle eines hat. Das Ergebnis ist ein normales ReaperPy-Projekt:
1. Wähle den Ordner als Projekt.
2. Schalte `00 BASIS` einmal ein.
3. Klicke die Einträge.

Das Speichern liest nur das Spiel. Erst wenn du BASIS einschaltest, ändert sich etwas.

> **Tipp:** Große Listen werden auf mehrere Projekte verteilt (`Items 1`, `Items 2` ...). Aktiviere immer nur **eines**.

## Testen oder sofort geben
- **1 ITEM TESTEN** - gibt ein Item und fragt, ob es angekommen ist. Die Antwort wird für dieses Spiel gemerkt.
- **JETZT GEBEN** - gibt alle angehakten Items sofort, ohne Trainer. Speichere im Spiel, um sie zu behalten.
- **ANGEHAKTE TESTEN** - prüft den Trainer vor dem Speichern: Image-Basis, Geben-Funktion, Platz für die Cave und den Namen jedes Items.
- **INVENTAR AUF MAX** - wird nur gezeigt, wenn das Spiel eine Funktion zum Erweitern des Inventars hat. Klicke selbst darauf, wenn du mehr Platz brauchst; JETZT GEBEN und TRAINER SPEICHERN schalten keine Plätze frei.

> **Achtung:** Bleibe beim Testen im Spiel (nicht im Hauptmenü) und speichere vorher.

## Nur das erste Item kommt an?
Das Spiel lehnt ein Item ohne freien Platz ab. Nutze **INVENTAR AUF MAX**, gib weniger Items oder Kategorien auf einmal, oder wähle unter *Auswahl selbst ändern* die Lager-Funktion.

## Nach einem Neustart des Spiels
Trainer, die mit ReaperPy 6.0.1 oder neuer gespeichert wurden, finden ihre Objekte von selbst wieder. Ein mit einer älteren Version gespeicherter Trainer hat eine feste Adresse und funktioniert nur, bis das Spiel beendet wird: Lade einen Spielstand und drücke **ITEMS FINDEN** und **TRAINER SPEICHERN** erneut.

## Einen fremden Trainer prüfen
**TRAINER PRÜFEN / ANPASSEN …** vergleicht einen Trainer-Ordner mit deinem laufenden Spiel („passt zur Spielversion" oder „für eine ANDERE Version gebaut - nicht aktivieren"). Unterscheiden sich nur die Item-Nummern, bietet es an, den Trainer an dein Spiel anzupassen.

## Image-Basis
ReaperPy vergleicht die Image-Basis mit der Speicherkarte der Konsole. Weichen sie ab, bietet es **BASIS ÜBERNEHMEN** an. Es rät nie eine Zahl.

Hat dein Spiel keine passende Geben-Funktion, lies [Werte, Live-Werte und das Cheat-Menü](howto:values-and-live). Weitere Hilfe: [Fehlersuche](howto:troubleshooting).
