# M6 V851S + RTL8733BS 云端编译实验（v9）

这是从 v8 独立出来的**真实内核模块构建尝试**。它不是固件、不连接 M6、不包含刷机流程；成功编译也**不能**证明模块能在原厂 Linux 4.9.191 上加载。

## 最快执行方式：GitHub Actions

1. 在你自己的 GitHub 新建一个**私有或公开**仓库，上传本压缩包的**解压后文件及文件夹**，保留 `.github/workflows` 目录。
2. 进入仓库 Actions → `M6 ARM32 experimental RTL8733BS build` → Run workflow。首次推送也可能自动触发。
3. 等待工作流结束，在页面底部下载 `m6-build-logs-and-experimental-module`；**失败也会生成日志**，把 `ci-output/build.log` 发回来即可。

注意：Github Actions 的运行时间/配额因账号而异。暂未实际在云端执行本流程；它是编译尝试，不保证一次通过。不要把任何生成的 `.ko` 放入 M6。

## 构建逻辑和严格边界

- 核对 3 个公开源码仓库的 Git 提交，另外核对 Linux 7.2.7 源码 SHA-256。
- 给实验性 V851S Linux 内核补足 MMC、SDIO、cfg80211、MODULES 选项，并**检验 Kconfig 实际启用情况**。
- 完整编译研究内核（不是 M6 原厂内核），生成匹配的 Module.symvers；再尝试编译 RTL8733BS `.ko`。
- 它使用 CatPlay Linux 7.x 补丁及 ARM32 适配副本。如果上游补丁、新内核接口、交叉编译出现错误，自动停止并保留详细日志，不将失败标为成功。

## 已知局限

- 同为 V851S 并不代表相同的内存、供电、SDIO引脚、板级设备树或 flash 布局。
- 实验内核和生产 M6 内核版本不同；生成的模块**绝对不能**直接替换原厂 `8733bs.ko`。
- 上游 `SUN50IW1P1` 路径面向其他全志板型，仍需要研究其供电控制和内核API；即使编译通过，仍未确认运行时兼容性。
- 原机备份、FEL恢复和实际 SDIO 硬件拓扑未核验。**safe_to_flash = false**。

上游参考：
- https://github.com/hbouhadji/prototype-v851s-port
- https://github.com/catplay-labs/catplay-firmware
- https://github.com/smp79/rtl8733BS_WiFi_linux_v5.15.17-113
