# Pointer und Spiel-Updates

Die Adresse deines Lebens ändert sich meistens bei jedem Spielstart. Zwei Werkzeuge helfen.

## POINTER: den Weg zum Wert finden
Ein Pointer ist eine gespeicherte Adresse, die auf eine andere zeigt. Ein *Pointer-Pfad* beginnt an etwas Festem (dem Spielprogramm) und endet bei deinem Wert, sodass er nach einem Neustart weiter funktioniert.

In **FORTGESCHRITTEN → POINTER**:
1. Wähle die Adresse deines Wertes und drücke **1) KARTE ERSTELLEN**.
2. Drücke **2) PFADE SUCHEN**.
3. Starte das Spiel neu, finde den Wert wieder und drücke **3) PRÜFEN (neues Ziel)**, um nur die Pfade zu behalten, die noch zu ihm führen.
4. Drücke **TOP 10 → CHEAT-LISTE**, um die besten zu nutzen.

**SCHNELL-SCAN (Konsole)** läuft Ebene für Ebene auf der Konsole und ist viel schneller (er braucht einen Payload, der das unterstützt). Aus **WERT SUCHEN** erreichst du das Werkzeug mit **→ POINTER-SCAN**.

> **Tipp:** Die fertigen Trainer für [Unreal](howto:items-unreal)- und [Unity](howto:items-unity)-Spiele brauchen keinen Pointer-Scan.

## AOB / UPDATE: Patches nach einem Spiel-Update
Ein **AOB** ist ein Byte-Muster mit Platzhaltern, zum Beispiel `48 8B 05 ?? ?? ?? ??`. Es beschreibt ein Stück Code, das gleich bleibt, auch wenn seine Adresse wandert.

Nach einem Spiel-Update sucht der **Update-Scan** das Muster jedes Patches erneut und berechnet seinen neuen Offset. Patches, die der Scan an mehreren Stellen findet, werden als mehrdeutig markiert und nicht geändert.

Ein Patch mit gespeichertem Muster (siehe **AOB / UPDATE**) übersteht die meisten Updates.
