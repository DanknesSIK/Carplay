"""Unit tests for pinned published V851SE DTB v23, using only mock bytes."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_public_dtb_v23 as verify


class PublicFixtureGuard(unittest.TestCase):
    def test_blob_hash_matches_git_formula(self):
        data=b'SYNTHETIC'
        self.assertEqual(verify.git_blob_sha1(data),
                         hashlib.sha1(b'blob 9\0SYNTHETIC').hexdigest())

    def test_unknown_fixture_rejected(self):
        with self.assertRaises(ValueError):
            verify.inspect_public_reference('M6',b'not-real-data')

    def test_empty_blob_fails_hash(self):
        with self.assertRaises(ValueError):
            verify.inspect_public_reference('full',b'')

    def test_mutation_blocks_reference(self):
        with self.assertRaises(ValueError):
            verify.inspect_public_reference('small',b'\xd0\x0d\xfe\xed'+b'\0'*128)

    def test_comparison_never_certifies_m6(self):
        full={'root_compatible':['allwinner,v851se'],'root_model':['reference']}
        small={'root_compatible':['allwinner,v851se'],'root_model':['reference']}
        output=verify.compare_documents(full,small)
        self.assertTrue(output['same_root_compatible'])
        for field in ('M6_running_version_proven','M6_GPIO_pinout_verified','M6_DTB_obtained','driver_can_be_loaded','safe_to_flash'):
            self.assertFalse(output[field])


    def test_directory_over_limit_reports_incomplete(self):
        import tempfile
        import scan_fdt_v20 as v20
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            for i in range(v20.MAX_FILES+1):
                (folder / f'{i:03}.bin').write_bytes(b'no-fdt')
            report = v20.make_report([folder])
        self.assertEqual(report['scanned_entries'], v20.MAX_FILES)
        self.assertTrue(report['input_limit_reached'])
        self.assertEqual(report['status'], 'incomplete-some-inputs-skipped-or-limited')
        self.assertFalse(report['safe_to_flash'])

    def test_zip_over_limit_reports_incomplete(self):
        import tempfile
        import zipfile
        import scan_fdt_v20 as v20
        with tempfile.TemporaryDirectory() as d:
            z = Path(d)/'synthetic.zip'
            with zipfile.ZipFile(z,'w') as archive:
                for i in range(v20.MAX_FILES+2):
                    archive.writestr(f'{i:03}.bin', b'none')
            report = v20.make_report([z])
        self.assertTrue(report['input_limit_reached'])
        self.assertEqual(report['scanned_entries'],v20.MAX_FILES)
        self.assertEqual(report['status'], 'incomplete-some-inputs-skipped-or-limited')

    def test_exact_limit_not_incomplete_without_more_inputs(self):
        import tempfile
        import scan_fdt_v20 as v20
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            for i in range(v20.MAX_FILES):
                (folder / f'{i:03}.bin').write_bytes(b'none')
            report=v20.make_report([folder])
        self.assertFalse(report['input_limit_reached'])
        self.assertEqual(report['scanned_entries'], v20.MAX_FILES)
        self.assertEqual(report['status'], 'no-literal-dtb-in-supplied-files')


if __name__=='__main__':
    unittest.main()
