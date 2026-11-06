# openpilot-ck89757 代码全面分析报告

> **分析对象**：`E:\code\openpilot-ck89757`（openpilot carrot 分支 `carrot_v260815` + `cp-custo-amap` 库斯途定制层）
> **基线 commit**：`32c2144`（分析期间仓库从 `70ba3d8` 推进到该 HEAD，本文结论以 `32c2144` 为准）
> **分析日期**：2026-11-03
> **车辆背景**：北京现代库斯途（HYUNDAI_CUSTIN_1ST_GEN），1.5T/2.0T + 8AT，整备质量 1754kg / 满载约 2300kg，轴距 3055mm，hyundai_k 500kbps CAN；与车机端 AmapNavi-Reborn 通过 UDP 协同（C3 发遥测 → 车机:7706，车机发指令 → C3:7705）

---

## 一、项目结构与定制层地图

| 文件 | 规模 | 职责 |
|---|---|---|
| `selfdrive/carrot/amap_navi.py` | 2125 行 | UDP 通信枢纽：设备发现(4210/5510)、外接激光雷达/摄像头接入(4211/4213)、后向 TTC 计算、遥测下发(7706)、指令接收(7705)、cereal `amapNavi` 消息发布 |
| `selfdrive/carrot/carrot_man.py` | ~1100 行 | 主控进程：内嵌 AmapNaviServ，10Hz 主循环消费车况+导航，弯道速度 `carrot_curve_speed`，发布 `carrotMan` 消息；内嵌 Web 配置服务(8088) 与 ZMQ 调试线程 |
| `selfdrive/carrot/carrot_serv.py` | ~2000 行 | 导航决策核心：高德事件→ATC 命令映射、匝道/限速/弯道目标速度、红绿灯状态机、e2e 减速 |
| `selfdrive/carrot/carrot_functions.py` | ~600 行 | 纵向规划消费端：`stop_distance`/`actual_stop_distance` 计算、红绿灯锁零、巡航限速合成 |
| `selfdrive/carrot/lane.py` | ~350 行 | ATC 变道执行进程（onroad 独立进程） |
| `selfdrive/carrot/config.py` | 333 行 | UnifiedParams：Params 与 nav_params.json 双源参数同步 |
| `selfdrive/carrot/web_interface.py` | ~300 行 | HTTP 参数配置服务（0.0.0.0:8088） |
| `selfdrive/controls/lib/desire_helper.py` | 定制段 | TTC 变道门禁、overtake_mode 三级阈值、盲区融合阻断 |
| `opendbc_repo/.../hyundai/*` | 定制点 | CUSTIN 指纹/平台定义/LFAHDA_MFC 报文 |

进程拓扑已核实（[process_config.py:142-146](file:///E:/code/openpilot-ck89757/system/manager/process_config.py#L142-L146)）：`carrot_man` 单进程内嵌 AmapNaviServ，`amap_navi` 独立进程已注释（避免双实例 UDP 端口竞争），`lane` 为 onroad 独立进程。

---

## 二、P0 级问题（安全红线，建议立即处理）

### P0-1 UDP 远程命令执行后门（RCE）
[amap_navi.py:842-857](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L842-L857)：
```python
elif 'echo_cmd' in json_obj:
    result = subprocess.run(json_obj['echo_cmd'], shell=True, capture_output=True, text=False)
```
- C3 监听 `0.0.0.0:4213`，**局域网内任何设备**发送 `{"echo_cmd": "<任意 shell 命令>"}` 即可以 root（openpilot 系统默认 root）执行任意命令，无任何鉴权、白名单或来源校验。
- `euc-kr` 解码兜底（L850）表明这是韩国 carrot 上游遗留的调试后门，随 fork 一并继承。
- **建议**：整段删除。若需远程调试，改为带 token 鉴权 + 命令白名单的专用通道，且默认关闭。同端口的正常职责（车道线数据接收 L824-839）应拆到独立端口/处理分支。

### P0-2 Web 配置服务无鉴权暴露驾驶参数写接口
[web_interface.py:277](file:///E:/code/openpilot-ck89757/selfdrive/carrot/web_interface.py#L277)：`HTTPServer(('0.0.0.0', 8088))`，全库 grep 无 password/auth/token。
- `POST /nav_params`（L199-220）直接写 `UnifiedParams` → 影响匝道减速距离、盲区门限、变道冷却等**行车安全参数**。热点内任意设备（包括乘客手机上的恶意页面做 CSRF/端口扫描）可篡改。
- **建议**：绑定 127.0.0.1 + 走 SSH 隧道，或最低限度加一次性 token；写接口加"驻车挡才允许写入"的物理条件门禁。

### P0-3 后向 TTC 失效语义被改为 fail-open（未提交改动，需评审）
[amap_navi.py:299-307](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L299-L307)（工作区未提交 diff）：
```python
ttc = min(ttc_list) if ttc_list else (99.0 if sensor_ready else 0.0)
```
- 原逻辑：无逼近目标 → `0.0` 哨兵 → 消费端一律阻断（fail-safe）。
- 新逻辑：`sensor_ready` 时无目标 → `99.0` 放行变道（修 F-32-01 空车道误阻断）。
- **风险点**：`sensor_ready` 判定过弱——`lidar_l/lidar_r` 在线标志只表示设备 1 秒内发过**任何**包，不表示回波质量；而 `main_lb_drel`（[amap_navi.py:1159-1162](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L1159-L1162)）采用"消抖取旧值"策略**没有独立超时清零**（clients 字典里的 `lb_drel` 有 1 秒超时，`main_*` 没有），传感器被泥污遮挡后可能长期使用旧距离。目前仅靠 `RadarSpeedEstimator` 的 500ms 丢失超时（L48）让 `vrel→None` 间接兜底。
- **建议**：`main_*_drel/xrel` 增加 1 秒新鲜度戳（对齐 clients 超时逻辑）；`sensor_ready` 要求"最近 N 秒内至少一次有效回波 + 当前帧雷达心跳在线"；并在 `tests/test_ttc_and_lane_change_gating.py` 增加"传感器在线但持续无回波"用例锁死该语义。

### P0-4 力矩参数重复定义仍在，启动必抛 RuntimeError（文档称已删除）
[interfaces.py:78-80](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/interfaces.py#L78-L80)：
```python
for candidate in (sub.keys() | params.keys() | override.keys()) - {'legend'}:
    if sum([candidate in x for x in [sub, params, override]]) > 1:
      raise RuntimeError(f'{candidate} is defined twice in torque config')
```
- 实际状态：`override.toml:77` 仍有 `"HYUNDAI_CUSTIN_1ST_GEN" = [2.5, 2.5, 0.1]`，`substitute.toml:43` 仍有 `"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"`，两者并存 → `sum(...) == 2` → **任何调用 `get_torque_params()` 的启动路径都会抛 RuntimeError**。路径常量 `TORQUE_OVERRIDE_PATH` / `TORQUE_SUBSTITUTE_PATH` 确认指向这两个文件（interfaces.py:40-41）。
- 但 37 §3.1、36/38 §3.1 都写明"彻底删除 override.toml:77"，**实际未删除**。这是启动级阻断，且与文档描述相反，属最高优先级。
- **建议**：二者只能留一个。`.agnes/COMPREHENSIVE_OPTIMIZATION_PLAN.md` 里的判断更可信——保留 `override.toml`（有实车标定意图），删掉 `substitute.toml` 的 Custin 行；或反过来。无论选哪个，都要补一条 `python -c "from opendbc.car.interfaces import get_torque_params; get_torque_params()"` 的冒烟测试进 CI，当前 33 个测试**没有一条**真正执行该函数。

### P0-5 安全设计"纸面修复"：文档宣称的防御在生产代码中不存在
- `echo_cmd` 生产代码 [amap_navi.py:842-857](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L842-L857) **至今仍是裸 `subprocess.run(..., shell=True)`**，无 `CarrotEchoCmdEnable` 参数、无 `IsOnroad` 锁死、无 IP 白名单、无审计日志。全库只有 `selfdrive/carrot/tests/test_security_switches.py` 出现 `CarrotEchoCmdEnable` 字样。
- 该测试文件在[自身内部](file:///E:/code/openpilot-ck89757/selfdrive/carrot/tests/test_security_switches.py#L23-L35)重新实现了一个 `handle_echo_cmd_logic()` 纯函数并对其断言，**测的不是生产代码**——典型的自证式测试（self-fulfilling test）。这解释了为何 37 §3.3 / 38 §1.5 的"四重纵深防御"能"测试全绿"却完全没生效。
- **建议**：删除后门是唯一正确解；若确需保留，则把网关函数落到生产模块，测试改为 `import` 真实函数而非复制逻辑。同时补一条静态断言：`assert 'shell=True' not in Path('amap_navi.py').read_text()`。

---

## 三、与库斯途车辆特点不符 / 需要适配的代码

按库斯途「2 吨级 MPV、3.055m 轴距、8AT、外挂激光雷达、车机协同」四个特点逐条核对：

### 3.1 整备质量 1754kg 已落地，但满载工况仍被低估
[values.py:447-448](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/hyundai/values.py#L447-L448)：`CarSpecs(mass=1754, wheelbase=3.055, steerRatio=17)`，并 `flags=CHECKSUM_CRC8 | SEND_LFA`。commit `16aff86` 已把 mass 从 1690 校正到 1754，这一点与 36/37/38 文档一致。
- 残留偏差：1754kg 是 2.0T 顶配**空载**值，满载 7 人 + 行李约 2.2~2.3 吨（+30%）。openpilot 的纵向规划与 NNFF 前馈都读该 mass，满载时制动距离与所需扭矩仍被系统性低估——这正是 MPV 的典型工况。
- **建议**：至少在 `VEHICLE_DYNAMICS.md` 记录该偏差；若走 `STD_CARGO_KG` 之类的载荷假设，按满载工况做保守化。`steerRatio=17` 来源仍是 learner 估值，建议用实车转向角-横摆标定复核。

### 3.2 「专车调优六项」：3 项已落地，3 项仅纸面
[VEHICLE_DYNAMICS.md:22-29](file:///E:/code/openpilot-ck89757/docs/custin/VEHICLE_DYNAMICS.md#L22-L29) 现状：
- **已落地**：帕里斯帝 NNFF 映射（substitute.toml:43）、mass=1754 + `SEND_LFA`（values.py:447-448）、`steerActuatorDelay=0.15` + `startAccel=1.0`（[interface.py:241-243](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/hyundai/interface.py#L241-L243)）。
- **未落地**：0.08g 横向加速度限幅、Jerk ≤0.05g/s 的平顺约束，`lateral_planner.py` 无任何 CUSTIN 分支；夏日温控在 `hardware.py` 中对 GPU 轨写 1 实际是**强制开启**而非释放（文档已撤回 1.65W 结论）。
- **"5.0s 变道"是伪落地**：[desire_helper.py:19](file:///E:/code/openpilot-ck89757/selfdrive/controls/lib/desire_helper.py#L19) 定义 `LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL`，随后在 [L1247](file:///E:/code/openpilot-ck89757/selfdrive/controls/lib/desire_helper.py#L1247) 按帧衰减 `lane_change_ll_prob`。该步进的物理速率是 **1.2 / 秒**（每 0.1s 掉 0.12），从 1.0 衰减到 0 只需 **约 0.83 秒**，比上游 `- DT_MDL`（1.0/s）还**快 20%**，与注释/文档宣称的"5.0 秒平缓"完全相反。若目标真是 5s，步进应为 `0.2 * DT_MDL`。同时 `LANE_CHANGE_TIME_MAX` 仍为 10s（L18），OVERTAKE 模式仍取 `LANE_CHANGE_TIME_MAX*2.0 = 20s`（L523），整体变道窗口并未随 MPV 调整。
- **建议**：修正该常量并补一个"衰减到 0 的墙钟耗时 ≈ 5s"的数值测试（现有 `test_mpv_smooth_lane_change.py` 只做了字符串存在性断言，无法发现这个数量级错误）。

### 3.3 恢复加速限值对满载 MPV 偏猛 + 单位注释误导
[carrot_serv.py:31-33](file:///E:/code/openpilot-ck89757/selfdrive/carrot/carrot_serv.py#L31-L33)：
```python
ACCEL_LIMIT = 1.5*3.6  # m/s²*3.6=km/h，舒适加减速限制
RESTORE_UP_ACCEL_LIMIT = 3.0*3.6
```
- 注释把 km/h/s 写成 m/s²，常量本身是"单位换算内嵌"的坏味道，极易被后续调参者误读 3.6 倍。
- `RESTORE_UP_ACCEL_LIMIT = 3.0 m/s²` 的恢复加速：1.5T 拖 2.3 吨 + 8AT 降挡再加速，实际执行不出该值且易产生顿挫（后排晕车敏感人群），建议恢复加速与巡航加速同样钳在 1.5~2.0 m/s²。

### 3.4 车身近障判定阈值未按车宽校准
[amap_navi.py:727-746](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L727-L746)：车身范围障碍判定用 `_xrel < 1200`（侧向 1.2m）+ 前后 3m/2m 阈值。
- 库斯途车宽 1.85m（半宽 0.925m），外挂激光雷达的安装位置决定了 xrel 坐标原点。若 xrel 以车轴中心起算，1.2m 仅留 0.275m 侧向余量，变道执行初期车身轻微摆动就可能误触发/漏触发。需对照雷达安装标定文件确认原点，并按 1.85m 车宽 + 后视镜宽度留出显式余量。

### 3.5 弯道速度控制依赖视觉车道宽钳位
[amap_navi.py:406-407](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L406-L407)：动态盲区宽度用 `max(1.2, min(3.5, laneWidth))`。
- 模型输出的车道宽度在高架匝道、旧高速上经常置信度不足；对宽车身 MPV，宁可偏保守。建议将钳位下限与车宽+后视镜联动（例如 ≥2.8m 才认为可容纳变道），而不是固定 1.2m。

### 3.6 上游遗留与中规环境混杂
- [carrot_functions.py:493-495](file:///E:/code/openpilot-ck89757/selfdrive/carrot/carrot_functions.py#L493-L495) 存在 CP949 韩文注释乱码；[amap_navi.py:850](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L850) `euc-kr` 解码兜底；carrot tune 依赖（broadcast 到 7705 的 legacy 广播）仍在运行。这些与中规库斯途 + 中文高德协同的现实无关，增加维护噪音，建议一次性清理。

### 3.7 红绿灯停稳锁零：行为正确但缺乏测试锁定
[carrot_functions.py:493-496](file:///E:/code/openpilot-ck89757/selfdrive/carrot/carrot_functions.py#L493-L496)（e2eCruise 无前车时清零）与 [L524-526](file:///E:/code/openpilot-ck89757/selfdrive/carrot/carrot_functions.py#L524-L526)（e2eStopped 锁零 `stop_dist=0`）共同实现"红灯停稳防蠕动"。历史文档曾把条件方向写反（33 号修订记录），说明此处**曾多次被误读**。
- **建议**：新增单元测试固化三个分支（e2eCruise 清零 / e2eStop 保持 / e2eStopped 锁零），并把 `actual_stop_distance` 的生命周期写进 docstring——这是防回归成本最低的一处。

### 3.8 已落地且与库斯途匹配良好的部分（值得肯定）
- 帕里斯帝 NNFF 扭矩映射：[substitute.toml:43](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/torque_data/substitute.toml#L43)，同平台 2 吨级借参，方向正确。
- TTC 三级变道门禁：[desire_helper.py:953-963](file:///E:/code/openpilot-ck89757/selfdrive/controls/lib/desire_helper.py#L953-L963)，`{0:1.8, 1:2.5, 2:3.5}s` 阈值 + `behind_ttc<=0` 失效阻断 + 执行期持续复检，C3 侧 fail-safe 语义完整且有测试覆盖。但**端到端未生效**：车机不消费 `lidar_behind_vdist_time`，且缺省 999m 放行（证据表 E-03）。
- CUSTIN 指纹与 CHECKSUM_CRC8（[values.py:445-449](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/hyundai/values.py#L445-L449)）、0x485 LFAHDA_MFC 仪表联动（hyundaican.py:119-131，每 5 帧随 LKAS11 发送）。
- 指令防重放：`cmd_index` 单调递增 + 10 秒无指令允许重置（[amap_navi.py:1025-1030](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L1025-L1030)）+ 非 app_ip 来源拒绝注入（L1013-1017）。

---

## 四、性能与架构优化点

### 4.1 遥测频率与契约不符
- 契约：[COOPERATIVE_PILOT.md:49](file:///E:/code/openpilot-ck89757/docs/custin/COOPERATIVE_PILOT.md#L49) 承诺 UDP 遥测 20Hz/50ms。
- 实码：[amap_navi.py:1598](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L1598) `Ratekeeper(10)` → 实际 **10Hz**；另有 [L666](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L666) `Ratekeeper(20)` 注释却写 "50Hz"。
- 车机端实际以 10Hz 遥测驱动决策 `tick`（[RelayEngine.kt:195-203](file:///E:/%E6%B1%BD%E8%BD%A6/%E5%BA%93%E6%96%AF%E9%80%94%E5%8D%87%E7%BA%A7%E7%A0%B4%E8%A7%A3/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/relay/RelayEngine.kt#L195-L203)），且**不做 TTC 复检**（见证据表 E-03），频率不一致只影响决策粒度与 HUD 刷新。**建议**：统一为 20Hz（改代码）或修订契约为 10Hz（改文档），并把频率提取为单一常量。

### 4.2 amap_navi.py 的线程与热路径开销
- 单进程 11+ 线程（udp_recv、per-client worker、data_deal、discovery、cmd_recv、lane_recv、broadcast、clean_clients、web、zmq、panda_debug），`SharedData` 为无锁裸字段共享（`app_ip_ts` 甚至未在 `__init__` 声明，L610 动态挂属性）。CPython GIL 下裸读虽不崩溃，但 `behind_ttc`、`main_*_drel` 这类**安全决策输入**存在跨线程时序竞态。
- `make_navi_message` 每帧 30+ 次 `hasattr` 防御（L1747-1930）+ 81 字段 JSON 序列化。capnp schema 固定后 `hasattr` 防御可全部删除；JSON 可用预构造模板增量更新。
- **建议**：分三步走——(1) 安全字段收拢到一个带 `threading.Lock` 的小结构或改用原子写快照；(2) 删除 hasattr 防御；(3) 中期把 transport（UDP）/domain（TTC、盲区融合）/gateway（cereal）拆成三个模块，与 AmapNavi-Reborn 的 Clean Architecture 对齐，便于两端共用同一份协议测试。

### 4.3 客户端 per-IP 线程模型
[amap_navi.py:884-932](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L884-L932)：每个 IP 起一个 worker 线程 + queue。雷达/摄像头设备多时线程数失控；清理依赖 `_clean_clients_thread` 1 秒扫描。
- **建议**：改单线程事件循环（select/asyncio），per-IP 状态只是字典项，天然消除 worker 生命周期管理（`client_active` 标志 + `del` 的竞态窗口随之消失）。

### 4.4 `is_side_object_risky` 参数双语义无文档
[amap_navi.py:1370-1423](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L1370-L1423)：`min_drel_scale ≥ 0` 时表示 `v_ego` 的倍数，`< 0` 时表示固定米数（`danger_dist = abs(min_drel_scale)`）。调用点传入 `LidarFrontVDistTime * 0.1`（config 默认 `-50` → `-5.0`，即固定 5m；`LidarBehindVDistTime=-100` → 固定 10m）。这个"正负号切换单位"的设计没有任何注释，调参页面上更看不出。另外后方 `danger_dist` 用 `v_ego` 计算而非后车速度，急速接近的后车在低速时 protection 偏弱（靠 `future_dist` 分支补）。
- **建议**：拆成两个显式参数（`min_gap_m` / `ego_speed_scale`），各配默认值与调参说明。

### 4.5 参数双源同步机制脆弱
[config.py](file:///E:/code/openpilot-ck89757/selfdrive/carrot/config.py)：
- 单例 `__new__`（L18-22）忽略 `nav_json_file` 参数差异——第二次传不同路径会静默返回第一实例。
- `_match_system_param`（L42-61）每次加载用 Params 值覆盖 JSON：类型靠"值猜测"（int/float/0-1 三态），`isinstance(True, int)` 为 True 的陷阱未处理；双向同步（`put_*` 两侧都写）在 Params 失败回退 JSON 时会产生两份"真源"。
- 8 处 `except Exception: pass` 吞异常。
- **建议**：Params 作为唯一真源，JSON 仅作出厂默认值（首次导入后不再回读）；按 key 显式声明类型表替代类型猜测。

### 4.6 单位双轨制
- cereal 层：`rfDrel = main_rf_drel/100`（mm→10mm 单位，[amap_navi.py:291-294](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L291-L294)）；UDP 层：M-13 修正后 `lb_drel/rb_drel` 强制米制（L1827-1833），而同包 `drel`（前车）也是米、`lf_drel` 等却是 mm（L1821）。
- 一个遥测包内三种距离单位并存，车机端解析器被迫逐键硬编码。**建议**：下一版协议全部统一为米（浮点一位小数），旧字段标记 deprecated 过渡一个版本。

### 4.7 代码卫生
- 死代码块：`is_side_object_risky_debug` 整段注释（L1425-1495）、`navi_comm_thread` 注释调用、多处被注释的调试 print。
- 异常写法：`except (KeyError, RuntimeError, Exception)`（L1590）、`except (OSError, Exception)`（L2108）冗余——前者直接 `except Exception`，且裸 `Exception` 会吞掉编程错误。
- `print()` 遍布热路径，无 logging 分级与落盘策略（仅部分用 `showDebugLog & 32` 位掩码门控）。建议统一 `common/swaglog`，行车日志按 ring buffer 采样。
- 魔法数字：声音索引 26/23/30+n（L1885-1893）应建枚举表并与车机端音效字典对齐。

---

## 五、工程化与流程

1. **工作区改动已基本收敛**：HEAD 为 `32c2144`，TTC 三态、`client_active` 初始化、MPV 变道步进、1754kg 等已随 `16aff86`/`47cbffc`/`32c2144` 提交入库；当前仅 `carrot_serv.py` 等少量文件有未提交修改。仍建议生产镜像构建时断言 `TEST_RELAX_MODE` 环境变量不存在（该变量可在 [amap_navi.py:1014-1015](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L1014-L1015) 放行 127.0.0.1 指令来源）。
2. **测试资产已具备但有两类系统性弱点**：`selfdrive/carrot/tests/` 现有 13 个文件、**33 个 `test_` 函数**（文档写"31 项"，口径已过时）。弱点一：大量断言是**源码字符串存在性检查**（如 `assertIn("LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL", text)`），只能证明"代码里写了这行"，无法证明行为正确——3.2 的 5s 数量级错误就是这么漏过的。弱点二：`test_security_switches.py` 测的是自己复制的 mock 逻辑，不是生产代码。建议：(a) 关键常量改为数值断言；(b) 安全网关测试 `import` 生产函数；(c) 补 `get_torque_params()` 冒烟调用（当前无一条测试真正执行它，导致 P0-4 未被发现）。
3. **行尾与编码**：历史上已踩过 CRLF 导致 shebang 失效的坑（commit 9e41bdc），建议补 `.gitattributes`（`*.py text eol=lf`）。
4. **文档-代码一致性**：`COOPERATIVE_PILOT.md` 与两端实码一致（C3 收 7705/发 7706；AmapNavi-Reborn 绑 7706 收遥测、发 7705 指令）✓。但工作区《09_智能体开发提示词》中写的"遥测 7705 / 控制 7706"与真实实现**相反**，属于过期文档，已建议同步修订，避免误导后续按提示词开发的新代码。
5. **Python 版本漂移**：`__pycache__` 出现 cpython-315 缓存（开发机 Python 3.15），C3 AGNOS 运行时版本不同，建议固定 dev 容器版本并在 CI 中对齐。

---

## 六、36 / 37 / 38 三份设计文档与代码一致性核验

以 HEAD `32c2144` 为基准，对三份文档中"已实现 / 已根除 / 已落地"的断言逐条回查代码：

| # | 文档断言 | 文档位置 | 代码实际 | 判定 |
|---|---|---|---|---|
| 1 | 已彻底删除 `override.toml:77` 的 Custin 条目 | 37 §3.1、36/38 §3.1 | `override.toml:77` 与 `substitute.toml:43` **同时存在**，`get_torque_params()` 必然抛 RuntimeError | ❌ 未修复（P0-4） |
| 2 | 已建立 echo_cmd 四重纵深防御 | 37 §3.3、38 §1.5 | 生产代码仍是裸 `shell=True`；仅测试文件里自建 mock 网关 | ❌ 纸面修复（P0-5） |
| 3 | `mass=1754` + `SEND_LFA` | 36/38 §3.2 | [values.py:447-448](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/hyundai/values.py#L447-L448) 完全一致 | ✅ 已落地 |
| 4 | `steerActuatorDelay=0.15`、`startAccel=1.0` | 36/38 §3.2 | [interface.py:241-243](file:///E:/code/openpilot-ck89757/opendbc_repo/opendbc/car/hyundai/interface.py#L241-L243) 完全一致 | ✅ 已落地 |
| 5 | MPV 5.0s 平缓变道 | 36/38 §3.4、37 §4.3 | 常量存在但衰减速率 1.2/s ≈ 0.83s 完成，方向反了；`LANE_CHANGE_TIME_MAX` 仍 10s / OVERTAKE 20s | ❌ 数值不符（见 3.2） |
| 6 | TTC 三态解耦（99.0 / min / 0.0） | 36/38 §3.3、37 §3.2 | [amap_navi.py:299-308](file:///E:/code/openpilot-ck89757/selfdrive/carrot/amap_navi.py#L299-L308) 与文档伪代码一致 | ✅ 已落地（判定仍弱，见 P0-3） |
| 7 | `CANCEL` 指令消费分支 | 38 §3.4、37 §5.4 | [desire_helper.py:526](file:///E:/code/openpilot-ck89757/selfdrive/controls/lib/desire_helper.py#L526) 已实现 | ✅ 已落地 |
| 8 | `SPEED_LIMIT` 巡航限速处理 | 36/38 §3.5 | handler 已注册（[carrot_serv.py:382-391](file:///E:/code/openpilot-ck89757/selfdrive/carrot/carrot_serv.py#L382-L391)），但车机把车道码 `"KEEP"` 放进 `direction/arg`（[CarrotUdpClient.kt:96-104](file:///E:/%E6%B1%BD%E8%BD%A6/%E5%BA%93%E6%96%AF%E9%80%94%E5%8D%87%E7%BA%A7%E7%A0%B4%E8%A7%A3/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/udp/CarrotUdpClient.kt#L96-L104)），`int(xArg)` 必抛 `ValueError` | ❌ 纸面闭环，功能失效（P0，证据表 E-01） |
| 9 | 车机按 `KEY_TYPE` 分流 10001/10019/10020 | 37 §3.4、38 §2.4 | [AmapBroadcastDecoder.kt:20-52](file:///E:/%E6%B1%BD%E8%BD%A6/%E5%BA%93%E6%96%AF%E9%80%94%E5%8D%87%E7%BA%A7%E7%A0%B4%E8%A7%A3/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/amap/AmapBroadcastDecoder.kt#L20-L52) **完全不读 KEY_TYPE**，只从 `AmapContract` 导出了常量 | ❌ 未实现 |
| 10 | 高德广播 2.0s 老化看门狗（置 `navValid=false`） | 37 §3.4、38 §2.4 | 全仓无 `navValid=false` 的超时路径，仅在断开/reset 时清零 | ❌ 未实现 |
| 11 | 变道超时严格结算为撤销 | 37 §3.5、38 §2.5 | [OvertakeStateMachine.kt](file:///E:/%E6%B1%BD%E8%BD%A6/%E5%BA%93%E6%96%AF%E9%80%94%E5%8D%87%E7%BA%A7%E7%A0%B4%E8%A7%A3/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/domain/decision/OvertakeStateMachine.kt) 已实现 `TELEMETRY_LOST` + CANCEL + 长冷却 | ✅ 已落地 |
| 12 | 31 项 TDD 全绿 | 36/38 §4 | 实际 33 个测试函数；"全绿"不等于覆盖正确（见五-2） | ⚠️ 口径过时 / 测试有效性不足 |
| 13 | 端口契约 7705 上行 / 7706 下行 | 37 §5.1、38 §2.3 | 两端实码一致（C3 收 7705 / 发 7706） | ✅ 正确（与《09》文档相反） |

**结论**：文档的"架构决断"部分（单进程独占 UDP、职责分权、端口矩阵）是可信且已落地的；但"缺陷已根除"章节存在 **2 处硬性失实**（P0-4 力矩重复定义、P0-5 echo_cmd）、**2 处未实现**（车机 KEY_TYPE 分流、2s 老化看门狗）、1 处数值伪落地（5.0s 变道），以及 1 处"handler 已注册但入参错配"的纸面闭环（`SPEED_LIMIT`）。这类"文档宣告完成、代码未动"的偏差比单纯未实现更危险，因为它会让后续维护者跳过验证。

---

## 七、建议路线图（按优先级）

| 优先级 | 事项 | 位置 |
|---|---|---|
| P0 | 删除 `echo_cmd` RCE 后门（文档称已防御，实际未动） | amap_navi.py:842-857 |
| P0 | 消除 torque 重复定义（override.toml:77 vs substitute.toml:43），否则启动抛 RuntimeError | opendbc/car/interfaces.py:78-80 |
| P0 | web 服务加鉴权/改绑 127.0.0.1 | web_interface.py:277 |
| P0 | `main_*_drel` 新鲜度 + sensor_ready 强化，锁 fail-safe 语义测试 | amap_navi.py:299-308, 1153-1162 |
| P1 | 修正 5.0s 变道常量（1.2→0.2 × DT_MDL）并改数值断言测试 | desire_helper.py:19, 1247 |
| P1 | 遥测频率对齐契约（10Hz→20Hz 或改文档） | amap_navi.py:1598 |
| P1 | 车机补 KEY_TYPE 分流 + 高德广播 2s 老化看门狗 | AmapBroadcastDecoder.kt / NaviState |
| P1 | 恢复加速限值 3.0→2.0 m/s²、单位注释改正 | carrot_serv.py:31-33 |
| P1 | 满载质量偏差记录；steerRatio 实测复核；横向 0.08g / Jerk 限幅落地或降级 Roadmap | values.py:447, lateral_planner.py |
| P2 | UDP 协议单位统一为米；频率常量化 | amap_navi.py |
| P2 | SharedData 安全字段加锁/快照；hasattr 清理 | amap_navi.py |
| P2 | UnifiedParams 单一真源化；类型表显式化 | config.py |
| P2 | is_side_object_risky 参数语义拆分与文档 | amap_navi.py:1370-1423 |
| P3 | 测试有效性改造（数值断言/import 生产函数/torque 冒烟） | selfdrive/carrot/tests |
| P3 | 死代码/韩文遗留清理、logging 统一、.gitattributes、CI 接入 | 全局 |

---

## 八、结论

项目整体架构（carrot 上游 + CUSTIN 定制层 + 外挂激光雷达融合 + 车机 UDP 协同）思路清晰，TTC 三态解耦、CANCEL 消费、NNFF 借参、指令防重放等安全相关实现质量高于典型个人 port 水准，且已具备成体系的 TDD 测试。**最紧迫的不是算法，而是四处安全/可用性红线**：RCE 后门、无鉴权参数写接口、TTC 弱判定，以及会直接导致启动失败的力矩参数重复定义——它们都位于"便利性调试代码"与"行车安全代码"的交界处，恰好是个人项目最容易失守的位置。

更值得警惕的是**文档与代码的信任缺口**：37/38 号文档把 `echo_cmd` 防御、override.toml 删除、5.0s 变道写成既成事实，甚至配了"全绿"测试，而代码侧一项未动（测试测的是复制的 mock 逻辑与源码字符串）。建议立即建立一条规则：**任何"已修复"断言必须附带一条会失败的测试或一条可执行的验证命令**，否则一律记为"未实现"。文档的架构决断部分仍然可信，但"缺陷已根除"章节在黑盒复核前不应作为事实源使用。
