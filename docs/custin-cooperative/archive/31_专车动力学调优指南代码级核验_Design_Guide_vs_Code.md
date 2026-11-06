# 31《专车动力学深度调优设计指南》代码级核验（Design Guide vs Code）

> **被核验文档**：`21_北京现代库斯途专车动力学深度调优与C3专属优化设计指南.md`
> **核验基线**：`E:\code\openpilot-ck89757`（`cp-custo-amap`，606b16c）工作区真实源码
> **核验方式**：指南中每一段"实施代码 / 配置 / 文件路径"↔ 真实源码逐行比对；凡指南以"已落地/可复制"口吻给出的代码，一律视为可执行补丁来验证
> **取证限制**：本会话 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`），未能执行 grep/编译/实车测量；结论基于源码阅读与符号轮廓（`module_report`），`file:line` 均可复核。**文中"1.65W / 39℃ / 70℃"等实测数字不采信**。
> **编号衔接**：延续 `30_..._Master_Adjudication.md` 的主索引（M-xx 不复用），本文新增项从 **M-24** 起编号。
> **核验日期**：2026-11-03

---

## 一、核验结论

### 🟠 [NEEDS REVISION] —— 车型分析扎实，但"实施部分"有 4 处与代码不符、1 处机制选错对象

指南第一部分（库斯途物理特征：3.055 m 轴距、1.75 m 级车高、扭力梁、8AT 大齿比、500 kbps C-CAN、`0x340`/`0x485`）与 openpilot 侧的实际接口是**对得上**的，工程判断方向（长轴距→力矩模型、高重心→平顺变道、8AT→起步扭矩、仪表→LFAHDA、夏日→功耗）也合理。作为"设计意图文档"它有价值。

问题集中在第二至六节：**6 个"优化方向"里**

| 分类 | 数量 | 明细 |
| :--- | :---: | :--- |
| 已在上游/全局实现，非本项目定制 | 2 | 8AT 起步 `startAccel=1.0`、Offroad 大核下线 `set_power_save()` |
| 已落地但指南描述与代码不符 | 1 | NNFF 映射（`substitute.toml:43` 已有，但归属与生效前提未说明） |
| **机制选错对象**（改错变量，达不到所述效果） | 1 | 5.0 s 平缓变道用 `lane_change_ll_prob` 衰减实现 |
| **仅提案、代码中不存在**（且给出的标识符不存在） | 2 | 前馈偏航角补偿 `τ_lead=0.15 s`、红灯锁零 `actual_stop_distance = 0.0` |
| 给出的实施代码是**伪代码**，照抄会报错 | 2 | `create_lfahda_mfc()` 签名与信号名不符；`LANE_CHANGE_STEP_CUSTO` 不存在 |

**最要紧的一句**：指南把"改 `lane_change_ll_prob` 的衰减步长"当成"把变道时间从 3.5 s 拉长到 5.0 s"的手段 —— 这个变量**不控制轨迹**，改它只会推迟"判定变道完成"的时刻，反而可能延长车辆处于 `laneChangeStarting` 的驻留时间。真正该动的是 `lateral_planner.py` 的 MPC 代价权重（`LATERAL_JERK_COST` / `LATERAL_ACCEL_COST`）与 `lane_planner_2` 的目标轨迹。

---

## 二、六个优化方向逐项核验

| # | 指南声称 | 代码现状（真实） | 判定 |
| :---: | :--- | :--- | :---: |
| 2.2 | `substitute.toml` 加 `"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"` | `opendbc_repo/opendbc/car/torque_data/substitute.toml:43` **已有该行**（606b16c 加入） | 🟢 已落地 |
| 2.3 | `lateral_planner.py` 增 `τ_lead = 0.15 s` 前馈超前补偿 `δ_lead = δ + τ·(dκ/dt)·v` | `selfdrive/controls/lib/lateral_planner.py` 全文仅 4 个方法：`__init__ / reset_mpc / update / publish`，**无任何 lead/tau/超前补偿实现**；轨迹由 `LateralMpc` 生成 | 🔴 **未实现（提案）** |
| 3.2 | `LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL`，把变道放宽到 4.8~5.2 s | `desire_helper.py:1241` 仍为 `max(self.lane_change_ll_prob - 2 * DT_MDL, 0.0)`；**`LANE_CHANGE_STEP_CUSTO` 标识符全仓不存在** | 🔴 **未实现；且机制错误（见 §三 E-1）** |
| 3.3 | 横向加速度 ≤0.08g、jerk ≤0.05g·s⁻¹ | `lateral_planner.py:20-25`：`LATERAL_ACCEL_COST = 0.0`、`LATERAL_JERK_COST = 0.04`、`STEERING_RATE_COST = 700.0`。这些才是真正影响平顺性的旋钮，指南未提及 | 🟠 **可调但未落到正确位置** |
| 4.2 | `if candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN: ret.startAccel = 1.0`（称"原版默认 1.5~2.0"） | `hyundai/interface.py:202` 已是**无条件** `ret.startAccel = 1.0`（全 Hyundai 通用），且上游默认就是 1.0。指南的"专属分支"无必要；"原版 1.5~2.0"不成立 | 🟠 **描述失真（非定制）** |
| 4.3 | `carrot_functions.py` 中"强制 `actual_stop_distance = 0.0`" | 该文件真实标识符为 `update_stop_dist(stop_x)`、`xStopFilter`、`stopSign`、`TrafficState.red/green`（`:234-283`）；**`actual_stop_distance` 不存在**；现逻辑由视觉 `model_x/model_v` 判 `stopSign`，**与高德红绿灯倒计时无任何耦合** | 🔴 **未实现 + 标识符不存在** |
| 5.1 | `create_lfahda_mfc(packer, enabled, hda_set_speed)`，信号 `HDA_SysState` / `HDA_SetSpeed` | `hyundaican.py:119-131` 实际签名为 **`create_lfahda_mfc(packer, CC, blinking_signal)`**；真实信号为 `LFA_Icon_State / HDA_Icon_State / HDA_VSetReq / HDA_USM / HDA_Icon_Wheel`（**无 `HDA_SysState`、无 `HDA_SetSpeed`**）；`HDA_VSetReq` 被硬置 0 | 🔴 **伪代码，照抄即报错** |
| 6.2 | 在 `system/hardware/tici/hardware.py` 固化"离线 4 个大核 + `force_clk_on=0` / `force_rail_on=0` + 1.65W" | `hardware.py:357-385` 的 **`set_power_save(powersave_enabled)`** 已实现：`for i in range(4,8)` 写 `cpu{i}/online=0` + governor 切换 + 放大器关断 + `affine_irq(7,"kgsl-3d0")`。**但**：① 是上游既有能力，由 thermald 在 offroad 调用，非本项目定制；② **无 `force_clk_on` / `force_rail_on`** 任何代码；③ 1.65 W / 39℃ 无代码依据 | 🟠 **描述失真（非定制）+ 2 处代码不存在** |

---

## 三、5 个技术性错误（按影响排序）

### E-1（Major）`lane_change_ll_prob` 不是变道时长控制器 —— 改它达不到 5.0 s

```python
# desire_helper.py:1239-1241（真实代码）
elif self.lane_change_state == LaneChangeState.laneChangeStarting:
    self.lane_change_ll_prob = max(self.lane_change_ll_prob - 2 * DT_MDL, 0.0)
    ...
    if lane_change_prob < 0.02 and self.lane_change_ll_prob < 0.01:      # :1254
        self.lane_change_state = LaneChangeState.laneChangeFinishing
```

`lane_change_ll_prob` 在这套代码里**只作为"进入 Finishing 的完成判据"的门限计数**（需与模型的 `lane_change_prob < 0.02` 同时满足）。真正的横向轨迹由 `lateral_planner.py` 的 `LateralMpc` 依据 `lane_planner_2.LanePlanner` 给出的车道目标生成（`lateral_planner.py:1-31, 83-242`）。

因此：
- 把步长从 `2 * DT_MDL`（0.5 s 走完 0→0.01）改成 `1.2 * DT_MDL`（约 0.83 s），**只会把"判定完成"的时刻推后**，车辆实际横移时间由 MPC/车道目标决定，**不会从 3.5 s 变成 5.0 s**；
- 副作用是状态机在 `laneChangeStarting` 驻留更久，`laneChange_ll_prob` 相关的完成判据更晚满足 → **可能拉长"已打灯、尚未判定完成"的窗口**，与"更平顺、更安全"的意图相反。

**正确做法（三选一或组合）**：
1. `lateral_planner.py:20-25` 调整 `LATERAL_JERK_COST` / `LATERAL_ACCEL_COST`（这是 MPC 内对横向 jerk/加速度的直接惩罚项）；
2. `lane_planner_2.LanePlanner` 的变道目标轨迹改为"多帧渐进"（把目标车道偏移量在 N 帧内线性/余弦插值）；
3. 若确需硬约束完成时间，用 `LANE_CHANGE_TIME_MAX`（当前 10 s，仅超时上限）配合自定义状态机计时，而不是复用 `ll_prob`。

### E-2（Major）`create_lfahda_mfc` 的调用契约与信号名不符 —— 照抄会崩

```python
# 真实签名（hyundaican.py:119）
def create_lfahda_mfc(packer, CC, blinking_signal):
  activeCarrot = CC.hudControl.activeCarrot
  values = {
    "LFA_Icon_State": 2 if CC.latActive else 1 if CC.enabled else 0,
    "HDA_Icon_State": 0 if activeCarrot == 3 and blinking_signal else 2 if activeCarrot >= 1 else 0,
    "HDA_VSetReq": 0,
    "HDA_USM": 2,
    "HDA_Icon_Wheel": 1 if CC.latActive else 0,
  }
```

指南给的 `(packer, enabled, hda_set_speed)` + `HDA_SysState` + `HDA_SetSpeed` **在 DBC 中不存在**，`packer.make_can_msg` 会因未知信号抛错。另外指南说"由 Panda 硬件 20Hz 发送"——实际发送节拍由 `carcontroller` 决定，且**仅当指纹含 `0x485`（`interface.py:216` 置 `HyundaiFlags.SEND_LFA`）时才发送**；无该报文的车型发出去也不会点亮。
**正确做法**：如需在仪表显示设定车速，应改 `"HDA_VSetReq": set_speed`（并确认 DBC 支持该信号缩放），而不是新增不存在的键。

### E-3（Major）`actual_stop_distance` 不存在；红灯锁零当前是"视觉判定"，与高德无耦合

```python
# carrot_functions.py:234-237（真实代码）
def update_stop_dist(self, stop_x):
    stop_x = self.xStopFilter.process(stop_x, median=True)
    stop_x = self.xStopFilter2.process(stop_x)
    return stop_x
```

`check_model_stopping()`（`:239-283`）用 `model_x / model_v` 判 `stopSign`，再积分 `stopSignCount` 决定 `TrafficState.red`。**全流程没有任何来自车机/高德的输入**，也没有 `actual_stop_distance` 这个量。
**正确做法**：若要"红灯期间锁零"，需要先有数据通道（`carrotMan` 目前不含高德红绿灯字段），再在 `check_model_stopping` 里用该状态覆盖 `stopSign`，并把 `stop_x` 钳到 0；仅改一行赋值是做不到的。

### E-4（Minor）`startAccel` 的语义被误解

`ret.startAccel` 是"从静止起步瞬间沿用的加速度基准"（配合 `vEgoStarting`），**不是加速度上限**，也不是 8AT 换挡冲击的直接旋钮。8AT 1-2 挡顿挫在 openpilot 侧的对应旋钮是 `longitudinalTuning`（kp/kf）与 `create_acc_commands` 的 `jerk` 参数（`hyundaican.py:232-327`），以及 `LongitudinalPersonality` 的加速度包络。指南把 `startAccel=1.0` 解释成"起步请求加速度呈抛物线温和爬升、彻底告别顿挫"，属**因果错配**。

### E-5（Minor）Offroad 大核下线是上游能力，且 GPU 部分代码不存在

`set_power_save()` 确实做 4 个大核 offline（`hardware.py:366-368`），但：① 触发方是 **thermald**（offroad 时调用），不是"在 hardware.py 里固化策略"；② **没有 `force_clk_on` / `force_rail_on`** 这两项 GPU 时钟/供电轨操作（代码里对 GPU 只做了 `affine_irq(7, "kgsl-3d0")` IRQ 绑核）；③ 1.65 W / 39℃ 为实测值，本轮无法验证。

---

## 四、指南完全没提、但对"库斯途专车调优"最关键的一件事

横向控制的**物理参数入口**不在 NNFF，而在 `CarParams`：

```python
# selfdrive/controls/lib/lateral_planner.py:40-42（真实代码）
self.factor1 = CP.wheelbase - CP.centerToFront
self.factor2 = (CP.centerToFront * CP.mass) / (CP.wheelbase * CP.tireStiffnessRear)
```

即：**轴距、质心到前轴距离、整车质量、后轮侧偏刚度**这四个量直接构造 MPC 的转向动力学模型。指南用大量篇幅论证"3.055 m 轴距 / 1.69~2.2 t 载荷跨度"，却没有指向最该核对的四处 `CarParams`（来自 `opendbc/car/hyundai/values.py` 的车型定义）。

**建议把"专车调优"的第一条改成**：核对并标定 `HYUNDAI_CUSTIN_1ST_GEN` 的 `wheelbase / centerToFront / mass（空载 vs 满载）/ tireStiffnessRear`，并对满载工况做一次 `factor2` 敏感性分析。**权重远高于移植 NNFF**——NNFF 只影响前馈力大小，而 `factor1/factor2` 错会让整个 MPC 的横摆模型失配。

---

## 五、可执行替代方案（替换指南中的伪代码）

### 5.1 平顺变道（替代 E-1 的 `ll_prob` 方案）

```diff
--- a/selfdrive/controls/lib/lateral_planner.py
+++ b/selfdrive/controls/lib/lateral_planner.py
@@
-PATH_COST = 1.0
-LATERAL_MOTION_COST = 0.11
-LATERAL_ACCEL_COST = 0.0
-LATERAL_JERK_COST = 0.04
+PATH_COST = 1.0
+LATERAL_MOTION_COST = 0.11
+LATERAL_ACCEL_COST = 2.0      # 库斯途 MPV：开始惩罚横向加速度（原 0.0 = 不惩罚）
+LATERAL_JERK_COST = 0.20      # 库斯途 MPV：横向 jerk 惩罚 ×5（原 0.04）
 STEERING_RATE_COST = 700.0
```

> ⚠️ 这两个权重会同时影响**车道居中**手感（不仅是变道），必须先在封闭场地做"直道微调 + 大弯"回归，再决定是否只在 `laneChangeState != off` 时切换权重（更安全的做法是运行时按状态切换，而不是全局改常量）。

### 5.2 仪表显示设定车速（替代 E-2）

```diff
--- a/opendbc_repo/opendbc/car/hyundai/hyundaican.py
+++ b/opendbc_repo/opendbc/car/hyundai/hyundaican.py
@@
-    "HDA_VSetReq": 0, #set_speed_in_units if activeCarrot >= 2 else 0,
+    # 需先在 DBC 中确认 HDA_VSetReq 的量纲/缩放；确认后再启用
+    "HDA_VSetReq": (int(CC.hudControl.setSpeed * 0.1) if CC.latActive else 0),
```

> 前置条件：`opendbc/dbc/generator/hyundai/...` 里 `LFAHDA_MFC` 必须有该信号；否则仍是空谈。**先查 DBC，再改代码。**

### 5.3 红灯期间"锁零"（替代 E-3，分三步）

1. **补齐数据通道**：`cereal/custom.capnp` 的 `CarrotMan` 尾插 `trafficLightState @N : Int32;` + `trafficLightSecondsLeft @N+1 : Int32;`（遵守 ordinal 追加规范，且必须重生成生成物——参见主索引 M-17 的教训）。
2. **车机侧下发**：`CarrotUdpClient.sendControlCommand` 已有 `cmd` 通道，新增 `"TRAFFIC_LIGHT"` + `arg="RED,92"`。
3. **C3 侧消费**：`carrot_functions.check_model_stopping()` 中，当 `trafficState == red` 且 `v_ego_kph < 1.0` 时强制 `stopSign = True`，并在 `update_stop_dist()` 返回前将该帧 `stop_x` 钳到 `min(stop_x, 0.0)`。

### 5.4 前馈超前补偿（替代 2.3 的空提案，且不要照抄公式）

指南的 `δ_lead = δ + τ·(dκ/dt)·v_ego` 量纲不闭合（`dκ/dt·v` 是 1/s²，加不到角度上）。若确需超前，正确形式是**对目标曲率做超前**：`κ_cmd = κ_desired + τ·dκ_desired/dt`（τ≈0.15 s），再交给 MPC 的 `path`。且在当前 `LateralMpc` 架构下，更简单的等效手段是对 `LanePlanner` 输出的目标轨迹加时间偏移。**建议本条降级为"待验证的探索项"，不要作为实施项列入清单。**

---

## 六、文档整改清单（照此改即可让指南变成可信的实施依据）

| 编号 | 位置 | 必改内容 |
| :---: | :--- | :--- |
| **M-24** | §3.2 / §7 清单 | 删除 `LANE_CHANGE_STEP_CUSTO` 与"5.0 s"因果表述；改为"通过 MPC 权重与车道目标轨迹实现平顺"，并标注需回归车道居中 |
| **M-25** | §5.1 / §7 清单 | 用真实签名 `create_lfahda_mfc(packer, CC, blinking_signal)` 与真实信号名替换；删除 `HDA_SysState`/`HDA_SetSpeed`；补"仅指纹含 `0x485` 才发送" |
| **M-26** | §4.3 / §7 清单 | 删除 `actual_stop_distance = 0.0`；改为"需先补交通灯数据通道（capnp + UDP + 消费端）"三步 |
| **M-27** | §4.2 | 更正为"`ret.startAccel = 1.0` 已是全局行为（`interface.py:202`），非库斯途专属；8AT 顿挫对应旋钮为 `longitudinalTuning` / jerk 参数" |
| **M-28** | §6.2 | 更正为"上游 `set_power_save()` 既有能力，由 thermald 在 offroad 调用"；删除 `force_clk_on/force_rail_on`；1.65 W/39℃ 标注为待实测 |
| **M-29** | §2.3 | 公式量纲修正为对曲率超前；并明确标注"当前 `lateral_planner.py` 无此实现，属提案" |
| **M-30** | 全文 | 新增一节"**CarParams 标定优先级高于 NNFF**"：`wheelbase / centerToFront / mass / tireStiffnessRear` → `lateral_planner.py:41-42` 的 `factor1/factor2` |

---

## 七、总体评价

这份指南的**前半部分（车型物理与根因分析）质量不错**，方向判断（长轴距→力矩模型、高重心→平顺、8AT→起步、仪表→LFAHDA、高温→功耗）与工程直觉一致；`substitute.toml` 的 NNFF 映射也确实已经落地。

它的**问题不在方向，而在"最后一公里"**：把"设计意图"写成了"实施说明"，其中 4 处代码是伪代码（签名/信号名/标识符不存在），1 处机制选错对象（`ll_prob` 当变道时长），2 处把上游既有能力包装成本项目定制。这类文档最危险的地方不是错误本身，而是**它看起来可以直接复制**——工程师照抄后遇到的不是"效果不佳"，而是运行时异常或"改了没反应"。

建议按 §六 的 M-24~M-30 逐条修正后再作为实施依据；同时把 §四 的 `CarParams` 标定提到所有专车调优之前。

---

**本文为独立核验意见，未修改任何工程文件；所有判定可在上述 `file:line` 复核。**
**主索引衔接**：新增 M-24 ~ M-30（见 §六）；`set_power_save` / NNFF 相关的既有序号见 `30_..._Master_Adjudication.md` §五（M-15、M-17）。
