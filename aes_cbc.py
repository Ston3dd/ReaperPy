"""aes_cbc.py - AES (128/192/256) im CBC-Modus in reinem Python.

Wird nur fuer .mc4-Cheat-Dateien gebraucht (base64 + AES-256-CBC).  Reines Python, damit ReaperPy
keine zusaetzliche Abhaengigkeit bekommt - eine mc4-Datei ist wenige KB gross, Geschwindigkeit ist
egal.  Implementierung nach FIPS-197, gegen die 'cryptography'-Bibliothek getestet (tests/).
"""

# ---- S-Box / Inverse S-Box aus dem GF(2^8)-Inversen berechnen (statt 512 Konstanten abzutippen) ----
def _build_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        # p *= 3 in GF(2^8)
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        # q /= 3 in GF(2^8)
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) & 0xFF ^ ((q << 2) | (q >> 6)) & 0xFF \
            ^ ((q << 3) | (q >> 5)) & 0xFF ^ ((q << 4) | (q >> 4)) & 0xFF
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


_SBOX = _build_sbox()
_INV = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV[_v] = _i


def _xtime(a):
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


_M2 = [_mul(i, 2) for i in range(256)]
_M3 = [_mul(i, 3) for i in range(256)]
_M9 = [_mul(i, 9) for i in range(256)]
_M11 = [_mul(i, 11) for i in range(256)]
_M13 = [_mul(i, 13) for i in range(256)]
_M14 = [_mul(i, 14) for i in range(256)]


class AES:
    def __init__(self, key):
        key = bytes(key)
        if len(key) not in (16, 24, 32):
            raise ValueError("AES-Schluessel muss 16, 24 oder 32 Byte lang sein")
        self.nk = len(key) // 4
        self.nr = self.nk + 6
        self.rk = self._expand(key)

    def _expand(self, key):
        nk, nr = self.nk, self.nr
        w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
        rcon = 1
        for i in range(nk, 4 * (nr + 1)):
            t = list(w[i - 1])
            if i % nk == 0:
                t = t[1:] + t[:1]
                t = [_SBOX[b] for b in t]
                t[0] ^= rcon
                rcon = _xtime(rcon)
            elif nk > 6 and i % nk == 4:
                t = [_SBOX[b] for b in t]
            w.append([a ^ b for a, b in zip(w[i - nk], t)])
        # 16-Byte-Rundenschluessel
        return [sum((w[4 * r + c] for c in range(4)), []) for r in range(nr + 1)]

    # State = 16 Byte, spaltenweise (wie im Standard: s[4*c + r])
    def encrypt_block(self, block):
        s = [b ^ k for b, k in zip(block, self.rk[0])]
        for rnd in range(1, self.nr):
            s = [_SBOX[b] for b in s]
            s = self._shift(s)
            s = self._mix(s)
            s = [b ^ k for b, k in zip(s, self.rk[rnd])]
        s = [_SBOX[b] for b in s]
        s = self._shift(s)
        return bytes(b ^ k for b, k in zip(s, self.rk[self.nr]))

    def decrypt_block(self, block):
        s = [b ^ k for b, k in zip(block, self.rk[self.nr])]
        for rnd in range(self.nr - 1, 0, -1):
            s = self._ishift(s)
            s = [_INV[b] for b in s]
            s = [b ^ k for b, k in zip(s, self.rk[rnd])]
            s = self._imix(s)
        s = self._ishift(s)
        s = [_INV[b] for b in s]
        return bytes(b ^ k for b, k in zip(s, self.rk[0]))

    @staticmethod
    def _shift(s):
        return [s[(4 * ((c + r) % 4)) + r] for c in range(4) for r in range(4)]

    @staticmethod
    def _ishift(s):
        return [s[(4 * ((c - r) % 4)) + r] for c in range(4) for r in range(4)]

    @staticmethod
    def _mix(s):
        out = []
        for c in range(4):
            a0, a1, a2, a3 = s[4 * c:4 * c + 4]
            out += [_M2[a0] ^ _M3[a1] ^ a2 ^ a3,
                    a0 ^ _M2[a1] ^ _M3[a2] ^ a3,
                    a0 ^ a1 ^ _M2[a2] ^ _M3[a3],
                    _M3[a0] ^ a1 ^ a2 ^ _M2[a3]]
        return out

    @staticmethod
    def _imix(s):
        out = []
        for c in range(4):
            a0, a1, a2, a3 = s[4 * c:4 * c + 4]
            out += [_M14[a0] ^ _M11[a1] ^ _M13[a2] ^ _M9[a3],
                    _M9[a0] ^ _M14[a1] ^ _M11[a2] ^ _M13[a3],
                    _M13[a0] ^ _M9[a1] ^ _M14[a2] ^ _M11[a3],
                    _M11[a0] ^ _M13[a1] ^ _M9[a2] ^ _M14[a3]]
        return out


def cbc_encrypt(key, iv, data):
    """data muss ein Vielfaches von 16 Byte sein (Padding macht der Aufrufer)."""
    if len(iv) != 16:
        raise ValueError("IV muss 16 Byte lang sein")
    if len(data) % 16:
        raise ValueError("Daten muessen ein Vielfaches von 16 Byte sein")
    aes, prev, out = AES(key), bytes(iv), bytearray()
    for i in range(0, len(data), 16):
        blk = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        prev = aes.encrypt_block(blk)
        out += prev
    return bytes(out)


def cbc_decrypt(key, iv, data):
    if len(iv) != 16:
        raise ValueError("IV muss 16 Byte lang sein")
    if len(data) % 16:
        raise ValueError("Verschluesselte Daten sind kein Vielfaches von 16 Byte")
    aes, prev, out = AES(key), bytes(iv), bytearray()
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        out += bytes(a ^ b for a, b in zip(aes.decrypt_block(blk), prev))
        prev = blk
    return bytes(out)


def pkcs7_pad(data, n=16):
    k = n - len(data) % n
    return bytes(data) + bytes([k]) * k


def pkcs7_unpad(data, n=16):
    if not data:
        return data
    k = data[-1]
    if 1 <= k <= n and data.endswith(bytes([k]) * k):
        return data[:-k]
    return data
