"""tools_extra_gui.py - neue Tabs in ReaperPy 5.0: FUNKTION AUFRUFEN, FUNKTIONS-LOGGER, JOURNAL.

Idee von Funktions-Caller und -Logger: PS5Debug-studio (alfizari, Apache-2.0).  Umsetzung eigen
(siehe caller.py / logger.py / journal.py - dort steht die ganze Logik, hier nur die Oberflaeche).
"""
import csv
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import asm_tools as AT
import caller as CL
import logger as LG
from tools_common import (BG, BG_CARD, ACCENT, TEXT_DIM, WARN, ERROR, FONT_LABEL, BaseTab,
                          button, entry, label, textbox, tree, with_scroll, hexs)


def _chk(parent, text, var, cmd=None):
    return tk.Checkbutton(parent, text=text, variable=var, command=cmd, bg=BG, fg=TEXT_DIM,
                          selectcolor=BG_CARD, activebackground=BG, activeforeground=ACCENT,
                          font=FONT_LABEL)


# ==================================================================
# Tab: Funktion aufrufen
# ==================================================================
class CallerTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.bufs = None
        self.history = []

        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 2))
        label(top, "FUNKTION").pack(side="left")
        self.v_fn = tk.StringVar(value="base+")
        e = entry(top, self.v_fn, 26); e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _e: self.run())
        self.v_safe = tk.BooleanVar(value=True)
        _chk(top, "Trampolin (sicher)", self.v_safe).pack(side="left", padx=6)
        button(top, "AUFRUFEN", self.run, accent=True).pack(side="left", padx=4)
        button(top, "→ DISASM", self._to_dis).pack(side="right")

        grid = tk.Frame(self, bg=BG); grid.pack(fill="x", padx=8, pady=2)
        self.v_args = []
        for i, reg in enumerate(("rdi", "rsi", "rdx", "rcx", "r8", "r9")):
            label(grid, reg.upper()).grid(row=i // 3, column=(i % 3) * 2, sticky="e", padx=(6, 2), pady=2)
            v = tk.StringVar(value="0"); self.v_args.append(v)
            entry(grid, v, 24).grid(row=i // 3, column=(i % 3) * 2 + 1, padx=2, pady=2)
        label(self, "Argumente: 0x1234 | 123 | -5 | base+0x10 | @puffer | @puffer+8 | \"Text\"   "
                    "(Float-Argumente gehen nicht - nur Ganzzahl-Register)").pack(anchor="w", padx=14)

        mid = tk.Frame(self, bg=BG); mid.pack(fill="both", expand=True, padx=8, pady=6)
        left = tk.Frame(mid, bg=BG); left.pack(side="left", fill="both", expand=True)
        label(left, "ERGEBNIS (RAX)").pack(anchor="w")
        self.out = textbox(left, height=12, width=60)
        self.out.configure(state="disabled")
        with_scroll(left, self.out)

        right = tk.Frame(mid, bg=BG); right.pack(side="right", fill="y", padx=(8, 0))
        label(right, "PUFFER IM SPIEL").pack(anchor="w")
        row = tk.Frame(right, bg=BG); row.pack(fill="x")
        self.v_bname, self.v_bsize = tk.StringVar(value="buf"), tk.StringVar(value="0x1000")
        entry(row, self.v_bname, 10).pack(side="left", padx=2)
        entry(row, self.v_bsize, 8).pack(side="left", padx=2)
        button(row, "ANLEGEN", self.buf_alloc, accent=True).pack(side="left", padx=2)
        self.tv = tree(right, [("n", "NAME"), ("a", "ADRESSE"), ("s", "GROESSE")], [80, 130, 70], height=7)
        self.tv.pack(fill="x", pady=4)
        self.v_bdata = tk.StringVar()
        entry(right, self.v_bdata, 34).pack(fill="x", pady=2)
        row2 = tk.Frame(right, bg=BG); row2.pack(fill="x")
        button(row2, "HEX SCHREIBEN", lambda: self.buf_write(False)).pack(side="left", padx=2)
        button(row2, "TEXT", lambda: self.buf_write(True)).pack(side="left", padx=2)
        button(row2, "LESEN", self.buf_read).pack(side="left", padx=2)
        row3 = tk.Frame(right, bg=BG); row3.pack(fill="x", pady=2)
        button(row3, "→ SPEICHER", self.buf_goto).pack(side="left", padx=2)
        button(row3, "ALLE FREIGEBEN", self.buf_free).pack(side="left", padx=2)
        label(right, "Aufruf haelt einen Spiel-Thread kurz an.\nNICHT parallel zum Debugger\n"
                     "benutzen, wenn das Spiel angehalten ist.", dim=True).pack(anchor="w", pady=6)

    # ---- Hilfen ----
    def _bufs(self):
        c = self.win.client
        if c is None:
            raise RuntimeError("nicht verbunden")
        if self.bufs is None or self.bufs.client is not c:
            self.bufs = CL.RemoteBuffers(c)
        return self.bufs

    def _put(self, text):
        self.out.configure(state="normal"); self.out.delete("1.0", "end")
        self.out.insert("1.0", text); self.out.configure(state="disabled")

    def _to_dis(self):
        try:
            self.win.goto_disasm(self.addr(self.v_fn.get()))
        except Exception as e:
            self.log(str(e), "err")

    # ---- Aufruf ----
    def run(self):
        try:
            rip = self.addr(self.v_fn.get())
            bufs = self._bufs()
        except Exception as e:
            return self.log(str(e), "err")
        texts = [v.get() for v in self.v_args]
        safe = self.v_safe.get()
        if not messagebox.askyesno("Funktion aufrufen",
                                   f"{rip:#x} im Spiel ausfuehren?\nFalsche Argumente koennen das Spiel "
                                   "abstuerzen lassen.", parent=self.win):
            return

        def job():
            args = CL.parse_args(texts, bufs, resolver=self.addr)
            t0 = time.time()
            rax = CL.do_call(self.win.client, rip, args, safe=safe)
            return args, rax, time.time() - t0, CL.describe_result(self.win.client, rax)

        def ok(res):
            args, rax, dt, desc = res
            head = f"{time.strftime('%H:%M:%S')}  call {rip:#x}({', '.join(f'{a:#x}' for a in args)})  [{dt * 1000:.0f} ms]"
            body = "\n".join(f"  {k:<12}{v}" for k, v in desc)
            self.history.insert(0, head + "\n" + body)
            self._put("\n\n".join(self.history[:20]))
            self.log(f"call {rip:#x} -> RAX={rax:#x}", "ok")
            self._fill_bufs()
        self.bg(job, ok)

    # ---- Puffer ----
    def _fill_bufs(self):
        self.tv.delete(*self.tv.get_children())
        if self.bufs:
            for n, (a, s) in self.bufs.items.items():
                self.tv.insert("", "end", values=(n, f"{a:#x}", f"{s:#x}"))

    def _sel_buf(self):
        sel = self.tv.selection()
        if not sel:
            raise ValueError("erst einen Puffer in der Liste waehlen")
        return self.tv.item(sel[0], "values")[0]

    def buf_alloc(self):
        try:
            bufs, name, size = self._bufs(), self.v_bname.get().strip(), int(self.v_bsize.get(), 0)
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(lambda: bufs.alloc(name, size),
                lambda a: (self.log(f"Puffer '{name}' @ {a:#x} ({size:#x} Byte)", "ok"), self._fill_bufs()))

    def buf_write(self, as_text):
        try:
            bufs, name = self._bufs(), self._sel_buf()
            raw = (self.v_bdata.get().encode("utf-8") + b"\0") if as_text else AT.parse_hex_bytes(self.v_bdata.get())
            if not raw:
                raise ValueError("keine Daten")
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(lambda: bufs.write(name, raw), lambda _r: self.log(f"{len(raw)} Byte nach '{name}'", "ok"))

    def buf_read(self):
        try:
            bufs, name = self._bufs(), self._sel_buf()
        except Exception as e:
            return self.log(str(e), "err")
        import memtools
        self.bg(lambda: (bufs.items[name][0], bufs.read(name, min(bufs.items[name][1], 0x400))),
                lambda r: self._put(memtools.hexdump(r[1], r[0])))

    def buf_goto(self):
        try:
            self.win.goto_memory(self._bufs().items[self._sel_buf()][0])
        except Exception as e:
            self.log(str(e), "err")

    def buf_free(self):
        try:
            bufs = self._bufs()
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(bufs.free_all, lambda _r: (self._fill_bufs(), self.log("Puffer freigegeben", "ok")))

    def shutdown(self):
        try:
            import ps5_more
            if self.win.client is not None:
                ps5_more.forget_trampolines(self.win.client)
        except Exception:
            pass


# ==================================================================
# Tab: Funktions-Logger
# ==================================================================
class LoggerTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.sess = None
        self.rows = []                  # alle Eintraege (dicts)
        self.running = False

        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 2))
        label(top, "FUNKTION").pack(side="left")
        self.v_fn = tk.StringVar(value="base+")
        entry(top, self.v_fn, 24).pack(side="left", padx=6)
        label(top, "RING").pack(side="left")
        self.v_ring = tk.StringVar(value="1024")
        ttk.Combobox(top, textvariable=self.v_ring, values=("256", "1024", "4096"), width=6,
                     state="readonly").pack(side="left", padx=4)
        self.v_thr = tk.BooleanVar(value=False)
        _chk(top, "Thread-ID", self.v_thr).pack(side="left", padx=6)
        self.b_start = button(top, "▶ START", self.start, accent=True); self.b_start.pack(side="left", padx=2)
        self.b_stop = button(top, "■ STOP", self.stop); self.b_stop.pack(side="left", padx=2)
        button(top, "LEEREN", self.clear).pack(side="left", padx=2)
        button(top, "CSV…", self.export).pack(side="right")
        self.lbl = label(self, "Aus. Hook: erste ≥8 Byte der Funktion werden durch einen Sprung ersetzt, "
                               "STOP stellt sie zurueck.")
        self.lbl.pack(anchor="w", padx=10)

        pan = ttk.PanedWindow(self, orient="horizontal"); pan.pack(fill="both", expand=True, padx=8, pady=6)
        lf = tk.Frame(pan, bg=BG); pan.add(lf, weight=3)
        cols = [("n", "#"), ("ret", "RUECKSPRUNG"), ("rdi", "RDI"), ("rsi", "RSI"), ("rdx", "RDX"),
                ("rcx", "RCX"), ("r8", "R8"), ("r9", "R9"), ("th", "THREAD")]
        self.tv = tree(lf, cols, [60, 120, 110, 110, 110, 110, 90, 90, 100], height=18)
        with_scroll(lf, self.tv)
        self.tv.bind("<Double-1>", self._dbl)
        rf = tk.Frame(pan, bg=BG); pan.add(rf, weight=1)
        label(rf, "NACH AUFRUFER").pack(anchor="w")
        self.grp = tree(rf, [("c", "ANZ"), ("ret", "RUECKSPRUNG"), ("off", "OFFSET")], [50, 130, 90], height=18)
        self.grp.pack(fill="both", expand=True)
        self.grp.bind("<Double-1>", self._grp_dbl)

    # ---- Steuerung ----
    def start(self):
        if self.running:
            return
        try:
            a = self.addr(self.v_fn.get()); ring = int(self.v_ring.get()); thr = self.v_thr.get()
        except Exception as e:
            return self.log(str(e), "err")
        if not messagebox.askyesno("Logger starten",
                                   f"Funktion {a:#x} patchen (Sprung in Code-Cave)?\nSteht am Funktionsanfang "
                                   "ein Sprungziel mitten in den ersten 8 Byte, kann das Spiel abstuerzen.",
                                   parent=self.win):
            return
        sess = LG.LoggerSession(self.win.app.backend, a, ring, thr)

        def ok(info):
            self.sess, self.running = sess, True
            self.lbl.configure(text=f"AKTIV  Hook {a:#x}  Cave {info['cave']:#x} ({info['cave_size']} B)  "
                                    f"Puffer {info['data']:#x}", fg=ACCENT)
            self.log(f"Logger aktiv @ {a:#x}", "ok")
            self.after(300, self._tick)
        self.bg(sess.start, ok)

    def stop(self):
        if not self.sess or not self.running:
            return
        sess, self.running = self.sess, False
        self.bg(sess.stop, lambda _r: (self.lbl.configure(text="Aus - Original-Bytes zurueckgeschrieben.",
                                                          fg=TEXT_DIM), self.log("Logger gestoppt", "ok")))

    def shutdown(self):
        if self.sess and self.running:
            self.running = False
            try:
                self.sess.stop()
            except Exception:
                pass

    def clear(self):
        self.rows.clear(); self._redraw()

    def _tick(self):
        if not self.running or not self.winfo_exists():
            return
        sess = self.sess

        def ok(recs):
            if recs:
                self.rows += recs
                self.rows = self.rows[-20000:]
                self._append(recs)
            if sess.lost:
                self.lbl.configure(text=self.lbl.cget("text").split("  VERLOREN")[0]
                                   + f"  VERLOREN {sess.lost} (Ring zu klein / zu schnell)", fg=WARN)
            self.after(300, self._tick)
        self.bg(sess.poll, ok, lambda e: (self.log(f"Logger-Poll: {e}", "err"), self.after(1000, self._tick)))

    # ---- Anzeige ----
    def _row(self, r):
        return (r["index"], f"{r['ret']:#x} (+{r['ret'] - self.base:#x})", *(f"{r[k]:#x}" for k in
                ("rdi", "rsi", "rdx", "rcx", "r8", "r9")), f"{r['thread']:#x}" if r["thread"] else "")

    def _append(self, recs):
        for r in recs[-500:]:
            self.tv.insert("", "end", values=self._row(r))
        kids = self.tv.get_children()
        if len(kids) > 3000:
            self.tv.delete(*kids[:len(kids) - 3000])
        self.tv.yview_moveto(1.0)
        self._groups()

    def _redraw(self):
        self.tv.delete(*self.tv.get_children())
        self._append(self.rows[-500:]) if self.rows else self._groups()

    def _groups(self):
        cnt = {}
        for r in self.rows:
            cnt[r["ret"]] = cnt.get(r["ret"], 0) + 1
        self.grp.delete(*self.grp.get_children())
        for ret, n in sorted(cnt.items(), key=lambda kv: -kv[1])[:200]:
            self.grp.insert("", "end", values=(n, f"{ret:#x}", f"+{ret - self.base:#x}"))

    def _dbl(self, _e):
        sel = self.tv.selection()
        if sel:
            self.win.goto_disasm(int(self.tv.item(sel[0], "values")[1].split()[0], 16) - 5)

    def _grp_dbl(self, _e):
        sel = self.grp.selection()
        if sel:
            self.win.goto_disasm(int(self.grp.item(sel[0], "values")[1], 16) - 5)

    def export(self):
        if not self.rows:
            return self.log("nichts zu exportieren", "warn")
        fn = filedialog.asksaveasfilename(parent=self.win, defaultextension=".csv",
                                          filetypes=[("CSV", "*.csv")])
        if not fn:
            return
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["index", *LG.FIELDS])
            for r in self.rows:
                w.writerow([r["index"], *(f"{r[k]:#x}" for k in LG.FIELDS)])
        self.log(f"{len(self.rows)} Aufrufe nach {fn}", "ok")


# ==================================================================
# Tab: Journal (Rueckgaengig)
# ==================================================================
class JournalTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        import journal
        self.j = journal.WriteJournal()
        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 2))
        self.v_on = tk.BooleanVar(value=True)
        _chk(top, "Schreibzugriffe aufzeichnen", self.v_on,
             lambda: setattr(self.j, "enabled", self.v_on.get())).pack(side="left")
        button(top, "AKTUALISIEREN", self.refresh).pack(side="left", padx=8)
        button(top, "AUSGEWAEHLTE ZURUECK", self.undo_sel, accent=True).pack(side="left", padx=2)
        button(top, "ALLES ZURUECK", self.undo_all).pack(side="left", padx=2)
        button(top, "LEEREN", lambda: (self.j.clear(), self.refresh())).pack(side="left", padx=2)
        label(self, "Jeder Schreibzugriff der Werkzeuge (Hex-Editor, Searcher, Skripte, Aufrufe ...) wird mit den "
                    "alten Bytes gemerkt. Freeze-Ticks und Schreibzugriffe > 64 KB nicht.").pack(anchor="w", padx=10)
        box = tk.Frame(self, bg=BG); box.pack(fill="both", expand=True, padx=8, pady=6)
        self.tv = tree(box, [("t", "ZEIT"), ("a", "ADRESSE"), ("n", "LAENGE"), ("o", "ALT"), ("w", "NEU"),
                             ("s", "QUELLE")], [80, 130, 60, 200, 200, 120], height=20)
        with_scroll(box, self.tv)
        self.tv.bind("<Double-1>", lambda _e: self.tv.selection() and self.win.goto_memory(
            int(self.tv.item(self.tv.selection()[0], "values")[1], 16)))
        self.after(500, self._auto)

    def attach(self):
        if self.win.client is not None:
            self.j.attach(self.win.client)

    def _auto(self):
        if not self.winfo_exists():
            return
        self.attach()
        if self.winfo_ismapped():
            self.refresh()
        self.after(1500, self._auto)

    def refresh(self):
        self.tv.delete(*self.tv.get_children())
        for i, e in enumerate(reversed(self.j.entries[-1000:])):
            vals = e.line()
            self.tv.insert("", "end", iid=str(len(self.j.entries) - 1 - i),
                           values=vals, tags=("undone",) if e.undone else ())
        self.tv.tag_configure("undone", foreground=TEXT_DIM)

    def undo_sel(self):
        ids = [int(i) for i in self.tv.selection()]
        if not ids:
            return self.log("nichts ausgewaehlt", "warn")
        ents = [self.j.entries[i] for i in sorted(ids, reverse=True) if i < len(self.j.entries)]

        def job():
            return sum(1 for e in ents if self.j.undo(e))
        self.bg(job, lambda n: (self.log(f"{n} Aenderung(en) rueckgaengig", "ok"), self.refresh()))

    def undo_all(self):
        n = len([e for e in self.j.entries if not e.undone])
        if not n or not messagebox.askyesno("Journal", f"{n} Aenderung(en) zurueckschreiben?", parent=self.win):
            return
        self.bg(self.j.undo_all, lambda k: (self.log(f"{k} Aenderung(en) rueckgaengig", "ok"), self.refresh()))

    def shutdown(self):
        self.j.detach()
