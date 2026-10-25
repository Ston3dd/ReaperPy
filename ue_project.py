"""ue_project.py - ein Spiel als Ganzes: Ordner waehlen -> SDK, Offsets, Dump, GObjects werden gefunden und geladen.

Erwartete Struktur (Beispiel Palworld/PS5-Dumper):
    <Spiel>/offsets.json  dump.json  dump.bin  dump.bin.engine.json  GObjects.txt
    <Spiel>/SDK/SDK_HEADERS/*_classes.hpp, *_structs.hpp (*_parameters.hpp werden uebersprungen)
dump.bin ist optional - ohne sie gibt es Kandidaten und Funktionsliste, aber keine Instruktionssuche.
"""
import os

import dumpmem
import uecheat
import uesdk


class GameProject:
    def __init__(self, folder=None, files=None, native="auto", log=print):
        self.log = log
        self.files = files or dumpmem.find_game_files(folder)
        self.native_mode = native                       # 'auto' | 'rva' | 'va'
        self.sdk = None
        self.dm = None
        self.dis = None
        self.native_info = None                         # (modus, quote_rva, quote_va)
        self.engine = {}                                # dump.bin.engine.json (vom Dumper gemessen)
        self._common = None

    # ------------------------------------------------------------ laden
    def load(self, skip_params=True):
        f = self.files
        if not (f.get("sdk") or f.get("offsets")):
            raise FileNotFoundError("weder SDK-Header noch offsets.json gefunden")
        self.sdk = uesdk.load(f.get("sdk"), f.get("offsets"), f.get("gobjects"), skip_params=skip_params)
        if f.get("engine"):
            try:
                import json
                with open(f["engine"], encoding="utf-8-sig") as fh:
                    self.engine = json.load(fh)
            except Exception as e:
                self.log(f"engine.json nicht lesbar: {e}")
        if f.get("dump_bin") and f.get("dump_json"):
            try:
                self.dm = dumpmem.DumpMemory(f["dump_bin"], f["dump_json"], module_base=self.sdk.offset("base"))
            except Exception as e:
                self.log(f"Dump nicht lesbar: {e}")
        else:
            self.log("kein dump.bin/dump.json gefunden - Instruktionssuche nicht moeglich")
        if self.dm is not None:
            import ue_instr
            self.dis = ue_instr.get_disasm()
            self._detect_native()
        return self

    @property
    def base(self):
        b = self.sdk.offset("base") if self.sdk else None
        return b if b is not None else (self.dm.base if self.dm else 0x400000)

    @property
    def title(self):
        if self.dm and self.dm.meta.get("title_id"):
            return self.dm.meta["title_id"]
        m = self.sdk.meta if self.sdk else {}
        return m.get("title_id") or m.get("title") or m.get("titleid") or ""

    def _detect_native(self):
        addrs = [fn.native for c in self.sdk.classes.values() for fn in c.funcs if fn.native]
        used = uecheat.native_usage(self.sdk)
        addrs = [a for a in addrs if used.get(a, 0) < uecheat.SHARED_MIN]
        if self.native_mode in ("rva", "va"):
            self.native_info = (self.native_mode, None, None)
        elif addrs:
            self.native_info = dumpmem.native_convention(self.dm, addrs, self.base)
        else:
            self.native_info = ("rva", None, None)

    def live_args(self):
        """Argumente fuer UELive.setup(): absolute Adressen + Layout aus dem Dumper"""
        e = self.engine or {}
        return {"abs_gobjects": e.get("arr"), "abs_gnames": e.get("pool"), "layout": e.get("layout")}

    def native_rva(self, native):
        mode = self.native_info[0] if self.native_info else (self.native_mode if self.native_mode != "auto" else "rva")
        return native if mode == "rva" else native - self.base

    def native_va(self, native):
        return self.native_rva(native) + self.base

    # ------------------------------------------------------------ Code-Sicht
    def code(self):
        """-> dict(buf, lo, hi, base_va, dump_rva, range)  fuer ue_instr"""
        if not self.dm:
            raise RuntimeError("kein Dump geladen")
        buf, lo, hi, base_va = self.dm.code_view()
        return {"buf": buf, "lo": lo, "hi": hi, "base_va": base_va, "dump_rva": base_va - self.base,
                "range": (lo, hi)}

    # ------------------------------------------------------------ Analyse
    def candidates(self, min_score=8.0, categories=None, top=None):
        c = uecheat.find_candidates(self.sdk, min_score)
        if categories:
            c = [x for x in c if x.category in categories]
        return c[:top] if top else c

    def functions(self, min_score=3.0):
        return uecheat.find_function_targets(self.sdk, min_score=min_score)

    def analyze(self, cands, include_reads=False, progress=None):
        import ue_auto
        cv = self.code()
        import ue_instr
        targets, class_offs = ue_auto.targets_for(self.sdk, cands)
        hits = ue_instr.scan(cv["buf"], targets, self.dis, class_offs, base_va=cv["base_va"],
                             dump_rva=cv["dump_rva"], include_reads=include_reads, progress=progress,
                             code_range=cv["range"])
        by = {}
        for h in hits:
            for t in h.tags:
                by.setdefault(t, []).append(h)
        return by

    def resolve_impl(self, fn):
        """Funktions-Dict (find_function_targets) -> Implementierungs-VA hinter dem Exec-Thunk oder None."""
        import ue_instr
        cv = self.code()
        if self._common is None:
            used = uecheat.native_usage(self.sdk)
            vas = [self.native_va(f.native) for c in self.sdk.classes.values() for f in c.funcs
                   if f.native and used.get(f.native, 0) < uecheat.SHARED_MIN]
            self._common = ue_instr.common_callees(cv["buf"], self.dis, vas, cv["base_va"], cv["lo"], cv["hi"])
        r = ue_instr.resolve_impl(cv["buf"], self.dis, self.native_va(fn["native"]), cv["base_va"], cv["lo"], cv["hi"],
                                  self._common)
        return r

    def function_patch(self, target_va, mode, name, with_aob=True, author="ReaperPy UE-Auto"):
        import ue_instr
        cv = self.code()
        pos = target_va - cv["base_va"]
        aob = None
        if with_aob:
            aob, _n = ue_instr.make_aob_at(cv["buf"], self.dis, pos, target_va, hook_len=len(ue_instr.RET_MODES[mode][0]),
                                          min_len=16, code_range=cv["range"])
        return ue_instr.func_ret_patch(cv["buf"], pos, target_va - self.base, mode, name, aob, author)

    def close(self):
        if self.dm:
            self.dm.close()
