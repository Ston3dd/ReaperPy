"""Tests fuer cheatmenu.py: Cheat-Menue ohne CheatManager (Shipping-Builds) - Engine-Werte + SDK-Werte an der Spielfigur."""
import os
import struct
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cheatmenu as M
import uesdk


def cls(name, parent, members=()):
    out = [f"// Class /Script/Game.{name[1:]}", "// 0x0040 (0x0400 - 0x0010)",
           f"class {name}" + (f" : public {parent}" if parent else ""), "{", "public:"]
    for typ, mname, off, sz, extra in members:
        bits = " : 1" if "BitIndex" in extra else ""
        out.append(f"\t{typ:<30} {mname + bits + ';':<34} // {off:#06x} ({sz:#06x}) [0x0018001040022a01] Property {extra}")
    out.append("};")
    return "\n".join(out) + "\n"


SDK_TEXT = "".join([
    cls("UObject", "", []),
    cls("AActor", "UObject", [("uint8_t", "bCanBeDamaged", 0x58, 1, "BitIndex: 0x02"), ("float", "CustomTimeDilation", 0x60, 4, "")]),
    cls("APawn", "AActor", []),
    cls("ACharacter", "APawn", [("class UCharacterMovementComponent*", "CharacterMovement", 0x300, 8, "")]),
    cls("UCharacterMovementComponent", "UObject",
        [("uint8_t", "MovementMode", 0x168, 1, ""), ("float", "MaxWalkSpeed", 0x178, 4, ""), ("float", "MaxFlySpeed", 0x17C, 4, ""),
         ("float", "JumpZVelocity", 0x180, 4, ""), ("float", "GravityScale", 0x184, 4, ""),
         ("uint8_t", "bCheatFlying", 0x1A0, 1, "BitIndex: 0x03")]),
    cls("AController", "AActor", [("class APawn*", "Pawn", 0x100, 8, ""), ("class APlayerState*", "PlayerState", 0x108, 8, "")]),
    cls("APlayerController", "AController", []),
    cls("AWorldSettings", "AActor", [("float", "TimeDilation", 0x40, 4, "")]),
    cls("UVitalsComponent", "UObject", [("float", "Health", 0x30, 4, ""), ("float", "MaxHealth", 0x34, 4, ""),
                                         ("float", "Stamina", 0x38, 4, ""), ("float", "MaxStamina", 0x3C, 4, "")]),
])

CTRL, PAWN, COMP, WORLD, VIT, VIT_ENEMY = 0x2000_0000, 0x3000_0000, 0x4000_0000, 0x5000_0000, 0x6000_0000, 0x6100_0000
STATE = 0x2100_0000


class Mem:
    def __init__(self):
        self.b = {}
        self.writes = []

    def read_memory(self, addr, n):
        return bytes(self.b.get(addr + i, 0) for i in range(n))

    def write_memory(self, addr, data):
        self.writes.append((addr, bytes(data)))
        for i, v in enumerate(data):
            self.b[addr + i] = v

    def put(self, addr, data):
        for i, v in enumerate(data):
            self.b[addr + i] = v


class FakeLive:
    OFFS = {("AController", "Pawn"): 0x100, ("AController", "PlayerState"): 0x108, ("ACharacter", "CharacterMovement"): 0x300,
            ("AActor", "bCanBeDamaged"): 0x58, ("AActor", "CustomTimeDilation"): 0x60, ("AWorldSettings", "TimeDilation"): 0x40,
            ("UCharacterMovementComponent", "MovementMode"): 0x168, ("UCharacterMovementComponent", "MaxWalkSpeed"): 0x178,
            ("UCharacterMovementComponent", "MaxFlySpeed"): 0x17C, ("UCharacterMovementComponent", "JumpZVelocity"): 0x180,
            ("UCharacterMovementComponent", "GravityScale"): 0x184, ("UCharacterMovementComponent", "bCheatFlying"): 0x1A0,
            ("UVitalsComponent", "Health"): 0x30}

    def __init__(self):
        self.index = {}
        self.inst = {"APlayerController": [CTRL], "AWorldSettings": [WORLD], "UVitalsComponent": [VIT, VIT_ENEMY]}
        self.outers = {VIT: PAWN, VIT_ENEMY: 0x7000_0000, 0x7000_0000: 0}

    def member_offset(self, c, m):
        return self.OFFS.get((c, m))

    def instances(self, c, **kw):
        return [{"addr": a, "name": f"{c}_{a:x}", "class": c, "owner": ""} for a in self.inst.get(c, [])]

    def outer(self, a):
        return self.outers.get(a, 0)

    def build_index(self):
        pass


def make(mem=None, live=None):
    mem = mem or Mem()
    mem.put(CTRL + 0x100, struct.pack("<Q", PAWN))
    mem.put(CTRL + 0x108, struct.pack("<Q", STATE))
    mem.put(PAWN + 0x300, struct.pack("<Q", COMP))
    mem.put(PAWN + 0x58, bytes([0b0000_0100]))               # bCanBeDamaged = true (Bit 2)
    mem.put(PAWN + 0x60, struct.pack("<f", 1.0))
    mem.put(COMP + 0x168, bytes([1]))                          # Walking
    mem.put(COMP + 0x178, struct.pack("<f", 600.0))
    mem.put(WORLD + 0x40, struct.pack("<f", 1.0))
    mem.put(VIT + 0x30, struct.pack("<ff", 40.0, 100.0))       # Health 40 / MaxHealth 100
    mem.put(VIT + 0x38, struct.pack("<ff", 10.0, 80.0))
    mem.put(VIT_ENEMY + 0x30, struct.pack("<ff", 7.0, 7.0))
    sdk = uesdk.parse_header_text(SDK_TEXT)
    menu = M.CheatMenu(live or FakeLive(), sdk, mem, log=lambda *a, **k: None)
    menu.build()
    return menu, mem


def f32(mem, addr):
    return struct.unpack("<f", mem.read_memory(addr, 4))[0]


class Menu(unittest.TestCase):
    def test_engine_entries_are_built_from_the_sdk(self):
        menu, _ = make()
        by = menu.by_key
        for k in ("god", "fly", "walkspeed", "flyspeed", "jump", "gravity", "ptime", "wtime"):
            self.assertTrue(by[k].ok, (k, by[k].status))
        self.assertEqual(by["god"].bit, 2)                                  # Bitfeld aus dem SDK

    def test_missing_sdk_member_is_explained_not_hidden(self):
        sdk = uesdk.parse_header_text(SDK_TEXT.replace("bCanBeDamaged", "bSomethingElse"))
        menu = M.CheatMenu(FakeLive(), sdk, Mem(), log=lambda *a, **k: None)
        menu.build()
        self.assertIn("gibt es in diesem Spiel nicht", menu.by_key["god"].status)
        self.assertTrue(menu.by_key["walkspeed"].ok)

    def test_god_toggles_only_the_bit_and_restores_it(self):
        menu, mem = make()
        menu.set_toggle("god", True)
        self.assertEqual(mem.read_memory(PAWN + 0x58, 1)[0], 0)             # Bit 2 aus
        mem.put(PAWN + 0x58, bytes([0b0000_0111]))                          # Spiel setzt es zurueck (+ andere Bits)
        menu.tick()
        self.assertEqual(mem.read_memory(PAWN + 0x58, 1)[0], 0b0000_0011)   # festgehalten, andere Bits unberuehrt
        menu.set_toggle("god", False)
        self.assertTrue(mem.read_memory(PAWN + 0x58, 1)[0] & 0b100)         # Original zurueck

    def test_fly_sets_movement_mode_and_cheatflying_and_goes_back_to_falling(self):
        menu, mem = make()
        menu.set_toggle("fly", True)
        self.assertEqual(mem.read_memory(COMP + 0x168, 1)[0], 5)
        self.assertTrue(mem.read_memory(COMP + 0x1A0, 1)[0] & 0b1000)
        mem.put(COMP + 0x168, bytes([1]))                                    # Landung: Spiel schaltet auf Walking
        menu.tick()
        self.assertEqual(mem.read_memory(COMP + 0x168, 1)[0], 5)             # wird wieder auf Flying gehalten
        menu.set_toggle("fly", False)
        self.assertEqual(mem.read_memory(COMP + 0x168, 1)[0], 1)             # Originalwert (Walking)
        self.assertFalse(mem.read_memory(COMP + 0x1A0, 1)[0] & 0b1000)

    def test_value_entry_sets_and_holds_and_releases(self):
        menu, mem = make()
        menu.set_value("walkspeed", "1200")
        self.assertEqual(f32(mem, COMP + 0x178), 1200.0)
        mem.put(COMP + 0x178, struct.pack("<f", 600.0))
        menu.tick()
        self.assertEqual(f32(mem, COMP + 0x178), 1200.0)
        menu.set_value("walkspeed", "*2", hold=False)                        # relativ, ohne Festhalten
        self.assertEqual(f32(mem, COMP + 0x178), 2400.0)
        mem.put(COMP + 0x178, struct.pack("<f", 600.0))
        menu.tick()
        self.assertEqual(f32(mem, COMP + 0x178), 600.0)

    def test_world_time_uses_world_settings(self):
        menu, mem = make()
        menu.set_value("wtime", "0.5")
        self.assertEqual(f32(mem, WORLD + 0x40), 0.5)

    def test_game_stats_only_touch_the_players_instance_and_use_max_for_auto(self):
        menu, mem = make()
        health = next(e for e in menu.entries if e.source == "spiel" and e.member == "Health")
        self.assertTrue(health.ok, health.status)
        menu.set_value(health.key, "auto")
        self.assertEqual(f32(mem, VIT + 0x30), 100.0)                        # MaxHealth der Figur
        self.assertEqual(f32(mem, VIT_ENEMY + 0x30), 7.0)                    # Gegner unberuehrt
        mem.put(VIT + 0x30, struct.pack("<f", 10.0))
        menu.tick()
        self.assertEqual(f32(mem, VIT + 0x30), 100.0)

    def test_pawn_change_drops_everything_and_never_writes_to_the_old_pawn(self):
        menu, mem = make()
        menu.set_toggle("god", True)
        menu.set_value("walkspeed", "900")
        mem.put(CTRL + 0x100, struct.pack("<Q", 0x3100_0000))               # Figur gewechselt (Tod/Level)
        n = len(mem.writes)
        msg = menu.tick()
        self.assertIn("gewechselt", msg)
        self.assertEqual(len(mem.writes), n)                                 # kein Schreibzugriff auf alte Adressen
        self.assertFalse(menu.by_key["god"].active)
        self.assertEqual(len(menu.freezer), 0)

    def test_no_player_controller_gives_a_clear_reason(self):
        live = FakeLive()
        live.inst["APlayerController"] = []
        menu, _ = make(live=live)
        menu.check_live()
        self.assertIn("Kein PlayerController", menu.by_key["god"].status)

    def test_check_live_marks_entries_without_player_instance(self):
        live = FakeLive()
        live.outers[VIT] = 0x7000_0000                                       # Komponente gehoert nicht zur Figur
        menu, _ = make(live=live)
        menu.check_live()
        health = next(e for e in menu.entries if e.source == "spiel" and e.member == "Health")
        self.assertIn("Spielfigur", health.status)
        self.assertTrue(menu.by_key["god"].ok)

    def test_release_all_restores_originals(self):
        menu, mem = make()
        menu.set_toggle("god", True)
        menu.set_value("walkspeed", "900")
        menu.release_all()
        self.assertTrue(mem.read_memory(PAWN + 0x58, 1)[0] & 0b100)
        self.assertEqual(f32(mem, COMP + 0x178), 600.0)
        self.assertEqual(len(menu.freezer), 0)

    def test_toggle_and_value_misuse_is_reported(self):
        menu, _ = make()
        with self.assertRaises(M.MenuError):
            menu.set_value("god", "1")
        with self.assertRaises(M.MenuError):
            menu.set_toggle("walkspeed", True)


if __name__ == "__main__":
    unittest.main()
