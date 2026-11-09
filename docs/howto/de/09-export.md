# Export für GoldHEN und etaHEN

Du kannst deine Cheats aus ReaperPy herausnehmen und im Cheat-Menü von GoldHEN oder etaHEN benutzen.

## Formate
- `.json` - das GoldHEN-Cheat-Format.
- `.shn` - SHN-XML. Nur An / Aus: Knöpfe werden als Schalter exportiert.
- `.mc4` - SHN, verschlüsselt, mit dem Dateinamen `TITELID_VERSION.mc4`.

## Exportieren
1. Öffne dein Projekt im Hauptfenster und schalte ein, was du exportieren willst.
2. Drücke **GOLDHEN-JSON** und wähle das Format.
3. Nutze **TITEL-ID/VERSION VOM SPIEL**, damit beide Werte aus dem laufenden Spiel kommen.

Titel-ID und Version müssen zum Spiel passen. Der Export kennt nur Mods in Section 0 der GoldHEN-JSON; andere Sections werden übersprungen, nicht halb importiert. Du kannst solche Dateien auch **importieren**.

## Auf die Konsole bringen
Kopiere die Datei auf die Konsole:
- GoldHEN: `/user/data/GoldHEN/cheats/json/`
- etaHEN: `/data/etaHEN/cheats/json/`

Starte dann das Spiel und öffne das Cheat-Menü.

## Item-Trainer
Ein Item-Trainer wird als mehrere Schalter exportiert. Schalte sie in dieser Reihenfolge ein:
1. `00a BASIS 1 - Cave`
2. `00b BASIS 2 - Haken`
3. dann die Items

Gut zu wissen:
- Die Dateien passen nur zu **dieser Spielversion**. Exportiere nach einem Spiel-Update neu.
- Die Item-Nummern (FNames) stammen aus der Spielsitzung. Ändern sie sich zwischen Spielstarts, funktioniert der Trainer nur bis zum nächsten Neustart: Starte das Spiel einmal neu und teste ihn erneut.
- BASIS und der eigene Haken des Tools (**ITEMS → JETZT GEBEN**) schließen sich aus: Schalte BASIS aus, bevor du JETZT GEBEN benutzt.

> **Achtung:** Exportierte Cave-Trainer sind auf einem Prozessor getestet, nicht an jedem Spiel. Speichere vorher und probiere einen Schalter nach dem anderen.

Taucht ein Cheat nicht im Menü auf, lies [Fehlersuche](howto:troubleshooting).
