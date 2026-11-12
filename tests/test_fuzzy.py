"""Fuzzy-Wertsuche: Eingabeformen, Bereichsberechnung, Scanner-Anbindung (Bereichs-Vergleich), value_plan."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import assist as A
import fuzzy as F
import scanner as SC


class Parse(unittest.TestCase):
    def test_input_forms(self):
        for text, want in (("75~5", ("75", "5")), ("75±5", ("75", "5")), ("75 +- 5%", ("75", "5%")), ("75+/-2", ("75", "2")),
                           ("~75", ("75", None)), ("ca. 75", ("75", None)), ("etwa 1,5", ("1,5", None)),
                           ("75~", ("75", None)), ("-3~1", ("-3", "1")), ("0x10~2", ("0x10", "2"))):
            self.assertEqual(F.parse_approx(text), want, text)

    def test_plain_numbers_are_not_fuzzy(self):
        for text in ("100", "-5", "9.5", "", "  ", "abc", "0x10"):
            self.assertIsNone(F.parse_approx(text), text)
            self.assertFalse(F.is_approx(text), text)

    def test_broken_fuzzy_is_an_error(self):
        for text in ("abc~5", "75~x", "~", "ca."):
            with self.assertRaises(F.FuzzyError, msg=text):
                F.parse_approx(text)

    def test_tolerance(self):
        self.assertEqual(F.parse_tolerance("5"), ("abs", 5.0))
        self.assertEqual(F.parse_tolerance("5%"), ("pct", 5.0))
        self.assertEqual(F.parse_tolerance("2,5 %"), ("pct", 2.5))
        self.assertEqual(F.parse_tolerance(""), ("pct", F.DEFAULT_PCT))
        with self.assertRaises(F.FuzzyError):
            F.parse_tolerance("viel")


class Range(unittest.TestCase):
    def test_integer_ranges(self):
        self.assertEqual(F.to_range("Int32", "75", "5"), ("70", "80"))
        self.assertEqual(F.to_range("Int32", "75", "10%"), ("67", "83"))         # 7.5 -> abrunden / aufrunden
        self.assertEqual(F.to_range("Int32", "10", "5%"), ("9", "11"))            # mindestens +-1
        self.assertEqual(F.to_range("Int32", "75", ""), ("71", "79"))             # Standard 5 %

    def test_clamped_to_type(self):
        self.assertEqual(F.to_range("UInt8", "250", "20"), ("230", "255"))
        self.assertEqual(F.to_range("UInt8", "3", "20"), ("0", "23"))
        self.assertEqual(F.to_range("Int8", "-120", "20"), ("-128", "-100"))
        with self.assertRaises(F.FuzzyError):
            F.to_range("UInt8", "1000", "1")

    def test_float_ranges(self):
        lo, hi = F.to_range("Float", "0.7", "5%")
        self.assertAlmostEqual(float(lo), 0.665, places=6)
        self.assertAlmostEqual(float(hi), 0.735, places=6)
        lo, hi = F.to_range("Double", "100", "0.5")
        self.assertEqual((float(lo), float(hi)), (99.5, 100.5))
        lo, hi = F.to_range("Float", "0", "5%")                                   # 5 % von 0 waere 0
        self.assertEqual((float(lo), float(hi)), (-0.01, 0.01))

    def test_hex_and_comma(self):
        self.assertEqual(F.to_range("Int32", "0x10", "2"), ("14", "18"))
        lo, hi = F.to_range("Float", "1,5", "0,5")
        self.assertEqual((float(lo), float(hi)), (1.0, 2.0))

    def test_describe(self):
        self.assertEqual(F.describe("Int32", "75", "5"), "70 bis 80")


class ScannerLink(unittest.TestCase):
    def test_fuzzy_uses_the_between_compare(self):
        self.assertEqual(SC.CTYPES[SC.FUZZY], SC.CTYPES["Zwischen"])
        self.assertNotIn(SC.FUZZY, SC.FIRST_ONLY)
        self.assertNotIn(SC.FUZZY, SC.NEXT_ONLY)

    def test_values_are_lower_and_upper_bound(self):
        v = SC.Scanner._values(None, "Int32", SC.FUZZY, "75", "5")
        self.assertEqual(struct.unpack("<ii", v), (70, 80))
        v = SC.Scanner._values(None, "Float", SC.FUZZY, "0.5", "10%")
        a, b = struct.unpack("<ff", v)
        self.assertAlmostEqual(a, 0.45, places=5)
        self.assertAlmostEqual(b, 0.55, places=5)

    def test_between_is_unchanged(self):
        v = SC.Scanner._values(None, "Int32", "Zwischen", "1", "9")
        self.assertEqual(struct.unpack("<ii", v), (1, 9))

    def test_check_values(self):
        SC.check_values("Int32", SC.FUZZY, "75", "5%")
        SC.check_values("Int32", "Genau", "5", "")
        SC.check_values("Int32", "Zwischen", "1", "9")
        with self.assertRaises(ValueError):
            SC.check_values("Int32", SC.FUZZY, "abc", "5")
        with self.assertRaises(ValueError):
            SC.check_values("Int32", SC.FUZZY, "75", "viel")
        with self.assertRaises(ValueError):
            SC.check_values("Int32", "Zwischen", "1", "zz")


class Plan(unittest.TestCase):
    def test_plain_plans_unchanged(self):
        self.assertEqual(A.value_plan("100"), {"vname": "Int32", "ctype": "Genau", "text": "100"})

    def test_typed_and_flagged_fuzzy(self):
        self.assertEqual(A.value_plan("75~5"), {"vname": "Int32", "ctype": SC.FUZZY, "text": "75", "text2": "5"})
        self.assertEqual(A.value_plan("9,5~1")["vname"], "Float")
        p = A.value_plan("70", approx=True, tol="10%")
        self.assertEqual((p["ctype"], p["text"], p["text2"]), (SC.FUZZY, "70", "10%"))

    def test_type_can_be_forced(self):
        self.assertEqual(A.value_plan("1.5~1", vname="Float")["vname"], "Float")

    def test_unknown_float(self):
        self.assertEqual(A.value_plan("", unknown=True, float_unknown=True)["vname"], "Float")
        self.assertEqual(A.value_plan("", unknown=True)["vname"], "Int32")

    def test_errors_are_value_errors(self):
        for text, kw in (("abc", {"approx": True}), ("75~x", {}), ("", {"approx": True})):
            with self.assertRaises(ValueError, msg=text):
                A.value_plan(text, **kw)


if __name__ == "__main__":
    unittest.main()
