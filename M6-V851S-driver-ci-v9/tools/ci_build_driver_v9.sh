#!/usr/bin/env bash
# EXPERIMENTAL ARM32 RTL8733BS source compile on GitHub Actions. No hardware/device flashing operations.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK_DIR:-$ROOT/.ci-work}"
LOGS="$ROOT/ci-output"
mkdir -p "$WORK" "$LOGS"
exec > >(tee -a "$LOGS/build.log") 2>&1
trap 'rc=$?; echo "RESULT: exit=$rc; for debugging inspect ci-output/build.log"; exit "$rc"' EXIT
export ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-
export JOBS="${JOBS:-4}"

clone_pin() {
  local url="$1" pin="$2" dest="$3"
  if [[ ! -d "$dest/.git" ]]; then git clone --filter=blob:none --quiet "$url" "$dest"; fi
  git -C "$dest" fetch --quiet origin "$pin"
  git -C "$dest" checkout --quiet --detach "$pin"
  [[ "$(git -C "$dest" rev-parse HEAD)" == "$pin" ]] || { echo "SOURCE_SHA_MISMATCH $dest"; exit 30; }
  echo "SOURCE_PIN_OK $(basename "$dest") $pin"
}

for c in git curl sha256sum patch make arm-linux-gnueabihf-gcc python3 xz tar; do
  command -v "$c" >/dev/null || { echo "MISSING_TOOL: $c"; exit 10; }
done

clone_pin https://github.com/hbouhadji/prototype-v851s-port.git \
  05d8262010922cefe05592238e8f60f98dab4613 "$WORK/prototype"
clone_pin https://github.com/catplay-labs/catplay-firmware.git \
  a8d0ce89eda388a4db7c8d86ca7b62eac9579025 "$WORK/catplay-firmware"
clone_pin https://github.com/smp79/rtl8733BS_WiFi_linux_v5.15.17-113.git \
  6b522b308fb7482cb43be290d639cfdf2bfd1838 "$WORK/rtl8733bs"

KERNEL_TARBALL="$WORK/linux-7.2.7.tar.xz"
if [[ ! -f "$KERNEL_TARBALL" ]]; then
  curl -fL --retry 3 --connect-timeout 20 \
    https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.2.7.tar.xz -o "$KERNEL_TARBALL"
fi
printf '%s  %s\n' '4ac34c47db2540ffb2713943f8d891ff1702e0ba6934525a493b7d1cad43145a' "$KERNEL_TARBALL" | sha256sum --check --status || {
  echo 'KERNEL_TARBALL_HASH_MISMATCH'; exit 31;
}
echo 'KERNEL_TARBALL_SHA256_OK'
KERNEL="$WORK/linux-7.2.7"
if [[ ! -d "$KERNEL" ]]; then tar -xf "$KERNEL_TARBALL" -C "$WORK"; fi

if [[ ! -f "$WORK/.v851s_patches_applied" ]]; then
  patch -d "$KERNEL" -p1 < "$WORK/prototype/stage1/configs/linux-7.2.7-v853-patchew-v2.patch"
  patch -d "$KERNEL" -p1 < "$WORK/prototype/stage1/configs/0001-v853-machine.patch"
  touch "$WORK/.v851s_patches_applied"
fi

# Stage1 prototype deliberately disabled MMC and module loading. Create separate research-only configuration.
MINICONF="$WORK/wifi-experimental-miniconfig"
python3 - "$WORK/prototype/stage1/configs/kernel.config" "$MINICONF" <<'PY'
import sys, pathlib
src=pathlib.Path(sys.argv[1]).read_text().splitlines()
overrides = {
 'MODULES':'y', 'KMOD':'y', 'MMC':'y', 'MMC_BLOCK':'y', 'MMC_SUNXI':'y',
 'WIRELESS':'y', 'WLAN':'y', 'CFG80211':'y', 'FW_LOADER':'y',
 'REGULATOR':'y', 'REGULATOR_FIXED_VOLTAGE':'y', 'RFKILL':'y',
 'NET':'y', 'NETDEVICES':'y', 'OF':'y', 'CRYPTO':'y', 'CRYPTO_AES':'y',
 'CRYPTO_CCM':'y', 'CRYPTO_GCM':'y', 'CRYPTO_CMAC':'y'
}
import re
kept=[]
for line in src:
 m=re.match(r'(?:# )?CONFIG_([A-Z0-9_]+)(?:=| is not set)',line)
 if not m or m.group(1) not in overrides:kept.append(line)
kept.extend(f'CONFIG_{k}={v}' for k,v in overrides.items())
pathlib.Path(sys.argv[2]).write_text('\n'.join(kept)+'\n')
PY
KOUT="$WORK/kernel-out"
mkdir -p "$KOUT"
KCONFIG_ALLCONFIG="$MINICONF" make -C "$KERNEL" O="$KOUT" allnoconfig
# Fail loudly when config dependencies were not resolved. No false positive .ko output.
python3 - "$KOUT/.config" <<'PY'
import pathlib,re,sys
x=pathlib.Path(sys.argv[1]).read_text()
need=['ARM','MODULES','MMC','MMC_SUNXI','NET','NETDEVICES','WLAN','CFG80211','OF','FW_LOADER']
bad=[v for v in need if not re.search(r'^CONFIG_'+v+r'=y$',x,re.M)]
if bad:
 print('KCONFIG_DEPENDENCY_MISSING:',', '.join(bad));sys.exit(23)
print('KCONFIG_GATE_OK')
PY
# A full, matching kernel build is needed for Module.symvers; modules_prepare alone is insufficient.
make -C "$KERNEL" O="$KOUT" -j"$JOBS" zImage modules
[[ -f "$KOUT/Module.symvers" ]] || { echo 'NO_MODULE_SYMVERS'; exit 24; }

VENDOR="$WORK/rtl8733bs-arm32-experiment"
if [[ ! -d "$VENDOR" ]]; then
  python3 "$ROOT/tools/prepare_vendor_driver_v8.py" \
    --source "$WORK/rtl8733bs" --dest "$VENDOR" \
    --patch "$WORK/catplay-firmware/meta-carplay/recipes-radio/drivers/rtl8733bs/0001-linux-7.0-compatibility.patch"
fi
bash "$ROOT/tools/build_rtl8733bs_v8.sh" "$KERNEL" "$KOUT" "$VENDOR"
[[ -f "$VENDOR/8733bs.ko" ]] || { echo 'DRIVER_OUTPUT_MISSING'; exit 25; }
cp "$VENDOR/8733bs.ko" "$LOGS/8733bs-ARM32-EXPERIMENTAL-DO-NOT-FLASH.ko"
file "$LOGS/8733bs-ARM32-EXPERIMENTAL-DO-NOT-FLASH.ko" | tee "$LOGS/driver-file.txt"
readelf -h "$LOGS/8733bs-ARM32-EXPERIMENTAL-DO-NOT-FLASH.ko" > "$LOGS/driver-elf-header.txt"
echo 'ARM32_EXPERIMENTAL_DRIVER_BUILD_COMPLETE_NOT_TESTED_ON_M6'
