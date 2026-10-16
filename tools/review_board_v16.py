#!/usr/bin/env python3
"""Static, fail-closed audit. Does not access M6 or generate firmware."""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "profiles/board_reference_evidence_v16.json"
SOURCE = ROOT / "drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16.c"
TEMPLATE = ROOT / "profiles/m6_unverified_wifi_v16.dts.txt"
EXPECTED = (
    "sunxi_wlan_set_power", "sunxi_wlan_get_bus_index", "sunxi_mmc_rescan_card"
)


def audit(evidence_path=EVIDENCE, source_path=SOURCE, template_path=TEMPLATE):
    evidence = json.loads(pathlib.Path(evidence_path).read_text(encoding="utf-8"))
    src = pathlib.Path(source_path).read_text(encoding="utf-8")
    template = pathlib.Path(template_path).read_text(encoding="utf-8")
    refs = evidence["reference_sources"]
    issues = []
    if len(refs) != 2 or refs[0]["wlan_regon_reference_gpio"] == refs[1]["wlan_regon_reference_gpio"]:
        issues.append("Independent reference board GPIOs must remain distinguishable")
    for symbol in EXPECTED:
        if not re.search(r"\b" + re.escape(symbol) + r"\s*\(", src):
            issues.append("Platform source missing function: " + symbol)
        if "EXPORT_SYMBOL_GPL(" + symbol + ")" not in src:
            issues.append("Platform source missing GPL export: " + symbol)
    # Intentional dual gates; never imply device compatibility from a green CI.
    if '"research,v851s-lybox-rtl8-wifi-verified"' not in src:
        issues.append("Missing distinct research-compatible string")
    if '"research,board-verified"' not in src:
        issues.append("Missing runtime board-evidence gate")
    if "DO NOT LOAD" not in src:
        issues.append("Missing experimental-only banner")
    if "mmc-host" not in src or "of_parse_phandle" not in src:
        issues.append("MMC host must be chosen by verified phandle")
    if re.search(r"<(?:&pio|0x25)\s+[^>]+>", template):
        issues.append("Unverified device-tree template MUST NOT encode GPIOs")
    if "NOT A COMPILE-READY DEVICE TREE" not in template:
        issues.append("Template must be explicitly non-deployable")
    if evidence.get("m6_specific_wifi_gpio_verified") is not False:
        issues.append("Unverified M6 GPIO must remain explicitly false")
    if evidence.get("m6_specific_dtb_obtained") is not False:
        issues.append("M6 DTB proof is missing and must remain explicitly false")
    if evidence.get("m6_actual_sdio_host_verified") is not False:
        issues.append("Unverified M6 MMC host must remain explicitly false")
    if "flash" not in evidence.get("forbidden_actions", []):
        issues.append("Flashing must remain forbidden")
    return {
        "schema": "m6.v851s.board-abi.audit.v16",
        "status": "static-check-passed" if not issues else "static-check-failed",
        "checks_passed": not issues,
        "issues": issues,
        "reference_sdio_host_candidates": sorted(set(r["wlan_busnum"] for r in refs)),
        "reference_regon_gpio_differ": refs[0]["wlan_regon_reference_gpio"] != refs[1]["wlan_regon_reference_gpio"],
        "abi_functions": list(EXPECTED),
        "m6_board_proven": False,
        "m6_gpio_proven": False,
        "m6_sdio_wiring_proven": False,
        "platform_module_kbuild_verified": False,
        "safe_to_load": False,
        "safe_to_flash": False,
        "note": "Static audit PASSED does not mean the M6 board is supported. CI kernel build is separate."
    }


def self_test():
    r = audit()
    assert r["checks_passed"] and not r["safe_to_load"] and not r["safe_to_flash"]
    assert r["abi_functions"] == list(EXPECTED)
    assert r["reference_regon_gpio_differ"]
    assert r["m6_board_proven"] is False
    print("SELFTEST PASS: 5 static/safety assertions")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", type=pathlib.Path)
    opts = ap.parse_args()
    if opts.self_test:
        self_test()
    else:
        result = audit()
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if opts.out:
            opts.out.parent.mkdir(parents=True, exist_ok=True)
            opts.out.write_text(payload, encoding="utf-8")
        print(payload)
        sys.exit(0 if result["checks_passed"] else 3)
