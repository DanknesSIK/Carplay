#!/usr/bin/env python3
"""Verify offline Kbuild cross-module modpost linkage. NOT device compatibility."""
import argparse
import json
import pathlib
import re
import subprocess
import sys

SYMBOLS = ("sunxi_wlan_set_power", "sunxi_wlan_get_bus_index", "sunxi_mmc_rescan_card")
PLATFORM = "sunxi_m6_platform_v16"


def exported_symbols(symvers_text: str) -> dict:
    """Return expected GPL exports provided by the v16 module's Module.symvers."""
    found = {}
    for line in symvers_text.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        _crc, symbol, provider, export = fields[:4]
        if symbol in SYMBOLS and pathlib.PurePosixPath(provider).name == PLATFORM and export == "EXPORT_SYMBOL_GPL":
            found[symbol] = provider
    return found


def undefined_symbols(nm_text: str) -> set:
    """U symbols can remain in .ko ELF: MODPOST+depends resolve the modules."""
    return set(re.findall(r"(?m)^\s*U\s+(sunxi_(?:wlan_set_power|wlan_get_bus_index|mmc_rescan_card))\s*$", nm_text))


def validate(link: dict) -> list:
    issues = []
    if set(link["exports"]) != set(SYMBOLS):
        issues.append("Missing required v16 GPL exports in Module.symvers")
    if set(link["wifi_undefined_sunxi_symbols"]) != set(SYMBOLS):
        issues.append("RTL8733BS did not reference exactly the 3 legacy platform symbols")
    if PLATFORM not in link["wifi_dependencies"]:
        issues.append("Wi-Fi .ko does not declare a dependency on the v16 platform module")
    if link["wifi_vermagic"] != link["platform_vermagic"] or not re.match(r"^7\.2\.7(?:-[^\s]+)?\s", link["wifi_vermagic"]):
        issues.append("Module vermagic mismatch or wrong experimental kernel")
    if link["wifi_module_name"] != "8733bs" or link["platform_module_name"] != PLATFORM:
        issues.append("Unexpected module names")
    if link["wifi_elf"] != "ELF32/ARM" or link["platform_elf"] != "ELF32/ARM":
        issues.append("One or both modules are not ARM32 ELF")
    if not link["legacy_platform_branch_enabled"]:
        issues.append("Legacy platform branch is not enabled on the isolated v17 Wi-Fi tree")
    return issues


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def elf_arch(path: pathlib.Path) -> str:
    result = command("readelf", "-h", str(path))
    if re.search(r"Class:\s*ELF32", result) and re.search(r"Machine:\s*ARM\b", result):
        return "ELF32/ARM"
    return "other"


def collect(platform_dir: pathlib.Path, wifi_dir: pathlib.Path) -> dict:
    platform_ko = platform_dir / (PLATFORM + ".ko")
    wifi_ko = wifi_dir / "8733bs.ko"
    symvers = platform_dir / "Module.symvers"
    marker = wifi_dir / "M6_OFFLINE_DRIVER_FORK.json"
    makefile = wifi_dir / "Makefile"
    for p in (platform_ko, wifi_ko, symvers, marker, makefile):
        if not p.is_file() or p.stat().st_size == 0:
            raise ValueError("Missing required built module or provenance input: " + str(p))
    info = json.loads(marker.read_text(encoding="utf-8"))
    if info.get("joint_link_v17", {}).get("intent") != "offline-modpost-linkage-only":
        raise ValueError("Missing verified v17 offline prepared-tree marker")
    if info.get("safe_to_flash") is not False:
        raise ValueError("Unsafe prepared-tree marker")
    platform_vermagic = command("modinfo", "-F", "vermagic", str(platform_ko))
    wifi_vermagic = command("modinfo", "-F", "vermagic", str(wifi_ko))
    link = {
        "exports": exported_symbols(symvers.read_text(encoding="utf-8")),
        "wifi_undefined_sunxi_symbols": sorted(undefined_symbols(command("nm", "-u", str(wifi_ko)))),
        "wifi_dependencies": sorted(d.strip() for d in command("modinfo", "-F", "depends", str(wifi_ko)).split(",") if d.strip()),
        "wifi_vermagic": wifi_vermagic,
        "platform_vermagic": platform_vermagic,
        "wifi_module_name": command("modinfo", "-F", "name", str(wifi_ko)),
        "platform_module_name": command("modinfo", "-F", "name", str(platform_ko)),
        "wifi_elf": elf_arch(wifi_ko),
        "platform_elf": elf_arch(platform_ko),
        "legacy_platform_branch_enabled": bool(re.search(r"(?m)^CONFIG_PLATFORM_ARM_SUN50IW1P1\s*=\s*y\s*$", makefile.read_text(encoding="utf-8"))),
    }
    return link


def report(link: dict, issues: list) -> dict:
    return {
        "schema": "m6.v851s.offline-joint-modpost.v17",
        "status": "pass" if not issues else "fail",
        "checks_passed": not issues,
        "issues": issues,
        "joint_symbol_linkage_verified": not issues,
        "checks": link,
        "m6_board_proven": False,
        "m6_gpio_proven": False,
        "m6_dtb_proven": False,
        "m6_runtime_verified": False,
        "stock_linux_4_9_191_compatible": False,
        "safe_to_load": False,
        "safe_to_flash": False,
        "scope": "Offline Linux 7.2.7 module build only; no device access",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platform-dir", type=pathlib.Path, required=True)
    ap.add_argument("--wifi-dir", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    a = ap.parse_args()
    try:
        link = collect(a.platform_dir, a.wifi_dir)
        errors = validate(link)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        link, errors = {}, ["Validation could not run: " + str(exc)[:350]]
    payload = report(link, errors)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("V17_JOINT_MODPOST_" + ("PASS" if not errors else "FAIL"))
    if errors:
        for issue in errors:
            print("V17_BLOCKED:", issue, file=sys.stderr)
    return 0 if not errors else 5


if __name__ == "__main__":
    sys.exit(main())
