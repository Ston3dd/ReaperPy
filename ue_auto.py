"""ue_auto.py - die ganze Kette in einem Schritt: SDK + Offsets + Dump -> Kandidaten -> Instruktionen -> Patches.

Kommandozeile:
  python ue_auto.py --sdk SDK_ORDNER --offsets Offsets.json --dump Dump.bin [--dump-rva 0x0]
                    [--min-score 8] [--top 15] [--categories Leben,Munition] [--out ORDNER] [--writes-only]

Ausgabe: Bericht auf der Konsole, `ue_report.json` und (mit --out) fertige .reapproj-Dateien
(NOP-Patch je Treffer + 'kann nicht sinken'-Cave, wo sie sich bauen laesst).
"""
import argparse
import json
import mmap
import os
import re
import sys

import ue_instr as U
import uecheat
import uesdk


def load_dump(path):
    f = open(path, "rb")
    try:
        return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except Exception:
        return f.read()


def targets_for(sdk, cands):
    """Kandidaten -> ({offset: [tags]}, {offsets aller Member der Klassen})"""
    targets, class_offs = {}, set()
    for c in cands:
        targets.setdefault(c.offset, []).append(c.key)
        for m in sdk.all_members(c.cls):
            if m.offset >= 0x80:
                class_offs.add(m.offset)
    return targets, class_offs


def analyze(sdk, dump, dis, cands, base_va=0x400000, dump_rva=0, include_reads=False, progress=None):
    """-> {candidate.key: [Hit]} (nach Score sortiert)."""
    targets, class_offs = targets_for(sdk, cands)
    hits = U.scan(dump, targets, dis, class_offs, base_va=base_va, dump_rva=dump_rva,
                  include_reads=include_reads, progress=progress)
    by = {}
    for h in hits:
        for t in h.tags:
            by.setdefault(t, []).append(h)
    return by


def hit_line(h):
    i = h.ins
    extra = []
    if h.dec_hint:
        extra.append("SUB davor")
    if h.ambiguity > 12:
        extra.append(f"mehrdeutig ({h.ambiguity} Funktionen)")
    return (f"{h.score:6.1f}  RVA {h.rva:#010x}  {i.text:<44} [{h.kind}] Ko-Zugriffe={h.coaccess}"
            + (f"  ({', '.join(extra)})" if extra else ""))


def safe_name(s):
    return re.sub(r"[^\w .()+-]", "_", s).strip(" .") or "Patch"


def write_patches(out_dir, dump, dis, hits, base_va, author="ReaperPy UE-Auto", with_aob=True,
                  caves=True, log=print, code_range=None):
    """-> [dateinamen].  Je Treffer NOP-Patch (+ Cave, wenn baubar)."""
    os.makedirs(out_dir, exist_ok=True)
    written, used = [], set()

    def save(p):
        fn, k = safe_name(p["name"]) + ".reapproj", 2
        while fn.lower() in used or os.path.exists(os.path.join(out_dir, fn)):
            fn, k = f"{safe_name(p['name'])} ({k}).reapproj", k + 1
        used.add(fn.lower())
        with open(os.path.join(out_dir, fn), "w", encoding="utf-8", newline="\n") as f:
            json.dump(p, f, indent=2, ensure_ascii=False)
        written.append(fn)

    for h in hits:
        aob_text = None
        if with_aob:
            try:
                aob_text, _n = U.make_aob(dump, dis, h, base_va, code_range=code_range)
            except Exception as e:
                log(f"  AOB fuer {h.rva:#x} fehlgeschlagen: {e}")
            if not aob_text:
                log(f"  {h.rva:#x}: keine eindeutige Signatur im Dump - Patch nutzt feste Adresse")
        save(U.nop_patch(dump, h, aob_text, author=author))
        if caves:
            ok, why = U.can_cave(h)
            if ok:
                save(U.keep_cave_patch(dump, h, aob_text, author=author))
            else:
                log(f"  {h.rva:#x}: keine Cave ({why})")
    return written


def report_dict(cands, by, limit=8):
    out = []
    for c in cands:
        hs = by.get(c.key, [])[:limit]
        out.append({"candidate": c.key, "category": c.category, "score": c.score, "offset": hex(c.offset),
                    "type": c.type, "reasons": c.reasons,
                    "hits": [{"rva": hex(h.rva), "insn": h.ins.text, "kind": h.kind, "score": h.score,
                              "coaccess": h.coaccess, "dec_hint": h.dec_hint, "ambiguity": h.ambiguity}
                             for h in hs]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="UE-SDK + Dump -> Cheat-Instruktionen + Patches")
    ap.add_argument("--game", help="Spielordner (findet offsets.json, dump.json/bin, SDK_HEADERS, GObjects automatisch)")
    ap.add_argument("--native", choices=("auto", "rva", "va"), default="auto",
                    help="sind 'native 0x..' im Header RVAs oder virtuelle Adressen?")
    ap.add_argument("--functions", type=int, default=0, help="N Funktions-Ziele mit Adresse und Implementierung ausgeben")
    ap.add_argument("--func-patch", action="append", default=[],
                    help="Klasse.Funktion:modus (ret|false|true|one|float0) - schreibt einen Funktions-Patch")
    ap.add_argument("--check-objects", action="store_true",
                    help="GObjects/GNames offline aus dem Dump pruefen und Diagnose ausgeben")
    ap.add_argument("--sdk"), ap.add_argument("--offsets"), ap.add_argument("--gobjects")
    ap.add_argument("--dump")
    ap.add_argument("--dump-rva", default="0x0", help="RVA, die Position 0 der Dump-Datei entspricht")
    ap.add_argument("--base", default="0x400000", help="Modul-Basisadresse (nur fuer Anzeige/Disasm)")
    ap.add_argument("--min-score", type=float, default=8.0)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--categories", default="", help="Komma-getrennt, z.B. Leben,Munition,Währung")
    ap.add_argument("--writes-only", action="store_true", default=True)
    ap.add_argument("--with-reads", action="store_true")
    ap.add_argument("--out", help="Ordner fuer .reapproj-Patches")
    ap.add_argument("--patches-per-candidate", type=int, default=2)
    ap.add_argument("--disasm", choices=("capstone", "objdump"))
    a = ap.parse_args(argv)
    if a.game:
        return main_game(a)
    if not a.dump:
        ap.error("--dump oder --game angeben")

    sdk = uesdk.load(a.sdk, a.offsets, a.gobjects)
    print(f"SDK: {sdk.stats['classes']} Klassen, {sdk.stats['members']} Member, {len(sdk.offsets)} Offsets")
    cands = uecheat.find_candidates(sdk, a.min_score)
    if a.categories:
        want = {c.strip() for c in a.categories.split(",")}
        cands = [c for c in cands if c.category in want]
    cands = cands[:a.top]
    if not cands:
        print("Keine Kandidaten - --min-score senken oder SDK-Pfad pruefen.")
        return 1
    dump = load_dump(a.dump)
    dis = U.get_disasm(a.disasm)
    base, rva = int(a.base, 0), int(a.dump_rva, 0)
    print(f"Dump {len(dump):,} Byte, Disassembler: {dis.name}")
    by = analyze(sdk, dump, dis, cands, base, rva, a.with_reads,
                 progress=lambda d, t: print(f"\r  Byte-Treffer {d}/{t}", end="", file=sys.stderr))
    chosen = []
    for c in cands:
        print(f"\n[{c.category}] {c.key}  @ {c.offset:#x} ({c.type})  Score {c.score:.1f}")
        hs = by.get(c.key, [])
        if not hs:
            print("   keine schreibende Instruktion gefunden")
        for h in hs[:6]:
            print("   " + hit_line(h))
        chosen += hs[:a.patches_per_candidate]
    with open("ue_report.json", "w", encoding="utf-8") as f:
        json.dump(report_dict(cands, by), f, indent=2, ensure_ascii=False)
    print("\nBericht: ue_report.json")
    if a.out and chosen:
        files = write_patches(a.out, dump, dis, chosen, base)
        print(f"{len(files)} Patch-Datei(en) nach {a.out}")
    return 0


def check_objects(proj, out=print):
    """Objekt-Erkennung offline pruefen (GObjects/GNames aus dump.bin)."""
    import collections
    import ue_live
    if not proj.dm:
        out("kein dump.bin/dump.json gefunden - Pruefung nicht moeglich. Gefunden wurde:")
        for k, v in proj.files.items():
            out(f"   {k:10} {v or 'FEHLT'}")
        out("Tipp: den Spiel-Ordner angeben (dort, wo dump.bin liegt), nicht nur den SDK-Unterordner.")
        return 1
    e = proj.engine or {}
    out(f"Basis (offsets.json): {proj.base:#x}   engine.json: arr={e.get('arr')} pool={e.get('pool')} layout={e.get('layout')}")
    lv = ue_live.UELive(proj.dm.read, proj.base, proj.sdk, log=out)
    try:
        rep = lv.setup([proj.base], **proj.live_args())
    except ue_live.UELiveError as ex:
        out(str(ex))
        out("-> Diagnose bitte weitergeben (mit den ersten Zeilen von offsets.json und dump.bin.engine.json).")
        return 2
    out(f"OK: GObjects @{rep['array']:#x}, {rep['count']} Objekte, Item {rep['item_size']:#x}, Name-Pool @{rep['name_blocks']:#x}")
    out(f"Name-Pool-Format: {lv.name_style.upper()}   - lese Objekt-Koepfe ...")
    idx = lv.build_index(lambda d, t: print(f"\r  {d}/{t}", end="", file=sys.stderr))
    print(file=sys.stderr)
    classes = collections.Counter(idx[idx[p][1]][2] for p in idx if idx[p][1] in idx)
    out(f"{len(idx)} Objekte lesbar; haeufigste Typen: " + ", ".join(f"{k} ({v})" for k, v in classes.most_common(6)))
    return 0


def main_game(a):
    """--game: alles aus einem Spielordner."""
    import ue_project
    proj = ue_project.GameProject(a.game, native=a.native).load()
    f = proj.files
    print(f"Spiel {proj.title or '?'}  Basis {proj.base:#x}")
    print("  gefunden: " + ", ".join(f"{k}={'ja' if v else 'NEIN'}" for k, v in f.items()))
    st = proj.sdk.stats
    print(f"  SDK: {st['classes']} Klassen, {st['members']} Member, {sum(len(c.funcs) for c in proj.sdk.classes.values())} Funktionen")
    if proj.native_info:
        m, r, v = proj.native_info
        print(f"  native-Adressen: {m.upper()}" + (f" (Treffer RVA {r:.0%} / VA {v:.0%})" if r is not None else " (vorgegeben)"))
    if a.check_objects:
        return check_objects(proj)
    cats = {c.strip() for c in a.categories.split(",")} if a.categories else None
    cands = proj.candidates(a.min_score, cats, a.top)
    if not cands:
        print("Keine Kandidaten - --min-score senken.")
        return 1
    by = {}
    chosen = []
    if proj.dm:
        by = proj.analyze(cands, a.with_reads,
                          progress=lambda d, t: print(f"\r  Byte-Treffer {d}/{t}", end="", file=sys.stderr))
    for c in cands:
        print(f"\n[{c.category}] {c.key}  @ {c.offset:#x} ({c.type})  Score {c.score:.1f}")
        for r in c.reasons[:3]:
            print(f"     - {r}")
        hs = by.get(c.key, [])
        if proj.dm and not hs:
            print("   keine schreibende Instruktion gefunden (Schalter/Daten werden evtl. nur per Live-Wert gesetzt)")
        for h in hs[:5]:
            print("   " + hit_line(h))
        chosen += hs[:a.patches_per_candidate]
    fnl = proj.functions()
    if a.functions:
        print("\n=== Funktions-Ziele ===")
        for d in fnl[:a.functions]:
            rv = proj.native_rva(d["native"]) if d["native"] else None
            line = f"{d['score']:4.1f}  {d['cls']}.{d['name']:<34} native RVA {rv:#x}" if rv is not None else \
                   f"{d['score']:4.1f}  {d['cls']}.{d['name']:<34} (keine Adresse)"
            if d["shared"]:
                line += "  [geteilter Stub - nicht patchbar]"
            elif proj.dm and d["native"]:
                try:
                    impl = proj.resolve_impl(d)
                    if impl:
                        line += f"  -> Impl RVA {impl[0] - proj.base:#x}"
                except Exception:
                    pass
            print(line)
    json_out = {"title": proj.title, "candidates": report_dict(cands, by), "functions": [
        {k: (hex(v) if k in ("native", "flags") and v is not None else v) for k, v in d.items()} for d in fnl[:300]]}
    with open("ue_report.json", "w", encoding="utf-8") as fh:
        json.dump(json_out, fh, indent=2, ensure_ascii=False)
    print("\nBericht: ue_report.json")
    wrote = []
    if a.out and chosen:
        cv = proj.code()
        wrote += write_patches(a.out, cv["buf"], proj.dis, chosen, cv["base_va"], code_range=cv["range"])
    if a.func_patch:
        if not a.out:
            print("--func-patch braucht --out"); return 1
        os.makedirs(a.out, exist_ok=True)
        idx = {(d["cls"], d["name"]): d for d in fnl}
        idx.update({(d["cls"].lstrip("UAF"), d["name"]): d for d in fnl})
        for spec in a.func_patch:
            try:
                nm, mode = spec.rsplit(":", 1)
                cls, fn = nm.rsplit(".", 1)
                d = idx.get((cls, fn)) or idx.get((cls.lstrip("UAF"), fn))
                if not d or not d["native"]:
                    raise KeyError(f"{nm} nicht gefunden/keine Adresse")
                if d["shared"]:
                    raise KeyError(f"{nm}: geteilter Stub")
                impl = proj.resolve_impl(d)
                if not impl:
                    raise KeyError(f"{nm}: keine Implementierung hinter dem Thunk gefunden")
                p = proj.function_patch(impl[0], mode, nm)
                fnm = os.path.join(a.out, safe_name(p["name"]) + ".reapproj")
                with open(fnm, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(p, fh, indent=2, ensure_ascii=False)
                wrote.append(os.path.basename(fnm))
            except Exception as e:
                print(f"  --func-patch {spec}: {e}")
    if wrote:
        print(f"{len(wrote)} Patch-Datei(en) nach {a.out}")
    proj.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
