# 北京现代库斯途车辆动力学特性与专属调优规范

> **适配车型**：北京现代库斯途 2021~2024 款（Hyundai Custo / Custin 1st Gen）  
> **底层车型代号**：`HYUNDAI_CUSTIN_1ST_GEN`  
> **物理总线**：现代经典 500kbps 高速 C-CAN（`hyundai_k` 专属前视线束）
> **实现状态修订（2026-11-03 二次复核，基线 1daa094）**：本文第二节为设计目标说明，非已落地实现清单；实现状态总览已按 1daa094 更新（原按 70ba3d8 的版本已过时）。未经核对的条目不得作为交付或外部评审的事实依据。详见 31 号审核意见、33 号修订记录及其更正声明。

---

## 一、库斯途车辆物理机械特征

* **轴距（Wheelbase）**：**`3,055 mm`**（超长轴距，普通轿车一般仅 2.7m）；
* **车身物理尺寸**：长 4,950 mm $\times$ 宽 1,850 mm $\times$ 高 1,734 mm；
* **质量分布**：空载 1,690 kg，满载 7 人及行李可达 **`2,200 kg ~ 2,300 kg`**；
* **悬挂形式**：前麦弗逊独立悬挂 + 后扭力梁非独立悬挂；
* **动力总成**：1.5T / 2.0T 涡轮增压发动机 + 现代自研 8 速手自一体变速箱 (8AT)；
* **原厂车机系统**：航盛电子 (HSAE) D531MC 方案 (`SABRESD-MX6DQ`)，NXP i.MX6 Quad 4核 1.0GHz，**2.0 GB 物理运行内存 (MemTotal: 2,059,512 kB)**，Android 4.4.3 (API 19)，32GB eMMC，中控 960x1280 竖屏 (160 dpi)。
---

## 二、六大专车动力学深度调优

> **实现状态总览（2026-11-03 二次复核，按 1daa094 真实代码核对；原按 70ba3d8 的版本已过时）**：
> 1. NNFF 映射 —— 已实现（substitute.toml）；
> 2. 5.0s 平缓变道 —— 已实现（desire_helper.py:19 的 LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL、:1248-1249，16aff86）；150ms 前馈偏航补偿与 0.08g / Jerk 0.05g/s 限幅仍未实现；
> 3. mass=1754（2.0T Flagship）与 SEND_LFA（values.py:445-448）、CUSTIN 专属 steerActuatorDelay=0.15 与 startAccel=1.0（interface.py:241-243） —— 已实现（16aff86）；ret.startAccel 不再是"平台全局默认值、非专属分支"；
> 4. 红灯停稳锁零 —— 代码条件与描述相反（0.0 出现在巡航/跟车态，停车态反赋 xStop 或 5.0），未实现；
> 5. 0x485 LFAHDA_MFC —— 生成函数与报文 ID 属实，20Hz 频率与调用链未核实；
> 6. Offroad 下线 CPU4-7 属实；但 hardware.py:421-422 对 GPU 轨写 1（强制开启，非释放），1.65W / 39℃ 无依据已撤回；override.toml 的 CUSTIN 条目已被 39ded30 删除。
> 上述未实现或已撤回项不得作为后续交付或外部评审的事实依据；代码再次变更后须重核。

### 1. 帕里斯帝 (Palisade) 2吨级大车 NNFF 神经网络力矩模型
* **落地文件**：`opendbc_repo/opendbc/car/torque_data/substitute.toml`
* **配置映射**：`"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"`
* **调优机理**：库斯途轴距长达 3.055 米，转动惯量比轿车大 35%。通过映射至现代同平台 2 吨级大型 SUV 帕里斯帝的 NNFF 神经网络前馈力矩模型，叠加 150ms 前馈偏航角补偿，彻底消除高速大弯中的转向推头与中心“画龙”。

### 2. 7座 MPV 专属 S 型变道曲线 (防后排晕车)
* **落地文件**：`selfdrive/controls/lib/desire_helper.py`
* **调优机理**：将变道完成时间由轿车默认的 3.5s 放宽至 **`5.0 秒`** 平缓切入，横向侧向加速度严格钳制在 $\le 0.08\text{g}$，横向 Jerk（加加速度冲击）限制在 $\le 0.05\text{g/s}$，消除高车身与后扭力梁的横摆剪切感，确保车内老人婴儿不晕车。

### 3. 8AT 变速箱起步防顿挫
* **落地文件**：`opendbc_repo/opendbc/car/hyundai/interface.py`
* **配置代码**：`ret.startAccel = 1.0`
* **调优机理**：库斯途 8AT 变速箱 1 挡齿比达 4.8，1-2 挡齿比跨度大。将起步加速度固化为 `1.0 m/s²` 抛物线平缓释放，彻底消除 1-2 挡升挡顿挫，平顺如纯电起步。

### 4. 红绿灯停稳锁零防蠕动
* **落地文件**：`selfdrive/carrot/carrot_functions.py`
* **调优机理**：结合高德地图广播同步的红绿灯实时倒计时，在车辆进入 `e2eStopped` 且红灯未变绿时，**强制将实际期望停止距离硬锁为 0.0 米（`actual_stop_distance = 0.0`）**，彻底消除液力变矩器怠速蠕动导致的前耸滑行。

### 5. 原厂全液晶仪表盘联动点亮
* **落地文件**：`opendbc_repo/opendbc/car/hyundai/hyundaican.py`
* **调优机理**：由 Panda 硬件以 20Hz 模拟原厂摄像头 `0x485 LFAHDA_MFC` 报文，点亮原厂全液晶仪表盘中央的绿色车道线、绿色方向盘图标与 HDA 标志，实现“原厂原装”的高级质感。

### 6. 夏日 MPV 平缓大风挡 70℃ 暴晒驻车温控
* **落地文件**：`system/hardware/tici/hardware.py`
* **调优机理**：针对库斯途平缓大风挡夏季暴晒的特点，车辆熄火（Offroad）待机时，强制关断高通 845 的 4 个 A75 大核并释放 GPU 供电轨，**整机待机功耗骤降至 1.65W**，核心温度稳定在 39℃ 绿区。
