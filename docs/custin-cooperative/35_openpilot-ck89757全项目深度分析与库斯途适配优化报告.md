# 35 openpilot-ck89757 全项目深度分析与库斯途适配优化报告

> 分析对象：E:/code/openpilot-ck89757（分支 cp-custo-amap，HEAD 1daa094；原报告撰写于 70ba3d8，见下方更正声明）
> 目标车型：北京现代库斯途 2021~2024（HYUNDAI_CUSTIN_1ST_GEN，3.055m 轴距 / 空载 1690kg、满载 2200kg+ / 1.734m 高重心 / 后扭力梁 / 8AT / 500kbps C-CAN / i.MX6 车机 + Comma 3）
> 分析方式：源码逐层取证（opendbc 车辆层、controls 控制层、selfdrive/carrot 定制层、cereal 消息层、system 进程层、构建与测试），并与 01~34 号既有审计结论交叉核对
> 分析日期：2026-11-03
> 文档性质：独立分析报告；本次未修改任何工程代码

---

> **实现状态变更更正声明（2026-11-03 二次复核，基线 1daa094）**：本报告撰写于 70ba3d8；其后 16aff86 / 39ded30 / 1daa094 三次提交改变了多项事实。以下逐条更正，正文历史描述保留以便追溯，凡与下表冲突处一律以本表为准。

| 报告位置 | 原结论（已过时） | 当前事实（1daa094） | 判定 |
| :--- | :--- | :--- | :--- |
| 文首 / 一 / 七 | HEAD 70ba3d8、工作区 8 文件未提交、12 未跟踪路径 | HEAD 1daa094，工作区干净 | 已过时 |
| 一、测试 | 9 个 test 文件、30 个函数，整个目录未被 git 跟踪 | 15 个 test_*.py 已被 git 跟踪（16aff86 / 47cbffc / 32c2144），仍未进 CI | 部分过时 |
| 二 / 4.1 | 工作区把 M-12 的 0.0 哨兵改回 99.0 放行 | 已由 P0 裁决补强为严格净空判据并提交 1daa094 | 已过时 |
| 3.1 | CarSpecs(mass=1690)、flags=CHECKSUM_CRC8 | mass=1754（2.0T Flagship）、flags 加 SEND_LFA（values.py:445-448） | 已过时 |
| 3.1 第 5 点 | override.toml:77 有 CUSTIN = [2.5, 2.5, 0.1] | 该条目已被 39ded30 删除（resolve torque duplicate）；substitute.toml 的 NNFF 映射仍在 | 已过时 |
| 3.2 | steerActuatorDelay 无 CUSTIN 专属覆盖 | interface.py:241-243 已加 CUSTIN 专属 0.15 与 startAccel=1.0 | 已过时 |
| 3.2 | 5.0 秒变道 / LANE_CHANGE_STEP_CUSTO 在代码中不存在 | desire_helper.py:19 已定义 LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL，:1248-1249 按 5.0s fade out | 已过时 |
| 3.2 / 3.3 | 0.08g / Jerk 限幅、150ms 前馈、CUSTIN 专属 startAccel 分支均不存在 | 前两项仍未实现；startAccel 已有 CUSTIN 专属分支（值仍 1.0） | 部分过时 |
| 3.2 / 3.4 / 3.5 | NNFF 借用 Palisade、safety 无 CUSTIN 条目、STEER_THRESHOLD=150、20Hz 全量 JSON | 经复核仍属实 | 仍属实 |
| 3.5 | 三份投递简化为 1 份，改动未提交需回归 | 已由后续提交收敛，单份投递在 HEAD | 已过时 |
| 4.1 第 1、2 条 | sensor_ready/99.0 与 TEST_RELAX_MODE 是工作区未提交并发改动 | 二者由 16aff86 提交进 HEAD；本轮 P0 裁决已补强净空判据、移除后门，1daa094 提交 | 已过时 |
| 4.2 / 4.3 | 282 处 print、16 线程共用单锁、76 处 except、4 大文件 6827 行 | 量级结论仍成立，具体计数随提交微变，需重跑 | 仍属实（计数待更新） |
| 4.4 第 1 条 | capnp 生成物 15 字段 vs schema 17 字段 | 仍是 8 words / 15 字段，M-17 阻塞未解除 | 仍属实 |
| 4.4 第 4 条 | 测试目录未纳入版本控制、没有进入 CI | 15 个文件已跟踪；仍未进 CI | 部分过时 |
| 五 P0 第一项 | 裁决工作区 M-12 与 TEST_RELAX_MODE 并发改动 | 已完成（30 号台账 P0 裁决记录 / 1daa094） | 已过时 |
| 五 P0 第二项 | 在 C3 执行 scons 重生成 capnp 生成物 | 仍待执行（M-17 阻塞） | 仍有效 |
| 六 | SConscript 注释未暂存、有被 git add -A 带走的风险 | NOTE(M-17) 已进 HEAD，工作区干净 | 已过时 |

仍待处理：C3 侧 scons 重生成（M-17）、物理台架负向实测、32 号第六节四项实机内存证据。另：由 33 号同步修订的 21 号 / 22 号 §4.4 / 23 号维度 6 / README / VEHICLE_DYNAMICS / docs/custin/README 中的"5.0s 未实现""startAccel 非专属"标注同样已过时，本次未更正，列为下一步。

## 一、项目全景与基线

| 项 | 实测 |
| :--- | :--- |
| 项目形态 | openpilot 上游 + CarrotPilot 定制分支，含 opendbc_repo / panda / msgq_repo / tinygrad_repo 等子仓库 |
| 核心定制层 | selfdrive/carrot/ 共 18 个 py、6827 行；4 个大文件：amap_navi.py 2125、carrot_serv.py 1790、carrot_man.py 1102、carrot_functions.py 554 |
| 其他规模 | selfdrive/controls 31 py、system 112 py、cereal 7 py |
| 构建 | SConstruct（Decider MD5-timestamp）、cereal/SConscript（capnpc 生成 C++ 绑定）；pyproject 要求 Python >=3.11,<3.13，依赖含 scons / pycapnp |
| 测试 | selfdrive/carrot/tests/ 下 15 个 test_*.py 已被 git 跟踪（16aff86 / 47cbffc / 32c2144 提交），ast.parse 全部通过；仍未进入 CI |
| git 状态 | HEAD 1daa094，工作区干净（原报告撰写时为 8 文件未提交 / 12 未跟踪，已由 39ded30 / 1daa094 收敛） |

基线提示（已更正）：原报告基于 70ba3d8 与当时工作区；此后 16aff86 / 39ded30 / 1daa094 收敛了全部并发改动，当前工作区干净。第四节 4.1 描述的并发改动已经 P0 裁决处理，详见文首更正声明与 30 号台账。

## 二、结论速览

| 类别 | 发现数 | 最高优先级 |
| :--- | :--- | :--- |
| 与库斯途车型不匹配 | 6 类 | 车辆参数标定不足（mass 已改 1754）、NNFF 借用 Palisade、8AT 通用参数；部分已由 16aff86 改善 |
| 安全与正确性 | 5 项 | M-12 净空判据已补强并提交 1daa094；台架实测待补 |
| 性能与实时性 | 5 项 | 282 处 print、16 线程共用单锁 |
| 代码质量 | 5 项 | 4 个大文件职责过载、76 处吞异常 |
| 构建与工程 | 4 项 | capnp 生成物 15 字段 vs schema 17 字段（M-17 阻塞）；测试已纳入 git、仍未进 CI |

## 三、与库斯途车型不匹配的代码

### 3.1 车辆物理参数标定不足（最高）

opendbc_repo/opendbc/car/hyundai/values.py:445-448（按 1daa094 更正）：

    HYUNDAI_CUSTIN_1ST_GEN = HyundaiPlatformConfig(
      [HyundaiCarDocs("Hyundai Custin 2023", "All", ...)],
      CarSpecs(mass=1754, wheelbase=3.055, steerRatio=17),  # mass: 1754kg (2.0T Flagship)
      flags=HyundaiFlags.CHECKSUM_CRC8 | HyundaiFlags.SEND_LFA,
    )

问题（按当前代码复核）：

1. mass 已由 1690（空载）修正为 1754（2.0T Flagship，16aff86），但仍无空载/满载自适应；库斯途满载 7 人可达 2200~2300kg，载荷跨度超过 500kg，满载与空载共用同一控制增益。
2. steerRatio=17 的注释原文写 from learner（学习器估计），非实测标定；该值显著大于同平台轿车（约 13~15）。
3. tireStiffnessFactor 未指定，使用默认；对 1.734m 高重心与后扭力梁非独立悬挂，默认轮胎侧偏刚度缺乏依据。
4. interface.py:166 的 ret.centerToFront = ret.wheelbase * 0.4（=1.222m）是全平台通用近似，未针对前置前驱 MPV 的质心位置标定。
5. override.toml 的 CUSTIN 条目已被 39ded30 删除（resolve torque duplicate），原报告所列 :77 数值不再适用；substitute.toml 的 NNFF 映射仍在。

建议：补齐空载/满载质量自适应、实测转向比与质心、用实车稳态圆周/双移线数据标定 tireStiffnessFactor 与最大横向加速度。

### 3.2 横向控制：长轴距 / 高重心 / 后扭力梁未被单独建模

> 【2026-11-03 更正】16aff86 已加 CUSTIN 专属 steerActuatorDelay=0.15（interface.py:241-243），并实现 5.0s 平缓变道（desire_helper.py:19 的 LANE_CHANGE_STEP_CUSTO、:1248-1249）。下文"无专属覆盖""5.0s 不存在""步进仍为 2 * DT_MDL"三处已过时；0.08g / Jerk 限幅与 150ms 前馈仍未实现；NNFF 借用 Palisade 仍属实。

- interface.py:167 的 ret.steerActuatorDelay = 0.1 为全平台通用；该文件里只有 KIA_OPTIMA_G4_FL 有 0.2 的车型专属覆盖（:242）。库斯途 EPS 响应更慢，未专属标定。
- substitute.toml:43 把 CUSTIN 映射到 HYUNDAI_PALISADE 的 NNFF 模型（lat_models/HYUNDAI_PALISADE.json，2023-08-07 训练，input_vars 含 roll）。Palisade 是 2 吨级 SUV，与 1.7~2.3t 高重心 MPV 加后扭力梁的侧倾/横摆特性不同；latcontrol_torque.py:237-244 把 roll 直接喂给 NNFF，模型迁移误差会直接进转向力矩。
- desire_helper.py:18 的 LANE_CHANGE_TIME_MAX = 10. 是超时上限，不是变道时长；:1247 的 ll_prob 步进仍为 2 * DT_MDL。21 号指南声称的 5.0 秒平缓变道 / 0.08g / Jerk 0.05g/s 在代码中不存在（已由 31/33 号澄清为设计意图）。
- 高重心 MPV 对横向 Jerk 更敏感，但当前变道轨迹没有车型专属的 jerk 或侧向加速度约束。

建议：为 CUSTIN 采集转向阶跃响应并标定 actor delay；长期训练 CUSTIN 专属 NNFF，至少把 roll 补偿与高重心侧倾对齐；变道轨迹增加基于车高的 jerk 上限。

### 3.3 纵向控制：8AT / 液力变矩器按通用参数处理

interface.py:200-206 全部为平台全局值，无 CUSTIN 分支：

    ret.startingState = False
    ret.vEgoStarting = 0.1
    ret.startAccel = 1.0
    ret.longitudinalActuatorDelay = 0.5
    ret.longitudinalTuning.kpBP = [0.] ; kpV = [1.] ; kf = 1.0

- 8AT 的 1-2 挡大齿比落差、液力变矩器锁止冲击、D 挡蠕行扭矩，均未进入纵向模型；startAccel=1.0 只是 Hyundai 平台默认（31 号审核已确认）。
- selfdrive/carrot/carrot_functions.py 承担红绿灯停稳/防蠕动：stop_distance=6.0、trafficStopAdjustRatio、actual_stop_distance 在 :449-:495 多处赋值（xStop / 5.0 / user_stop_distance / 每帧递减 / 巡航态清零），状态转移复杂，且该文件多处注释为韩文乱码（编码问题），可读性差。
- 31 号审核指出：停稳且红灯时强制 actual_stop_distance = 0.0 与代码条件相反（0.0 出现在巡航/跟车态）；该语义混乱仍在。

建议：为 8AT 标定起步加速度曲线与换挡期间的扭矩请求斜率；把 carrot_functions 的停稳状态机抽成显式状态表并补单元测试（现有 test_dynamics_invariants.py 只覆盖纯函数，未覆盖状态机）；统一文件编码与注释语言。

### 3.4 CAN / safety / 传感器：无 CUSTIN 专属条目

- safety/safety/safety_hyundai.h 中 0x340 LKAS11、0x485 LFAHDA_MFC 出现在多个通用 rx/tx 列表；全目录检索没有 CUSTIN 专属配置。
- carstate.py:235/483 用 abs(steeringTorque) > STEER_THRESHOLD 判驾驶员接管；values.py:44 默认 STEER_THRESHOLD=150，仅 CANFD 车型改为 250（:51）。CUSTIN 属 hyundai_k（非 CANFD），沿用 150，未见对该车 EPS 的标定。
- 4 路外挂侧向微型激光雷达的数据在 selfdrive/carrot 层自行解析（amap_navi.py 的 lb_drel / rb_drel / lb_vrel / rb_vrel），不进入 openpilot 标准 radar pipeline；其距离单位在协议层曾混发（M-13 已修为米制）。

建议：复核 STEER_THRESHOLD 与 0x340 扭矩上限对 CUSTIN 的适用性；在 safety 配置中显式列出 CUSTIN 及其 CAN 指纹；把外挂雷达接入统一的时间戳/有效性模型，避免传感器在线但数据陈旧被当作有效。

### 3.5 车机协同侧的性能假设

- amap_navi.py 以 Ratekeeper(20) 推 20Hz 遥测（:666 注释误写 50Hz），JSON 含大量字段；工作区当前已把历史上的同一报文连发 3 份简化为 1 份（:1644 一带），但该改动未提交、需回归验证。
- 车机为 i.MX6 Quad / Android 4.4 / Dalvik（32 号裁决已统一 RAM 口径为 2.0GB，MemFree 约 150MB）。Dalvik 的 GC_FOR_ALLOC STW 与高频对象分配仍是瓶颈，C3 侧零分配优化只做了一半（车机端 CarrotTelemetryParser 已改为游标扫描）。
- 建议：遥测按变化率/差量发送而非全量 20Hz；字段按车机实际消费集合裁剪；在 C3 侧加发送频率与包长上限保护。

## 四、可优化提升的地方

### 4.1 安全与正确性（优先处理）

> 【2026-11-03 更正】第 1、2 条描述的 sensor_ready/99.0 与 TEST_RELAX_MODE 已由 16aff86 提交进 HEAD，并由 P0 裁决补强（严格净空判据）、移除后门，1daa094 提交；本节原文保留供追溯，不再作为待办。第 3、4、5 条仍需台架/回归验证。

1. 工作区并发改动与已闭环结论冲突（最高）：amap_navi.py 未提交 diff 把 M-12 的 ttc = min(ttc_list) if ttc_list else 0.0 改为

       sensor_ready = lidar_l or lidar_r or main_lb_drel is not None or main_rb_drel is not None
       ttc = min(ttc_list) if ttc_list else (99.0 if sensor_ready else 0.0)

   即传感器就绪且无逼近目标时 99.0 放行。这解决了空车道误阻断，但重新引入一类 fail-open：当后车并排（vrel 约 0）或 ttc_list 因数据陈旧为空、而 sensor_ready 判据仍为真时，会被判为净空放行。TTC 模型本身无法覆盖零相对速度、零间距。建议：把 sensor_ready 升级为数据新鲜度加有效性位双判据，并保留 0.0 作为未知即阻断的兜底；该改动需与 30 号台账 M-12 状态一并裁决，不能静默覆盖。
2. 环境变量后门：同一 diff 在 _update_command 加了 TEST_RELAX_MODE=1 且 ip 为 127.0.0.1 时绕过 app_ip 来源白名单。生产环境误设该变量会削弱注入防护；建议改为测试专用 fixture/monkeypatch，不在生产代码读环境变量。
3. TTC 只取两侧最小、不区分变道方向（当前为全保守，可接受），但应显式记录设计决策。
4. 断网/心跳超时机制仍依赖 carrot_lane_change_count 自然衰减（曾由 M-14 把门禁移出计数器，工作区又有改动），需回归验证。
5. 来源认证目前只有 IP 白名单加 index 单调校验，无会话令牌；热点环境应视为不可信网络（M-01 相关）。

### 4.2 性能与实时性

| 指标 | 实测 | 影响 |
| :--- | :--- | :--- |
| selfdrive/carrot 下 print | 282 处 | 生产构建应改为分级日志；20Hz 循环里的 print 会放大调度抖动 |
| interface.py 下 print | 40 处（美元符号或井号开头的调试输出） | 每次启动/特征检测刷屏 |
| threading.Thread | 16 处（amap_navi 内 7 个 UDP 线程加每客户端一个 worker） | 线程数随客户端增长，且共用单个全局 lock（amap_navi.py:23），锁竞争与死锁风险 |
| except Exception | 76 处 | 大量吞异常；其中收包线程异常后 sleep(0.05) 空转，线程静默失效而进程仍存活 |
| time.sleep | 31 处 | 部分用于异常退避，建议统一为带退避上限的可取消等待 |
| Ratekeeper(20) 注释 | 写 50Hz | 文档与实现不符，易误导维护者 |

另：navi_broadcast_info 线程未设 daemon（amap_navi.py:268），进程退出时可能阻塞；建议统一 daemon 并加 stop 事件。

### 4.3 代码质量与可维护性

1. 职责过载：amap_navi.py 2125 行同时承担进程入口、UDP 发现/收发、客户端管理、遥测组包、Cereal 发布、雷达数据解析、TTC 计算；carrot_serv.py 1790 行、carrot_man.py 1102 行同样混合多职责。建议按通信层 / 状态层 / 发布层 / 决策数据层拆分。
2. 异常处理：76 处 except Exception 中多数只 print 或 pass；1 处裸 except。建议按边界分层：网络/解析边界捕获具体异常并计数上报，内部逻辑不吞。
3. 编码与注释：carrot_functions.py 多处韩文乱码注释；values.py 中 HYUNDAI_CASPER 等相邻车型的注释误写 mass 来源为 custin 链接（复制粘贴痕迹）；desire_helper.py 保留韩文注释。建议统一 UTF-8 与注释语言规范。
4. 魔法数字：99.0 / 0.0 / 0.1 / 10.0 / 2.5 / 32（showDebugLog 位标志）等散落各处，建议集中到常量或 Params，并在 30 号台账登记语义。
5. 复制逻辑：amap_navi.py 中 make_navi_message 与 make_lidar_message 有重复字段拼装；_update_command 与各 _update_* 的 JSON 键处理可抽成 schema 校验函数。

### 4.4 构建与工程

1. M-17 capnp 生成物漂移（34 号已给指引与脚本）：cereal/gen/cpp/custom.capnp.c++:914-918 的 schema blob 与 member 数组仍是 15 字段版，而 cereal/custom.capnp 有 17 字段。本机无 capnpc；设备侧执行 bash tools/regen_capnp_gen.sh 即可重生成并验收。
2. .gitignore:48 忽略 cereal/gen，但生成物被 git 跟踪（历史带入），是漂移土壤；如需改为纯构建产物，须单独授权 git rm --cached。
3. SConstruct 使用 MD5-timestamp 决策器：source 内容 MD5 变化才会重建；34 号脚本的 touch 只改 mtime，对内容未变不会触发重复重建（期望行为），实际重建由 schema 内容变化保证。
4. 测试已进入版本控制但仍未进 CI（已更正）：selfdrive/carrot/tests/ 下 15 个 test_*.py 已被 git 跟踪（16aff86 / 47cbffc / 32c2144），语法全部通过；仍需在 CI 跑 pytest 与生成物一致性检查。
5. 仓库根目录有 12 个未跟踪文档/工具（AGENTS.md、COMMA3_CUSTIN_MASTER_GUIDE.md、docs/、tools/ 等），建议区分应提交与本地产物。

### 4.5 文档一致性

- 01~34 号文档存在 F/U/O、F-29、N/C/H/B、M 等多套编号；30 号主索引表已统一为 M-01~M-35，应作为唯一真相源。
- 21/22/23 号与 README / VEHICLE_DYNAMICS 的虚构实现声称已由 33 号修订记录标注；25/28 号历史报告的 RAM/PSS 旧口径已由 32 号裁决标注。
- 建议：后续任何已修复/已闭环声明必须引用 M 编号并给出当前基线 file:line，避免再次出现 4.1 那种静默覆盖。

## 五、优先级整改清单

| 优先级 | 项 | 依据 | 建议动作 |
| :--- | :--- | :--- | :--- |
| P0（已完成） | 裁决 M-12 与 TEST_RELAX_MODE 并发改动 | 4.1 / 30 号台账 | 已完成：净空判据补强、后门移除、门禁统一，由 1daa094 提交；台架实测待补 |
| P0 | 在 C3 执行 scons 重生成并提交 capnp 生成物 | 4.4 / 34 号 | bash tools/regen_capnp_gen.sh --commit |
| P1 | 车辆参数实测标定（质量自适应、转向比、质心、轮胎刚度） | 3.1 | 实车稳态圆周 / 双移线 / 阶跃响应采集 |
| P1 | CUSTIN 专属横向参数（actor delay、NNFF 迁移误差） | 3.2 | 至少标定 steerActuatorDelay；长期训练 CUSTIN NNFF |
| P1 | 8AT 纵向起步/换挡标定与停稳状态机重构 | 3.3 | 抽出显式状态表加单元测试 |
| P1 | 把测试目录纳入 git 与 CI | 4.4 | pytest 加生成物一致性检查 |
| P2 | 生产日志改造、线程收敛、异常分层 | 4.2 / 4.3 | 282 处 print 改日志级别；worker 改线程池；异常按边界处理 |
| P2 | 大文件拆分、魔法数字集中、注释编码统一 | 4.3 | 按通信/状态/发布/决策数据分层 |
| P2 | 遥测差量发送、字段裁剪 | 3.5 | 降低 20Hz 全量 JSON 对车机 Dalvik 的压力 |
| P3 | safety / STEER_THRESHOLD 对 CUSTIN 复核 | 3.4 | 与 0x340 扭矩上限一起实车确认 |

## 六、附：cereal/SConscript 改动核查（回应前一条核查要求）

| 项 | 结论 |
| :--- | :--- |
| 来源 | 工作区 diff 只有 4 行 M-17 防漂移注释，插在 schema_files 定义前；由本会话 2026-11-03 11:30 加入，无并发会话改动混入 |
| git 状态（已更正） | NOTE(M-17) 注释已进 HEAD，工作区干净；原报告所述"未暂存"为 70ba3d8 时状态 |
| 构建影响 | SConscript 是 Python 构建脚本，井号注释不参与解析；schema_files 列表、env.Command 的 target/source/action、env.Library 全部未变，不改变依赖关系、不触发额外重建、不影响 log/car/legacy 三个 schema |
| 风险（已解除） | 原"未提交、可能被 git add -A 带走"风险已随 39ded30 / 1daa094 收敛而解除 |

## 七、分析边界

本报告未修改任何工程代码；原始结论基于 70ba3d8 静态取证，文首更正声明已按 1daa094 逐条更新过时项。实车动力学 / CAN / safety 类判断均标注为需实机标定，未以文档声称代替代码事实。所有 file:line 可复核；本次更正同样未修改任何工程代码。
