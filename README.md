# M6 V851S / RTL8733BS 研究总览（更新至 v21，2026-10-16）

> **尚未取得适用于当前 M6 的原厂 DTB 或可恢复备份。没有刷机或模块安装授权。所有成功的 GitHub Actions 仅证明离线编译和静态测试，不证明硬件兼容。**

| 阶段 | GitHub 验证 | 真实含义 |
|---|---|---|
| v16 | 通过 | 研究板级兼容接口，未确认 M6 GPIO |
| v17 | 通过 | Linux 7.2.7 实验 ABI 联合构建，并非原厂 4.9.191 模块 |
| v18 | 通过 | 参考 stage1 DTB 中 MMC1 禁用；未取得 M6 DTB |
| v19 | 通过 | 公开 V851S/V851SE 均为 SDIO1，供电 GPIO 不同 |
| v20 | 12/12 测试通过 | 离线原始镜像中的 FDT 结构扫描 |
| v21 | 14/14 测试通过 | 离线 TOC1/boot_package 目录检查及 DTB 条目校验 |

## 当前证据缺口与下一步

- 已有升级包 `26041414.2807.2`，设备先前诊断现行版本 `25060316.2807.2`，**不是同一个版本**。
- 原厂 `kernel` 样本中没找到有效明文 FDT；不代表真实完整闪存没有 DTB。
- 需来自 **实际 M6** 的只读完整启动包/设备树、准确存储分区信息、Wi-Fi 上电 GPIO 和可验证的恢复路径。
- 针对固件型号 `2807`，<https://www.drive2.ru/b/655924107983990956/> 报告过使用 `Z2-V03 2024-11-09` 主板及 RTL8733BS 的类似适配器。这是**第三方实物参考线索，不是你的 M6 主板认证**。
- 不做自动刷写、不加载实验 `.ko`、不根据其它参考板 GPIO 修改真实启动参数。

## 工具

- `python tools/scan_fdt_v20.py --input FILE --out report.json`
- `python tools/audit_toc1_v21.py --input FILE --out report.json`

这两个工具**仅在本地、使用合法持有的二进制样本**；不连接实机、不上传原厂镜像；如果当前手头只有增量升级包，建议先检查是否能由厂商提供完整版本匹配的启动包，而不是继续刷机实验。

### 分阶段记录

下面保留最初的 v16 研究说明以追溯历史。详见 `docs/README-v19.md`、`docs/README-v20.md`、`docs/README-v21.md`。

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
