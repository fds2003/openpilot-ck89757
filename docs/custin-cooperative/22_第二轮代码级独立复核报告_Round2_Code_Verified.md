# 22 C3 端协同领航修改方案 · 第二轮代码级独立复核报告

> **受审工程**：`openpilot-ck89757`（分支 `cp-custo-amap`，基线 `24b7ff2`，HEAD `dcd0264`）  
> **对照工程**：`AmapNavi-Reborn`（车机端 Kotlin 真实源码，本机可读）  
> **受审文档**：`19_...白皮书.md`（设计与 Diff）、`20_...Peer_Review_Master_Prompt.md`（评审维度）  
> **前序报告**：`21_第三方专家独立审计结论与整改建议_Code_Verified_Peer_Review.md`  
> **复核方式**：白皮书 Diff ↔ C3 真实源码 ↔ 车机真实源码，三方逐行比对（非文档评审）  
> **取证说明**：本机 Windows 环境下 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`），**未执行任何构建、测试或运行命令**；全部结论均来自源码逐行阅读，file:line 可在本机直接复核  
> **审计日期**：2026-11-02  
> **综合判定**：🔴 **[FAIL] — 存在严重致命缺陷，严禁上实车**

---

## 一、综合评审结论

🔴 **`[FAIL]`**

本轮复核独立复现了 21 号报告的核心结论，并在此基础上**新增 10 项发现、加严 3 项判定**。最关键的增量结论是：

1. **本次修改引入的"双实例"不只是端口竞争，而是会触发 msgq 的单一发布者约束（`MultiplePublishersError`），构成启动期崩溃竞态**：`carrot_man`（`always_run`）内部 `CarrotMan.__init__` 第一行就构造 `AmapNaviServ()`（`carrot_man.py:191`），而 `AmapNaviServ.__init__` 末尾 `start_navi_comm()` 会启动全部 UDP 线程、并在 `amap_navi.py:269` 创建 `PubMaster(['amapNavi'])`。本次改动把 `amap_navi` 也设为 `always_run`（`process_config.py:144`），于是**两个进程同时发布同一个 cereal service `amapNavi`**。`cereal/messaging/__init__.py:3` 显式导入 `MultiplePublishersError`——后启动者将无法绑定并抛错。谁先启动、谁崩，取决于 manager 的启动顺序，属于**不可复现的启动期故障**。
2. **本轮修改的安全门禁（后车 TTC 阻断）在实际链路上几乎不存在**：车机只下发 `LANECHANGE / SPEED_LIMIT / CANCEL_LANE_CHANGE`（`RelayEngine.kt:44-56,97`），从不发 `OVERTAKE`，所以 `desire_helper.py:521-524` 的 `carrot_lane_change_count = int(LANE_CHANGE_TIME_MAX*2.0/DT_MDL)`（400 帧 = 20 s）永不被设置；`LANECHANGE` 只给 4 帧（0.2 s）窗口。**新加的门禁只在命令后 200 ms 内生效**，其余时间完全不存在。
3. **门禁的输入本身不可信**：`lb_vrel`（左后车相对速度、即 TTC 的分母）由**左前方**的估计器实例产出（`amap_navi.py:1136` 用 `self.leftFrontTarget.update(...)`），而 `self.leftBehindTarget` 在 `amap_navi.py:213` 建好后**从未被使用**；同一估计器实例被"前 +5000mm / 后 −2500mm"两个距离交替喂入，在 `max_acc=4.0 m/s²` 限幅下速度估计必然饱和失真。
4. **新线程带来一处"静默死亡"缺陷**：`_discovery_responder_thread` 写入的 client 记录只有 `last_time` 键（`amap_navi.py:598`），而 `_clean_clients_thread` 用 `info["last_seen"]` 索引（`amap_navi.py:1514`）。**第一次收到 `c3_ping` 后，清理线程立即 `KeyError` 并整体死亡**（该线程无 try/except），客户端清理、`ext_state`、worker 退出标记全部永久失效。

结论不变且更明确：**这份修改不是"待优化"，而是功能区基本未接通的半成品**，且其安全论证（白皮书 §5.1/5.2/5.3）与代码行为系统性不符。

---

## 二、六大维度符合性速览

| 维度（按文档 20） | 判定 | 关键发现 |
| :--- | :--- | :--- |
| 1 网络拓扑与通信契约正确性 | 🔴 FAIL | N-01 / N-02 / 确认 C-02、C-03、N-09 |
| 2 多线程并发与进程生命周期 | 🔴 FAIL | **N-01（双发布者竞态）**、N-04（线程死亡）、N-05（并发无锁）、N-10 |
| 3 变道控制与 TTC 数学严密性 | 🔴 FAIL | **N-02（门禁作用域 0.2 s）**、**N-03（分母估计器错位）**、确认 C-05 |
| 4 功能安全、容灾与极端工况 | 🔴 FAIL | 确认 C-06 / C-07 / C-08，N-07（无时效校验）、N-08 |
| 5 Cereal / Cap'n Proto 兼容性 | 🟡 PASS（附强制前提） | 确认 M-06（结构体追加合规）＋ **N-06（生成代码未重生成）** |
| 6 代码质量、异常处理与边界 | 🟠 NEEDS REVISION | N-04 / N-05 / N-10、确认 M-03 |

仅"维度 5 的 schema 追加本身"合规；其余五个维度均存在阻断级缺陷。

---

## 三、审查发现项矩阵

> 路径前缀：`C3:` = `E:/code/openpilot-ck89757/`；`HU:` = `E:/汽车/库斯途升级破解/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/`  
> **N-xx** = 本轮新增发现；**✔C-xx** = 本轮独立复现并与 21 号报告一致

### 3.1 本轮新增发现（10 项）

| 编号 | 文件与行号 | 等级 | 问题现象与机理分析 | 改进建议 |
| :--- | :--- | :--- | :--- | :--- |
| **N-01** | `C3:selfdrive/carrot/carrot_man.py:191,340-345`；`C3:selfdrive/carrot/amap_navi.py:269,574-583`；`C3:system/manager/process_config.py:143-144`；`C3:cereal/messaging/__init__.py:3,239-245` | **Critical** | **双发布者 + 启动期崩溃竞态（比 21 的 C-01 更底层的机理）**。`carrot_man.py:191` 在 `CarrotMan.__init__` 第一行就 `self.amap_navi = AmapNaviServ()`，而 `AmapNaviServ.__init__` 末尾即 `start_navi_comm()`，其中 `amap_navi.py:269` 建 `PubMaster(['amapNavi'])`、`574-583` 启动 6 个 UDP 线程。本次改动让 `amap_navi` 与 `carrot_man` 都 `always_run`，因此：① 两个进程都尝试 `pub_sock('amapNavi')`，msgq 只允许单一 publisher，后到者抛 `MultiplePublishersError`（该异常类型在该文件第 3 行被显式导入，是库的既有语义）；② 二者都用 `SO_REUSEADDR` 绑 `5510/7705/4211/4213`，UDP 单播包内核只投递给其中一个 socket；③ `carrot_man.py:340-345` 读的是**本进程** `self.amap_navi.shared_data`，跨进程不共享。表现为：**启动顺序决定"谁崩"或"谁收包"，导致"有时能变道、有时不能"的不可复现故障**；若 `carrot_man` 崩，则 `carrotMan` service 整体缺失，`desire_helper` 读到全零默认值，全套 carrot 功能静默失效 | 二选一冻结进程模型：**(a)** 撤回 `process_config.py:144`，由 `carrot_man` 内嵌实例独占全部 UDP 与 `amapNavi` 发布者；**(b)** 真双进程：删除 `carrot_man.py:191` 的内嵌构造，指令与状态一律走 cereal（新增 `amapNaviCmd` 上行 service）。**禁止两进程同时持有同一 service 的 PubMaster** |
| **N-02** | `C3:selfdrive/controls/lib/desire_helper.py:505-524,919-941`；`HU:data/relay/RelayEngine.kt:44-56,97`；`HU:data/udp/CarrotUdpClient.kt:107-121` | **Critical** | **安全门禁的作用域只有 200 ms，20 s 窗口永不可达**。门禁整段写在 `if self.carrot_lane_change_count > 0:` 内。该计数仅由两条路径赋值：`OVERTAKE` → `int(10*2.0/0.05)=400` 帧（20 s）；其它命令（含 `LANECHANGE`）→ `int(0.2/0.05)=4` 帧（0.2 s）。而车机侧 `cmd` 只可能是 `LANECHANGE / SPEED_LIMIT / CANCEL_LANE_CHANGE`（`RelayEngine.kt:44-46`），**`OVERTAKE` 分支在真实链路上不可达**。结论：新增的 TTC 阻断在每次变道命令后仅存活 4 帧（200 ms），之后自动消失——而一次线控变道需要数秒 | 门禁必须挂在**变道状态机本身**（off/pre/starting/finishing 全阶段），而不是挂在某个会自然衰减的计数器上；`overtake` 语义应由独立的持久状态承载 |
| **N-03** | `C3:selfdrive/carrot/amap_navi.py:213,1136`（对比 1174 右侧正确写法） | **Critical** | **TTC 分母用错了估计器实例**。`self.shared_data.lb_vrel = self.leftFrontTarget.update(lb_dreltmp, dist_timems)`（1136 行）——左后车相对速度由**左前方**估计器计算；`self.leftBehindTarget`（213 行创建）全文件未被引用。且 `lidar_id == 0` 的同一包会连续用 `lf_dreltmp`（前方为正，如 +5000）与 `lb_dreltmp`（后方为负，如 −2500）喂入同一实例，`RadarSpeedEstimator` 的 `allowed_dv = 4.0*dt`（`amap_navi.py:82`）限幅下输出恒定饱和，`lb_vrel` 与物理量无关。右侧对称代码（1174 行）用的是 `rightBehindTarget`，**左右不一致，证明这是笔误而非设计** | 改为 `self.leftBehindTarget.update(...)`；并把"一个估计器只服务一个目标"写成不变量（估算器内部持有 `last_dist_m` 状态，不能复用） |
| **N-04** | `C3:selfdrive/carrot/amap_navi.py:598`（写 `last_time`）vs `1509-1540`（读 `info["last_seen"]`） | **Critical** | **新线程导致清理线程静默死亡**。`_discovery_responder_thread` 插入的 client 字典只有 `last_time/device/device_type/alive`；`_clean_clients_thread` 第 1514 行 `active_clients = {ip: info for ip, info in self.clients.items() if now - info["last_seen"] < 1.0}` 用中括号索引 → **首个 `c3_ping` 之后立刻 `KeyError`**。该线程体无 `try/except`，异常抛出后线程永久退出；`with lock` 会正常释放（不会死锁），但从此：客户端永不过期、`self.shared_data.ext_state` 冻结、`client_active[ip]=False` 标记不再下发、每客户端 worker 线程永不退出（线程泄漏）。`manager` 只监控**进程**存活，看不到线程死亡，进程仍"健康" | 统一键名（都用 `last_seen`）；`_clean_clients_thread` 整体包 `try/except` 并打印；client 记录用**同一个工厂函数**创建，避免结构漂移 |
| **N-05** | `C3:selfdrive/carrot/amap_navi.py:983-995,937-940,586-617,937-1010` | **Major** | **新线程把"单写者"变成"多写者"，且共用传感器解析器**。`_process_single_packet` 现在被 3 类调用者并发调用：每客户端 `_client_worker` 线程、`_udp_recv_thread`（4211）、新增的 `_headunit_cmd_recv_thread`（7705）。`_update_sensors` 对 `self.shared_data.main_*_drel`、`RadarSpeedEstimator` 内部状态、`self.clients[ip]` 做**无锁或整条覆盖**写；7705 上的 `{"cmd":...}` 包会一路走到 `_update_sensors` 的 `else`（其它设备）分支，把 `self.clients[车机IP]` 整条覆盖为 `{port,last_seen,device}`。另外 `_update_command` 的 `if "param" in json_obj: self.shared_data.overtake_mode = int(json_obj.get("param", 1))`（993 行）：① 与 `cmd` 无关——**任何**带 `param` 键的包头（包括第三方设备配置包）都能静默改写安全阈值；② 无白名单，`param` 非数字时 `int()` 抛错，被 `_process_single_packet` 的 `try` 吞掉，导致**同包的 blinker/传感器字段全部丢失** | 为每类报文设独立入口函数（cmd 包不要进 `_update_sensors`）；`overtake_mode` 仅在 `cmd=="OVERTAKE"` 时更新且校验 `param ∈ {0,1,2}`；共享状态统一加锁或改为"单写者线程 + 队列" |
| **N-06** | `C3:cereal/custom.capnp:76-77`；`C3:cereal/gen/cpp/custom.capnp.h:63-79` | **Major** | **生成代码未重新生成（维度 5 的强制前提）**。`AmapNavi` 在 `.capnp` 中已追加 `@15`/`@16`，但已提交的 C++ 生成头仍为 `CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d, 8, 0)`——**8 个 data word**，与改动前 15 字段（14×Int32 + 1×Bool = 15 slot）一致；新增 2 个 4 字节字段后应为 **9 word**。说明生成物是旧的。若构建流程未强制 `capnpc` 重跑，C++ 侧消费方（日志工具/回放/任何读 `amapNavi` 的 C++ 代码）会按旧布局解码，读到错位或直接缺符号 | 提交前强制重新生成（capnp 编译 + scons），把 `cereal/gen/cpp/*.capnp.h/.c++` 一并纳入本次改动；CI 加"生成物与 schema 一致性"检查 |
| **N-07** | `C3:selfdrive/controls/lib/desire_helper.py:428-430,923-924`；`C3:cereal/messaging/__init__.py:184-190`；`C3:selfdrive/carrot/amap_navi.py:270,304-305` | **Major** | **消费端无时效/有效性校验，安全输入可"僵死生效"**。`amapNavi = self.sm['amapNavi']` 每帧直读，不看 `self.sm.updated[...]`、不看 `self.sm.valid['amapNavi']`、不看 `recv_time` 时效。而 `public_amap_navi` 无条件 `msg.valid = True`（`amap_navi.py:270`），使 `valid` 位与"雷达是否真的在工作"完全解耦。后果：`amap_navi` 崩溃或雷达断流后，**最后一个 `lidarBehindVdistTime` 与 `overtakeMode` 会无限期被继续消费**。另一半风险来自 `SubMaster.__init__`：`self.data[s] = new_message(s).as_reader()`（`cereal/messaging/__init__.py:184`）——**首帧是全零结构**，此时 `overtakeMode = 0` 恰好等于"激进 1.8 s"，与白皮书声称的默认 1（常规）相反 | `desire_helper` 增加超时判定（如 `now - recv_time > 0.5 s` → 视为无效并阻断）；`valid` 位改为反映真实健康度（雷达断流即置 False）；`overtakeMode` 用显式哨兵（0 表示"未设置"→ 取常规），禁用 0 作为激进编码 |
| **N-08** | `C3:selfdrive/controls/lib/desire_helper.py:934-936,1090-1100` | **Minor** | **新门禁顺手掐掉了原有的"盲区受阻"上报通道**。冲突分支里 `auto_lane_change_trigger_no_bsd = False`；该变量在下游 `bsd block` 分支（约 1092 行）用于置 `self.atc_bsd = blinker_state`，供 `carrot_man` 做加减速协同。后车逼近阻断时该标志不再置位，**纵向协同/提示链路丢失**，驾驶员只听到一次"盲区有车"语音 | 为"后车逼近"定义独立标志并贯通到 `carrotMan`，不要复用 bsd 通道 |
| **N-09** | `C3:selfdrive/carrot/amap_navi.py:1541-1560,1590-1596`；`HU:data/udp/CarrotTelemetryParser.kt:33-40`；`19:§2.3` | **Minor** | **遥测口径与白皮书不符，新增 TTC 未进 UDP**。① 白皮书称"20 Hz 推送 81 项遥测"，实际 UDP 推送在 `navi_broadcast_info`，`Ratekeeper(10)`（`amap_navi.py:1546` 附近）→ **10 Hz**；20 Hz 的 `_data_deal_thread` 只做雷达处理与 cereal 发布。② 同一 `navi_dat` 连发三份：`(ip, port=4210)`、`(ip, 7706)`、`(app_ip, 7706)`，弱网下带宽 ×3。③ **新算出的 TTC 只写进 cereal，没有写进 UDP JSON**，而车机解析器读的是 `lidar_behind_vdist_time`（`CarrotTelemetryParser.kt:39`）→ HUD 的后车时距恒为 0。④ C3 发 `break_press`（拼写），车机读 `brake_press` | 统一为"一份 schema + 一份 fixture + 两端往返单测"；TTC 同时进 cereal 与 UDP；修正拼写 |
| **N-10** | `C3:selfdrive/carrot/amap_navi.py:586-617` | **Suggestion** | 探针响应的三个小隐患：① 回包固定发往 `(ip, 5510)`，而非报文源端口 `addr[1]`（当前车机发现模块恰好 `bind(5510)` 才侥幸可用，一旦换实现即失效）；② 判据为 `b"c3_ping" in data` 的**子串包含**，任意包含该子串的载荷都会触发，并可借此劫持 `app_ip`（遥测单播外泄）；③ `app_ip` 无 TTL、无源校验，DHCP 变更后长期指向旧地址 | 回 `addr[1]`、改为 JSON schema 校验、`app_ip` 加租约与源白名单 |

### 3.2 对 21 号报告的独立复现结果

| 21 号编号 | 本轮复核 | 证据补充与判定调整 |
| :--- | :--- | :--- |
| C-01 双实例 | ✔ 复现并**加严** | 补充 `MultiplePublishersError` 崩溃竞态机制（见 N-01），严重度不变但可观测性/可诊断性大幅提升 |
| C-02 端口契约反转 | ✔ 复现 | 双向独立取证：`CarrotUdpClient.kt:30-32`（`PORT_TELEMETRY=7705` 本地 bind 收、`PORT_CONTROL=7706` 发）+ `CarrotTelemetryParser.kt:6` 注释"C3 遥测 JSON (Port 7705)"。C3 侧 `amap_navi.py:200-201` 仍是 `navi_port=7706` 发、`navi_remote_port=7705` 收 → **收发均反向** |
| C-03 发现握手三重断裂 | ✔ 复现 | 车机：`bind(5510)`，向 `255.255.255.255:4210` 发 `{"cmd":"discover","port":5510}`，要求 `resp=="c3_pong"` 且读 `auth`/`device_id`（`UdpDeviceDiscovery.kt:34-36,71-92,116-127`）。C3：5510 上只认 `b"c3_ping"`，回包字段为 `device/status/ip/version`。**目的端口、探针内容、响应 schema 三处全错** |
| C-04 上行字段错配 | ✔ 复现 | 车机实际发出：`cmd / direction / index / v_cruise / blinker / timestamp`（`CarrotUdpClient.kt:110-117`）。C3 读 `arg`（得 None → `desire_helper.py:508` 恒判 RIGHT）、读 `param`（车机从不发）、判 `cmd=="OVERTAKE"`（永假） |
| C-05 TTC 五重 fail-open | ✔ 复现 | ①`ttc=99.0` 无数据放行；②capnp 零默认 + `getattr` 兜底无效；③`main_lb_drel` 为负（后方为负，见 `amap_navi.py:1364-1382` docstring"后方为负"及 1120 行 `lb_dreltmp >= -1000` 语义）→ TTC 为负 → `0.0 < ttc` 恒假；④`vrel ≥ -0.1`（并排车）跳过；⑤`if lb ... elif rb` 不分方向。**另加 N-02（作用域 0.2 s）与 N-03（分母估计器错位）** |
| C-06 接管声明与代码不符 | ✔ 复现 | `desire_helper.py:1336-1338`：`steering_pressed = steeringPressed and ((torque<0 and LEFT) or (torque>0 and RIGHT))` —— 仅"反向打盘"成立，无 1.2 Nm 阈值（CAN 布尔），`lane_change_audio(4)` 那行被注释，语音要等 `atc_cancel_delay = int(2.0/DT_MDL)` 即 2 s；更新周期 20 Hz（`DT_MDL=0.05`，50 ms），非白皮书所称 20 ms |
| C-07 断网容灾不成立 | ✔ 复现 | `carrot_lane_change_count` 每帧 `max(0,c-1)`（`desire_helper.py:431`）；归零后走 `else` 分支即常规自主变道逻辑，**不是**"单车道居中" |
| C-08 变道中途不复检 TTC | ✔ 复现 | `laneChangeStarting` 阶段只判断 `lane_change_prob < 0.02 and ll_prob < 0.01` 转 `Finishing`（`desire_helper.py:1213` 附近），TTC 无任何作用点 |
| M-03 遥测字段不对齐 | ✔ 复现并**细化** | 补充"新 TTC 未进入 UDP"与 `break_press` 拼写（见 N-09） |
| M-06 capnp 追加合规 | ✔ 复现（判定附前提） | 结构与 ordinal 合规；但生成物未同步（N-06），**前提不成立时不能视为 PASS** |
| M-07 `carState` 未订阅 | ✔ 复现 | `amap_navi.py:190`：`SubMaster(['modelV2','selfdriveState','radarState','carrotMan'])` 无 `carState`；`update_navi_carstate` 仅在 `carrot_man` 内被调用 → 独立进程里 `shared_data.carState` 恒 False，`make_navi_message` 的整车状态段整体跳过 |

---

## 四、三条致命链路（机理串联）

### 链路 A：进程/发布者竞态（N-01）

```
manager 启动 carrot_man (always_run)           manager 启动 amap_navi (always_run, 本次改动)
        │                                              │
   CarrotMan.__init__                            AmapNaviServ.__init__
   → self.amap_navi = AmapNaviServ()  ─┐         ┌─→ PubMaster(['amapNavi'])   ← 同一 service
                                       ├─ 都创建 ─┤
   → AmapNaviServ.__init__            ─┘         └─→ 6 个 UDP 线程：bind 5510/7705/4211/4213
        │                                              │
        └──────────► 谁后到 pub_sock → MultiplePublishersError → 进程崩 → manager 重启 → 再竞争
                       若崩的是 carrot_man ⇒ carrotMan service 缺失 ⇒ desire_helper 全零输入
                       若崩的是 amap_navi ⇒ 7705 指令进不来（或进到另一进程，carrot_man 看不到）
```

### 链路 B：安全门禁的空转（N-02 + C-04 + C-05）

```
车机点"变道" → sendControlCommand("LANECHANGE", direction=int, index, v_cruise)
      │  （无 arg、无 param、无 OVERTAKE）
      ▼
C3 amap_navi 收包（且可能收到另一个实例的 socket 上）
      │  remote_cmd="LANECHANGE", remote_arg=None
      ▼
carrot_man → carrotMan.carrotCmd="LANECHANGE", carrotArg=None
      ▼
desire_helper:508  carrotArg=="LEFT"? False → 恒 BLINKER_RIGHT（方向反）
desire_helper:521  carrot_lane_change_count = 4 帧（0.2 s）
      ▼
919 行 if count>0：0.2 s 内读 TTC
      · overtakeMode: capnp 零默认 0 → 激进 1.8 s（首帧/进程崩溃时）
      · behind_ttc  : lb_vrel 由左前估计器算出（不可信）→ 且 lb_drel 为负 → TTC 为负
      · 0.0 < 负值 → rear_conflict = False
      ▼
0.2 s 后 count 归零 → 门禁整段消失 → 回到原逻辑（无后车校验）
```

### 链路 C：线程死亡（N-04）

```
车机 5510 广播 discover ──✗(发往 4210，C3 无人监听)  ← C-03
   （若换成 c3_ping 命中 5510）
        ▼
_discovery_responder_thread → self.clients[ip] = {"last_time":...,"device":"navi"}
        ▼
_clean_clients_thread 下一轮（0.2 s 内）
   active_clients = {ip: info ... if now - info["last_seen"] < 1.0}   ← KeyError
        ▼
   线程整体退出（无 try/except，无重启）→ 客户端永不过期 / ext_state 冻结 / worker 泄漏
```

---

## 五、极端工况推演

1. **启动期（最易触发，也最易被误判为"偶发"）**  
   manager 并发拉起两进程，谁拿到 `amapNavi` 发布者取决于调度。冷启动 10 次可能出现 2~3 种行为：能变道 / 不能变道 / carrot 功能全失效。**这不是玄学，是 N-01 的必然后果**。诊断方法：`ls /dev/shm` 与 manager 日志里是否出现 `MultiplePublishersError`，以及 `journalctl -u manager` 里 carrot_man 的重启计数。

2. **高速 120 km/h，后车 140 km/h 逼近（本应被拦截的核心场景）**  
   30 s 内：`carrot_lane_change_count` 已归零 → TTC 门禁不存在（N-02）；即便命令刚下发 200 ms 内命中门禁，`lb_drel` 为负 → `behind_ttc < 0` → `0.0 < behind_ttc` 为假 → 放行（C-05③）；即使符号被修好，分母来自饱和的错位估计器（N-03）→ 数值不可信。**三层缺陷叠加，该场景 100% 漏检。**

3. **并排加塞（20 km/h 市区拥堵）**  
   后车与己车同速、间距 3 m：`lb_vrel ≈ 0`，`vrel < -0.1` 不成立 → `ttc = 99.0` → 放行；`side_object_detected` 若因动态盲区 `dynamicBlindRange` 把 xrel 判为超宽而屏蔽（`amap_navi.py:449-460` 的 `lb_blind_mask`），盲区门禁也同时失效 → 直接切入并行车辆。**TTC 对"零相对速度、极小间距"无定义，而这是最高频的危险场景。**

4. **雷达单帧跳变 / 目标短暂越过**  
   `main_lb_drel` 瞬时为 −5000 mm，`if ... and self.shared_data.main_lb_drel` 对非零值恒真 → `ttc` 为负 → 放行。门禁对异常值没有任何有效性/连续性校验（`lbDrelValid` 只在发布端置位，消费端从不读）。

5. **车机断电 / 高德闪退 / Wi-Fi 断开**  
   无心跳超时机制；`carrot_lane_change_count` 自然衰减，期间沿用最后一次的 `overtakeMode` 与 `lane_change_available`；归零后进入常规自主变道分支。**白皮书 §5.1"绝不失控变道"不成立**（C-07）。若此刻 `amapNavi` 发布者恰好是已崩溃进程，`behind_ttc` 会僵死在最后一次值（N-07）。

6. **同热点内他人设备/恶意注入**  
   任意设备向 C3:7705 发 `{"cmd":"LANECHANGE","index":N}` → 指令注入；发含 `c3_ping` 子串的包 → 劫持 `app_ip`，遥测单播外泄；发 `{"param":3}` → 静默改写安全阈值；发 `{"param":"LEFT"}` → `int()` 抛错被吞，**同包传感器字段全部丢弃**（N-05）。当前无源认证、无序号单调校验、无白名单。

---

## 六、最小整改顺序（不可颠倒）

> 修复顺序错了会互相掩盖：先修门禁 → 被进程竞态掩盖；先修端口 → 被字段错配掩盖。

1. **冻结进程模型（阻断 N-01 / C-01 / M-07）**  
   推荐方案 (a)：撤回 `process_config.py:144`，由 `carrot_man` 内嵌实例独占。收益：一并解决双发布者竞态、UDP 双 bind、`carState` 缺失、跨进程共享断裂。若坚持双进程，则必须删除 `carrot_man.py:191` 的内嵌构造并新增 cereal 上行通道。
2. **冻结通信契约（阻断 C-02 / C-03 / C-04 / N-09）**  
   以两端真实代码反向生成唯一契约表（端口 × 方向 × 字段名 × 单位 × 枚举），两端按表改；先跑三段环回：`discover→pong`、`遥测→HUD`、`指令→carrotMan→desire`。**在契约表冻结前禁止实车联调。**
3. **修线程安全与生命周期（阻断 N-04 / N-05 / N-10）**  
   client 记录统一键名与工厂函数；`_clean_clients_thread` 加 `try/except`；cmd 包走独立解析函数；`overtake_mode` 仅由 `cmd=="OVERTAKE"` 更新并做 `{0,1,2}` 白名单。
4. **重做 TTC 门禁（阻断 N-02 / N-03 / N-07 / C-05 / C-08）**  
   参考实现骨架（伪代码）：

```python
# 1) 方向先行：只允许"目标侧"的后方雷达参与
side_blind  = amapNavi.leftBlind  if self.carrot_blinker_state == BLINKER_LEFT else amapNavi.rightBlind
drel_valid  = amapNavi.lbDrelValid if self.carrot_blinker_state == BLINKER_LEFT else amapNavi.rbDrelValid
drel_m      = abs(amapNavi.lbDrel) / 100.0      # 与发布端单位对齐后再除，严禁盲目 /1000
vrel_mps    = lb_vrel if LEFT else rb_vrel      # 发布端必须改用 leftBehindTarget/rightBehindTarget

# 2) fail-safe：无效 / 缺失 / 时效超限 / 非正值 一律阻断
fresh      = (time.monotonic() - self.sm.recv_time['amapNavi']) < 0.5
mode       = amapNavi.overtakeMode if amapNavi.overtakeMode in (0, 1, 2) else 1
thr        = {0: 1.8, 1: 2.5, 2: 3.5}[mode]
ttc        = drel_m / max(-vrel_mps, 0.1) if (drel_valid and fresh and vrel_mps < 0) else 0.0
rear_block = not (ttc > thr)                    # 0 / 负 / NaN / 失效 全部 → 阻断

# 3) 作用域：绑定变道状态机全阶段，而不是会衰减的计数器
if rear_block and self.lane_change_state != LaneChangeState.off:
    self.lane_change_state = LaneChangeState.off     # 含 starting 阶段主动中止
    auto_lane_change_trigger = auto_lane_change_trigger_no_bsd = False
    self.lane_change_audio(True, 6, 0)               # 并为"后车逼近"新增独立语音
```

5. **补生成物与实证（N-06 + 白皮书 §5 重写）**  
   重新生成 capnp 产物并纳入本次提交；`cereal/messaging/__init__.py` 首帧零默认必须显式处理。白皮书 §5.1/5.2/5.3 三段容灾必须逐条给出对应代码行号与实测数据（尤其是接管端到端延迟），否则不能作为功能安全证据。

---

## 七、最终实车落地建议

1. **先验证"进程模型唯一性"，再碰任何功能**：上车前用 `ps | grep -E 'carrot_man|amap_navi'` 与 `ss -ulnp | grep -E '5510|7705|7706|4211|4213'` 确认**每个端口只有一个 owner**；确认 manager 日志无 `MultiplePublishersError`。这一步不过，后面所有现象都是噪声。
2. **联调必须打桩、分段验证、录 pcap**：`discover→pong` → `遥测→HUD`（先只验 3 个字段）→ `指令→carrotMan.carrotCmd→desire.trigger_name`。每段用 `ShowDebugLog` 打印真实值，禁止端到端一把梭；全程在封闭热点下抓 UDP 包。
3. **台架注入测试（上车前必须做完）**：雷达断流 / 负距离 / 并排车 / 消息缺失 / 车机断电 / 畸形 `param` 六类故障注入，验证"无数据即阻断"而非"无数据即放行"，并确认每类故障都有可见告警（日志 + HUD + 语音）。
4. **把驾驶员接管作为唯一"最高优先级"重新实测**：当前实现只对"反向打盘"生效、无扭矩阈值、语音延迟 2 s。建议改为纯 `steeringPressed` 同帧清 `desire`，并实测端到端延迟（预期 50 ms 量级，而非白皮书声称的 20 ms）。
5. **把车载热点当不可信网络**：`7705` 指令加源 IP 白名单 + `index` 单调校验 + `param` 白名单；`app_ip` 加租约。否则任何同热点设备都能诱发非预期转向。

---

## 八、附：文档不实/待修陈述清单

| 文档位置 | 声称 | 代码事实 |
| :--- | :--- | :--- |
| `19:§1.1` | 注释掉即"完全不会拉起进程、C3 无监听套接字、静默死亡" | `carrot_man.py:191` 内嵌 `AmapNaviServ()` 一直在监听；取消注释是制造双实例 |
| `19:§1.2`、`20:维度1` | 车机 `PORT_TELEMETRY=7706`、`PORT_CONTROL=7705` | 真实相反：收遥测 7705、发控制 7706 |
| `19:§1.1` | manager "3 秒内看门狗自愈" | manager 只监控进程；线程死亡（N-04）与 bind 失败静默 return 均不可见 |
| `19:§2.2`、`§2.3` | 20 Hz 推送 81 项遥测 | UDP 推送为 10 Hz；TTC 未进 UDP；字段名与车机解析器不符 |
| `19:§3.1` | 双向握手自愈状态机已实现 | 端口/探针/响应三处不匹配，`app_ip` 恒为 None |
| `19:§3.2` | "seq 严格单调递增，C3 自动丢弃旧包" | C3 无任何 seq 校验；车机字段名为 `index`，且只存不校验 |
| `19:§3.3` | `TTC = d_behind/\|v_behind−v_ego\|`，`0<TTC<thr` 阻断 | `d_behind` 为负 → TTC 为负 → 条件恒假；分母来自错位估计器 |
| `19:§3.4` | 四重刚性门禁"任一不通过立即封锁" | 仅影响触发瞬间的一个布尔量；`torque` 路径与 `laneChangeNeedTorque` 路径可绕过；`starting/finishing` 阶段无复检 |
| `19:§5.1` | 断网 10 s 后回退单车道居中 | 计数为 20 s（且通常根本不会进入），归零后是常规自主变道分支 |
| `19:§5.2` | 越过中线则完成、刚打灯则中止 | 代码中不存在；`laneChangeStarting` 无任何 TTC 复检 |
| `19:§5.3` | 20 ms 内无条件切断转向扭矩 | 20 Hz / 50 ms；仅"反向打盘"生效；无 1.2 Nm 阈值 |
| `20:维度1` | 端口矩阵"是否存在冲突" | 前提本身错误，送外部模型会得到误判 PASS |

---

**本文为独立审计意见，未修改任何工程文件；全部结论均可在上述 file:line 复核。**
