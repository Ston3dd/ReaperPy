"""tools_assist_gui.py - Tab ASSISTENT: in vier Schritten vom Wert im Spiel zum fertigen Cheat (Logik: assist.py).

    1 Wert finden      Zahl eintragen (oder: Zahl unbekannt) und SUCHEN       -> benutzt den Scanner (Tab WERT SUCHEN)
    2 Eingrenzen       Wert im Spiel aendern, neue Zahl eintragen, EINGRENZEN -> wenige Treffer bleiben uebrig
    3 Wer aendert ihn? Watchpoint auf den Treffer; welcher Befehl schreibt?   -> benutzt den Debugger (Tab DEBUGGER)
    4 Cheat bauen      PRESET waehlen                                          -> Patch oder Cave im Cheat-Editor
"""
import tkinter as tk

import assist as A
import asm_tools as AT
import ps5_ext as X
import scanner as SC
import tools_i18n
from tools_common import (ACCENT, BG, FONT_HEAD, FONT_LABEL, FONT_TEXT, TEXT_DIM, WARN, BaseTab, button, entry, label, tree,
                          with_scroll)

MAX_ROWS = 50
POLL_MS = 400


def _head(parent, text):
    tk.Label(parent, text=text, bg=BG, fg=ACCENT, font=FONT_HEAD, anchor="w").pack(fill="x", padx=12, pady=(12, 2))


def _hint(parent, text):
    lb = tk.Label(parent, text=text, bg=BG, fg=TEXT_DIM, font=FONT_TEXT, anchor="w", justify="left", wraplength=900)
    lb.pack(fill="x", padx=12)
    return lb


class AssistTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.writers = A.Writers()
        self.cands = {}                       # iid -> (Adresse, Wertname)
        self.watching = False
        self.watch_idx = None
        self.watch_addr = None
        self.seen = set()
        self.vname = "Int32"

        label(self, "In vier Schritten vom Wert im Spiel zum fertigen Cheat. Du musst kein Assembler koennen.").pack(
            anchor="w", padx=12, pady=(8, 0))

        # ---- 1 ----
        _head(self, "1  WERT FINDEN")
        _hint(self, "Lies im Spiel eine Zahl ab (zum Beispiel dein Leben oder dein Geld) und trage sie hier ein. "
                    "Kommazahlen mit Punkt. Siehst du nur eine Leiste ohne Zahl, waehle 'Zahl unbekannt'.")
        r1 = tk.Frame(self, bg=BG); r1.pack(fill="x", padx=12, pady=4)
        self.v_unknown = tk.BooleanVar(value=False)
        tk.Radiobutton(r1, text="Ich kenne die Zahl", value=False, variable=self.v_unknown, bg=BG, fg=ACCENT,
                       selectcolor=BG, activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL).pack(side="left")
        tk.Radiobutton(r1, text="Zahl unbekannt", value=True, variable=self.v_unknown, bg=BG, fg=ACCENT,
                       selectcolor=BG, activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL).pack(side="left", padx=8)
        label(r1, "ZAHL").pack(side="left", padx=(16, 4))
        self.v_num = tk.StringVar()
        e = entry(r1, self.v_num, 12)
        e.pack(side="left")
        e.bind("<Return>", lambda _e: self.start_search())
        button(r1, "SUCHEN", self.start_search, accent=True).pack(side="left", padx=8)

        # ---- 2 ----
        _head(self, "2  EINGRENZEN")
        _hint(self, "Aendere den Wert im Spiel (zum Beispiel ein Leben verlieren) und trage die neue Zahl ein. "
                    "Bei unbekannter Zahl: sage, ob der Wert gefallen, gestiegen oder gleich geblieben ist. "
                    "Wiederhole das, bis nur noch wenige Treffer uebrig sind.")
        r2 = tk.Frame(self, bg=BG); r2.pack(fill="x", padx=12, pady=4)
        label(r2, "NEUE ZAHL").pack(side="left")
        self.v_new = tk.StringVar()
        e2 = entry(r2, self.v_new, 12)
        e2.pack(side="left", padx=8)
        e2.bind("<Return>", lambda _e: self.narrow("exact"))
        button(r2, "EINGRENZEN", lambda: self.narrow("exact"), accent=True).pack(side="left", padx=2)
        button(r2, "GEFALLEN", lambda: self.narrow("down")).pack(side="left", padx=(12, 2))
        button(r2, "GESTIEGEN", lambda: self.narrow("up")).pack(side="left", padx=2)
        button(r2, "GLEICH GEBLIEBEN", lambda: self.narrow("same")).pack(side="left", padx=2)
        button(r2, "NEU STARTEN", self.restart).pack(side="right", padx=2)
        self.lbl_count = label(self, "Noch nicht gesucht.")
        self.lbl_count.pack(anchor="w", padx=12)
        fr = tk.Frame(self, bg=BG); fr.pack(fill="x", padx=12, pady=(2, 0))
        self.tv_c = tree(fr, [("a", "ADRESSE"), ("v", "WERT JETZT")], [200, 160], height=4,
                         empty="Noch keine Treffer. Gib oben die Zahl ein und klicke SUCHEN.")
        with_scroll(fr, self.tv_c)
        button(self, "WERTE AKTUALISIEREN", self.refresh_candidates).pack(anchor="w", padx=12, pady=2)

        # ---- 3 ----
        _head(self, "3  WER AENDERT DEN WERT?")
        _hint(self, "Markiere oben den Treffer, dessen Wert im Spiel mitgeht, und klicke BEOBACHTEN. Dann loese im Spiel die "
                    "Aenderung aus (Schaden nehmen, Geld ausgeben). Das Spiel laeuft dabei weiter.")
        r3 = tk.Frame(self, bg=BG); r3.pack(fill="x", padx=12, pady=4)
        self.b_watch = button(r3, "BEOBACHTEN", self.start_watch, accent=True)
        self.b_watch.pack(side="left")
        button(r3, "STOPP", self.stop_watch).pack(side="left", padx=4)
        self.lbl_watch = label(r3, "Aus.")
        self.lbl_watch.pack(side="left", padx=12)
        fr3 = tk.Frame(self, bg=BG); fr3.pack(fill="x", padx=12)
        self.tv_w = tree(fr3, [("a", "BEFEHL @"), ("i", "BEFEHL"), ("t", "WAS PASSIERT"), ("n", "ANZAHL")],
                         [150, 260, 400, 70], height=4,
                         empty="Noch nichts beobachtet. Klicke BEOBACHTEN und ändere den Wert im Spiel.")
        with_scroll(fr3, self.tv_w)

        # ---- 4 ----
        _head(self, "4  CHEAT ERSTELLEN")
        _hint(self, "Markiere den Befehl, der deinen Wert aendert, und waehle ein PRESET (zum Beispiel: Wert sinkt nicht mehr).")
        r4 = tk.Frame(self, bg=BG); r4.pack(fill="x", padx=12, pady=4)
        button(r4, "PRESET…", self.to_preset, accent=True).pack(side="left")
        button(r4, "IM DISASSEMBLER", self.to_disasm).pack(side="left", padx=4)

    # ------------------------------------------------------------------ Hilfen
    def _scan(self):
        st = getattr(self.win, "scan_tab", None)
        if st is None:
            self.log("Der Tab WERT SUCHEN ist nicht verfügbar", "err")
        return st

    def _await_scan(self, st, then):
        if not self.winfo_exists():
            return
        if st.running:
            self.after(POLL_MS, lambda: self._await_scan(st, then))
        else:
            then()

    def _lang(self):
        return tools_i18n.lang()

    # ------------------------------------------------------------------ Schritt 1 und 2
    def start_search(self):
        st = self._scan()
        if st is None:
            return
        try:
            plan = A.value_plan(self.v_num.get(), unknown=self.v_unknown.get())
        except ValueError as e:
            return self.log(str(e), "warn")
        if st.running:
            return self.log("Es läuft schon ein Scan", "warn")
        self.vname = plan["vname"]
        st.vt.set(plan["vname"])
        st._ct_values(first=True)
        st.ct.set(plan["ctype"])
        st._ct_changed()
        st.v1.set(plan["text"])
        self.writers = A.Writers()
        self._fill_writers()
        st.scan_first()
        if st.running:
            self.lbl_count.configure(text="Suche läuft ...", fg=WARN)
            self._await_scan(st, lambda: self._after_scan(first=True))

    def narrow(self, kind):
        st = self._scan()
        if st is None:
            return
        if not st.sc or not st.sc.first_scan_done:
            return self.log("Erst in Schritt 1 SUCHEN", "warn")
        if st.running:
            return self.log("Es läuft schon ein Scan", "warn")
        if kind == "exact":
            try:
                plan = A.value_plan(self.v_new.get())
            except ValueError as e:
                return self.log(str(e), "warn")
            st.ct.set("Ungefähr (Float)" if st.sc.vname == "Float" else "Genau")
            st.v1.set(plan["text"])
        else:
            st.ct.set({"down": "Kleiner geworden", "up": "Größer geworden", "same": "Unverändert"}[kind])
            st.v1.set("")
        st._ct_changed()
        st.scan_next()
        if st.running:
            self.lbl_count.configure(text="Grenze ein ...", fg=WARN)
            self._await_scan(st, lambda: self._after_scan(first=False))

    def restart(self):
        st = self._scan()
        if st is None:
            return
        if st.running:
            return self.log("Erst abbrechen (Tab WERT SUCHEN)", "warn")
        st.new_scan()
        self.tv_c.delete(*self.tv_c.get_children())
        self.cands.clear()
        self.lbl_count.configure(text="Noch nicht gesucht.", fg=TEXT_DIM)

    def _after_scan(self, first):
        st = self._scan()
        sc = st.sc if st else None
        if sc is None or not sc.first_scan_done:
            self.lbl_count.configure(text="Die Suche ist fehlgeschlagen - Details im Log.", fg=WARN)
            return
        kind, msg = A.advice(sc.count, self._lang(), first=first)
        self.lbl_count.configure(text=msg, fg=ACCENT if kind == "good" else WARN)
        self.vname = sc.vname
        self.tv_c.delete(*self.tv_c.get_children())
        self.cands.clear()
        if 0 < sc.count <= MAX_ROWS:
            self.refresh_candidates()

    def refresh_candidates(self):
        st = self._scan()
        sc = st.sc if st else None
        if sc is None or not sc.first_scan_done or not 0 < sc.count <= MAX_ROWS:
            return
        vname = sc.vname

        def ok(rows):
            keep = self.tv_c.selection()
            self.tv_c.delete(*self.tv_c.get_children())
            self.cands.clear()
            for r in rows:
                iid = str(r["addr"])
                self.cands[iid] = (r["addr"], vname)
                self.tv_c.insert("", "end", iid=iid, values=(f"{r['addr']:#x}", SC.fmt_value(vname, r["cur"])))
            for k in keep:
                if self.tv_c.exists(k):
                    self.tv_c.selection_add(k)
            if len(rows) == 1:
                self.tv_c.selection_set(str(rows[0]["addr"]))
        self.win.bg(lambda: sc.results(0, MAX_ROWS), ok, lambda e: self.log(f"{type(e).__name__}: {e}", "err"), lock=False)

    # ------------------------------------------------------------------ Schritt 3
    def _chosen(self):
        sel = self.tv_c.selection()
        if not sel:
            self.log("Erst oben einen Treffer markieren", "warn")
            return None
        return self.cands.get(sel[0])

    def start_watch(self):
        if self.watching:
            return
        pick = self._chosen()
        if not pick:
            return
        addr, vname = pick
        dbg = getattr(self.win, "dbg_tab", None)
        if dbg is None:
            return self.log("Debugger-Tab nicht verfügbar", "err")
        size = A.watch_size(vname)
        if addr % size:
            return self.log(f"Adresse {addr:#x} muss auf {size} Byte ausgerichtet sein (Hardware-Watchpoint)", "err")
        if dbg.sess and dbg.sess.attached:
            return self._arm(dbg, addr, size)
        dbg.attach()
        self.lbl_watch.configure(text="Debugger wird verbunden ...", fg=WARN)
        self._wait_attached(dbg, addr, size, 50)

    def _wait_attached(self, dbg, addr, size, tries):
        if not self.winfo_exists():
            return
        if dbg.sess and dbg.sess.attached:
            return self._arm(dbg, addr, size)
        if tries <= 0:
            self.lbl_watch.configure(text="Aus.", fg=TEXT_DIM)
            return self.log("Der Debugger wurde nicht verbunden - im Tab DEBUGGER ATTACH versuchen", "warn")
        self.after(500, lambda: self._wait_attached(dbg, addr, size, tries - 1))

    def _arm(self, dbg, addr, size):
        sess = dbg.sess
        try:
            idx = sess.free_wp_index()
        except Exception as e:  # noqa: BLE001
            return self.log(str(e), "err")

        def ok(_r):
            self.watch_idx, self.watch_addr, self.watching = idx, addr, True
            self.seen = set(dbg.hit_items)
            try:
                dbg._fill_wps()
            except Exception:  # noqa: BLE001
                pass
            self.lbl_watch.configure(text=f"AKTIV  beobachtet {addr:#x}  - jetzt im Spiel den Wert ändern", fg=ACCENT)
            self.log(f"Beobachte Schreibzugriffe auf {addr:#x}", "ok")
            self.after(POLL_MS, lambda: self._poll_hits(dbg, addr, size))
        self.win.bg(lambda: sess.set_watchpoint(idx, addr, size, X.WP_WRITE), ok)

    def _poll_hits(self, dbg, addr, size):
        if not self.watching or not self.winfo_exists():
            return
        new = [i for i in list(dbg.hit_items) if i not in self.seen]
        self.seen.update(new)
        for iid in new:
            hit = dbg.hit_items.get(iid)
            if hit and hit.get("kind") == "WP" and hit.get("addr") == addr:
                self._handle_hit(dbg, hit, addr, size)
        self.after(POLL_MS, lambda: self._poll_hits(dbg, addr, size))

    def _handle_hit(self, dbg, hit, addr, size):
        regs = hit["regs"]
        rip = regs["rip"]
        sess, client = dbg.sess, self.win.client

        def job():
            writer = None
            try:
                before = client.read_memory(rip - 16, 16)
                writer = A.find_writer(rip, before, regs, addr, size, AT.disassemble_lines)
            finally:
                try:
                    sess.resume()                     # das Spiel soll nicht stehen bleiben
                except Exception as e:  # noqa: BLE001
                    self.win.ui(lambda e=e: self.log(f"Weiter: {e}", "warn"))
            return writer

        def ok(writer):
            self.writers.add(writer)
            self._fill_writers()
            if writer is None:
                self.log(f"Treffer bei RIP {rip:#x}, aber der schreibende Befehl ließ sich nicht bestimmen", "warn")
        self.win.bg(job, ok, lambda e: self.log(f"{type(e).__name__}: {e}", "err"))

    def stop_watch(self):
        if not self.watching:
            return
        self.watching = False
        idx = self.watch_idx
        dbg = getattr(self.win, "dbg_tab", None)
        sess = dbg.sess if dbg else None
        self.lbl_watch.configure(text="Aus.", fg=TEXT_DIM)
        if sess and idx is not None:
            def done(_r):
                try:
                    dbg._fill_wps()
                except Exception:  # noqa: BLE001
                    pass
                self.log("Beobachtung beendet", "ok")
            self.win.bg(lambda: sess.clear_watchpoint(idx), done)

    def _fill_writers(self):
        self.tv_w.delete(*self.tv_w.get_children())
        for r in self.writers.rows(self._lang()):
            self.tv_w.insert("", "end", iid=str(r["addr"]), values=(f"{r['addr']:#x}", r["insn"], r["text"], r["count"]))
        kids = self.tv_w.get_children()
        if len(kids) == 1:
            self.tv_w.selection_set(kids[0])

    # ------------------------------------------------------------------ Schritt 4
    def _writer(self):
        sel = self.tv_w.selection()
        if not sel:
            self.log("Erst in Schritt 3 einen Befehl markieren", "warn")
            return None
        return int(sel[0]), self.tv_w.item(sel[0], "values")[1]

    def to_preset(self):
        w = self._writer()
        if not w:
            return
        self.stop_watch()
        tab = getattr(self.win, "t_dis", None)
        if tab is None:
            return self.log("Der Disassembler ist nicht verfügbar", "err")
        tab.recipe_at(w[0], w[1])

    def to_disasm(self):
        w = self._writer()
        if w:
            self.win.goto_disasm(w[0])

    def shutdown(self):
        self.watching = False
