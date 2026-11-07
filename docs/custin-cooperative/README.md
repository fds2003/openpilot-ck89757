# 库斯途双端协同智驾系统 — 文档总览

> 车机端：`AmapNavi-Reborn`（北京现代库斯途，Android 4.4.3 / API 19，armeabi-v7a）
> C3 端：`openpilot-ck89757`（分支 `cp-custo-amap`，Comma 3 / AGNOS）
> 文档基线：2026-11-06，所有结论以**当前代码**为准

---

## 1. 系统定位

车机负责**导航意图与人机交互**，C3 负责**感知、执行与安全否决**：

```
高德车机版 ──广播──► 车机 App ──UDP 7705──► C3 ──CAN──► 车辆
                     ▲                │
                     └──UDP 7706──────┘
```

- 车机**不向 C3 发送原始导航数据**（算路、TBT、推荐车道、限速均留在本机）。
- C3 接收的是**决策结论**：变道意图、目标车速、车道线类型、转向灯。
- C3 保留独立安全门禁与执行权；协同模式下不自主发起导航转向。

---

## 2. 当前通信基线（与代码一致）

| 端口 | 方向 | 载荷 | 实现 |
|---|---|---|---|
| 4210 | 车机 → 广播 | `{"cmd":"discover","port":5510}` | `UdpDeviceDiscovery` / `_discovery_responder_thread` |
| 5510 | 车机本地绑定 | 发现响应 | 同上 |
| 7705 | 车机 → C3 | `{"cmd","direction","arg","param","seq","index","v_cruise","blinker","timestamp"}` | `CarrotUdpClient` / `_headunit_cmd_recv_thread` |
| 7706 | C3 → 车机 | 遥测 JSON（约 42 键，10–20Hz） | `make_navi_message` / `CarrotTelemetryParser` |
| 4211 | 车机 → C3 | `{"ctrlid","ctrl":"blinker","state"}` 或传感器上行 | `sendBlinkerCtrlComm` / `_udp_recv_thread` |
| 4213 | C3 内部 / 车机 → C3 | `{"resp":"lane","left_lane","right_lane","lane_valid"}` | `lane_runner` / `_lane_recv_thread` |
| 4215 | adbridge → C3 | `{"tl":"red\|green","cd","st","dir"}` | `_traffic_light_recv_thread` |
| 5210 / 4212 | — | 仅常量声明，**从未使用** | — |

管理通道保持 loopback：ZMQ `127.0.0.1:7710`、路由 `127.0.0.1:7709`、Kisa `127.0.0.1:12345`。

---

## 3. 文档地图

| 文档 | 内容 |
|---|---|
| `01_产品功能与UI规格.md` | 功能矩阵、HUD、设置项、音效、与原版差异 |
| `02_系统架构与设计.md` | 分层架构、HU/C3 模块、关键决策、车辆参数 |
| `03_通信契约与功能边界.md` | 端口、载荷、高德广播、功能边界、代码证据 |
| `04_C3端协同设计.md` | 进程模型、线程、命令链、协同模式、lane_runner |
| `05_代码基线与差异分析.md` | 两个代码仓基线、APK/Reborn/C3 差异、已修与残留 |
| `06_审计与整改总册.md` | 审计时间线、缺陷主索引、最终裁定、经验 |
| `07_实施与部署.md` | 车机/C3 构建、依赖、模型、参数、回滚 |
| `08_验证与交付.md` | TDD 流程、测试结果、真实模型实测、验收标准 |
| `09_四端联合核验.md` | 当前权威协议核验与可运行性判定 |
| `10_上车验证清单.md` | 54 项实车检查 |
| `11_仪表移植方案.md` | 原厂 HSAE 仪表移植设计、字段映射、测试与风险 |
| `12_仪表投影布局对照.md` | custin/cluster 的 Parcel 布局对照与偏差清单 |
| `13_原厂三包与仪表投影分析.md` | 三个原厂 APK 的角色、仪表链路、显示码语义、IPC 契约 |
| `14_原厂三包功能全景与架构拆解.md` | 三个原厂 APK 的全功能矩阵、架构分层、跨 App IPC 与改造启示 |
| `15_L1共存切换实施方案.md` | 高德替代百度导航、保留原车功能的 L1 共存方案与工作分解 |
| `16_L1详细架构与实现设计.md` | L1 的组件架构、线程模型、状态机、代码级实现设计与测试设计 |
| `17_未完成工作与剩余事项.md` | 待完成/待实车标定事项总表（ADAS/L1/广播/C3/工程），按执行顺序 |

---

## 4. 单一事实源

1. **协议与可运行性**：`09_四端联合核验.md`
2. **代码现状**：两个仓库的 HEAD 与 `docs/custin-cooperative/05_代码基线与差异分析.md`
3. **历史过程**：`archive/`（75 份原始文档，保留追溯，不作为当前结论）

> 任何文档与代码冲突时，以代码为准，并在本目录对应文档中更新。

---

## 5. 归档说明

`archive/` 保留整合前的全部原始文档，包括早期设计、历轮审计、整改交付等。
合并文档只保留结论、关键证据与待办，细节可回溯 archive 中的原件。

---

## 6. 真车标定脚本

`scripts/calibrate_cluster.sh`（两仓均有副本）用于在 HSAE 车机上逐项验证
仪表投影与 ADAS 电子地平线（transact 14），把仪表实际反应回填到
`AdasPayloadCodec`/`ClusterMapper` 语义名。

**使用方式**（PC 端 Git Bash / WSL，adb 能连车机）：

```bash
# 全流程：打开仪表投影页 → 检测 HSAE → 逐帧 TBT/图标/ADAS
./scripts/calibrate_cluster.sh

# 只发某个 displayType 标定帧（如 96 环岛）
./scripts/calibrate_cluster.sh --seq 96

# 只发 ADAS Position 测试帧（type 458）
./scripts/calibrate_cluster.sh --adas

# 指定 adb 设备（多设备时）
ADB_DEVICE=192.168.x.x:5555 ./scripts/calibrate_cluster.sh
```

要点：
- 车机需装 Reborn v1.4.0+ 且为系统应用/平台签名（可写 HSAE 仪表）。
- 每发一帧立即观察仪表对应区域（箭头/限速/弯道/罗盘/进度）反应并记录。
- 脚本靠 `uiautomator dump` 定位按钮；车机 UI 高刷新时 dump 偶发失败，
  先 `--seq 65` 单帧冒烟再跑全流程。
- 标定结果回填：`AdasPayloadCodec` 注释、`ClusterMapper.mapTurnType`
  候选码、`17_未完成工作与剩余事项.md` 勾选 `[实车]`。
