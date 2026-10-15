#!/usr/bin/env bash
# Build ONLY a research module using a prepared ARM kernel tree; never writes device/firmware.
set -euo pipefail
[[ $# -eq 3 ]] || { echo 'Usage: build_rtl8733bs_v8.sh KERNEL_SOURCE KERNEL_BUILD DRIVER_PREPARED' >&2; exit 2; }
KERNEL_SOURCE="$(realpath "$1")"
KERNEL_BUILD="$(realpath "$2")"
DRIVER="$(realpath "$3")"
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 "$HERE/stage2_preflight_v8.py" --kernel-source "$KERNEL_SOURCE" --kernel-config "$KERNEL_BUILD/.config" --driver "$DRIVER"
command -v arm-linux-gnueabihf-gcc >/dev/null || { echo 'Missing ARM32 cross compiler arm-linux-gnueabihf-gcc' >&2; exit 3; }
[[ -f "$KERNEL_BUILD/Module.symvers" ]] || { echo 'BLOCKED: kernel Module.symvers missing. A fully built matching kernel is required.' >&2; exit 3; }
[[ -f "$KERNEL_BUILD/include/generated/autoconf.h" ]] || { echo 'BLOCKED: kernel not prepared' >&2; exit 3; }
echo 'Building experimental driver. Success WILL NOT mean M6 compatible or safe to load.'
# ARCH and CROSS_COMPILE are passed as command-line overrides to prevent upstream ARM64 platform overrides.
make -C "$KERNEL_SOURCE" O="$KERNEL_BUILD" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- \
  M="$DRIVER"CONFIG_RTL8733BS=m \ 
  "USER_EXTRA_CFLAGS=-DCONFIG_LITTLE_ENDIAN -DCONFIG_IOCTL_CFG80211 -DRTW_USE_CFG80211_STA_EVENT -DCONFIG_RTW_IOCTL_SET_COUNTRY -DCONFIG_CONCURRENT_MODE" \
  -j"${JOBS:-4}" modules
[[ -f "$DRIVER/8733bs.ko" ]] || { echo 'No 8733bs.ko produced' >&2; exit 4; }
file "$DRIVER/8733bs.ko"
readelf -h "$DRIVER/8733bs.ko" | grep -E 'Class:|Machine:'
echo 'EXPERIMENTAL .ko built; DO NOT LOAD OR FLASH ON M6.'
