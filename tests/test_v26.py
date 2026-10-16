"""v26 safe ADB collector tests. All devices/results are simulated."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import adb_readonly_m6_v26 as v


class MockADB:
    def __init__(self, mode='authorized'):
        self.mode=mode
        self.commands=[]
    def __call__(self,*args,**kwargs):
        self.commands.append(args)
        if args[0]=='devices':
            if self.mode=='none': return 0, b'List of devices attached\n'
            if self.mode=='unauthorized':return 0,b'List of devices attached\nSERIAL unauthorized\n'
            if self.mode=='two':return 0,b'List of devices attached\nA device\nB device\n'
            return 0,b'List of devices attached\nFAKE123 device\n'
        key=args[-1]
        if key=='/sys/firmware/fdt':
            from test_v20 import fake_fdt
            return 0,fake_fdt()
        if key=='/proc/config.gz':return 1,b''
        if key=='/proc/device-tree/model':return 0,b'synthetic-test-board\0'
        if key=='/proc/device-tree/compatible':return 0,b'fake,soc\0'
        if key=='/proc/version':return 0,b'Linux version 4.9.191 synthetic-build'
        if key=='/proc/modules':return 0,b'8733bs 4096 0 - Live 0xf00\n'
        return 0,b'synthetic text for '+key.encode()


class V26(unittest.TestCase):
    def test_requires_authorized_device(self):
        for state in ('none','unauthorized','two'):
            with self.assertRaises(RuntimeError):
                v.probe(MockADB(state))

    def test_authorized_probe_does_not_emit_serial_publicly(self):
        r=v.probe(MockADB())
        self.assertEqual(r['serial_for_internal_use_only'],'FAKE123')

    def test_mock_output_requires_no_write_commands(self):
        fake=MockADB()
        with tempfile.TemporaryDirectory() as d:
            r=v.audit(Path(d),runner=fake)
        self.assertFalse(r['safe_to_flash'])
        self.assertFalse(r['safe_to_load'])
        self.assertFalse(r['real_board_identity_authenticated'])
        allowed = {'devices','shell','exec-out'}
        for command in fake.commands:
            self.assertFalse(any(word in command for word in
                ('push','root','remount','reboot','install','sideload','flash','erase','setprop','mount','su')))
            if command[0]!='devices':
                self.assertEqual(command[:2],('-s','FAKE123'))
                self.assertIn(command[2],allowed)

    def test_synthetic_dtb_saved_with_sha256(self):
        fake=MockADB()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            report=v.audit(root,runner=fake)
            binary=root/'m6-readonly-device-tree.dtb'
            self.assertTrue(binary.is_file())
            self.assertEqual(report['observed']['device_tree_fdt']['bytes'],len(binary.read_bytes()))
            self.assertTrue(report['observed']['device_tree_fdt']['board_provenance_not_yet_verified'])
            self.assertFalse(report['complete_flash_backup_verified'])

    def test_no_device_identifiers_in_saved_json(self):
        fake=MockADB()
        with tempfile.TemporaryDirectory() as d:
            v.audit(Path(d),runner=fake)
            saved=(Path(d)/'m6-v26-report.json').read_text()
            self.assertNotIn('FAKE123',saved)
            self.assertFalse(json.loads(saved)['device_serial_stored'])

    def test_missing_optional_config_is_not_success(self):
        fake=MockADB()
        with tempfile.TemporaryDirectory() as d:
            report=v.audit(Path(d),runner=fake)
        self.assertIn('kernel_config_gz',report['missing_or_inaccessible'])
        self.assertNotIn('kernel_config_gz',report['observed'])

    def test_no_fdt_if_damaged_header(self):
        class BadFDT(MockADB):
            def __call__(self,*args,**kwargs):
                if args[-1]=='/sys/firmware/fdt':
                    self.commands.append(args)
                    return 0,b'not a dtb'
                return super().__call__(*args,**kwargs)
        with tempfile.TemporaryDirectory() as d:
            report=v.audit(Path(d),runner=BadFDT())
            self.assertFalse((Path(d)/'m6-readonly-device-tree.dtb').exists())
        self.assertIn('device_tree_fdt_invalid_header',report['missing_or_inaccessible'])

    def test_full_flash_backup_is_never_attempted(self):
        fake=MockADB()
        with tempfile.TemporaryDirectory() as d:
            report=v.audit(Path(d),runner=fake)
        self.assertFalse(report['complete_flash_backup_verified'])
        for cmd in fake.commands:
            self.assertFalse(any('/dev/mtd' in v for v in cmd))
            self.assertFalse(any('/dev/mmcblk' in v for v in cmd))


if __name__=='__main__':
    unittest.main()
