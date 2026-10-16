#!/usr/bin/env python3
"""Offline audit of two public V851S/V851SE reference device trees.

No actual M6 DTB is present. Evidence about a DIFFERENT board is NEVER
hardware proof; do not copy its GPIO, load a module, or flash firmware.
"""
import argparse
import json
from pathlib import Path
import re
import sys

REFERENCES = {
    'gxcreator': {
        'url': 'https://raw.githubusercontent.com/gxcreator/aa-smartbox-re/00fa1232a2faa04b91efb4dbd4d7e345489b7c1a/info/decompiled-tree-linux.dts',
        'soc_compatible': 'allwinner,v851s', 'regon': 'PE6', 'chip_en': 'PH13',
    },
    'hbouhadji': {
        'url': 'https://raw.githubusercontent.com/hbouhadji/prototype-v851s-port/05d8262010922cefe05592238e8f60f98dab4613/analyse-v851s/stock-full.dts',
        'soc_compatible': 'allwinner,v851se', 'regon': 'PA11', 'chip_en': 'PE9',
    },
}


def node_body(text: str, name: str) -> str:
    """Find literal named DTS node body, counting nested braces."""
    m = re.search(r'(?m)^\s*' + re.escape(name) + r'\s*\{', text)
    if not m:
        raise ValueError('DTS node missing: ' + name)
    depth = 1
    for pos in range(m.end(), len(text)):
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
            if depth == 0:
                return text[m.end():pos]
    raise ValueError('Unbalanced DTS node: ' + name)


def prop(node: str, key: str) -> str:
    m = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*=\s*(.*?);', node, re.S)
    if not m:
        raise ValueError('DTS property missing: ' + key)
    return m.group(1).strip()


def number_cells(node: str, key: str) -> list[int]:
    value = prop(node, key)
    m = re.fullmatch(r'<\s*(.*?)\s*>', value, re.S)
    if not m:
        raise ValueError(key + ': not DTS number cells')
    parts = m.group(1).split()
    if not parts or any(not re.fullmatch(r'(?:0[xX][0-9a-fA-F]+|[0-9]+)', p) for p in parts):
        raise ValueError(key + ': bad number cells')
    return [int(p, 16 if p.lower().startswith('0x') else 10) for p in parts]


def text_cells(node: str, key: str) -> list[str]:
    parts = re.findall(r'"([^"]*)"', prop(node, key))
    if not parts:
        raise ValueError(key + ': missing string values')
    # Some DTB decompilers emit NUL-delimited strings in one quoted literal.
    return [t for value in parts for t in value.split(r'\0') if t]


def gpio_reference(node: str, key: str) -> str:
    vals = number_cells(node, key)
    if len(vals) != 7 or not (0 <= vals[1] <= 25 and 0 <= vals[2] <= 31):
        raise ValueError(key + ': not a plausible vendor seven-cell GPIO')
    return 'P' + chr(ord('A') + vals[1]) + str(vals[2])


def inspect(text: str) -> dict:
    root = node_body(text, '/')
    sdio = node_body(text, 'sdmmc@04021000')
    wlan = node_body(text, 'wlan@0')
    regs = number_cells(sdio, 'reg')
    bus = number_cells(wlan, 'wlan_busnum')
    width = number_cells(sdio, 'bus-width')
    if len(regs) != 4 or len(bus) != 1 or len(width) != 1:
        raise ValueError('Unexpected register/bus/width property')
    if 'allwinner,sunxi-wlan' not in text_cells(wlan, 'compatible'):
        raise ValueError('Incorrect WLAN compatible')
    return {
        'root_compatible': text_cells(root, 'compatible'),
        'mmc1_address': regs[1],
        'mmc1_status': text_cells(sdio, 'status')[0],
        'mmc1_bus_width': width[0],
        'wlan_bus': bus[0],
        'wlan_status': text_cells(wlan, 'status')[0],
        'wlan_regon_reference_only': gpio_reference(wlan, 'wlan_regon'),
        'chip_en_reference_only': gpio_reference(wlan, 'chip_en'),
        'contains_target_board_identifier': 'v851s-lybox_rtl8' in text.lower(),
    }


def audit(first: str, second: str) -> dict:
    data = {'gxcreator': inspect(first), 'hbouhadji': inspect(second)}
    checks = {}
    for label, item in data.items():
        expected = REFERENCES[label]
        checks[label + '_soc_variant'] = expected['soc_compatible'] in item['root_compatible']
        checks[label + '_mmc1_host'] = item['mmc1_address'] == 0x04021000
        checks[label + '_mmc1_enabled_in_reference'] = item['mmc1_status'] == 'okay'
        checks[label + '_wlan_enabled_in_reference'] = item['wlan_status'] == 'okay'
        checks[label + '_sdio1_x4'] = item['wlan_bus'] == 1 and item['mmc1_bus_width'] == 4
        checks[label + '_pin_matches_reference'] = (
            item['wlan_regon_reference_only'] == expected['regon']
            and item['chip_en_reference_only'] == expected['chip_en'])
        checks[label + '_not_target_board'] = not item['contains_target_board_identifier']
    checks['two_different_soc_variants'] = (
        data['gxcreator']['root_compatible'] != data['hbouhadji']['root_compatible'])
    checks['different_wlan_power_pins'] = (
        data['gxcreator']['wlan_regon_reference_only'] != data['hbouhadji']['wlan_regon_reference_only']
        and data['gxcreator']['chip_en_reference_only'] != data['hbouhadji']['chip_en_reference_only'])
    ok = all(checks.values())
    return {
        'schema': 'm6.public-dts-reference-audit.v19',
        'status': 'REFERENCE_AUDIT_PASS_NOT_M6_VERIFIED' if ok else 'REFERENCE_AUDIT_FAILED',
        'research_checks_passed': ok,
        'source_urls_pinned': {n: r['url'] for n, r in REFERENCES.items()},
        'checks': checks,
        'reference_data': data,
        'note': 'Two public references are V851S vs V851SE; both have SDIO1, but power pins differ. Neither is an M6 v851s-lybox_rtl8 verified DTB.',
        'm6_actual_dtb_verified': False,
        'm6_gpio_verified': False,
        'm6_sdio_wiring_verified': False,
        'device_driver_runtime_verified': False,
        'safe_to_load': False,
        'safe_to_flash': False,
        'next_evidence': [
            'Authenticated target-board v851s-lybox_rtl8 DTB from original firmware or read-only partition dump',
            'Actual GPIO / regulator / clock / pinctrl / mmc-pwrseq assignment of the M6',
            'Read-only on-device enumeration or manufacturer documentation',
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gx', type=Path, required=True)
    p.add_argument('--hb', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    try:
        gx = args.gx.read_text(encoding='utf-8')
        hb = args.hb.read_text(encoding='utf-8')
        result = audit(gx, hb)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result['research_checks_passed'] else 3
    except (OSError, ValueError, IndexError) as err:
        print('V19_BLOCKED:', err, file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
