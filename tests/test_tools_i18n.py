"""Tests: Englisch-Uebersetzung der Werkzeug-Tabs, Rechtsklick-Menues, Start-Tab, Tab-Navigation."""
import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()  # noqa: E702
import i18n_harvest as H
import tools_ctx as C
import tools_i18n as T
from tools_i18n_en import EN, SAME


class Lang:
    def __init__(self, lang):
        self.lang = lang

    def __enter__(self):
        self.old = T.lang()
        T.set_lang(self.lang)

    def __exit__(self, *a):
        T.set_lang(self.old)


# ---------------------------------------------------------------------------------------------
class Dictionary(unittest.TestCase):
    def test_german_passthrough_is_default(self):
        self.assertEqual(T.lang(), "de")
        self.assertEqual(T.translate("ATTACH first"), "ATTACH first")
        self.assertEqual(T.translate("Tabelle gespeichert: x"), "Tabelle gespeichert: x")

    def test_exact_fragment_and_whitespace(self):
        with Lang("en"):
            self.assertEqual(T.translate("WERT SUCHEN"), "FIND VALUE")
            self.assertEqual(T.translate("  WERT SUCHEN "), "  FIND VALUE ")
            self.assertEqual(T.translate("12 DataTables im Spiel - unten per Doppelklick lesen"),
                             "12 DataTables in the game - double-click one below to read it")
            self.assertEqual(T.translate("Spiel neu gestartet - neue PID 99; scans/debugger reset"),
                             "Game restarted - new PID 99; scans/debugger reset")

    def test_word_boundaries_protect_longer_words(self):
        with Lang("en"):
            self.assertEqual(T.translate("Mengenangabe"), "Mengenangabe")
            self.assertEqual(T.translate("Menge"), "Quantity")
            self.assertEqual(T.translate("Menge: 5"), "Quantity: 5")

    def test_non_strings_and_empty(self):
        with Lang("en"):
            self.assertEqual(T.translate(""), "")
            self.assertEqual(T.translate(None), None)
            self.assertEqual(T.translate(5), 5)

    def test_all_tab_names_and_start_texts_have_english(self):
        from tools_gui import ToolsWindow
        subs = tuple(label for g in ToolsWindow.GROUPS.values() for _inner, label in g)           # Unterreiter in UNREAL/UNITY
        for name in ToolsWindow.SIMPLE + ToolsWindow.ADVANCED + subs + ("START", "FORTGESCHRITTEN"):
            self.assertTrue(name in EN or name in SAME, name)
        with Lang("en"):
            self.assertEqual(T.translate("FORTGESCHRITTEN"), "ADVANCED")
            self.assertEqual(T.translate("★ UE-ENTDECKER"), "★ UE DISCOVERER")
            self.assertEqual(T.translate("ENTDECKER"), "DISCOVERER")

    def test_every_ui_string_in_the_tabs_is_translated(self):
        """Neue deutsche Texte in den Tabs ohne Eintrag in tools_i18n_en.py lassen diesen Test scheitern."""
        miss = H.missing(set(EN) | SAME)
        self.assertEqual(miss, [], f"{len(miss)} Text(e) ohne Uebersetzung, z. B. {miss[:5]}")

    def test_english_values_contain_no_umlauts_and_keep_format_placeholders(self):
        bad = [(k, v) for k, v in EN.items() if re.search("[äöüßÄÖÜ]", v)]
        self.assertEqual(bad, [])
        for k, v in EN.items():
            self.assertEqual(k.count("{}"), v.count("{}"), k)


# ---------------------------------------------------------------------------------------------
class W:
    """Fake-Widget mit der Tk-Schnittstelle, die tools_i18n.apply_to benutzt."""
    def __init__(self, cls, text="", children=(), **kw):
        self.cls, self.opts, self.kids = cls, {"text": text, **kw}, list(children)
        self.vars = {}
        self.tabs_ = {}
        self.heads = {}

    def winfo_children(self): return self.kids
    def winfo_class(self): return self.cls
    def cget(self, k): return self.opts.get(k, "")
    def configure(self, **kw): self.opts.update(kw)
    def getvar(self, n): return self.vars[n]
    def setvar(self, n, v): self.vars[n] = v
    def tabs(self): return list(self.tabs_)
    def tab(self, t, option=None, **kw):
        if kw:
            self.tabs_[t].update(kw)
        else:
            return self.tabs_[t][option]
    def heading(self, c, option=None, **kw):
        if kw:
            self.heads[c].update(kw)
        else:
            return self.heads[c][option]
    def title(self, v=None):
        if v is None:
            return self.opts["title"]
        self.opts["title"] = v


class Walker(unittest.TestCase):
    def tree(self):
        lbl = W("Label", "WERT SUCHEN")
        btn = W("Button", "ERSTER SCAN" if False else "FIRST SCAN")
        nb = W("TNotebook")
        nb.tabs_ = {"t1": {"text": "SPEICHER"}, "t2": {"text": "FORTGESCHRITTEN"}}
        tv = W("Treeview", columns=("a", "b"))
        tv.heads = {"a": {"text": "ADRESSE"}, "b": {"text": "WERT"}}
        vlab = W("Label", "", textvariable="PY_VAR1")
        vlab.vars["PY_VAR1"] = "nicht verbunden"
        entry = W("Entry", "WERT SUCHEN")                       # Eingabefelder bleiben unangetastet
        top = W("Toplevel", "", children=[lbl, btn, nb, tv, vlab, entry], title="REAPERPY  //  WERKZEUGE")
        return top, dict(lbl=lbl, btn=btn, nb=nb, tv=tv, vlab=vlab, entry=entry)

    def test_switch_to_english_and_back_restores_german(self):
        top, w = self.tree()
        with Lang("en"):
            T.apply_to(top)
            self.assertEqual(w["lbl"].opts["text"], "FIND VALUE")
            self.assertEqual(w["btn"].opts["text"], "FIRST SCAN")
            self.assertEqual([t["text"] for t in w["nb"].tabs_.values()], ["MEMORY", "ADVANCED"])
            self.assertEqual([h["text"] for h in w["tv"].heads.values()], ["ADRESSE", "WERT"][:0] or [T.translate("ADRESSE"), T.translate("WERT")])
            self.assertEqual(w["vlab"].vars["PY_VAR1"], T.translate("nicht verbunden"))
            self.assertEqual(w["entry"].opts["text"], "WERT SUCHEN")
            self.assertEqual(top.opts["title"], "REAPERPY  //  TOOLS")
        T.apply_to(top)                                         # zurueck auf Deutsch
        self.assertEqual(w["lbl"].opts["text"], "WERT SUCHEN")
        self.assertEqual([t["text"] for t in w["nb"].tabs_.values()], ["SPEICHER", "FORTGESCHRITTEN"])
        self.assertEqual(w["vlab"].vars["PY_VAR1"], "nicht verbunden")
        self.assertEqual(top.opts["title"], "REAPERPY  //  WERKZEUGE")

    def test_text_set_by_the_program_later_is_translated_again(self):
        top, w = self.tree()
        with Lang("en"):
            T.apply_to(top)
            w["lbl"].configure(text="HITS")                     # Code setzt neuen (deutschen) Text
            w["lbl"].configure(text="SPEICHER")
            T.apply_to(top)
            self.assertEqual(w["lbl"].opts["text"], "MEMORY")
        T.apply_to(top)
        self.assertEqual(w["lbl"].opts["text"], "SPEICHER")

    def test_broken_widgets_do_not_stop_the_walk(self):
        class Broken(W):
            def cget(self, k): raise RuntimeError("weg")
        good = W("Label", "WERT SUCHEN")
        top = W("Toplevel", "", children=[Broken("Label", "x"), good], title="x")
        with Lang("en"):
            T.apply_to(top)
        self.assertEqual(good.opts["text"], "FIND VALUE")

    def test_german_mode_changes_nothing(self):
        top, w = self.tree()
        T.apply_to(top)
        self.assertEqual(w["lbl"].opts["text"], "WERT SUCHEN")


class Hooks(unittest.TestCase):
    def test_var_hook_translates_only_in_english_and_is_idempotent(self):
        class V:
            def __init__(self): self.v = None
            def set(self, x): self.v = x
        T.install_var_hook(V)
        T.install_var_hook(V)
        v = V()
        v.set("nicht verbunden")
        self.assertEqual(v.v, "nicht verbunden")
        with Lang("en"):
            v.set("nicht verbunden")
            self.assertEqual(v.v, T.translate("nicht verbunden"))
            v.set("12")
            self.assertEqual(v.v, "12")                         # kurze Eingaben bleiben
            v.set(5)
            self.assertEqual(v.v, 5)

    def test_dialog_hooks_translate_title_and_message(self):
        seen = []
        mb = types.SimpleNamespace(showinfo=lambda title, message, **k: seen.append(("info", title, message)),
                                   askyesno=lambda title, message, **k: seen.append(("yn", title, message)) or True)
        sd = types.SimpleNamespace(askstring=lambda title, prompt, **k: seen.append(("s", title, prompt, k)) or "x")
        fd = types.SimpleNamespace(asksaveasfilename=lambda **k: seen.append(("f", k)) or "")
        T.install_dialog_hooks(mb, sd, fd)
        T.install_dialog_hooks(mb, sd, fd)
        with Lang("en"):
            mb.showinfo("Cheat editor", "Not a readable patch format: ")
            sd.askstring("Name des Eintrags", "Name des Trainer-Eintrags:", parent=1)
            fd.asksaveasfilename(title="Log speichern")
        self.assertEqual(seen[0], ("info", "Cheat editor", "Not a readable patch format: "))
        self.assertEqual(seen[1][1:3], ("Entry name", "Name of the trainer entry:"))
        self.assertEqual(seen[2][1]["title"], T.translate("Log speichern")) if False else None
        mb.showinfo("Bearbeiten", "Kein lesbares Patch-Format: ")
        self.assertEqual(seen[3][1:], ("Bearbeiten", "Kein lesbares Patch-Format: "))                     # Deutsch: unveraendert


# ---------------------------------------------------------------------------------------------
class FakeTree:
    def __init__(self, cols, rows, selected=()):
        self.cols, self.rows = cols, rows
        self.sel = list(selected)
        self.clip = ""
        self.sel_calls = []

    def __getitem__(self, k): return tuple(self.cols) if k == "columns" else None
    def identify_row(self, y): return str(y) if 0 <= y < len(self.rows) else ""
    def identify_column(self, x): return f"#{x}"
    def selection(self): return tuple(self.sel)
    def selection_set(self, *ids):
        ids = ids[0] if len(ids) == 1 and isinstance(ids[0], (list, tuple)) else ids
        self.sel = list(ids if isinstance(ids, (list, tuple)) else [ids])
    def get_children(self): return tuple(str(i) for i in range(len(self.rows)))
    def item(self, iid, k): return tuple(self.rows[int(iid)])
    def set(self, iid, col): return self.rows[int(iid)][self.cols.index(col)]
    def heading(self, c, k): return c.upper()
    def clipboard_clear(self): self.clip = ""
    def clipboard_append(self, t): self.clip += t


class ContextMenus(unittest.TestCase):
    def setUp(self):
        self.tv = FakeTree(["addr", "name"], [("0x401000", "Health"), ("7FFF0000", "Ammo")])

    def run_item(self, items, label):
        fn = dict(i for i in items if i[0])[label]
        fn()

    def test_tree_menu_copy_row_cell_and_csv(self):
        items = C.tree_items(self.tv, 2, 0)                         # Zeile 0, Spalte "name"
        self.assertEqual(self.tv.sel, ["0"])                        # Rechtsklick waehlt die Zeile
        labels = [i[0] for i in items]
        self.assertEqual(labels[:2], ["Zeile kopieren", "Zelle kopieren"])
        self.run_item(items, "Zeile kopieren")
        self.assertEqual(self.tv.clip, "0x401000\tHealth")
        self.run_item(items, "Zelle kopieren")
        self.assertEqual(self.tv.clip, "Health")
        self.run_item(items, "Alle Zeilen kopieren (CSV)")
        self.assertEqual(self.tv.clip, "ADDR,NAME\n0x401000,Health\n7FFF0000,Ammo\n")
        self.run_item(items, "Alles auswählen")
        self.assertEqual(len(self.tv.sel), 2)

    def test_tree_menu_goto_for_addresses_only_with_tools_window(self):
        calls = []
        win = types.SimpleNamespace(app=types.SimpleNamespace(IMAGE_BASE=0x400000), goto_memory=lambda a: calls.append(("mem", a)),
                                    goto_disasm=lambda a: calls.append(("dis", a)))
        items = C.tree_items(self.tv, 1, 0, win)                    # Spalte "addr"
        self.run_item(items, "Im Speicher öffnen")
        self.run_item(items, "Im Disassembler öffnen")
        self.assertEqual(calls, [("mem", 0x401000), ("dis", 0x401000)])
        self.assertNotIn("Im Speicher öffnen", [i[0] for i in C.tree_items(self.tv, 2, 0, win)])        # "Health" ist keine Adresse
        self.assertNotIn("Im Speicher öffnen", [i[0] for i in C.tree_items(self.tv, 1, 0, None)])

    def test_multiple_selection_copies_all_selected_rows(self):
        self.tv.sel = ["0", "1"]
        items = C.tree_items(self.tv, 1, 1)
        self.assertEqual(items[0][0], "Zeilen kopieren")
        items[0][1]()
        self.assertEqual(self.tv.clip, "0x401000\tHealth\n7FFF0000\tAmmo")

    def test_empty_tree_has_no_menu_items(self):
        self.assertEqual(C.tree_items(FakeTree(["a"], []), 1, 0), [])

    def test_address_detection(self):
        for t in ("0x401000", "7FFF0000", "base+0x10", "base - 0x20", "00000000004010A0"):
            self.assertTrue(C.looks_like_address(t), t)
        for t in ("Health", "1234", "", "+0x10", "hello world"):
            self.assertFalse(C.looks_like_address(t), t)
        self.assertEqual(C.addr_value("base+0x10", 0x400000), 0x400010)
        self.assertEqual(C.addr_value("7FFF0000"), 0x7FFF0000)

    def test_menu_labels_follow_language(self):
        with Lang("en"):
            labels = [i[0] for i in C.tree_items(self.tv, 2, 0)]
        self.assertEqual(labels[:2], ["Copy row", "Copy cell"])
        self.assertIn("Select all", labels)

    def test_entry_and_text_menus(self):
        events = []
        e = types.SimpleNamespace(event_generate=events.append, select_range=lambda *a: events.append(("sel", a)),
                                  icursor=lambda *a: None, cget=lambda k: "normal", delete=lambda *a: events.append(("del", a)))
        items = C.entry_items(e)
        self.assertEqual([i[0] for i in items if i[0]], ["Ausschneiden", "Kopieren", "Einfügen", "Alles markieren", "Feld leeren"])
        self.run_item(items, "Kopieren")
        self.run_item(items, "Feld leeren")
        self.assertEqual(events[0], "<<Copy>>")
        self.assertEqual(events[1], ("del", (0, "end")))
        ro = types.SimpleNamespace(event_generate=events.append, cget=lambda k: "disabled", tag_add=lambda *a: None, _is_log=True)
        labels = [i[0] for i in C.text_items(ro, save_dialog=lambda: None) if i[0]]
        self.assertEqual(labels, ["Kopieren", "Alles markieren", "Log leeren", "Log speichern…"])        # schreibgeschuetzt: kein Einfuegen
        rw = types.SimpleNamespace(event_generate=events.append, cget=lambda k: "normal", tag_add=lambda *a: None)
        self.assertEqual([i[0] for i in C.text_items(rw) if i[0]], ["Ausschneiden", "Kopieren", "Einfügen", "Alles markieren"])

    def test_widgets_with_own_menu_are_skipped(self):
        called = []
        orig = C.show_menu
        C.show_menu = lambda *a: called.append(1)
        try:
            ev = types.SimpleNamespace(widget=types.SimpleNamespace(_has_ctx=True), x=1, y=1)
            self.assertIsNone(C.on_tree(ev))
            self.assertIsNone(C.on_text(ev))
        finally:
            C.show_menu = orig
        self.assertEqual(called, [])

    def test_install_binds_classes_once(self):
        calls = []
        root = types.SimpleNamespace(bind_class=lambda cls, seq, fn, add=None: calls.append((cls, seq)))
        C.install(root)
        C.install(root)
        classes = {c for c, _s in calls}
        self.assertEqual(classes, {"Treeview", "Entry", "TEntry", "TCombobox", "Spinbox", "Text"})
        self.assertEqual({s for _c, s in calls}, {"<Button-3>", "<Button-2>"})
        self.assertEqual(len(calls), 2 * 6)


# ---------------------------------------------------------------------------------------------
class StartTabAndNavigation(unittest.TestCase):
    def make_start(self, connected=True, project="Super Game PPSA11111", n=3):
        import tools_start_gui as S
        shown = []
        app = types.SimpleNamespace(backend=types.SimpleNamespace(client=object() if connected else None, pid=4242 if connected else None),
                                    current_project=project, patches={i: 1 for i in range(n)},
                                    root=types.SimpleNamespace(deiconify=lambda: shown.append("deiconify"), lift=lambda: shown.append("lift"),
                                                               focus_force=lambda: shown.append("focus")))
        logs = []
        win = types.SimpleNamespace(app=app, show_tab=lambda t: shown.append(("tab", t)), scan_tab="SCAN", t_cheat="CHEAT",
                                    discover_tab="DISC", adv_frame="ADV", log=lambda m, k="info": logs.append((k, m)),
                                    ui=lambda fn: fn())
        t = S.StartTab(None, win)
        return t, shown, logs

    def test_status_text_variants(self):
        t, _s, _l = self.make_start()
        txt = t.status_text()
        self.assertIn("Verbunden mit der PS5", txt)
        self.assertIn("Codes: 3", txt)
        t, *_ = self.make_start(connected=False, project=None, n=0)
        txt = t.status_text()
        self.assertIn("Nicht verbunden", txt)
        self.assertIn("Keine Codes geladen", txt)
        t, *_ = self.make_start(project="Leer", n=0)
        self.assertIn("enthält aber keine Codes", t.status_text())

    def test_buttons_lead_to_the_right_tabs(self):
        t, shown, logs = self.make_start()
        for target, expect in (("scan_tab", "SCAN"), ("t_cheat", "CHEAT"), ("discover_tab", "DISC"), ("adv_frame", "ADV")):
            t.go(target)
            self.assertEqual(shown[-1], ("tab", expect))
        t.go("show_main")
        self.assertEqual(shown[-3:], ["deiconify", "lift", "focus"])
        t.go("gibt_es_nicht")
        self.assertEqual(logs[-1][0], "err")

    def test_start_tab_texts_are_translated(self):
        import tools_start_gui as S
        with Lang("en"):
            self.assertEqual(T.translate(S.STEPS[1][1][:30]), T.translate(S.STEPS[1][1][:30]))
            self.assertEqual(T.translate(S.STEPS[0][3]), "SHOW MAIN WINDOW")
            adv = next(e for e in S.EXTRAS if e[3] == "adv_frame")               # nicht vom Listen-Index abhaengig
            self.assertEqual(T.translate(adv[2]), "OPEN ADVANCED")
            items = next(e for e in S.EXTRAS if e[3] == "items_tab")
            self.assertEqual(T.translate(items[2]), "GO TO ITEMS")

    def test_show_tab_reaches_tabs_inside_advanced_notebook(self):
        from tools_gui import ToolsWindow
        sel = []
        nb = types.SimpleNamespace(select=lambda t: sel.append(("main", t)))
        adv = types.SimpleNamespace(select=lambda t: sel.append(("adv", t)))
        fake = types.SimpleNamespace(adv_nb=adv, nb=nb, adv_frame="FRAME")
        inner = types.SimpleNamespace(master=adv)
        outer = types.SimpleNamespace(master=nb)
        ToolsWindow.show_tab(fake, inner)
        ToolsWindow.show_tab(fake, outer)
        ToolsWindow.show_tab(fake, None)
        self.assertEqual(sel, [("main", "FRAME"), ("adv", inner), ("main", outer)])

    def test_tab_groups_are_consistent(self):
        from tools_gui import ToolsWindow
        self.assertFalse(set(ToolsWindow.SIMPLE) & set(ToolsWindow.ADVANCED))
        for needed in ("SPEICHER", "DEBUGGER", "DISASSEMBLER", "POINTER"):
            self.assertIn(needed, ToolsWindow.ADVANCED)
        for needed in ("WERT SUCHEN", "CHEATS BEARBEITEN", "★ UNREAL", "★ UNITY"):
            self.assertIn(needed, ToolsWindow.SIMPLE)
        # jeder Unterreiter gehoert genau einem Sammel-Tab und steht nicht noch einmal oben oder bei FORTGESCHRITTEN
        inner = [i for g in ToolsWindow.GROUPS.values() for i, _l in g]
        self.assertEqual(len(inner), len(set(inner)))
        self.assertFalse(set(inner) & (set(ToolsWindow.SIMPLE) | set(ToolsWindow.ADVANCED)))
        names = {i for i, _l in ToolsWindow.GROUPS["★ UNREAL"]}
        self.assertIn("★ UE-ENTDECKER", names)
        self.assertIn("UE-AUTO", names)
        self.assertTrue(all("UNITY" in i for i, _l in ToolsWindow.GROUPS["★ UNITY"]))
        self.assertEqual(ToolsWindow.GROUPED, set(inner))

    def test_show_tab_reaches_tabs_inside_unreal_and_unity_groups(self):
        from tools_gui import ToolsWindow
        sel = []
        nb = types.SimpleNamespace(select=lambda t: sel.append(("main", t)))
        gnb = types.SimpleNamespace(select=lambda t: sel.append(("group", t)))
        gnb.group = "UNREAL-FRAME"
        fake = types.SimpleNamespace(adv_nb=object(), nb=nb, adv_frame="FRAME")
        tab = types.SimpleNamespace(master=gnb)
        ToolsWindow.show_tab(fake, tab)
        self.assertEqual(sel, [("main", "UNREAL-FRAME"), ("group", tab)])


if __name__ == "__main__":
    unittest.main()


class ComboHook(unittest.TestCase):
    """Auswahllisten: im EN-Modus englisch angezeigt, der Code bekommt weiter die deutschen Originalwerte."""

    def setUp(self):
        import types
        T.set_lang("en")

        class Var:
            n = 0

            def __init__(self):
                Var.n += 1
                self._name = f"PY_VAR{Var.n}"
                self.v = ""

            def __str__(self):
                return self._name

            def set(self, v):
                self.v = v

            def get(self):
                return self.v

        class Combo:
            def __init__(self, master=None, **kw):
                self.kw = dict(kw)

            def configure(self, cnf=None, **kw):
                self.kw.update(cnf or {})
                self.kw.update(kw)

            config = configure

            def cget(self, k):
                return self.kw.get(k)

            def get(self):
                return self.kw["textvariable"].get()
        self.Var, self.Combo = Var, Combo
        T.install_var_hook(Var)
        T.install_combobox_hook(types.SimpleNamespace(Combobox=Combo))

    def tearDown(self):
        T.set_lang("de")

    def test_values_are_translated_and_get_returns_german(self):
        v = self.Var()
        cb = self.Combo(None, values=["Genau", "Größer als"], textvariable=v)
        self.assertEqual(cb.kw["values"], ("Exact", "Greater than"))
        v.set("Genau")                                  # Code setzt den deutschen Wert ...
        self.assertEqual(v.v, "Exact")                  # ... angezeigt wird englisch
        self.assertEqual(v.get(), "Genau")              # ... und der Code liest wieder den Originalwert
        self.assertEqual(cb.get(), "Genau")

    def test_values_set_later_are_translated_too(self):
        v = self.Var()
        cb = self.Combo(None, textvariable=v)
        cb.configure(values=["Zwischen", "Verändert"])
        self.assertEqual(cb.kw["values"], ("Between", "Changed"))

    def test_other_variables_are_not_reverse_translated(self):
        v, other = self.Var(), self.Var()
        self.Combo(None, values=["Genau"], textvariable=v)
        other.set("Exact")
        self.assertEqual(other.get(), "Exact")

    def test_german_mode_is_untouched(self):
        T.set_lang("de")
        v = self.Var()
        cb = self.Combo(None, values=["Genau"], textvariable=v)
        self.assertEqual(cb.kw["values"], ["Genau"])
