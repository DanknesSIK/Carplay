#!/usr/bin/env bash
# Off-device Kbuild/modpost linkage test, using v9's pinned kernel and v16 platform.
# No insmod/modprobe, device commands, boot image creation or flash writes.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/.ci-work"
KERNEL="$WORK/linux-7.2.7"
KOUT="$WORK/kernel-out"
SOURCE="$WORK/rtl8733bs"
PLATFORM="$ROOT/drivers/m6_sunxi_platform_v16"
WIFI="$WORK/rtl8733bs-linked-v17"
PATCH="$WORK/catplay-firmware/meta-carplay/recipes-radio/drivers/rtl8733bs/0001-linux-7.0-compatibility.patch"
OUT="$ROOT/ci-output"
mkdir -p "$OUT"
exec > >(tee "$OUT/m6-v17-joint-build.log") 2>&1
for f in "$KERNEL/Makefile" "$KOUT/Module.symvers" "$SOURCE/Makefile" "$PLATFORM/Module.symvers" "$PLATFORM/sunxi_m6_platform_v16.ko" "$PATCH"; do
  [[ -s "$f" ]] || { echo "V17_MISSING_PREREQUISITE: $f"; exit 20; }
done
# v9/v16 output is preserved; a separate clean, verified source copy is created.
[[ ! -e "$WIFI" ]] || { echo "V17_REFUSE_EXISTING_OUTPUT_DIR: $WIFI"; exit 21; }
python3 "$ROOT/tools/prepare_vendor_driver_v8.py" --source "$SOURCE" --dest "$WIFI" --patch "$PATCH"
python3 "$ROOT/tools/prepare_joint_wifi_v17.py" --prepared-tree "$WIFI" --pins "$ROOT/profiles/v8_source_pins.json"
# Modpost resolves external imports using platform Module.symvers, and records
# the platform module in `depends`. ELF undefined symbols remain normal.
make -C "$KERNEL" O="$KOUT" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- \
  M="$WIFI" CONFIG_RTL8733BS=m \
  KBUILD_EXTRA_SYMBOLS="$PLATFORM/Module.symvers" \
  "USER_EXTRA_CFLAGS=-DCONFIG_LITTLE_ENDIAN -DCONFIG_IOCTL_CFG80211 -DRTW_USE_CFG80211_STA_EVENT -DCONFIG_RTW_IOCTL_SET_COUNTRY -DCONFIG_CONCURRENT_MODE" \
  -j"${JOBS:-4}" modules
python3 "$ROOT/tools/verify_joint_v17.py" \
  --platform-dir "$PLATFORM" --wifi-dir "$WIFI" \
  --out "$OUT/m6-v17-joint-modpost-audit.json"
echo 'V17_OFFLINE_JOINT_MODULES_VERIFIED__M6_HARDWARE_NOT_VERIFIED'
