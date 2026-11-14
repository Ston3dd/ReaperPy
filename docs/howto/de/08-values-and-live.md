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

## CAVEMAKER: Cheats aus der dump.cs, getestet und geprüft
**UNITY → CAVEMAKER** baut aus jeder Methode und jedem Feld der `dump.cs` einen Cheat: Rückgabewert festlegen, Parameter ändern (z. B. immer 999 Geld bekommen), ein Feld des übergebenen Objekts setzen, ein Instanz- oder statisches Feld festhalten. Du brauchst nur den Reiter MANUELL (Spiel-Ordner laden, verbinden, MODUL ERKENNEN) und drückst im CAVEMAKER **LISTE LADEN**. Links wählst du etwas aus (Suche, Kategorie, „nur sinnvolle Cheats“), rechts **WAS SOLL PASSIEREN?**, Modus und Wert. **HINZUFÜGEN** liest die Original-Bytes live aus dem Spiel und baut Patch oder Code Cave samt Signatur; sie landet in der **SAMMLUNG**. Bei statischen Feldern sucht **HAKEN AUTOMATISCH FINDEN** selbst eine Methode, die im Spiel regelmäßig läuft, und prüft live, dass der Wert wirklich gesetzt wird.

In der SAMMLUNG probierst du mit **TEST AN** / **TEST AUS** direkt im Spiel. **IN PROJEKT ÜBERNEHMEN** prüft jeden Hook vorher mit ReaperPys eigenem Parser und Cave-Assembler (gibt es eine Patch-Stelle, ein Label `OriginTarget`, einen passenden `OriginReturn`, führt jeder Sprung zu einem Label, endet die Cave mit dem Rücksprung, lässt sie sich assemblieren?), schreibt die Datei, liest sie zurück und legt sie als normale Karte ins Hauptfenster. Ein Hook, den ReaperPy nicht verstehen würde, wird mit Begründung abgelehnt und nicht still übergangen.

**UNREAL → CAVEMAKER** ist das Cheat-Menü mit derselben Sammlung: **CODE CAVE BAUEN** legt die Cave nicht gleich auf die Platte, sondern in die SAMMLUNG - dort prüfen, **TEST AN** / **TEST AUS** im Spiel, dann **IN PROJEKT ÜBERNEHMEN**.

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

Der Speicher wird dabei **nur einmal** durchsucht (Fortschritt in %, mit **SCAN ABBRECHEN** stoppbar); danach lädt jedes angeklickte Feld sofort. Klassen mit einem `Instance`-Feld werden sogar ganz ohne Scan gefunden.

**Cave mit fester Menge:** Wähle links ein Instanz-Feld (z. B. `gold`), trage bei **CAVE MIT MENGE** `999` ein und drücke **CODE CAVE BAUEN**. ReaperPy baut daraus dieselbe dauerhafte Cave wie im CHEAT-MENÜ und speichert den Patch.

Das alles ist für Einzelspieler-Spiele auf deiner eigenen Konsole. Für den nächsten Schritt siehe [Export](howto:export).
