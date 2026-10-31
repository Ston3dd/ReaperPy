"""ue_items: Items einteilen, in Pakete/Projekte verteilen, Trainer bauen (ohne Konsole, mit Fake-Image)."""
import os, shutil, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cave_trainer as TR
import uesdk
import test_cave_trainer as TS
import test_ue_profile as TP
import ue_cavegen as CG
import ue_items as IT
import ue_profile as P


def rows(names, **vals):
    return [{"name": n, "fname_hex": f"{i + 1:02x}" + "00" * 7, "row_ptr": 0, "values": dict(vals.get(n, {}))}
            for i, n in enumerate(names)]


class Categories(unittest.TestCase):
    def test_name_prefix(self):
        self.assertEqual(IT.name_prefix("Item_Fish_Trout"), "Fish")
        self.assertEqual(IT.name_prefix("DT_Weapon_Sword"), "Weapon")
        self.assertEqual(IT.name_prefix("FishTrout"), "Fish")
        self.assertIsNone(IT.name_prefix("Gold"))
        self.assertIsNone(IT.name_prefix("Item_Potion"))          # nur ein Wort uebrig
        self.assertIsNone(IT.name_prefix("Item_42_x"))

    def test_prefix_grouping_other_and_no_item_word(self):
        names = [f"Item_Fish_{i}" for i in range(5)] + [f"Item_Weapon_{i}" for i in range(4)] + ["Item_Gold_Lone"]
        its = IT.build_items(rows(names))
        cats = IT.group_items(its)
        self.assertEqual(list(cats), ["Fish", "Weapon", IT.OTHER])
        self.assertEqual([len(v) for v in cats.values()], [5, 4, 1])
        self.assertTrue(all("item" not in c.lower() for c in cats))

    def test_fallback_all_when_no_structure(self):
        its = IT.build_items(rows(["Gold", "Potion", "Sword", "Shield"]))
        self.assertEqual(list(IT.group_items(its)), [IT.ALL])

    def test_category_column_enum_and_int(self):
        cols = [("ItemType", "FName", 0, 8), ("Price", "int32", 8, 4)]
        r = rows(["A", "B", "C", "D"], A={"ItemType": "EItemType::Weapon"}, B={"ItemType": "EItemType::Weapon"},
                 C={"ItemType": "EItemType::Food"}, D={"ItemType": "EItemType::Food"})
        self.assertEqual(list(IT.group_items(IT.build_items(r, cols))), ["Food", "Weapon"])
        r = rows(["A", "B", "C"], A={"ItemType": 1}, B={"ItemType": 1}, C={"ItemType": 2})
        cols = [("ItemType", "int32", 0, 4)]
        self.assertEqual(list(IT.group_items(IT.build_items(r, cols))), ["Item Type 1", "Item Type 2"])

    def test_junk_rows_dropped(self):
        its = IT.build_items(rows(["None", "", "Gold"]))
        self.assertEqual([i["name"] for i in its], ["Gold"])


class Packages(unittest.TestCase):
    def items(self, cat, n):
        return [{"name": f"{cat}{i}", "fname": bytes([1] * 8), "id": i, "category": cat} for i in range(n)]

    def test_names_match_split_package(self):
        groups = {"Fische": self.items("f", 30), "Waffen": self.items("w", 10)}
        pk = IT.packages(groups)
        self.assertEqual([n for n, _ in pk], ["Fische 1", "Fische 2", "Fische 3", "Waffen"])
        self.assertEqual([len(i) for _, i in pk], [14, 14, 2, 10])
        ref = [o.name for o in TR.split_package("Fische", list(range(30)))]
        self.assertEqual([n for n, _ in pk[:3]], ref)

    def test_unique_names_for_clashing_categories(self):
        groups = {"Fish": self.items("a", 3), "fish": self.items("b", 3)}
        names = [n.lower() for n, _ in IT.packages(groups)]
        self.assertEqual(len(set(names)), 2)

    def test_split_projects_limits(self):
        groups = {f"Kat{k}": self.items(f"k{k}", 40) for k in range(20)}       # 800 Items
        pk = IT.packages(groups)
        pr = IT.split_projects(pk)
        self.assertGreater(len(pr), 1)
        for p in pr:
            self.assertLessEqual(sum(len(i) for _, i in p), TR.MAX_ROWS)
            self.assertLessEqual(len(p), TR.MAX_OPTIONS)
        self.assertEqual(sum(len(i) for p in pr for _, i in p), 800)
        many = [(f"p{k}", self.items("x", 1)) for k in range(150)]
        self.assertTrue(all(len(p) <= TR.MAX_OPTIONS for p in IT.split_projects(many)))

    def test_project_dirs(self):
        self.assertEqual([os.path.basename(d) for d in IT.project_dirs("/x", 1)], ["Items"])
        self.assertEqual([os.path.basename(d) for d in IT.project_dirs("/x", 3)], ["Items 1", "Items 2", "Items 3"])

    def test_usable_number_ids(self):
        its = [{"id": 5}, {"id": None}]
        self.assertEqual(IT.usable(its, "int"), ([{"id": 5}], [{"id": None}]))
        self.assertEqual(IT.usable(its, "fname"), (its, []))


class Choosing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sdk = TP.sdk_from(TP.GAME_A, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_Items.DT_Items")])
        cls.prof = P.build(cls.sdk)

    def test_give_candidates_need_an_id_parameter(self):
        ok, bad = IT.give_candidates(self.prof, self.sdk)
        self.assertEqual({s.data["name"] for s in ok}, {"GiveItem", "AddItem"})
        self.assertIn("AddGold", {s.data["name"] for s, _ in bad})
        self.assertEqual(IT.id_param(ok[0], self.sdk)["kind"], "fname")

    def test_choose_table_prefers_item_tables(self):
        live = [(0x10, "DT_Enemies"), (0x20, "DT_Items")]
        ranked = IT.choose_table(IT.table_candidates(self.prof), live)
        self.assertEqual(ranked[0][1], (0x20, "DT_Items"))
        self.assertEqual([n for _a, n in IT.order_tables(live)], ["DT_Items"])      # Junk (Gegner ...) fliegt raus


# Nachgebautes "verwirrendes" Spiel: viele DataTables, nur eine ist die Item-Liste; viele Funktionen mit "Item" im Namen.
GAME_C = "".join([
    TP.cls("FItemParam", "FTableRowBase", [("FName", "ItemId", 0x08, 8), ("int32", "Price", 0x10, 4),
                                           ("int32", "MaxStack", 0x14, 4)], kind="struct"),
    TP.cls("FFxParam", "FTableRowBase", [("FName", "FxId", 0x08, 8), ("float", "Scale", 0x10, 4)], kind="struct"),
    TP.cls("FZombieAIParam", "FTableRowBase", [("FName", "ZombieId", 0x08, 8), ("float", "Speed", 0x10, 4)], kind="struct"),
    TP.cls("APlayerController", "AController", [("class UItemBagComponent*", "ItemBag", 0x300, 8)]),
    TP.cls("UItemBagComponent", "UActorComponent", [], ["void AddItem(class FName ItemName, int32 Count);"]),
    TP.cls("UMyInventorySubsystem", "UGameInstanceSubsystem", [],
           ["void AddImportantItem(class FName ItemName, int32 Count);", "void AddItemInventory(class FName ItemName, int32 Count);"]),
    TP.cls("UMyCheatManager", "UCheatManager", [],
           ["void AddSelectItem(class FName ItemName, int32 Count);", "void AddPresetItem(class FName ItemName, int32 Count);"]),
    TP.cls("AItemModelViewActor", "AActor", [], ["void SpawnItem(class FName ItemName, int32 Count);"]),
])
GAME_C_TABLES = ["DT_FxParam_Player", "DT_ItemParam", "DT_UIMapParam", "DT_ZombieAIParam", "DT_TextIconTag",
                 "DT_UISoundParam", "DT_TriggerEffectParam", "DT_WorkbenchBuildParam"]


class ConfusingGame(unittest.TestCase):
    """Spiel mit vielen Tabellen/Funktionen: nur die passenden werden gezeigt, die beste automatisch gewaehlt."""
    @classmethod
    def setUpClass(cls):
        objs = [(i + 1, 0x7000_1000 + 0x1000 * i, "DataTable", f"DataTable /Game/Data/{n}.{n}")
                for i, n in enumerate(GAME_C_TABLES)]
        cls.sdk = TP.sdk_from(GAME_C, objs)
        cls.prof = P.build(cls.sdk)
        cls.live = [(0x7000_1000 + 0x1000 * i, n) for i, n in enumerate(GAME_C_TABLES)]

    def test_name_relevance(self):
        good = ["DT_ItemParam", "DT_Items", "DT_WeaponParam", "DT_ConsumableData", "DT_LootTable", "DT_ITEMPARAM"]
        bad = ["DT_FxParam_Player", "DT_UIMapParam", "DT_ZombieAIParam", "DT_TextIconTag", "DT_UISoundParam",
               "DT_TriggerEffectParam", "DT_WorkbenchBuildParam", "DT_Enemies", "DT_ItemTextParam"]
        for n in good:
            self.assertGreaterEqual(IT.table_relevance(n), IT.REL_MIN, n)
        for n in bad:
            self.assertLess(IT.table_relevance(n), IT.REL_MIN, n)
        self.assertGreater(IT.table_relevance("DT_ItemParam"), IT.table_relevance("DT_ItemShopParam"))

    def test_only_the_item_table_is_relevant_and_chosen(self):
        rated = IT.rate_tables(IT.table_candidates(self.prof), self.live)
        self.assertEqual(len(rated), len(GAME_C_TABLES))                        # alle bewertet, nichts verloren
        self.assertEqual([r["name"] for r in rated if r["relevant"]], ["DT_ItemParam"])
        self.assertEqual(rated[0]["name"], "DT_ItemParam")
        self.assertEqual(IT.choose_table(IT.table_candidates(self.prof), self.live)[0][1][1], "DT_ItemParam")
        self.assertEqual([n for _a, n in IT.order_tables(self.live)][0], "DT_ItemParam")

    def test_reachable_function_wins_and_odd_ones_are_not_relevant(self):
        rated = IT.rate_functions(self.prof, self.sdk)
        by = {f"{r['sug'].data['owner']}.{r['sug'].data['name']}": r for r in rated}
        self.assertEqual(rated[0]["sug"].title, "UItemBagComponent.AddItem")          # Objekt ueber den PlayerController erreichbar
        self.assertEqual(rated[0]["reach"], "member")
        self.assertTrue(rated[0]["relevant"])
        self.assertEqual([r["sug"].title for r in rated if r["relevant"]], ["UItemBagComponent.AddItem"])
        sub = by["UMyInventorySubsystem.AddImportantItem"]
        self.assertEqual(sub["reach"], "zero")
        self.assertFalse(sub["relevant"])
        self.assertIn("Spezial-Items", sub["reasons"])
        self.assertIn("Objekt nicht erreichbar", sub["reasons"])
        self.assertIn("gehoert zur Anzeige", by["AItemModelViewActor.SpawnItem"]["reasons"])
        self.assertIn("kein normales Item-Geben", by["UMyCheatManager.AddSelectItem"]["reasons"])
        self.assertIn("kein normales Item-Geben", by["UMyCheatManager.AddPresetItem"]["reasons"])
        self.assertEqual(IT.function_label(rated[0]), "UItemBagComponent.AddItem  [Name + Menge]")

    def test_without_reachable_function_best_guess_is_still_offered_but_not_relevant(self):
        sdk = TP.sdk_from(TP.GAME_A)                                                  # GAME_A: nichts ueber den PlayerController
        rated = IT.rate_functions(P.build(sdk), sdk)
        self.assertTrue(rated)
        self.assertFalse(any(r["relevant"] for r in rated))


class FakeMem:
    """Kleiner Fake-Speicher fuer try_give: vtable von Objekt 0x1000 -> ProcessEvent 0x3000."""
    def __init__(self):
        self.m = bytearray(0x10000); self.nxt = 0x8000; self.freed = []
        struct.pack_into("<Q", self.m, 0x1000, 0x2000)
        struct.pack_into("<Q", self.m, 0x2000 + 8 * 77, 0x403000)
    def read_memory(self, a, n): return bytes(self.m[a:a + n])
    def write_memory(self, a, d): self.m[a:a + len(d)] = d
    def allocate_memory(self, n): a = self.nxt; self.nxt += n + 0x40; return a
    def free_memory(self, a, n): self.freed.append(a)


class FakeGameLive:
    index = {}
    def __init__(self, instances=(0x1000,)):
        self.inst = [{"addr": a, "name": f"Obj_{i}"} for i, a in enumerate(instances)]
    def find_function(self, owner, name): return 0xF00
    def instances(self, owner, **k): return self.inst
    def default_object(self, owner): return 0x1000


def item_fp(with_return=True):
    ms = [uesdk.Member("ItemName", "FName", 0, 8, pflags=0x80), uesdk.Member("Count", "int32", 8, 4, pflags=0x80)]
    if with_return:
        ms.append(uesdk.Member("ReturnValue", "bool", 0x10, 1, pflags=0x400))
    return uesdk.FuncParams("/Script/Game.ItemBagComponent.AddItem", 0x18, ms)


class TryGive(unittest.TestCase):
    """Test '1 Item geben': echte Instanz + ProcessEvent, Parameter aus Item und Menge."""
    def setUp(self):
        self.objs = [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_ItemParam.DT_ItemParam")]
        self.sdk = TP.sdk_from(GAME_C, self.objs)
        self.sdk.func_params = {"/Script/Game.ItemBagComponent.AddItem": item_fp()}
        self.prof = P.build(self.sdk)
        self.func = next(r["sug"] for r in IT.rate_functions(self.prof, self.sdk) if r["sug"].data["name"] == "AddItem"
                         and r["sug"].data["owner"] == "UItemBagComponent")
        self.item = {"name": "Item_A", "fname": bytes.fromhex("0b" + "00" * 7), "id": None, "category": "x"}

    def run_call(self, ret=1, live=None, mem=None):
        mem = mem or FakeMem(); seen = {}

        def caller(c, rip, obj, fn, params):
            seen.update(rip=rip, obj=obj, fn=fn, buf=c.read_memory(params, 0x18))
            c.write_memory(params + 0x10, bytes([ret]))                       # "Spiel" schreibt den bool-Rueckgabewert
            return 0
        res = IT.try_give(live or FakeGameLive(), mem, self.sdk, self.func, self.item, 0x400000, 7, caller)
        return res, seen, mem

    def test_item_and_amount_reach_the_call(self):
        res, seen, mem = self.run_call()
        self.assertEqual((seen["rip"], seen["obj"], seen["fn"]), (0x403000, 0x1000, 0xF00))
        self.assertEqual(seen["buf"][:8], bytes.fromhex("0b" + "00" * 7))                # FName aus der Tabellenzeile
        self.assertEqual(struct.unpack_from("<i", seen["buf"], 8)[0], 7)               # Menge
        self.assertFalse(res["returned_false"])
        self.assertEqual((res["instance"], res["reach"]), (0x1000, "member"))
        self.assertEqual(len(mem.freed), 1)

    def test_report_lists_object_parameters_and_bytes(self):
        res = self.run_call()[0]
        text = "\n".join(res["detail"])
        self.assertIn("Objekt: Obj_0 @ 0x1000", text)
        self.assertIn("Eingabe: ItemName (FName) @+0x0 = 0b 00 00 00 00 00 00 00", text)
        self.assertIn("Eingabe: Count (int32) @+0x8 = 07 00 00 00", text)
        self.assertIn("Rueckgabe: ReturnValue (bool)", text)

    def test_unusual_amount_name_is_still_filled(self):
        sdk = TP.sdk_from("".join([TP.cls("UBagComp", "UActorComponent", [], ["void AddItemToBag(class FName ItemName, int32 Value);"])]))
        func = next(s for s in IT.give_candidates(P.build(sdk), sdk)[0])
        fp = uesdk.FuncParams("/Script/Game.BagComp.AddItemToBag", 0xC,
                              [uesdk.Member("ItemName", "FName", 0, 8, pflags=0x80), uesdk.Member("Value", "int32", 8, 4, pflags=0x80)])
        got = IT.test_assignments(func, fp, {"fname": bytes(8), "id": None}, 5, sdk)
        self.assertEqual(got["Value"], "5")

    def test_give_many_calls_once_per_item_and_counts_rejections(self):
        mem, seen = FakeMem(), []
        items = [dict(self.item, name=f"Item_{i}", fname=bytes([i + 1]) + bytes(7)) for i in range(3)]

        def caller(c, rip, obj, fn, params):
            seen.append(c.read_memory(params, 0x18))
            c.write_memory(params + 0x10, bytes([0 if len(seen) == 2 else 1]))      # das 2. Item lehnt das Spiel ab
            return 0
        done = []
        res = IT.give_many(FakeGameLive(), mem, self.sdk, self.func, items, 0x400000, 9, lambda n, t: done.append((n, t)), caller)
        self.assertEqual((res["total"], res["given"], res["rejected"], res["skipped"]), (3, 2, ["Item_1"], []))
        self.assertEqual([struct.unpack_from("<i", b, 8)[0] for b in seen], [9, 9, 9])
        self.assertEqual([b[0] for b in seen], [1, 2, 3])
        self.assertEqual(done[-1], (3, 3))
        self.assertEqual(len(mem.freed), 3)                                          # jeder Puffer freigegeben

    def test_false_return_is_reported(self):
        self.assertTrue(self.run_call(ret=0)[0]["returned_false"])

    def test_clear_errors(self):
        with self.assertRaises(ValueError) as c:
            IT.try_give(FakeGameLive(instances=()), FakeMem(), self.sdk, self.func, self.item, 0x400000)
        self.assertIn("kein Objekt der Klasse UItemBagComponent", str(c.exception))
        self.sdk.func_params = {}
        with self.assertRaises(ValueError) as c:
            IT.try_give(FakeGameLive(), FakeMem(), self.sdk, self.func, self.item, 0x400000)
        self.assertIn("Parameter-Layout", str(c.exception))

    def test_number_id_functions(self):
        sdk = TP.sdk_from(TP.GAME_B)
        func = next(s for s in IT.give_candidates(P.build(sdk), sdk)[0] if s.data["name"] == "GiveItemById")
        fp = uesdk.FuncParams("/Script/Game.MyGameMode.GiveItemById", 8,
                              [uesdk.Member("ItemID", "int32", 0, 4, pflags=0x80), uesdk.Member("Amount", "int32", 4, 4, pflags=0x80)])
        self.assertEqual(IT.test_assignments(func, fp, {"fname": b"", "id": 42}, 3, sdk), {"ItemID": "42", "Amount": "3"})
        with self.assertRaises(ValueError):
            IT.test_assignments(func, fp, {"fname": b"", "id": None}, 3, sdk)

    def test_verified_changes_ranking_and_label(self):
        key = IT.func_key(self.func)
        base = {r["sug"].title: r for r in IT.rate_functions(self.prof, self.sdk)}
        ok = {r["sug"].title: r for r in IT.rate_functions(self.prof, self.sdk, {key: "ok"})}
        bad = {r["sug"].title: r for r in IT.rate_functions(self.prof, self.sdk, {key: "fail"})}
        self.assertEqual(ok[key]["score"], base[key]["score"] + 4)
        self.assertIn("✔ getestet", IT.function_label(ok[key]))
        self.assertFalse(bad[key]["relevant"])
        self.assertIn("Test fehlgeschlagen", bad[key]["reasons"])
        self.assertNotEqual(IT.rate_functions(self.prof, self.sdk, {key: "fail"})[0]["sug"].title, key)


class FakeLiveFn:
    def function_entry(self, owner, name): return (0x1234, None)


class BuildTrainer(unittest.TestCase):
    def setUp(self):
        self.sdk = TP.sdk_from(TP.GAME_A, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_Items.DT_Items")])
        self.prof = P.build(self.sdk)
        self.img = TS.FakeImage()
        self.orig = CG.find_impl
        CG.find_impl = lambda read, base, thunk: self.img.impl
        self.addCleanup(setattr, CG, "find_impl", self.orig)
        self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_options_plan_and_files(self):
        ok, _ = IT.give_candidates(self.prof, self.sdk)
        func = next(s for s in ok if s.data["name"] == "GiveItem")
        names = [f"Item_Fish_{i}" for i in range(20)] + [f"Item_Weapon_{i}" for i in range(5)]
        its = IT.build_items(rows(names))
        pk = IT.packages(IT.group_items(its))
        opts, skipped = IT.make_options(pk, func, self.sdk, FakeLiveFn(), self.img.read, self.img.BASE, 999)
        self.assertEqual([o.name for o in opts], ["Fish 1", "Fish 2", "Weapon"])
        self.assertEqual(skipped, 0)
        self.assertEqual([len(o.rows) for o in opts], [14, 6, 5])
        row = opts[0].rows[0]
        self.assertEqual((row.amount, row.spec.function), (999, "UMyCheatManager.GiveItem"))
        self.assertEqual(row.fname, bytes.fromhex("01" + "00" * 7))             # FName der ersten Tabellenzeile
        p = TR.plan(self.img.read, self.img.maps, self.img.BASE, opts, None, self.img.pe, [self.img.slot],
                    log=lambda _m: None, settle=0)
        files = TR.write_project(os.path.join(self.tmp, "Items"), p, game="Testspiel")
        self.assertTrue(any("Fish 1" in f for f in files), files)
        self.assertTrue(any("Weapon" in f for f in files))

    BAG = TP.cls("UDMXInventory", "UObject", [], [
        "int32_t AddItemToBackPack(struct FName ItemId, int32_t Add, struct FName WorkId, bool bCallEvent);",
        "int32_t AddItemInBackPackItemList(int32_t SlotIndex, struct FName ItemId, int32_t Add, struct FName WorkId);"])

    def test_real_world_signature_add_item_to_backpack(self):
        """AddItemToBackPack(FName ItemId, int32 Add, FName WorkId, bool bCallEvent): Add ist die Menge, WorkId bleibt leer."""
        sdk = TP.sdk_from(self.BAG)
        prof = P.build(sdk)
        func = next(s for s in IT.give_candidates(prof, sdk)[0] if s.data["name"] == "AddItemToBackPack")
        roles = {a["name"]: a["role"] for a in CG.classify_params(func.data["params"], sdk)}
        self.assertEqual(roles, {"ItemId": "id", "Add": "count", "WorkId": "id", "bCallEvent": "other"})
        fp = uesdk.FuncParams("/Script/Game.Inv.AddItemToBackPack", 0x1C, [
            uesdk.Member("ItemId", "FName", 0, 8, pflags=0x80), uesdk.Member("Add", "int32", 8, 4, pflags=0x80),
            uesdk.Member("WorkId", "FName", 0xC, 8, pflags=0x80), uesdk.Member("bCallEvent", "bool", 0x14, 1, pflags=0x80),
            uesdk.Member("ReturnValue", "int32", 0x18, 4, pflags=0x400)])
        got = IT.test_assignments(func, fp, {"fname": bytes.fromhex("54d0040000000000"), "id": None}, 3, sdk)
        self.assertEqual(got, {"ItemId": "hex:54d0040000000000", "Add": "3"})          # WorkId / bCallEvent nicht angefasst

    def test_trainer_row_for_two_fname_parameters_builds(self):
        sdk = TP.sdk_from(self.BAG)
        func = next(s for s in IT.give_candidates(P.build(sdk), sdk)[0] if s.data["name"] == "AddItemToBackPack")
        pk = [("A", [{"name": "ItemX", "fname": bytes.fromhex("01" + "00" * 7), "id": None, "category": "A"}])]
        opts, _ = IT.make_options(pk, func, sdk, FakeLiveFn(), self.img.read, self.img.BASE, 50)
        args = {a["name"]: a["value"] for a in opts[0].rows[0].spec.args}
        self.assertEqual(args["Add"], 50)                                                # Menge kommt in 'Add' an
        self.assertEqual(args["WorkId"], bytes(8))                                       # zweiter FName: leer, kein Fehler
        self.assertEqual(args["ItemId"], bytes.fromhex("01" + "00" * 7))

    def test_slot_index_is_not_the_item_id(self):
        sdk = TP.sdk_from(self.BAG)
        func = next(s for s in IT.give_candidates(P.build(sdk), sdk)[0] if s.data["name"] == "AddItemInBackPackItemList")
        roles = {a["name"]: a["role"] for a in CG.classify_params(func.data["params"], sdk)}
        self.assertEqual(roles, {"SlotIndex": "other", "ItemId": "id", "Add": "count", "WorkId": "id"})

    def test_missing_function_and_impl_give_clear_errors(self):
        ok, _ = IT.give_candidates(self.prof, self.sdk)
        pk = [("A", [{"name": "x", "fname": bytes([1] * 8), "id": 1, "category": "A"}])]

        class NoFn:
            def function_entry(self, o, n): return None
        with self.assertRaises(ValueError) as c:
            IT.make_options(pk, ok[0], self.sdk, NoFn(), self.img.read, self.img.BASE, 5)
        self.assertIn("nicht gefunden", str(c.exception))
        CG.find_impl = lambda read, base, thunk: None
        with self.assertRaises(ValueError) as c:
            IT.make_options(pk, ok[0], self.sdk, FakeLiveFn(), self.img.read, self.img.BASE, 5)
        self.assertIn("native Implementierung", str(c.exception))


if __name__ == "__main__":
    unittest.main()
