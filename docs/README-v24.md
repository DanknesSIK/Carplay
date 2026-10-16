# 物本 M6 v24 — FIT 与真正板级设备树分离

## 为什么修复

U-Boot FIT（常用扩展名 `.itb`）**本身就是 Flattened Device Tree (FDT) 格式**。如果仅根据 FDT magic（`d00dfeed`）和结构校验判定“发现设备树”，可能把 FIT 启动镜像的元数据误认为 Linux 运行设备树。此前的 v20/v21/v22 使用的是纯静态结构查找，因此存在这种报告混淆风险。

官方 FIT 格式说明：
- https://docs.u-boot.org/en/v2024.04/usage/fit/source_file_format.html
- https://docs.u-boot.org/en/stable/usage/fit/index.html

## 本次修复

1. v20 在 FDT 校验过程中区分三种类型：
   - `u-boot-fit-container`：存在顶层 `/images` 和 `/configurations` 节点；
   - `board-device-tree-candidate`：非 FIT 且根节点具有 `model` 或 `compatible`；
   - `unclassified-fdt`：结构有效但无法确认性质。
2. v20 的总 `valid_literal_fdt_count` 保留原意，同时**单独统计** `board_device_tree_candidates_count` 和 `fit_container_count`。若只检出 FIT，不再写成“找到板级 DTB”，而使用 `fit-container-only-not-a-board-dtb`。
3. `tools/inspect_fit_v24.py` 解析 FIT 镜像列表、默认配置、各配置引用的 FDT 与其他镜像，并对 **未压缩** 的 `flat_dt` 子镜像做结构验证。
4. 支持内嵌 `data` 和 `data-offset` 的边界检查；对于含糊的 `data-position` 固定地址，仅记录而不擅自视为本地文件偏移，也不执行解密或解压。
5. v22 PhoenixSuite 检查器可在 `u-boot.fex`、`sunxi.fex`、`boot_package.fex` 等相关条目中识别 FIT 元数据，并从内部列出候选 DTB，但始终保留“来源/真实 M6 板级身份未认证”。

## Windows 本地离线用法

在你的工作副本根目录，仅对你**合法持有**的完整原厂数据执行：

```powershell
python tools/inspect_fit_v24.py --input "D:\M6\u-boot.itb" --out "D:\M6\fit-v24.json"
python tools/audit_phoenix_wty_v22.py --input "D:\M6\stock-full.img" --out "D:\M6\stock-index-v22.json"
```

第一条只接受有效 FIT 结构；普通板级 DTB 或损坏容器会被拒绝。第二条只接受 PhoenixSuite `IMAGEWTY` 镜像，可在相关目录项内调用 FIT 分析。

**限制：** 配置引用不等于签名验证；未解压压缩 FDT；`data-position` 不自动寻址；仅使用静态字节，不判断哪一份 DTB 真正由 bootloader 选用。即使找到 `model` 或 `compatible`，也**不能**认证 `v851s-lybox_rtl8` 这台设备，不能证明其 GPIO、电源时序或升级恢复能力。

## 自动回归和来源区别

GitHub Actions：`M6 v24 FIT metadata vs board DTB audit (offline synthetic only)`。

- FIT 元数据结构、嵌入式/相对位置 FDT、边界错误、压缩格式禁解析、无法定位的固定地址均用**合成**样本测试。
- 与 v22 结合测试，检查 `u-boot.fex` 以及非 TOC1 `boot_package.fex` 的 FIT 目录识别。
- [v23 工作流](https://github.com/DanknesSIK/Carplay/actions/runs/38869022595) 仍用于公开、来源固定的 V851SE 真实 DTB 测试，但那些样本不是你的 M6。
- 实机仍未获取可信 DTB 或完整版本一致的固件备份，当前 `safe_to_flash=false`、`safe_to_load=false`。

## 下一步有实际价值的证据

1. 获取真正匹配用户现行固件 `25060316.2807.2`、目标板号 `v851s-lybox_rtl8` 的厂商完整启动包或可信只读备份。
2. 核查分区布局、DTB 版本、GPIO/SDIO 控制器及真实 Wi-Fi 上电信号。
3. 在恢复路径和验证依据充足之前，不加载 v17 Linux 7.2.7 研究模块到厂商 Linux 4.9.191，不直接刷写。

此前已获取的更新包 `26041414.2807.2` 与设备诊断运行版本不一致，不能当做原机完整备份。
