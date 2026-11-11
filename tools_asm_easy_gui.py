"""tools_asm_easy_gui.py - Dialoge fuer Einsteiger: PRESET (fertige Aenderungen) und Assembler mit Live-Vorschau.

Logik: asm_recipes.py (Presets), asm_help.py (Fehlertexte, Groessen-Vorschau).
"""
import tkinter as tk

import asm_help as AH
import asm_recipes as AR
import tools_i18n
from tools_common import ACCENT, BG, BG_CARD, FONT_LABEL, TEXT_DIM, WARN, button, entry, label, textbox


def local_assembler():
    """Keystone lokal (schnell, ohne Verbindung) oder None - fuer die Live-Vorschau beim Tippen."""
    try:
        from keystone import KS_ARCH_X86, KS_MODE_64, Ks
        ks = Ks(KS_ARCH_X86, KS_MODE_64)

        def asm(text, addr=0):
            enc, _n = ks.asm(text, addr)
            return bytes(enc or b"")
        return asm
    except Exception:  # noqa: BLE001
        return None


class AsmDialog(tk.Toplevel):
    """Assembler eingeben, unten steht live: Groesse, passt es?, oder was falsch ist."""

    def __init__(self, parent, title, prompt, space=0, addr=0, initial=""):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.result = None
        self.space, self.addr = space, addr
        self._asm = local_assembler()
        self._job = None
        label(self, prompt).pack(anchor="w", padx=12, pady=(12, 4))
        self.box = textbox(self, height=8, width=60)
        self.box.pack(fill="both", expand=True, padx=12)
        self.box.insert("1.0", initial)
        self.box.bind("<KeyRelease>", lambda _e: self._later())
        self.lbl = tk.Label(self, text="", bg=BG, fg=TEXT_DIM, font=FONT_LABEL, justify="left", wraplength=520, anchor="w")
        self.lbl.pack(fill="x", padx=12, pady=4)
        row = tk.Frame(self, bg=BG); row.pack(fill="x", padx=12, pady=(0, 12))
        button(row, "OK", self._ok, accent=True).pack(side="right", padx=2)
        button(row, "ABBRECHEN", self.destroy).pack(side="right", padx=2)
        label(row, "Mehrere Befehle: je einer pro Zeile. Beispiele: nop   mov eax, 999   add dword ptr [rbx+0x10], 5").pack(side="left")
        self.transient(parent)
        self.grab_set()
        self._preview()

    def text(self):
        return self.box.get("1.0", "end").strip()

    def _later(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(350, self._preview)

    def _preview(self):
        if self._asm is None:
            self.lbl.configure(text=tools_i18n.translate("Vorschau braucht pip install keystone-engine - OK prueft trotzdem."),
                               fg=TEXT_DIM)
            return
        kind, msg = AH.fit_preview(self.text(), self.space, self._asm, self.addr)
        self.lbl.configure(text=msg, fg={"ok": ACCENT, "pad": ACCENT, "big": WARN, "err": WARN}.get(kind, TEXT_DIM))

    def _ok(self):
        self.result = self.text()
        self.destroy()


def ask_asm(parent, title, prompt, space=0, addr=0, initial=""):
    d = AsmDialog(parent, title, prompt, space, addr, initial)
    parent.wait_window(d)
    return d.result


class RecipeDialog(tk.Toplevel):
    """Preset waehlen (kein Assembler tippen).  result = (preset-id, wert) oder None."""

    def __init__(self, parent, insn_text):
        super().__init__(parent)
        self.title("Preset")
        self.configure(bg=BG)
        self.result = None
        lang = tools_i18n.lang()
        self.ids = list(AR.IDS)
        label(self, "Befehl: " + insn_text).pack(anchor="w", padx=12, pady=(12, 4))
        label(self, "Was soll passieren?").pack(anchor="w", padx=12)
        self.v = tk.StringVar(value=self.ids[0])
        self.desc = tk.Label(self, text="", bg=BG, fg=TEXT_DIM, font=FONT_LABEL, justify="left", wraplength=520, anchor="w")
        for rid in self.ids:
            tk.Radiobutton(self, text=AR.title(rid, lang), value=rid, variable=self.v, command=self._sel, bg=BG, fg=ACCENT,
                           selectcolor=BG_CARD, activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL,
                           anchor="w").pack(fill="x", padx=16)
        self.desc.pack(fill="x", padx=12, pady=8)
        row = tk.Frame(self, bg=BG); row.pack(fill="x", padx=12)
        self.lbl_val = label(row, "ZAHL")
        self.lbl_val.pack(side="left")
        self.v_val = tk.StringVar(value="999")
        self.e_val = entry(row, self.v_val, 12)
        self.e_val.pack(side="left", padx=8)
        btn = tk.Frame(self, bg=BG); btn.pack(fill="x", padx=12, pady=12)
        button(btn, "WEITER", self._ok, accent=True).pack(side="right", padx=2)
        button(btn, "ABBRECHEN", self.destroy).pack(side="right", padx=2)
        self.transient(parent)
        self.grab_set()
        self._sel()

    def _sel(self):
        rid = self.v.get()
        self.desc.configure(text=AR.describe(rid, tools_i18n.lang()))
        st = "normal" if AR.needs_value(rid) else "disabled"
        self.e_val.configure(state=st)

    def _ok(self):
        self.result = (self.v.get(), self.v_val.get())
        self.destroy()


def ask_recipe(parent, insn_text):
    d = RecipeDialog(parent, insn_text)
    parent.wait_window(d)
    return d.result
