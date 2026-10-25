"""ue_world.py - synthetische UE-Welt (Speicherabbild + SDK) fuer UE-LIVE-Tests; importiert kein tkinter."""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ue_quick as Q, uesdk
import test_ue_live as TL

HDR = """// Class /Script/Game.HealthComponent
// 0x0020 (0x00A0 - 0x0080) CastFlags 0x0
class UHealthComponent : public UActorComponent
{
public:
\tfloat                                              Health;                        // 0x0080 (0x0004) [0x0018001040022a01] FloatProperty
\tfloat                                              MaxHealth;                     // 0x0084 (0x0004) [0x0018001040022a01] FloatProperty
\tint32                                              Gold;                          // 0x0088 (0x0004) [0x0018001040022a01] IntProperty
\tFFixedPoint64                                      Stamina;                       // 0x0090 (0x0008) [0x0018001040022a01] StructProperty
\tbool                                               bIsEnableMuteki;               // 0x0098 (0x0001) [0x0018001040022a21] BoolProperty BitIndex: 0x02
\tuint8                                              Level;                         // 0x0099 (0x0001) [0x0018001040022a01] ByteProperty
\tint64                                              Big;                           // 0x00A0 (0x0008) [0x0018001040022a01] Int64Property
};
"""


def tgt(sdk, member):
    c = next(c for c in uecheat.find_candidates(sdk, 0) if c.member == member) if False else None
    m = sdk.find_member("UHealthComponent", member)
    return Q.Target("UHealthComponent", member, m.type, m.offset, m.bit)


class Client:
    """Ersatz-Client auf dem synthetischen Speicherabbild."""
    def __init__(self, im): self.im, self.pid, self.writes = im, 1, []
    def read_memory(self, a, n): return self.im.read(a, n)
    def write_memory(self, a, d): self.writes.append((a, bytes(d))); self.im.w(a, d)
    def get_maps(self): return [(TL.BASE, TL.BASE + 0x2000, 5), (TL.HEAP, TL.HEAP + 0x200000, 3)]


class Proj:
    base = TL.BASE
    def __init__(self, sdk): self.sdk = sdk
    def live_args(self): return {}


def world():
    im, ref = TL.build(True)
    sdk = uesdk.parse_header_text(TL.SDK_TXT)
    uesdk.parse_header_text(HDR, sdk)
    sdk.offsets.update({"gobjects": 0x100, "gnames": 0x400})
    c = Client(im)
    p1 = ref["p1"]
    im.w(p1 + 0x80, struct.pack("<ff", 75.5, 100.0)); im.w(p1 + 0x88, struct.pack("<i", 1234))
    im.w(p1 + 0x90, struct.pack("<q", 55000)); im.w(p1 + 0x98, bytes([0b10000001]))
    return im, ref, sdk, c


