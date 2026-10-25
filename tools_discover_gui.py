"""tools_discover_gui.py - Tab "UE-ENTDECKER": fuer JEDES Unreal-Spiel die gaengigen Bausteine vorschlagen.

  1) Im Tab UE-LIVE den SPIEL-ORDNER laden (und fuer die Live-Funktionen verbinden)
  2) ANALYSIEREN: Items (ID + Menge), Tabellen, Slot-/ID-Enums, Geben-Funktionen, Cheat-Manager, Waehrung, Stats
  3) Vorschlag anklicken -> Begruendung + wie man ihn benutzt
  4) Tabelle anklicken -> TABELLE LIVE LESEN: Zeilen mit Namen, FName-Bytes und Spalten (Preis, Stack, IDs ...)
  5) Exportieren (CSV/JSON) oder den Bericht speichern

Alles ist ein Vorschlag mit Begruendung, kein Beweis.  Logik: ue_profile.py (testbar ohne Oberflaeche und Konsole).
"""
import os
import re
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import cave_trainer as TR
import ue_cavegen as CG
import ue_profile as P
from tools_common import BG, TEXT_DIM, BaseTab, button, entry, label, tree, with_scroll

def _find_impl(read, base, thunk):
    """Native Implementierung hinter dem Exec-Thunk (Disassembler noetig)."""
    return CG.find_impl(read, base, thunk)


KINDS = [("alle", None)] + [(v, k) for k, v in P.KIND_LABEL.items()]
MAX_ROWS_SHOWN = 4000
MAX_RANGE = 0x4000_0000


class DiscoverTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.prof = None
        self.view = []              # aktuell angezeigte Vorschlaege (iid = Index)
        self.tables = None          # [(addr, name)] aus dem laufenden Spiel
        self.cur = None             # (Tabellenname, rows, cols) der zuletzt gelesenen Tabelle
        self.rows_mode = "rows"     # untere Liste zeigt "rows" (Tabellenzeilen) oder "tables" (Tabellen zur Auswahl)
        self.tab_list = []          # [(addr, name)] passend zur Tabellen-Anzeige
        self.v_info = tk.StringVar(value="Erst im Tab UE-LIVE den Spiel-Ordner laden, dann ANALYSIEREN.")
        self.v_kind = tk.StringVar(value="alle")
        self.v_q = tk.StringVar()
        self.v_table = tk.StringVar()
        self.v_idnum = tk.StringVar()
        self.v_cnt = tk.StringVar()
        self.hits = []
        self._busy = False
        self.v_amount = tk.StringVar(value="999")
        self.v_this = tk.StringVar(value="auto")
        self.v_byref = tk.BooleanVar(value=False)
        self.v_extra = tk.StringVar()
        self.v_rowq = tk.StringVar()
        self._support = {}          # id(Vorschlag) -> None (geht) | Grund (geht nicht), damit nichts erst am Ende scheitert

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 2))
        button(top, "🔎  ANALYSIEREN", self.analyze, accent=True).pack(side="left", padx=2)
        button(top, "NEU ANALYSIEREN", self.reanalyze).pack(side="left", padx=2)
        label(top, "  Art").pack(side="left")
        cb = ttk.Combobox(top, textvariable=self.v_kind, values=[k for k, _ in KINDS], state="readonly", width=16)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.fill())
        label(top, "Suche").pack(side="left", padx=(8, 0))
        q = entry(top, self.v_q, 22)
        q.pack(side="left", padx=4)
        q.bind("<KeyRelease>", lambda _e: self.fill())
        button(top, "BERICHT SPEICHERN…", self.save_report).pack(side="left", padx=8)
        button(top, "IN UE-LIVE ÖFFNEN", self.open_in_live).pack(side="left", padx=2)
        tk.Label(self, textvariable=self.v_info, bg=BG, fg=TEXT_DIM, anchor="w").pack(fill="x", padx=10)

        mid = tk.PanedWindow(self, orient="vertical", bg=BG, sashwidth=4)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        up = tk.Frame(mid, bg=BG)
        mid.add(up, stretch="always")
        cols = [("kind", "Art"), ("title", "Vorschlag"), ("score", "Wert"), ("detail", "Details")]
        self.tv = tree(up, cols, [120, 280, 50, 520], height=11, anchors={"score": "e"})
        with_scroll(up, self.tv)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.tv.bind("<Double-1>", lambda _e: self.on_double())
        self.txt = tk.Text(mid, height=7, wrap="word", bg="#101010", fg="#d0d0d0", relief="flat")
        mid.add(self.txt, stretch="never")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=8, pady=(2, 0))
        button(bar, "📋  TABELLE LIVE LESEN", self.read_table, accent=True).pack(side="left", padx=2)
        label(bar, "  Tabelle (wird per Doppelklick eingetragen)").pack(side="left")
        entry(bar, self.v_table, 20).pack(side="left", padx=4)
        button(bar, "TABELLEN IM SPIEL LISTEN", self.list_tables).pack(side="left", padx=2)
        button(bar, "TABELLE EXPORTIEREN…", self.export_table).pack(side="left", padx=8)
        label(bar, "  Item-Name suchen").pack(side="left")
        rq = entry(bar, self.v_rowq, 16)
        rq.pack(side="left", padx=4)
        rq.bind("<KeyRelease>", lambda _e: self._fill_rows())
        low = tk.Frame(self, bg=BG)
        low.pack(fill="both", expand=True, padx=8, pady=4)
        self.tv_rows = tree(low, [("name", "Zeile (Name = ID)"), ("fname", "FName (hex)"), ("vals", "Spalten")],
                            [240, 150, 620], height=9)
        with_scroll(low, self.tv_rows)
        self.tv_rows.bind("<Double-1>", lambda _e: self.on_rows_double())
        self.tv_rows.bind("<<TreeviewSelect>>", lambda _e: self._auto_id())

        bar2 = tk.Frame(self, bg=BG)
        bar2.pack(fill="x", padx=8, pady=(2, 0))
        button(bar2, "🔍  INVENTAR-EINTRÄGE SUCHEN", self.find_entries, accent=True).pack(side="left", padx=2)
        label(bar2, "  ID-Zahl (nur bei Zahlen-IDs)").pack(side="left")
        entry(bar2, self.v_idnum, 10).pack(side="left", padx=4)
        label(bar2, "Menge im Spiel (optional)").pack(side="left")
        entry(bar2, self.v_cnt, 10).pack(side="left", padx=4)
        button(bar2, "MENGE SETZEN…", self.set_entry_count).pack(side="left", padx=8)
        bar3 = tk.Frame(self, bg=BG)
        bar3.pack(fill="x", padx=8, pady=(6, 0))
        button(bar3, "🧰  CAVE-TRAINER EXPORTIEREN…", self.export_cave_trainer, accent=True).pack(side="left", padx=2)
        label(bar3, "  Menge").pack(side="left")
        entry(bar3, self.v_amount, 9).pack(side="left", padx=4)
        label(bar3, "this").pack(side="left")
        ttk.Combobox(bar3, textvariable=self.v_this, values=["auto", "zero", "hooked", "member"], state="readonly",
                     width=8).pack(side="left", padx=4)
        tk.Checkbutton(bar3, text="FName per Zeiger (const FName&)", variable=self.v_byref, bg=BG, fg=TEXT_DIM,
                       selectcolor=BG, activebackground=BG).pack(side="left", padx=4)
        label(bar3, "Weitere Parameter").pack(side="left")
        entry(bar3, self.v_extra, 22).pack(side="left", padx=4)
        label(self, "   Geben-Funktion anklicken (+ bei FName-ID Zeilen in der Tabelle waehlen) -> ReaperPy-Projekt mit fester Cave "
                    "fuer JEDES Spiel.  Format 'Name=Wert, Name=Wert'.").pack(anchor="w")
        low2 = tk.Frame(self, bg=BG)
        low2.pack(fill="x", padx=8, pady=4)
        self.tv_hits = tree(low2, [("addr", "Eintrag"), ("name", "Item"), ("cnt", "Menge"), ("caddr", "Mengen-Adresse")],
                            [150, 220, 100, 180], height=4)
        with_scroll(low2, self.tv_hits)
        self.tv_hits.bind("<Double-1>", lambda _e: self._goto_hit())

    # -- Zugriff auf UE-LIVE ------------------------------------------------------------------
    def _uelive(self):
        for t in getattr(self.win, "extra_tabs", []):
            if t.__class__.__name__ == "UeLiveTab":
                return t
        return None

    def _sdk(self):
        return getattr(getattr(self._uelive(), "proj", None), "sdk", None)

    def _live(self):
        live = getattr(self._uelive(), "live", None)
        if live is None:
            raise ValueError("Kein Live-Zugriff - im Tab UE-LIVE zuerst das Spiel laden und verbinden")
        if live.index is None:
            live.build_index()
        return live

    # -- Analyse ------------------------------------------------------------------------------
    def _gp(self):
        return getattr(getattr(self.win, "app", None), "gp", None)

    def analyze(self, force=False):
        sdk = self._sdk()
        if sdk is None:
            self.log("Kein SDK geladen - im Tab UE-LIVE den SPIEL-ORDNER waehlen", "err")
            return
        gp = self._gp()
        sig = P.signature(sdk)
        if gp is not None and not force and gp.discover and gp.discover.get("sig") == sig:
            try:
                prof = P.from_json(gp.discover["json"])
            except ValueError:
                prof = None
            if prof is not None:
                self._analyzed(prof, cached=True)
                return
        self.v_info.set("Analysiere SDK …")

        def done(prof):
            if gp is not None:                                  # fuer das naechste Mal merken
                gp.discover = {"sig": sig, "json": P.to_json(prof)}
                gp.save()
            self._analyzed(prof)
        self.bg(lambda: P.build(sdk), done, lambda e: self.log(f"Analyse fehlgeschlagen: {e}", "err"))

    def reanalyze(self):
        self.analyze(force=True)

    def _analyzed(self, prof, cached=False):
        self.prof = prof
        c = prof.counts
        self.v_info.set(f"{len(prof.suggestions)} Vorschlaege · {c.get('item_struct', 0)} Item-Structs · "
                        f"{c.get('table', 0)} Tabellen · {c.get('give_function', 0)} Geben-Funktionen · "
                        f"{c.get('cheat_manager', 0)} Cheat-Manager · {c.get('stat_enum', 0)} Stat-Enums")
        self.fill()
        self.log("UE-Entdecker: " + self.v_info.get() + ("  (aus dem Zwischenspeicher)" if cached else ""), "ok")
        self._next_step()
        for n in prof.notes:
            self.log("   " + n, "info")

    def _unsupported(self, s):
        """None = der Cave-Trainer kann diese Geben-Funktion bauen, sonst der Grund in einfachen Worten."""
        if s.kind != "give_function":
            return None
        key = id(s)
        if key not in self._support:
            try:
                CG.classify_params(s.data["params"], self._sdk())
                CG.check_return(s.data.get("ret"))
                self._support[key] = None
            except (TR.TrainerError, KeyError, TypeError) as e:
                self._support[key] = str(e)
        return self._support[key]

    def fill(self):
        self.tv.delete(*self.tv.get_children())
        self.view = []
        if self.prof is None:
            return
        kind = dict(KINDS).get(self.v_kind.get())
        q = self.v_q.get().strip().lower()
        sugg = [x for x in self.prof.suggestions if not (kind and x.kind != kind)]
        # Geben-Funktionen, die der Trainer bauen kann, vor denen, die er nicht kann (Reihenfolge sonst unveraendert)
        sugg.sort(key=lambda x: 1 if (x.kind == "give_function" and self._unsupported(x)) else 0)
        for s in sugg:
            if q and q not in (s.title + " " + s.detail + " " + " ".join(s.evidence)).lower():
                continue
            why = self._unsupported(s)
            title = ("✗ " if why else ("✔ " if s.kind == "give_function" else "")) + s.title
            detail = s.detail if not why else "GEHT NICHT: " + why
            self.tv.insert("", "end", iid=str(len(self.view)),
                           values=(P.KIND_LABEL.get(s.kind, s.kind), title, s.score, detail))
            self.view.append(s)

    def _next_step(self):
        """Sagt in einem Satz, was als Naechstes zu tun ist - passend zu dem, was die Analyse gefunden hat."""
        if self.prof is None:
            return
        ok = [x for x in self.prof.suggestions if x.kind == "give_function" and not self._unsupported(x)]
        tabs = [x for x in self.prof.suggestions if x.kind == "table"]
        if ok and tabs:
            msg = ("Naechster Schritt: unten TABELLE LIVE LESEN, einen Item-NAMEN in der Liste anklicken, dann eine Zeile mit ✔ "
                   "(Geben-Funktion) oben anklicken und CAVE-TRAINER EXPORTIEREN. IDs musst du nicht kennen.")
        elif ok:
            msg = "Naechster Schritt: eine Zeile mit ✔ (Geben-Funktion) oben anklicken und CAVE-TRAINER EXPORTIEREN."
        elif tabs:
            msg = ("Keine Geben-Funktion ist baubar - Weg ueber den Speicher: Tabelle lesen, Item-Namen waehlen, "
                   "dann INVENTAR-EINTRAEGE SUCHEN und die Menge direkt setzen.")
        else:
            msg = "Nichts Passendes gefunden - Bericht speichern oder in UE-LIVE von Hand suchen."
        self.v_info.set(self.v_info.get() + "   |   " + msg)

    def _selected(self):
        sel = self.tv.selection()
        if not sel:
            return None
        try:
            return self.view[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def on_select(self):
        s = self._selected()
        self.txt.delete("1.0", "end")
        if s is None:
            return
        if s.kind == "table":
            self.v_table.set(s.data.get("table_name") or "")        # Name direkt eintragen (leer = automatisch passende Tabelle)
        lines = [f"{P.KIND_LABEL.get(s.kind, s.kind)}: {s.title}   (Wert {s.score}/10)", s.detail, ""]
        lines += [f"  • {e}" for e in s.evidence]
        why = self._unsupported(s)
        if why:
            lines += ["", "✗ Dafuer laesst sich KEIN Cave-Trainer bauen: " + why,
                      "  Tipp: eine Zeile mit ✔ nehmen, oder den Weg ueber INVENTAR-EINTRAEGE SUCHEN (Menge direkt im Speicher setzen)."]
        if s.howto:
            lines += ["", "So benutzt du es: " + s.howto]
        self.txt.insert("1.0", "\n".join(lines))

    def on_double(self):
        """Doppelklick auf einen Vorschlag: Tabelle -> sofort live lesen; Member-Vorschlaege -> in UE-LIVE oeffnen."""
        s = self._selected()
        if s is None:
            return
        if s.kind == "table":
            self.read_table()
        elif s.kind in ("currency", "stat_array", "attribute_set"):
            self.open_in_live()

    def on_rows_double(self):
        """Doppelklick in der unteren Liste: in der Tabellen-Auswahl -> diese Tabelle lesen."""
        if self.rows_mode != "tables":
            return
        sel = self.tv_rows.selection()
        try:
            addr, name = self.tab_list[int(sel[0])]
        except (IndexError, ValueError):
            return
        self.v_table.set(name)
        self.read_table()

    def _show_tables(self, tabs):
        self.rows_mode, self.tab_list = "tables", list(tabs)
        self.tv_rows.delete(*self.tv_rows.get_children())
        for i, (_a, n) in enumerate(self.tab_list):
            self.tv_rows.insert("", "end", iid=str(i), values=(n, "", "Doppelklick = diese Tabelle lesen"))

    def _selected_rows(self):
        """Angeklickte Tabellenzeilen (nur wenn unten Zeilen angezeigt werden)."""
        if self.rows_mode != "rows" or not self.cur:
            return []
        out = []
        for i in self.tv_rows.selection():
            try:
                out.append(self.cur[1][int(i)])
            except (ValueError, IndexError):
                pass
        return out

    # -- Tabellen live -------------------------------------------------------------------------
    def list_tables(self):
        def job():
            live = self._live()
            self.tables = P.find_table_objects(live)
            return self.tables

        def ok(tabs):
            if not tabs:
                self.log("Keine DataTable-Objekte im Spiel gefunden (Spielstand geladen?)", "err")
                return
            self._show_tables(tabs)
            self.log(f"{len(tabs)} DataTables im Spiel - unten per Doppelklick lesen", "ok")

        self.bg(job, ok, lambda e: self.log(str(e), "err"))

    def read_table(self):
        s = self._selected()
        typed = self.v_table.get().strip().lower()
        if s is None and not typed:
            self.log("Erst einen Tabellen-Vorschlag anklicken oder einen Tabellen-Namen eintippen", "err")
            return
        if s is not None and s.kind != "table" and not typed:
            self.log("Das ist keine Tabelle - eine Zeile der Art 'Tabelle' anklicken (oder Namen eintippen)", "err")
            return

        def job():
            live = self._live()
            if self.tables is None:
                self.tables = P.find_table_objects(live)
            tabs = self.tables
            pick = None
            if typed:
                pick = next(((a, n) for a, n in tabs if typed in n.lower()), None)
            elif s is not None:
                pick = P.best_table_for(s, tabs)
            if pick is None:
                if not tabs:
                    raise ValueError("Keine DataTable-Objekte im Spiel gefunden (Spielstand geladen?)")
                return "choose", tabs
            cols = s.data.get("columns", []) if s is not None and not typed else []
            if typed and s is not None and s.kind == "table":
                cols = s.data.get("columns", [])
            rows, cols = P.read_table(live.rd, live.fname_str, pick[0], cols)
            return pick[1], rows, cols

        def ok(res):
            if res[0] == "choose":
                self._show_tables(res[1])
                self.log("Keine eindeutig passende Tabelle gefunden - unten die Tabellen des Spiels: "
                         "die richtige per Doppelklick lesen", "info")
                return
            name, rows, cols = res
            self.cur = res
            self.rows_mode = "rows"
            self.v_rowq.set("")
            self._fill_rows()
            if not rows:
                self.log(f"Tabelle {name}: keine Zeilen gelesen (RowMap nicht erkannt?)", "err")
            else:
                self.log(f"Tabelle {name}: {len(rows)} Zeilen, {len(cols)} Spalten gelesen"
                         + (f" (Anzeige {MAX_ROWS_SHOWN})" if len(rows) > MAX_ROWS_SHOWN else ""), "ok")

        self.bg(job, ok, lambda e: self.log(str(e), "err"))

    def _fill_rows(self):
        """Tabellenzeilen anzeigen, gefiltert nach dem Item-Namen (iid bleibt der Index in der vollen Liste)."""
        if self.rows_mode != "rows" or not self.cur:
            return
        q = self.v_rowq.get().strip().lower()
        self.tv_rows.delete(*self.tv_rows.get_children())
        shown = 0
        for i, r in enumerate(self.cur[1]):
            if q and q not in r["name"].lower():
                continue
            if shown >= MAX_ROWS_SHOWN:
                break
            vals = "; ".join(f"{k}={v}" for k, v in r["values"].items())
            self.tv_rows.insert("", "end", iid=str(i), values=(r["name"], r["fname_hex"], vals))
            shown += 1

    def _auto_id(self):
        """Eine Zeile angeklickt: gibt es in der Tabelle eine ID-Spalte mit Zahl, wird sie als ID-Zahl uebernommen."""
        rows = self._selected_rows()
        if len(rows) != 1:
            return
        for k, v in rows[0]["values"].items():
            if P.ID_NAME.search(str(k)) and isinstance(v, int) and not isinstance(v, bool):
                self.v_idnum.set(str(v))
                self.log(f"ID-Zahl aus Spalte {k} uebernommen: {v}", "info")
                return

    def export_table(self):
        if not self.cur or not self.cur[1]:
            self.log("Erst eine Tabelle lesen (TABELLE LIVE LESEN)", "err")
            return
        name, rows, cols = self.cur
        path = filedialog.asksaveasfilename(title="Tabelle speichern", defaultextension=".csv", initialfile=f"{name}.csv",
                                            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")])
        if not path:
            return
        text = P.table_to_json(rows, cols, name) if path.lower().endswith(".json") else P.table_to_csv(rows, cols)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.log(f"Tabelle gespeichert: {path} ({len(rows)} Zeilen, inkl. FName-Bytes)", "ok")

    # -- Inventar-Eintraege suchen / Menge setzen -------------------------------------------------
    def _ranges(self):
        maps = self.win.client.get_maps()
        return sorted((m[0], m[1]) for m in maps if (m[2] & 3) == 3 and 0x1000 <= m[1] - m[0] <= MAX_RANGE)

    def find_entries(self):
        s = self._selected()
        if s is None or s.kind != "item_struct" or not s.data.get("id") or not s.data.get("count"):
            self.log("Erst einen Vorschlag der Art 'Item-Struct' mit ID + Menge anklicken", "err")
            return
        d = s.data
        idinfo, cnt = d["id"], d["count"]
        try:
            ctype = P.base_name(cnt["type"])
            if ctype not in P.INT_FMT:
                raise ValueError(f"Die Menge ist vom Typ {cnt['type']} - so einen Wert kann ich im Speicher nicht suchen/setzen. "
                                 "Anderen Item-Struct-Vorschlag waehlen oder die Menge in UE-LIVE von Hand aendern")
            pats = {}
            if idinfo["id_kind"] == "fname":
                sel = self._selected_rows()
                if not sel:
                    raise ValueError("Erst Items in der Tabelle waehlen (Tabelle doppelklicken, dann Zeile(n) anklicken) - "
                                     "deren FName wird gesucht")
                for r in sel[:50]:
                    pats[bytes.fromhex(r["fname_hex"])] = r["name"]
            else:
                txt = self.v_idnum.get().strip()
                if not txt:
                    raise ValueError("Keine ID-Zahl: erst unten TABELLE LIVE LESEN und das Item anklicken (die ID wird uebernommen) "
                                     "- oder die Zahl ins Feld eintippen")
                num = int(txt, 0)
                pats[P.id_pattern("int", number=num, size=max(1, min(8, idinfo["size"])))] = f"ID {num}"
            cv = self.v_cnt.get().strip()
            value = (float(cv) if ctype in ("float", "double") else int(cv, 0)) if cv else None
        except ValueError as e:
            self.log(str(e), "err")
            return
        client = self.win.client
        ranges = self._ranges()
        self.v_info.set("Suche Eintraege im Speicher …")

        def job():
            return P.find_instances(client.read_memory, ranges, idinfo["offset"], pats, cnt["offset"], ctype, value)

        def ok(hits):
            self.hits = hits
            self.tv_hits.delete(*self.tv_hits.get_children())
            for i, h in enumerate(hits):
                self.tv_hits.insert("", "end", iid=str(i), values=(f"{h.base:#x}", h.name, h.count, f"{h.count_addr:#x}"))
            self.v_info.set(f"{len(hits)} Eintraege gefunden")
            self.log(f"{len(hits)} Inventar-Eintraege von {s.title} gefunden"
                     + ("" if value is not None else " (ohne Mengen-Angabe: nur plausible Mengen - ggf. 'Menge im Spiel' eintragen)"),
                     "ok" if hits else "err")

        self.bg(job, ok, lambda e: self.log(str(e), "err"))

    def _hit(self):
        sel = self.tv_hits.selection()
        if not sel:
            return None
        try:
            return self.hits[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _goto_hit(self):
        h = self._hit()
        if h is not None:
            self.win.goto_memory(h.count_addr)

    def set_entry_count(self):
        h = self._hit()
        if h is None:
            self.log("Erst einen gefundenen Eintrag anklicken", "err")
            return
        val = simpledialog.askstring("Menge setzen", f"Neue Menge fuer {h.name} (jetzt {h.count}):", parent=self.win)
        if not val:
            return
        try:
            data = P.set_count(self.win.client.write_memory, h, float(val) if h.count_type in ("float", "double") else int(val, 0))
        except (ValueError, struct.error) as e:
            self.log(f"Ungueltige Menge: {e}", "err")
            return
        self.log(f"{h.name}: Menge @ {h.count_addr:#x} = {data.hex()} geschrieben (im Spiel Inventar neu oeffnen)", "ok")

    def _ilog(self, msg):
        self.win.ui(lambda: self.log(msg, "info"))

    def _run(self, job, ok):
        self._busy = True

        def done(res):
            self._busy = False
            ok(res)

        def fail(e):
            self._busy = False
            msg = str(e) or e.__class__.__name__
            self.log(msg, "err")
            self.v_info.set("Fehler: " + msg)

        self.bg(job, done, fail)

    # -- Cave-Trainer fuer beliebige Funktionen ----------------------------------------------------
    def _hook_targets(self, live):
        """Nur LESEN: ProcessEvent-Adresse + vtable-Slots der PlayerController -> (pe, slots, notizen)."""
        import ue_hook as HK
        import ue_call
        sdk = self._sdk()
        pidx = sdk.offset("process_event_index", "processeventindex", default=77)
        prva = sdk.offset("process_event")
        objs = []
        try:
            objs = [i["addr"] for i in live.instances("APlayerController") if "Default__" not in i["name"]]
        except Exception:  # noqa: BLE001
            pass
        if not objs:
            raise ValueError("Kein PlayerController gefunden - Spielstand laden (nicht im Hauptmenue)")
        read = self.win.client.read_memory
        pe = ue_call.process_event_addr(read, objs[0], pidx, fallback=(self.base + prva) if prva else None)
        slots, notes = HK.find_slots(read, objs, pidx, pe)
        return pe, slots, notes

    def _parse_extra(self, text):
        out = {}
        for part in [p for p in text.replace(";", ",").split(",") if p.strip()]:
            if "=" not in part:
                raise ValueError(f"'{part.strip()}' - Format 'Name=Wert'")
            k, v = part.split("=", 1)
            v = v.strip()
            out[k.strip()] = float(v) if re.fullmatch(r"-?\d*\.\d+(e-?\d+)?", v) else int(v, 0)
        return out

    def export_cave_trainer(self):
        if self._busy:
            self.log("Es laeuft noch ein Auftrag - kurz warten", "err")
            return
        s = self._selected()
        if s is None or s.kind != "give_function":
            self.log("Erst eine Zeile der Art 'Geben-Funktion' anklicken (z. B. AddItem / GiveItem)", "err")
            return
        d = s.data
        sdk = self._sdk()
        try:
            cls = CG.classify_params(d["params"], sdk)
            CG.check_return(d.get("ret"))
            ctext = self.v_amount.get().strip() or "1"
            fl = any(a["role"] == "count" and a["kind"] in ("float", "double") for a in cls)
            amount = float(ctext) if fl else int(ctext, 0)
            extra = self._parse_extra(self.v_extra.get())
            id_arg = next((a for a in cls if a["role"] == "id"), None)
            ids = []                                        # [(alias, wert)]
            if id_arg is None:
                ids = [(f"{d['name']} x{ctext}", None)]
            elif id_arg["kind"] == "fname":
                sel = self._selected_rows()
                if not sel:
                    raise ValueError("Die Funktion braucht einen Item-Namen (FName): erst eine Item-Tabelle doppelklicken, "
                                     "dann Zeile(n) unten anklicken")
                ids = [(r["name"], bytes.fromhex(r["fname_hex"])) for r in sel]
            else:
                txt = self.v_idnum.get().strip()
                if not txt:
                    raise ValueError("Die Funktion braucht eine ID-Zahl, die in der Tabelle nicht zu finden war - erst eine Item-Tabelle "
                                     "lesen und das Item anklicken (die ID wird dann automatisch uebernommen) oder die Zahl eintippen")
                ids = [(f"ID {int(txt, 0)}", int(txt, 0))]
        except (ValueError, TR.TrainerError) as e:
            self.log(str(e), "err")
            return
        byref = [a["name"] for a in cls if a["kind"] == "fname"] if self.v_byref.get() else []
        # Eintraege: je Zeile einer ODER ein Paket (in 14er geteilt)
        package = False
        if len(ids) > 1:
            ans = messagebox.askyesnocancel("Trainer-Eintraege", f"{len(ids)} Zeilen gewaehlt.\n\nJA = Paket-Eintraege "
                                            f"(je {TR.PACK_SIZE} Items)\nNEIN = je Zeile ein eigener Eintrag", parent=self.win)
            if ans is None:
                return
            package = ans
        pname = ""
        if package:
            pname = simpledialog.askstring("Name des Eintrags", "Name des Trainer-Eintrags:",
                                           initialvalue=d["name"], parent=self.win)
            if not pname:
                return
        out_dir = filedialog.askdirectory(title="Ordner fuer das Trainer-Projekt waehlen (neu, oder vorhandener Trainer wird erweitert)",
                                          parent=self.win)
        if not out_dir:
            return
        old = TR.load_options(out_dir)
        client, base = self.win.client, self.base
        this_pick = self.v_this.get()
        self.v_info.set("Baue Cave-Trainer …")

        def job():
            live = self._live()
            ent = live.function_entry(d["owner"], d["name"])
            if not ent:
                raise ValueError(f"{d['owner']}.{d['name']} wurde im laufenden Spiel nicht gefunden")
            impl = _find_impl(client.read_memory, base, ent[0])
            if impl is None:
                raise ValueError("Die native Implementierung wurde nicht erkannt (Blueprint-Funktion oder ungewohnter Thunk) - "
                                 "dafuer laesst sich keine statische Cave bauen.")
            mode, off, note = CG.choose_this(sdk, d["owner"])
            self._ilog("this: " + note)
            if this_pick != "auto":
                if this_pick == "member" and mode != "member":
                    raise ValueError("this=member: im PlayerController wurde kein Zeiger auf " + d["owner"] + " gefunden")
                mode, off = this_pick, (off if this_pick == "member" else 0)
            rows = [CG.build_row(alias, impl - base, d["params"], d.get("ret"), sdk, (mode, off), id_value=val,
                                 count_value=amount, extra=extra, byref=byref, function=f"{d['owner']}.{d['name']}")
                    for alias, val in ids]
            if package:
                opts = TR.split_package(pname, rows)
            elif id_arg is None:
                opts = [TR.Option(rows[0].alias, rows)]
            else:
                opts = [TR.Option(f"{r.alias} x{ctext}", [r]) for r in rows]
            merged = TR.merge_options(old, opts)
            pe, slots, notes = self._hook_targets(live)
            for n in notes:
                self._ilog("Haken: " + n)
            maps = [(m[0], m[1], m[2]) for m in client.get_maps()]
            p = TR.plan(client.read_memory, maps, base, merged, None, pe, slots, log=self._ilog)
            files = TR.write_project(out_dir, p, game=str(getattr(getattr(self._uelive(), "proj", None), "name", "") or ""))
            return p, files

        def ok(res):
            p, files = res
            self.log(f"Cave-Trainer geschrieben: {out_dir}", "ok")
            self.log(f"   {len(p.options)} Eintrag/Eintraege, Cave base+{p.cave - p.base:#x} ({len(p.cave_bytes)} Byte), "
                     f"Schalter base+{p.flag_addr - p.base:#x}, {len(p.slots)} Haken-Slot(s)", "ok")
            for w in p.warnings:
                self.log("   " + w, "info")
            self.log("In ReaperPy den Ordner als Projekt waehlen, '00 BASIS' EINMAL aktivieren, dann Eintraege anklicken. "
                     "Am echten Spiel NICHT getestet - vorher speichern; bei Absturz zuerst 'this' und 'FName per Zeiger' pruefen.", "info")
            self.v_info.set(f"Cave-Trainer exportiert: {len(p.options)} Eintraege -> {os.path.basename(out_dir)}")

        self._run(job, ok)

    # -- Bericht / UE-LIVE ----------------------------------------------------------------------
    def save_report(self):
        if self.prof is None:
            self.log("Erst ANALYSIEREN", "err")
            return
        path = filedialog.asksaveasfilename(title="Bericht speichern", defaultextension=".md", initialfile="UE_ENTDECKER.md",
                                            filetypes=[("Markdown", "*.md"), ("JSON", "*.json")])
        if not path:
            return
        text = P.to_json(self.prof) if path.lower().endswith(".json") else P.render_markdown(self.prof)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.log(f"Bericht gespeichert: {path}", "ok")

    def open_in_live(self):
        s = self._selected()
        if s is None:
            self.log("Erst einen Vorschlag anklicken", "err")
            return
        d = s.data
        owner = d.get("owner") or (d.get("containers") or [{}])[0].get("owner") or (d.get("struct") or "")
        member = d.get("member") or ((d.get("id") or {}).get("name") if s.kind == "item_struct" else "")
        if s.kind == "attribute_set":
            member = d["attrs"][0][0] if d.get("attrs") else ""
        if not owner or not member:
            self.log("Dieser Vorschlag zeigt auf keinen einzelnen Member - Details im Textfeld", "err")
            return
        ue = self._uelive()
        if ue is None:
            self.log("Tab UE-LIVE nicht gefunden", "err")
            return
        ue.v_q.set(f"{owner}.{member}")
        try:
            ue._fill_targets()
            self.win.show_tab(ue)
        except Exception:  # noqa: BLE001 - nur Komfort
            pass
        self.log(f"UE-LIVE: Suche auf {owner}.{member} gesetzt", "ok")
