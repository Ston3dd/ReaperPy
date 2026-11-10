# Erste Schritte

ReaperPy ändert Zahlen und Code in einem Spiel, während es auf deiner gehackten PS5 läuft - Leben, Munition, Geld, Items und mehr. Für die einfachen Werkzeuge brauchst du keine Programmierkenntnisse. Diese Seite bringt dich von null zum verbundenen Tool.

## Was du brauchst
- Eine gehackte PS5 mit geladenem **ps5debug-NG**-Payload.
- Deinen PC im selben Netzwerk wie die Konsole. Erlaube ReaperPy in der Firewall den Port **755**: Die Konsole verbindet sich zurück zu deinem PC, um Breakpoint-Treffer zu melden.
- Das laufende Spiel mit geladenem Spielstand (nicht im Hauptmenü).

> **Tipp:** Nutze ReaperPy für Einzelspieler-Spiele auf deiner eigenen Konsole.

## 1. Verbinden
1. Starte das Spiel auf der Konsole und lade deinen Spielstand.
2. Lade den Payload auf der Konsole.
3. Gib die IP-Adresse der Konsole im Hauptfenster bei **PS5 IP** ein.
4. Drücke **VERBINDEN**. Wenn es klappt, zeigt die Statuszeile die Prozessnummer (`verbunden - PID ...`) und die Konsole zeigt meist eine kurze Benachrichtigung.
5. ReaperPy erkennt das Spiel an seiner Titel-ID und lädt passende Codes aus deiner Bibliothek automatisch.

**Es verbindet nicht?** Öffne **WERKZEUGE → START** und drücke **VERBINDUNG PRÜFEN**. ReaperPy prüft nacheinander, ob die IP gültig ist, ob die Konsole antwortet, ob der Payload geladen ist und ob ein Spiel läuft - und sagt dir in einfachen Worten, wo es hakt und was du tun kannst (zum Beispiel „Payload nicht geladen - sende ihn erneut“). Auf der Konsole wird nichts verändert. Scheitert **VERBINDEN**, steht im Protokoll ein ähnlicher Hinweis.

## 2. Werkzeuge öffnen
Drücke im Hauptfenster auf **WERKZEUGE**. Der erste Tab, **START**, sagt dir in einfachen Worten, ob du verbunden bist und welche Codes geladen sind, und hat große Knöpfe für die Einsteiger-Schritte. Der Knopf **? HILFE** oben öffnet die Anleitung, die zum gerade sichtbaren Tab gehört. Alle Anleitungen öffnest du jederzeit auch mit dem Knopf **ANLEITUNGEN** im Hauptfenster, sogar ohne Verbindung.

## 3. Welches Werkzeug für welche Aufgabe
- **Eine Zahl, die ich sehen kann** (Leben, Munition, Geld), und du willst einen fertigen Cheat: [Cheat in vier Schritten](howto:guided-cheat) (Tab **ASSISTENT**). Zum Suchen von Hand mit allen Optionen: [Einen Wert finden](howto:find-value).
- **Alle Items eines Unreal-Engine-Spiels**: [Items in Unreal-Spielen](howto:items-unreal).
- **Alle Items eines Unity-Spiels**: [Items in Unity-Spielen](howto:items-unity).
- **Leben, Gold, Erfahrung, Munition als fertige Patches** oder Live-Werte: [Werte, Live-Werte und das Cheat-Menü](howto:values-and-live).
- **Eine gefundene Adresse zum Cheat machen**: [Cheats bearbeiten](howto:edit-cheats) und [Assembler für Einsteiger](howto:assembler-basics).
- **Die Cheats in GoldHEN / etaHEN nutzen**: [Export](howto:export).
- **Etwas funktioniert nicht mehr**: [Fehlersuche](howto:troubleshooting).

## 4. Sicher bleiben
- **Speichere zuerst im Spiel.** Eine Änderung lebt nur im Speicher des Spiels; nach einem Neustart ist das Original zurück.
- Jeder Schreibzugriff der Werkzeuge wird aufgezeichnet. **FORTGESCHRITTEN → JOURNAL / UNDO** macht einzelne Änderungen oder alles rückgängig.
- Schließt sich das Spiel nach einer Änderung, öffne **FORTGESCHRITTEN → KERNEL-LOG**. Dort stehen Abstürze und Fehler, oft mit der Ursache.
- Ändere immer nur eine Sache. Wenn etwas schiefgeht, weißt du, woran es lag.
- Unbekannte Wörter stehen im [Glossar](howto:glossary).
