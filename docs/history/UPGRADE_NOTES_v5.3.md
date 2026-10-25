# ReaperPy v5.3 — Cheat Testbench

- Fokus auf Cheat-Kandidaten: Health/Survival, Geld, Items/Inventory, Waffen/Munition, Bewegung, Debug/Cheat-Hooks, Unlocks/Progression sowie AI-/Wahrnehmungs- und Spawn-/Freeze-Spuren.
- `cheat_testbench.py` erzeugt eine gefilterte Kandidatenliste aus GObjects-Exporten.
- `cheat_testbench_gui.py` erlaubt manuelles Teststatus-Tracking und Notizen.
- Vorbefüllte Berichte stammen aus `dump.bin.engine.zip`; 4.459 statische Kandidaten in zwei Datensätzen. Das ist bewusst eine breite Suchliste, keine Liste bestätigter Cheats.
- Bau-/Craftingkosten werden gefiltert.
- Statische Symbolanalyse bleibt read-only; keine automatischen Funktionsaufrufe oder Memory-Patches.
