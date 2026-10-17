# M6 v28 — 原厂 ARM ELF 的 USB / EFEX / CGI 离线逆向（2026-10-17）

本轮对用户自己提供的 **26041414.2807.2** 升级包 `customer` 中真实 7 个程序或脚本进行解包后静态审计，不执行二进制、不联系实机、不操作厂家云端。用户已明确要求 **不拆机**；该约束包含不短接、不焊接和不使用拆芯片编程器。报告只提交原厂文件 SHA256、ELF 只读区地址和安全分类，不上传私有原厂 ELF。

**运行中的设备此前报告 `25060316.2807.2`，与升级包不是同一版本。下述证据来自 OTA，不可推定为运行设备当前状态。**

## 发现 1：CarPlay 与 Android Auto 是两条明确不同的启动分支

`app/lyLink.sh` 根据 `/mnt/UDISK/ly_linktype_aa` 选择服务：AA 路径启动 `raaservice -B -w -k1`；默认 CarPlay 路径启动 `logwrapper ly_testcp -f=2 &`、`rcpservice` 和 `lylinkapp`。因此 `raaservice` 中存在 ADB/USB Accessory 代码不能证明 CarPlay 正常模式会执行该配置。

## 发现 2：原厂 ARM ELF `.rodata` 中存在多套 USB Gadget 命令

对 stripped ELF32 ARM `ly_testcp` 的 ELF header 和 section header 进行离线验证，`.rodata` 文件偏移 `0x103b0`，虚拟地址 `0x203b0`，大小 14,447 B。出现：

- `rm configs/c.1/ffs.adb`：**移除** ADB FunctionFS 接口的静态命令；
- `ln -s functions/acm.gs0 configs/c.1`：建立 ACM USB 串口类的命令；
- `echo 0x0525 > idVendor` / `echo 0xA4A7 > idProduct`：该源码段会设置另一组测试 VID/PID，**不是** Windows 实际检测到的 `05AC:12A8`；
- `/sys/kernel/config/usb_gadget/rockchip/` 与 `/sys/kernel/config/usb_gadget/g1/` 同时存在；还有多个不同 UDC 名称。

**结论：这是多平台、多模式二进制。** 只要没分析完 ARM 反汇编的条件分支，就不能根据字符串把某一套 USB 操作归属于当前 M6。不能把 `{"code":0}` 当作启动了 ADB，已运行的 Windows `adb devices` 实测为空。禁止强行修改 USB 驱动绑定。

## 发现 3：找到了 `ly_efex`，但不是可用的无拆机恢复通道

`ly_testcp` 的 ELF `.rodata` 包含 `/sys/class/misc/ly_misc_dev/ly/ly_efex` 和 `ly_efex_mode=`，同区域还存在 `/proc/cmdline`、`reboot` 字符串。这是有价值的下一阶段代码交叉引用目标。

**截至 v28 没有确认该代码在 M6 运行，未确认写入值、进入 BootROM 的条件或稳定恢复方法。严禁实际写入该节点、触发未知测试按键或执行重启命令。**

## 发现 4：原厂后台同时含分区读取和破坏性擦写代码

`ota/www/cgi-bin/index.cgi` 的 `.rodata` 文件偏移 `0x630c`，存在 `/proc/mtd`、`MEMERASE`、清理 `/mnt/UDISK` 的命令。不能把读取字符串等同于经安全认证的只读全盘导出接口；`id=host` 以外的 CGI 功能未经验证，禁止主动试探。另 `app/lyUpdate.sh` 会使 OTA 版网页、CGI 替换系统底层默认页面，`mtpservice.conf` 含 `/mnt/UDISK` 读写存储声明与另一个占位 USB VID；不代表设备当前启用了该 MTP 配置。

v27 发现的“提交日志”OSS 上传链仍是安全风险；不要点击提交日志或申请 STS 凭据。

## 验证与交付

- [v28 精确 SHA256/只读区/事实白名单报告](customer_v28_evidence.json)。
- 当前会话交付 `M6-v28-offline-USB-RE.zip`：含 `reverse_usb_v28.py`、`test_v28.py`、原始样本（用户自行提供）可用的 `squashfs_xz_v27.py`、完整本地 JSON、中文报告。
- 本地 6 项单元测试全部通过（含 1 项真实原厂镜像）；公开运行时没有用户私有镜像，对该项应跳过。测试结果不构成真实 USB 调试或刷机能力。

## 后续目标

**下一阶段只做原厂 ELF 的控制流与字符串交叉引用**：确认 `ly_efex` 对应哪些条件、是否只属于工厂测试，检查 CGI 的 `conn=` 设置究竟持久化在哪里。最终必须取得**无拆机、可验证的完整备份和可恢复路径**，否则 `safe_to_flash=false` 不变。
