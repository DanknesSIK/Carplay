# M6 v26 — 原厂后台 ADB 模式 + 只读实机证据采集

## 2026-10-16 实机测试结论（重要更新）

- 用户在原厂 CGI 执行 `id=set&conn=adb`，服务器返回 `{"code":0}`，但这**仅表示接受设置请求**，不能证明启动了 ADB 服务。
- Windows 正确安装 Android Platform Tools 后，`adb devices -l` 多次列出空设备列表。直接连接电脑与通过 USB Hub 均未识别出可用 ADB。
- USB 断开/连接前后 Windows 的新增设备是 `USB\\VID_05AC&PID_12A8` 及 `MI_00` MTP；该次测试用户确认没有通过 USB 接入 iPhone。该标识**与其他 CarPlay 转换器模拟 iPhone USB gadget 的已公开行为一致**，但不能单凭 VID/PID 认证 M6 PCB 或 USB 固件行为。参考：https://github.com/harrylepotter/carplay-receiver/issues/9 及 https://github.com/GainSec/3rdParty-Carplay-AndroidAuto-Dongle-Security-Research 。
- **立即停止继续试 ADB、装未知 USB 驱动、将 Apple 接口强制替换为 ADB 驱动。** 如已切换 `adb`，在确认原厂后台可访问的情况下恢复默认 `conn=aoa`，验证 CarPlay 正常。
- 本文件后面原有 ADB 操作步骤保留作历史说明和仅在确实发现已授权 ADB 时的工具使用文档，**不再作为本机当前推荐操作**。
- 已按板级而非商品营销型号核对 [CatPlay](https://github.com/catplay-labs/catplay/blob/986776c022cad40bf2e7f2df09c02cf9807936e2/README.md)：已支持的 `Wooboobox M6` 条目是 `Ingenic X1600 / AX1800M`，不是原厂升级包为 `v851s-lybox_rtl8`、`ly2807` 的本机；V851S 的 `Wooboobox T2` 条目是 `AIC8800D80` 移植中，也不是该机的匹配候选。
- **唯一剩余高价值方案**：从物本官方技术支持索取 `ly2807 / v851s-lybox_rtl8` 完整启动链/分区资料/恢复步骤；官网邮箱 support@wooboobox.com，来源 https://cn.wooboobox.com/contact-us.html 。当前设备报告运行 `25060316.2807.2`，另有原厂 OTA `26041414.2807.2` 仅供离线研究；不要混淆两版，更不要安装陌生固件。

## 为什么这一阶段比继续编译更重要

复核用户自己保存的 `M6-backend.html`（来源于 M6 原厂后台）确认存在菜单 **连接方式** 与两个选项：

- `{label: "默认", value: "aoa"}`
- `{label: "ADB", value: "adb"}`

点击选项会发送 `/cgi-bin/index.cgi?id=set&conn=` + 所选值。这是**会更改设备设置的请求**，不是只读查询。

⚠ 只发现网页功能，并不证明此 M6 已运行 ADB 服务、有 root 权限，或可以直接导出分区。切到 ADB 模式可能临时失去 CarPlay USB 连接。需要用户在本机实操时明确同意；自动化脚本**绝不切换连接模式**。如果管理页不可恢复访问，停止试验并联系官方，不再执行其它复位或未知指令。

## 取得用户授权和物理连接后怎么做

1. 确保 M6 当前能正常工作、能连接其自身 Wi-Fi 并打开 `http://192.168.1.101` 的原厂后台；记录现有连接模式，默认通常为 `aoa`。
2. 进入设置页 → **连接方式** → **ADB**。这是唯一需要用户明确执行的模式切换；确认切换不会干扰重要使用场景。切换后，将 M6 的数据接口接入 Windows 电脑，使用可传数据的线缆。
3. 在 Windows 上安装/准备官方 Android **platform-tools**（`adb`），确保 Python 3 可用。在 **不安装不明驱动、不修改系统文件**的情况下先运行 `adb devices`；必须出现恰好一个已授权设备。如果只出现 `unauthorized`、`offline` 或无设备，立即停止，不做 root、端口扫描或刷机。
4. 从此仓库根目录运行：

   ```powershell
   python tools/adb_readonly_m6_v26.py --out-dir "M6-v26-local-readonly"
   ```

5. 输出全都保存在电脑本地：`m6-v26-report.json`，若可读取还会得到 `m6-readonly-device-tree.dtb`、`m6-readonly-config.gz`。**不上传**到 GitHub 公共仓库；供后续只读核对。
6. 如原厂后台仍可访问，手动将连接方式切回 **默认/aoa**。重新连接到车机检查 CarPlay 是否正常；若后台断开或设备异常，不尝试其他隐藏设置或 POST 升级。

## 脚本具体读取什么

命令**仅允许** `adb devices`、`adb shell uname -r`、`adb shell cat /proc/version`、`cat /proc/modules`、`cat /proc/mtd`、`cat /proc/partitions`、`ls -l /dev/by-name`、`ls /sys/bus/sdio/devices`，以及只读 `adb exec-out cat /sys/firmware/fdt`、`/proc/device-tree/model`、`/proc/device-tree/compatible`、`/proc/config.gz`。

- 不写入设备或任何分区，不调用 `adb root`、`remount`、`push`、`reboot`、`install`、`flash`。
- 不尝试读取 `/dev/mtdX` 或 `/dev/mmcblkX` 原始分区；获取分区布局并不能证明已经备份完成。
- 仅当直接 FDT 头通过基本长度校验时才保存 DTB。文件依然未经 M6 板级真实性认证，进一步静态解析可用 v20–v24 工具。
- 只允许一个已授权 USB ADB 设备；序列号只用于本地单次命令，绝不保存到 JSON。
- 若无权限访问某项，报告标注 `missing_or_inaccessible`，不会伪造数据或把空输出误作成功。

## 如何使三个刷机前置项有机会真正关闭

**A. 设备树/分区：** 得到可信 `/sys/firmware/fdt` 或其他运行设备树标识、`/proc/mtd`、`/dev/by-name`，进一步核查 SDIO 和供电配置。注意 Android Boot Image 中 `dt_size=0`，真正 DTB 很可能位于其他启动区域。

**B. 内核兼容：** `uname -r`、`/proc/version`、`/proc/config.gz` + 已加载的 `/proc/modules` 可以缩小内核匹配差距，但仍需要和厂商源码、符号 ABI、编译器和模块接口核对。原厂 OTA 的 4.9.191 驱动不能由 Linux 7.2.7 编译产物替代。

**C. 备份/恢复：** ADB 能读取分区列表不等于能做完整备份，更不能证明刷坏 bootloader 后可恢复。下一阶段需要了解实际存储介质、读回权限、容量、校验、M6 专属恢复方式。Allwinner FEL 是可能的候选，但此前 USB 记录只看到了 Apple `05AC:12A8`，没有 `1F3A:EFE8` 证据。其他 V851S3 板子的 FEL 触点和闪存偏移**不能用于这台 M6**。

工具保持 `safe_to_flash=false`，除非用户提供更多**实机**证据并完成完整恢复验证。

技术参考：
- https://linux-sunxi.org/FEL
- https://tina.100ask.net/SdkModule/Linux_Save_DevelopmentGuide-02/
