"""Offline unit tests only: no network, hardware or driver loading."""
import importlib.util
from pathlib import Path
import struct
import unittest

P = Path(__file__).resolve().parents[1]/'tools/audit_board_dtb_v18.py'
spec = importlib.util.spec_from_file_location('board_audit_v18', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture():
    patch = '''+++ b/arch/arm/boot/dts/allwinner/sun8i-v851s-lizard.dts
+wifi_pwrseq: wifi-pwrseq { compatible = "mmc-pwrseq-simple"; };
+&mmc1 { xr829: wifi@1 { reg = <1>; }; };
--- /dev/null
+++ b/arch/arm/boot/dts/allwinner/sun8i-v853.dtsi
+mmc1: mmc@4021000 {
+  compatible = "allwinner,sun20i-d1-mmc";
+  status = "disabled";
+};
'''
    config='\n'.join('CONFIG_'+x+'='+y for x,y in mod.EXPECTED.items())+'\n'
    stage1='/dts-v1/;\n/ { compatible = "catplay,v851s-dongle-stage1"; };\n'
    return patch,stage1,config


class Audits(unittest.TestCase):
    def test_reference_is_blocked_for_m6(self):
        result=mod.audit(*fixture())
        self.assertTrue(result['research_checks_passed'])
        for key in ('safe_to_flash','safe_to_load','m6_dtb_verified','m6_wifi_runtime_ready'):
            self.assertFalse(result[key])
    def test_missing_mmc1_is_rejected(self):
        p,s,c=fixture()
        self.assertFalse(mod.audit(p.replace('mmc1: mmc@4021000', 'mmc2: mmc@4022000'),s,c)['research_checks_passed'])
    def test_disabled_mmc1_is_required(self):
        p,s,c=fixture()
        self.assertFalse(mod.audit(p.replace('status = "disabled"', 'status = "okay"'),s,c)['research_checks_passed'])
    def test_stage1_mmc1_override_is_rejected(self):
        p,s,c=fixture()
        self.assertFalse(mod.audit(p,s+'\n&mmc1 { status="okay"; };',c)['research_checks_passed'])
    def test_missing_kernel_option_is_rejected(self):
        p,s,c=fixture()
        self.assertFalse(mod.audit(p,s,c.replace('CONFIG_MMC_SUNXI=y','CONFIG_MMC_SUNXI=n'))['research_checks_passed'])
    def test_fake_magic_dtb_not_valid(self):
        self.assertEqual(mod.fdt_info(b'ANDROID!'+b'\xd0\x0d\xfe\xed'+b'garbage'*12)['valid_literal_fdt_candidates'],0)
    def test_structurally_plausible_dtb_header(self):
        header=struct.pack('>10I',0xd00dfeed, 64, 40, 48, 56, 17, 16, 0, 8, 8)
        self.assertEqual(mod.fdt_info(header+b'\0'*24)['valid_literal_fdt_candidates'],1)

if __name__ == '__main__':
    unittest.main()
