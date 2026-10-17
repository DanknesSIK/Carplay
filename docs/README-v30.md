# M6 v30 — `conn=adb` 真实配置读写的 ARM 反汇编证据（2026-10-17）

只分析用户持有的原厂 OTA `26041414.2807.2` 中真实 `ota/www/cgi-bin/index.cgi` (SHA256 `3978333fc280e3ad5b0afa718474af61327f20812b54730d7bb26086dcfda6c9`)。本机旧运行版报告 `25060316.2807.2`，**并不相同**。无实机通信、无厂家程序执行、无拆机、无闪存操作。

## 真实 ARM32 调用链

通过 v29 的 ELF 地址交叉引用和 v30 对原厂 `bl` 指令验证：

1. `0x145b0` 取得 `private` 字符串，`0x145b4` 调用 `0x159f4`（解析 `/proc/mtd` 定位分区）。
2. `0x145c4` 构建 `conn=` 字段。
3. `0x14604` 调用 `0x15d24`，进入配置块更新函数。
4. 更新函数核对旧数据（`0x15f1c` → `read`、`0x15f94` → `memcmp`），需要变化时用 `memcpy` 修改缓冲。
5. 包含实际 MTD ioctl 参数 `MEMGETINFO 0x80204d01`、`MEMUNLOCK 0x40084d06`（`0x160e8`）和 `MEMERASE 0x40084d02`（`0x16134`）；之后 `0x161e4` 调用 `write`，`0x161f8` 调用 `fsync`，并检查写回结果。

原厂程序的 **9 个 ARM BL 调用关系和 3 个 MTD ioctl 常量**均通过精确 SHA256、真实 ELF 和 ARM 指令核查；**3/3 本地测试通过**，均不操作设备。对应事实清单见 [customer_v30_evidence.json](customer_v30_evidence.json)。原始 CGI 和私有固件不上传公共 GitHub。

## 实际含义

`/cgi-bin/index.cgi?id=set&conn=adb` **不是只读操作**。在该 OTA 版本中，`conn=` 设置路径会更新 **`private` MTD 分区持久化配置**，并不能证明 USB `adbd` 已启用。用户当时观察到 `{"code":0}`，但 Windows 枚举显示苹果风格 `05AC:12A8`、`adb devices` 为空；两者并不矛盾。

**不要继续反复访问 `conn=adb` 或未知 CGI**：会带来对闪存配置的擦写风险。用户没有提出再次更改配置，不要擅自调用设置接口；如果当前 CarPlay 正常，无需操作。

## 不能从此推出的结论

- 该控制流来自 **新版 OTA 的 CGI**，不证明当前已安装的旧版 CGI 逐字节相同。
- 函数含条件分支；执行成功并不保证每次都会擦除，但这是经过确认的可能写入路径。
- CGI 存在 `/proc/mtd` 或旧配置读取函数，**不等于具有经认证的整机只读备份下载 API**。
- 当前仍缺真实 M6 专属 DTB、现机完整备份、可靠无需拆机恢复入口；`safe_to_flash=false`。

本地 `M6-v30-CGI-private-write-audit.zip` 提供离线校验脚本、v29 ARM PIC 交叉引用工具、测试和已脱敏 JSON。用户明确不接受拆机；后续仅允许离线原始文件逆向、可靠的只读证据分析。