"""tools_common.py – Theme + Hilfen für das Werkzeug-Fenster."""
import re
import tkinter as tk
from tkinter import ttk

BG          = "#06080d"
BG_BAR      = "#0a0f18"
BG_CARD     = "#0e1420"
BG_CARD_HVR = "#161f30"
BORDER      = "#182130"
BORDER_HVR  = "#2a3950"
ACCENT      = "#00ffc8"
ACCENT_DIM  = "#008a6a"
TEXT        = "#e6edf3"
TEXT_DIM    = "#7d8590"
WARN        = "#ffb000"
ERROR       = "#ff3366"

FONT_MONO  = ("Consolas", 10)
FONT_LABEL = ("Consolas", 9)
FONT_HEAD  = ("Consolas", 11, "bold")


def style_ttk(root):
    """Dunkles ttk-Theme. Wird vom Hauptfenster UND vom Werkzeug-Fenster aufgerufen (idempotent)."""
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    # tk-Widgets zeigen sonst einen hellen Fokus-/Highlight-Rahmen in Systemfarbe
    for w in ("Button", "Checkbutton", "Radiobutton"):
        root.option_add(f"*{w}.highlightThickness", 0)
    st.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BORDER,
                 lightcolor=BG, darkcolor=BG)
    st.configure("TNotebook.Tab", background=BG_CARD, foreground=TEXT_DIM,
                 padding=(14, 6), font=FONT_LABEL, borderwidth=0, bordercolor=BORDER,
                 lightcolor=BG_CARD, darkcolor=BG_CARD)
    st.map("TNotebook.Tab",
           background=[("selected", BG_CARD_HVR)],
           foreground=[("selected", ACCENT)])
    st.configure("Treeview", background=BG_CARD, fieldbackground=BG_CARD,
                 foreground=TEXT, font=FONT_MONO, rowheight=20, borderwidth=0,
                 bordercolor=BORDER, lightcolor=BG_CARD, darkcolor=BG_CARD)
    st.configure("Treeview.Heading", background=BG_BAR, foreground=ACCENT_DIM,
                 font=FONT_LABEL, borderwidth=0, bordercolor=BORDER,
                 lightcolor=BG_BAR, darkcolor=BG_BAR)
    st.map("Treeview", background=[("selected", BORDER_HVR)],
           foreground=[("selected", ACCENT)])

    # --- Combobox -------------------------------------------------------
    # clam malt eine readonly-Combobox mit hellgrauem Feld; mit heller Schrift (TEXT) war der Inhalt
    # (Int32, Genau, ...) unlesbar. Alle Zustände explizit auf das dunkle Theme mappen.
    st.configure("TCombobox", fieldbackground=BG_CARD, background=BG_CARD,
                 foreground=TEXT, arrowcolor=ACCENT, bordercolor=BORDER,
                 lightcolor=BG_CARD, darkcolor=BG_CARD, insertcolor=ACCENT,
                 selectbackground=BG_CARD, selectforeground=TEXT, padding=3)
    st.map("TCombobox",
           fieldbackground=[("readonly", BG_CARD), ("disabled", BG_BAR), ("active", BG_CARD_HVR)],
           background=[("readonly", BG_CARD), ("active", BG_CARD_HVR), ("pressed", BG_CARD_HVR)],
           foreground=[("readonly", TEXT), ("disabled", TEXT_DIM)],
           selectbackground=[("readonly", BG_CARD), ("focus", BG_CARD)],
           selectforeground=[("readonly", TEXT), ("focus", TEXT)],
           bordercolor=[("focus", ACCENT_DIM), ("active", BORDER_HVR)],
           arrowcolor=[("disabled", TEXT_DIM), ("active", ACCENT)])
    # Dropdown-Liste (ein klassisches tk.Listbox)
    for opt, val in (("background", BG_CARD), ("foreground", TEXT),
                     ("selectBackground", BORDER_HVR), ("selectForeground", ACCENT),
                     ("font", FONT_MONO)):
        root.option_add(f"*TCombobox*Listbox.{opt}", val)

    st.configure("Vertical.TScrollbar", background=BG_CARD, troughcolor=BG,
                 arrowcolor=TEXT_DIM, bordercolor=BG, lightcolor=BG_CARD,
                 darkcolor=BG_CARD, borderwidth=0, relief="flat")
    st.map("Vertical.TScrollbar", background=[("active", BORDER_HVR)])
    st.configure("Horizontal.TProgressbar", troughcolor=BG_CARD, background=ACCENT,
                 bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT_DIM, thickness=6)
    st.configure("Reaper.Horizontal.TProgressbar", troughcolor=BG_BAR, background=ACCENT,
                 bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT_DIM, thickness=3)


def button(parent, text, cmd, accent=False, **kw):
    return tk.Button(parent, text=text, command=cmd, bg=BG_CARD,
                     fg=ACCENT if accent else TEXT, font=FONT_LABEL, relief="flat",
                     bd=0, padx=10, pady=4, cursor="hand2", highlightthickness=0,
                     activebackground=BG_CARD_HVR, activeforeground=ACCENT, **kw)


def label(parent, text, dim=True, **kw):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_DIM if dim else TEXT,
                    font=FONT_LABEL, **kw)


def entry(parent, var=None, width=18, **kw):
    return tk.Entry(parent, textvariable=var, width=width, bg=BG_CARD, fg=TEXT,
                    insertbackground=ACCENT, relief="flat", font=FONT_MONO,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT_DIM, disabledbackground=BG_BAR,
                    disabledforeground=TEXT_DIM, readonlybackground=BG_BAR, **kw)


def textbox(parent, height=8, width=40, **kw):
    return tk.Text(parent, height=height, width=width, bg=BG_CARD, fg=TEXT,
                   insertbackground=ACCENT, relief="flat", font=FONT_MONO,
                   highlightthickness=1, highlightbackground=BORDER,
                   highlightcolor=ACCENT_DIM, wrap="none", undo=True, **kw)


def tree(parent, columns, widths, height=12, anchors=None, actions=None, details=None):
    """Treeview mit Spalten.  Optional:
    actions  - Liste (Text, Funktion) fuer das Rechtsklick-Menue; (None, None) = Trennlinie.
    details  - Funktion(iid) -> Liste (Name, Wert); wird im Menuepunkt "Eigenschaften..." angehaengt.
    """
    t = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings",
                     height=height, selectmode="extended")
    for i, (key, title) in enumerate(columns):
        t.heading(key, text=title)
        t.column(key, width=widths[i], anchor=(anchors or {}).get(key, "w"),
                 stretch=(i == len(columns) - 1))
    if actions or details:
        _attach_context_menu(t, columns, actions or [], details)
    return t


def row_properties(table, columns, iid, details=None):
    """Eigenschaften einer Zeile als [(Titel, Wert)].  Leere Symbol-Spalten (z.B. ❄) entfallen;
    details(iid) darf weitere (Name, Wert)-Paare liefern."""
    vals = tuple(table.item(iid, "values"))
    out = []
    for i, (_key, title) in enumerate(columns):
        v = vals[i] if i < len(vals) else ""
        v = "" if v is None else str(v)
        if v == "" and not any(ch.isalnum() for ch in str(title)):
            continue
        out.append((str(title), v))
    if details:
        out.extend((str(k), str(v)) for k, v in details(iid))
    return out


def _attach_context_menu(t, columns, actions, details):
    def show_props(iid):
        from tkinter import messagebox
        try:
            text = "\n".join(f"{k}:  {v}" for k, v in row_properties(t, columns, iid, details))
        except Exception as e:
            text = f"Keine Eigenschaften: {e}"
        messagebox.showinfo("Eigenschaften", text, parent=t)

    def popup(event):
        m = None
        try:
            iid = t.identify_row(event.y)
            if iid and iid not in t.selection():
                t.selection_set(iid)
            m = tk.Menu(t, tearoff=0, bg=BG_CARD, fg=TEXT, activebackground=BG_CARD_HVR,
                        activeforeground=ACCENT)
            for text, fn in actions:
                if text is None:
                    m.add_separator()
                else:
                    m.add_command(label=text, command=fn)
            if iid:
                if actions:
                    m.add_separator()
                m.add_command(label="Eigenschaften...", command=lambda: show_props(iid))
            m.tk_popup(event.x_root, event.y_root)
        finally:
            if m is not None:
                try:
                    m.grab_release()
                except Exception:
                    pass

    t.bind("<Button-3>", popup)
    t._has_ctx = True


def with_scroll(parent, widget):
    """Widget + vertikale Scrollbar nebeneinander packen (widget bekommt den Platz)."""
    sb = ttk.Scrollbar(parent, orient="vertical", command=widget.yview)
    widget.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    widget.pack(side="left", fill="both", expand=True)
    return sb


def parse_addr(text, base=0):
    """'0x4A9093', '4a9093', 'base+0xAA9093', 'base - 10' -> int."""
    t = text.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("Adresse leer")
    t = t.replace("base", f"0x{base:x}")
    parts = re.findall(r"([+-]?)(0x[0-9a-f]+|[0-9a-f]+)", t)
    if not parts or "".join(s + v for s, v in parts) != t:
        raise ValueError(f"Ungültige Adresse: {text!r}")
    total = 0
    for sign, val in parts:
        n = int(val, 16)
        total += -n if sign == "-" else n
    if total < 0:
        raise ValueError("Negative Adresse")
    return total


def hexs(v):
    return f"0x{v:X}"


class BaseTab(tk.Frame):
    """Basisklasse: Zugriff auf das Fenster (Netzwerk, Log, Navigation)."""

    def __init__(self, parent, win):
        super().__init__(parent, bg=BG)
        self.win = win

    # Kurzformen
    @property
    def base(self):
        return self.win.app.IMAGE_BASE

    def bg(self, fn, ok=None, err=None):
        self.win.bg(fn, ok, err)

    def log(self, msg, kind="info"):
        self.win.log(msg, kind)

    def addr(self, text):
        return parse_addr(text, self.base)
