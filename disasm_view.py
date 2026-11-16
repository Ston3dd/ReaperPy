"""disasm_view.py - Disassembler-Ansicht im ReaperPy-Design: ADRESSE | HEX | INSTRUKTION | LÄNGE.

Gedacht fuer "was ist hier eben passiert?": Der Befehl, der geschrieben hat, ist gruen hinterlegt, die Zeile, an der die
CPU steht (RIP), gelb - dazu ein paar Befehle davor und danach, damit man den Zusammenhang sieht.  Die markierten
Zeilen werden in die Mitte der Liste gescrollt (nicht ganz nach oben).  Eine Klick-Auswahl bleibt blau wie ueberall im Tool.

    v = DisasmView(parent, on_open=fn(line), on_preset=fn(line))
    v.show(build_context(...))          # Ergebnis aus hit_context.py
    v.show_lines(lines, marks, focus)   # oder direkt
    v.show_message("Noch kein Treffer")
"""
import tkinter as tk
from tkinter import ttk

import asm_tools as AT
import theme as T
from tools_common import (BG_BAR, BG_CARD, BORDER, TEXT, TEXT_DIM2, ACCENT, ACCENT_DIM, WARN,
                          FONT_MONO, FONT_LABEL, FONT_TEXT, tree, with_scroll)

MARK_TEXT = {"writer": "✎ SCHREIBER", "rip": "▶ RIP"}
_FLOW = ("call", "jmp", "ret", "leave")
_QUIET = ("nop", "int3", "xchg ax, ax", "data16")


def _kind_of(line):
    """Grobe Art eines Befehls fuer die Schriftfarbe: 'flow' (Spruenge, Aufrufe), 'quiet' (Fuellbytes) oder 'plain'."""
    m = line["mnemonic"]
    base = m.split()[-1] if m.startswith(("lock ", "rep", "bnd ", "notrack ")) else m
    if base.startswith(_QUIET) or base == "db":
        return "quiet"
    if base.startswith(_FLOW) or (base.startswith("j") and len(base) <= 4):
        return "flow"
    return "plain"


def style_rows(tv):
    """Zeilenfarben fuer jede Befehls-Tabelle im Tool: pro Zeile genau EIN Tag (Zebra x Art), Markierungen gehen vor."""
    bold = (FONT_MONO[0], FONT_MONO[1], "bold")
    for kind, fg in (("plain", TEXT), ("flow", ACCENT_DIM), ("quiet", TEXT_DIM2)):
        tv.tag_configure(f"{kind}_a", background=BG_CARD, foreground=fg)
        tv.tag_configure(f"{kind}_b", background=T.ROW_ALT, foreground=fg)
    tv.tag_configure("writer", background=T.ROW_WRITER, foreground=ACCENT, font=bold)
    tv.tag_configure("rip", background=T.CALLOUT_WARN_BG, foreground=WARN, font=bold)


def row_tag(line, index, mark=None):
    """Das Tag einer Zeile: Markierung ('writer' / 'rip') oder Zebra x Befehlsart."""
    if mark in ("writer", "rip"):
        return mark
    return f"{_kind_of(line)}_{'ab'[index % 2]}"


def addr_width(lines):
    """Hex-Stellen fuer die Adressspalte: gleich breit, aber nur so breit wie noetig (PS5-Code liegt meist bei 0x4xxxxx)."""
    return max([8] + [len(f"{ln['addr']:X}") for ln in lines])


def center_row(tv, idx, n, tries=4):
    """Zeile idx von n in die Mitte der sichtbaren Liste scrollen (ttk 'see' wuerde sie nur an den Rand holen).

    Die sichtbare Zeilenzahl kommt aus der echten Hoehe des Widgets - das Fenster ist oft niedriger als `height`.
    Ist es noch nicht angeordnet (Hoehe 1), wird kurz gewartet und es nochmal versucht."""
    if not n:
        return
    try:
        tv.update_idletasks()
        h = tv.winfo_height()
        if h <= 30 and tries:
            return tv.after(60, lambda: center_row(tv, idx, n, tries - 1))
        row = int(ttk.Style(tv).lookup("Treeview", "rowheight") or 20)
        rows = max(1, (h - row - 2) // row)                       # eine Zeile geht fuer die Kopfleiste ab
        tv.yview_moveto(max(0, min(idx - rows // 2, n - rows)) / n)
    except tk.TclError:
        pass


class DisasmView(tk.Frame):
    COLS = [("mark", ""), ("addr", "ADRESSE"), ("hex", "HEX"), ("ins", "INSTRUKTION"), ("len", "LÄNGE")]
    WIDTHS = [96, 100, 160, 220, 50]

    def __init__(self, parent, on_open=None, on_preset=None, height=12):
        super().__init__(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        self.on_open, self.on_preset = on_open, on_preset
        self.lines, self.marks, self.focus = [], {}, None

        # Kopf: ein Satz in Klartext + Legende
        head = tk.Frame(self, bg=BG_BAR)
        head.pack(fill="x")
        legend = tk.Frame(head, bg=BG_BAR)
        legend.pack(side="right", padx=8)
        self._chip(legend, "SCHREIBER", T.ROW_WRITER, ACCENT).pack(side="left", padx=(0, 4))
        self._chip(legend, "RIP", T.CALLOUT_WARN_BG, WARN).pack(side="left")
        self.lbl = tk.Label(head, text="", bg=BG_BAR, fg=TEXT, font=FONT_TEXT, anchor="w", justify="left")
        self.lbl.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        head.bind("<Configure>", lambda e: self.lbl.configure(wraplength=max(200, e.width - 220)))

        body = tk.Frame(self, bg=BG_CARD)
        body.pack(fill="both", expand=True)
        self.tv = tree(body, self.COLS, self.WIDTHS, height=height,
                       anchors={"len": "e", "mark": "w"},
                       actions=[("ADRESSE KOPIEREN", lambda: self._copy("addr")),
                                ("BYTES KOPIEREN", lambda: self._copy("hex")),
                                ("INSTRUKTION KOPIEREN", lambda: self._copy("ins")),
                                (None, None),
                                ("IM DISASSEMBLER ÖFFNEN", self._open),
                                ("PRESET …", self._preset)],
                       empty="Noch kein Treffer - setze einen Breakpoint oder Watchpoint und lass das Spiel laufen.")
        with_scroll(body, self.tv)
        self.tv.column("len", stretch=False, width=50)        # tree() dehnt sonst die letzte Spalte; hier soll es INSTRUKTION sein
        self.tv.column("ins", stretch=True)
        self.tv.bind("<Double-1>", lambda _e: self._open())

        style_rows(self.tv)

    @staticmethod
    def _chip(parent, text, bg, fg):
        return tk.Label(parent, text=f" {text} ", bg=bg, fg=fg, font=FONT_LABEL, padx=4, pady=1)

    # ---- Anzeige ----
    def show(self, ctx):
        """Ergebnis von hit_context.build_context."""
        self.lbl.configure(text=ctx.get("headline", ""))
        self.show_lines(ctx["lines"], ctx.get("marks"), ctx.get("focus"), keep_headline=True)

    def show_lines(self, lines, marks=None, focus=None, keep_headline=False):
        self.lines, self.marks, self.focus = list(lines), dict(marks or {}), focus
        if not keep_headline:
            self.lbl.configure(text="")
        self.tv.delete(*self.tv.get_children())
        focus_iid = None
        w = addr_width(self.lines)
        for i, ln in enumerate(self.lines):
            mark = self.marks.get(ln["addr"])
            self.tv.insert("", "end", iid=str(i), tags=(row_tag(ln, i, mark),), values=(
                MARK_TEXT.get(mark, ""), f"{ln['addr']:0{w}X}", AT.hexdump_line(ln["bytes"]),
                f"{ln['mnemonic']} {ln['op_str']}".strip(), ln["size"]))
            if ln["addr"] == focus:
                focus_iid = i
        if focus_iid is not None:
            self.after_idle(lambda: center_row(self.tv, focus_iid, len(self.lines)))

    def show_message(self, text):
        """Statt einer Liste nur einen Satz zeigen (z. B. Fehler beim Lesen)."""
        self.lines, self.marks, self.focus = [], {}, None
        self.tv.delete(*self.tv.get_children())
        self.lbl.configure(text=text)

    # ---- Auswahl / Aktionen ----
    def line(self):
        """Markierte Zeile, sonst die hervorgehobene (Schreiber / RIP)."""
        sel = self.tv.selection()
        if sel:
            return self.lines[int(sel[0])]
        return next((ln for ln in self.lines if ln["addr"] == self.focus), None)

    def _open(self):
        ln = self.line()
        if ln and self.on_open:
            self.on_open(ln)

    def _preset(self):
        ln = self.line()
        if ln and self.on_preset:
            self.on_preset(ln)

    def _copy(self, what):
        ln = self.line()
        if not ln:
            return
        text = {"addr": f"{ln['addr']:#x}", "hex": AT.hexdump_line(ln["bytes"]),
                "ins": f"{ln['mnemonic']} {ln['op_str']}".strip()}[what]
        self.clipboard_clear()
        self.clipboard_append(text)
