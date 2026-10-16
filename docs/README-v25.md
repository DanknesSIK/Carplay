# M6 v25 — 三项刷机前置条件的真实固件核查（2026-10-16）

> **本阶段不是可刷机固件。** 用户提供的原厂 OTA 文件没有写入此公共仓库，只提交了白名单元数据到 [stock_evidence_v25.json](stock_evidence_v25.json)。原始固件的读取、哈希和 CPIO 解析已在离线工作区执行；GitHub Actions 的 v25 测试只核对元数据内部一致性，不会再次取得原始用户二进制。

## 1. 原厂 DTB 和分区表

- 重读了原始 `kernel`（2,066,432 bytes，SHA256 见 JSON）：Android Boot Image 头部板型标识 `v851s-lybox_rtl8`、kernel=2,061,216 bytes、ramdisk=12 bytes、page_size=2048、`dt_size=0`。原始文件中没有明文 FDT magic。**不意味着 M6 没有 DTB**，只是 DTB 未在该 OTA boot image 中检出。
- `M6-header.bin` 的 1 MiB 来自 `update.swu` **开头部分**，不是 boot0/u-boot 全盘备份。newc CPIO 头指向 `sw-description`（3,186 bytes）以及尚未收完整的 `customer`（4,366,336 bytes）。
- SWUpdate 配置项目 `ly2807`；实际启用的升级项目仅 `kernel → /dev/by-name/boot` 和 `customer → /dev/by-name/customer`。
- 需要真实 M6 对应 DTB、`sys_partition.fex`/设备真实分区读回证据，确认真实 SDIO、GPIO、供电引脚后才能改板级驱动。**不套用公开参考板 PE6/PA11 引脚。**

## 2. Linux 4.9.191 模块与源码兼容

- 原厂模块 `8733bs.ko` 的历史离线提取报告（v5）显示 `vermagic=4.9.191 preempt mod_unload ARMv7 thumb2 p2v8`，并引用 `sunxi_mmc_rescan_card`、`sunxi_wlan_get_bus_index`、`sunxi_wlan_set_power`。
- 这个模块是此前**同一个 OTA** 的静态证据，本轮没有再次解出 .ko。它的存在也**不能证明设备当前选用了 8733bs 分支**；启动脚本还包含 8821cs/aic8800。
- [DongshanPI/Yuzukilizard-v851s-TinaSDK](https://github.com/DongshanPI/Yuzukilizard-v851s-TinaSDK) 有 V851S 的 Linux 4.9 配置、`board.dts` 和部分驱动补丁，但**不是 M6 的精确内核构建树**。其参考板启用 `CONFIG_XR829_WLAN=m`，而非物本 M6 的已认证 RTL8733BS 硬件。该 GitHub 仓库本身不含独立可直接构建的完整 Linux 4.9 树；公开下载的底层 Tina SDK 也不能替代 M6 厂商修改。
- Linux 7.2.7 的实验 .ko 无法直接用于 M6 原厂 4.9.191。缺少精确的 `.config`、`Module.symvers`、构建标志和匹配 M6 的 DTS 时，**没有可靠的兼容模块可装**。

相关技术依据：[百问网 Wi-Fi 迁移](https://tina.100ask.net/SdkModule/Linux_Wi-Fi_DevelopmentGuide-03/)；[Tina 系统配置](https://tina.100ask.net/BasicComponent/Linux_Configuration_DevelopmentGuide-01/)。

## 3. 无损备份和恢复

- SWUpdate `upgrade_recovery` 阶段会设置 `boot_partition=recovery`，但更新描述中 `recovery` 镜像的 `images` 块被注释掉，**本包没有验证出可用于救砖的 recovery 镜像**。
- 旧设备诊断报告的运行版为 `25060316.2807.2`，OTA 文件属于 `26041414.2807.2`，不能作为原机完整备份。
- Allwinner BootROM FEL 的常见 USB ID 是 `1F3A:EFE8`。此前用户提供的 Windows v15 USB 记录仅识别 `05AC:12A8`（Apple 设备），**没有提供 M6 进入 FEL 的证据**。即使未来识别出 FEL，也不能直接证明设备具备读出 SPI NAND/eMMC 全盘或稳定恢复的能力。
- 可用只读 Windows PnP 清单工具（本地压缩包 `usb_host_readonly_v25.ps1`）筛查 1F3A:EFE8，绝不擅自安装 USB 驱动或修改存储。需取得M6实际存储几何、完整一致的双份备份校验、经过验证的设备恢复操作后才能批准刷机。

参考：[linux-sunxi FEL](https://linux-sunxi.org/FEL)；[全志 Tina 分区指南](https://tina.100ask.net/SdkModule/Linux_Save_DevelopmentGuide-02/)。

## 准入条件

只有以下**全部**取得实机证据，才考虑生成并刷写研究固件：

1. `m6_specific_dtb_or_partition_layout_verified=true`，真实 SDIO/GPIO/供电链得到确认；
2. `matched_kernel_tree_config_and_symbol_version_verified=true`，针对原厂 4.9.191 的 ABI 与运行态验证成功；
3. `backup_of_actual_current_firmware_verified=true` 和 `recovery_procedure_tested=true`，确保恢复可靠；

目前这些标识均为 `false`。**Safe to flash: false. Safe to load: false.**

本次报告解决的是对缺口的严格定位，并非已经消除了这些硬件依赖。不要把 SDK 示例镜像、FEL 的通用地址或示例 `.ko` 刷进 M6。
