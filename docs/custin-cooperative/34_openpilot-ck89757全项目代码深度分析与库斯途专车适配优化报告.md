# 34_openpilot-ck89757 全项目代码深度分析与库斯途专车适配优化报告

> **分析对象**：`E:\code\openpilot-ck89757`（`cp-custo-amap` 分支，HEAD `70ba3d8`，工作区含未提交修改）
> **分析方式**：全仓结构扫描 + 关键路径逐行阅读 + 车辆参数/控制链路交叉核对 + 可复现指标统计
> **日期**：2026-11-03
> **说明**：本文反映**当前工作区**状态。工作区有 8 个文件未提交（`amap_navi.py` / `carrot_serv.py` / `desire_helper.py` / `cereal/SConscript` / README / docs / `.vscode`），分析结论与 HEAD 可能存在差异。

---

## 一、执行摘要

### 总体判断

| 维度 | 评价 |
|:---|:---|
| 架构完整性 | 🟢 openpilot 主链完整，Carrot 定制层功能丰富，双端协同链路已在代码层打通 |
| 库斯途专车适配 | 🟠 **大量沿用 Hyundai 通用假设**，关键车辆参数（质心、轮胎刚度、载荷、雷达供应商）未针对库斯途标定 |
| 安全与可靠性 | 🔴 仍有 **未认证 UDP 远程命令执行面**、**未认证 Web 参数写入**、**TTC 三态语义缺陷** |
| 性能 | 🟠 Carrot 层单进程多线程 + 高频 JSON/capnp + 大量 print，存在 GIL 与延迟风险 |
| 代码质量 | 🟠 核心文件 1800~2100 行、死导入、注释代码、宽泛异常捕获、测试未入库 |
| 可维护性 | 🟠 工作区脏、文档编号冲突、capnp 生成物过期、无 CI |

### 最值得优先处理的 6 件事

1. **删除/禁用 `amap_navi._lane_recv_thread` 的 `echo_cmd` 远程 shell**（未认证 UDP → RCE）。
2. **关闭或鉴权 `carrot_man` 的 8088 Web 参数写入**（同网段任何人可改 `Params`）。
3. **修复 TTC 三态语义**：当前"无后车目标"与"雷达失效"都输出 `0.0` → 空车道永久阻断变道。
4. **修复 `SPEED_LIMIT` 端到端契约**：车机发 `arg="KEEP"`、速度在 `v_cruise`，C3 handler 永远解析失败。
5. **为库斯途补齐车辆参数**：`centerToFront`、`tireStiffnessFactor`、载荷、雷达供应商、`SEND_LFA`。
6. **恢复可构建性**：`build.gradle` 签名配置引用未定义属性，当前所有 Gradle 构建都会失败。

---

## 二、分析范围与方法

- **仓库规模**：约 690 MB，Python 文件 1859 个；`selfdrive` 下 190 个。
- **核心定制层**：`selfdrive/carrot/` 7680 行；`selfdrive/controls/` 6026 行；`selfdrive/selfdrived/` 2242 行；`selfdrive/modeld/` 1277 行。
- **方法**：
  1. 目录/行数/依赖/进程配置扫描；
  2. 关键循环（controlsd 100 Hz、modeld 20 Hz、carrot_man 10 Hz、amap_navi 20/10 Hz）逐段阅读；
  3. 车辆参数从 `CarSpecs` → `CarParams` → `latcontrol/lateral_planner/longitudinal_planner` 全链路追踪；
  4. 双端协议从 Kotlin 发送端 → C3 解析端 → 消费端全链路比对；
  5. 用可重放命令核对 file:line（见附录）。

---

## 三、项目结构与运行模型

### 3.1 进程与频率

- `system/manager/process_config.py` 注册 **56 个进程**，其中 **14 个 `always_run`**。
- 关键频率：

| 进程/模块 | 频率 | 说明 |
|:---|:---:|:---|
| `controlsd` | 100 Hz | `Ratekeeper(100)`，横向/纵向控制主环 |
| `selfdrived` | 100 Hz | 事件与状态机 |
| `modeld` | 20 Hz | 模型推理；**`DesireHelper.update` 也在这里执行** |
| `plannerd` | 20 Hz | `LateralPlanner` / MPC，发布 `lateralPlan` |
| `carrot_man` | 10 Hz | Carrot 主进程，内嵌 `AmapNaviServ`、Web 服务 |
| `amap_navi` 数据线程 | 20 Hz | 遥测下行 + `amapNavi` capnp 发布 |
| `amap_navi` 广播线程 | 10 Hz | 局域网广播 |
| `lane` 进程 | onroad | Flask/OpenCV 视频流调试服务 |

### 3.2 数据闭环

```
摄像头/雷达/外挂激光雷达
      │
      ▼
modeld(20Hz) ── modelV2 ──► plannerd(20Hz) ── lateralPlan ──► controlsd(100Hz) ──► CAN/Panda
      │                                                           ▲
      └─ DesireHelper.update ── laneChangeState/Direction ───────┘
      │
carrot_man(10Hz) ── carrotMan ──► modeld/controlsd（盲区、ATC、导航）
      │
amap_navi(20Hz) ── amapNavi ──► DesireHelper（TTC/overtakeMode）
      │
UDP 7705/7706/4210/4211/4213 ◄──► 车机 AmapNavi-Reborn
```

### 3.3 定制层的耦合点

- `DesireHelper` 同时依赖 `modelV2`、`carRotMan`、`radarState`、`amapNavi`，并在 `modeld` 内执行（`modeld.py:474`）。
- `AmapNaviServ` 被嵌入 `carrot_man`（`carrot_man.py:191`），自带 9 个线程、1 个 `PubMaster(['amapNavi'])`。
- `carrot_serv.py` 承担 ATC、导航、限速、按钮、巡航等大量逻辑，1790 行。

---

## 四、库斯途专车适配问题（重点）

### 4.1 车辆参数与动力学模型

`opendbc_repo/opendbc/car/hyundai/values.py:445-448`：

```python
HYUNDAI_CUSTIN_1ST_GEN = HyundaiPlatformConfig(
  [HyundaiCarDocs("Hyundai Custin 2023", "All", car_parts=CarParts.common([CarHarness.hyundai_k]))],
  CarSpecs(mass=1690, wheelbase=3.055, steerRatio=17),
  flags=HyundaiFlags.CHECKSUM_CRC8,
)
```

| 参数 | 当前值 | 问题 | 建议 |
|:---|:---|:---|:---|
| `mass` | 1690 kg（整备） | 满载可到 2200~2300 kg，**载荷变化约 36%**；横向 MPC/前馈使用 `CP.mass`，无载荷估计 | 在 `CarParams` 提供 `Params` 覆盖或在标定时按满载复测；至少用 1690/2300 两档验证 |
| `wheelbase` | 3.055 m | 正确 | — |
| `steerRatio` | 17 | 偏高（Palisade 17.94），转向慢、扭矩需求大 | 用 `liveParameters` 收敛值复核；必要时调 `CustomSteerMax` |
| `centerToFront` | **`wheelbase * 0.4`（interface.py:166）** | Hyundai 接口**硬编码 0.4**，忽略 `CarSpecs.centerToFrontRatio`；Custin 得到 1.222 m，未按实际轴荷标定 | 实测前后轴荷，设置 CUSTIN 的 `centerToFrontRatio`，并让 Hyundai 接口使用它 |
| `tireStiffnessFactor` | **默认 1.0**（未设置） | Palisade 为 0.63；库斯途后扭力梁、MPV 轮胎，1.0 可能高估轮胎刚度 | 以 0.6~0.7 起步，结合 `liveTorqueParameters` 与实车横向响应验证 |
| `torque substitute` | `CUSTIN → PALISADE` | Palisade 1999 kg / 2.9 m / 0.63，与 Custin 1690 kg / 3.055 m / 1.0 不同；`latAccelFactor=2.54`、`friction=0.13` 来自 Palisade | 先验证 Palisade 参数；若横向响应偏差大，试 `SANTA_FE` 或自训 |

**关键机理**：
- `scale_tire_stiffness()`（`opendbc/car/__init__.py:74-82`）用 `mass / wheelbase / centerToFront / tireStiffnessFactor` 计算前后轮胎刚度；Custin 的 `1.0` 与 Palisade 的 `0.63` 不是同一量级。
- `lateral_planner.py:37-38`：
  ```python
  self.factor1 = CP.wheelbase - CP.centerToFront
  self.factor2 = (CP.centerToFront * CP.mass) / (CP.wheelbase * CP.tireStiffnessRear)
  ```
  这两个因子直接进入 MPC；`centerToFront`/`tireStiffness` 偏差会改变预测轨迹与实际响应的匹配度。
- `configure_torque_tune()`（`interfaces.py:527-538`）则使用 substitute 后的 Palisade `latAccelFactor`/`friction`。**同一辆车上同时存在"Palisade 的扭矩参数"与"Custin 的 MPC 参数"**，二者不自洽，是当前最典型的专车适配隐患。

### 4.2 横向控制与 MPV 舒适性

- `latcontrol_torque.py` 使用 `latAccelFactor`、`friction`、NNFF；Custin 通过 substitute 得到 Palisade 参数。
- `liveTorqueParameters` 会在线学习 `latAccelFactor/friction`（`latcontrol_torque.py:134-140`），但 `CP.mass`、`CP.tireStiffnessRear` 不会在线更新。
- 变道轨迹由模型输出决定；`desire_helper.py` 只管理状态机与 `ll_prob`，**没有横向加速度/Jerk 限幅**。
- 21 号指南提出的 `LANE_CHANGE_STEP_CUSTO = 1.2*DT_MDL` **在代码中不存在**，且 `lane_change_ll_prob` 只写入 `modelV2.meta.laneChangeProb`，唯一引用处是 `lateral_planner.py:149` 的注释——**改它不会改变变道轨迹或时长**。
- 库斯途车高 1.734 m、后扭力梁、7 座满载，快速变道时后排横向 jerk 明显；当前没有 MPV 专属路径整形。

**建议**：
1. 在 `LateralMpc`/`lane_planner_2` 的路径层做横向加速度/Jerk 约束，而不是改 `ll_prob`；
2. 用实车采集 `latAccel`/`jerk`，按满载工况标定；
3. 变道时长/侧向加速度做成 `Params` 可调，按驾驶模式分档。

### 4.3 纵向控制与 8AT

`opendbc/car/hyundai/interface.py:196-209`：

```python
ret.pcmCruise = not ret.openpilotLongitudinalControl
ret.startingState = False
ret.vEgoStarting = 0.1
ret.startAccel = 1.0
ret.longitudinalActuatorDelay = 0.5
ret.longitudinalTuning.kpBP = [0.]
ret.longitudinalTuning.kpV = [1.]
ret.longitudinalTuning.kf = 1.0
```

- `startAccel = 1.0` 是**所有 Hyundai 车型无条件生效**，不是库斯途专属；文档中"针对 CUSTIN 固化"的写法与代码不符。
- `longitudinalActuatorDelay = 0.5`、`kp/kf = 1.0` 为通用值；2.3 t 满载 MPV 的制动/加速响应未标定。
- `carrot_functions.py` 的 `A_CRUISE_MAX_BP_CARROT`、`cruiseMaxVals`、`comfortBrake=2.4`、`tFollowGap=1.1~1.6` 为通用 Carrot 参数，非库斯途专属。
- 8AT 蠕行/1-2 挡冲击相关参数（`stop_distance=6.0`、`trafficStopDistanceAdjust=2.0`）未针对库斯途验证。
- `longitudinal_planner.py:292` 的 `_jerk_factor = 1.5` 为硬编码，满载舒适性未验证。

**建议**：
- 把 `startAccel`、`longitudinalActuatorDelay`、`kp/kf`、`tFollowGap`、`comfortBrake` 纳入 CUSTIN 专属参数表；
- 用满载/空载两档做 0-30 km/h 起步、30-0 刹停、拥堵蠕行三组测试，再定值；
- 8AT 低速工况优先验证"停稳不耸动、起步不点头"。

### 4.4 CAN / ADAS / 仪表

| 项 | 当前 | 风险/建议 |
|:---|:---|:---|
| 雷达供应商 | `CUSTIN` flags 仅 `CHECKSUM_CRC8`，**未设 `MANDO_RADAR`** | 若库斯途使用 Mando 雷达，`dbc_dict` 不会加载 `hyundai_kia_mando_front_radar_generated` → `radarUnavailable=True`，雷达跟踪不可用。**先确认雷达供应商**；若是 Mando，加 `HyundaiFlags.MANDO_RADAR` |
| `SEND_LFA` | 仅在车辆指纹含 `0x485` 时动态置位（`interface.py:135-137`） | 若实车指纹无 `0x485`，仪表 `LFAHDA_MFC` 不会发送，绿色车道线/方向盘/ HDA 不会点亮。**用实车 fingerprint 日志确认** |
| `openpilotLongitudinalControl` | `alpha_long and alphaLongitudinalAvailable` | 若未开 alpha long，纵向使用原厂 SCC，Carrot 纵向调参不生效；需在文档与验收中明确 |
| 转向 | `0x340 LKAS11`，每帧发送（100 Hz） | 文档曾写 50 Hz，实际 100 Hz；不影响功能，但文档需更正 |
| 仪表 | `0x485 LFAHDA_MFC`，20 Hz，`HDA_VSetReq` 恒 0 | 不会同步巡航设定车速；文档中"同步设定时速"不实 |
| 总线 | 经典 500 kbps C-CAN，`hyundai_k` 线束 | 与代码一致；注意非 CAN-FD 路径 |

### 4.5 车机协同链路中的专车相关缺陷

1. **TTC 三态缺失（Critical）**：`amap_navi.py:304` 无目标 → `0.0`；`desire_helper.py:959` `<=0` 即阻断 → **空车道无法变道**。应区分"有目标安全 / 无目标 / 传感器失效"。
2. **`SPEED_LIMIT` 载荷不匹配（Major）**：车机 `CarrotUdpClient.kt:109-121` 发 `arg="KEEP"`、速度在 `v_cruise`；C3 `amap_navi.py:1030-1035` 取 `remote_arg="KEEP"`；`carrot_serv.py:381-393` 对 `"KEEP"` 执行 `int()` → 失败。**功能仍是空操作**。
3. **`CANCEL` 已接通但语义需验证**：`ca6cb4a` 已加 `desire_helper.py:526` 分支；需实车确认 50 ms 内状态机复位与播报。
4. **`app_ip` 可被抢占**：5510 探针无认证，任何设备发 `discover`/`c3_ping` 都能成为 `app_ip`；配合 7705 白名单可接管指令通道。建议加共享密钥/设备指纹。
5. **`atc_state` 已发送**：`amap_navi.py:1909`；此前"两端都不存在"的审计结论应撤销。

---

## 五、安全与可靠性缺陷（P0）

### 5.1 未认证 UDP 远程命令执行（Critical）

`amap_navi.py:842-855`：

```python
elif 'echo_cmd' in json_obj:
    result = subprocess.run(json_obj['echo_cmd'], shell=True, capture_output=True, text=False)
    ...
    sock.sendto(echo.encode(), addr)
```

- 位于 `_lane_recv_thread`，绑定 `0.0.0.0:4213`（`amap_navi.py:815-818`）。
- 同 Wi-Fi 热点内**任何设备**可发送 `{"echo_cmd":"..."}` 在 C3 上执行任意 shell 命令，并回传 stdout。
- 这是当前最严重的代码级安全问题。**建议立即删除该分支**，或至少加 `TEST_*` 环境变量 + 源 IP 白名单 + 命令白名单。

### 5.2 未认证 Web 参数写入（Critical）

`web_interface.py:277`：

```python
self.web_server = HTTPServer(('0.0.0.0', self.port), handler)
```

`do_POST` 支持 `/save_params`（`:132-141`），会调用 `save_params()` 写入 `Params`。没有鉴权、没有 CSRF 防护、绑定所有网卡。热点内任何人可修改 openpilot 参数（包括影响安全行为的开关）。

**建议**：绑定 `127.0.0.1` 或加 token 鉴权；生产模式禁用 `/save_params`；至少限制到 `app_ip`。

### 5.3 运行时 `pip install`（Major）

`lane.py:314-358` 在缺依赖时执行：

```python
subprocess.run("pip install flask", shell=True, ...)
subprocess.run("pip install opencv-python", shell=True, ...)
```

- `lane` 进程在 `process_config.py:146` 以 `only_onroad` 启动；每次上车都可能触发安装/重试。
- 车载环境常无外网，重试 10 次会阻塞启动；同时引入供应链风险。
- **建议**：依赖预置到镜像；缺依赖时直接禁用该调试服务，不在运行时安装。

### 5.4 协议无认证/无版本/无完整性

- 7705/7706/4210/4211/4213 全部明文 UDP，无 HMAC、无版本字段、无序号窗口（仅有单调 seq）。
- 建议：协议加 `version`、`nonce`、`hmac`；或至少绑定 `app_ip` + 共享密钥。

### 5.5 其他

- `TEST_RELAX_MODE` 允许 127.0.0.1 发包；仅本机可利用，风险低，但应确保生产环境不设置。
- `cereal/gen/cpp/custom.capnp.h:70` 仍为 `(…, 8, 0)`，与 17 字段 schema 不一致（M-17）；Python 侧不受影响，C++ 工具需重生成。
- `build.gradle` 签名配置引用未定义属性，**当前所有 Gradle 构建在配置阶段失败**（M-24）。

---

## 六、性能优化

### 6.1 线程与 GIL

- `AmapNaviServ` 内含 **9 个 `threading.Thread`**：数据线程、UDP 接收、lane 接收、客户端清理、5510/4210 探针、7705 指令、广播、Client worker 等。
- `carrot_man` 另有主循环（10 Hz）、Web 线程、多个业务线程。
- Python GIL 下，JSON 解析、`json.dumps`、capnp 构建、`print` 会与 10 Hz 主循环竞争；虽然 `controlsd` 是独立进程，但 `carrotMan` 数据延迟会间接影响 `DesireHelper`。
- **建议**：把 `amap_navi` 的网络 I/O 收敛到 `selectors`/`asyncio` 单线程事件循环；CPU 密集的 JSON 解析移到独立进程或使用二进制协议；用有界队列解耦。

### 6.2 高频序列化

- `_data_deal_thread` 20 Hz：`make_navi_message()` 构建大字典 + `json.dumps`；`public_amap_navi()` 再构建 capnp。两套序列化串行执行。
- `navi_broadcast_info` 10 Hz 广播；`make_broadcast_message` 重复构建。
- **建议**：静态字段缓存；只序列化变化字段；把遥测降到 10 Hz（HUD 不需要 20 Hz）；capnp 与 JSON 共用一次数据快照。

### 6.3 日志与打印

- 全 `selfdrive` 有 **738 处 `print(`**，`amap_navi.py` 77 处、`desire_helper.py` 大量调试输出。
- 部分受 `showDebugLog` 门控，但异常路径与启动路径未门控。
- `services.py:84-85`：`carrotMan`/`amapNavi` 均为 `(True, 0.)`，即 **log=True 且不检查频率**，10/20 Hz 自定义消息都会写日志，增加磁盘 I/O 与日志体积。
- **建议**：统一 `swaglog`/`cloudlog`，按等级与频率限流；`carrotMan`/`amapNavi` 设 `log=False` 或降频；移除热路径 print。

### 6.4 参数读取

- 全仓 **82 处 `Params()` 实例化**；`carrot_serv` 每 10 帧读一批参数，`carrot_functions` 每 20 帧读，`amap_navi` 每 100 帧读。频率总体可控，但 `Params` 是文件/共享内存读取，建议单例缓存 + 变更通知。
- `UnifiedParams` 单例缓存 `nav_data`，但系统参数与 JSON 的优先级逻辑存在类型判断瑕疵（bool 是 int 的子类；`value in (0,1)` 对 float 也成立）。

### 6.5 其他

- `lane.py` 的 Flask/OpenCV 视频流在 C3 上常驻（onroad），若非调试必需，建议默认关闭。
- `modeld` 20 Hz 内执行 `DH.update`（Python，100+ 行状态机）；若 profile 显示 >2 ms，可考虑移到独立 20 Hz 线程/进程，避免阻塞模型推理。
- `selfdrived/events.py` 43 KB、`car/cruise.py` 33 KB、`radard.py` 31 KB，均为大文件；事件/雷达路径在 100 Hz/20 Hz 热环中，建议 profile 热点。

---

## 七、代码质量与可维护性

### 7.1 巨型文件

| 文件 | 行数 | 说明 |
|:---|:---:|:---|
| `selfdrive/carrot/amap_navi.py` | 2125 | 网络、协议、雷达、盲区、capnp、线程全在一个类 |
| `selfdrive/carrot/carrot_serv.py` | 1790 | ATC、导航、限速、按钮、巡航 |
| `selfdrive/controls/lib/desire_helper.py` | 1415 | 变道状态机 + 盲区 + 导航 + 语音 |
| `selfdrive/carrot/carrot_man.py` | 1102 | 主循环 + Web + 多线程 |

**建议**：按职责拆分（transport / protocol / perception-fusion / decision / actuation），至少把 `amap_navi` 拆成 `udp_server.py`、`telemetry.py`、`lidar.py`、`publisher.py`。

### 7.2 死代码与注释

- `carrot_serv.py` 有 10 个未使用导入：`fcntl`、`socket`、`struct`、`threading`、`FTP`、`Ratekeeper`、`MyMovingAverage`、`TICI`、`Coordinate`、`DT_MDL`。
- `desire_helper.py` 有 167 行注释（大量被注释掉的旧逻辑），`carrot_serv.py` 137 行。
- `amap_navi.py` 有大量 `#print(...)` 与注释分支。
- **建议**：用 `ruff`/`pyflakes` 清理；把历史逻辑移入文档或 git 历史，不在代码中保留。

### 7.3 异常处理

- `selfdrive` 下 **118 处** `except Exception` 或裸 `except`；`amap_navi.py` 24 处。
- 常见模式：捕获后 `print` 然后继续，丢失上下文；网络/解析错误与逻辑错误混在一起。
- **建议**：分层异常（协议错误 → 丢弃包；状态错误 → 告警；未知 → 上报 `cloudlog` 并限流），避免静默吞错。

### 7.4 测试与工程化

- `selfdrive/carrot/tests/` 有 10 个测试文件、约 853 行，覆盖 TTC、命令 handler、schema、动力学不变量等，**但目录未纳入 git**（`git status` 显示 `?? selfdrive/carrot/tests/`）。
- 没有 CI 配置针对该 fork；`pyproject.toml` 继承上游。
- 工作区 8 个文件未提交；`amap_navi.py`/`carrot_serv.py`/`desire_helper.py` 的改动未形成可追溯提交。
- **建议**：提交测试目录；在 CI 中跑 `pytest selfdrive/carrot/tests`；把 9 项修复拆成独立提交并附 M 编号。

### 7.5 文档与编号

- 项目根目录出现三份 30 号、三份 31 号、多份 32 号文档，M 编号在 30 号主索引与 32 号终审报告中指向不同缺陷。
- **建议**：以 `30_三份29号核验报告统一主索引表.md` 为唯一台账；其余文档标注"历史/废止"；新发现只追加 M-36 起。

---

## 八、架构级优化建议

### 8.1 把"车辆参数"从代码中抽出来

当前 CUSTIN 的参数散落在：

- `values.py` 的 `CarSpecs`
- `interface.py` 的 `centerToFront=0.4`、`startAccel=1.0`、`longitudinalActuatorDelay=0.5`、`kp/kf`
- `substitute.toml` 的 torque 映射
- `carrot_functions.py` 的巡航/跟车/jerk 参数
- `desire_helper.py` 的变道阈值

**建议**：建立 `docs/custin/vehicle_profile.yaml`（或 `Params`）作为单一来源，启动时加载并覆盖 `CarParams`/`CarrotPlanner`/`DesireHelper` 的默认值；代码只保留通用逻辑。这样换车/换载荷只改配置，不改核心文件。

### 8.2 协议分层

- 定义 `protocol_version`、消息类型、字段范围、频率、超时、重放窗口。
- 把 JSON 替换为 `capnp`/`msgpack` 或紧凑二进制；至少对 7705 指令做 HMAC。
- 双端共用一份 schema（从 `cereal/custom.capnp` 生成 Kotlin/Python）。

### 8.3 状态机与决策分离

- `DesireHelper` 目前同时处理状态、盲区、导航、语音；建议拆成 `LaneChangeStateMachine` + `SafetyGate` + `AudioPolicy`。
- 用显式三态 `TTC_VALID / NO_TARGET / SENSOR_FAULT` 取代 `0.0/99.0` 哨兵。

### 8.4 可观测性

- 统一 `cloudlog`/`swaglog`，按模块分级；关键决策（TTC、阻断原因、CANCEL、SPEED_LIMIT）打结构化日志。
- 为 `amapNavi`/`carrotMan` 增加健康状态（最后收包时间、序号、丢包率），HUD 显示"数据新鲜度"而非仅"已连接"。

---

## 九、优先级路线图

| 优先级 | 项 | 预计工作量 | 影响 |
|:---:|:---|:---:|:---|
| **P0** | 删除 `echo_cmd` 远程 shell | 0.5 h | 消除 RCE |
| **P0** | Web 8088 鉴权/禁用 `/save_params` | 1 h | 消除参数篡改 |
| **P0** | TTC 三态（无目标 vs 失效） | 0.5 d | 恢复空车道变道 + 真正 fail-safe |
| **P0** | `SPEED_LIMIT` 载荷契约 | 0.5 d | 恢复定速微调/匝道减速 |
| **P0** | `build.gradle` 条件签名 | 0.5 h | 恢复可构建 |
| **P0** | `scons` 重生成 capnp 生成物 | 0.5 h | C++ 工具一致性 |
| **P1** | 库斯途车辆参数标定（质心/轮胎刚度/载荷/雷达） | 1~2 d + 实车 | 横向/纵向手感与安全 |
| **P1** | 8AT 起步/蠕行/停稳专项标定 | 1 d + 实车 | 舒适性 |
| **P1** | 变道舒适性（MPV 路径整形/横向 jerk） | 1~2 d + 实车 | 后排晕车 |
| **P1** | `lane.py` 运行时 pip 移除、默认关闭 | 0.5 d | 启动可靠性/供应链 |
| **P2** | `amap_navi` 拆模块、单线程事件循环 | 2~3 d | 性能/可维护性 |
| **P2** | 日志分级/限流、服务 log=False | 1 d | 日志体积/CPU |
| **P2** | 死导入/注释代码清理、CI、测试入库 | 1 d | 可维护性 |
| **P2** | 文档主索引统一、工作区提交 | 0.5 d | 可追溯性 |

---

## 十、附录：关键证据与可复放命令

```bash
# 车辆参数
sed -n '445,448p' opendbc_repo/opendbc/car/hyundai/values.py
sed -n '160,210p' opendbc_repo/opendbc/car/hyundai/interface.py
grep -n "centerToFrontRatio\|tireStiffnessFactor" opendbc_repo/opendbc/car/__init__.py opendbc_repo/opendbc/car/interfaces.py

# 安全面
sed -n '842,856p' selfdrive/carrot/amap_navi.py        # echo_cmd
sed -n '132,141p;270,282p' selfdrive/carrot/web_interface.py  # 未认证 POST / 0.0.0.0
sed -n '314,358p' selfdrive/carrot/lane.py             # 运行时 pip install

# TTC / 指令
sed -n '296,305p' selfdrive/carrot/amap_navi.py
sed -n '953,962p' selfdrive/controls/lib/desire_helper.py
sed -n '109,121p' /e/汽车/库斯途升级破解/AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/data/udp/CarrotUdpClient.kt
sed -n '381,393p' selfdrive/carrot/carrot_serv.py

# 性能/质量
wc -l selfdrive/carrot/*.py selfdrive/controls/lib/desire_helper.py
grep -c "print(" selfdrive/carrot/amap_navi.py
grep -rn "except Exception\|except:" --include=*.py selfdrive | grep -v __pycache__ | wc -l
grep -n "carrotMan\|amapNavi" cereal/services.py

# 构建/生成物
sed -n '9,15p;33,38p' /e/汽车/库斯途升级破解/AmapNavi-Reborn/app/build.gradle
grep -n "CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d" cereal/gen/cpp/custom.capnp.h
```

---

## 十一、结论

`openpilot-ck89757` 是一条**功能完整、定制很深**的分支：主链（modeld/plannerd/controlsd）保留完整，Carrot 层把导航、盲区、激光雷达、变道、巡航、Web、双端协同都做了进去。它的优势是"能用、功能多"，代价是**单进程巨类、多线程、强耦合、专车参数散落**。

对库斯途而言，最需要修正的不是"再加功能"，而是：
1. **把车辆参数真正标定到库斯途**（质心、轮胎刚度、载荷、雷达供应商、LFA 指纹）；
2. **把安全门禁的三态语义做对**（无目标 vs 失效）；
3. **把未认证的远程执行面关掉**（echo_cmd、Web 参数写入、UDP 白名单）；
4. **把高频/大文件/日志/线程收敛**，让 10 Hz Carrot 与 20 Hz 模型、100 Hz 控制之间的延迟可预期。

完成 P0 + P1 后，这套系统才具备"在库斯途上可解释、可标定、可验收"的工程基础。
