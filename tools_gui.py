"""tools_gui.py – Werkzeug-Fenster für ReaperPy (Speicher, Disassembler, Konverter,
Cheat-Editor, AOB/Update-Scan, Debugger).  Wird aus gui.py über den Button
"WERKZEUGE" geöffnet und nutzt eine EIGENE Verbindung zur PS5, damit die
Haupt-Verbindung (Patches an/aus) nie durcheinanderkommt."""
import tools_i18n
import json
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import aob as AOB
import asm_tools as AT
import ps5_ext as X
from ps5_client import PS5DebugClient
from reapatch import ReapPatch
from patch_engine import apply_patch, deactivate_patch, is_cave_patch, asm_to_bytes
from tools_groups import GroupTab
from tools_common import (BG, BG_BAR, BG_CARD, ACCENT, TEXT, TEXT_DIM, WARN,
                          ERROR, FONT_LABEL, FONT_HEAD, BaseTab, style_ttk,
                          button, label, entry, textbox, tree, with_scroll, hexs)


# ==================================================================
# Tab: Speicher
# ==================================================================
class MemoryTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.cur = None
        self.auto = False

        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=8, pady=(8, 4))
        label(bar, "ADRESSE").pack(side="left")
        self.v_addr = tk.StringVar(value="base")
        e = entry(bar, self.v_addr, 22); e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _e: self.read())
        label(bar, "LÄNGE").pack(side="left")
        self.v_len = tk.StringVar(value="0x200")
        entry(bar, self.v_len, 8).pack(side="left", padx=6)
        button(bar, "LESEN", self.read, accent=True).pack(side="left", padx=2)
        button(bar, "◀", lambda: self.page(-1)).pack(side="left", padx=2)
        button(bar, "▶", lambda: self.page(1)).pack(side="left", padx=2)
        self.v_auto = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="AUTO 500ms", variable=self.v_auto, command=self._auto,
                       bg=BG, fg=TEXT_DIM, selectcolor=BG_CARD, activebackground=BG,
                       activeforeground=ACCENT, font=FONT_LABEL).pack(side="left", padx=8)
        button(bar, "MAPS", self.load_maps).pack(side="right")

        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=8)
        left = tk.Frame(body, bg=BG); left.pack(side="left", fill="both", expand=True)
        self.txt = textbox(left, height=20, width=84)
        self.txt.configure(state="disabled")
        with_scroll(left, self.txt)
        right = tk.Frame(body, bg=BG); right.pack(side="right", fill="y", padx=(8, 0))
        self.maps = tree(right, [("start", "START"), ("end", "ENDE"), ("prot", "RWX")],
                         [130, 130, 50], height=18)
        self.maps.pack(fill="y", expand=True)
        self.maps.bind("<Double-1>", self._map_dbl)

        self.snap = None
        self.last = (0, b"")
        self.lbl_insp = label(self, "Klick auf ein Byte -> Werte-Inspektor")
        self.lbl_insp.pack(fill="x", padx=10)
        self.txt.bind("<ButtonRelease-1>", self._inspect)
        tl = tk.Frame(self, bg=BG); tl.pack(fill="x", padx=8, pady=(4, 0))
        label(tl, "WERKZEUGE").pack(side="left")
        button(tl, "SNAPSHOT", self.snapshot).pack(side="left", padx=2)
        button(tl, "VERGLEICH", self.compare).pack(side="left", padx=2)
        button(tl, "ALS DATEI…", self.save_file).pack(side="left", padx=2)
        button(tl, "DATEI → SPEICHER…", self.load_file).pack(side="left", padx=2)
        button(tl, "HEXDUMP KOPIEREN", self.copy_dump).pack(side="left", padx=2)

        wr = tk.Frame(self, bg=BG); wr.pack(fill="x", padx=8, pady=8)
        label(wr, "SCHREIBEN @").pack(side="left")
        self.v_waddr = tk.StringVar()
        entry(wr, self.v_waddr, 20).pack(side="left", padx=6)
        self.v_wbytes = tk.StringVar()
        entry(wr, self.v_wbytes, 40).pack(side="left", padx=6)
        button(wr, "SCHREIBEN", self.write, accent=True).pack(side="left", padx=2)
        button(wr, "→ DISASM", lambda: self.win.goto_disasm(self._cur_addr())).pack(side="right")

    def _cur_addr(self):
        return self.cur if self.cur is not None else self.addr(self.v_addr.get())

    def goto(self, address):
        self.v_addr.set(hexs(address))
        self.read()

    def page(self, d):
        try:
            n = int(self.v_len.get(), 0)
            self.v_addr.set(hexs(max(0, self._cur_addr() + d * n)))
            self.read()
        except Exception as e:
            self.log(str(e), "err")

    def _auto(self):
        self.auto = self.v_auto.get()
        if self.auto:
            self._tick()

    def _tick(self):
        if not self.auto or not self.winfo_exists():
            return
        self.read(quiet=True)
        self.after(500, self._tick)

    def read(self, quiet=False):
        try:
            a = self.addr(self.v_addr.get())
            n = max(1, min(int(self.v_len.get(), 0), 0x10000))
        except Exception as e:
            return self.log(str(e), "err")
        self.cur = a
        self.v_waddr.set(hexs(a))
        self.bg(lambda: self.win.client.read_memory(a, n),
                lambda data: self._show(a, data),
                (lambda e: None) if quiet else None)

    def _show(self, a, data):
        self.last = (a, bytes(data))
        lines = []
        for i in range(0, len(data), 16):
            row = data[i:i + 16]
            hx = " ".join(f"{b:02X}" for b in row).ljust(47)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
            lines.append(f"{a + i:016X}  {hx}  {asc}")
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(lines))
        self.txt.configure(state="disabled")

    # ---- Inspektor / Snapshot / Datei ----
    def _inspect(self, _e):
        import memtools
        try:
            line, col = (int(x) for x in self.txt.index("insert").split("."))
        except Exception:
            return
        a, data = self.last
        if col >= 18 and col < 18 + 47:
            i = (col - 18) // 3
        elif col >= 18 + 49:
            i = col - (18 + 49)
        else:
            return
        pos = (line - 1) * 16 + i
        if not 0 <= pos < len(data):
            return
        info = memtools.inspect(data[pos:pos + 8])
        self.v_waddr.set(hexs(a + pos))
        self.lbl_insp.configure(text=f"{a + pos:#x}:  " + "   ".join(f"{k} {v}" for k, v in info[:9]))

    def snapshot(self):
        a, data = self.last
        if not data:
            return self.log("erst LESEN", "warn")
        self.snap = (a, data)
        self.log(f"Snapshot {a:#x} ({len(data):#x} Byte) gemerkt - Wert im Spiel aendern, dann VERGLEICH", "ok")

    def compare(self):
        import memtools
        if not self.snap:
            return self.log("erst SNAPSHOT", "warn")
        a, old = self.snap

        def show(new):
            runs = memtools.diff_bytes(old, new, a)
            d = tk.Toplevel(self); d.title(f"Vergleich: {len(runs)} geaenderte Bereiche")
            d.configure(bg=BG)
            tv = tree(d, [("a", "ADRESSE"), ("o", "ALT"), ("n", "NEU")], [140, 220, 220], height=20)
            with_scroll(d, tv)
            for ad, o, n in runs[:5000]:
                tv.insert("", "end", values=(f"{ad:#x}", o.hex(" ").upper(), n.hex(" ").upper()))
            tv.bind("<Double-1>", lambda _e: tv.selection() and (
                self.goto(int(tv.item(tv.selection()[0], "values")[0], 16))))
            self.log(f"Vergleich: {len(runs)} Bereiche geaendert", "ok")
        self.bg(lambda: self.win.client.read_memory(a, len(old)), show)

    def save_file(self):
        a, data = self.last
        if not data:
            return self.log("erst LESEN", "warn")
        fn = filedialog.asksaveasfilename(parent=self.win, initialfile=f"dump_{a:X}.bin",
                                          filetypes=[("Binaer", "*.bin"), ("Alle", "*.*")])
        if fn:
            with open(fn, "wb") as f:
                f.write(data)
            self.log(f"{len(data)} Byte -> {fn}", "ok")

    def load_file(self):
        try:
            a = self.addr(self.v_waddr.get())
        except Exception as e:
            return self.log(str(e), "err")
        fn = filedialog.askopenfilename(parent=self.win)
        if not fn:
            return
        with open(fn, "rb") as f:
            data = f.read(0x100000)
        if not data or not messagebox.askyesno("Datei -> Speicher",
                                               f"{len(data)} Byte aus der Datei nach {a:#x} schreiben?",
                                               parent=self.win):
            return
        self.bg(lambda: self.win.client.write_memory(a, data),
                lambda _r: (self.log(f"{len(data)} Byte geschrieben @ {a:#x}", "ok"), self.read()))

    def copy_dump(self):
        import memtools
        a, data = self.last
        if data:
            self.clipboard_clear(); self.clipboard_append(memtools.hexdump(data, a))
            self.log("Hexdump in der Zwischenablage", "ok")

    def write(self):
        try:
            a = self.addr(self.v_waddr.get())
            data = AT.parse_hex_bytes(self.v_wbytes.get())
            if not data:
                raise ValueError("Keine Bytes")
        except Exception as e:
            return self.log(str(e), "err")
        if not messagebox.askyesno("Schreiben", f"{len(data)} Byte(s) nach {a:#x} schreiben?"):
            return

        def job():
            self.win.client.write_memory(a, data)
            return self.win.client.read_memory(a, len(data))
        self.bg(job, lambda back: (self.log(f"Geschrieben @ {a:#x}: {AT.hexdump_line(back)}", "ok"),
                                   self.read()))

    def load_maps(self):
        self.bg(lambda: self.win.client.get_maps(), self._show_maps)

    def _show_maps(self, maps):
        self.maps.delete(*self.maps.get_children())
        for s, e, p in sorted(maps):
            flags = ("r" if p & 1 else "-") + ("w" if p & 2 else "-") + ("x" if p & 4 else "-")
            self.maps.insert("", "end", values=(f"{s:016X}", f"{e:016X}", flags))

    def _map_dbl(self, _e):
        sel = self.maps.selection()
        if sel:
            self.goto(int(self.maps.item(sel[0], "values")[0], 16))


# ==================================================================
# Tab: Disassembler
# ==================================================================
class DisasmTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.lines = []
        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=8, pady=(8, 4))
        label(bar, "ADRESSE").pack(side="left")
        self.v_addr = tk.StringVar(value="base")
        e = entry(bar, self.v_addr, 22); e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _e: self.run())
        label(bar, "ANZAHL").pack(side="left")
        self.v_n = tk.StringVar(value="64")
        entry(bar, self.v_n, 5).pack(side="left", padx=6)
        button(bar, "DISASM", self.run, accent=True).pack(side="left", padx=2)
        button(bar, "▶ WEITER", self.next_page).pack(side="left", padx=2)
        button(bar, "FOLGEN", self.follow).pack(side="left", padx=2)
        if not AT.HAVE_CAPSTONE:
            label(bar, "  Capstone fehlt: pip install capstone").pack(side="left")

        cols = [("addr", "ADRESSE"), ("off", "OFFSET"), ("bytes", "BYTES"), ("ins", "INSTRUKTION")]
        fr = tk.Frame(self, bg=BG); fr.pack(fill="both", expand=True, padx=8)
        self.tv = tree(fr, cols, [150, 90, 200, 380], height=22)
        with_scroll(fr, self.tv)
        self.tv.bind("<Double-1>", lambda _e: self.follow())

        act = tk.Frame(self, bg=BG); act.pack(fill="x", padx=8, pady=8)
        button(act, "NOP", self.nop).pack(side="left", padx=2)
        button(act, "ÄNDERN…", self.patch).pack(side="left", padx=2)
        button(act, "XREFS AUF ADRESSE", self.xrefs).pack(side="left", padx=2)
        button(act, "→ HEX", self.to_hex).pack(side="left", padx=2)
        button(act, "→ CHEAT-EDITOR", self.to_cheat, accent=True).pack(side="right")
        button(act, "ALS CAVE-HOOK", self.to_cave_hook, accent=True).pack(side="right", padx=(0, 6))

    def goto(self, address):
        self.v_addr.set(hexs(address))
        self.run()

    def run(self):
        try:
            a = self.addr(self.v_addr.get())
            n = max(1, min(int(self.v_n.get(), 0), 1000))
        except Exception as e:
            return self.log(str(e), "err")

        def job():
            data = self.win.client.read_memory(a, n * 15 + 16)
            return AT.disassemble_lines(data, a, n)
        self.bg(job, self._show)

    def _show(self, lines):
        self.lines = lines
        self.tv.delete(*self.tv.get_children())
        base = self.base
        for i, l in enumerate(lines):
            off = l["addr"] - base
            self.tv.insert("", "end", iid=str(i), values=(
                f"{l['addr']:016X}", f"+{off:X}" if off >= 0 else "-",
                AT.hexdump_line(l["bytes"]), f"{l['mnemonic']} {l['op_str']}".strip()))

    def next_page(self):
        if self.lines:
            last = self.lines[-1]
            self.v_addr.set(hexs(last["addr"] + last["size"]))
            self.run()

    def _selected(self):
        return [self.lines[int(i)] for i in self.tv.selection()]

    def follow(self):
        sel = self._selected()
        if not sel:
            return
        t = AT.branch_target(sel[0]) or AT.rip_target(sel[0])
        if t is None:
            return self.log("Kein direktes Sprung-/RIP-Ziel in dieser Zeile", "warn")
        if AT.branch_target(sel[0]) is not None:
            self.goto(t)
        else:
            self.win.goto_memory(t)

    def _write(self, address, data, what):
        def job():
            self.win.client.write_memory(address, data)
            return self.win.client.read_memory(address, len(data))
        self.bg(job, lambda back: (self.log(f"{what} @ {address:#x}: {AT.hexdump_line(back)}", "ok"),
                                   self.run()))

    def nop(self):
        sel = self._selected()
        if not sel:
            return
        a = sel[0]["addr"]
        n = sum(l["size"] for l in sel)
        if messagebox.askyesno("NOP", f"{n} Byte(s) ab {a:#x} mit NOP (90) füllen?"):
            self._write(a, b"\x90" * n, "NOP")

    def patch(self):
        sel = self._selected()
        if not sel:
            return
        a = sel[0]["addr"]
        size = sum(l["size"] for l in sel)
        text = simpledialog.askstring(
            "Ändern", f"Neuer Assembler-Code für {size} Byte(s) @ {a:#x}\n"
                      f"(mehrere Befehle mit ; trennen, Rest wird NOP):", parent=self)
        if not text:
            return
        try:
            data = AT.assemble(text.replace(";", "\n"), a, self.win.client)
            if len(data) > size:
                return messagebox.showerror("Zu groß", f"{len(data)} > {size} Bytes")
            data += b"\x90" * (size - len(data))
        except Exception as e:
            return messagebox.showerror("Assembler", str(e))
        self._write(a, data, "Patch")

    def xrefs(self):
        sel = self._selected()
        if not sel:
            return
        target = sel[0]["addr"]

        def job():
            regs = AOB.exec_regions(self.win.client.get_maps())
            out = []
            for s, e in regs:
                out += X.find_xrefs_to(self.win.client, s, e - s, target)
            return out
        self.bg(job, lambda res: self.win.show_list(f"Xrefs auf {target:#x}", res))

    def to_hex(self):
        sel = self._selected()
        if sel:
            self.win.goto_memory(sel[0]["addr"])

    def to_cave_hook(self):
        """Gewählte Zeile = Hook-Start. Kopiert ganze Befehle (>= 8 Byte) in eine Cave-Vorlage."""
        sel = self._selected()
        if not sel:
            return self.log("Erst die Startzeile des Hooks markieren", "warn")
        a = sel[0]["addr"]

        def job():
            return AT.build_cave_hook(self.win.client.read_memory(a, 96), a)

        def ok(r):
            r["addr"] = a
            self.win.to_cave_hook(r)
            for w in r["warnings"]:
                self.log(f"Hook: {w}", "warn")
        self.bg(job, ok)

    def to_cheat(self):
        sel = self._selected()
        if not sel:
            return
        a = sel[0]["addr"]
        orig = " ".join(AT.hexdump_line(l["bytes"]) for l in sel)
        asm = "\n".join(f"{l['mnemonic']} {l['op_str']}".strip() for l in sel)
        self.win.to_cheat({"addr": a, "default": orig, "default_asm": asm})


# ==================================================================
# Tab: Konverter
# ==================================================================
class ConverterTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        top = tk.Frame(self, bg=BG); top.pack(fill="both", expand=True, padx=8, pady=8)
        l = tk.Frame(top, bg=BG); l.pack(side="left", fill="both", expand=True)
        r = tk.Frame(top, bg=BG); r.pack(side="left", fill="both", expand=True, padx=(8, 0))

        label(l, "ASSEMBLER (x86-64, Intel)").pack(anchor="w")
        self.asm = textbox(l, height=10, width=40); self.asm.pack(fill="both", expand=True)
        row = tk.Frame(l, bg=BG); row.pack(fill="x", pady=4)
        label(row, "BASIS").pack(side="left")
        self.v_base = tk.StringVar(value="0")
        entry(row, self.v_base, 16).pack(side="left", padx=6)
        button(row, "→ BYTES", self.to_bytes, accent=True).pack(side="left")

        label(r, "BYTES (hex)").pack(anchor="w")
        self.hx = textbox(r, height=10, width=40); self.hx.pack(fill="both", expand=True)
        row = tk.Frame(r, bg=BG); row.pack(fill="x", pady=4)
        button(row, "→ ASSEMBLER", self.to_asm, accent=True).pack(side="left")

        label(self, "WERT-KONVERTER (Hex / Dezimal / Float)").pack(anchor="w", padx=8)
        row = tk.Frame(self, bg=BG); row.pack(fill="x", padx=8, pady=4)
        self.v_val = tk.StringVar(value="0x3F800000")
        e = entry(row, self.v_val, 26); e.pack(side="left")
        e.bind("<Return>", lambda _e: self.conv())
        button(row, "KONVERTIEREN", self.conv, accent=True).pack(side="left", padx=6)
        self.res = tree(self, [("k", "TYP"), ("v", "WERT")], [180, 420], height=9)
        self.res.pack(fill="x", padx=8, pady=(0, 8))

    def to_bytes(self):
        try:
            base = self.addr(self.v_base.get()) if self.v_base.get().strip() not in ("", "0") else 0
        except Exception as e:
            return self.log(str(e), "err")
        text = self.asm.get("1.0", "end").strip()

        def job():
            return AT.assemble(text, base, self.win.client)
        self.bg(job, lambda b: (self.hx.delete("1.0", "end"),
                                self.hx.insert("1.0", AT.hexdump_line(b)),
                                self.log(f"{len(b)} Byte(s) assembliert", "ok")))

    def to_asm(self):
        try:
            data = AT.parse_hex_bytes(self.hx.get("1.0", "end"))
            base = self.addr(self.v_base.get()) if self.v_base.get().strip() not in ("", "0") else 0
            lines = AT.disassemble_lines(data, base)
        except Exception as e:
            return self.log(str(e), "err")
        self.asm.delete("1.0", "end")
        self.asm.insert("1.0", "\n".join(f"{l['mnemonic']} {l['op_str']}".strip() for l in lines))

    def conv(self):
        self.res.delete(*self.res.get_children())
        try:
            out = AT.convert_value(self.v_val.get())
        except Exception as e:
            return self.log(str(e), "err")
        for k, v in out.items():
            self.res.insert("", "end", values=(k, v))


# ==================================================================
# Tab: Cheat-Editor
# ==================================================================
CAVE_TEMPLATE = (";  Cave-Code (läuft anstelle der überschriebenen Befehle)\n"
                 ";  Die Original-Befehle hier wiederholen, dann zurückspringen:\n"
                 "    jmp OriginReturn\n")


class CheatTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.test_state = None
        self.test_rp = None
        self.v = {k: tk.StringVar() for k in ("name", "author", "offset", "aob", "aoboff", "ret")}
        self.v["aoboff"].set("0")
        self.v["ret"].set("8")
        self.v_type = tk.StringVar(value="patch")

        g = tk.Frame(self, bg=BG); g.pack(fill="x", padx=8, pady=(8, 2))
        for i, (k, t, w) in enumerate([("name", "NAME", 30), ("author", "AUTOR", 16),
                                        ("offset", "OFFSET (ab Image-Base)", 16)]):
            label(g, t).grid(row=0, column=i * 2, sticky="w", padx=(0, 4))
            entry(g, self.v[k], w).grid(row=0, column=i * 2 + 1, padx=(0, 12))
        t = tk.Frame(self, bg=BG); t.pack(fill="x", padx=8, pady=2)
        for val, txt in (("patch", "EINFACHER PATCH / NOP"), ("cave", "CODE-CAVE")):
            tk.Radiobutton(t, text=txt, variable=self.v_type, value=val, command=self._type,
                           bg=BG, fg=TEXT, selectcolor=BG_CARD, activebackground=BG,
                           activeforeground=ACCENT, font=FONT_LABEL).pack(side="left", padx=(0, 12))
        label(t, "OriginReturn (Bytes)").pack(side="left", padx=(12, 4))
        entry(t, self.v["ret"], 4).pack(side="left")

        cols = tk.Frame(self, bg=BG); cols.pack(fill="both", expand=True, padx=8, pady=4)
        a = tk.Frame(cols, bg=BG); a.pack(side="left", fill="both", expand=True)
        b = tk.Frame(cols, bg=BG); b.pack(side="left", fill="both", expand=True, padx=(8, 0))
        label(a, "ORIGINAL (Assembler oder Hex-Bytes)").pack(anchor="w")
        self.t_def = textbox(a, height=6, width=34); self.t_def.pack(fill="both", expand=True)
        self.lbl_new = label(b, "NEU (Assembler oder Hex-Bytes, z.B.  nop:8 )")
        self.lbl_new.pack(anchor="w")
        self.t_new = textbox(b, height=6, width=34); self.t_new.pack(fill="both", expand=True)

        label(self, "CAVE-CODE (nur bei Code-Cave) – neue Labels mit  'Name:'  in eigener Zeile")\
            .pack(anchor="w", padx=8)
        self.t_cave = textbox(self, height=7, width=80)
        self.t_cave.pack(fill="both", expand=True, padx=8)
        self.t_cave.insert("1.0", tools_i18n.translate(CAVE_TEMPLATE))

        s = tk.Frame(self, bg=BG); s.pack(fill="x", padx=8, pady=4)
        label(s, "SIGNATUR").pack(side="left")
        entry(s, self.v["aob"], 62).pack(side="left", padx=6)
        label(s, "OFFSET").pack(side="left")
        entry(s, self.v["aoboff"], 5).pack(side="left", padx=6)
        button(s, "ERZEUGEN", self.make_sig).pack(side="left")

        f = tk.Frame(self, bg=BG); f.pack(fill="x", padx=8, pady=8)
        button(f, "NEU", self.clear).pack(side="left", padx=2)
        button(f, "LADEN…", self.load_file).pack(side="left", padx=2)
        button(f, "TEST AN", self.test_on).pack(side="left", padx=(16, 2))
        button(f, "TEST AUS", self.test_off).pack(side="left", padx=2)
        button(f, "SPEICHERN…", self.save, accent=True).pack(side="right")
        self._type()

    # ---- Übernahme aus anderen Tabs ----
    def fill(self, d):
        if "addr" in d:
            self.v["offset"].set(hexs(d["addr"] - self.base))
        if "default" in d:
            self.t_def.delete("1.0", "end"); self.t_def.insert("1.0", d["default"])
        if "new" in d:
            self.t_new.delete("1.0", "end"); self.t_new.insert("1.0", d["new"])
        if "aob" in d:
            self.v["aob"].set(d["aob"]); self.v["aoboff"].set(str(d.get("aoboff", 0)))

    def fill_hook(self, d):
        """Vorlage vom Disassembler (AT.build_cave_hook): Code-Cave komplett vorbelegen."""
        self.clear()
        off = d["addr"] - self.base
        self.v["offset"].set(hexs(off))
        if not self.v["name"].get().strip():
            self.v["name"].set(f"Hook_{off:X}")
        self.v["ret"].set(str(d["size"]))                       # OriginReturn = Summe der Befehle
        self.t_def.delete("1.0", "end"); self.t_def.insert("1.0", d["default"])
        self.t_new.delete("1.0", "end"); self.t_new.insert("1.0", d["new"])
        self.v_type.set("cave")
        self._type()                                            # Cave-Textfeld aktivieren
        self.t_cave.delete("1.0", "end"); self.t_cave.insert("1.0", d["cave"])
        self.log(f"Cave-Hook @ {d['addr']:#x}: {d['size']} Byte überschrieben, "
                 f"OriginReturn = {d['size']}", "ok")

    def clear(self):
        for k in self.v:
            self.v[k].set("")
        self.v["aoboff"].set("0"); self.v["ret"].set("8")
        for t in (self.t_def, self.t_new):
            t.delete("1.0", "end")
        self.t_cave.delete("1.0", "end"); self.t_cave.insert("1.0", tools_i18n.translate(CAVE_TEMPLATE))

    def _type(self):
        cave = self.v_type.get() == "cave"
        self.t_cave.configure(state="normal" if cave else "disabled")
        if cave and not self.t_new.get("1.0", "end").strip():
            self.t_new.insert("1.0", "jmp OriginTarget")

    # ---- Modell <-> JSON ----
    def _offset(self):
        t = self.v["offset"].get().strip()
        if not t:
            raise ValueError("Offset fehlt")
        return int(t, 16) if not t.lower().startswith("0x") else int(t, 16)

    def _cave_labels(self):
        """Text -> [(label, code)]. Erster Block ohne Label = OriginTarget."""
        blocks, cur, lines = [], "OriginTarget", []
        for raw in self.t_cave.get("1.0", "end").splitlines():
            s = raw.strip()
            if s.endswith(":") and " " not in s and not s.startswith(";"):
                if lines:
                    blocks.append((cur, "\n".join(lines)))
                cur, lines = s[:-1], []
            elif s and not s.startswith((";", "#", "//")):     # Kommentarzeilen weglassen
                lines.append(raw.rstrip())
        if lines:
            blocks.append((cur, "\n".join(lines)))
        return blocks

    def build_json(self):
        name = self.v["name"].get().strip()
        if not name:
            raise ValueError("Name fehlt")
        src = {"label": "OriginSource", "offset": self._offset(),
               "defaultValue": self.t_def.get("1.0", "end").strip(),
               "newValue": self.t_new.get("1.0", "end").strip()}
        if not src["newValue"]:
            raise ValueError("'NEU' ist leer")
        if self.v["aob"].get().strip():
            AOB.parse_pattern(self.v["aob"].get())         # validieren
            src["aob"] = self.v["aob"].get().strip()
            src["aobOffset"] = int(self.v["aoboff"].get() or "0", 0)
        variables = [src]
        if self.v_type.get() == "cave":
            variables.append({"label": "OriginReturn", "offset": int(self.v["ret"].get() or "8", 0)})
            labels = self._cave_labels()
            if not labels:
                raise ValueError("Cave-Code fehlt")
            for lbl, code in labels:
                variables.append({"label": lbl, "defaultValue": code})
            if "jmp" not in src["newValue"].lower() and "call" not in src["newValue"].lower():
                src["newValue"] = "jmp OriginTarget"
        return {"name": name, "author": self.v["author"].get().strip(), "Variables": variables}

    def _hook_len_hint(self):
        try:
            return max(len(AT.parse_hex_bytes(self.t_def.get("1.0", "end"))), 1)
        except Exception:
            return 8

    def save(self):
        try:
            data = self.build_json()
        except Exception as e:
            return messagebox.showerror("Cheat-Editor", str(e))
        folder = self.win.app.PATCH_DIR or ""
        fn = filedialog.asksaveasfilename(
            parent=self, initialdir=folder or None,
            initialfile=f"{data['name']}.reapproj", defaultextension=".reapproj",
            filetypes=[("ReapProj", "*.reapproj"), ("JSON", "*.json")])
        if not fn:
            return
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.log(f"Gespeichert: {fn}", "ok")
        if folder and os.path.abspath(os.path.dirname(fn)) == os.path.abspath(folder):
            self.win.app.load_patches()

    def load_file(self):
        fn = filedialog.askopenfilename(parent=self, initialdir=self.win.app.PATCH_DIR or None,
                                        filetypes=[("Patch", "*.reapproj *.json *.reapatch"), ("Alle", "*.*")])
        if not fn:
            return
        try:
            with open(fn, encoding="utf-8") as f:
                d = json.load(f)
            variables = d.get("Variables") or d.get("variables") or []
            src = next(v for v in variables if str(v.get("label", "")).lower().startswith("originsource"))
        except Exception as e:
            return messagebox.showerror("Laden", f"Kein lesbares Patch-Format: {e}")
        self.clear()
        self.v["name"].set(d.get("name", "")); self.v["author"].set(d.get("author", ""))
        off = src.get("offset", 0)
        self.v["offset"].set(hexs(int(off, 0) if isinstance(off, str) else int(off)))
        self.t_def.insert("1.0", src.get("defaultValue", "")); self.t_new.insert("1.0", src.get("newValue", ""))
        self.v["aob"].set(src.get("aob", "")); self.v["aoboff"].set(str(src.get("aobOffset", 0)))
        labels = [(v["label"], v.get("defaultValue", "")) for v in variables
                  if v is not src and v.get("defaultValue") and v.get("label") != "OriginReturn"]
        ret = next((v for v in variables if v.get("label") == "OriginReturn"), None)
        if labels:
            self.v_type.set("cave")
            self.t_cave.configure(state="normal")
            self.t_cave.delete("1.0", "end")
            for lbl, code in labels:
                if lbl != "OriginTarget":
                    self.t_cave.insert("end", f"{lbl}:\n")
                self.t_cave.insert("end", code + "\n")
            if ret:
                self.v["ret"].set(str(ret.get("offset", 8)))
        else:
            self.v_type.set("patch")
        self._type()

    # ---- Signatur ----
    def make_sig(self):
        try:
            a = self.base + self._offset()
        except Exception as e:
            return self.log(str(e), "err")
        hl = 8 if self.v_type.get() == "cave" else self._hook_len_hint()

        def job():
            return AOB.make_signature(self.win.client, self.win.client.get_maps(), a, hl)
        self.bg(job, lambda r: (self.v["aob"].set(r[0]), self.v["aoboff"].set("0"),
                                self.log(f"Signatur eindeutig ({len(r[0].split())} Bytes)", "ok")))

    # ---- Test auf der Konsole ----
    def _temp_patch(self):
        data = self.build_json()
        fd, path = tempfile.mkstemp(suffix=".reapproj")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        rp = ReapPatch.load(path)
        os.remove(path)
        return rp

    def test_on(self):
        try:
            rp = self._temp_patch()
            hook = self.base + self._offset()
        except Exception as e:
            return messagebox.showerror("Test", str(e))
        if self.test_state:
            return self.log("Test läuft schon - erst TEST AUS", "warn")
        self.test_rp = rp

        def job():
            return apply_patch(self.win.app.backend, rp, hook)
        self.bg(job, lambda st: (setattr(self, "test_state", st),
                                 self.log(f"Test aktiv @ {hook:#x}", "ok")))

    def test_off(self):
        if not self.test_state:
            return self.log("Kein aktiver Test", "warn")
        st, rp = self.test_state, self.test_rp

        def job():
            return deactivate_patch(self.win.app.backend, rp, st)
        self.bg(job, lambda _r: (setattr(self, "test_state", None),
                                 self.log("Test zurückgesetzt", "ok")))


# ==================================================================
# Tab: AOB / Update-Scan
# ==================================================================
class AobTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 2))
        label(top, "MUSTER").pack(side="left")
        self.v_pat = tk.StringVar()
        entry(top, self.v_pat, 60).pack(side="left", padx=6)
        self.v_scope = tk.StringVar(value="exec")
        ttk.Combobox(top, textvariable=self.v_scope, values=["exec", "alle lesbaren"],
                     width=14, state="readonly").pack(side="left", padx=4)
        button(top, "SERVER-SCAN", lambda: self.scan(False), accent=True).pack(side="left", padx=2)
        button(top, "LOKAL (ALLE)", lambda: self.scan(True)).pack(side="left", padx=2)

        sig = tk.Frame(self, bg=BG); sig.pack(fill="x", padx=8, pady=2)
        label(sig, "SIGNATUR AUS ADRESSE").pack(side="left")
        self.v_addr = tk.StringVar()
        entry(sig, self.v_addr, 20).pack(side="left", padx=6)
        label(sig, "HOOK-LÄNGE").pack(side="left")
        self.v_hl = tk.StringVar(value="8")
        entry(sig, self.v_hl, 4).pack(side="left", padx=6)
        self.v_wild = tk.BooleanVar(value=True)
        tk.Checkbutton(sig, text="Hook-Bytes wildcarden", variable=self.v_wild, bg=BG, fg=TEXT_DIM,
                       selectcolor=BG_CARD, activebackground=BG, activeforeground=ACCENT,
                       font=FONT_LABEL).pack(side="left", padx=6)
        button(sig, "ERZEUGEN", self.make_sig).pack(side="left", padx=2)
        button(sig, "→ CHEAT-EDITOR", self.sig_to_cheat).pack(side="left", padx=2)

        fr = tk.Frame(self, bg=BG); fr.pack(fill="x", padx=8, pady=4)
        self.res = tree(fr, [("addr", "TREFFER"), ("off", "OFFSET")], [200, 120], height=5)
        with_scroll(fr, self.res)
        self.res.bind("<Double-1>", self._dbl)

        label(self, "PATCHES – SIGNATUREN & UPDATE-SCAN (nach Spiel-Updates)").pack(anchor="w", padx=8, pady=(8, 0))
        fr2 = tk.Frame(self, bg=BG); fr2.pack(fill="both", expand=True, padx=8)
        self.pt = tree(fr2, [("name", "PATCH"), ("off", "OFFSET"), ("sig", "SIGNATUR"),
                             ("found", "GEFUNDEN"), ("new", "NEUER OFFSET"), ("state", "STATUS")],
                       [230, 90, 80, 140, 110, 200], height=10)
        with_scroll(fr2, self.pt)
        self.rows = {}           # iid -> dict(path, rp, new_off)

        act = tk.Frame(self, bg=BG); act.pack(fill="x", padx=8, pady=8)
        button(act, "LISTE LADEN", self.fill_patches).pack(side="left", padx=2)
        button(act, "SIGNATUREN ERZEUGEN (fehlende)", self.gen_all).pack(side="left", padx=2)
        button(act, "UPDATE-SCAN", self.update_scan, accent=True).pack(side="left", padx=2)
        button(act, "OFFSETS ÜBERNEHMEN", self.apply_updates, accent=True).pack(side="right", padx=2)

    # ---- freies Scannen ----
    def scan(self, local):
        try:
            pat, mask = AOB.parse_pattern(self.v_pat.get())
        except Exception as e:
            return self.log(str(e), "err")
        scope = self.v_scope.get()

        def job():
            maps = self.win.client.get_maps()
            regs = AOB.exec_regions(maps) if scope == "exec" else AOB.readable_regions(maps)
            if local:
                return AOB.scan_local(self.win.client, regs, pat, mask, limit=200)
            return AOB.find_matches(self.win.client, regs, pat, mask, limit=50)
        self.bg(job, self._show)

    def _show(self, hits):
        self.res.delete(*self.res.get_children())
        for a in hits:
            self.res.insert("", "end", values=(f"{a:016X}", f"+{a - self.base:X}" if a >= self.base else "-"))
        self.log(f"{len(hits)} Treffer", "ok" if hits else "warn")

    def _dbl(self, _e):
        sel = self.res.selection()
        if sel:
            self.win.goto_disasm(int(self.res.item(sel[0], "values")[0], 16))

    # ---- Signatur aus Adresse ----
    def make_sig(self):
        try:
            a = self.addr(self.v_addr.get())
            hl = int(self.v_hl.get(), 0)
        except Exception as e:
            return self.log(str(e), "err")
        wild = self.v_wild.get()

        def job():
            return AOB.make_signature(self.win.client, self.win.client.get_maps(), a, hl, wild)
        self.bg(job, lambda r: (self.v_pat.set(r[0]),
                                self.log(f"Eindeutige Signatur ({len(r[0].split())} Bytes)", "ok")))

    def sig_to_cheat(self):
        try:
            a = self.addr(self.v_addr.get())
        except Exception as e:
            return self.log(str(e), "err")
        self.win.to_cheat({"addr": a, "aob": self.v_pat.get().strip(), "aoboff": 0})

    # ---- Patch-Liste ----
    def fill_patches(self):
        self.pt.delete(*self.pt.get_children())
        self.rows.clear()
        for i, (path, rp) in enumerate(self.win.app.patches.items()):
            if not rp.origin_source:
                continue
            iid = str(i)
            self.rows[iid] = {"path": path, "rp": rp, "new_off": None}
            self.pt.insert("", "end", iid=iid, values=(
                rp.name, hexs(rp.origin_source[0]), "ja" if rp.origin_aob else "-", "", "", ""))

    def _set(self, iid, **kw):
        cols = ["name", "off", "sig", "found", "new", "state"]
        vals = list(self.pt.item(iid, "values"))
        for k, v in kw.items():
            vals[cols.index(k)] = v
        self.pt.item(iid, values=vals)

    def _hook_len(self, rp, hook):
        if is_cave_patch(rp):
            return 8
        try:
            d = asm_to_bytes(self.win.app.backend, rp.origin_source[1], hook)
            n = asm_to_bytes(self.win.app.backend, rp.origin_source[2], hook)
            return max(len(d), len(n), 1)
        except Exception:
            return 8

    def gen_all(self):
        if not self.rows:
            self.fill_patches()
        todo = [(iid, r) for iid, r in self.rows.items() if not r["rp"].origin_aob]
        if not todo:
            return self.log("Alle Patches haben schon eine Signatur", "info")
        if not messagebox.askyesno("Signaturen", f"Für {len(todo)} Patch(es) Signaturen erzeugen und "
                                   f"in die Patch-Dateien schreiben?\n(Das Spiel sollte die Version "
                                   f"haben, zu der die Offsets passen!)"):
            return
        base = self.base

        def job():
            maps = self.win.client.get_maps()
            out = []
            for iid, r in todo:
                rp = r["rp"]
                hook = base + rp.origin_source[0]
                try:
                    sig, _ = AOB.make_signature(self.win.client, maps, hook, self._hook_len(rp, hook))
                    AOB.update_patch_file(r["path"], aob=sig, aob_offset=0)
                    out.append((iid, "ok", sig))
                except Exception as e:
                    out.append((iid, "err", str(e)))
            return out

        def done(res):
            for iid, st, msg in res:
                self._set(iid, sig="ja" if st == "ok" else "-",
                          state="Signatur gespeichert" if st == "ok" else f"Fehler: {msg}"[:60])
            self.log(f"{sum(1 for _, s, _ in res if s == 'ok')}/{len(res)} Signaturen gespeichert", "ok")
            self.win.app.load_patches()
            self.after(300, self.fill_patches)
        self.bg(job, done)

    def update_scan(self):
        if not self.rows:
            self.fill_patches()
        base = self.base
        rows = {iid: r for iid, r in self.rows.items() if r["rp"].origin_aob}
        if not rows:
            return self.log("Keine Patches mit Signatur - erst SIGNATUREN ERZEUGEN", "warn")

        def job():
            regs = AOB.exec_regions(self.win.client.get_maps())
            out = []
            for iid, r in rows.items():
                rp = r["rp"]
                try:
                    pat, mask = AOB.parse_pattern(rp.origin_aob)
                    hits = AOB.find_matches(self.win.client, regs, pat, mask, limit=3)
                    out.append((iid, hits))
                except Exception as e:
                    out.append((iid, str(e)))
            return out

        def done(res):
            for iid, hits in res:
                r = self.rows[iid]
                old = base + r["rp"].origin_source[0]
                if isinstance(hits, str):
                    self._set(iid, state=f"Fehler: {hits}"[:60]); continue
                if not hits:
                    self._set(iid, found="-", new="", state="NICHT GEFUNDEN"); continue
                hook = hits[0] + r["rp"].origin_aob_offset
                new_off = hook - base
                r["new_off"] = new_off
                note = "mehrdeutig! " if len(hits) > 1 else ""
                state = (note + "unverändert") if hook == old else (note + "VERSCHOBEN")
                self._set(iid, found=hexs(hook), new=hexs(new_off), state=state)
            self.log("Update-Scan fertig", "ok")
        self.bg(job, done)

    def apply_updates(self):
        changes = [(iid, r) for iid, r in self.rows.items()
                   if r["new_off"] is not None and r["new_off"] != r["rp"].origin_source[0]
                   and "mehrdeutig" not in self.pt.item(iid, "values")[5]]
        if not changes:
            return self.log("Keine eindeutigen Änderungen", "info")
        if not messagebox.askyesno("Offsets übernehmen",
                                   f"{len(changes)} Patch-Datei(en) mit neuem Offset überschreiben?"):
            return
        n = 0
        for iid, r in changes:
            try:
                AOB.update_patch_file(r["path"], new_offset=r["new_off"])
                n += 1
            except Exception as e:
                self._set(iid, state=f"Fehler: {e}"[:60])
        self.log(f"{n} Datei(en) aktualisiert", "ok")
        AOB.clear_cache()
        self.win.app.load_patches()
        self.after(300, self.fill_patches)


# ==================================================================
# Fenster
# ==================================================================
class ToolsWindow(tk.Toplevel):
    # Reihenfolge der Anfaenger-Tabs (START kommt zuerst, FORTGESCHRITTEN zuletzt)
    SIMPLE = ("WERT SUCHEN", "CHEATS BEARBEITEN", "★ UNREAL", "★ UNITY")
    ADVANCED = ("SPEICHER", "DISASSEMBLER", "POINTER", "KONVERTER", "AOB / UPDATE", "DEBUGGER", "KERNEL-LOG",
                "PYTHON-SKRIPT", "FUNKTION AUFRUFEN", "FUNKTIONS-LOGGER", "JOURNAL / UNDO")
    # Sammel-Tabs: Reitername -> [(interner Tab-Name, Reiter-Beschriftung im Sammel-Tab)] in Arbeitsreihenfolge
    GROUPS = {
        "★ UNREAL": (("★ ITEMS", "ITEMS"), ("★ WERTE", "WERTE"), ("★ UE-LIVE", "LIVE"), ("★ CHEAT-MENÜ", "CHEAT-MENÜ"),
                     ("★ UE-ENTDECKER", "ENTDECKER"), ("UE-AUTO", "EXPERTE")),
        "★ UNITY": (("★ WERTE UNITY", "SCHNELL"), ("★ UNITY MANUELL", "MANUELL")),
    }
    GROUPED = {inner for subs in GROUPS.values() for inner, _t in subs}

    def __init__(self, app):
        super().__init__(app.root)
        try:
            import branding
            branding.apply_icon_to(self, app.root)
        except Exception:
            pass
        self.app = app
        self.title("REAPERPY  //  WERKZEUGE")
        self.configure(bg=BG)
        self.geometry("1200x760")
        style_ttk(self)
        self.client = None
        self.q = queue.Queue()
        self.net_lock = threading.RLock()
        self.dbg_tab = None

        head = tk.Frame(self, bg=BG_BAR); head.pack(fill="x")
        tk.Label(head, text="▸  WERKZEUGE", bg=BG_BAR, fg=ACCENT, font=FONT_HEAD).pack(side="left", padx=12, pady=8)
        self.lbl_state = tk.Label(head, text="verbinde ...", bg=BG_BAR, fg=WARN, font=FONT_LABEL)
        self.lbl_state.pack(side="right", padx=12)
        button(head, "SESSION LADEN…", self.session_load).pack(side="right", padx=2, pady=4)
        button(head, "SESSION SPEICHERN…", self.session_save).pack(side="right", padx=2, pady=4)

        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        # Anfaenger-Tabs liegen oben, alles Spezielle im Tab FORTGESCHRITTEN (eigenes Notebook)
        self.adv_frame = tk.Frame(self.nb, bg=BG)
        self.adv_nb = ttk.Notebook(self.adv_frame)
        self.adv_nb.pack(fill="both", expand=True)
        self.groups = {name: GroupTab(self.nb, self, name) for name in self.GROUPS}
        self.unreal_group, self.unity_group = self.groups["★ UNREAL"], self.groups["★ UNITY"]
        self.t_mem = MemoryTab(self.adv_nb, self)
        self.t_dis = DisasmTab(self.adv_nb, self)
        self.t_conv = ConverterTab(self.adv_nb, self)
        self.t_cheat = CheatTab(self.nb, self)
        self.t_aob = AobTab(self.adv_nb, self)
        tabs = [(self.t_mem, "SPEICHER"), (self.t_dis, "DISASSEMBLER"), (self.t_conv, "KONVERTER"),
                (self.t_cheat, "CHEATS BEARBEITEN"), (self.t_aob, "AOB / UPDATE")]
        self.scan_tab = None
        try:
            from tools_scan_gui import ScanTab
            self.scan_tab = ScanTab(self.nb, self)
            tabs.insert(1, (self.scan_tab, "WERT SUCHEN"))
        except Exception as e:
            msg = f"Searcher-Tab nicht geladen: {e}"
            self.after(200, lambda msg=msg: self.log(msg, "err"))
        self.ptr_tab = None
        try:
            from tools_pointer_gui import PointerTab
            self.ptr_tab = PointerTab(self.adv_nb, self)
            tabs.insert(2, (self.ptr_tab, "POINTER"))
        except Exception as e:
            msg = f"Pointer-Tab nicht geladen: {e}"
            self.after(200, lambda msg=msg: self.log(msg, "err"))
        try:
            from tools_debug_gui import DebugTab
            self.dbg_tab = DebugTab(self.adv_nb, self)
            tabs.append((self.dbg_tab, "DEBUGGER"))
        except Exception as e:
            msg = f"Debugger-Tab nicht geladen: {e}"
            self.after(200, lambda msg=msg: self.log(msg, "err"))
        self.klog_tab = None
        try:
            from klog_tab import KlogTab
            self.klog_tab = KlogTab(self.adv_nb, self)
            tabs.append((self.klog_tab, "KERNEL-LOG"))
        except Exception as e:
            msg = f"Kernel-Log-Tab nicht geladen: {e}"
            self.after(200, lambda msg=msg: self.log(msg, "err"))
        self.script_tab = None
        try:
            from script_tab import ScriptTab
            self.script_tab = ScriptTab(self.adv_nb, self)
            tabs.append((self.script_tab, "PYTHON-SKRIPT"))
        except Exception as e:
            msg = f"Skript-Tab nicht geladen: {e}"
            self.after(200, lambda msg=msg: self.log(msg, "err"))
        self.extra_tabs = []
        self.discover_tab = None
        self.items_tab = None
        self.values_tab = None
        self.values_tab_unity = None
        self.unity_tab = None
        # jeder Zusatz-Tab einzeln: ein defekter Tab darf die anderen nicht mitreissen
        extra = (("tools_extra_gui", "CallerTab", "FUNKTION AUFRUFEN"),
                 ("tools_extra_gui", "LoggerTab", "FUNKTIONS-LOGGER"),
                 ("tools_extra_gui", "JournalTab", "JOURNAL / UNDO"),
                 ("tools_uelive_gui", "UeLiveTab", "★ UE-LIVE"),
                 ("tools_items_gui", "ItemsTab", "★ ITEMS"),
                 ("tools_values_gui", "ValuesTab", "★ WERTE", {"engine": "ue"}),
                 ("tools_values_gui", "ValuesTab", "★ WERTE UNITY", {"engine": "unity"}),
                 ("tools_discover_gui", "DiscoverTab", "★ UE-ENTDECKER"),
                 ("tools_cheatmenu_gui", "CheatMenuTab", "★ CHEAT-MENÜ"),
                 ("tools_unity_gui", "UnityTab", "★ UNITY MANUELL"),
                 ("tools_ue_gui", "UeTab", "UE-AUTO"))
        group_of = {inner: g for g, subs in self.GROUPS.items() for inner, _t in subs}
        for modname, clsname, name, *kw in extra:
            try:
                cls = getattr(__import__(modname), clsname)
                parent = self.groups[group_of[name]].nb if name in group_of else (
                    self.adv_nb if name in self.ADVANCED else self.nb)
                t = cls(parent, self, **(kw[0] if kw else {}))
                self.extra_tabs.append(t)
                tabs.append((t, name))
                if clsname == "DiscoverTab":
                    self.discover_tab = t
                if clsname == "ItemsTab":
                    self.items_tab = t
                if name == "★ WERTE":
                    self.values_tab = t
                if name == "★ WERTE UNITY":
                    self.values_tab_unity = t
                if clsname == "UnityTab":
                    self.unity_tab = t
            except Exception as e:
                msg = f"Tab {name} nicht geladen: {e}"
                self.after(200, lambda msg=msg: self.log(msg, "err"))
        by_name = {name: t for t, name in tabs}
        try:
            from tools_start_gui import StartTab
            self.start_tab = StartTab(self.nb, self)
            self.nb.add(self.start_tab, text="START")
        except Exception as e:
            self.start_tab = None
            msg = f"Start-Tab nicht geladen: {e}"
            self.after(200, lambda msg=msg: self.log(msg, "err"))
        for name, subs in self.GROUPS.items():                     # Sammel-Tabs fuellen (nur Tabs, die geladen werden konnten)
            for inner, sub_title in subs:
                if inner in by_name:
                    self.groups[name].add(by_name[inner], sub_title)
            by_name[name] = self.groups[name]
        for name in self.SIMPLE:
            if name in by_name:
                self.nb.add(by_name[name], text=name)
        for t, name in tabs:
            if name in self.ADVANCED:
                self.adv_nb.add(t, text=name)
        self.nb.add(self.adv_frame, text="FORTGESCHRITTEN")
        self.easy_tab = by_name.get("★ UE-LIVE")
        if self.start_tab is not None:                             # Einsteiger-Tab zuerst zeigen
            self.nb.select(self.start_tab)
        stash = getattr(app, "tools_stash", None)        # Cheat-Liste/Pointer der letzten Sitzung
        if stash:
            try:
                import session
                session.apply_tools(self, stash)
            except Exception as e:
                msg = f"Sitzung nicht eingesetzt: {e}"
                self.after(200, lambda msg=msg: self.log(msg, "err"))

        self.logbox = textbox(self, height=6, width=80)
        self.logbox.pack(fill="x", padx=6, pady=(0, 6))
        self.logbox.configure(state="disabled")
        self.logbox._is_log = True
        self.logbox._save_log = self.save_log
        try:
            import tools_ctx
            tools_ctx.install(app.root)
        except Exception:
            pass
        for tag, col in (("ok", ACCENT), ("err", ERROR), ("warn", WARN), ("info", TEXT_DIM)):
            self.logbox.tag_configure(tag, foreground=col)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self.after(30, self.apply_language))
        self.adv_nb.bind("<<NotebookTabChanged>>", lambda _e: self.after(30, self.apply_language))
        for g in self.groups.values():
            g.nb.bind("<<NotebookTabChanged>>", lambda _e: self.after(30, self.apply_language))
        self.after(200, self.apply_language)
        self.after(80, self._poll)
        self.bg(self._connect, lambda _r: self._set_state("verbunden", ACCENT),
                lambda e: self._set_state(f"Fehler: {e}", ERROR))

    # ---- Verbindung ----
    def _connect(self):
        be = self.app.backend
        if not be.client or be.pid is None:
            raise RuntimeError("Haupt-Fenster nicht verbunden (erst VERBINDEN)")
        c = PS5DebugClient(be.host, be.port)
        c.connect()
        c.pid = be.pid
        self.client = c
        return True

    def _set_state(self, text, color):
        self.lbl_state.configure(text=text, fg=color)

    # ---- Hintergrund-Jobs ----
    def bg(self, fn, ok=None, err=None, lock=True):
        """Job im Hintergrund. lock=False für Jobs mit eigener Verbindung (z.B. Scanner)."""
        def run():
            try:
                if lock:
                    with self.net_lock:
                        res = fn()
                else:
                    res = fn()
            except Exception as e:
                self.q.put((err or self._log_err, e))
            else:
                self.q.put((ok, res))
        threading.Thread(target=run, daemon=True).start()

    def _log_err(self, e):
        self.log(f"{type(e).__name__}: {e}", "err")

    def _poll(self):
        try:
            while True:
                cb, val = self.q.get_nowait()
                if cb:
                    try:
                        cb(val)
                    except Exception as e:
                        self.log(f"UI-Fehler: {e}", "err")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(80, self._poll)

    def log(self, msg, kind="info"):
        if not self.winfo_exists():
            return
        self.logbox.configure(state="normal")
        try:
            import tools_i18n
            msg = tools_i18n.translate(str(msg))
        except Exception:
            pass
        try:
            import logsetup
            logsetup.log("[tools] " + str(msg), kind)
        except Exception:
            pass
        self.logbox.insert("end", time.strftime("%H:%M:%S ") + str(msg) + "\n", kind)
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def apply_language(self):
        """Sprache des Hauptfensters (DE/EN) auf alle Tabs anwenden; im EN-Modus alle 2 s nachziehen
        (Texte, die die Tabs zwischendurch deutsch setzen)."""
        try:
            import tools_i18n
            if not self.winfo_exists():
                return
            tools_i18n.apply_to(self)
            if tools_i18n.lang() == "en" and not getattr(self, "_i18n_tick", False):
                self._i18n_tick = True
                self.after(2000, self._i18n_loop)
        except Exception:
            pass

    def _i18n_loop(self):
        self._i18n_tick = False
        try:
            import tools_i18n
            if self.winfo_exists() and tools_i18n.lang() == "en":
                self.apply_language()
        except Exception:
            pass

    def save_log(self):
        path = filedialog.asksaveasfilename(title="Log speichern", defaultextension=".txt", initialfile="werkzeuge_log.txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.logbox.get("1.0", "end-1c"))

    def ui(self, fn):
        """Thread-sicher etwas im UI-Thread ausführen (z.B. aus dem Debugger-Callback)."""
        self.q.put((lambda _v: fn(), None))

    # ---- Navigation zwischen Tabs ----
    def show_tab(self, tab):
        """Tab nach vorne holen - auch wenn er im Notebook FORTGESCHRITTEN oder in einem Sammel-Tab (UNREAL/UNITY) liegt."""
        if tab is None:
            return
        try:
            master = getattr(tab, "master", None)
            group = getattr(master, "group", None)
            if master is self.adv_nb:
                self.nb.select(self.adv_frame)
                self.adv_nb.select(tab)
            elif group is not None:
                self.nb.select(group)
                master.select(tab)
            else:
                self.nb.select(tab)
        except Exception:
            pass

    def goto_memory(self, address):
        self.show_tab(self.t_mem); self.t_mem.goto(address)

    def goto_disasm(self, address):
        self.show_tab(self.t_dis); self.t_dis.goto(address)

    def to_pointer(self, address, vname="Int32"):
        if not self.ptr_tab:
            return self.log("Pointer-Tab nicht verfügbar", "err")
        self.show_tab(self.ptr_tab)
        self.ptr_tab.set_target(address, vname)
        self.log("Pointer: 1) KARTE ERSTELLEN  2) PFADE SUCHEN", "info")

    def to_debug_watch(self, address, size=4):
        if not self.dbg_tab:
            return self.log("Debugger-Tab nicht verfügbar", "err")
        self.show_tab(self.dbg_tab)
        self.dbg_tab.v_wp.set(hexs(address))
        self.dbg_tab.v_wsize.set(str(size if size in (1, 2, 4, 8) else 4))
        self.log("Debugger: ATTACH, dann WATCHPOINT SETZEN (Typ 'schreiben'). RIP des Treffers zeigt "
                 "HINTER die schreibende Instruktion - die davor ist der Schreiber.", "info")

    def to_cheat(self, data):
        self.show_tab(self.t_cheat); self.t_cheat.fill(data)

    def to_cave_hook(self, data):
        self.show_tab(self.t_cheat); self.t_cheat.fill_hook(data)

    # ---- Sitzung ----
    def session_save(self):
        import session
        app = self.app
        fn = filedialog.asksaveasfilename(
            parent=self, initialdir=app.PATCH_DIR or None,
            initialfile=os.path.basename(session.default_path(app.PATCH_DIR, app.current_project)),
            defaultextension=session.EXT,
            filetypes=[("Cheat-Session", "*" + session.EXT), ("JSON", "*.json")])
        if not fn:
            return
        try:
            session.save(fn, session.collect(app))
            self.log(f"Sitzung gespeichert: {fn}", "ok")
        except Exception as e:
            messagebox.showerror("Sitzung", str(e), parent=self)

    def session_load(self):
        import session
        app = self.app
        fn = filedialog.askopenfilename(
            parent=self, initialdir=app.PATCH_DIR or None,
            filetypes=[("Cheat-Session", "*" + session.EXT), ("JSON", "*.json")])
        if not fn:
            return
        try:
            data = session.load(fn)
        except Exception as e:
            return messagebox.showerror("Sitzung", str(e), parent=self)
        n_active = len((data.get("patches") or {}).get("active", []))
        activate = bool(n_active) and messagebox.askyesno(
            "Sitzung", f"{n_active} gespeicherte aktive Patch(es) jetzt einschalten?", parent=self)
        info = session.apply(app, data, activate=activate)
        if info["project_mismatch"]:
            self.log("Hinweis: Sitzung gehört zu einem anderen Projekt", "warn")
        self.log(f"Sitzung geladen: {info['cheats']} Cheat(s), {info['patches']} Patch(es) vorgemerkt"
                 f"{', ' + str(info['activated']) + ' aktiviert' if activate else ''}"
                 f"{', ' + str(info['missing']) + ' fehlen im Ordner' if info['missing'] else ''}", "ok")

    def on_game_changed(self):
        """Spiel wurde neu gestartet (neue PID): Verbindungen/Sitzungen der Tabs sind ungültig."""
        be = self.app.backend
        if self.client:
            self.client.pid = be.pid
        try:
            if self.dbg_tab:
                self.dbg_tab.shutdown()
                self.dbg_tab.sess = None
                self.dbg_tab.lbl.configure(text="nicht attached", fg=TEXT_DIM)
            if self.scan_tab:
                self.scan_tab.shutdown()
                self.scan_tab.sc = None
                self.scan_tab.running = False
            if self.ptr_tab:
                self.ptr_tab.pm = None
        except Exception:
            pass
        self.log(f"Spiel neu gestartet - neue PID {be.pid}; Scans/Debugger zurückgesetzt", "warn")

    def show_list(self, title, addrs):
        d = tk.Toplevel(self); d.title(title); d.configure(bg=BG)
        tv = tree(d, [("a", "ADRESSE"), ("o", "OFFSET")], [200, 120], height=16)
        tv.pack(fill="both", expand=True, padx=8, pady=8)
        for a in addrs:
            tv.insert("", "end", values=(f"{a:016X}", f"+{a - self.app.IMAGE_BASE:X}"))
        tv.bind("<Double-1>", lambda _e: tv.selection() and
                self.goto_disasm(int(tv.item(tv.selection()[0], "values")[0], 16)))
        self.log(f"{title}: {len(addrs)} Treffer", "ok" if addrs else "warn")

    def close(self):
        try:
            import session
            self.app.tools_stash = session.collect_tools(self)    # Cheat-Liste überlebt das Schließen
        except Exception:
            pass
        try:
            if self.dbg_tab:
                self.dbg_tab.shutdown()
        except Exception:
            pass
        for _t in (getattr(self, "klog_tab", None), getattr(self, "script_tab", None),
                   *getattr(self, "extra_tabs", [])):
            try:
                if _t:
                    _t.shutdown()
            except Exception:
                pass
        try:
            if self.scan_tab:
                self.scan_tab.shutdown()
            if self.ptr_tab:
                self.ptr_tab.shutdown()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.destroy()
