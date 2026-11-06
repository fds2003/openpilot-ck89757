# 21_C3端协同领航方案独立同行评审报告（Peer Review）

> **审计人角色**：资深智驾安全审计专家 / 独立红队（由第三方模型按《20_主提示词》规范执行）
> **审计对象**：`openpilot-ck89757` 仓库 `cp-custo-amap` 分支，Commit `dcd0264`
> **审计输入**：《19_C3端协同领航修改方案深度技术论证与代码审计白皮书》 + 仓库**实际源码逐行核验**（非仅审白皮书 Diff）
> **报告日期**：2026-11-02
> **审计方法**：白皮书声明的每一处关键逻辑，均与 `git show dcd0264` 的真实 Diff 及现网源码交叉验证，并向下追溯至信号源（`carrot_man.py`、`_update_command`、`RadarSpeedEstimator`）。

---

## 一、综合评审结论 (Overall Verdict)

# 🟠 [NEEDS REVISION] —— 存在 Major 级逻辑/安全缺陷，修正前**不得**上实车联调

核心安全方向是正确的（TTC 门禁、盲区和实线阻断、驾驶员扭矩熔断均存在且方向正确），但**实现层有 3 个 Major 缺陷**：

1. **TTC 门禁在"信号缺失"时语义反转**：后车时距信号失效/超时/静止时，`behind_ttc = 99.0` → `rear_conflict = False` → 门禁**放行**。这是典型的 **fail-open**（失效放行）而非 fail-safe（失效阻断），与白皮书 5.1 的"断网绝不失控"结论直接矛盾。
2. **TTC 计算存在量纲混用与"后车未跟踪"盲区**：`main_lb_drel` 为毫米、`lb_vrel` 为 m/s（含 0.5s 滑窗平滑 + 4m/s² 限幅），且该速度只在"本帧有左后距离回传"时才刷新——后车消失/静止时速度**被冻结**在旧值，TTC 会长期虚低（误报）或虚高（漏报）。
3. **`param` 解析无防御 + `overtake_mode` 无限期锁存**：车机任意 UDP 客户端可发 `{"param":"garbage"}` 使 `int()` 抛异常；且该值**没有超时/心跳失效复位**，一旦误设（如 0 激进）将在 7705 断链后继续生效 10s 变道窗口内。

**亮点（必须保留）**：端口 7705/7706 错配修复正确；5510 动态 IP 学习思路正确；Cap'n Proto 追加字段 `@15/@16` **符合 Cap'n Proto 尾插兼容性规范**（维度 5 通过）。

---

## 二、审查发现项矩阵 (Findings Matrix)

| 编号 | 涉及文件与行号 | 严重等级 | 问题现象与机理分析 | 改进建议 |
|:---|:---|:---:|:---|:---|
| **F-01** | `amap_navi.py:295-300`（TTC 计算块） | **Major (Critical)** | `behind_ttc` 默认值 `99.0` 落入 `desire_helper` 的 `0.0 < behind_ttc < 2.5` 判定**之外**，即"无信号=无风险"。当激光雷达掉线、后车未跟踪、车速为 0（`lb_vrel` 不刷新）时，门禁自动解除，系统允许打灯切入。这是 **fail-open**。白皮书 5.1 宣称"断网绝不产生非预期变道"——但该结论只在 7705 指令链路成立，**TTC 走的是独立雷达链路，断链时恰恰放行**。 | 引入**雷达数据新鲜度**位：`rear_conflict = (TTC信号老化 > 1.0s) or (0 < ttc < 门限)`。信号缺失/老化时应按"最保守"处理（等价于 `ttc=0` 或强制 `rear_conflict=True`），即 **fail-safe 关闭**超车放行，宁可不变道。 |
| **F-02** | `amap_navi.py:296-299` + `RadarSpeedEstimator.update` | **Major** | 量纲与语义双重隐患：(a) `main_lb_drel` 单位 **mm**、`lb_vrel` 单位 **m/s**，公式 `(drel/1000)/abs(vrel)` 数值上成立但高度依赖单位不变式，无任何注释/断言；(b) `lb_vrel` 仅在"本帧 `detect_side&1` 且 `lidar_id∈{0,2}` 且回传了左后距离"时经 `leftFrontTarget.update` 刷新，后车静止/丢失时该值**冻结**在最后一次运动值，导致 TTC 长期误判（虚低→频繁误报"盲区有车"，虚高→漏报后车急加速）。 | (a) 将 mm→m 转换与量纲校验集中在单一函数并加 `assert`；(b) 给 `lb_vrel/rb_vrel` 加**过期门控**（如 0.5s 未刷新即视为 None→回到 F-01 的 fail-safe 分支）；(c) 改用**基于距离趋势的 TTC**（`d_rel/收敛速度`）而非对 vrel 求 `abs`，避免滑窗平滑引入的 0.5s 时滞。 |
| **F-03** | `amap_navi.py:993-994`（`_update_command`） | **Major (安全)** | `self.shared_data.overtake_mode = int(json_obj.get("param", 1))` 未做类型与异常防御。7705 是**局域网明文 UDP**，`addr` 来自任意客户端。`param` 为字符串/浮点时 `int()` 抛 `ValueError`，虽被外层 `try/except` 捕获，但异常发生在 `_process_single_packet` 的中段，**其后 `_update_control/_update_sensors` 被跳过**——一次畸形包即可连带冻结雷达盲区数据更新一个周期。且 `overtake_mode` **无复位**：7705 断链后该值无限锁存，激进模式 `1.8s` 持续生效。 | (a) `try: mode=int(...) except: mode=1` 局部容错；(b) 校验 `mode in {0,1,2}`，否则回 1；(c) 加**指令心跳/时间戳**，>3s 无 7705 指令则 `overtake_mode` 复位到默认 1（常规）。 |
| **F-04** | `amap_navi.py:818`（`echo_cmd`，**本次 Diff 未改但同链路**） | **Minor→Major(连带)** | `subprocess.run(json_obj['echo_cmd'], shell=True)` 允许 7705 客户端下发**任意 shell 命令**在 C3 上执行。虽非本次 4 文件改动，但与新增的 7705 监听同属"开放 UDP 写通道"，一旦 7705 被第三方接入即成 **远程命令执行**通道。 | 7705 监听应增加**源 IP 白名单**（仅 `self.shared_data.app_ip`），非白名单源直接丢弃；`echo_cmd` 在生产分支禁用或加静态黑名单。 |
| **F-05** | `amap_navi.py:598` + `1592-1593` | **Minor** | 多车机/多热点场景下 `self.shared_data.app_ip` 是**单一全局变量**，被 5510 探针每帧覆盖。若车载网络同时存在车机 A（活跃）与误入网络的手机热点 B（发 `c3_ping`），`app_ip` 会被 B 抢占，20Hz 遥测被改投到 B，A 端 HUD 断联。 | `app_ip` 按 `clients` 存活状态做**权重选择**（最近活跃/心跳最强者），而非"最后写入即锁定"；或引入 `app_ip` 需 N 帧连续确认才生效的消抖。 |
| **F-06** | `desire_helper.py:936`（`frame % int(2.0/DT_MDL)`） | **Minor** | `DT_MDL` 若不为 0.02 的整数倍关系，`int(2.0/DT_MDL)` 取整会导致播报周期与名义 2s 偏差；且该音频播报**每 2s 一次**对"盲区有车"语义偏频繁，易引发驾驶员听觉疲劳。 | 改为以独立 `audio_timer` 计时（参考已有 `self.lane_change_audio_delay` 范式），与 `frame` 解耦。 |
| **F-07** | `desire_helper.py:923-924`（`getattr(amapNavi,...,99.0)`） | **Minor (亮点+残留)** | 用 `getattr` 兜底 capnp 缺字段是**好习惯**（旧日志回放/旧构建安全），但默认值 `99.0` 与 F-01 的 fail-open 根因同源。`overtakeMode` 默认 1（常规）合理。 | 保留 `getattr` 防御；把 TTC 缺省语义从"99=无风险"改为"99=未知→保守放行关闭"，与 F-01 联动修复。 |
| **F-08** | `process_config.py:144`（`always_run`） | **Minor** | `amap_navi` 置为 `always_run` 使其在 **Offroad 熄火**时仍常驻（`only_onroad` 才会随下电关闭）。对纯通信桥接进程影响有限（仅占用网络/电量），但与白皮书"节能策略"的合规性描述不完全一致。 | 若可接受熄火后停止收车机 ping，可改 `enabled=onroad or check_fleet`；若需熄火后仍能握手，则保留 `always_run` 并在文档中显式标注该功耗决策。 |
| **F-09** | `custom.capnp:74-75`（`@15/@16` 尾插） | **Suggestion (通过)** | **维度 5 结论：合规。** Cap'n Proto 要求新增字段以结构体尾部顺序编号追加、不改动既有字段编号/标识符；本次 `AmapNavi` 保留原 `@0–@14` 不变，新增 `@15/@16`，struct 标识 `@0xaedffd8f31e7b55d` 未变。**旧日志回放**（缺 `@15/@16`）读到的 Python 对象该属性缺省为 0/0.0，而消费端 `getattr(amapNavi,'overtakeMode',1)` 默认 1、TTC 缺省 0.0（注意：capnp 缺省 Int32/Float32 为 0 而非 99.0！见下方质询 E-3）。 | 无需改代码；但需在部署文档声明"capnp 缺省为 0"的语义，避免与 Python 侧 `getattr` 默认 99.0 产生认知割裂（见 F-07/E-3）。 |

---

## 三、针对极端工况的推演与质询 (Edge Case Scenarios)

### E-1 车载 Wi-Fi 掉线 + 雷达后车未跟踪（双重信号缺失）
**系统行为**：`lb_vrel`/`main_lb_drel` 停在最后有效值或置 0 → `behind_ttc=99.0` → `rear_conflict=False`。此时若车机在断链前已下发 `OVERTAKE`（`carrot_lane_change_count` 在 10s 窗口内未归零），`desire_helper` 走 `carrot_lane_change_count>0` 分支，TTC 门禁**不阻断**，仅靠 `side_object_detected`（毫米波盲区 + 实线）兜底。
**质询**：后车是**车侧后方**目标，毫米波 `leadLeft/leadRight` 通常覆盖的是**侧前方**，后车急进可能**不在该雷达视锥内** → 唯一的后车门禁就是这条失效放行的 TTC 通道。**结论：此工况下"后方来车极速逼近仍可盲切"的风险并未被真正封死。**

### E-2 极低车速（<5km/h，蠕行/拥堵）
`lb_vrel` 相对速度被 `RadarSpeedEstimator` 的 4m/s² 限幅 + 0.5s 滑窗强烈平滑，蠕行时 `|lb_vrel|` 常在 0.1 附近抖动；`behind_ttc` 在 `(0, 2.5)` 内频繁越阈，触发 2s 周期的"盲区有车"误报，且 `rear_conflict=True` 长期封锁超车——**功能在低速下基本不可用**。
**质询**：是否需要按 `v_ego` 对 TTC 门限做**低速豁免/门限放大**？

### E-3 capnp 缺省值语义割裂（0 vs 99.0）
旧构建/旧日志回放的 `amapNavi` 对象中，新增字段 capnp 层缺省为 `Int32=0`、`Float32=0.0`。此时 `overtakeMode=0`（被 `desire_helper` 的 `getattr` 读到的是 **capnp 真实值 0 = 激进**，而非 Python 代码里期望的 1）；`lidarBehindVdistTime=0.0` → `0.0 < 0.0` 为 False，门禁同样放行。**即：升级后未重新编 capnp 的场景，行为会静默切到"激进 1.8s + TTC 恒 0"组合**，与"默认常规 2.5s"的文档假设相反。
**质询**：`getattr` 的默认值（1 / 99.0）是否只在**属性完全不存在**时生效？对"属性存在但 capnp 默认 0"的情形无效。需显式区分"未写入"与"写入了 0"。

### E-4 网络风暴 / 7705 广播泛洪
`_headunit_cmd_recv_thread` 对每个 1024B 包调用 `_process_single_packet` → 逐包 `json.loads` + 四个 `_update_*`。若热点误配导致某设备对 7705 高速刷包，该守护线程 CPU 占用飙升（Python GIL 下会挤占 `controlsd` 100Hz 主循环的调度时隙），且每个包都可能经 `echo_cmd` 触发 `subprocess`。**质询**：是否有 7705 的**限速/频控/源白名单**？

### E-5 5510 探针伪造
`_discovery_responder_thread` 对任意含 `b"c3_ping"` 的 256B 报文即回 pong 并把源 IP 锁为 `app_ip`，**无 MAC/无密钥/无来源校验**。局域网内任何设备可抢占 `app_ip`（同 F-05），使遥测改道。属可接受但需文档披露的 **DoS 面**。

---

## 四、各维度专项结论（对应主提示词六维度）

- **维度 1 网络拓扑**：端口矩阵 `车机 listen 7706/5510 + C3 listen 7705/5510 + C3→7706` **无冲突、闭环成立**，修 1.2 的错配是正确动作。主要健壮性缺口在 **app_ip 单变量锁定（F-05）** 与 **7705 无源鉴权（F-04）**。
- **维度 2 多线程/生命周期**：新增两线程均为独立守护线程 + 独立 socket 阻塞 `recvfrom`，**不在 `controlsd` 主循环内**，不会直接阻塞 100Hz 控制；但 7705 泛洪下 Python GIL 存在**间接抢占**风险（E-4）。`SharedData` 的 `clients` 字典有 `lock` 保护；但 `overtake_mode/behind_ttc/app_ip` 为**无锁裸赋值**，读写撕裂为整字写（CPython 下原子）可接受，语义上仍建议纳入同一锁或加注释。`always_run` 的 Offroad 常驻见 F-08。
- **维度 3 TTC 数学**：量纲（mm vs m/s）与平滑时滞是**主要不严密点（F-01/F-02）**；`abs(vrel)` 掩盖了"后车远离"语义（本应远离=安全）；三级门限 1.8/2.5/3.5s 在 120km/h 下分别对应约 51/69/117m 后车间距，**常规/保守符合工程常识，激进 1.8s（≈51m）偏激进但属用户自选项**——前提是 F-01 的 fail-open 必须改为 fail-safe。
- **维度 4 功能安全**：**驾驶员扭矩熔断**（`steering_pressed` → 强制 `LaneChangeState.off` + 播报"领航已退出"）**真实存在且无条件**（`desire_helper.py:1336-1348`），20ms 量级成立，人类控制权优先级正确，**这是本方案最强的一层门禁**。但后车 TTC 这一层在信号缺失时 fail-open（F-01），使"四重刚性矩阵"实为**"三重刚性 + 一重条件刚性"**，与白皮书 3.4 的"任何一重不通过立即封锁"表述不符。
- **维度 5 序列化兼容**：**通过**（F-09）。尾插追加字段、标识符不变，符合 Cap'n Proto 规范；旧日志回放可反序列化（字段缺省 0），消费端 `getattr` 兜底防崩。需补文档披露 capnp 缺省 0 的语义。
- **维度 6 代码质量/边界**：`param` 无防御（F-03）、`echo_cmd` shell=True（F-04）、`frame%int(2.0/DT_MDL)` 取整（F-06）为可修复的低级项；JSON 解析已被 `try/except` 包裹、未崩进程，属可接受。

---

## 五、最终实车落地建议与专家寄语 (Actionable Advice)

1. **修 F-01/F-02 后再上实车**：把"后车 TTC 信号缺失/老化"从 fail-open 改为 fail-safe。这是唯一"必须修改"的安全项——否则"断网不失控"的白皮书承诺在**后方来车**这一主威胁上并不成立。
2. **上实车前给 7705 加源 IP 白名单**：只接受 `self.shared_data.app_ip` 的指令包；非白名单丢弃。同时冻结/禁用 `echo_cmd` 的 `subprocess(shell=True)` 路径，消除远程 shell 通道（F-04）。
3. **联调顺序**：先静态验证端口闭环（Wireshark 抓 7705/7706/5510 三向），确认 5510 握手→`app_ip` 锁定→7706 单播投递链路；再单独验证 7705 `OVERTAKE` 下行→`overtake_mode` 生效；最后在**有后车**的封闭场地验证 TTC 阻断，并**刻意断开雷达/断网**复现 F-01，确认修复后门禁按保守关闭。
4. **capnp 全量重编并做回归**：确保 `overtakeMode/lidarBehindVdistTime` 在 C3 与回放工具两侧均为新版本，避免 E-3 的"缺省 0=激进"静默切换；用一段旧日志回放确认无崩溃（验证维度 5）。
5. **建立 7705 指令与雷达数据的统一心跳老化表**：`overtake_mode`、`behind_ttc`、`app_ip` 三者都应带**时间戳 + 超时复位**，超时按最保守默认（模式=1、TTC=未知→关闭放行、app_ip 保留最后有效值但降频重探针）。这是把"四重门禁"从"条件刚性"升级为真·刚性矩阵的总抓手。

> **专家寄语**：方向（动态组网 + 后车 TTC 门禁 + 驾驶员绝对优先）正确且工程完成度高于预期，`steering_pressed` 熔断与端口错配修复是扎实的安全资产。但当前版本**把最关键的后车威胁门禁做成了 fail-open**，与文档宣称的 ASIL-D"任何一重不通过立即封锁"存在**事实性落差**。请先封堵 F-01/F-03/F-04 三项 Major，再进入实车阶段——**宁可保守错过一次超车，也不要在后车急进时盲切。**

---

## 附：本审计的"证据锚点"（可复核行号）

- `selfdrive/controls/lib/desire_helper.py:920-940`（TTC 门禁实际实现，与白皮书 4.4 一致）
- `selfdrive/controls/lib/desire_helper.py:1336-1348`（`steering_pressed` 无条件熔断，验证维度 4 最强层）
- `selfdrive/carrot/amap_navi.py:295-300`（TTC 计算 + `behind_ttc` 默认 99.0，F-01/F-02 根因）
- `selfdrive/carrot/amap_navi.py:584-635`（新增 5510 探针 / 7705 指令两守护线程，维度 2）
- `selfdrive/carrot/amap_navi.py:818`（`echo_cmd` shell=True，F-04）
- `selfdrive/carrot/amap_navi.py:993-994`（`param` 无防御 + `overtake_mode` 无锁存复位，F-03）
- `cereal/custom.capnp:58-76`（`AmapNavi` 尾插 `@15/@16`，维度 5 通过）
- `system/manager/process_config.py:144`（`amap_navi` → `always_run`，F-08）
