"""Englisch-Modus: Meldungen aus allen Modulen, Statuszeile, neue Fenster (Export-Dialog) - nichts bleibt still deutsch."""
import glob
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import i18n_harvest as H
import tools_i18n as T
from tools_i18n_en import EN, SAME

ROOT = os.path.join(os.path.dirname(__file__), "..")
GERMAN = re.compile(r"[äöüÄÖÜß]|\b(und|oder|nicht|kein|keine|Spiel|wird|fuer|für|mit|bitte|zuerst|gefunden|Fehler|Datei|"
                    r"Adresse|waehlen|wählen|schreiben|lesen|nach|aus|ein)\b", re.I)


class Lang:
    def __enter__(self):
        self.old = T.lang()
        T.set_lang("en")

    def __exit__(self, *a):
        T.set_lang(self.old)


class Backend(unittest.TestCase):
    def test_german_messages_in_all_modules_have_english(self):
        files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(ROOT, "*.py")))
        old = (H.FILES, H.CTX)
        H.FILES = files
        H.CTX = H.CTX + ("Toplevel", "Entry", "Text", "Combobox", "_say", "say", "Frame")
        try:
            miss = [(f, s) for f, s in H.missing(set(EN) | SAME) if GERMAN.search(s)]
        finally:
            H.FILES, H.CTX = old
        self.assertEqual(miss, [], f"{len(miss)} deutsche Meldung(en) ohne Englisch, z. B. {miss[:5]}")

    def test_status_line_and_export_dialog_texts(self):
        with Lang():
            self.assertEqual(T.translate("verbunden"), "connected")
            self.assertEqual(T.translate("nicht verbunden"), "not connected")
            self.assertEqual(T.translate("TITEL-ID/VERSION VOM SPIEL"), "TITLE ID/VERSION FROM GAME")
            self.assertEqual(T.translate("Spielname"), "Game name")
            self.assertEqual(T.translate("EXPORTIEREN ..."), "EXPORT ...")
            self.assertEqual(T.translate("Erkannt: PPSA13197  \"eboot.bin\"  Version 01.014.001"),
                             "Detected: PPSA13197  \"eboot.bin\"  Version 01.014.001")
            self.assertIn("must be running", T.translate(
                "Spiel muss laufen und ps5debug verbunden sein. Cave-Platz und Original-Bytes werden live aus dem Spiel gelesen."))
        self.assertEqual(T.translate("verbunden"), "verbunden")            # DE bleibt unveraendert

    def test_german_values_never_leak_umlauts_into_english(self):
        bad = [(k, v) for k, v in EN.items() if re.search("[äöüßÄÖÜ]", v)]
        self.assertEqual(bad, [])

    def test_dictionary_status_reports_entries(self):
        n, err = T.status()
        self.assertGreater(n, 1000)
        self.assertEqual(err, "")

    def test_toplevel_hook_translates_new_windows(self):
        import types
        applied = []

        class Top:
            def __init__(self, *a, **k):
                self.calls = []

            def after(self, ms, fn):
                self.calls.append(ms)
                fn()

            def winfo_exists(self):
                return True
        tk = types.SimpleNamespace(Toplevel=Top)
        old = T.apply_to
        T.apply_to = lambda w: applied.append(w)
        try:
            T.install_toplevel_hook(tk)
            T.install_toplevel_hook(tk)                  # idempotent
            with Lang():
                t = tk.Toplevel()
                self.assertEqual(t.calls, [60, 400, 1500])
            self.assertEqual(len(applied), 3)
            applied.clear()
            tk.Toplevel()                                # DE: nichts tun
            self.assertEqual(applied, [])
        finally:
            T.apply_to = old


if __name__ == "__main__":
    unittest.main()
