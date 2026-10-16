"""Strictly offline unit tests; no hardware, no network, no flashing."""
import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / 'tools/audit_reference_sdio_v19.py'
spec = importlib.util.spec_from_file_location('audit_v19', SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fake_dts(soc: str, regon: str, chip: str, mmc_status: str = 'okay',
             marker: str = '') -> str:
    def pin(name):
        return '0x25 0x%02x 0x%02x 0x01 0x01 0x02 0x00' % (
            ord(name[1]) - ord('A'), int(name[2:]))
    return f'''/dts-v1/;
/ {{
    compatible = "allwinner,sun8iw21p1\\0arm,sun8iw21p1\\0{soc}";
    model = "{marker}";
    soc {{
        sdmmc@04021000 {{
            reg = <0x00 0x4021000 0x00 0x1000>;
            status = "{mmc_status}";
            bus-width = <0x04>;
        }};
        wlan@0 {{
            compatible = "allwinner,sunxi-wlan";
            wlan_busnum = <0x01>;
            wlan_regon = <{pin(regon)}>;
            chip_en = <{pin(chip)}>;
            status = "okay";
        }};
    }};
}};
'''


def pair():
    return (fake_dts('allwinner,v851s', 'PE6', 'PH13'),
            fake_dts('allwinner,v851se', 'PA11', 'PE9'))


class ReferenceAuditV19(unittest.TestCase):
    def test_valid_references_only_not_m6(self):
        r = mod.audit(*pair())
        self.assertTrue(r['research_checks_passed'])
        for key in ('safe_to_load', 'safe_to_flash', 'm6_actual_dtb_verified',
                    'm6_gpio_verified', 'device_driver_runtime_verified'):
            self.assertFalse(r[key])

    def test_wlan_gpio_differences_required(self):
        gx, hb = pair()
        self.assertFalse(mod.audit(gx, hb.replace('0x00 0x0b', '0x04 0x06'))['research_checks_passed'])

    def test_enabled_reference_mmc1_required(self):
        gx, hb = pair()
        self.assertFalse(mod.audit(gx.replace('status = "okay";', 'status = "disabled";', 1), hb)['research_checks_passed'])

    def test_wrong_sdio_bus_rejected(self):
        gx, hb = pair()
        self.assertFalse(mod.audit(gx.replace('wlan_busnum = <0x01>', 'wlan_busnum = <0x02>'), hb)['research_checks_passed'])

    def test_wrong_reference_soc_rejected(self):
        gx, hb = pair()
        self.assertFalse(mod.audit(gx.replace('allwinner,v851s', 'allwinner,v853'), hb)['research_checks_passed'])

    def test_m6_identifier_in_reference_blocks(self):
        gx, hb = pair()
        self.assertFalse(mod.audit(gx.replace('model = ""', 'model = "v851s-lybox_rtl8"'), hb)['research_checks_passed'])

    def test_corrupt_property_fail_closed(self):
        gx, hb = pair()
        with self.assertRaises(ValueError):
            mod.audit(gx.replace('wlan_regon', 'something_else'), hb)

    def test_unbalanced_node_fails(self):
        with self.assertRaises(ValueError):
            mod.node_body('/ {\n compatiblesomething;\n', '/')

    def test_decode_gpio(self):
        gx, _ = pair()
        r = mod.inspect(gx)
        self.assertEqual(r['wlan_regon_reference_only'], 'PE6')
        self.assertEqual(r['chip_en_reference_only'], 'PH13')


if __name__ == '__main__':
    unittest.main()
