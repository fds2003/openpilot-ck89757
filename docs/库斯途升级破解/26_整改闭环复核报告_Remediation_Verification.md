# 26 整改闭环复核报告 · Remediation Verification

> **被复核文档**：`25_双端独立审计整改闭环与全量修复交付报告.md`（声称"全量 10 项审查意见 100% 完成工程级代码修改、实机验证闭环"）
> **复核对象**：`E:\汽车\库斯途升级破解\AmapNavi-Reborn`（工作区现状） + `E:\code\openpilot-ck89757`（工作区现状）
> **复核方式**：对 25 号报告中每一条"修改实施"逐行比对**当前工作区真实代码**（非报告截图）
> **取证限制**：本机 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`），**无法执行 git / sha256sum / dumpsys / adb**；因此 25 号报告 §四 的提交哈希 `493e8dd`、APK SHA-256、PSS 15.2MB、"语法编译 0 警告"等证据**本轮不可验证**，本报告不采信其结论，仅独立核验源码。
> **复核日期**：2026-11-02
> **复核判定**：🔴 **[FAIL] —— 整改未闭环，核心通信链路仍处于物理断开状态，且新增 1 个 Critical 回归**

---

## 一、复核结论（一句话）

**9 项"代码改动"确有落盘，但其中最关键的端口契约修复把两端同步镜像改写，制造了与整改前完全同构的"同向冲突"——改了数字，没改角色，双端依旧零通信；探针握手虽已能配对，却因回包 `ip` 字段填了"车机自己的 IP"，使车机把指令发给自己。** 因此 25 号报告"双向链路瞬间打通""动态 IP 捕获率 100%""具备完全闭环上车条件"三条结论均不成立。

---

## 二、10 项整改逐条复核结果

| # | 25 号声称的修复 | 复核判定 | 代码实证（当前工作区） |
| :---: | :--- | :---: | :--- |
| 1 | UDP 7705/7706 端口契约对齐（X-01） | 🔴 **未修复（Critical）** | 车机 `CarrotUdpClient.kt:31-32`：`PORT_TELEMETRY=7706`（bind 收）、`PORT_CONTROL=7705`（发）；C3 `amap_navi.py:200-201`：`navi_port=7705`（**发遥测**）、`navi_remote_port=7706`（**bind 收指令**）。→ C3 把遥测发往车机 **7705**（车机听 7706）；车机把指令发往 C3 **7705**（C3 听 7706）。**两端依然"同端口同角色"，与整改前的错误结构完全一致**，只是数字互换 |
| 2 | 探针 5510/4210 全兼容（X-02） | 🟠 **部分修复 + 新增 Critical** | 车机 `UdpDeviceDiscovery.kt:72-83`：同时发 `{"cmd":"discover","port":5510}` 到 4210、`c3_ping` 到 4210 与 5510；`parseResponse` 接受 `c3_pong/ready/comma3`（`:116-127`）✓。C3 `amap_navi.py:591-627`：bind 4210 ✓、双探针识别 ✓、`resp:c3_pong`+`auth`+`device_id` ✓、回源端口 ✓、写 `last_seen` ✓。**但 C3 回包 `"ip": ip` 用的是 `addr[0]`（探针发送方＝车机自己）**，而车机 `:124` 优先采用 `reportedIp` → **车机把 C3 地址记成了自己的 IP**，指令全部发给自己 |
| 3 | 净空门禁 mm→m 量纲与符号（H-01） | 🟢 **已修复** | `CarrotTelemetryParser.kt:47-52` 新增 `parseDistanceMeter()`：`abs(rawMm)/1000`，`-999999`/`0` → `999.0` 哨兵；`parse()` 第 66-67 行对 `lb_drel/rb_drel` 调用 ✓。`LateralSafetyEvaluator.kt:78-83` 与米制门限比较 ✓。**遗留**：缺失/解析失败与"无目标"同为 `999.0` → 距离门禁对雷达断流仍是 fail-open（见 §四 R-04） |
| 4 | 指令全量带 `arg/param/seq`（X-03） | 🟢 **已修复** | 车机 `CarrotUdpClient.kt`：`put("arg", action.code)` + `put("param", overtakeMode)` + `put("seq", seq)`，保留 `direction/index` 兼容 ✓；C3 `_update_command` 读 `direction or arg`、`index or seq`、`param` 白名单 `{0,1,2}` ✓，`CANCEL_LANE_CHANGE→CANCEL` ✓ |
| 5 | 撤回独立进程，消双实例（X-04） | 🟢 **已修复** | `process_config.py:144` 已恢复注释，`carrot_man` 内嵌实例独占 ✓ |
| 6 | 补 `last_seen` 消除 KeyError（C-01） | 🟢 **已修复** | `amap_navi.py:609-615` 同时写 `last_time` 与 `last_seen` ✓ |
| 7 | TTC 绝对值 + Fail-Safe 门禁（X-05） | 🟠 **部分修复，3 个致命子项未修** | C3 `amap_navi.py:293-302`：`abs(d)/1000/abs(v)`、双侧取 min、`99.0` 哨兵 ✓；`desire_helper.py:925-937`：`behind_ttc<=0` 或 `<thr` 即阻断 ✓。**但**：① `amap_navi.py:1159` **左后速度仍用 `self.leftFrontTarget.update(...)`**（左前估计器，`leftBehindTarget` 建而不用）→ TTC 分母仍不可信；② 门禁仍写在 `if self.carrot_lane_change_count > 0` 内 → `LANECHANGE` 只给 4 帧 = **0.2 s** 生命周期；③ 仍无方向区分（双侧取 min 是"更保守"但不是"正确"），且 `laneChangeStarting` 阶段无复检（原报告 C-08 未处理） |
| 8 | 指令白名单与防重放（A-03/A-04） | 🟡 **基本可用，有残留** | `amap_navi.py:1001-1017`：`app_ip` 源校验、`param` 白名单、`CANCEL` 转换 ✓。**残留**：`cmd_index` 单调校验只用于更新计数，`remote_cmd/remote_arg/overtake_mode` 仍**无条件赋值** → 白名单内重放旧包仍可改写 `overtake_mode`（`carrot_man` 的转发因 `cmd_index` 未变而不触发，属"部分防护"） |
| 9 | 帕里斯帝 NNFF 映射（C-07） | 🟢 **已落盘（待实机校验）** | `substitute.toml:43` 新增 `"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"` ✓。**待验证**：`HYUNDAI_PALISADE` 的力矩/NNFF 参数是否真实存在，否则启动日志报 substitute 回退 |
| 10 | 驾驶员介入下一帧退出（C-02） | 🟡 **改了一半，且文档与代码不符** | `desire_helper.py:1336-1339`：`steering_pressed = carstate.steeringPressed`（已去掉"反向"条件）✓。**但** 25 号报告 §3.6 展示的"立即 `lane_change_audio(True,4,0)`"在文件中**仍是注释**（`:1343`），且 `:1348` 的 `self.atc_cancel_delay = min(-1, self.atc_cancel_delay - 1)` 使其恒 ≤ -1 → `:1349 if self.atc_cancel_delay == 0:` **永不成立 → "领航已退出"语音在整段生命周期内一次都不会播报** |

**统计**：🟢 已修复 5 项（#3、#4、#5、#6、#9）；🟠 部分修复 2 项（#2、#7）；🟡 名义修复但有实质缺陷 2 项（#8、#10）；🔴 未修复 1 项（#1）——而 #1 与 #2 恰恰是"功能是否存在"的前提。

---

## 三、致命回归与未闭环项（须立即处理）

### 🔴 R-01（Critical · 新引入）C3 探针回包把"车机 IP"当"自身 IP"回给车机

```python
# C3:selfdrive/carrot/amap_navi.py:604-627（当前代码）
ip = addr[0]                 # ← 这是"探针发送方"，也就是车机自己
...
resp = json.dumps({ "resp": "c3_pong", ..., "ip": ip, ... })   # ← 把车机 IP 当 C3 IP 播出去
```

```kotlin
// HU:data/udp/UdpDeviceDiscovery.kt:122-127（当前代码）
val reportedIp = json.optString("ip")
val ip = if (reportedIp.isNotEmpty()) reportedIp else packet.address?.hostAddress ?: ""
```

**后果**：握手会"成功"，但 `C3Device.ip` = 车机自己 → `udpClient.updateTarget(自己)` → 所有指令发往 `本机:7705`（本机只听 7706）→ 落空。**比整改前更危险**，因为整改前 HUD 明确显示"未连接"，现在会显示"已连接"却完全不工作——故障从"可见"变成"静默"。

**修复（一行）**：

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-            "ip": ip,
+            # 必须是 C3 自身在车载热点网段的地址，绝不能用探针发送方地址
+            "ip": self.navi_get_local_ip() or ip,
```

> 车机侧无需改动。另建议车机侧加一道自检：`if (ip == 本机IP) 视为无效响应`，避免未来再次被同类回包污染。

### 🔴 R-02（Critical · 未修复）端口仍是"同向冲突"，只需再动一端即可真正闭环

当前（**错**）：

| 端 | bind（收） | send（发） | 结果 |
| :--- | :--- | :--- | :--- |
| 车机 | 7706 | → 7705 | 车机→C3:7705，C3 听 7706 ✗ |
| C3 | 7706 | → 7705 | C3→车机:7705，车机听 7706 ✗ |

正确（任一可行，**必须交叉**）：

| 方案 | 车机 bind / send | C3 bind / send |
| :--- | :--- | :--- |
| **A（改 C3 一行）** | 7706 / 7705 | 7705（cmd 收）/ 7706（遥测发） |
| B（改车机一行） | 7705 / 7706 | 7706 / 7705 |

方案 A 补丁（与 25 号报告 §2.1 期望的"C3 `navi_port=7705` / `navi_remote_port=7706`"相反，请以本表为准）：

```diff
--- a/selfdrive/carrot/amap_navi.py
+++ b/selfdrive/carrot/amap_navi.py
@@
-    self.navi_port = 7705        # 车机 PORT_TELEMETRY：遥测收端口
-    self.navi_remote_port = 7706  # 车机 PORT_CONTROL：指令发往 C3 的端口
+    self.navi_port = 7706        # C3 遥测【发送】目标 = 车机 PORT_TELEMETRY(7706)
+    self.navi_remote_port = 7705  # C3 指令【接收】端口 = 车机 PORT_CONTROL(7705)
```

> 判定原则只有一句：**一端的 `send` 端口必须等于另一端的 `bind` 端口，且两端绝不能"用同一端口收又发同一类报文"**。

### 🟠 R-03（Major · 未修复）TTC 分母仍由"左前"估计器产出

`amap_navi.py:1159`：`self.shared_data.lb_vrel = self.leftFrontTarget.update(lb_dreltmp, dist_timems)`
—— 左后速度仍在用**左前方**估计器（`leftBehindTarget` 建而不用），且同包内 `lf_dreltmp` 与 `lb_dreltmp` 交替喂入同一实例，`max_acc=4.0` 限幅下输出恒定饱和。右侧（`rightBehindTarget`）写法正确，证明这是笔误。

```diff
-                self.shared_data.lb_vrel = self.leftFrontTarget.update(lb_dreltmp, dist_timems)
+                self.shared_data.lb_vrel = self.leftBehindTarget.update(lb_dreltmp, dist_timems)
```

### 🟠 R-04（Major · 未修复）门禁作用域仍是 0.2 s；变道中途无复检

`desire_helper.py:920` 的整段 fail-safe 仍包在 `if self.carrot_lane_change_count > 0:` 内。车机只发 `LANECHANGE`（`RelayEngine.kt:97`），该计数为 `int(0.2/DT_MDL)=4` 帧 = **200 ms**；`OVERTAKE` 分支仍不可达。→ **安全门禁在变道真正需要的数秒内并不存在**，且 `laneChangeStarting` 阶段（`:1213` 附近）只有 `lane_change_prob/ll_prob` 判定，无 TTC 复检。

建议最小改动（在 `laneChangeStarting` 分支内追加，不依赖计数器）：

```python
      elif self.lane_change_state == LaneChangeState.laneChangeStarting:
        # 变道执行期持续复检后车时距（fail-safe：失效即中止）
        _alive = self.sm.alive['amapNavi']
        _ttc = amapNavi.lidarBehindVdistTime if _alive else 0.0
        _thr = {0: 1.8, 1: 2.5, 2: 3.5}.get(amapNavi.overtakeMode, 2.5)
        if (_ttc <= 0.0) or (_ttc < _thr):
          self.lane_change_state = LaneChangeState.off
          self.lane_change_direction = LaneChangeDirection.none
          self.trigger_name = "rear ttc abort"
          self.lane_change_audio(True, 12, 0)
```

### 🟡 R-05（Minor）"领航已退出"语音永不播报

`desire_helper.py:1348`：`self.atc_cancel_delay = min(-1, self.atc_cancel_delay - 1)` → 恒 ≤ -1，`:1349` 的 `== 0` 分支不可达。

```diff
-    self.atc_cancel_delay = min(-1, self.atc_cancel_delay - 1)
+    self.atc_cancel_delay = max(-1, self.atc_cancel_delay - 1)
```

### 🟡 R-06（Minor）车机净空门禁对"测距缺失"仍 fail-open

`parseDistanceMeter` 把"缺失/解析失败"与"无目标"都映射为 `999.0 m` → 直接放行。建议区分三态：`有目标 / 无目标 / 未知`，未知一律阻断（与 C3 侧 `behind_ttc<=0 → 阻断` 保持同一安全哲学）。

### 🟡 R-07（Minor）重放仍可改写超车模式

`_update_command` 中 `cmd_index` 单调校验只更新计数；`self.shared_data.overtake_mode = raw if raw in (0,1,2) else 1` 在旧索引包上仍执行。建议把 `remote_cmd/remote_arg/overtake_mode` 的赋值整体移入 `if idx is not None and idx > cmd_index:` 分支内。

---

## 四、25 号报告的证据链问题（影响其"闭环"主张的可信度）

| 声称 | 复核情况 |
| :--- | :--- |
| "全量 10 项 100% 完成" | 实为 5 项完成、2 项部分、2 项名义完成、1 项（端口）未修复 |
| "与 C3 端 `navi_port=7705 / navi_remote_port=7706` 完全咬合，双向链路瞬间打通" | **咬合方向相反**：两端 send/bind 角色相同，属物理断开（R-02） |
| "动态 IP 捕获率达到 100%" | 捕获会"成功"但捕获到的是**车机自己的 IP**（R-01），危害更大 |
| "§3.6 立即播报'领航已退出'" | 该行代码仍为注释，且 `min(-1,…)` 使播报分支永不可达（R-05） |
| "§4.1 APK SHA-256 / PSS 15.2MB 实机验证" | 本机无 adb/dumpsys/sha256sum 权限，**无法验证**；另注：同文档另一处仍称"常驻 3.5MB"，与 15.2MB 自相矛盾 |
| "§4.2 提交 `493e8dd` / Python 静态编译 0 错误 0 警告" | 本机无 git 与 python 可用，**无法验证**；工作区存在未提交修改的可能，`git log` 必须在 C3 上现场执行 |
| 引用"`24_双端全量协同工程_独立审计总报告.md`、`24_审计报告.md`" | 本轮审计实际只产出 `24_双端全量工程独立安全审查报告_Master_Review_Result.md`，另两份文件的来源需说明 |

---

## 五、可执行的验收流程（5 分钟台架，不再依赖"看起来连上了"）

按顺序做，任何一步失败即停止，**不要越过 R-01/R-02 去测功能**：

```bash
# ① C3 侧端口归属：每个端口必须只有一个 owner，且 bind/send 角色正确
ss -ulnp | grep -E ':(4210|5510|7705|7706)\b'

# ② C3 侧抓包：让车机发起一次扫网，确认探针进得来、回包 ip 字段是 C3 自己
sudo tcpdump -ni any -A 'udp port 4210' -c 4
#   期望看到回包形如 {"resp":"c3_pong",...,"ip":"192.168.x.C3"}  ← 必须是 C3 的地址

# ③ 车机侧日志：确认捕获到的 target 不是本机
adb logcat -s AmapNavi:D | grep -i -E 'C3Device|c3_pong|target'

# ④ 单包双向连通（不经业务逻辑）
#   C3 → 车机：手工发一帧遥测，车机 HUD 车速应变化
python3 -c "import socket,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(json.dumps({'v_ego_kph':88}).encode(),('<车机IP>',7706))"
#   车机 → C3：手工发一条指令，C3 打印 remote_cmd
python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'{\"cmd\":\"LANECHANGE\",\"arg\":\"LEFT\",\"param\":2,\"seq\":9}',('<C3_IP>',7705))"
```

④ 双向都通之后，再按"三段闭环"验收：`discover→pong`（含 ip 正确）→ `遥测→HUD 3 字段` → `按钮→carrotMan.carrotCmd→desire.trigger_name`。

---

## 六、放行判定

| 条件 | 状态 |
| :--- | :---: |
| R-01 探针回包填 C3 自身 IP | ❌ 未修复 |
| R-02 端口 send/bind 交叉 | ❌ 未修复 |
| R-03 `lb_vrel` 用左后估计器 | ❌ 未修复 |
| R-04 门禁脱离 0.2 s 计数器 + 执行期复检 | ❌ 未修复 |
| H-01 量纲 | ✅ 已修 |
| X-03 字段对齐 | ✅ 已修 |
| X-04 双实例 | ✅ 已修 |
| C-01 线程 KeyError | ✅ 已修 |
| C-07 NNFF 落盘 | ✅ 已落（待实机校验） |

**判定：🔴 仍为 FAIL。** 距"可上车联调"只差 2 处端口/回包修正（各 1 行）+ 1 行估计器修正，但**在这 4 项完成并用 §五 的 ④ 步实测通过之前，任何实车路测都没有意义**——因为此刻双端一条报文都过不去，所有"变道成功/失败"的观察都无法归因。

---

**本报告为独立复核意见，未修改任何工程文件；全部结论均可在上述 `file:line` 复核。**
