# M6 V851S v22 — 全志 PhoenixSuite 完整镜像 `IMAGEWTY` 离线目录审计

## 本轮新增的关键功能

此前 v20 直接扫描明文 FDT，v21 专门检查 TOC1 启动包。**v22 首先解析更外层的 PhoenixSuite 完整 `.img`**（二进制头 `IMAGEWTY`），检查目录的条目数、每项名称、长度和起始偏移，再对相关条目执行二级审计：

- `sunxi.fex` / `sunxi.dtb` / `dtb.fex`：做有限的 FDT 结构扫描，记录候选 DTB 节点与相对偏移；
- `boot_package.fex` / `toc1.fex`：复用 v21 TOC1 条目检查，判断其是否列出结构有效的 `dtb`；
- `u-boot.fex`：只做有上限的明文 FDT 搜索；**并不意味着能解析所有 Allwinner 打包变体**；
- `sys_partition.fex`：仅记录名称、偏移和大小，不声称能解释完整分区表。

所有边界按 **本地文件实际大小**验证，拒绝过大目录、越界和条目重叠。对最多 64 MiB 的相关条目计算 SHA256。扫描不会解包写文件，也不接触设备或服务器。

来源依据：Andre Przywara 的开源 `sunxi-fw`，`sunxi-wty.c` 明确给出 PhoenixSuite 容器的 `IMAGEWTY` 头、0x400 字节目录单元、条目名称偏移和 64-bit 数据起止字段。

https://github.com/apritzel/sunxi-fw/blob/main/sunxi-wty.c

## 只在本人电脑本地使用

如果已经拥有可信、版本匹配的原厂完整 `.img`（不需要现在取得，也不应上传公开仓库），在当前仓库根目录运行：

```powershell
python tools/audit_phoenix_wty_v22.py --input "D:\\M6\\stock-full.img" --out "D:\\M6\\phoenix-index-v22.json"
```

**注意不是 Android `kernel` 启动镜像，也不是 SWUpdate 的增量 `customer`。** 只有文件头为 `IMAGEWTY` 的完整 PhoenixSuite 镜像才能由这个脚本检查；对其余格式会拒绝并退出，而不是输出虚假的 M6 DTB 结论。

限制：完整文件最多 8 GiB，条目最多 256，二级检查最多 64 MiB；静态 SHA256、偏移和明文设备树结构不能证明镜像来源或匹配原厂正在运行的 `25060316.2807.2`。任何输出都包含 `safe_to_flash=false` 和 `m6_real_device_dtb_authenticated=false`。

## 自动测试

Actions → `M6 V851S PhoenixSuite IMAGEWTY container index v22 (synthetic only)`。该工作流测试人工合成的完整镜像、FDT 和 TOC1 的组合，以及越界、重复覆盖、损坏条目等异常情况。不下载任何真实原厂镜像，不生成固件，不刷写盒子。

## 证据分级

- **已实跑**：v16–v21 离线编译和模拟测试；
- **本版本会验证**：完整 IMG 目录解析器能处理合成样本；
- **仍缺失**：可信的目标板 `v851s-lybox_rtl8` 真机 DTB、板级供电引脚、可核验的恢复路径；
- **禁止**：把其它设备的 `sunxi.fex`、启动分区或内核模块直接写入物本 M6。

