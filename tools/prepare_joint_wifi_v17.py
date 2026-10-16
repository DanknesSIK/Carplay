#!/usr/bin/env python3
"""Opt in to the *legacy* SDIO platform ABI in an isolated prepared RTL8733BS tree.

For offline Linux 7.2.7 modpost research only. Never changes the v9 generic build.
"""
import argparse
import json
import pathlib
import re
import sys

EXPECTED_SYMBOLS = (
    "sunxi_wlan_set_power", "sunxi_wlan_get_bus_index", "sunxi_mmc_rescan_card"
)


def configure(tree: pathlib.Path, pins: pathlib.Path) -> dict:
    makefile = tree / "Makefile"
    manifest = tree / "M6_OFFLINE_DRIVER_FORK.json"
    if not makefile.is_file() or not manifest.is_file():
        raise ValueError("Need a separately prepared v8 vendor tree with its provenance manifest")
    marker = json.loads(manifest.read_text(encoding="utf-8"))
    pinned = json.loads(pins.read_text(encoding="utf-8"))["driver"]["commit"]
    if marker.get("pinned_driver_commit") != pinned or marker.get("safe_to_flash") is not False:
        raise ValueError("Untrusted vendor source pin or unsafe source manifest")
    if marker.get("joint_link_v17"):
        raise ValueError("v17 already configured; start with a fresh prepared vendor tree")
    data = makefile.read_text(encoding="utf-8")
    if not re.search(r"^CONFIG_PLATFORM_I386_PC\s*=\s*n\s*$", data, re.M):
        raise ValueError("The generic x86 platform must be disabled")
    platform_section = data.partition("ifeq ($(CONFIG_PLATFORM_ARM_SUN50IW1P1), y)")[2]
    if not platform_section:
        raise ValueError("Missing upstream SUN50 platform stanza")
    platform_section = platform_section.partition("ifeq ($(CONFIG_USB_HCI), y)")[0]
    if "EXTRA_CFLAGS += -DCONFIG_RESUME_IN_WORKQUEUE" in platform_section:
        raise ValueError("CONFIG_RESUME_IN_WORKQUEUE must remain disabled in the SUN50 stanza")
    if not re.search(r"^CONFIG_SDIO_HCI\s*=\s*y\s*$", data, re.M):
        raise ValueError("The vendor driver must use SDIO_HCI")
    pattern = r"^CONFIG_PLATFORM_ARM_SUN50IW1P1\s*=\s*n\s*$"
    amended, count = re.subn(pattern, "CONFIG_PLATFORM_ARM_SUN50IW1P1 = y", data, count=1, flags=re.M)
    if count != 1:
        raise ValueError("Cannot uniquely activate legacy Sunxi SDIO platform branch")
    # Old SUN50 naming is reused ONLY for these external ABI imports. This does
    # not assert that the M6 uses an ARM64 SoC or shares that board's pins.
    marker["joint_link_v17"] = {
        "intent": "offline-modpost-linkage-only",
        "legacy_platform_branch": "CONFIG_PLATFORM_ARM_SUN50IW1P1=y (ABI import only)",
        "expected_external_symbols": list(EXPECTED_SYMBOLS),
        "m6_gpio_verified": False,
        "m6_dtb_verified": False,
        "m6_runtime_verified": False,
        "safe_to_load": False,
        "safe_to_flash": False,
    }
    makefile.write_text(amended, encoding="utf-8")
    manifest.write_text(json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return marker["joint_link_v17"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prepared-tree", type=pathlib.Path, required=True)
    ap.add_argument("--pins", type=pathlib.Path, required=True)
    args = ap.parse_args()
    try:
        result = configure(args.prepared_tree, args.pins)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("V17_PREPARE_BLOCKED:", exc, file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
