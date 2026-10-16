"""Synthetic FIT integration checks for v24, no actual M6 images or hardware."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'tests'))
import inspect_fit_v24 as fit
import scan_fdt_v20 as v20
from test_v20 import fake_fdt

KEYS = ['description','timestamp','type','compression','data','data-offset','data-size','data-position',
        'fdt','default','arch','os']
STRINGS = b''.join(x.encode()+b'\0' for x in KEYS)

def _word(x: int) -> bytes:
    return struct.pack('>I', x)

def _begin(name: str) -> bytes:
    raw = name.encode() + b'\0'
    return _word(1) + raw + b'\0' * ((-len(raw))%4)

def _prop(key: str, value: bytes) -> bytes:
    return _word(3) + struct.pack('>II',len(value),STRINGS.index(key.encode()+b'\0')) + value + b'\0' * ((-len(value))%4)

def synthetic_fit(*, kind='flat_dt', compression='none', layout='embedded', payload=None,
                  offset=0, position=0, config='fdt-A', data_size_override=None) -> bytes:
    if payload is None:
        payload = fake_fdt()
    structure = _begin('')
    structure += _begin('images')
    structure += _begin('fdt-A')
    structure += _prop('description', b'Synthetic only\0')
    structure += _prop('type', kind.encode()+b'\0')
    structure += _prop('compression', compression.encode()+b'\0')
    if layout == 'embedded':
        structure += _prop('data', payload)
    elif layout == 'external':
        structure += _prop('data-offset', _word(offset))
        structure += _prop('data-size', _word(len(payload) if data_size_override is None else data_size_override))
    elif layout == 'position':
        structure += _prop('data-position', _word(position))
        structure += _prop('data-size', _word(len(payload)))
    structure += _word(2) + _word(2)
    structure += _begin('configurations')
    structure += _prop('default', b'conf-1\0')
    structure += _begin('conf-1')
    structure += _prop('description', b'only test\0')
    structure += _prop('fdt', config.encode()+b'\0')
    structure += _word(2) + _word(2) + _word(2) + _word(9)  # end conf, configurations, root
    reserve = b'\0'*16
    struct_off = 40+len(reserve)
    str_off = struct_off + len(structure)
    total = str_off + len(STRINGS)
    header = struct.pack('>10I',0xd00dfeed,total,struct_off,str_off,40,17,16,0,len(STRINGS),len(structure))
    result = header + reserve + structure + STRINGS
    if layout == 'external':
        result += b'\0'*((-len(result))%4)
        result += b'\0'*offset + payload
    if layout == 'position':
        result += b'\0'*256 + payload
    return result


class FITV24(unittest.TestCase):
    def test_fit_metadata_not_device_tree(self):
        b = synthetic_fit(kind='kernel',layout='none')
        valid = v20.validate_fdt(b)
        self.assertEqual(valid['fdt_kind'],'u-boot-fit-container')
        self.assertFalse(valid['is_board_device_tree_candidate'])
        a = v20.analyse_buffer('test.itb',b)
        self.assertEqual(a['board_device_tree_candidates_count'],0)
        self.assertEqual(a['fit_container_count'],1)
        self.assertEqual(a['valid_literal_fdt_count'],1)

    def test_fit_only_report_does_not_claim_board_candidate(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'fit.itb'
            p.write_bytes(synthetic_fit(kind='kernel',layout='none'))
            r=v20.make_report([p])
        self.assertEqual(r['status'],'fit-container-only-not-a-board-dtb')
        self.assertEqual(r['board_device_tree_candidates_found'],0)
        self.assertFalse(r['safe_to_flash'])

    def test_actual_dtb_fixture_remains_board_candidate(self):
        d=v20.validate_fdt(fake_fdt())
        self.assertEqual(d['fdt_kind'],'board-device-tree-candidate')
        self.assertTrue(d['is_board_device_tree_candidate'])

    def test_embedded_board_dtb_index(self):
        x=fit.inspect_fit(synthetic_fit())
        self.assertEqual(x['source_kind'],'u-boot-fit-container-not-board-device-tree')
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],1)
        self.assertEqual(x['default_configuration'],['conf-1'])
        self.assertEqual(x['configurations']['conf-1']['fdt_images'],['fdt-A'])
        entry=x['image_entries'][0]
        self.assertEqual(entry['board_dt_root_model'],['Synthetic test board'])
        self.assertEqual(entry['data_layout'],'embedded-property')
        self.assertFalse(x['safe_to_flash'])

    def test_external_relative_fdt(self):
        x=fit.inspect_fit(synthetic_fit(layout='external',offset=128))
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],1)
        self.assertEqual(x['image_entries'][0]['data_layout'],'external-relative-offset')

    def test_external_relative_with_firmware_prefix(self):
        blob=b'R'*64+synthetic_fit(layout='external',offset=16)
        x=fit.inspect_fit(blob,64)
        self.assertEqual(x['fit_absolute_offset'],64)
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],1)

    def test_external_relative_out_of_bounds(self):
        x=fit.inspect_fit(synthetic_fit(layout='external',offset=0x40000))
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],0)
        self.assertTrue(x['image_entries'][0]['external_data_out_of_bounds'])

    def test_external_relative_false_length(self):
        x=fit.inspect_fit(synthetic_fit(layout='external',data_size_override=8))
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],0)
        self.assertFalse(x['image_entries'][0]['board_dt_fdt_structure_valid'])

    def test_data_position_remains_unresolved(self):
        x=fit.inspect_fit(synthetic_fit(layout='position',position=4096))
        self.assertEqual(x['image_entries'][0]['data_layout'],'external-position-unresolved')
        self.assertFalse(x['image_entries'][0]['board_dt_fdt_structure_valid'])

    def test_compressed_never_inflated(self):
        x=fit.inspect_fit(synthetic_fit(compression='gzip'))
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],0)
        self.assertIn('Compressed FDT',x['image_entries'][0]['not_inspected_reason'])

    def test_non_fdt_image_does_not_authorize(self):
        x=fit.inspect_fit(synthetic_fit(kind='kernel'))
        self.assertEqual(x['embedded_or_relative_board_dtb_candidates'],0)

    def test_corrupt_metadata_rejected(self):
        b=bytearray(synthetic_fit())
        b[0:4]=b'FAIL'
        with self.assertRaises(ValueError):
            fit.inspect_fit(b)

    def test_truncated_fit_rejected(self):
        with self.assertRaises(ValueError):
            fit.inspect_fit(synthetic_fit()[:90])

    def test_malicious_config_reference_is_unverified(self):
        x=fit.inspect_fit(synthetic_fit(config='nonexistent'))
        self.assertEqual(x['configurations']['conf-1']['fdt_images'],['nonexistent'])
        self.assertFalse(x['actual_M6_DTB_authenticated'])

    def test_unknown_fdt_without_board_identification(self):
        b=synthetic_fit(kind='kernel',layout='none')
        x=fit.inspect_fit(b)
        self.assertFalse(x['fit_signatures_cryptographically_verified'])
        self.assertFalse(x['running_M6_firmware_version_matched'])


if __name__=='__main__':
    unittest.main()
