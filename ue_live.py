"""ue_live.py - liest die Unreal-Objektwelt (GObjects / GNames) live aus dem laufenden Spiel.

Damit werden aus SDK-Namen echte Adressen: Instanzen einer Klasse (z.B. HealthComponent), deren
Member-Adressen (Instanz + Offset) und die Einstiegsadresse nativer UFunctions (ExecFunction).

Unterstuetzt: UE 4.23+ / UE5 (FNamePool, FChunkedFixedUObjectArray).  Aeltere Engines (TNameEntryArray)
werden NICHT unterstuetzt.  Alle Layout-Werte kommen aus dem SDK (UObject/UStruct/UFunction-Member),
sonst aus typischen Standardwerten; Array-Layout und Name-Pool werden gegen den Speicher geprueft.
"""

import struct

BLOCK = 0x10000  # Objekte je Chunk
READ_BLOCK = 0x10000  # Cache-Blockgroesse beim Lesen


class UELiveError(RuntimeError):
    pass


def _u32(b, o=0):
    return struct.unpack_from("<I", b, o)[0]


def _u64(b, o=0):
    return struct.unpack_from("<Q", b, o)[0]


def _valid_ptr(p):
    return 0x10000 <= p < 0x800000000000


class UELive:
    def __init__(self, read, module_base, sdk=None, gobjects_rva=None, gnames_rva=None, log=print):
        self._read = read
        self.base = module_base
        self.sdk = sdk
        self.log = log
        off = (lambda *n, default=None: sdk.offset(*n, default=default)) if sdk else (lambda *n, default=None: default)
        self.gobjects_rva = gobjects_rva if gobjects_rva is not None else off("gobjects")
        self.gnames_rva = gnames_rva if gnames_rva is not None else off("gnames")

        # Objekt-Layout: erst offsets.json (UObject_Class ...), dann SDK-Member, dann Standardwerte
        def pick_offset(key, cls, names, default):
            return sdk.offset(key) if sdk and sdk.offset(key) is not None else self._sdk_off(cls, names, default)

        self.o_class = pick_offset("UObject_Class", "UObject", ("Class", "ClassPrivate"), 0x10)
        self.o_name = pick_offset("UObject_Name", "UObject", ("Name", "NamePrivate"), 0x18)
        self.o_outer = pick_offset("UObject_Outer", "UObject", ("Outer", "OuterPrivate"), 0x20)
        self.o_super = pick_offset("UStruct_SuperStruct", "UStruct", ("SuperStruct",), 0x40)
        self.o_exec = pick_offset("UFunction_ExecFunction", "UFunction", ("ExecFunction", "Func"), None)
        self.hint_item_size = sdk.offset("fuobjectitem_size", "fuobjectitemsize") if sdk else None
        self.name_style = "ue5"
        self.none_index = 0
        self.layout = [0, 16, 20, 24, 28]  # Offsets: Objects, MaxElements, NumElements, MaxChunks, NumChunks
        self.diag = []
        self.item_size = None
        self.arr = None  # Adresse der FChunkedFixedUObjectArray
        self.pool_blocks = None  # Adresse des Block-Zeigerfeldes im FNamePool
        self.names_cache = {}
        self._pages = {}
        self.index = None  # {addr: (class_ptr, name)} nach build_index
        self._anc_cache = {}
        self.live_found = None

    def rd(self, addr, n):
        if addr < 0 or addr + n > 0xFFFFFFFFFFFFFFFF:
            raise OSError(f"ungueltige Adresse {addr:#x}")
        if n > READ_BLOCK:
            return bytes(self._read(addr, n))
        end = addr + n
        out = bytearray()
        a = addr
        while a < end:
            block = a & ~(READ_BLOCK - 1)
            page = self._pages.get(block)
            if page is None:
                try:
                    page = bytes(self._read(block, READ_BLOCK))
                except Exception:
                    page = False  # Block nicht komplett lesbar -> direkt lesen
                if len(self._pages) > 512:
                    self._pages.clear()
                self._pages[block] = page
            if page is False:
                return bytes(self._read(addr, n))
            take = min(end, block + READ_BLOCK) - a
            out += page[a - block : a - block + take]
            a += take
        return bytes(out)

    def drop_cache(self):
        self._pages.clear()
        self.__dict__.pop("_mo_cache", None)
        self._anc_cache = {}
        self.index = None

    def _sdk_off(self, cls, names, default):
        if self.sdk:
            for n in names:
                member = self.sdk.find_member(cls, n)
                if member:
                    return member.offset
        return default

    def setup(self, bases=None, abs_gobjects=None, abs_gnames=None, layout=None, maps=None):
        """GObjects und GNames pruefen/erkennen.  Probiert nacheinander mehrere Modulbasen (Dump-Basis,
        Basis des laufenden Prozesses, Projektbasis) und optional die absoluten Adressen aus
        dump.bin.engine.json.  Bei Misserfolg steht in der Fehlermeldung, was jeweils gelesen wurde."""
        self.diag = []
        if layout:
            self.layout = list(layout)
        pairs = []
        for base in dict.fromkeys(bases or [self.base]):
            if self.gobjects_rva is not None and self.gnames_rva is not None:
                pairs.append((base, base + self.gobjects_rva, base + self.gnames_rva, f"Basis {base:#x} + RVA"))
        if (
            self.gobjects_rva is not None
            and self.gnames_rva is not None
            and min(self.gobjects_rva, self.gnames_rva) >= 0x400000
        ):
            pairs.append(
                (self.base, self.gobjects_rva, self.gnames_rva, "Werte aus offsets.json als absolute Adressen")
            )
        if abs_gobjects and abs_gnames:
            base = self.base
            pairs.append((base, abs_gobjects, abs_gnames, "absolute Adressen (dump.bin.engine.json)"))
        if not pairs and not maps:
            raise UELiveError("GObjects/GNames-Offset fehlen (offsets.json oder engine.json)")
        for base, gobjects, gnames, why in pairs:
            self.diag.append(f"-- Versuch: {why}")
            if not self._detect_objects(gobjects):
                continue
            if not self._detect_names(gnames):
                continue
            self.base = base
            none = self.fname_str(self.none_index)
            if none != "None":
                self.diag.append(f"   FName {self.none_index} ist '{none}' statt 'None' - Name-Pool-Layout passt nicht")
                continue
            return {
                "array": self.arr,
                "item_size": self.item_size,
                "name_blocks": self.pool_blocks,
                "count": self.num_elements,
                "base": base,
            }
        if maps:  # nichts aus Datei passte (oder gar keine Offsets) -> bei jedem Start live suchen
            found = self.auto_find(maps, bases)
            if found:
                return found
        raise UELiveError("GObjects/GNames nicht erkannt:\n" + "\n".join(self.diag))

    # ---- Live-Suche: GObjects/GNames ohne offsets.json -------------------------------------------------------
    def auto_find(self, maps, bases=None, max_mb=384):
        """Sucht FChunkedFixedUObjectArray (GObjects) und FNamePool (GNames) im beschreibbaren Datenbereich des
        Hauptmoduls und prueft jeden Treffer gegen den Speicher.  -> Info-Dict wie setup() oder None."""
        cand_bases = [b for b in dict.fromkeys(bases or [self.base]) if b]
        mod = live_module_base(maps)
        if mod:
            cand_bases.append(mod)
        lo = min(cand_bases) if cand_bases else 0x400000
        regions = sorted((m[0], m[1]) for m in maps if (m[2] & 3) == 3 and m[0] >= lo and m[0] < lo + 0x40000000)
        self.diag.append(f"-- Live-Suche in {len(regions)} beschreibbaren Modul-Bereichen ab {lo:#x}")
        o_mx, o_num, o_maxc, o_numc = (o // 4 for o in self.layout[1:5])
        arr_hits, pool_hits, scanned = [], [], 0
        step = 0x100000
        for start, end in regions:
            a = start
            while a < end and scanned < max_mb * 0x100000:
                n = min(step + 0x80, end - a)
                try:
                    raw = bytes(self._read(a, n))
                except Exception:
                    a += step
                    continue
                scanned += n
                last = a + n >= end
                usable = len(raw) // 8 * 8 if (last or len(raw) <= 0x100) else (len(raw) - 0x80) // 8 * 8
                ints = memoryview(raw[: len(raw) // 4 * 4]).cast("i")
                quads = memoryview(raw[: len(raw) // 8 * 8]).cast("Q")
                top = usable // 8
                for k in range(top):
                    # GObjects: Zeiger, MaxElements == MaxChunks * 65536, NumElements <= Max, NumChunks*65536 >= Num
                    i = k * 2
                    if i + max(o_mx, o_num, o_maxc, o_numc) >= len(ints):
                        break
                    mx = ints[i + o_mx]
                    if mx > 0 and ints[i + o_maxc] * BLOCK == mx:
                        num, numc = ints[i + o_num], ints[i + o_numc]
                        if 100 <= num <= mx and 1 <= numc <= ints[i + o_maxc] and numc * BLOCK >= num:
                            if _valid_ptr(quads[k + self.layout[0] // 8]):
                                arr_hits.append(a + k * 8)
                    # FNamePool: Lock(8) | CurrentBlock | CurrentByteCursor | Blocks[] ab +0x10
                    cb, cur = ints[i + 2] if i + 3 < len(ints) else -1, ints[i + 3] if i + 3 < len(ints) else -1
                    if 0 <= cb <= 2048 and 0 <= cur <= 0x20000 and cur % 2 == 0 and k + 3 + cb < len(quads):
                        # Blocks[0..cb] sind Zeiger, danach kommt ein Nullzeiger (noch nicht angelegter Block)
                        if _valid_ptr(quads[k + 2]) and quads[k + 3 + cb] == 0 and (cb == 0 or _valid_ptr(quads[k + 2 + cb])):
                            pool_hits.append(a + k * 8)
                a += step
        self.diag.append(f"   {scanned // 0x100000} MB durchsucht, {len(arr_hits)} GObjects- und {len(pool_hits)} GNames-Kandidaten")
        arr_ok = next((x for x in arr_hits if self._detect_objects(x)), None)
        if arr_ok is None:
            return None
        pool_ok = None
        for x in pool_hits[:4000]:
            if self._detect_names(x):
                none = self.fname_str(self.none_index)
                if none == "None":
                    pool_ok = x
                    break
        if pool_ok is None:
            self.diag.append("   GObjects gefunden, aber kein FNamePool mit 'None'-Eintrag")
            return None
        base = next((b for b in sorted(cand_bases) if b <= arr_ok), lo)
        self.base = base
        self.live_found = {"gobjects": arr_ok, "gnames": pool_ok, "gobjects_rva": arr_ok - base, "gnames_rva": pool_ok - base}
        self.diag.append(
            f"   LIVE gefunden: GObjects {arr_ok:#x} (RVA {arr_ok - base:#x}), GNames {pool_ok:#x} (RVA {pool_ok - base:#x})"
        )
        self.log(f"UE-LIVE: GObjects {arr_ok:#x} / GNames {pool_ok:#x} live gefunden (RVA {arr_ok - base:#x} / {pool_ok - base:#x})")
        return {"array": self.arr, "item_size": self.item_size, "name_blocks": self.pool_blocks,
                "count": self.num_elements, "base": base}

    # ---- Live-Offsets: Member-Offsets aus den Reflection-Daten des laufenden Spiels --------------------------
    def _plo(self, key, default):
        v = self.sdk.offset(key) if self.sdk else None
        return v if v is not None else default

    def member_offset(self, sdk_class, member):
        """Offset eines Members, direkt aus der FProperty-Kette der UClass im Spiel gelesen (statt aus den Headern).
        Sucht auch in den Eltern.  -> int oder None (Klasse/Member nicht gefunden)."""
        cache = self.__dict__.setdefault("_mo_cache", {})
        key = (sdk_class, member)
        if key in cache:
            return cache[key]
        o_children = self._plo("UStruct_ChildProperties", 0x50)
        o_next = self._plo("FField_Next", 0x18)
        o_name = self._plo("FField_Name", 0x20)
        o_off = self._plo("Property_Offset_Internal", 0x44)
        result = None
        cls = self.find_class(sdk_class)
        for c in self.class_chain(cls) if cls else []:
            try:
                f = _u64(self.rd(c + o_children, 8))
                for _ in range(8192):
                    if not _valid_ptr(f):
                        break
                    raw = self.rd(f + o_name, 8)
                    if self.fname_str(_u32(raw, 0), _u32(raw, 4)) == member:
                        off = struct.unpack_from("<i", self.rd(f + o_off, 4))[0]
                        if 0 <= off < 0x1000000:
                            result = off
                        break
                    f = _u64(self.rd(f + o_next, 8))
            except Exception:
                pass
            if result is not None:
                break
        cache[key] = result
        return result

    def _try_array(self, a):
        """-> (objs, num) oder (None, grund)"""
        try:
            hdr = self.rd(a, 0x20)
        except Exception as error:
            return None, f"Lesefehler: {error}"
        if len(hdr) < 0x20:
            return None, f"nur {len(hdr)} Byte gelesen"
        layout = self.layout
        objs = _u64(hdr, layout[0])
        mx, num, maxc, numc = (struct.unpack_from("<i", hdr, o)[0] for o in layout[1:5])
        info = f"objs={objs:#x} max={mx} num={num} chunks={numc}/{maxc}"
        if not _valid_ptr(objs):
            return None, f"{info} -> Objects-Zeiger ungueltig"
        if not (100 <= num <= 8_000_000 and mx >= num):
            return None, f"{info} -> Elementzahl unplausibel"
        if not (1 <= numc <= 512 and numc * BLOCK >= num):
            return None, f"{info} -> Chunkzahl passt nicht zur Elementzahl"
        try:
            chunk0 = _u64(self.rd(objs, 8))
        except Exception as error:
            return None, f"{info} -> Chunk-Tabelle nicht lesbar: {error}"
        if not _valid_ptr(chunk0):
            return None, f"{info} -> Chunk 0 ungueltig ({chunk0:#x})"
        return (objs, num), info

    def _detect_objects(self, addr):
        for delta in (0, 0x10, 0x8, 0x18):  # Array direkt oder in FUObjectArray
            r, info = self._try_array(addr + delta)
            if not r:
                self.diag.append(f"   GObjects @{addr + delta:#x}: {info}")
                continue
            objs, num = r
            chunk0 = _u64(self.rd(objs, 8))
            # offsets.json nennt manchmal 20 (Rohgroesse ohne Alignment), echt sind meist 24: alle Kandidaten
            # gegen die ersten 32 Eintraege pruefen und den mit den meisten gueltigen Objekten nehmen.
            sizes = [x for x in dict.fromkeys((self.hint_item_size, 0x18, 0x10, 0x20, 0x14, 0x28)) if x]
            best = (0, None)
            for size in sizes:
                ok = 0
                try:
                    raw = self.rd(chunk0, size * 32)
                except Exception as error:
                    self.diag.append(f"   GObjects @{addr + delta:#x}: Chunk 0 nicht lesbar: {error}")
                    break
                for i in range(32):
                    ptr = _u64(raw, i * size)
                    if ptr and _valid_ptr(ptr):
                        try:
                            if _valid_ptr(_u64(self.rd(ptr + self.o_class, 8))):
                                ok += 1
                        except Exception:
                            pass
                self.diag.append(f"   GObjects @{addr + delta:#x}: Item {size:#x}: {ok}/32 Objekte mit gueltiger Klasse")
                if ok > best[0]:
                    best = (ok, size)
            if best[1] and best[0] >= 8:
                size = best[1]
                self.arr, self.item_size, self.num_elements, self._objs = addr + delta, size, num, objs
                self.diag.append(f"   GObjects @{addr + delta:#x}: ok ({num} Objekte, Item {size:#x})")
                return True
        return False

    @staticmethod
    def _none_style(head):
        """Header des Eintrags 0 ("None", Laenge 4) -> 'ue5' (Len = hdr>>6) | 'ue4' (Len = hdr>>1) | None"""
        if len(head) < 6 or head[2:6] != b"None":
            return None
        hdr = struct.unpack_from("<H", head)[0]
        if (hdr >> 6) == 4 and not hdr & 1:
            return "ue5"
        if (hdr >> 1) == 4 and not hdr & 1:
            return "ue4"
        return None

    def _detect_names(self, addr):
        seen = []
        for blocks_off in (0x10, 0x8, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40, 0x50):
            try:
                first_block = _u64(self.rd(addr + blocks_off, 8))
                if not _valid_ptr(first_block):
                    continue
                head = self.rd(first_block, 8)
            except Exception as error:
                seen.append(f"+{blocks_off:#x}: Block 0 nicht lesbar ({error})")
                continue
            style, none_at = self._none_style(head), 0
            if not style:  # "None" liegt evtl. nicht ganz am Blockanfang
                try:
                    wide = self.rd(first_block, 64)
                except Exception:
                    wide = b""
                k = wide.find(b"None")
                if 2 <= k <= 60:
                    style = self._none_style(wide[k - 2 : k + 6])
                    none_at = (k - 2) // 2 if style else 0
            if style:
                self.none_index = none_at
                self.pool_blocks, self.name_style = addr + blocks_off, style
                self.diag.append(f"   GNames @{addr:#x}: ok (Blocks +{blocks_off:#x}, Eintragsformat {style})")
                return True
            seen.append(f"+{blocks_off:#x}: Blocks[0]={first_block:#x} Kopf {head.hex(' ')}")
        for line in seen[:4]:
            self.diag.append(f"   GNames @{addr:#x} {line}")
        try:
            first = self.rd(addr, 0x58).hex(" ")[:96]
        except Exception as error:
            first = f"nicht lesbar: {error}"
        self.diag.append(f"   GNames @{addr:#x}: kein 'None'-Eintrag gefunden (Anfang: {first})")
        return False

    def fname_str(self, idx, number=0):
        key = (idx, number)
        if key in self.names_cache:
            return self.names_cache[key]
        blk, off = idx >> 16, (idx & 0xFFFF) * 2
        base = _u64(self.rd(self.pool_blocks + blk * 8, 8))
        if not _valid_ptr(base):
            return f"<name {idx:#x}>"
        hdr = struct.unpack_from("<H", self.rd(base + off, 2))[0]
        length, wide = (hdr >> 1 if self.name_style == "ue4" else hdr >> 6), hdr & 1
        raw = self.rd(base + off + 2, length * (2 if wide else 1))
        text = raw.decode("utf-16-le" if wide else "latin-1", "replace")
        if number > 0:
            text += f"_{number - 1}"
        self.names_cache[key] = text
        return text

    def name(self, obj):
        raw = self.rd(obj + self.o_name, 8)
        return self.fname_str(_u32(raw, 0), _u32(raw, 4))

    def class_ptr(self, obj):
        return _u64(self.rd(obj + self.o_class, 8))

    def outer(self, obj):
        return _u64(self.rd(obj + self.o_outer, 8))

    def class_name(self, obj):
        return self.name(self.class_ptr(obj))

    def full_name(self, obj, depth=8):
        parts, o = [], obj
        for _ in range(depth):
            parts.append(self.name(o))
            o = self.outer(o)
            if not _valid_ptr(o):
                break
        return f"{self.class_name(obj)} " + ".".join(reversed(parts))

    def super_of(self, cls):
        return _u64(self.rd(cls + self.o_super, 8))

    def is_a(self, cls, target):
        return target in self.ancestors(cls)

    def ancestors(self, cls):
        """Klasse + alle Eltern als Menge (gecacht).  Kaputte Zeiger (tote Objekte) ergeben eine leere/kurze Menge
        statt eines Fehlers."""
        cached = self._anc_cache.get(cls)
        if cached is None:
            chain, current = set(), cls
            for _ in range(32):
                if not _valid_ptr(current) or current in chain:
                    break
                chain.add(current)
                try:
                    current = self.super_of(current)
                except Exception:
                    break
            cached = self._anc_cache[cls] = frozenset(chain)
        return cached

    def iter_objects(self, progress=None):
        n = self.num_elements
        nchunks = (n + BLOCK - 1) // BLOCK
        table = self.rd(self._objs, nchunks * 8)
        for c in range(nchunks):
            chunk = _u64(table, c * 8)
            if not _valid_ptr(chunk):
                continue
            cnt = min(BLOCK, n - c * BLOCK)
            raw = bytes(self._read(chunk, cnt * self.item_size))
            for i in range(cnt):
                ptr = _u64(raw, i * self.item_size)
                if _valid_ptr(ptr):
                    yield c * BLOCK + i, ptr
            if progress:
                progress(min(n, (c + 1) * BLOCK), n)

    def build_index(self, progress=None):
        """Einmal ueber alle Objekte: {adresse: (index, class_ptr, name)}  (dauert je nach Spiel)."""
        idx, outers, rflags = {}, {}, {}
        n_total = max(1, self.num_elements)
        for i, ptr in self.iter_objects():
            if progress and i % 2000 == 0:
                progress(i, n_total)
            try:
                hdr = self.rd(ptr, max(self.o_outer, self.o_name, self.o_class) + 8)
                cl = _u64(hdr, self.o_class)
                nm = self.fname_str(_u32(hdr, self.o_name), _u32(hdr, self.o_name + 4))
            except Exception:
                continue
            idx[ptr] = (i, cl, nm)
            outers[ptr] = _u64(hdr, self.o_outer)
            rflags[ptr] = _u32(hdr, 8)  # UObject.ObjectFlags (RF_ClassDefaultObject 0x10, RF_ArchetypeObject 0x20)
        self.index, self.outers, self.rflags = idx, outers, rflags
        return idx

    def is_template(self, ptr):
        """CDO, Archetyp oder Unterobjekt davon (z. B. Default__BP_X_C.AttributeSetCore) - kein echtes Spielobjekt.
        Ohne dieses Filtern zaehlt man jede Blueprint-Vorlage als 'Instanz'."""
        flags, outers = getattr(self, "rflags", {}), getattr(self, "outers", {})
        cur = ptr
        for _ in range(8):
            if cur not in flags:
                return False
            if flags[cur] & 0x30 or self.index[cur][2].startswith("Default__"):
                return True
            cur = outers.get(cur, 0)
            if not cur:
                return False
        return False

    def _strip(self, n):
        return n[1:] if len(n) > 2 and n[0] in "UAFE" and n[1].isupper() else n

    @staticmethod
    def _is_class_kind(kind):
        """'Class', 'BlueprintGeneratedClass', 'WidgetBlueprintGeneratedClass', 'AnimBlueprintGeneratedClass' ..."""
        return kind.endswith("Class")

    def _name_variants(self, sdk_name):
        out = {sdk_name, self._strip(sdk_name)}
        if len(sdk_name) > 1 and sdk_name[0] in "UAFEuafe":  # auch Namen, bei denen _strip nichts tut
            out.add(sdk_name[1:])
        return out

    def find_class(self, sdk_name):
        """UClass-Objekt zu einem SDK-Namen (UHealthComponent -> 'HealthComponent').  Findet auch Blueprint-/
        Widget-/Anim-Klassen (...GeneratedClass), Namen mit '_C' und ignoriert Gross-/Kleinschreibung als
        letzten Versuch."""
        if self.index is None:
            self.build_index()
        fc = self.__dict__.setdefault("_fc_cache", {})
        if fc.get("_idx") is not self.index:
            fc.clear()
            fc["_idx"] = self.index
        if sdk_name in fc:
            return fc[sdk_name]
        fc[sdk_name] = self._find_class_uncached(sdk_name)
        return fc[sdk_name]

    def _find_class_uncached(self, sdk_name):
        want = self._name_variants(sdk_name)
        kind = lambda cl: self.index.get(cl, (0, 0, ""))[2]  # noqa: E731
        for key, (_i, cl, nm) in self.index.items():
            if nm in want and self._is_class_kind(kind(cl)):
                return key
        for key, (_i, cl, nm) in self.index.items():  # BP-Klassen enden auf _C
            if any(nm == w + "_C" for w in want) and self._is_class_kind(kind(cl)):
                return key
        low = {w.lower() for w in want} | {w.lower() + "_c" for w in want}
        for key, (_i, cl, nm) in self.index.items():
            if nm.lower() in low and self._is_class_kind(kind(cl)):
                return key
        return None

    def similar_classes(self, sdk_name, limit=8):
        """Namen vorhandener Klassen, die den (gekuerzten) Namen enthalten - Hilfe, wenn find_class scheitert."""
        if self.index is None:
            self.build_index()
        core = self._strip(sdk_name).lower()
        out = []
        for _key, (_i, cl, nm) in self.index.items():
            if self._is_class_kind(self.index.get(cl, (0, 0, ""))[2]) and core and core in nm.lower():
                out.append(nm)
        return sorted(set(out), key=lambda n: (len(n), n))[:limit]

    def count_default_objects(self, sdk_name):
        """Default__-Objekte (CDO) der Klasse - zeigt, dass die Klasse existiert, aber nichts instanziiert ist."""
        cls = self.find_class(sdk_name)
        if not cls:
            return 0
        return sum(
            1
            for _k, (_i, cl, nm) in self.index.items()
            if nm.startswith("Default__") and (cl == cls or cls in self.ancestors(cl))
        )

    def instances(self, sdk_name, subclasses=True, include_defaults=False):
        """Alle Instanzen einer Klasse -> [{addr, index, name, class}]"""
        cls = self.find_class(sdk_name)
        if not cls:
            return []
        out = []
        for key, (i, cl, nm) in self.index.items():
            if not include_defaults and (nm.startswith("Default__") or self.is_template(key)):
                continue
            if cl == cls or (subclasses and cls in self.ancestors(cl)):
                out.append({"addr": key, "index": i, "name": nm, "class": self.index.get(cl, (0, 0, "?"))[2]})
        for item in out[:500]:  # Besitzer (Outer) dazu: "CHA_Xaurip_C_123" statt nur "AttributeSetCore"
            try:
                outer = self.outer(item["addr"])
                item["owner"] = self.index[outer][2] if outer in self.index else ""
            except Exception:
                item["owner"] = ""
        return out

    def class_chain(self, cls_ptr, limit=32):
        out = []
        while _valid_ptr(cls_ptr) and len(out) < limit:
            out.append(cls_ptr)
            cls_ptr = self.super_of(cls_ptr)
        return out

    def find_function(self, class_sdk_name, func_name):
        """UFunction-OBJEKT (nicht der native Zeiger) in der Klasse oder ihren Eltern -> Adresse | None"""
        cls = self.find_class(class_sdk_name)
        if not cls:
            return None
        chain = set(self.class_chain(cls))
        for key, (_i, cl, nm) in self.index.items():
            if nm == func_name and self.index.get(cl, (0, 0, ""))[2] == "Function" and self.outer(key) in chain:
                return key
        return None

    def default_object(self, class_sdk_name):
        """Default__Klasse (CDO) - Ziel fuer statische Funktionen wie GameplayStatics.*"""
        want = "Default__" + self._strip(class_sdk_name)
        if self.index is None:
            self.build_index()
        for key, (_i, _cl, nm) in self.index.items():
            if nm == want:
                return key
        return None

    def function_entry(self, class_sdk_name, func_name):
        """ExecFunction-Adresse einer UFunction (nativer Einsprung) -> (addr, rva) oder None."""
        if self.o_exec is None:
            raise UELiveError("Offset von UFunction.ExecFunction fehlt im SDK")
        if self.index is None:
            self.build_index()
        want_cls = {class_sdk_name, self._strip(class_sdk_name)}
        for key, (_i, cl, nm) in self.index.items():
            if nm != func_name or self.index.get(cl, (0, 0, ""))[2] != "Function":
                continue
            o = self.outer(key)
            if o in self.index and self.index[o][2] in want_cls:
                addr = _u64(self.rd(key + self.o_exec, 8))
                return (addr, addr - self.base) if _valid_ptr(addr) else None
        return None


def instances_by_scan(live, class_ptr, find_u64):
    """Schnellweg: Objekte finden, indem nach dem Klassenzeiger im Speicher gesucht wird (Scanner der
    Konsole).  find_u64(wert) -> [adressen].  -> [Objektadressen]"""
    return sorted({a - live.o_class for a in find_u64(class_ptr) if a >= live.o_class})


def live_module_base(maps):
    """Basis des Hauptmoduls aus einer Speicherkarte [(start, end, prot, ...)]: niedrigste ausfuehrbare Region."""
    ex = sorted(mapping[0] for mapping in maps if (mapping[2] & 4) and mapping[0] >= 0x10000)
    return ex[0] if ex else None
