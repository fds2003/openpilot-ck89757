# openpilot-ck89757 · `cp-custo-amap` 分支全面深度代码分析报告

> **分析对象**：`github.com/fds2003/openpilot-ck89757`，分支 `cp-custo-amap`，HEAD `70ba3d8`
> **上游基线**：`git_src_commit = ce355250be…`（2025-03-07），版本串 `COMMA_VERSION "0.9.9"`，CarrotPilot 系 fork
> **目标车辆**：北京现代 库斯途（Hyundai Custin / Custo，1st Gen，2021–2024，1.5T/2.0T + 现代 8AT，7 座 MPV，轴距 3055 mm，车长 4950 mm）
> **硬件**：Comma 3（分支文档自称 2 GB RAM；车机为航盛 HSAE D531MC）
> **方法**：全量代码阅读 + 逐条定位 `文件:行号` 复核 + 关键结论在沙箱内用真实 TOML/加载器逻辑复算验证。所有条目均为**实际读到的代码**；无法静态确认的，集中标注为「需实车/日志验证」。

---

## 0. 结论速览

### 0.1 一句话结论
这是一个功能密度极高、但**当前状态无法开机**的移植分支：`torque_data` 里库斯途被同时写进 `override.toml` 与 `substitute.toml`，触发 `get_torque_params()` 的重复定义断言 → `card.py` 在**任何车型**上启动即 `RuntimeError`。在此之上，本分支把上游 openpilot 的三道最后防线（**panda 横向扭矩校验、消息老化与进程/通信看门狗、fail-safe 减速下限**）同时削平，而最新提交的"高德协同领航"核心门禁逻辑存在**语义反转**——后方无车时反而永久阻断变道。

### 0.2 Top 12（按"必修程度"排序）

| # | 问题 | 位置 | 等级 |
|---|---|---|---|
| 1 | 库斯途 torque 参数被双重定义 → 启动即崩（全车型受影响） | `opendbc_repo/opendbc/car/torque_data/{override.toml:77, substitute.toml:43}` + `interfaces.py:69-80` | **P0 阻断** |
| 2 | panda 横向安全校验算出来了但**从不阻止发送**；`max_steer` 从 270 抬到 512 | `safety_hyundai.h:255-257`、`safety_hyundai_canfd.h:7,358` | **P0 安全** |
| 3 | 发 own SCC12 即自动 `controls_allowed = true`；按钮 resume 不再要求 `controls_allowed` | `safety_hyundai.h:223-228, 268-270`、`safety_hyundai_common.h:79-97` | **P0 安全** |
| 4 | TTC 门禁语义反转：后方"无目标"→ `ttc=0.0` → **阻断变道**，且每 2 s 播报"后方来车" | `amap_navi.py`（producer 哨兵）+ `desire_helper.py:949-970, 1247-1259` | **P0 功能** |
| 5 | `carrotMan`/`amapNavi` 频率=0 → `SubMaster.alive` **恒真**，进程死后仍用陈旧值 | `cereal/services.py:84-85` + `cereal/messaging/__init__.py:153-157` | **P0 架构** |
| 6 | `loggerd` 被注释停用 + 7 处 `pass#` 静音 `processNotRunning/cameraMalfunction/commIssue/sensorDataInvalid` | `process_config.py:85`、`selfdrived.py:378-473` | **P0 可观测性** |
| 7 | `safety_mismatch = False #carrot` — 硬件安全模式一致性校验失效 | `selfdrived.py:357-358` | **P0 安全** |
| 8 | D 挡即允许横向输出，与 `selfdriveState.active` 脱钩 | `controlsd.py:139-148` | **P0 安全** |
| 9 | `DisableDM` 默认 **"1"**（驾驶员监控默认关闭且相关进程不启动） | `manager.py:172` + `process_config.py:77` | **P0 安全** |
| 10 | 两处**未鉴权远程命令执行**（UDP 4213 / ZMQ-TCP 7710 的 `echo_cmd` → `subprocess(shell=True)`）；明文 FTP + 仓库内硬编码口令 | `amap_navi.py:840`、`carrot_man.py:883`、`carrot_man.py:764-770,880` | **P0 安全/合规** |
| 11 | 库斯途的车辆参数抄自**台湾版** Custin 且 `steerRatio` 来自 learner；NNFF「帕里斯帝模型」文档宣称但代码中永不生效 | `hyundai/values.py:445-449`、`interfaces.py:169-197` | **P1 标定** |
| 12 | 默认即「原厂雷达下线 + openpilot 控纵向 + 向雷达 ECU 写配置」，对国产 SCC 未做车型隔离 | `hyundai/interface.py:183-188, 250-266` | **P1 安全** |

---

## 1. 项目概况与架构

### 1.1 谱系与代码布局

| 维度 | 事实 |
|---|---|
| Fork 谱系 | CarrotPilot（韩国 comma 系 fork）→ 再叠加 `cp-custo-amap` 库斯途/高德定制层。README 顶部仍保留韩文法律免责声明，`selfdrive/carrot/carrot_functions.py:449` 等位置残留 EUC-KR 转码失败的乱码 |
| 车辆代码位置 | **不在** `selfdrive/car/hyundai`，而在 **`opendbc_repo/opendbc/car/hyundai/`**（新版 monorepo 布局）。safety 固件同样下沉到 `opendbc_repo/opendbc/safety/safety/safety_hyundai*.h` |
| 自研代码位置 | `selfdrive/carrot/`（8 个 .py，6803 行）、`selfdrive/car/cruise.py`、`selfdrive/controls/lib/desire_helper.py`、`cereal/custom.capnp`、`cereal/services.py` |
| 依赖管理 | **无 `.gitmodules`**：`opendbc_repo / msgq_repo / panda / tinygrad_repo / rednose_repo / teleoprtc_repo / third_party` 全部以普通文件 **vendored** 进主仓（3695 个被跟踪文件）。上游对应关系只剩 `git_src_commit` 一行哈希 |
| 预编译产物 | 根目录 `prebuilt` 是 **0 字节标记文件**（不是目录），`launch_chffrplus.sh:116` 据此跳过 `build.py`；仓库里提交了 20+ 个 `.so`。设备上跑的二进制与源码的一致性在仓库内**无法自证** |
| 进程规模 | `system/manager/process_config.py` 共 56 条进程注册项；本 fork 额外常驻 `carrot_man`（`always_run`）、`fleet_manager`、`lane`（`only_onroad`），并**注释掉了 `loggerd`** |

### 1.2 数据流（本分支特有）

```
车机高德(AmapNavi-Reborn) ──UDP 5510/4210 探针握手──┐
   ▲ 遥测 20Hz (sendto :7706)                        │
   └── 指令 (LANECHANGE/OVERTAKE/CANCEL/mode) :7705 ──┤
                                                     ▼
   ESP32/激光雷达 BSD ── UDP 4211/4213 ──►  AmapNaviServ（线程×7，被内嵌进 carrot_man 进程）
                                                     │ SharedData（无锁全局可变对象）
                                                     ▼
                                             carrot_man（10Hz + Web:8088 + ZMQ:7710 + FTP）
                                                     │ pub: carrotMan / navRoute
                                                     ▼
   modeld(DesireHelper 在此实例化) ◄── sm['amapNavi']（alive 恒真）
     │ desire/laneChangeState/eventType
     ▼
   plannerd(longitudinal_planner / long_mpc)  ── carrot_functions（CarrotPlanner）
     ▼
   controlsd ─► carcontroller(hyundai) ─► panda(safety_hyundai) ─► C-CAN 500k
```

关键结构性事实（后文多条结论都依赖它）：

1. `DesireHelper` **只在 `modeld.py:363` 实例化**（`lateral_planner.py:34` 的构造被注释掉），因此 `desire_helper.py` 里的 `self.sm['amapNavi']` 取的是 **modeld 的 SubMaster**（`modeld.py:332` 已订阅 `amapNavi`，不会 KeyError，但见 §5/§6 的老化问题）。
2. `amap_navi` 作为独立进程**已被禁用**（`process_config.py:144` 注释：「由 carrot_man 内嵌实例独占 UDP，避免双实例端口竞争」），`AmapNaviServ` 在 `carrot_man.py:191` 构造，其 7 个线程全部跑在 carrot_man 进程内。
3. `amapNavi` 消息的发布者是 `amap_navi.py:193` 的 PubMaster，调用点为 `_data_deal_thread`（20 Hz）。

---

## 2. 阻断级缺陷（当前分支开不了机）

### 2.1 复现路径（已在沙箱内用真实加载器逻辑复算）

```toml
# opendbc_repo/opendbc/car/torque_data/override.toml:77
"HYUNDAI_CUSTIN_1ST_GEN" = [2.5, 2.5, 0.1]
# opendbc_repo/opendbc/car/torque_data/substitute.toml:43
"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"
```

```python
# opendbc_repo/opendbc/car/interfaces.py:69-80
@cache
def get_torque_params():
  ...
  for candidate in (sub.keys() | params.keys() | override.keys()) - {'legend'}:
    if sum([candidate in x for x in [sub, params, override]]) > 1:
      raise RuntimeError(f'{candidate} is defined twice in torque config')
```

沙箱复算结果（按仓库当前文本）：

```
DUPLICATED: ['HYUNDAI_CUSTIN_1ST_GEN']      # 唯一冲突项恰好就是库斯途
```

调用链：`card.py → get_car() → CarInterface.get_params() → get_std_params()`（`interfaces.py:499` 取 `maxLateralAccel`）以及 `configure_torque_tune()`（`interfaces.py:528`，所有非 ANGLE_CONTROL 的现代车都会走，包含库斯途）。

### 2.2 影响

* **这不是"库斯途专属"故障，是全车型故障**：`get_torque_params()` 在遍历所有候选时抛错，与当前识别到的车型无关。也就是说这个分支刷机后 `card` 起不来、pandad 收不到 controls 输入，onroad 完全不可用。
* 该缺陷由 `493e8dd fix(audit-remediation): … and NNFF mapping` 这个**审计修复提交**引入——为了"把库斯途映射到帕里斯帝"而在 `substitute.toml` 加了一行，却没注意到 `override.toml` 里早已存在库斯途条目。这说明**分支没有任何 CI/最小冒烟测试**（`.github/workflows/` 里的是上游模板，本 fork 未跑 `test_car_interfaces`/`test_lateral_limits`，否则第 3 秒就会被抓到）。

### 2.3 修复（二选一，语义完全不同，必须显式决策）

| 方案 | 结果 | 评价 |
|---|---|---|
| 删 `override.toml:77`，留 `substitute→PALISADE` | 库斯途用帕里斯帝**实测值** `[2.5446, 1.8722, 0.1301]` | ✅ 推荐。数据来自 torqued 实测，且与文档宣称的"映射帕里斯帝"一致 |
| 删 `substitute.toml:43`，留 `override=[2.5, 2.5, 0.1]` | `latAccelFactor=2.5 / MAX_LAT_ACCEL_MEASURED=2.5 / friction=0.1` | ⚠️ 手拍值。`MAX_LAT_ACCEL_MEASURED=2.5 m/s² ≈ 0.255 g` 比帕里斯帝实测 1.87 乐观 **34%**，对高重心、后扭力梁的 7 座 MPV 是**错误的横向能力上界**（会污染 `steerLimited` 判定） |

> 补充：即使修好重复定义，§9 会说明这些标定值在运行时**被 `LateralTorqueCustom=1` 整体短路**，实际跑的是 `LateralTorqueAccelFactor=3000→3.0`。也就是说 TOML 里写什么都没用——标定层放错了位置。

### 2.4 次级启动风险（同属"开不了机/悄悄降级"类）

* `hyundai/carstate.py:123-124`：构造期 `ast.literal_eval(Params().get("FingerPrints"))` 无 try 保护。`FingerPrints` 是 `str(dict)` 落盘（`car_helpers.py:208`），库斯途总线地址多、字典大，一旦截断/缺失 → CarInterface 起不来且**无提示**。
* `carrot_serv.py:314`：`int(self.params.get("AutoCurveSpeedLowerLimit"))` —— `UnifiedParams.get` 未命中返回 `None` → `TypeError`，被上层宽 `except` 吞掉（见 §7），后果是"导航限速/自动弯道减速整体静默停摆"，而进程看起来正常。

---

## 3. 与库斯途车辆特性不匹配的代码（专项）

### 3.1 车型定义的实际形态（先厘清"我们开的到底是哪台车"）

```python
# opendbc_repo/opendbc/car/hyundai/values.py:445-449
HYUNDAI_CUSTIN_1ST_GEN = HyundaiPlatformConfig(          # ← 经典 CAN（非 CanFD 构造器）
  [HyundaiCarDocs("Hyundai Custin 2023", "All",
                  car_parts=CarParts.common([CarHarness.hyundai_k]))],
  CarSpecs(mass=1690, wheelbase=3.055, steerRatio=17),
  flags=HyundaiFlags.CHECKSUM_CRC8,                       # ← 只有 CRC8，无 CAMERA_SCC / MANDO_RADAR / EV / ANGLE_CONTROL
)
```

由此推导出的行为（均可在代码中确认）：

| 项目 | 结论 | 证据 |
|---|---|---|
| 总线 | 经典 500 kbps C-CAN，DBC = `hyundai_kia_generic` | `values.py:183`，`carstate.py:694-701`（`Bus.pt=0`、`Bus.cam=2` 硬编码） |
| 横向控制 | **torque 控制**（`LatControlTorque`），不是角度控制 | `interface.py:169-172`；`ANGLE_CONTROL` 未置位 |
| 纵向 | 默认被强制为 openpilot 长控（见 §3.5） | `interface.py:183-188` |
| 文档年份 | 仅 `2023` 一档，README/`docs/custin/*` 却宣称支持 **2021–2024** | `values.py:446` vs `docs/custin/VEHICLE_DYNAMICS.md:3` |

> **第 1 条不匹配**：车型文档写 "Custin 2023"，但本分支自述覆盖 2021–2024。国产库斯途 2021 款与 2023/2024 款在 ADAS 供应商与固件上存在差异（见 §4.4 指纹），把年域写窄会让 `docs/CARS.md` 与用户预期错位，写宽则需要补指纹——目前是**两头都不成立**。

### 3.2 CarSpecs：抄自台湾版、来源标注自证不可靠

```python
CarSpecs(mass=1690, wheelbase=3.055, steerRatio=17),
# 注释: mass: from https://www.hyundai-motor.com.tw/clicktobuy/custin#spec_0 , steerRatio: from learner
```

同一段注释被**连续复制给另外两款车**（`values.py:452` CASPER、`values.py:458` CASPER_EV 的注释仍指向 `.../custin#spec_0`），是"参数靠复制粘贴"文化的实锤。具体问题：

| 参数 | 现值 | 库斯途（国产）情况 | 影响 |
|---|---|---|---|
| `mass` | 1690 kg（**台湾版整备**） | 国产 2.0T 公开值约 1.73–1.78 t；`docs/custin/VEHICLE_DYNAMICS.md` 自己写"满载 7 人 + 行李 2200–2300 kg" | 质量进入 `StiffnessRotationTorqueParams`/横向观测/长控限幅。系统性偏轻 → **同方向盘转角下模型认为横向加速度更高**→ 实际推头；也影响制动余量估计。`STD_CARGO_KG=136`（`opendbc/interfaces.py:14`）对 7 座 MPV 明显不足 |
| `steerRatio` | 17（来自 learner） | 17 对 MPV 偏大（同集团 Staria 11.94、Ioniq 9 为 16.02） | 曲率↔方向盘角换算错 → 低速大幅修正画龙 / 回正不足 |
| `centerToFront` | `wheelbase * 0.4 = 1.222 m`（全现代一刀切，`interface.py:166`） | 长轴 + 前机舱 + 三排座椅，质心比轿车更靠后 | 横向观测器/横摆模型残差被 3.055 m 轴距放大 |
| `minEnableSpeed` | **未设**（默认 `-1.0`，`opendbc/car/__init__.py:306`） | 国产现代 ACC 常有最低激活速度（历史上的 `FCA_11_KPH` 语义） | 模型里现代老标志位（`FCA_11_KPH/NO_STOP_LEAD/…`）在新架构已不存在，本分支也**没有用 `minEnableSpeed` 表达"这车低速开不了 ACC"**。后果：`selfdrived/events.py:238` 在任何车速都提示可激活；UI/报警节奏与现实不符 → **需实车确认** |
| `stopDistance`/`stopping` 相关 | 未针对 MPV 上调 | 满载制动距离显著长于 SUV/轿车 | 跟停距离偏近 |
| `tireStiffnessFactor` | 未设（=1.0） | 后扭力梁 + MPV 轮胎（多为 215/70R17 高扁平比） | 侧偏刚度假设偏乐观 |

### 3.3 横向标定：EPS 力矩域与"最后防线"

```python
# values.py:36-72（CarControllerParams）——库斯途走 else 默认分支
self.STEER_MAX = 409        # 默认；上游注释明写「若原厂 LKAS 请求上限 <384，把车加进名单」
# values.py:65 注释原文：
# "To determine the limit for your car, find the maximum value that the stock LKAS will request."
```

* 库斯途**没有**被放进 `<384` 名单，也没有 override，直接用 409。国产 MDPS（`56310/O3100`，见 fingerprints）厂商标定常为 340/384 档，**409 未经测量**（`需日志验证`）。
* 更严重的是 safety 侧（§5.2）：`HYUNDAI_LIMITS(512, 10, 10)` 且校验被注释掉 → **软件层 `STEER_MAX` 猜错时，硬件层不再兜底**。对高重心 MPV，这直接对应"突发大扭矩/救车过冲"风险。
* `STEER_DELTA_UP = 3 / DOWN = 7`（100 Hz）也是全现代通用值，未按库斯途 EPS 响应重标。
* 现代车特有的 **EPS "ActToi 保活"窗口**被沿用：`min_valid_request_frames = 89, max_invalid_request_frames = 2`（`safety_hyundai.h:17-19`，配合 `carcontroller.py:19-21,165-167`）。这个 90 帧窗口是从 Santa Fe 一类车型测出来的，**库斯途 MDPS 是否同参数未验证**（`需实车`）。若不匹配，典型症状是"连续转向数分钟后 LKAS 自动退出/仪表报 LKAS 故障"。

### 3.4 驾驶员状态判定：HOD 完全没被使用

* CAN 路径下 `steeringPressed` **只用力矩阈值**：`carstate.py:235` `abs(steeringTorque) > 150`（`STEER_THRESHOLD`，`values.py:44`）+ 5 帧去抖。
* 电容方向盘（HOD / `STEER_TOUCH_*`）解析只存在于 CANFD 分支（`carstate.py:488-489, 559`）。库斯途走 CAN，**即使实车有电容 HOD，本移植也读不到**。
* 后果（对库斯途尤其明显，因为 MPV 长途、方向盘握持轻）：
  1. 轻握不打方向 → 力矩不过 150 → openpilot 认为"手不在盘上"，触发过度告警；
  2. 反过来，路面颠簸/大车转向惯性产生的瞬时分量，可能被当成"驾驶员在施加方向"——`desire_helper.py:1350-1352` 本分支已把"反向打盘才退出变道"改成 **`steering_pressed` 即退出**（`carstate.steeringPressed`），叠加力矩阈值噪声 → **变道会被路面噪声打断**（这是"更安全但更恼人"的取舍，见 §6.4）。
* `需实车验证`：国产库斯途是否具备 HDA_HOD 类报文；若有，应解析并用作 engaged/驾驶员检测输入。

### 3.5 纵向：8AT、起步、走停、雷达下线（**本分支对 MPV 最不合适的一组改动**）

```python
# opendbc_repo/opendbc/car/hyundai/interface.py:179-207
ret.radarUnavailable = RADAR_START_ADDR not in fingerprint[1] or Bus.radar not in DBC[...]   # 库斯途 → True
ret.openpilotLongitudinalControl = alpha_long and ret.alphaLongitudinalAvailable
# carrot, if camera_scc enabled, enable openpilotLongitudinalControl
if ret.flags & HyundaiFlags.CAMERA_SCC.value or params.get_int("EnableRadarTracks") > 0:
  ret.radarUnavailable = False
  ret.openpilotLongitudinalControl = True if camera_scc != 3 else False
...
ret.startingState = False # True  # carrot
ret.vEgoStarting = 0.1
ret.startAccel = 1.0
ret.longitudinalActuatorDelay = 0.5
ret.longitudinalTuning.kpV = [1.]; ret.longitudinalTuning.kf = 1.0
```

`system/manager/manager.py:124` 把 `("EnableRadarTracks", "1")` 作为**出厂默认**种入，因此对库斯途而言：

* 默认走 **「原厂 SCC 雷达下线（UDS `28 83 01` @0x7d0）+ openpilot 接管纵向」**；
* `CarInterface.init()`（`interface.py:263-266, 272-299`）**每次启动都向雷达 ECU 写配置项**：`10 07`（扩展会话）+ `2E 01 42` 写入 `b"\x00\x00\x00\x01\x00\x01"`。对一台从未验证过的国产 Mando 雷达（`99110-O3000`）做**非只读诊断写入**，中途掉电或 DID 语义不符都可能留下不良配置。同时 `disable_ecu` 关的是**原厂 FCW/AEB 的执行侧**。

对库斯途的具体不合适之处：

1. **前车信息来源退化**：`radar_interface.py:44-55, 258-304` 回退到解析 SCC11 融合目标，而 `hyundaican.py:261-274` 在长控模式下**由 openpilot 自己伪造 SCC11 的 `ACC_ObjStatus/ACC_ObjDist`** → 模型→SCC11→RadarData→规划存在**自回环**（误检的前车可能长期驻留）。这是现代车型通用风险，但对"MPV 家庭用车 + 城市跟停"场景尤其刺眼。`需日志`：观察 `modelLead` 与 SCC11 回显的耦合。
2. **拓扑硬编码**：`enable_radar_tracks` 里 `sccBus = 2 if CAMERA_SCC else 0`、`disable_ecu(bus=0)`。库斯途未置 `CAMERA_SCC`，若国产版 SCC/雷达实际挂在另一条 bus，这两个操作**静默失败**（`EnableRadarTracksResult` 有回写但无人消费告警），表现为"看起来开了长控，但跟不住车"。
3. **`startingState = False`**：上游用 `vEgoStarting/startAccel` 处理"从静止起步"的专用逻辑被关掉，起步交给按钮 spam（`carcontroller.py:486-491`：`if hud_control.leadVisible or v_ego_kph > 10.0: send_button = Buttons.RES_ACCEL`）。这条隐含假设「库斯途 ACC 在 >10 km/h 或能看到前车时可用 RES 恢复」——**若国产库斯途是全速域 S&G 则多余，若不支持静止恢复则会反复 spam RES、仪表闪烁、误判可起步**。
4. **`startAccel = 1.0` + `longitudinalActuatorDelay = 0.5`（文档第 3 条）**：对涡轮 + 液力变矩器 8AT，`1.0 m/s²` 目标配合 0.5 s 执行延迟，仍是"命令先给、扭矩后到"的阶跃；`docs/custin/VEHICLE_DYNAMICS.md` 把它描述成"抛物线平缓释放、彻底消除 1-2 挡顿挫"——**代码里不存在任何抛物线/S 曲线生成**，`startAccel` 只是一个常数。这是文档与实现的实质偏差（§11）。
5. `ACCEL_MIN/MAX = -4/+2.5`（`values.py:15-16`）未随 MPV 变化。满载 2.3 t 时 +2.5 m/s² 根本执行不到 → 控制器与实际能力失配（积分/延迟表现变差）。

### 3.6 车身尺寸相关：盲区/变道阈值仍是轿车标定

`amap_navi.py` 里由车身尺寸推导的障碍判定框，多处仍是轿车经验值：

* `amap_navi.py:1159-1160` 兜底值 `lf_drel if ... else 0.1` / `0.`（**单位是 mm 的信号流里塞进 0.1/0**，与 `:1161` 的 `<= 1000 / >= -1000`（mm）判断量级冲突；见 §7「单位混用」）。
* 车身/侧向盲区框的 `+3000 / -1000 / ±5000 mm` 一类常量（`amap_navi.py:436-468, 722-741`），"车头前 3 m"对 **4950 mm 车长、3055 mm 轴距**的车只覆盖约半个车身：侧后雷达刚扫到车尾之后的目标即进入判定区，MPV 变道本应要求**更大**的接受间隙。
* 同一块左右侧逻辑是复制粘贴（`:722` 与 `:739` 复用同名局部变量 `lf_limit_val`），极易在只改一侧时出错。

> 建议：把这些常量收敛为 `CUSTIN_GEOMETRY = {length:4.95, width:1.85, wheelbase:3.055}`，判定式统一由几何推导（`rear_bumper = -length/2` 等），并给 MPV 的接受间隙/TTC 下限乘一个大于 1 的系数（§12）。

### 3.7 文档宣称"已落地"的六项专车调校，实际情况

| 文档条目（`docs/custin/VEHICLE_DYNAMICS.md`） | 代码事实 |
|---|---|
| ① 帕里斯帝 NNFF 神经网络力矩模型 + 150 ms 前馈偏航补偿 | **不成立**。NNFF 模型按平台名精确/相似度匹配：`lat_models/` 无 `HYUNDAI_CUSTIN*`，`get_nn_model_path` 要求相似度 ≥0.9（`SequenceMatcher("HYUNDAI_CUSTIN_1ST_GEN","HYUNDAI_PALISADE")≈0.53`）→ 返回 None；`manager.py` 默认 `("NNFF","0")`。`substitute.toml` 只影响 **analytic** torque 参数，**不影响 NN 模型选择**。"150 ms 前馈偏航补偿"在全仓无任何对应代码 |
| ② 7 座 MPV 5.0 s 平缓变道 S 曲线、横向 ≤0.08 g、jerk ≤0.05 g/s | **不成立**。`desire_helper.py:18` 只有 `LANE_CHANGE_TIME_MAX = 10.`（超时上限，不是 5 s 执行时长），淡入淡出仍是 `.5 s/1 s` 比例；全仓搜不到 `5.0`、`0.08*9.81`、`0.05 g/s` 相关常量 |
| ③ 8AT 起步防顿挫固化 `startAccel = 1.0` | 代码存在（`interface.py:203`），但为**全现代车型共用**、非库斯途专属，且见 §3.5-4 的效果分析 |
| ④ 红绿灯停稳锁零防蠕动 | 存在（`carrot_functions.py` e2e 相关分支），但与 §3.5 的 `startingState=False` 叠加后，红绿逻辑与"锁零"的交互未被状态机约束（§7 M 级） |
| ⑤ 仪表盘 `0x485 LFAHDA_MFC` 20 Hz 联动点亮 | **成立**。`safety_hyundai.h:32` TX 白名单含 `{0x485,0,8}`；`carcontroller.py:353-355` 每 5 帧发一次（100 Hz/5 = 20 Hz）；`hyundaican.py:119-131` 组包；`interface.py:135-136` 依据 `0x485 in fingerprint[2]` 自动置 `SEND_LFA`。这是六条里唯一完全对得上的 |
| ⑥ 暴晒驻车温控：offroad 强制关断 4 个大核并释放 GPU 供电轨 | `system/hardware/tici/hardware.py` 无该逻辑（该文件最后一次改动是通用 carrot 提交），属把 **上游 Comma 3 电源管理行为**包装成"库斯途专属调优" |

> **结论**：README/文档给出的"五大/六大专车调校"中，**只有 ⑤ 完全成立，③④ 部分成立但并非库斯途专属，①②⑥ 与代码不符**。对安全类开源项目，这类"宣传性标定"本身是风险（用户会按文档预期去信任系统能力，尤其 ①②直接描述横向能力与变道平顺性）。

### 3.8 "抄别的车"的痕迹（同族污染）

* `values.py:452/458`：Casper / Casper EV 的规格注释仍指向 `.../custin#spec_0`。
* `carcontroller.py:90`：`angle_max_torque = 240` 基准值来自别的车型族，用于动态 `lkas_max_torque` 归一（`:183-210`）。
* `lidar_speed_test.py:7-75` 与 `amap_navi.py:25-93` 的 `RadarSpeedEstimator` 是**两份逐字相同实现**（`max_acc=4.0 m/s²` 也按轿车取值），改一忘一。

---

## 4. 现代 / CAN 协议层移植质量问题

### 4.1 做得对的部分（先给公允评价）

* LKAS11 alive 计数 `CF_Lkas_MsgCount = frame % 0x10`（`hyundaican.py:35`，100 Hz，4 bit 正确）；
* SCC12 校验和算法（`hyundaican.py:197-198` 的 `0x10 - (nibble sum) % 0x10`）与 ESC 侧需求一致；
* panda 侧对 0x260 / 0x386 / 0x394 / 0x421 做了 counter+CRC 校验（`safety_hyundai.h:46-59` `HYUNDAI_COMMON_RX_CHECKS` + `hyundai_get_counter`）；
* 车型能力（`SEND_LFA`/`USE_FCA`/`ESCC`/`CAMERA_SCC`）由 **指纹地址自动判定**（`interface.py:130-149`），而不是写死车型名单——这是正确做法。

### 4.2 TX 白名单里的报文长度错误（会导致发送被 panda 静默拒收）

```c
// safety_hyundai.h:29-43  HYUNDAI_TX_MSGS（默认/非 long 列表）
{1186, 0, 8},   // FRT_RADAR11, Bus 0   ← 声明 8 字节
```
```dbc
// hyundai_kia_generic.dbc:1484
BO_ 1186 FRT_RADAR11: 2 FCA              ← 实际 2 字节
```
而长控列表里写的是正确的 `{0x4A2, 0, 2}`（`safety_hyundai.h:350`、`:427`）。

`safety.h:231-244` 的 `tx_msg_safety_check` 要求 **addr + bus + length 三者精确匹配**，因此非长控模式下 `create_frt_radar_opt()`（`hyundaican.py:350-354`，用于"骗 TCS 说雷达在位"）的每一帧都会被 safety 固件拒发。影响面小（多数情况走长控），但说明**默认列表被按长控列表批量扩写时没有逐一校对 DLC**。同时会持续触发 panda 的调试打印（见 4.3）。

### 4.3 被塞进 safety 固件的调试打印（实时性与可靠性风险）

`safety.h:232-253, 258-285`：`_prev_not_allowed_addr` / `_prev_error_addr` 两个模块级全局 + 整表 dump（`print("allowed addr = ")` 后循环 `putui`）。

* 上游有意避免在 safety hook 里做串口输出（F1/H7 上串流阻塞会干扰 CAN 处理节奏）。fork 加了带"去重"的 print，作为调试手段可理解，但**量产移植应改为计数器 + `health` 字段上报**。
* Python 侧同样大量 `print("$$$…")`（`hyundai/interface.py:186,199,224,227`、`carrot/*` 共 267 处），而 `loggerd` 已被停用（§5.6）→ 这些信息只留在 tmux 屏幕缓冲区。

### 4.4 指纹质量：单固件样本 + ABS 可缺 + 失败即 MOCK

```python
# opendbc_repo/opendbc/car/hyundai/fingerprints.py:354-367
CAR.HYUNDAI_CUSTIN_1ST_GEN: {
  (Ecu.abs, 0x7d1, None):       [b'\xf1\x00KU ESC \x01 101!\x02\x03 58910-O3200'],
  (Ecu.fwdRadar, 0x7d0, None):  [b'\xf1\x00KU__ SCC F-CUP      1.00 1.01 99110-O3000         '],
  (Ecu.eps, 0x7d4, None):       [b'\xf1\x00KU  MDPS C 1.00 1.01 56310/O3100 4KUCC101'],
  (Ecu.fwdCamera, 0x7c4, None): [b'\xf1\x00KU2 MFC  AT CHN LHD 1.00 1.02 99211-O3000 220923'],
}
```

* `AT CHN LHD` 说明指纹确实取自国产版（**这点是对的**）；但**每个 ECU 各只有 1 条固件串**，任一 ECU 换供应商/年款（2021→2024）strict 匹配即失败，只能落到 fuzzy（`values.py:837-880`，靠 `KU` 平台码 + 日期窗）。
* `values.py:971-975` 把 CUSTIN 列入 `non_essential_ecus[Ecu.abs]`：无 comma power 时仅 3 个 ECU 参与匹配。**由于每 ECU 只有 1 条串，任何一条对不上就整体失败**，没有"部分匹配"缓冲。
* 失败后：`car_helpers.py:157-159` 回落 **MOCK**，随后 `CarSelected3` 允许按名字**强选车型**（`car_helpers.py:160-203`）—— 强选绕过全部 ECU/总线一致性校验，等于把"轴距 3055 / steerRatio 17 / STEER_MAX 409"的库斯途参数刷到一台未被识别的车上。
* `card.py:84` `is_release = True #self.params.get_bool("IsReleaseBranch")` 硬编码为真，使依赖 `is_release` 的分支（含 `card.py:129` 的 `secOc` 校验）语义被永久固定。

### 4.5 现代特有的"EPS 保活 / 原厂抑制"机制在本车无数据支撑

* `carcontroller.py:19-21,165-167` + `safety_hyundai.h:17-19`：`ActToi` 的 89 帧窗口 / 最多 2 帧无效——沿用 LKAS 车型（Santa Fe 等）标定（§3.3）。
* `hyundaican.py:357-375 create_mdps12()`：向 bus2 回播 MDPS12 并**强制 `CF_Mdps_ToiUnavail = 1`、`CF_Mdps_ToiActive = 0`**，目的是让原厂 LKAS 保持"哑火"，避免与 openpilot 抢方向盘。这属于**改写原厂 EPS 意图**的操作，必须实车验证；且该函数直接改写传入的 `mdps12` 原 dict（`values = mdps12` 未 copy），存在跨帧状态污染隐患。

### 4.6 信号自回环（openpilot 解析自己发出去的报文）

经典 CAN 长控模式下 openpilot 会**伪造** SCC11（`hyundaican.py:261-274`：`ACC_ObjStatus = 1 if hud_control.leadVisible`），而 `radar_interface.py:44-55, 282-302` 在 `EnableRadarTracks` 打开时又**从 bus0 解析 SCC11 作为前车来源**。模型 → SCC11 → RadarData → 规划的闭环存在自激风险（误检的前车可能长时间驻留）。`radar_interface.py:127-155` 两个 `CANParser`（scc / tracks）的 `updated_scc.clear()` 出现在 `:130` 与 `:146` 两处，更新条件互相缠绕，属易错结构。→ `需日志验证`。

### 4.7 总线拓扑硬编码

`carstate.py:694-701` 固定 `Bus.pt=0 / Bus.cam=2`；`hyundaican.py` 全部 ADAS 报文打 bus0（按钮在 `CAMERA_SCC` 时改 bus2，`:115/362`）；`enable_radar_tracks` 的 `sccBus = 2 if CAMERA_SCC else 0`（`interface.py:276`）。国产 topology 一旦不同，表现为**静默失灵**（有 print，无 event）。→ `需实车总线映射图`。

---

## 5. 安全模型被削弱的改动清单（红线）

> 上游 openpilot 的安全模型是**分层**的：Python 侧限幅 → panda safety 固件独立校验 → 报警/脱开/禁止激活。本分支在**每一层都做了减法**，叠起来的结果是"只剩一层软件限幅，而这一层出错时无人知晓、无日志可查"。以下每一条都在代码中逐字确认。

### 5.1 横向扭矩：panda 校验被"算而不拦"

```c
// opendbc_repo/opendbc/safety/safety/safety_hyundai.h:204-206, 249-258
const TorqueSteeringLimits HYUNDAI_STEERING_LIMITS     = HYUNDAI_LIMITS(512, 10, 10);
const TorqueSteeringLimits HYUNDAI_STEERING_LIMITS_ALT = HYUNDAI_LIMITS(512, 10, 10);
...
if (steer_torque_cmd_checks(desired_torque, steer_req, limits)) {
  //tx = false;                    ← 校验结果被丢弃
}
```
```c
// safety_hyundai_canfd.h:7
.max_steer = 512, //270,           ← 上限被抬高 90%
// safety_hyundai_canfd.h:357-358
//tx = false;                       ← 同样注释掉
```

被绕过的内容：幅值上限（512）、每帧变化率（`max_rate_up/down = 10`）、驾驶员扭矩容差（`driver_torque_allowance=50 / multiplier=2`）、`max_rt_delta=112`（瞬时跳变）、以及 89 帧 ActToi 容差。**唯一残余约束**是 Python 侧 `STEER_MAX`（库斯途为未实测的 409）与 `STEER_DELTA_UP=3`。

**为什么这条对库斯途特别糟**：3 吨级前馈假设（帕里斯帝 substitute）+ 大轴距 + 高重心 + 后扭力梁，一旦上位参数错（如 §9 的 `LateralTorqueAccelFactor=3.0`），EPS 会**没有任何硬件兜底地**把这个扭矩打进转向柱。

**修复**：恢复 `tx = false;`；把 `max_steer` 回到实测的原厂 LKAS 上限（先取 384 保守值，用日志确认后再调）。

### 5.2 激活动画：发 own 报文即取得控制权

```c
// safety_hyundai.h:223-228
if (addr == 0x421) {
  int cruise_engaged = (GET_BYTES(to_send, 0, 4) >> 13) & 0x3U;
  if (cruise_engaged) {
    if(!controls_allowed) print("auto engage controls_allowed....\n");
    controls_allowed = true;                  // ← 由 openpilot 自己发出的报文置位
  }
```
```c
// safety_hyundai_common.h:79-85
if (!hyundai_longitudinal) {
    hyundai_last_button_interaction = 0U;     // carrot
  //if (cruise_engaged && !cruise_engaged_prev && (hyundai_last_button_interaction < HYUNDAI_PREV_BUTTON_SAMPLES)) {
    if (cruise_engaged) { controls_allowed = true; }
```
上游要求"ACC 上升沿 + 近期用户按过按钮"才进入控制态；这里去掉按钮门，等价于**只要软件发出 cruise_engaged=1 即可自动进入控制态**（含被远程/自动激活的路径，见 §5.4 与 §6 的 UDP 面）。

同时：`hyundai_longitudinal` 仅在 `ALLOW_DEBUG` 构建生效（`safety_hyundai_common.h:71-76`），而 `interface.py:229-231` 无条件把 `LONG` 写进 safetyParam → **量产固件里 Python 与 panda 对"这是不是长控车"的认知根本不一致**，engage 语义完全依赖上面的后门。

### 5.3 AEB/制动命令不再受限

```c
// safety_hyundai.h:232-241
//int aeb_decel_cmd = GET_BYTE(to_send, 2);
//bool aeb_req = GET_BIT(to_send, 54U);
violation |= longitudinal_accel_checks(desired_accel_raw, HYUNDAI_LONG_LIMITS);
violation |= longitudinal_accel_checks(desired_accel_val, HYUNDAI_LONG_LIMITS);
//violation |= (aeb_decel_cmd != 0);
//violation |= aeb_req;
```
openpilot 可以在 SCC12 里置**伪装成原厂 AEB 的** `CF_VSM_DecCmd / AEB_CmdAct / StopReq`。FCA11（0x38D）仍被拦（`:211-219`），说明作者只是"顺手注释"，不是一致的安全设计。

按钮通道同样被放宽：`safety_hyundai.h:268-270` `bool allowed_resume = (button == 1);// && controls_allowed;` —— **RES/加速按钮不再要求 controls_allowed**，任何车速下都可 spam。

### 5.4 软件层对硬件安全配置的一致性校验失效

```python
# selfdrive/selfdrived/selfdrived.py:353-361
safety_mismatch = pandaState.safetyModel not in IGNORED_SAFETY_MODES
safety_mismatch  = False #carrot                       # ← 无条件覆盖
if (safety_mismatch and self.sm.frame*DT_CTRL > 10.) or pandaState.safetyRxChecksInvalid or self.mismatch_counter >= 200:
```
panda 被刷成 `silent/noOutput` 以外的任何错误 safety（例如 ALLOUTPUT、或别的车型），**onroad 不再报 controlsMismatch**。这是"硬件安全层配错"的唯一告警通道。

### 5.5 未 engage 也能打方向（挡位旁路）

```python
# selfdrive/controls/controlsd.py:139-148
driving_gear = CS.gearShifter not in (gear.neutral, gear.park, gear.reverse, gear.unknown)
lateral_enabled = driving_gear
...
CC.latActive = ((self.sm['selfdriveState'].active or lateral_enabled) and CS.latEnabled and ...)
```
挂 D 挡即允许横向输出，与 `enabled` 解耦（这是 carrot 的"全时 LKA"取向）。叠加 §5.1（panda 不拦）与 §5.2（无需按钮即取得控制权），意味着**方向盘可能在 UI 显示未激活的状态下出力**。对家庭 MPV 用户，这是最容易造成"我没开它怎么自己在转"的信任崩塌与事故点。

另外 `events.py:778-781` 把 `wrongGear` 从 `SOFT_DISABLE` 降为 `USER_DISABLE`：行驶中挂 N 不再软退出。

### 5.6 看门狗与"带病运行"

```python
# selfdrive/selfdrived/selfdrived.py（7 处 pass#）
378: pass#self.events.add(EventName.processNotRunning)
382: pass#self.events.add(EventName.cameraMalfunction)
406/410: pass#self.events.add(EventName.commIssue)
408: pass#self.events.add(EventName.commIssueAvgFreq)
435: pass#self.events.add(EventName.sensorDataInvalid)
473: pass#self.events.add(EventName.noGps)
```
上游这些事件是 **SOFT_DISABLE + NO_ENTRY**（进程挂了/摄像头断流/CAN 通信异常 → 退出并禁止再激活）。静音后 `manager` 仍会重启进程，但**期间系统照常控制车辆**。再叠加 `loggerd` 停用：

```python
# system/manager/process_config.py:85
#NativeProcess("loggerd", "system/loggerd", ["./loggerd"], logging),
NativeProcess("encoderd", ..., only_onroad),        # 编码器照跑，但没有 logd 段目录
```
→ **出事时既没有报警，也没有 qlog 可复盘**。这与 `carrot` 目录里 267 个 `print()`、0 个 `cloudlog` 形成鲜明对比：诊断信息只存在于 tmux 屏幕缓冲区，靠 `carrot_man.py:758` 的 `tmux capture-pane` 抓屏上传。

### 5.7 驾驶员监控默认关闭

```python
("DisableDM", "1"),                                                   # manager.py:172（出厂默认）
return (started or params.get_bool("IsDriverViewEnabled")) and params.get_int("DisableDM") == 0   # process_config.py:77（进程不启动）
if not self.CP.notCar and self.params.get_int("DisableDM") == 0: ...  # selfdrived.py:182（DM 事件不进）
cs.forceDecel = bool((awarenessStatus < 0. and DisableDM == 0) or softDisabling)   # controlsd.py:357（降级减速一并屏蔽）
```
`DisableDM=1` 时是**三处同时生效**：模型不跑、事件不加、失联不减速。再叠加 §5.6 的 `cameraMalfunction` 静音 → **驾驶员摄像头坏了系统完全无感**。这是所有条目里最接近"法规红线"的一条（README 顶部只保留了韩文免责声明，未说明这些默认关）。

同类还有：`RecordAudio="1"`（`manager.py:35`，上游默认关，涉及乘员录音合规）、`MuteSeatbelt`/`MuteDoor`（参数键存在，可屏蔽安全带/车门报警）。

### 5.8 未鉴权的远程命令执行与凭据泄露（安全 = 供应链 + 车辆总线入口）

| 面 | 位置 | 事实 |
|---|---|---|
| UDP 4213 `echo_cmd` | `amap_navi.py:810` bind `0.0.0.0:4213`；`:838-853` | `subprocess.run(json_obj['echo_cmd'], shell=True)` —— **任意命令执行，无鉴权无白名单** |
| ZMQ/TCP 7710 `echo_cmd` | `carrot_man.py:841` `bind("tcp://*:7710")`；`:881-896` | 同上 |
| Web 参数写入 | `web_interface.py:30-36` + `:277`（`HTTPServer('0.0.0.0', 8088)`） | `store_toggle_values` 对**任意 key** 直接 `params.put`，无鉴权/白名单/范围校验。可远程写 `OpenpilotEnabledToggle`、`DisableDM`、转向标定 |
| 明文 FTP + 仓库内口令 | `carrot_man.py:764-770`（`shind0.synology.me:8021`, user `carrotpilot`）、`:875/:880`（密码 `Ekdrmsvkdlffjt7710` 写死两处）、`selfdrive/frogpilot/fleetmanager/fleet_manager.py:105-111` | onroad 约 50 s 后**自动**上传 `tmux.log` + 全参数表（`send_settings=True`）；`fleet_manager` 亦自动上传路线 |
| UDP 信令伪造 | `carrot_man.py:626`（bind 7706）、`amap_navi.py:648`（bind 7705） | 车机指令通道仅靠"记住第一个 IP"（`amap_navi.py:1009`，只在 `_update_command` 生效）；`_update_blinker`/`_update_control`/`_update_sensors` **无来源校验** → 同网段可伪造盲区/转向灯/限速 |
| 时间写入 | `carrot_serv.py:1600/1603/1639` | `os.system(f"sudo timedatectl set-timezone {timezone_remote}")`，`timezone_remote` 来自手机 UDP JSON，未做字符白名单 → 命令注入面（当前调用点被注释，属休眠） |
| 开机自删脚本 | `launch_openpilot.sh:2-8` | `yes \| bash 1.sh && rm -- 1.sh`：执行不在仓库内的脚本 |
| 热更新 | `restart.sh`（`git pull` + tmux） | 远端仓库被劫持即等于全设备被接管 |

> 一台挂在转向柱上的设备同时开放：RCE × 2、无鉴权写参数 × 1、明文凭据 × 1、`git pull` 自更新。**这些不是"隐私建议"，是 CAN 总线的远程入口**：拿到 7710/4213 就等于拿到 §5.5 的横向输出控制权。

### 5.9 传感器/ECU 侧的不可逆动作

* `interface.py:256-260`：`disable_ecu(bus=0, addr=0x7d0, com_cont_req=b'\x28\x83\x01')` —— 关掉原厂 SCC 雷达即**原厂 FCW/AEB 的执行侧**。
* `interface.py:272-299`：`enable_radar_tracks` 向雷达写 DID `0x0142`。库斯途的 `99110-O3000` **从未验证支持该 DID**。
* 两者都无"写入失败即禁止进入 openpilot 长控"的兜底（`EnableRadarTracksResult` 有写但无消费）→ 静默半失效状态。

### 5.10 其他 fail-open 细节

| 位置 | 问题 |
|---|---|
| `latcontrol_torque.py:135-161` + `manager.py:151-157` | `LateralTorqueCustom` 默认 **1** → `update_live_torque_params()` 直接 `return`，**torqued 在线学习被永久关闭**，改用 `LateralTorqueAccelFactor=3000→3.0`（库斯途实际约 2.4–2.5）。且"1→0 复位"分支写成 `if self.lateralTorqueCustom > 1`，**复位永远不触发** |
| `controlsd.py:274-277` | 单帧 `\|a\|>16 m/s²` 即判定碰撞 → 写 `OpenpilotEnabledToggle=False` **+ 同步落盘在 100 Hz 线程内**。库斯途过减速带/坑洼（尤其满载）叠加到 1.6 g 不罕见 → 行驶中突然卸载系统且需人工恢复。应多帧确认 + 阈值 ≥25 m/s² |
| `long_mpc`/`longitudinal_planner.py:279-284` | `not has_lead` 时把 `accel_limits_turns[0]` 钳到 `-0.15`；`v_cruise==0` 时减速率取 `carrot.autoNaviSpeedDecelRate`（默认 0.8 m/s²）→ **DM 软降级的 fail-safe 减速下限被用户可调参数决定**，最坏 0.8 m/s² |
| `longitudinal_planner.py:256` | `accel_limits_turns[0] = accel_limits_turns[0] = 0.0 ## carrot` —— 自赋值笔误，几乎肯定是 `[0]=[1]=0` 或 `accel_limits_turns[1]` 的复制粘贴漏改 |
| `radard.py:489-548` | "天桥/龙门架"过滤：`abs(vrel)<1.0 & abs(yrel)<1.5 & 10<drel<80 & stable_count>=5` 判为龙门架剔除 lead。城市缓行接近停止队列/事故断头车会命中 → **需实车确认**，这是把轿车高架工况直接搬过来的典型例子 |
| `radard.py:691-694` | `leadTwo.dRel` 人为 -8 m 以"让 MPC 更早减速" → 几何量被扭曲，纵向出现"莫名刹车"；应改代价权重而非改几何 |
| `cruise.py:353-354` | `initialize_v_cruise()` 首行 `return`，下面整段死代码 → engage 时巡航初值策略缺失 |

---

## 6. 新功能专项审查：高德协同领航（`cp-custo-amap` 五个提交）

### 6.1 这五个提交做了什么（`dcd0264 → 70ba3d8`）

改动面很小（`amap_navi.py` +162 行、`desire_helper.py` +52 行、`custom.capnp` +2 字段、`process_config.py` 1 行、`substitute.toml` 1 行），但引入了**跨进程实时控制闭环**：车机高德 → UDP 7705 指令 → `SharedData` → `carrotMan`/`amapNavi` capnp → `DesireHelper` 变道状态机 → `lateralPlan`。

结构上是清楚的（生产者/消费者分离、`overtakeMode` 三级门禁、执行期复检、CANCEL 消费），但存在下列**必须在装车前解决**的问题。

### 6.2 【P0】TTC 门禁语义反转：后方无车 → 永久禁止变道

生产者侧（`amap_navi.py`，`public_amap_navi()` 内）：

```python
# 两侧后向雷达都参与，取最小 TTC（最保守）；无有效目标 -> 0.0 哨兵，
# 消费端一律阻断（M-12：失效态不得解释为"安全"）
ttc_list = []
for side in ("lb", "rb"):
    d = getattr(self.shared_data, f"main_{side}_drel", None)
    v = getattr(self.shared_data, f"{side}_vrel", None)
    if d is not None and abs(d) > 0 and v is not None and v < -0.1:
        ttc_list.append((abs(d) / 1000.0) / abs(v))
ttc = min(ttc_list) if ttc_list else 0.0
msg.amapNavi.lidarBehindVdistTime = float(ttc)
```

消费者侧（`desire_helper.py:955-970`）：

```python
amap_alive = self.sm.alive['amapNavi']
behind_ttc = amapNavi.lidarBehindVdistTime if amap_alive else 0.0
ttc_threshold = {0: 1.8, 1: 2.5, 2: 3.5}.get(overtake_mode, 2.5)
rear_conflict = (behind_ttc <= 0.0) or (behind_ttc < ttc_threshold)
if rear_conflict:
    auto_lane_change_trigger = False
    auto_lane_change_trigger_no_bsd = False
    if (self.frame % int(2.0 / DT_MDL)) == 0:
        self.lane_change_audio(True, 6, 0)      # 播报"后方来车"
```

**逻辑推导**（可直接在代码里读出来）：

| 后方实际情况 | `main_lb/rb_drel`、`*_vrel` | `ttc` | `rear_conflict` | 结果 |
|---|---|---|---|---|
| **空无一车**（最常见） | `None` | `0.0` | **True** | 阻断变道 + 每 2 s 播"后方来车" |
| 后车同速跟随（`v_rel≈0`） | 有值但 `v !< -0.1` | `0.0` | **True** | 阻断 |
| 后车远离（正解，最该放行） | `v>0` | `0.0` | **True** | 阻断 |
| 后车逼近、TTC 8 s（安全） | 有值、`v<-0.1` | `8.0` | False | 放行 |
| 未接 BSD/车机（默认状态） | 全无 | `0.0` | **True** | 阻断 |

即**作者把"无数据"和"危险"编码成了同一个值 `0.0`，而"安全"反而需要一个非零 TTC**。这在数学上把门禁的补集搞反了：真正该 fail-closed 的是"数据不可用"，而"确认无威胁"与"确实有威胁"都必须是可区分的第三态。

后果不止自动变道：`desire_helper.py:1247-1259` 的执行期复检同样用 `(_ttc <= 0.0) or (_ttc < _thr)`，而**驾驶员打灯变道**走的是 `:1147` 的 `driver_desire_enabled` 分支（不受 `auto_lane_change_trigger` 门控）→ 进入 `laneChangeStarting` 后**下一帧即被打回 off**，并再次播报语音。也就是说：

> **在未连接车机/BSD 的默认状态下，本分支把 openpilot 的整个自主/手动变道能力全部关闭，且每 2 秒播放一次"后方来车"提示。**

这是一个"看起来更保守、实则不可用"的实现，用户会以关闭功能或物理拔线收场——比原来的风险更大。

**修复方案（建议的实现形式）**：把状态显式三值化，而不是用 0.0 复用两种含义。

```python
# 生产端：capnp 已有 lbDrelValid/rbDrelValid，加一字段
ttcStatus: uint8   # 0=UNKNOWN/陈旧, 1=NO_THREAT(无逼近目标), 2=THREAT(ttc 有效)
ttc: float32

# 消费端
if ttcStatus == UNKNOWN and not盲区数据可用:  → 回退到"仅用摄像头/原厂 BSD"的判定（或降级为禁止自动变道但允许驾驶员变道）
if ttcStatus == NO_THREAT: → 放行
if ttcStatus == THREAT and ttc < thr: → 阻断
```
并且语音提示必须**只在驾驶员/系统真正发起了变道请求时**播报，不能挂在无条件每 2 s 的通用门禁上。

### 6.3 【P0】门禁的可信度地基是坏的：`amapNavi.alive` 恒真

```python
# cereal/services.py:84-85
"carrotMan": (True, 0.),
"amapNavi":  (True, 0.),
# cereal/messaging/__init__.py:153-157
on_demand = {s: SERVICE_LIST[s].frequency <= 1e-5 for s in services}
self.static_freq_services = set(s for s in services if not on_demand[s])
self.alive = {s: on_demand[s] for s in services}          # → True 且永不更新（:220 只遍历 static）
```

* `alive['amapNavi']` **恒为 True** → `desire_helper.py:955/1251` 的"消息缺失"分支形同虚设（发布进程死了也走 `if amap_alive` 那条，用**冻结的最后一帧**）。若最后一帧是"无来车大值"→ 门禁持续放行；若是启动初值 0 → 永久阻断 + 永久语音。这两种表现都随机取决于 carrot_man 死掉时的那一刻。
* 与文档承诺直接冲突：`docs/custin/COOPERATIVE_PILOT.md:99` 写"Wi-Fi 断开 >1.0 s 自动回退标准 ACC"，而协议层没有任何老化机制。
* `carrotMan` 同理：`controlsd.py:282` `desired_kph = min(CS.vCruiseCluster, self.sm['carrotMan'].desiredSpeed)` **没有 alive/时效检查**，carrot_man 死后 `desiredSpeed` 用陈旧值或 capnp 默认 0 → **巡航目标被钳到 0**（`carrot_functions.py:307-314` 同型）。这是"缺数据当 0 参与数学"的教科书案例。

**修复**：① `services.py` 填真实频率（`amapNavi` 20 Hz、`carrotMan` 10 Hz）；② 所有消费者按 `recv_frame`/`logMonoTime` 加 max-age（≤0.5 s）；③ 对 `desiredSpeed` 做 `>0` 有效性判断。

### 6.4 【P1】指令通道：CANCEL 依赖 index，且缺"同一 index 多命令"保护

```python
# amap_navi.py:_update_command
if self.shared_data.app_ip is not None and ip != self.shared_data.app_ip:
    return                                   # 仅此处做了来源绑定
...
idx = json_obj.get("index") or json_obj.get("seq")
...
if idx is not None and (idx > self.shared_data.cmd_index or self.shared_data.cmd_index == -1):
    self.shared_data.cmd_index = idx
    if "cmd" in json_obj: self.shared_data.remote_cmd = "CANCEL" if c == "CANCEL_LANE_CHANGE" else c
```
```python
# desire_helper.py:526
elif carrotMan.carrotCmdIndex != self.carrot_cmd_index_last and carrotMan.carrotCmd == "CANCEL":
```

* **若车机发的 CANCEL 不带 `index`/`seq`，整条命令被丢弃**（`idx is None` → 不进入赋值块）。README 宣称"CANCEL 50 ms 内立即中止变道"，但代码要求一个由对端维护的单调序号——协议契约完全建立在"车机一定会正确编号"上，且**丢包后（UDP）该次变道永远无法取消**，只能靠驾驶员打盘（`:1350` 已改成任意方向 `steeringPressed` 即退出，这条是好的）。
* 来源绑定只在 `_update_command` 里；`_update_blinker`（`:986-1007`，直接写 `shared_data.ext_blinker`）、`_update_control`（`blinker_ctrl`）、`_update_sensors`（盲区/距离/速度）**均无来源校验**。同网段设备可伪造"无盲区 + 安全 TTC"，即**绕过 §6.2 的门禁**。`app_ip` 本身又来自 4210 探针的首个响应（`:587-641`），可被抢先。
* 端口编排存在结构性冲突（虽然 `606b16c` 修了"cross-binding"）：本机同时 `bind 7705`（amap 收指令，`amap_navi.py:648`）和 `sendto :7705`（carrot_man 广播，`carrot_man.py:433`）；同时 `bind 7706`（carrot_man 收手机，`:626`）和 `sendto :7706`（amap 发遥测，`amap_navi.py:1632`）。广播地址自环会把自家报文喂进自家解析器（`_process_single_packet` 每包 `json.loads`），端口语义（谁是发、谁是收）在两个文件里**互为相反**，无任何集中契约或断言。

### 6.5 【P1】把 7 线程 UDP 服务塞进 carrot_man，且共享数据无锁

`process_config.py:144` 关掉独立 `amap_navi` 进程后，`AmapNaviServ`（含 `_data_deal_thread`(20 Hz)、`_udp_recv_thread`、`_lane_recv_thread`、`_headunit_cmd_recv_thread`、`_discovery_responder_thread`、`_clean_clients_thread`、`navi_broadcast_info`(10 Hz)、以及每客户端一个 `_client_worker` 线程）全部运行在 **carrot_man 进程**内。

* `self.lock` 只保护 `clients` 字典（`amap_navi.py:1011,1592` 等），**`SharedData` 的 60+ 个业务字段全部无锁**：`_data_deal_thread` 写 `main_lb_drel/lf_vrel/overtake_mode/behind_ttc…`，`carrot_man` 的 broadcast 线程在 `:316-347` 逐字段拷贝，`_udp_recv/_process_single_packet` 在另一线程写同一批字段。典型后果：`is_side_object_risky()` 拿到的 `drel` 与 `vrel` 来自**不同时刻的不同目标**——这正是变道安全判定最怕的撕裂读。
* `_client_worker` 动态建线程 + 无 `maxlen` 队列（`:891-931`）：热点里大量异动 IP 可稳定堆积线程（2 GB RAM 设备上）。
* 每线程/每帧的 `Params().get_bool("IsOnroad")`（`:1695,1949,1991`）、每帧 `json.dumps` 大对象（`make_navi_message` 实测 68 个 key，README 称 81 项；另有 `make_lidar/blinker_message` 三份近似重复）都是可避免的周期开销与 GC 压力。
* **正确做法**：`amap_navi` 恢复为独立进程，所有跨线程交换走 **capnp `amapNavi` 消息**（已有 `public_amap_navi()`），carrot_man 只作消费者；`SharedData` 直接删成快照 dataclass，由唯一一个线程构造并整体替换（写时复制），杜绝细粒度锁。

### 6.6 【P2】与车型相关的缺失

* **库斯途的 MPV 特性没有体现在门禁里**：`ttc_threshold` 只有 `1.8/2.5/3.5 s` 三档，**不随自车速度、目标速度差、天气/路面（后扭力梁 + 高重心更易横摆）变化**。变道安全间隙应表达为 `gap ≥ v_self·t + Δv 相关项`，而非纯 TTC 常数。
* `overtake_mode` 由车机任意下发且默认 1（`desire_helper.py:951-956` 只校验取值 ∈{0,1,2}），**没有与车速/挡位/ engaged 状态联锁**（`carrotMan.carrotCmd` 的 SPEED 分支同样无 engaged 检查，见 `cruise.py:443-476`）。
* `msg.amapNavi` 的 `lfDrel/lbDrel/…` 用 `int(round(drel/100))`（0.1 m 分辨率）但 `ttc` 用原始 mm 计算，两套精度并存，回放对账困难。

### 6.7 【正面】值得肯定的几处

* `606b16c`/`ca6cb4a` 的自检是**真审计**（发现并修了端口交叉绑定、探针自 IP 回显、`leftBehindTarget` 拼写不一致、执行期复检窗口从 `ll_prob>0.3` 的 350 ms 扩到整个 Starting 阶段），这比多数 fork 强；
* `ca6cb4a` 把 `min(-1, x-1)` 改成 `max(-1, x-1)`（`desire_helper.py:1364`）修掉了 `atc_cancel_delay` 不可达；
* `:1350-1352` 把"反向打盘才退出"改成"任意盘 interven 即退出"，方向上是更保守的；
* `overtake_mode` 白名单校验、`cmd_index` 单调 + 10 s 复位，是有意识的重放防护。

问题在于**基础数据类型设计**（§6.2 的 0.0 复用）和**消息老化**（§6.3）——这两条不修，其余细节改进的收益都是负的。

---

## 7. 可靠性：并发、竞态与静默失效

### 7.1 已确证的逻辑死块 / 复制粘贴缺陷

| 位置 | 事实 | 后果 |
|---|---|---|
| `carrot_serv.py:773-776` | `compute_delta_v_for_front_rear()` 里 **前目标也调用了 `compute_delta_v_for_rear()`**，而 `:728` 明确存在从未被使用的 `compute_delta_v_for_front()` | 相邻车道"前方目标"按"后方跟逼车"的符号语义计算（`v_rel` 含义相反）→ 该加速时减速、该让行时抢行。调用点：`:1028`（左侧）、`:1049`（右侧）。这是**当前分支最明确的算法级 bug** |
| `carrot_serv.py:784,793` | `if f_drel_mm < b_drel_mm * 0.3:` —— 后车 `drel` 为负（`b*0.3<0`），前车 `drel` 为正 → 条件**恒真**；注释写的是"前车距离只有后车的 1/3" | 决策分支恒定走"选择加速"，与安全意图相反。应使用 `abs()` |
| `carrot_serv.py:887/890 vs 935` | 递减用 `min(0, cnt-1)`（可为负）、递增用 `max(0, cnt+1)`（**恒为 0**），而消费处判 `if cnt == 2` | `cnt == 2` 分支**永久不可达**（约 350 行的 `update_auto_turn` 中一段逻辑从未运行） |
| `carrot_serv.py:450-509 vs 35-89` | 同一个转向类型映射被写了 **两份**（模块级 `nav_type_mapping` 与函数内 `turn_type_mapping`），内容已漂移（如 `201/arrive` 一份写 5、一份写 8；`14 uturn` 5 vs 7），且函数内那份**每帧重建** | 同一 maneuver 在不同代码路径映射出不同结果；顺带的 CPU/GC 浪费 |
| `amap_navi.py:25-93` vs `lidar_speed_test.py:7-75` | `RadarSpeedEstimator` **两份完全相同实现** | 改一忘一 |
| `amap_navi.py:722-741`、`:1581-1688` vs `carrot_man.py:394-463`、`make_navi/lidar/blinker_message`（`:1690-2062`） | 三处 150 行级别的复制粘贴（左右侧、两个广播线程、三类消息构造） | 维护成本高、易只改一半 |
| `desire_helper.py:500-506` | 关键判据被注释掉又用另一种写法恢复（`#if carrotMan.carrotCmdIndex != …`）；`carrot_serv.py:661/706` 用 `time.monotonic()` 与 wall-clock 混用后判 `dt == 0`（浮点相等） | 恒假分支 + 时间基准不统一，是本仓库的通用病灶 |
| `cereal/custom.capnp:58-76` | `AmapNavi` 17 个字段用 `Int32` 承载位标志（`leftBlind` 编码 6 个 bool）与 `0` 哨兵 | 见 §6.2/6.3：位标志可用，但**"无效值"必须用显式 Valid 字段或 enum**，而不是复用一个数值 |

### 7.2 状态量用字符串表达，且用子串判定方向

`carrot_serv.py:883-959` 一带：`atc_type` 依次被追加 `" prepare"`、变成 `"atc left"`、再比较 `atc_type in ["fork left", "atc left"]`，并用 `"left" in atc_type` 判方向。字符串既当状态、又当类型、又当方向，配合 `desire_helper.py` 里同样的字符串契约（`carrotCmd == "CANCEL"` / `"LANECHANGE"` / `"OVERTAKE"`），一次改文案就会静默断开跨进程协议。→ 应为 `enum`（capnp 里定义）。

### 7.3 异常吞掉 = 功能静默消失（本仓库最普遍的可靠性问题）

* 全仓（`selfdrive/` + `system/` + `opendbc/car/`）**199 处** `except Exception` / `except:`；`carrot/` 目录内 **51+** 处，其中 `carrot_man.py:381` 写成 `except (OSError, Exception)`（等价于裸 except，且掩盖了 OSError 的分类处理意图）。
* 危险样例（都会导致"看起来正常、实际能力丢失"）：
  * `carrot_man.py:453-462`（broadcast 主体 `while True: try/except Exception`，仅 `(showDebugLog & X)` 时才打印）；
  * `carrot_serv.py:368-379` 红绿灯 JSON 解析 → `float()` 抛错即 `pass` → **红绿灯状态永远 0**，规划端永不进入停车分支；
  * `carrot_serv.py:314` `int(self.params.get(...))` → `TypeError` 被上层吞 → 整条导航限速链停摆（§2.4）；
  * `amap_navi.py:593-596, 648-651`：socket `bind` 失败只 `print` 后 **`return`（线程直接退出）** → 协同领航整条链路静默死亡，且 `ProcessManager` 视 carrot_man 存活；
  * `amap_navi.py:655-657`：`_headunit_cmd_recv_thread` 的 `except Exception: time.sleep(0.05)` 无限重试（错误永久性时变成 20 Hz 空转）。
* 与之配套的是 **`cloudlog` 在 carrot 目录出现 0 次**、`loggerd` 停用（§5.6）→ 这些静默失效**不留任何可回放证据**。

### 7.4 参数读取的空值语义（`get()` vs `get_int()`）

`UnifiedParams.get()`（`carrot/config.py:328-330`）直通 `Params.get()`，**未命中返回 `None`**；代码里既有 `get_int()`（返回 0），也有 `int(self.params.get(...))`（抛 `TypeError`），还有 `self.params.get("Version").decode()`（`None.decode()` → `AttributeError`）。更糟的是 `config.py:42-61 _match_system_param` 在同步系统参数与 `nav_params.json` 时把"系统未写入"归一成 `sys_val = 0`，因为 `0 is not None` 成立 → **默认值被 0 永久覆盖并回写**。

安全敏感的"0 有危险语义"参数清单（必须加下限钳制）：
`TFollowGap1..4`（=0 → 时距 0 秒）、`ComfortBrake`（=0 → `carrot_functions.py:519` 除零 → **plannerd 崩溃 = 纵向控制消失**）、`autoNaviSpeedDecelRate`（=0 → `carrot_man.py:538` 除零）、`MyDrivingMode`（=0 → `DrivingMode(0)` ValueError → plannerd 崩溃）、`desiredSpeed`（=0 → §6.3）。

### 7.5 单位混用

`drel` 一路以 **mm** 传递（`carrot_serv.py:729/753` 显式 `*0.001`），但 `amap_navi.py:1159-1160` 的兜底值是 `0.1 / 0.`（米级数值），`:1161` 又用 `<= 1000`（mm）比较；`capnp` 里 `lfDrel = round(drel/100)`（0.1 m）而 TTC 用 mm 计算。**同一物理量三种量纲**。建议：全部改名带单位后缀（`drel_mm`、`vrel_mps`），并让 `is_side_object_risky()` 只接受带后缀入参（见 §12）。

### 7.6 定时与线程收尾

* 关键循环用 `time.sleep()` 而非 `Ratekeeper`：`carrot_man.py:662/738/750/754/823/906/1076`、`amap_navi.py:657`。`carrot_man.py:872` 的 `isOnroadCount == 500` 用 `==`（错过即不再触发，直到 offroad 复位）。
* `carrot_man.main` 里 `carrot_man_thread()` 内部是 `while True` 且永不返回；`except KeyboardInterrupt` 之后 `while True:` 从函数体重启 → **进程无法优雅退出**（靠 manager SIGKILL）。7+ 个线程全 `daemon=True` 且无名、无 join → 崩溃时无法定位线程归属。
* `lane.py:295-358 ensure_package()` 在设备上 `pip install flask / opencv-python`，导入期断网进入 30 s 死循环；`lane.py:475` 用 `run_simple('0.0.0.0', 8888, threaded=True)`（werkzeug 开发服务器、无鉴权、无界线程）。`lane` 仍在 `process_config.py:146` 以 `only_onroad` 启用。

---

## 8. 性能与资源占用（Comma 3 / 2 GB）

### 8.1 内存与进程数

| 项 | 事实 | 评价 |
|---|---|---|
| 常驻进程 | `process_config.py` 共 56 条注册项，onroad 实际约 27 个 Python + 7+ native；`carrot_man` 为 `always_run`（停车也在跑 web/flask、FTP、8 线程 UDP） | 2 GB 设备偏紧。**把 Web/FTP/UDP 服务与实时控制同进程**是双输：既占控制进程 CPU，又让服务故障拖垮控制 |
| `lowMemory` 告警 | `selfdrived.py:435 pass#sensorDataInvalid` 一类被静音；`managerState` 事件也被静音（`:378`） | OOM killer 杀进程时**不再有软退出**（§5.6），属最危险的组合 |
| 线程栈 | `amap_navi` 每客户端 1 线程（`:891-900`），无上限、无队列 `maxlen` | 潜在线程堆积 |

### 8.2 100 Hz / 20 Hz 热路径上的不必要工作

| 位置 | 问题 | 建议 |
|---|---|---|
| `controlsd.py:174-179` | 每帧 `params.get_int("UseLaneLineCurveSpeed")`、`get_float("SteerActuatorDelay")`（含 `abs(sm['carrotMan'].vTurnSpeed)`）在 100 Hz 控制环内 | 集中到已有的 `%100` 参数刷新回调 |
| `controlsd.py:274-277` | 碰撞判定里 `params.put_bool()` **同步落盘**在 100 Hz 线程内 | `put_bool_nonblocking`；且先做 3 帧确认 |
| `desire_helper.py:377-412` | 每 100 帧读 **24 个 Params**（顺序调用、无缓存）；`amap_navi.py` 每帧 `get_bool("IsOnroad")` ×3 | Params 已有 mtime 缓存机制，应统一走一份快照 |
| `carrot_man.py:489-559` | 10 Hz 内做 `get_path_after_distance` + shapely `LineString.interpolate`（10 m 步进逐点插值）+ 纯 Python DP，路线几千点时 O(n) 全扫 | 降频到 2–5 Hz + 增量重算；或预计算累计弧长 |
| `carrot_man.py:572`、`amap_navi.py:1690-2062` | 每帧 `json.dumps` 大 payload（68 个 key 的遥测 / 全参数表），且 `make_navi/lidar/blinker_message` 三份重复 | 复用同一个 dict + ujson/orjson；分频降载（遥测 10 Hz 足够） |
| `carrot_serv.py:450-509` | 每调用重建 55 项映射字典 | 提到模块级常量 |
| `radar_interface.py:127-155` | 两个 CANParser 都喂同一 `can_strings`，更新条件缠绕 | 单次解析、一次更新 |
| `carcontroller.py:158-217` | 对 **torque 控制车型（含库斯途）**仍然每帧计算 `apply_std_steer_angle_limits`、`angle_limit_counter`、`lkas_max_torque` 等角度控制专用量 | 用 `if self.angle_control:` 收敛，省 CPU 且避免误改 |
| `hyundai/interface.py:253` vs `opendbc/interfaces.py:383` | `LongitudinalPersonalityMax` 一处设 "4"、一处设 3；`init()` 每次开机 `Params().put(...)`，`interface.py:135-149` 一堆 `print("$$$")` | 统一初始化来源，去掉启动期写盘 |
| `manager.py:429-435` | 每次 manager 启动 `os.system("python ../../opendbc/car/hyundai/values.py > SupportedCars")` ×7 | 由构建期生成，运行时不 fork 解释器；且 `tools/` 已有生成脚本 |
| `cereal` 载荷 | `CarrotMan` 38 字段（含 5 段 `Text`，其中 `naviPaths` 是整条导航 polyline）以 ~17 Hz 发布；`carState` 新增 16 字段 100 Hz 广播（含 `logCarrot: Text`） | 长文本走低频独立 topic；控制字段用 packed 数值 |

### 8.3 冷启动与并发
`config.py:333` 在 **模块 import 期**构造 `UnifiedParams()` 单例，而 `carrot_man` 构造期即拉起 7–8 线程，与 `manager` 的 `set_default_params()` 存在竞态窗口（→ §7.4 的 0 值覆盖正好在这个窗口触发）。建议：所有参数读取推迟到 `main()` 内、线程在 `started` 之后再 spawn。

---

## 9. 配置与参数系统问题

1. **标定层被放错位置**：真正的车辆标定应来自 `CarSpecs` / `torque_data` / `lateralTuning`（由 `get_params()` 一次性写入 `CP`）。本分支的实际生效源是**设备上的通用 UI 参数**：
   * `LateralTorqueCustom=1` 默认开 → `latcontrol_torque.py:134-137` 直接 `return`，**torqued -learning 被永久禁用**，并每 10 帧用 `LateralTorqueAccelFactor=3000(→3.0)`、`Friction=100(→0.1)` 覆写 `torque_params`（`:144-162`）。库斯途 override/substitute 里写什么都没用。
   * `CustomSteerMax`、`SteerActuatorDelay`、`CruiseButtonTest1..3`、`SpeedFromPCM=2` 等"玩家后门"被当作新车的出厂标定来源。
   → **正确做法**：在 `interface.py` 里给 `candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN` 加覆盖块（同文件 `:241` 已有先例），把 `LateralTorqueCustom` 默认改 0。
2. **默认值清单里混入"危险 1"**：`manager.py:110-190` —— `EnableRadarTracks=1`（§3.5）、`DisableDM=1`（§5.7）、`LateralTorqueCustom=1`、`RecordAudio=1`、`NNFF=0`（与文档矛盾，§11）。移植新车应遵循"新特性默认关、故障可回退"的原则。
3. **三源参数不一致**：`carrot_settings.json`（UI 声明 default/min/max）、`manager.py` 种入值、代码里 `__init__` 硬编码。例：`MyDrivingMode` JSON=3 / `manager.py:108`="1"；`AutoCurveSpeedFactorH` 三处不同（`config.py`、`carrot_man.py:216-217/1047-1050`）。且**没有迁移机制**：删功能不删键（如 `TrafficStopDistanceAdjust` 只在 `params_keys.h:225` 与注释里，是死键）。
4. **`SoftRestartTriggered==2` 全量覆写**（`manager.py:250-262`）：一次"软重启"动作会把用户所有自定义参数重置（含转向/制动标定）。应只补写 `params.get(k) is None` 的键。
5. **持久化原子性**：`config.py:111-118` 保存 `nav_params.json` 无 tmp+`os.replace`+fsync → 行车中掉电即截断，下次启动静默回落默认（`:101-105` 仅 print）。用户标定丢失。

---

## 10. 工程实践、构建与供应链

### 10.1 依赖与可复现性

| 问题 | 证据 | 影响 |
|---|---|---|
| 无 `.gitmodules`，全部 vendored | `git ls-files` 中 mode 160000 条目为 0；上游关系只剩 `git_src_commit` 一行 | 无法 `submodule update`、无法 diff 上游安全修复、无法证明 `opendbc/safety` 改了什么。**对安全回归审计是灾难** |
| 提交内含 `.so` / `.bin` 产物，`prebuilt` 是 0 字节标记 | `launch_chffrplus.sh:116` 据此跳过 `build.py`；`git ls-files \| grep '\.so$'` 命中 params_pyx/msgq/acados/commonmodel 等；`panda/board/obj/*.bin` 亦入库 | 设备跑的是**仓库里的二进制**，与源码一致性无法自证（历史上 `9e414bdc` 还专门修过 scp 部署引入的 CRLF，说明分发链路是手工的） |
| 运行时改源码 | `launch_chffrplus.sh:109-112` 按语言 **复制覆盖 `events.py`**（ko/en 互换），且判定条件用的还是旧路径 `controls/lib/events.py`（新架构里该路径不存在 → 判断恒不成立） | 运行时篡改源码、行号与 Sentry/traceback 失真、且该逻辑**已经失效**却仍留在启动脚本 |
| 开机执行不在仓库的自删脚本 | `launch_openpilot.sh:2-8`、`INSTALLER_GUIDE.md` | 不可审计；配合 `restart.sh` 的 `git pull` 构成"远端可换代码" |
| 设备侧 pip 安装 | `lane.py:316/344`（flask、opencv-python） | 断网即启动卡死 |
| CI 未落地 | `.github/workflows/` 保留上游模板，但 §2 的启动级错误（重复 torque 定义）能提交到 HEAD，说明 fork 未跑最小的 car/torque 单测 | 见 §12 P0 |

### 10.2 Python 风格与静态检查
`pyproject.toml` 里 ruff 配置仍是上游的严格集合，但 `selfdrive/carrot/*` 与新增逻辑基本不通：无类型注解（约 6800 行仅 `amap_navi.py:1042-1073` 一处用了 `int | None`）、`import` 写在函数体中部（`carrot_man.py:1079`、`hyundaican.py:376` 的 `from opendbc.car.hyundai.carcontroller import HyundaiJerk` —— **carcontroller 反向 import carstate 的调用者，存在循环依赖风险**）、拼写错误进入标识符（`V_CRUVE_LOOKUP_VALS`、`laneChangig`、`moduel`）。

### 10.3 隐私与法务
`RecordAudio=1`、`DisableDM=1`、自动 FTP 上传日志与全量参数、明文凭据入库、README 只有韩文免责声明而**未披露上述默认行为**——若本仓库公开分发给国内用户，这几条都需要在 README 首屏中文说明并默认关闭。

---

## 11. 文档与代码一致性核对表

| 文档/README 宣称 | 出处 | 代码事实 | 判定 |
|---|---|---|---|
| "帕里斯帝 NNFF 神经网络力矩模型 + 150 ms 前馈偏航补偿" | `README.md`（核心特性 5-1）、`docs/custin/VEHICLE_DYNAMICS.md` 二-1 | `lat_models/` 无 CUSTIN 键，`get_nn_model_path()` 相似度门槛 0.9（实际 ≈0.53）→ None；`("NNFF","0")` 为默认；`substitute.toml` 只影响 analytic 参数；全仓无 150 ms 前馈实现 | ❌ **未实现** |
| "5.0 s 平缓变道 S 曲线，横向 ≤0.08 g，jerk ≤0.05 g/s（防晕车）" | `README.md`、`VEHICLE_DYNAMICS.md` 二-2 | `desire_helper.py:18` 仅 `LANE_CHANGE_TIME_MAX=10.`；淡入淡出 `.5 s/1 s`；`drive_helpers` 为 0.13 s 平滑 + 3.0 m/s² jerk 上限；无任何 5.0/0.08/0.05 常量 | ❌ **未实现** |
| "8AT 起步防顿挫，固化 `startAccel=1.0`" | `VEHICLE_DYNAMICS.md` 二-3 | `interface.py:203` 存在，但对**所有现代车型通用**，且非抛物线生成 | ⚠️ **部分成立、非专车** |
| "三级超车风格（激进/常规/保守）+ 激光雷达 TTC 刚性门禁 + 执行期持续复检" | `README.md`、`COOPERATIVE_PILOT.md` | `desire_helper.py:955-970/1247-1259` 存在；但**语义反转（§6.2）+ `alive` 恒真（§6.3）** | ⚠️ **实现了但不可用/不可信** |
| "车机下发 `CANCEL` 50 ms 内立即中止变道" | `README.md`、`COOPERATIVE_PILOT.md` | 依赖 `index` 存在且单调（§6.4）；UDP 丢包即永久无法取消 | ⚠️ **条件成立** |
| "Wi-Fi 断开 >1.0 s 自动回退标准 ACC" | `COOPERATIVE_PILOT.md:99` | `services.py` 频率 0 → `alive` 恒真，无任何老化机制 | ❌ **未实现** |
| "20 Hz `0x485 LFAHDA_MFC` 点亮原厂仪表绿色车道线/方向盘" | `VEHICLE_DYNAMICS.md` 二-5 | `carcontroller.py:353-355`（100/5=20 Hz）、`hyundaican.py:119-131`、`safety_hyundai.h:32` | ✅ **成立** |
| "offroad 强制关断 4 个 A75 大核 + 释放 GPU 供电轨，待机 1.65 W / 39 ℃" | `VEHICLE_DYNAMICS.md` 二-6 | `hardware.py` 无对应改动（属上游 Comma 3 电源管理） | ❌ **非本分支实现** |
| 硬件内存描述 | `README.md`/`COOPERATIVE_PILOT.md` 写 4 GB / SDM845；最新提交 `70ba3d8` 只改了 `VEHICLE_DYNAMICS.md` 为 2.0 GB | 文档内部互相矛盾，未同步 | ⚠️ **文档不一致** |
| 「2021~2024 款全部支持」 | `VEHICLE_DYNAMICS.md:3`、`README.md` | `values.py:446` 仅 `"Hyundai Custin 2023"`，且每 ECU 单条固件串（§4.4） | ❌ **超出实测范围** |

**代码有但文档完全没写**（这些恰恰是风险最高的）：panda `tx=false`（§5.1）、auto-engage（§5.2）、AEB 检查关闭（§5.3）、`safety_mismatch=False`（§5.4）、D 挡横向（§5.5）、`loggerd` 停用（§5.6）、`DisableDM=1`（§5.7）、`echo_cmd` RCE（§5.8）、向雷达 ECU 写配置（§5.9）、`DynamicExperimental` 自动切实验模式（`longitudinal_planner.py:141-208`）、碰撞单帧判定（`controlsd.py:274`）、radard 龙门架过滤与 leadTwo -8 m。

> 一句实话：**文档把"计划中的调校"写成了"已完成的调校"**，而把"实际改变了安全边界"的改动全部略过。对于一个要装在家庭 MPV 上的系统，这个偏差的方向是错的——应当在 README 首屏放一张"与上游安全行为差异表"。

---

## 12. 优化路线图（P0 → P3）

### P0 · 恢复"能开机 + 硬件/软件安全边界"（装车前必须完成）

```
1  删 torque_data 重复定义（保留 substitute→PALISADE，删 override.toml:77）
   └ 加最小冒烟测试：python -c "from opendbc.car.interfaces import get_torque_params; get_torque_params()" 进 CI
2  恢复 safety_hyundai.h:256 / safety_hyundai_canfd.h:358 的 tx=false；max_steer 回 270→（再按实测设 384）
3  恢复 safety_hyundai_common.h:79-97 的"近期用户按钮"门；删除 safety_hyundai.h:223-228 的 auto-engage 后门
4  恢复 SCC12 的 aeb_decel_cmd/aeb_req 违反判定（safety_hyundai.h:232-241）与 0x4F1 resume 的 controls_allowed 门
5  selfdrived.py:358 删除 `safety_mismatch = False`
6  controlsd.py:139-148 恢复 `selfdriveState.active and ...`（若坚持全时 LKA，单列一个显式、UI 常显、受 DM 联锁的模式）
7  services.py 给 carrotMan/amapNavi 填真实频率；所有消费者加 max-age；`desiredSpeed<=0` 不参与 min()
8  manager.py:172 DisableDM→"0"；process_config.py:85 恢复 loggerd；恢复 7 处 pass# 的事件（至少 camera/commIssue/sensorData/processNotRunning）
9  删除 amap_navi.py:840 与 carrot_man.py:883 的 echo_cmd；web_interface 加鉴权+键白名单；FTP 口令出库并改 HTTPS+per-device token
10 修 §6.2 的 TTC 三值化（ttcStatus），并把语音提示限定在"确有变道请求"时
11 修 `carrot_serv.py:773-776`（前目标误用 `_for_rear`）与 `:784/793` 的 `abs()` 缺失
```

**验收**：`card`+`controlsd`+`plannerd`+`modeld` 冷启动无异常；SIL 场景能跑出"未 engage 不输出扭矩 / panda 配错必报警 / BSD 断开必降级"三条断言；开一段路能拿到 qlog。

### P1 · 让库斯途"参数是这台车的"

```
1  interface.py 增加 candidate == HYUNDAI_CUSTIN_1ST_GEN 覆盖块：
   mass(国产铭牌实测)、steerRatio(本车 learner 重跑)、centerToFront(轴荷标定)、
   startAccel / longitudinalActuatorDelay / steeringAngleDeadzone / tireStiffnessFactor
2  manager.py:151 LateralTorqueCustom 默认→0，恢复 torqued 在线学习；标定值改由 platform 提供而非 UI 参数
3  用日志测出原厂 LKAS 力矩峰值 → 决定 STEER_MAX（409 or 384 or 255）并同步 safety max_steer
4  若实车有电容 HOD：carstate 增加 HOD 信号解析，替代/补充力矩阈值
5  用真实日志确认：ACC 最低激活速度、是否全速域 S&G、停车保持时长 → 落到 minEnableSpeed/vEgoStopping/stopDistance
6  确认 SCC/雷达总线拓扑与 disable_ecu/enable_radar_tracks 应答；失败即禁止进入 openpilot 长控（现在只写 EnableRadarTracksResult 无人消费）
7  补齐 2021–2024 国产多供应商 FW 指纹（每 ECU ≥2 条），并为 CUSTIN 加回归指纹用例
8  变道间隙/TTC 阈值改为由车长 4.95 m / 轴距 3.055 m 几何推导（§3.6）
```

### P2 · 可靠性工程

```
1  amap_navi 恢复为独立进程；SharedData → 不可变快照（写时复制）或统一走 amapNavi capnp
2  消灭"吞异常"：给 carrot 侧所有 except Exception 加计数 + 一条 `carrotHealth` capnp 消息（断连/解析失败/线程退出可见）
3  参数层：UnifiedParams 全部 get_int/get_bool/get_float + 显式默认；_match_system_param 的 None/0 混淆修掉；nav_params.json 改 tmp+os.replace
4  端口/协议契约集中到一份 `contracts.py`（枚举 + 断言），UDP 入口统一 schema 校验 + 共享 token
5  删除死块与重复：==2 不可达分支、两份 RadarSpeedEstimator、两份转向映射、三份 make_*_message、`initialize_v_cruise` 死代码
6  量纲统一：drel_mm / vrel_mps 命名 + 边界处转换（`atc_type` 字符串状态机 → enum）
7  Ratekeeper 取代 sleep；线程 name/join；socket 超时统一 socket.timeout
8  静态检查把 selfdrive/carrot/** 纳入 ruff+mypy 白名单并逐步消除
```

### P3 · 性能与结构

```
1  100 Hz/20 Hz 热路径参数读取收敛（§8.2 表）
2  carrot_man 路线/插值计算降频到 2–5 Hz + 增量；广播 JSON 复用对象、遥测 10 Hz
3  carcontroller 扭矩车型跳过角度控制计算
4  fleet_manager/lane/web 三类服务改为 offroad 或按需拉起 + 资源上限（rlimit/cgroup）
5  DesireHelper.update(952 行) 与 CarrotServ.update_auto_turn(324 行) 拆分 + 单元测试（先做纯函数：TTC、间隙、限速仲裁）
6  建立 fork 的"与上游差异清单"文档（现在只有 README 特性宣传）
```

---

## 13. 必须做实车 / 日志验证的清单

以下 12 项**无法靠读码定论**，但每一条都会改变本文的结论，建议用一次 30–60 分钟的日志（`loggerd` 恢复后）+ 台架测量收口：

| # | 待验证项 | 判据 / 采集方式 | 若与假设不符，谁会失效 |
|---|---|---|---|
| 1 | 国产库斯途 **整备质量 / 轴荷** | 铭牌 + 四轮称重 | `CarSpecs.mass`、`centerToFront`、横向能力上界（§3.2） |
| 2 | **steerRatio 实测** | `tools/learner` 重跑本车 | `SteerBoostRatio` 校验、低速画龙/回正（§3.2） |
| 3 | **原厂 LKAS 力矩请求峰值** | cabana 录 MDPS/LKAS 11-bit 域 | `STEER_MAX`、safety `max_steer`（§3.3/§5.1） |
| 4 | **MDPS LFA alive 计时器**（89 帧/2 帧窗口是否适配） | 连续 10 min 转向 + 观察是否报 LKAS 故障 | §4.5、§3.3 |
| 5 | **是否有电容 HOD** 及其报文 | 离手/轻握对比原始 CAN | §3.4 |
| 6 | **ACC 最低激活速度 / 全速域 S&G / 停车保持时长** | 实车操作 + SCC11/12、CLU11 | `minEnableSpeed`、`startingState`、RES spam（§3.5-3/5） |
| 7 | **总线拓扑**（0x420/0x421/0x425 出现在 bus0 还是 bus2；`0x485`、ESP12 YAW_RATE 是否存在） | 双 bus 原始抓取 | §4.7、`carstate.py:230` yaw 来源、`SEND_LFA` |
| 8 | **disable_ecu / enable_radar_tracks 的 UDS 应答**（`6A`?） | UDS 日志 | 原厂 AEB/FCW 是否被下线、SCC11 是否可用（§5.9/§3.5） |
| 9 | **modelLead ↔ SCC11 自回环**现象 | 对比 `radarState` 与 `modelV2.action` | §4.6 |
| 10 | **ESP12 `DriverOverride==2`（刹车）、EMS16 `AclAct`、EMS12 油门域**在 8AT 车型上的取值 | 各踏板工况抓取 | `brakePressed`/`gasPressed` → controls_allowed 退出（§5.2 的替代门） |
| 11 | **后扭力梁满载时的横摆/侧倾表现** | 定速变道 + `latAccel` 峰谷 | 变道时长与 jerk 目标（本文档 §11 中被宣传的 5.0 s/0.08 g） |
| 12 | **BSD 设备缺失时的实际行为** | 拔网线复现 | §6.2/§6.3 的结论会在实车上表现为"永远不能变道 + 持续语音"，需第一时间确认 |

---

## 附录 A：量化指标（本分支现状）

| 指标 | 数值 |
|---|---|
| 主仓 Python（不含 vendored 仓与 tests） | 334 个文件 / 47,528 行 |
| `selfdrive/carrot/` | 8 个文件 / 6,803 行；最大文件 `amap_navi.py` 2115 行、`carrot_serv.py` 1776 行、`carrot_man.py` 1102 行 |
| 超长函数（同类文件） | `desire_helper.update()` **952 行**；`carrot_serv.update_auto_turn()` 324 行；`amap_navi._update_sensors()` 296 行；`carrot_functions.update()` 183 行 |
| 上帝类 | `AmapNaviServ`（37 方法 + 7 线程）、`CarrotServ`（22 方法 / 200+ 属性）、`CarrotMan` |
| 宽异常捕获 | 主仓 3 个目录合计 **199** 处；`carrot/` 内 51+ 处（`amap_navi.py` 28、`carrot_man.py` 28、`web_interface.py` 26） |
| `print()` 调试输出 | `carrot/` **267** 处；`hyundai/interface.py` 40 处；`desire_helper.py` 51 处。`cloudlog` 在 `carrot/` 出现 **0** 次 |
| 进程注册项 | 56（`process_config.py`），其中 `loggerd` 已注释、`amap_navi` 内嵌、`lane` onroad 常驻 |
| 网络入口 | 11 个端口（4210/4211/4212/4213/5510/7705/7706/7709/7710/8021/8088 + 8888/12345），**全部 `0.0.0.0`，无一处鉴权**；端口语义在两文件间互为反向 |
| 被静音的上游安全事件 | `processNotRunning`、`cameraMalfunction`、`commIssue`、`commIssueAvgFreq`、`sensorDataInvalid`、`noGps`、`controlsMismatch`(部分)、`wrongGear`(降级) |
| 文档 | `COMMA3_CUSTIN_MASTER_GUIDE.md` 297 行、`INSTALLER_GUIDE.md` 240 行、`docs/custin/*` 173 行、`README.md` 167 行 |

## 附录 B：证据位置索引（按文件）

**库斯途车型移植**
`opendbc_repo/opendbc/car/hyundai/values.py:14-16,17-30,36-72,89-142,183,445-449,452,458,837-880,971-975`；
`.../hyundai/interface.py:45-59,130-149,160-235,241,250-266,272-299`；
`.../hyundai/carstate.py:123-124,150,176-193,230,235,488-489,517,543-544,559,694-701`；
`.../hyundai/carcontroller.py:19-21,90,158-217,353-355,459-533,486-491`；
`.../hyundai/hyundaican.py:35-45,110-131,196,239,261-274,282,350-354,357-375`；
`.../hyundai/radar_interface.py:44-55,127-155,258-304`；
`.../hyundai/fingerprints.py:354-367`；`.../car/fingerprints.py:16-17`；
`.../car/interfaces.py:14,69-80,169-197,499,528`；`.../car/car_helpers.py:155-208`；
`.../car/torque_data/{override.toml:77, substitute.toml:43, params.toml:32}`；
`opendbc_repo/opendbc/safety/safety/safety_hyundai.h:6-27,29-43,46-59,200-285,310-313`；
`.../safety_hyundai_canfd.h:7,78,102,218,331,357-358`；`.../safety_hyundai_common.h:55-97`；
`opendbc_repo/opendbc/safety/safety.h:135,231-285`；`opendbc_repo/opendbc/dbc/hyundai_kia_generic.dbc:1484,1496`。

**控制与规划**
`selfdrive/controls/controlsd.py:139-148,174-179,274-277,282-293,357`；
`selfdrive/controls/lib/latcontrol_torque.py:87-88,134-162`；
`selfdrive/controls/lib/desire_helper.py:18,255-275,377-412,415-419,500-535,920-975,1130-1180,1215-1275,1350-1366`；
`selfdrive/controls/lib/lateral_planner.py:33-34,159-189`；`selfdrive/controls/lib/lane_planner_2.py:91-113,305-307`；
`selfdrive/controls/lib/longitudinal_planner.py:141-208,231,245-256,272-287,346`；`selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py:322-330,384-391,435-436`；
`selfdrive/controls/lib/longcontrol.py:42-49`；`selfdrive/controls/radard.py:66-79,185-207,339-344,366-372,489-548,573-584,691-694`；
`selfdrive/controls/plannerd.py:26-35`；`selfdrive/modeld/modeld.py:332,363,455-490`；
`selfdrive/selfdrived/selfdrived.py:69,182-185,353-361,378-473`；`selfdrive/selfdrived/events.py:238,778-782`；
`selfdrive/car/cruise.py:188,288,332,353-354,443-476`；`selfdrive/car/card.py:84,103,129`。

**carrot / 协同领航**
`selfdrive/carrot/amap_navi.py:25-93,95-182,187-270,271-309,328-389,436-468,538-596,587-660,644-680,659-812,808-910,933-1073,1130-1230,1278-1283,1363-1489,1551-1690,1690-2062,2101-2115`；
`selfdrive/carrot/carrot_man.py:45,191-215,255-314,316-353,355-463,489-559,572-577,615-665,706,758-810,825-834,841-900,959,1029-1102`；
`selfdrive/carrot/carrot_serv.py:35-89,314,362,368-379,450-509,661-726,728-800,817-1167,1176-1270,1594-1644,1676`；
`selfdrive/carrot/carrot_functions.py:82,88,157-176,187-241,278-281,305-314,400-405,449,519`；
`selfdrive/carrot/config.py:42-61,101-118,111-118,236-333`；
`selfdrive/carrot/web_interface.py:25-45,132-150,277`；`selfdrive/carrot/lane.py:53,224-234,295-358,369-382,415-475`。

**系统 / 构建 / 文档**
`system/manager/manager.py:22-248,250-262`（默认值清单：32,35,64,65,76,108,110,124,151-157,172,189）；
`system/manager/process_config.py:67,77,85,142-146`；`system/hardware/tici/hardware.py`（无 §11 所述改动）；
`launch_openpilot.sh:2-8`、`launch_chffrplus.sh:92-116`、`restart.sh`；
`cereal/services.py:84-85`、`cereal/messaging/__init__.py:138-190,220-226`、`cereal/custom.capnp:58-76`；
`selfdrive/frogpilot/fleetmanager/fleet_manager.py:38-44,105-111,707`；
`opendbc_repo/opendbc/car/__init__.py:306`；`docs/custin/{README,COOPERATIVE_PILOT,VEHICLE_DYNAMICS}.md`、`COMMA3_CUSTIN_MASTER_GUIDE.md`、`INSTALLER_GUIDE.md`、`README.md`。

---

### 免责说明
本报告为**静态代码审查**结论，不构成任何"某项改动车上可用/不可用"的实测判断。文中任何涉及转向、制动、驾驶员监控的条目，其修复都必须先在**台架或封闭路段**验证；现代/起亚车型对 LFA/SCC 报文的行为在不同年款与供应商之间差异很大，§13 的 12 项验证是得出结论的前提。
