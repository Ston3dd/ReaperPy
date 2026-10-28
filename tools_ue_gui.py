"""tools_ue_gui.py - Tab "UE-AUTO": Unreal-SDK + Dump -> Cheat-Kandidaten -> Instruktionen/Funktionen -> Patches.

Die Logik steckt in ue_project.py (Spielordner), uesdk.py (Parser), uecheat.py (Filter), ue_instr.py
(Scan/Patch-Bau), ue_live.py (Objekte lesen) und dumpmem.py (Dump als Speicher) - hier nur Oberflaeche.
"""

import json
import os
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tools_common import (
    ACCENT,
    BG,
    WARN,
    BaseTab,
    button,
    entry,
    label,
    tree,
    with_scroll,
)

PACK = {
    "float": "<f",
    "double": "<d",
    "int32": "<i",
    "int": "<i",
    "uint32": "<I",
    "int64": "<q",
    "uint64": "<Q",
    "int16": "<h",
    "uint16": "<H",
    "uint8": "<B",
    "int8": "<b",
    "bool": "<B",
    "int32_t": "<i",
    "uint32_t": "<I",
    "int64_t": "<q",
    "uint64_t": "<Q",
    "int16_t": "<h",
    "uint16_t": "<H",
    "uint8_t": "<B",
    "int8_t": "<b",
    "ffixedpoint64": "<q",
}
FIXED_SCALE = 1000  # FFixedPoint64.Value = Anzeigewert x 1000 (Palworld)
FILE_KEYS = (
    ("sdk", "SDK-ORDNER…", "sdk"),
    ("offsets", "OFFSETS.JSON…", "offsets"),
    ("dump_json", "DUMP.JSON…", "dump_json"),
    ("dump_bin", "DUMP.BIN…", "dump_bin"),
    ("gobjects", "GOBJECTS.TXT (opt.)…", "gobjects"),
)


def _norm_type(type_name):
    type_name = type_name.replace("struct ", "").replace("class ", "").replace(" ", "").lower()
    return type_name


def _fmt_for(t):
    return PACK.get(_norm_type(t))


def _show(fmt, raw, t):
    value = struct.unpack(fmt, raw)[0]
    if _norm_type(t) == "ffixedpoint64":
        return f"{value} (= {value / FIXED_SCALE:.6g})"
    return f"{value:.6g}" if fmt in ("<f", "<d") else str(value)


class UeTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.proj = self.live = None
        self.cands, self.by, self.cur_hits, self.cur_cand = [], {}, [], None
        self.insts, self.funcs, self.impl = [], [], {}

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(8, 2))
        self.v = {k: tk.StringVar() for k, _t, _f in FILE_KEYS}
        self.v["game"] = tk.StringVar()
        button(top, "SPIEL-ORDNER…", self._pick_game, accent=True).grid(row=0, column=0, sticky="we", padx=2, pady=1)
        entry(top, self.v["game"], 70).grid(row=0, column=1, sticky="we", padx=2, pady=1)
        for i, (k, txt, _f) in enumerate(FILE_KEYS, start=1):
            button(top, txt, self._pick_dir if k == "sdk" else (lambda k=k: self._pick_file(k))).grid(
                row=i, column=0, sticky="we", padx=2, pady=1
            )
            entry(top, self.v[k], 70).grid(row=i, column=1, sticky="we", padx=2, pady=1)
        top.grid_columnconfigure(1, weight=1)
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=8, pady=2)
        label(row, "NATIVE ADR.").pack(side="left")
        self.v_nat = tk.StringVar(value="auto")
        ttk.Combobox(row, textvariable=self.v_nat, values=("auto", "rva", "va"), width=5, state="readonly").pack(
            side="left", padx=4
        )
        # keine Filter-Regler mehr: nichts wird nach Score/Kategorie ausgeblendet (jedes Spiel benennt anders)
        self.v_min = tk.StringVar(value="-99")
        self.v_cat = tk.StringVar(value="alle")
        self.v_q = tk.StringVar()
        search_entry = entry(row, self.v_q, 16)
        search_entry.pack(side="left", padx=4)
        search_entry.bind("<KeyRelease>", lambda _e: self._fill_cands())
        button(row, "▶ LADEN & ANALYSIEREN", self.load, accent=True).pack(side="right")
        self.lbl = label(
            self,
            "Spiel-Ordner wählen: offsets.json, dump.json/.bin, SDK_HEADERS und GObjects.txt werden "
            "automatisch gefunden. Ohne dump.bin gibt es Kandidaten und Funktionsliste, aber keine "
            "Instruktionssuche.",
        )
        self.lbl.pack(anchor="w", padx=10)

        pan = ttk.PanedWindow(self, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=8, pady=6)
        left = tk.Frame(pan, bg=BG)
        pan.add(left, weight=2)
        label(left, "CHEAT-KANDIDATEN (SDK)").pack(anchor="w")
        self.tc = tree(
            left,
            [("s", "SCORE"), ("c", "KATEGORIE"), ("k", "KLASSE.MEMBER"), ("o", "OFFSET"), ("t", "TYP")],
            [55, 110, 250, 70, 90],
            height=16,
        )
        with_scroll(left, self.tc)
        self.tc.bind("<<TreeviewSelect>>", lambda _e: self._on_cand())
        right = tk.Frame(pan, bg=BG)
        pan.add(right, weight=3)
        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True)

        instr_page = tk.Frame(self.nb, bg=BG)
        self.nb.add(instr_page, text="INSTRUKTIONEN")
        bar = tk.Frame(instr_page, bg=BG)
        bar.pack(fill="x", pady=2)
        button(bar, "SUCHEN", self.find_hits, accent=True).pack(side="left", padx=2)
        button(bar, "→ DISASM", self.goto_hit).pack(side="left", padx=2)
        button(bar, "NOP-PATCH", lambda: self.make_patches(False)).pack(side="left", padx=2)
        button(bar, "+ CAVE 'KANN NICHT SINKEN'", lambda: self.make_patches(True)).pack(side="left", padx=2)
        self.th = tree(
            instr_page,
            [("s", "SCORE"), ("r", "RVA"), ("i", "INSTRUKTION"), ("k", "ART"), ("c", "KO"), ("f", "HINWEIS")],
            [55, 90, 270, 55, 40, 190],
            height=14,
        )
        with_scroll(instr_page, self.th)
        self.th.bind("<Double-1>", lambda _e: self.goto_hit())

        func_page = tk.Frame(self.nb, bg=BG)
        self.nb.add(func_page, text="FUNKTIONEN")
        bar2 = tk.Frame(func_page, bg=BG)
        bar2.pack(fill="x", pady=2)
        button(bar2, "IMPL. AUFLÖSEN", self.func_impl, accent=True).pack(side="left", padx=2)
        button(bar2, "→ DISASM", self.func_goto).pack(side="left", padx=2)
        self.v_mode = tk.StringVar(value="false")
        import ue_instr

        ttk.Combobox(bar2, textvariable=self.v_mode, values=tuple(ue_instr.RET_MODES), width=7, state="readonly").pack(
            side="left", padx=(10, 2)
        )
        button(bar2, "FUNKTIONS-PATCH", self.func_patch).pack(side="left", padx=2)
        button(bar2, "NATIVE ADR. (live)", self.func_entry).pack(side="left", padx=2)
        bar2b = tk.Frame(func_page, bg=BG)
        bar2b.pack(fill="x", pady=2)
        label(bar2b, "PARAMETER").pack(side="left")
        self.v_ufarg = tk.StringVar()
        entry(bar2b, self.v_ufarg, 42).pack(side="left", padx=4)
        button(bar2b, "UFUNKTION AUFRUFEN (live)", self.func_call).pack(side="left", padx=2)
        label(
            bar2b,
            "z.B. TimeDilation=0.3 WorldContextObject=0x…  | Objekt = gewählte Instanz (Tab INSTANZEN), "
            "bei statischen Funktionen das Default-Objekt",
            dim=True,
        ).pack(side="left", padx=6)
        self.tf = tree(
            func_page,
            [
                ("c", "KLASSE"),
                ("f", "FUNKTION"),
                ("k", "KAT."),
                ("n", "NATIVE RVA"),
                ("i", "IMPL RVA"),
                ("s", "SIGNATUR"),
            ],
            [150, 190, 70, 90, 90, 300],
            height=14,
        )
        with_scroll(func_page, self.tf)
        self.tf.bind("<Double-1>", lambda _e: self.func_goto())
        label(
            func_page,
            "NATIVE ist der Exec-Thunk (UHT-Hülle). Gepatcht wird die IMPLEMENTIERUNG dahinter - ein 'ret' im "
            "Thunk würde den Blueprint-Stack verschieben. Geteilte Stubs (viele Funktionen, gleiche Adresse) "
            "sind Blueprint/Delegates und nicht patchbar.",
            dim=True,
        ).pack(anchor="w")

        live_page = tk.Frame(self.nb, bg=BG)
        self.nb.add(live_page, text="INSTANZEN")
        bar3 = tk.Frame(live_page, bg=BG)
        bar3.pack(fill="x", pady=2)
        button(bar3, "LIVE FINDEN", lambda: self.instances(False), accent=True).pack(side="left", padx=2)
        button(bar3, "AUS DUMP", lambda: self.instances(True)).pack(side="left", padx=2)
        button(bar3, "→ SPEICHER", self.inst_mem).pack(side="left", padx=2)
        button(bar3, "→ SCHREIBER FINDEN", self.inst_watch).pack(side="left", padx=2)
        self.v_set = tk.StringVar()
        entry(bar3, self.v_set, 10).pack(side="left", padx=(10, 2))
        button(bar3, "WERT SETZEN", self.inst_set).pack(side="left", padx=2)
        self.ti = tree(
            live_page,
            [("a", "OBJEKT"), ("n", "NAME"), ("m", "MEMBER-ADRESSE"), ("v", "WERT")],
            [140, 220, 150, 170],
            height=14,
        )
        with_scroll(live_page, self.ti)
        label(
            live_page,
            "LIVE: echte Objekte im laufenden Spiel (UE 4.23+/5). AUS DUMP: Zustand zur Dump-Zeit (Adressen "
            "gelten nur für diesen Lauf). FixedPoint-Werte: Eingabe × 1000 (Palworld). Den Schreiber findest "
            "du, indem du im Spiel den Wert änderst - der Debugger zeigt die Instruktion.",
            dim=True,
        ).pack(anchor="w")

    def _pick_game(self):
        folder = filedialog.askdirectory(parent=self.win, title="Spielordner (mit offsets.json, dump.json, SDK ...)")
        if not folder:
            return
        self.v["game"].set(folder)
        import dumpmem

        game_files = dumpmem.find_game_files(folder)
        for k, _t, fk in FILE_KEYS:
            self.v[k].set(game_files.get(fk) or "")
        missing = [k for k, value in game_files.items() if not value]
        self.lbl.configure(
            text="gefunden: "
            + ", ".join(k for k, value in game_files.items() if value)
            + (f"   |   FEHLT: {', '.join(missing)}" if missing else ""),
            fg=WARN if missing else ACCENT,
        )

    def _pick_dir(self):
        d = filedialog.askdirectory(parent=self.win, title="SDK-Ordner (SDK_HEADERS)")
        if d:
            self.v["sdk"].set(d)

    def _pick_file(self, k):
        f = filedialog.askopenfilename(parent=self.win)
        if f:
            self.v[k].set(f)

    def load(self):
        try:
            min_score = float(self.v_min.get())
        except Exception as error:
            return self.log(str(error), "err")
        files = {k: (self.v[k].get().strip() or None) for k, _t, _f in FILE_KEYS}
        files["engine"] = None
        if not (files["sdk"] or files["offsets"]):
            return self.log("SPIEL-ORDNER wählen (oder SDK-Ordner/offsets.json angeben)", "err")
        native = self.v_nat.get() or "auto"

        def job():
            import ue_project

            proj = ue_project.GameProject(
                files=files, native=native, log=lambda m: self.win.ui(lambda: self.log(m, "warn"))
            ).load()
            return proj, proj.candidates(min_score), proj.functions()

        def ok(result):
            if self.proj:
                self.proj.close()
            self.proj, self.cands, self.funcs = result
            self.by, self.impl, self.live = {}, {}, None
            self._fill_cands()
            self._fill_funcs()
            stats = self.proj.sdk.stats
            nat = self.proj.native_info
            self.lbl.configure(
                text=f"{self.proj.title or '?'}  |  {stats['classes']} Klassen, {stats['members']} Member, {len(self.cands)} Kandidaten, "
                f"{len(self.funcs)} Funktionsziele  |  Basis {self.proj.base:#x}  |  "
                + (f"Dump: ja ({self.proj.dis.name})" if self.proj.dm else "Dump: NEIN")
                + (f"  |  native = {nat[0].upper()}" if nat else ""),
                fg=ACCENT,
            )
            self.log("Spiel geladen", "ok")

        self.bg(job, ok)

    def _fill_cands(self):
        self.tc.delete(*self.tc.get_children())
        cat, query = self.v_cat.get(), self.v_q.get().strip().lower()
        for i, candidate in enumerate(self.cands):
            if (cat not in ("alle", "") and candidate.category != cat) or (
                query and query not in candidate.key.lower()
            ):
                continue
            self.tc.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    f"{candidate.score:.1f}",
                    candidate.category,
                    candidate.key,
                    f"{candidate.offset:#x}",
                    candidate.type,
                ),
            )

    def _fill_funcs(self):
        self.tf.delete(*self.tf.get_children())
        for i, function in enumerate(self.funcs[:4000]):
            nat = f"{self.proj.native_rva(function['native']):#x}" if function["native"] else "—"
            if function["shared"]:
                nat += " (geteilt)"
            impl = self.impl.get(i)
            self.tf.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    function["cls"],
                    function["name"],
                    function["category"],
                    nat,
                    f"{impl - self.proj.base:#x}" if impl else "",
                    function["sig"],
                ),
            )

    def _sel_cands(self):
        return [self.cands[int(i)] for i in self.tc.selection()]

    def _on_cand(self):
        sc = self._sel_cands()
        self.cur_cand = sc[0] if sc else None
        self._show_hits()

    def find_hits(self):
        sel = self._sel_cands()
        if not sel or not self.proj or not self.proj.dm:
            return self.log("erst laden (mit dump.bin) und Kandidaten wählen (Mehrfachauswahl möglich)", "warn")
        proj = self.proj

        def ok(by):
            self.by.update(by)
            self._show_hits()
            n = sum(len(by.get(c.key, [])) for c in sel)
            self.log(f"{n} schreibende Instruktion(en) gefunden", "ok" if n else "warn")

        self.bg(lambda: proj.analyze(sel), ok)

    def _show_hits(self):
        self.th.delete(*self.th.get_children())
        self.cur_hits = self.by.get(self.cur_cand.key, []) if self.cur_cand else []
        for i, cur_hit in enumerate(self.cur_hits[:500]):
            note = []
            if cur_hit.dec_hint:
                note.append("SUB davor")
            if cur_hit.ambiguity > 12:
                note.append(f"mehrdeutig ({cur_hit.ambiguity})")
            self.th.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    f"{cur_hit.score:.1f}",
                    f"{cur_hit.rva:#x}",
                    cur_hit.ins.text,
                    cur_hit.kind,
                    cur_hit.coaccess,
                    ", ".join(note),
                ),
            )

    def _sel_hits(self):
        return [self.cur_hits[int(i)] for i in self.th.selection()]

    def goto_hit(self):
        sh = self._sel_hits()
        if sh:
            self.win.goto_disasm(self.base + sh[0].rva)

    def _patch_dir(self):
        app = self.win.app
        if not app.PATCH_DIR:
            raise RuntimeError("kein Projekt/Patch-Ordner aktiv - erst ein Projekt öffnen")
        return app.PATCH_DIR

    def make_patches(self, caves):
        hits = self._sel_hits()
        if not hits:
            return self.log("erst Treffer wählen", "warn")
        try:
            pdir = self._patch_dir()
        except Exception as error:
            return self.log(str(error), "err")
        if not messagebox.askyesno(
            "Patches erzeugen",
            f"{len(hits)} Treffer -> .reapproj in\n{pdir}\n"
            "Hinweis: gilt für ALLE Objekte, die diesen Code nutzen (auch Gegner).",
            parent=self.win,
        ):
            return
        proj = self.proj

        def job():
            import ue_auto

            code = proj.code()
            return ue_auto.write_patches(
                pdir,
                code["buf"],
                proj.dis,
                hits,
                code["base_va"],
                caves=caves,
                code_range=code["range"],
                log=lambda m: self.win.ui(lambda: self.log(m, "warn")),
            )

        self.bg(job, lambda files: self._patched(files))

    def _patched(self, files):
        try:
            self.win.app.load_patches()
        except Exception as error:
            self.log(f"Patch-Liste nicht neu geladen: {error}", "warn")
        self.log(f"{len(files)} Patch-Datei(en): " + ", ".join(files[:4]) + (" …" if len(files) > 4 else ""), "ok")

    def _sel_func(self):
        sel = self.tf.selection()
        if not sel:
            raise ValueError("erst eine Funktion wählen")
        i = int(sel[0])
        return i, self.funcs[i]

    def func_impl(self):
        try:
            i, func = self._sel_func()
        except Exception as error:
            return self.log(str(error), "err")
        if not self.proj or not self.proj.dm:
            return self.log("dafür wird dump.bin gebraucht", "warn")
        if not func["native"] or func["shared"]:
            return self.log("geteilter Stub bzw. keine Adresse - nichts aufzulösen (Blueprint/Delegate)", "warn")
        proj = self.proj

        def ok(result):
            if not result:
                return self.log(f"{func['cls']}.{func['name']}: keine Implementierung hinter dem Thunk erkannt", "warn")
            self.impl[i] = result[0]
            self._fill_funcs()
            self.log(
                f"{func['cls']}.{func['name']}: Implementierung RVA {result[0] - proj.base:#x}"
                + (f" (+{len(result) - 1} weitere Kandidaten)" if len(result) > 1 else ""),
                "ok",
            )

        self.bg(lambda: proj.resolve_impl(func), ok)

    def func_goto(self):
        try:
            i, f = self._sel_func()
        except Exception as error:
            return self.log(str(error), "err")
        va = self.impl.get(i) or (self.proj.native_va(f["native"]) if f["native"] else None)
        if va:
            self.win.goto_disasm(va)

    def func_patch(self):
        try:
            i, func = self._sel_func()
            pdir = self._patch_dir()
        except Exception as error:
            return self.log(str(error), "err")
        if func["shared"] or not func["native"]:
            return self.log("geteilter Stub bzw. keine Adresse - nicht patchbar", "err")
        if i not in self.impl:
            return self.log("erst IMPL. AUFLÖSEN (der Thunk selbst darf nicht gepatcht werden)", "warn")
        mode, va, name, proj = self.v_mode.get(), self.impl[i], f"{func['cls']}.{func['name']}", self.proj
        if not messagebox.askyesno(
            "Funktions-Patch",
            f"{name}\nImplementierung {va - proj.base:#x}: Modus '{mode}'.\nGilt für alle Aufrufer der Funktion.",
            parent=self.win,
        ):
            return

        def job():
            p = proj.function_patch(va, mode, name)
            fn = os.path.join(
                pdir, "".join(c if c.isalnum() or c in " ._()-+" else "_" for c in p["name"]) + ".reapproj"
            )
            with open(fn, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(p, handle, indent=2, ensure_ascii=False)
            return [os.path.basename(fn)]

        self.bg(job, self._patched)

    def func_entry(self):
        try:
            i, func = self._sel_func()
        except Exception as error:
            return self.log(str(error), "err")

        def job():
            return self._ensure_live().function_entry(func["cls"], func["name"])

        def ok(result):
            if not result:
                return self.log(f"{func['cls']}.{func['name']}: kein nativer Einsprung", "warn")
            self.log(f"{func['cls']}.{func['name']}: ExecFunction {result[0]:#x} (RVA {result[1]:#x})", "ok")
            self.win.goto_disasm(result[0])

        self.bg(job, ok)

    def func_call(self):
        """Eine UFunction ueber ProcessEvent aufrufen (Verfahren wie uecall im ps4-unreal-dumper)."""
        try:
            i, func = self._sel_func()
            if not self.proj:
                raise RuntimeError("erst laden")
            assign_txt = self.v_ufarg.get()
        except Exception as error:
            return self.log(str(error), "err")
        sel = self.ti.selection()
        inst = self.insts[int(sel[0])][0]["addr"] if sel else None
        if not messagebox.askyesno(
            "UFunction aufrufen",
            f"{func['cls']}.{func['name']}\nLäuft auf einem Hilfs-Thread des Spiels. Funktionen, die "
            "Objekte erzeugen (SpawnActor, Widgets), können das Spiel zum Absturz bringen.",
            parent=self.win,
        ):
            return
        proj = self.proj

        def job():
            import ue_call

            live = self._ensure_live()
            if live.index is None:
                live.build_index()
            proj.sdk.load_params()
            params = proj.sdk.params_for(func["cls"], func["name"])
            if not params:
                raise ValueError("kein Parameter-Layout gefunden (…_parameters.hpp im SDK-Ordner?)")
            function = live.find_function(func["cls"], func["name"])
            if not function:
                raise ValueError("UFunction-Objekt im Spiel nicht gefunden (Klasse nicht geladen?)")
            obj = inst
            if (func["flags"] & 0x2000) or obj is None:  # FUNC_Static -> Default-Objekt
                if not (func["flags"] & 0x2000):
                    raise ValueError("erst im Tab INSTANZEN eine Instanz wählen")
                obj = live.default_object(func["cls"])
                if not obj:
                    raise ValueError("Default-Objekt der Klasse nicht gefunden")
            idx = proj.sdk.offset("process_event_index", "processeventindex", default=77)
            rva = proj.sdk.offset("process_event")
            process_event = ue_call.process_event_addr(
                self.win.client.read_memory, obj, idx, fallback=(self.base + rva) if rva else None
            )
            return ue_call.call_ufunction(
                self.win.client, obj, function, params, ue_call.parse_assignments(assign_txt), process_event
            )

        def ok(outs):
            self.log(f"{func['cls']}.{func['name']} aufgerufen" + ("" if outs else " (keine Ausgabe)"), "ok")
            for k, v in outs:
                self.log(f"   {k} = {v}", "ok")

        self.bg(job, ok)

    def _ensure_live(self, offline=False):
        import ue_live
        import ue_quick as Q

        proj = self.proj
        if proj is None:
            raise RuntimeError("erst laden")
        args = proj.live_args()
        if offline:
            if not proj.dm:
                raise RuntimeError("kein Dump geladen")
            live = ue_live.UELive(proj.dm.read, proj.base, proj.sdk, log=self.log)
            live.setup([proj.base], **args)
            return live
        client = self.win.client
        if client is None:
            raise RuntimeError("nicht verbunden")
        if self.live is not None and self.live._read == client.read_memory and self.live.arr:
            return self.live
        bases = [proj.base]
        try:
            module_base = ue_live.live_module_base(client.get_maps())
            if module_base:
                bases.append(module_base)
        except Exception:
            pass
        bases.append(self.base)
        live = ue_live.UELive(client.read_memory, proj.base, proj.sdk, log=self.log)
        try:
            try:
                maps = client.get_maps()
            except Exception:
                maps = None
            live.setup(bases, maps=maps, **args)
        except ue_live.UELiveError as error:
            self.live = None
            raise RuntimeError(
                f"{error}\n(Spiel gestartet und Level geladen? Heap-Adressen aendern sich bei jedem Start - "
                f"Basis im Prozess: {bases[1]:#x})"
                if len(bases) > 1
                else str(error)
            )
        Q.attach_fast(live, client, lambda m: self.log(m, "info"))  # parallele Lese-Verbindungen fuer den Objekt-Index
        self.live = live
        self.log(
            f"GObjects {live.num_elements} Objekte, Item {live.item_size:#x}, Name-Pool ok, Basis {live.base:#x}", "ok"
        )
        return live

    def instances(self, offline):
        if not self.cur_cand or not self.proj:
            return self.log("erst Kandidat wählen", "warn")
        cand = self.cur_cand
        self.inst_offline = offline

        def job():
            live = self._ensure_live(offline)
            if live.index is None:
                live.build_index()
            fmt, rows = _fmt_for(cand.type), []
            for i in live.instances(cand.cls)[:300]:
                val = ""
                try:
                    if fmt:
                        val = _show(fmt, live.rd(i["addr"] + cand.offset, struct.calcsize(fmt)), cand.type)
                except Exception:
                    val = "?"
                rows.append((i, val))
            return rows

        def ok(rows):
            self.insts = rows
            self.ti.delete(*self.ti.get_children())
            for n, (i, val) in enumerate(rows):
                self.ti.insert(
                    "", "end", iid=str(n), values=(f"{i['addr']:#x}", i["name"], f"{i['addr'] + cand.offset:#x}", val)
                )
            self.nb.select(2)
            self.log(
                f"{len(rows)} Instanz(en) von {cand.cls}" + (" (aus Dump)" if offline else ""), "ok" if rows else "warn"
            )

        self.bg(job, ok)

    def _sel_inst(self):
        sel = self.ti.selection()
        if not sel or not self.cur_cand:
            raise ValueError("erst eine Instanz wählen")
        return self.insts[int(sel[0])][0]["addr"] + self.cur_cand.offset

    def inst_mem(self):
        try:
            self.win.goto_memory(self._sel_inst())
        except Exception as error:
            self.log(str(error), "err")

    def inst_watch(self):
        try:
            self.win.to_debug_watch(self._sel_inst(), min(self.cur_cand.size or 4, 8))
        except Exception as error:
            self.log(str(error), "err")

    def inst_set(self):
        try:
            addr, fmt = self._sel_inst(), _fmt_for(self.cur_cand.type)
            if not fmt:
                raise ValueError(f"Typ '{self.cur_cand.type}' nicht beschreibbar")
            if getattr(self, "inst_offline", False):
                raise ValueError("Instanzen aus dem Dump sind nur zum Ansehen - LIVE FINDEN benutzen")
            txt = self.v_set.get().strip()
            if _norm_type(self.cur_cand.type) == "ffixedpoint64":
                val = int(round(float(txt) * FIXED_SCALE))
            elif fmt in ("<f", "<d"):
                val = float(txt)
            else:
                val = int(txt, 0)
            data = struct.pack(fmt, val)
        except Exception as error:
            return self.log(str(error), "err")
        self.bg(lambda: self.win.client.write_memory(addr, data), lambda _r: self.log(f"{addr:#x} = {txt}", "ok"))

    def shutdown(self):
        if self.proj:
            self.proj.close()
