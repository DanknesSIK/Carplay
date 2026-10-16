# M6 V851S v19 — 公共参考设备树差异检查（只读）

本补丁延续 v18 结果，**不修改现有 v16/v17/v18 文件**，仅检查两份固定 Git commit 的公开参考 DTS。它不需要设备、不生成 DTB，也不运行驱动，更不会接触真实 M6。

## 核心发现

| 项目 | gxcreator V851S | hbouhadji V851SE |
|---|---|---|
| SDIO WLAN 连接 | `wlan_busnum = 1` | `wlan_busnum = 1` |
| SDIO1 控制器 | `0x04021000` | `0x04021000` |
| 总线宽度 | 4 bit | 4 bit |
| WLAN_REGON | `PE6` | `PA11` |
| CHIP_EN | `PH13` | `PE9` |
| 原厂 M6 `v851s-lybox_rtl8`? | 否 | 否 |

注意：V851S 和 V851SE 是不同变体；上表的电源控制引脚不可迁移到 M6。上面两份参考固件和前述 `catplay` 项目中的同名商业型号，都不足以认定你的 M6 硬件已经得到支持。

## 上传路径

将此压缩包解压后，**按相同的相对路径**上传到原仓库 `DanknesSIK/Carplay` 的 `main` 分支：

- `.github/workflows/m6-reference-sdio-v19.yml`
- `tools/audit_reference_sdio_v19.py`
- `tests/test_v19.py`
- `docs/README-v19.md`

测试：

```sh
python3 -m unittest discover -s tests -p 'test_v19.py' -v
```

启动：`Actions` → `M6 V851S public reference GPIO comparison v19 (offline audit only)` → `Run workflow`。产物为 `m6-v19-public-reference-audit-not-verified`，其中含 JSON 证据和两个源码的 SHA256。Workflow 的名称里 `offline audit` 是指设备离线、纯静态分析，工作流本身仍需网络读取公开 DTS。

## 当前不可跨越的证据缺口

1. 还没有从 **真正的 M6 (`v851s-lybox_rtl8`)** 获得可信的 DTB／boot 分区映射。
2. 还没有 M6 板卡真实 GPIO、SDIO、供电和时钟的可验证资料。
3. v17 的 `.ko` 编译成功并不意味着能安装到原厂 Linux 4.9.191 或当前盒子。

不得刷写、安装模块、修改 Boot0、硬套上述参考引脚。即使此处 `PASS` 也仅表示“公开参考树的已知差异得到确认”。

## 已核对的参考源码

- https://github.com/gxcreator/aa-smartbox-re/blob/00fa1232a2faa04b91efb4dbd4d7e345489b7c1a/info/decompiled-tree-linux.dts
- https://github.com/hbouhadji/prototype-v851s-port/blob/05d8262010922cefe05592238e8f60f98dab4613/analyse-v851s/stock-full.dts
