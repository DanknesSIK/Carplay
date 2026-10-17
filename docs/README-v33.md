# M6 v33 — 原厂 Android boot image 与 Recovery 缺口（2026-10-17）

> 全程只处理用户现有的私有原厂文件，没有拆机、连接设备、升级、刷机或执行原厂 ARM 程序。用户已经明确不接受拆机。实际设备报告运行 `25060316.2807.2`，原厂样本是另一版本 `26041414.2807.2`。

## 在原始 kernel 文件上的新验证
- `kernel` 是 **2,066,432 字节** Android legacy `ANDROID!` boot image；SHA256 `5a17aa388f98011ba7f24508b9d6a4b84650c45ceb68f173307031dd15b992c9`。Header: board `v851s-lybox_rtl8`、page 2,048、kernel size 2,061,216、second size 0、**dt_size=0**。
- Ramdisk size **12 字节**，内容只是 `ramdisk.img\n` 占位文本，**不是有效的恢复系统 / initramfs**。
- kernel 区内真正有效的 XZ 流从 boot 文件偏移 **12,192** 开始，消耗 **2,051,004** 压缩字节，解压后 **4,044,400** 字节。解压内容 SHA256 `d2fd80a7d62b8f4510046125e7d95b352e43297efe0570c3ff9041eb4c084623`。
- 解压内核直接包含编译信息：`Linux version 4.9.191 (os@machine) (gcc version 6.4.1 (OpenWrt/Linaro GCC 6.4-2017.11 2017-11) ) #422 PREEMPT Fri Mar 27 03:25:37 UTC 2026`。**这只是升级 OTA 的编译标识，不是旧运行版的实测内核**。
- 解压内核里扫描到 2 处 `D0 0D FE ED` FDT magic，但其后均是无效头数据：总大小、结构体偏移等不符合 FDT 格式；全 boot 文件及其解压内核中**没有通过校验的 DTB**。这不能排除 U-Boot、闪存其他分区中另有 DTB。扫描未发现 `IKCFG_ST`/`IKCFG_ED`，不能从当前内核直接提取编译 `.config`。
- 原厂无线驱动 `8733bs.ko` SHA256 `aa4a1205f77dd06b2ab82ff9e1af22125b9f831c1bc8fcfa92b0a5c74e6477b9`，modinfo 中 `vermagic=4.9.191 preempt mod_unload ARMv7 thumb2 p2v8`。与 OTA 内核版本一致，但未认证完整 Module.symvers/ABI/实机 GPIO 和 SDIO 电源。

## 与原始 SWU 的交叉校验
本地脚本重新读取 `M6-header.bin` 中的 CPIO `sw-description`，实际 `project=ly2807`。升级阶段 `upgrade_recovery` 设置 `boot_partition=recovery`，最终阶段恢复 `boot`。**SWUpdate 活动镜像项只包含 `kernel -> /dev/by-name/boot`、`customer -> /dev/by-name/customer`，没有启用写入 recovery 或 rootfs 的镜像项。** 样本只有 SWU 头部 1 MiB，不是完整归档；Recovery 内容和现机是否能启动 Recovery 均未知。

## 实际决策
用户手里的原厂 `kernel` **不能当作完整救砖镜像**，也无法单凭它恢复整机；当前缺失：旧版原机 boot、专属 DTB、rootfs、Recovery、完整分区备份与已验证非拆机恢复入口。**SAFE_TO_UPGRADE=false；SAFE_TO_FLASH=false。** 不是已证明该 OTA 必然刷坏，而是无法为用户的不拆机约束建立可靠回退。

已在真实本地原厂样本 **7/7** 测试通过；无私有数据的独立测试 **6 通过 + 1 跳过**。当前会话交付 `M6-v33-boot-recovery-offline-audit.zip`，包含脚本 `audit_bootchain_v33.py`、其 v31 SWU parser 依赖、单元测试、脱敏 JSON 与中文报告，**无原厂内核与厂商专有二进制**。

下一阶段只可继续基于已取得镜像离线逆向和调查可靠公开资料；不再重复实机 ADB、CGI 切换、未知恢复按键或其他高风险操作。
