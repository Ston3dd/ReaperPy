"""Test: der Unity-Teil ist im EN-Modus vollstaendig uebersetzt - auch Meldungen mit eingesetzten Zahlen/Namen und die
Log-Rueckrufe aus il2cpp_dump.py (die die allgemeine Pruefung in test_tools_i18n nicht sieht).  Und: deutsche Texte
haben echte Umlaute (kein 'Pruefe', 'bestaetigt', 'ueber' ...)."""
import ast
import os
import re
import struct
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import ghost_tk; ghost_tk.install()  # noqa: E402,E702
import test_il2cpp as TI  # noqa: E402
import test_unity_tab as TU  # noqa: E402
import tools_i18n as I  # noqa: E402
from pathlib import Path

GERMAN = re.compile(
    r"[äöüÄÖÜß]|\b(und|oder|nicht|kein|keine|ein|eine|der|die|das|dem|den|für|mit|wird|werden|Spiel|Klasse|Klassen|"
    r"Objekt|Objekte|Speicher|Modul|Fehler|Datei|Methode|Methoden|Wert|Werte|Feld|Felder|Adresse|geladen|gefunden|"
    r"Regionen|Tabelle|suche|Suche|Zeiger|leer|gesetzt|erwartet|gelesen|Diagnose|Basis|Treffer|Anzahl|jetzt|noch|"
    r"auch|dann|beim|erst|Ordner|wählen|bitte|Insgesamt|Prüfe|davon|haben|zeigt|nur|Liste|Bibliotheken|Zeile|"
    r"rechts|links|Geduld|ersten|etwas|ändern|lassen|diese|Spielstand|Anzeige|Instanzen|Instanz|schnell|wirkt|auf|"
    r"Auswahl|alle|setzen|einfrieren|auftauen|suchen|laden|erkennen|scannen|Protokoll|Griff)\b", re.IGNORECASE)
ASCII_UMLAUT = re.compile(r"\b(Pruefe|geprueft|bestaetigt|ueber|enthaelt|pruefbar|waehle|Rueckgabe\w*|zurueck\w*|Menue|"
                          r"befuellt|laenger|fuer|Oeffne\w*|aendern|loeschen|Loesch\w*|koennen|muessen|waehlen)\b")


class UnityI18n(unittest.TestCase):
    def tearDown(self):
        I.set_lang("de")

    def _flow_messages(self):
        """Echte Abfolge im Tab: laden, erkennen, scannen, Wert setzen, patchen - und der Fehlerfall."""
        a = TU.UnityTabFlow()
        a.setUp()
        t, w = a.t, a.w
        t.load()
        t.detect_base()
        t.scan_game()
        t.shown = [x for x in t.targets if x.key == "Game.Wallet.gold"]
        t.tl.selection = lambda: ("0",)
        t.cur = t.shown[0]
        t.refind(force=True)
        t.tr.selection = lambda: ("0",)
        t.set_value("5")
        t.v_mq.set("CanBuy")
        t._fill_methods()
        t.ml.selection = lambda: ("0",)
        t.apply_patch("true")
        t.apply_patch("true")                         # zweites Mal: Fehlermeldung
        t.v_nq.set("item")
        t._fill_names()
        out = [m for _k, m in w.logs] + [m for _k, m in t.log_lines]
        out += [t.info_text, t.lbl.cget("text"), t.lbl_list.cget("text"), t.lbl_cur.cget("text")]
        a.tearDown()
        # Fehlerfall: Modul nicht passend -> Diagnose-Bericht
        b = TU.UnityTabFlow()
        b.setUp()
        b.t.load()
        b.c.maps = [(TI.BASE, TI.BASE + 0x1000, 4, "Il2CppUserAssemblies.prx"),
                    (TI.BASE + 0x1000, TI.BASE + 0x10000, 3, "Il2CppUserAssemblies.prx")]
        b.c.put(TI.BASE + 0x2000, struct.pack("<Q", 0))
        b.c.get_maps_named = lambda: b.c.maps
        b.t.detect_base()
        out += [m for _k, m in b.w.logs] + [m for _k, m in b.t.log_lines] + [b.t.lbl.cget("text")]
        # Ohne script.json / ohne dump.cs
        c = TU.UnityTabFlow()
        c.setUp()
        os.remove(os.path.join(c.tmp.name, "dump.cs"))
        c.t.load()
        out += [m for _k, m in c.w.logs] + [c.t.lbl.cget("text")]
        b.tearDown()
        c.tearDown()
        return list(dict.fromkeys(m for m in out if m))

    def test_flow_messages_fully_english(self):
        I.set_lang("en")
        bad = [(m, I.translate(m)) for m in self._flow_messages() if GERMAN.search(I.translate(m))]
        self.assertEqual(bad, [], "deutsche Reste im EN-Modus:\n" + "\n".join(f"  {m!r} -> {e!r}" for m, e in bad))

    def test_every_text_fragment_translated(self):
        """Jeder deutsche Text-Baustein im Code hat eine saubere englische Fassung (auch f-String-Teile)."""
        I.set_lang("en")
        bad = []
        for fn in ("il2cpp_dump.py", "tools_unity_gui.py"):
            tree = ast.parse(Path(os.path.join(HERE, "..", fn)).read_text(encoding="utf-8"))
            docs = set()
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                        and isinstance(getattr(n.body[0], "value", None), ast.Constant):
                    docs.add(id(n.body[0].value))
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                    t = n.value
                    if len(t.strip()) < 3 or not re.search(r"[A-Za-zäöüÄÖÜß]{3}", t) or t.startswith(("<", "/", "Q.", "tk.", "#")):
                        continue
                    if GERMAN.search(I.translate(t)):
                        bad.append(f"{fn}:{n.lineno}: {t!r}")
        self.assertEqual(bad, [], "Text-Bausteine ohne (vollständige) Übersetzung:\n" + "\n".join(bad))

    def test_language_switch_rebuilds_log_and_info(self):
        a = TU.UnityTabFlow()
        a.setUp()
        a.t.load()
        de_lines = list(a.t.log_lines)
        self.assertTrue(any("Klassen" in m for _k, m in de_lines))
        I.set_lang("en")
        a.t._relang()
        self.assertFalse(any(GERMAN.search(m) for _k, m in a.t.log_lines), a.t.log_lines)
        I.set_lang("de")
        a.t._relang()
        self.assertEqual(a.t.log_lines, de_lines)
        a.tearDown()

    def test_german_texts_use_real_umlauts(self):
        bad = []
        for fn in ("il2cpp_dump.py", "tools_unity_gui.py"):
            tree = ast.parse(Path(os.path.join(HERE, "..", fn)).read_text(encoding="utf-8"))
            docs = set()
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                        and isinstance(getattr(n.body[0], "value", None), ast.Constant):
                    docs.add(id(n.body[0].value))                 # Docstrings sieht niemand
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                    m = ASCII_UMLAUT.search(n.value)
                    if m:
                        bad.append(f"{fn}:{n.lineno}: {m.group(0)!r} in {n.value[:60]!r}")
        self.assertEqual(bad, [], "ASCII-Umlaute in Texten:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
