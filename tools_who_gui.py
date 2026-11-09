"""tools_who_gui.py - Tab SPIELER / GEGNER: herausfinden, woran man den Spieler erkennt (Logik: whois.py).

Wenn Spieler und Gegner denselben Code zum Veraendern des Lebens benutzen, wuerde ein Cheat dort ALLE unsterblich
machen.  Der Tab zeichnet auf, was bei Treffern des Spielers und bei Treffern von Gegnern anders ist, und baut danach
einen Cheat, der nur fuer den Spieler (oder nur fuer Gegner) gilt.
"""
import time
import tkinter as tk
from tkinter import messagebox, ttk

import aob as AOB
import asm_recipes as AR
import tools_i18n
import whois as W
from tools_common import ACCENT, BG, BG_CARD, FONT_LABEL, TEXT_DIM, BaseTab, button, entry, label, tree, with_scroll

RECIPE_IDS = ("disable", "set_value")


def _chk(parent, text, var):
    return tk.Checkbutton(parent, text=text, variable=var, bg=BG, fg=TEXT_DIM, selectcolor=BG_CARD,
                          activebackground=BG, activeforeground=ACCENT, font=FONT_LABEL)


class WhoTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.sess = None
        self.running = False
        self.phase = None                    # None | "a" | "b"
        self.rows = {"a": [], "b": []}
        self.found = []
        self.hook_addr = None

        label(self, "Wenn Spieler und Gegner denselben Code fuer das Leben benutzen, macht ein normaler Cheat ALLE unsterblich. "
                    "Hier findest du heraus, woran man den Spieler erkennt.").pack(anchor="w", padx=10, pady=(8, 0))
        label(self, "1. Adresse des Befehls eintragen, der das Leben aendert (zum Beispiel aus 'Wer schreibt hier?' im Debugger).  "
                    "2. AUFZEICHNEN starten.  3. Phase A: nur du wirst getroffen.  4. Phase B: nur Gegner werden getroffen.  "
                    "5. AUSWERTEN.").pack(anchor="w", padx=10)

        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 2))
        label(top, "BEFEHL @").pack(side="left")
        self.v_addr = tk.StringVar(value="base+")
        entry(top, self.v_addr, 24).pack(side="left", padx=6)
        self.b_start = button(top, "AUFZEICHNEN STARTEN", self.start, accent=True)
        self.b_start.pack(side="left", padx=2)
        self.b_stop = button(top, "STOPP", self.stop)
        self.b_stop.pack(side="left", padx=2)
        button(top, "LEEREN", self.clear).pack(side="left", padx=2)
        self.lbl = label(self, "Aus.")
        self.lbl.pack(anchor="w", padx=10)

        ph = tk.Frame(self, bg=BG); ph.pack(fill="x", padx=8, pady=4)
        self.b_a = button(ph, "PHASE A: NUR ICH WERDE GETROFFEN", lambda: self.set_phase("a"))
        self.b_a.pack(side="left", padx=2)
        self.b_b = button(ph, "PHASE B: NUR GEGNER WERDEN GETROFFEN", lambda: self.set_phase("b"))
        self.b_b.pack(side="left", padx=2)
        button(ph, "PAUSE", lambda: self.set_phase(None)).pack(side="left", padx=2)
        self.lbl_cnt = label(ph, "A: 0   B: 0")
        self.lbl_cnt.pack(side="left", padx=12)
        button(ph, "AUSWERTEN", self.evaluate, accent=True).pack(side="right")

        label(self, "GEFUNDENE MERKMALE (das oberste ist das sicherste)").pack(anchor="w", padx=10, pady=(6, 0))
        fr = tk.Frame(self, bg=BG); fr.pack(fill="both", expand=True, padx=8)
        self.tv = tree(fr, [("k", "ART"), ("st", "NACH NEUSTART GLEICH"), ("c", "SICHERHEIT"), ("d", "BESCHREIBUNG")],
                       [90, 150, 90, 640], height=9)
        with_scroll(fr, self.tv)

        bot = tk.Frame(self, bg=BG); bot.pack(fill="x", padx=8, pady=8)
        label(bot, "CHEAT").pack(side="left")
        self.v_rec = tk.StringVar()
        self.cb_rec = ttk.Combobox(bot, textvariable=self.v_rec, width=44, state="readonly",
                                   values=[AR.title(r, "de") for r in ("disable", "set_value")])
        self.cb_rec.current(0)
        self.cb_rec.pack(side="left", padx=6)
        label(bot, "WERT").pack(side="left")
        self.v_val = tk.StringVar(value="999")
        entry(bot, self.v_val, 8).pack(side="left", padx=6)
        label(bot, "GILT FUER").pack(side="left")
        self.v_for = tk.StringVar(value="nur den Spieler")
        ttk.Combobox(bot, textvariable=self.v_for, values=("nur den Spieler", "nur Gegner"), width=16,
                     state="readonly").pack(side="left", padx=6)
        button(bot, "→ CHEAT-EDITOR", self.to_cheat, accent=True).pack(side="right")

    # ---- von aussen (Disassembler) ----
    def fill(self, addr):
        self.v_addr.set(f"{addr:#x}")

    # ---- Aufzeichnen ----
    def start(self):
        if self.running:
            return
        try:
            a = self.addr(self.v_addr.get())
        except Exception as e:
            return self.log(str(e), "err")
        if not messagebox.askyesno("Aufzeichnen", f"Befehl bei {a:#x} patchen (Sprung in eine Code-Cave)?\n"
                                                  "STOPP stellt ihn wieder her.", parent=self.win):
            return
        sess = W.ProbeSession(self.win.app.backend, a)

        def ok(info):
            self.sess, self.running, self.hook_addr = sess, True, a
            self.lbl.configure(text=f"AKTIV  Hook {a:#x}  Cave {info['cave']:#x} ({info['cave_size']} B)", fg=ACCENT)
            self.log(f"Aufzeichnung aktiv @ {a:#x}", "ok")
            self.after(300, self._tick)
        self.bg(sess.start, ok)

    def stop(self):
        if not self.sess or not self.running:
            return
        sess, self.running = self.sess, False
        self.phase = None
        self.bg(sess.stop, lambda _r: (self.lbl.configure(text="Aus - Original-Bytes zurueckgeschrieben.", fg=TEXT_DIM),
                                       self.log("Aufzeichnung gestoppt", "ok")))

    def shutdown(self):
        if self.sess and self.running:
            self.running = False
            try:
                self.sess.stop()
            except Exception:  # noqa: BLE001
                pass

    def clear(self):
        self.rows = {"a": [], "b": []}
        self.found = []
        self.tv.delete(*self.tv.get_children())
        self._count()

    def set_phase(self, p):
        if p and not self.running:
            return self.log("Erst AUFZEICHNEN STARTEN", "warn")
        self.phase = p
        names = {"a": "Phase A laeuft: lass dich von Gegnern treffen, greife selbst nicht an.",
                 "b": "Phase B laeuft: greife Gegner an, lass dich nicht treffen.", None: "Pause."}
        self.lbl.configure(text=("AKTIV  " if self.running else "") + names[p], fg=ACCENT if p else TEXT_DIM)

    def _count(self):
        self.lbl_cnt.configure(text=f"A: {len(self.rows['a'])}   B: {len(self.rows['b'])}")

    def _tick(self):
        if not self.running or not self.winfo_exists():
            return
        sess = self.sess

        def ok(recs):
            if recs and self.phase:
                self.rows[self.phase] += recs
                self.rows[self.phase] = self.rows[self.phase][-2000:]
                self._count()
            if sess.lost:
                self.log(f"{sess.lost} Treffer verloren (zu schnell)", "warn")
                sess.lost = 0
            self.after(300, self._tick)
        self.bg(sess.poll, ok, lambda e: (self.log(f"Aufzeichnung: {e}", "err"), self.after(1000, self._tick)))

    # ---- Auswerten ----
    def evaluate(self):
        a, b = list(self.rows["a"]), list(self.rows["b"])
        if len(a) < 2 or len(b) < 2:
            return self.log("Zu wenig Treffer: in jeder Phase mindestens 3 Mal treffen lassen", "warn")
        cl = self.win.client

        def job():
            regs = AOB.exec_regions(cl.get_maps(), 0x1000)
            return W.analyze(a, b, read=cl.read_memory, is_code=lambda v: any(s <= v < e for s, e in regs),
                             recheck=lambda: time.sleep(0.6))

        def ok(found):
            self.found = found
            self.tv.delete(*self.tv.get_children())
            lang = tools_i18n.lang()
            kinds = {"caller": "AUFRUFER", "field": "FELD", "object": "OBJEKT"}
            for i, c in enumerate(found):
                self.tv.insert("", "end", iid=str(i), values=(
                    kinds[c["kind"]], "ja" if c["stable"] else "nein",
                    "hoch" if c["confidence"] == "high" else "niedrig", W.describe(c, self.base, lang)))
            if found:
                self.tv.selection_set("0")
                self.log(f"{len(found)} Merkmal(e) gefunden - das oberste ist das sicherste", "ok")
            else:
                self.log("Kein Unterschied gefunden. Phasen sauber trennen (in A nur du, in B nur Gegner) und "
                         "mehr Treffer aufzeichnen.", "warn")
        self.bg(job, ok)

    # ---- Cheat bauen ----
    def to_cheat(self):
        sel = self.tv.selection()
        if not sel or self.hook_addr is None:
            return self.log("Erst AUSWERTEN und ein Merkmal markieren", "warn")
        c = self.found[int(sel[0])]
        rid = RECIPE_IDS[self.cb_rec.current()] if self.cb_rec.current() >= 0 else "disable"
        value = self.v_val.get()
        side = "player" if self.v_for.get() == "nur den Spieler" else "enemy"
        a = self.hook_addr

        def job():
            data = self.win.client.read_memory(a, 96)
            plan = AR.make_plan(rid, data, a, value, guarded=True)
            cave = W.guard_cave(c, a, plan["cheat"], plan["body"], apply_to=side)
            return {"addr": a, "size": plan["size"], "default": plan["default"], "cave": cave,
                    "new": "jmp OriginTarget", "warnings": plan["warnings"]}

        def ok(r):
            self.win.to_cave_hook(r)
            for w in r["warnings"]:
                self.log(f"Hook: {w}", "warn")
            if not c["stable"]:
                self.log("Achtung: Dieses Merkmal gilt nur bis zum Beenden des Spiels - nach jedem Start neu ermitteln.",
                         "warn")
        self.bg(job, ok)
