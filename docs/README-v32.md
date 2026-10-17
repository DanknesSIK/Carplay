# M6 v32：原厂升级失败路径与 UDISK 风险分析（2026-10-17）

**本轮为真实原厂固件的离线静态分析；没有连接用户的物本 M6，没有刷机、升级、修改设置或拆机。** 证据来自取得的 `26041414.2807.2` 升级包，用户设备此前报告 `25060316.2807.2`，所以所有结论必须保留版本差异这一前提。

## 已验证的三个发现

**1. 固件更新程序有条件地调用 `format_udisk.sh`。** 原厂 `app/update` SHA256 `be9e84ec0cca4ec505eb6177eaa42809c596bfef43a2a5f8ad62ebb0e40242c6` 的 ARM 指令：`0x10e00` 调用 `strncmp` 比较 `upgrade_` 前缀，`0x10e08` 在不相等时分支到 `0x10f28`；`0x10f2c` 引用 `format_udisk.sh`，`0x10f30` 调用 `0x119b0` shell 执行包装函数。此路径受前面的状态判断约束，不能声称“每次升级都会格式化”。**实际 `format_udisk.sh` 脚本未包含在提取的用户 `customer` 镜像中**，因此暂时不能说明具体会擦除哪些内容。

**2. `app/check_udisk.sh` 的自动修复存在真实的格式化回退。** 如果 `/mnt/UDISK` 没有挂载，脚本尝试根据文件系统类型处理。JFFS2 挂载失败后可能运行 `mkfs_jffs2`，ext4 分支运行 `fsck.ext4 -y`，挂载失败后又有 `mkfs.ext4 -m 0`。这些是用户真实原厂样本中的 Shell 代码，不代表已在当前设备触发。不应把 UDISK 的内容安全视为升级流程必然保证的特性。

**3. 发起升级只是异步提交，不代表全部阶段成功。** 原厂 `app/update` 在 `0x114ec` 运行 `fw_setenv ly_boot_mode update`，`0x114f8` 运行 `touch /mnt/UDISK/update_flag`，`0x11520` 调用封装函数执行 `swupdate_cmd.sh -i %s -e stable,upgrade_recovery &`（后台启动）。`0x11524` 检查的是 Shell 调用返回值，并非 SWUpdate 各分区写入已完成；程序其他代码中还存在后续升级状态与成功/失败处理。原厂 `lyUpdate.sh` 在替换后台更新程序时使用 `killall -9 update`，也会重新启动 httpd。**未在审计样本中验证完整回滚链。**

## 升级失败阶段与未验证事项

| 阶段 | 原厂 manifest / 程序的事实 | 无法验证的风险 |
| --- | --- | --- |
| 开始前 | `boot_partition=recovery`，但 recovery 镜像安装条目被注释 | 当前现机 Recovery 是否可用 |
| 写入过程中 | 写 `boot`、`customer` 镜像 | 断电、写入失败能否回滚 |
| 结束时 | 清理 SWU 状态并返回 `boot` 引导 | 故障时是否有环境变量滞留 |
| UDISK 异常 | 格式化条件调用和自动文件系统修复代码已验证 | 当前机型/版本实际触发条件，原机数据是否可备份 |

## 工具与测试

已经建立完全离线的 v32 审计器（仅用户本地现有固件输入），具有**固定 SHA256 识别、关键 ARM 指令核对、缺失脚本判定、无副作用输出**。用户真实样本本地 **5/5** 测试通过。打包交付 `M6-v32-recovery-failure-offline-audit.zip`，没有包含任何 OEM ELF 或原厂镜像。在不携带私人固件的独立目录执行测试：**4 通过，1 项真实样本测试按预期跳过**。工具使用需要 Python 3 和 LLVM objdump。

本项目此前的 [v31 OTA 启动顺序分析](README-v31.md) 和 [Issue #1](https://github.com/DanknesSIK/Carplay/issues/1) 仍适用。**SAFE_TO_UPGRADE=false，SAFE_TO_FLASH=false**；没有不拆机的完整原厂备份和故障恢复方案，不能建议实机升级。
