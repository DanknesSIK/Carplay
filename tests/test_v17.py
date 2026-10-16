"""Offline-only tests; intentionally do not require a kernel or target device."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = import_file("prepare_joint_wifi_v17", ROOT / "tools/prepare_joint_wifi_v17.py")
verify = import_file("verify_joint_v17", ROOT / "tools/verify_joint_v17.py")


class PreparationTests(unittest.TestCase):
    def fixture(self, path):
        path.mkdir()
        (path / "Makefile").write_text("""CONFIG_PLATFORM_I386_PC = n
CONFIG_SDIO_HCI = y
CONFIG_PLATFORM_ARM_SUN50IW1P1 = n
ifeq ($(CONFIG_PLATFORM_ARM_SUN50IW1P1), y)
# CONFIG_RESUME_IN_WORKQUEUE disabled for ARM32 research
ifeq ($(CONFIG_USB_HCI), y)
endif
endif
# Unrelated platform config below intentionally still includes this:
EXTRA_CFLAGS += -DCONFIG_RESUME_IN_WORKQUEUE
""", encoding="utf-8")
        (path / "M6_OFFLINE_DRIVER_FORK.json").write_text(json.dumps({"pinned_driver_commit": "test_pin", "safe_to_flash": False}))
        pins = path.parent / "pins.json"
        pins.write_text(json.dumps({"driver": {"commit": "test_pin"}}))
        return pins

    def test_prepares_only_explicitly_verifiable_vendor_copy(self):
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td) / "prepared"
            pins = self.fixture(d)
            mark = prep.configure(d, pins)
            self.assertTrue(mark["legacy_platform_branch"].startswith("CONFIG_PLATFORM_ARM_SUN50IW1P1=y"))
            self.assertFalse(mark["safe_to_load"])
            self.assertFalse(mark["safe_to_flash"])
            self.assertIn("CONFIG_PLATFORM_ARM_SUN50IW1P1 = y", (d / "Makefile").read_text())
            self.assertRaises(ValueError, prep.configure, d, pins)

    def test_fails_closed_for_unpatched_power_mode(self):
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td) / "prepared"
            pins = self.fixture(d)
            makefile = d / "Makefile"
            makefile.write_text(makefile.read_text().replace("# CONFIG_RESUME_IN_WORKQUEUE disabled for ARM32 research", "EXTRA_CFLAGS += -DCONFIG_RESUME_IN_WORKQUEUE"))
            self.assertRaises(ValueError, prep.configure, d, pins)

    def test_pin_mismatch_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td) / "prepared"
            pins = self.fixture(d)
            pins.write_text(json.dumps({"driver": {"commit": "wrong"}}))
            original = (d / "Makefile").read_text()
            self.assertRaises(ValueError, prep.configure, d, pins)
            self.assertEqual(original, (d / "Makefile").read_text())


class LinkingReportTests(unittest.TestCase):
    def test_symvers_requires_gpl_and_correct_provider(self):
        txt = """0x00000000 sunxi_wlan_set_power drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16 EXPORT_SYMBOL_GPL
0x00000000 sunxi_wlan_get_bus_index drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16 EXPORT_SYMBOL_GPL
0x00000000 sunxi_mmc_rescan_card drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16 EXPORT_SYMBOL_GPL
0x00000000 sunxi_bad drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16 EXPORT_SYMBOL_GPL
"""
        self.assertEqual(set(verify.exported_symbols(txt)), set(verify.SYMBOLS))
        self.assertEqual(verify.exported_symbols(txt.replace("EXPORT_SYMBOL_GPL", "EXPORT_SYMBOL")), {})

    def test_undefined_symbol_reading(self):
        inp = "                 U sunxi_mmc_rescan_card\n                 U sunxi_wlan_set_power\n  U sunxi_wlan_get_bus_index\n                 U printk\n"
        self.assertEqual(verify.undefined_symbols(inp), set(verify.SYMBOLS))

    def test_joint_link_report_must_require_module_dependency(self):
        good = dict(exports={x: "drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16" for x in verify.SYMBOLS},
                    wifi_undefined_sunxi_symbols=list(verify.SYMBOLS), wifi_dependencies=[verify.PLATFORM, "cfg80211"],
                    wifi_vermagic="7.2.7 SMP mod_unload ARMv7 ", platform_vermagic="7.2.7 SMP mod_unload ARMv7 ",
                    wifi_module_name="8733bs", platform_module_name=verify.PLATFORM,
                    wifi_elf="ELF32/ARM", platform_elf="ELF32/ARM", legacy_platform_branch_enabled=True)
        self.assertEqual(verify.validate(good), [])
        report = verify.report(good, [])
        self.assertTrue(report["joint_symbol_linkage_verified"])
        self.assertFalse(report["safe_to_flash"])
        self.assertFalse(report["m6_runtime_verified"])
        wrong = dict(good, wifi_dependencies=["cfg80211"])
        self.assertIn("dependency", " ".join(verify.validate(wrong)))

    def test_kernel_mismatch_blocks_joint_pass(self):
        good = dict(exports={x: "p" for x in verify.SYMBOLS}, wifi_undefined_sunxi_symbols=list(verify.SYMBOLS),
                    wifi_dependencies=[verify.PLATFORM], wifi_vermagic="7.2.7 SMP ",
                    platform_vermagic="4.9.191 PREEMPT ", wifi_module_name="8733bs",
                    platform_module_name=verify.PLATFORM, wifi_elf="ELF32/ARM", platform_elf="ELF32/ARM",
                    legacy_platform_branch_enabled=True)
        self.assertTrue(any("vermagic" in e for e in verify.validate(good)))


if __name__ == "__main__":
    unittest.main()
