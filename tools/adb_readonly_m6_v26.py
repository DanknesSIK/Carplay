#!/usr/bin/env python3
"""M6 USB ADB evidence collector — host-initiated, read-only commands only.

Requires one physically connected, already-authorized ADB device. This tool
does NOT enable ADB mode, change device settings, root, remount, push, reboot,
flash, or read whole flash partitions. All outputs remain on the local host.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time

TEXT_READS = {
    "kernel_release": ("shell", "uname", "-r"),
    "kernel_version": ("shell", "cat", "/proc/version"),
    "loaded_modules": ("shell", "cat", "/proc/modules"),
    "mtd_partitions": ("shell", "cat", "/proc/mtd"),
    "block_partitions": ("shell", "cat", "/proc/partitions"),
    "by_name_links": ("shell", "ls", "-l", "/dev/by-name"),
    "sdio_devices": ("shell", "ls", "/sys/bus/sdio/devices"),
}
BINARY_READS = {
    "device_tree_fdt": ("exec-out", "cat", "/sys/firmware/fdt"),
    "device_tree_model": ("exec-out", "cat", "/proc/device-tree/model"),
    "device_tree_compatible": ("exec-out", "cat", "/proc/device-tree/compatible"),
    "kernel_config_gz": ("exec-out", "cat", "/proc/config.gz"),
}
MAX_TEXT_OUTPUT = 256 * 1024
MAX_BINARY_OUTPUT = 4 * 1024 * 1024


def run_adb(*args: str, timeout: int = 15) -> tuple[int, bytes]:
    # Fixed tool, not shell=True. No device writes or arbitrary user commands.
    try:
        proc = subprocess.run(("adb",) + args, capture_output=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, b""


def probe(runner=run_adb) -> dict:
    status, output = runner("devices", timeout=15)
    if status != 0:
        raise RuntimeError("ADB unavailable; install platform-tools on the host first")
    authorized = []
    for line in output.decode("utf-8", "replace").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            authorized.append(fields[0])
    if len(authorized) != 1:
        raise RuntimeError("Expected exactly one authorized ADB device, found "+str(len(authorized)))
    # Never emit serial numbers into reports or logs.
    serial = authorized[0]
    return {"serial_for_internal_use_only": serial}


def audit(out_dir: Path, runner=run_adb) -> dict:
    if out_dir.is_symlink():
        raise ValueError("Output directory cannot be a symlink")
    local = probe(runner)
    serial = local["serial_for_internal_use_only"]
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "m6.adb.local-readonly-evidence.v26",
        "device_interface": "one authorized USB ADB interface (identity not authenticated)",
        "device_serial_stored": False,
        "observed": {},
        "missing_or_inaccessible": [],
        "real_board_identity_authenticated": False,
        "complete_flash_backup_verified": False,
        "firmware_recovery_tested": False,
        "safe_to_load": False,
        "safe_to_flash": False,
    }
    for key, command in TEXT_READS.items():
        status, raw = runner("-s", serial, *command, timeout=15)
        if status != 0 or len(raw) > MAX_TEXT_OUTPUT:
            report["missing_or_inaccessible"].append(key)
            continue
        decoded = raw.decode("utf-8", "replace").strip()[:MAX_TEXT_OUTPUT]
        # Prevent accidental export of shell diagnostics that are not relevant.
        if key == "kernel_version":
            decoded = decoded[:1024]
        if key == "loaded_modules":
            decoded = "\n".join(x.split()[0] for x in decoded.splitlines() if x.split())[:8192]
        report["observed"][key] = decoded
    # Device-tree metadata may not be available via /sys/firmware/fdt on Tina 4.9.
    for key in ("device_tree_model","device_tree_compatible","device_tree_fdt","kernel_config_gz"):
        status, raw = runner("-s", serial, *BINARY_READS[key], timeout=20)
        if status != 0 or not raw or len(raw) > MAX_BINARY_OUTPUT:
            report["missing_or_inaccessible"].append(key)
            continue
        if key in ("device_tree_model","device_tree_compatible"):
            labels = [x.decode("utf-8","replace")[:160] for x in raw.split(b"\0") if x][:10]
            report["observed"][key] = labels
        elif key == "device_tree_fdt":
            if len(raw)<40 or raw[:4] != b"\xd0\x0d\xfe\xed":
                report["missing_or_inaccessible"].append("device_tree_fdt_invalid_header")
                continue
            declared = struct.unpack_from(">I",raw,4)[0]
            if not (40 <= declared <= len(raw) <= MAX_BINARY_OUTPUT):
                report["missing_or_inaccessible"].append("device_tree_fdt_invalid_length")
                continue
            payload = raw[:declared]
            fname = out_dir / "m6-readonly-device-tree.dtb"
            fname.write_bytes(payload)
            report["observed"]["device_tree_fdt"] = {
                "local_path": fname.name, "bytes":len(payload), "sha256":hashlib.sha256(payload).hexdigest(),
                "board_provenance_not_yet_verified": True,
            }
        elif key == "kernel_config_gz":
            if not raw.startswith(b"\x1f\x8b"):
                report["missing_or_inaccessible"].append("kernel_config_gz_not_gzip")
                continue
            fname = out_dir / "m6-readonly-config.gz"
            fname.write_bytes(raw)
            report["observed"]["kernel_config_gz"] = {"local_path":fname.name,
                "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
    report["evidence_collected"] = bool(report["observed"])
    (out_dir / "m6-v26-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=Path("M6-v26-local-readonly"))
    args=p.parse_args()
    try:
        report=audit(args.out_dir)
        print(json.dumps({"result":"LOCAL_READONLY_PROBE_FINISHED",
                          "evidence_categories":sorted(report["observed"]),
                          "safe_to_flash":False,
                          "output_dir":str(args.out_dir)}, ensure_ascii=False))
    except (RuntimeError,ValueError) as exc:
        p.exit(3, "V26_READONLY_BLOCKED: "+str(exc)+"\n")


if __name__=="__main__":
    main()
