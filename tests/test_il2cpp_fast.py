"""Schnelles Lesen/Suchen: ChunkStream (parallel, geordnet) und der Qword-Filter des census."""
import os
import random
import struct
import threading
import time
import unittest

import il2cpp_dump as D


class ChunkStreamTests(unittest.TestCase):
    def test_order_and_content_with_many_readers(self):
        mem = os.urandom(1 << 16)

        def slow(addr, n):
            time.sleep(random.random() * 0.003)
            return mem[addr:addr + n]
        jobs = D._plan_jobs([(0, len(mem))], 4096, 16)
        got = list(D.ChunkStream([slow] * 4, jobs))
        self.assertEqual([g[0] for g in got], [j[0] for j in jobs])
        self.assertTrue(all(g[2] == mem[g[0]:g[0] + j[2]] for g, j in zip(got, jobs)))

    def test_failed_read_gives_none_and_stream_continues(self):
        calls = []

        def bad(addr, n):
            calls.append(addr)
            if addr == 4096:
                raise OSError("x")
            return bytes(n)
        out = list(D.ChunkStream([bad], D._plan_jobs([(0, 12288)], 4096, 0)))
        self.assertEqual([o[2] is None for o in out], [False, True, False])

    def test_cancel_stops(self):
        flag = threading.Event()
        n = 0
        for _ in D.ChunkStream([lambda a, k: bytes(k)] * 2, D._plan_jobs([(0, 1 << 20)], 4096, 0), cancel=flag.is_set):
            n += 1
            if n == 3:
                flag.set()
        self.assertLess(n, 10)

    def test_plan_jobs_alignment(self):
        jobs = D._plan_jobs([(0, 100)], 32, 8, align=8)
        self.assertEqual(jobs[0], (0, 32, 40))
        self.assertEqual(sum(j[1] for j in jobs), 96)


class MatcherTests(unittest.TestCase):
    def _data(self):
        rnd = random.Random(7)
        kset = {rnd.randrange(0x7000_0000_0000, 0x7000_0010_0000) & ~7 for _ in range(300)}
        words = [rnd.randrange(0, 1 << 47) for _ in range(5000)]
        want = sorted(rnd.sample(range(5000), 40))
        ks = sorted(kset)
        for i in want:
            words[i] = ks[i % len(ks)]
        return kset, struct.pack(f"<{len(words)}Q", *words), want

    def test_fast_and_slow_agree(self):
        kset, buf, want = self._data()
        n = len(buf)
        expected = [i for i in range(n // 8) if struct.unpack_from("<Q", buf, i * 8)[0] in kset]
        self.assertEqual(sorted(set(expected) | set(want)), expected)
        self.assertEqual(D._qword_matcher(kset)(buf, n), expected)
        import sys
        saved = sys.modules.get("numpy")
        sys.modules["numpy"] = None                         # numpy "nicht installiert"
        try:
            self.assertEqual(D._qword_matcher(kset)(buf, n), expected)
        finally:
            if saved is None:
                sys.modules.pop("numpy", None)
            else:
                sys.modules["numpy"] = saved


if __name__ == "__main__":
    unittest.main()
