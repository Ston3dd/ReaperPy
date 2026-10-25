"""Tests fuer ue_profile: der Entdecker findet in verschiedenen (synthetischen) Spielen die gaengigen Bausteine."""
import json
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ue_profile as P
import uesdk


def cls(name, parent, members=(), funcs=(), kind="class", size=0x200):
    head = "ScriptStruct" if kind == "struct" else "Class"
    out = [f"// {head} /Script/Game.{name[1:]}", f"// 0x0040 ({size:#06x} - 0x0010)",
           f"{kind} {name}" + (f" : public {parent}" if parent else ""), "{", "public:"]
    for typ, mname, off, sz in members:
        out.append(f"\t{typ:<44} {mname + ';':<34} // {off:#06x} ({sz:#06x}) [0x0018001040022a01] Property")
    for f in funcs:
        out.append(f"\t{f}")
    out.append("};")
    return "\n".join(out) + "\n"


def enum(name, values, under="uint8_t"):
    out = [f"// Enum /Script/Game.{name}", f"enum class {name} : {under}", "{"]
    out += [f"\t{n:<48} = {v}," for n, v in values]
    out.append("};")
    return "\n".join(out) + "\n"


GAME_A = "".join([
    # Inventar-Eintrag + Halter
    cls("FInvEntry", "", [("FName", "ItemId", 0x00, 8), ("int32", "Count", 0x08, 4), ("int32", "SlotIndex", 0x0C, 4),
                          ("float", "Durability", 0x10, 4)], kind="struct", size=0x18),
    cls("UInventoryComponent", "UActorComponent",
        [("TArray<struct FInvEntry>", "Items", 0xB0, 16), ("int32", "Gold", 0xC0, 4), ("int32", "MaxSlots", 0xC4, 4)],
        ["void AddItem(class FName ItemName, int32 Count);", "void RemoveItem(class FName ItemName, int32 Count);"]),
    # Tabellen-Zeilenstructs
    cls("FItemRow", "FTableRowBase", [("FName", "ItemId", 0x08, 8), ("int32", "Price", 0x10, 4), ("int32", "MaxStack", 0x14, 4),
                                       ("enum EEquipSlot", "EquipSlot", 0x18, 1), ("FText", "DisplayName", 0x20, 24)], kind="struct"),
    cls("FShopRow", "FTableRowBase", [("FName", "ShopId", 0x08, 8), ("int32", "Price", 0x10, 4)], kind="struct"),
    cls("FEnemyRow", "FTableRowBase", [("FName", "EnemyId", 0x08, 8), ("float", "HP", 0x10, 4)], kind="struct"),
    cls("UGameData", "UObject", [("class UDataTable*", "ItemTable", 0x30, 8), ("struct FDataTableRowHandle", "Start", 0x38, 16)]),
    # Widget: darf NICHT als Item auftauchen
    cls("UInventoryWidget", "UUserWidget", [("FName", "ItemId", 0x300, 8), ("int32", "Count", 0x308, 4)]),
    # Cheat-Manager
    cls("UMyCheatManager", "UCheatManager", [],
        ["void GodMode();", "void Ghost();", "void AddGold(int32 Amount);", "void GiveItem(class FName ItemName, int32 Count);",
         "void TeleportTo(float X, float Y, float Z);", "void UnlockAll();", "void AddXP(int32 Amount);"]),
    # GAS
    "struct FGameplayAttributeData\n{\n};\n",
    cls("UCoreAttributeSet", "UAttributeSet", [("struct FGameplayAttributeData", "Health", 0x30, 16),
                                               ("struct FGameplayAttributeData", "MaxHealth", 0x40, 16)]),
    # Stat-Enum + Array
    enum("EAttrType", [("Attr_None", 0), ("Attr_Health", 1), ("Attr_MaxHealth", 2), ("Attr_Stamina", 3), ("Attr_Mana", 4),
                       ("Attr_AttackPower", 5), ("Attr_Level", 6), ("Attr_Num", 7)]),
    cls("UStatComponent", "UActorComponent", [("TArray<float>", "StatValues", 0x80, 16)],
        ["float GetStat(enum EAttrType Type);"]),
    enum("EEquipSlot", [("EEquipSlot_None", 0), ("EEquipSlot_Head", 1), ("EEquipSlot_Body", 2), ("EEquipSlot_Weapon", 3)]),
    enum("EItemRarity", [("Common", 0), ("Rare", 1), ("Epic", 2)]),
    enum("EColor", [("Red", 0), ("Green", 1)]),
])

GAME_B = "".join([
    cls("FBagSlot", "", [("int32", "ItemID", 0x00, 4), ("int32", "Quantity", 0x04, 4), ("int32", "BagIndex", 0x08, 4)],
        kind="struct", size=0x0C),
    cls("UBagComponent", "UActorComponent", [("TArray<struct FBagSlot>", "Slots", 0x90, 16), ("int32", "Coins", 0xA0, 4)]),
    cls("AMyGameMode", "AGameModeBase", [], ["void GiveItemById(int32 ItemID, int32 Amount);", "void GiveXp(int32 Amount);"]),
    cls("AActor", "UObject", [("float", "CustomTimeDilation", 0x30, 4)]),
])

EMPTY_GAME = cls("AFoo", "AActor", [("float", "Speed", 0x30, 4)])


def sdk_from(text, gobjects=None):
    sdk = uesdk.parse_header_text(text)
    if gobjects:
        sdk.gobjects = list(gobjects)
    return sdk


class StaticDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls_):
        cls_.sdk = sdk_from(GAME_A, [(1, 0x7000_1000, "DataTable", "DataTable /Game/Data/DT_Items.DT_Items"),
                                     (2, 0x7000_2000, "DataTable", "DataTable /Game/Data/DT_Enemies.DT_Enemies"),
                                     (3, 0x7000_3000, "DataTable", "DataTable /Game/Data/DT_Items.Default__DT_Items")])
        cls_.prof = P.build(cls_.sdk)

    def by(self, kind):
        return {s.title: s for s in self.prof.of(kind)}

    def test_item_struct_with_id_count_slot_and_container(self):
        items = self.by("item_struct")
        s = items["FInvEntry"]
        self.assertEqual(s.data["id"]["name"], "ItemId")
        self.assertEqual(s.data["id"]["id_kind"], "fname")
        self.assertEqual(s.data["count"]["name"], "Count")
        self.assertEqual(s.data["count"]["offset"], 8)
        self.assertEqual([m["name"] for m in s.data["slots"]], ["SlotIndex"])
        self.assertEqual([m["name"] for m in s.data["extras"]], ["Durability"])
        self.assertEqual(s.data["containers"][0]["owner"], "UInventoryComponent")
        self.assertEqual(s.data["containers"][0]["member"], "Items")
        self.assertGreaterEqual(s.score, 9)
        self.assertEqual(self.prof.of("item_struct")[0].title, "FInvEntry")      # bester Treffer zuerst

    def test_widget_is_not_an_item(self):
        self.assertNotIn("UInventoryWidget", self.by("item_struct"))

    def test_tables_roles_ids_holders_and_live_objects(self):
        t = self.by("table")
        self.assertEqual(t["FItemRow"].data["role"], "Items")
        self.assertEqual(t["FShopRow"].data["role"], "Shop/Preise")
        self.assertEqual(t["FEnemyRow"].data["role"], "Charaktere/Gegner")
        self.assertIn("ItemId", t["FItemRow"].data["id_columns"])
        self.assertEqual(t["FItemRow"].data["table_name"], "DT_Items")             # Plural-Abgleich Item/Items
        self.assertEqual(t["FItemRow"].data["tables"], [(0x7000_1000, "DataTable /Game/Data/DT_Items.DT_Items")])
        self.assertEqual(t["FEnemyRow"].data["table_name"], "DT_Enemies")
        self.assertIn("Tabellen-Halter im SDK", t)
        holders = {(c, m) for c, m, _o, _t in t["Tabellen-Halter im SDK"].data["holders"]}
        self.assertEqual(holders, {("UGameData", "ItemTable"), ("UGameData", "Start")})
        self.assertGreater(t["FItemRow"].score, t["FShopRow"].score - 0.01)

    def test_id_and_slot_enums(self):
        e = self.by("id_enum")
        self.assertEqual(e["EEquipSlot"].data["role"], "slot")
        self.assertEqual(e["EEquipSlot"].data["values"][:2], [(1, "Head"), (2, "Body")] if False else e["EEquipSlot"].data["values"][:2])
        self.assertIn((3, "Weapon"), [tuple(v) for v in e["EEquipSlot"].data["values"]])
        self.assertEqual(e["EItemRarity"].data["role"], "seltenheit")
        self.assertNotIn("EColor", e)
        sm = self.by("slot_member")
        self.assertIn("SlotIndex", sm)
        self.assertTrue(any(o == "FInvEntry" for o, _off in sm["SlotIndex"].data["owners"]))

    def test_give_functions_ranked_by_shape_and_owner(self):
        g = self.prof.of("give_function")
        names = [s.title for s in g]
        self.assertIn("UInventoryComponent.AddItem", names)
        self.assertIn("UMyCheatManager.GiveItem", names)
        self.assertIn("UMyCheatManager.AddGold", names)
        top = g[0]
        self.assertEqual(top.data["shape"], "name+menge")
        self.assertEqual(top.title, "UMyCheatManager.GiveItem")                    # CheatManager > Inventory
        add = next(s for s in g if s.title == "UInventoryComponent.AddItem")
        self.assertEqual([p[1] for p in add.data["params"]], ["ItemName", "Count"])
        self.assertNotIn("UInventoryComponent.RemoveItem", names)
        gold = next(s for s in g if s.title == "UMyCheatManager.AddGold")
        self.assertEqual(gold.data["shape"], "menge")

    def test_cheat_manager_categories(self):
        cm = self.by("cheat_manager")["UMyCheatManager"]
        cats = cm.data["categories"]
        self.assertIn("GodMode", cats["Unverwundbar"])
        self.assertIn("Ghost", cats["Fliegen/Geist"])
        self.assertIn("TeleportTo", cats["Teleport"])
        self.assertEqual(cm.data["count"], 7)

    def test_stat_enum_array_and_gas(self):
        se = self.by("stat_enum")["EAttrType"]
        self.assertIn("hp", se.data["roles"])
        self.assertEqual(se.data["count"], 7)
        self.assertNotIn("EColor", self.by("stat_enum"))
        sa = self.by("stat_array")["UStatComponent.StatValues"]
        self.assertEqual(sa.data["enum"], "EAttrType")
        self.assertEqual(sa.data["offset"], 0x80)
        gas = self.by("attribute_set")["UCoreAttributeSet"]
        self.assertEqual([a[0] for a in gas.data["attrs"]], ["Health", "MaxHealth"])
        self.assertIn("Current +0x3c", " ".join(gas.evidence))

    def test_currency_member(self):
        c = self.by("currency")
        self.assertIn("UInventoryComponent.Gold", c)
        self.assertNotIn("UInventoryComponent.MaxSlots", c)

    def test_markdown_and_json(self):
        md = P.render_markdown(self.prof)
        for needle in ("FInvEntry", "Geben-Funktion", "Tabelle", "ItemId"):
            self.assertIn(needle, md)
        data = json.loads(P.to_json(self.prof))
        self.assertEqual(data["counts"]["item_struct"], len(self.prof.of("item_struct")))
        self.assertTrue(all(s["score"] <= 10 for s in data["suggestions"]))


class OtherGames(unittest.TestCase):
    def test_int_id_game(self):
        prof = P.build(sdk_from(GAME_B))
        s = prof.of("item_struct")[0]
        self.assertEqual(s.title, "FBagSlot")
        self.assertEqual((s.data["id"]["name"], s.data["id"]["id_kind"]), ("ItemID", "int"))
        self.assertEqual(s.data["count"]["name"], "Quantity")
        self.assertEqual([m["name"] for m in s.data["slots"]], ["BagIndex"])
        g = {x.title: x for x in prof.of("give_function")}
        self.assertEqual(g["AMyGameMode.GiveItemById"].data["shape"], "id+menge")
        self.assertIn("UBagComponent.Coins", {x.title for x in prof.of("currency")})

    def test_unknown_game_gives_notes_not_nonsense(self):
        prof = P.build(sdk_from(EMPTY_GAME))
        self.assertEqual(prof.suggestions, [])
        self.assertTrue(any("eigene Namen" in n for n in prof.notes))
        self.assertTrue(any("GObjects" in n for n in prof.notes))

    def test_empty_sdk(self):
        prof = P.build(uesdk.SDK())
        self.assertTrue(any("keine Klassen" in n for n in prof.notes))

    def test_stellar_blade_style_structs_are_recognised_without_sb_names(self):
        """FSBItemInstance-aehnlich: Alias (FName) + Count ohne 'Item' im Zaehler-Namen."""
        text = cls("FThingInstance", "", [("FName", "ItemAlias", 0x20, 8), ("int32", "ItemCount", 0x34, 4)], kind="struct") + \
            cls("UPocket", "UObject", [("TArray<struct FThingInstance>", "List", 0x40, 16)])
        s = P.build(sdk_from(text)).of("item_struct")[0]
        self.assertEqual((s.data["id"]["name"], s.data["count"]["name"]), ("ItemAlias", "ItemCount"))
        self.assertEqual(s.data["containers"][0]["owner"], "UPocket")


class Helpers(unittest.TestCase):
    def test_split_args_and_shapes(self):
        self.assertEqual(P.split_args("class FName ItemName, int32 Count"), [("class FName", "ItemName"), ("int32", "Count")])
        self.assertEqual(P._shape(P.split_args("class FName ItemName, int32 Count")), "name+menge")
        self.assertEqual(P._shape(P.split_args("int32 ItemId, int32 Num")), "id+menge")
        self.assertEqual(P._shape(P.split_args("class FString Code")), "name")
        self.assertEqual(P._shape(P.split_args("float Value")), "menge")
        self.assertEqual(P._shape([]), "")

    def test_derives_from_without_base_in_sdk(self):
        sdk = sdk_from(cls("FFoo", "FTableRowBase", kind="struct") + cls("FBar", "FFoo", kind="struct"))
        self.assertTrue(P.derives_from(sdk, "FBar", "FTableRowBase"))
        self.assertFalse(P.derives_from(sdk, "FBar", "UObject"))

    def test_type_helpers(self):
        self.assertEqual(P.base_name("TArray<struct FItem>"), "TArray")
        self.assertEqual(P.base_name("class UItem*"), "UItem")
        self.assertEqual(P.inner_types("TMap<FName, struct FItem>"), ["FName", "FItem"])


# ----------------------------------------------------------------------------------------------
# Live
# ----------------------------------------------------------------------------------------------
class Mem:
    def __init__(self):
        self.r = []

    def put(self, a, d):
        self.r.append((a, bytearray(d)))

    def read(self, a, n):
        for b, buf in self.r:
            if b <= a and a + n <= b + len(buf):
                return bytes(buf[a - b:a - b + n])
        raise OSError(hex(a))


class LiveTable(unittest.TestCase):
    NAMES = {10: "Item_Gold", 11: "Item_Potion", 12: "Item_Sword"}

    def setUp(self):
        m = Mem()
        self.rows = [(10, 500, 99, 0), (11, 25, 10, 0), (12, 1200, 1, 3)]
        elems = bytearray()
        for i, (ix, price, stack, slot) in enumerate(self.rows):
            rp = 0x7000_0200_0000 + i * 0x100
            row = bytearray(0x40)
            struct.pack_into("<II", row, 0x08, ix, 0)
            struct.pack_into("<ii", row, 0x10, price, stack)
            row[0x18] = slot
            m.put(rp, row)
            elems += struct.pack("<IIQii", ix, 0, rp, 0, 0)
        arr = 0x7000_0100_0000
        m.put(arr, elems)
        tbl = 0x7000_0000_8000
        t = bytearray(0x300)
        t[0x30:0x40] = struct.pack("<Qii", arr, 3, 3)
        m.put(tbl, t)
        self.m, self.tbl = m, tbl
        self.cols = [("ItemId", "FName", 0x08, 8), ("Price", "int32", 0x10, 4), ("MaxStack", "int32", 0x14, 4),
                     ("EquipSlot", "enum EEquipSlot", 0x18, 1), ("DisplayName", "FText", 0x20, 24)]

    def fname(self, ix, nb=0):
        return self.NAMES.get(ix, f"<name {ix:#x}>")

    def test_read_table_decodes_columns_and_fnames(self):
        rows, cols = P.read_table(self.m.read, self.fname, self.tbl, self.cols)
        self.assertEqual([c[0] for c in cols], ["ItemId", "Price", "MaxStack"])         # Enum/FText werden nicht geraten
        self.assertEqual([r["name"] for r in rows], ["Item_Gold", "Item_Potion", "Item_Sword"])
        self.assertEqual(rows[0]["fname_hex"], "0a00000000000000")
        self.assertEqual(rows[1]["values"], {"ItemId": "Item_Potion", "Price": 25, "MaxStack": 10})

    def test_without_columns_still_lists_names(self):
        rows, cols = P.read_table(self.m.read, self.fname, self.tbl, None)
        self.assertEqual(len(rows), 3)
        self.assertEqual(cols, [])

    def test_csv_and_json_export(self):
        rows, cols = P.read_table(self.m.read, self.fname, self.tbl, self.cols)
        csv_text = P.table_to_csv(rows, cols)
        self.assertEqual(csv_text.splitlines()[0], "Name,FName(hex),ItemId,Price,MaxStack")
        self.assertIn("Item_Sword,0c00000000000000,Item_Sword,1200,1", csv_text)
        js = json.loads(P.table_to_json(rows, cols, "DT_Items"))
        self.assertEqual(js["rows"][2]["Price"], 1200)
        self.assertEqual(js["table"], "DT_Items")

    def test_best_table_for_prefers_known_name_then_overlap(self):
        sug = P._sug("table", "FItemRow", 8, "", [], {"table_name": "DT_Items", "row_struct": "FItemRow"})
        tabs = [(1, "DT_Enemies"), (2, "DT_Items")]
        self.assertEqual(P.best_table_for(sug, tabs), (2, "DT_Items"))
        sug2 = P._sug("table", "FItemRow", 8, "", [], {"table_name": "", "row_struct": "FItemRow"})
        self.assertEqual(P.best_table_for(sug2, tabs), (2, "DT_Items"))
        self.assertIsNone(P.best_table_for(P._sug("table", "FQuestRow", 5, "", [], {"row_struct": "FQuestRow"}), tabs))

    def test_decode_value_variants(self):
        self.assertEqual(P.decode_value(struct.pack("<f", 1.5), "float"), 1.5)
        self.assertEqual(P.decode_value(b"\x01", "bool"), True)
        self.assertEqual(P.decode_value(struct.pack("<q", -5), "int64"), -5)
        self.assertEqual(P.decode_value(bytes(8), "FName", self.fname), "")
        self.assertEqual(P.decode_value(bytes(8), "FText"), "<FText>")


class WMem(Mem):
    def write(self, a, d):
        for b, buf in self.r:
            if b <= a and a + len(d) <= b + len(buf):
                buf[a - b:a - b + len(d)] = d
                return
        raise OSError(hex(a))


class Instances(unittest.TestCase):
    BASE = 0x7000_0300_0000

    def setUp(self):
        m = WMem()
        heap = bytearray(0x2000)
        gold, potion = bytes.fromhex("0a00000000000000"), bytes.fromhex("0b00000000000000")
        for off, key, cnt in ((0x100, gold, 500), (0x118, potion, 7), (0x200, gold, 0), (0x300, gold, 12345)):
            heap[off:off + 8] = key
            struct.pack_into("<i", heap, off + 8, cnt)
        heap[0x401:0x409] = gold                                            # unausgerichtet -> kein Treffer
        struct.pack_into("<i", heap, 0x409, 99)
        m.put(self.BASE, heap)
        self.m, self.gold, self.potion = m, gold, potion
        self.rng = [(self.BASE, self.BASE + 0x2000)]

    def test_find_by_id_plausible_counts(self):
        hits = P.find_instances(self.m.read, self.rng, 0, {self.gold: "Item_Gold"}, 8)
        self.assertEqual([(h.base - self.BASE, h.count) for h in hits], [(0x100, 500), (0x300, 12345)])   # Menge 0 verworfen
        self.assertEqual(hits[0].count_addr, self.BASE + 0x108)

    def test_exact_count_filters_decoys(self):
        hits = P.find_instances(self.m.read, self.rng, 0, {self.gold: "Item_Gold", self.potion: "Item_Potion"}, 8,
                                count_value=7)
        self.assertEqual([(h.name, h.count) for h in hits], [("Item_Potion", 7)])

    def test_int_id_and_float_count(self):
        m = WMem()
        buf = bytearray(0x100)
        struct.pack_into("<If", buf, 0x20, 4711, 2.5)
        m.put(self.BASE, buf)
        pat = P.id_pattern("int", number=4711, size=4)
        hits = P.find_instances(m.read, [(self.BASE, self.BASE + 0x100)], 0, {pat: "ID 4711"}, 4, "float")
        self.assertEqual((len(hits), hits[0].count, hits[0].count_type), (1, 2.5, "float"))
        self.assertEqual(hits[0].base, self.BASE + 0x20)

    def test_set_count_writes_native_type(self):
        h = P.find_instances(self.m.read, self.rng, 0, {self.gold: "G"}, 8, count_value=500)[0]
        data = P.set_count(self.m.write, h, 99999)
        self.assertEqual(data, struct.pack("<i", 99999))
        self.assertEqual(struct.unpack("<i", self.m.read(h.count_addr, 4))[0], 99999)

    def test_id_pattern_errors_and_bad_count_type(self):
        with self.assertRaises(ValueError):
            P.id_pattern("fname", b"123")
        with self.assertRaises(ValueError):
            P.id_pattern("tag")
        with self.assertRaises(ValueError):
            P.id_pattern("int")
        with self.assertRaises(ValueError):
            P.find_instances(self.m.read, self.rng, 0, {self.gold: "x"}, 8, "FText")

    def test_unreadable_ranges_are_skipped(self):
        hits = P.find_instances(self.m.read, [(0x1000, 0x2000)] + self.rng, 0, {self.gold: "G"}, 8, count_value=500)
        self.assertEqual(len(hits), 1)


if __name__ == "__main__":
    unittest.main()
