# Werte, Live-Werte und das Cheat-Menü

Diese Werkzeuge sind für einzelne Werte: Leben, Ausdauer, Gold, Erfahrung, Munition. Nimm das, was zu deinem Spiel passt.

## WERTE: fertige Patches in drei Schritten
Der Tab **WERTE** (unter **UNREAL** und **UNITY**) ist der einfachste Weg. Die drei Schritte sind dieselben wie bei den Items:
1. Wähle den Spielordner.
2. **WICHTIGES FINDEN**
3. **PATCHES SPEICHERN**

- **Unreal Engine:** Die Werte deiner Spielfigur kommen aus dem SDK und werden an der laufenden Figur geprüft. Für jeden angehakten Wert baut ReaperPy eine Cave, die ihn am Sinken hindert. Nutzt das Spiel einen Subtraktions-Befehl, wird dieser Befehl abgeschaltet (Munition und Gold sinken nicht mehr, Aufsammeln funktioniert weiter). Erfahrung wird auf die Zahl gesetzt, die du eingibst.
- **Unity (IL2CPP):** Methoden werden an ihren Namen erkannt (`TakeDamage`, `SpendMoney`, `UseAmmo` ...). Jede Zeile sagt in einfachen Worten, was passiert. Klassen, die nach Gegnern aussehen, sind markiert und nicht vorab angehakt.

> **Achtung:** Diese Patches gelten für **alle** Objekte, die den Code benutzen - auch Gegner. Die Namenserkennung bei Unity ist eine Faustregel: Sieh dir die Liste an, bevor du speicherst.

## LIVE: Werte sehen und ändern, während du spielst
In **UNREAL → LIVE** wählst du den SDK-Ordner des Spiels, klickst einen Wert wie `UHealthComponent.Health` an und siehst rechts den Live-Wert. Mit der rechten Maustaste auf einer Zeile änderst du den Wert, frierst ihn ein oder taust ihn auf, zeigst ihn im Speicher oder findest den Schreiber. Instanz-Adressen ändern sich bei jedem Spielstart; Klassen und Offsets bleiben gültig.

## CHEAT-MENÜ: Schalter für deine Spielfigur
Drücke **MENÜ AUFBAUEN**, nachdem du das Spiel in LIVE geladen hast. Jeder Eintrag zeigt, ob er an deiner Figur erreichbar ist (Haken) oder warum nicht (Kreuz). **AN / AUS** (oder Doppelklick) schaltet einen Eintrag um und stellt beim Ausschalten den Originalwert wieder her. Wechselt deine Figur (Tod, Ladebildschirm), werden alle Einträge freigegeben. **CODE CAVE BAUEN** macht aus dem gewählten Eintrag einen dauerhaften Cheat: ReaperPy sucht im Spiel-Code die Instruktion, die den Wert schreibt, und speichert eine Cave als `.reapproj`-Patch (ohne aktives Projekt fragt es nach einem Ordner). Mit **CAVE: TREFFER WÄHLEN** suchst du die Instruktion selbst aus.

## ENTDECKER: Was gibt es zu finden?
**UNREAL → ENTDECKER** analysiert das SDK und sagt dir in einfachen Worten, was das Spiel bietet: Item-Tabellen, Geben-Funktionen, Statistik-Enums, Cheat-Manager - und ob sich für jedes ein Trainer bauen lässt. Starte mit **ANALYSIEREN**. **TABELLE LIVE LESEN** listet die Zeilen einer Tabelle nach Namen. **INVENTAR-EINTRÄGE SUCHEN** setzt Mengen direkt im Speicher, wenn keine Geben-Funktion passt.

## EXPERTE
**UNREAL → EXPERTE** enthält die statischen Werkzeuge: Kandidaten aus den SDK-Headern, Befehlssuche im Dump, NOP- und Cave-Patches. Es ist auch ein Kommandozeilen-Tool (`python ue_auto.py --help`).

## Unity: CHEAT-MENÜ
**UNITY → CHEAT-MENÜ** funktioniert wie das von Unreal, gebaut aus `dump.cs`: Methoden-Patches (Schaden nehmen, Geld ausgeben, Ausdauer verbrauchen) und Felder (Leben, Gold, Ausdauer, EXP, Hunger ...). Lade im Reiter MANUELL den Spiel-Ordner, verbinde, lade einen Spielstand und drücke **MENÜ AUFBAUEN**. **AN / AUS** schaltet einen Eintrag, **WERT SETZEN** schreibt eine Zahl und hält sie fest, **ALLE AUS** stellt die Originale zurück. Bei Feldern erzeugt **CODE CAVE BAUEN** eine dauerhafte Cave, bei Methoden speichert **PATCH SPEICHERN** den fertigen Patch.

## Unity: SCHNELL und MANUELL
In **UNITY → MANUELL**:
1. Wähle den Il2CppDumper-Ordner.
2. Starte das Spiel, lade einen Spielstand, verbinde und drücke **MODUL ERKENNEN**.
3. Drücke einmal **SPIEL SCANNEN**. Danach suchst du `Klasse.Feld` (gold, hp, money ...), siehst alle lebenden Objekte und änderst oder frierst den Wert ein. *Methoden* lässt eine Methode true / false / eine feste Zahl liefern oder leer laufen. *Namen* listet Enums wie Item-IDs.

Das alles ist für Einzelspieler-Spiele auf deiner eigenen Konsole. Für den nächsten Schritt siehe [Export](howto:export).
