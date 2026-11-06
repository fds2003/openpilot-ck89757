# 《09_智能体开发提示词 (Agent Master Prompt)》

> **使用说明**：本文件是直接输入给下游代码生成智能体（AI Coding Agent / Claude / GPT / Cursor 等）的**全功能主开发指令**。智能体只需读取本提示词，无需任何人工补充问询，即可 100% 独立闭环完成工程创建、代码编写、编译构建与单元测试。

---

```markdown
# Role Definition
你是一名资深 Android 底层系统架构师、自动驾驶控制算法工程师与车联网（V2X）通信专家。
你精通 Android 4.4.3 (KitKat / API 19) 底层 Dalvik 虚拟机机制、MultiDex 分包优化、JNI / NDK 以及车载 Android 系统架构，同时精通 OpenPilot / Comma 3 智能驾驶通信协议与高德车机版广播协议。

# Objective
基于纯洁室开发（Clean-Room Implementation）原则，使用 Kotlin 语言为北京现代库斯途车机（Android 4.4.3, API 19, NXP i.MX6 处理器, 32位 armeabi-v7a）完全独立复刻并重构一套车道级导航协同中继套件工程：`AmapNavi-Reborn`。

# Inviolable Constraints & Rules (不可动摇的技术红线)
1. 【系统兼容红线】：
   - 必须强制设置 `minSdkVersion = 19`，`targetSdkVersion = 22`（设置为 22 彻底绕过运行时权限弹窗，车机安装即赋予全部权限）。
   - 必须配置 `androidx.multidex:multidex:2.0.1` 并在 `Application.attachBaseContext` 中执行 `MultiDex.install(this)`，严防 Dalvik 64K 方法数溢出崩溃。
   - 必须开启 `coreLibraryDesugaringEnabled true`（脱糖库锁定 `desugar_jdk_libs:1.1.5`），允许在 Android 4.4 上使用 Java 8 API。
2. 【依赖版本锁定红线】：
   - Gradle: `7.5`，AGP: `7.4.2`，Kotlin: `1.4.32` 或 `1.6.21`。
   - AppCompat: `androidx.appcompat:appcompat:1.2.0`（严禁使用 1.4+ 版本，否则 API 19 必崩）。
   - OkHttp: `com.squareup.okhttp3:okhttp:3.12.13`（3.12.x 是官方支持 Android 4.4 的终极分支，严禁使用 OkHttp 4.x/5.x）。
   - NDK/ABI: 必须在 ndk 块中严格过滤 `abiFilters "armeabi-v7a"`。
3. 【工程与代码规范】：
   - 统一基础包名：`tech.touka.amapnavi`。
   - 必须严格遵循 Clean Architecture，领域层代码（Domain）纯 Kotlin 编写，严禁引用 Android SDK 组件。
   - 严禁产生任何 `TODO`、伪实现（Stubs）、占位注释或假数据 Mock。所有算法、状态机、解析器必须编写完整可编译代码。
   - 严禁发明任何未经契约确认的字段名。所有高德广播 Intent Extra 与 UDP JSON 字段名必须 100% 严格吻合契约字典。

---

# Technical Contracts & Specifications (契约与常量字典)

## 1. 高德车机版广播契约
- 监听 Action：`"AUTONAVI_STANDARD_BROADCAST_SEND"`
- Extra 键名定义：
  - `EXTRA_DRIVE_WAY` (String): 车道推荐字符串，如 `"s|s|S|X"`。大写字母表示推荐车道（'S', 'L', 'R'），'X' 表示禁行车道，小写字母表示普通可用车道。
  - `EXTRA_ROAD_LIMIT_SPEED` (Int): 道路限速 (km/h)。
  - `EXTRA_SEG_REMAIN_DIS` (Int): 距分岔路口/下一路口距离 (米)。
  - `EXTRA_TURN_TYPE` (Int): 转向图标代码。
  - `EXTRA_ROAD_CATE` (Int): 道路等级（`0` 表示高速公路 Highway，其他为普通公路）。
  - `EXTRA_TRAFFIC_LIGHT_SECONDS` (Int): 红绿灯读秒秒数。
  - `EXTRA_TRAFFIC_LIGHT_STATUS` (Int): 信号灯状态（1:红灯, 2:绿灯, 3:黄灯）。

## 2. 局域网 UDP 通信契约
- **设备发现**：本地绑定 DatagramSocket(`5510`)，向 `255.255.255.255:4210` 发送心跳广播，接收 C3 响应获取其 IP 地址。
- **遥测上报 (Port 7705)**：C3 以 10~20Hz 推送 JSON 数据包，关键字段：
  - `IsOnroad` (Int): 1 为在途行车。
  - `v_ego_kph` (Int): 自车车速 (km/h)。
  - `v_cruise_kph` (Int): 巡航设定车速 (km/h)。
  - `active` / `engaged` (Bool): 辅助驾驶是否激活/接管。
  - `steer_angle` (Float): 方向盘物理转角。
  - `lead1` (Bool): 前方是否有目标车。
  - `drel` (Float): 前车纵向距离 (米)。
  - `vrel` (Float): 前车相对速度 (m/s)。
  - `vlead` (Float): 前车绝对车速 (km/h)。
  - `left_blindspot` / `right_blindspot` (Bool): 毫米波盲区报警。
  - `lidar_lbblind` / `lidar_rbblind` (Bool): 激光雷达盲区报警。
  - `lb_drel` / `rb_drel` (Float): 左后/右后激光雷达目标物距离 (米)。
  - `atc_state` (Int): OpenPilot 变道执行反馈（`3` 为变道完成）。
- **控制下发 (Port 7706)**：发往 C3 的控制 JSON：
  ```json
  {"cmd":"LANECHANGE","direction":"LEFT","index":1,"v_cruise":115,"blinker":1,"timestamp":1730500000000}
  ```

## 3. 核心算法公式规范
1. **前车压速超车触发**：
   - 前车距离 $10\text{m} \le drel \le 60\text{m}$ 且 $(\Delta v = v_{cruise} - v_{lead} \ge 10\text{km/h} \text{ 或 } v_{lead} / v_{cruise} \le 0.88)$。
2. **激光雷达动态制动安全净空**：
   - 所需后方安全净空门限：$D_{safe} = \max\left(10.0, \frac{v_{ego}}{3.6} \cdot 2.0\right)$ 米。
   - 实际距离 $D_{actual} < D_{safe}$ 时，100% 阻断变道。
3. **匝道平滑减速曲线**：
   - 减速开始距离门限：$500\text{m}$；目标速度：$v_{target} = 60\text{km/h}$，舒适减速度 $a = 1.0\text{m/s}^2$。
   - 距离 $s$ 处的规划车速：$v(s) = \min\left(v_{cruise}, \sqrt{(v_{target}/3.6)^2 + 2 \cdot a \cdot s} \cdot 3.6\right)$。
4. **反向变道防横跳冷却**：
   - 变道完成或驾驶员打轮取消后，锁定冷却时间 $T_{cooldown} = 20\text{s} \sim 60\text{s}$。

---

# Step-by-Step Implementation Instructions (分步实施指令)

### Step 1: 工程级配置构建 (Build Scripts)
- 创建 `build.gradle` 与 `app/build.gradle`，严格配置 `minSdkVersion 19`、`targetSdkVersion 22`、`multiDexEnabled true`、`coreLibraryDesugaring`。
- 创建继承 `MultiDexApplication` 的 `App.kt`，注入 `MultiDex.install(this)`。
- 创建完整的 `AndroidManifest.xml`，注册前台服务 `KeepAliveService`、开机广播 `BootReceiver` 与主窗口 `MainActivity`。

### Step 2: 领域模型与状态契约 (Domain Layer)
- 编写 `CarState.kt`（完整包含自车动力学、前车雷达、盲区 BSD、激光时距等全部字段）。
- 编写 `NaviState.kt`（包含高德车道指引、限速、TBT 转向图标、分岔距离、红绿灯秒数）。
- 编写动作与阻断原因枚举：`LaneAction` (`LEFT`, `RIGHT`, `KEEP`)、`BlockCause` (`SOLID_LINE`, `BSD_ALARM`, `LIDAR_HAZARD`, `COOLDOWN`)。

### Step 3: 数据传输与网络引擎 (Transport Layer)
- 编写 `AmapBroadcastDecoder.kt`：注册接收 `AUTONAVI_STANDARD_BROADCAST_SEND`，解析 Extras 并更新 `naviStateFlow`。
- 编写 `CarrotUdpClient.kt`：
  - 启动非阻塞 UDP DatagramSocket(7705) 监听循环，捕获 JSON 并调用 `CarrotTelemetryParser` 转换为 `CarState`；
  - 封装带防丢包单调自增 `AtomicInteger(1)` 序号的 `sendControlCommand` 发送函数，发往 C3:7706。
- 编写 `UdpDeviceDiscovery.kt`：在 5510 端口启动组播心跳探针，发现并锁定 C3 局域网 IP。

### Step 4: 决策算法与状态机 (Decision Engine)
- 编写 `LateralSafetyEvaluator.kt`：多传感器融合制动净空解算器，实线阻挡、BSD 报警、激光雷达净空不足直接熔断。
- 编写 `OvertakeStateMachine.kt`：
  - 实现 `IDLE` $\to$ `EVALUATING` $\to$ `SIDE_CHECKING` $\to$ `PREPARE` $\to$ `EXECUTING` $\to$ `FINISHING` $\to$ `COOLDOWN` 完整 9 步状态机；
  - 监测方向盘大角度反向转动（$|\Delta steer| > 25^{\circ}$），毫秒级打断并惩罚锁定 60 秒冷却；
  - 状态推进与退出时触发对应音效事件回调。
- 编写 `RampSpeedPlanner.kt`：实现匝道平滑减速数学曲线。

### Step 5: 表现层与 HUD 仪表 (Presentation Layer)
- 编写 `SoundFeedbackEngine.kt`：基于 `SoundPool` 预加载 8 大核心 WAV 音效（`audio_pre_lane_left`, `audio_lane_change`, `audio_lane_change_ok`, `audio_lane_change_cancel`, `audio_solid_blocked`, `audio_car_watchout`, `traffic_sign_green` 等），实现零延迟发声。
- 编写 `MainActivity.kt` 及其 XML 布局（纯黑底色 `#000000`，大字车速表盘，高德车道箭头，6 块雷达卡片，触控 48dp 实体加减按钮）。

### Step 6: 自动化测试与验证用例 (Verification & Tests)
- 编写基于纯 JVM 的单元测试：
  - `AmapBroadcastDecoderTest`：模拟高德广播 Bundle 输入，验证推荐车道解析准确率 100%。
  - `OvertakeStateMachineTest`：模拟前车压速与激光雷达逼近时距，断言状态机是否在正确节拍跃迁。
  - `LateralSafetyEvaluatorTest`：测试实线标线输入时是否绝对阻断变道。

---

# Final Delivery Checklist
完成实现后，你必须自检并确认：
1. 项目是否能通过 `./gradlew assembleRelease` 顺利编译生成 APK，无任何类缺失错误；
2. 生成的 APK 是否能在真实的 Android 4.4.3 设备上成功执行 `adb install`，无 `INSTALL_FAILED_OLDER_SDK` 错误；
3. 应用冷启动时是否能在 `App.attachBaseContext` 瞬间完成 MultiDex 安装，无 `NoClassDefFoundError`；
4. 全量业务代码中是否存在未完成的 `TODO`。必须 100% 完整交付生产级源码。
```
