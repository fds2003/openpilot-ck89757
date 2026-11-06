# 现代库斯途智能领航双端全量协同工程独立安全审查报告

> **审查依据**：`23_双端全量工程第三方专家独立审查终极主提示词_Master_Review_Prompt.md`
> **受审资料**：`22_双端全量协同技术方案与源码实现综合审计总纲.md`（含两端全量源码路径与逐行 Diff）
> **实际取证对象**：
>
> - 车机端：`E:\汽车\库斯途升级破解\AmapNavi-Reborn\`（Kotlin 源码、`AndroidManifest.xml`、`build.gradle`、`res/layout`）
> - C3 端：`E:\code\openpilot-ck89757`（分支 `cp-custo-amap`，`cereal/`、`selfdrive/`、`system/`、`opendbc_repo/`）
>
> **取证方式说明**：本机 Windows 环境 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`），**未执行任何构建、编译、dumpsys 或实机命令**；全部结论基于源码逐行阅读，引用均为 `file:line` 可复核。文档（22）中的性能实测数字（PSS 3.5MB、功耗 1.65W、39℃）本轮**无法验证**，仅评审其与代码的一致性。
>
> **审计日期**：2026-11-02

---

## 一、综合评审结论 (Overall Verdict)

### 🔴 [FAIL] — 存在严重的功能安全漏洞与通信级死锁，严禁实车部署

决定性事实支撑：

1. **两端 UDP 端口是"同向冲突"而非"配置错位"，物理上不可能通信**。车机端 `CarrotUdpClient.kt:30-32` 定义 `PORT_TELEMETRY=7705`（本地 `bind` 收）与 `PORT_CONTROL=7706`（发往对端 7706）；C3 端 `amap_navi.py:200-201` 定义 `navi_port=7706`（发）与 `navi_remote_port=7705`（`_headunit_cmd_recv_thread` `bind` 收）。**两端都"在 7705 收、往 7706 发"**——遥测永远到达不了车机，指令永远到达不了 C3。这与"改一个端口号"不同，是契约层设计错误，任何上层算法（含 TTC 门禁）在此之上都不可能生效。
2. **车机端唯一的后车净空门禁 `LateralSafetyEvaluator` 量纲全错**：它把 C3 上报的 `lb_drel`（**毫米**、且后方为**负**）直接当作"米"与 `max(10.0, v_ego·2.0)`（几十米）比较（`LateralSafetyEvaluator.kt:64-88`；`CarState.kt:39` 注释却写"米"）。结果是：有后车目标时 `负值 < 55` → **永久阻断变道**；无目标时用默认 `999f` → **永久放行**。这是本轮最重要的新增发现。
3. **C3 端"解禁进程"制造双实例与双发布者竞态**：`carrot_man.py:191` 在 `CarrotMan.__init__` 第一行就构造 `AmapNaviServ()`，其 `__init__` 末尾即 `start_navi_comm()` 并在 `amap_navi.py:269` 创建 `PubMaster(['amapNavi'])`。本次又把 `amap_navi` 设为 `always_run`（`process_config.py:144`）。两个进程都发布同一 cereal service —— `cereal/messaging/__init__.py:3` 显式导入的 `MultiplePublishersError` 正是在此场景抛出：**启动顺序决定谁崩、谁收包**。
4. **文档 22 与实际代码大面积不符**（虚构代码片段、声称已实施但代码中不存在的优化），使该文档**不能作为外部模型的审计证据基**。例如 §3.3① 展示的 `CarrotTelemetryParser` 实现（`CarrotTelemetry`/`extractDouble`）在实际文件中并不存在；§4.4 声称已配置 `"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"`，但 `substitute.toml` 全文无该条目；`build.gradle` 明确 `minifyEnabled false`，与"开启 ProGuard/R8 死代码精简"矛盾。

**结论**：车机端的"内存/兼容性重构"部分确有真实工程质量（`MultiDexApplication` 引导正确、`@RequiresApi(26)` 通知渠道已正确隔离到独立 `object` 内、`ViewStub` 惰性挂载真实存在），但**协同链路与安全门禁未接通且方向错误**，属"论证通过、实现不成立"的高危状态。

---

## 二、分端深度审查意见与挑刺整改矩阵 (Findings & Rectification Matrix)

> 前缀：`HU:` = `E:\汽车\库斯途升级破解\AmapNavi-Reborn\app\src\main\java\tech\touka\amapnavi\`；`C3:` = `E:\code\openpilot-ck89757\`。
> 编号：`X-`=通信协同，`H-`=车机端，`C-`=C3 端，`D-`=文档与证据链。

### 2.1 通信协同层（决定功能是否存在）

| 编号 | 端 | 源码路径与行号 | 级别 | 缺陷机理与底层风险 | 修复方案 |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **X-01** | 通信（双端） | `HU:data/udp/CarrotUdpClient.kt:30-32,34-52,107-121`；`C3:selfdrive/carrot/amap_navi.py:200-201,586-600,1588-1596` | **Critical** | **同向绑定，双向全断**。车机 `bind(7705)` 收、发往 `7706`；C3 `bind(7705)` 收、发往 `7706`。两端角色完全对称 → 遥测与指令各自打到"对方也在用的发送口"，无人监听。表现为 HUD 永久灰屏 + 车机所有按钮无反应，且**与发现握手是否成功无关**（即使 IP 学到也照样不通）。白皮书/总纲 §5.1 声称的"C3→7706、车机→7705"与**车机代码相反** | 冻结契约为：**C3 发 7706 / 收 7705；车机收 7706 / 发 7705**。车机端改两个常量即可（见 §三 补丁 P-01） |
| **X-02** | 通信（双端） | `HU:data/udp/UdpDeviceDiscovery.kt:34-36,71-92,116-127`；`C3:selfdrive/carrot/amap_navi.py:586-617` | **Critical** | **发现握手三重不匹配**：① 车机向 `255.255.255.255:4210` 广播探针，C3 新线程却 `bind(5510)`——探针根本到不了该线程（C3 侧无人监听 4210，`navi_broadcast_info` 只往 4210 **发**）；② 车机探针为 `{"cmd":"discover","port":5510}`，C3 只认字节子串 `b"c3_ping"`；③ 车机要求回包 `resp=="c3_pong"` 且读 `auth`/`device_id`/`ip`，C3 回的是 `{"device":"comma3","status":"ready",...}`。三重全错 → `app_ip` 恒 `None`，"动态 IP 自愈状态机"从未运行 | C3 改为 `bind(4210)`、同时兼容两种探针、按车机 schema 回包到 `addr[1]`（见 §三 P-02）；车机保留现状即成为契约 owner |
| **X-03** | 通信（双端） | `HU:data/udp/CarrotUdpClient.kt:107-121`；`HU:core/event/LaneAction.kt:8-11`；`C3:selfdrive/carrot/amap_navi.py:986-995`；`C3:selfdrive/carrot/carrot_man.py:340-345`；`C3:selfdrive/controls/lib/desire_helper.py:505-524` | **Critical** | **上行字段名与语义全面错配**。车机实发 `cmd/direction/index/v_cruise/blinker/timestamp`（`direction` 是字符串 `"LEFT"/"RIGHT"/"KEEP"`）；C3 读 `arg`→恒 `None`→`desire_helper.py:508` 恒判 `BLINKER_RIGHT`（**方向必错**）；C3 读 `param`→车机从不发→三级超车模式恒为常规；C3 判 `cmd=="OVERTAKE"`→车机只发 `LANECHANGE/SPEED_LIMIT/CANCEL_LANE_CHANGE`→**20 s 窗口永不进入**，新门禁仅剩 `LANECHANGE` 给的 4 帧（0.2 s） | 车机改为同时下发 `arg` 与 `param`、`seq`（保留旧键做兼容）；C3 兼容读取两种键名并做 `param ∈ {0,1,2}` 白名单（见 §三 P-03 / P-06） |
| **X-04** | C3 进程 | `C3:selfdrive/carrot/carrot_man.py:191`；`C3:selfdrive/carrot/amap_navi.py:269,574-583`；`C3:system/manager/process_config.py:143-144`；`C3:cereal/messaging/__init__.py:3,239-245` | **Critical** | **双实例 + 双发布者启动竞态**。`carrot_man` 内嵌 `AmapNaviServ()` 已自带 6 个 UDP 线程与 `PubMaster(['amapNavi'])`；再解禁独立 `amap_navi` 进程 → ① 两个 publisher 抢同一 service，后到者抛 `MultiplePublishersError`；② 两进程各 `SO_REUSEADDR` 绑 `5510/7705/4211/4213`，UDP 单播包只投给其中一个；③ `carrot_man.py:340-345` 读的是**本进程** `shared_data`，跨进程不共享。表现为"有时能变道有时不能"的不可复现故障；若崩的是 `carrot_man`，`carrotMan` service 缺失，`desire_helper` 读到全零默认值，整套 carrot 功能静默失效 | **撤回 `process_config.py:144`**（推荐，见 P-04），由内嵌实例独占；若坚持双进程则必须删除 `carrot_man.py:191` 内嵌构造并新增 cereal 上行通道 |
| **X-05** | 通信→安全 | `C3:selfdrive/carrot/amap_navi.py:295-301,1136,1174,216`；`C3:selfdrive/controls/lib/desire_helper.py:919-941,1213-1220` | **Critical** | **TTC 安全门禁五重失效 + 作用域错误**：① `main_lb_drel` 后方为**负**，故 `ttc = 负 / abs(vrel) < 0`，而判据是 `0.0 < ttc < thr` → **恒假，永不阻断**；② `lb_vrel` 由 `self.leftFrontTarget`（左**前**估计器）算出（1136 行，`leftBehindTarget` 建而不用），且被前/后两个距离交替喂入、`max_acc=4.0` 限幅下恒定饱和 → 分母不可信（对比 1174 行右侧写法正确）；③ 雷达无数据时 `ttc=99.0` **放行**；④ capnp `Float32` 零默认 `0.0`，`getattr(..., 99.0)` 对 capnp reader 永不生效，`0.0 < 0.0` 为假 → 消息缺失/进程崩溃即放行；⑤ `if lb ... elif rb` 不分变道方向，向右变道时左后来车可完全掩盖右后高速来车 | 见 §三 P-05 / P-06：绝对值化、方向化、失效即阻断、门禁绑定状态机全阶段 |
| **X-06** | 通信→安全 | `HU:data/relay/RelayEngine.kt:97,152-158`；`C3:selfdrive/carrot/amap_navi.py:986-995`；`C3:selfdrive/controls/lib/desire_helper.py:505-509` | **Major** | **撤销与定速指令在 C3 侧无实现**。车机 `onCancelCommand` 发 `CANCEL_LANE_CHANGE`、`nudgeCruise` 发 `SPEED_LIMIT`，C3 仅把它们写进 `remote_cmd`，`desire_helper` 只识别 `LANECHANGE/OVERTAKE` → **撤销变道与定速微调按钮全部无效**。一旦车机侧判定危险撤销，C3 仍在执行原变道 | C3 在 `_update_command` 中对 `CANCEL_LANE_CHANGE` 置 `remote_cmd="CANCEL"` 并令 `cmd_index` 变化，`desire_helper` 收到即 `lane_change_state=off`；`SPEED_LIMIT` 走 `vCruise` 通道（P-06 附） |

### 2.2 车机端（Android 4.4 / Dalvik / i.MX6）

| 编号 | 端 | 源码路径与行号 | 级别 | 缺陷机理与底层风险 | 修复方案 |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **H-01** | 车机 | `HU:domain/safety/LateralSafetyEvaluator.kt:64-88`；`HU:core/model/CarState.kt:38-40`；`HU:data/udp/CarrotTelemetryParser.kt:42-43`；`C3:selfdrive/carrot/amap_navi.py:1130-1140` | **Critical** | **净空门禁量纲错误（mm 当 m 用）+ 符号未处理**。C3 用原始毫米值上报（`lb_drel` 后方为负，如 `-12500`），车机 `CarState.leftRearDistance` 注释写"米"、默认 `999f`，直接与 `max(10.0, v_ego_mps*2.0)`（例：100km/h → 55m）比较。结果：**有目标 → 负值 < 55 → 永久阻断**；**无目标 → 999 > 55 → 永久放行**。该门禁在两种状态下都是错的，且是车机端唯一与"后车逼近"相关的判定 | 统一到米并取绝对值、缺省置"未知→阻断"（见 §三 P-07） |
| **H-02** | 车机 | `HU:data/prefs/UserSettingsRepository.kt:110-137`；`HU:core/model/OvertakeSettings.kt:9-19` | **Major** | **超车参数设置界面基本不生效**。`loadOvertakeSettings()` 只回填 3 个字段（`enabled/standardCooldownMs/allowRightOvertake`），`minEngageSpeedKmh(60)/prepareBlinkMs(1200)/interruptCooldownMs(60000)/telemetryTimeoutMs(1000)/executeTimeoutMs(4500)/driverSteerThresholdDeg(25)` 全部走构造默认值；`setInt/setFloat` 仅对 `KEY_REVERSE_COOLDOWN_S` 刷新缓存 → **改任何参数都要重启进程**。`KEY_OVERTAKE_MODE`（0/1/2 激进/常规/保守）在整个工程中**从未被读取**，也没有下发给 C3 的通道 | 全字段绑定 + 任何 `set*` 后统一 `reload()`；新增 `overtakeMode` 并随指令下发（P-08） |
| **H-03** | 车机 | `HU:data/relay/RelayEngine.kt:152-158`；`HU:data/udp/CarrotUdpClient.kt:62-88` | **Major** | **决策在主线程外的 UDP 接收协程里同步跑，且每包分配**。`onTelemetry`（在 `Dispatchers.IO` 的 `receive` 循环内被调用）→ `stateMachine.tick()` → `snapshot()` **每个 tick `new OvertakeStatus`** + `String.format` + 字符串模板拼接；阻塞信息还会拖慢收包循环本身。Dalvik 无并发压缩 GC，这是 `GC_FOR_ALLOC` 停顿的真实来源，与文档"零 GC 停顿"直接矛盾 | tick 转交单线程 conflated 通道；`message` 改预生成常量表（P-09） |
| **H-04** | 车机 | `HU:data/udp/CarrotTelemetryParser.kt:12-52,66-129`；`HU:data/udp/CarrotUdpClient.kt:76-84` | **Major** | **"零对象分配"不成立**。每个包 `String(packet.data,0,len,UTF_8)` **必分配 1 个 String**；`parse()` 内 20 次 `substring(...)` **各分配 1 个 String**（`fastGetInt/fastGetBool/fastGetFloat` 全部用 `substring`），20-50Hz 下约 1000-2000 次分配/秒；`String.format` 在 UI 侧再叠加。此外 `parse(json: JSONObject)` 重载仍在，任意误用即回到 HashMap 时代 | 改为 `ByteArray` 级游标解析、纯数值累加（P-10） |
| **H-05** | 车机 | `HU:ui/main/MainActivity.kt:245-300,196-215` | **Major** | **HUD 在 Main 线程 20-50Hz 全量刷新**。`renderCar` 每次 emission 执行 ~14 次 `setText`（每次分配 Spannable）+ 4 次 `setTextColor` + `String.format`；`tvLight` 每帧 `setBackgroundColor` 触发重绘。在 i.MX6/GC2000 上这本身就是掉帧与 GC 的放大器，与文档"Vivante 弱 GPU / 毫秒级平滑"自相矛盾。另外 `"🚦 红灯 …" / "🟢 绿灯 …"` 使用的 emoji（`U+1F6A6`/`U+1F7E2`）在 Android 4.4 的 NotoColorEmoji 中**无字形**，实机显示为豆腐块 □ | 渲染节流到 10Hz + 变更检测 + 去 emoji 改矢量色块（P-11） |
| **H-06** | 车机 | `HU:domain/decision/OvertakeStateMachine.kt:213-248`；`HU:core/model/CarState.kt:46`；`C3:selfdrive/carrot/amap_navi.py:1636-1780` | **Major** | **变道完成反馈两端都没有**。车机 `handleExecuting` 依赖 `car.atcState == 3` 判断完成，但 C3 的遥测 JSON **从不发送 `atc_state`**（`make_navi_message` 无此键）→ 每次变道必然走到 `executeTimeoutMs` 超时分支，且该分支注释为"按完成结算"，随后进 `FINISHING → COOLDOWN` 并播报"变道完成"。**失败/卡住的变道被当作成功结算** | 车机超时分支改为"撤销 + 报错 + 长冷却"（P-12）；C3 后续补发 `lane_change_state` |
| **H-07** | 车机 | `HU:../build.gradle:38-43`；`HU:../AndroidManifest.xml:36-90` | **Minor** | **文档与工程不符的实证**：`minifyEnabled false`（文档称"开启 ProGuard/R8 死代码精简，彻底剔除 OkHttp"）；manifest 仍声明 5 个独立 `Setting*Activity`（文档称"废除跨 Activity 启动"）。`ViewStub` 同窗挂载确为真实实现（`MainActivity.kt:154-170`），但只覆盖 3 个参数页，设备页/日志页仍是 `startActivity` | 文档据实修正；`minifyEnabled true` + 保留规则（P-13） |
| **H-08** | 车机 | `HU:ui/main/MainActivity.kt:172-178`；`HU:service/KeepAliveService.kt:30-52` | **Minor** | 返回键在浮层隐藏时 `super.onBackPressed()` → `finish()` 主界面；`KeepAliveService` 因 `START_STICKY` 继续跑但 UI 已被销毁，重新进入时 `RelayEngine.start()` 早退（`running=true`），UI 与引擎生命周期无一致约定。车载场景更合适的是退到后台而非销毁 | 改为 `moveTaskToBack(true)`（P-14） |
| **H-09** | 车机 | `HU:../AndroidManifest.xml:43-90` | **Minor** | `SettingActivity` 等 5 个组件 `exported="true"` + `ACTION_VIEW` 过滤且无 `data` scheme，任意第三方 App 可拉起；当前 `targetSdk 22` 下 `exported` 不生效（默认允许），一旦按计划升 targetSdk 将直接暴露 | 删除 `exported`/intent-filter，或加私有自定义 action（P-15） |
| **H-10** | 车机 | `HU:service/KeepAliveService.kt:24-35` | **Suggestion** | `onCreate` 与 `onStartCommand` 各自 `buildNotification()` 一次，产生两份 Notification 对象；`setSmallIcon(R.mipmap.ic_launcher)` 用彩色启动图标作状态栏小图标，API 19 下会以整图缩放显示（视觉异常）。Dalvik 兼容性方面**做得正确**：`@RequiresApi(26)` 的 `NotificationChannel` 已隔离在独立 `object` 内，API 19 分支不会加载该类，不会触发 `VerifyError`——这一点应作为正面结论保留 | 通知对象缓存为字段、小图标改用单色 drawable（P-16） |

### 2.3 C3 端（openpilot / cp-custo-amap）

| 编号 | 端 | 源码路径与行号 | 级别 | 缺陷机理与底层风险 | 修复方案 |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **C-01** | C3 | `C3:selfdrive/carrot/amap_navi.py:1509-1540`（第 1514 行）vs `598` | **Critical** | **新线程导致清理线程静默死亡**。`_discovery_responder_thread` 写入的 client 记录只有 `last_time`；`_clean_clients_thread` 用 `info["last_seen"]` 索引 → 首个 `c3_ping` 后立即 `KeyError`；该线程无 `try/except`，异常即永久退出 → 客户端永不过期、`ext_state` 冻结、每客户端 worker 线程泄漏。`manager` 只监控进程存活，对此完全无感 | 统一键名 + 线程级 try/except + 单点工厂（P-17） |
| **C-02** | C3 | `C3:selfdrive/controls/lib/desire_helper.py:1336-1342` | **Major** | **接管声明与代码不符**：`steering_pressed` 要求"方向盘扭矩方向与转向灯相反"，非"任何反抗力矩"；无 `1.2 Nm` 阈值（`carState.steeringPressed` 是 CAN 布尔）；`lane_change_audio(4)` 那行被注释，播报要等 `atc_cancel_delay = int(2.0/DT_MDL)`（2 s）；更新周期 20 Hz（50 ms），非文档所称 20 ms | 去掉方向附加条件、恢复即时播报、实测端到端延迟（P-18） |
| **C-03** | C3 | `C3:selfdrive/carrot/amap_navi.py:190`；`C3:selfdrive/carrot/carrot_man.py:406` | **Major** | 独立进程的 `SubMaster` 订阅列表不含 `carState`，`update_navi_carstate` 仅在 `carrot_man` 内被调用 → 独立实例的 `shared_data.carState` 恒 `False`，`make_navi_message` 的整车状态段（`v_ego_kph/engaged/steer_angle/blindspot`）整体跳过 → 遥测报文残缺 | 随 X-04 统一进程模型解决（P-04） |
| **C-04** | C3 | `C3:selfdrive/carrot/amap_navi.py:1541-1560,1590-1596`；`HU:data/udp/CarrotTelemetryParser.kt:33-41` | **Major** | **遥测口径与订阅方不匹配**：C3 发 `break_press`（拼写），车机读 `brake_press`；C3 从不发 `lidar_behind_vdist_time/atc_state/driver_steering/active`，而车机解析器逐项读取 → HUD 后车时距恒 0、完成反馈恒缺失；同一报文连发 3 份（`4210` + `7706` + `app_ip:7706`），弱网下带宽 ×3；实际 UDP 推送为 `Ratekeeper(10)` = 10 Hz，非文档所称 20 Hz | 统一 schema + fixture 往返测试；TTC 同时写入 JSON；去重复投递（P-19） |
| **C-05** | C3 | `C3:cereal/custom.capnp:76-77`；`C3:cereal/gen/cpp/custom.capnp.h:63-79` | **Major** | **生成物未重生成**。`AmapNavi` 已追加 `@15/@16`，但已提交的 C++ 生成头仍是 `CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d, 8, 0)`（8 个 data word，对应改动前 15 字段；新增 2 个 4 字节字段后应为 9）。构建若未重跑 capnp，C++ 消费方按旧布局错位解码 | 重新生成并纳入提交；CI 加一致性检查（P-20） |
| **C-06** | C3 | `C3:selfdrive/controls/lib/desire_helper.py:431,505-524,959-975` | **Major** | **断网容灾声明不成立**：`carrot_lane_change_count` 每帧 `max(0,c-1)` 自然衰减（`OVERTAKE` 路径 `int(10*2.0/0.05)=400` 帧 = 20 s，非 10 s），期间沿用最后已知的 `overtakeMode`；归零后进入 `else` 分支即常规自主变道逻辑，**不是**"单车道居中" | 引入显式心跳超时状态，超时立即 `auto_lane_change_trigger=False` 并告警（P-06 附） |
| **C-07** | C3 | `C3:opendbc_repo/opendbc/car/torque_data/substitute.toml`（全文 105 行） | **Major** | **"帕里斯帝 NNFF 力矩映射"未实施**：全文无 `HYUNDAI_CUSTIN_1ST_GEN` 条目。库斯途因此落在 `CarInterfaceBase.configure_torque_tune()` 的默认/直采路径，横向力矩参数与大车（2t / 3.055m 轴距）不匹配，弯道易画龙 | 按文档意图补条目并跑 NNFF 校验（P-21） |
| **C-08** | C3 | `C3:opendbc_repo/opendbc/car/hyundai/interface.py:202,216-222` | **Minor** | **专车调优被夸大**：`ret.startAccel = 1.0` 是**全 Hyundai 通用**赋值（非库斯途分支）；`0x485` 的 LFAHDA 处理走的是上游既有 `HyundaiFlags.SEND_LFA` + `HAS_LFAHDA` 机制，不是本次定制。文档 §4.4 将其表述为"库斯途专属优化"，属证据失真 | 文档据实改写；如需专车差异化，加 `if candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN:` 分支（P-22） |
| **C-09** | C3 | `C3:selfdrive/controls/lib/desire_helper.py:1330-1350`；文档 §4.4 第 2 条 | **Minor** | **"5.0 s S 曲线 / ≤0.08g / jerk ≤0.05g·s⁻¹"在代码中无实现证据**：`LANE_CHANGE_TIME_MAX = 10.0` 是超时上限，横向轨迹由模型驱动，未发现 5.0 s 或横向 jerk 钳制的代码行 | 提供 file:line 或撤回该结论（P-23） |

### 2.4 文档与证据链

| 编号 | 涉及 | 位置 | 级别 | 问题 | 整改 |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **D-01** | 文档 | `22:§3.3①` | Major | 展示的 `CarrotTelemetryParser`（`CarrotTelemetry` 类、`extractDouble/extractBoolean/extractInt`、`left_line_type` 字段）**在实际文件中不存在**；实际为 `object CarrotTelemetryParser.parse(String): CarState` + `fastGetInt/Bool/Float`。用虚构代码送外部模型评审，必然得出错误的"通过"结论 | 以真实文件内容替换 |
| **D-02** | 文档 | `22:§5.1` | Critical | 契约表标注"7706 C3→车机遥测 / 7705 车机→C3 命令"，与车机代码 `PORT_TELEMETRY=7705`（收）`PORT_CONTROL=7706`（发）**相反**；且与 C3 代码组合后形成同向冲突（X-01） | 以本报告 §三 P-01 冻结后的端口重写契约表，并补"谁 bind / 谁 send"两列 |
| **D-03** | 文档 | `22:§3.3`、`§4.4`、`§3.4` | Major | "开启 ProGuard/R8 精简"（实为 `minifyEnabled false`）、"废除跨 Activity"（仍 5 个 Activity）、"帕里斯帝 NNFF 已配置"（无该条目）、"PSS 3.5MB / 1.65W / 39℃"（无任何可复现测量命令） | 逐条给出 `file:line` 或测量命令；不能复核的结论不得进入审计基 |
| **D-04** | 提示词 | `23:二.3`、`23:维度 3/4/5/6` | Major | 主提示词把"车机监听 7706 / C3 发往 7706"与"TTC=1.8/2.5/3.5 s 有效"、"20ms 接管"等**未经代码验证的前提**写死，外部模型会据此推演并给出 PASS 类误判 | 先固化 X-01/X-05 的结论，再据此重写提示词前提 |

---

## 三、直接可落地的精确代码修改实现 (Exact Code Fixes)

> 说明：以下补丁均针对本轮已核实的真实文件内容编写。若枚举/字段与最新提交有差异，以补丁中的注释为准做微调。
> **应用顺序必须为 P-01 → P-02 → P-03 → P-04（进程模型）→ P-17 → P-05/P-06（门禁）→ 其余。**

### P-01（X-01，Critical）车机端端口契约修正 — 复制即用

```diff
--- a/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/udp/CarrotUdpClient.kt
+++ b/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/udp/CarrotUdpClient.kt
@@ -27,10 +27,14 @@
     )

     companion object {
-        const val PORT_TELEMETRY = 7705
-        const val PORT_CONTROL = 7706
+        // 契约冻结：C3 在 7705 收指令、向 7706 推遥测
+        //          车机在 7706 收遥测、向 7705 发指令
+        // 注意：两端必须交叉，绝不能"同一端口既收又发"（旧实现即此错误，双向全断）
+        const val PORT_TELEMETRY = 7706   // 本机接收遥测的端口
+        const val PORT_CONTROL = 7705     // 对端(C3)接收指令的端口
     }
```

同时更新文档化注释：

```diff
  *  - 本地绑定 7705 接收 10~20Hz 遥测 JSON；
- *  - 向 C3:7706 下发控制指令，index 采用 AtomicInteger 单调自增防丢包序号。
+ *  - 本地绑定 7706 接收遥测 JSON；
+ *  - 向 C3:7705 下发控制指令，seq 采用 AtomicInteger 单调自增防丢包序号。
```

### P-02（X-02，Critical）C3 端发现应答线程 —— 整体函数替换

```python
# C3:selfdrive/carrot/amap_navi.py  替换 _discovery_responder_thread 全函数
  def _discovery_responder_thread(self):
    """响应车机端 UdpDeviceDiscovery 探针（bind 4210，兼容两种探针格式）。

    契约（以车机端 UdpDeviceDiscovery.kt 为准）：
      探针: {"cmd":"discover","port":5510}  或  字节串 b"c3_ping"
      回包: {"resp":"c3_pong","ip":<本机IP>,"device_id":"c3","auth":true}
      回包目标: 报文源地址 addr[0]:addr[1]（绝不可硬编码端口）
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
      s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
      try:
        s.bind(('0.0.0.0', self.broadcast_port))  # 4210，与车机探针目标一致
      except Exception as e:
        print(f"Discovery bind {self.broadcast_port} error: {e}")
        raise  # 让进程退出，由 manager 重启并上报，避免"线程静默死亡"

      while True:
        try:
          data, addr = s.recvfrom(256)
          is_probe = (b"c3_ping" in data) or (b'"discover"' in data)
          if not is_probe:
            continue
          ip = addr[0]
          resp = json.dumps({
            "resp": "c3_pong",
            "ip": self.navi_get_local_ip() or ip,
            "device_id": "c3",
            "auth": True,
          }).encode('utf-8')
          s.sendto(resp, (ip, addr[1]))       # 回源端口，不硬编码 5510
          # 只有"被车机主动探针确认"才锁定 IP，且加租约
          self.shared_data.app_ip = ip
          self.shared_data.app_ip_ts = time.time()
          with lock:
            self.clients.setdefault(ip, {})
            self.clients[ip].update({
              "last_seen": time.time(),        # 必须与 _clean_clients_thread 同键名
              "device": "navi",
              "port": self.broadcast_port,
            })
        except Exception as e:
          print(f"Discovery responder error: {e}")
          time.sleep(0.2)
```

> 配套：`SharedData.__init__` 增加 `self.app_ip_ts = 0.0`；消费处加租约判据
> `if self.shared_data.app_ip and (time.time() - self.shared_data.app_ip_ts) < 30.0:`。

### P-03（X-03，Critical）车机端指令报文补齐 —— 复制即用

```diff
--- a/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/udp/CarrotUdpClient.kt
+++ b/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/udp/CarrotUdpClient.kt
@@ -104,13 +104,18 @@
     /**
      * 下发控制指令。cmd 可选 "LANECHANGE" / "SPEED_LIMIT" / "CANCEL_LANE_CHANGE"。
      */
-    fun sendControlCommand(cmd: String, action: LaneAction, vCruise: Int) {
+    fun sendControlCommand(
+        cmd: String,
+        action: LaneAction,
+        vCruise: Int,
+        overtakeMode: Int = 1   // 0:激进 1:常规 2:保守
+    ) {
         val json = JSONObject().apply {
             put("cmd", cmd)
-            put("direction", action.code)
-            put("index", sequenceId.getAndIncrement())
+            put("arg", action.code)          // C3 实际读取的键（LEFT/RIGHT/KEEP）
+            put("direction", action.code)    // 兼容旧键，可选保留
+            put("param", overtakeMode)       // 三级超车模式下发通道
+            put("seq", sequenceId.getAndIncrement())   // C3 契约键
+            put("index", sequenceId.get())             // 兼容旧键
             put("v_cruise", vCruise)
             put("blinker", action.blinker)
             put("timestamp", System.currentTimeMillis())
         }
```

### P-04（X-04 + C-03，Critical）C3 进程模型收敛 —— 撤回双实例

```diff
--- a/system/manager/process_config.py
+++ b/system/manager/process_config.py
@@ -141,7 +141,8 @@ procs = [
   PythonProcess("fleet_manager", "selfdrive.frogpilot.fleetmanager.fleet_manager", check_fleet),
   PythonProcess("carrot_man", "selfdrive.carrot.carrot_man", always_run),#, enabled=not PC),
   #PythonProcess("auto_overtake", "selfdrive.carrot.auto_overtake", always_run),#, enabled=not PC),
-  PythonProcess("amap_navi", "selfdrive.carrot.amap_navi", always_run),
+  # amap_navi 的 UDP/发布者已由 carrot_man 内嵌实例独占（carrot_man.py:191 -> AmapNaviServ()）
+  # 双进程会触发 msgq MultiplePublishersError 与 UDP 双 bind 竞态，故保持禁用
+  #PythonProcess("amap_navi", "selfdrive.carrot.amap_navi", always_run),
   #PythonProcess("lane", "selfdrive.carrot.lane", check_lane and only_onroad),
```

若必须保留独立进程（方案 b），则删除内嵌并加兜底：

```diff
--- a/selfdrive/carrot/carrot_man.py
+++ b/selfdrive/carrot/carrot_man.py
@@ -188,7 +188,10 @@
 class CarrotMan:
   def __init__(self):
-    self.amap_navi = AmapNaviServ()
+    # 单一所有者：独立 amap_navi 进程运行时，本进程不再构造实例
+    from openpilot.common.params import Params as _P
+    self.amap_navi = None if _P().get_bool("AmapNaviStandalone") else AmapNaviServ()
```

> 注：`self.amap_navi` 的所有下游访问（`carrot_man.py:330-345` 等）必须同步做 `None` 保护，否则引入 NPE 等价崩溃——这也是我**推荐方案 (a)** 的原因。

### P-05（X-05，Critical）C3 端 TTC 计算修正 —— 整体替换

```python
# C3:selfdrive/carrot/amap_navi.py  替换 public_amap_navi 中 TTC 计算段
    # ---- 后车时距（方向化 + 绝对值化 + 有效性门禁） ----
    # 单位：drel 为 mm 且后方为负；vrel 为 m/s 且逼近为负
    def _rear_ttc(drel_mm, vrel_mps):
      if drel_mm is None or vrel_mps is None:
        return 0.0                      # 无数据 -> 0.0 表示"不可用"，消费端按阻断处理
      if vrel_mps >= -0.1:              # 不逼近（并排/远离）
        return 99.0
      return abs(drel_mm) / 1000.0 / max(-vrel_mps, 0.1)

    left_ttc = _rear_ttc(self.shared_data.main_lb_drel, self.shared_data.lb_vrel)
    right_ttc = _rear_ttc(self.shared_data.main_rb_drel, self.shared_data.rb_vrel)
    self.shared_data.behind_ttc_left = left_ttc
    self.shared_data.behind_ttc_right = right_ttc
    # 广播语义：取两侧较小者（保守），供 HUD 显示
    self.shared_data.behind_ttc = min(left_ttc, right_ttc)

    msg.amapNavi.overtakeMode = int(self.shared_data.overtake_mode) if self.shared_data.overtake_mode in (0, 1, 2) else 1
    msg.amapNavi.lidarBehindVdistTime = float(self.shared_data.behind_ttc)
    msg.amapNavi.leftRearTtcValid = left_ttc > 0.0
    msg.amapNavi.rightRearTtcValid = right_ttc > 0.0
```

```diff
--- a/cereal/custom.capnp
+++ b/cereal/custom.capnp
@@
 	overtakeMode @15 : Int32;
 	lidarBehindVdistTime @16 : Float32;
+	leftRearTtcValid @17 : Bool;
+	rightRearTtcValid @18 : Bool;
 }
```

### P-06（X-05 + X-06 + C-06，Critical）C3 端变道门禁 —— 替换 `desire_helper.py` 冲突块

```python
# C3:selfdrive/controls/lib/desire_helper.py
# 1) 在 DesireHelper.__init__ 增加：
    self.rear_block_latched = False

# 2) 新方法（放在 update 之前）：
  def _rear_ttc_block(self, amapNavi, blinker_state, fresh):
    """后车逼近刚性门禁。失效即阻断（fail-safe）。"""
    if not fresh:
      return True                                   # 遥测不新鲜 -> 阻断
    mode = amapNavi.overtakeMode
    thr = {0: 1.8, 1: 2.5, 2: 3.5}.get(mode, 2.5)   # 非法值 -> 常规
    if blinker_state == BLINKER_LEFT:
      ttc, valid = amapNavi.lidarBehindVdistTime, amapNavi.leftRearTtcValid
    else:
      ttc, valid = amapNavi.lidarBehindVdistTime, amapNavi.rightRearTtcValid
    if not valid:
      return True                                   # 传感器不可用 -> 阻断
    return not (ttc > thr)                          # 0/负/NaN/超门限 -> 阻断

# 3) 替换 919-941 原冲突块为：
    if self.carrot_lane_change_count > 0:
      auto_lane_change_blocked = False
      fresh = (time.monotonic() - self.sm.recv_time['amapNavi']) < 0.5
      rear_block = self._rear_ttc_block(amapNavi, self.carrot_blinker_state, fresh)
      if rear_block:
        auto_lane_change_trigger = False
        auto_lane_change_trigger_no_bsd = False   # 保留 bsd 上报语义见注释
        if (self.frame % int(2.0 / DT_MDL)) == 0:
          self.lane_change_audio(True, 12, 0)     # 新增"后方来车过快"语音
      else:
        auto_lane_change_trigger = lane_change_available and not side_object_detected
        auto_lane_change_trigger_no_bsd = lane_change_available
      self.rear_block_latched = rear_block
    else:
      # 计数器衰减但门禁仍在：只要仍在变道流程内就继续复检
      self.rear_block_latched = self._rear_ttc_block(
        amapNavi, self.blinker_state,
        (time.monotonic() - self.sm.recv_time['amapNavi']) < 0.5
      ) if self.lane_change_state != LaneChangeState.off else False

# 4) 在 laneChangeStarting 分支（约 1213 行）加入中止：
      if self.rear_block_latched:
        self.lane_change_state = LaneChangeState.off
        self.lane_change_direction = LaneChangeDirection.none
        self.trigger_name = "rear ttc abort"
        self.lane_change_audio(True, 12, 0)
```

```python
# C3:selfdrive/carrot/amap_navi.py  _update_command 整体替换（X-03 + X-06）
  def _update_command(self, json_obj, ip):
    with lock:
      if "index" in json_obj:
        self.shared_data.cmd_index = int(json_obj.get("index"))
      elif "seq" in json_obj:
        self.shared_data.cmd_index = int(json_obj.get("seq"))

      if "cmd" in json_obj:
        cmd = json_obj.get("cmd")
        # 撤销指令必须有明确语义，否则车机的紧急撤销在 C3 侧无效
        self.shared_data.remote_cmd = "CANCEL" if cmd == "CANCEL_LANE_CHANGE" else cmd
        self.shared_data.remote_arg = json_obj.get("arg", json_obj.get("direction"))

      # 三级超车模式：仅在明确携带 param 且取值合法时更新
      param = json_obj.get("param", None)
      if param is not None:
        try:
          v = int(param)
        except (TypeError, ValueError):
          v = None
        if v in (0, 1, 2):
          self.shared_data.overtake_mode = v
```

```python
# C3:selfdrive/carrot/ccarrot_man.py 化指令 -> 撤销通道（紧随 340-345）
      if self.carrot_serv.carrotCmd == "CANCEL":
        self.carrot_serv.carrotCmd = "LANECHANGE"
        self.carrot_serv.carrotArg = "CANCEL"
```

### P-07（H-01，Critical）车机端净空门禁量纲修正 —— 整体函数替换

```kotlin
// HU:domain/safety/LateralSafetyEvaluator.kt
    fun evaluateSide(action: LaneAction, car: CarState, isTargetSolid: Boolean): SafetyAuditResult {
        if (action == LaneAction.KEEP) {
            return SafetyAuditResult(false, BlockCause.NO_TARGET_LANE, reasonDesc = "未指定目标车道")
        }

        // 1. 标线准入
        if (isTargetSolid) {
            return SafetyAuditResult(false, BlockCause.SOLID_LINE, isSolidBlocked = true,
                reasonDesc = "侧向为实线或禁行标线，禁止变道")
        }

        // 2. 毫米波盲区
        val bsdAlarm = if (action == LaneAction.LEFT) car.leftBlindspot else car.rightBlindspot
        if (bsdAlarm) {
            return SafetyAuditResult(false, BlockCause.BSD_ALARM, isBsdBlocked = true,
                reasonDesc = "毫米波雷达盲区有车")
        }

        // 3. 激光雷达盲区
        val lidarBlind = if (action == LaneAction.LEFT) car.lidarLeftRearBlind else car.lidarRightRearBlind
        if (lidarBlind) {
            return SafetyAuditResult(false, BlockCause.LIDAR_HAZARD, isLidarBlocked = true,
                reasonDesc = "激光雷达侧后盲区报警")
        }

        // 4. 动态净空（单位统一为米；无数据即阻断）
        //    C3 上报 lb_drel/rb_drel 单位为 mm 且后方为负，必须 abs + /1000
        val rawMm = if (action == LaneAction.LEFT) car.leftRearDistance else car.rightRearDistance
        if (!car.hasRearDistance) {   // 解析器置位：本次报文是否真的带来了 lb_drel/rb_drel
            return SafetyAuditResult(false, BlockCause.LIDAR_HAZARD, isLidarBlocked = true,
                reasonDesc = "侧后方测距缺失，安全起见禁止变道")
        }
        val rearDistanceM = Math.abs(rawMm) / 1000f
        val requiredDistance = Math.max(minStaticClearanceM, (car.vEgo / 3.6f) * minSafeTimeHeadway)
        if (rearDistanceM < requiredDistance) {
            return SafetyAuditResult(false, BlockCause.LIDAR_HAZARD, isLidarBlocked = true,
                reasonDesc = "侧后方车距过近(实际:${formatDistance(rearDistanceM)}m < 门限:${formatDistance(requiredDistance)}m)")
        }

        return SafetyAuditResult(true, BlockCause.NONE, reasonDesc = "侧向安全，允许变道")
    }
```

```diff
--- a/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/core/model/CarState.kt
+++ b/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/core/model/CarState.kt
@@
-    val leftRearDistance: Float = 999f,     // 激光雷达测得左后方车辆距离 (米)
-    val rightRearDistance: Float = 999f,    // 激光雷达测得右后方车辆距离 (米)
+    val leftRearDistance: Float = 0f,       // 左后方车距 (mm, 后方为负) — 与 C3 报文单位一致
+    val rightRearDistance: Float = 0f,      // 右后方车距 (mm, 后方为负)
+    val hasRearDistance: Boolean = false,   // 本帧是否携带了有效侧后测距
```

解析器同步：`leftRearDistance = fastGetFloat(payload, "lb_drel", 0f)`，并 `hasRearDistance = payload.contains("\"lb_drel\":") || payload.contains("\"rb_drel\":")`（零分配实现见 P-10）。

### P-08（H-02，X-03，Major）车机端参数全量绑定 + 超车模式下发

```kotlin
// HU:data/prefs/UserSettingsRepository.kt
    private fun loadOvertakeSettings(): OvertakeSettings = OvertakeSettings(
        enabled = prefs.getBoolean(KEY_OVERTAKE_ENABLED, true),
        minEngageSpeedKmh = prefs.getInt("overtake_min_speed_kmh", 60),
        prepareBlinkMs = prefs.getInt("overtake_prepare_blink_ms", 1200).toLong(),
        standardCooldownMs = prefs.getInt(KEY_REVERSE_COOLDOWN_S, 20) * 1000L,
        interruptCooldownMs = prefs.getInt("overtake_interrupt_cooldown_s", 60) * 1000L,
        telemetryTimeoutMs = prefs.getInt("overtake_telemetry_timeout_ms", 1000).toLong(),
        executeTimeoutMs = prefs.getInt("overtake_execute_timeout_ms", 4500).toLong(),
        driverSteerThresholdDeg = prefs.getInt("overtake_steer_threshold_deg", 25).toFloat(),
        allowRightOvertake = prefs.getBoolean("allow_right_overtake", false)
    )

    /** 任何写操作后统一刷新缓存（原实现只在两个 key 上刷新） */
    private fun reload() { cachedOvertakeSettings = loadOvertakeSettings() }

    fun setBoolean(key: String, value: Boolean) { prefs.edit().putBoolean(key, value).apply(); reload() }
    fun setInt(key: String, value: Int)         { prefs.edit().putInt(key, value).apply(); reload() }
    fun setFloat(key: String, value: Float)     { prefs.edit().putFloat(key, value).apply(); reload() }
    fun getOvertakeMode(): Int = prefs.getInt(KEY_OVERTAKE_MODE, 1).coerceIn(0, 2)
```

`RelayEngine` 中把模式带给 C3：

```diff
--- a/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/relay/RelayEngine.kt
@@
         onControlCommand = { action, vCruise ->
-            udpClient.sendControlCommand(LANE_CHANGE_COMMAND, action, vCruise)
+            udpClient.sendControlCommand(
+                LANE_CHANGE_COMMAND, action, vCruise,
+                overtakeMode = settingsRepository.getOvertakeMode()
+            )
         },
         onCancelCommand = { action ->
             udpClient.sendControlCommand(CANCEL_COMMAND, action, 0)
         },
```

### P-09（H-03，Major）把决策移出收包协程 + 消灭每 tick 分配

```kotlin
// HU:data/relay/RelayEngine.kt
    // 单线程决策调度器：收包协程只投递最新帧，绝不在此做决策
    private val decisionScope = CoroutineScope(SupervisorJob() + Dispatchers.Default.limitedParallelism(1))
    private val latestFrame = MutableStateFlow<CarState?>(null)

    private fun onTelemetry(payload: String) {
        latestFrame.value = CarrotTelemetryParser.parse(payload)   // 解析仍在收包线程（快）
    }

    private fun startDecisionLoop() {
        decisionScope.launch {
            latestFrame.collect { car ->
                if (car == null) return@collect
                val navi = decoder.naviStateFlow.value
                _carStateFlow.value = car
                _overtakeStatusFlow.value = stateMachine.tick(car, navi, settingsRepository.settings)
                updateRampSpeed(car, navi)
            }
        }
    }
```

`stateMachine.message` 改为常量表（节选）：

```kotlin
// HU:domain/decision/OvertakeStateMachine.kt
    private val MSG_IDLE = "待机"
    private val MSG_NOT_ENGAGED = "智驾未接管，禁止发起超车"
    private val MSG_NOT_HIGHWAY = "当前非高速路段，禁止自主超车"
    // snapshot() 内不再使用字符串模板；需要动态数字时改为「数字写入独立 TextView」
```

### P-10（H-04，Major）真正的零分配解析器（ByteArray 级）

```kotlin
// HU:data/udp/CarrotTelemetryParser.kt —— 新增，完全避免 String/substring
object CarrotTelemetryParserFast {
    /** 直接在 UDP 载荷字节上扫描；不产生任何中间对象。 */
    fun parse(buf: ByteArray, len: Int, out: MutableCarState) {
        out.reset()
        var i = 0
        while (i < len) {
            if (buf[i] != '"'.code.toByte()) { i++; continue }
            val keyStart = i + 1
            var j = keyStart
            while (j < len && buf[j] != '"'.code.toByte()) j++
            if (j >= len) return
            val keyLen = j - keyStart
            var k = j + 1
            while (k < len && (buf[k] == ' '.code.toByte() || buf[k] == ':'.code.toByte())) k++
            when {
                byteEq(buf, keyStart, keyLen, "v_ego_kph") -> { out.vEgo = readInt(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "steer_angle") -> { out.steerAngle = readFloat(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "drel") -> { out.drel = readFloat(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "lb_drel") -> { out.leftRearDistance = readFloat(buf, k, len); out.hasRearDistance = true }
                byteEq(buf, keyStart, keyLen, "rb_drel") -> { out.rightRearDistance = readFloat(buf, k, len); out.hasRearDistance = true }
                byteEq(buf, keyStart, keyLen, "lidar_lbblind") -> { out.lidarLeftRearBlind = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "lidar_rbblind") -> { out.lidarRightRearBlind = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "left_blindspot") -> { out.leftBlindspot = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "right_blindspot") -> { out.rightBlindspot = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "lead1") -> { out.lead1 = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "atc_state") -> { out.atcState = readInt(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "IsOnroad") -> { out.isOnroad = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "engaged") -> { out.engaged = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "v_cruise_kph") -> { out.vCruise = readInt(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "brake_press") -> { out.brakePress = readBool(buf, k, len) }
                byteEq(buf, keyStart, keyLen, "gas_press") -> { out.gasPress = readBool(buf, k, len) }
            }
            i = k
        }
        out.timestamp = System.currentTimeMillis()
    }

    private fun byteEq(buf: ByteArray, off: Int, len: Int, key: String): Boolean {
        if (len != key.length) return false
        for (t in 0 until len) if (buf[off + t] != key[t].code.toByte()) return false
        return true
    }
    private fun readInt(buf: ByteArray, start: Int, len: Int): Int {
        var i = start; var sign = 1; var v = 0; var any = false
        if (i < len && buf[i] == '-'.code.toByte()) { sign = -1; i++ }
        while (i < len) { val c = buf[i].toInt(); if (c < 48 || c > 57) break; v = v * 10 + (c - 48); i++; any = true }
        return if (any) v * sign else 0
    }
    private fun readFloat(buf: ByteArray, start: Int, len: Int): Float { /* 同上 + 小数位累加，返回 Float（不装箱） */ }
    private fun readBool(buf: ByteArray, start: Int, len: Int): Boolean =
        start < len && (buf[start] == 't'.code.toByte() || buf[start] == '1'.code.toByte())
}
```

> `CarrotUdpClient` 的 `receive` 改为把 `packet.data`/`packet.length` 直接交给该解析器（**不再构造 String**），`payload` 参数保留给调试日志开关。

### P-11（H-05，Major）HUD 渲染节流 + 去 emoji

```kotlin
// HU:ui/main/MainActivity.kt
    private var lastRenderMs = 0L
    private val RENDER_MIN_INTERVAL_MS = 100L   // 10Hz 足够肉眼"跟手"，i.MX6 上省 60% 绘制

    private fun renderCar(car: CarState) {
        val now = System.currentTimeMillis()
        if (now - lastRenderMs < RENDER_MIN_INTERVAL_MS) { currentCar = car; return }
        lastRenderMs = now
        currentCar = car
        if (car.vEgo != lastVego) { lastVego = car.vEgo; tvSpeed.text = car.vEgo.toString() }
        // ……其余字段同样先比后写
    }

    // 信号灯徽章：去掉 🚦 / 🟢（Android 4.4 NotoColorEmoji 无 U+1F6A6 / U+1F7E2 字形 → 豆腐块）
    tvLight.text = when {
        navi.trafficLightStatus == 1 && navi.trafficLightSeconds > 0 -> "红灯 ${navi.trafficLightSeconds}s"
        navi.trafficLightStatus == 2 && navi.trafficLightSeconds > 0 -> "绿灯 ${navi.trafficLightSeconds}s"
        else -> "路口无信号灯"
    }
```

### P-12（H-06，Major）执行超时不再"按完成结算"

```diff
--- a/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/domain/decision/OvertakeStateMachine.kt
+++ b/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/domain/decision/OvertakeStateMachine.kt
@@
         if (now - stateSinceMs > settings.executeTimeoutMs) {
-            state = OvertakeState.FINISHING
-            stateSinceMs = now
-            message = "变道执行超时 ${settings.executeTimeoutMs}ms，按完成结算"
+            // 未收到完成反馈（C3 当前不上报 atc_state）时，绝不能假定成功
+            onCancelCommand(candidate)
+            onSound(SoundEvent.LANE_CHANGE_CANCEL)
+            cooldownUntilMs = now + settings.interruptCooldownMs
+            state = OvertakeState.COOLDOWN
+            stateSinceMs = now
+            blockCause = BlockCause.DRIVER_OVERRIDE
+            message = "变道执行超时 ${settings.executeTimeoutMs}ms 且未收到完成反馈，已撤销并锁定 ${settings.interruptCooldownMs / 1000L} 秒"
+            return
         }
```

### P-13 ~ P-16（H-07 ~ H-10，Minor/Suggestion）

```diff
--- a/AmapNavi-Reborn/app/build.gradle
+++ b/AmapNavi-Reborn/app/build.gradle
@@
         release {
-            minifyEnabled false
+            minifyEnabled true
             proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
+            // 保留 Kotlin 元数据与 Parcelable，避免 Dalvik 上反射失败
+            // proguard-rules.pro 需含: -keep class kotlin.Metadata { *; }  -keepclassmembers class * implements android.os.Parcelable
         }
```

```diff
--- a/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/ui/main/MainActivity.kt
+++ b/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/ui/main/MainActivity.kt
@@
     override fun onBackPressed() {
         if (layoutSettingsOverlay?.visibility == View.VISIBLE) {
             layoutSettingsOverlay?.visibility = View.GONE
         } else {
-            super.onBackPressed()
+            // 车机场景：退到后台保活，而不是销毁主界面
+            moveTaskToBack(true)
         }
     }
```

```diff
--- a/AmapNavi-Reborn/app/src/main/AndroidManifest.xml
+++ b/AmapNavi-Reborn/app/src/main/AndroidManifest.xml
@@
         <activity
             android:name=".ui.setting.SettingActivity"
-            android:exported="true"
+            android:exported="false"
             android:windowSoftInputMode="stateHidden|adjustPan"
             android:configChanges="orientation|screenSize|keyboardHidden"
             android:launchMode="singleTask"
             android:screenOrientation="unspecified">
-            <intent-filter>
-                <action android:name="android.intent.action.VIEW" />
-                <category android:name="android.intent.category.DEFAULT" />
-            </intent-filter>
         </activity>
         <!-- NavSettingActivity / OvertakeSettingActivity / LogManagerActivity / UdpDeviceActivity 同样处理 -->
```

```kotlin
// HU:service/KeepAliveService.kt
    private var cachedNotification: Notification? = null
    private fun buildNotification(): Notification = cachedNotification ?: NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(R.drawable.ic_stat_relay)   // 单色状态栏图标，勿用彩色启动图
        .setContentTitle("AmapNavi 协同中继")
        .setContentText("高德导航与 C3 实时桥接运行中")
        .setOngoing(true)
        .setContentIntent(contentIntent())
        .build().also { cachedNotification = it }
```

### P-17（C-01，Critical）C3 清理线程修复

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
   def _clean_clients_thread(self):
     while True:
-      now = time.time()
-      with lock:
-        # 保留活跃客户端
-        active_clients = {ip: info for ip, info in self.clients.items() if now - info["last_seen"] < 1.0}
+      try:
+        now = time.time()
+        with lock:
+          # 保留活跃客户端：用 .get 兜底，兼容历史记录缺键（发现线程曾写 last_time）
+          active_clients = {
+            ip: info for ip, info in self.clients.items()
+            if now - info.get("last_seen", info.get("last_time", 0.0)) < 1.0
+          }
+          self.clients = active_clients
+      except Exception as e:
+        print(f"_clean_clients_thread error: {e}")   # 绝不让线程静默死亡
+        continue
```

### P-18（C-02，Major）驾驶员接管条件修正

```diff
--- a/selfdrive/controls/lib/desire_helper.py
+++ b/selfdrive/controls/lib/desire_helper.py
@@
-    steering_pressed = carstate.steeringPressed and \
-                     ((carstate.steeringTorque < 0 and blinker_state == BLINKER_LEFT) or (carstate.steeringTorque > 0 and blinker_state == BLINKER_RIGHT))
+    # 人类绝对优先：任何方向的方向盘介入都立即退出变道（不附加方向条件）
+    steering_pressed = carstate.steeringPressed
     if steering_pressed and self.lane_change_state != LaneChangeState.off:
       self.lane_change_direction = LaneChangeDirection.none
       self.lane_change_state = LaneChangeState.off
       self.blinker_ignore = True
       print("---steering_pressed, set LaneChangeState.off")
       if atc_desire_enabled:
         self.atc_cancel = True
-        self.atc_cancel_delay = int(2.0 / DT_MDL)
-        #self.lane_change_audio(True, 4, 0)
+        self.atc_cancel_delay = 0            # 立即播报，不再等 2 秒
+        self.lane_change_audio(True, 4, 0)
```

### P-19（C-04，Major）遥测 schema 对齐

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-        if self.shared_data.break_press is not None:
-          msg["break_press"] = self.shared_data.break_press
+        if self.shared_data.break_press is not None:
+          msg["brake_press"] = self.shared_data.break_press   # 与车机解析器键名一致（原为错拼 break_press）
@@
+      # 后车时距（与 cereal 同源），供车机 HUD 与本地门禁交叉校验
+      msg["lidar_behind_vdist_time"] = float(self.shared_data.behind_ttc)
+      msg["lidar_lbblind"] = bool(self.shared_data.lidar_lbblind)
+      msg["lidar_rbblind"] = bool(self.shared_data.lidar_rbblind)
+      msg["atc_state"] = int(self.shared_data.atc_state)      # 由 carrot_man 从 desire 状态回填，见 P-12 备注
```

```diff
# 去掉同一报文的三份重复投递，只保留"目标车机单播"
-                        sock.sendto(navi_dat, (ip, port))
-                        sock.sendto(navi_dat, (ip, self.navi_port))
-                        if self.shared_data.app_ip and self.shared_data.app_ip != ip:
-                          sock.sendto(navi_dat, (self.shared_data.app_ip, self.navi_port))
+                        target_ip = self.shared_data.app_ip or ip
+                        sock.sendto(navi_dat, (target_ip, self.navi_port))
```

### P-20（C-05，Major）capnp 生成物同步

```bash
# 在 C3 上执行（构建机）
cd /data/openpilot
scons -j4 cereal/gen/cpp/custom.capnp.h      # 或完整 scons 构建
git add cereal/gen/cpp/custom.capnp.h cereal/gen/cpp/custom.capnp.c++
# 校验：新结构应为 9 个 data word
grep -n "CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d" cereal/gen/cpp/custom.capnp.h
# 期望输出: (aedffd8f31e7b55d, 9, 0)   ← 当前为 8，说明未重生成
```

### P-21（C-07，Major）补库斯途力矩映射

```diff
--- a/opendbc_repo/opendbc/car/torque_data/substitute.toml
+++ b/opendbc_repo/opendbc/car/torque_data/substitute.toml
@@
 "HYUNDAI_TUCSON" = "HYUNDAI_SANTA_FE"
+"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"   # 3.055m 轴距 / 1.7-2.2t，沿用大车 NNFF
 "HYUNDAI_SANTA_FE_2022" = "HYUNDAI_SANTA_FE_HEV_2022"
```

> 前置检查：`HYUNDAI_PALISADE` 必须存在于 `opendbc/car/torque_data/neural_feedforward_params/` 或 `torque_data/lateral/`，否则 `substitute` 会回退并在启动日志报错——**必须实机确认后再合并**。

### P-22 / P-23（C-08 / C-09，文档据实修正，无需改代码）

- `interface.py:202` 的 `ret.startAccel = 1.0` 属全局 Hyundai 行为：若确实需要库斯途专属，加
  `if candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN: ret.startAccel = 1.0; ret.longitudinalActuatorDelay = 0.5`；
  否则文档删除"库斯途专属"表述。
- "5.0 s S 曲线 / ≤0.08g / jerk ≤0.05g·s⁻¹"：请提供 `file:line`；本轮全量检索 `desire_helper.py` 未见对应实现（`LANE_CHANGE_TIME_MAX = 10.0` 仅为超时上限）。

---

## 四、极端边缘工况推演与反例压力测试 (Stress Tests)

### 场景 A：高负荷内存极限 —— 复杂立交三维渲染中收到遥测风暴 + 立即挂 R 挡

**推演**：高德占 209MB，车机可用约 350MB。伴侣应用侧，`CarrotUdpClient` 每包 `String`+20 次 `substring`（H-04）、`RelayEngine` 每包 `CarState` + 每 tick 一个 `OvertakeStatus`（H-03）、`MainActivity` 每次 emission 约 18 次 `setText/format`（H-05）。50Hz × 上述分配量 ≈ 数千次/秒的 Dalvik 分配 → 堆频繁触顶 → `GC_FOR_ALLOC` 连续 STW（30-80ms/次，可能连发）。挂 R 挡瞬间，系统需在 0.5s 内起 `reverse_service` 并分配显示缓冲；若恰逢 Dalvik 连续 GC 或 LMK 抖动，倒车影像出现 2-3s 黑屏的**概率显著上升**。
**结论**：文档声称的"零 GC + 3.5MB 常驻"在代码层不成立；R 挡红线在"导航 + 遥测风暴 + 挂倒挡"叠加工况下**无工程保证**。
**验证方法（实机）**：`adb shell dumpsys meminfo tech.touka.amapnavi` 连续采样 10 分钟 + `adb logcat | grep -i "GC_FOR_ALLOC"` 统计频次，同时在挂 R 挡瞬间抓 `dumpsys SurfaceFlinger` 首帧时间。

### 场景 B：高速断网 + 变道执行中 + 后方快车

**推演**：
1. 车机侧 `OvertakeStateMachine.tick` 的看门狗（`isTelemetryFresh(now, 1000ms)`）在 1s 后触发，状态回 `IDLE`，并**尝试发 `CANCEL_LANE_CHANGE`**；
2. 但 X-01（同向端口）意味着 C3 **收不到任何指令**；X-03/X-06 意味着即使收到也只写入 `remote_cmd`，`desire_helper` 不识别 `CANCEL_LANE_CHANGE`；
3. C3 侧的 `carrot_lane_change_count` 从 400 帧（20s）自然衰减，期间 `desire_helper.py:505-524` 分支持续评估并可能继续完成变道；
4. 同时后车 TTC 门禁因 X-05（负距离 → `0<ttc` 恒假）**永不阻断**。
**结论**：断网后 **C3 侧没有任何"外部撤销"通道，也没有有效的后车门禁**，剩下唯一的兜底是驾驶员打方向盘（且 C-02 显示该条件还被"反向"限制）。文档 §5.2"绝无非预期转向"不成立。
**验证方法**：台架断开 Wi-Fi，在 `desire_helper` 打印 `lane_change_state / trigger_name / carrot_lane_change_count`，确认 20s 内的状态迁移与是否仍会 `laneChangeStarting`。

### 场景 C：雨雪污损导致激光雷达点云跳变（TTC 99s → 0.1s → 99s）

**推演**：
- **车机侧**：`LateralSafetyEvaluator` 用 `lb_drel` 与米制门限比较（H-01）。跳变到 `-8000mm` 时 → `-8000 < 55` → 阻断（"误刹车式"过度阻断，变道功能彻底不可用）；跳变到缺帧 → `hasRearDistance=false`（P-07 后）→ 阻断；旧代码则用 `999f` → 放行。**两种状态之间没有任何迟滞/消抖**，会出现"变道按钮时灵时不灵"的抖动。
- **C3 侧**：`RadarSpeedEstimator` 有 `max_acc=4.0` 限幅与 `smooth_n=5` 滑动平均，**但左后速度用的是左前估计器**（X-05②），跳变会被写入错误实例并污染左前判定；`lb_vrel` 在 `-0.1` 边界反复穿越时，`ttc` 在 `99` 与 `几十` 之间跳变，配合 `0<ttc<thr` 恒假的现状，实际不产生任何阻断。
**结论**：传感器劣化工况既没有"保守阻断"的一致性，也没有"合理放行"的合理性 —— 属于典型的**无迟滞、无量纲校验、无有效性位**的安全函数。
**验证方法**：注入录制的污损点云序列（或直接以 JSON 重放 `lb_drel` 跳变序列），观测两端状态机是否有连续 N 帧（建议 N=3，即 150ms）确认机制。

---

## 五、实车部署与首次路测安全寄语 (Deployment Checklist)

1. **先做"三段连通闭环"，再谈任何功能。** 顺序：① `discover → c3_pong`（P-02）；② `遥测 → HUD` 只验 3 个字段（`v_ego_kph`/`left_blindspot`/`lidar_behind_vdist_time`）；③ `按钮 → C3 carrotMan.carrotCmd → desire.trigger_name`。每段都用 `ss -ulnp | grep -E '4210|7705|7706'` 确认**每个端口只有一个 owner**，并确认 manager 日志无 `MultiplePublishersError`（X-04）。**三段未全绿前禁止上路，哪怕只是"试一下变道"。**
2. **U 盘装 APK 后先验 Dalvik 兼容与内存红线。** 装机后立刻 `adb logcat | grep -E "VerifyError|NoClassDefFoundError|GC_FOR_ALLOC"`；再让高德进入导航 + 反复挂 R 挡 10 次，记录倒车影像首帧时间。**只要出现一次黑屏或 >1s 延迟，就不要继续路测**——这条红线比任何智驾功能都重要。（`MultiDexApplication` 引导与 `@RequiresApi(26)` 隔离这两个点目前是正确的，别在后续改动中破坏。）
3. **首次点火只测"不动作"**：ACC ON、不开智驾、不点超车，观察 HUD 是否稳定、C3 是否被误下发指令、车机是否发热/重启。确认"什么都不做时系统绝对安静"（尤其是 P-08 缓存刷新后参数不会自激下发）。
4. **首次路测把"后车门禁"当主角，而不是把"能变道"当成功标准。** 在封闭/车少的高速上，让后车以明显相对速度接近（或直接以日志重放方式注入 TTC 序列），**先验证它会阻断**；只有确认"该阻断时确实阻断"，才允许做一次真实变道。P-07 上线前，车机端净空门禁处于"恒阻断或恒放行"状态，等于没有门禁。
5. **全程留证**：车载热点侧录 UDP pcap、C3 侧保留 `rlog`、车机侧打开 `app_log`。任何一次"偶发不变道"，第一件事是确认当时**哪个进程持有 7705/7706**、以及 `overtakeMode/behind_ttc` 的实际数值——本工程的绝大多数故障都在这两个数字里。

---

## 六、附：判定汇总

| 端 | Critical | Major | Minor | Suggestion |
| :--- | :---: | :---: | :---: | :---: |
| 通信协同（X） | 5 | 1 | 0 | 0 |
| 车机端（H） | 1 | 5 | 3 | 1 |
| C3 端（C） | 1 | 6 | 2 | 0 |
| 文档/提示词（D） | 1 | 3 | 0 | 0 |
| **合计** | **8** | **15** | **5** | **1** |

**放行条件（缺一不可）**：X-01 修复并实测双端收发一次成功；X-04 进程模型冻结（单实例单发布者）；X-05 + P-06 门禁改为"失效即阻断 + 方向化 + 全阶段复检"；H-01 量纲修正；H-02 参数真实生效；文档 D-01~D-04 据实重写。

---

**本报告为独立审计意见，未修改任何工程文件；所有结论均可在上述 `file:line` 复核。**
