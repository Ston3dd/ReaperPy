"""GoldHEN/etaHEN: zu grosse memory-Eintraege werden automatisch in kleine Stuecke geteilt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import export_goldhen as G


def entry(off, n, fill="AB"):
    return {"offset": "%X" % off, "on": fill * n, "off": "00" * n}


class Split(unittest.TestCase):
    def test_big_entry_is_split_and_reassembles(self):
        e = entry(0x64A5D80, 8830)
        parts = G.split_entries([e])
        self.assertEqual(len(parts), 18)
        self.assertTrue(all(len(p["on"]) // 2 <= G.MAX_ENTRY for p in parts))
        self.assertEqual("".join(p["on"] for p in parts), e["on"])
        self.assertEqual("".join(p["off"] for p in parts), e["off"])
        pos = 0x64A5D80
        for p in parts:                                     # lueckenlos, richtige Adressen
            self.assertEqual(int(p["offset"], 16), pos)
            pos += len(p["on"]) // 2
        self.assertEqual(pos, 0x64A5D80 + 8830)

    def test_small_entries_untouched(self):
        mem = [entry(0x1000, 8), entry(0x2000, G.MAX_ENTRY)]
        self.assertEqual(G.split_entries(mem), mem)

    def test_other_keys_kept(self):
        e = entry(0x10, 1000); e["comment"] = "x"
        self.assertTrue(all(p.get("comment") == "x" for p in G.split_entries([e])))

    def test_split_mods_reports_and_keeps_names(self):
        notes = []
        mods = G.split_mods([{"name": "A", "type": "checkbox", "memory": [entry(0x100000, 3000)]}], notes)
        self.assertEqual([m["name"] for m in mods], ["A"])
        self.assertEqual(len(mods[0]["memory"]), 6)
        self.assertTrue(notes)

    def test_too_many_entries_spread_over_switches_in_order(self):
        mods = G.split_mods([{"name": "B", "type": "checkbox", "memory": [entry(0x100000, 60000)]}])
        self.assertGreater(len(mods), 1)
        self.assertTrue(all(len(m["memory"]) <= G.MAX_ENTRIES for m in mods))
        self.assertIn("(Teil 1/", mods[0]["name"])
        joined = "".join(e["on"] for m in mods for e in m["memory"])
        self.assertEqual(joined, "AB" * 60000)

    def test_validate_flags_oversized_entry(self):
        doc = {"id": "PPSA06929", "version": "01.004.000",
               "mods": [{"name": "X", "type": "checkbox", "memory": [entry(0x10, 4400)]}]}
        self.assertTrue(any("2048" in i for i in G.validate(doc)))
        doc["mods"][0]["memory"] = G.split_entries(doc["mods"][0]["memory"])
        self.assertEqual(G.validate(doc), [])


if __name__ == "__main__":
    unittest.main()
