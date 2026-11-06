# 30 三份 29 号核验报告交叉裁定 + 缺陷主索引（Master Adjudication & Single Source of Truth）

> **背景**：针对 `28_最终全量修复闭环与实测验收交付报告.md`，同一目录下并存三份独立核验：
> - **A**：`29_28号最终交付报告独立核验与真伪对照.md`（编号体系 F-xx / O-xx，有 git 与 sha256 实测）
> - **B**：`29_28号最终交付报告_独立核验报告.md`（编号体系 F-29-xx，有 `py_compile` 与 sha256 实测）
> - **C**：`29_第28号最终交付报告独立核验_Final_Verification.md`（编号体系 P-/N-/C-，无 shell 权限，纯源码取证）
>
> **本文目的**：① 裁定三份报告的一致与分歧（以代码为准，不以"多数意见"为准）；② 建立**唯一主索引表**，终结"同一缺陷在不同报告里编号不同 → 下一轮被静默丢弃"的流程性失效；③ 给出唯一权威判定与最小补齐路径。
> **取证限制**：本文作者所在会话 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`），**未执行** git / sha256sum / py_compile / adb。A、B 两份报告声称已实跑上述命令并给出可重放命令，本文采信其"可复现性"，但标注**未经本人复现**；所有 `file:line` 与逻辑判定均由本人独立阅读源码得出。
> **裁定日期**：2026-11-03

---

## 一、裁定结论

### 🟠 [NEEDS REVISION]（三份报告一致）

| 维度 | 裁定 | 三份报告是否一致 |
| :--- | :--- | :---: |
| 双端通信链路（端口 / 探针 / 遥测 / 指令） | ✅ **首次真正闭环** | 一致 |
| 后车 TTC 数据源（绝对值 / 双侧 / 估计器隔离） | ✅ 已闭环 | 一致 |
| 后车 TTC 门禁（安全语义） | 🔴 **未闭环**：触发段困在 0.2 s 计数器；执行段 fail-open；"雷达掉线"与"无目标"不可区分 | 一致 |
| 车机 → C3 控制闭环（撤销 / 定速） | 🔴 **未闭环**：`CANCEL` 与 `SPEED_LIMIT` 均无消费者 | 一致（B 明确分项，C 合并为一条） |
| 变道结果判定 | 🔴 未闭环：`atc_state` 两端都不存在 → 失败当成功 | **仅 C 提出**（A、B 未覆盖） |
| 超车参数/模式下发 | 🔴 未闭环：车机侧 `KEY_OVERTAKE_MODE` 从不读取 | **仅 C 提出** |
| 28 号"全部遗留问题 100% 修复" | ❌ **不成立** | 一致 |
| 证据链（提交 / APK / 编译） | 🟢 可复核（A、B 实跑） | A、B 实测；C 无法验证 |

**一句话裁定**：**通信通了，安全语义还没通。** 28 号报告是一次真实有效的修复，但它把"链路打通"当成了"闭环完成"——剩下的是"哨兵值 99.0 代表安全还是未知"这类语义定义问题，以及"车机按下撤销后 C3 是否真的收手"这类端到端闭环问题。

---

## 二、三份报告交叉一致性矩阵

图例：✔ 明确指出 ｜ ◐ 提及但未列为独立项 ｜ ✗ 未覆盖

| 缺陷（本文主索引号） | A | B | C | 裁定 |
| :--- | :---: | :---: | :---: | :--- |
| **M-01** 端口同向冲突 | ✔ 已闭环 | ✔ 已闭环 | ✔ 已闭环 | ✅ 已修（`amap_navi.py:200-201` + `CarrotUdpClient.kt:31-32` 交叉成立） |
| **M-02** 探针回包自指（填车机 IP） | ✔ 已闭环（表述略夸大） | ✔ 已闭环 | ✔ 已闭环 | ✅ 已修（C3 `c3_ip` + 车机优先物理源 IP，双重防护） |
| **M-03** 左后速度用左前估计器 | ✔ 已闭环 | ✔ 已闭环 | ✔ 已闭环 | ✅ 已修（`amap_navi.py:1166`） |
| **M-04** 量纲 mm/m 与符号 | ✔ 已闭环（边界瑕疵） | ✔ 已落盘（潜伏缺陷） | ◐ 判为"前提错误+新 fail-open" | 🟠 已落盘但有 2 处边界缺陷（见 M-11/M-12） |
| **M-05** 门禁困在 0.2 s 计数器（B-04） | ✔ 未修 | ✗ | ✔ 未修 | 🔴 **未修**（`desire_helper.py:920` 仍在 `if carrot_lane_change_count > 0` 内） |
| **M-06** 执行期复检 fail-open + 权限窗（B-05/N-1/U-03） | ✔ 未闭环 | ✔ fail-open | ✔ fail-open + 350 ms 窗 | 🔴 **未闭环**（三份一致，见 §三.1） |
| **M-07** 雷达缺失/无目标不可区分（F-02 / F-29-01） | ✔ Critical | ✔ Major | ✔ 未修 | 🔴 **未修**（"消息失活才阻断"被 `always_run` 的发布者废掉） |
| **M-08** `CANCEL_LANE_CHANGE` 无消费者（C-08） | ◐ 未单列 | ✔ Major | ✔ Major | 🔴 未修（`carrot_serv.py:354-360` 命令表仅 `DETECT`；`desire_helper:507` 只认 LANECHANGE/OVERTAKE） |
| **M-09** `SPEED_LIMIT` 无消费者（F-29-03） | ✗ | ✔ Major | ◐ | 🔴 未修（同上命令表；UI 却显示已同步） |
| **M-10** 序号门控致车机重启后指令锁死（F-29-05） | ✗ | ✔ Minor | ✗ | 🔴 **真实缺陷，漏检于 A/C**（见 §三.2） |
| **M-11** `parse(JSONObject)` 默认 999.0 → 0.999 m → 永久阻断（F-29-07） | ✗ | ✔ Minor | ✗ | 🔴 **真实缺陷，漏检于 A/C**（见 §三.3） |
| **M-12** `parseDistanceMeter` 100 阈值双向反例 | ◐ O-01（米制>100 误除） | ◐ F-29-08 | ✔（mm≤100 误放行） | 🟠 两向都有反例；风险取决于协议单位是否固定 |
| **M-13** 重放包仍可改写 `overtake_mode`（C-09） | ✗ | ✔ Minor | ✔ Minor | 🔴 未修（`_update_command` 赋值在序号门控之外） |
| **M-14** 变道完成反馈 `atc_state` 缺失 → 失败当成功（H-06） | ✗ | ✗ | ✔ Major | 🔴 **真实缺陷，漏检于 A/B**（见 §三.4） |
| **M-15** 超车模式/参数在车机侧无出口（H-02） | ✗ | ✗ | ✔ Major | 🔴 **真实缺陷，漏检于 A/B** |
| **M-16** 验收手册第 2 步被白名单丢弃（O-04/F-29-09） | ✔ | ✔ | ✗ | 🟠 文档缺陷，漏检于 C（`app_ip` 已设时 127.0.0.1 被 `_update_command` 直接 return） |
| **M-17** capnp 生成物未重生成（8 word） | ✗ | ✗ | ✔ Major | 🔴 未修（`cereal/gen/cpp/custom.capnp.h:70` 仍 `8, 0`） |
| **M-18** 遥测三份重复投递 + 缺 TTC/`atc_state` 字段（C-04） | ✗ | ✗ | ✔ Minor | 🔴 未修（`amap_navi.py:1619-1622`） |
| **M-19** 清理线程无 try/except（C-01b） | ✗ | ✗ | ✔ Minor | 🔴 未修 |
| **M-20** 车机实时性：决策在收包协程 / HUD 20-50Hz 全量刷新（H-03/H-05） | ✗ | ✗ | ✔ Major | 🔴 未修（与"零 GC / 3.5MB"文档主张仍冲突） |
| **M-21** 实机类证据不可核验（PSS 15.5 MB / adb 设备号） | ✔ | ✔ | ✔ | ⚪ 需现场复现 |
| **M-22** release APK 非标准 Gradle 产物路径（O-03） | ✔ | ✗ | ✗ | ⚪ 需确认打包链路 |
| **M-23** 文档"全部 100% 修复"措辞失真（F-29-10/D-05） | ✔ | ✔ | ✔ | ⚪ 必须改写 |

**统计（主索引 23 项）**：🟢 已闭环 **3**（M-01/02/03）；🟠 部分或存在边界缺陷 **3**（M-04/M-12/M-16）；🔴 未闭环 **14**；⚪ 文档/证据 **3**。

---

## 三、分歧裁定（逐条以代码裁决）

### 3.1 M-06：执行期复检到底"通过"还是"未通过"

**B 判 🟡「通过（正常雷达工况）」；A、C 判 fail-open、未闭环。裁定：A、C 正确。**

```python
# C3:selfdrive/controls/lib/desire_helper.py:1246-1252
_alive = self.sm.alive['amapNavi']
_ttc = amapNavi.lidarBehindVdistTime if _alive else 0.0
_thr = {0: 1.8, 1: 2.5, 2: 3.5}.get(getattr(amapNavi, 'overtakeMode', 1), 2.5)
if (0.0 < _ttc < _thr) and self.lane_change_ll_prob > 0.3:
```

两条独立缺陷，B 只承认了第一条：

1. `_alive == False → _ttc = 0.0`，而判据要求 `0.0 < _ttc` → **不中止**。同一文件 `:930` 的触发段门禁写的却是 `behind_ttc <= 0.0 → 阻断`。**同一安全函数、两处相反的失效策略**——这是工程上最难辩护的一类不一致。
2. `lane_change_ll_prob > 0.3`：`ll_prob` 自 1.0 起以 `2*DT_MDL = 0.1/帧` 衰减，`>0.3` 仅前 **7 帧 = 350 ms** 成立；而 `laneChangeStarting` 通常持续 1~3 s。**即真正开始横向移动后（后车加速逼近的典型时刻）已无中止权**，与 28 号"毫秒级持续复检"的表述不符。

### 3.2 M-10：车机重启后指令锁死（A、C 漏检）

```python
# C3:amap_navi.py:1008-1010
if idx is not None and idx > self.shared_data.cmd_index:
    self.shared_data.cmd_index = idx        # 只在此处自增
# C3:carrot_man.py:342
if self.shared_cmd_index_last != self.amap_navi.shared_data.cmd_index:   # 不变则不下发
```

```kotlin
// HU:CarrotUdpClient.kt:41
private val sequenceId = AtomicInteger(1)   // 进程内计数，App 重启归 1
```

**机理**：车机 App 重启后 `seq` 从 1 重新开始，而 C3 的 `cmd_index` 保持历史最大值（如 137）。`idx > cmd_index` 永不成立 → `cmd_index` 不变 → `carrot_man` 永不转发 → **所有变道按钮静默失效**，且无任何报错。这是"现场最难查"的一类缺陷：现象是"重启后按键没反应，重启 C3 才好"。
**修复**：`amap_navi.py` 在 `app_ip` 变化或 >5 s 无指令时 `self.shared_data.cmd_index = -1`；或改用"会话号 + 序号"双键。

### 3.3 M-11：`parse(JSONObject)` 默认值会造成永久阻断（A、C 漏检）

```kotlin
// HU:CarrotTelemetryParser.kt:123-124（JSONObject 重载）
leftRearDistance  = parseDistanceMeter(json.optDouble("lb_drel", 999.0).toFloat()),
rightRearDistance = parseDistanceMeter(json.optDouble("rb_drel", 999.0).toFloat()),
```

`999.0 > 100` → `999/1000 = 0.999 m` → `LateralSafetyEvaluator` 判 `0.999 < max(10, v·2.0)` → **永久阻断变道**。当前该重载未被调用（`RelayEngine` 只走字符串重载），属**潜伏缺陷**：任何人日后为日志/调试改用它，变道功能立刻"莫名其妙全禁"。
**修复**：默认值改 `-999999.0`（与流式重载一致）。

### 3.4 M-14：变道失败被结算为成功（A、B 漏检）

```kotlin
// HU:OvertakeStateMachine.kt:243-247
if (now - stateSinceMs > settings.executeTimeoutMs) {
    state = OvertakeState.FINISHING
    message = "变道执行超时 ${settings.executeTimeoutMs}ms，按完成结算"
}
```

而 C3 遥测 JSON **从不包含 `atc_state`**（`make_navi_message` 无该键），车机却在 `:237` 等 `car.atcState == 3`。结论：**每一次变道都必然走超时分支**，随后 `handleFinishing()` 播报"变道完成"并进入冷却。**失败、卡住、被阻断的变道，全部被记为成功。** 这直接击穿"变道结果可信度"，也是 M-08（撤销无效）之外的第二个"闭环缺失"。

### 3.5 M-04 / M-12：量纲修复的两种反例，谁的判定更准

三份报告各自抓到一个方向的反例，**三者都对，但严重度不同**：

| 输入 | 结果 | 风险 |
| :--- | :--- | :--- |
| mm 值 `\|v\| ≤ 100`（车距 ≤ 10 cm） | 被当米 → 80~100 m → **放行** | 极端贴近，实际由 `lidar_lbblind` 兜底；C 提 |
| 米值 `> 100`（如 120.5 m） | 被 `/1000` → 0.12 m → **误阻断** | 保守侧，不危险；A/B 提 |
| JSONObject 缺键默认 999 | → 0.999 m → **永久阻断** | 潜伏致命；B 提 |

**裁定**：根治办法不是调阈值，而是**在协议层固定单位**（建议统一米制，C3 侧 `/1000` 后输出），并删除启发式。

---

## 四、对我方（C）报告的自我更正

为保证主索引可信，主动列出 C 报告的漏检与偏差：

| # | 内容 | 性质 |
| :--- | :--- | :--- |
| 1 | **漏检 M-10**（车机重启后序号锁死） | 漏检 — 我只读了 `_update_command` 与 `carrot_man` 的转发条件，未把"车机进程重启"这一时序纳入推演 |
| 2 | **漏检 M-11**（JSONObject 重载默认 999 → 0.999 m） | 漏检 — 我核对了字符串重载，未核对第二个重载的默认值语义 |
| 3 | **漏检 M-16**（验收命令被白名单丢弃） | 漏检 — 我核对了白名单存在，未把它与 28 号给的验收命令对撞 |
| 4 | 对 P-5 的表述过重 | 偏差 — 我以"默认值应在协议层固定"的正确结论，包装了对"适配式阈值"的整体否定；实际上 C3 单位是毫米这一点，A/B 的读法（已落盘、有边界瑕疵）更公允 |
| 5 | 对 P-2 的评价 | 偏差 — A 的 O-05 更准确：**车机侧优先物理源 IP 之后**，C3 的 `c3_ip` 计算仅在源 IP 为 127.0.0.1 时才被采用，属"双保险"而非"关键修复" |

同时，C 报告独有且经本轮复核成立的项：**M-05**（0.2 s 计数器未解除）、**M-14**（失败当成功）、**M-15**（车机侧参数无出口）、**M-17**（capnp 生成物 8 word）、**M-18/M-19/M-20**。

三份报告互补关系：**A 强在证据链与流程根因，B 强在逐项实测与潜伏缺陷，C 强在端到端语义闭环（撤销/结果/参数）。**

---

## 五、唯一主索引（Single Source of Truth）

> 规则：**编号不复用、不重排**；任何后续"闭环"声明必须逐条引用本表编号并给出修复提交哈希。状态取值：`FIXED` / `PARTIAL` / `OPEN` / `DOC-ONLY` / `UNVERIFIABLE`。

### 5.1 阻断级（决定"是否可上车"）

| 编号 | 缺陷 | 端 | 位置 | 级别 | 状态 | 备注 |
| :---: | :--- | :---: | :--- | :---: | :---: | :--- |
| M-01 | 端口同向冲突 | 协同 | `amap_navi.py:200-201` / `CarrotUdpClient.kt:31-32` | Critical | **FIXED** @606b16c | 交叉成立 |
| M-02 | 探针回包自指 | 协同 | `amap_navi.py:617-626` / `UdpDeviceDiscovery.kt:124-133` | Critical | **FIXED** @606b16c | 双保险 |
| M-03 | 左后速度用左前估计器 | C3 | `amap_navi.py:1166` | Critical | **FIXED** @606b16c | — |
| M-05 | 门禁困在 0.2 s 计数器 | C3 | `desire_helper.py:920` | Critical | **OPEN** | 需脱离计数器或改发 OVERTAKE |
| M-06 | 执行期复检 fail-open + 350 ms 窗 | C3 | `desire_helper.py:1246-1252` | Critical | **PARTIAL** @606b16c | 见 §三.1 补丁 |
| M-07 | 雷达缺失与无目标不可区分 | C3 | `amap_navi.py:295-305` | Major | **OPEN** | 建议加 `lidarTtcValid` @17 |
| M-08 | CANCEL 无消费者 | C3 | `carrot_serv.py:354-360` / `desire_helper.py:507` | Major | **OPEN** | 撤销是空操作 |
| M-14 | 失败变道被结算为成功 | 车机 | `OvertakeStateMachine.kt:237-247` | Major | **OPEN** | C3 也不发 `atc_state` |

### 5.2 功能与一致性

| 编号 | 缺陷 | 端 | 位置 | 级别 | 状态 |
| :---: | :--- | :---: | :--- | :---: | :---: |
| M-04 | 净空量纲（主修复） | 车机 | `CarrotTelemetryParser.kt:48-54` | Critical | **PARTIAL**（边界见 M-11/M-12） |
| M-09 | SPEED_LIMIT 无消费者 | C3 | `carrot_serv.py:354-360` | Major | **OPEN** |
| M-10 | 车机重启后序号锁死 | 协同 | `amap_navi.py:1008` / `CarrotUdpClient.kt:41` | Major | **OPEN** |
| M-11 | JSONObject 重载默认 999 → 0.999 m | 车机 | `CarrotTelemetryParser.kt:123-124` | Major(潜伏) | **OPEN** |
| M-12 | 100 阈值双向反例 | 车机 | `CarrotTelemetryParser.kt:56-62` | Minor | **OPEN** |
| M-13 | 重放可改写 `overtake_mode` | C3 | `amap_navi.py:1009-1020` | Minor | **OPEN** |
| M-15 | 超车模式/参数在车机侧无出口 | 车机 | `UserSettingsRepository.kt:130-137` | Major | **OPEN** |
| M-17 | capnp 生成物未重生成 | C3 | `cereal/gen/cpp/custom.capnp.h:70` | Major | **OPEN** |
| M-18 | 遥测三份重复 + 缺字段 | C3 | `amap_navi.py:1619-1622` | Minor | **OPEN** |
| M-19 | 清理线程无 try/except | C3 | `amap_navi.py:1509-1540` | Minor | **OPEN** |
| M-20 | 车机实时性（决策/渲染） | 车机 | `RelayEngine.kt:152` / `MainActivity.kt:245+` | Major | **OPEN** |

### 5.3 文档与证据

| 编号 | 内容 | 状态 |
| :---: | :--- | :---: |
| M-16 | 验收手册第 2 步被白名单丢弃 | **OPEN**（改发真实车机 IP，或先清空 `app_ip`） |
| M-21 | 实机证据（PSS 15.5 MB / adb 设备号） | **UNVERIFIABLE**（需现场 `dumpsys`） |
| M-22 | release APK 非标准 Gradle 产物路径 | **UNVERIFIABLE**（`app/build/outputs/apk` 仅 `debug/`） |
| M-23 | "全部遗留问题 100% 修复"措辞失真 | **DOC-ONLY**（建议改为"5 项阻断闭环 + 14 项待处理"） |

---

## 六、最小补齐路径（按风险排序，一次提交可完成 1~5）

1. **M-07**（最高风险）：`ttc_list` 为空时不要用 `99.0` 表达"安全"，改用有效性位或雷达存在标志：
   ```python
   lidar_present = bool(self.shared_data.lidar_l or self.shared_data.lidar_r)
   msg.amapNavi.lidarBehindVdistTime = float(ttc if (lidar_present and ttc_list) else 0.0)
   ```
   （消费端 `behind_ttc <= 0.0 → 阻断` 的语义此时才真正生效）
2. **M-06**：`if _too_close and ll_prob > 0.3`，其中 `_too_close = (not _alive) or (_ttc <= 0.0) or (_ttc < _thr)`；若保留 `ll_prob` 限制，则 `ll_prob <= 0.3` 时禁止发新指令并播报。
3. **M-08 / M-09**：`carrot_serv._update_cmd` 的 `command_handlers` 增加 `"CANCEL"` 与 `"SPEED_LIMIT"`；`desire_helper` 增加 `CANCEL` 分支直接置 `off`。
4. **M-10**：`app_ip` 变化或 5 s 无指令时 `cmd_index = -1`。
5. **M-11**：`parse(JSONObject)` 默认值改 `-999999.0`。
6. **M-14**：超时分支改"撤销 + 报错 + 长冷却"（不得 `FINISHING`）；C3 侧补发 `atc_state`。
7. **M-15 / M-17 / M-05**：参数全字段绑定 + `KEY_OVERTAKE_MODE` 随指令下发；`scons` 重生成 capnp 并提交；门禁移出计数器。
8. **M-18 / M-19 / M-20**：去重复投递、补 try/except、决策移出收包协程 + HUD 10 Hz 节流。

---

## 七、流程改进（比任何单点缺陷都重要）

三份报告各自独立编号，直接导致 **28 号把"F-02（TTC fail-open）"整套漏掉**——它在 B-01~B-05 体系里没有对应编号。这是本项目连续三轮出现"上轮点名的致命项在下一轮静默消失"的根因。建议立即生效四条规则：

1. **唯一主索引**：以本文件 §五 为唯一编号源，任何新发现追加而非重排；任何"闭环"声明必须逐条引用编号 + 修复提交哈希。
2. **禁止绝对化措辞**：不允许再出现"100% 闭环 / 全部修复 / 完全具备上车条件"；改为"已闭环 N 项（附编号）/ 待处理 M 项（附编号）"。
3. **负向测试为准入条件**：变道类功能必须证明"该阻断时确实阻断"（雷达断流 / 负距离 / 并排车 / 消息缺失 四类反例），仅正向跑通不算通过。
4. **证据分层标注**：`代码级`（可 file:line 复核）／`命令级`（附可重放命令 + 输出）／`实机级`（附设备序列号 + 抓图），三者不得混写在同一结论里。

---

## 八、最终放行建议

| 阶段 | 前置条件 |
| :--- | :--- |
| **台架联调**（现在即可） | 无需再改代码；按 M-16 修正后的命令验证 4210 握手 / 7706 遥测 / 7705 指令三向 |
| **封闭场地低速变道** | 修完 M-05 / M-06 / M-07 / M-08 / M-14 |
| **高速实车** | 再加修 M-09 / M-10 / M-11 / M-15 / M-17 / M-18 / M-20 |

**专家寄语**：这一轮的工程执行值得肯定——五项阻断全部真实落地，证据链也经得起复核，三份独立核验在"链路已通"上罕见地完全一致。剩下的分歧已经不在代码事实，而在**验收口径**：是"改动落盘了"还是"端到端真的闭环了"。`CANCEL` 按下去 C3 不动、变道失败显示成功、雷达掉线门禁消失——这三件事只要有一件没被证明，就不叫闭环。

---

**本文为独立裁定意见，未修改任何工程文件。**
**关联**：`24`（首轮双端审计）、`26`（25 号整改核验）、`27`（结论汇总）、`28`（被核验交付报告）、`29`×3（三份独立核验）。
