"""dumpmem.py - Prozess-Dump (dump.bin + dump.json) als lesbarer Speicher.

dump.json beschreibt, welche Speicherregionen (Start/Ende/Schutz/Datei-Offset) in dump.bin liegen.
Damit lassen sich virtuelle Adressen offline lesen (Objekte, Namen, Code) und der Code-Bereich des
Spiels (eboot) fuer die Instruktionssuche herausloesen.  Die Datei kann mehrere GB gross sein ->
mmap, nie komplett laden.
"""

import bisect
import json
import mmap
import os


class DumpMemory:
    def __init__(self, bin_path, json_path=None, regions=None, module_base=None):
        self.bin_path = bin_path
        meta = {}
        if regions is None:
            with open(json_path, encoding="utf-8-sig") as handle:
                meta = json.load(handle)
            regions = meta.get("regions", [])
        self.meta = {k: value for k, value in meta.items() if k != "regions"}
        self.regions = sorted(
            (
                {
                    "name": region.get("name", ""),
                    "start": region["start"],
                    "end": region["end"],
                    "prot": region.get("prot", 0),
                    "offset": region["offset"],
                }
                for region in regions
            ),
            key=lambda r: r["start"],
        )
        self._starts = [region["start"] for region in self.regions]
        self.f = open(bin_path, "rb")
        try:
            self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        except (ValueError, OSError):
            self.mm = self.f.read()
        main = next((region for region in self.regions if region["prot"] & 4), None)
        if main is None and module_base is not None:  # kein Exec-Bereich: Region an der Modulbasis
            main = next((region for region in self.regions if region["start"] <= module_base < region["end"]), None)
        self.module_name = main["name"] if main else ""
        self.base = module_base if module_base is not None else (main["start"] if main else 0)

    def close(self):
        try:
            if hasattr(self.mm, "close"):
                self.mm.close()
            self.f.close()
        except Exception:
            pass

    def region_of(self, va):
        i = bisect.bisect_right(self._starts, va) - 1
        if i >= 0 and va < self.regions[i]["end"]:
            return self.regions[i]
        return None

    def va_to_off(self, va):
        region = self.region_of(va)
        return None if region is None else region["offset"] + (va - region["start"])

    def read(self, va, n):
        """n Byte ab virtueller Adresse; ueber Regionsgrenzen nur, wenn die Regionen luckenlos folgen."""
        out = bytearray()
        while n > 0:
            region = self.region_of(va)
            if region is None:
                raise OSError(f"Adresse {va:#x} nicht im Dump")
            take = min(n, region["end"] - va)
            offset = region["offset"] + (va - region["start"])
            chunk = self.mm[offset : offset + take]
            if len(chunk) < take:
                raise OSError(f"Dump zu kurz bei {va:#x}")
            out += chunk
            va += take
            n -= take
        return bytes(out)

    def code_regions(self):
        """Ausfuehrbare Regionen des Hauptmoduls (eboot) -> [region]."""
        return [region for region in self.regions if region["prot"] & 4 and region["name"] == self.module_name]

    def code_view(self):
        """Groesster Code-Bereich -> (buf, lo, hi, base_va).  `buf` ist der mmap der ganzen Datei;
        Position p im Bereich [lo, hi) entspricht der Adresse base_va + p."""
        rs = self.code_regions()
        if not rs:
            raise ValueError("kein ausfuehrbarer Bereich im Dump")
        region = max(rs, key=lambda x: x["end"] - x["start"])
        return (
            self.mm,
            region["offset"],
            region["offset"] + (region["end"] - region["start"]),
            region["start"] - region["offset"],
        )


def native_convention(dump, addrs, module_base, sample=400):
    """Sind die 'native 0x...'-Adressen aus den Headern RVAs oder virtuelle Adressen?
    Test: Funktionsanfaenge liegen auf 16-Byte-Grenzen hinter CC/C3-Auffuellung.
    -> ('rva'|'va', trefferquote_rva, trefferquote_va)"""
    buf, lo, hi, base_va = dump.code_view() if hasattr(dump, "code_view") else dump
    addrs = sorted({addr for addr in addrs if addr})[:: max(1, len(set(addrs)) // sample or 1)][:sample]

    def good(va):
        pos = va - base_va
        if not (lo + 1 <= pos < hi) or va % 16:
            return False
        prev = buf[pos - 1]
        return buf[pos] != 0xCC and prev in (0xCC, 0xC3, 0x90)

    n = max(1, len(addrs))
    rva_score = sum(good(addr + module_base) for addr in addrs) / n
    va_score = sum(good(addr) for addr in addrs) / n
    return ("rva" if rva_score >= va_score else "va"), rva_score, va_score


def find_game_files(folder):
    """Ordner eines Spiels (oder dessen Eltern) -> gefundene Dateien.  Erkennt die Struktur:
    offsets.json, dump.json, dump.bin, dump.bin.engine.json, GObjects.txt, [SDK/]SDK_HEADERS/*"""
    found = {"sdk": None, "offsets": None, "dump_json": None, "dump_bin": None, "gobjects": None, "engine": None}
    best_sdk = (0, None)
    for root, dirs, files in os.walk(folder):
        depth = root[len(folder) :].count(os.sep)
        if depth > 5:
            dirs[:] = []
            continue
        low = {file.lower(): file for file in files}
        n_cls = sum(1 for file in files if file.lower().endswith(("_classes.hpp", "_structs.hpp")))
        if n_cls > best_sdk[0]:
            best_sdk = (n_cls, root)
        for key, name in (
            ("offsets", "offsets.json"),
            ("dump_json", "dump.json"),
            ("gobjects", "gobjects.txt"),
            ("engine", "dump.bin.engine.json"),
        ):
            if name in low and not found[key]:
                found[key] = os.path.join(root, low[name])
        if not found["dump_bin"]:
            if "dump.bin" in low:
                found["dump_bin"] = os.path.join(root, low["dump.bin"])
            else:
                bins = [os.path.join(root, file) for file in files if file.lower().endswith(".bin")]
                if bins:
                    found["dump_bin"] = max(bins, key=os.path.getsize)
    found["sdk"] = best_sdk[1]
    # Fehlendes auch in den Eltern-Ordnern suchen (z.B. wenn nur der SDK-Unterordner gewaehlt wurde)
    parent = os.path.abspath(folder)
    for _ in range(3):
        parent = os.path.dirname(parent)
        if not parent or not os.path.isdir(parent):
            break
        for key, name in (
            ("offsets", "offsets.json"),
            ("dump_json", "dump.json"),
            ("gobjects", "gobjects.txt"),
            ("engine", "dump.bin.engine.json"),
            ("dump_bin", "dump.bin"),
        ):
            if found[key]:
                continue
            for base in (parent, os.path.join(parent, "SDK")):
                try:
                    names = {f.lower(): f for f in os.listdir(base)}
                except OSError:
                    continue
                if name in names:
                    found[key] = os.path.join(base, names[name])
                    break
    # ps4-unreal-dumper legt die Offsets als GameDefines.hpp ab (#define GObjects_Offset ...) statt offsets.json
    if not found["offsets"]:
        search = [folder] + [os.path.dirname(os.path.abspath(folder))] * 0
        parent = os.path.abspath(folder)
        for _ in range(4):
            search.append(parent)
            parent = os.path.dirname(parent)
        for base in search:
            for sub in ("", "SDK"):
                try:
                    names = {f.lower(): f for f in os.listdir(os.path.join(base, sub))}
                except OSError:
                    continue
                if "gamedefines.hpp" in names:
                    found["offsets"] = os.path.join(base, sub, names["gamedefines.hpp"])
                    break
            if found["offsets"]:
                break
        if not found["offsets"]:
            for root, _dirs, files in os.walk(folder):
                if root[len(folder):].count(os.sep) > 5:
                    continue
                hit = [f for f in files if f.lower() == "gamedefines.hpp"]
                if hit:
                    found["offsets"] = os.path.join(root, hit[0])
                    break
    return found
