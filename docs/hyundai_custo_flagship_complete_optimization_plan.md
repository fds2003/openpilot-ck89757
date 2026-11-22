# 北京现代库斯途 2.0T 旗舰版专车智驾深度优化全景方案与工程落地规范

> **工程仓库**：`E:\code\custo-new`  
> **基础基线**：`sunnypilot v0.9.8.0 release` (`commit 167ef31`)  
> **分支名称**：`custo-new`  
> **目标车型**：北京现代库斯途 2021~2024 款 **2.0T 顶配旗舰版（Smartstream G4NN 2.0T 380T GDi + 8AT）**  
> **规范依据**：深度整合《21号专车动力学指南》、《31号独立代码核验报告》及《34号TDD闭环交付报告》

---

## 目录索引

- [一、 车型机械与动力学物理基准真值](#一-车型机械与动力学物理基准真值)
- [二、 现存代码缺陷与独立核验避坑指南](#二-现存代码缺陷与独立核验避坑指南)
- [三、 五大核心专车优化模块设计与代码规范](#三-五大核心专车优化模块设计与代码规范)
  - [3.1 模块一：专车平台定义与大车神经网络力矩映射 (NNFF)](#31-模块一专车平台定义与大车神经网络力矩映射-nnff)
  - [3.2 模块二：8AT 传动防顿挫与超长轴距偏航时延补偿](#32-模块二8at-传动防顿挫与超长轴距偏航时延补偿)
  - [3.3 模块三：MPV 静音座舱与夏季前风挡极端暴晒三段式温控](#33-模块三mpv-静音座舱与夏季前风挡极端暴晒三段式温控)
  - [3.4 模块四：家庭场景友好型驾驶员状态监控 (Family DM) 策略](#34-模块四家庭场景友好型驾驶员状态监控-family-dm-策略)
  - [3.5 模块五：改装硬件兼容与系统告警链治理](#35-模块五改装硬件兼容与系统告警链治理)
- [四、 敏感配置隔离与国内云服务治理](#四-敏感配置隔离与国内云服务治理)
- [五、 TDD 自动化测试验证矩阵](#五-tdd-自动化测试验证矩阵)
- [六、 分步落地执行路线图与实车点火 Checklist](#六-分步落地执行路线图与实车点火checklist)

---

## 一、 车型机械与动力学物理基准真值

现代库斯途（Hyundai Custo / Custin 1st Gen）基于现代起亚第三代 **i-GMP (N3) 平台**，其动力学响应与通用紧凑型轿车（如伊兰特）存在本质的物理级差异：

```
                      【现代库斯途整车动力学几何图示】
  ◄─────────────────────────── 全长 4,950 mm ───────────────────────────►
 ┌────────────────────────────────────────────────────────────────────────┐
 │   引擎盖 (2.0T G4NN)   │  前排驾驶舱  │   二排航空座椅   │  三排与后备箱 │
 └───────────┬────────────┴──────┬───────┴──────────┬───────┴──────┬──────┘
             │                   │                  │              │
        前轮转向轴               │             质心 (CG)        后轮轴
       (前麦弗逊独立)            │                              (后扭力梁)
             ▲                   │                  ▲              ▲
             │                   │                  │              │
             └───────────────────┼──────────────────┴──────────────┘
                         超长轴距: 3,055 mm (大轿车标准为 2,750mm)
                         整备质量: 1,754 kg (2.0T 顶配旗舰版实重)
                         原厂实测转向比: 17.0 (大车转向比)
```

### 1.1 关键物理与控制参数对照
- **车型代号**：`HYUNDAI_CUSTIN_1ST_GEN`（兼容国际命名 Custin 与国内 Custo）；
- **车身尺寸**：长 4950mm $\times$ 宽 1850mm $\times$ 高 1734mm；
- **轴距（Wheelbase）**：**`3.055 m`**（3055mm，处于 openpilot 适配车型第一梯队）；
- **整备质量（Mass）**：**`1754 kg`**（2.0T 旗舰版实重，满载可达 2.2 吨）；
- **转向比（Steer Ratio）**：**`17.0`**（原厂 MDPS 标定，非小车 13~15）；
- **底盘与悬挂**：前麦弗逊独立悬挂 + 后扭力梁非独立悬挂；侧倾中心偏高，横向加加速度（Jerk）过大极易引起后排甩尾感与晕车；
- **动力传动系统**：Smartstream 2.0T 涡轮增压发动机（380T）+ **8AT 变速箱**；1 挡齿比达 4.8，2 挡齿比落差近 2.0，配大容量液力变矩器；
- **车载网络与 ADAS**：500kbps 高速 C-CAN（非 CAN-FD），线束接口 `CarHarness.hyundai_k`，仪表盘支持 `0x485 LFAHDA_MFC` 20Hz 点亮。

---

## 二、 现存代码缺陷与独立核验避坑指南

结合对现有 7 个提交的深入分析与《31号独立代码核验报告》，明确必须纠正的误区与代码异味：

| 模块 | 当前 custo-new 代码现状 | 真实隐患 / 独立核验避坑裁决 | 正确优化决策 |
| :--- | :--- | :--- | :--- |
| **车型识别** | 缺失 `HYUNDAI_CUSTIN_1ST_GEN` 定义，使用通用逻辑 | 导致几何计算、偏航惯性矩失真，无法做专车条件分支 | 显式注册库斯途专车平台，精准录入物理参数 |
| **8AT 起步** | 借用 `Params().get_bool("LkasToggle")` 切换 1.0/1.6 | 严重破坏参数职责，跨车型逻辑混淆 | 在专车分支中固化 `ret.startAccel = 1.0`，彻底移除借壳参数 |
| **横向转向** | 缺乏力矩模型，套用小车参数，高速易“画龙” | 31号证实：全仓无 `tau_lead=0.15`，真实落地点是 `steerActuatorDelay` | `substitute.toml` 映射帕里斯帝大车 NNFF，接口设置 `delay=0.15` |
| **散热温控** | 借用 `StockLongToyota`，强制限速 max 80% | **高危**：夏季暴晒超 85℃ 失去 100% 极温救险，极易热保护关机退巡航；熄火未限频 | 移除借用，实现三段式：常温低噪、高温过渡、>80℃ 拉满 100% 救险 |
| **驾驶员监控** | 借用 `SubaruManualParkingBrakeSng`，放大 10 倍 | 拷贝近百行代码，动态切换不生效；超时放至 110s/300s 等同废除 DM | 移除借用与百行冗余，合理放宽侧偏头至 6~8s，守死闭眼/玩手机红线 |
| **硬件检测** | `hardwared.py` 中直接 `if False: #TICI` 屏蔽 | 连底层存储真实掉盘也完全静默，导致模型和日志崩溃无法报警 | 放宽非三星 NVMe 报错，保留基础挂载健康检查 |
| **环境配置** | `launch_env.sh` 中硬编码明文 Mapbox 私钥与私有 IP | Secret Token 泄露，存在盗刷与封禁风险 | 剥离敏感 Token 为本地环境变量，提供安全加载模板 |

---

## 三、 五大核心专车优化模块设计与代码规范

### 3.1 模块一：专车平台定义与大车神经网络力矩映射 (NNFF)

#### 1. 车型平台注册（`selfdrive/car/hyundai/values.py`）
在 `CAR(Platforms)` 类中新增库斯途专用平台定义，显式绑定实测物理尺寸与全液晶仪表联动标志：

```python
# [selfdrive/car/hyundai/values.py]
class CAR(Platforms):
  # ... 原有车型 ...
  
  # Hyundai Custo / Custin 1st Gen (2.0T Flagship)
  HYUNDAI_CUSTIN_1ST_GEN = HyundaiPlatformConfig(
    [HyundaiCarDocs("Hyundai Custin 2023", "All", car_parts=CarParts.common([CarHarness.hyundai_k]))],
    CarSpecs(mass=1754, wheelbase=3.055, steerRatio=17.0),
    flags=HyundaiFlags.CHECKSUM_CRC8 | HyundaiFlags.SEND_LFA,
  )
```

#### 2. 大车神经网络前馈模型映射（`selfdrive/car/torque_data/substitute.toml`）
库斯途与帕里斯帝同属 3 米长轴距、近 2 吨大车，映射帕里斯帝（Palisade）力矩网络可获得饱满的转弯力矩前馈，消除进弯发软推头与出弯微摆画龙：

```toml
# [selfdrive/car/torque_data/substitute.toml]
"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"
```

---

### 3.2 模块二：8AT 传动防顿挫与超长轴距偏航时延补偿

#### 1. 专车分支落地与参数解耦（`selfdrive/car/hyundai/interface.py`）
- 彻底删除对 `LkasToggle` 的借用；
- 针对 8AT 变速箱液力变矩器起步冲的特性，固化 `startAccel = 1.0`（升 2 挡平滑抛物线）；
- 针对 3.055m 长轴距引起的车体偏航响应滞后，将转向执行器超前补偿延时设为 `0.15s`：

```python
# [selfdrive/car/hyundai/interface.py]
    # 彻底清理原有借用代码:
    # if Params().get_bool("LkasToggle"):
    #   ret.startAccel = 1.0
    # else:
    #   ret.startAccel = 1.6

    # 规范库斯途专车动力学分支:
    if candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN:
      ret.steerActuatorDelay = 0.15  # 3.055m 超长轴距偏航建立补偿 (150ms 超前前馈)
      ret.startAccel = 1.0           # 2.0T 8AT 专属: 固化起步加速度，消除 1-2 挡升挡冲击
    else:
      ret.steerActuatorDelay = 0.1
      ret.startAccel = 1.6
```

---

### 3.3 模块三：MPV 静音座舱与夏季前风挡极端暴晒三段式温控

#### 1. 治理原则
库斯途前风挡倾角大、玻璃面积近 1.5㎡，夏季暴晒中控台极易达到 70℃。原代码简单限制 80% 风扇在极端高温下必然导致过热关机；必须构建“舒适区静音、极温区拉满、驻车限功耗”的阶梯保护体系。

#### 2. 控制算法重构（`system/hardware/fan_controller.py`）
- 彻底移除 `StockLongToyota` 参数依赖；
- 采用智能三段式曲线：
  - **人耳舒适静音区（< 72℃）**：风扇控制在 20%~30%，完全隐入座舱静音背景；
  - **温升线性平衡区（72℃ ~ 82℃）**：线性提升风扇功率至 65%；
  - **极端暴晒救险区（> 82℃）**：**强制拉满 100% 极限压温**，保住不脱退、不损坏芯片；
  - **熄火驻车（`ignition == False`）**：严格限制风扇功率 $\le 20\%$，保护汽车小电瓶健康。

```python
# [system/hardware/fan_controller.py]
class TiciFanController(BaseFanController):
  def __init__(self) -> None:
    super().__init__()
    cloudlog.info("Setting up TICI fan handler for Hyundai Custo")
    self.last_ignition = False
    self.controller = PIDController(k_p=0, k_i=4e-3, k_f=1, rate=(1 / DT_HW))

  def update(self, cur_temp: float, ignition: bool) -> int:
    self.controller.neg_limit = -(100 if ignition else 30)
    self.controller.pos_limit = -(30 if ignition else 0)

    if ignition != self.last_ignition:
      self.controller.reset()

    # 库斯途 MPV 智能三段式专属温控策略
    if cur_temp > 82.0:
      # 极端暴晒救险: 强制拉满 100% 极限压温，坚守不关机底线
      fan_pwr_out = 100 if ignition else 30
    elif cur_temp > 72.0:
      # 升温平衡段: 72℃~82℃ 线性从 30% 上升至 70%
      fan_pwr_out = int(interp(cur_temp, [72.0, 82.0], [30.0, 70.0]))
      if not ignition:
        fan_pwr_out = min(20, fan_pwr_out)
    else:
      # 静音舒适段: < 72℃ 维持在 20%~30% 低噪区间
      fan_pwr_out = int(interp(cur_temp, [60.0, 72.0], [15.0, 30.0]))
      if not ignition:
        fan_pwr_out = min(15, fan_pwr_out)

    self.last_ignition = ignition
    return fan_pwr_out
```

---

### 3.4 模块四：家庭场景友好型驾驶员状态监控 (Family DM) 策略

#### 1. 治理原则
库斯途作为家庭 MPV，主驾需经常转头关照二排儿童与车内后视镜。原版 2~3 秒侧偏头即报警破坏家庭氛围；此前借用斯巴鲁手刹开关暴力放大 10 倍则完全废止了 DM。我们需要：**适度放宽偏头容限，严守闭眼与玩手机安全底线，消灭冗余代码**。

#### 2. 代码重构（`selfdrive/monitoring/helpers.py`）
- 彻底移除 `SubaruManualParkingBrakeSng` 参数读取与百行重复代码；
- 提供轻量化的 `apply_family_friendly_policy()` 方法微调偏转参数：

```python
# [selfdrive/monitoring/helpers.py]
  def apply_family_friendly_policy(self):
    """库斯途家庭 MPV 关怀型 DM 策略:
    适度放宽驾驶员转头看后视镜/后排儿童的姿态判定容限;
    严格保留对闭眼打瞌睡、低头玩手机的即时高灵敏报警。
    """
    self._AWARENESS_TIME = 45.                     # 被动接管总超时 (原 30s)
    self._AWARENESS_PRE_TIME_TILL_TERMINAL = 20.   # 预警倒计时放宽
    self._DISTRACTED_TIME = 16.                    # 主动偏头容限从 11s 放宽至 16s
    self._DISTRACTED_PRE_TIME_TILL_TERMINAL = 10.
    
    # 适度放宽偏航角阈值 (允许更从容看右侧后视镜与后排)
    self._POSE_YAW_THRESHOLD_SLACK = 0.55
    self._POSESTD_THRESHOLD = 0.35

    # 严守安全红线 (眼睛开闭度、眨眼、视线注意力门限维持高灵敏不变)
    self._FACE_THRESHOLD = 0.7
    self._EYE_THRESHOLD = 0.65
    self._BLINK_THRESHOLD = 0.865
```

---

### 3.5 模块五：改装硬件兼容与系统告警链治理

#### 1. 存储健康检查规范化（`system/hardware/hardwared.py`）
- 撤回暴力打补丁的 `if False: #TICI`；
- 恢复 `/data/media` 的挂载健康检测（真实掉盘时必须报警，防止黑盒故障）；
- 对非三星 980 NVMe 改装硬件放宽报错拦截，仅输出调试日志，不再阻塞系统：

```python
# [system/hardware/hardwared.py]
    if TICI:
      if not os.path.isfile("/persist/comma/living-in-the-moment"):
        if not Path("/data/media").is_mount():
          set_offroad_alert_if_changed("Offroad_StorageMissing", True)
        else:
          # 改装硬件与非标 NVMe 优雅兼容: 仅记录日志，不再弹窗报错阻断
          try:
            with open("/sys/block/nvme0n1/device/model") as f:
              model = f.read().strip()
            if not model.startswith("Samsung SSD 980"):
              cloudlog.info(f"Custom/Non-standard NVMe detected: {model}")
              # 不再设置 Offroad_BadNvme 弹窗
          except Exception:
            pass
```

#### 2. GPS 弱信号抑制配置化（`selfdrive/controls/controlsd.py`）
- 恢复原版 `self.events.add(EventName.noGps)` 代码，不采用暴力注释；
- 通过距离阈值与配置开关做平滑抑制，地库出库 1.5km 内自动静默，保证惯导发散时仍能通知车主接管。

---

## 四、 敏感配置隔离与国内云服务治理

针对 `launch_env.sh` 中硬编码的私有域名与 Mapbox Secret Token，采取环境变量加载与模板隔离：

1. **改造 `launch_env.sh`**：优先从本地环境持久化参数读取，Git 仓库只保留脱敏占位符；
2. **新增 `launch_env.local.template`**：供车机或测试环境配置私有 Token，该文件加入 `.gitignore` 彻底防泄露。

---

## 五、 TDD 自动化测试验证矩阵

针对上述 5 大模块，建立严格的 TDD 单元测试断言，确保改动 100% 可回归检验：

| 测试用例文件 | 核心断言内容 | 预期结果 |
| :--- | :--- | :--- |
| `test_custin_specs.py` | 验证 `CAR.HYUNDAI_CUSTIN_1ST_GEN` 存在，`mass == 1754`，`wheelbase == 3.055`，`steerRatio == 17.0`，包含 `SEND_LFA` | ✅ 绿灯通过 |
| `test_custin_interface.py` | 验证 `candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN` 分支生效，`startAccel == 1.0`，`steerActuatorDelay == 0.15`，无 `LkasToggle` 调用 | ✅ 绿灯通过 |
| `test_torque_substitute.py` | 验证 `substitute.toml` 中存在 `"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"` 映射 | ✅ 绿灯通过 |
| `test_custo_fan.py` | 验证温度 >82℃ 时风扇输出 100；验证 <72℃ 时风扇输出在 15~30 之间；验证熄火时输出 $\le 20$ | ✅ 绿灯通过 |
| `test_family_dm.py` | 验证 DM 在偏头 12s 时不触发报警，但闭眼超阈值时立即告警；无斯巴鲁开关依赖 | ✅ 绿灯通过 |
| `test_hardware_nvme.py` | 验证掉盘时正常上报 `Offroad_StorageMissing`；非标型号时不报 `Offroad_BadNvme` | ✅ 绿灯通过 |

---

## 六、 分步落地执行路线图与实车点火 Checklist

```
  【三阶段实施路线图】
  阶段一：车型注册与动力学固化 (values.py / substitute.toml / interface.py)
      │
      ▼
  阶段二：温控安全重构与硬件兼容 (fan_controller.py / hardwared.py)
      │
      ▼
  阶段三：家庭 DM 策略与纯洁化治理 (helpers.py / controlsd.py / launch_env.sh)
```

### 实车点火验收 Checklist（上车前终验）
- [ ] **仪表盘联动**：点火后仪表盘中央亮起白色方向盘；开启巡航后方向盘与车道线变为高亮鲜绿色，HDA 图标点亮；
- [ ] **起步体验**：红绿灯前车起步后，车辆平缓线性跟出，1-2 挡升挡无顿挫、无突兀抬头前冲；
- [ ] **弯道循迹**：以 80~100 km/h 驶入高速大曲率弯道，方向盘力矩充盈沉稳，无微摆画龙与推头；
- [ ] **座舱风扇**：常规行驶中前风挡风扇安静不可闻；强光暴晒停车等待时风扇平稳控温，无过热告警；
- [ ] **家庭 DM**：驾驶员转头看右侧后视镜或后排 5~6 秒内不报红，闭眼或看手机时即刻清脆提醒。

---
> 规范已就绪，经用户确认后即可按阶段逐一执行落地。
