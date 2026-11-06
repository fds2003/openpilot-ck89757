# 32 库斯途双端协同工程 · 独立审计终审总报告（All Rounds Consolidated）

> **一句话结论**：通信链路已经真正打通，但**安全语义的最后一公里尚未闭环**——紧急撤销按下去 C3 不动、变道失败被结算为成功、雷达掉线后门禁静默消失。当前状态：**可上台架联调，不可上开放道路**。
>
> **受审工程**
>
> - 车机端：`E:\汽车\库斯途升级破解\AmapNavi-Reborn`（Android 4.4.2 KitKat / Dalvik / i.MX6 / 960×1280）
> - C3 端：`E:\code\openpilot-ck89757`（分支 `cp-custo-amap`，基线 `24b7ff2`，最新修复提交 `606b16c`）
>
> **审计轮次**：5 轮（首轮双端红队审计 → 25 号整改核验 → 28 号整改核验 → 三份核验报告交叉裁定 → 专车调优指南核验）
>
> **取证限制（重要，请连同结论一起读）**：本轮审计所运行的会话 **WSL/bash 不可用**（`HCS_E_SERVICE_NOT_AVAILABLE`），**未执行** git / sha256sum / py_compile / adb / dumpsys / 实车测量。所有 `file:line` 结论均由源码逐行阅读得出，可直接复核；凡"实机数据"（PSS、功耗、温度、APK 指纹、提交哈希）一律**标注不可验证**，不从文档转述中采信。
>
> **日期**：2026-11-03

---

## 一、终审判定

### 🟠 [NEEDS REVISION] —— 允许台架联调，禁止直接上车

| 能力维度 | 判定 | 依据 |
| :--- | :---: | :--- |
| 双端 UDP 通信（端口 / 握手 / 收发） | 🟢 **首次真正闭环** | 端口交叉成立、探针回包不再自指（双端双保险） |
| 后车 TTC 数据源（量纲 / 符号 / 估计器隔离） | 🟢 已闭环 | 绝对值化、双侧取最小、左后估计器修正 |
| 后车 TTC 安全语义 | 🔴 **未闭环** | 触发段困在 0.2 s 计数器；执行段 fail-open；"雷达掉线"与"无目标"不可区分 |
| 车机 → C3 控制闭环（撤销 / 定速 / 参数） | 🔴 **未闭环** | `CANCEL`、`SPEED_LIMIT` 均无消费者；车机超车模式无下发出口 |
| 变道结果判定 | 🔴 **未闭环** | `atc_state` 两端都不存在 → 每次变道必然"按完成结算" |
| 车机实时性（Dalvik GC / i.MX6 渲染） | 🔴 未动 | 决策在收包协程、HUD 20-50Hz 全量刷新 |
| 文档可信度 | 🔴 需系统性整改 | 多份文档存在"声称已修而代码未修""伪代码当实施说明" |

---

## 二、已完成闭环项（本轮唯一可放心的部分）

| 编号 | 内容 | 证据 | 提交 |
| :---: | :--- | :--- | :---: |
| M-01 | 端口同向冲突 → **交叉咬合** | C3 `amap_navi.py:200-201`（发 7706 / 收 7705）+ 车机 `CarrotUdpClient.kt:31-32`（收 7706 / 发 7705） | 606b16c |
| M-02 | 探针回包自指 → **双端双保险** | C3 `amap_navi.py:617-626` 用 `connect+getsockname` 取自身 IP；车机 `UdpDeviceDiscovery.kt:124-133` 优先物理源 IP 并过滤 127.0.0.1 | 606b16c |
| M-03 | 左后速度用左前估计器 → **修正** | `amap_navi.py:1166` 改用 `leftBehindTarget` | 606b16c |
| M-04 | 净空量纲（mm 当 m、负值当正） → **修正** | 车机 `CarrotTelemetryParser.kt:48-54` 取绝对值 + 单位归一 | 606b16c |
| — | 驾驶员接管条件去掉"反向"限制 | `desire_helper.py:1336-1339` | 606b16c |
| — | `atc_cancel_delay` 的 `min(-1,…)` 改 `max(-1,…)` | `desire_helper.py:1360`，语音播报分支自此可达 | 606b16c |
| — | 双实例/双发布者竞态消除 | `process_config.py:144` 恢复注释，由 `carrot_man` 内嵌实例独占 | 493e8dd |
| — | 清理线程 `KeyError` 引爆 | `amap_navi.py:609-615` 双写 `last_time`/`last_seen` | 493e8dd |
| — | 库斯途 NNFF 映射落盘 | `substitute.toml:43` | 606b16c |

> 说明：A、B 两份同行核验报告声称已实跑 `git` / `sha256sum` / `py_compile`，与 28 号报告的提交号 `606b16c`、APK 指纹 `e89640cc…`、字节数 `8,230,447` 一致。本人环境无法复现，此项按"他人可复现证据"标注。

---

## 三、缺陷主索引（M-01 ~ M-30，唯一编号源）

> 规则：**编号不复用、不重排**；任何"闭环"声明必须逐条引用编号 + 修复提交哈希。
> 状态：`FIXED` / `PARTIAL` / `OPEN` / `DOC-ONLY` / `UNVERIFIABLE`

### 3.1 阻断级（决定"是否可上车"）

| 编号 | 缺陷 | 端 | 位置 | 级别 | 状态 |
| :---: | :--- | :---: | :--- | :---: | :---: |
| M-01 | 端口同向冲突 | 协同 | `amap_navi.py:200-201` / `CarrotUdpClient.kt:31-32` | Critical | **FIXED** |
| M-02 | 探针回包把自己 IP 当 C3 | 协同 | `amap_navi.py:617-626` / `UdpDeviceDiscovery.kt:124-133` | Critical | **FIXED** |
| M-03 | 左后速度用左前估计器 | C3 | `amap_navi.py:1166` | Critical | **FIXED** |
| M-04 | 净空量纲与符号 | 车机 | `CarrotTelemetryParser.kt:48-54` | Critical | **PARTIAL**（边界见 M-11/M-12） |
| M-05 | 门禁困在 0.2 s 计数器 | C3 | `desire_helper.py:920` | Critical | **OPEN** |
| M-06 | 执行期复检 fail-open + 350 ms 权限窗 | C3 | `desire_helper.py:1246-1252` | Critical | **PARTIAL** |
| M-07 | 雷达掉线与"无目标"不可区分 | C3 | `amap_navi.py:295-305` | Major | **OPEN** |
| M-08 | `CANCEL_LANE_CHANGE` 无消费者 | C3 | `carrot_serv.py:354-360` / `desire_helper.py:507` | Major | **OPEN** |
| M-14 | 变道失败被结算为成功 | 车机 | `OvertakeStateMachine.kt:237-247` | Major | **OPEN** |

### 3.2 功能与一致性

| 编号 | 缺陷 | 端 | 位置 | 级别 | 状态 |
| :---: | :--- | :---: | :--- | :---: | :---: |
| M-09 | `SPEED_LIMIT` 无消费者（定速微调/匝道减速全失效） | C3 | `carrot_serv.py:354-360` | Major | **OPEN** |
| M-10 | 车机重启后序号锁死（`cmd_index` 不回退） | 协同 | `amap_navi.py:1008` / `CarrotUdpClient.kt:41` | Major | **OPEN** |
| M-11 | `parse(JSONObject)` 默认 999 → 0.999 m → 永久阻断 | 车机 | `CarrotTelemetryParser.kt:123-124` | Major(潜伏) | **OPEN** |
| M-12 | `parseDistanceMeter` 100 阈值双向反例 | 车机 | `CarrotTelemetryParser.kt:56-62` | Minor | **OPEN** |
| M-13 | 重放包仍可改写 `overtake_mode` | C3 | `amap_navi.py:1009-1020` | Minor | **OPEN** |
| M-15 | 超车模式/参数在车机侧无出口 | 车机 | `UserSettingsRepository.kt:130-137` | Major | **OPEN** |
| M-17 | capnp 生成物未重生成（仍 8 data word） | C3 | `cereal/gen/cpp/custom.capnp.h:70` | Major | **OPEN** |
| M-18 | 遥测三份重复投递 + 缺 `atc_state`/TTC 字段 | C3 | `amap_navi.py:1619-1622` | Minor | **OPEN** |
| M-19 | 清理线程无 try/except（线程可静默死亡） | C3 | `amap_navi.py:1509-1540` | Minor | **OPEN** |
| M-20 | 决策在收包协程 + HUD 20-50Hz 全量刷新 | 车机 | `RelayEngine.kt:152` / `MainActivity.kt:245+` | Major | **OPEN** |

### 3.3 文档、证据与设计指南

| 编号 | 内容 | 级别 | 状态 |
| :---: | :--- | :---: | :---: |
| M-16 | 验收手册第 2 步发 127.0.0.1 会被 `app_ip` 白名单丢弃 | Minor | **OPEN** |
| M-21 | 实机证据（PSS 15.5 MB / adb 设备号） | — | **UNVERIFIABLE** |
| M-22 | release APK 非标准 Gradle 产物路径（`apk/` 下仅 `debug/`） | — | **UNVERIFIABLE** |
| M-23 | "全部遗留问题 100% 修复"措辞失真 | — | **DOC-ONLY** |
| **M-24** | 指南 §3.2：`LANE_CHANGE_STEP_CUSTO` 不存在；`ll_prob` 不是变道时长控制器 | Major | **DOC-ONLY** |
| **M-25** | 指南 §5.1：`create_lfahda_mfc` 签名与信号名不符（真实为 `(packer, CC, blinking_signal)`，无 `HDA_SysState`/`HDA_SetSpeed`） | Major | **DOC-ONLY** |
| **M-26** | 指南 §4.3：`actual_stop_distance` 标识符不存在；红灯逻辑为纯视觉判定，与高德无耦合 | Major | **DOC-ONLY** |
| **M-27** | 指南 §4.2：`startAccel=1.0` 为全局行为且语义被误解（非加速度上限） | Minor | **DOC-ONLY** |
| **M-28** | 指南 §6.2：大核下线是上游 `set_power_save()`；`force_clk_on`/`force_rail_on` 不存在 | Minor | **DOC-ONLY** |
| **M-29** | 指南 §2.3：`τ_lead` 补偿公式量纲不闭合，且 `lateral_planner.py` 无此实现 | Minor | **DOC-ONLY** |
| **M-30** | 指南缺"`CarParams` 标定优先于 NNFF"（`wheelbase/centerToFront/mass/tireStiffnessRear` → `factor1/factor2`） | Major | **DOC-ONLY** |

**统计**：FIXED 3 ｜ PARTIAL 3 ｜ OPEN 14 ｜ DOC-ONLY 8 ｜ UNVERIFIABLE 2

---

## 四、四个必须理解的机理（不看代码也能判断对错）

### 4.1 为什么"雷达掉线 = 放行"是设计缺陷，而不是配置问题

发布端在"没有后车目标"时发送哨兵 `99.0`；消费端用 `0.0 < ttc < thr` 判定危险。于是**"雷达掉线"与"后方确实无车"产生完全相同的信号**，两种情况下都不阻断。而 `amapNavi` 由 `carrot_man`（`always_run`）持续发布，所以"消息失活才阻断"这条路永远是死的。
**结论**：安全函数必须能区分"安全"与"未知"三态（有目标安全 / 无目标 / 未知），并用显式有效性位承载。

### 4.2 为什么"0.2 s 门禁"等于没有门禁

车机只下发 `LANECHANGE`（`RelayEngine.kt:97`），C3 侧该计数为 `int(0.2/DT_MDL)=4` 帧 = 200 ms；`OVERTAKE` 分支因车机从不下发而不可达。一次线控变道需要数秒——**门禁在最需要的时段不存在**。

### 4.3 为什么"失败变道被结算为成功"是安全缺陷

C3 遥测 JSON 从不包含 `atc_state`，车机却在等 `atcState == 3`。因此每次变道必然走到 `executeTimeoutMs` 超时分支，该分支直接 `state = FINISHING` 并播报"变道完成"。**被阻断、卡住、未完成的变道，全部计入成功并进入冷却**——这会污染驾驶员对系统的信任基线。

### 4.4 为什么"撤销按钮无效"会让前面所有门禁失效

车机的 `onCancelCommand` 发 `CANCEL_LANE_CHANGE`，C3 `_update_command` 会把它转成 `"CANCEL"`，但**消费端 `desire_helper` 只识别 `LANECHANGE`/`OVERTAKE`**，`carrot_serv` 的命令表只有 `DETECT`。于是：驾驶员/车机判定危险时**没有任何外部手段让 C3 收手**，只剩驾驶员打方向盘这一条路。

---

## 五、可直接落地的补丁（按风险排序）

### P-1（M-07，最高风险）让"未知"变成阻断

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-    ttc = min(ttc_list) if ttc_list else 99.0
+    lidar_present = bool(self.shared_data.lidar_l or self.shared_data.lidar_r)
+    # 无目标 -> 99.0（安全）；雷达不在线 -> 0.0（未知，消费端按阻断处理）
+    ttc = min(ttc_list) if (lidar_present and ttc_list) else (99.0 if lidar_present else 0.0)
     self.shared_data.behind_ttc = ttc
     msg.amapNavi.lidarBehindVdistTime = float(ttc)
```

### P-2（M-06）执行期复检与全文件安全哲学对齐

```diff
-        if (0.0 < _ttc < _thr) and self.lane_change_ll_prob > 0.3:
+        _too_close = (not _alive) or (_ttc <= 0.0) or (_ttc < _thr)
+        if _too_close and self.lane_change_ll_prob > 0.3:
           self.lane_change_state = LaneChangeState.off
           self.lane_change_direction = LaneChangeDirection.none
           self.trigger_name = "rear ttc abort"
           self.lane_change_audio(True, 6, 0)
```

> 若坚持"已越中线不再中止"，必须补对等规则：`ll_prob <= 0.3` 时**禁止下发新变道指令**并立即播报告警，避免"既不停也不报"的沉默区。

### P-3（M-08 / M-09）补齐撤销与定速消费端

```diff
--- a/selfdrive/carrot/carrot_serv.py
+++ b/selfdrive/carrot/carrot_serv.py
@@
       command_handlers = {
         "DETECT": self._handle_detect_command,
+        "CANCEL": self._handle_cancel_command,
+        "SPEED_LIMIT": self._handle_speed_limit_command,
       }
```

```diff
--- a/selfdrive/controls/lib/desire_helper.py
+++ b/selfdrive/controls/lib/desire_helper.py
@@
-    elif carrotMan.carrotCmdIndex != self.carrot_cmd_index_last and (carrotMan.carrotCmd == "LANECHANGE" or carrotMan.carrotCmd == "OVERTAKE"):
+    elif carrotMan.carrotCmdIndex != self.carrot_cmd_index_last and carrotMan.carrotCmd == "CANCEL":
+      self.carrot_cmd_index_last = carrotMan.carrotCmdIndex
+      self.carrot_lane_change_count = 0
+      self.lane_change_state = LaneChangeState.off
+      self.lane_change_direction = LaneChangeDirection.none
+      self.lane_change_audio(True, 4, 0)
+    elif carrotMan.carrotCmdIndex != self.carrot_cmd_index_last and (carrotMan.carrotCmd == "LANECHANGE" or carrotMan.carrotCmd == "OVERTAKE"):
```

### P-4（M-10）车机重启后恢复可用

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-          self.shared_data.app_ip = ip
+          if self.shared_data.app_ip != ip:
+            self.shared_data.cmd_index = -1     # 车机 IP 变化=新会话，序号重新从 1 开始
+          self.shared_data.app_ip = ip
```

### P-5（M-14）失败不得结算为成功

```diff
--- a/AmapNavi-Reborn/.../domain/decision/OvertakeStateMachine.kt
+++ b/AmapNavi-Reborn/.../domain/decision/OvertakeStateMachine.kt
@@
         if (now - stateSinceMs > settings.executeTimeoutMs) {
-            state = OvertakeState.FINISHING
-            message = "变道执行超时 ${settings.executeTimeoutMs}ms，按完成结算"
+            onCancelCommand(candidate)
+            onSound(SoundEvent.LANE_CHANGE_CANCEL)
+            cooldownUntilMs = now + settings.interruptCooldownMs
+            state = OvertakeState.COOLDOWN
+            blockCause = BlockCause.DRIVER_OVERRIDE
+            message = "执行超时且未收到完成反馈，已撤销并锁定 ${settings.interruptCooldownMs / 1000L} 秒"
+            return
         }
```

### P-6（M-11）潜伏的永久阻断

```diff
-            leftRearDistance = parseDistanceMeter(json.optDouble("lb_drel", 999.0).toFloat()),
-            rightRearDistance = parseDistanceMeter(json.optDouble("rb_drel", 999.0).toFloat()),
+            leftRearDistance = parseDistanceMeter(json.optDouble("lb_drel", -999999.0).toFloat()),
+            rightRearDistance = parseDistanceMeter(json.optDouble("rb_drel", -999999.0).toFloat()),
```

### P-7（M-17）生成物一致性（必须在 C3 上执行）

```bash
cd /data/openpilot && scons -j4 cereal/gen/cpp/custom.capnp.h
grep -n "CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d" cereal/gen/cpp/custom.capnp.h
# 期望为 (…, 9, 0)；当前仍为 8，说明未重生成
```

### P-8（M-05 / M-15 / M-20）结构与实时性

- 门禁移出 `carrot_lane_change_count > 0` 分支（或让车机改发 `OVERTAKE` 使 20 s 窗口可达，二选一需先定契约）；
- 车机 `loadOvertakeSettings()` 全字段绑定 + 任意 `set*` 后 `reload()` + `KEY_OVERTAKE_MODE` 随指令 `param` 下发；
- 决策移出 UDP 收包协程（单线程 conflated 通道）；HUD 渲染节流到 10 Hz + 变更检测。

---

## 六、验收流程（先证"不通即停"，再证"能变"）

```bash
# ① 端口归属：每个端口恰好一个 owner，且 bind/send 角色交叉
ss -ulnp | grep -E ':(4210|7705|7706)\b'

# ② 探针回包：ip 必须是 C3 自己（不是车机）
sudo tcpdump -ni any -A 'udp port 4210' -c 4 | grep -o '"ip":"[^"]*"'

# ③ 单包双向（注意 M-16：不要用 127.0.0.1，app_ip 白名单会丢包）
python3 -c "import socket,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(json.dumps({'v_ego_kph':88}).encode(),('<车机IP>',7706))"
python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'{\"cmd\":\"LANECHANGE\",\"arg\":\"LEFT\",\"param\":2,\"seq\":9}',('<C3_IP>',7705))"

# ④ 撤销链路（M-08 修好后才有意义）
python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'{\"cmd\":\"CANCEL_LANE_CHANGE\",\"seq\":99}',('<C3_IP>',7705))"
#   期望：desire_helper 打印 state=off / trigger 复位

# ⑤ Dalvik 红线（每次装 APK）
adb logcat | grep -E "VerifyError|NoClassDefFoundError|GC_FOR_ALLOC"
```

**负向测试为准入条件**（正向跑通不算通过）：雷达断流 / 负距离 / 并排车 / 消息缺失 / 车机断电 / 畸形 `param` 六类反例，逐类确认"该阻断时确实阻断"。

---

## 七、放行分级

| 阶段 | 前置条件 | 当前是否可做 |
| :--- | :--- | :---: |
| 台架联调（端口/握手/单包/遥测上屏） | 无需改码，按 §六 修正测试命令 | ✅ **可以** |
| 封闭场地低速单次变道 | 修完 M-05 / M-06 / M-07 / M-08 / M-14 | ❌ |
| 高速实车 | 再加修 M-09 / M-10 / M-11 / M-15 / M-17 / M-18 / M-20 | ❌ |

---

## 八、文档可信度评级（供后续引用时判断权重）

| 文档 | 主要问题 | 可信度 |
| :--- | :--- | :---: |
| `19` 白皮书 / `20` 主提示词 | 端口方向、TTC 有效性、20 ms 接管等前提与代码相反，会误导外部模型 | 🔴 不可作证据基 |
| `22` 双端总纲 | 展示的解析器代码在实际文件中不存在；"已配 NNFF / 已开 R8 / 已废跨 Activity"均不实 | 🔴 |
| `23` 终极主提示词 | 同上，前提未经验证 | 🟠 需重写前提 |
| `25` 25 号整改报告 | 端口"咬合"结论相反；"立即播报"代码仍是注释 | 🔴 |
| `28` 28 号交付报告 | 5 项阻断真实落地（本轮最大进步），但"全部遗留 100% 修复"不成立 | 🟠 |
| `21` 专车调优指南 | 车型分析扎实；4 处实施代码为伪代码、1 处机制选错对象、2 处把上游能力当定制 | 🟠 |
| `26 / 27 / 29×3 / 30` 各轮核验 | 与代码一致（本人复核过其中关键项） | 🟢 |

---

## 九、流程改进（比任何单点缺陷都重要）

本项目连续多轮出现同一类失效：**上轮点名的致命项在下一轮静默消失**（典型：TTC fail-open 在另一套编号体系里没有对应编号，被整套漏掉）。四条规则建议立即生效：

1. **唯一主索引**：以本文件 §三 为唯一编号源，新发现只追加不重排；任何"闭环"声明必须逐条引用编号 + 提交哈希。
2. **禁止绝对化措辞**：不允许"100% 闭环 / 全部修复 / 完全具备上车条件"；改为"已闭环 N 项（附编号）/ 待处理 M 项（附编号）"。
3. **负向测试即准入**：安全相关功能必须证明"危险时会停"，正向往返不算通过。
4. **证据分层标注**：`代码级`（file:line）／`命令级`（可重放命令 + 输出）／`实机级`（设备号 + 抓图），三者不得混写成同一结论。

---

## 十、终审寄语

这一轮工程的进步是真实的：两个致命的通信断路被一次性改对，而且两端都加了双重防护（C3 用 `getsockname` 取自身 IP，车机优先用 UDP 物理源地址）——说明整改方已经理解了问题本质，而不是继续换数字。A、B 两份并行核验在"链路已通"上也给出了完全一致的结论，这在多方审计里并不常见。

剩下的分歧已经不在代码事实，而在**验收口径**：是"改动落盘了"，还是"端到端真的闭环了"。

**`CANCEL` 按下去 C3 不动、变道失败显示成功、雷达掉线门禁消失——这三件事只要有一件没被证明，就不该说闭环。** 补齐 §五 的 P-1~P-5 五项（合计不足 40 行），这套双端协同就真正具备了上车联调的工程基础。

---

**本报告为独立审计意见，未修改任何工程文件；所有判定可在上述 `file:line` 复核。**
**分轮详版**：`24`（首轮双端审计）、`26`（25 号整改核验）、`27`（中期汇总）、`29`（28 号整改核验）、`30`（三份核验交叉裁定 + 主索引）、`31`（专车调优指南核验）。
