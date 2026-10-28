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

---

# Update 2: Tab "★ ITEMS" - alle Items als Trainer in drei Schritten

Vorher: UE-LIVE laden -> UE-ENTDECKER -> ANALYSIEREN -> Geben-Funktion anklicken -> Tabelle lesen -> Zeilen wählen -> CAVE-TRAINER
EXPORTIEREN (Menge, this, FName per Zeiger, Ordner ...). Jetzt ein Tab, drei Schritte:

1. **SPIEL**: Spiel-Ordner wählen (wird gemerkt), im Hauptfenster verbinden, Spielstand laden. Der Tab zeigt ✔/✗ in Klartext.
2. **ITEMS FINDEN**: sucht selbst die Item-Tabelle (Namen mit Item/Inventory/Loot/Weapon zuerst) und die Geben-Funktion, die der
   Trainer bauen kann, liest alle Items live und teilt sie in Kategorien ein (Kategorie-Spalte, sonst Namens-Vorsilbe:
   `Item_Fish_Trout` -> *Fish*). Haken setzen (Kästchen, Doppelklick, Leertaste, Rechtsklick), Suche, Kategorie-Filter,
   ALLE AN / ALLE AUS.
3. **TRAINER SPEICHERN**: Menge je Item, ein Klick. Einträge à 14 Items je Kategorie (*Fish 1*, *Fish 2* ..., ohne das Wort
   "Item"). Mehr als 400 Items oder 64 Einträge -> mehrere Projekte (`Items 1`, `Items 2` ...), davon nur EINS gleichzeitig
   aktivieren. Speicherort: Datenordner/trainer/<Spiel>/ (Button ORDNER ÖFFNEN). Beim Speichern wird im Spiel nur gelesen.

Falls die Automatik falsch liegt: über der Liste *Item-Tabelle* / *Geben-Funktion* ändern. Gibt es keine baubare Funktion, sagt der
Tab warum und verweist auf UE-ENTDECKER -> INVENTAR-EINTRÄGE SUCHEN.

## Dateien (Update 2)
neu: `ue_items.py`, `tools_items_gui.py`, `tests/test_ue_items.py`, `tests/test_gui_items.py`
geändert: `tools_gui.py` (Tab registriert), `tools_start_gui.py` (Karte), `tools_discover_gui.py` (nutzt `ue_items.hook_targets`),
`tools_i18n_en.py`, `tests/i18n_harvest.py`, `tests/test_tools_i18n.py`, `README.md`, `CHANGELOG.md`

## Hinweise
- Die Trainer-Erzeugung selbst ist der bisherige, getestete Code (cave_trainer / ue_cavegen); neu ist die Automatik davor.
  Mit einer Fake-Konsole habe ich den ganzen Weg durchgespielt (Items lesen -> Pakete -> Cave-Plan -> Projektdateien), an einem
  echten Spiel NICHT. Bitte zuerst mit einem Spielstand testen, den du nicht brauchst.
- Die Kategorie-Einteilung ist eine Heuristik. Stimmt sie bei deinem Spiel nicht, sag mir die Tabellen-/Spaltennamen, dann passe ich sie an.

## Git (Update 2)
```
git add ue_items.py tools_items_gui.py tools_gui.py tools_start_gui.py tools_discover_gui.py tools_i18n_en.py \
        tests/test_ue_items.py tests/test_gui_items.py tests/i18n_harvest.py tests/test_tools_i18n.py \
        README.md CHANGELOG.md UPDATE_NOTES_scan_sections.md
git commit -m "New ITEMS tab: find all items and save them as a trainer in three steps"
git push
```

---

# Update 3: Trainer auf anderen Konsolen (kein Platz für die Cave / "schon aktiv" / "nichts kommt an")

## Was ich im Code gefunden habe
1. **Patches wurden blind geschrieben.** `_apply_simple` hat die Bytes an der Zieladresse nie mit den erwarteten Original-Bytes
   verglichen. Bei einer anderen Spielversion liegen an deinen Adressen andere Daten: der Patch überschreibt sie (nichts kommt
   im Spiel an) oder `detect_patched` hält zufällig passende Bytes (z. B. Schalter-Byte `01`) für "schon aktiviert".
2. **Item-Nummern (FNames) sind fest eingebaut** und stammen aus *deiner* Spielsitzung. Bei jemand anderem können dieselben
   Items andere Nummern haben -> die Funktion bekommt einen unbekannten Namen, und es passiert nichts.
3. **Die Cave liegt im Padding am Ende der Code-Regionen** (meist < 4 KB). Die Größe hing nur von der Zeilenzahl ab (bis 400 Items
   je Projekt = mehrere KB) und wurde nicht gegen den freien Platz geprüft. Wer zuerst deine BASIS aktiviert, hat das Padding
   belegt; danach findet auch sein eigener Build keinen Platz. Die alte Meldung nannte weder Zahlen noch Grund.

Welche der drei bei deinem Bekannten zutrifft, kann ich von hier nicht sehen - die Absicherungen decken alle drei ab.

## Was neu ist
- **Versions-Wächter** (`patch_engine.py`): Trainer-Patches (`"Verify": true`) werden verweigert, wenn dort weder das erwartete
  Original noch der Patch steht. Meldung mit Adresse und Bytes. Normale Community-Patches ohne das Flag laufen wie bisher.
- **Versions-Fingerabdruck** im Trainer (`_trainer_spec.json` -> `anchors`).
- **TRAINER PRÜFEN / ANPASSEN …** im Tab ITEMS: vergleicht Fingerabdruck + Item-Nummern mit dem laufenden Spiel; bei anderen Item-Nummern
  und passender Version schreibt es den Trainer für dein Spiel neu (BASIS muss aus sein). Bei anderer Version: klare Warnung.
- **Cave-Größe nach freiem Platz**: ITEMS liest den freien Code-Platz und teilt automatisch auf mehrere Projekte auf.
  Fehlermeldung "Kein freier Code-Platz" nennt jetzt gebraucht / größte Lücke / belegte Region-Enden.
- **Image-Basis-Prüfung** (`imagebase.py`): vergleicht die Basis im Hauptfenster mit der benannten Speicherkarte (`eboot.bin`).
  Weicht sie ab: Meldung + Knopf BASIS ÜBERNEHMEN, Speichern gesperrt. Keine Namen in der Karte: "nicht prüfbar" - nie eine geratene Zahl.

## Zum Vorschlag "Adressen zentral in read()/write() umrechnen"
Nicht eingebaut. Geprüft: 65 Lese-/Schreibaufrufe in 20 Dateien; fast alle bekommen schon LIVE-Adressen (Pointer, Heap, Bibliotheken)
oder rechnen selbst `IMAGE_BASE + RVA`. Eine zentrale Umrechnung würde diese Adressen ein zweites Mal verschieben; die
vorgeschlagene Erkennung ("irgendein lesbares Segment", Rückfall auf den ersten Karteneintrag) kann zudem die falsche Region
treffen - das wäre genau die geratene Zahl. Deine Prüfung (0x400000, und der Phoenix-Studio-Screenshot zeigt `executable[0]-5-400000`)
spricht für feste Basis. Ich habe daher nur das Prüfen eingebaut: stimmt die Basis nicht, wird es sichtbar gemeldet.

## Dateien (Update 3)
neu: `imagebase.py`, `tests/test_trainer_portability.py`, `tests/test_imagebase.py`
geändert: `cave_trainer.py`, `patch_engine.py`, `tools_items_gui.py`, `ue_items.py`, `tools_i18n_en.py`, `tests/test_gui_items.py`,
`README.md`, `CHANGELOG.md`

## Git (Update 3) - alles zusammen (die Zip enthält Update 1-3)
```
git add -A
git commit -m "Trainer portability: version guard, cave sizing by free space, check/adapt trainer, image base check"
git push
```
