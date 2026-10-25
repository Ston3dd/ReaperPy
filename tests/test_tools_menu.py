import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk

ghost_tk.install()
import tools_common as common

COLUMNS = [("f", "❄"), ("n", "NAME"), ("v", "WERT")]


class Table:
    def __init__(self, rows):
        self.rows = rows

    def item(self, row, option=None):
        return self.rows[row]


class RowProperties(unittest.TestCase):
    def test_titles_and_values(self):
        table = Table({"0": ("", "Health", "75.5")})
        self.assertEqual(common.row_properties(table, COLUMNS, "0"), [("NAME", "Health"), ("WERT", "75.5")])

    def test_symbol_column_with_value_is_kept(self):
        table = Table({"0": ("❄", "Health", "75.5")})
        self.assertEqual(common.row_properties(table, COLUMNS, "0")[0], ("❄", "❄"))

    def test_details_are_appended(self):
        table = Table({"0": ("", "Health", "75.5")})
        pairs = common.row_properties(table, COLUMNS, "0", lambda row: [("Offset", 0x80)])
        self.assertEqual(pairs[-1], ("Offset", "128"))

    def test_short_rows_do_not_fail(self):
        table = Table({"0": ("", "Health")})
        self.assertEqual(common.row_properties(table, COLUMNS, "0"), [("NAME", "Health"), ("WERT", "")])


if __name__ == "__main__":
    unittest.main()
