#!/usr/bin/env bash
# Independently cross-compile ONLY the research board ABI against v9's Linux 7.2.7 kernel.
# No firmware image, no device access, no module loading or flashing.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KERNEL="$ROOT/.ci-work/linux-7.2.7"
KOUT="$ROOT/.ci-work/kernel-out"
MODULE="$ROOT/drivers/m6_sunxi_platform_v16"
OUT="$ROOT/ci-output"
mkdir -p "$OUT"
python3 "$ROOT/tools/review_board_v16.py" --out "$OUT/m6-v16-board-static-audit.json"
for x in "$KERNEL/Makefile" "$KOUT/.config" "$KOUT/Module.symvers" "$MODULE/Makefile"; do
    [[ -f "$x" ]] || { echo "MISSING_BUILD_INPUT: $x"; exit 8; }
done
command -v arm-linux-gnueabihf-gcc >/dev/null
make -C "$KERNEL" O="$KOUT" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- \
    M="$MODULE" -j"${JOBS:-4}" modules
KO="$MODULE/sunxi_m6_platform_v16.ko"
[[ -s "$KO" ]] || { echo "M6_V16_KO_NOT_BUILT"; exit 9; }
file "$KO" | tee "$OUT/m6-v16-elf-file.txt"
readelf -h "$KO" > "$OUT/m6-v16-elf-header.txt"
grep -q 'Machine:.*ARM' "$OUT/m6-v16-elf-header.txt"
nm -g "$KO" > "$OUT/m6-v16-module-symbols.txt"
for symbol in sunxi_wlan_set_power sunxi_wlan_get_bus_index sunxi_mmc_rescan_card; do
    grep -Eq "[[:space:]]${symbol}$" "$OUT/m6-v16-module-symbols.txt" || {
        echo "ABI_SYMBOL_MISSING: $symbol"; exit 10;
    }
done
# Do not copy the .ko into any distribution artifact: the target is unverified.
echo 'M6_V16_BOARD_ABI_ELF_BUILT_RESEARCH_ONLY_NOT_LOADABLE_ON_STOCK'
