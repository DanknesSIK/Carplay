# M6 V851S / RTL8733BS 研究总览（更新至 v26，2026-10-16）

> **尚未取得适用于当前 M6 的原厂 DTB 或可恢复备份。没有刷机或模块安装授权。所有成功的 GitHub Actions 仅证明离线编译和静态测试，不证明硬件兼容。**

| 阶段 | GitHub 验证 | 真实含义 |
|---|---|---|
| v16 | 通过 | 研究板级兼容接口，未确认 M6 GPIO |
| v17 | 通过 | Linux 7.2.7 实验 ABI 联合构建，并非原厂 4.9.191 模块 |
| v18 | 通过 | 参考 stage1 DTB 中 MMC1 禁用；未取得 M6 DTB |
| v19 | 通过 | 公开 V851S/V851SE 均为 SDIO1，供电 GPIO 不同 |
| v20 | 12/12 测试通过 | 离线原始镜像中的 FDT 结构扫描 |
| v21 | 14/14 测试通过 | 离线 TOC1/boot_package 目录检查及 DTB 条目校验 |
| v22 | 14/14 测试通过 | PhoenixSuite IMAGEWTY 完整 IMG 目录索引、FDT/TOC1 递归静态检查 |
| v23 | 真实公开 DTB 校验通过 | 固定 Git blob 验证 V851SE 两份真实设备树、修复超限漏扫误报；**不是 M6 设备树** |
| v24 | FIT 与板级 DTB 分离，完整回归通过 | 新增 FIT 镜像列表和内嵌/外置 DTB 静态分析；接入 v22 目录扫描，**不是 M6 实机验证** |
| v25 | 用户原厂 OTA 的原始文件复核 | 确认 boot header dt_size=0、更新只写 boot/customer，recovery 镜像不在该 SWU 的有效写入列表；记录精确哈希 |
| v26 | 原厂 ADB 菜单确证、读设备工具已开发 | 提供仅已授权 USB ADB 设备的只读 DTB/内核/分区采集；**实机尚未连接，需物理操作** |

## v32 原厂升级失败路径审计（2026-10-17）

- [v32 技术报告](docs/README-v32.md) · [v32 ARM 与 Shell 证据](docs/customer_v32_evidence.json)。
- 用户真实 `app/update` ARM 指令证明存在**条件性** `format_udisk.sh` 调用；`app/check_udisk.sh` 也有挂载失败后重新建文件系统的回退逻辑。前者实际脚本主体不在已获取 `customer` 中，因此**未证实会在现机升级时触发或每次清盘**。
- `swupdate_cmd.sh -i %s -e stable,upgrade_recovery &` 以**后台**方式启动；对 Shell 返回值的检查不等于所有 SWUpdate 阶段成功。原厂 `lyUpdate.sh` 还会替换运行中的后台更新程序和 httpd。
- 已开发并交付独立 Python v32 离线审计器和测试：真实样本 **5/5** 通过；无原厂二进制的干净环境 **4 通过、1 跳过**。
- 没有用户旧版固件、完整运行版备份或验证的不拆机恢复途径：**`SAFE_TO_UPGRADE=false`、`SAFE_TO_FLASH=false`**。

## v31 离线升级安全审计（2026-10-17）

- [v31 完整技术报告](docs/README-v31.md) · [v31 精确证据 JSON](docs/customer_v31_evidence.json)。
- **校验了用户原始 OTA 索引与 customer 文件的真实一致性**：SWU 前缀为 CRC-newc；`sw-description` 和 `customer` 的 CPIO 累加 CRC、尺寸与现有客户镜像全部吻合。**未获得完整 SWU 归档，不能校验整个升级包**。
- 原厂 manifest 在 `upgrade_recovery` 阶段将 `boot_partition=recovery`，但 `recovery` 镜像写入被注释；下一阶段才把 `kernel` 和 `customer` 写入 `boot`/`customer`，第三阶段返回普通引导。**既有 Recovery 是否可启动完全未知**。
- 原厂 `app/update` 的 7 条 ARM32 BL 调用边已核实：先校验项目和 magic，随后处理文件/MD5，再调用 `swupdate_cmd.sh -i %s -e stable,upgrade_recovery &`。**有项目校验不代表完整主板兼容或恢复可靠**。
- 提供仅本地文件操作的 v31 Python 审计器、6 个测试及脱敏报告；不提交原厂固件二进制。
- 仍无在用 `25060316.2807.2` 镜像、可用 Recovery 的实机证据、完整恢复备份或非拆机救砖方案：**`SAFE_TO_UPGRADE=false`、`SAFE_TO_FLASH=false`**。

## v28–v30 本机原厂文件离线逆向（2026-10-17）

- **v28**：从用户原厂 `customer` 提取的 7 个真正 ARM 程序/脚本证明 CarPlay 与 Android Auto 启动路径不同、USB Gadget 为多平台片段，同时发现 `ly_efex` 和 UDISK/CGI 擦写线索。详见 [v28](docs/README-v28.md)。
- **v29**：真实 ARM32 交叉引用及平台函数 `getenv("LY_PLATFORM")` 分支验证：`v851=3`，`aixin513=5`。仅 `aixin513` 分支读取 `ly_efex` sysfs，其它平台（含 `v851`）读取 `/proc/cmdline` 里的 `ly_efex_mode=`；**这是恢复状态检查，不是已验证的 FEL 激活入口**。详见 [v29](docs/README-v29.md)。
- **v30**：对原始 OTA `index.cgi` 进行 ARM 调用边核查：`conn=` 配置处理进入 `private` MTD 的读、比较、解锁、擦除、写回与 `fsync` 链。此前 `{"code":0}` 只代表 CGI 设置处理成功/接受，**不能证明 ADB 已启动；请勿重复请求修改模式**。本地验证 9 条调用关系和 3 个 MTD ioctl 常量。详见 [v30](docs/README-v30.md)。

**重要版本限制**：分析用的是 `26041414.2807.2` OTA，用户机器先前报告的是 `25060316.2807.2`；无法断定 OTA 二进制与在用版本完全相同。用户**不接受拆机或物理短接**；没有原机完整备份或非拆机恢复路径，因此 `SAFE_TO_FLASH=false`，停止盲目内核升级和其他主板固件试刷。

## v27 已完成：真实 OEM customer 二进制逆向（2026-10-17）

- **实际完整提取 67 个文件**，用户提供的 `customer` 4,366,336 B，解包 9,636,620 B 普通文件；没有提取或提交设备密钥及原厂专有程序。
- 用户先前保存的旧版网页含 `onSelConn() / ADB` 选项，但 `26041414.2807.2` OTA 的 `index.html` 已移除该选项（底层 CGI 仍有 `conn=` 参数）。**不能再用原厂网页 200 / code=0 推断 ADB 可用**。
- 原厂 `ly_testcp` 包含操作 USB Gadget 的 `ffs.adb`、`accessory.gs2`、`usb_mode` 命令字符串，但仅是静态证据。
- **隐私发现**：网页“提交日志”从 CGI 下载 `dmesg + logcat` 后通过 OSS SDK 上传日志和设备信息。不要点击该按钮，也不要通过 `id=sts` 获取云端令牌。
- [v27 完整发现与限制](docs/README-v27.md) · [v27 敏感信息已去除的证据表](docs/customer_v27_evidence.json)。不拆机、不使用 ADB 或未知网络接口、不刷机；下一阶段研究本地代码交叉引用。

## 实机 USB 核验后的最新结论（2026-10-16）

- 用户 Windows 主机已确认 `adb devices -l` **无设备**；原厂 `conn=adb` 仅返回 `{"code":0}` 并未建立 ADB。请**停止**重复 ADB 测试，不要强制重绑定 `05AC:12A8` 为 Android 驱动。
- 设备 USB 重新枚举显示 `05AC:12A8`，与其他 CarPlay USB gadget 模拟 iPhone 的公开行为一致，**不能用 VID/PID 验证当前 PCB**。
- CatPlay 支持列表中的 `Wooboobox M6` 属于 **X1600/AX1800M**；本机升级镜像是 **V851S/ly2807**，不能使用它的固件，也不能使用 V821B/ly5166/T2 的固件。
- 经用户原始 SWU CPIO 复核，`recovery` 镜像安装项被注释，实际固件写入只含 `boot` 和 `customer`。**没有完整救砖镜像**。
- 物本官网公开下载中心暂未列出经验证匹配的 `ly2807` 全量固件。官方技术支持：**support@wooboobox.com**（[官网联系方式](https://cn.wooboobox.com/contact-us.html)）。针对本机向厂商确认完整恢复固件、分区/DTB、无损备份及恢复过程，明确旧运行版 `25060316.2807.2` 与研究 OTA `26041414.2807.2` 不同。
- [v26 实机测试核查](docs/README-v26.md) 和 [Issue #1 所需资料](https://github.com/DanknesSIK/Carplay/issues/1) 已同步更新。**仍然不允许刷机或装入实验模块。**

## 当前证据缺口与下一步

缺少原厂证据的追踪与解锁条件见 [Issue #1：M6 boot package / DTB 实机认证](https://github.com/DanknesSIK/Carplay/issues/1)。此问题尚未解决，不能通过更多合成 CI 测试绕过。

- 已有升级包 `26041414.2807.2`，设备先前诊断现行版本 `25060316.2807.2`，**不是同一个版本**。
- 原厂 `kernel` 样本中没找到有效明文 FDT；不代表真实完整闪存没有 DTB。
- 需来自 **实际 M6** 的只读完整启动包/设备树、准确存储分区信息、Wi-Fi 上电 GPIO 和可验证的恢复路径。
- 针对固件型号 `2807`，<https://www.drive2.ru/b/655924107983990956/> 报告过使用 `Z2-V03 2024-11-09` 主板及 RTL8733BS 的类似适配器。这是**第三方实物参考线索，不是你的 M6 主板认证**。
- 不做自动刷写、不加载实验 `.ko`、不根据其它参考板 GPIO 修改真实启动参数。

## 工具

- `python tools/scan_fdt_v20.py --input FILE --out report.json`
- `python tools/audit_toc1_v21.py --input FILE --out report.json`
- `python tools/audit_phoenix_wty_v22.py --input FULL_PHOENIX_IMG --out report.json`
- `python tools/inspect_fit_v24.py --input U_BOOT_FIT_ITB --out report.json`
- `python tools/adb_readonly_m6_v26.py --out-dir M6-v26-local-readonly` （**仅实机已授权 ADB 后使用；不会自动切换设备模式**）

这些工具**仅在本地、使用合法持有的二进制样本**；不连接实机、不上传原厂镜像；如果当前手头只有增量升级包，建议先检查是否能由厂商提供完整版本匹配的启动包，而不是继续刷机实验。

### 分阶段记录

下面保留最初的 v16 研究说明以追溯历史。v23 的公开真实 DTB 校验记录见 [Actions](https://github.com/DanknesSIK/Carplay/actions/runs/38869022595)。详见 `docs/README-v19.md` 至 `docs/README-v26.md`。

---

# V851S / RTL8733BS board ABI — independent research v16

**状态：仅离线源码/编译实验；非 M6 适配成功证明；不支持原厂 4.9.191。**

这个增量包只添加一个可能的 **Linux 7.2.7 板级兼容层**，保留原 `m6-build.yml` / `tools/ci_build_driver_v9.sh` 不变。

## 已取得的证据
- GitHub 第8次 ARM32 研究编译成功：`8733bs.ko`，Linux 7.2.7，ELF32 ARM。
- 原厂升级包板号：`v851s-lybox_rtl8`；原厂运行系统 Linux 4.9.191。
- 两个独立 V851S 参考 DTS 均用 SDIO1（寄存器 `0x04021000`），**但 GPIO 不同**，不是 M6 GPIO 证据。
- 原厂 Wi-Fi 模块依赖 `sunxi_wlan_set_power`、`sunxi_wlan_get_bus_index`、`sunxi_mmc_rescan_card`。
- 公开的 `raauve/x96q-ssv6006-wifi` 提供这些 ABI 的功能参考，属于 H616/X96Q 而不是 M6。

## 本次代码做什么

`drivers/m6_sunxi_platform_v16/sunxi_m6_platform_v16.c` 是**不可部署的候选实现**：
- 使用 Linux 通用 GPIO descriptor、regulator、Device Tree 的 MMC phandle 与 `mmc_detect_change`，不硬编码引脚/总线寄存器；
- 定义并导出原厂所需 3 个 Sunxi 函数；
- 没有获得正式 DT 设备匹配时，所有函数均安全退出或返回 `-ENODEV`；
- 即使有人提供设备树，probe 仍要求 `research,board-verified`；这是实验安全检查，不是硬件认证；
- 其供电时序仅是**待验证的设计草案**，并未证明适合 M6。

`profiles/m6_unverified_wifi_v16.dts.txt` **不是可直接编译或安装的设备树**，刻意缺少所有 GPIO、MMC phandle。不要手动照抄参考板的 GPIO。

## 测试（无需设备）

```bash
python3 -m unittest discover -s tests -p 'test_v16.py' -v
python3 tools/review_board_v16.py --out ci-output/m6-v16-board-static-audit.json
```

## 提交到 GitHub（只添加新文件，不覆盖之前成功的源码）

将本包中以下相对路径整体复制/上传到 `DanknesSIK/Carplay` 仓库根目录：

- `.github/workflows/m6-platform-v16.yml`
- `drivers/m6_sunxi_platform_v16/{Makefile,sunxi_m6_platform_v16.c}`
- `tools/{review_board_v16.py,ci_build_platform_v16.sh}`
- `profiles/{board_reference_evidence_v16.json,m6_unverified_wifi_v16.dts.txt}`
- `tests/test_v16.py`

**GitHub 网页上传隐藏文件夹 `.github` 时请保留目录层级。** 执行 Actions → `M6 V851S research board ABI (v16, no flash)` → `Run workflow`。这条新流水线会重用已有 v9 研究内核构建、单独编译平台候选模块、核对 ELF/符号并仅上传日志，不上传新平台 `.ko`。新模块的真正 Kbuild **需由这条 CI 运行确认**。

不能运行/安装任一实验 `.ko`，不能把相关代码刷到 M6，不能擦除 Boot0。原厂系统、M6 设备树和 GPIO 仍未验证。

## 外部源码（研究参考，不能作为 M6 实测）
- https://github.com/DanknesSIK/Carplay/actions/runs/38728648505
- https://github.com/gxcreator/aa-smartbox-re/blob/00fa1232a2faa04b91efb4dbd4d7e345489b7c1a/info/decompiled-tree-linux.dts
- https://github.com/hbouhadji/prototype-v851s-port/blob/05d8262010922cefe05592238e8f60f98dab4613/analyse-v851s/stock-full.dts
- https://github.com/raauve/x96q-ssv6006-wifi/blob/main/sunxi-rf/sunxi-wlan.c
