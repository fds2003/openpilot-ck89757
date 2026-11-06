# 21 C3 端协同领航修改方案 第三方专家独立审计结论与整改建议

> 被审文档：19_C3端协同领航修改方案深度技术论证与代码审计白皮书.md、20_第三方专家模型独立审计与验证主提示词_Peer_Review_Master_Prompt.md
> 受审工程：openpilot-ck89757（分支 cp-custo-amap，基线 24b7ff2，HEAD dcd0264）
> 对照工程：AmapNavi-Reborn（车机端 Kotlin 真实源码）
> 审计方式：白皮书 Diff ↔ C3 真实代码 ↔ 车机真实源码，三方逐行比对（非纯文档评审）
> 审计日期：2026-11-02
> 结论等级：[FAIL]（按文件20 的四档判定，为最严重一档）
> 文档性质：独立审计意见；本次未修改任何工程文件

---

## 一、审计结论

**[FAIL] — 存在严重致命缺陷，严禁上实车。**

这不是"若干优化空间"，而是**核心链路根本没接通**：白皮书 1.1 解禁 amap_navi 进程这一改动制造了双实例与跨进程共享断裂，导致车机下发的变道指令无法可靠到达 desire_helper；叠加端口契约整体反转、设备发现握手三处不匹配、上行指令字段错配，本次 4 处修改所声称的功能在真实代码上均无法稳定工作。

更严重的是，TTC 安全门禁在传感器失效、消息缺失或数据异常时是 **fail-open（默认放行）**，且白皮书 5.1 / 5.2 / 5.3 三段安全论证与代码不符。这类"论证通过但实现缺失"的状态，比明确报错更危险。

Git 证据链属实：分支 cp-custo-amap、HEAD dcd0264、基线 24b7ff2 与白皮书声明一致。但**代码内容与白皮书描述大面积不符**，且白皮书19 与提示词20 自身存在事实性前提错误。

## 二、六大维度符合性速览

| 维度（按文件20） | 结论 | 关键发现编号 |
| :--- | :--- | :--- |
| 1 网络拓扑与通信契约 | FAIL | C-02、C-03、M-03 |
| 2 多线程并发与进程生命周期 | FAIL | C-01、M-02、M-07 |
| 3 变道控制与 TTC 数学严密性 | FAIL | C-05、M-04、C-04 |
| 4 功能安全、容灾与极端工况 | FAIL | C-06、C-07、C-08、M-01 |
| 5 Cereal / Cap'n Proto 兼容性 | PASS（有前提） | M-06、M-05 |
| 6 代码质量与边界漏洞 | NEEDS REVISION | M-01、M-03、m-01 ~ m-05 |

六个维度中，仅维度5 的序列化兼容性本身实质通过。

## 三、审查发现项矩阵

> 路径前缀：C3: = E:/code/openpilot-ck89757/ ；HU: = E:/汽车/库斯途升级破解/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/ ；19: / 20: = 对应两份文档。所有 file:line 均可复核。

| 编号 | 文件与行号 | 等级 | 问题现象与机理分析 | 改进建议 |
| :--- | :--- | :--- | :--- | :--- |
| C-01 | C3:system/manager/process_config.py:144；C3:selfdrive/carrot/carrot_man.py:191,340-344；C3:selfdrive/carrot/amap_navi.py:269,2054-2058 | Critical | 根因级缺陷。carrot_man 进程内已 AmapNaviServ() 内嵌实例，而 AmapNaviServ.__init__ 末尾即 start_navi_comm() 启动全部 UDP 线程；白皮书却把"amap_navi 独立进程被注释"当缺陷解禁，于是两个 always_run 进程各持一份实例、各自 SO_REUSEADDR 绑定 5510 / 7705 / 4211 / 4213。同一 UDP 包只会被其中一个 socket 收到；carrot_man.py:340 读的是本进程 shared_data，与 amap_navi 进程实例跨进程不共享。结果：包落到 carrot_man 内嵌实例时链路偶尔能通，落到 amap_navi 独立实例时指令只更新另一份 shared_data、carrot_man 永远看不到，desire_helper.py:920 的 TTC 分支间歇性永不执行。此外白皮书 1.1 的缺陷一属于误诊：carrot_man 内嵌实例本就一直在 5510 / 4211 / 4213 上监听，"C3 本地根本没有监听套接字、静默死亡"不成立；取消注释不是修复，而是制造了双实例与端口竞争 | 二选一冻结进程模型：(a) 撤回 process_config.py 改动，由 carrot_man 内嵌实例独占全部 UDP；(b) 真双进程，则删除 carrot_man 的直接对象访问，改用 Cereal/ZMQ 传递指令与状态 |
| C-02 | C3:selfdrive/carrot/amap_navi.py:200-201,1591,1636；19:§1.2/§2.3；20:维度1；HU:data/udp/CarrotUdpClient.kt:34-35；HU:data/udp/CarrotTelemetryParser.kt:8 | Critical | 端口契约整体反转。真实车机：PORT_TELEMETRY=7705（本地绑定收遥测）、PORT_CONTROL=7706（向 C3:7706 发控制），CarrotTelemetryParser 注释亦写明"C3 遥测 JSON (Port 7705)"；白皮书称"车机 7706 收遥测、7705 发控制"，完全颠倒。C3 监听集合仅 4211 / 4213 / 5510 / 7705，无人监听 7706，车机指令全部 ICMP Port Unreachable；C3 遥测改发 7706 而车机在 7705 收，双向全断。原代码 sendto(..., navi_remote_port=7705) 本来正确，被当成 bug 改错。提示词20 维度1 的前提同样错误，用它驱动外部模型会得出误判结论 | 以代码为准重新冻结《端口-方向-载荷》契约表，两端同步改；先做三段环回连通性测试再谈功能 |
| C-03 | C3:selfdrive/carrot/amap_navi.py:589-617；HU:data/udp/UdpDeviceDiscovery.kt:34-36,81,116-127；19:§3.1 | Critical | 发现握手三重断裂。车机绑 5510、向 255.255.255.255:4210 发 {"cmd":"discover","port":5510}，期望 resp=="c3_pong"；C3 绑 5510 只认 b"c3_ping"，回包为 {"device","status","ip","version"}。目的端口、探针内容、响应格式三处全不匹配，app_ip 恒为 None，白皮书 3.1 的动态 IP 自愈状态机从未运行 | 统一探针/响应 JSON schema 与端口；或改为 C3 单向广播通告、车机被动监听 |
| C-04 | HU:data/udp/CarrotUdpClient.kt:109-121；HU:data/relay/RelayEngine.kt:44,97；C3:selfdrive/carrot/amap_navi.py:989-994；C3:selfdrive/controls/lib/desire_helper.py:508,520 | Critical | 上行指令字段错配。车机只发 cmd / direction / index / v_cruise / blinker / timestamp，且 cmd 仅 LANECHANGE / SPEED_LIMIT / CANCEL（无 OVERTAKE）。C3 读 "arg" 得 None，carrotArg=None，desire_helper.py:508 恒判为 RIGHT，所有变道方向反了；C3 读 "param"，车机从不发（车机 overtake_mode 只在本地 SharedPreferences，见 UserSettingsRepository.kt:82），三级超车模式无下发入口、恒为常规；carrotCmd=="OVERTAKE" 分支永不触发，故 LANE_CHANGE_TIME_MAX*2.0 的 20 秒窗口也永不进入 | 对齐 arg 与 direction、补齐 param 与 overtake cmd，两端各写一份 schema 单测 |
| C-05 | C3:selfdrive/carrot/amap_navi.py:295-301；C3:selfdrive/controls/lib/desire_helper.py:923-930；C3:cereal/custom.capnp:76-77 | Critical | TTC 门禁五重 fail-open：① 雷达无数据 ttc=99.0 放行；② capnp Float32 字段默认 0.0，getattr(...,99.0) 对 capnp reader 不生效，消息缺失/旧日志/进程崩溃时 0.0 < 0.0 为 False 而放行；③ main_lb_drel 为负时 ttc 为负，0.0 < ttc 为 False 而放行；④ 后车并排 vrel≈0 时条件 < -0.1 不满足，ttc=99 放行；⑤ if lb ... elif rb 不区分变道方向，向右变道时左后一旦满足条件，右后高速来车被完全跳过而放行 | 无效 / 缺失 / ≤0 一律判为阻断；按 carrot_blinker_state 或 atc_left_right 显式选对应侧雷达；用 lbDrelValid 等有效性位做门禁 |
| C-06 | C3:selfdrive/controls/lib/desire_helper.py:1336-1342；19:§3.4/§5.3 | Critical | 接管安全声明与代码不符。真实条件是 steeringPressed 且反向扭矩方向匹配转向灯，仅"反向打盘"成立，非"任何方向用力打盘即无条件切断"；1.2Nm 阈值不存在（steeringPressed 是 CAN 布尔）；运行周期 20Hz（DT_MDL=0.05，50ms），非白皮书声称的 20ms / 50Hz；lane_change_audio(4) 即时播报那行被注释，语音需等 2 秒 atc_cancel_delay | 改为纯 steeringPressed 同帧清 desire，去掉方向附加条件；实测端到端接管延迟后重写白皮书 |
| C-07 | C3:selfdrive/controls/lib/desire_helper.py:431,507,523,959；19:§5.1 | Critical | 断网容灾不成立。carrot_lane_change_count 每帧 max(0,c-1) 递减，OVERTAKE 初值 int(10*2.0/0.05)=400 帧 = 20 秒，非白皮书说的 10 秒；LANE_CHANGE_TIME_MAX 只用于 lane_change_timer。归零后进入 else 分支即常规自主变道逻辑（auto_lane_change_enable），不是"回退单车道居中"，断网后仍可能自主变道 | 显式定义心跳超时状态，超时强制 auto_lane_change_trigger=False 并告警，不依赖计数自然衰减 |
| C-08 | C3:selfdrive/controls/lib/desire_helper.py:920-940,959+；19:§5.2 | Critical | 变道中途不复检 TTC。TTC 仅影响触发瞬间的 auto_lane_change_trigger；状态机进入启动/完成阶段后无任何复检，白皮书 5.2 描述的"越过中线则完成、刚打灯则中止"代码中不存在，属虚构容灾论证 | 状态机各阶段复检 TTC，定义中止 / 回正 / 完成的可观测条件 |
| M-01 | C3:selfdrive/carrot/amap_navi.py:583-635,986-994；19:§3.2 | Major | 无认证 / 无来源过滤 / 无重放防护。绑 0.0.0.0:7705 与 0.0.0.0:5510，热点内任意设备可注入变道指令或伪造 c3_ping 劫持 app_ip（遥测单播外泄）；param 用 int() 无白名单，畸形值异常被吞；cmd_index 只存不校验单调性。白皮书声称的"seq 严格递增、旧序列号自动丢弃"在代码中完全不存在（车机字段叫 index） | 源 IP 白名单 + 会话令牌/HMAC + index 单调校验 + param 限定 {0,1,2} |
| M-02 | C3:system/manager/process_config.py:144；C3:selfdrive/carrot/amap_navi.py:589-592,626-629；19:§1.1 | Major | always_run 使 offroad 常驻 20Hz 收发送与广播，与熄火节能策略冲突；bind 失败时线程静默 return，进程仍存活，manager 不会重启。白皮书"3 秒内看门狗自愈"对线程级故障不成立 | 改 only_onroad / 条件启动；bind 失败上报告警并让进程退出以便重启 |
| M-03 | C3:selfdrive/carrot/amap_navi.py:1660-1760,291,297；HU:data/udp/CarrotTelemetryParser.kt:29-47；19:§2.3 | Major | 遥测字段名两端不对齐：C3 发 break_press、lb_vrel、v_ego_kph，车机读 brake_press、lidar_behind_vdist_time、lb_drel、lidar_lbblind，HUD 雷达卡片与 TTC 恒为默认值；白皮书示例里的 lidar_behind_vdist_time、left_line_type 等 C3 根本不发。同一 main_lb_drel（单位 mm）在 lbDrel 用 /100、TTC 用 /1000，至少一处量纲错误，车机按米解析会放大 10 倍 | 生成唯一 JSON schema，两端用同一 fixture 做序列化 / 解析往返测试 |
| M-04 | C3:selfdrive/controls/lib/desire_helper.py:926-930；19:§3.3 | Major | 门限不耦合车速与变道时长。1.8 / 2.5 / 3.5s 为固定瞬时 TTC，未计本车速、后车绝对速度、变道所需时间（窗口长达 20s）；120km/h 下 1.8s 仅约 60m。且 capnp overtakeMode 默认 0 会落进 if ==0: 1.8，意外启用最激进模式，与 fail-safe 意图相反 | 门限改为 TTC > t_lanechange + margin 并随车速缩放；默认值显式判空并取常规 |
| M-05 | C3:selfdrive/controls/lib/desire_helper.py:923-924；19:维度5 | Major | getattr 兜底对 capnp 无效。self.sm['amapNavi'] 的字段始终存在，default 永不生效；新 reader 读旧日志得 0 / 0.0，恰好触发 C-05 与 M-04。白皮书只答"不破坏反序列化"，未识别语义陷阱 | 用显式有效性位判断，或给字段设哨兵默认值并在消费端校验 valid |
| M-06 | C3:cereal/custom.capnp:59-78 | Pass | 维度5 唯一通过项：@15 / @16 追加在 struct 末尾、ordinal 连续，符合 Cap'n Proto 向下兼容规范，旧 reader 忽略新字段、新 reader 读旧数据不崩 | 配合 M-05 处理默认值语义，发布前跑一次 log replay 回归 |
| M-07 | C3:selfdrive/carrot/amap_navi.py:191,534-535,1661；C3:selfdrive/carrot/carrot_man.py:406 | Major | 独立 amap_navi 进程的 SubMaster 订阅列表不含 carState（L191 被注释），而 update_navi_carstate(sm) 仅在 carrot_man.py:406 被以其自身含 carState 的 sm 调用，独立进程 shared_data.carState 恒为 False，make_navi_message 中 if self.shared_data.carState 分支整体跳过，v_ego_kph / engaged / steer_angle / blindspot 等车辆状态字段全部不发，遥测报文不完整 | 先按 C-01 统一进程模型再定数据源；或显式补订阅 carState 并在独立进程内调用 |
| m-01 | C3:selfdrive/carrot/amap_navi.py:640；19:§2.2 | Minor | Ratekeeper(20) 注释 #50Hz（实为 20Hz）；白皮书把 amap_navi 进程内线程描述成会阻塞 controlsd 100Hz 主循环，两者是不同进程，无此路径 | 修正文档 |
| m-02 | C3:selfdrive/controls/lib/desire_helper.py:937 | Minor | rear_conflict 播报 lane_change_audio(6) 注释"盲区有车"，实际是后方来车，误导驾驶员 | 新增对应语音类型 |
| m-03 | C3:selfdrive/carrot/amap_navi.py:597；19:§2.2 | Minor | shared_data.app_ip 在锁外写，clients 有锁；CPython 引用赋值原子、风险低，但与"SharedData 线程安全"声明不符 | 统一加锁或改 volatile 语义说明 |
| m-04 | 19:§3.2 | Minor | "FastTelemetryScanner / 无锁打包"与真实 CarrotTelemetryParser / 全局 lock 不符，命名与描述失实 | 修正 |
| m-05 | C3:selfdrive/carrot/amap_navi.py:1633-1636 | Minor | 修改不彻底：navi 通告仍广播到 navi_remote_port(7705)，但通告内容声明端口 7706，形成两套并存的不一致通告 | 统一 |
| m-06 | 19:§2.1 | Minor | 时序图把控制链路画成 UDP → amapNavi Cereal → desire_helper，真实链路是 UDP → SharedData → carrot_man → carrotMan.carrotCmd → desire_helper（且因 C-01 断裂） | 重画时序图 |

## 四、对提示词20 本身的附加评审

20_第三方专家模型独立审计与验证主提示词_Peer_Review_Master_Prompt.md 不宜直接用于外部模型评审：

1. 维度1 的端口前提（"车机监听 7706/5510，C3 监听 7705/5510，C3 发往 7706"）与两端真实代码矛盾，外部模型会基于错误前提推演，极易给出 PASS 类误判；
2. 六大维度缺失两个决定性检查项：进程边界 / 跨进程共享一致性（C-01 的根因），以及车机端设置项到 C3 的端到端字段贯通（C-04）；
3. 缺少"白皮书声明 ↔ 真实代码逐条比对"这一取证步骤，导致白皮书里虚构的报文示例、seq 防重放、5.x 容灾论证无法被识破。

建议先按本报告修订提示词，再送外部模型做二次独立复核。

## 五、针对极端工况的推演与质询

1. **网络风暴 / 热点内多设备**：乘客手机向 C3:7705 泛洪 c3_ping 或畸形 LANECHANGE。app_ip 被最后一个包劫持，20Hz 遥测单播持续外泄；param="abc" 触发 int() 异常被 except 吞掉、线程退化为 20Hz 空转且 manager 无感知；指令注入可诱发非预期转向。当前无任何源认证。
2. **极低车速 / 后车并排**：本车 20km/h，后车紧贴左后 3m 同速（vrel≈0）。lb_vrel < -0.1 不成立，ttc=99.0 放行；若激光雷达同时未报盲区，side_object_detected 也不阻断，直接切入相邻车辆。TTC 对"零相对速度、零间距"无定义，而这是最常见的加塞场景。
3. **雷达点云跳变 / 负距离**：main_lb_drel 瞬时跳为 -5000mm（目标越过或滤波异常），if ... and main_lb_drel 对负值仍为 True，ttc 为负，0.0 < ttc 为 False 而放行。单点异常即击穿门禁，无连续性 / 有效性校验（lbDrelValid 只在发布端置位，消费端未读）。
4. **车机断电 / Wi-Fi 断开瞬间**：无心跳超时机制，carrot_lane_change_count 从 400 帧（20s）自然递减，期间沿用上次的 overtake_mode 与 lane_change_available；归零后进入自主变道分支。若此刻满足自主变道条件，断网后仍会打灯变道。白皮书 5.1"绝不失控变道"不成立。
5. **双实例端口竞争随机性（最隐蔽）**：两个 always_run 进程都 SO_REUSEADDR 绑同一组端口，内核 UDP 分发与启动顺序决定哪个 socket 收到包，指令这次被 carrot_man 内嵌实例收到（链路偶尔通）、下次被 amap_navi 独立进程收到（链路断）。表现为间歇性、不可复现的"有时能变道有时不能"，也解释了为何作者可能误以为"修好了"，是实车最难排查的故障形态。

## 六、最终实车落地建议与专家寄语

1. **先冻结契约，再动代码**：以两端真实代码反向生成唯一的《端口 / 方向 / JSON schema / Cereal 字段》契约表，白皮书19 与提示词20 全部按该表重写。在此之前禁止实车联调。
2. **修复顺序不可颠倒**：先定进程模型（C-01），再修端口与握手（C-02 / C-03），最后才是 TTC 门禁。用 ss -ulnp 确认每个端口只有一个 owner；对 ping→pong、遥测→HUD、指令→carrotMan→desire 三段分别打桩验证，不要端到端一把梭。
3. **门禁默认态必须 fail-safe**：把"无数据 / 无效 / 缺失 / 0"统一判为阻断，补变道方向选择与有效性位；台架注入测试覆盖"雷达断流、负距离、并排车、消息缺失"四类。
4. **重写安全论证**：白皮书 5.1 / 5.2 / 5.3 三段容灾行为目前与代码不符，必须逐条给出对应代码行号与实测数据（尤其接管端到端延迟），否则不能作为功能安全证据。
5. **把车载热点当不可信网络**：加源 IP 白名单 + index 单调校验 + param 白名单；联调先用封闭热点、录全量 UDP pcap，再逐步放宽。

---

本文为独立审计意见，未修改任何工程文件；全部结论均可在上述 file:line 复核。
