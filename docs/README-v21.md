# M6 V851S v21 — TOC1/boot_package 离线目录核验

## 新增成果

v20 是普通二进制中的 FDT 魔数扫描器。v21 新增只读 TOC1 **容器级**解析，可以先解析全志启动包（常见于 `boot_package.fex`、`toc1.fex`）的头部和条目目录，再判断 `dtb`、`sunxi.dtb`、`fdt` 条目中是否包含结构有效的 FDT。

检查：TOC1 头部 magic、长度、item 数量、校验和、条目结束符、数据边界、512 字节对齐、区间重叠；加密项不尝试解密。输出 SHA256、候选偏移、名称和有限 DTB 节点信息。检出 DTB **不能证明**它属于真实 M6 或与现有固件一致。

参考代码来源：
- U-Boot TOC1 RFC（2021-10）：https://lists.u-boot-project.org/pipermail/u-boot/2021-October/463731.html
- 全志 Tina Linux OTA / boot package 说明：https://cloud.tencent.com/developer/article/2225252
- 公开全志私有 TOC 结构：https://github.com/BPI-SINOVOIP/BPI-M3-bsp/blob/master/u-boot-sunxi/include/private_toc.h

## 使用方法

无需拆机、无需取得 root，只有在你**已经合法拥有可信固件文件**的情况下才运行：

```powershell
python tools/audit_toc1_v21.py --input "D:\M6\boot_package.fex" --out "D:\M6\toc1-report.json"
```

也支持本地 `toc1.fex` 或完整只读闪存备份（需是原始二进制）。会检查任意文件偏移处的 TOC1。限制：输入最大 1 GiB，单 TOC 容器 64 MiB，64 条目，最多 16 个候选，防止畸形输入消耗无限资源。若内含另一种非 TOC1 启动格式、数据加密或压缩，未检出不等于不存在 DTB。不会从设备读取、不会刷写、不会加载模块、不会复制/导出原厂固件。

源码只允许读取本地已下载的二进制，不接收 URL，不做网络访问，扫描时不会将实际镜像上传 GitHub。

## GitHub Actions 验证

工作流 `M6 V851S TOC1 container and DTB index v21 (synthetic only)` 只运行人工合成 TOC1 的单元测试，以及不产生可刷写文件的安全门禁。**不上传真实固件**。成功仅证明解析器能正确处理测试样本，并不能替代生产设备验证。

## 当前不可跨越的证据缺口

- 设备诊断的现行版本早前为 `25060316.2807.2`，而此前得到的升级包版本为 `26041414.2807.2`，并非同一份在机备份。
- 真实 M6 `v851s-lybox_rtl8` 的 DTB、MMC、Wi-Fi 上电引脚、启动分区与恢复路径依然没有核验。
- v17 的 Linux 7.2.7 实验模块不能直接用于现行 Linux 4.9.191；禁止将任何 v16–v21 研究产物刷入盒子。

后续应继续搜索同一板号的完整原厂 boot package 或厂商分区布局文档；如果没有，不再反复无意义重新编译已有实验驱动。
