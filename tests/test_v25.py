#!/usr/bin/env python3
"""v25 offline firmware manifest consistency only; firmware bytes are not in GitHub CI."""
import json
import re
import unittest
from pathlib import Path

DOC = json.loads((Path(__file__).resolve().parents[1] / "docs/stock_evidence_v25.json").read_text(encoding="utf-8"))


class StockEvidenceV25(unittest.TestCase):
    def test_source_files_are_only_provenance_hashes(self):
        self.assertEqual(set(DOC["source_files"]), {"M6-header.bin", "kernel", "customer"})
        self.assertEqual(DOC["source_files"]["M6-header.bin"]["size_bytes"], 1048576)
        for f in DOC["source_files"].values():
            self.assertRegex(f["sha256"], r"^[0-9a-f]{64}$")

    def test_swu_is_a_partial_ota_not_backup(self):
        self.assertTrue(DOC["swu_header_is_prefix_only"])
        self.assertEqual(DOC["swu_entries_visible_in_prefix"][0]["name"], "sw-description")
        self.assertFalse(DOC["swu_entries_visible_in_prefix"][1]["payload_fully_present"])

    def test_boot_image_matches_board_but_has_no_dtb(self):
        boot = DOC["boot_image"]
        self.assertEqual(boot["boot_board_identifier"], "v851s-lybox_rtl8")
        self.assertEqual(boot["page_size"], 2048)
        self.assertEqual(boot["dtb_size_header_bytes"], 0)
        self.assertFalse(boot["full_fdt_validated_in_boot_image"])

    def test_ota_write_targets_are_narrow(self):
        self.assertEqual({(i["filename"],i["target"]) for i in DOC["swupdate"]["active_upgrade_kernel_image_targets"]},
                         {("kernel","/dev/by-name/boot"),("customer","/dev/by-name/customer")})
        self.assertEqual(DOC["swupdate"]["ly_project_name"],"ly2807")

    def test_recovery_entry_is_not_a_verified_recovery_image(self):
        self.assertTrue(DOC["swupdate"]["recovery_bootenv_switch_present"])
        self.assertFalse(DOC["swupdate"]["recovery_image_install_active"])
        self.assertFalse(DOC["swupdate"]["full_recovery_image_verified"])
        self.assertFalse(DOC["recovery_procedure_tested"])

    def test_module_origin_explicitly_historical(self):
        m=DOC["previous_vendor_module_metadata"]
        self.assertIn("not re-extracted",m["source"])
        self.assertTrue(m["vermagic"].startswith("4.9.191"))
        self.assertEqual(set(m["platform_symbol_dependencies"]),
                         {"sunxi_mmc_rescan_card","sunxi_wlan_get_bus_index","sunxi_wlan_set_power"})
        self.assertFalse(DOC["customer_image"]["actual_module_extraction_this_run"])

    def test_version_mismatch_is_real(self):
        self.assertNotEqual(DOC["user_device_reported_version"],DOC["ota_version_from_prior_customer_report"])
        self.assertTrue(DOC["version_mismatch"])

    def test_safe_to_load_and_flash_are_always_blocked(self):
        for key in ("real_m6_fel_usb_confirmed","backup_of_actual_current_firmware_verified",
                    "m6_specific_dtb_or_partition_layout_verified",
                    "matched_kernel_tree_config_and_symbol_version_verified",
                    "real_m6_gpio_sdio_power_sequence_verified","safe_to_load","safe_to_flash"):
            self.assertIs(DOC[key],False,key)


if __name__=="__main__":
    unittest.main()
