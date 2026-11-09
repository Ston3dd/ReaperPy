# Items in Unity-Spielen

Der Tab **UNITY → ITEMS** funktioniert wie der für Unreal: alle Items eines Unity-Spiels (IL2CPP) als Trainer in drei Schritten.

> **Hinweis:** Dieser Teil ist neu. Das Finden der Items klappt allein mit dem Dump, aber das Geben von Items ist noch an wenigen echten Spielen ausprobiert. Lässt sich eine Methode nicht nutzen, steht in der Liste der Grund.

## Bevor du anfängst
- Lass **Il2CppDumper** (den Fork von TetzkatLipHoka, der auch mit Konsolen-Speicherabbildern klappt) über dein Spiel laufen. Dein Ordner braucht `dump.cs` und `script.json`. Verschachtelte Ordner sind in Ordnung - die Dateien werden gesucht.
- Nimm einen Dump von **genau der Spielversion, die du spielst**.
- Das Finden der Items braucht keine Verbindung zur Konsole. Das Speichern schon.

## Schritt 1 - Spiel
Drücke **SPIEL-ORDNER WÄHLEN …** und wähle den Il2CppDumper-Ordner. Bei einem großen Spiel dauert das Laden etwa zehn Sekunden.

## Schritt 2 - Items finden
Drücke **ITEMS FINDEN**. ReaperPy wählt die Item-Liste (das Enum mit den Item-IDs), die Methode zum Geben von Items (`AddItem`, `GiveItem` ... mit einer Item-ID und optional einer Menge) und einen Einstiegspunkt von selbst. Hake die gewünschten Items an.

## Schritt 3 - Trainer speichern
Drücke **TRAINER SPEICHERN**. Das Ergebnis ist ein normales ReaperPy-Projekt, genau wie bei [Items in Unreal-Spielen](howto:items-unreal): Schalte `00 BASIS` einmal ein und klicke dann die Einträge. Kategorien, mehrere Projekte und **TRAINER PRÜFEN …** funktionieren genauso.

> **Tipp:** Methoden, die ein Item-Objekt oder einen Text statt einer ID brauchen, stehen mit dem Grund in der Liste und werden übersprungen.

## Weitere Unity-Seiten
Für einzelne Werte und Methoden-Patches siehe [Werte, Live-Werte und das Cheat-Menü](howto:values-and-live).

## Gut zu wissen
- Objektadressen ändern sich bei jedem Spielstart. Klassen, Offsets und RVAs bleiben für dieselbe Spielversion gültig.
- Stelle die Image-Basis von ReaperPy auf die im Tab gezeigte Basis des IL2CPP-Moduls, wenn du exportierte Patches in **CHEATS BEARBEITEN** lädst.
