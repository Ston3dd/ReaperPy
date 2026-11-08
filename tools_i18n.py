"""tools_i18n.py - Deutsch -> Englisch fuer die Werkzeug-Tabs (greift, wenn im Hauptfenster auf EN geschaltet wird).

Die Tabs haben ihre Texte deutsch im Code.  Statt jede Stelle umzubauen, uebersetzt diese Schicht zur Laufzeit:
  translate(text)        ganze Texte ueber das Woerterbuch (tools_i18n_en.EN), sonst Bruchstuecke (laengste zuerst) -
                         so werden auch Meldungen mit eingesetzten Zahlen/Namen uebersetzt
  apply_to(root)         Widget-Baum durchgehen: Beschriftungen, Notebook-Reiter, Tabellen-Kopfzeilen, Label-Variablen;
                         merkt sich je Widget den deutschen Originaltext -> Rueckschalten auf DE stellt alles wieder her
  install_var_hook()     StringVar.set uebersetzt Statuszeilen, die der Code nach dem Umschalten setzt
  install_text_hooks()   configure(text=...), neue Widgets, Rechtsklick-Menues, Tabellen-Kopfzeilen und Reiter werden schon
                         beim Setzen uebersetzt (sonst stuende der deutsche Text bis zum naechsten 2-s-Durchlauf da)
  install_dialog_hooks() Titel/Text von Meldungs-, Eingabe- und Dateidialogen
Auf Deutsch (Standard) tun alle Funktionen nichts.
"""
import re

LANG = "de"
_cache = {}
_rx = None
_EN = None
MIN_FRAGMENT = 4


LOAD_ERROR = ""          # Text des Fehlers, falls tools_i18n_en nicht geladen werden konnte


def _dict():
    global _EN, LOAD_ERROR
    if _EN is None:
        try:
            from tools_i18n_en import EN
        except Exception as e:  # noqa: BLE001
            EN = {}
            LOAD_ERROR = f"{e.__class__.__name__}: {e}"      # sichtbar machen statt still alles deutsch zu lassen
        _EN = EN
    return _EN


def status():
    """-> (Anzahl Woerterbuch-Eintraege, Fehlertext) - leer/0 heisst: Englisch faellt still auf Deutsch zurueck."""
    return len(_dict()), LOAD_ERROR


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("de", "en") else "de"
    _cache.clear()


def lang():
    return LANG


def _regex():
    global _rx
    if _rx is None:
        keys = sorted((k for k in _dict() if len(k.strip()) >= MIN_FRAGMENT), key=len, reverse=True)
        L = "A-Za-zÄÖÜäöüß"

        def pat(k):                      # Bruchstuecke nur an Wortgrenzen ersetzen ('Menge' nicht in 'Mengenangabe')
            p = re.escape(k)
            if k[0].isalpha():
                p = f"(?<![{L}])" + p
            if k[-1].isalpha():
                p += f"(?![{L}])"
            return p
        _rx = re.compile("|".join(pat(k) for k in keys)) if keys else re.compile(r"(?!x)x")
    return _rx


def translate(text):
    """Deutscher Text -> englischer Text (nur im EN-Modus; sonst unveraendert)."""
    if LANG != "en" or not isinstance(text, str) or not text.strip():
        return text
    hit = _cache.get(text)
    if hit is not None:
        return hit
    en = _dict()
    if text in en:
        out = en[text]
    else:
        core = text.strip()
        if core in en:
            lead, trail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
            out = lead + en[core] + trail
        else:
            out = _regex().sub(lambda m: en[m.group(0)], text)
    _cache[text] = out
    return out


tr = translate


# --------------------------------------------------------------------------------------------------
# Widget-Baum
# --------------------------------------------------------------------------------------------------
TEXT_CLASSES = {"Label", "Button", "Checkbutton", "Radiobutton", "Labelframe", "TLabel", "TButton", "TCheckbutton",
                "TRadiobutton", "TLabelframe", "Menubutton", "TMenubutton"}
VAR_CLASSES = {"Label", "TLabel"}
MENU_LABEL_TYPES = {"command", "cascade", "checkbutton", "radiobutton"}
_TEXT_WIDGET_NAMES = {"label", "button", "checkbutton", "radiobutton", "labelframe", "menubutton"}    # ohne "ttk::"


# Rueckwaerts-Tabelle fuer Auswahllisten: angezeigter englischer Wert -> deutscher Originalwert.
# Der Code vergleicht/ordnet Combobox-Werte ueber die deutschen Texte (z. B. SCOPES[var.get()]); get() liefert deshalb
# im EN-Modus wieder das deutsche Original zurueck.
_REV = {}
_COMBO_VARS = set()    # Namen der StringVars, die an eine Combobox gebunden sind (nur dort wird get() zurueckuebersetzt)


def untranslate(text):
    return _REV.get(text, text) if isinstance(text, str) else text


def translate_values(values):
    """Werteliste einer Combobox uebersetzen (und die Rueckwaerts-Tabelle fuellen)."""
    if LANG != "en":
        return values
    try:
        seq = tuple(values)
    except TypeError:
        return values
    out = []
    for v in seq:
        if isinstance(v, str):
            en = translate(v)
            if en != v:
                _REV.setdefault(en, v)
            out.append(en)
        else:
            out.append(v)
    return tuple(out)


def _remember(w, slot, current):
    """Deutschen Originaltext zu `current` bestimmen: wurde der Text seit unserem letzten Setzen vom Programm geaendert,
    ist der neue Text das neue Original."""
    store = w.__dict__.setdefault("_i18n", {})
    orig, last = store.get(slot, (None, None))
    if orig is None or current != last:
        orig = current
    return store, orig


def _apply_text(w, slot, current, setter):
    store, orig = _remember(w, slot, current)
    new = translate(orig) if LANG == "en" else orig
    if new != current:
        setter(new)
    store[slot] = (orig, new)


_APPLYING = False        # True, solange apply_to selbst Texte setzt (die Hooks duerfen dann nichts aendern oder merken)


def apply_to(root):
    """Ganzen Widget-Baum unterhalb von root uebersetzen / zurueckstellen."""
    global _APPLYING
    _APPLYING = True
    try:
        _apply_to(root)
    finally:
        _APPLYING = False


def _apply_to(root):
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            stack.extend(w.winfo_children())
        except Exception:  # noqa: BLE001
            pass
        try:
            cls = w.winfo_class()
        except Exception:  # noqa: BLE001
            continue
        try:
            if cls in TEXT_CLASSES:
                tv = ""
                if cls in VAR_CLASSES:
                    try:
                        tv = str(w.cget("textvariable"))
                    except Exception:  # noqa: BLE001
                        tv = ""
                if tv:
                    cur = w.getvar(tv)
                    if isinstance(cur, str):
                        _apply_text(w, "var", cur, lambda v, w=w, tv=tv: w.setvar(tv, v))
                else:
                    cur = w.cget("text")
                    if isinstance(cur, str) and cur:
                        _apply_text(w, "text", cur, lambda v, w=w: w.configure(text=v))
            elif cls == "TCombobox":
                vals = tuple(str(x) for x in w.cget("values"))
                if vals:
                    store = w.__dict__.setdefault("_i18n", {})
                    orig, last = store.get("values", (None, None))
                    if orig is None or vals != last:
                        orig = tuple(untranslate(x) for x in vals)
                    new = translate_values(orig) if LANG == "en" else orig
                    if new != vals:
                        w.configure(values=new)
                    store["values"] = (orig, new)
                tv = str(w.cget("textvariable"))
                if tv:
                    _COMBO_VARS.add(tv)
                    cur = w.getvar(tv)
                    if isinstance(cur, str) and cur:
                        de = untranslate(cur)
                        new = translate(de) if LANG == "en" else de
                        if new != cur:
                            w.setvar(tv, new)
                            if new != de:
                                _REV.setdefault(new, de)
            elif cls == "Menu":
                last = w.index("end")
                if last is not None:
                    for i in range(int(last) + 1):
                        if w.type(i) in MENU_LABEL_TYPES:
                            cur = w.entrycget(i, "label")
                            if isinstance(cur, str) and cur:
                                _apply_text(w, f"menu:{i}", cur, lambda v, w=w, i=i: w.entryconfigure(i, label=v))
            elif cls == "TNotebook":
                for tab in w.tabs():
                    cur = w.tab(tab, "text")
                    _apply_text(w, f"tab:{tab}", cur, lambda v, w=w, tab=tab: w.tab(tab, text=v))
            elif cls == "Treeview":
                for col in [str(c) for c in w.cget("columns")]:
                    cur = w.heading(col, "text")
                    _apply_text(w, f"col:{col}", cur, lambda v, w=w, col=col: w.heading(col, text=v))
            elif cls in ("Toplevel", "Tk"):
                cur = w.title()
                _apply_text(w, "title", cur, lambda v, w=w: w.title(v))
        except Exception:  # noqa: BLE001 - ein kaputtes Widget darf die Uebersetzung nicht stoppen
            continue


# --------------------------------------------------------------------------------------------------
# Variablen und Dialoge
# --------------------------------------------------------------------------------------------------
def install_var_hook(var_cls):
    """var_cls.set uebersetzt Texte, die der Code spaeter setzt (Statuszeilen).  Idempotent."""
    if getattr(var_cls, "_i18n_hooked", False):
        return
    orig = var_cls.set

    orig_get = getattr(var_cls, "get", None)

    def set_(self, value):
        if LANG == "en" and isinstance(value, str) and len(value) >= MIN_FRAGMENT:
            en = translate(value)
            if en != value and str(self) in _COMBO_VARS:
                _REV.setdefault(en, value)
            value = en
        return orig(self, value)

    def get_(self):
        v = orig_get(self)
        return _REV.get(v, v) if LANG == "en" and isinstance(v, str) and str(self) in _COMBO_VARS else v
    var_cls.set = set_
    if orig_get is not None:
        var_cls.get = get_
    var_cls._i18n_hooked = True


def install_toplevel_hook(tk_mod):
    """Jedes neue Fenster (Export-Dialog, Auswahl-Dialoge ...) wird im EN-Modus nach dem Aufbau uebersetzt.  Idempotent."""
    top = tk_mod.Toplevel
    if getattr(top, "_i18n_hooked", False):
        return
    orig = top.__init__

    def init(self, *a, **kw):
        orig(self, *a, **kw)
        if LANG == "en":
            for ms in (60, 400, 1500):                    # die Widgets entstehen erst nach __init__
                try:
                    self.after(ms, lambda: apply_to(self) if self.winfo_exists() and LANG == "en" else None)
                except Exception:  # noqa: BLE001
                    break
    top.__init__ = init
    top._i18n_hooked = True


def install_combobox_hook(ttk_mod):
    """Auswahllisten (ttk.Combobox): values werden im EN-Modus uebersetzt, get() liefert das deutsche Original.  Idempotent."""
    cb = ttk_mod.Combobox
    if getattr(cb, "_i18n_hooked", False):
        return
    orig_init, orig_conf, orig_get = cb.__init__, cb.configure, cb.get

    def _tv(self, vals):
        if LANG != "en":
            return vals
        orig = tuple(untranslate(x) for x in vals) if not isinstance(vals, str) else vals
        new = translate_values(orig)
        if not isinstance(vals, str):
            self.__dict__.setdefault("_i18n", {})["values"] = (orig, new)
        return new

    def init(self, master=None, **kw):
        tvar = kw.get("textvariable")
        if tvar is not None:
            _COMBO_VARS.add(str(tvar))
        if "values" in kw:
            vals = kw["values"]
            self.__dict__.setdefault("_i18n", {})
            kw["values"] = _tv(self, vals)
        orig_init(self, master, **kw)

    def conf(self, cnf=None, **kw):
        if isinstance(cnf, dict) and "values" in cnf:
            cnf = dict(cnf)
            cnf["values"] = _tv(self, cnf["values"])
        if "values" in kw:
            kw["values"] = _tv(self, kw["values"])
        return orig_conf(self, cnf, **kw)

    def get(self):
        v = orig_get(self)
        return _REV.get(v, v) if LANG == "en" and isinstance(v, str) else v
    cb.__init__, cb.configure, cb.config, cb.get = init, conf, conf, get
    cb._i18n_hooked = True


def _tr_set(w, slot, text):
    """Text sofort uebersetzen und das deutsche Original merken (damit Rueckschalten auf DE funktioniert).  -> (neuer Text, Original)"""
    if LANG != "en" or _APPLYING or not isinstance(text, str) or len(text) < MIN_FRAGMENT:
        return text, None
    return translate(text), text


def install_text_hooks(tk_mod, ttk_mod=None):
    """Texte werden schon beim Setzen uebersetzt, nicht erst beim naechsten Durchlauf von apply_to:
       - neue Widgets (Label, Button, ...) und configure(text=...)  -> kein kurzes Aufblitzen von Deutsch nach einer Suche
       - Rechtsklick-Menues (Menu.add/insert/entryconfigure)         -> Menues werden von apply_to nicht erreicht, solange sie neu entstehen
       - Tabellen-Kopfzeilen (Treeview.heading) und Reiter (Notebook.add/tab)
    Jede Aenderung faellt bei einem Fehler auf das unveraenderte Verhalten zurueck.  Idempotent; ohne echtes tkinter (Tests) wirkungslos."""
    misc = getattr(tk_mod, "Misc", None)
    base = getattr(tk_mod, "BaseWidget", None)
    if misc is None or base is None or getattr(misc, "_i18n_text_hooked", False):
        return
    orig_conf, orig_init = misc.configure, base.__init__

    def _is_text_widget(w):
        try:
            return w.winfo_class() in TEXT_CLASSES
        except Exception:  # noqa: BLE001
            return False

    def conf(self, cnf=None, **kw):
        de = None
        try:
            if LANG == "en" and not _APPLYING:
                src = kw if isinstance(kw.get("text"), str) else (cnf if isinstance(cnf, dict) and isinstance(cnf.get("text"), str) else None)
                if src is not None and _is_text_widget(self):
                    en, de = _tr_set(self, "text", src["text"])
                    if de is not None:
                        if src is kw:
                            kw = dict(kw, text=en)
                        else:
                            cnf = dict(cnf, text=en)
        except Exception:  # noqa: BLE001
            de = None
        res = orig_conf(self, cnf, **kw)
        if de is not None:
            self.__dict__.setdefault("_i18n", {})["text"] = (de, (kw if "text" in kw else cnf)["text"])
        return res

    def init(self, master, widgetName, cnf={}, kw={}, extra=()):  # noqa: B006 - Signatur wie tkinter.BaseWidget
        de, new = None, None
        try:
            if LANG == "en" and not _APPLYING and str(widgetName).split("::")[-1].lower() in _TEXT_WIDGET_NAMES:
                for d in (kw, cnf):
                    if isinstance(d, dict) and isinstance(d.get("text"), str):
                        new, de = _tr_set(None, "text", d["text"])
                        if de is not None:
                            if d is kw:
                                kw = dict(kw, text=new)
                            else:
                                cnf = dict(cnf, text=new)
                        break
        except Exception:  # noqa: BLE001
            de = None
        orig_init(self, master, widgetName, cnf, kw, extra)
        if de is not None:
            self.__dict__.setdefault("_i18n", {})["text"] = (de, new)

    misc.configure = misc.config = conf
    base.__init__ = init

    menu = getattr(tk_mod, "Menu", None)
    if menu is not None and not getattr(menu, "_i18n_text_hooked", False):
        o_add, o_ins, o_cfg = menu.add, menu.insert, menu.entryconfigure

        def _label(d_cnf, kw):
            """-> (cnf, kw, deutscher Text oder None) mit uebersetztem label."""
            try:
                if LANG == "en" and not _APPLYING:
                    for key in ("kw", "cnf"):
                        d = kw if key == "kw" else d_cnf
                        if isinstance(d, dict) and isinstance(d.get("label"), str):
                            en, de = _tr_set(None, "label", d["label"])
                            if de is not None:
                                d = dict(d, label=en)
                                return (d_cnf, d, de, en) if key == "kw" else (d, kw, de, en)
                            break
            except Exception:  # noqa: BLE001
                pass
            return d_cnf, kw, None, None

        def add(self, itemType, cnf={}, **kw):  # noqa: B006
            cnf, kw, de, en = _label(cnf, kw)
            res = o_add(self, itemType, cnf, **kw)
            if de is not None:
                try:
                    self.__dict__.setdefault("_i18n", {})[f"menu:{int(self.index('end'))}"] = (de, en)
                except Exception:  # noqa: BLE001
                    pass
            return res

        def insert(self, index, itemType, cnf={}, **kw):  # noqa: B006
            cnf, kw, _de, _en = _label(cnf, kw)
            return o_ins(self, index, itemType, cnf, **kw)

        def entryconfigure(self, index, cnf=None, **kw):
            cnf2, kw, de, en = _label(cnf if isinstance(cnf, dict) else {}, kw)
            if isinstance(cnf, dict):
                cnf = cnf2
            res = o_cfg(self, index, cnf, **kw)
            if de is not None:
                try:
                    self.__dict__.setdefault("_i18n", {})[f"menu:{int(self.index(index))}"] = (de, en)
                except Exception:  # noqa: BLE001
                    pass
            return res
        menu.add, menu.insert, menu.entryconfigure, menu.entryconfig = add, insert, entryconfigure, entryconfigure
        menu._i18n_text_hooked = True

    tv = getattr(ttk_mod, "Treeview", None) if ttk_mod is not None else None
    if tv is not None and not getattr(tv, "_i18n_text_hooked", False):
        o_head = tv.heading

        def heading(self, column, option=None, **kw):
            de = en = None
            try:
                if "text" in kw:
                    en, de = _tr_set(self, "col", kw["text"])
                    if de is not None:
                        kw = dict(kw, text=en)
            except Exception:  # noqa: BLE001
                de = None
            res = o_head(self, column, option, **kw)
            if de is not None and isinstance(column, str):
                self.__dict__.setdefault("_i18n", {})[f"col:{column}"] = (de, en)
            return res
        tv.heading = heading
        tv._i18n_text_hooked = True

    nb = getattr(ttk_mod, "Notebook", None) if ttk_mod is not None else None
    if nb is not None and not getattr(nb, "_i18n_text_hooked", False):
        o_nadd = nb.add

        def nadd(self, child, **kw):
            de = en = None
            try:
                if "text" in kw:
                    en, de = _tr_set(self, "tab", kw["text"])
                    if de is not None:
                        kw = dict(kw, text=en)
            except Exception:  # noqa: BLE001
                de = None
            res = o_nadd(self, child, **kw)
            if de is not None:
                self.__dict__.setdefault("_i18n", {})[f"tab:{child}"] = (de, en)
            return res
        nb.add = nadd
        nb._i18n_text_hooked = True

    misc._i18n_text_hooked = True


def install_dialog_hooks(messagebox, simpledialog, filedialog):
    """Titel/Meldung/Aufforderung der Standarddialoge uebersetzen.  Idempotent."""
    def wrap(mod, name, text_args):
        fn = getattr(mod, name, None)
        if fn is None or getattr(fn, "_i18n", False):
            return

        def w(*args, **kw):
            args = list(args)
            for i in text_args:
                if i < len(args) and isinstance(args[i], str):
                    args[i] = translate(args[i])
            for k in ("title", "message", "prompt"):
                if isinstance(kw.get(k), str):
                    kw[k] = translate(kw[k])
            return fn(*args, **kw)
        w._i18n = True
        setattr(mod, name, w)
    for n in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askyesnocancel", "askretrycancel"):
        wrap(messagebox, n, (0, 1))
    for n in ("askstring", "askinteger", "askfloat"):
        wrap(simpledialog, n, (0, 1))
    for n in ("askopenfilename", "asksaveasfilename", "askdirectory", "askopenfilenames"):
        wrap(filedialog, n, ())
