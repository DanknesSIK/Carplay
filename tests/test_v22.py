"""v22 PhoenixSuite IMAGEWTY fake-image regression tests: no OEM firmware."""
import sys
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import audit_phoenix_wty_v22 as audit
from test_v20 import fake_fdt
from test_v21 import toc1_fixture


def make_wty(parts=None):
    if parts is None:
        parts = [('sunxi.fex', fake_fdt()), ('boot_package.fex', toc1_fixture())]
    count = len(parts)
    where = audit.HEADER_SIZE + count * audit.ENTRY_SIZE
    total = where + sum(((len(payload)+511)//512)*512 for _, payload in parts)
    blob = bytearray(total)
    blob[:8] = b'IMAGEWTY'
    struct.pack_into('<Q', blob, 24, total)
    struct.pack_into('<I', blob, 60, count)
    for i, (name, payload) in enumerate(parts):
        entry = audit.HEADER_SIZE + audit.ENTRY_SIZE*i
        blob[entry+36:entry+36+len(name)] = name.encode('ascii')
        struct.pack_into('<QQ', blob, entry+75*4, len(payload), where)
        blob[where:where+len(payload)] = payload
        where += ((len(payload)+511)//512)*512
    return bytes(blob)


class WtyV22(unittest.TestCase):
    def test_parse_valid_two_components(self):
        report = audit.inspect_image(make_wty())
        self.assertEqual(report['entry_count'], 2)
        self.assertFalse(report['safe_to_flash'])
        self.assertFalse(report['m6_real_device_dtb_authenticated'])

    def test_direct_sunxi_fex_dtb_found(self):
        report = audit.inspect_image(make_wty())
        found = report['entries'][0]['offline_details']['literal_fdt_candidates']
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['root_model'], ['Synthetic test board'])

    def test_nested_bootpackage_toc1_found(self):
        report = audit.inspect_image(make_wty())
        nested = report['entries'][1]['offline_details']
        self.assertTrue(nested['toc1_index_valid'])
        self.assertTrue(nested['toc1_entries'][0]['literal_fdt_structure_valid'])

    def test_hidden_offset_inside_entry(self):
        image = make_wty([('sunxi.fex', b'\x00' * 256 + fake_fdt())])
        report = audit.inspect_image(image)
        self.assertEqual(report['entries'][0]['offline_details']['literal_fdt_candidates'][0]['relative_offset'], 256)

    def test_valid_but_unrelated_entry_not_scanned(self):
        report = audit.inspect_image(make_wty([('rootfs.fex', b'\0'*128)]))
        self.assertFalse(report['entries'][0]['relevant_to_boot_or_dtb'])
        self.assertNotIn('offline_details', report['entries'][0])

    def test_random_bytes_rejected(self):
        with self.assertRaises(ValueError):
            audit.inspect_image(b'\0' * 8192)

    def test_truncated_index_rejected(self):
        image = make_wty()
        with self.assertRaises(ValueError):
            audit.inspect_image(image[:1500])

    def test_excessive_entries_rejected(self):
        image = bytearray(make_wty())
        struct.pack_into('<I', image, 60, audit.MAX_ENTRIES + 1)
        with self.assertRaises(ValueError):
            audit.inspect_image(image)

    def test_entry_data_out_of_range_rejected(self):
        image = bytearray(make_wty())
        struct.pack_into('<Q', image, audit.HEADER_SIZE+77*4, len(image) - 1)
        with self.assertRaises(ValueError):
            audit.inspect_image(image)

    def test_overlapping_payloads_rejected(self):
        image = bytearray(make_wty())
        first = struct.unpack_from('<Q', image, audit.HEADER_SIZE+77*4)[0]
        struct.pack_into('<Q', image, audit.HEADER_SIZE+audit.ENTRY_SIZE+77*4, first)
        with self.assertRaises(ValueError):
            audit.inspect_image(image)

    def test_unterminated_filename_rejected(self):
        image = bytearray(make_wty())
        image[audit.HEADER_SIZE+36:audit.HEADER_SIZE+300] = b'A'*264
        with self.assertRaises(ValueError):
            audit.inspect_image(image)

    def test_header_claims_overlong_file_rejected(self):
        image = bytearray(make_wty())
        struct.pack_into('<Q', image, 24, len(image)+1024)
        with self.assertRaises(ValueError):
            audit.inspect_image(image)

    def test_toc1_corrupt_stays_unverified(self):
        toc = bytearray(toc1_fixture())
        toc[-1] ^= 7
        report = audit.inspect_image(make_wty([('toc1.fex', bytes(toc))]))
        self.assertFalse(report['entries'][0]['offline_details']['toc1_index_valid'])
        self.assertFalse(report['safe_to_load'])

    def test_synthetic_fdt_always_unverified(self):
        report = audit.inspect_image(make_wty([('dtb', fake_fdt())]))
        self.assertFalse(report['m6_running_firmware_version_matched'])
        self.assertFalse(report['safe_to_flash'])


if __name__ == '__main__':
    unittest.main()
