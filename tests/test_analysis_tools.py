import unittest
from analysis_tools import extract_strings, build_call_graph, infer_call_arguments

class AnalysisToolsTests(unittest.TestCase):
    def test_extract_ascii_and_utf16(self):
        raw = b'\x00\x01Hello World!\x00A\x00B\x00C\x00D\x00\x00'
        got = extract_strings(raw, 0x1000, 4)
        self.assertTrue(any(x['text'] == 'Hello World!' and x['address'] == 0x1002 for x in got))
        self.assertTrue(any(x['text'].endswith('ABCD') and x['encoding'] == 'utf-16le' for x in got))

    def test_graph_requires_capstone_or_returns_graph(self):
        try:
            import capstone  # noqa
        except Exception:
            self.skipTest('Capstone optional dependency not installed')
        # call rel32 from 0x1000 to 0x1006; ret at target
        graph = build_call_graph(bytes.fromhex('E8 01 00 00 00 90 C3'), 0x1000)
        self.assertIn({'source': 0x1000, 'target': 0x1006}, graph['edges'])

    def test_argument_hints_are_explicitly_heuristic(self):
        lines = [
            {'addr': 0x1000, 'mnemonic': 'mov', 'op_str': 'rdi, 0x1234'},
            {'addr': 0x1005, 'mnemonic': 'call', 'op_str': '0x2000'},
        ]
        got = infer_call_arguments(lines, 1)
        self.assertEqual(got['rdi']['hint'], 'integer/immediate candidate')

if __name__ == '__main__': unittest.main()
