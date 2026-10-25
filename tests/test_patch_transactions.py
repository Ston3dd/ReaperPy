import tempfile
import unittest
from patch_transactions import PatchTransaction, PatchConflict

class FakeMemory:
    def __init__(self, data): self.data=bytearray(data)
    def read(self, addr, size): return bytes(self.data[addr:addr+size])
    def write(self, addr, data): self.data[addr:addr+len(data)]=data

class PatchTests(unittest.TestCase):
    def setUp(self):
        self.mem=FakeMemory(bytes(range(64)))
        self.tx=PatchTransaction(self.mem.read,self.mem.write)
    def test_apply_and_rollback(self):
        before=self.mem.read(4,3)
        result=self.tx.apply(4,b'abc',expected=before)
        self.assertEqual(self.mem.read(4,3),b'abc')
        self.tx.rollback(result)
        self.assertEqual(self.mem.read(4,3),before)
        self.assertTrue(result.rolled_back)
    def test_expected_mismatch_does_not_write(self):
        original=self.mem.read(4,2)
        with self.assertRaises(PatchConflict): self.tx.apply(4,b'zz',expected=b'no')
        self.assertEqual(self.mem.read(4,2),original)
    def test_rollback_refuses_external_change(self):
        result=self.tx.apply(4,b'xy')
        self.mem.write(4,b'!!')
        with self.assertRaises(PatchConflict): self.tx.rollback(result)

if __name__=='__main__': unittest.main()
