#!/usr/bin/env python3
"""Read-only offline scan for literal FDT blobs in OWNED firmware samples.

Never talks to hardware, never flashes, installs a module, executes input, or
claims that a DTB belongs to a target board solely because of its contents.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys
import zipfile

MAGIC = b'\xd0\x0d\xfe\xed'
HEADER = struct.Struct('>10I')
MAX_FILE = 1024 * 1024 * 1024  # limit input to 1 GiB
MAX_FDT = 16 * 1024 * 1024
MAX_FILES = 64
MAX_FDTS_PER_FILE = 32
MAX_MAGIC_ATTEMPTS = 100000
MAX_ZIP_MEMBER = 256 * 1024 * 1024
MAX_ZIP_TOTAL = 512 * 1024 * 1024
HARDWARE_NODES = ('wlan@', 'wifi@', 'sdmmc@', 'mmc@')
HARDWARE_PROPS = ('wlan_busnum', 'bus-width', 'status', 'wlan_regon', 'chip_en', 'reg',
                  'mmc-pwrseq', 'non-removable', 'cap-sdio-irq', 'clock-names')


def align4(n: int) -> int:
    return (n + 3) & ~3


def decode_strings(val: bytes) -> list[str]:
    if not val.endswith(b'\x00') or not val:
        return []
    return [s.decode('utf-8', 'replace')[:200] for s in val.split(b'\x00') if s][:16]


def validate_fdt(buf: bytes | mmap.mmap, at: int = 0) -> dict | None:
    """Fully check FDT header, reserved map and structure/string token bounds."""
    n = len(buf)
    if at < 0 or n - at < 40:
        return None
    try:
        magic, total, st, ss, mr, version, compat, _cpu, ns, nt = HEADER.unpack_from(buf, at)
        if magic != 0xd00dfeed or not (72 <= total <= MAX_FDT and total <= n-at):
            return None
        if not (16 <= version <= 25 and 16 <= compat <= version):
            return None
        if not (40 <= st < total and st % 4 == 0 and nt >= 8 and st + nt <= total):
            return None
        if not (40 <= ss < total and ns > 0 and ss + ns <= total):
            return None
        if not (40 <= mr < st and mr % 8 == 0):
            return None
        st_beg, st_end = at + st, at + st + nt
        ss_beg, ss_end = at + ss, at + ss + ns
        strings = bytes(buf[ss_beg:ss_end])
        if strings[-1:] != b'\0':
            return None
        # Header maps usually place reservations before structure.
        reserve_ptr = at + mr
        found_reserve_end = False
        while reserve_ptr + 16 <= st_beg:
            base, length = struct.unpack_from('>QQ', buf, reserve_ptr)
            reserve_ptr += 16
            if base == length == 0:
                found_reserve_end = True
                break
        if not found_reserve_end:
            return None
        pos = st_beg
        depth = 0
        names = []
        root_seen = False
        saw_end = False
        root_compatible = []
        root_model = []
        nodes = []
        tokens = 0
        while pos + 4 <= st_end:
            token = struct.unpack_from('>I', buf, pos)[0]
            pos += 4
            tokens += 1
            if tokens > 200_000:
                return None
            if token == 1:  # FDT_BEGIN_NODE
                if depth >= 64:
                    return None
                nul = buf.find(b'\0', pos, st_end)
                if nul < 0 or nul - pos > 256:
                    return None
                name = bytes(buf[pos:nul]).decode('utf-8', 'replace')
                if depth == 0:
                    if root_seen or name:
                        return None
                    root_seen = True
                names.append(name)
                depth += 1
                pos = at + align4(nul + 1 - at)
            elif token == 2:  # FDT_END_NODE
                if depth == 0:
                    return None
                names.pop()
                depth -= 1
            elif token == 3:  # FDT_PROP
                if depth == 0 or pos + 8 > st_end:
                    return None
                length, nameoff = struct.unpack_from('>II', buf, pos)
                pos += 8
                if nameoff >= len(strings) or length > st_end-pos:
                    return None
                name_end = strings.find(b'\0', nameoff)
                if name_end < 0 or name_end-nameoff > 128:
                    return None
                key = strings[nameoff:name_end].decode('ascii', 'replace')
                val = bytes(buf[pos:pos+length])
                pos = at + align4(pos + length - at)
                if pos > st_end:
                    return None
                if depth == 1 and key == 'compatible':
                    root_compatible = decode_strings(val)
                if depth == 1 and key == 'model':
                    root_model = decode_strings(val)
                if any(names[-1].startswith(prefix) for prefix in HARDWARE_NODES) and key in HARDWARE_PROPS:
                    item = next((x for x in nodes if x['path'] == '/'+'/'.join(x for x in names if x)), None)
                    if item is None:
                        if len(nodes) >= 60:
                            continue
                        item = {'path': '/'+'/'.join(x for x in names if x), 'properties': {}}
                        nodes.append(item)
                    if key in ('status', 'clock-names'):
                        item['properties'][key] = decode_strings(val)
                    elif key in ('non-removable', 'cap-sdio-irq'):
                        item['properties'][key] = True
                    elif len(val) % 4 == 0 and len(val) <= 32:
                        item['properties'][key] = list(struct.unpack('>'+str(len(val)//4)+'I', val)) if val else []
                    else:
                        item['properties'][key] = '<non-integer-or-oversized>'
            elif token == 4:  # FDT_NOP
                pass
            elif token == 9:  # FDT_END
                if depth != 0 or not root_seen:
                    return None
                saw_end = True
                break
            else:
                return None
        if not saw_end:
            return None
        return {'offset': at, 'size_bytes': total, 'version': version,
                'root_model': root_model, 'root_compatible': root_compatible,
                'hardware_nodes_reference_only': nodes,
                'm6_identification_not_authenticated': True,
                'm6_verified': False}
    except (IndexError, OverflowError, ValueError, struct.error, TypeError):
        return None


def scan_candidates(buf: bytes | mmap.mmap) -> tuple[list[dict], bool]:
    out = []
    start = 0
    attempts = 0
    while start < len(buf) and len(out) < MAX_FDTS_PER_FILE and attempts < MAX_MAGIC_ATTEMPTS:
        at = buf.find(MAGIC, start)
        if at < 0:
            return out, False
        start = at + len(MAGIC)
        attempts += 1
        entry = validate_fdt(buf, at)
        if entry:
            out.append(entry)
    return out, buf.find(MAGIC, start) >= 0


def candidates(buf: bytes | mmap.mmap) -> list[dict]:
    return scan_candidates(buf)[0]


def sha256_bytes(buf: bytes | mmap.mmap) -> str:
    digest = hashlib.sha256()
    for i in range(0, len(buf), 1024 * 1024):
        digest.update(buf[i:i+1024*1024])
    return digest.hexdigest()


def classify(buf: bytes | mmap.mmap) -> dict:
    head = buf[:min(len(buf), 4096)]
    tail = buf[:min(len(buf), 8 * 1024 * 1024)]
    return {
        'android_boot_magic': head.startswith(b'ANDROID!'),
        'squashfs_magic_at_start': head.startswith(b'hsqs'),
        'contains_target_board_marker_first_8mb': b'v851s-lybox_rtl8' in tail,
        'note': 'markers are hints, not proof of provenance or completeness',
    }


def analyse_buffer(name: str, buf: bytes | mmap.mmap) -> dict:
    c, was_limited = scan_candidates(buf)
    return {
        'input_name': name,
        'size_bytes': len(buf),
        'sha256': sha256_bytes(buf),
        'format_hints': classify(buf),
        'valid_literal_fdt_count': len(c),
        'scan_incomplete_due_to_limits': was_limited,
        'valid_literal_fdt_candidates': c,
        'no_dtb_does_not_exclude_other_partitions': not bool(c),
        'file_is_authenticated_m6_running_firmware': False,
        'safe_to_flash': False,
    }


def analyse_path(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        return [{'input_name': path.name, 'skipped': 'not a regular non-symlink file'}]
    if path.stat().st_size > MAX_FILE:
        return [{'input_name': path.name, 'skipped': 'file over size limit (1 GiB)'}]
    if zipfile.is_zipfile(path):
        out = []
        total = 0
        with zipfile.ZipFile(path) as z:
            for item in z.infolist():
                if item.is_dir():
                    continue
                if len(out) >= MAX_FILES:
                    out.append({'input_name': path.name, 'skipped': 'ZIP member count limit reached'})
                    break
                if item.file_size > MAX_ZIP_MEMBER or total + item.file_size > MAX_ZIP_TOTAL:
                    out.append({'input_name': item.filename, 'skipped': 'ZIP decompressed size limit'})
                    continue
                total += item.file_size
                try:
                    with z.open(item) as f:
                        data = f.read(MAX_ZIP_MEMBER + 1)
                    if len(data) != item.file_size:
                        raise ValueError('ZIP member length mismatch')
                    out.append(analyse_buffer(path.name + '::' + Path(item.filename).name, data))
                except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as e:
                    out.append({'input_name': Path(item.filename).name, 'skipped': type(e).__name__})
        return out
    with path.open('rb') as f:
        if not path.stat().st_size:
            return [analyse_buffer(path.name, b'')]
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as view:
            return [analyse_buffer(path.name, view)]


def make_report(paths: list[Path]) -> dict:
    found = []
    for path in paths[:MAX_FILES]:
        if not path.exists() or path.is_symlink():
            raise ValueError("Input path is missing or symlink: " + str(path))
        if path.is_dir():
            children = [p for p in sorted(path.iterdir()) if p.is_file() and not p.is_symlink()]
            if not children:
                raise ValueError("Input directory has no regular files: " + str(path))
            for child in children[:MAX_FILES - len(found)]:
                found.extend(analyse_path(child))
        else:
            found.extend(analyse_path(path))
        if len(found) >= MAX_FILES:
            break
    if not found or all('skipped' in x for x in found):
        raise ValueError('No files were scanned')
    hits = sum(x.get('valid_literal_fdt_count', 0) for x in found)
    return {'schema': 'm6.v851s.offline-fdt-preflight.v20',
            'scope': 'OFFLINE READ-ONLY, UNTRUSTED FILE SCAN; NOT DEVICE VALIDATION',
            'scanned_entries': len(found), 'literal_fdt_candidates_found': hits,
            'status': ('incomplete-some-inputs-skipped-or-limited' if any('skipped' in x or x.get('scan_incomplete_due_to_limits') for x in found)
                       else 'candidate-found-needs-authentication' if hits
                       else 'no-literal-dtb-in-supplied-files'),
            'evidence': found,
            'm6_actual_board_dtb_authenticated': False,
            'm6_runtime_wlan_verified': False,
            'safe_to_load': False, 'safe_to_flash': False,
            'next': 'Obtain a genuine full stock image/boot package or read-only dump, confirm source and version; a partial OTA kernel is not sufficient.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, action='append', required=True, help='Local file or flat directory; may repeat')
    p.add_argument('--out', type=Path, required=True, help='Local JSON report')
    a = p.parse_args()
    try:
        result = make_report(a.input)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'status': result['status'], 'scanned_entries': result['scanned_entries'],
                          'literal_fdt_candidates_found': result['literal_fdt_candidates_found'],
                          'report': str(a.out), 'safe_to_flash': False}, ensure_ascii=False))
        return 5 if result['status'] == 'incomplete-some-inputs-skipped-or-limited' else 0
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print('V20_SCAN_ERROR: ' + str(e), file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
