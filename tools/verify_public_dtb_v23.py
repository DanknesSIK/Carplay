#!/usr/bin/env python3
"""Audit two PINNED, publicly published V851SE DTBs with real FDT parser.

Never confuses this different reference board with M6 v851s-lybox_rtl8.
Git object SHA-1 checks tie results to the expected immutable source blobs.
Read-only local files. No raw DTB uploaded as an artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from scan_fdt_v20 import validate_fdt

PUBLIC_SOURCE = {
    "full": {
        "git_blob_sha1": "eb093bd73c02202ea5b11cbe1e5f1f7f90cd80e3",
        "path": "analyse-v851s/stock-full.dtb",
    },
    "small": {
        "git_blob_sha1": "1d6fb9a403f746df362977e6836201545dd705af",
        "path": "analyse-v851s/stock-small.dtb",
    },
}
COMMIT = "05d8262010922cefe05592238e8f60f98dab4613"
REPO = "hbouhadji/prototype-v851s-port"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def inspect_public_reference(kind: str, content: bytes) -> dict:
    if kind not in PUBLIC_SOURCE:
        raise ValueError("not an approved public reference variant")
    expect = PUBLIC_SOURCE[kind]
    actual_sha1 = git_blob_sha1(content)
    if actual_sha1 != expect["git_blob_sha1"]:
        raise ValueError(f"{kind}: Git blob hash mismatch")
    if len(content) < 72 or content[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError(f"{kind}: not an FDT header")
    doc = validate_fdt(content)
    if doc is None:
        raise ValueError(f"{kind}: v20 parser rejected a real published reference DTB")
    if doc["size_bytes"] != len(content):
        # The full file can have zero padding in some formats, but these exact
        # public DTB blobs are expected to contain one complete DTB each.
        raise ValueError(f"{kind}: unanticipated data after DTB")
    if "v851s-lybox_rtl8" in content.decode("latin1").lower():
        raise ValueError(f"{kind}: M6 target marker unexpected in public reference")
    if not doc["root_compatible"]:
        raise ValueError(f"{kind}: missing root compatible, cannot classify board")
    return {
        "source": f"https://github.com/{REPO}/blob/{COMMIT}/{expect['path']}",
        "source_git_commit": COMMIT,
        "git_blob_sha1_verified": True,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "root_model": doc["root_model"],
        "root_compatible": doc["root_compatible"],
        "captured_hardware_node_count": len(doc["hardware_nodes_reference_only"]),
        "hardware_nodes_reference_only": doc["hardware_nodes_reference_only"],
        "NOT_M6": True,
        "real_M6_hardware_authenticated": False,
        "safe_to_load": False,
        "safe_to_flash": False,
    }


def compare_documents(full: dict, small: dict) -> dict:
    return {
        "schema": "m6.v851s.public-real-dtb-cross-check.v23",
        "status": "PUBLIC_REFERENCE_ONLY_NOT_TARGET_M6",
        "public_reference_full": full,
        "public_reference_small": small,
        "same_root_compatible": full["root_compatible"] == small["root_compatible"],
        "M6_running_version_proven": False,
        "M6_GPIO_pinout_verified": False,
        "M6_DTB_obtained": False,
        "driver_can_be_loaded": False,
        "safe_to_flash": False,
        "next_required": "Authenticated current-board M6 DTB or complete original boot package, not a public V851SE reference.",
    }


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--full", required=True, type=Path)
    a.add_argument("--small", required=True, type=Path)
    a.add_argument("--out", required=True, type=Path)
    args = a.parse_args()
    try:
        if any(p.is_symlink() or not p.is_file() for p in (args.full, args.small)):
            raise ValueError("inputs must be local non-symlink regular files")
        if any(p.stat().st_size > 2*1024*1024 for p in (args.full, args.small)):
            raise ValueError("public DTB larger than allowed 2 MiB bound")
        full = inspect_public_reference("full", args.full.read_bytes())
        small = inspect_public_reference("small", args.small.read_bytes())
        report = compare_documents(full, small)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "full_root_model": full["root_model"],
            "small_root_model": small["root_model"],
            "same_root_compatible": report["same_root_compatible"],
            "safe_to_flash": False,
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print("V23_PUBLIC_DTB_BLOCKED:", exc, file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
