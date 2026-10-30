"""script_tab.py - Python-Skript-Editor mit `ps5`-API (siehe script_api.py)."""
import threading
import tkinter as tk
from tkinter import filedialog

from script_api import Ps5Api, run_script
from tools_common import (ACCENT, BG, BG_CARD, BG_CARD_HVR, FONT_MONO, TEXT, BaseTab, button, label, textbox)

SAMPLE = '''# ps5 = laufendes Spiel.  F5 = ausfuehren.
base = ps5.module()                       # eboot.bin
print("Basis:", hex(base))
# hp = ps5.pointer(base + 0x4A1C00, 0x20, 0x1C4)
# if hp: ps5.write_u32(hp, 999, undo=True)   # undo_all() stellt zurueck
# site = ps5.aob("48 8B 05 ?? ?? ?? ?? 8B 40 1C")
# if site: ps5.nop(site, 6)
'''

API_LIST = [
    ("module(name='eboot.bin')", "ps5.module()"),
    ("pointer(root, *offs)", "ps5.pointer(base + 0x0, 0x0)"),
    ("aob('48 8B ?? ..')", "ps5.aob(\"48 8B ?? ??\")"),
    ("read(addr, n)", "ps5.read(addr, 4)"),
    ("write(addr, data, undo)", "ps5.write(addr, '90 90', undo=True)"),
    ("read_u32 / f32 / u64 ...", "ps5.read_u32(addr)"),
    ("write_u32 / f32 / u64 ...", "ps5.write_u32(addr, 999, undo=True)"),
    ("nop(addr, n)", "ps5.nop(addr, 6)"),
    ("asm(text, addr)", "ps5.asm('mov eax, 1', addr)"),
    ("patch_asm(addr, text)", "ps5.patch_asm(addr, 'mov eax, 1')"),
    ("alloc(name, size, init)", "ps5.alloc('buf', 64)"),
    ("call(addr, *args)", "rax = ps5.call(ps5.module().base + 0x1000, 1, 'text')"),
    ("foreground()", "pid, tid, name, ver = ps5.foreground()"),
    ("write_many([(addr, bytes)])", "ps5.write_many([(a, b'\\x90\\x90')])"),
    ("log_calls(addr, seconds)", "calls = ps5.log_calls(addr, 5)"),
    ("notify(msg)", "ps5.notify('Hallo')"),
    ("sleep(sec)", "ps5.sleep(1.0)"),
    ("undo_all()", "ps5.undo_all()"),
]


class ScriptTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.api = None
        self._api_client = None
        self._thread = None

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=6, pady=6)
        self.btn_run = button(bar, "AUSFUEHREN (F5)", self.run, accent=True)
        self.btn_run.pack(side="left")
        button(bar, "STOP", self.stop).pack(side="left", padx=4)
        button(bar, "ALLES RUECKGAENGIG", self.undo).pack(side="left")
        button(bar, "OEFFNEN…", self.open).pack(side="left", padx=(14, 4))
        button(bar, "SPEICHERN…", self.save).pack(side="left")

        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=6)
        self.ed = textbox(mid, height=16, width=90)
        self.ed.pack(side="left", fill="both", expand=True)
        self.ed.insert("1.0", SAMPLE)
        side = tk.Frame(mid, bg=BG)
        side.pack(side="left", fill="y", padx=(6, 0))
        label(side, "API (Doppelklick = einfuegen)").pack(anchor="w")
        self.lb = tk.Listbox(side, width=30, height=16, bg=BG_CARD, fg=TEXT, font=FONT_MONO,
                             selectbackground=BG_CARD_HVR, selectforeground=ACCENT, relief="flat",
                             exportselection=False)
        self.lb.pack(fill="y", expand=True)
        for sig, _ in API_LIST:
            self.lb.insert("end", sig)
        self.lb.bind("<Double-Button-1>", self._insert_api)

        label(self, "Ausgabe").pack(anchor="w", padx=8, pady=(6, 0))
        self.out = textbox(self, height=8, width=90)
        self.out.pack(fill="x", padx=6, pady=(0, 6))
        self.out.configure(state="disabled", undo=False)
        self.ed.bind("<F5>", lambda _e: self.run())
        self.bind_all("<Control-Return>", lambda _e: None)

    # -- Hilfen -------------------------------------------------------------
    def _say(self, text):
        def put():
            self.out.configure(state="normal")
            self.out.insert("end", text + "\n")
            self.out.see("end")
            self.out.configure(state="disabled")
        self.win.ui(put)

    def _get_api(self):
        c = self.win.client
        if c is None:
            raise RuntimeError("Nicht verbunden")
        if self.api is None or self._api_client is not c:
            self.api = Ps5Api(c, self.win.app.backend, self.win.app.IMAGE_BASE,
                              lock=self.win.net_lock, out=self._say)
            self._api_client = c
        self.api.image_base = self.win.app.IMAGE_BASE
        return self.api

    def _insert_api(self, _e):
        i = self.lb.curselection()
        if i:
            self.ed.insert("insert", API_LIST[i[0]][1])

    # -- Aktionen --------------------------------------------------------------
    def run(self):
        if self._thread and self._thread.is_alive():
            return self._say("-- laeuft noch (STOP druecken) --")
        try:
            api = self._get_api()
        except Exception as e:
            return self._say(f"Fehler: {e}")
        code = self.ed.get("1.0", "end")
        self.btn_run.configure(state="disabled")

        def work():
            try:
                run_script(code, api, self._say)
            finally:
                self.win.ui(lambda: self.btn_run.configure(state="normal"))

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def stop(self):
        if self.api:
            self.api.stop()

    def undo(self):
        if not self.api:
            return self._say("Nichts rueckgaengig zu machen.")
        try:
            self._say(f"{self.api.undo_all()} Schreibzugriff(e) zurueckgesetzt")
        except Exception as e:
            self._say(f"Fehler: {e}")

    def open(self):
        p = filedialog.askopenfilename(parent=self, filetypes=[("Python", "*.py"), ("Alle", "*.*")])
        if p:
            with open(p, encoding="utf-8") as f:
                self.ed.delete("1.0", "end")
                self.ed.insert("1.0", f.read())

    def save(self):
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".py",
                                         filetypes=[("Python", "*.py")])
        if p:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.ed.get("1.0", "end").rstrip() + "\n")

    def shutdown(self):
        self.stop()
