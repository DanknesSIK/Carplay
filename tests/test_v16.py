#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from review_board_v16 import audit

class BoardGate(unittest.TestCase):
    def test_gates(self):
        result = audit()
        self.assertTrue(result["checks_passed"], result["issues"])
        for flag in ("safe_to_load", "safe_to_flash", "m6_board_proven", "m6_gpio_proven"):
            self.assertFalse(result[flag])

    def test_two_distinct_reference_gpio_sets(self):
        result = audit()
        self.assertTrue(result["reference_regon_gpio_differ"])
        self.assertEqual(result["reference_sdio_host_candidates"], [1])

    def test_all_three_symbols_exist(self):
        self.assertEqual(len(audit()["abi_functions"]), 3)

    def test_remove_export_triggers_fail(self):
        src = ROOT / "drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16.c"
        with tempfile.TemporaryDirectory() as d:
            t = pathlib.Path(d) / "altered.c"
            t.write_text(src.read_text().replace("EXPORT_SYMBOL_GPL(sunxi_wlan_set_power);", "/* removed */"))
            self.assertFalse(audit(source_path=t)["checks_passed"])

    def test_no_gpio_in_m6_template(self):
        text = (ROOT / "profiles/m6_unverified_wifi_v16.dts.txt").read_text()
        self.assertNotIn("<&pio", text)
        self.assertNotIn("status = \"okay\"", text)

    def test_no_load_flash_in_workflow(self):
        script = (ROOT / "tools/ci_build_platform_v16.sh").read_text()
        for forbidden in ("insmod ", "modprobe ", "flashcp ", "nandwrite ", "dd if="):
            self.assertNotIn(forbidden, script)

if __name__ == '__main__':
    unittest.main(verbosity=2)
