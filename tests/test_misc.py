import os, struct, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal, unwind, memtools


class FakeClient:
    def __init__(self): self.mem = bytearray(256); self.log = []
    def read_memory(self, a, n): return bytes(self.mem[a:a + n])
    def write_memory(self, a, d): self.log.append((a, bytes(d))); self.mem[a:a + len(d)] = d


class T(unittest.TestCase):
    def test_journal(self):
        c = FakeClient(); j = journal.WriteJournal(); j.attach(c)
        c.write_memory(0x10, b"\x01\x02"); c.write_memory(0x10, b"\x01\x02")   # gleicher Wert 2x
        c.write_memory(0x20, b"\xAA"); c.write_memory(0x20, b"\xAA")          # kein Doppel-Eintrag
        c.write_memory(0x30, b"\x00")                                            # unveraendert -> nichts
        self.assertEqual(len(j.entries), 2)
        c.write_memory(0x10, b"\x09")
        self.assertEqual(j.undo_all(), 3)
        self.assertEqual(bytes(c.mem[0x10:0x12]), b"\x00\x00")
        self.assertEqual(bytes(c.mem[0x20:0x21]), b"\x00")
        self.assertFalse(j.undo(j.entries[0]))                                  # schon zurueck
        j.detach(); c.write_memory(0x40, b"\x01"); self.assertEqual(len(j.entries), 3)

    def test_call_detection(self):
        u = unwind.call_len_ending_at
        self.assertEqual(u(b"\x90" * 5 + b"\xE8\x01\x02\x03\x04", 10), 5)         # call rel32
        self.assertEqual(u(b"\x90" * 8 + b"\xFF\xD0", 10), 2)                      # call rax
        self.assertEqual(u(b"\x90" * 7 + b"\x41\xFF\xD3", 10), 3)                  # call r11
        self.assertEqual(u(b"\x90" * 4 + b"\xFF\x15\x10\x00\x00\x00", 10), 6)      # call [rip+x]
        self.assertEqual(u(b"\x90" * 7 + b"\xFF\x50\x18", 10), 3)                  # call [rax+0x18]
        self.assertEqual(u(b"\x90" * 6 + b"\xFF\x14\x24" + b"\x90", 10), 0)        # kein Call am Ende
        self.assertEqual(u(b"\x90" * 7 + b"\xFF\x14\x24", 10), 3)                  # call [rsp]
        self.assertEqual(u(b"\x90" * 10, 10), 0)

    def test_unwind(self):
        code_base = 0x400000
        code = bytearray(b"\x90" * 0x100)
        code[0x20:0x25] = b"\xE8\x00\x00\x00\x00"          # call bei 0x20 -> ret 0x25
        code[0x40:0x42] = b"\xFF\xD0"                       # call rax -> ret 0x42
        stack = struct.pack("<8Q", 5, code_base + 0x25, 0x1234, code_base + 0x42, code_base + 0x60, 0, 0, 0)
        def read(a, n):
            if a < 0x8000: return stack[a - 0x7000:a - 0x7000 + n].ljust(n, b"\0")
            return bytes(code[a - code_base:a - code_base + n]).ljust(n, b"\0")
        fr = unwind.unwind(read, 0x7000, lambda a: code_base <= a < code_base + 0x100, depth=64)
        self.assertEqual([f["ret"] for f in fr], [code_base + 0x25, code_base + 0x42])
        self.assertEqual(fr[0]["slot"], 0x7008)

    def test_diff_inspect(self):
        old = bytes(16); new = bytearray(old); new[2] = 1; new[4] = 2; new[12] = 9
        r = memtools.diff_bytes(old, bytes(new), 0x1000, merge_gap=2)
        self.assertEqual([(a, n) for a, _, n in r], [(0x1002, b"\x01\x00\x02"), (0x100C, b"\x09")])
        d = dict(memtools.inspect(struct.pack("<f", 1.5) + bytes(4)))
        self.assertEqual(d["float"], "1.5")
        self.assertIn("i32", d)
        self.assertEqual(dict(memtools.inspect(b"Hallo\x00xx"))["ASCII"], "Hallo")
        self.assertTrue(memtools.hexdump(b"AB" * 10, 0x10).startswith("0000000000000010  41 42"))



import caller
class BufClient(FakeClient):
    def __init__(self): super().__init__(); self.mem = bytearray(0x40000); self.next = 0x1000; self.freed = []
    def allocate_memory(self, n): a = self.next; self.next += n + 0x100; return a
    def free_memory(self, a, n): self.freed.append(a)

class CallerTest(unittest.TestCase):
    def test_args(self):
        c = BufClient(); b = caller.RemoteBuffers(c)
        base = b.alloc("buf", 0x40)
        a = caller.parse_args(["0x10", "-1", "@buf", "@buf+0x8", '"hi"', "deadbeef"], b)
        self.assertEqual(a[0], 0x10); self.assertEqual(a[1], 2**64 - 1)
        self.assertEqual((a[2], a[3]), (base, base + 8))
        self.assertEqual(bytes(c.mem[a[4]:a[4] + 3]), b"hi\0"); self.assertEqual(a[5], 0xDEADBEEF)
        self.assertEqual(caller.parse_args(["1"], b), [1, 0, 0, 0, 0, 0])
        with self.assertRaises(caller.ArgError): caller.parse_args(["1"] * 7)
        with self.assertRaises(caller.ArgError): caller.parse_arg("@nope", b)
        with self.assertRaises(caller.ArgError): caller.parse_arg("xyz")
        self.assertEqual(caller.parse_arg("eboot+4", None, lambda t: 0x400004), 0x400004)
        b.write("buf", b"\x01\x02", 4); self.assertEqual(b.read("buf", 2, 4), b"\x01\x02")
        with self.assertRaises(caller.ArgError): b.write("buf", b"x" * 0x50)
        b.free_all(); self.assertEqual(len(c.freed), 2)

    def test_describe(self):
        c = BufClient(); c.mem[0x20000:0x20006] = b"Hallo\0"
        d = dict(caller.describe_result(c, 0x20000))
        self.assertEqual(d["String @rax"], "Hallo")
        self.assertEqual(dict(caller.describe_result(c, 2**64 - 1))["i64"], "-1")



class ScriptApiTest(unittest.TestCase):
    def test_call_foreground_many(self):
        import script_api, ps5_more
        saved = (ps5_more.call, ps5_more.foreground_app, ps5_more.write_multi)
        self.addCleanup(lambda: (setattr(ps5_more, "call", saved[0]),
                                 setattr(ps5_more, "foreground_app", saved[1]),
                                 setattr(ps5_more, "write_multi", saved[2])))
        c = BufClient()
        seen = {}
        ps5_more.call = lambda cl, addr, *a, safe=True: seen.update(addr=addr, a=a) or 99
        ps5_more.foreground_app = lambda cl: (1, "CUSA00001", "X", "01.00")
        ps5_more.write_multi = lambda cl, e, want_status=False: seen.update(w=e)
        api = script_api.Ps5Api(c)
        self.assertEqual(api.call(0x500000, 5, "hi"), 99)
        self.assertEqual(seen["addr"], 0x500000); self.assertEqual(seen["a"][0], 5)
        self.assertEqual(bytes(c.mem[seen["a"][1]:seen["a"][1] + 3]), b"hi\0")
        self.assertEqual(api.foreground()[1], "CUSA00001")
        api.write_many([(1, b"x")]); self.assertEqual(seen["w"], [(1, b"x")])

if __name__ == "__main__":
    unittest.main()
