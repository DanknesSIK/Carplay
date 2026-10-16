"""Synthetic-only TOC1 fixtures. NO actual M6 firmware is used."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import audit_toc1_v21 as mod
from test_v20 import fake_fdt


def toc1_fixture(payloads=None, base_offset=0):
    if payloads is None:
        payloads = [('dtb', fake_fdt(), 0)]
    count = len(payloads)
    data_start = (64 + 368 * count + 511) // 512 * 512
    total = data_start
    placement = []
    for name, body, encrypted in payloads:
        offset = total
        placement.append((name, offset, body, encrypted))
        total += (len(body) + 511)//512*512
    b = bytearray(total)
    b[:8] = b'TOC1.GLH'
    struct.pack_into('<6I', b, 16, mod.TOC_MAGIC, mod.STAMP, 0, 0, count, total)
    b[60:64] = b'MIE;'
    for i, (name, offset, body, encrypted) in enumerate(placement):
        head = 64 + i * 368
        b[head:head+len(name)] = name.encode('ascii')
        struct.pack_into('<6I', b, head+64, offset, len(body), encrypted, 3, 0, 0)
        b[head+364:head+368] = b'IIE;'
        b[offset:offset+len(body)] = body
    # Checksum field initially contains BROM_STAMP_VALUE; sum then store it.
    checksum = sum(struct.unpack_from('<I', b, i)[0] for i in range(0, total, 4)) & 0xffffffff
    struct.pack_into('<I', b, 20, checksum)
    return b'\0'*base_offset + bytes(b)


class V21(unittest.TestCase):
    def test_realistic_synthetic_toc1(self):
        x = mod.parse_toc1(toc1_fixture())
        self.assertIsNotNone(x)
        self.assertEqual(x['item_count'], 1)
        self.assertTrue(x['items'][0]['literal_fdt_structure_valid'])
        self.assertEqual(x['items'][0]['dtb_root_model'], ['Synthetic test board'])
        self.assertFalse(x['target_board_authenticated'])
        self.assertFalse(x['safe_to_flash'])

    def test_embedded_at_nonzero_offset(self):
        r = mod.audit_buffer(toc1_fixture(base_offset=2048))
        self.assertEqual(r['toc1_candidates_validated'], 1)
        self.assertEqual(r['toc1_containers'][0]['toc1_absolute_offset'], 2048)

    def test_multi_item_index(self):
        buf = toc1_fixture([('u-boot', b'A'*180, 0), ('dtb', fake_fdt(), 0)])
        x = mod.parse_toc1(buf)
        self.assertEqual([i['name'] for i in x['items']], ['u-boot', 'dtb'])
        self.assertTrue(x['items'][1]['literal_fdt_structure_valid'])
        self.assertIsNone(x['items'][0]['literal_fdt_structure_valid'])

    def test_encrypted_item_never_parsed(self):
        x = mod.parse_toc1(toc1_fixture([('dtb', fake_fdt(), 1)]))
        self.assertIsNotNone(x)
        self.assertIsNone(x['items'][0]['literal_fdt_structure_valid'])
        self.assertTrue(x['items'][0]['encrypted_flag'])

    def test_wrong_checksum_rejected(self):
        b = bytearray(toc1_fixture())
        b[-1] ^= 0x01
        self.assertIsNone(mod.parse_toc1(b))

    def test_bad_magic_rejected(self):
        b = bytearray(toc1_fixture())
        b[16] ^= 0xff
        self.assertIsNone(mod.parse_toc1(b))

    def test_truncated_container_rejected(self):
        b = toc1_fixture()
        self.assertIsNone(mod.parse_toc1(b[:600]))

    def test_bad_header_end_rejected(self):
        b = bytearray(toc1_fixture())
        b[60:64] = b'XXXX'
        self.assertIsNone(mod.parse_toc1(b))

    def test_bad_item_end_rejected(self):
        b = bytearray(toc1_fixture())
        b[64+364:64+368] = b'XXXX'
        self.assertIsNone(mod.parse_toc1(b))

    def test_bad_entry_size_rejected(self):
        b = bytearray(toc1_fixture())
        struct.pack_into('<I', b, 64+68, 0xffffffff)
        self.assertIsNone(mod.parse_toc1(b))

    def test_bad_entry_offset_rejected(self):
        b = bytearray(toc1_fixture())
        struct.pack_into('<I', b, 64+64, 512*9999)
        self.assertIsNone(mod.parse_toc1(b))

    def test_overlap_rejected(self):
        b = bytearray(toc1_fixture([('uboot', b'A'*64, 0), ('dtb', fake_fdt(), 0)]))
        off = struct.unpack_from('<I', b, 64+64)[0]
        struct.pack_into('<I', b, 64+368+64, off)
        self.assertIsNone(mod.parse_toc1(b))

    def test_random_magic_no_toc1(self):
        self.assertEqual(mod.find_toc1(b'\0'*19 + struct.pack('<I', mod.TOC_MAGIC) + b'X'*100)[0], [])

    def test_local_file_report(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/'synthetic-bootpackage.bin'
            p.write_bytes(toc1_fixture())
            r = mod.audit_buffer(p.read_bytes(), p.name)
            self.assertEqual(r['result'], 'TOC1_CANDIDATES_UNAUTHENTICATED')
            self.assertFalse(r['real_m6_board_dtb_verified'])
            self.assertFalse(r['safe_to_load'])


if __name__ == '__main__':
    unittest.main()
