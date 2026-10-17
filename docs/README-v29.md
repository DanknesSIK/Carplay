# M6 v29 — ARM32 ELF 字符串交叉引用与 EFEX 条件分支（2026-10-17）

本轮继续**纯离线**分析用户持有的 `26041414.2807.2` 原厂 OTA 解出的 ARM32 ELF，不连接实机。其当前实际安装版报告为 `25060316.2807.2`，两版不一致。用户不接受任何拆机，且无验证备份恢复路径，因此 **safe_to_flash=false**。

## 新结果：`ly_efex` 是状态检查而非已验证的 FEL 启动入口

在 SHA256 `76d0e614179e67a8089ef81b732b65a6662a97e3278a22002a2e3444e1b40ed9` 的 `app/ly_testcp` 中，通过真实 ARM 指令验证：

1. 函数 `0x158e8` 调用 `getenv("LY_PLATFORM")` 后用 `strcmp` 返回平台 ID：`v3=0`、`v831=1`、`v851=3`、`09=2`、`v821=4`、`aixin513=5`、未匹配为 0。
2. 函数 `0x13740` 在 `0x13764` 判断平台 ID 是否等于 `5`：
   - **ID 5（aixin513）**：`open("/sys/class/misc/ly_misc_dev/ly/ly_efex",2)`、`read` 最多 16 字节、`atoi`，判断结果是否为 1；没有发现该函数对该节点写入。
   - **其它平台（包括 `v851`）**：读 `/proc/cmdline`，`strstr("ly_efex_mode=")`，用 `strtoul(...,10)` 提取数值，返回是否等于 1。
3. 在 `0x14ee0` 调用上述函数；返回非零时进入显示状态/等待循环，**尚未找到在该调用链内激活 BootROM FEL 的命令**。不能用该代码指导用户触发 FEL。

这些是原厂 OTA 静态控制流结果，**不是本机实测 `LY_PLATFORM` 值**，更不证明存在无拆机恢复通道。公开的 V821B/ly6239 研究仓库也使用 `ly_efex_mode`，但硬件不同不能照搬恢复方法：
https://github.com/lvalen91/CPC200-CCPA_resources

## 实际交叉引用（静态代码地址）

- `ly_testcp`：`ly_efex_mode=` → `0x137ec`；`ly_efex` → `0x13770`；`rm .../ffs.adb` → `0x1316c`；`echo device > .../usb_mode` → `0x13000`。
- `index.cgi`：`conn=` → `0x136ec`, `0x145c4`, `0x151b0`；`/proc/mtd` → `0x15a0c`；UDISK 破坏性清理字符串 → `0x14550`。
- `raaservice`：`configs/c.1/ffs.adb` → `0x2160c`, `0x21abc`。
- `MEMERASE` 在当前支持的 PIC 检测器中没有直接 xref，**这不证明没有擦除逻辑**。

本地工具 `xref_arm_v29.py` 使用 `llvm-objdump` 离线反汇编并匹配 ARM 状态的 `ldr rX,[pc]` + `add rX,pc,rX` 地址引用；不执行任何原厂代码。此方法不覆盖所有 Thumb/ARM/间接引用，不能仅凭缺失 xref 推断代码不可达。**3/3 本地测试通过**。完整脚本、测试和私有二进制之外的分析 JSON 打包为 `M6-v29-ARM-xrefs.zip` 提供给用户。

下一阶段重点是 `index.cgi` 的三处 `conn=` 交叉引用以及持久化写入方式；仍不得调用未知 CGI、修改设备开机模式或刷写。