"""Tests fuer il2cpp_dump.py: Mini-dump.cs/script.json + simulierter Spielspeicher (keine Konsole noetig)."""
import json
import os
import struct
import tempfile
import unittest

import il2cpp_dump as D

DUMP = """// Image 0: Assembly-CSharp.dll - 0
// Image 1: mscorlib.dll - 3

// Namespace: Game
public enum ItemId // TypeDefIndex: 0
{
\tpublic int value__; // 0x0
\tpublic const ItemId None = 0;
\tpublic const ItemId Apple = 7;
}

// Namespace: Game
public class Wallet // TypeDefIndex: 1
{
\t// Fields
\tpublic int gold; // 0x10
\tpublic float luck; // 0x14
\tpublic bool god; // 0x18
\tpublic ItemId last; // 0x1C
\tpublic static Wallet Instance; // 0x0
\tpublic const int MAX = 99;

\t// Methods

\t// RVA: 0x1000 Offset: 0x1000 VA: 0x1000
\tpublic bool CanBuy(int price) { }

\t// RVA: 0x1010 Offset: 0x1010 VA: 0x1010
\tpublic void Spend(int n) { }

\t// RVA: 0x1020 Offset: 0x1020 VA: 0x1020
\tpublic float GetLuck() { }
}

// Namespace: Game
public class Hidden // TypeDefIndex: 2
{
\tpublic int hp; // 0x10
}

// Namespace: System
public class Object // TypeDefIndex: 3
{
}
"""
SCRIPT = {"ScriptMetadata": [{"Address": 0x2000, "Name": "Game.Wallet_TypeInfo", "Signature": "Game_Wallet_c*"}]}
BASE = 0x7000000
KLASS = 0x9000000


class FakeMem:
    def __init__(self):
        self.d = {}

    def put(self, addr, data):
        for i, b in enumerate(data):
            self.d[addr + i] = b

    def read(self, addr, n):
        return bytes(self.d.get(addr + i, 0) for i in range(n))


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        sub = os.path.join(self.tmp.name, "a", "b")
        os.makedirs(sub)
        open(os.path.join(sub, "dump.cs"), "w").write(DUMP)
        json.dump(SCRIPT, open(os.path.join(sub, "script.json"), "w"), indent=2)
        self.g = D.GameDump(D.find_game_files(self.tmp.name), log=lambda m: None).load()

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse(self):
        w = self.g.find_class("Game.Wallet")
        self.assertEqual([f.name for f in w.fields], ["gold", "luck", "god", "last", "Instance", "MAX"])
        self.assertEqual(w.find_field("gold").offset, 0x10)
        self.assertTrue(w.find_field("Instance").static)
        self.assertEqual(w.methods[0].rva, 0x1000)
        self.assertEqual(w.image, "Assembly-CSharp.dll")
        self.assertEqual(self.g.find_class("Object").image, "mscorlib.dll")
        e = self.g.find_class("ItemId")
        self.assertEqual(e.enum_values, [("None", 0), ("Apple", 7)])
        self.assertEqual(self.g.typeinfo_for(w), 0x2000)
        self.assertEqual(self.g.enum_search("item apple")[0][2], 7)

    def test_targets(self):
        names = {(c.name, f.name, p) for c, f, p, _s in self.g.value_targets()}
        self.assertIn(("Wallet", "gold", "int32"), names)
        self.assertIn(("Wallet", "last", "int32"), names)     # Enum-Feld
        self.assertNotIn(("Wallet", "Instance", "uint64"), names)

    def test_patch_bytes(self):
        m = self.g.find_class("Wallet").methods
        self.assertEqual(D.make_patch(m[0], "true"), b"\xb8\x01\x00\x00\x00\xc3")
        self.assertEqual(D.make_patch(m[1], "noop"), b"\xc3")
        self.assertEqual(D.make_patch(m[2], "value", 1.0), b"\xb8\x00\x00\x80\x3f\x66\x0f\x6e\xc0\xc3")
        with self.assertRaises(ValueError):
            D.make_patch(m[1], "true")        # void
        with self.assertRaises(ValueError):
            D.make_patch(m[0], "noop")        # bool darf nicht leer gemacht werden
        with self.assertRaises(ValueError):
            D.make_patch(m[2], "true")        # float

    def test_live(self):
        mem = FakeMem()
        name_str, ns_str = 0x5000100, 0x5000200
        mem.put(name_str - 1, b"\0Wallet\0")
        mem.put(ns_str, b"Game\0")
        mem.put(KLASS + 0x10, struct.pack("<Q", name_str))
        mem.put(KLASS + 0x18, struct.pack("<Q", ns_str))
        mem.put(KLASS + 0x40, struct.pack("<Q", KLASS))
        mem.put(BASE + 0x2000, struct.pack("<Q", KLASS))
        mem.put(KLASS + D.K_STATIC_FIELDS, struct.pack("<Q", 0xA000000))
        inst = 0x8000040
        mem.put(inst, struct.pack("<Q", KLASS))
        mem.put(inst + 0x10, struct.pack("<i", 123))
        maps = [(BASE, BASE + 0x10000, 5), (0x5000000, 0x5001000, 1), (0x8000000, 0x8001000, 3), (KLASS, KLASS + 0x1000, 3)]
        # Basis wird gegen Klassennamen geprueft (Name an klass+0x10)
        self.assertEqual(D.find_module_base(mem.read, maps, self.g, log=lambda m: None), BASE)
        live = D.Il2CppLive(mem.read, self.g, BASE, maps, log=lambda m: None)
        w = self.g.find_class("Wallet")
        self.assertEqual(live.klass_ptr(w), KLASS)
        self.assertEqual(live.instances(w), [inst])
        self.assertEqual(live.static_base(w), 0xA000000)

    def _world(self):
        mem = FakeMem()
        name_str, ns_str = 0x5000100, 0x5000200
        mem.put(name_str - 1, b"\0Wallet\0")
        mem.put(ns_str, b"Game\0")
        mem.put(KLASS + 0x10, struct.pack("<Q", name_str))
        mem.put(KLASS + 0x18, struct.pack("<Q", ns_str))
        mem.put(KLASS + 0x40, struct.pack("<Q", KLASS))
        mem.put(BASE + 0x2000, struct.pack("<Q", KLASS))
        return mem

    def test_no_reads_outside_maps(self):
        """Regression: unmappte Adressen duerfen nie an die Konsole gehen (ein fehlgeschlagener Read kostet dort Sekunden)."""
        mem = self._world()
        maps = [(0x100000 + i * 0x20000, 0x100000 + i * 0x20000 + 0x1000, 5) for i in range(300)]
        maps += [(BASE, BASE + 0x10000, 5), (0x5000000, 0x5001000, 1), (KLASS, KLASS + 0x1000, 3)]
        bad = []

        def read(a, n):
            if not any(s <= a and a + n <= e for s, e, _p in maps):
                bad.append(a)
            return mem.read(a, n)

        self.assertEqual(D.find_module_base(read, maps, self.g, log=lambda m: None), BASE)
        self.assertEqual(bad, [])

    def test_base_in_the_middle_of_a_group(self):
        """Modul beginnt nicht am Anfang einer Speichergruppe (Module liegen ohne Luecke hintereinander)."""
        mem = self._world()
        maps = [(BASE - 0x100000, BASE, 5), (BASE, BASE + 0x10000, 5), (0x5000000, 0x5001000, 1), (KLASS, KLASS + 0x1000, 3)]
        self.assertEqual(D.find_module_base(mem.read, maps, self.g, log=lambda m: None), BASE)

    def test_uninitialized_slots_are_skipped(self):
        """IL2CPP fuellt TypeInfo-Zeiger erst beim ersten Benutzen: leere Slots duerfen die Basis nicht verwerfen."""
        import copy
        g = copy.copy(self.g)
        g.typeinfo_rva = dict(self.g.typeinfo_rva)
        for i, n in enumerate(("Game.Hidden", "Game.ItemId", "System.Object")):
            g.typeinfo_rva[n] = 0x1F00 + i * 8          # Slots bleiben 0
        g._slot_cache = None
        mem = self._world()
        maps = [(BASE, BASE + 0x10000, 5), (0x5000000, 0x5001000, 1), (KLASS, KLASS + 0x1000, 3)]
        ok, tried = D.check_base(mem.read, BASE, g, maps=maps)
        self.assertEqual((ok, tried), (1, 1))

    def test_execute_only_module_start_named(self):
        """PS5: der Code-Anfang eines Moduls ist nur ausfuehrbar (prot=4). Die Basis darf deshalb nicht an 'lesbar' haengen."""
        mem = self._world()
        maps = [(BASE, BASE + 0x1000, 4, "Il2CppUserAssemblies.prx"), (BASE + 0x1000, BASE + 0x10000, 3, "Il2CppUserAssemblies.prx"),
                (0x4000000, 0x4010000, 5, "eboot.bin"), (0x5000000, 0x5001000, 1, ""), (KLASS, KLASS + 0x1000, 3, "")]
        msgs = []
        self.assertEqual(D.find_module_base(mem.read, maps, self.g, log=msgs.append), BASE)
        self.assertTrue(any("Il2CppUserAssemblies.prx" in m for m in msgs))

    def test_execute_only_module_start_unnamed(self):
        """Auch ohne Modulnamen (aeltere Payload): jede Region zaehlt als Kandidat, nicht nur lesbare."""
        mem = self._world()
        maps = [(BASE, BASE + 0x1000, 4), (BASE + 0x1000, BASE + 0x10000, 3), (0x5000000, 0x5001000, 1), (KLASS, KLASS + 0x1000, 3)]
        self.assertEqual(D.find_module_base(mem.read, maps, self.g, log=lambda m: None), BASE)

    def test_failure_has_diagnosis(self):
        """Falscher Dump: Fehler mit Bericht (Modulname, Basis, was im Speicher steht) statt nur 'passt nicht'."""
        mem = self._world()
        mem.put(BASE + 0x2000, struct.pack("<Q", 0))           # Slot leer
        maps = [(BASE, BASE + 0x1000, 4, "Il2CppUserAssemblies.prx"), (BASE + 0x1000, BASE + 0x10000, 3, "Il2CppUserAssemblies.prx")]
        msgs = []
        with self.assertRaises(D.DumpError):
            D.find_module_base(mem.read, maps, self.g, log=msgs.append)
        text = "\n".join(msgs)
        self.assertIn("Diagnose Il2CppUserAssemblies.prx", text)
        self.assertIn("Alle Slots leer", text)

    def test_census_family_and_monitor(self):
        """census zaehlt Objekte je Klasse; Zeiger in Klassen-Strukturen (Monitor-Feld != 0) zaehlen nicht; Objekte von
        Unterklassen finden sich ueber die Basisklasse."""
        g = self.g
        mem = self._world()
        sub = 0x9100000                                       # Unterklasse 'Hidden' erbt von 'Wallet' (im Test per Hand)
        g.find_class("Hidden").base = "Wallet"
        g._parent = None
        del g._parent
        g.typeinfo_rva["Game.Hidden"] = 0x2008
        g._slot_cache = None
        name2, ns2 = 0x5000300, 0x5000200
        mem.put(name2 - 1, b"\0Hidden\0")
        mem.put(sub + 0x10, struct.pack("<Q", name2))
        mem.put(sub + 0x18, struct.pack("<Q", ns2))
        mem.put(sub + 0x40, struct.pack("<Q", sub))
        mem.put(sub + 0x48, struct.pack("<Q", sub))
        mem.put(BASE + 0x2008, struct.pack("<Q", sub))
        mem.put(KLASS + 0x48, struct.pack("<Q", KLASS))        # castClass zeigt auf sich: kein Objekt
        for i, addr in enumerate((0x8000040, 0x8000080)):      # 2 Wallets, 1 Hidden
            mem.put(addr, struct.pack("<QQ", KLASS, 0))
        mem.put(0x80000C0, struct.pack("<QQ", sub, 0))
        mem.put(0x8000100, struct.pack("<QQ", KLASS, 0x1234))  # Monitor gesetzt -> Klassen-Struktur-artig, ignoriert
        maps = [(BASE, BASE + 0x10000, 5), (0x5000000, 0x5001000, 1), (0x8000000, 0x8001000, 3),
                (KLASS, KLASS + 0x1000, 3), (sub, sub + 0x1000, 3)]
        live = D.Il2CppLive(mem.read, g, BASE, maps, log=lambda m: None)
        counts, inited = live.census()
        self.assertEqual(counts, {"Game.Wallet": 2, "Game.Hidden": 1})
        self.assertEqual(inited, {"Game.Wallet", "Game.Hidden"})
        w = g.find_class("Wallet")
        self.assertEqual(live.instances(w), [0x8000040, 0x8000080, 0x80000C0])   # inkl. Unterklasse
        self.assertEqual(live.instances(g.find_class("Hidden")), [0x80000C0])

    def _census_world(self):
        mem = self._world()
        mem.put(KLASS + 0x48, struct.pack("<Q", KLASS))
        for addr in (0x8000040, 0x8000080, 0x8001040):
            mem.put(addr, struct.pack("<QQ", KLASS, 0))
        maps = [(BASE, BASE + 0x10000, 5, "Il2CppUserAssemblies.prx"), (0x5000000, 0x5001000, 1, ""),
                (0x8000000, 0x8001000, 3, ""), (0x8001000, 0x8002000, 3, ""), (KLASS, KLASS + 0x1000, 3, "")]
        reads = []

        def read(a, n):
            reads.append((a, n))
            return mem.read(a, n)

        live = D.Il2CppLive(read, self.g, BASE, maps, log=lambda m: None)
        return mem, live, reads

    def test_instances_from_census_cache(self):
        """Nach census() liest instances() nur noch die Objekt-Koepfe (16 Byte) statt den Heap neu."""
        mem, live, reads = self._census_world()
        live.census()
        del reads[:]
        w = self.g.find_class("Wallet")
        self.assertEqual(live.instances(w), [0x8000040, 0x8000080, 0x8001040])
        self.assertEqual(live.last_source, "cache")
        self.assertTrue(all(n <= 16 for _a, n in reads), reads)

    def test_cache_drops_freed_objects(self):
        mem, live, reads = self._census_world()
        live.census()
        mem.put(0x8000080, struct.pack("<QQ", 0, 0))              # Objekt wurde freigegeben
        w = self.g.find_class("Wallet")
        self.assertEqual(live.instances(w), [0x8000040, 0x8001040])
        self.assertNotIn(0x8000080, live.objects["Game.Wallet"])

    def test_rescan_refreshes_cache(self):
        mem, live, reads = self._census_world()
        live.census()
        mem.put(0x8000100, struct.pack("<QQ", KLASS, 0))          # neues Objekt nach dem Scan
        w = self.g.find_class("Wallet")
        self.assertEqual(len(live.instances(w)), 3)                # Cache kennt es nicht
        self.assertEqual(len(live.instances(w, use_cache=False)), 4)
        self.assertEqual(live.last_source, "scan")
        self.assertEqual(len(live.instances(w)), 4)                # Cache ist erneuert

    def test_module_regions_are_skipped(self):
        maps = [(0x1000000, 0x1100000, 3, "Il2CppUserAssemblies.prx"), (0x2000000, 0x2100000, 3, "eboot.bin"),
                (0x3000000, 0x3100000, 3, ""), (0x4000000, 0x4100000, 3, "anon")]
        live = D.Il2CppLive(lambda a, n: b"", self.g, BASE, maps, log=lambda m: None)
        self.assertEqual(live.heap_regions(), [(0x3000000, 0x3100000), (0x4000000, 0x4100000)])

    def test_clean_names(self):
        C = D.Class("N", "Foo", "class")
        self.assertEqual(D.clean_field_name("<Reputation>k__BackingField"), "Reputation")
        self.assertEqual(D.clean_field_name("gold"), "gold")
        self.assertTrue(D.is_generated(D.Class("N", "UIMoneyHeld.<>c__DisplayClass30_0", "class")))
        self.assertTrue(D.is_generated(D.Class("N", "Foo.<Run>d__3", "class")))
        self.assertFalse(D.is_generated(C))
        self.assertTrue(D.is_generated(C, D.Field("<>4__this", "Foo", 0x10)))
        self.assertFalse(D.is_generated(C, D.Field("<Gold>k__BackingField", "int", 0x10)))

    def test_resolve_by_name(self):
        mem = FakeMem()
        k = 0x9000000
        mem.put(0x5000100 - 1, b"\0Hidden\0")
        mem.put(0x5000200, b"Game\0")
        mem.put(k + 0x10, struct.pack("<Q", 0x5000100))
        mem.put(k + 0x18, struct.pack("<Q", 0x5000200))
        mem.put(k + 0x40, struct.pack("<Q", k))
        maps = [(0x5000000, 0x5001000, 1), (k, k + 0x1000, 3)]
        live = D.Il2CppLive(mem.read, self.g, BASE, maps, log=lambda m: None)
        self.assertEqual(live.klass_ptr(self.g.find_class("Hidden")), k)

    def test_reapproj(self):
        doc = D.reapproj_for_patch("Gold", 0x1000, b"\x55", b"\xc3")
        p = D.write_reapproj(self.tmp.name, doc)
        import reapatch
        rp = reapatch.ReapPatch.load(p)
        self.assertEqual(rp.origin_source[0], 0x1000)


if __name__ == "__main__":
    unittest.main()
