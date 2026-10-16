#!/usr/bin/env python3
"""Bounded, read-only Allwinner TOC1 index inspection.

Only inspects caller-provided local bytes. No flashing, boot modification,
driver loading, hardware access, key handling, or firmware execution.
Do NOT interpret a TOC1/DTB match as proof of the real M6 board.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys

from scan_fdt_v20 import validate_fdt

TOC_MAGIC = 0x89119800
STAMP = 0x5f0a6c39
TOC_HDR = 64
ITEM_HDR = 368
ITEM_END = b'IIE;'
MAIN_END = b'MIE;'
MAX_IMAGE_BYTES = 1024 * 1024 * 1024
MAX_TOC_BYTES = 64 * 1024 * 1024
MAX_ITEMS = 64
MAX_CANDIDATES = 16
MAX_MAGIC_CHECKS = 50000


def _u32(buf, pos: int) -> int:
    return struct.unpack_from('<I', buf, pos)[0]


def _checksum_ok(buf, at: int, length: int, original: int) -> bool:
    """Allwinner additive checksum: checksum field is treated as STAMP."""
    view = memoryview(buf)[at:at+length]
    try:
        total = 0
        for offset in range(0, length, 4):
            total = (total + struct.unpack_from('<I', view, offset)[0]) & 0xffffffff
        return ((total + STAMP) & 0xffffffff) == ((2 * original) & 0xffffffff)
    finally:
        view.release()


def parse_toc1(buf: bytes | mmap.mmap, at: int = 0) -> dict | None:
    """Return validated container metadata; reject malformed/bad-checksum TOCs."""
    size = len(buf)
    if at < 0 or at + TOC_HDR > size:
        return None
    try:
        if _u32(buf, at+16) != TOC_MAGIC or bytes(buf[at+60:at+64]) != MAIN_END:
            return None
        count = _u32(buf, at+32)
        total = _u32(buf, at+36)
        chk = _u32(buf, at+20)
        if not (1 <= count <= MAX_ITEMS):
            return None
        table_end = TOC_HDR + ITEM_HDR * count
        if not (table_end <= total <= MAX_TOC_BYTES and total <= size-at and total % 512 == 0):
            return None
        if not _checksum_ok(buf, at, total, chk):
            return None

        items = []
        seen_names = set()
        spans = []
        for i in range(count):
            start = at + TOC_HDR + ITEM_HDR*i
            name_raw = bytes(buf[start:start+64])
            name = name_raw.split(b'\x00', 1)[0]
            if not name or len(name) > 63 or any(c < 32 or c >= 127 for c in name):
                return None
            name_decoded = name.decode('ascii')
            if name_decoded in seen_names:
                return None
            seen_names.add(name_decoded)
            offset, length, encrypted, item_type, load_addr, _idx = struct.unpack_from('<6I', buf, start+64)
            if bytes(buf[start+364:start+368]) != ITEM_END:
                return None
            # Alignments enforced here to reject arbitrary incidental bytes; 512-byte
            # alignment follows public non-secure TOC1 image builder.
            if offset % 512 or offset < (table_end + 511)//512*512:
                return None
            if not (0 < length <= total and offset <= total - length):
                return None
            if encrypted not in (0, 1):
                return None
            span = (offset, offset+length)
            if any(span[0] < b and a < span[1] for a, b in spans):
                return None
            spans.append(span)
            entry = {
                'name': name_decoded,
                'file_offset': at + offset,
                'relative_offset': offset,
                'size_bytes': length,
                'encrypted_flag': bool(encrypted),
                'item_type': item_type,
                'payload_sha256': hashlib.sha256(buf[at+offset:at+offset+length]).hexdigest(),
            }
            # Inspect DTB only in a named plaintext item. Do not decode encrypted items.
            if name_decoded.lower() in ('dtb', 'sunxi.dtb', 'fdt') and encrypted == 0:
                fdt = validate_fdt(buf, at+offset)
                if fdt and fdt['size_bytes'] <= length and fdt['is_board_device_tree_candidate']:
                    entry['literal_fdt_structure_valid'] = True
                    entry['dtb_root_model'] = fdt['root_model']
                    entry['dtb_root_compatible'] = fdt['root_compatible']
                    entry['mmc_wlan_nodes_reference_only'] = fdt['hardware_nodes_reference_only']
                else:
                    entry['literal_fdt_structure_valid'] = False
            else:
                entry['literal_fdt_structure_valid'] = None
            items.append(entry)
        return {
            'toc1_absolute_offset': at,
            'toc1_size_bytes': total,
            'header_checksum_valid': True,
            'item_count': count,
            'items': items,
            'untrusted_source': True,
            'target_board_authenticated': False,
            'safe_to_load': False,
            'safe_to_flash': False,
        }
    except (OverflowError, ValueError, IndexError, struct.error, TypeError):
        return None


def find_toc1(buf: bytes | mmap.mmap) -> tuple[list[dict], bool]:
    # Search the constant TOC magic, then infer candidate header at magic-16.
    signature = struct.pack('<I', TOC_MAGIC)
    start = 0
    checks = 0
    found = []
    while start < len(buf) and checks < MAX_MAGIC_CHECKS and len(found) < MAX_CANDIDATES:
        at = buf.find(signature, start)
        if at < 0:
            return found, False
        checks += 1
        start = at + 4
        if at < 16:
            continue
        item = parse_toc1(buf, at-16)
        if item:
            found.append(item)
    return found, buf.find(signature, start) != -1


def audit_buffer(buf: bytes | mmap.mmap, name: str = 'local-image') -> dict:
    containers, limited = find_toc1(buf)
    return {
        'schema': 'm6.v851s.toc1-readonly-audit.v21',
        'input_basename': Path(name).name,
        'input_size_bytes': len(buf),
        'input_sha256': hashlib.sha256(buf).hexdigest(),
        'toc1_candidates_validated': len(containers),
        'scan_incomplete_due_to_limits': limited,
        'toc1_containers': containers,
        'result': ('partial-scan' if limited else
                   'TOC1_CANDIDATES_UNAUTHENTICATED' if containers else
                   'NO_PLAINTEXT_TOC1_IN_THIS_FILE'),
        'absence_does_not_exclude_other_formats_or_partitions': True,
        'real_m6_board_dtb_verified': False,
        'safe_to_load': False,
        'safe_to_flash': False,
        'needs': 'An authenticated complete stock boot package or read-only full dump for the ACTUAL M6, with version reconciliation.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Local firmware/boot package only (not a device)')
    parser.add_argument('--out', type=Path, required=True, help='Local JSON; do not publish proprietary firmware')
    args = parser.parse_args()
    try:
        path = args.input
        if path.is_symlink() or not path.is_file():
            raise ValueError('Input must be a local non-symlink regular file')
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError('Image larger than supported 1-GiB limit')
        with path.open('rb') as f:
            if path.stat().st_size:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as buf:
                    result = audit_buffer(buf, path.name)
            else:
                result = audit_buffer(b'', path.name)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'result': result['result'],
                          'toc1_candidates_validated': result['toc1_candidates_validated'],
                          'safe_to_flash': False,
                          'report': str(args.out)}, ensure_ascii=False))
        return 5 if result['scan_incomplete_due_to_limits'] else 0
    except (OSError, ValueError) as exc:
        print('V21_READONLY_ERROR:', exc, file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
