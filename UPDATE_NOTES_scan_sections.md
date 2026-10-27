# Update: Cheat-Searcher - Speicherbereiche + neues Layout

## Neu
- **SPEICHERBEREICHE** (rechte Spalte im Tab WERT SUCHEN): zeigt, was im Spiel-Speicher liegt
  - **eboot.bin aufgesplittet**: Code-, Nur-Lesen- und Daten-Bereich je als eigene Zeile (Adresse, Größe, Rechte)
  - Spiel-Module (`.prx`, kein System), **Systembibliotheken** (eine Zeile je Lib), Heap, Shared Memory, Stacks
  - Heap-Regionen ab 1 MB einzeln, kleinere als eine Sammelzeile (statt 17 000 Einzelzeilen)
  - **Haken je Zeile** (Klick auf das Kästchen, Doppelklick oder Leertaste), Kategoriezeilen schalten die ganze Gruppe
- **AUSBLENDEN-Filter**: Voreinstellungen (alle Systembibliotheken / libSce* / libc+libkernel+libm / Shared Memory / Stacks)
  und **eigene Muster** (`libSce*, SDL, Shm`; mit `*` Platzhalter, ohne `*` Namensteil). Standard: Systembibliotheken aus.
  Rechtsklick auf ein Modul -> *Modul ausblenden*.
- Knöpfe **ALLE / KEINE / NUR EBOOT / NUR SPIEL**, Rechtsklick: ein-/ausschalten, nur Auswahl scannen, Adresse kopieren,
  im Speicher anzeigen.
- Zusammenfassung: *Ausgewählt: x / y Regionen · MB / MB (-%)*, nach einem Scan zusätzlich die geschätzte Lesezeit
  (aus dem Tempo des letzten Scans).
- Der Filter wird **beim Scan-Start mit einer frischen Speicherkarte** angewendet (der Heap wächst) und in
  `scan_filter.json` im Datenordner gemerkt.

## Layout
- Drei Spalten: **TREFFER | SCAN | BEREICHE**, unten die **ADRESSLISTE**; Karten mit Titelleiste, gefüllte Hauptknöpfe.
- Rechtsklick-Menüs für Treffer und Adressliste.
- Seltene Einstellungen im Dialog **OPTIONEN** (Tempo-Filter, Float, Parallel, Aliasing, kleine Segmente, Snapshot-RAM,
  Auslagern, Debug-Log, SELBSTTEST, REGIONEN-BERICHT). Es wurde keine Funktion entfernt.

## Geänderte / neue Dateien
neu: `regionfilter.py`, `tools_sections_gui.py`, `tests/test_regionfilter.py`, `tests/test_scan_sections_gui.py`
geändert: `scanner.py` (`regions(pick=...)`, `last_mbps`), `tools_scan_gui.py`, `tools_i18n_en.py`,
`tests/i18n_harvest.py`, `README.md`, `CHANGELOG.md`

## Hinweise
- Libs auszublenden ist für Spielwerte normalerweise unbedenklich. Wird ein Wert nicht gefunden: Filter auf **ALLE** und neu scannen.
- Das Layout wurde ohne Display (nur mit Test-Attrappe) geprüft - bitte einmal in der echten Oberfläche ansehen.

## Git
```
git add regionfilter.py tools_sections_gui.py tools_scan_gui.py scanner.py tools_i18n_en.py \
        tests/test_regionfilter.py tests/test_scan_sections_gui.py tests/i18n_harvest.py \
        README.md CHANGELOG.md UPDATE_NOTES_scan_sections.md
git commit -m "Cheat searcher: memory sections panel (eboot.bin split, hide system libs), new layout"
git push
```
