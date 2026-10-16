# M6 V851S v20 — 原厂完整镜像中的 DTB 安全定位（仅离线）

## 做到了什么

这是 **只读扫描脚本与合成样本测试**，不是 M6 驱动/固件。它可以在 Windows/Linux/macOS 的 Python 3.10+ 上扫描**用户合法持有的**原厂完整镜像、原厂启动包、单独的 DTB、ZIP 升级包（ZIP 原地解压到内存，不写回）、或包含原厂镜像的文件夹。

对每个输入输出 SHA256、格式线索、通过较完整 FDT 结构边界校验的候选 DTB 数量、偏移、根节点的 model/compatible，以及有限的 MMC/WLAN 硬件节点属性。不记录 MAC、序列号、密码等属性；不执行输入镜像中的代码。不会连接设备、修改分区、提供刷机功能或自动认为候选就是 M6 DTB。

## 当前 M6 证据限制

此前用户提供的升级镜像版本是 `26041414.2807.2`，当前设备早前报告 `25060316.2807.2`。曾扫描的仅是 **升级包 kernel**（2066432 字节）而非完整闪存备份；没有找到 FDT。原厂驱动是 Linux 4.9.191，不能把 Linux 7.2.7 的研究 `.ko` 装入原厂系统。

另一个 V851S 同系列设备曾在启动日志 `Entry_name = dtb`，提示设备树可以放在 U-Boot 启动包里。**不能据此认定 M6 相同，更不能沿用其它设备的 GPIO、bootloader 或固件。**

## 在本地使用，不要把原厂完整镜像上传 GitHub

解压 v20 ZIP 到一个文件夹；进入该目录，在 PowerShell 中执行：

```powershell
python -m unittest discover -s tests -p test_v20.py -v
python tools/scan_fdt_v20.py --input "D:\M6原厂固件\kernel" --out "v20-report.json"
```

如果持有**合法来源、版本可确认**的完整原厂闪存镜像，则换成 `--input "D:\M6原厂固件\flash_backup.img"`；也可以输入 ZIP 或某个**只含待分析镜像**的文件夹。多份输入允许重复指定 `--input`。结果写在本地 JSON。它不会把原始二进制/DTB上传到任何平台。

**本工具不会自动输出候选 DTB 的二进制文件**；先完成来源和版本核对、排除误识别，再考虑手工提取。报告的 GPIO 只是样本中已有的数据，未经实机测量不能使用。

限制：单文件至多 1 GiB、DTB 至多 16 MiB、ZIP 单文件解压上限 256 MiB，文件数有上限；压缩/加密/混淆数据、厂商专用 boot package 未必能识别，`0 candidates` 不表示设备没有 DTB。候选通过结构校验也不表示签名、板型、运行版本与真机一致。

## 上传到 GitHub 的文件

- `.github/workflows/m6-stock-image-v20.yml`
- `tools/scan_fdt_v20.py`
- `tests/test_v20.py`
- `docs/README-v20.md`

进入 Actions 运行 `M6 v20 offline DTB locator synthetic safety tests`，测试只使用自动生成的合成 DTB 和此前的 v18 JSON 结论，**不上传原厂镜像**。它通过也不代表拿到了 M6 设备树。

## 下一步实际证据

从厂商获取针对 `v851s-lybox_rtl8`、设备当前版本 `25060316.2807.2` 的官方完整镜像/启动包或可核验版本的只读备份；若以后可以合法、安全地获得本机命令行，则优先检查只读 `/proc/device-tree`（前提是内核提供）；绝不直接按网上其它 V851S 的 PIN、分区布局操作。**禁止刷机、覆盖 boot0、修改启动分区、擅自启用免密 root/telnet。**

参考资料：
- https://tina.100ask.net/SdkModule/Linux_Deploy_DevelopmentGuide-04/
- https://allwinner-docs.100ask.org/en/System/Linux_SystemSoftware_DevelopmentGuide.html
- https://github.com/gxcreator/aa-smartbox-re
