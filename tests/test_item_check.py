"""item_check: Vorab-Test (nur Lesen) und Live-Test (Test-Cave, Haken wird IMMER entfernt) - ohne Konsole."""
import os, struct, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cave_trainer as TR
import item_check as IC
import test_cave_trainer as TS
import test_ue_items as TI
import test_ue_profile as TP
import ue_cavegen as CG
import ue_items as IT
import ue_profile as P

PC = 0x7000000100                 # "PlayerController" im Fake-Heap
BAG = 0x7000000800


class FakeLive:
    def __init__(self, names):
        self.names = names                                    # {index: Text}
        self.entry = (0x1234, None)

    def function_entry(self, owner, name):
        return self.entry

    def instances(self, cls):
        return [{"addr": PC, "name": "BP_PlayerController_C_0"}]

    def fname_str(self, idx, number=0):
        return self.names.get(idx, f"<name {idx:#x}>")


def items(names, start=1):
    return [{"name": n, "fname": struct.pack("<II", start + i, 0), "id": None, "category": "A", "table": ""}
            for i, n in enumerate(names)]


class Base(unittest.TestCase):
    def setUp(self):
        self.sdk = TP.sdk_from(TI.GAME_C, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_ItemParam.DT_ItemParam")])
        self.prof = P.build(self.sdk)
        self.func = next(r["sug"] for r in IT.rate_functions(self.prof, self.sdk) if r["relevant"])   # AddItem (erreichbar)
        self.img = TS.FakeImage()
        struct.pack_into("<Q", self.img.mem[0x7000000000], 0x100 + 0x300, BAG)                     # PC -> ItemBag
        self._old = CG.find_impl, IT.hook_targets
        CG.find_impl = lambda read, base, thunk: self.img.impl
        IT.hook_targets = lambda sdk, live, read, base, wide=False: (self.img.pe, [self.img.slot], [])
        self.addCleanup(self._restore)
        self.names = {1: "Item_A", 2: "Item_B", 3: "Item_C"}
        self.live = FakeLive(self.names)
        self.its = items(["Item_A", "Item_B", "Item_C"])

    def _restore(self):
        CG.find_impl, IT.hook_targets = self._old

    def pre(self, its=None, live=None):
        return IC.preflight(its or self.its, self.func, self.sdk, live or self.live, self.img.read, self.img.BASE,
                            self.img.maps, log=lambda _m: None)


class Preflight(Base):
    def test_everything_fine(self):
        rep = self.pre()
        self.assertFalse(rep.blocking, rep.text())
        self.assertEqual([c.status for c in rep.checks], [IC.OK] * len(rep.checks), rep.text())
        self.assertEqual([r.status for r in rep.results], [IC.OK] * 3)
        self.assertEqual(rep.counts()[IC.OK], 3)

    def test_wrong_fname_is_a_failure_for_that_item_only(self):
        its = items(["Item_A", "Item_B", "Item_C"])
        its[1]["fname"] = struct.pack("<II", 3, 0)                      # zeigt auf Item_C, heisst aber Item_B
        its[2]["fname"] = struct.pack("<II", 99, 0)                     # gibt es nicht im Namenspool
        rep = self.pre(its)
        self.assertEqual([r.status for r in rep.results], [IC.OK, IC.FAIL, IC.FAIL])
        self.assertIn("Item_C", rep.results[1].reasons[0])
        self.assertIn("Namenspool", rep.results[2].reasons[0])
        self.assertFalse(rep.blocking)

    def test_none_and_empty_names(self):
        its = items(["None", " ", "Item_A"])
        rep = self.pre(its)
        self.assertEqual([r.status for r in rep.results], [IC.FAIL] * 3)          # 3. Item: Index 3 gehoert zu 'Item_C', nicht 'Item_A'
        self.assertEqual(rep.results[0].reasons, ["kein gültiger Name"])

    def test_missing_function_blocks_all_items(self):
        self.live.entry = None
        rep = self.pre()
        self.assertTrue(rep.blocking)
        self.assertTrue(all(r.status == IC.FAIL for r in rep.results))
        self.assertIn("gibt es im laufenden Spiel nicht", rep.text())

    def test_no_native_impl_blocks(self):
        CG.find_impl = lambda read, base, thunk: None
        rep = self.pre()
        self.assertTrue(rep.blocking)
        self.assertIn("kein normaler C++-Code", rep.text())

    def test_impl_in_data_region_is_rejected(self):
        CG.find_impl = lambda read, base, thunk: self.img.BASE + 0x12100        # rw-, nicht ausfuehrbar
        rep = self.pre()
        self.assertTrue(rep.blocking)
        self.assertIn("ausführbar", rep.text())

    def test_null_this_pointer_is_only_a_warning(self):
        struct.pack_into("<Q", self.img.mem[0x7000000000], 0x100 + 0x300, 0)
        rep = self.pre()
        self.assertFalse(rep.blocking)
        warn = [c for c in rep.checks if c.status == IC.WARN]
        self.assertEqual([c.name for c in warn], ["Objekt (this)"])
        self.assertIn("Spielstand laden", warn[0].text)

    def test_function_that_never_reads_this_needs_no_object(self):
        """Shipping-Build: der CheatManager wird nie angelegt (Zeiger 0) - die Funktion liest this aber nicht -> kein Hindernis."""
        struct.pack_into("<Q", self.img.mem[0x7000000000], 0x100 + 0x300, 0)
        old = CG.impl_ignores_this
        CG.impl_ignores_this = lambda read, impl: True
        try:
            rep = self.pre()
        finally:
            CG.impl_ignores_this = old
        self.assertFalse(rep.blocking)
        self.assertEqual([c for c in rep.checks if c.status == IC.WARN], [])
        self.assertIn("liest this nie", rep.text())

    def test_hook_slots_missing_blocks(self):
        IT.hook_targets = lambda sdk, live, read, base, wide=False: (self.img.pe, [], ["vtable 0x1: Slot 77 zeigt woandershin"])
        rep = self.pre()
        self.assertTrue(rep.blocking)
        self.assertIn("Haken", rep.text())

    def test_no_cave_room_blocks(self):
        self.img.write(self.img.BASE + 0x0000, b"\x90" * 0x10000)             # die ganze Code-Region ist Code, kein Padding
        rep = self.pre()
        room = next(c for c in rep.checks if c.name == "Platz für die Cave")
        self.assertEqual(room.status, IC.FAIL)
        self.assertIn("kein freier Code-Platz", room.text)
        self.assertTrue(rep.blocking)

    def test_wrong_base_is_reported(self):
        rep = IC.preflight(self.its, self.func, self.sdk, self.live, self.img.read, 0x10000000, self.img.maps)
        self.assertTrue(rep.blocking)
        self.assertEqual(rep.checks[0].name, "Image-Basis")


class SubsystemObject(Base):
    """Klasse, deren Objekt der Trainer ueber den PlayerController nicht erreicht (Subsystem) - aber im Spiel existiert."""

    def setUp(self):
        super().setUp()
        self.live.instances = lambda cls: [{"addr": BAG, "name": "Sub_0"}]
        struct.pack_into("<Q", self.img.mem[0x7000000000], BAG - 0x7000000000, 0x4141_0000)       # vtable des Objekts
        self._cs = CG.choose_this
        CG.choose_this = lambda sdk, owner, hooked="APlayerController", static=False, this_unused=None: ("zero", 0, "x")
        self.addCleanup(setattr, CG, "choose_this", self._cs)

    def test_preflight_accepts_the_fixed_address(self):
        rep = self.pre()
        self.assertEqual([c for c in rep.checks if c.status == IC.WARN], [])
        self.assertIn("feste Adresse", rep.text())

    def test_reach_is_abs(self):
        self.assertEqual(IC._reach(self.func, self.sdk, self.live, self.img.read, self.img.BASE), "abs")

    def test_without_a_live_object_it_stays_a_warning(self):
        self.live.instances = lambda cls: []
        rep = self.pre()
        self.assertEqual([c.name for c in rep.checks if c.status == IC.WARN], ["Objekt (this)"])


class WideHooks(Base):
    """Haken auch an Pawn/HUD ...: nur wenn kein Eintrag `this` vom PlayerController braucht."""

    PAWN = 0x7000000200

    def setUp(self):
        super().setUp()
        IT.hook_targets = self._old[1]                                      # die echte Funktion pruefen
        self.vt1 = self.img.slot - 8 * 77
        self.vt2 = self.img.slot + 0x400 - 8 * 77
        self.img.write(self.img.slot + 0x400, struct.pack("<Q", self.img.pe))
        self.img.write(PC, struct.pack("<Q", self.vt1))
        self.img.write(self.PAWN, struct.pack("<Q", self.vt2))
        self.live.instances = lambda cls: {"APlayerController": [{"addr": PC, "name": "PC_0"}],
                                           "APawn": [{"addr": self.PAWN, "name": "Pawn_0"}]}.get(cls, [])

    def test_wide_adds_the_pawn_vtable(self):
        _pe, slots, _n = IT.hook_targets(self.sdk, self.live, self.img.read, self.img.BASE)
        self.assertEqual(slots, [self.img.slot])
        _pe, slots, _n = IT.hook_targets(self.sdk, self.live, self.img.read, self.img.BASE, wide=True)
        self.assertEqual(slots, [self.img.slot, self.img.slot + 0x400])

    def test_needs_controller_only_for_hooked_and_member_rows(self):
        class N:
            def __init__(self, **k): self.__dict__.update(k)
        opt = lambda mode: N(rows=[N(spec=N(this_mode=mode))])  # noqa: E731
        self.assertTrue(IT.needs_controller([opt("hooked")]))
        self.assertTrue(IT.needs_controller([opt("zero"), opt("member")]))
        self.assertFalse(IT.needs_controller([opt("zero"), opt("abs")]))

    def test_give_via_cave_hooks_wide_only_for_objects_the_controller_is_not_needed_for(self):
        seen = []
        real = IT.hook_targets
        IT.hook_targets = lambda sdk, live, read, base, wide=False: seen.append(wide) or real(sdk, live, read, base, wide)
        self.addCleanup(setattr, IT, "hook_targets", self._old[1])
        IC.give_via_cave(self.its, self.func, self.sdk, self.live, self.img.read, self.img.write, self.img.BASE, self.img.maps,
                         5, log=lambda _m: None, wait=0.2)
        self.assertEqual(seen, [False])                                     # GAME_C: this kommt vom PlayerController
        cs = CG.choose_this
        CG.choose_this = lambda sdk, owner, hooked="APlayerController", static=False, this_unused=None: ("zero", 0, "x")
        self.addCleanup(setattr, CG, "choose_this", cs)
        old_lo = IT.live_object
        IT.live_object = lambda live, read, owner: (BAG, 0x4141_0000)
        self.addCleanup(setattr, IT, "live_object", old_lo)
        IC.give_via_cave(self.its, self.func, self.sdk, self.live, self.img.read, self.img.write, self.img.BASE, self.img.maps,
                         5, log=lambda _m: None, wait=0.2)
        self.assertEqual(seen, [False, True])


class Probe(Base):
    def game(self):
        """Simuliert den Spiel-Thread: die Cave setzt gesetzte Schalter (Bytes == 1 am Ende der Daten-Region) auf 0."""
        end = self.img.BASE + 0x16000
        buf = bytearray(self.img.read(end - 0x100, 0x100))
        if 1 in buf:
            self.img.write(end - 0x100, bytes(0 if b == 1 else b for b in buf))

    def go(self, rep=None, tick="game", **kw):
        rep = rep or self.pre()
        tick = self.game if tick == "game" else tick
        n = IC.live_probe(self.its, rep.results, self.func, self.sdk, self.live, self.img.read, self.img.write,
                          self.img.BASE, self.img.maps, 5, log=lambda _m: None, wait=0.4, tick=tick, **kw)
        return rep, n

    def test_all_items_run_and_hook_is_removed(self):
        rep, n = self.go()
        self.assertEqual(n, 3)
        self.assertEqual([r.ran for r in rep.results], [True, True, True])
        self.assertEqual([r.label for r in rep.results], ["✔ läuft"] * 3)
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)      # Haken weg
        self.assertEqual(self.img.read(self.img.BASE + 0x16000 - 0x100, 0x100), bytes(0x100))        # Schalter 0

    def test_after_the_first_miss_the_rest_is_not_waited_for_one_by_one(self):
        sets, real = [], self.img.write
        self.img.write = lambda a, d: (sets.append(a) if d == b"\x01" else None, real(a, d))[1]
        rep, n = self.go(tick=None)
        self.assertEqual(len(sets), 1)                                       # nur der erste Schalter wurde gesetzt und abgewartet
        self.assertEqual([r.ran for r in rep.results], [False] * 3)

    def test_nothing_given_says_what_to_do(self):
        res = self.give(tick=None)
        self.assertEqual(res["given"], 0)
        self.assertIn("Kamera bewegen", res["error"])

    def test_cave_that_never_runs_is_reported_and_cleaned_up(self):
        rep, n = self.go(tick=None)
        self.assertEqual(n, 0)
        self.assertEqual([r.ran for r in rep.results], [False] * 3)
        self.assertEqual([r.status for r in rep.results], [IC.WARN] * 3)
        self.assertIn("nicht ausgeführt", rep.results[0].reasons[0])
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)
        self.assertEqual(self.img.read(self.img.BASE + 0x16000 - 0x100, 0x100), bytes(0x100))

    def test_failed_items_are_not_probed(self):
        its = items(["Item_A", "Item_B", "Item_C"]); its[1]["fname"] = struct.pack("<II", 99, 0)
        self.its = its
        rep, n = self.go(rep=self.pre(its))
        self.assertEqual(n, 2)
        self.assertEqual([r.ran for r in rep.results], [True, None, True])

    def test_hook_is_removed_even_if_writing_fails_midway(self):
        calls = {"n": 0}
        real = self.img.write

        def flaky(addr, data):
            calls["n"] += 1
            if addr < self.img.BASE + 0x10000 and calls["n"] > 1 or (len(data) == 1 and data == b"\x01"):
                raise IOError("Verbindung weg")
            real(addr, data)
        self.img.write = flaky
        with self.assertRaises(IOError):
            self.go()
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)

    def expand(self, tick):
        f = P._sug("expand_function", "UItemBag.ExpandAll", 9, "()", [], {"owner": "UItemBag", "name": "ExpandAll", "params": [],
                                                                         "ret": "void", "flags": 0, "native": 1})
        return IC.run_expand(f, self.sdk, self.live, self.img.read, self.img.write, self.img.BASE, self.img.maps,
                             log=lambda _m: None, wait=0.4, tick=tick)

    def test_run_expand_runs_once_on_the_game_thread_and_removes_the_hook(self):
        self.assertTrue(self.expand(self.game))
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)

    def test_run_expand_reports_a_cave_that_never_ran(self):
        self.assertFalse(self.expand(None))
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)
        self.assertEqual(self.img.read(self.img.BASE + 0x16000 - 0x100, 0x100), bytes(0x100))

    def test_hooked_by_someone_else_gives_clear_error_and_changes_nothing(self):
        self.img.write(self.img.slot, struct.pack("<Q", self.img.pe + 0x10))
        with self.assertRaises(TR.TrainerError) as c:
            self.go()
        self.assertIn("zeigt nicht auf ProcessEvent", str(c.exception))
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe + 0x10)

    def give(self, tick="game", **kw):
        tick = self.game if tick == "game" else tick
        return IC.give_via_cave(self.its, self.func, self.sdk, self.live, self.img.read, self.img.write, self.img.BASE,
                                self.img.maps, 5, log=lambda _m: None, wait=0.4, tick=tick, **kw)

    def test_give_via_cave_gives_the_items_on_the_game_thread_and_removes_the_hook(self):
        res = self.give()
        self.assertEqual((res["total"], res["given"], res["error"]), (3, 3, None))
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)        # Haken weg
        self.assertEqual(self.img.read(self.img.BASE + 0x16000 - 0x100, 0x100), bytes(0x100))

    def test_give_via_cave_says_so_when_the_game_never_runs_the_cave(self):
        res = self.give(tick=None)
        self.assertEqual(res["given"], 0)
        self.assertIn("nicht ausgeführt", res["error"])
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe)

    def test_give_via_cave_with_foreign_hook_raises_before_changing_anything(self):
        self.img.write(self.img.slot, struct.pack("<Q", self.img.pe + 0x10))
        with self.assertRaises(TR.TrainerError):
            self.give()
        self.assertEqual(struct.unpack("<Q", self.img.read(self.img.slot, 8))[0], self.img.pe + 0x10)

    def test_give_via_cave_twice_reuses_the_left_over_cave(self):
        self.assertEqual(self.give()["given"], 3)
        self.assertEqual(self.give()["given"], 3)                  # die erste Cave blieb stehen - der Platz wird wiederverwendet

    def test_manual_answer_no_marks_running_items(self):
        rep, _n = self.go()
        IC.apply_manual_answer(rep.results, [0, 1, 2], worked=False)
        self.assertTrue(all(r.status == IC.WARN for r in rep.results))
        rep2, _ = self.go()
        IC.apply_manual_answer(rep2.results, [0, 1, 2], worked=True)
        self.assertTrue(all(r.status == IC.OK for r in rep2.results))

    def test_many_items_are_split_into_groups_by_free_space(self):
        names = {i + 1: f"Item_{i}" for i in range(40)}
        self.live.names = names
        self.its = items([f"Item_{i}" for i in range(40)])
        rep, n = self.go(rep=self.pre(self.its))
        self.assertEqual(n, 40)


if __name__ == "__main__":
    unittest.main()


class FarCave(unittest.TestCase):
    """Image-Padding zu weit von den Zielen: Ausweichplatz in Reichweite, und alle Ziele zaehlen."""

    def test_far_region_used_when_image_padding_is_out_of_reach(self):
        base = 0x400000
        maps = [(base, base + 0x10000, 5), (0x80000000, 0x80010000, 5), (0x7F000000 + 0x2000000, 0x7F000000 + 0x2010000, 5)]
        mem = {s: bytearray(e - s) for s, e, _p in maps}

        def read(a, n):
            for s, e, _p in maps:
                if s <= a and a + n <= e:
                    return bytes(mem[s][a - s:a - s + n])
            raise IOError

        old = TR.LIMIT
        TR.LIMIT = 0x20000000
        try:
            target = 0x80004000                               # Item-Funktion weit weg vom Image-Padding
            sl = TR.Slots(read, TR.image_span(maps, base), lambda _m: None)
            sl.targets = [target, base + 0x100]               # ... aber auch ProcessEvent im Image muss erreichbar sein
            sl.far_span = [(0x80000000, 0x80010000, 5)]
            self.assertTrue(sl.reaches(0x80008000, 0x100, target) is False)   # weit vom Image
            sl.targets = [target]
            cave, _n = sl.alloc_code(0x100, target)
            self.assertTrue(0x80000000 <= cave < 0x80010000 or base <= cave < base + 0x10000)
            sl2 = TR.Slots(read, TR.image_span(maps, base), lambda _m: None)
            sl2.targets = [target]
            sl2.far_span = [(0x80000000, 0x80010000, 5)]
            cave, _n = sl2.alloc_code(0x100, target)
            self.assertTrue(sl2.reaches(cave, 0x100, target))
        finally:
            TR.LIMIT = old
