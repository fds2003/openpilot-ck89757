# 《11_软件功能规格说明书 (FSD / SRS)》

> **项目名称**：`AmapNavi-Reborn` (车载高德车道级导航与开源智驾中继套件)  
> **文档版本**：V1.0  
> **基准对照**：`AmapNavi-V1.3.6.9.apk` 全量功能规格 100% 对齐  
> **编写日期**：2026-11-02  
> **规范等级**：工业级功能规格定义，涵盖 8 大页面、45 个具体用例 (UC-01 ~ UC-45)、全量配置参数、通信报文与界面交互规范。

---

## 目录

- [一、文档概述与对齐目标](#一文档概述与对齐目标)
- [二、全量功能用例矩阵 (UC-01 ~ UC-45)](#二全量功能用例矩阵-uc-01--uc-45)
- [三、页面级功能详细规格说明](#三页面级功能详细规格说明)
  - [3.1 MainActivity 主控制中枢与全景 HUD 仪表](#31-mainactivity-主控制中枢与全景-hud-仪表)
  - [3.2 SettingActivity 通用参数设置工作台](#32-settingactivity-通用参数设置工作台)
  - [3.3 NavSettingActivity 车道级领航专属设置面板](#33-navsettingactivity-车道级领航专属设置面板)
  - [3.4 OvertakeSettingActivity 自动超车专属设置面板](#34-overtakesettingactivity-自动超车专属设置面板)
  - [3.5 LogManagerActivity 本地决策日志管理台](#35-logmanageractivity-本地决策日志管理台)
  - [3.6 UdpDeviceActivity 局域网 C3 设备管理界面](#36-udpdeviceactivity-局域网-c3-设备管理界面)
  - [3.7 WxPayActivity 极客打赏与设备身份展示界面](#37-wxpayactivity-极客打赏与设备身份展示界面)
  - [3.8 WebViewActivity 内嵌 Web 说明容器](#38-webviewactivity-内嵌-web-说明容器)
- [四、全量参数持久化字典 (SharedPreferences)](#四全量参数持久化字典-sharedpreferences)
- [五、验收测试标准与判定准则](#五验收测试标准与判定准则)

---

## 一、文档概述与对齐目标

本规格说明书作为 `AmapNavi-Reborn` 的最终功能验收基准，确保复刻版本在**功能完整性、业务逻辑闭环度、界面操作层次**上与原版 `AmapNavi-V1.3.6.9.apk` 实现 **100% 完全对齐**。任何模块不得擅自删减用户可见功能。

---

## 二、全量功能用例矩阵 (UC-01 ~ UC-45)

| 用例编号 | 所属页面 / 模块 | 功能名称 | 触发条件 / 操作入口 | 预期输出与系统行为 |
| :---: | :--- | :--- | :--- | :--- |
| **UC-01** | `MainActivity` | 双速度表盘渲染 | 系统启动 | 左侧显示自车车速 `vEgo`，右侧显示巡航设定车速 `vCruise`。 |
| **UC-02** | `MainActivity` | 高德导航 TBT 指引 | 收到高德广播 | 呈现转向图标、距下个转弯剩余距离、道路名称。 |
| **UC-03** | `MainActivity` | 高德车道指引符号 | 收到 `EXTRA_DRIVE_WAY` | 动态渲染车道推荐箭头（如 `↑`、`→`、`⛔` 等）。 |
| **UC-04** | `MainActivity` | 限速快捷增减重置 | 点击快捷大按钮 | `[▲ +5]`, `[▼ -5]`, `[↺ 重置]` 实时调整当前巡航限速偏置并下发 C3。 |
| **UC-05** | `MainActivity` | 快捷操作路由栏 | 点击顶部按钮 | 分别跳转至设置、领航参数、超车参数、设备列表、赞助、展开超车抽屉。 |
| **UC-06** | `MainActivity` | 超车全景卡片抽屉 | 点击 `[超车]` 按钮 | 展开/收起下层 `layoutOvertakeDebug`，展示多传感器雷达阵列与决策详情。 |
| **UC-07** | `MainActivity` | 6 块雷达卡片矩阵 | 收到 C3 遥测数据 | 左/右前毫米波、正前车、自车、左/右后激光卡片变色（绿/黄/红）。 |
| **UC-08** | `MainActivity` | 实时决策 Trace | 系统运行中 | 底部文本滚动区实时显示系统决策思考流程（格式化时序文本）。 |
| **UC-09** | `MainActivity` | 导航模拟与日志操作 | 点击底部辅助按钮 | 提供清空日志、复制日志到剪贴板及导航引导模拟自测能力。 |
| **UC-10** | `SettingActivity` | 顶部一体化导航 Tab | 点击 Tab 按钮 | 在 [通用参数]、[领航参数]、[超车参数] 三大面板间无缝切换。 |
| **UC-11** | `SettingActivity` | 辅助停车与红灯控速 | 勾选复选框 / 点击 ± | 配置 `cbNaviTrafficAssist`、`cbCpTrafficAssist`、`cbRedLightTrafficAssist`。 |
| **UC-12** | `SettingActivity` | 视觉车道线检测配置 | 勾选复选框 / 点击 ± | 配置车道线检测周期 (默认500ms)、显示视频、显示车道线、高帧率模式。 |
| **UC-13** | `SettingActivity` | 视觉车道识别模式 | RadioGroup 单选 | 切换快速（Fast）、标准（Normal）、保守（Slow）三挡识别速度。 |
| **UC-14** | `SettingActivity` | 道路限速跟随与偏置 | 输入数值 / 点击 ± | 配置最低限速、最高限速（默认130）、百分比提速、固定提速 km/h。 |
| **UC-15** | `SettingActivity` | 收费站场景自适应 | 输入数值 / 点击 ± | 设置收费站目标限速、提前减速距离、驶过后维持时间。 |
| **UC-16** | `SettingActivity` | 车机顶部留空避让 | 输入数值 / 点击 ± | 设置 `top_pad_dp`（0~100dp），像素级避让库斯途车机顶部状态栏。 |
| **UC-17** | `SettingActivity` | 开发者工具入口 | 点击功能按钮 | 支持一键唤起安装 Flask、安装 CV2 或进入车道线标定自测。 |
| **UC-18** | `NavSettingActivity` | 车道领航双模开关 | 勾选复选框 | 分别控制高速公路车道领航 (`app_navi`) 与普通公路领航 (`app_road_navi`)。 |
| **UC-19** | `NavSettingActivity` | 推荐车道变道策略 | 勾选复选框 | 控制走推荐车道 (`suggest_lane_en`) 与避开禁行车道 (`dis_lane_en`)。 |
| **UC-20** | `NavSettingActivity` | 靠边偏好与宽松条件 | 勾选复选框 | 控制提前靠左、提前靠右、纯视觉靠右、宽松变道条件 (`safety_legacy_mode`)。 |
| **UC-21** | `NavSettingActivity` | 领航模式切换 | RadioGroup 单选 | 单选激进、标准、保守领航变道时机模式。 |
| **UC-22** | `NavSettingActivity` | 关键距离阈值设定 | 点击 ± 步进控件 | 设置领航最低车速 (km/h)、变道控制距离 (高速/低速)、分岔距离 (高速/低速)。 |
| **UC-23** | `NavSettingActivity` | 匝道平滑减速系统 | 勾选开关 / 设置参数 | 启用匝道提前减速，设置减速起点距离、目标限速（60/45）、驶入维持时间。 |
| **UC-24** | `OvertakeSettingActivity`| 超车模式单选面板 | RadioGroup 单选 | 提供 **[激进] [常规] [保守]** 超车模式一键切换。 |
| **UC-25** | `OvertakeSettingActivity`| 场景超车独立开关 | 勾选复选框 | 独立控制高速超车开关 (`cbHighway`) 与公路超车开关 (`cbRoad`)。 |
| **UC-26** | `OvertakeSettingActivity`| 激光雷达阈值模式 | RadioButton 切换 | 前向/后向分别支持“固定距离模式 (米)”与“速度时距模式 (秒)”切换。 |
| **UC-27** | `OvertakeSettingActivity`| 相对速度外推时距 | 点击 ± 步进控件 | 设置前向/后向相对速度外推时距（默认 4.0 秒）。 |
| **UC-28** | `OvertakeSettingActivity`| 外部阻挡门限联动 | 勾选复选框 | 控制“有禁行车道 X 时禁止超车”、“有推荐车道 * 时禁止超车”。 |
| **UC-29** | `OvertakeSettingActivity`| 反向变道防横跳冷却 | 点击 ± 步进控件 | 设置反向变道冷却锁定时长（默认 20 秒，防频繁变道）。 |
| **UC-30** | `LogManagerActivity` | 日志分类分栏切换 | 点击顶部 Tab | 在主系统日志 (`logs/app/`) 与超车决策日志 (`logs/overtake/`) 间切换。 |
| **UC-31** | `LogManagerActivity` | 历史日志倒序列表 | 进入页面 | 按生成时间倒序陈列所有日志文件（文件名、修改时间、文件大小）。 |
| **UC-32** | `LogManagerActivity` | 单文件内容查看与复制 | 点击日志条目 | 展开日志文本查看器，支持一键将日志全文复制到系统剪贴板。 |
| **UC-33** | `LogManagerActivity` | 单选删除与一键清空 | 点击删除按钮 | 触发确认弹窗，确认后彻底删除选定文件或清空全部分类日志。 |
| **UC-34** | `LogManagerActivity` | 系统分享导出日志 | 点击分享按钮 | 通过 `FileProvider` 调用系统分享组件，导出当前选中的日志文件。 |
| **UC-35** | `UdpDeviceActivity` | 组播探针启停控制 | 点击操作按钮 | 启动/停止 5510 端口 UDP 组播设备探测广播。 |
| **UC-36** | `UdpDeviceActivity` | 设备列表动态展示 | 收到 C3 响应 | 列表呈现局域网内发现的 C3 设备（IP 地址、Device ID、响应时间）。 |
| **UC-37** | `UdpDeviceActivity` | 手动选择目标设备 | 点击设备条目 | 将当前选中的设备 IP 固化为 UDP 控制与遥测主通信节点。 |
| **UC-38** | `WxPayActivity` | 赞助二维码展示 | 进入页面 | 纯黑全屏背景，居中呈现微信收款赞助码静态图片。 |
| **UC-39** | `WxPayActivity` | 软件唯一标识呈现 | 页面渲染 | 读取车机 `android_id` 生成唯一设备指纹，提示用户赞助时备注 ID。 |
| **UC-40** | `WxPayActivity` | 关闭退出交互 | 点击关闭按钮 | 退出赞助页面，平滑返回上级界面。 |
| **UC-41** | `WebViewActivity` | 内嵌 Web 说明容器 | 触发外部链接 | 加载本地或远程车载文档与说明 HTML。 |
| **UC-42** | 全局守护 | 开机通电自启 | 系统通电开机 | `BootReceiver` 监听 `BOOT_COMPLETED`，自动拉起核心前台服务。 |
| **UC-43** | 全局守护 | 前台保活防杀 | Service 创建 | 挂载不可清除的前台通知，提升进程 OOM 优先级为 `FOREGROUND_APP`。 |
| **UC-44** | 全局交互 | 驾驶员抗力接管熔断 | 变道中打方向盘 | 监测到转向扭矩超过阈值，立即撤销变道并启动 60 秒冷却锁定。 |
| **UC-45** | 全局交互 | 多通道低延迟音效 | 状态机节点触发 | 通过 `SoundPool` 毫秒级播放 8 大核心 WAV 音频。 |

---

## 三、页面级功能详细规格说明

### 3.1 `MainActivity` 主控制中枢与全景 HUD 仪表
- **视觉排版**：纯黑 `#000000` 底色，顶部状态栏（标题、高德状态、C3 状态、快捷按钮）、中部主仪表（左侧大字车速表盘 + 推荐车道，右侧 6 块雷达卡片）、底部控制台（实时 Trace 与超车状态）。
- **操作交互**：
  - 点击“设置”：启动 `SettingActivity`；
  - 点击“OP参数”：启动 `NavSettingActivity`；
  - 点击“超车”：展开/收起下层 `layoutOvertakeDebug` 全景抽屉，并提供跳转 `OvertakeSettingActivity` 入口；
  - 点击“设备”：启动 `UdpDeviceActivity`；
  - 点击“赞助”：启动 `WxPayActivity`。

### 3.2 `SettingActivity` 通用参数设置工作台
- **Tab 布局**：顶部陈列 `[通用参数]`、`[领航参数]`、`[超车参数]`，点击平滑切换页面。
- **参数分组**：
  1. 辅助停车组：`cbNaviTrafficAssist`, `cbCpTrafficAssist`, `cbRedLightTrafficAssist` 及目标车速增减（`etCpMinSpeedLimt`）；
  2. 视觉车道线组：`cbLaneDetect`, `cbVideoShow`, `cbLaneShow`, `cbLaneTypePublish`, `cbVideoShowFast`, `cbLaneColor`，检测周期 `etLaneDetectInterval`（步进 50ms）；
  3. 识别模式单选：`rbVisionLaneFastMode`（快速）、`rbVisionLaneNormalMode`（标准）、`rbVisionLaneSlowMode`（保守）；
  4. 限速偏置组：最低/最高限速输入、百分比偏置、固定提速输入；
  5. 车机避让偏置：`etTopPad`（0~100dp），针对库斯途原车状态栏遮挡。

### 3.3 `NavSettingActivity` 车道级领航专属设置面板
- **领航开关**：高速领航、公路领航、走推荐车道、避开禁行车道、提前靠左、提前靠右、纯视觉靠右、宽松变道条件、靠边禁止变道、领航播报、先播报后变道。
- **模式单选**：激进 / 标准 / 保守领航时机模式。
- **距离微调**：领航最低车速（20km/h）、变道控制距离（高速 2000m / 低速 500m）、分岔距离（高速 80m / 低速 30m）。
- **匝道减速系统**：匝道减速开关、减速起点距离（高速 400m / 低速 200m）、目标限速（高速 60 / 低速 45）、维持时间（10s）。

### 3.4 `OvertakeSettingActivity` 自动超车专属设置面板
- **超车模式单选面板**：
  - **激进 (Fast)**：较小跟车时距容忍（10~40m），前车压速 5km/h 即可发起超车；
  - **常规 (Normal)**：标准工况（跟车 10~60m，压速 $\ge 10\text{km/h}$，速度比 $\le 0.88$）；
  - **保守 (Slow)**：大时距等待，严格侧向净空。
- **多模式激光雷达阈值**：
  - 前向门限：固定距离（5.0m）与速度时距自由单选；
  - 后向门限：固定距离（10.0m）与速度时距自由单选；
  - 相对逼近时距：前向 4.0s，后向 4.0s。
- **反向冷却锁**：设定反向变道锁定时长（默认 20 秒，范围 10~60 秒）。

### 3.5 `LogManagerActivity` 本地决策日志管理台
- **分栏查看**：分类标签 `[主日志 app/]` 与 `[超车日志 overtake/]`。
- **文件列表**：呈现文件名、时间戳与体积，点击加载全文。
- **操作保障**：支持一键复制到剪贴板，删除与全删弹出 `custom_dialog` 二次确认。

### 3.6 `UdpDeviceActivity` 局域网 C3 设备管理界面
- **动态扫描**：点击“查找设备”，向 255.255.255.255:4210 发送探针，列表呈现响应设备（IP、设备 ID、最后响应时间）。
- **手动选择**：点击列表单行，将当前设备绑定为主控节点。

### 3.7 `WxPayActivity` 极客打赏与设备身份展示界面
- **极简弹窗**：纯黑背景，居中呈现微信赞助二维码，展示软件唯一 ID（`android_id` 算法生成），加宽“关闭”按钮退出。

### 3.8 `WebViewActivity` 内嵌 Web 说明容器
- **内嵌浏览**：配置标准 WebSettings，加载本地用户手册或远程调试端点。

---

## 四、全量参数持久化字典 (SharedPreferences)

所有配置项均统一持久化在 `amapnavi_settings.xml` 中，具备内存双向缓存机制：

| 参数 Key | 类型 | 默认值 | 业务含义与作用 |
| :--- | :---: | :---: | :--- |
| `app_overtake` | Bool | `true` | 自主超车总开关 (高速) |
| `app_road_overtake` | Bool | `false` | 自主超车总开关 (普通公路) |
| `overtake_mode` | Int | `1` | 超车模式 (0:激进, 1:常规, 2:保守) |
| `overtake_reverse_cooldown_s` | Int | `20` | 反向变道防横跳冷却秒数 |
| `lidar_front_dist_mode` | Int | `0` | 激光前向阈值模式 (0:固定米, 1:时距) |
| `lidar_front_dist_m` | Float | `5.0` | 激光前向固定安全距离 (米) |
| `lidar_rear_dist_mode` | Int | `0` | 激光后向阈值模式 (0:固定米, 1:时距) |
| `lidar_rear_dist_m` | Float | `10.0` | 激光后向固定安全距离 (米) |
| `app_navi` | Bool | `true` | 车道级领航总开关 (高速) |
| `app_road_navi` | Bool | `false` | 车道级领航总开关 (公路) |
| `suggest_lane_en` | Bool | `true` | 走推荐车道策略 |
| `dis_lane_en` | Bool | `true` | 避开禁行车道策略 |
| `keep_left_en` / `keep_right_en` | Bool | `false` | 提前靠左 / 靠右行驶偏好 |
| `nav_mode` | Int | `1` | 领航变道时机模式 (0:激进, 1:标准, 2:保守) |
| `ramp_slowdown_en` | Bool | `true` | 匝道提前平滑减速开关 |
| `ramp_slowdown_dist_h` | Int | `400` | 匝道减速起点距离 (高速, 米) |
| `ramp_slowdown_speed_h` | Int | `60` | 匝道目标巡航车速 (高速, km/h) |
| `ramp_hold_time` | Int | `10` | 驶入匝道后低速维持秒数 |
| `top_pad_dp` | Int | `0` | 车机顶部避让留空像素 (dp) |

---

## 五、验收测试标准与判定准则

1. **界面完整性验收**：
   - 从 `MainActivity` 点击各个按钮，必须能 100% 顺利拉起全部 7 个二级页面，无任何 `ActivityNotFoundException` 或权限拒绝闪退；
   - 在现代库斯途 **960 × 1280 竖屏** 或 **1080 × 1920 测试手机** 上，所有页面元素均能自适应填充，无截断或变形。
2. **数据双向闭环验收**：
   - 在任何设置页面修改参数（如将超车模式改为“激进”，或修改激光雷达距离），点击保存后退出，主界面状态机必须实时应用新阈值。
3. **通信与控制验收**：
   - 高德导航广播到达时，车道推荐符号实时渲染；
   - C3 遥测数据到达时，表盘与 6 块雷达卡片实时跳动；
   - 触发超车变道时，UDP 7706 发出对应的 `LANECHANGE` 指令，状态机进入 20 秒冷却。
