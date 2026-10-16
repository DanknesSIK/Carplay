# M6 v23 — 使用真实公开 DTB 进行解析器兼容性测试

本阶段与 v16–v22 最大的区别：`m6-public-real-dtb-v23.yml` 会从公开研究仓库的**固定 Git 提交**读取两份真实设备树（不是合成 DTB），核对原始 Git blob SHA-1，再调用 v20 FDT 解析器读取 root `model`、`compatible`、MMC/WLAN 等有限结构。不会下载你的 M6 原厂镜像，也不会访问你的盒子。

## 公开样本和核验锁

来源仓库：https://github.com/hbouhadji/prototype-v851s-port

固定 Git commit：`05d8262010922cefe05592238e8f60f98dab4613`

| 文件 | Git blob SHA-1 |
|---|---|
| `analyse-v851s/stock-full.dtb` | `eb093bd73c02202ea5b11cbe1e5f1f7f90cd80e3` |
| `analyse-v851s/stock-small.dtb` | `1d6fb9a403f746df362977e6836201545dd705af` |

GitHub Actions [第 38869022595 次运行](https://github.com/DanknesSIK/Carplay/actions/runs/38869022595) 成功：两份公共真实 DTB 均通过哈希和 FDT 解析；它们的 model 都是 `sun8iw21`，根节点兼容标识并不完全相同。此结果只能证明解析器支持这些**公开参考板**文件，不能证明你的 M6 实机兼容。工作流仅上传 JSON 元数据，不上传原始二进制。

## 与用户原厂设备的关系

- M6 升级包曾显示 board `v851s-lybox_rtl8`、Linux 4.9.191。
- 用户先前报告设备运行版本 `25060316.2807.2`，已取得的升级包为 `26041414.2807.2`，版本不一致。
- 当前仍未取得该 M6 的可信设备树、完整原厂分区备份、GPIO/稳压器引脚或恢复机制。
- 外部文献中的 V851SE DTB **不是 M6 固件、不能被安装/刷写/复用 GPIO**。
- 即使所有自动测试通过，`M6_DTB_obtained=false`、`safe_to_flash=false`、`driver_can_be_loaded=false`。

## 增强的拒绝误报机制

修复了 v20 的输入统计问题：原先单个目录/ZIP 超过扫描文件上限时，有可能直接跳过余下样本却输出“没有 DTB”；现在在 JSON 中给出 `input_limit_reached=true`，`status=incomplete-some-inputs-skipped-or-limited`，返回非零退出码，避免把**部分扫描**误判为**完整无发现**。

新增 3 项限制测试覆盖：目录超限、ZIP 超限、恰好达到上限时不误报。此前上传的原厂升级镜像不在 GitHub 中，不能通过 CI 直接获取真实 M6 设备树。

## 额外公开线索（不足以证明可用）

俄语拆机讨论中将部分 `2807` 系列产品对应到 `Z2-V03` 和 RTL8733BS，但该商品与用户当前 M6 的电路板、固件版本和闪存布局均未比对，**不能直接套用**。

- https://www.drive2.ru/b/655924107983990956/

不要把固件升级页 `version.json` 当作当前真机完整备份。只有目标板完整原始分区镜像、厂家经过核对的板级 DTB、或得到授权的只读实机数据，才能推进板级认证。
