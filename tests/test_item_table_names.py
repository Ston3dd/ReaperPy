"""Tests: Erkennung von Item-Tabellen allein am Namen - fuer JEDES Spiel gleich, ohne spielspezifische Namen."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ue_items as I

ITEM_TABLES = """DT_ItemParam DT_Item ItemMaster DT_WeaponData DT_Armor ItemTable DT_Consumables DT_ITEMPARAM DT_Goods DT_GOODS
ITEM_DATA ItemDataTable DT_Equipment EquipParam DT_Loot DT_Items_Weapons WeaponDataTable DT_Gear MstItem mst_item MSTITEM
DT_Inventory DT_Pickups Itm_Master DT_Wpn DT_Eqp DT_Armr DT_Ammo DT_Currency DT_Resource DT_Ingredient FoodTable DT_Accessory
DT_Relic DT_Potion DT_ConsumableItem DT_KeyItems DT_CraftingIngredients DT_Materials DT_Tools DT_WeaponParam_Sword ItemList_Main
DT_ItemInfo DT_Items_Consumable DT_ITEM DT_WEAPON DT_Gold DT_Coin DT_Cosmetics DT_Outfit DT_Recipes DT_Shop DT_ITEMDATATABLE
MSTWEAPON""".split()

NOT_ITEM_TABLES = """DT_UIMapParam DT_FxParam DT_EnemyParam DT_AWARENESSPARAM DT_PhysicalMaterial DT_SurfaceMaterial DT_MATERIALINSTANCE
DT_ToolTip DT_ToolTipText DT_Toolbar DT_ToolbarLayout DT_SoftwareInfo DT_HardwareSettings DT_Hardware DT_Beware DT_Coincidence
DT_GoldenHour DT_Itemize DT_DamageType DT_Sound DT_Dialogue DT_Quest DT_Skill DT_Camera DT_Level DT_Stage DT_Achievements
DT_GameplayTags DT_Questionnaire DT_Lighting DT_Weather DT_Foliage DT_Landscape DT_Mesh DT_SkeletalMesh DT_Decal DT_NPCSchedule
DT_Gamepad DT_Difficulty DT_Credits DT_Localization DT_LoadingTips""".split()

PRESENTATION_OF_ITEMS = ["DT_ItemIcon", "DT_ITEMICON", "DT_ItemTooltipText", "DT_ItemShopUI", "DT_ITEMTEXT"]


class TableNames(unittest.TestCase):
    def test_item_tables_are_found_on_both_levels(self):
        for level in (I.LEVEL_STRICT, I.LEVEL_NORMAL):
            for name in ITEM_TABLES:
                self.assertGreaterEqual(I.table_relevance(name, "", (), level), I.rel_min(level), (level, name))

    def test_other_tables_are_not_taken_for_items(self):
        for level in (I.LEVEL_STRICT, I.LEVEL_NORMAL):
            for name in NOT_ITEM_TABLES:
                self.assertLess(I.table_relevance(name, "", (), level), I.rel_min(level), (level, name))

    def test_presentation_tables_next_to_an_item_word_are_dropped(self):
        for level in (I.LEVEL_STRICT, I.LEVEL_NORMAL):
            for name in PRESENTATION_OF_ITEMS:
                self.assertLess(I.table_relevance(name, "", (), level), I.rel_min(level), (level, name))

    def test_normal_level_keeps_item_lists_with_a_soft_negative_word(self):
        for name in ("DT_ItemSkill", "DT_CharacterItem", "DT_ItemQuest"):
            self.assertGreaterEqual(I.table_relevance(name, "", (), I.LEVEL_NORMAL), I.rel_min(I.LEVEL_NORMAL), name)

    def test_off_level_keeps_everything(self):
        self.assertEqual(I.rel_min(I.LEVEL_OFF), float("-inf"))

    def test_run_together_names_are_split_into_known_words(self):
        self.assertEqual(I._split_tokens("DT_ITEMPARAM"), ["dt", "item", "param"])
        self.assertEqual(I._split_tokens("mstitem"), ["mst", "item"])
        self.assertEqual(I._split_tokens("DT_WEAPONDATATABLE"), ["dt", "weapon", "datatable"])

    def test_unknown_words_are_not_cut_up(self):
        for name in ("DT_SoftwareInfo", "DT_Toolbar", "DT_Itemize", "DT_AWARENESS"):
            toks = I._split_tokens(name)
            self.assertNotIn("ware", toks, name)
            self.assertNotIn("tool", toks, name)
            self.assertNotIn("item", toks, name)

    def test_selection_list_knows_abbreviations_and_ignores_lookalikes(self):
        tables = [(1, "DT_Wpn"), (2, "DT_Eqp"), (3, "DT_ItemParam"), (4, "DT_SoftwareInfo"), (5, "DT_Toolbar"), (6, "DT_Enemy")]
        names = [n for _a, n in I.order_tables(tables, I.LEVEL_NORMAL)]
        self.assertIn("DT_Wpn", names)
        self.assertIn("DT_Eqp", names)
        self.assertIn("DT_ItemParam", names)
        self.assertNotIn("DT_SoftwareInfo", names)
        self.assertNotIn("DT_Toolbar", names)

    def test_rating_orders_the_best_table_first(self):
        tables = [(1, "DT_Sound"), (2, "DT_ItemParam"), (3, "DT_Wpn"), (4, "DT_UIParam")]
        rated = I.rate_tables([], tables, I.LEVEL_NORMAL)
        self.assertEqual(rated[0]["name"], "DT_ItemParam")
        self.assertEqual({r["name"] for r in rated if r["relevant"]}, {"DT_ItemParam", "DT_Wpn"})


if __name__ == "__main__":
    unittest.main()
