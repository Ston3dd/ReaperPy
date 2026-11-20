"""tools_buildcheat_gui.py - Dialog "CHEAT BAUEN": aus den markierten Disassembler-Zeilen einen NOP- oder Cave-Cheat machen.

Der Dialog fragt nur: NOP oder Cave, Name, und ob gleich gespeichert werden soll.  Die Arbeit (Stellen bilden, Texte bauen)
macht cheat_from_disasm.py; vorbereitet wird im Cheat-Editor (TEST AN/AUS, SPEICHERN mit Signatur).

    res = ask_build_cheat(parent, lines, image_base)    # None oder {'mode': 'nop'|'cave', 'name': str, 'save': bool}
"""
import tkinter as tk

import cheat_from_disasm as CD
import tools_i18n
from tools_common import ACCENT, BG, BG_CARD, FONT_LABEL, TEXT_DIM, WARN, button, entry, label, tree

MODES = (("nop", "NOP - die markierten Befehle abschalten"),
         ("cave", "CAVE - die Befehle in eine Code-Cave kopieren und dort ändern"))
DESC = {"nop": "Die markierten Befehle werden mit NOP überschrieben, z. B. der Abzug von Leben oder Munition. "
               "Mehrere getrennte Stellen gehen in einem Cheat.",
        "cave": "Die markierten Befehle landen in einer eigenen Cave. Dort kannst du sie ändern oder weglassen und eigenen "
                "Code davor setzen. Es zählt die erste Stelle."}
HINT = {"far": "Die Stellen liegen weit auseinander: nur die erste bekommt eine Signatur, die anderen folgen mit demselben "
               "Abstand. Nach einem Spiel-Update erst testen.",
        "short": "Der Hook braucht mindestens {n} Byte: die Befehle dahinter werden mit in die Cave kopiert.",
        "ignored": "{n} weitere Stelle(n) werden in der Cave nicht berücksichtigt - nur die erste zählt.",
        "long": "{n} Byte werden überschrieben - sehr lange Folge. Prüfe, dass in der Mitte kein Sprung landet."}
COUNT = "{n} Zeile(n) markiert = {s} Stelle(n), {b} Byte"


def _short(text, n):
    return text if len(text) <= n else text[:n - 1] + "…"


class BuildCheatDialog(tk.Toplevel):
    def __init__(self, parent, lines, base):
        super().__init__(parent)
        self.title("Cheat bauen")
        self.configure(bg=BG)
        self.result = None
        self.rs, self.base = CD.runs(lines), base
        n, s, b = CD.summary(self.rs)
        label(self, tools_i18n.translate(COUNT).format(n=n, s=s, b=b)).pack(anchor="w", padx=12, pady=(12, 4))

        tv = tree(self, [("n", "STELLE"), ("a", "ADRESSE"), ("o", "OFFSET"), ("b", "BYTES"), ("i", "BEFEHLE")],
                  [60, 110, 80, 170, 300], height=min(6, max(2, len(self.rs))))
        tv.pack(fill="x", padx=12)
        for i, r in enumerate(self.rs, 1):
            tv.insert("", "end", values=(i, f"{r['addr']:#x}", f"+{r['addr'] - base:X}" if r["addr"] >= base else "-",
                                         _short(CD.run_hex(r), 32),
                                         _short("; ".join(f"{x['mnemonic']} {x['op_str']}".strip() for x in r["lines"]), 60)))

        label(self, "Was soll der Cheat tun?").pack(anchor="w", padx=12, pady=(12, 0))
        self.v_mode = tk.StringVar(value="nop")
        for mode, text in MODES:
            tk.Radiobutton(self, text=tools_i18n.translate(text), value=mode, variable=self.v_mode, command=self._sel, bg=BG,
                           fg=ACCENT, selectcolor=BG_CARD, activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL,
                           anchor="w").pack(fill="x", padx=16)
        self.desc = tk.Label(self, text="", bg=BG, fg=TEXT_DIM, font=FONT_LABEL, justify="left", wraplength=640, anchor="w")
        self.desc.pack(fill="x", padx=12, pady=(8, 2))
        self.warn = tk.Label(self, text="", bg=BG, fg=WARN, font=FONT_LABEL, justify="left", wraplength=640, anchor="w")
        self.warn.pack(fill="x", padx=12)

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(8, 0))
        label(row, "NAME").pack(side="left")
        self.v_name = tk.StringVar(value=CD.default_name("nop", self.rs, base))
        self._auto = self.v_name.get()
        entry(row, self.v_name, 30).pack(side="left", padx=8)

        btn = tk.Frame(self, bg=BG)
        btn.pack(fill="x", padx=12, pady=12)
        button(btn, "IM CHEAT-EDITOR ÖFFNEN", lambda: self._ok(False), accent=True).pack(side="right", padx=2)
        button(btn, "SOFORT SPEICHERN…", lambda: self._ok(True)).pack(side="right", padx=2)
        button(btn, "ABBRECHEN", self.destroy).pack(side="right", padx=2)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(parent)
        self.grab_set()
        self._sel()

    def _sel(self):
        mode = self.v_mode.get()
        self.desc.configure(text=tools_i18n.translate(DESC[mode]))
        texts = []
        for key, val in CD.warnings(mode, self.rs):
            texts.append(tools_i18n.translate(HINT[key]).format(n=val))
        self.warn.configure(text="\n".join(texts))
        if self.v_name.get() == self._auto:                       # Name nur mitnehmen, solange der Nutzer ihn nicht geändert hat
            self._auto = CD.default_name(mode, self.rs, self.base)
            self.v_name.set(self._auto)

    def _ok(self, save):
        self.result = {"mode": self.v_mode.get(), "name": self.v_name.get().strip(), "save": save}
        self.destroy()


def ask_build_cheat(parent, lines, base):
    d = BuildCheatDialog(parent, lines, base)
    parent.wait_window(d)
    return d.result
