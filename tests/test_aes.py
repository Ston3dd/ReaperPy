"""AES-Test: FIPS-197-Vektoren + Abgleich mit 'cryptography' (falls installiert)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aes_cbc as A


class AesTest(unittest.TestCase):
    def test_fips197_aes256(self):
        key = bytes(range(32))
        pt = bytes.fromhex("00112233445566778899aabbccddeeff")
        ct = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
        self.assertEqual(A.AES(key).encrypt_block(pt), ct)
        self.assertEqual(A.AES(key).decrypt_block(ct), pt)

    def test_fips197_aes128_192(self):
        pt = bytes.fromhex("00112233445566778899aabbccddeeff")
        self.assertEqual(A.AES(bytes(range(16))).encrypt_block(pt).hex(), "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual(A.AES(bytes(range(24))).encrypt_block(pt).hex(), "dda97ca4864cdfe06eaf70a0ec0d7191")

    def test_against_cryptography(self):
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except Exception:
            self.skipTest("cryptography nicht installiert")
        for n in (16, 160, 1600):
            key, iv, data = os.urandom(32), os.urandom(16), os.urandom(n)
            enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
            ref = enc.update(data) + enc.finalize()
            self.assertEqual(A.cbc_encrypt(key, iv, data), ref)
            self.assertEqual(A.cbc_decrypt(key, iv, ref), data)

    def test_padding(self):
        for n in range(0, 40):
            d = os.urandom(n)
            self.assertEqual(A.pkcs7_unpad(A.pkcs7_pad(d)), d)


if __name__ == "__main__":
    unittest.main()
