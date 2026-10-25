import struct
import unittest
from ps5_client import PS5DebugClient, STATUS_SUCCESS

class RpcCallTests(unittest.TestCase):
    def test_call_packet_layout_and_result(self):
        c=PS5DebugClient('127.0.0.1'); c.pid=123
        sent=[]; c._send_packet=lambda cmd,data=b'': sent.append((cmd,data))
        replies=[STATUS_SUCCESS,123,0xABCDEF]
        c._recv_status=lambda: replies.pop(0)
        c._recv_u32=lambda: replies.pop(0)
        c._recv_u64=lambda: replies.pop(0)
        result=c.call_function(0x401000,[1,2],0x700000)
        self.assertEqual(result,0xABCDEF)
        cmd,payload=sent[0]
        self.assertEqual(cmd,0xBDAA0006)
        self.assertEqual(len(payload),68)
        fields=struct.unpack('<I8Q',payload)
        self.assertEqual(fields,(123,0x700000,0x401000,1,2,0,0,0,0))
    def test_requires_pid(self):
        c=PS5DebugClient('127.0.0.1')
        with self.assertRaisesRegex(RuntimeError,'PID'):
            c.call_function(0x401000)
    def test_max_six_args(self):
        c=PS5DebugClient('127.0.0.1'); c.pid=123
        with self.assertRaisesRegex(ValueError,'sechs'):
            c.call_function(0x401000,[1,2,3,4,5,6,7])

if __name__=='__main__': unittest.main()
