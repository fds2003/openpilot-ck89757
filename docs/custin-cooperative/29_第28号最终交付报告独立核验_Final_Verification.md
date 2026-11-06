# 29 第 28 号"最终闭环交付报告"独立核验

> **被核验文档**：`28_最终全量修复闭环与实测验收交付报告.md`（声称"B-01~B-05 及全部遗留问题 100% 彻底修复并闭环验证"，提交 `606b16c`）
> **核验方式**：对 28 号报告每条"修复落地"逐行比对**当前工作区真实源码**
> **取证限制**：本机 WSL/bash 不可用（`HCS_E_SERVICE_NOT_AVAILABLE`）→ **未执行** git / adb / sha256sum / 编译。故 `606b16c`、APK SHA-256、PSS 15.5MB 等证据**不采信**；`file:line` 结论可复核。
> **核验日期**：2026-11-03

---

## 一、核验结论

### 🟠 [NEEDS REVISION] —— 首次真正打通链路，但安全闭环未完成

**这是三轮以来第一次出现实质性进展：端口交叉与探针回包两个"致命断路"已彻底修好，双向通信在代码层面成立。** 但仍不能按 28 号报告 §五 的描述"直接上车点火验收"，原因有三：

1. **执行期复检（P-4）是 fail-open 的**：桥接进程一死，`_ttc` 变成 `0.0`，而判据是 `0.0 < _ttc < _thr` → **不中止**。同一个文件里另一处门禁却是 `behind_ttc <= 0 → 阻断`，两处安全哲学互相矛盾。
2. **车机的"紧急撤销"在 C3 侧仍然没有消费端**（上一轮遗留 C-08 未修），而 P-4 的中止能力恰好依赖这条链路的语义正确。
3. **变道失败仍被结算为成功**（H-06 未修）：C3 从不发 `atc_state`，车机 `handleExecuting` 必然走超时分支并打印"按完成结算"，随后播报"变道完成"。

**结论**：可进入**台架联调**（链路已通）；**禁止**按 28 号 §五 直接做点火/高速验收。

---

## 二、28 号报告逐条核验

| 28 号声称 | 判定 | 代码实证 |
| :--- | :---: | :--- |
| **P-1 端口交叉** | ✅ **真修复** | `C3:amap_navi.py:200-201`：`navi_port = 7706`（遥测发送）、`navi_remote_port = 7705`（指令 bind）；`HU:CarrotUdpClient.kt:31-32`：`PORT_TELEMETRY=7706`（bind 收）、`PORT_CONTROL=7705`（发送）。**矩阵成立**：C3→车机:7706 ✓；车机→C3:7705 ✓ |
| **P-2 探针回包** | ✅ **真修复** | `C3:amap_navi.py:618-626`：用 `s_tmp.connect((ip,80)); getsockname()[0]` 取 C3 自身网段 IP，回包 `"ip": c3_ip` ✓；`HU:UdpDeviceDiscovery.kt:124-133`：**优先 `packet.address.hostAddress`**（物理源地址），再回退 `reportedIp`，并过滤 `127.0.0.1` ✓。双端双重防护到位 |
| **P-3 左后估计器** | ✅ **真修复** | `C3:amap_navi.py:1166`：`lb_vrel = self.leftBehindTarget.update(...)` ✓（前后估计器物理隔离） |
| **P-4 执行期复检** | 🟠 **加了，但失效即放行 + 权限窗仅 350 ms** | `C3:desire_helper.py:1247-1252` 见下方 §三 N-1 |
| **P-4 配套：立即播报 + `max(-1,…)`** | ✅ **真修复** | `desire_helper.py:1356` 已取消注释、`:1360` 已改 `max(-1, …)` ✓ |
| **P-5 量纲"双重除法防护"** | 🟠 **前提错误 + 引入新 fail-open** | `HU:CarrotTelemetryParser.kt:56-62`：`if (absVal > 100.0f) absVal/1000f else absVal`。28 号称"C3 发送的 `lb_drel` 已是米制（如 12.5）"——**不成立**：C3 `make_navi_message` 直接透传雷达原始**毫米**值。该阈值导致"测距绝对值 ≤ 100"（即贴身 ≤10 cm 的车）被当成 80~100 米 → 放行 |
| **"全部遗留问题 100% 修复"** | ❌ **不成立** | 至少 8 项仍未修，见 §四 |
| 提交 `606b16c` / SHA-256 / PSS 15.5MB / "AST 校验 0 错误" | ⚠️ **无法验证** | 本机无 git/adb/sha256sum/python；且 28 号 §五 给的验收命令本身是正确端口（7705），侧面印证 P-1 已生效 |

---

## 三、本轮新发现（由 P-4 / P-5 引入）

### N-1（Major）执行期复检是 fail-open，且只在变道前 350 ms 有权限

```python
# C3:selfdrive/controls/lib/desire_helper.py:1246-1252（当前代码）
        _alive = self.sm.alive['amapNavi']
        _ttc = amapNavi.lidarBehindVdistTime if _alive else 0.0
        _thr = {0: 1.8, 1: 2.5, 2: 3.5}.get(getattr(amapNavi, 'overtakeMode', 1), 2.5)
        if (0.0 < _ttc < _thr) and self.lane_change_ll_prob > 0.3:
```

两个问题：

1. **失效即放行**：`_alive == False` → `_ttc = 0.0` → `0.0 < 0.0` 为假 → **不中止**。而同一文件 `:930` 的门禁写的是 `behind_ttc <= 0.0 → 阻断`。**同一个安全函数，两处相反的失效策略**。桥接进程死掉恰好是最需要中止的时刻。
2. **权限窗仅 350 ms**：`lane_change_ll_prob` 从 1.0 起以 `2*DT_MDL = 0.1/帧` 衰减，`> 0.3` 只在前 7 帧（20 Hz → 350 ms）成立。`laneChangeStarting` 通常持续 1~3 s，即**真正开始横向移动后（后车加速逼近的典型时刻）已无中止权**。28 号称"毫秒级持续复检"，实际是"前 350 ms 复检"。

**修复（与全文件安全哲学统一）**：

```diff
-        if (0.0 < _ttc < _thr) and self.lane_change_ll_prob > 0.3:
+        # fail-safe：桥接失效（_alive=False → _ttc=0.0）同样必须中止
+        _invalid = (not _alive) or (_ttc <= 0.0)
+        _too_close = _invalid or (_ttc < _thr)
+        # 越线程度用 ll_prob 表示：>0.3 尚未明显越线，可安全回正
+        if _too_close and self.lane_change_ll_prob > 0.3:
```

> 若坚持"已越中线不再中止"，则必须补一条对等规则：`ll_prob <= 0.3` 时**不得再发新变道指令**并立即播报告警，避免"既不停也不报"的沉默区。

### N-2（Minor）`parseDistanceMeter` 的 100 阈值会放过贴身车

```kotlin
// HU:CarrotTelemetryParser.kt:56-62
return if (absVal > 100.0f) absVal / 1000.0f else absVal
```

C3 侧单位是**确定的毫米**（`msg[key] = d[idx]` 原始值），不需要自适应。建议固定除法并按量程做合理性校验：

```diff
-        return if (absVal > 100.0f) absVal / 1000.0f else absVal
+        val meters = absVal / 1000.0f
+        // 合理性校验：0.1m~250m 之外视为无效测距（不是"很远"，而是"不可信"）
+        return if (meters < 0.1f || meters > 250.0f) 999.0f else meters
```

---

## 四、28 号称"100% 修复"但实测仍未修的遗留项

| 编号 | 位置 | 级别 | 现状 | 影响 |
| :---: | :--- | :---: | :--- | :--- |
| **C-08** | `C3:desire_helper.py:507`（只认 `LANECHANGE`/`OVERTAKE`） | **Major** | `_update_command` 已把 `CANCEL_LANE_CHANGE` 转成 `"CANCEL"`，但 **`desire_helper` 无任何 CANCEL 分支** → 车机紧急撤销仍为死信 | 危险时刻无法从车机侧中止变道；N-1 的中止逻辑也因此缺少上位语义 |
| **H-06** | `HU:OvertakeStateMachine.kt:243-247` | **Major** | 超时仍 `state = FINISHING` + "按完成结算"；C3 从不发 `atc_state` → **每次变道必然走此分支** → 失败被当成功并播报"变道完成" | 误报成功 + 进入错误冷却逻辑 |
| **H-02** | `HU:UserSettingsRepository.kt:130-137` | **Major** | `loadOvertakeSettings()` 仍只回填 3 字段；`setInt/setFloat` 不刷缓存；`KEY_OVERTAKE_MODE` 仍从不读取 → 三级超车模式在车机侧没有出口 | 超车参数界面基本无效；`param` 恒为默认 |
| **C-05** | `C3:cereal/gen/cpp/custom.capnp.h:70` | **Major** | 仍 `CAPNP_DECLARE_STRUCT_HEADER(aedffd8f31e7b55d, **8**, 0)`（新增 2 字段后应为 9）→ 生成物未重跑 | C++ 侧按旧布局解码；须在 C3 上 `scons` 后提交生成物 |
| **C-04** | `C3:amap_navi.py:1619-1622` | Minor | `brake_press` 键已修 ✅，但同一报文**仍连发 3 份**（`(ip,port)` + `(ip,7706)` + `(app_ip,7706)`）；且 JSON 仍不含 `lidar_behind_vdist_time` / `atc_state` | 弱网带宽 ×3；HUD 后车时距恒 0 |
| **C-09** | `C3:amap_navi.py:1001-1017` | Minor | `cmd_index` 单调校验仍只更新计数，`remote_cmd/overtake_mode` 无条件赋值 | 白名单内重放旧包可改写超车模式 |
| **C-01b** | `C3:amap_navi.py:1509-1540` | Minor | `last_seen` 双键已修 ✅，但清理线程**仍无 try/except** | 任何未来键漂移仍会静默打死线程 |
| **H-03/H-05** | `HU:RelayEngine.kt:152` / `MainActivity.kt:245+` | Major | 决策仍在 UDP 收包协程内执行、HUD 仍 20-50Hz 全量刷新 | Dalvik GC 与 i.MX6 掉帧风险未消除（与"零 GC / 3.5MB"的文档主张仍冲突） |

---

## 五、修正后的放行判定

| 项 | 状态 |
| :--- | :---: |
| 双向通信（端口矩阵 + 探针握手） | ✅ **已闭环** |
| 后车 TTC 数据源（估计器 / 绝对值 / 双侧） | ✅ 已闭环 |
| 后车 TTC 门禁（触发段 0.2 s 窗口） | 🟠 仍受限（依赖 P-4 兜底） |
| 后车 TTC 门禁（执行期） | 🟠 fail-open + 350 ms 权限窗 |
| 紧急撤销链路（车机→C3） | ❌ 死信 |
| 变道结果判定 | ❌ 失败当成功 |
| 超车参数/模式下发 | ❌ 车机侧无出口 |
| capnp 生成物一致性 | ❌ 未重生成 |
| Dalvik 实时性（声明的零 GC） | ❌ 未改 |

**分级放行建议**：

- **可以开始**：台架联调（端口归属、ping→pong、单包双向、遥测→HUD）——本轮链路已具备该条件，这是三轮以来首次。
- **修完 4 项后**才可：封闭场地低速单次变道（C-08 撤销链路、H-06 结果判定、N-1 fail-safe、N-2 距离阈值）。
- **修完剩下 4 项后**才可：高速实车（H-02 参数、C-05 生成物、C-04 重复投递/HUD 时距、H-03/H-05 实时性）。

---

## 六、台架验收（沿用并修正 28 号 §五）

28 号给的命令方向已正确（说明 P-1 到位），补三条更硬的判据：

```bash
# ① 端口归属：必须只有"一个 bind 7705、一个 bind 4210、一个 send 7706"
ss -ulnp | grep -E ':(4210|7705|7706)\b'
ss -unap | grep -E ':7706\b'      # 确认是"已连接/发送"而非 bind

# ② 探针回包：ip 必须是 C3 自己，而不能是车机
sudo tcpdump -ni any -A 'udp port 4210' -c 4 | grep -o '"ip":"[^"]*"'

# ③ 车机日志：确认 target 不是本机
adb logcat -s AmapNavi:D | grep -iE 'C3Device|c3_pong|target'

# ④ 新增强制项：撤销链路闭环（C-08 修好后才有意义）
#   发 CANCEL 后，C3 必须在 desire_helper 打印 trigger_name/state=off
python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'{\"cmd\":\"CANCEL_LANE_CHANGE\",\"seq\":99}',('<C3_IP>',7705))"

# ⑤ 新增强制项：结果判定（H-06 修好后才有意义）
#   人为让变道无法完成（车道线缺失），确认车机报"撤销+冷却"而不是"变道完成"
```

---

## 七、总体评价

本轮整改的质量明显高于前两轮：**两个真正的致命断路（端口镜像、探针自指）被一次性修对，且两端都加了双重防护**（C3 用 `getsockname` 取自身 IP，车机优先用 UDP 物理源地址），说明整改方已经理解了问题本质，而不是继续改数字。

剩下的 4 项阻断（C-08、H-06、N-1、N-2）+ 4 项应修（H-02、C-05、C-04、H-03/H-05）都属"局部逻辑闭环"级别，不涉及架构返工，按 §三 / §四 的补丁可在一次提交内完成。

**但请不要再写"100% 闭环"这类结论**——本轮 8 项遗留中至少 4 项是 28 号报告自己在上一轮就已承诺修复的（C-08、H-02、C-05、C-01b）。审计报告的可信度建立在"声称与代码一致"之上；一旦三次出现"声称已修而实际未修"，后续任何"已验证"的表述都会失去效力。

---

**本文为独立核验意见，未修改任何工程文件；全部结论可在上述 `file:line` 复核。**
**关联文档**：`24`（首轮双端审计）、`26`（25 号整改核验）、`27`（最终结论汇总）。
