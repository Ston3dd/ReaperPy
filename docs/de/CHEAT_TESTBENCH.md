# ReaperPy Cheat Testbench 5.3

Fokus: Cheat-Kandidaten statt allgemeiner SDK-Zusammenfassung. Erzeugt eine evidenzbasierte Symbol-Liste aus den `GObjects.txt` deiner Dumps (jedes Spiel bekommt seinen Ordnernamen im ZIP, sonst den ZIP-Namen, als Spielname) plus eine lokale GUI, um jeden Kandidaten als `NOT TESTED`, `PASS`, `FAIL` oder `INCONCLUSIVE` zu markieren und Beobachtungen zu speichern.

## Start
1. Python 3.10+ installieren.
2. `python cheat_testbench.py "../dump.bin.engine.zip" --out cheat_testbench` ausführen. (Der ZIP-Pfad muss auf dein Archiv zeigen.)
3. `python cheat_testbench_gui.py cheat_testbench/cheat_candidates.json` starten.

## Wichtig
- Der Scan ist statische Symbolsuche, kein Cheat-Aktivator. `GObjects.txt`-Einträge sind keine bestätigten Funktions-/Instruktionsadressen.
- `PASS` bedeutet, dass du das Verhalten in deiner eigenen Testumgebung beobachtet hast; es wird nicht automatisch verifiziert. Teste pro Durchlauf nur eine Änderung, notiere Build/Version, Szene, Ausgangszustand und Save/Reload-Verhalten.
- Keine Crafting-/Baukosten-Kandidaten werden aufgenommen. Ein Treffer kann trotzdem ein False Positive sein.
- Die Kategorie „AI / perception“ (Sicht-/Hör-Sinne, Alarmzustand) und „Enemy spawn / freeze leads“ liefern nur Spuren für weitere Analyse, keinen bestätigten Freeze- oder Unsichtbar-Eintrag.
