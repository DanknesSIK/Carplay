#!/usr/bin/env python3
"""Read-only V851S stage1 MMC1/DTB audit. Never certifies M6 hardware."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

MMC_PATH = '/soc/mmc@4021000'
EXPECTED = {
    'MMC': 'y', 'MMC_SUNXI': 'y', 'MODULES': 'y',
    'OF': 'y', 'CFG80211': 'y', 'REGULATOR': 'y',
    'PINCTRL_SUN8I_V853': 'y',
}


def added_file(patch: str, name: str) -> str:
    """Read only '+' additions for a given target file in a unified diff."""
    wanted = f'+++ b/{name}'
    in_file = False
    lines = []
    for line in patch.splitlines():
        if line.startswith('+++ '):
            in_file = (line == wanted)
            continue
        if line.startswith('--- ') and in_file:
            break
        if in_file and line.startswith('+') and not line.startswith('+++'):
            lines.append(line[1:])
    return '\n'.join(lines)


def dt_node_body(text: str, node: str) -> str:
    """Return braced node body, enough for properties in pinned DTSI."""
    match = re.search(r'(?m)^\s*' + re.escape(node) + r'\s*\{', text)
    if not match:
        return ''
    depth = 1
    start = match.end()
    for j in range(start, len(text)):
        if text[j] == '{': depth += 1
        if text[j] == '}':
            depth -= 1
            if depth == 0: return text[start:j]
    return ''


def kernel_flags(text: str) -> dict:
    flags = dict(re.findall(r'(?m)^CONFIG_([A-Z0-9_]+)=(\S+)\s*$', text))
    return {key: {'required': val, 'actual': flags.get(key, 'not-set'), 'ok': flags.get(key) == val} for key, val in EXPECTED.items()}


def fdt_info(blob: bytes) -> dict:
    """Conservative scan for literal, structurally plausible DTB headers only."""
    offsets = []
    magic = b'\xd0\x0d\xfe\xed'
    pos = 0
    while True:
        at = blob.find(magic, pos)
        if at < 0: break
        pos = at + 1
        if at + 40 > len(blob): continue
        (_magic, total, off_struct, off_strings, off_reserve,
         version, last_comp, _boot_cpu, strings_size, struct_size) = struct.unpack_from('>10I', blob, at)
        if not (40 <= total <= len(blob) - at and version >= 16 and last_comp <= version):
            continue
        if not (0 < off_struct < total and 0 < off_strings < total and 0 < off_reserve < total):
            continue
        if not (off_struct + struct_size <= total and off_strings + strings_size <= total):
            continue
        offsets.append(at)
    return {'size_bytes': len(blob), 'valid_literal_fdt_candidates': len(offsets), 'offsets': offsets[:6]}


def inspect_dtb(dtb: Path) -> dict:
    """Inspect compiled prototype DTB without accessing any hardware."""
    def prop(node, key):
        p = subprocess.run(['fdtget', '-t', 's', str(dtb), node, key], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    compat = prop('/', 'compatible')
    sdio = prop(MMC_PATH, 'status')
    pwrseq = prop(MMC_PATH, 'mmc-pwrseq')
    return {
        'prototype_compatible': compat,
        'mmc1_status': sdio,
        'mmc1_status_is_disabled': sdio == 'disabled',
        'mmc1_pwrseq_property_present': pwrseq is not None,
        'is_prototype_not_m6': bool(compat and 'catplay,v851s-dongle-stage1' in compat),
    }


def audit(patch_text: str, stage1_text: str, config_text: str,
          dtb: Path | None = None, stock_kernel: Path | None = None) -> dict:
    dtsi = added_file(patch_text, 'arch/arm/boot/dts/allwinner/sun8i-v853.dtsi')
    lizard = added_file(patch_text, 'arch/arm/boot/dts/allwinner/sun8i-v851s-lizard.dts')
    mmc1 = dt_node_body(dtsi, 'mmc1: mmc@4021000')
    flags = kernel_flags(config_text)
    source_tests = {
        'pinned_dtsi_mmc1_present': bool(mmc1),
        'pinned_dtsi_mmc1_disabled': bool(re.search(r'\bstatus\s*=\s*"disabled"\s*;', mmc1)),
        'stage1_has_no_mmc1_override': not bool(re.search(r'&mmc1\s*\{', stage1_text)),
        'stage1_does_not_declare_m6_wifi': not bool(re.search(r'v851s-lybox_rtl8|research,board-verified|rtl8733bs', stage1_text, re.I)),
        'lizard_is_separate_reference_board': 'wifi_pwrseq' in lizard and 'xr829:' in lizard,
        'research_kernel_flags_enabled': all(x['ok'] for x in flags.values()),
    }
    built = inspect_dtb(dtb) if dtb else None
    if built is not None:
        source_tests['built_stage1_dtb_mmc1_disabled'] = built['mmc1_status_is_disabled']
        source_tests['built_dtb_is_prototype'] = built['is_prototype_not_m6']
        source_tests['built_dtb_does_not_enable_pwrseq'] = not built['mmc1_pwrseq_property_present']
    stock = None
    if stock_kernel:
        data = stock_kernel.read_bytes()
        if len(data) > 32 * 1024 * 1024: raise ValueError('Stock file too large for a boot-header audit')
        stock = fdt_info(data)
        stock['android_boot_magic'] = data.startswith(b'ANDROID!')
        stock['m6_board_marker_found'] = b'v851s-lybox_rtl8' in data
        stock['note'] = 'Literal FDT scan in this sample only; does not rule out a DTB in another partition.'
    is_ok = all(source_tests.values())
    return {
        'schema': 'm6.v851s.stage1-dtb-audit.v18',
        'status': 'research-check-pass' if is_ok else 'research-check-fail',
        'research_checks_passed': is_ok,
        'source_checks': source_tests,
        'kernel_config_flags': flags,
        'built_stage1_dtb': built,
        'stock_boot_file_scan': stock,
        'reference_lizard_is_NOT_the_M6': True,
        'stage1_dtb_has_WIFI_enabled': False if is_ok else None,
        'm6_actual_wifi_gpio_known': False,
        'm6_actual_sdio_wiring_verified': False,
        'm6_dtb_verified': False,
        'm6_wifi_runtime_ready': False,
        'safe_to_load': False,
        'safe_to_flash': False,
        'next_missing_evidence': [
            'An authenticated DTB for v851s-lybox_rtl8 (not reference Lizard)',
            'Verified M6 Wi-Fi regulator/GPIO and MMC mapping',
            'Read-only runtime enumeration or equivalent vendor board documentation',
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--patch', type=Path, required=True)
    p.add_argument('--stage1-dts', type=Path, required=True)
    p.add_argument('--kernel-config', type=Path, required=True)
    p.add_argument('--dtb', type=Path)
    p.add_argument('--stock-kernel', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    try:
        report = audit(a.patch.read_text(encoding='utf-8'), a.stage1_dts.read_text(encoding='utf-8'),
                       a.kernel_config.read_text(encoding='utf-8'), a.dtb, a.stock_kernel)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report['research_checks_passed'] else 4
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        print('V18_AUDIT_BLOCKED:', e, file=sys.stderr)
        return 5


if __name__ == '__main__':
    sys.exit(main())
