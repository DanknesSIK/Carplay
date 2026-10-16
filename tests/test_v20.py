"""Synthetic-only tests: not obtained from any real M6 device."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v20', ROOT/'tools/scan_fdt_v20.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fake_fdt() -> bytes:
    names = b'model\x00compatible\x00status\x00wlan_busnum\x00wlan_regon\x00'
    def tok(v): return struct.pack('>I', v)
    def begin(name):
        body = name.encode()+b'\0'
        return tok(1)+body+b'\0'*((-len(body)) % 4)
    def prop(key, content):
        idx = names.index(key.encode()+b'\0')
        return tok(3)+struct.pack('>II', len(content), idx)+content+b'\0'*((-len(content)) % 4)
    st = (begin('')+prop('model', b'Synthetic test board\0')+
          prop('compatible', b'example,test-only\0')+begin('wlan@0')+
          prop('status', b'okay\0')+
          prop('wlan_busnum', tok(1))+
          prop('wlan_regon', struct.pack('>7I', 37,4,6,1,1,2,0))+
          tok(2)+tok(2)+tok(9))
    reserve = b'\0'*16
    off_mr = 40
    off_st = off_mr + len(reserve)
    off_str = off_st + len(st)
    total = off_str+len(names)
    hd = struct.pack('>10I', 0xd00dfeed,total,off_st,off_str,off_mr,17,16,0,len(names),len(st))
    return hd + reserve + st + names


class TestV20(unittest.TestCase):
    def test_synthetic_dtb_is_valid(self):
        x = mod.validate_fdt(fake_fdt())
        self.assertIsNotNone(x)
        self.assertEqual(x['root_model'], ['Synthetic test board'])
        self.assertEqual(x['hardware_nodes_reference_only'][0]['properties']['wlan_busnum'], [1])
        self.assertFalse(x['m6_verified'])

    def test_find_offset_inside_boot_package(self):
        blob = b'boot_pkg_research_only' + fake_fdt() + b'zzzz'
        cs = mod.candidates(blob)
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0]['offset'], len(b'boot_pkg_research_only'))

    def test_fake_magic_rejected(self):
        self.assertEqual(mod.candidates(b'ANDROID!'+mod.MAGIC+b'junk'*10), [])

    def test_dtb_too_long_rejected(self):
        x = bytearray(fake_fdt())
        x[4:8] = struct.pack('>I', mod.MAX_FDT+1)
        self.assertIsNone(mod.validate_fdt(x))

    def test_wrong_endianness_rejected(self):
        x = bytearray(fake_fdt())
        x[0:4] = b'\xed\xfe\x0d\xd0'
        self.assertIsNone(mod.validate_fdt(x))

    def test_truncated_rejected(self):
        x = fake_fdt()
        self.assertIsNone(mod.validate_fdt(x[:len(x)//2]))

    def test_malicious_property_bounds_rejected(self):
        x = bytearray(fake_fdt())
        prop_loc = bytes(x).find(struct.pack('>I', 3))
        self.assertGreater(prop_loc, 40)
        x[prop_loc+4:prop_loc+8] = struct.pack('>I', 0xfffffff0)
        self.assertIsNone(mod.validate_fdt(x))

    def test_no_fdt_is_not_hardware_proof(self):
        r = mod.analyse_buffer('kernel', b'ANDROID!'+b'v851s-lybox_rtl8')
        self.assertEqual(r['valid_literal_fdt_count'], 0)
        self.assertFalse(r['file_is_authenticated_m6_running_firmware'])
        self.assertTrue(r['no_dtb_does_not_exclude_other_partitions'])

    def test_valid_synthetic_inside_zip(self):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            z = Path(d)/'owned-sample.zip'
            with zipfile.ZipFile(z, 'w') as f:
                f.writestr('firmware/boot_package.bin', b'SAMPLE' + fake_fdt())
            r = mod.make_report([z])
        self.assertEqual(r['literal_fdt_candidates_found'], 1)
        self.assertFalse(r['safe_to_flash'])

    def test_missing_input_fails_closed(self):
        with self.assertRaises(ValueError):
            mod.make_report([Path('/this/path/does/not/exist/firmware.bin')])

    def test_empty_directory_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                mod.make_report([Path(d)])

    def test_report_gate_always_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'synthetic.dtb'
            f.write_bytes(fake_fdt())
            r = mod.make_report([f])
        self.assertEqual(r['literal_fdt_candidates_found'], 1)
        self.assertFalse(r['safe_to_flash'])
        self.assertFalse(r['safe_to_load'])
        self.assertFalse(r['m6_actual_board_dtb_authenticated'])


if __name__ == '__main__':
    unittest.main()
