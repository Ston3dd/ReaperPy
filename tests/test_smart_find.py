"""smart_find.py: intelligentes Finden (andere Sprachen, Abkuerzungen, Tippfehler, Klasse traegt den Namen, Geschwister-Logik,
Verschleierung) und seine Einbindung in Unity (values_auto, unity_cheatmenu, unity_items) und Unreal (uecheat) - ohne Konsole."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import il2cpp_dump as D  # noqa: E402
import smart_find as SF  # noqa: E402
import test_unity_items as TU  # noqa: E402
import uecheat as UC  # noqa: E402
import unity_cheatmenu as UM  # noqa: E402
import unity_items as U  # noqa: E402
import values_auto as VA  # noqa: E402

ITEMS = ["None", "Potion_Small", "Potion_Big", "Sword_Iron", "Sword_Steel", "Shield_Wood", "Fish_Trout", "Gold", "Wood", "Stone",
         "Herb_Red", "Herb_Blue", "Count"]


def fld(typ, name, off):
    return f"\tpublic {typ} {name}; // {off:#x}\n"


def make_game(tmp, classes, enums=()):
    """classes: [(Name, Koerper)] - Koerper aus fld()/TU.meth().  enums: [(Name, [Werte])]."""
    parts = ["// Image 0: Assembly-CSharp.dll - 0\n// Image 1: UnityEngine.CoreModule.dll - 500\n"]
    td = 0
    for name, values in enums:
        parts.append(TU.enum_text(name, [(n, i) for i, n in enumerate(values)], td))
        td += 1
    for name, body in classes:
        parts.append(TU.cls_text(name, td, body))
        td += 1
    parts.append("// Namespace: UnityEngine\npublic class MonoBehaviour // TypeDefIndex: 500\n{\n}\n")
    path = os.path.join(tmp, "dump.cs")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    g = D.GameDump({"dump_cs": path}, log=lambda *_a: None)
    g.load()
    return g


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)


class Words(unittest.TestCase):
    def test_tokens_handle_prefixes_camel_snake_backing_and_lowercase_runs(self):
        self.assertEqual(SF.tokens("m_curHP"), ["cur", "hp"])
        self.assertEqual(SF.tokens("<Gold>k__BackingField"), ["gold"])
        self.assertEqual(SF.tokens("get_PlayerHealthMax"), ["player", "health", "max"])
        self.assertEqual(SF.tokens("playerhealth"), ["player", "health"])
        self.assertEqual(SF.tokens("bIsDead"), ["is", "dead"])
        self.assertEqual(SF.tokens("Munición"), ["municion"])
        self.assertEqual(SF.tokens(None), [])

    def test_fuzzy_matching_finds_typos_plurals_and_prefixes_but_not_short_noise(self):
        v = {"immortal", "ammunition", "health"}
        self.assertEqual(SF.match_word("immortal", v)[0], 1.0)
        self.assertGreaterEqual(SF.match_word("immotal", v)[0], 0.8)          # Tippfehler (steht so in echten Spielen)
        self.assertGreaterEqual(SF.match_word("healths", v)[0], 0.8)
        self.assertGreaterEqual(SF.match_word("ammu", v)[0], 0.7)             # Anfang eines langen Worts
        self.assertEqual(SF.match_word("hea", v)[0], 0)                       # zu kurz: kein Raten
        self.assertEqual(SF.match_word("table", v)[0], 0)

    def test_concepts_in_other_languages_abbreviations_and_romaji(self):
        want = {"vida": SF.LEBEN, "Salud": SF.LEBEN, "Gesundheit": SF.LEBEN, "m_Hp": SF.LEBEN, "curMp": SF.MANA,
                "Munition": SF.MUNITION, "balas": SF.MUNITION, "dinero": SF.GELD, "Kinsen": SF.GELD, "Muenzen": SF.GELD,
                "gld": SF.GELD, "Ausdauer": SF.AUSDAUER, "keiken": SF.XP, "Immotal": SF.SCHALTER, "unverwundbar": SF.SCHALTER}
        for name, cat in want.items():
            hits = SF.concepts_of(name)
            self.assertTrue(hits and hits[0].concept == cat, f"{name}: {hits}")

    def test_unrelated_names_are_not_concepts(self):
        for name in ("Transform", "speed", "Magnitude", "position", "Vector3", "ItemSlot", "levelName"[:0] or "color"):
            self.assertEqual([h for h in SF.concepts_of(name) if h.conf >= 0.55], [], name)

    def test_verb_roles(self):
        want = {"PayCoins": "spend", "GastarMunicion": "spend", "TakeDamage": "damage", "Verbrauchen": "spend",
                "AddGold": "add", "Obtener": "add", "Heal": "add", "CanAfford": "check", "HasAmmo": "check",
                "GetDamage": "get", "get_Health": "get", "set_Health": "set", "HitEnemy": "hit", "Frobnicate": None}
        for name, role in want.items():
            self.assertEqual(SF.verb_role(name), role, name)

    def test_obfuscation_is_detected_only_when_most_names_are_unreadable(self):
        junk = ["\u0001", "a", "b", "Qxzv", "\u0002\u0003", "aa", "Zxcv"] * 6
        frac, obf = SF.obfuscation(junk)
        self.assertTrue(obf and frac > 0.9)
        self.assertFalse(SF.obfuscation(["AddGold", "TakeDamage", "Update", "PlayerHealth"] * 10)[1])
        self.assertFalse(SF.obfuscation(["a", "b"])[1])                       # zu wenig Namen fuer ein Urteil


class UnityFields(Base):
    def game(self):
        return make_game(self.tmp, [
            ("Spieler", fld("float", "m_Hp", 0x10) + fld("float", "m_MaxHp", 0x14) + fld("float", "curMp", 0x18)
             + fld("int", "Munition", 0x1C) + fld("float", "healthRegenRate", 0x20) + fld("float", "moveSpeed", 0x24)),
            ("Geldbeutel", fld("int", "amount", 0x10)),
            ("Wallet", fld("int", "Kinsen", 0x10)),
            ("Zombie", fld("float", "health", 0x10)),
            ("HealthBarUI", fld("float", "health", 0x10)),
            ("Cheats", fld("bool", "Immotal", 0x10) + fld("bool", "isVisible", 0x11)),
            ("Boring", fld("int", "tileCount", 0x10) + fld("float", "x", 0x14)),
        ])

    def test_finds_abbreviations_other_languages_and_class_inherited_meaning(self):
        by = {f"{u.cls.name}.{u.field.name}": u for u in SF.unity_fields(self.game())}
        self.assertEqual(by["Spieler.m_Hp"].concept, SF.LEBEN)
        self.assertEqual(by["Spieler.curMp"].concept, SF.MANA)
        self.assertEqual(by["Spieler.Munition"].concept, SF.MUNITION)
        self.assertEqual(by["Wallet.Kinsen"].concept, SF.GELD)
        self.assertEqual(by["Cheats.Immotal"].concept, SF.SCHALTER)
        # 'amount' sagt allein nichts - aber die Klasse heisst Geldbeutel (= Geld)
        self.assertEqual(by["Geldbeutel.amount"].concept, SF.GELD)
        self.assertIn("Klasse", by["Geldbeutel.amount"].why)

    def test_rates_speeds_unrelated_and_non_matching_types_stay_out(self):
        names = {f"{u.cls.name}.{u.field.name}" for u in SF.unity_fields(self.game())}
        for bad in ("Spieler.healthRegenRate", "Spieler.moveSpeed", "Boring.tileCount", "Boring.x", "Cheats.isVisible"):
            self.assertNotIn(bad, names)

    def test_player_class_beats_enemy_and_ui_class_with_the_same_field(self):
        by = {u.cls.name: u for u in SF.unity_fields(self.game()) if u.field.name == "health"}
        self.assertEqual(set(by), {"Zombie", "HealthBarUI"})
        self.assertLess(by["Zombie"].conf, 0.9)
        self.assertLess(by["HealthBarUI"].conf, by["Zombie"].conf)

    def test_pair_and_stat_class_raise_confidence(self):
        by = {u.field.name: u for u in SF.unity_fields(self.game()) if u.cls.name == "Spieler"}
        self.assertTrue(by["m_Hp"].paired)
        self.assertIn("Max-Feld", by["m_Hp"].why)
        self.assertGreater(by["m_Hp"].conf, by["m_MaxHp"].conf)               # das Maximum ist nur Begleitwert


class UnityMethods(Base):
    def game(self):
        return make_game(self.tmp, [
            ("Geldbeutel", fld("int", "amount", 0x10) + TU.meth(0x1000, "public void Pay(int n)")
             + TU.meth(0x1010, "public bool Enough(int n)") + TU.meth(0x1020, "public void Add(int n)")),
            ("Jugador", TU.meth(0x2000, "public void TomarDanio(float d)") + TU.meth(0x2010, "public void GastarMunicion(int n)")),
            ("Feind", TU.meth(0x3000, "public void TomarDanio(float d)")),
            ("Menu", TU.meth(0x4000, "public void LoadLevel(int n)") + TU.meth(0x4010, "public void HitButton()")),
        ])

    def test_class_gives_the_concept_when_the_method_name_does_not(self):
        by = {f"{u.method.cls.name}.{u.method.name}": u for u in SF.unity_methods(self.game())}
        self.assertEqual((by["Geldbeutel.Pay"].concept, by["Geldbeutel.Pay"].role), (SF.GELD, "spend"))
        self.assertEqual(by["Geldbeutel.Enough"].role, "check")
        self.assertEqual(by["Geldbeutel.Add"].role, "add")

    def test_other_language_names_work(self):
        by = {f"{u.method.cls.name}.{u.method.name}": u for u in SF.unity_methods(self.game())}
        self.assertEqual((by["Jugador.TomarDanio"].concept, by["Jugador.TomarDanio"].role), (SF.LEBEN, "damage"))
        self.assertEqual((by["Jugador.GastarMunicion"].concept, by["Jugador.GastarMunicion"].role), (SF.MUNITION, "spend"))

    def test_noise_is_not_reported(self):
        names = {f"{u.method.cls.name}.{u.method.name}" for u in SF.unity_methods(self.game())}
        self.assertNotIn("Menu.LoadLevel", names)                              # 'Level' allein ist kein Erfahrungs-Hinweis
        self.assertNotIn("Menu.HitButton", names)                              # 'Hit' ohne Leben-/Spieler-Klasse

    def test_patch_mode_only_for_safe_actions(self):
        by = {f"{u.method.cls.name}.{u.method.name}": u for u in SF.unity_methods(self.game())}
        self.assertEqual(SF.patch_mode(by["Geldbeutel.Pay"])[0], "noop")
        self.assertEqual(SF.patch_mode(by["Geldbeutel.Enough"])[0], "true")
        self.assertIsNone(SF.patch_mode(by["Geldbeutel.Add"]))                 # Hinzufuegen wird nie automatisch gepatcht

    def test_integration_adds_them_as_candidates_never_pre_ticked(self):
        g = self.game()
        cands = {c.label.replace("Game.", ""): c for c in VA.find_unity_candidates(g)}
        pay = cands["Geldbeutel.Pay"]
        self.assertEqual((pay.cat, pay.mode), ("Geld", "noop"))
        self.assertFalse(pay.default_on)
        self.assertIn("erkannt", pay.effect)
        self.assertEqual(cands["Jugador.TomarDanio"].cat, "Leben")
        self.assertIn("Feind.TomarDanio", cands)
        self.assertTrue(cands["Feind.TomarDanio"].warn)                        # Gegner-Klasse wird gewarnt
        self.assertGreater(cands["Jugador.TomarDanio"].score, cands["Feind.TomarDanio"].score)
        self.assertNotIn("Geldbeutel.Add", cands)

    def test_existing_name_rules_are_untouched(self):
        g = make_game(self.tmp, [("PlayerHealth", TU.meth(0x1000, "public void TakeDamage(int amount)"))])
        cands = VA.find_unity_candidates(g)
        self.assertEqual([c.label for c in cands], ["Game.PlayerHealth.TakeDamage"])  # nicht doppelt durch die smarte Erkennung


class UnityCheatmenuFields(Base):
    def test_menu_offers_fields_the_word_list_does_not_know(self):
        g = make_game(self.tmp, [("Spieler", fld("float", "m_Hp", 0x10) + fld("int", "Munition", 0x14) + fld("float", "Salud", 0x18)),
                                 ("Wallet", fld("int", "Kinsen", 0x10))])
        ents = {e.label.replace("Game.", ""): e for e in UM.field_entries(g)}
        self.assertEqual(ents["Spieler.m_Hp"].cat, "Leben")
        self.assertEqual(ents["Wallet.Kinsen"].cat, "Geld")
        self.assertIn("erkannt", ents["Wallet.Kinsen"].note)
        self.assertEqual(ents["Spieler.m_Hp"].note, "")                       # schon von der Namensliste erkannt: unveraendert
        self.assertEqual(ents["Spieler.Munition"].cat, "Munition")

    def test_rate_fields_still_not_offered(self):
        g = make_game(self.tmp, [("Spieler", fld("float", "m_Hp", 0x10) + fld("float", "healthRegenRate", 0x14))])
        self.assertFalse(any("RegenRate" in e.label for e in UM.field_entries(g)))


class GiveByShape(Base):
    def game(self):
        inv = (TU.meth(0x1100, "public void Obtener(ItemID id, int n)") + TU.meth(0x1110, "public void Quitar(ItemID id, int n)")
               + TU.meth(0x1120, "public bool Tiene(ItemID id)") + TU.meth(0x1200, "public void Update()"))
        odd = (TU.meth(0x1300, "public void Zorp(ItemID id, int n)") + TU.meth(0x1310, "public void Remove(ItemID id, int n)"))
        lone = TU.meth(0x1400, "public void Handle(ItemID id, int n)")
        return make_game(self.tmp, [("Mochila", inv), ("Zork", odd), ("Bag", lone + TU.meth(0x1410, "public void Update()"))],
                         enums=[("ItemID", ITEMS)])

    def test_sibling_of_a_remove_method_is_found_even_with_a_meaningless_name(self):
        g = self.game()
        names = {f"{m.cls.name}.{m.name}": (s, strong) for m, s, _why, strong in SF.give_by_shape(g, g.find_class("ItemID"))}
        self.assertIn("Zork.Zorp", names)                                       # Form wie Remove(ItemID, int) in derselben Klasse
        self.assertTrue(names["Zork.Zorp"][1])
        self.assertIn("Mochila.Obtener", names)                                 # Verb 'obtener' = hinzufuegen
        self.assertNotIn("Zork.Remove", names)                                  # die Entfernen-Methode selbst nie
        self.assertNotIn("Mochila.Quitar", names)
        self.assertNotIn("Mochila.Tiene", names)

    def test_lone_method_is_only_a_weak_candidate(self):
        g = self.game()
        got = {f"{m.cls.name}.{m.name}": strong for m, _s, _w, strong in SF.give_by_shape(g, g.find_class("ItemID"))}
        self.assertFalse(got["Bag.Handle"])

    def test_give_candidates_use_shape_only_after_strict_and_flag_weak_ones_as_fallback(self):
        g = self.game()
        item = g.find_class("ItemID")
        strict = {f"{x.method.cls.name}.{x.method.name}" for x in U.give_candidates(g, item, level="strict")[0]}
        normal = {f"{x.method.cls.name}.{x.method.name}" for x in U.give_candidates(g, item, level="normal")[0]}
        off = {f"{x.method.cls.name}.{x.method.name}" for x in U.give_candidates(g, item, level="off")[0]}
        self.assertNotIn("Zork.Zorp", strict)                                   # streng bleibt wie bisher
        self.assertIn("Zork.Zorp", normal)                                      # Geschwister-Beleg reicht ab 'normal'
        self.assertIn("Mochila.Obtener", normal)
        self.assertNotIn("Bag.Handle", normal)                                  # ohne Beleg erst 'aus' (= Notloesung)
        self.assertIn("Bag.Handle", off)
        z = next(x for x in U.give_candidates(g, item, level="normal")[0] if x.method.name == "Zorp")
        self.assertIn("Form", z.note)


class ItemLists(Base):
    def test_enum_name_in_another_language_counts_as_a_name_hit(self):
        g = make_game(self.tmp, [], enums=[("Objeto", ITEMS), ("Gegenstand", ITEMS), ("Farbe", ["Rot", "Gruen", "Blau", "Gelb", "Weiss"])])
        self.assertGreater(U.enum_score(g.find_class("Objeto")), 0)
        self.assertEqual(U.enum_how(g.find_class("Objeto")), "name")
        self.assertEqual(U.enum_how(g.find_class("Gegenstand")), "name")
        self.assertEqual(U.enum_score(g.find_class("Farbe")), 0)

    def test_item_rows_in_other_languages_are_recognised_by_content(self):
        import item_finder as F
        names = ["espada_hierro", "espada_acero", "espada_oro", "pocion_pequena", "pocion_grande", "pocion_mega", "escudo_madera",
                 "pescado_trucha", "hierba_roja", "hierba_azul", "madera", "piedra"]
        self.assertGreaterEqual(F.content_score(names)[0], F.CONTENT_OK)
        de = ["Schwert_Eisen", "Schwert_Stahl", "Schwert_Gold", "Trank_Klein", "Trank_Gross", "Trank_Mega", "Schild_Holz",
              "Kraut_Rot", "Kraut_Blau", "Kraut_Gelb", "Holz", "Stein"]
        self.assertGreaterEqual(F.content_score(de)[0], F.CONTENT_OK)

    def test_name_says_item(self):
        self.assertGreaterEqual(SF.name_says_item("ObjetoID"), 0.8)
        self.assertGreaterEqual(SF.name_says_item("Inventar"), 0.8)
        self.assertEqual(SF.name_says_item("Color"), 0)


class Report(Base):
    def test_report_lists_findings_with_reasons_in_both_languages(self):
        g = make_game(self.tmp, [("Spieler", fld("float", "m_Hp", 0x10) + fld("float", "m_MaxHp", 0x14)),
                                 ("Wallet", fld("int", "Kinsen", 0x10) + TU.meth(0x1000, "public void Pay(int n)"))])
        de, data = SF.report(g)
        self.assertIn("■ Leben", de)
        self.assertIn("Spieler.m_Hp", de)
        self.assertIn("Wallet.Pay", de)
        en, _ = SF.report(g, "en")
        self.assertIn("field", en)
        self.assertNotIn("Methode", en)
        self.assertFalse(data["obfuscated"])

    def test_obfuscated_game_says_so_and_what_helps(self):
        body = "".join(fld("int", f"\u0001{i}", 0x10 + 4 * i) for i in range(12)) + "".join(
            TU.meth(0x1000 + i, f"public void a{'b' * (i % 3)}(int x)") for i in range(12))
        g = make_game(self.tmp, [("Qxz", body)])
        text, data = SF.report(g)
        self.assertTrue(data["obfuscated"])
        self.assertIn("verschleiert", text)
        self.assertIn("verschleiert", SF.no_result_hint(g))
        self.assertIn("obfuscated", SF.no_result_hint(g, "en"))

    def test_clean_game_without_hits_says_nothing_found_not_obfuscated(self):
        g = make_game(self.tmp, [("Tile", fld("int", "tileCount", 0x10) + TU.meth(0x1000, "public void Rotate(float a)"))])
        text, data = SF.report(g)
        self.assertEqual(text, SF.msg_nothing_found())
        self.assertEqual(SF.no_result_hint(g), "")


class FakeMember:
    def __init__(self, name, typ="float", offset=0x10, bit=-1, ptype="FloatProperty"):
        self.name, self.type, self.offset, self.bit, self.ptype, self.owner, self.size = name, typ, offset, bit, ptype, "", 4


class UnrealMembers(unittest.TestCase):
    def classify(self, name, typ="float", cls="ABP_Hero_Character"[:0] or "AHeroCharacter"):
        return UC.classify_member(FakeMember(name, typ), cls)

    def test_exact_names_keep_their_score_and_fuzzy_ones_score_lower_with_a_reason(self):
        exact = self.classify("Health")
        fuzzy = self.classify("Vida")
        self.assertIsNotNone(exact)
        self.assertIsNotNone(fuzzy)
        self.assertEqual(fuzzy[1], "Leben")
        self.assertLess(fuzzy[0], exact[0])
        self.assertTrue(any("erinnert" in r for r in fuzzy[2]))

    def test_other_languages_abbreviations_and_typos_are_found(self):
        self.assertEqual(self.classify("Municion", "int32")[1], "Munition")
        self.assertEqual(self.classify("m_Hp")[1], "Leben")
        self.assertEqual(self.classify("Healt")[1], "Leben")
        self.assertEqual(self.classify("Dinero", "int32")[1], "Währung")
        self.assertEqual(self.classify("bImmotal", "uint8")[1], "Cheat-Schalter")

    def test_unrelated_members_are_still_ignored(self):
        for name in ("Magnitude", "ComponentTags", "Transform", "Armature"):
            self.assertIsNone(self.classify(name), name)


class UnrealFunctions(unittest.TestCase):
    def test_function_roles_in_any_language(self):
        self.assertEqual(SF.ue_function_role("TakeDamage"), (SF.LEBEN, "damage"))
        self.assertEqual(SF.ue_function_role("GastarMunicion"), (SF.MUNITION, "spend"))
        self.assertEqual(SF.ue_function_role("DineroHinzufuegen")[1], "add")
        self.assertEqual(SF.ue_function_role("Frobnicate"), (None, None))

    def test_find_functions_adds_smart_matches(self):
        class Cls:
            functions = [("GastarMunicion", "void (int32 N)"), ("AddItem", "void (FName)"), ("Frobnicate", "void ()")]

        class Sdk:
            classes = {"AWaffe": Cls()}
        got = {(f, cat) for _c, f, cat, _s in UC.find_functions(Sdk())}
        self.assertIn(("AddItem", "Items"), got)                                # alte Erkennung unveraendert
        self.assertIn(("GastarMunicion", "Munition"), got)                      # neu
        self.assertNotIn("Frobnicate", {f for f, _c in got})


if __name__ == "__main__":
    unittest.main()
