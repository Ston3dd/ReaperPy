"""export_goldhen.py - alle geladenen ReaperPy-Patches als EINE GoldHEN/etaHEN-Cheat-JSON.

Format (GoldHEN / etaHEN, Datei {TitleID}_{Version}.json):

    {"name": ..., "id": "CUSA12345", "version": "01.00", "process": "eboot.bin",
     "mods": [{"name": ..., "type": "checkbox",
               "memory": [{"offset": "<hex, relativ zur Modul-Basis>", "on": "<hex>", "off": "<hex>"}]}],
     "credits": [...]}

Einfache Patches (kein Label-Sprung)
    -> pro Patch-Stelle ein memory-Eintrag: on = neue Bytes, off = Original-Bytes.

Code-Cave-Patches (newValue springt per jmp/call auf ein Label)
    GoldHEN kann zur Laufzeit KEINEN Speicher anfordern, ReaperPy tut das aber (find_cave /
    allocate_memory).  Deshalb wird die Cave hier FEST in freien Leerraum IM Spiel-Image gelegt
    (Null-/0xCC-Padding am Ende der ausfuehrbaren Region) und als normaler memory-Eintrag
    geschrieben:
        1) Cave-Eintrag : on = Cave-Code (inkl. 'jmp OriginReturn'), off = derselbe Code (Cave bleibt stehen)
        2) Hook-Eintrag : on = jmp rel32 + NOPs,                      off = Original-Befehle
    Cave zuerst, Hook danach - so zeigt der Hook nie in leeren Speicher.  Beim Abschalten wird nur der Hook
    zurueckgesetzt; die Cave NICHT zu nullen verhindert Abstuerze, wenn ein Thread noch in ihr laeuft.
    Platz: zuerst nicht beschreibbare Code-Regionen (r-x); beschreibbare (rwx) nur als Fallback mit Warnung.

Gelesen wird LIVE von der Konsole (Original-Bytes, Memory-Map, freie Stellen), das Spiel muss also
laufen und ps5debug verbunden sein.  Aktive Patches sind kein Problem: dann kommen die Original-
Bytes aus defaultValue.

CLI:
    python export_goldhen.py --ip 192.168.137.2 --id CUSA12345 --version 01.00 \
        --out CUSA12345_01.00.json  <patch-ordner-oder-dateien> ...
"""
import argparse
import json
import os
import re
import sys

import aob as AOB
import patch_engine as PE
from reapatch import ReapPatch, is_patch_file

try:
    import capstone as _cs
    from capstone import x86_const as _x86
    HAVE_CAPSTONE = True
except Exception:                                   # pragma: no cover
    _cs = _x86 = None
    HAVE_CAPSTONE = False

TARGET_BASE = 0x400000          # Basis, auf die GoldHEN/etaHEN die 'offset'-Werte beziehen
LIMIT = 0x7F000000              # rel32-Reichweite (mit Sicherheitsabstand)
FILL_BYTES = (0x00, 0xCC)       # Padding, das als Cave-Platz taugt
TAIL_SCAN = 0x8000              # so viel vom Ende jeder Exec-Region wird zuerst geprueft
MIN_RUN = 0x20


class ExportError(Exception):
    pass


def _hex(b):
    return bytes(b).hex().upper()


def _read(backend, addr, n):
    d = backend.read(addr, n)
    if d is None or len(d) < n:
        raise ExportError(f"{addr:#x}: {n} Byte nicht lesbar")
    return bytes(d)


# ======================================================================
# Cave-Platz im Image
# ======================================================================
class _Run:
    __slots__ = ("start", "end", "tail", "region", "prot")

    def __init__(self, start, end, tail, region=(0, 0), prot=5):
        self.start, self.end, self.tail = start, end, tail
        self.region, self.prot = region, prot       # Region, in der die Luecke liegt, und deren Schutzbits


def _prot_str(p):
    return ("r" if p & 1 else "-") + ("w" if p & 2 else "-") + ("x" if p & 4 else "-")


class CaveAllocator:
    """Verwaltet freien Padding-Platz in ausfuehrbaren Regionen (Allokation von hinten nach vorn,
    16-Byte-ausgerichtet).  Bevorzugt echtes Segment-Ende-Padding; erst wenn das nicht reicht,
    werden grosse 0x00/0xCC-Luecken mitten im Code genutzt (Warnung im Report)."""

    def __init__(self, backend, log=print, image_base=None):
        self.backend = backend
        self.log = log
        self.image_base = image_base
        self._tail = {}                 # scope -> Luecken am Region-Ende
        self._inner = {}                # scope -> Luecken mitten im Code
        self.used_inner = False
        self.used_outside = False       # Cave ausserhalb des zusammenhaengenden Spiel-Images (Fallback)
        self._warned_outside = False
        self._warned_writable = False
        self.used_writable = False      # Cave in beschreibbarer (rwx) Region (Fallback)
        self.last_region = None         # (start, end, prot) der zuletzt vergebenen Cave

    # -- Scannen ---------------------------------------------------------
    def _regions(self, scope="image"):
        """Ausfuehrbare Regionen.  Mit bekannter Image-Basis NUR das Spiel-Image ("image"): Regionen UNTER der Basis
        oder in anderen Modulen waeren als GoldHEN-Offset (Basis + RVA) falsch bzw. nach dem Neustart ungueltig.
        scope "above" = Fallback: Regionen oberhalb der Basis ausserhalb des zusammenhaengenden Images."""
        maps = [(int(s), int(e), int(p)) for s, e, p in self.backend.get_maps(force=True)]
        if self.image_base:
            import cave_trainer
            span = cave_trainer.image_span(maps, self.image_base)
            if not span and not getattr(self, "_warned_no_image", False):
                self._warned_no_image = True
                self.log(f"[cave] WARNUNG: Image-Basis {self.image_base:#x} liegt in keiner Speicherregion - "
                         "Basis im Projekt pruefen; es werden Regionen oberhalb der Basis benutzt")
            if scope == "image":
                cand = [(s, e, p) for s, e, p in span if p & 4]
            else:
                inside = {(s, e) for s, e, _p in span}
                cand = [(s, e, p) for s, e, p in maps if (p & 4) and s >= self.image_base and (s, e) not in inside]
        else:
            cand = [(s, e, p) for s, e, p in maps if p & 4]
        return sorted((s, e, p) for s, e, p in cand if (e - s) >= 0x1000)

    def _scan_tail(self, scope="image"):
        runs = []
        for s, e, prot in self._regions(scope):
            n = min(TAIL_SCAN, e - s)
            try:
                data = _read(self.backend, e - n, n)
            except Exception:
                continue
            last = data[-1]
            if last not in FILL_BYTES:
                continue
            cnt = len(data) - len(data.rstrip(bytes([last])))
            if cnt >= MIN_RUN:
                runs.append(_Run(e - cnt, e, True, (s, e), prot))
        runs.sort(key=lambda r: -(r.end - r.start))
        what = "im Spiel-Image" if scope == "image" and self.image_base else "am Region-Ende"
        self.log(f"[cave] {len(runs)} Padding-Luecke(n) {what} gefunden")
        return runs

    def _scan_inner(self, scope="image"):
        runs = []
        rx = re.compile(b"(?:\x00{128,}|\xCC{128,})")
        CH = 0x100000
        for s, e, prot in self._regions(scope):
            pos = s
            while pos < e:
                size = min(CH + 256, e - pos)
                try:
                    data = _read(self.backend, pos, size)
                except Exception:
                    pos += CH
                    continue
                for m in rx.finditer(data):
                    if pos + m.end() <= e:
                        runs.append(_Run(pos + m.start(), pos + m.end(), False, (s, e), prot))
                pos += CH
        # Duplikate aus ueberlappenden Chunks entfernen
        uniq = {}
        for r in runs:
            uniq[r.start] = r if r.start not in uniq or r.end > uniq[r.start].end else uniq[r.start]
        out = sorted(uniq.values(), key=lambda r: -(r.end - r.start))
        self.log(f"[cave] {len(out)} Luecke(n) im Code gefunden (Fallback)")
        return out

    # -- Allokation --------------------------------------------------------
    def _find(self, need, near):
        need = (need + 15) & ~15
        scopes = ("image", "above") if self.image_base else ("image",)
        for scope in scopes:
            if scope not in self._tail:
                self._tail[scope] = self._scan_tail(scope)
            # erst nicht beschreibbare Regionen (r-x), beschreibbare (rwx) nur als Fallback; je Stufe erst Segment-Ende, dann Code-Luecken
            for writable in (False, True):
                for pool_i in range(2):
                    if pool_i == 1 and scope not in self._inner:
                        self._inner[scope] = self._scan_inner(scope)
                    pool = self._tail[scope] if pool_i == 0 else self._inner.get(scope, [])
                    for r in pool:
                        if bool(r.prot & 2) != writable:
                            continue
                        cave = (r.end - need) & ~0xF
                        if cave < r.start:
                            continue
                        if self.image_base and cave < self.image_base:
                            continue
                        if abs(cave - near) > LIMIT or abs(cave + need - near) > LIMIT:
                            continue
                        return r, cave, need, scope
        where = f"im Spiel-Image (ab Basis {self.image_base:#x})" if self.image_base else "im Spiel-Image"
        raise ExportError(f"Kein freier Platz fuer die Cave {where} gefunden")

    def peek(self, near, need=16):
        return self._find(need, near)[1]

    def alloc(self, need, near):
        r, cave, need, scope = self._find(need, near)
        r.end = cave
        self.last_region = (r.region[0], r.region[1], r.prot)
        if not r.tail:
            self.used_inner = True
        if r.prot & 2:
            self.used_writable = True
            if not self._warned_writable:
                self._warned_writable = True
                self.log("[cave] WARNUNG: kein Platz in nicht beschreibbaren Code-Regionen - Cave liegt in einer "
                         "beschreibbaren (rwx) Region; dort kann das Spiel Daten ablegen")
        if scope != "image":
            self.used_outside = True
            if not self._warned_outside:
                self._warned_outside = True
                self.log("[cave] WARNUNG: kein Platz im zusammenhaengenden Spiel-Image - Cave liegt ausserhalb "
                         "(ungeprueft, ggf. anderes Modul)")
        return cave, need

    def release(self, cave, need):
        """Letzte Allokation zurueckgeben (nur wenn sie noch am Luecken-Anfang liegt)."""
        for cache in (self._tail, self._inner):
            for pool in cache.values():
                for r in pool:
                    if r.end == cave:
                        r.end = cave + need
                        return


# ======================================================================
# Pruefungen
# ======================================================================
def _cave_self_writes(code, cave_addr):
    """Schreibzugriffe der Cave auf sich selbst ([rip+x] ins eigene Stueck) - die Region ist
    r-x, ein Spiel-Thread wuerde dort abstuerzen.  Nur mit Capstone pruefbar."""
    if not HAVE_CAPSTONE:
        return None
    md = _cs.Cs(_cs.CS_ARCH_X86, _cs.CS_MODE_64)
    md.detail = True
    hits = []
    for ins in md.disasm(bytes(code), cave_addr):
        for op in ins.operands:
            if op.type != _x86.X86_OP_MEM or op.mem.base != _x86.X86_REG_RIP:
                continue
            tgt = ins.address + ins.size + op.mem.disp
            if cave_addr <= tgt < cave_addr + len(code) and (op.access & _cs.CS_AC_WRITE):
                hits.append(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}")
    return hits


def _mod_name(rp):
    name = rp.name or os.path.basename(rp.path)
    base, ext = os.path.splitext(name)
    return base if ext and is_patch_file(name) else name


# ======================================================================
# Patches -> mods
# ======================================================================
def _build_simple(backend, rp, hook, target_base, warnings):
    plan = PE._plan_sites(backend, rp, hook)
    if not plan:
        raise ExportError("newValue fehlt (nichts zu patchen)")
    memory = []
    for p in plan:
        addr = p["addr"]
        new_raw = PE.asm_to_bytes(backend, p["new_asm"], addr)
        if not new_raw:
            raise ExportError(f"newValue @ {addr:#x} ergibt keine Bytes")
        try:
            default = PE.asm_to_bytes(backend, p["default_asm"], addr)
        except Exception:
            default = b""
        size = len(default) or len(new_raw)
        if len(new_raw) > size:
            raise ExportError(f"Neuer Code zu gross @ {addr:#x}: {len(new_raw)} > {size}")
        new_bytes = new_raw + b"\x90" * (size - len(new_raw))
        mem = _read(backend, addr, size)
        if mem == new_bytes:
            if not default:
                raise ExportError(f"Patch @ {addr:#x} ist gerade aktiv und hat keinen defaultValue "
                                  f"- erst deaktivieren")
            off = default
        else:
            off = mem
            if default and mem != default:
                warnings.append(f"@ {addr:#x}: Bytes im Spiel weichen von defaultValue ab "
                                f"(nehme Spiel-Bytes: {_hex(mem)})")
        if addr - target_base < 0:
            raise ExportError(f"Adresse {addr:#x} liegt unter der Basis {target_base:#x}")
        memory.append({"offset": f"{addr - target_base:X}", "on": _hex(new_bytes), "off": _hex(off)})
    return memory


def _build_cave(backend, alloc, rp, hook, target_base, warnings):
    ret_off = rp.origin_return_offset or 8
    hook_len = max(ret_off, 5)

    mem = _read(backend, hook, hook_len)
    active, _cave, _typ = PE.detect_patched(backend, rp, hook)
    if active:
        default = PE._asm_or_empty(backend, rp.origin_source[1], hook)
        if len(default) < hook_len:
            raise ExportError(f"Patch ist gerade aktiv, defaultValue fehlt oder ist zu kurz "
                              f"({len(default)} < {hook_len} Byte) - erst deaktivieren")
        original = default[:hook_len]
    else:
        original = mem

    # Groesse bestimmen (jmp-Kodierung kann von der Adresse abhaengen), dann endgueltig bauen
    trial_base = alloc.peek(hook)
    trial, _ = PE.assemble_cave(backend, rp, trial_base, hook, ret_off)
    need = len(trial)
    for _ in range(4):
        cave_addr, reserved = alloc.alloc(need, hook)
        code, src = PE.assemble_cave(backend, rp, cave_addr, hook, ret_off)
        if len(code) <= reserved:
            break
        alloc.release(cave_addr, reserved)
        need = len(code)
    else:
        raise ExportError("Cave-Groesse stabilisiert sich nicht")
    if not code:
        raise ExportError("Cave ist leer")

    cave_orig = _read(backend, cave_addr, len(code))
    if cave_orig.count(cave_orig[0]) != len(cave_orig) or cave_orig[0] not in FILL_BYTES:
        alloc.release(cave_addr, reserved)
        raise ExportError(f"Cave-Platz {cave_addr:#x} ist nicht mehr leer (Spiel hat dort Daten)")

    hook_bytes = PE.build_hook(backend, hook, cave_addr, length=hook_len)
    if hook_bytes[0] != 0xE9:
        warnings.append(f"Hook beginnt nicht mit E9 (jmp rel32): {_hex(hook_bytes[:8])}")

    writes = _cave_self_writes(code, cave_addr)
    if writes:
        warnings.append("Cave schreibt in sich selbst (Region ist r-x -> Absturz moeglich): "
                        + "; ".join(writes[:3]))
    elif writes is None:
        warnings.append("Capstone fehlt - Selbst-Schreibzugriffe der Cave nicht geprueft")

    for what, a in (("Cave", cave_addr), ("Hook", hook)):
        if a - target_base < 0:
            raise ExportError(f"{what}-Adresse {a:#x} liegt unter der Basis {target_base:#x}")

    return [
        {"offset": f"{cave_addr - target_base:X}", "on": _hex(code), "off": _hex(code)},
        {"offset": f"{hook - target_base:X}", "on": _hex(hook_bytes), "off": _hex(original)},
    ], {"cave": cave_addr, "cave_size": len(code), "hook": hook, "region": alloc.last_region}


def build_mods(backend, patches, image_base, target_base=TARGET_BASE, log=print):
    """-> (mods, report).  report: [{name, status: ok|skip|error, kind, msg, warnings}]"""
    alloc = CaveAllocator(backend, log, image_base=image_base)
    mods, report, hooks = [], [], {}
    for rp in patches:
        name = _mod_name(rp)
        rep = {"name": name, "file": os.path.basename(rp.path), "status": "ok",
               "kind": "", "msg": "", "warnings": []}
        report.append(rep)
        if not rp.origin_source:
            rep.update(status="skip", msg="keine OriginSource im Patch")
            continue
        try:
            hook = AOB.resolve_hook(backend, rp, image_base, log=log)
            if PE.is_cave_patch(rp):
                memory, info = _build_cave(backend, alloc, rp, hook, target_base, rep["warnings"])
                rep["kind"] = "Cave"
                rs, re_, rp_ = info["region"] or (0, 0, 0)
                rep["msg"] = (f"Hook {hook:#x} -> Cave {info['cave']:#x} ({info['cave_size']} Byte) "
                              f"in Region {rs:#x}-{re_:#x} ({_prot_str(rp_)})")
            else:
                memory = _build_simple(backend, rp, hook, target_base, rep["warnings"])
                rep["kind"] = "Patch"
                rep["msg"] = f"{len(memory)} Stelle(n), erste @ {hook:#x}"
        except Exception as e:
            rep.update(status="error", msg=str(e))
            continue
        if hook in hooks:
            rep["warnings"].append(f"gleiche Hook-Adresse wie '{hooks[hook]}' - nicht gleichzeitig aktivieren")
        hooks.setdefault(hook, name)
        mods.append({"name": name, "type": "checkbox", "memory": memory})
    if alloc.used_inner:
        for r in report:
            if r["kind"] == "Cave" and r["status"] == "ok":
                r["warnings"].append("Cave liegt in einer Code-Luecke statt am Segment-Ende (Fallback)")
    if alloc.used_writable:
        for r in report:
            if r["kind"] == "Cave" and r["status"] == "ok":
                r["warnings"].append("Cave liegt in einer beschreibbaren (rwx) Region (Fallback) - vor dem Einsatz pruefen")
    if alloc.used_outside:
        for r in report:
            if r["kind"] == "Cave" and r["status"] == "ok":
                r["warnings"].append("Cave liegt AUSSERHALB des zusammenhaengenden Spiel-Images (Fallback) - vor dem "
                                     "Einsatz pruefen")
    return mods, report


# ======================================================================
# JSON
# ======================================================================
def build_document(mods, game, title_id, version, process, credits):
    return {
        "name": game or title_id,
        "id": title_id,
        "version": version,
        "process": process or "eboot.bin",
        "mods": mods,
        "credits": credits or [],
    }


def validate(doc):
    """Formale Pruefung gegen das, was GoldHEN/etaHEN erwarten. -> Liste von Problemen."""
    issues = []
    if not re.fullmatch(r"[A-Z]{4}\d{5}", doc.get("id", "")):
        issues.append(f"Titel-ID '{doc.get('id')}' hat nicht das Format CUSA12345 / PPSA12345")
    if not re.fullmatch(r"\d{2}\.\d{2,3}(?:\.\d{3})?", doc.get("version", "")):
        issues.append(f"Version '{doc.get('version')}' hat nicht das Format 01.00 (PS4) bzw. 01.000.000 (PS5)")
    if not doc.get("mods"):
        issues.append("keine Mods enthalten")
    for m in doc.get("mods", []):
        if not m.get("memory"):
            issues.append(f"'{m.get('name')}': keine memory-Eintraege")
        for e in m.get("memory", []):
            on, off = e.get("on", ""), e.get("off", "")
            if len(on) != len(off):
                issues.append(f"'{m['name']}' @ {e.get('offset')}: on/off verschieden lang")
            if len(on) % 2 or not re.fullmatch(r"[0-9A-F]*", on + off):
                issues.append(f"'{m['name']}' @ {e.get('offset')}: on/off kein gueltiges Hex")
    return issues


def write_json(doc, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:      # UTF-8 ohne BOM
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")


def suggested_filename(title_id, version, fmt="json"):
    return f"{title_id}_{version}.{fmt}"


def export(backend, patches, image_base, out_path, game, title_id, version, process,
           credits=None, target_base=TARGET_BASE, log=print, fmt="json"):
    """Komplett: bauen, pruefen, schreiben.  fmt: 'json' (GoldHEN/etaHEN), 'shn' oder 'mc4'.
    -> (doc, report, issues)"""
    mods, report = build_mods(backend, patches, image_base, target_base, log)
    doc = build_document(mods, game, title_id, version, process, credits)
    issues = validate(doc) if mods else ["keine Mods exportierbar - Datei wurde NICHT geschrieben"]
    if mods:
        if fmt == "json":
            write_json(doc, out_path)
        else:
            import cheatfmt
            errors, warns = cheatfmt.check(doc, fmt)
            issues += warns
            if errors:
                issues += [f"{fmt.upper()}: {e}" for e in errors]
                issues.append(f"{fmt.upper()}-Datei wurde NICHT geschrieben")
                doc = dict(doc, mods=[])            # Aufrufer sieht: nichts geschrieben
            else:
                cheatfmt.save_file(doc, out_path, fmt)
    return doc, report, issues


# ======================================================================
# GUI (aus gui.py: ExportDialog(app))
# ======================================================================
def _gui_dialog():
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tools_common import (ACCENT, BG, BG_BAR, BG_CARD, BG_CARD_HVR, ERROR, FONT_LABEL, FONT_MONO, TEXT, TEXT_DIM, WARN)
    import library

    class ExportDialog(tk.Toplevel):
        def __init__(self, app):
            super().__init__(app.root)
            self.app = app
            self.q = queue.Queue()
            self.title("GoldHEN / etaHEN - JSON exportieren")
            self.configure(bg=BG)
            self.geometry("820x640")
            self.transient(app.root)

            pj = app.current_project or ""
            names = [rp.name for rp in app.patches.values()]
            gid = library.extract_id(pj, os.path.basename(app.PATCH_DIR or ""), *names)
            self.v_id = tk.StringVar(value=gid)
            self.v_ver = tk.StringVar(value="01.00")
            self.v_game = tk.StringVar(value=library.clean_title(pj, gid) if pj else "")
            self.v_proc = tk.StringVar(value=getattr(app.backend, "process_name", "eboot.bin"))
            self.v_base = tk.StringVar(value=hex(TARGET_BASE))
            self.v_fmt = tk.StringVar(value="json")
            authors = sorted({rp.author for rp in app.patches.values() if rp.author})
            self.v_cred = tk.StringVar(value=", ".join(authors))

            top = tk.Frame(self, bg=BG)
            top.pack(fill="x", padx=12, pady=(12, 4))
            rows = (("Titel-ID", self.v_id, 12), ("Version", self.v_ver, 8),
                    ("Prozess", self.v_proc, 14), ("Offset-Basis", self.v_base, 10))
            for i, (lab, var, w) in enumerate(rows):
                tk.Label(top, text=lab, bg=BG, fg=TEXT_DIM, font=FONT_LABEL).grid(row=0, column=i * 2, sticky="e", padx=(8, 3))
                tk.Entry(top, textvariable=var, width=w, bg=BG_CARD, fg=ACCENT, insertbackground=ACCENT,
                         relief="flat", font=FONT_MONO).grid(row=0, column=i * 2 + 1)
            row1b = tk.Frame(self, bg=BG)
            row1b.pack(fill="x", padx=12, pady=2)
            tk.Label(row1b, text="Format", bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", padx=(8, 3))
            ttk.Combobox(row1b, textvariable=self.v_fmt, values=("json", "shn", "mc4"), width=6,
                         state="readonly").pack(side="left")
            tk.Label(row1b, text="json = GoldHEN/etaHEN   shn = XML-Cheat   mc4 = verschluesseltes SHN",
                     bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", padx=8)
            tk.Button(row1b, text="TITEL-ID/VERSION VOM SPIEL", bg=BG_CARD, fg=ACCENT, font=FONT_LABEL,
                      relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
                      command=self.detect_game).pack(side="right")
            row2 = tk.Frame(self, bg=BG)
            row2.pack(fill="x", padx=12, pady=2)
            for lab, var, w in (("Spielname", self.v_game, 34), ("Credits", self.v_cred, 34)):
                tk.Label(row2, text=lab, bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", padx=(8, 3))
                tk.Entry(row2, textvariable=var, width=w, bg=BG_CARD, fg=ACCENT, insertbackground=ACCENT,
                         relief="flat", font=FONT_MONO).pack(side="left")

            tk.Label(self, text="Patches (Mehrfachauswahl, Standard: alle)", bg=BG, fg=TEXT_DIM,
                     font=FONT_LABEL).pack(anchor="w", padx=16, pady=(10, 2))
            lf = tk.Frame(self, bg=BG)
            lf.pack(fill="both", expand=False, padx=12)
            self.lb = tk.Listbox(lf, selectmode="extended", height=9, bg=BG_CARD, fg=TEXT,
                                 selectbackground=BG_CARD_HVR, selectforeground=ACCENT,
                                 font=FONT_MONO, relief="flat", exportselection=False)
            sb = ttk.Scrollbar(lf, command=self.lb.yview)
            self.lb.configure(yscrollcommand=sb.set)
            self.lb.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            self.items = sorted(app.patches.items(), key=lambda kv: kv[1].name.lower())
            for path, rp in self.items:
                tag = "Cave " if rp.origin_source and PE.is_cave_patch(rp) else "Patch"
                on = "*" if path in app.applied else " "
                self.lb.insert("end", f"{on} [{tag}] {_mod_name(rp)}")
            self.lb.select_set(0, "end")

            bar = tk.Frame(self, bg=BG)
            bar.pack(fill="x", padx=12, pady=8)
            self.btn = tk.Button(bar, text="EXPORTIEREN ...", bg=BG_CARD, fg=ACCENT, font=FONT_LABEL,
                                 relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                                 activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                                 command=self.start)
            self.btn.pack(side="left")
            tk.Button(bar, text="IMPORTIEREN (json/shn/mc4) ...", bg=BG_CARD, fg=ACCENT, font=FONT_LABEL,
                      relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                      activebackground=BG_CARD_HVR, activeforeground=ACCENT,
                      command=self.do_import).pack(side="left", padx=6)
            tk.Label(bar, text="* = aktuell aktiv (Original-Bytes kommen dann aus defaultValue)",
                     bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", padx=12)

            self.out = tk.Text(self, bg=BG_BAR, fg=TEXT, font=FONT_MONO, relief="flat", height=14,
                               wrap="word")
            self.out.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            self.out.tag_config("err", foreground=ERROR)
            self.out.tag_config("warn", foreground=WARN)
            self.out.tag_config("ok", foreground=ACCENT)
            self.after(100, self._poll)
            self._say("Spiel muss laufen und ps5debug verbunden sein. Cave-Platz und Original-Bytes "
                      "werden live aus dem Spiel gelesen.")
            if not gid and getattr(app.backend, "client", None) is not None:
                self.after(300, self.detect_game)           # Titel-ID/Version/Name automatisch eintragen
            try:
                import tools_i18n
                tools_i18n.apply_to(self)                   # EN-Modus: Beschriftungen, Knoepfe, Titel
            except Exception:
                pass

        def do_import(self):
            import gh_import
            a = self.app
            if not a.PATCH_DIR or not os.path.isdir(a.PATCH_DIR):
                return messagebox.showerror("Import", "Kein Patch-Ordner geladen.", parent=self)
            src = filedialog.askopenfilename(parent=self, title="Cheat-Datei waehlen",
                                             filetypes=[("Cheat-Dateien", "*.json *.shn *.mc4"),
                                                        ("JSON", "*.json"), ("SHN", "*.shn"),
                                                        ("MC4", "*.mc4"), ("Alle", "*.*")])
            if not src:
                return
            try:
                tb = int(self.v_base.get().strip(), 16)
                notes = []
                w, sk = gh_import.import_into(a.PATCH_DIR, src, a.IMAGE_BASE, tb, notes=notes)
            except Exception as e:
                return self._say(f"Import-FEHLER: {e}", "err")
            for n in notes:
                self._say(f"   {n}", "warn")
            self._say(f"Import: {len(w)} Patch(es) geschrieben, {len(sk)} uebersprungen (existieren schon)", "ok")
            for n in sk:
                self._say(f"   uebersprungen: {n}", "warn")
            a.load_patches()

        def detect_game(self):
            """Titel-ID, Name und Version des Vordergrund-Spiels von der Konsole holen."""
            import ps5_more
            cl = self.app.backend.client
            if cl is None:
                return self._say("Nicht verbunden.", "err")

            def work():
                try:
                    res = ps5_more.foreground_app(cl)
                except Exception as e:
                    self.q.put(("log", (f"Spiel-Erkennung fehlgeschlagen: {e}", "err")))
                    return
                self.q.put(("game", res))
            threading.Thread(target=work, daemon=True).start()

        def _got_game(self, res):
            pid, tid, name, ver = res
            if not pid or not tid:
                return self._say("Kein Spiel im Vordergrund erkannt.", "warn")
            self.v_id.set(tid)
            if ver:
                self.v_ver.set(ver)
            if name and not self.v_game.get().strip():
                self.v_game.set(name)
            self._say(f"Erkannt: {tid}  \"{name}\"  Version {ver or '?'}", "ok")

        # -- Hilfen ------------------------------------------------------
        def _say(self, msg, tag=None):
            try:
                import tools_i18n
                msg = tools_i18n.translate(msg)
            except Exception:
                pass
            self.out.insert("end", msg + "\n", tag or ())
            self.out.see("end")

        def _poll(self):
            try:
                while True:
                    kind, payload = self.q.get_nowait()
                    if kind == "log":
                        self._say(*payload)
                    elif kind == "game":
                        self._got_game(payload)
                    elif kind == "done":
                        self.btn.configure(state="normal")
            except queue.Empty:
                pass
            try:
                if self.winfo_exists():
                    self.after(100, self._poll)
            except Exception:
                pass

        def start(self):
            a = self.app
            if a.backend.client is None or a.backend.pid is None:
                messagebox.showerror("Export", "Nicht verbunden / Spiel nicht gefunden (VERBINDEN).", parent=self)
                return
            sel = [self.items[i][1] for i in self.lb.curselection()]
            if not sel:
                messagebox.showerror("Export", "Keine Patches ausgewaehlt.", parent=self)
                return
            if not self.v_id.get().strip():                 # Titel-ID fehlt: vom laufenden Spiel holen
                try:
                    import ps5_more
                    self._got_game(ps5_more.foreground_app(a.backend.client))
                except Exception:
                    pass
            tid = self.v_id.get().strip().upper()
            ver = self.v_ver.get().strip()
            try:
                tb = int(self.v_base.get().strip(), 16)
            except ValueError:
                messagebox.showerror("Export", "Offset-Basis ist keine Hex-Zahl.", parent=self)
                return
            fmt = self.v_fmt.get()
            path = filedialog.asksaveasfilename(
                parent=self, title="Cheat-Datei speichern", defaultextension="." + fmt,
                initialfile=suggested_filename(tid or "CUSAxxxxx", ver or "01.00", fmt),
                filetypes=[(fmt.upper(), "*." + fmt)])
            if not path:
                return
            creds = [c.strip() for c in self.v_cred.get().split(",") if c.strip()]
            args = (a.backend, sel, a.IMAGE_BASE, path, self.v_game.get().strip(), tid, ver,
                    self.v_proc.get().strip(), creds, tb, fmt)
            self.btn.configure(state="disabled")
            self._say(f"--- Export von {len(sel)} Patch(es) ---")
            threading.Thread(target=self._work, args=args, daemon=True).start()

        def _work(self, backend, sel, image_base, path, game, tid, ver, proc, creds, tb, fmt="json"):
            def log(m):
                return self.q.put(("log", (str(m), None)))
            try:
                doc, report, issues = export(backend, sel, image_base, path, game, tid, ver, proc,
                                             creds, tb, log=log, fmt=fmt)
                for r in report:
                    tag = {"ok": "ok", "skip": "warn", "error": "err"}[r["status"]]
                    self.q.put(("log", (f"[{r['status'].upper():5}] {r['name']}: {r['kind']} {r['msg']}", tag)))
                    for w in r["warnings"]:
                        self.q.put(("log", (f"        ! {w}", "warn")))
                for i in issues:
                    self.q.put(("log", (f"Pruefung: {i}", "warn")))
                n = len(doc["mods"])
                if n:
                    self.q.put(("log", (f"Fertig: {n} Mod(s) -> {path}", "ok")))
                    if fmt == "json":
                        self.q.put(("log", (f"Auf die Konsole kopieren: GoldHEN /user/data/GoldHEN/cheats/json/, "
                                            f"etaHEN /data/etaHEN/cheats/json/ "
                                            f"(Dateiname {suggested_filename(tid, ver)}).", None)))
                    else:
                        self.q.put(("log", (f"{fmt.upper()}: Datei in den {fmt}-Ordner deines Cheat-Menues legen, "
                                            f"Dateiname {suggested_filename(tid, ver, fmt)} (Titel-ID und "
                                            "Version muessen zum Spiel passen).", None)))
            except Exception as e:
                self.q.put(("log", (f"FEHLER: {e}", "err")))
            finally:
                self.q.put(("done", None))

    return ExportDialog


def ExportDialog(app):
    return _gui_dialog()(app)


# ======================================================================
# CLI
# ======================================================================
def _collect_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _d, files in os.walk(p):
                out += [os.path.join(root, f) for f in sorted(files) if is_patch_file(f)]
        elif os.path.isfile(p):
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="ReaperPy-Patches -> GoldHEN/etaHEN-JSON (live von der Konsole)")
    ap.add_argument("patches", nargs="+", help="Patch-Dateien oder Ordner")
    ap.add_argument("--ip", required=True)
    ap.add_argument("--port", type=int, default=744)
    ap.add_argument("--process", default="eboot.bin")
    ap.add_argument("--id", required=True, help="Titel-ID, z.B. CUSA12345 / PPSA12345")
    ap.add_argument("--version", default="01.00")
    ap.add_argument("--game", default="")
    ap.add_argument("--credits", default="")
    ap.add_argument("--image-base", default="0x400000", help="Image-Basis, auf die sich die Patch-Offsets beziehen")
    ap.add_argument("--target-base", default=hex(TARGET_BASE), help="Basis der JSON-Offsets (Standard 0x400000)")
    ap.add_argument("--format", choices=("json", "shn", "mc4"), default="json",
                    help="Ausgabeformat (Standard json = GoldHEN/etaHEN)")
    ap.add_argument("--out", help="Ausgabedatei (Standard: {id}_{version}.<format>)")
    a = ap.parse_args(argv)

    from ps5_backend import PS5Backend
    files = _collect_files(a.patches)
    patches, bad = [], 0
    for f in files:
        try:
            patches.append(ReapPatch.load(f))
        except Exception as e:
            bad += 1
            print(f"[skip] {f}: {e}")
    if not patches:
        print("Keine ladbaren Patches.")
        return 1

    be = PS5Backend(a.ip, a.port)
    be.process_name = a.process
    be.connect()
    be.find_pid(a.process)
    out = a.out or suggested_filename(a.id.upper(), a.version, a.format)
    creds = [c.strip() for c in a.credits.split(",") if c.strip()]
    doc, report, issues = export(be, patches, int(a.image_base, 16), out, a.game, a.id.upper(),
                                 a.version, a.process, creds, int(a.target_base, 16), fmt=a.format)
    for r in report:
        print(f"[{r['status'].upper():5}] {r['name']}: {r['kind']} {r['msg']}")
        for w in r["warnings"]:
            print(f"        ! {w}")
    for i in issues:
        print(f"Pruefung: {i}")
    if doc["mods"]:
        print(f"{len(doc['mods'])} Mod(s) -> {out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
