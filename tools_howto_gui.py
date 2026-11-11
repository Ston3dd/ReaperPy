"""tools_howto_gui.py - Fenster "ANLEITUNGEN": Schritt-fuer-Schritt-Erklaerungen fuer Einsteiger.

Das Fenster wird vom Hauptfenster (Knopf ANLEITUNGEN) und vom Knopf "? HILFE" im Werkzeug-Fenster geoeffnet.

Links die Liste der Anleitungen (oder die Suchtreffer), rechts der Text.  Die Dateien liegen in docs/howto/de und docs/howto/en
(siehe howto.py); angezeigt wird die Sprache des Programms und beim Umschalten DE / EN sofort die andere.
"""
import tkinter as tk
from tkinter import ttk

import howto
import theme
import tools_i18n
from tools_common import (ACCENT, BG, BG_BAR, BG_CARD, BG_LOG, BORDER, FONT_HEAD, FONT_LABEL, SELECT, TEXT, TEXT_DIM,
                          WARN, BaseTab, entry, style_ttk)

BODY = ("Consolas", 10)
BODY_B = ("Consolas", 10, "bold")
BODY_I = ("Consolas", 10, "italic")
H1 = ("Consolas", 15, "bold")
H2 = ("Consolas", 12, "bold")
H3 = ("Consolas", 10, "bold")
START_TOPIC = "first-steps"


class HowToTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.root_dir = None                      # Tests: anderer Ordner mit Anleitungen
        self._lang = tools_i18n.lang()
        self._slug = None
        self._shown = []                          # slugs der Zeilen in der Liste
        self.v_search = tk.StringVar(value="")
        self.v_found = tk.StringVar(value="")

        tk.Label(self, text="ANLEITUNGEN", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(self, text="Schritt für Schritt erklärt - die Sprache folgt der Umschaltung DE / EN.", bg=BG, fg=TEXT_DIM,
                 font=FONT_LABEL).pack(anchor="w", padx=16)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)
        left = tk.Frame(body, bg=BG, width=270)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        row = tk.Frame(left, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="Suchen:", bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left")
        self.e_search = entry(row, self.v_search, width=24)
        self.e_search.pack(side="left", padx=8, fill="x", expand=True)
        tk.Label(left, textvariable=self.v_found, bg=BG, fg=TEXT_DIM, font=FONT_LABEL, anchor="w").pack(fill="x", pady=(4, 2))
        self.lb = tk.Listbox(left, bg=BG_CARD, fg=TEXT, selectbackground=SELECT, selectforeground=TEXT, activestyle="none",
                             relief="flat", highlightthickness=1, highlightbackground=BORDER, font=BODY, exportselection=False)
        self.lb.pack(fill="both", expand=True)
        self.lb.bind("<<ListboxSelect>>", self._on_pick)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.txt = tk.Text(right, wrap="word", bg=BG_CARD, fg=TEXT, insertbackground=TEXT, relief="flat", padx=16, pady=12,
                           font=BODY, highlightthickness=1, highlightbackground=BORDER, cursor="arrow", spacing1=2, spacing3=2)
        sb = ttk.Scrollbar(right, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        self._tags()

        self.v_search.trace_add("write", lambda *_a: self.refresh_list())
        self.refresh_list()
        self.show(START_TOPIC)
        self.after(1000, self._tick)

    # ---- Darstellung ----------------------------------------------------------------------------------
    def _tags(self):
        t = self.txt
        t.tag_configure("h1", font=H1, foreground=ACCENT, spacing1=6, spacing3=8)
        t.tag_configure("h2", font=H2, foreground=ACCENT, spacing1=16, spacing3=4)
        t.tag_configure("h3", font=H3, foreground=TEXT, spacing1=10, spacing3=2)
        t.tag_configure("b", font=BODY_B)
        t.tag_configure("i", font=BODY_I)
        t.tag_configure("code", font=BODY, foreground=ACCENT, background=BG_LOG)
        t.tag_configure("li", lmargin1=18, lmargin2=36, spacing1=2)
        t.tag_configure("codeblock", font=BODY, foreground=ACCENT, background=BG_LOG, lmargin1=14, lmargin2=14, rmargin=14,
                        spacing1=1, spacing3=1)
        t.tag_configure("tip", background=theme.ACCENT_BG, lmargin1=10, lmargin2=10, rmargin=10, spacing1=6, spacing3=6)
        t.tag_configure("note", background=BG_BAR, lmargin1=10, lmargin2=10, rmargin=10, spacing1=6, spacing3=6)
        t.tag_configure("warn", background=theme.CALLOUT_WARN_BG, foreground=WARN, lmargin1=10, lmargin2=10, rmargin=10,
                        spacing1=6, spacing3=6)
        t.tag_configure("hit", background=SELECT)
        t.tag_configure("rule", font=("Consolas", 4), background=BORDER)

    def _link(self, slug):
        name = "link:" + slug
        t = self.txt
        if name not in t.tag_names():
            t.tag_configure(name, foreground=ACCENT, underline=True)
            t.tag_bind(name, "<Button-1>", lambda _e, s=slug: self.show(s))
            t.tag_bind(name, "<Enter>", lambda _e: t.configure(cursor="hand2"))
            t.tag_bind(name, "<Leave>", lambda _e: t.configure(cursor="arrow"))
        return name

    def _put(self, spans, base=()):
        for text, style in spans:
            tags = list(base)
            if style.startswith("link:"):
                tags.append(self._link(style[5:]))
            elif style:
                tags.append(style)
            self.txt.insert("end", text, tuple(tags))

    def render(self, md, words=()):
        t = self.txt
        t.configure(state="normal")
        t.delete("1.0", "end")
        for kind, content in howto.parse(md):
            if kind in ("h1", "h2", "h3"):
                self._put(content, (kind,))
                t.insert("end", "\n", (kind,))
            elif kind == "p":
                self._put(content)
                t.insert("end", "\n\n")
            elif kind in ("ul", "ol"):
                for n, item in enumerate(content, 1):
                    t.insert("end", ("  •  " if kind == "ul" else f"  {n}.  "), ("li",))
                    self._put(item, ("li",))
                    t.insert("end", "\n", ("li",))
                t.insert("end", "\n")
            elif kind == "code":
                for line in content.split("\n"):
                    t.insert("end", " " + line + " \n", ("codeblock",))
                t.insert("end", "\n")
            elif kind in ("tip", "note", "warn"):
                self._put(content, (kind,))
                t.insert("end", "\n\n", (kind,))
            elif kind == "hr":
                t.insert("end", " \n", ("rule",))
        for w in words:
            self._mark(w)
        t.configure(state="disabled")
        t.yview_moveto(0)

    def _mark(self, word):
        t = self.txt
        start = "1.0"
        first = None
        while True:
            pos = t.search(word, start, stopindex="end", nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(word)}c"
            t.tag_add("hit", pos, end)
            first = first or pos
            start = end
        if first:
            t.see(first)

    # ---- Liste / Suche --------------------------------------------------------------------------------
    def refresh_list(self):
        query = self.v_search.get().strip()
        lang = tools_i18n.lang()
        self.lb.delete(0, "end")
        self._shown = []
        if query:
            hits = howto.search(query, lang, self.root_dir)
            for h in hits:
                self.lb.insert("end", h["title"])
                self._shown.append(h["slug"])
            self.v_found.set(f"{len(hits)} Treffer" if hits else "Keine Treffer")
        else:
            for a in howto.articles(lang, self.root_dir):
                self.lb.insert("end", a["title"])
                self._shown.append(a["slug"])
            self.v_found.set("")
        self._select_current()

    def _select_current(self):
        self.lb.selection_clear(0, "end")
        if self._slug in self._shown:
            i = self._shown.index(self._slug)
            self.lb.selection_set(i)
            self.lb.see(i)

    def _on_pick(self, _e=None):
        sel = self.lb.curselection()
        if sel and sel[0] < len(self._shown):
            self.show(self._shown[sel[0]], keep_list=True)

    def show(self, slug, keep_list=False):
        """Anleitung anzeigen (Sprache des Programms); die Suchwoerter werden markiert."""
        lang = tools_i18n.lang()
        try:
            md = howto.load(slug, lang, self.root_dir)
        except KeyError:
            self.log(f"Anleitung nicht gefunden: {slug}", "err")
            return
        self._slug, self._lang = slug, lang
        words = [w for w in self.v_search.get().lower().split() if w] if keep_list else ()
        self.render(md, words)
        if not keep_list:
            self._select_current()

    def focus_search(self):
        self.e_search.focus_set()

    def _tick(self):
        """Sprache umgeschaltet (DE <-> EN)?  Dann Liste und Anleitung neu laden."""
        try:
            if not self.winfo_exists():
                return
            if tools_i18n.lang() != self._lang:
                self.refresh_list()
                self.show(self._slug or START_TOPIC, keep_list=bool(self.v_search.get().strip()))
            self.after(1000, self._tick)
        except Exception:  # noqa: BLE001
            pass


class HowToWindow(tk.Toplevel):
    """Eigenes Fenster mit den Anleitungen - braucht keine Verbindung zur PS5."""

    def __init__(self, app, slug=None):
        super().__init__(app.root)
        try:
            import branding
            branding.apply_icon_to(self, app.root)
        except Exception:  # noqa: BLE001 - das Symbol ist nur Zierde
            pass
        self.app = app
        self.title("REAPERPY  //  ANLEITUNGEN")
        self.configure(bg=BG)
        self.geometry("1000x720")
        style_ttk(self)
        self._i18n_tick = False
        self.tab = HowToTab(self, self)
        self.tab.pack(fill="both", expand=True)
        if slug:
            self.tab.show(slug)
        self.apply_language()

    def log(self, msg, kind="info"):
        self.app.log_msg(msg, kind)

    def show(self, slug=None):
        """Fenster nach vorne holen, mit slug direkt diese Anleitung zeigen."""
        if slug:
            self.tab.show(slug)
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:  # noqa: BLE001
            pass

    def apply_language(self):
        """Sprache des Hauptfensters (DE / EN) uebernehmen; im EN-Modus alle 2 s nachziehen (Texte, die spaeter gesetzt werden)."""
        try:
            if not self.winfo_exists():
                return
            tools_i18n.apply_to(self)
            if tools_i18n.lang() == "en" and not self._i18n_tick:
                self._i18n_tick = True
                self.after(2000, self._i18n_loop)
        except Exception:  # noqa: BLE001
            pass

    def _i18n_loop(self):
        self._i18n_tick = False
        try:
            if self.winfo_exists() and tools_i18n.lang() == "en":
                self.apply_language()
        except Exception:  # noqa: BLE001
            pass
