# 27 库斯途双端协同工程 · 独立审计最终结论汇总（Consolidated Final Review）

> **汇总来源**：`24_双端全量工程独立安全审查报告_Master_Review_Result.md`（首轮双端红队审计）、`26_整改闭环复核报告_Remediation_Verification.md`（整改验证）
> **被审工程**
> - 车机端：`E:\汽车\库斯途升级破解\AmapNavi-Reborn`（Android 4.4.2 / Dalvik / i.MX6 / 960×1280）
> - C3 端：`E:\code\openpilot-ck89757`（`cp-custo-amap`，基线 `24b7ff2`）
> **审计方式**：白皮书与整改报告所声称的每一处修改 ↔ 两端**当前工作区真实源码**逐行比对（不做文档评审，不采信截图与结论）
> **取证限制**：本机 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`）→ **未执行** git / adb / dumpsys / sha256sum / 编译 / 实机测量。本文所有"已修复 / 未修复"结论均基于源码阅读，`file:line` 可直接复核；报告中的实测数字（PSS、功耗、温度、提交哈希、APK 指纹）一律不采信。
> **汇总日期**：2026-11-02
> **最终判定**：🔴 **[FAIL] — 禁止实车部署。** 功能链路当前物理断开，安全门禁在实际变道时段内不生效。

---

## 一、总判定与一句话结论

| 轮次 | 对象 | 判定 | 核心原因 |
| :--- | :--- | :---: | :--- |
| 首轮（24） | 双端方案 + 源码 | 🔴 FAIL | 端口同向冲突、量纲全错、双发布者竞态、TTC 门禁五重失效 |
| 整改核查（26） | 整改报告 25 的 10 项修复 | 🔴 FAIL | 5 项已修、2 项半修、2 项名义修、**1 项未修且是前提**；另**新增 1 个 Critical 回归** |

**一句话**：*整改改了 9 处代码，但把最关键的两处改成了"看起来对、实际更糟"——端口仍是两端镜像（换数字没换角色），探针回包把车机自己的 IP 当成 C3 的地址，于是 HUD 会显示"已连接"而报文一条也到不了对端。*

---

## 二、审计结论速览（按端）

| 维度 | 车机端 | C3 端 | 协同链路 |
| :--- | :---: | :---: | :---: |
| 通信契约（端口/字段/握手） | 🟠 | 🟠 | 🔴 断开 |
| 安全门禁（后车 TTC / 净空） | 🟢 已修 | 🔴 未生效 | — |
| 进程与并发 | 🟢 | 🟠 | — |
| 实时性与 Dalvik 内存 | 🟠 声明不实 | 🟢 | — |
| 功能安全声明与代码一致性 | 🟠 | 🔴 | 🔴 |
| 文档/证据可信度 | 🔴 | 🟠 | 🔴 |

---

## 三、缺陷总台账（40 项，含整改后状态）

> 状态：✅已修 ｜ 🟠部分修 ｜ ❌未修 ｜ ⚪文档/证据类（无需改码）
> 前缀：`HU:` = `AmapNavi-Reborn/app/src/main/java/tech/touka/amapnavi/`；`C3:` = `openpilot-ck89757/`

### 3.1 阻断级（必须全修才可上车）

| 编号 | 端 | 位置 | 级别 | 缺陷 | 状态 |
| :---: | :---: | :--- | :---: | :--- | :---: |
| **B-01** | 协同 | `HU:data/udp/CarrotUdpClient.kt:31-32` / `C3:selfdrive/carrot/amap_navi.py:200-201` | Critical | **端口同向冲突**：车机 bind 7706 / 发 7705；C3 bind 7706 / 发 7705 → 两端角色镜像，双向全断 | ❌ |
| **B-02** | 协同 | `C3:selfdrive/carrot/amap_navi.py:604-627` / `HU:data/udp/UdpDeviceDiscovery.kt:122-127` | Critical | **探针回包 `ip` 填了探针发送方（车机自己）的地址**，车机据此把 C3 地址记成本机 → 指令发给自己；且 HUD 显示"已连接"（静默故障） | ❌（整改新引入） |
| **B-03** | C3 | `C3:selfdrive/carrot/amap_navi.py:1159` | Critical | `lb_vrel`（TTC 分母）由**左前方**估计器产出，`leftBehindTarget` 建而不用；同包前/后距离交替喂入同一实例 → 输出饱和失真（右侧 1197 行写法正确） | ❌ |
| **B-04** | C3 | `C3:selfdrive/controls/lib/desire_helper.py:920` | Critical | TTC 门禁整段包在 `if self.carrot_lane_change_count > 0` 内；车机只发 `LANECHANGE`（该计数 = 4 帧 = **0.2 s**），`OVERTAKE` 分支不可达 → **门禁在变道真正需要的数秒内不存在** | ❌ |
| **B-05** | C3 | `C3:selfdrive/controls/lib/desire_helper.py:1213+` | Critical | 变道执行阶段（`laneChangeStarting`）只判 `lane_change_prob/ll_prob`，**无 TTC 复检**，无法中止已发起的变道 | ❌ |

### 3.2 车机端（Android 4.4 / Dalvik / i.MX6）

| 编号 | 位置 | 级别 | 缺陷 | 状态 |
| :---: | :--- | :---: | :--- | :---: |
| H-01 | `HU:data/udp/CarrotTelemetryParser.kt:47-52,66-67`；`HU:domain/safety/LateralSafetyEvaluator.kt:78-83` | Critical | 净空门禁量纲（mm 当 m、负值当正） | ✅ 已修（`parseDistanceMeter` = abs/1000） |
| H-02 | `HU:data/prefs/UserSettingsRepository.kt:130-137` | Major | `loadOvertakeSettings()` 仅回填 3 字段，其余 6 项走默认值；`setInt/setFloat` 不刷新缓存 → 改参数必须重启；`KEY_OVERTAKE_MODE` 从不读取、从不下发 | ❌ 未触及 |
| H-03 | `HU:data/relay/RelayEngine.kt:152-158` | Major | 决策在 UDP 收包协程内同步执行，且每包 `new CarState`、每 tick `new OvertakeStatus` + `String.format` | ❌ |
| H-04 | `HU:data/udp/CarrotTelemetryParser.kt` / `CarrotUdpClient.kt:76-84` | Major | 每包仍 `String(packet.data,…)` 分配；`scanFloat` 已去 substring ✅，但"零分配"整体不成立 | 🟠 |
| H-05 | `HU:ui/main/MainActivity.kt:245-300` | Major | HUD 在 Main 线程 20-50Hz 全量 `setText`/`setTextColor`/`setBackgroundColor`；🚦/🟢 emoji 在 Android 4.4 无字形（豆腐块） | ❌ |
| H-06 | `HU:domain/decision/OvertakeStateMachine.kt:243-248`；`C3:amap_navi.py` 遥测 | Major | 完成反馈 `atc_state` **两端都不存在**（C3 不发、车机在等）→ 每次变道走超时分支且"按完成结算"→ 失败当成功 | ❌ |
| H-07 | `HU:../build.gradle:38-43`；`HU:../AndroidManifest.xml` | Minor | `minifyEnabled false`（文档称已开 R8）、仍存在 5 个独立 Setting Activity（文档称已废跨 Activity） | ⚪/❌ |
| H-08 | `HU:ui/main/MainActivity.kt:172-178` | Minor | 返回键 `finish()` 主界面（车载宜 `moveTaskToBack`） | ❌ |
| H-09 | `HU:../AndroidManifest.xml:43-90` | Minor | 5 个 `exported="true"` + 无 data scheme 的 VIEW filter | ❌ |
| H-10 | `HU:service/KeepAliveService.kt:24-35` | Suggestion | 通知对象重复构造；彩色启动图标当状态栏小图标。**Dalvik 兼容性做法正确**（`@RequiresApi(26)` 隔离在独立 object 内，API19 不加载该类，不会 `VerifyError`）——应保留 | ❌ |

### 3.3 C3 端（openpilot / cp-custo-amap）

| 编号 | 位置 | 级别 | 缺陷 | 状态 |
| :---: | :--- | :---: | :--- | :---: |
| C-01 | `C3:selfdrive/carrot/amap_navi.py:609-615,1509-1540` | Critical | 发现线程写 `last_time` 而清理线程读 `last_seen` → `KeyError` 打死清理线程 | ✅ 已修（双键写入）；⚠️ 清理线程**仍无 try/except**，同类故障不可自愈 |
| C-02 | `C3:selfdrive/controls/lib/desire_helper.py:1336-1349` | Major | 接管条件已去"反向"限制 ✅；但 `lane_change_audio(4)` 仍被注释，且 `atc_cancel_delay = min(-1, …)` 恒 ≤ -1 → **"领航已退出"语音永不播报** | 🟠 |
| C-03 | `C3:selfdrive/carrot/amap_navi.py:190` | Major | 独立进程 SubMaster 不含 `carState` → 遥测整车状态段整体缺失 | ✅ 随"撤回独立进程"消解 |
| C-04 | `C3:amap_navi.py:1636-1780` / `HU:CarrotTelemetryParser.kt:33-41` | Major | 新旧键并存：`break_press`↔`brake_press`；C3 不发 `lidar_behind_vdist_time/atc_state`；同报文三份重复投递；UDP 实为 10Hz | ❌ |
| C-05 | `C3:cereal/custom.capnp:76-77` / `C3:cereal/gen/cpp/custom.capnp.h:63-79` | Major | 生成头仍 `CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d, 8, 0)`（应为 9）→ 生成物未重跑 | ❌ |
| C-06 | `C3:desire_helper.py:431,505-524` | Major | 断网后计数 20 s 自然衰减，归零走常规自主变道分支，非"单车道居中" | ❌ |
| C-07 | `C3:opendbc_repo/opendbc/car/torque_data/substitute.toml:43` | Major | 库斯途 NNFF 映射缺失 | ✅ 已落盘（待实机校验 `HYUNDAI_PALISADE` 参数存在） |
| C-08 | `C3:amap_navi.py:1001-1017` + `desire_helper.py:505-524` | Major | `CANCEL_LANE_CHANGE→CANCEL` 转换已加 ✅，但**消费端 `desire_helper` 只识别 LANECHANGE/OVERTAKE，不识别 CANCEL** → 紧急撤销仍是空操作 | 🟠 |
| C-09 | `C3:amap_navi.py:1001-1017` | Minor | `cmd_index` 单调校验只更新计数；`remote_cmd/overtake_mode` 仍无条件赋值 → 白名单内重放旧包可改写超车模式 | 🟠 |
| C-10 | `C3:process_config.py:144` | Critical | 解禁 `amap_navi` 造成双实例 + `MultiplePublishersError` 竞态 + UDP 双 bind | ✅ 已撤回（推荐方案 a） |
| C-11 | `C3:opendbc_repo/opendbc/car/hyundai/interface.py:202,216-222` | Minor | `startAccel=1.0` 为全 Hyundai 通用、`0x485 LFAHDA` 为上游既有机制，被文档包装成"库斯途专属" | ⚪ 文档修正 |
| C-12 | `C3:desire_helper.py`（全文） | Minor | 文档称"5.0 s S 曲线 / ≤0.08g / jerk ≤0.05g·s⁻¹"无实现证据（`LANE_CHANGE_TIME_MAX=10` 仅是超时上限） | ⚪ 需提供 file:line 或撤回 |

### 3.4 文档与证据链

| 编号 | 位置 | 级别 | 问题 | 状态 |
| :---: | :--- | :---: | :--- | :---: |
| D-01 | `22:§3.3①` | Major | 展示的 `CarrotTelemetryParser`（`CarrotTelemetry`/`extractDouble`）**在真实文件中不存在** | ❌ |
| D-02 | `22:§5.1` | Critical | 端口契约表方向与车机代码相反 | ❌ |
| D-03 | `22:§3.3, §4.4, §3.4` | Major | "开启 R8 精简"、"废除跨 Activity"、"NNFF 已配"、"PSS 3.5MB/1.65W/39℃" 均无据 | ❌ |
| D-04 | `23`（提示词） | Major | 把未经验证的端口/TTC/20ms 接管前提写死，会误导外部模型给出 PASS | ❌ |
| D-05 | `25:§2.1, §3.6, §4.1` | Critical | "端口完全咬合/双向瞬间打通"不成立；"立即播报"代码仍是注释；APK 指纹与 PSS 无法复核，且文档内 3.5MB 与 15.2MB 自相矛盾 | ❌ |

**统计（整改后）**：已修 6 项；部分修 4 项；未修 22 项；文档类 8 项。其中 **Critical 未修 5 项（B-01~B-05）+ 新增 1 项（B-02）**。

---

## 四、阻断项补丁（4 处，可直接复制；改完必须实测）

### P-1 端口交叉（B-01）

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-    self.navi_port = 7705        # 车机 PORT_TELEMETRY：遥测收端口
-    self.navi_remote_port = 7706  # 车机 PORT_CONTROL：指令发往 C3 的端口
+    self.navi_port = 7706        # C3 遥测【发送】目标 = 车机 PORT_TELEMETRY(7706)
+    self.navi_remote_port = 7705  # C3 指令【接收】端口 = 车机 PORT_CONTROL(7705)
```

> 判定口诀：**一端的 send 端口必须等于另一端的 bind 端口；绝不能"同一端口既收又发同一类报文"**。改完后的正确矩阵：
> 车机 bind 7706 / send→7705 ｜ C3 bind 7705 / send→7706

### P-2 探针回包填 C3 自身 IP（B-02）

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-            "ip": ip,
+            "ip": self.navi_get_local_ip() or ip,   # 绝不能用探针发送方地址
```

车机侧建议加自检：`if (捕获IP == 本机IP) 视为无效响应`。

### P-3 左后速度估计器（B-03）

```diff
-                self.shared_data.lb_vrel = self.leftFrontTarget.update(lb_dreltmp, dist_timems)
+                self.shared_data.lb_vrel = self.leftBehindTarget.update(lb_dreltmp, dist_timems)
```

### P-4 门禁脱离计数器 + 执行期复检（B-04 / B-05）

```python
# desire_helper.py: laneChangeStarting 分支内追加（不依赖 carrot_lane_change_count）
      elif self.lane_change_state == LaneChangeState.laneChangeStarting:
        _alive = self.sm.alive['amapNavi']
        _ttc = amapNavi.lidarBehindVdistTime if _alive else 0.0
        _thr = {0: 1.8, 1: 2.5, 2: 3.5}.get(amapNavi.overtakeMode, 2.5)
        if (_ttc <= 0.0) or (_ttc < _thr):
          self.lane_change_state = LaneChangeState.off
          self.lane_change_direction = LaneChangeDirection.none
          self.trigger_name = "rear ttc abort"
          self.lane_change_audio(True, 12, 0)
```

> 同步补：`CANCEL` 消费分支（C-08）、`atc_cancel_delay = max(-1, …)`（C-02 语音）、`overtake_mode/remote_cmd` 移入 `idx > cmd_index` 分支内（C-09）。

---

## 五、验收流程（先测"通不通"，再测"变不变"）

```bash
# ① 端口归属：每个端口恰好一个 owner，且 bind/send 角色符合 §四 矩阵
ss -ulnp | grep -E ':(4210|5510|7705|7706)\b'

# ② 探针回包内容：ip 字段必须是 C3 自己的地址
sudo tcpdump -ni any -A 'udp port 4210' -c 4

# ③ 单包双向连通（绕过全部业务逻辑）
#   C3 → 车机（HUD 车速应变化）
python3 -c "import socket,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(json.dumps({'v_ego_kph':88}).encode(),('<车机IP>',7706))"
#   车机 → C3（C3 打印 remote_cmd）
python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'{\"cmd\":\"LANECHANGE\",\"arg\":\"LEFT\",\"param\":2,\"seq\":9}',('<C3_IP>',7705))"

# ④ 三段闭环：discover→pong（ip 正确）→ 遥测→HUD 3 字段 → 按钮→carrotMan.carrotCmd→desire.trigger_name

# ⑤ Dalvik 红线（每次装 APK 后必查）
adb logcat | grep -E "VerifyError|NoClassDefFoundError|GC_FOR_ALLOC"
```

**只要 ③ 有一向不通，后续任何"变道成功/失败"的观察都无法归因。**

---

## 六、上线节奏建议

| 阶段 | 允许做的事 | 禁止的事 |
| :--- | :--- | :--- |
| 阶段 0：台架 | 端口/回包/单包双向 + 六类故障注入（雷达断流、负距离、并排车、消息缺失、车机断电、畸形 param） | 点火上路 |
| 阶段 1：驻车通电 | 断电重启 10 次、挂 R 挡 10 次（记录倒车影像首帧）、观测 GC 频次与 PSS | 开启智驾 |
| 阶段 2：封闭场地 | 低速直线、单次打灯变道（驾驶员全程手扶）、验证"该阻断时确实阻断" | 高速、连续变道 |
| 阶段 3：高速 | 单次真实变道 + 完整日志留存（pcap + rlog + app_log） | 夜间/雨天/大车流首次试 |

**核心原则**：先证明"它在危险时会停"，再证明"它平时能动"。当前 B-01~B-05 未修的状态下，连"它能不能动"都尚未被观测到。

---

## 七、证据索引（全部可复核）

| 主题 | 文件:行 |
| :--- | :--- |
| 车机端口常量 | `HU:data/udp/CarrotUdpClient.kt:31-32` |
| C3 端口常量 | `C3:selfdrive/carrot/amap_navi.py:200-201` |
| 探针发送（车机） | `HU:data/udp/UdpDeviceDiscovery.kt:72-83` |
| 探针回包（C3） | `C3:selfdrive/carrot/amap_navi.py:591-627` |
| 回包解析（车机） | `HU:data/udp/UdpDeviceDiscovery.kt:113-134` |
| TTC 发布（C3） | `C3:selfdrive/carrot/amap_navi.py:293-303` |
| 左后速度估计器 | `C3:selfdrive/carrot/amap_navi.py:1159`（右侧正确写法 `:1197`） |
| TTC 门禁（C3） | `C3:selfdrive/controls/lib/desire_helper.py:920-937` |
| 变道执行阶段 | `C3:selfdrive/controls/lib/desire_helper.py:1213-1225` |
| 接管处理 | `C3:selfdrive/controls/lib/desire_helper.py:1336-1352` |
| 指令解析 | `C3:selfdrive/carrot/amap_navi.py:1001-1017` |
| 量纲转换（车机） | `HU:data/udp/CarrotTelemetryParser.kt:47-52,66-67` |
| 净空门禁（车机） | `HU:domain/safety/LateralSafetyEvaluator.kt:78-83` |
| 参数仓库 | `HU:data/prefs/UserSettingsRepository.kt:130-137` |
| 执行超时结算 | `HU:domain/decision/OvertakeStateMachine.kt:243-248` |
| 进程配置 | `C3:system/manager/process_config.py:144` |
| 力矩映射 | `C3:opendbc_repo/opendbc/car/torque_data/substitute.toml:43` |
| capnp 生成物 | `C3:cereal/gen/cpp/custom.capnp.h:63-79` |

---

**本文为独立审计结论汇总，未修改任何工程文件；所有判定均可在上述 file:line 复核。**
**关联文档**：`24_双端全量工程独立安全审查报告_Master_Review_Result.md`（首轮）、`26_整改闭环复核报告_Remediation_Verification.md`（整改验证）。
