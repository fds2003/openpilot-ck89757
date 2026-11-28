# 全量代码深度分析报告（`cp-custo-amap`）

> **分析范围**：`cereal/`、`selfdrive/carrot/`、`selfdrive/modeld/`、`selfdrive/controls/`、`selfdrive/car/`、`opendbc_repo/`、`system/manager/`、`system/hardware/`、`common/`、`selfdrive/ui/`、`launch_*.sh` 及 `docs/custin-cooperative/`（17、19 号文档）。  
> **仓库状态**：当前处于 `prebuilt` 预编译交付态（全库无 `.cc` 源码，`selfdrive/ui/` 仅保留头文件、翻译与预编译 ELF），开发与调优集中在 Python/Cython 层。

---

## 一、 端到端系统架构与真实数据流

```
[外部协同]
  车机 AmapNavi-Reborn ──(UDP 4210/5510/7705/7706)──▶ amap_navi.py (20Hz) ──▶ Pub(amapNavi)
  adbridge 红绿灯      ──(UDP 4215)─────────────────▶ carrot_man.py (10Hz) ──▶ carrot_serv.py ──▶ Pub(carrotMan)
  lane_runner.py (20Hz ONNX) ──(UDP 4213)───────────▶ amap_navi.py

[感知 → 规划 → 控制]
  camerad ─▶ modeld (parse_model_outputs.py + desire_helper.py, 20Hz) ─▶ Pub(modelV2)
                                                                            │
  radard (20Hz, 订阅 modelV2/carState/liveTracks) ──────────────────────────┼─▶ Pub(radarState)
                                                                            ▼
  plannerd (20Hz, 订阅 modelV2/radarState/carrotMan)
    ├─ lateral_planner + lane_planner_2 ─▶ Pub(lateralPlan)
    └─ longitudinal_planner + carrot_functions + long_mpc ─▶ Pub(longitudinalPlan)
                                                                            │
  controlsd (100Hz, poll selfdriveState) ◀──────────────────────────────────┘
    ├─ LoC.update() / LaC.update() ─▶ Pub(carControl)
    └─ card.py (100Hz) ─▶ CarController.update() ─▶ sendcan (LKAS11 100Hz / SCC 50Hz / LFAHDA_MFC 20Hz) ─▶ Panda Safety
```

---

## 二、 核心模块实现盘点

### 1. 高德协同与 Carrot 核心（`selfdrive/carrot/` & `cereal/`）
- **Cap'n Proto 槽位复用**：`cereal/log.capnp:2695-2696` 将 `customReserved0`/`1` 映射为 `carrotMan` (`Custom.CarrotMan`) 与 `amapNavi` (`Custom.AmapNavi`)，定义于 `cereal/custom.capnp:14-76`。
- **双核心守护进程**：
  - `carrot_man.py`（`always_run`，`process_config.py:142`）：聚合 `SubMaster`（11 个 topic）、内嵌 `amap_navi` 与 `WebInterface`（HTTP `127.0.0.1:8088`）、ZMQ REP（`127.0.0.1:7710`）、UDP `7706/7705/12345`、TCP `7709`，以 10 Hz 驱动 `carrot_serv.update_navi()` 发布 `carrotMan`。
  - `amap_navi.py`：全系统唯一 `amapNavi` 发布者，20 Hz 处理线程 + 10 Hz 广播线程，负责车机发现（4210）、雷达/摄像头聚合（4211）、车道线（4212/4213）、红绿灯桥接（4215）及超车控制（7705）。
  - `lane_runner.py`（`only_onroad`，20 Hz）：从 `camerad` 读取 `VISION_STREAM_ROAD`，执行 `lane.onnx` 推理并发送至 `127.0.0.1:4213`。
  - `lane.py`（`only_onroad`）：Flask 视频流服务（`0.0.0.0:8888`）。
- **配置回退机制**：`UnifiedParams`（`config.py`）优先读写 `Params`（受限于 `common/params_keys.h` 静态白名单），未注册键回退至 `selfdrive/carrot/nav_params.json`。

### 2. 感知、规划与控制（`selfdrive/modeld/` & `selfdrive/controls/`）
- **置信度截断**：`parse_model_outputs.py:103, 108` 对 `lane_lines_prob <= 0.2` 与 `lead_prob <= 0.35` 执行置零。
- **变道意图与 TTC 门禁（`desire_helper.py`）**：
  - 触发段（L955-966）与执行段 `laneChangeStarting`（L1252-1270）结合 `amapNavi.overtakeMode`（1.8s / 2.5s / 3.5s）与 `lidarBehindVdistTime` 做后向防撞阻断；
  - `carstate.steeringPressed`（L1363-1373）或 `carrotCmd == "CANCEL"`（L526-535）立即中止变道。
- **纵向调优与红灯锁零**：
  - `long_mpc.py:40, 45, 300, 303-304` 降低急动度权重（`J_EGO_COST=4.3`、`jerk_factor *= 0.78`）并实现 `vRel > -1.0` 时的跟车目标速度钳位（L402-405）。
  - **红灯停稳锁零已修复生效**：`carrot_functions.py:436-437` 及末尾兜底 `L529-531` 在 `e2eStopped` 且 `user_stop_distance < 0` 时强制 `actual_stop_distance = 0.0`、`stop_dist = 0.0`。

### 3. 现代库斯途车辆接口与 CAN 安全（`opendbc_repo/` & `selfdrive/car/`）
- **平台识别与参数**：
  - `CAR.HYUNDAI_CUSTIN_1ST_GEN`（`values.py:445-449`）：`mass=1754`、`wheelbase=3.055`、`steerRatio=17`，标志位 `CHECKSUM_CRC8 | SEND_LFA`，`Ecu.abs` 设为非必需 ECU（L971-975）；4 个固件指纹位于 `fingerprints.py:354-367`。
  - `interface.py:241-243`：覆盖 `steerActuatorDelay = 0.15`、`startAccel = 1.0`。
  - `substitute.toml:43` 将库斯途映射到 `HYUNDAI_PALISADE` 的 3 项力矩基础参数（`params.toml:32`）。
- **CAN 发送与仪表联动**：
  - `carcontroller.py:327-368`：100 Hz 发送 `LKAS11 (0x340)`，50 Hz 发送 `SCC11/12/14`（及 `HyundaiJerk.check_carrot_cruise` 减速/驻车保持逻辑），**20 Hz 发送 `LFAHDA_MFC (0x485)`**（调用链完整，且 `safety_hyundai.h` 已放行 TX 并阻断 Bus 2->0 原车转发）。

### 4. 系统生命周期与基线核对（`system/`、`launch_*.sh`、`docs/`）
- **启动与环境**：`launch_chffrplus.sh` 包含 venv PATH 兜底、时区兜底（`Asia/Shanghai`）、AGNOS GPU/DSP 设备授权、`prebuilt` 跳过编译等逻辑；`manager.py:301-305` 调用 `manager_shm_patch.py` 清理 `/dev/shm` 旧信号量与缓存。
- **硬件电源策略**：`tici/hardware.py:357-446` 初始化时强制开启 GPU 性能模式（`710MHz`、`force_rail_on=1`）；Offroad 下线大核 CPU 4-7 并切换小核为 `ondemand`，Onroad 上线全部 8 核并切为 `performance`。
- **质量审查基线**：[19_C3端代码质量审查.md](file:///E:/code/cp-custo-amap/docs/custin-cooperative/19_C3端代码质量审查.md) 的 `Q-1 ~ Q-9` 主体修复已随近期提交合入代码（文档本身尚未同步更新勾选状态）；[17_未完成工作与剩余事项.md](file:///E:/code/cp-custo-amap/docs/custin-cooperative/17_未完成工作与剩余事项.md) 中的实车标定项与车机端 ADAS 扩展仍待后续推进。

---

## 三、 源码级重点问题与风险清单（按严重程度分级）

### 🔴 P0：安全边界与控制逻辑严重缺陷（建议优先处理）

1. **Panda C 层转向扭矩超限拦截被注释**  
   - 位置：`opendbc_repo/opendbc/safety/safety/safety_hyundai.h:255-257`  
   - 现象：`steer_torque_cmd_checks(...)` 后的 `//tx = false;` 被注释，且 `safety_hyundai.h:204-205` 限值（`512, 10, 10`）远高于 Python 层库斯途配置（`409, 3, 7`）。同时 `safety_hyundai_common.h:84-88` 与 `safety_hyundai.h:224-228` 绕过了原版按键交互时间窗直接允许控制。

2. **二轮车/行人避让横向坐标系符号反转**  
   - 位置：`selfdrive/controls/lib/lateral_planner.py:172`、`selfdrive/controls/lib/lane_planner_2.py:93, 106, 307`  
   - 现象：`radard.py` 的 `yRel` 为**左正右负**，而 `lane_planner_2.py` 按**右正左负**过滤 `-0.3 < d_lat < 1.6` 并执行 `path_xyz[:, 1] -= shift`（左偏）。导致右侧目标漏检，左侧近距离目标反而触发向左迎面偏移。（注：`controlsd.py:175, 189-201` 仅在 `lanefull_mode_enabled` 为 True 时消费 `lateralPlan`）。

3. **adbridge 4215 红绿灯状态在发送前被无条件清零**  
   - 位置：`selfdrive/carrot/carrot_man.py:328-332`、`selfdrive/carrot/carrot_serv.py:369-372, 1425, 1447`  
   - 现象：`carrot_man.py` 刚写入 `carrot_serv.traffic_state`，随后 `carrot_serv.update_navi` 调用 `_update_cmd()`，在 `traffic_light_count < 0`（无视觉 `DETECT` 时）直接将 `self.traffic_state = 0`，导致 bridge 红绿灯无法传给下游。

4. **`LANE_CHANGE_STEP_CUSTO` 实际耗时仅 0.83s（与 5.0s 设计不符）**  
   - 位置：`selfdrive/controls/lib/desire_helper.py:19, 1249`  
   - 现象：`1.2 * DT_MDL`（每帧 0.06）使 `lane_change_ll_prob` 在约 17 帧（0.83 秒）内归零，远快于注释所述的 5.0 秒平缓变道。

5. **TTC 中止（`abort`）状态机可能被同帧后续条件覆盖**  
   - 位置：`selfdrive/controls/lib/desire_helper.py:1265-1272`  
   - 现象：`if abort:` 将状态置 `off` 后，下一行使用独立 `if lane_change_prob < 0.02 and self.lane_change_ll_prob < 0.01:`（非 `elif`），在边界帧会覆盖为 `laneChangeFinishing`。

---

### 🟠 P1：功能失效、并发竞态与安全暴露

6. **盲区变道提速保持计数写反导致功能完全失效**  
   - 位置：`selfdrive/carrot/carrot_serv.py:1050`  
   - 现象：`min(-1, self.bsd_speed_keep_time - 1)` 应为 `max(-1, ...)`，首帧即被钳位到 `-1`。

7. **侧向邻车加减速距离公式条件反转**  
   - 位置：`selfdrive/carrot/carrot_serv.py:687, 693, 707, 714`  
   - 现象：`(min(0, 40.0 - d)/40.0) * 3` 在 `0 < d < 40` 时恒为 `0`。

8. **天桥过滤 `_overpass_tracker` 同帧双倍计数且无老化清理**  
   - 位置：`selfdrive/controls/radard.py:407, 503-547, 594, 646`  
   - 现象：同一帧内 `get_lead` 与 `compute_leads` 各调用一次 `_is_overpass`，计数翻倍且字典只增不删。

9. **`SharedData` 与 `clients` 仍存在跨线程无锁读写撕裂**  
   - 位置：`selfdrive/carrot/amap_navi.py:632-679, 827-971, 1652-1708, 1991-1992, 2047-2048, 2185-2188`、`carrot_man.py:325-368`  
   - 现象：`Q-1` 已保护 `make_navi_message`/`make_blinker_message` 读路径，但写入线程、`make_lidar_message`、`left_blindspot/right_blindspot` 及 `clients` 嵌套字典超时更新仍在锁外操作。

10. **ZMQ REP 非法 JSON 分支未回包导致状态机死锁**  
    - 位置：`selfdrive/carrot/carrot_man.py:908-942`  
    - 现象：`json_obj is None` 分支未调用 `socket.send(...)`，破坏 ZMQ `REP` 交互状态机。

11. **Web / ZMQ / 视频流接口存在安全绕过**  
    - `selfdrive/carrot/web_interface.py:195-196, 255-276`：`POST /nav_params` 绕过 `PARAM_KEY_WHITELIST` 并全量覆盖 `nav_data`。  
    - `selfdrive/carrot/carrot_man.py:913-914`：`carrot_cmd_zmq` 的 HMAC 仅校验 `raw_message[:64]`。  
    - `selfdrive/carrot/lane.py:475`：HTTP 视频流监听 `0.0.0.0:8888` 且无鉴权。

---

### 🟡 P2：配置、模型匹配与工程细节缺陷

12. **库斯途默认无雷达配置 & NNFF 模型无法自动继承**  
    - `values.py:445-449` 未配 `MANDO_RADAR`，默认 `radarUnavailable = True`（`interface.py:179`）。  
    - `interfaces.py:169-197` 的 `get_nn_model_path` 不读取 `substitute.toml`，库斯途无法自动加载 `HYUNDAI_PALISADE.json` NNFF 权重。
13. **`UnifiedParams` 类型混淆与并发写风险**  
    - `selfdrive/carrot/config.py:51-56, 63-88, 328-330`：`int` 与 `bool` (`0/1`) 判别分支冲突、`nav_params.json` 写入无文件锁、`get()` 无 JSON 回退。
14. **其余笔误、空指针与死代码**  
    - `carrot_serv.py:1290-1291`（次转弯误判主转弯绿灯）、`carrot_serv.py:1654`（`szTBTMainTextNext` 错读 `szTBTMainText`）；  
    - `longitudinal_planner.py:259`（重复赋值 `accel_limits_turns[0] = accel_limits_turns[0] = 0.0`）、`L295-298`（硬编码 `_jerk_factor = 1.5`）；  
    - `carrot_man.py:1098`（`and` 误用代替 `or`）、`L1139`（`max_curve == 0.0` 除零）、`L1158-1162`（`KeyboardInterrupt` 未退出循环）；  
    - `carrot_functions.py:88, 103, 142, 221`（`DrivingMode(0)` 异常与 `dynamicTFollowLC=0.0` 初始值清零时距）；  
    - `safety_hyundai.h:441, 480`（`return hyundai_init_carrot(...)` 导致后方原版 init 代码不可达）；`hyundaican.py:29, 53`（硬编码 `CF_Lkas_SysWarning = 0`）。
