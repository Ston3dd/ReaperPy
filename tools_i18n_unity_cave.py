"""Englische Texte für den Tab UNITY > CAVEMAKER (tools_unity_cave_gui.py, cavemaker.py, cave_check.py)."""
EN_UNITY_CAVE = {
    'CAVEMAKER': 'CAVEMAKER',
    '★ UNITY CAVEMAKER': '★ UNITY CAVEMAKER',
    # --- cave_check.py ---
    'Ungültiger Offset ': 'Invalid offset ',
    'Der neue Code (newValue) der Patch-Stelle ist leer - der Patch würde nichts tun':
        'The new code (newValue) of the patch site is empty - the patch would do nothing',
    'Die Original-Bytes (defaultValue) fehlen - ReaperPy könnte den Patch nicht zurücknehmen':
        'The original bytes (defaultValue) are missing - ReaperPy could not undo the patch',
    'Das Label OriginTarget fehlt - die Cave hätte keinen Anfang': 'The label OriginTarget is missing - the cave would have no start',
    'Der neue Code ergibt keine Bytes': 'The new code produces no bytes',
    ' wird von ReaperPy nicht als Patch-Datei erkannt': ' is not recognised as a patch file by ReaperPy',
    'Die gespeicherte Datei weicht nach dem Zurücklesen vom gebauten Patch ab':
        'After reading it back, the saved file differs from the patch that was built',
    "Der Patch springt auf ein Label, das es nicht gibt: '": "The patch jumps to a label that does not exist: '",
    ' Byte) passt nicht zu den Original-Bytes (': ' bytes) does not match the original bytes (',
    ' Byte) - nach der Cave würde mitten in einem Befehl weitergemacht':
        ' bytes) - after the cave, execution would continue in the middle of an instruction',
    ' ist zu klein für einen Sprung': ' is too small for a jump',
    ' Byte) ist länger als die Original-Bytes (': ' bytes) is longer than the original bytes (',
    'Die Cave lässt sich nicht assemblieren: ': 'The cave cannot be assembled: ',
    'Die Cave endet nicht mit dem Rücksprung nach ': 'The cave does not end with the jump back to ',
    " - das Spiel würde hinter dem Code ins Leere laufen (letzte Zeile: '":
        " - the game would run into nothing behind the code (last line: '",
    # --- cavemaker.py ---
    'Das Backend hat keine Schreib-Funktion, die ich kenne (ps5_backend.py)':
        'The backend has no write function I know (ps5_backend.py)',
    'Wert außerhalb des Bereichs (': 'Value out of range (',
    'Wert außerhalb des Bereichs': 'Value out of range',
    'Für x und + sind nur Werte bis 2147483647 möglich': 'For x and + only values up to 2147483647 are possible',
    'Für ein Instanzfeld braucht es eine Instanz-Methode': 'An instance field needs an instance method',
    "' geht hier nicht": "' does not work here",
    'Am Hook steht schon ein jmp (E9) - ist hier noch ein Patch aktiv? Erst TEST AUS.':
        'There is already a jmp (E9) at the hook - is a patch still active here? TEST OFF first.',
    'script.json fehlt für diese Klasse': 'script.json is missing for this class',
    'Die Klasse ist im Spiel noch nicht geladen - erst im Spiel dorthin gehen (z. B. Spielstand laden) und nochmal versuchen':
        'The class is not loaded in the game yet - go there in the game first (e.g. load a save) and try again',
    '). cavemaker.py muss im ReaperPy-Ordner liegen und mit demselben Python gestartet werden wie ReaperPy.':
        '). cavemaker.py must be in the ReaperPy folder and run with the same Python as ReaperPy.',
    'Rückgabewert festlegen (': 'Set the return value (',
    "Befehl am Anfang der Methode nicht verlagerbar: '": "Instruction at the start of the method cannot be relocated: '",
    "' - bitte eine andere Haken-Methode nehmen": "' - please use another hook method",
    ' Byte) länger als die Funktion (': ' bytes) longer than the function (',
    'Dieses Argument lässt sich nicht abbilden': 'This argument cannot be mapped',
    'script.json nicht gefunden - statische Felder sind nicht möglich (Methoden und Instanzfelder gehen)':
        'script.json not found - static fields are not possible (methods and instance fields work)',
    ') ändern': ') change',
    "Befehl am Anfang der Methode nicht verlagerbar (benutzt r10 und r11): '":
        "Instruction at the start of the method cannot be relocated (uses r10 and r11): '",
    ' TypeInfo-Zeiger (statische Felder möglich)': ' TypeInfo pointers (static fields possible)',
    'Keine eindeutige Signatur (': 'No unique signature (',
    ') - Patch gilt nur für diese Basis': ') - the patch only applies to this base',
    '    läuft nur ab und zu (Ereignis-Methode) - merke ich mir als Notlösung, suche weiter.':
        '    runs only now and then (event method) - kept as a fallback, searching on.',
    '    übersprungen: ': '    skipped: ',
    'Kein TypeInfo-Zeiger (script.json) für diese Klasse': 'No TypeInfo pointer (script.json) for this class',
    'Statisches Feld: feste Adresse im Code (wie der Hook selbst) - gilt für diese Modul-Basis, auf der gleichen Spiel-Version also immer.':
        'Static field: fixed address in the code (like the hook itself) - valid for this module base, so always on the same game version.',
    '    läuft regelmäßig - das ist der richtige Haken.': '    runs regularly - this is the right hook.',
    '    Zurücksetzen fehlgeschlagen: ': '    Reset failed: ',
    # --- tools_cave_common.py / tools_ue_cave_gui.py / cave_check.py (gemeinsame Sammlung) ---
    ' Byte) - die Cave würde mitten in überschriebenen Bytes weiterlaufen':
        ' bytes) - the cave would continue in the middle of overwritten bytes',
    ': Hinzugefügt: ': ': Added: ',
    ': erst in der SAMMLUNG einen Eintrag wählen': ': choose an entry in the COLLECTION first',
    ': Dieser Patch ist schon an - erst TEST AUS.': ': this patch is already on - TEST OFF first.',
    ': Dieser Patch ist nicht aktiv.': ': this patch is not active.',
    ': Test AUS: ': ': Test OFF: ',
    ': Test AN @ ': ': Test ON @ ',
    ': Test: ': ': Test: ',
    ': Erst TEST AUS.': ': TEST OFF first.',
    ': Die SAMMLUNG ist leer.': ': the COLLECTION is empty.',
    ': Projekt: ': ': Project: ',
    ': Zurücksetzen: ': ': Reset: ',
    ' abgelehnt': ' rejected',
    'Hauptfenster: ': 'Main window: ',
    'Eintrag wählen und einen anderen Haken nehmen.': 'Choose an entry and take another hook.',
    'Erst im Tab UE-LIVE den Spiel-Ordner laden und verbinden, Spielstand laden, dann MENÜ AUFBAUEN. Danach Eintrag wählen und CODE CAVE BAUEN.':
        'First load the game folder in the UE-LIVE tab and connect, load a save, then BUILD MENU. Then choose an entry and click BUILD CODE CAVE.',
    "' benutzt - zwei Caves an derselben Stelle gehen nicht. Bitte 'Treffer selbst wählen' und eine andere nehmen.":
        "' - two caves at the same place do not work. Please use 'choose hit yourself' and take another one.",
    'CAVEMAKER: Gilt für ALLE Objekte, die diesen Code benutzen (auch Gegner). Erst TEST AN, im Spiel prüfen, dann IN PROJEKT ÜBERNEHMEN.':
        'CAVEMAKER: applies to ALL objects that use this code (enemies too). TEST ON first, check in the game, then TAKE OVER INTO PROJECT.',
    'Diese Instruktion (': 'This instruction (',
    ') wird schon von ': ') is already used by ',
    'CAVEMAKER: Diese Instruktion (': 'CAVEMAKER: This instruction (',
    # --- tools_unity_cave_gui.py ---
    'Haken-Methode wählen': 'Choose a hook method',
    'Erst im Tab MANUELL den Spiel-Ordner laden.': 'Load the game folder in the MANUAL tab first.',
    ' Kandidaten im Spiel-Code': ' candidates in the game code',
    ', ohne script.json (statische Felder nicht möglich)': ', without script.json (static fields not possible)',
    'CAVEMAKER: Hinzugefügt: ': 'CAVEMAKER: Added: ',
    '  (mit Signatur)': '  (with signature)',
    'CAVEMAKER: Haken-Suche für ': 'CAVEMAKER: hook search for ',
    ': ich probiere bis zu 60 Methoden, je etwa 3-4 s. Bitte im Spiel bleiben und NICHT im Menü stehen - am besten im laufenden Spiel herumlaufen …':
        ': trying up to 60 methods, about 3-4 s each. Please stay in the game and do NOT stand in a menu - best walk around in the running game …',
    'CAVEMAKER: Prüfe 6 s lang, ob der Wert wirklich gesetzt wird - bitte im Spiel weiterspielen …':
        'CAVEMAKER: checking for 6 s whether the value is really set - please keep playing …',
    'CAVEMAKER: erst im Tab MANUELL den SPIEL-ORDNER laden': 'CAVEMAKER: first load the GAME FOLDER in the MANUAL tab',
    "CAVEMAKER: keine statischen Felder in der Liste - Filter 'Statisch (live)' wählen (braucht script.json)":
        "CAVEMAKER: no static fields in the list - choose the filter 'Static (live)' (needs script.json)",
    'Nicht möglich: ': 'Not possible: ',
    'CAVEMAKER: erst links etwas auswählen': 'CAVEMAKER: choose something on the left first',
    'ReaperPy würde diesen Hook nicht richtig verstehen: ': 'ReaperPy would not understand this hook correctly: ',
    "CAVEMAKER: Das geht nur bei statischen Feldern: links ein Feld mit Wert in der Spalte WERT LIVE wählen, rechts 'Statisches Feld festhalten'.":
        "CAVEMAKER: this only works for static fields: choose a field with a value in the LIVE VALUE column on the left, 'Hold static field' on the right.",
    'CAVEMAKER: Das geht nur bei Einträgen, die in dieser Sitzung aus einem statischen Feld gebaut wurden. Sonst: ENTFERNEN und neu mit HAKEN AUTOMATISCH FINDEN anlegen.':
        'CAVEMAKER: this only works for entries built from a static field in this session. Otherwise: REMOVE and create again with FIND HOOK AUTOMATICALLY.',
    "CAVEMAKER: Die Haken-Suche geht nur mit 'festlegen (=)' oder 'mindestens (>=)'.":
        "CAVEMAKER: the hook search only works with 'set (=)' or 'at least (>=)'.",
    'CAVEMAKER: Die Suche läuft schon.': 'CAVEMAKER: the search is already running.',
    'Keine freie Haken-Methode zur Auswahl.': 'No free hook method to choose from.',
    'CAVEMAKER: erst in der SAMMLUNG einen Eintrag wählen': 'CAVEMAKER: choose an entry in the COLLECTION first',
    'CAVEMAKER: Dieser Patch ist schon an - erst TEST AUS.': 'CAVEMAKER: this patch is already on - TEST OFF first.',
    'CAVEMAKER: Dieser Patch ist nicht aktiv.': 'CAVEMAKER: this patch is not active.',
    'CAVEMAKER: Test AUS: ': 'CAVEMAKER: Test OFF: ',
    'CAVEMAKER: Erst TEST AUS.': 'CAVEMAKER: TEST OFF first.',
    'Eintrag wählen und ANDEREN HAKEN SUCHEN.': 'Choose an entry and click SEARCH OTHER HOOK.',
    'Diese Cheats benutzen denselben Haken und können so nicht gleichzeitig laufen:':
        'These cheats use the same hook and cannot run at the same time:',
    ' übernommen, ': ' taken over, ',
    'WERTE LESEN (live)': 'READ VALUES (live)',
    'HAKEN-METHODE (läuft oft, z. B. Update)': 'HOOK METHOD (runs often, e.g. Update)',
    'JETZT SCHREIBEN': 'WRITE NOW',
    'HAKEN AUTOMATISCH FINDEN + HINZUFÜGEN': 'FIND HOOK AUTOMATICALLY + ADD',
    '(statische Felder; im laufenden Spiel bleiben)': '(static fields; stay in the running game)',
    'IN PROJEKT ÜBERNEHMEN': 'TAKE OVER INTO PROJECT',
    'CAVEMAKER: Lesen: ': 'CAVEMAKER: Reading: ',
    ") wird schon von '": ") is already used by '",
    "' benutzt. Zwei Cheats am selben Haken gehen nicht gleichzeitig - bitte eine andere Haken-Methode wählen oder HAKEN AUTOMATISCH FINDEN benutzen.":
        "'. Two cheats on the same hook cannot run at the same time - please choose another hook method or use FIND HOOK AUTOMATICALLY.",
    'CAVEMAKER: Kein Haken gefunden, der den Wert setzt. Spiel an eine andere Stelle bringen (z. B. im Laden) und nochmal versuchen - oder JETZT SCHREIBEN nehmen.':
        'CAVEMAKER: no hook found that sets the value. Move the game to another place (e.g. in a shop) and try again - or use WRITE NOW.',
    'CAVEMAKER: GEFUNDEN: ': 'CAVEMAKER: FOUND: ',
    ' - läuft regelmäßig, der Cheat wirkt dauerhaft (Status AN).': ' - runs regularly, the cheat works permanently (status ON).',
    'CAVEMAKER: NUR NOTLÖSUNG: ': 'CAVEMAKER: FALLBACK ONLY: ',
    ' läuft nur bei einem Ereignis. Der Cheat wirkt nur in diesen Momenten. Besser: im Spiel an eine andere Stelle gehen und die Suche wiederholen.':
        ' runs only on an event. The cheat only works at those moments. Better: go to another place in the game and repeat the search.',
    ': geschrieben, aber der Wert ist danach nicht ': ': written, but the value afterwards is not ',
    ' - das Spiel überschreibt ihn wohl sofort. Dann HAKEN AUTOMATISCH FINDEN benutzen.':
        ' - the game probably overwrites it at once. Then use FIND HOOK AUTOMATICALLY.',
    'CAVEMAKER: Schreiben: ': 'CAVEMAKER: Writing: ',
    'CAVEMAKER: Zurücksetzen: ': 'CAVEMAKER: Reset: ',
    ' und wird immer wieder neu gesetzt - der Cheat wirkt dauerhaft.': ' and is set again and again - the cheat works permanently.',
    'CAVEMAKER: Prüfung: ': 'CAVEMAKER: Check: ',
    '. Die Offsets der Patches sind relativ zur Image-Basis; die Signatur findet den Hook auch nach einem Neustart wieder.':
        '. The patch offsets are relative to the image base; the signature finds the hook again after a restart.',
    "' im Spiel läuft. Passiert nichts, ist die Methode die falsche - dann HAKEN AUTOMATISCH FINDEN oder JETZT SCHREIBEN nehmen.":
        "' runs in the game. If nothing happens, the method is the wrong one - then use FIND HOOK AUTOMATICALLY or WRITE NOW.",
    ' gesetzt, aber der Haken läuft nur ab und zu. Besser: HAKEN AUTOMATISCH FINDEN.':
        ', but the hook only runs now and then. Better: FIND HOOK AUTOMATICALLY.',
    ' wurde einmal auf ': ' was set once to ',
    ' steht auf ': ' is at ',
    ' ist noch ': ' is still ',
    'CAVEMAKER: Test OK: ': 'CAVEMAKER: Test OK: ',
    'CAVEMAKER: Test nur TEILWEISE OK: ': 'CAVEMAKER: Test only PARTLY OK: ',
    'CAVEMAKER: Test FEHLGESCHLAGEN: ': 'CAVEMAKER: Test FAILED: ',
    'CAVEMAKER: Test AN @ ': 'CAVEMAKER: Test ON @ ',
    'CAVEMAKER: Test: ': 'CAVEMAKER: Test: ',
    'CAVEMAKER: Erzeugen: ': 'CAVEMAKER: Build: ',
    'CAVEMAKER: Vorschau: ': 'CAVEMAKER: Preview: ',
    'CAVEMAKER: Projekt: ': 'CAVEMAKER: Project: ',
    'CAVEMAKER: Hinweis: ': 'CAVEMAKER: Note: ',
    'CAVEMAKER: Geschrieben: ': 'CAVEMAKER: Written: ',
    'CAVEMAKER: Haken-Suche: ': 'CAVEMAKER: Hook search: ',
    'CAVEMAKER: Achtung: Dieser Cheat wirkt nur, wenn \'': 'CAVEMAKER: Note: this cheat only works when \'',
    'CAVEMAKER: Das IL2CPP-Modul liegt bei ': 'CAVEMAKER: the IL2CPP module is at ',
    ', die Image-Basis im Hauptfenster ist ': ', the image base in the main window is ',
    '  (nachgelesen: stimmt)': '  (read back: matches)',
    ' Werte gelesen': ' values read',
    'Dieser Haken (': 'This hook (',
    'CAVEMAKER: erst LISTE LADEN': 'CAVEMAKER: LOAD LIST first',
    '. Die Haken-Methode läuft im Spiel nicht (oder zu selten). TEST AUS, ENTFERNEN und HAKEN AUTOMATISCH FINDEN.':
        '. The hook method does not run in the game (or too rarely). TEST OFF, REMOVE and FIND HOOK AUTOMATICALLY.',
    ') - der Patch gilt nur für diese Basis': ') - the patch only applies to this base',
    # --- Release-Karte im Export-Dialog (export_goldhen.py) ---
    'Cover wählen': 'Choose cover',
    "' ist kein Hex-Wert wie #00ffc8 - die Farbe kommt aus dem Cover.": "' is not a hex value like #00ffc8 - the colour is taken from the cover.",
}
# Beschriftungen: nur eintragen, wenn es sie noch nicht gibt (Wörter wie SUCHE sind anderswo schon übersetzt)
EN_UNITY_CAVE_LABELS = {
    'LISTE LADEN': 'LOAD LIST', 'PKT': 'PTS', 'KATEGORIE': 'CATEGORY', 'ART': 'TYPE', 'KLASSE.NAME': 'CLASS.NAME',
    'WERT LIVE': 'LIVE VALUE', 'TYP / SIGNATUR': 'TYPE / SIGNATURE', 'HOOK': 'HOOK', 'SUCHE': 'SEARCH',
    'Alle': 'All', 'Methode': 'Method', 'Feld': 'Field', 'Statisch (live)': 'Static (live)', 'Sonstige': 'Other',
    'Unity/System': 'Unity/System', 'nur sinnvolle Cheats': 'only useful cheats', 'Nichts gewählt': 'Nothing chosen',
    'WAS SOLL PASSIEREN?': 'WHAT SHOULD HAPPEN?', 'MODUS': 'MODE', 'MENGE / WERT': 'AMOUNT / VALUE',
    'Flag AN (true)': 'Flag ON (true)', 'NAME': 'NAME', 'VORSCHAU': 'PREVIEW', 'HINZUFÜGEN': 'ADD',
    'SAMMLUNG': 'COLLECTION', 'PATCH': 'PATCH', 'STATUS': 'STATUS', 'TEST AN': 'TEST ON', 'TEST AUS': 'TEST OFF',
    'ENTFERNEN': 'REMOVE', 'ANDEREN HAKEN SUCHEN': 'SEARCH OTHER HOOK', 'AUTOR': 'AUTHOR',
    'CaveMaker': 'CaveMaker', 'Projekt': 'Project',
    'Release-Karte (PNG) mit erstellen': 'Also create a release card (PNG)', 'Cover': 'Cover', 'Farbe': 'Colour',
    'WÄHLEN ...': 'CHOOSE ...', 'NUR KARTE ...': 'CARD ONLY ...',
    'Cover und Farbe leer lassen: das Cover wird in der Bibliothek gesucht, die Farbe kommt aus dem Cover.':
        'Leave cover and colour empty: the cover is looked up in the library, the colour is taken from the cover.',
    '--- Release-Karte ---': '--- Release card ---', 'Release-Karte speichern': 'Save release card',
    'Release-Karte: ': 'Release card: ', 'Keine Cheats für die Karte.': 'No cheats for the card.',
    'Release-Karte nicht erstellt: ': 'Release card not created: ',
    'kein Cover gefunden - Portal-Verlauf': 'no cover found - portal gradient', 'Cover: ': 'Cover: ',
    'Erst im Tab MANUELL den Spiel-Ordner laden, verbinden und MODUL ERKENNEN - dann hier LISTE LADEN.':
        'First load the game folder in the MANUAL tab, connect and DETECT MODULE - then LOAD LIST here.',
    'festlegen (=)': 'set (=)', 'vervielfachen (x)': 'multiply (x)', 'addieren (+)': 'add (+)', 'mindestens (>=)': 'at least (>=)',
    'Wert fehlt': 'Value missing', 'Ganze Zahl erwartet': 'Whole number expected',
    'Methode leer machen (tut nichts)': 'Make the method empty (does nothing)',
    'Geld': 'Money', 'EXP/Level': 'EXP/Level', 'Leben/Schaden': 'Health/Damage', 'Ressource': 'Resource',
    'Item/Inventar': 'Item/Inventory', 'Freischaltung': 'Unlock', 'Zeit/Tempo': 'Time/Speed', 'Kampf': 'Combat',
}
