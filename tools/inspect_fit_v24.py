#!/usr/bin/env python3
"""Inspect U-Boot FIT metadata and plaintext FDT image references, read-only.

FIT (.itb) IS an FDT but IS NOT itself the board's boot-time device tree.
Only inspect local data. Do not execute firmware, verify boot signatures,
load modules, connect to hardware, flash, or certify the M6 board.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys

from scan_fdt_v20 import validate_fdt, align4, MAX_FDT

MAX_INPUT = 1024 * 1024 * 1024
MAX_IMAGE_NODES = 128
MAX_CONFIG_NODES = 128
MAX_PROPS = 4096
MAX_PROPERTY_LABEL = 1024
IMAGE_KEYS = {'type', 'description', 'compression', 'data', 'data-offset',
              'data-size', 'data-position', 'arch', 'os'}
CONFIG_KEYS = {'fdt', 'kernel', 'firmware', 'description'}
FDT_DATA_TYPES = {'flat_dt'}


def _read_strings(raw: bytes) -> list[str]:
    if not raw or not raw.endswith(b'\0'):
        return []
    return [x.decode('utf-8', 'replace')[:200] for x in raw.split(b'\0') if x][:16]


def _numeric(raw: bytes) -> int | None:
    if len(raw) not in (4, 8):
        return None
    return int.from_bytes(raw, 'big')


def _fit_nodes(data: bytes | mmap.mmap, at: int, total: int) -> tuple[dict, dict, dict]:
    """Bounded non-executing FDT token walk; only retain useful FIT metadata."""
    if at + 40 > len(data) or at + total > len(data):
        raise ValueError('FIT header out of file bounds')
    hdr = struct.unpack_from('>10I', data, at)
    struct_start, str_start, str_len, struct_len = hdr[2], hdr[3], hdr[8], hdr[9]
    ptr, end = at + struct_start, at + struct_start + struct_len
    strings = bytes(data[at+str_start:at+str_start+str_len])
    stack: list[str] = []
    images: dict = {}
    configs: dict = {}
    main: dict = {}
    prop_count = 0
    while ptr + 4 <= end:
        tok = struct.unpack_from('>I', data, ptr)[0]
        ptr += 4
        if tok == 1:  # FDT_BEGIN_NODE
            nul = data.find(b'\0', ptr, end)
            if nul < 0 or nul - ptr > 256:
                raise ValueError('Malformed FIT node name')
            name = bytes(data[ptr:nul]).decode('utf-8', 'replace')
            stack.append(name)
            ptr = at + align4(nul + 1 - at)
            if len(stack) == 3:
                if stack[1] == 'images':
                    if len(images) >= MAX_IMAGE_NODES or name in images:
                        raise ValueError('Excess or duplicate FIT image node')
                    images[name] = {}
                if stack[1] == 'configurations':
                    if len(configs) >= MAX_CONFIG_NODES or name in configs:
                        raise ValueError('Excess or duplicate FIT configuration node')
                    configs[name] = {}
        elif tok == 2:  # FDT_END_NODE
            if not stack:
                raise ValueError('Unbalanced FIT nodes')
            stack.pop()
        elif tok == 3:  # FDT_PROP
            if ptr + 8 > end:
                raise ValueError('FIT property header truncated')
            length, off = struct.unpack_from('>II', data, ptr)
            ptr += 8
            if off >= len(strings) or length > end - ptr:
                raise ValueError('FIT property bounds invalid')
            key_end = strings.find(b'\0', off)
            if key_end < 0:
                raise ValueError('FIT property key unterminated')
            key = strings[off:key_end].decode('utf-8', 'replace')
            value_at = ptr
            ptr = at + align4(ptr + length - at)
            if ptr > end:
                raise ValueError('FIT property alignment out of bounds')
            prop_count += 1
            if prop_count > MAX_PROPS:
                raise ValueError('Too many FIT properties')
            # Only properties of direct child images/configs, and default config.
            if len(stack) == 2 and stack[1] == 'configurations' and key == 'default':
                main['default'] = _read_strings(bytes(data[value_at:value_at+min(length,MAX_PROPERTY_LABEL)]))
            if len(stack) != 3:
                continue
            dest = (images.get(stack[2]) if stack[1] == 'images' else
                    configs.get(stack[2]) if stack[1] == 'configurations' else None)
            allowed = IMAGE_KEYS if stack[1] == 'images' else CONFIG_KEYS
            if dest is None or key not in allowed:
                continue
            if key in dest:
                raise ValueError('Duplicate FIT image/config property')
            if key == 'data':
                dest['data'] = {'at': value_at, 'length': length}
            elif length > MAX_PROPERTY_LABEL:
                dest[key] = {'unsupported_oversized_property_bytes': length}
            elif key in ('data-offset', 'data-position', 'data-size'):
                dest[key] = _numeric(bytes(data[value_at:value_at+length]))
            else:
                dest[key] = _read_strings(bytes(data[value_at:value_at+length]))
        elif tok == 4:  # FDT_NOP
            pass
        elif tok == 9:
            break
        else:
            raise ValueError('Invalid FIT token')
    return images, configs, main


def inspect_fit(data: bytes | mmap.mmap, at: int = 0) -> dict:
    header = validate_fdt(data, at)
    if header is None or header['fdt_kind'] != 'u-boot-fit-container':
        raise ValueError('Not a structurally valid U-Boot FIT container')
    total = header['size_bytes']
    images, configs, main = _fit_nodes(data, at, total)
    if not images or not configs:
        raise ValueError('FIT index missing images or configurations')
    parsed_images = []
    references = {}
    for conf_name, values in configs.items():
        references[conf_name] = {'fdt_images': values.get('fdt', []),
                                 'firmware_images': values.get('firmware', []),
                                 'kernel_images': values.get('kernel', [])}
    for name, props in images.items():
        kinds = props.get('type', [])
        compressions = props.get('compression', [])
        image_type = kinds[0] if isinstance(kinds,list) and kinds else None
        compression = compressions[0] if isinstance(compressions,list) and compressions else 'none'
        result = {
            'name': name[:200],
            'type': image_type,
            'compression': compression,
            'data_layout': 'none',
            'board_dt_fdt_structure_valid': False,
            'board_dt_blob_sha256': None,
            'board_dt_root_model': [],
            'board_dt_root_compatible': [],
            'hardware_nodes_reference_only': [],
            'not_target_board_authenticated': True,
        }
        size = props.get('data-size')
        data_pos = props.get('data-position')
        data_offset = props.get('data-offset')
        data_property = props.get('data')
        data_start = None
        data_length = None
        if data_property is not None:
            result['data_layout'] = 'embedded-property'
            data_start, data_length = data_property['at'], data_property['length']
        elif data_pos is not None:
            # data-position is an absolute address/position, NOT necessarily
            # a byte offset in a local firmware image. Do not dereference it.
            result['data_layout'] = 'external-position-unresolved'
            result['external_data_position_untrusted'] = data_pos
            result['declared_data_size'] = size
        elif data_offset is not None:
            result['data_layout'] = 'external-relative-offset'
            result['declared_data_offset'] = data_offset
            result['declared_data_size'] = size
            if isinstance(data_offset,int) and isinstance(size,int):
                # FIT external store is immediately after the FDT, rounded to 4.
                candidate_pos = at + align4(total) + data_offset
                if (0 < size <= MAX_FDT and
                    at <= candidate_pos <= len(data) and
                    size <= len(data) - candidate_pos):
                    data_start, data_length = candidate_pos, size
                else:
                    result['external_data_out_of_bounds'] = True
        if image_type in FDT_DATA_TYPES and compression == 'none' and data_start is not None:
            if 40 <= data_length <= MAX_FDT:
                nested = validate_fdt(data, data_start)
                if (nested and nested['size_bytes'] <= data_length and
                    nested['fdt_kind'] == 'board-device-tree-candidate'):
                    result['board_dt_fdt_structure_valid'] = True
                    result['board_dt_blob_sha256'] = hashlib.sha256(
                        data[data_start:data_start+nested['size_bytes']]).hexdigest()
                    result['board_dt_root_model'] = nested['root_model']
                    result['board_dt_root_compatible'] = nested['root_compatible']
                    result['hardware_nodes_reference_only'] = nested['hardware_nodes_reference_only']
        elif image_type in FDT_DATA_TYPES and compression != 'none':
            result['not_inspected_reason'] = 'Compressed FDT; decompression not attempted'
        parsed_images.append(result)
    return {
        'schema': 'm6.v851s.fit-separation.v24',
        'source_kind': 'u-boot-fit-container-not-board-device-tree',
        'fit_absolute_offset': at,
        'fit_fdt_metadata_length': total,
        'default_configuration': main.get('default', []),
        'configurations': references,
        'image_entries': parsed_images,
        'fit_image_count': len(parsed_images),
        'fit_config_count': len(configs),
        'embedded_or_relative_board_dtb_candidates': sum(
            x['board_dt_fdt_structure_valid'] for x in parsed_images
        ),
        'fit_signatures_cryptographically_verified': False,
        'actual_M6_DTB_authenticated': False,
        'running_M6_firmware_version_matched': False,
        'safe_to_load': False,
        'safe_to_flash': False,
        'note': 'Metadata inspection only. Configuration selection, integrity, signatures and physical board support are unverified.'
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    try:
        path = args.input
        if path.is_symlink() or not path.is_file():
            raise ValueError('Expected a local, regular, non-symlink file')
        if path.stat().st_size > MAX_INPUT:
            raise ValueError('File exceeds 1 GiB safety limit')
        with path.open('rb') as f:
            if not path.stat().st_size:
                raise ValueError('Empty FIT file')
            with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
                doc = inspect_fit(mm)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'source_kind':doc['source_kind'],
                          'fit_image_count':doc['fit_image_count'],
                          'board_dt_candidates':doc['embedded_or_relative_board_dtb_candidates'],
                          'safe_to_flash':False},ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print('V24_FIT_READONLY_ERROR:',exc,file=sys.stderr)
        return 4


if __name__=='__main__':
    sys.exit(main())
