#!/usr/bin/env python3
"""Read-only, bounded PhoenixSuite IMAGEWTY firmware directory auditor.

This is an untrusted-input format *inspector*, not a device driver, firmware
extractor or flasher. Synthetic CI inputs are never M6 hardware evidence.

IMAGEWTY offsets used below follow Andre Przywara's GPL-2.0 sunxi-fw
sunxi-wty.c (header at 0, 0x400-byte entries, 64-bit size/offset fields).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys

import audit_toc1_v21 as toc1
import scan_fdt_v20 as fdt
import inspect_fit_v24 as fit

HEADER_SIZE = 0x400
ENTRY_SIZE = 0x400
MAX_ENTRIES = 256
MAX_INPUT_SIZE = 8 * 1024 * 1024 * 1024
MAX_NESTED_SEARCH = 64 * 1024 * 1024
IMAGE_MAGIC = b'IMAGEWTY'
ENTRY_NAMES_INTEREST = (
    'sunxi.fex', 'sunxi.dtb', 'dtb.fex', 'dtb', 'boot_package.fex',
    'boot_package_nor.fex', 'toc1.fex', 'u-boot.fex',
    'sys_partition.fex', 'sys_partition_nor.fex',
)


def _u32(data, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _u64(data, offset: int) -> int:
    return struct.unpack_from('<Q', data, offset)[0]


def _entry_name(data, offset: int) -> str | None:
    # WTY item filename starts at 9 * sizeof(u32); the size field starts at
    # 75 * sizeof(u32), so the filename must not run into numeric metadata.
    field = bytes(data[offset+36:offset+300])
    name = field.split(b'\x00', 1)[0]
    if not (0 < len(name) <= 255) or any(b < 32 or b > 126 for b in name):
        return None
    return name.decode('ascii')


def _scan_related_payload(data, name: str, start: int, length: int) -> dict:
    result: dict = {'related_entry': True, 'has_authenticated_m6_dtb': False}
    lower = name.lower()
    if lower in ('boot_package.fex', 'boot_package_nor.fex', 'toc1.fex'):
        toc = toc1.parse_toc1(data, start) if length <= toc1.MAX_TOC_BYTES else None
        if toc and toc['toc1_size_bytes'] <= length:
            result['toc1_index_valid'] = True
            result['toc1_entries'] = [
                {'name': x['name'], 'size_bytes': x['size_bytes'],
                 'literal_fdt_structure_valid': x['literal_fdt_structure_valid'],
                 'dtb_root_model': x.get('dtb_root_model', []),
                 'dtb_root_compatible': x.get('dtb_root_compatible', [])}
                for x in toc['items']
            ]
        else:
            result['toc1_index_valid'] = False
            result['note'] = 'Not a proven unencrypted TOC1; other boot package formats remain possible.'
    if lower in ('sunxi.fex', 'sunxi.dtb', 'dtb.fex', 'dtb', 'u-boot.fex'):
        limit = min(length, MAX_NESTED_SEARCH)
        if limit:
            # Only copy a bounded slice. A FDT/DTB can begin at any offset.
            blob = bytes(data[start:start+limit])
            found, incomplete = fdt.scan_candidates(blob)
            result['literal_fdt_candidates'] = [
                {'relative_offset': x['offset'], 'size_bytes': x['size_bytes'],
                 'fdt_kind': x['fdt_kind'],
                 'is_board_device_tree_candidate': x['is_board_device_tree_candidate'],
                 'root_model': x['root_model'], 'root_compatible': x['root_compatible']}
                for x in found
            ]
            result['nested_search_truncated'] = incomplete or length > MAX_NESTED_SEARCH
        else:
            result['literal_fdt_candidates'] = []
            result['nested_search_truncated'] = False
    # A FIT is an FDT-format index, not the board DTB. Look for FIT
    # metadata in a bounded subcomponent, including non-TOC boot packages.
    # Never execute referenced images or treat names as signed evidence.
    if lower in ('boot_package.fex', 'boot_package_nor.fex', 'toc1.fex',
                 'sunxi.fex', 'sunxi.dtb', 'dtb.fex', 'dtb', 'u-boot.fex'):
        limit = min(length, MAX_NESTED_SEARCH)
        blob = bytes(data[start:start+limit])
        found, incomplete = fdt.scan_candidates(blob)
        fit_nodes = [x for x in found if x['fdt_kind'] == 'u-boot-fit-container']
        fit_reports = []
        for item in fit_nodes[:4]:
            try:
                fit_reports.append(fit.inspect_fit(blob, item['offset']))
            except ValueError:
                fit_reports.append({'status':'FIT_METADATA_INVALID',
                                    'safe_to_flash':False,
                                    'actual_M6_DTB_authenticated':False})
        result['u_boot_fit_containers_seen'] = len(fit_nodes)
        result['u_boot_fit_metadata'] = fit_reports
        result['fit_scan_incomplete'] = incomplete or len(fit_nodes)>4 or length>MAX_NESTED_SEARCH
        result['contains_target_authenticated_dtb'] = False
    return result


def inspect_image(data: bytes | mmap.mmap, name: str = 'local-stock-image') -> dict:
    n = len(data)
    if n < HEADER_SIZE or bytes(data[:8]) != IMAGE_MAGIC:
        raise ValueError('Not an IMAGEWTY PhoenixSuite file')
    count = _u32(data, 60)
    claimed_size = _u64(data, 24)
    if not (1 <= count <= MAX_ENTRIES):
        raise ValueError('Invalid or excessive IMAGEWTY entry count')
    table_end = HEADER_SIZE + ENTRY_SIZE * count
    if not (table_end <= claimed_size <= n):
        raise ValueError('IMAGEWTY header size or entry table is truncated')
    if claimed_size > MAX_INPUT_SIZE:
        raise ValueError('IMAGEWTY declared size exceeds 8 GiB')
    spans = []
    entries = []
    for i in range(count):
        head = HEADER_SIZE + ENTRY_SIZE*i
        name_part = _entry_name(data, head)
        if name_part is None:
            raise ValueError('Invalid or unterminated PhoenixSuite entry filename')
        size = _u64(data, head + 75*4)
        off = _u64(data, head + 77*4)
        if size and (off < table_end or off > claimed_size or size > claimed_size-off):
            raise ValueError('PhoenixSuite payload outside declared image bounds')
        if size:
            spans.append((off, off+size, name_part))
        item = {
            'name': name_part,
            'file_offset': off,
            'size_bytes': size,
            'relevant_to_boot_or_dtb': name_part.lower() in ENTRY_NAMES_INTEREST,
        }
        if name_part.lower() in ENTRY_NAMES_INTEREST and size:
            # Hash only bounded relevant entries. Do not expose raw payload.
            if size <= MAX_NESTED_SEARCH:
                item['sha256'] = hashlib.sha256(data[off:off+size]).hexdigest()
            else:
                item['sha256'] = None
                item['hash_skipped_reason'] = 'Relevant payload over 64 MiB'
            item['offline_details'] = _scan_related_payload(data, name_part, off, size)
        entries.append(item)
    spans.sort(key=lambda x:x[0])
    for left, right in zip(spans, spans[1:]):
        if left[1] > right[0]:
            raise ValueError('Overlapping PhoenixSuite entry regions')
    return {
        'schema': 'm6.phoenixsuite-wty-readonly-index.v22',
        'source_basename': Path(name).name,
        'source_size_bytes': n,
        'declared_image_size_bytes': claimed_size,
        'entry_count': count,
        'format': 'PhoenixSuite IMAGEWTY',
        'entries': entries,
        'evidence_limitations': [
            'Directory and embedded FDT structure checks do not authenticate the target board.',
            'Other Allwinner containers, signed/encrypted FDT and partitions may remain undetected.',
            'No hardware access, firmware execution, writing, extraction, module loading or flashing.',
        ],
        'm6_real_device_dtb_authenticated': False,
        'm6_running_firmware_version_matched': False,
        'safe_to_load': False,
        'safe_to_flash': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        path = args.input
        if not path.is_file() or path.is_symlink():
            raise ValueError('Input must be a local regular, non-symlink file')
        size = path.stat().st_size
        if not (HEADER_SIZE <= size <= MAX_INPUT_SIZE):
            raise ValueError('Outside permitted size range (0x400 bytes to 8 GiB)')
        with path.open('rb') as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
                result = inspect_image(data, path.name)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'entry_count': result['entry_count'],
                          'relevant_entries': [x['name'] for x in result['entries']
                                              if x['relevant_to_boot_or_dtb']],
                          'report': str(args.out), 'safe_to_flash': False},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, struct.error) as exc:
        print('V22_WTY_READONLY_ERROR:', exc, file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
