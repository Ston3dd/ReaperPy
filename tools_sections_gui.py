"""tools_sections_gui.py - Bereichsliste des Cheat-Searchers (Tab WERT SUCHEN).

Zeigt, was im Speicher des Spiels liegt: die eboot.bin aufgesplittet (Code / Konstanten / Daten), Spiel-Module, die
Systembibliotheken, Heap usw.  Jede Zeile hat einen Haken; Systembibliotheken & Co. lassen sich per Ausblend-Filter
(Voreinstellungen + eigene Muster) aus dem Scan nehmen.  Weniger Speicher = schnellerer Scan, vor allem bei
"Unbekannter Startwert".  Die Logik steckt in regionfilter.py (ohne GUI testbar).
"""
import tkinter as tk
from tkinter import ttk

import regionfilter as RF
import tools_i18n as T
from tools_common import BG_CARD, BG_CARD_HVR, ACCENT, TEXT, TEXT_DIM, WARN, FONT_LABEL, FONT_MONO, entry

CHK = {"on": "☑", "off": "☐", "mixed": "▣"}
DIM_HIDDEN = "#4a525c"


def tr(text):
    return T.translate(text)


def _fmt_count(n):
    return f"{n:,}".replace(",", " ")


class SectionPanel(tk.Frame):
    """Baum: Kategorie -> Bereiche.  Spalte 1 ist der Haken (Klick = ein/aus)."""

    def __init__(self, parent, tab, bg=BG_CARD):
        super().__init__(parent, bg=bg)
        self.tab = tab
        self.bgc = bg
        self.maps, self.secs, self.rows = [], {}, {}
        self.open = {"eboot"}                       # aufgeklappte Kategorien
        self._loading = False
        self.state = RF.load_state(self._path())
        self._build()
        self.update_summary()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _path(self):
        try:
            import os
            import paths
            return os.path.join(paths.data_dir(), "scan_filter.json")
        except Exception:
            return ""

    def _build(self):
        bg = self.bgc
        r1 = tk.Frame(self, bg=bg); r1.pack(fill="x")
        tk.Label(r1, text="AUSBLENDEN", bg=bg, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left")
        self.b_hide = tk.Button(r1, text="", command=self._popup_hide, bg=BG_CARD_HVR, fg=TEXT, font=FONT_LABEL,
                                relief="flat", bd=0, padx=8, pady=3, cursor="hand2", anchor="w",
                                activebackground=BG_CARD_HVR, activeforeground=ACCENT)
        self.b_hide.pack(side="left", fill="x", expand=True, padx=(6, 0))

        r2 = tk.Frame(self, bg=bg); r2.pack(fill="x", pady=(4, 0))
        tk.Label(r2, text="EIGENE MUSTER", bg=bg, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left")
        self.v_custom = tk.StringVar(value=self.state.custom)
        e = entry(r2, self.v_custom, 18)
        e.pack(side="left", fill="x", expand=True, padx=(6, 0))
        e.bind("<KeyRelease>", lambda _e: self._custom_changed())
        e.bind("<FocusOut>", lambda _e: self._custom_changed())
        tk.Label(self, text="z. B.  libSce*, SDL, Shm   (* = beliebig; ohne * = Namensteil)", bg=bg, fg=TEXT_DIM,
                 font=FONT_LABEL, anchor="w").pack(fill="x")

        r3 = tk.Frame(self, bg=bg); r3.pack(fill="x", pady=(6, 4))
        for text, fn in (("ALLE", self.sel_all), ("KEINE", self.sel_none), ("NUR EBOOT", self.sel_eboot),
                         ("NUR SPIEL", self.sel_game)):
            self._small(r3, text, fn).pack(side="left", padx=(0, 4))
        self._small(r3, "↻ AKTUALISIEREN", self.refresh).pack(side="right")

        fr = tk.Frame(self, bg=bg); fr.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(fr, columns=("chk", "size", "rights", "info"), show="tree headings",
                               height=8, selectmode="extended")
        self.tv.heading("#0", text="BEREICH")
        self.tv.heading("chk", text="✓")
        self.tv.heading("size", text="GRÖSSE")
        self.tv.heading("rights", text="RECHTE")
        self.tv.heading("info", text="INFO")
        self.tv.column("#0", width=190, stretch=True)
        self.tv.column("chk", width=34, anchor="center", stretch=False)
        self.tv.column("size", width=74, anchor="e", stretch=False)
        self.tv.column("rights", width=50, anchor="center", stretch=False)
        self.tv.column("info", width=100, stretch=False)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tv.pack(side="left", fill="both", expand=True)
        self.tv.tag_configure("cat", foreground=ACCENT, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self.tv.tag_configure("catoff", foreground=TEXT_DIM, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self.tv.tag_configure("off", foreground=TEXT_DIM)
        self.tv.tag_configure("hidden", foreground=DIM_HIDDEN)
        self.tv.bind("<Button-1>", self._click)
        self.tv.bind("<Double-1>", self._double)
        self.tv.bind("<space>", lambda _e: self._toggle_selected())
        self.tv.bind("<Button-3>", self._popup_row)
        self.tv.bind("<<TreeviewOpen>>", lambda _e: self._remember_open())
        self.tv.bind("<<TreeviewClose>>", lambda _e: self._remember_open())

        self.lbl_sum = tk.Label(self, text="", bg=bg, fg=TEXT, font=FONT_LABEL, anchor="w", justify="left")
        self.lbl_sum.pack(fill="x", pady=(6, 0))
        self.lbl_est = tk.Label(self, text="", bg=bg, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left")
        self.lbl_est.pack(fill="x")
        self._hide_title()

    def _small(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=BG_CARD_HVR, fg=TEXT, font=FONT_LABEL, relief="flat",
                         bd=0, padx=7, pady=2, cursor="hand2", activebackground=BG_CARD_HVR, activeforeground=ACCENT)

    # ------------------------------------------------------------------
    # Daten laden
    # ------------------------------------------------------------------
    def scope_key(self):
        return self.tab.scope_key()

    def refresh(self, quiet=False):
        """Prozess-Karte der Konsole holen und die Liste neu aufbauen."""
        cl = getattr(self.tab.win, "client", None)
        if cl is None or not hasattr(cl, "get_maps_named"):
            if not quiet:
                self.tab.log("nicht verbunden - im Hauptfenster VERBINDEN", "warn")
            return
        if self._loading:
            return
        self._loading = True

        def job():
            return cl.get_maps_named()

        def ok(maps):
            self._loading = False
            self.set_maps(maps)
            if not quiet:
                self.tab.log(f"Bereiche: {len(maps)} Regionen eingelesen", "ok")

        def err(e):
            self._loading = False
            if not quiet:
                self.tab.log(f"Bereiche: {e}", "err")
        self.tab.win.bg(job, ok, err)

    def auto(self):
        """Beim Anzeigen des Tabs einmal automatisch laden (wenn verbunden und noch leer)."""
        if not self.secs and not self._loading:
            self.refresh(quiet=True)

    def set_maps(self, maps):
        self.maps = list(maps)
        self.secs = RF.build_sections(self.maps)
        self._fill()
        self.update_summary()

    def make_pick(self, scope):
        """Auswahl-Funktion fuer Scanner.regions(pick=...): arbeitet mit einer Kopie der Einstellung und frischen Karte."""
        st = self.state.copy()

        def pick(named):
            self.tab.win.ui(lambda m=list(named): self.set_maps(m))
            return RF.included_starts(named, st, scope)
        return pick

    # ------------------------------------------------------------------
    # Anzeige
    # ------------------------------------------------------------------
    def _fill(self):
        tv = self.tv
        keep = [i for i in tv.selection()]
        top = tv.yview()[0] if self.secs else 0.0
        tv.delete(*tv.get_children())
        self.rows = {}
        scope = self.scope_key()
        for cat, lst in self.secs.items():
            stt = self.state.category_state(cat, lst)
            nreg = sum(len(s.regions) for s in lst)
            cid = f"c:{cat}"
            tv.insert("", "end", iid=cid, text=tr(RF.CATS[cat]), open=(cat in self.open),
                      values=(CHK[stt], RF.fmt_size(sum(s.size for s in lst)), "", f"{_fmt_count(nreg)} {tr('Regionen')}"),
                      tags=("catoff" if stt == "off" else "cat",))
            self.rows[cid] = ("cat", cat)
            for s in lst:
                self._insert_section(cid, s, scope)
        for i in keep:
            if i in self.rows:
                tv.selection_add(i)
        try:
            tv.yview_moveto(top)
        except Exception:
            pass

    def _insert_section(self, parent, s, scope):
        n, b, sn, sb = RF.section_stats(s, self.state, scope)
        on = self.state.is_on(s)
        info, tags = "", []
        if n == 0:
            info, tags = tr("nicht im Bereich"), ["hidden"]
        elif not on:
            tags = ["off"]
        elif sn == 0:
            reg = next(r for r in s.regions if RF.in_scope(r.prot, scope))
            info, tags = tr("ausgeblendet") + ": " + tr(self.state.hidden_reason(reg, s.cat)), ["hidden"]
        elif sn < n:
            info = tr("teils ausgeblendet")
        elif len(s.regions) > 1:
            info = f"{_fmt_count(len(s.regions))} {tr('Regionen')}"
        sid = f"s:{s.key}"
        label = tr(s.label) if s.label == RF.SMALL_LABEL else self._row_label(s)
        self.tv.insert(parent, "end", iid=sid, text=label,
                       values=(CHK["on" if on else "off"], RF.fmt_size(s.size), s.rights, info), tags=tuple(tags))
        self.rows[sid] = ("sec", s)

    def _row_label(self, s):
        if s.cat == "eboot":                          # "Code  0x400000" -> Art uebersetzen, Adresse behalten
            kind, _, addr = s.label.partition("  ")
            return f"{tr(kind)}  {addr}"
        return s.label

    def _hide_title(self):
        names = [tr(RF.PRESETS[k][0]) for k in RF.PRESETS if k in self.state.hide]
        if RF.split_patterns(self.state.custom):
            names.append(tr(RF.CUSTOM_LABEL))
        txt = ", ".join(names) if names else tr("keine Regel aktiv")
        self.b_hide.configure(text=f"{txt}  ▾")

    def update_summary(self):
        if not self.secs:
            self.lbl_sum.configure(text=tr("Noch keine Bereiche - AKTUALISIEREN drücken (Spiel muss verbunden sein)"),
                                   fg=WARN)
            self.lbl_est.configure(text="")
            return
        st = RF.stats(self.secs, self.state, self.scope_key())
        saved = 100 * (1 - st["sel_b"] / st["total_b"]) if st["total_b"] else 0
        self.lbl_sum.configure(
            text=f"{tr('Ausgewählt:')} {_fmt_count(st['sel_n'])} / {_fmt_count(st['total_n'])} {tr('Regionen')}  ·  "
                 f"{RF.fmt_size(st['sel_b'])} / {RF.fmt_size(st['total_b'])}"
                 + (f"  (-{saved:.0f} %)" if saved >= 1 else ""), fg=ACCENT if st["sel_n"] else WARN)
        mbps = getattr(getattr(self.tab, "sc", None), "last_mbps", 0) or 0
        est = f"{tr('Lesezeit')} ≈ {st['sel_b'] / RF.MB / mbps:.0f} s  ({tr('Tempo vom letzten Scan')})" if mbps else ""
        self.lbl_est.configure(text=est)

    def _changed(self):
        if self._path():
            RF.save_state(self.state, self._path())
        self._hide_title()
        self._fill()
        self.update_summary()

    def on_scope_changed(self):
        if self.secs:
            self._fill()
        self.update_summary()

    # ------------------------------------------------------------------
    # Bedienung
    # ------------------------------------------------------------------
    def _remember_open(self):
        self.open = {self.rows[i][1] for i in self.tv.get_children() if i in self.rows
                     and self.rows[i][0] == "cat" and self.tv.item(i, "open")}

    def _click(self, ev):
        try:
            if self.tv.identify_region(ev.x, ev.y) != "cell" or self.tv.identify_column(ev.x) != "#1":
                return None
            iid = self.tv.identify_row(ev.y)
        except Exception:
            return None
        if iid in self.rows:
            self._toggle(iid)
            return "break"
        return None

    def _double(self, ev):
        try:
            if self.tv.identify_column(ev.x) == "#1":
                return "break"                          # zwei schnelle Klicks auf den Haken nicht doppelt zaehlen
            iid = self.tv.identify_row(ev.y)
        except Exception:
            return None
        if iid in self.rows and self.rows[iid][0] == "sec":
            self._toggle(iid)
            return "break"
        return None

    def _toggle(self, iid):
        kind, obj = self.rows[iid]
        if kind == "cat":
            on = self.state.category_state(obj, self.secs[obj]) != "on"
        else:
            on = not self.state.is_on(obj)
        self._apply(self.tv.selection() if iid in self.tv.selection() else (iid,), on)

    def _toggle_selected(self):
        sel = [i for i in self.tv.selection() if i in self.rows]
        if sel:
            kind, obj = self.rows[sel[0]]
            on = (self.state.category_state(obj, self.secs[obj]) != "on") if kind == "cat" else not self.state.is_on(obj)
            self._apply(sel, on)

    def _apply(self, iids, on):
        for iid in iids:
            if iid not in self.rows:
                continue
            kind, obj = self.rows[iid]
            if kind == "cat":
                self.state.set_category(obj, on, self.secs[obj])
            else:
                self.state.set_section(obj, on, self.secs[obj.cat])
        self._changed()

    def sel_all(self):
        self.state.all_on()
        self._changed()

    def sel_none(self):
        self.state.all_off()
        self._changed()

    def sel_eboot(self):
        self.state.only(("eboot",))
        self._changed()

    def sel_game(self):
        self.state.only(("eboot", "gamemod", "heap"))
        self._changed()

    def _custom_changed(self):
        txt = self.v_custom.get()
        if txt != self.state.custom:
            self.state.custom = txt
            self._changed()

    def _popup_hide(self):
        m = tk.Menu(self, tearoff=0, bg=BG_CARD, fg=TEXT, activebackground=BG_CARD_HVR, activeforeground=ACCENT)
        self._hide_vars = {}
        for key, (name, _fn) in RF.PRESETS.items():
            v = tk.BooleanVar(value=key in self.state.hide)
            self._hide_vars[key] = v
            m.add_checkbutton(label=tr(name), variable=v, command=lambda k=key: self._hide_toggled(k))
        try:
            m.tk_popup(self.b_hide.winfo_rootx(), self.b_hide.winfo_rooty() + self.b_hide.winfo_height())
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    def _hide_toggled(self, key):
        if self._hide_vars[key].get():
            self.state.hide.add(key)
        else:
            self.state.hide.discard(key)
        self._changed()

    # --- Rechtsklick ------------------------------------------------------------------------------
    def _popup_row(self, ev):
        iid = self.tv.identify_row(ev.y)
        if iid and iid not in self.tv.selection():
            self.tv.selection_set(iid)
        sel = [i for i in self.tv.selection() if i in self.rows]
        m = tk.Menu(self, tearoff=0, bg=BG_CARD, fg=TEXT, activebackground=BG_CARD_HVR, activeforeground=ACCENT)
        if sel:
            m.add_command(label=tr("Auswahl einschalten"), command=lambda: self._apply(sel, True))
            m.add_command(label=tr("Auswahl ausschalten"), command=lambda: self._apply(sel, False))
            m.add_command(label=tr("Nur diese Auswahl scannen"), command=lambda: self._only(sel))
            secs = [self.rows[i][1] for i in sel if self.rows[i][0] == "sec" and self.rows[i][1].module]
            if secs:
                m.add_separator()
                m.add_command(label=tr("Modul ausblenden (zu eigenen Mustern)"), command=lambda: self._hide_modules(secs))
            first = self.rows[sel[0]]
            if first[0] == "sec":
                m.add_separator()
                m.add_command(label=tr("Startadresse kopieren"), command=lambda: self._copy(first[1].start))
                m.add_command(label=tr("Im Speicher anzeigen"), command=lambda: self._goto(first[1].start))
            m.add_separator()
        m.add_command(label=tr("Alle aufklappen"), command=lambda: self._expand(True))
        m.add_command(label=tr("Alle zuklappen"), command=lambda: self._expand(False))
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    def _only(self, iids):
        self.state.all_off()
        for iid in iids:
            kind, obj = self.rows[iid]
            if kind == "cat":
                self.state.set_category(obj, True, self.secs[obj])
            else:
                self.state.set_section(obj, True, self.secs[obj.cat])
        self._changed()

    def _hide_modules(self, secs):
        for s in secs:
            self.state.hide_pattern(s.module)
        self.v_custom.set(self.state.custom)
        self._changed()

    def _copy(self, addr):
        try:
            self.clipboard_clear()
            self.clipboard_append(f"0x{addr:X}")
        except Exception:
            pass

    def _goto(self, addr):
        try:
            self.tab.win.goto_memory(addr)
        except Exception as e:
            self.tab.log(f"{e}", "err")

    def _expand(self, opened):
        self.open = set(self.secs) if opened else set()
        self._fill()
