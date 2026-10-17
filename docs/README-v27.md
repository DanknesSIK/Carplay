# M6 v27：真实原厂 customer 的离线逆向结果（2026-10-17）

> 用户不接受拆机或短接测试点。仅分析用户既有固件，不联系实机，不刷写。**safe_to_flash=false**。

## 样本与真实性
对用户原始 `customer` SquashFS 4.0/XZ（4,366,336 字节，SHA256 `f81c48122f138855ad193fd48a7eafff84691c4a2bd621cb19d2c115c2d3a1d5`）进行了**真实解包**，得到 67 个普通文件（合计 9,636,620 字节），以及一个未按普通文件提取的设备节点。包含 ARM CGI、`ly_testcp`、`lylinkapp`、无线驱动和 OEM 前端。没有执行任何厂商程序。提取出文件的白名单 SHA256、功能标志及风险分类见 [customer_v27_evidence.json](customer_v27_evidence.json)。

**OTA 是版本 `26041414.2807.2`，而用户先前的已安装版本报告为 `25060316.2807.2`。** OTA 不等于当前原机的完整闪存备份。

## 新发现

**1. 新旧网页 ADB 选择器不一致。** 用户另存的旧版原厂管理页面 `M6-backend.html`（SHA256 `f9d1595ea4df1cb360b6c0be5a986e7b36a3115a42eee125231d6e71c017e029`）包含 `div_conn`、`function onSelConn()` 和 `value: "adb"`。但新 OTA 中实际读取的 `ota/www/index.html` **三者都没有**，只保留了 `hdconn()` 机型条件函数。新 OTA 的 `index.cgi` 仍包含 `conn=` 参数及输出 `conn` 状态字段的字符串。因此：设置请求返回 `{"code":0}`，不能证明 USB ADB 可连接。

**2. USB 模式控制代码线索。** 原厂 `lyLink.sh` 启动 `ly_testcp`；后者二进制含 `rm configs/c.1/ffs.adb`、`echo device > /sys/usb_ctrl/usb_mode`、`functions/accessory.gs2`，表明存在针对 USB Gadget 的配置代码。**只是字符串静态证据**，尚未证实实际执行了哪条分支。实机 Windows 枚举 `05AC:12A8` 而 `adb devices` 为空；继续反复安装 ADB 驱动无价值。

**3. 后台部分接口有副作用或隐私风险。** CGI 包含 `id=host`、`id=logcat`、`id=sts`、`id=set`、`id=p2p`、`id=upload`、`id=aa`、`id=png`。已有用户网页调用表明 `id=host` 查询状态；`id=logcat` 在 CGI 中汇总 `dmesg` 与 `logcat` 为 `/tmp/log.gz`，网页随后使用 `getOSSCli().then(c => c.put(n,b))` 上传日志，并另外上传包含设备信息和表单信息的 JSON。**不要按网页提交日志按钮、不调用 STS 获取云端凭据、不调用 P2P 或未知更新接口。** `id=p2p` 关联停止 AP/开启 P2P 的命令，并非查询。

**4. Wi-Fi 及分区分析。** 原厂 `modules/8733bs.ko` SHA256 为 `aa4a1205f77dd06b2ab82ff9e1af22125b9f831c1bc8fcfa92b0a5c74e6477b9`；`lyLoadModule.sh` 有 `8733bs`、`8821cs`、`aic8800` 分支。CGI 含读取 `/proc/mtd` 及访问 `/dev/mtdblock%d` 的函数线索；**不意味着存在经认证、无副作用的整机闪存下载 API**。

## 离线复现
已制作标准库 Python 3 的 SquashFS v4/XZ 只读提取与标记工具、白名单哈希分析程序、单元测试。原厂二进制**没有上传到公共仓库**；可在本地持有的同一 `customer` 样本执行：

```sh
python tools/audit_customer_v27.py --input /path/to/customer --backend-snapshot /path/to/M6-backend.html --out customer_v27_evidence.json
python -m unittest discover -s tests -p 'test_v27.py' -v
```

本轮用户真实样本本地验证 **5/5** 通过，包括受限解压、错格式拒绝、隐私报告与真实固件指纹校验。测试不证明 M6 实机兼容。完整 v27 工具包已作为当前会话 ZIP 交付（包含所有工具源文件）；公共仓库先保存原厂分析报告，不存放固件原文。

## 后续路线
继续分析现有 ARM CGI 与 `ly_testcp` 的**静态代码交叉引用**，限定于既有固件；不拆机、不试刷、不调用未知接口、不尝试未授权网络访问。恢复路径尚未验证，刷机禁令不变。
