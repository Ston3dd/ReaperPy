import os, sys, unittest, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ghost_tk; ghost_tk.install()


class FakeClient:
    def __init__(self): self.mem = bytearray(0x40000); self.nxt = 0x10000; self.pid = 1
    def read_memory(self, a, n): return bytes(self.mem[a:a + n])
    def write_memory(self, a, d): self.mem[a:a + len(d)] = d
    def allocate_memory(self, n): a = self.nxt; self.nxt += n + 0x100; return a
    def free_memory(self, a, n): pass
    def get_maps(self): return [(0x10000, 0x30000, 3), (0x1000, 0x2000, 5)]


class FakeWin:
    def __init__(self):
        self.client = FakeClient(); self.logs = []; self.went = []
        self.app = type("A", (), {"IMAGE_BASE": 0x400000, "backend": object()})()
    def bg(self, fn, ok=None, err=None, lock=True):
        try: r = fn()
        except Exception as e:
            (err or (lambda e: self.logs.append(("err", str(e)))))(e); return
        if ok: ok(r)
    def log(self, m, k="info"): self.logs.append((k, m))
    def goto_memory(self, a): self.went.append(("mem", a))
    def goto_disasm(self, a): self.went.append(("dis", a))
    def ui(self, fn): fn()


class T(unittest.TestCase):
    def test_imports(self):
        import tools_extra_gui, tools_gui, tools_debug_gui, tools_pointer_gui, tools_scan_gui  # noqa

    def test_caller_tab(self):
        import tools_extra_gui as G, caller
        self.addCleanup(setattr, caller, "do_call", caller.do_call)
        w = FakeWin(); t = G.CallerTab(None, w)
        caller.do_call = lambda c, rip, args, safe=True: 0x1234
        t.v_fn.set("0x500000"); t.v_args[0].set("0x10"); t.v_args[1].set('"hi"')
        t.v_bname.set("b1"); t.v_bsize.set("0x40"); t.buf_alloc()
        self.assertIn("b1", t.bufs.items)
        t.run()
        self.assertTrue(any("RAX=0x1234" in m for k, m in w.logs), w.logs)
        self.assertIn("0x1234", t.history[0])
        t.v_args[2].set("@nope"); t.run()
        self.assertTrue(any(k == "err" for k, _ in w.logs))

    def test_journal_tab(self):
        import tools_extra_gui as G
        w = FakeWin(); t = G.JournalTab(None, w); t.attach()
        w.client.write_memory(0x10100, b"\xAA\xBB")
        self.assertEqual(len(t.j.entries), 1)
        t.refresh(); self.assertEqual(len(t.tv.rows), 1)
        t.tv.sel = tuple(t.tv.rows); t.undo_sel()
        self.assertEqual(bytes(w.client.mem[0x10100:0x10102]), b"\0\0")
        t.shutdown()

    def test_logger_tab_flow(self):
        import tools_extra_gui as G, logger
        self.addCleanup(setattr, logger, "LoggerSession", logger.LoggerSession)
        started = {}
        class FakeSess:
            lost = 0
            def __init__(self, *a): started["args"] = a
            def start(self): return {"cave": 0x500000, "cave_size": 100, "data": 0x600000}
            def poll(self):
                return [{"index": 0, "ret": 0x401234, "rdi": 1, "rsi": 2, "rdx": 3, "rcx": 4, "r8": 5,
                         "r9": 6, "thread": 0}] * 3
            def stop(self): started["stopped"] = True
        logger.LoggerSession = FakeSess
        w = FakeWin(); t = G.LoggerTab(None, w)
        t.v_fn.set("0x401000"); t.start()
        self.assertTrue(t.running)
        t._tick()
        self.assertEqual(len(t.rows), 3)
        self.assertEqual(len(t.tv.rows), 3)
        self.assertEqual(list(t.grp.rows.values())[0][0], 3)
        t.tv.sel = (next(iter(t.tv.rows)),); t._dbl(None)
        self.assertEqual(w.went[-1], ("dis", 0x401234 - 5))
        t.stop(); self.assertTrue(started.get("stopped"))

    def test_memory_tab_inspector(self):
        import tools_gui as TG
        w = FakeWin(); t = TG.MemoryTab(None, w)
        data = struct.pack("<f", 1.5) + bytes(12)
        t._show(0x401000, data)
        t.txt.index = lambda *a: "1.18"          # Cursor auf dem ersten Hex-Byte
        t._inspect(None)
        self.assertIn("float 1.5", t.lbl_insp._text)
        t.snapshot(); self.assertIsNotNone(t.snap)

if __name__ == "__main__":
    unittest.main()
