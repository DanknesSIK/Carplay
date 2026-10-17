# v31 — SWUpdate 真实升级流程与升级前校验静态审计（2026-10-17）

**结论：safe_to_upgrade=false / safe_to_flash=false。** 用户拒绝拆机和短接；当前实机版据报告为 `25060316.2807.2`，取得的 OTA 为 `26041414.2807.2`。整个 v31 仅接触原始本地升级样本，不接触实机，也不向任何服务器传输镜像、凭据或日志。

## 1. SWU 的完整性关联检查（实测）

`M6-header.bin` 只是 `update.swu` 的 **1,048,576 字节前缀**，开头的 45 字节是外层标签；偏移 45 为 CRC-newc CPIO 开始。

- `sw-description` 的头部偏移 **45**，数据偏移 **173**，长度 **3,186 字节**，CPIO 累加 CRC **`0x0002d92a`**；直接重新计算匹配。
- 紧邻的 `customer` 头部偏移 **3,361**，数据偏移 **3,481**，头部声明长度 **4,366,336 字节**，累加 CRC **`0x219e7f19`**。
- 用户另存的完整 `customer` 镜像长度、CPIO 累加 CRC、此前缀覆盖到的部分内容均与 CPIO 条目吻合。SHA256：`f81c48122f138855ad193fd48a7eafff84691c4a2bd621cb19d2c115c2d3a1d5`。
- 这是**同一 OTA 条目匹配证据**，不是厂商数字签名或适配许可。由于 SWU 全文缺失，不能验证后面的 `kernel` CPIO 条目、所有条目的 CRC、尾部 `TRAILER!!!` 等。单独 `kernel` SHA256 `5a17aa388f98011ba7f24508b9d6a4b84650c45ceb68f173307031dd15b992c9` 不构成整个包的校验。

## 2. 已启用的三阶段与风险

删除 C 风格注释后，实际生效的 SWUpdate 条目为：

| 阶段 | 修改引导环境/写入的对象 |
| --- | --- |
| `upgrade_recovery` | 设置 `swu_mode=upgrade_kernel`、`ly_boot_mode=update`、`boot_partition=recovery`；原先 `recovery -> /dev/by-name/recovery` 的 `images` **已注释，不执行** |
| `upgrade_kernel` | 写入 `kernel -> /dev/by-name/boot` 和 `customer -> /dev/by-name/customer`；设置 `swu_mode=upgrade_usr` |
| `upgrade_usr` | 清除 `swu_param`/`swu_software`/`swu_mode`/`swu_next`，将 `boot_partition=boot`、`ly_boot_mode=normal` |

即：**未验证现机 recovery 能启动之前，无法证明完整升级能从第一阶段安全走到第三阶段。** 包中未验证到可用于恢复引导链的完整刷机镜像。此前按照其他 M6 型号刷机的建议仍不安全。

## 3. 真实 ARM 更新程序调用边

真正的 `app/update` 是 ARM32 ELF，SHA256 `be9e84ec0cca4ec505eb6177eaa42809c596bfef43a2a5f8ad62ebb0e40242c6`。使用 `llvm-objdump` 验证：

- `0x11394 -> 0x12340`：项目标识检查函数；
- `0x11428 -> 0x11e18`：升级文件复制/校验路径；
- `0x11520 -> 0x119b0`：执行命令辅助函数；该调用附近存在确切格式串 `swupdate_cmd.sh -i %s -e stable,upgrade_recovery &`；
- `0x1251c -> 0x1095c` / `0x1258c -> 0x1095c` / `0x125ec -> 0x1095c`：使用 ARM PLT 的 `strncmp` 验证 manifest 中 magic 和项目标识的比较链；
- `0x12638 -> 0x10950`：ARM PLT 的 `strstr`，查询项目相关字符串。

程序还使用 `fw_printenv -n %s` 获取 `ly_project_name` 等环境变量，包含 `0xAA55A55A` magic、`cd %s;md5sum -c md5.txt` 校验命令。已证明**存在**校验代码与先进行项目检查的处理顺序，不代表该设备一定通过校验；也不能由此推断签名有效、断电可靠或者分区布局正确。

原厂 `lyUpdate.sh` 会重启或替换升级及网页服务；`lyLink.sh` 在 update 模式会删除 UDISK 中的 Android Auto 标记。这不是无副作用的“更新应用”。

## 4. 可复现与限制

本轮新写的 `audit_ota_v31.py` 只读解析偏移正确的 CRC-newc、校验 `sw-description` 与独立 `customer` 之间的关联、以固定 SHA256 检查真实更新程序以及验证上述 7 条 ARM32 BL 调用边。6/6 本地测试通过（包括真实原厂样本和错误输入拒绝）。独立 ZIP 包含工具、测试、已脱敏 JSON 报告和说明，**不包含原厂二进制**。

没有完整 CPIO、当前版本的全量闪存备份、Recovery 真正内容、认证的 DTB 和不拆机的恢复方式之前，**不推荐安装 OTA**。

## 后续

继续对 `app/update` 的错误码、升级失败分支以及 `swupdate_cmd.sh` 的系统依赖关系作离线分析；不要继续尝试隐藏 CGI、ADB 切换、按键复位或刷机。
