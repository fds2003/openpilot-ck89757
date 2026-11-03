# CarrotPilot (cp 分支) 综合优化方案

**项目**: openpilot-ck89757 · 分支 `cp` · HEAD `24b7ff2`
**目标平台**: Hyundai Custin 1st Gen · Comma 3 (SDA845 · AGNOS · larch64 · Python 3.11.4)
**版本**: V2.0 综合版
**日期**: 2026-07-08
**状态**: 内部技术文档

---

## 0. 文档定位与前提

### 0.1 与既有审计结论的关系

本方案基于以下 16+ 份文档交叉验证：

| 文档 | 核心贡献 |
|------|----------|
| `optimization-plan.md` (OP-01~OP-10) | 原始优化方案（已被 V2 审计判定 REJECTED） |
| `THIRD_PARTY_EVALUATION_GUIDE_V2.md` | 红队审计：38/100 REJECTED，OP-01/05/06 为 Blocker，OP-04 为 Critical |
| `AUDIT_REPORT_CP_OPTIMIZATION_REDTEAM.md` | 确认 F-06 (LeadDataV3 缺 dRel)、F-14、S-1~S-5 安全漏洞 |
| `CONSOLIDATED_AUDIT_AND_OPTIMIZATION_REPORT.md` | 统一审计结论，含硬件与代码层面发现 |
| `CODE_VERIFIED_OPTIMIZATION_PLAN.md` | 代码行号级验证，修正 OP-01/05/06 可行性 |
| `CUSTIN_COMMA3_CP_MASTER_OPTIMIZATION_PLAN.md` | 完整实施蓝图（V1，含已被否决条目） |
| `hw-sw-optimization-plan.md` | 软硬件联合优化（GPU/CPU/存储/温度） |
| `security-findings.md` | S-1~S-5 安全漏洞原始记录 |
| `carrot_new_analysis.md` | CarrotPilot 新增代码全量分析 |
| `THIRD_PARTY_AUDIT_PROMPT.md` | 审计任务书 |
| 其余 6 份 | 补充参考 |

**本方案核心原则**：
1. 凡 V2 审计判定不可行的条目（OP-01 原方案、OP-05 原方案、OP-06 原方案、OP-04 原方案），给出**修正后**的可行实现，并明确标注与原方案的差异。
2. 安全漏洞（S-1~S-5）为最高优先级，须在功能优化之前完成修复。
3. 每项修改标注精确文件路径和行号，可直接用于代码评审。

### 0.2 优先级定义

| 级别 | 含义 | 时间目标 |
|------|------|----------|
| P0 | 安全/合规阻断，必须立即修复 | 1 周内 |
| P1 | 功能正确性缺陷，影响日常驾驶安全 | 2 周内 |
| P2 | 性能/稳定性优化，提升体验 | 1 个月内 |
| P3 | 长期架构演进，非紧急 | 下一版本周期 |

---

## 1. 安全修复（P0）

> 本节对应 V2 审计 S-1~S-5 及红队审计确认的安全漏洞。
> **所有安全修复必须在任何功能优化合并之前完成**，否则 cp 分支不具备量产发布条件。

### 1.1 S-1 · ZMQ 7710 RCE（Critical · Blocker）

**位置**: `selfdrive/carrot/carrot_man.py:841,883`

**现状**:
```python
# :841 - 无认证，监听所有网卡
socket.bind("tcp://*:7710")
# :883 - 将 JSON 字符串直接作为 shell 命令执行
result = subprocess.run(json_obj['echo_cmd'], shell=True, capture_output=True, text=False)
```

**风险**: 任何同网段设备可发送 `{"cmd":"echo_cmd","echo_cmd":"rm -rf /"}` 获得 root 权限。

**修复方案**:

```python
# carrot_man.py:841 → 替换为本地回环绑定 + 令牌认证
import hashlib, time, secrets

ZMQ_AUTH_TOKEN = params.get_str("ZMQAuthToken", "").encode()  # 默认空=拒绝所有

def _zmq_rep_handler(self):
  while True:
    request = self.zmq_socket.recv_string()
    try:
      json_obj = json.loads(request)
    except json.JSONDecodeError:
      self.zmq_socket.send_string("error:invalid_json")
      continue

    # 1. 令牌验证（必须提供且匹配）
    if not ZMQ_AUTH_TOKEN:
      self.zmq_socket.send_string("error:no_auth_configured")
      continue
    provided_token = json_obj.get('token', '')
    if not hmac.compare_digest(provided_token.encode(), ZMQ_AUTH_TOKEN):
      self.zmq_socket.send_string("error:auth_failed")
      continue

    cmd = json_obj.get('cmd', '')
    # 2. 命令白名单（替代 shell=True）
    ALLOWED_CMDS = {'version', 'status', 'toggle', 'reboot', 'log_tail'}
    if cmd not in ALLOWED_CMDS:
      self.zmq_socket.send_string(f"error:cmd_not_allowed:{cmd}")
      continue
    # 3. 执行白名单命令，不使用 shell
    self.zmq_socket.send_string(self._safe_exec(cmd, json_obj))
```

**配套变更**:
- `params_keys.h`: 新增 `ZMQAuthToken` 参数键。
- `carrot_man.py:626` (UDP 7706) 同步加 token 验证。
- 文档更新 `SECURITY.md`：移除"RCE 通道已启用"描述，改为"受限命令接口"。

### 1.2 S-2 · FTP 硬编码凭据（High）

**位置**: `selfdrive/carrot/carrot_man.py:766,875,880`

**现状**:
```python
FTP_HOST = "shind0.synology.me"
FTP_USER = "openpilot"
FTP_PASS = "Ekdrmsvkdlffjt7710"  # 硬编码明文密码
```

**修复方案**:

```python
# 改为从参数系统读取，默认禁用
FTP_ENABLED = params.get_bool("CarrotFTPEnabled", False)  # 默认 False
FTP_HOST = params.get_str("CarrotFTPHost", "")
FTP_USER = params.get_str("CarrotFTPUser", "")
FTP_PASS = params.get_str("CarrotFTPPass", "")

if FTP_ENABLED and all([FTP_HOST, FTP_USER, FTP_PASS]):
  # 使用 ftplib，添加连接超时
  ftp = ftplib.FTP(timeout=10)
  ftp.connect(FTP_HOST, 21, timeout=10)
```

**配套变更**:
- `params_keys.h`: 新增 4 个 FTP 参数键。
- 立即在 Synology NAS 端**轮换密码**（已泄露于代码库）。
- 禁止在日志中打印 FTP 密码。

### 1.3 S-3 · HTTP 8088 无白名单 params.put + 全网卡绑定（High）

**位置**: `selfdrive/carrot/web_interface.py` · `store_toggle_values()` / `save_params` / `HTTPServer`

**现状**（3 处叠加风险）:
```python
# 1) 无白名单写参
def store_toggle_values(updated_values):
  for key, value in updated_values.items():
    params.put(key, value.encode('utf-8'))  # 任意键可写，含 OpenpilotEnabledToggle

# 2) socket 绑定全网卡
self.web_server = HTTPServer(('0.0.0.0', self.port), handler)  # 同网段任何设备可直接 POST /save_params

# 3) CORS 全开
self.send_header('Access-Control-Allow-Origin', '*')
```

**风险**: 同网段攻击者可 POST `/save_params` 写入 `ZMQAuthToken`（关闭 §1.1 认证）或 `OpenpilotEnabledToggle`，控制行为被篡改。

**修复方案**:

```python
# web_interface.py
# 1) 参数键白名单
PARAM_KEY_WHITELIST = frozenset({
  "CarrotAutoTurnControl", "CarrotEcoMode", "CarrotSafeMode", "CarrotHighMode",
  "CarrotStopDist", "CarrotFollowTime", "CarrotLateralAgg", "CarrotLongitudinalAgg",
  "CarrotVoiceAlert", "CarrotDashLight",
})

def store_toggle_values(updated_values):
  for key, value in updated_values.items():
    if key not in PARAM_KEY_WHITELIST:
      cloudlog.warning(f"web_interface: rejected non-whitelisted key: {key}")
      continue
    try:
      params.put(key, value.encode('utf-8'))
    except Exception as e:
      cloudlog.error(f"web_interface: failed to write {key}: {e}")

# 2) 绑定回环（仅本机能访问；若需 LAN 访问，改用 127.0.0.1 + SSH 端口转发）
self.web_server = HTTPServer(('127.0.0.1', self.port), handler)

# 3) 移除 CORS 全开（回环绑定后同机无跨域需求）
# 删除 Access-Control-Allow-Origin: *
```

### 1.4 S-4 · UDP 7706/7709/12345 无认证注入（Medium）

**位置**: `selfdrive/carrot/carrot_man.py:626,706,959`；`selfdrive/carrot/amap_navi.py:722,795`

**现状**: 所有 UDP 端点绑定 `0.0.0.0`，无来源 IP 校验，无消息签名。

**修复方案**:

```python
# 统一增加 IP 白名单（默认仅允许本地和 LAN）
ALLOWED_UDP_SOURCES = {
  '127.0.0.1',          # 本地
  '192.168.42.1',       # 车机默认网关
  '192.168.42.0/24',    # 车机局域网段
}

def _udp_check_source(addr):
  ip = addr[0]
  if ip in ALLOWED_UDP_SOURCES:
    return True
  # 检查是否在 192.168.42.0/24 范围内
  if ip.startswith('192.168.42.'):
    return True
  cloudlog.debug(f"udp: rejected packet from {ip}")
  return False

# 在每个 recvfrom 后调用
raw, addr = sock.recvfrom(4096)
if not _udp_check_source(addr):
  continue
```

**amap_navi.py 端口 4210-4213**: 同样加 IP 白名单，4211（导航数据接收）建议进一步限制为仅 `192.168.42.1`（车机本身）。

### 1.5 S-5 · 新增 amap_navi.py 端口未覆盖（Medium）

**位置**: `selfdrive/carrot/amap_navi.py:722,795`

V1 审计仅覆盖 S-1~S-4，**amap_navi.py 的 4 个 UDP 端口（4210/4211/4212/4213）未被纳入安全清单**。

**修复方案**: 与 1.4 相同，统一 IP 白名单。4210（广播发送）本身无风险，但 4211（监听）需限制来源。

### 1.6 安全修复汇总

| ID | 位置 | 严重度 | 修复动作 | 验收标准 |
|----|------|--------|----------|----------|
| S-1 | `carrot_man.py:841,883` | Critical | 回环绑定 + 令牌 + 命令白名单 + 禁用 shell | `nmap -sV` 扫描 7710 无 RCE 向量 |
| S-2 | `carrot_man.py:766,875` | High | 参数化凭据 + 默认禁用 | 代码搜索 `Ekdrmsvkdlffjt7710` 无结果 |
| S-3 | `web_interface.py` | High | 参数键白名单 + 回环绑定 + 移除 CORS `*` | 非白名单键写入被拒；`netstat` 仅 127.0.0.1:8088 |
| S-4 | `carrot_man.py:626,706,959` | Medium | UDP IP 白名单 | 非白名单 IP 包被丢弃 |
| S-5 | `amap_navi.py:722,795` | Medium | UDP IP 白名单 | 同上 |

---

## 2. 算法正确性修复（P1）

> 本节对应 V2 审计 OP-01/04/05/06 中**不可行方案**的修正实现。
> 原方案已被判定 REJECTED，此处给出代码行号级的可行替代。

### 2.1 OP-01 修正 · 雷达天桥过滤（Critical）

**核实结果（修正方案原文）**：

方案 V1 称 `_is_overpass` 有 **4 个调用点**，经完整重读 `radard.py` 后确认实际为 **6 个调用点**，且存在**两套判断标准不一致**：

| 行号 | 调用 | 判断对象 | 标准字段 |
|------|------|----------|----------|
| :537 | `self._update_overpass_tracker(track)` | Track | `yRel` |
| :573 | `if self._is_overpass(track)` | Track（主） | `yRel` |
| :582 | `if not self._is_overpass(track_scc)` | Track（SCC backup） | `yRel` |
| :625 | `if self._is_overpass(c)` | Track（compute_leads） | `yRel` |
| :728 | `if not _is_overpass_dict(self.leadCutIn)` | dict（局部函数） | `dPath` |
| :740 | `if not _is_overpass_dict(self.leadCenter)` | dict（局部函数） | `dPath` |

**根本性缺陷（N-1 深层）**：`_update_overpass_tracker` 用 `track.identifier`（Hyundai slot 号 `32+N`，**每帧重新分配**）做 `_overpass_tracker` 的 key。同一物理目标每帧可能换 slot → `stable_count` 每帧被重置 → **永远达不到 5 → 天桥确认逻辑实际上从不触发**。这是比"缺 dRel 字段"更致命的问题。

**修正方案**:

```python
# 1) 统一 6 个调用点为单一入口，消除 Track/dict 两套标准不一致
# 2) 用 (round(dRel,1), round(yRel,1)) 做跨帧稳定 key，完全弃用 slot 号
import time

def _should_filter_lead(self, lead_like) -> bool:
  """
  lead_like: Track 实例 或 dict（compute_leads 产出的 lead_dict）
  统一判断标准，替换 _is_overpass + _is_overpass_dict + _update_overpass_tracker
  """
  if hasattr(lead_like, 'identifier'):      # Track 实例
    dRel, yRel, vRel = lead_like.dRel, lead_like.yRel, lead_like.vLead
  else:                                       # dict
    dRel = lead_like.get('dRel', 0)
    yRel = lead_like.get('yRel', lead_like.get('dPath', 0))
    vRel = lead_like.get('vLead', 0)

  pos_key = (round(dRel, 1), round(yRel, 1))   # 跨帧稳定，不依赖 slot

  is_stationary = abs(vRel) < 1.0
  is_centered = abs(yRel) < 1.5
  is_mid_range = 10.0 < dRel < 80.0

  if is_stationary and is_centered and is_mid_range:
    entry = self._overpass_tracker.setdefault(
      pos_key, {'stable_count': 0, 'last_seen': time.monotonic()})
    entry['stable_count'] += 1
    entry['last_seen'] = time.monotonic()
  elif pos_key in self._overpass_tracker:
    del self._overpass_tracker[pos_key]

  # 清理 3s 未见条目
  now = time.monotonic()
  for k in [k for k, v in self._overpass_tracker.items() if now - v['last_seen'] > 3.0]:
    del self._overpass_tracker[k]

  return pos_key in self._overpass_tracker and self._overpass_tracker[pos_key]['stable_count'] >= 5

# 替换全部 6 个调用点：
# :573  主 track    → if self._should_filter_lead(track): track = None
# :582  SCC backup  → if not self._should_filter_lead(track_scc): track = track_scc
# :625  循环内      → if self._should_filter_lead(c): continue
# :728  leadCutIn   → if not self._should_filter_lead(self.leadCutIn): ...
# :740  leadCenter  → if not self._should_filter_lead(self.leadCenter): ...
# :537  删除 _update_overpass_tracker，逻辑已并入 _should_filter_lead
# 删除 _is_overpass_dict 局部函数
```

**验收标准**: 过桥场景（含 8 slot 雷达重分配）日志中过滤触发且对应帧不产生减速；非桥场景 false positive < 1/100km；单元测试覆盖 slot 换绑场景。

### 2.2 OP-04 修正 · 视觉-雷达交叉验证（Critical）

**原方案缺陷**: `LeadDataV3` 无 `dRel` 字段，无法直接做视觉-雷达距离匹配。

**修正方案**: 用**相对速度 + 横向位置**做匹配，而非绝对距离。

```python
# radard.py - 视觉-雷达交叉验证（修正版）
# 视觉 lead 数据：dVision, vVision, yVision (来自 parse_model_outputs.py)
# 雷达 lead 数据：dRadar, vRadar, yRadar (来自 radar_interface.py)

def _cross_validate_lead(self, vision_lead, radar_lead):
  """
  视觉与雷达 lead 一致性检查。
  匹配条件：
    1. 相对速度差 < 1.5 m/s
    2. 横向位置差 < 1.2 m
    3. 距离差 < 15 m（容忍雷达-视觉标定误差）
  """
  if not vision_lead.get('active', False):
    return True  # 视觉无 lead，直接接受雷达
  if not radar_lead.get('valid', False):
    return False  # 雷达无效，拒绝视觉 lead（避免 ghost braking）

  dv = abs(vision_lead['v'] - radar_lead['vRel'])
  dy = abs(vision_lead['y'] - radar_lead['yrel'])
  dd = abs(vision_lead['d'] - radar_lead['drel'])

  if dv > 1.5:
    cloudlog.debug(f"cross_val: speed mismatch {dv:.2f} m/s")
    return False
  if dy > 1.2:
    cloudlog.debug(f"cross_val: lateral mismatch {dy:.2f} m")
    return False
  if dd > 15.0:
    cloudlog.debug(f"cross_val: distance mismatch {dd:.2f} m")
    return False
  return True
```

### 2.3 OP-05 修正 · Custin 扭矩参数（Blocker）

**原方案缺陷**: `HYUNDAI_CUSTIN_1ST_GEN` 已在 `override.toml:77` 定义，若同时在 `substitute.toml` 加一条，`get_torque_params()` 的 `sum([candidate in x for x in [sub, params, override]]) > 1` 检查会抛出 `RuntimeError`。

**修正方案**: 只保留 `override.toml` 中的定义，**不添加 `substitute.toml` 条目**。改为验证 override 参数是否经过实测标定。

```python
# 现状：override.toml:77
# "HYUNDAI_CUSTIN_1ST_GEN" = [2.5, 2.5, 0.1]
# 这些值是占位值（与 PALISADE 相近但未经 Custin 实测）

# 正确做法：在 Custin 车辆上用 panda CAN 采集实际转向扭矩数据，
# 运行 opendbc_repo/opendbc/car/tests/test_torque_params.py 生成拟合值，
# 更新 override.toml 而非 substitute.toml

# 同时确认 NNFF 模型路径存在：
# opendbc_repo/opendbc/car/hyundai/model_path/
#   HYUNDAI_CUSTIN_1ST_GEN.json  ← 此文件不存在，NNFF 永远不激活
# 若需要 NNFF，需先训练/导出模型并注册 json 配置
```

**验收标准**:
- `pytest -k "test_hyundai" selfdrive/car/tests/test_models.py` 通过
- Custin 实车 0-100km/h 转向响应无超调（MPC 侧）
- `grep -r "HYUNDAI_CUSTIN_1ST_GEN" opendbc_repo/opendbc/car/torque_data/` 只在 `override.toml` 出现

### 2.4 OP-06 修正 · 100Hz 纵向停止分支乘法反馈（Blocker）

**原方案缺陷** (F-04): `longcontrol.py` 的 stopping 分支：
```python
output_accel = self.last_output_accel  # ← 用上一帧值作为本帧起点
stopAccel = self.stopping_accel if self.stopping_accel < 0.0 else self.CP.stopAccel
if output_accel > stopAccel:
  output_accel = min(output_accel, 0.0)
  output_accel -= self.CP.stoppingDecelRate * DT_CTRL  # 每帧减 0.01 m/s²
self.last_output_accel = np.clip(output_accel, accel_limits[0], accel_limits[1])
```

**问题**: `last_output_accel` 作为下一起点 → 指数衰减 `a(n) = a(0) - n*rate`，但被 `np.clip` 截断后，若 `accel_limits[0]` 比理论终值高，停止距离计算与实际不符。

**修正方案**: 改为**基于目标速度和距离的解析解**，不依赖帧间累积。

```python
# longcontrol.py - stopping 分支（修正版）
if self.state == LongCtrlState.stopping:
  # 解析计算：从当前速度减速到 0 所需的恒定减速度
  v_ego = self.CP.v_ego
  stop_dist_remaining = max(0.0, self.stop_distance - v_ego * DT_CTRL)  # 动态更新
  if stop_dist_remaining > 0.1:
    # 等距减速：a = -v² / (2*d)
    a_needed = -(v_ego ** 2) / (2.0 * stop_dist_remaining)
    a_needed = max(a_needed, self.CP.stoppingDecelRate * -5.0)  # 下限：最大减速度
  else:
    a_needed = -self.CP.stoppingDecelRate * 3.0  # 最后 0.1m 用固定减速

  # 平滑：限制减速度变化率（jerk limit）
  jerk_limit = 2.0  # m/s³
  da_max = jerk_limit * DT_CTRL
  a_smoothed = self.last_output_accel + np.clip(a_needed - self.last_output_accel, -da_max, da_max)

  # 与 PID 分支的 floor 限制对齐（smooth_stop_mode）
  if self.smooth_stop_mode == 1:
    a_smoothed = max(a_smoothed, -self.CP.stoppingDecelRate * 2.0)
  elif self.smooth_stop_mode == 2:
    a_smoothed = max(a_smoothed, -self.CP.stoppingDecelRate * 1.5)

  self.last_output_accel = float(np.clip(a_smoothed, accel_limits[0], accel_limits[1]))
  output_accel = self.last_output_accel
```

**验收标准**:
- 100km/h → 0 停止距离误差 < 1.5m（vs 理论 25m）
- 停止过程中减速度曲线无突变（jerk < 3.0 m/s³）
- 红灯停车无蠕行（e2eStopped 锁零生效）

### 2.5 N-1 修正 · trackId 槽位复用（High）

**位置**: `opendbc_repo/opendbc/car/hyundai/radar_interface.py`

**现状**: Hyundai 雷达 DBC 中 `trackId = 32 + slot`，slot 0-7，共 8 个槽位。每帧重新分配，同一物理目标可能在相邻帧获得不同 slot。

**影响**: 任何用 `trackId` 做跨帧稳定性的逻辑（包括 `_is_overpass` 的稳定计数）都会失效。

**修正方案**（已在 2.1 的 `_update_overpass_tracker` 中用位置联合键解决）:
```python
# 不再单独依赖 trackId，改为 (id, drel, yrel) 三元组做近似匹配
# 匹配阈值：Δdrel < 2.0m 且 Δyrel < 1.0m 视为同一目标
```

### 2.6 F-14 修正 · 目标类型推断（Medium）

**位置**: `selfdrive/controls/lib/lateral_planner.py`

**现状**:
```python
if v < 1.5:
  o_type = 'pedestrian'
elif v < 5.0:
  o_type = fallback_type  # 通常是 'two_wheel'
else:
  return None
```

**问题**: 以 `v_ego` 作为类型判断依据，但 `vLead` 是相对速度，慢速自行车（vLead ≈ 0.5）和行人（vLead ≈ 0）无法区分。

**修正方案**:
```python
# 结合横向距离和目标速度绝对值做类型推断
def _infer_obstacle_type(v_rel, y_rel, v_ego):
  v_abs = v_ego + v_rel  # 目标绝对速度估计
  if v_abs < 0.5:
    return 'pedestrian'
  elif 0.5 <= v_abs < 8.0 and abs(y_rel) < 2.0:
    return 'two_wheel'
  elif v_abs >= 8.0:
    return None  # 车辆目标，不触发两轮车躲避
  return fallback_type
```

---

## 3. 硬件与系统优化（P2）

### 3.1 GPU 功耗管理（Adreno 630）

**位置**: `system/hardware/tici/hardware.py` · `initialize_hardware()`

**现状**:
```python
sudo_write("0", "/sys/class/kgsl/kgsl-3d0/min_pwrlevel")
sudo_write("0", "/sys/class/kgsl/kgsl-3d0/max_pwrlevel")
sudo_write("1", "/sys/class/kgsl/kgsl-3d0/force_clk_on")
sudo_write("1", "/sys/class/kgsl/kgsl-3d0/force_rail_on")
sudo_write("710", "/sys/class/kgsl/kgsl-3d0/max_clock_mhz")
```

`min_pwrlevel=0` = 锁定最高频率档，`force_clk_on` 强制时钟常开 → GPU 功耗固定 ~4.5W，无法降频。

**修正方案**:
```python
def initialize_hardware(self):
  # 允许 GPU 在空闲时降频（仅加载模型时锁定高频）
  sudo_write("0", "/sys/class/kgsl/kgsl-3d0/max_pwrlevel")       # 最高档
  sudo_write("4", "/sys/class/kgsl/kgsl-3d0/min_pwrlevel")       # 最低档（允许降频）
  sudo_write("0", "/sys/class/kgsl/kgsl-3d0/force_clk_on")       # 不强制时钟
  sudo_write("0", "/sys/class/kgsl/kgsl-3d0/force_rail_on")      # 不强制电压轨
  sudo_write("550", "/sys/class/kgsl/kgsl-3d0/max_clock_mhz")   # 降峰值频率（原 710）
  # 模型推理前 1 秒临时锁高频
  # modeld.py 推理循环中：
  #   self.gpu_lock_high()   → min_pwrlevel=0, max_pwrlevel=0, force_clk_on=1
  #   推理完成后：
  #   self.gpu_unlock()       → min_pwrlevel=4, force_clk_on=0
```

**预期收益**: 待机功耗降 ~2W，模型推理时性能不变。

### 3.2 CPU 频率策略（gold core 限制）

**位置**: `system/hardware/tici/hardware.py` · `set_power_save()`

**现状**:
```python
# offroad 时 gold core (4-7) offlined，仅保留 0-3
# onroad 时恢复，但 scaling_max_freq 被限制在 1689.6 MHz
# 而 OPP 表显示 gold core 支持 2803.2 MHz
sudo_write("1689600", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
# ... cpu1-7 同样限制
```

**修正方案**:
```python
# onroad 时放开 gold core 频率限制
def set_power_save(self, save: bool):
  if save:
    # offroad：降频 + 下线 4-7
    for cpu in range(8):
      sudo_write("1000000", f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
    for cpu in range(4, 8):
      sudo_write("0", f"/sys/devices/system/cpu/cpu{cpu}/online")
    # 切换 governor 到 powersave
    for cpu in range(4):
      sudo_write("powersave", f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
  else:
    # onroad：恢复全速
    for cpu in range(8):
      sudo_write("1", f"/sys/devices/system/cpu/cpu{cpu}/online")
    # gold core 开放最高频率（MPC/推理需要）
    for cpu in range(4, 8):
      sudo_write("2803200", f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
      sudo_write("performance", f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
    # 小核保持节能
    for cpu in range(4):
      sudo_write("1900800", f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq")
      sudo_write("conservative", f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
```

**预期收益**: MPC 求解器（gold core）从 1.7GHz → 2.8GHz，求解时间预计降 30-40%。

### 3.3 风扇曲线修复（commit bb8c576 弱化）

**位置**: `system/hardware/tici/hardware.py` · 风扇控制逻辑

**现状**（commit bb8c576 后）:
```python
# 60°C 才启动风扇，最高 80% 转速
if temp > 60:
  fan_duty = min(80, int((temp - 60) * 4))  # 90°C → 100% 但被 cap 在 80%
```

**修正方案**:
```python
# 恢复更积极的风扇曲线（SDA845 在 75°C 以上 throttle）
FAN_CURVE = {
  45: 30,  # 45°C → 30%
  55: 45,  # 55°C → 45%
  65: 65,  # 65°C → 65%
  75: 90,  # 75°C → 90%
  85: 100, # 85°C → 100%
}

def _fan_duty_for_temp(self, temp: int) -> int:
  for threshold, duty in sorted(FAN_CURVE.items()):
    if temp <= threshold:
      return duty
  return 100
```

### 3.4 UFS I/O 调度器（cfq → noop）

**位置**: 启动脚本或 `system/hardware/tici/hardware.py`

**现状**: UFS 使用 `cfq`（CFQ I/O 调度器），对顺序写入（日志/录像）有额外排序开销。

**修正方案**:
```python
# 在 initialize_hardware() 中
sudo_write("none", "/sys/block/sda/queue/scheduler")  # 或 /sys/block/dm-0
sudo_write("256", "/sys/block/sda/queue/read_ahead_kb")
sudo_write("256", "/sys/block/sda/queue/write_cache")  # 若硬件有写缓存
```

### 3.5 NVMe 温度轮询（F-5）

**位置**: `system/hardware/tici/hardware.py` · `get_nvme_temperatures()`

**现状**:
```python
def get_nvme_temperatures(self):
  out = subprocess.check_output("sudo smartctl -aj /dev/nvme0", shell=True)
  # Comma 3 没有 NVMe 设备（UFS 存储），此调用永远抛 FileNotFoundError
```

**修正方案**:
```python
def get_nvme_temperatures(self):
  # 先检查设备存在
  if not os.path.exists('/dev/nvme0n1'):
    return []  # 无 NVMe，返回空列表
  try:
    out = subprocess.check_output(
      "sudo smartctl -aj /dev/nvme0", shell=True, timeout=5
    )
    return json.loads(out)
  except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
    cloudlog.warning("nvme: temperature read failed")
    return []
```

**`hardwared.py` 调用端**:
```python
# system/hardware/hardwared.py - hw_state_thread
nvme_temps = HARDWARE.get_nvme_temperatures()
if not nvme_temps:
  # 无 NVMe，使用 UFS 温度（若可获取）
  ufs_temp = HARDWARE.get_ufs_temperature()  # 新增
```

### 3.6 ignition 去抖（`hardwared.py`）

**位置**: `system/hardware/hardwared.py` · `hardware_thread`

**现状**:
```python
HARDWARE.set_power_save(not should_start)  # 每次 ignition 状态变化立即调用
```

**问题**: ignition 信号噪声（CAN 总线干扰）导致频繁的 onroad/offroad 切换，每次触发 CPU 上下线。

**修正方案**:
```python
# 加 500ms 去抖
_last_ignition = None
_debounce_ms = 500

def _debounced_power_save(self, should_start: bool):
  global _last_ignition
  now = time.monotonic()
  if _last_ignition is None or abs(should_start - _last_ignition) > 0:
    # 状态变化，记录时间
    self._pending_save = not should_start
    self._pending_time = now
    return
  elif should_start != _last_ignition:
    # 新状态，重置计时
    self._pending_save = not should_start
    self._pending_time = now
    return

# 在主循环中
if hasattr(self, '_pending_save') and time.monotonic() - self._pending_time > _debounce_ms/1000:
  HARDWARE.set_power_save(self._pending_save)
  _last_ignition = not self._pending_save
  del self._pending_save
```

---

## 4. 工程质量基线（P3）

### 4.1 `manager_shm_patch.py` 启动时共享内存清理

**现状**: 已实现，功能正常。保留。

**补充**: 在 `manager.py` 中确认调用顺序：
```python
# system/manager/manager.py
import openpilot.system.manager.manager_shm_patch as shm_patch
shm_patch.cleanup_shm()  # 必须在 process_config 加载之前
```

### 4.2 时区回退（`launch_chffrplus.sh`）

**现状**: 已实现 `Asia/Shanghai` 回退。保留。

**补充**: 验证 `TZ` 环境变量在所有子进程中传播：
```bash
export TZ="Asia/Shanghai"
# 确认 controlsd/radard/modeld 子进程继承此变量
# 在 launch_chffrplus.sh 中检查
```

### 4.3 Ruff 格式化基线

**现状**: 代码库 2 空格缩进，但部分 CarrotPilot 文件（`carrot_man.py`、`web_interface.py`）混用 4 空格。

**修正方案**:
```bash
# 仅对 CarrotPilot 目录运行 ruff format
ruff format selfdrive/carrot/
# 验证无逻辑变更
git diff --stat
```

### 4.4 日志脱敏

**现状**: `cloudlog` 中可能打印 FTP 密码、ZMQ 命令内容。

**修正方案**:
```python
# 在 cloudlog 包装层加脱敏过滤
SENSITIVE_KEYS = {'FTP_PASS', 'ZMQAuthToken', 'echo_cmd'}

def _sanitize_log(msg: str) -> str:
  for key in SENSITIVE_KEYS:
    if key in msg:
      msg = msg.replace(key, f"{key}=****")
  return msg
```

### 4.5 参数键注册

**现状**: 新增参数键（`ZMQAuthToken`、`CarrotFTP*`、`CarrotAutoTurnControl` 等）需同步到 `common/params_keys.h`，否则 `params.get_int()` 抛 `UnknownKeyName`。

**修正方案**:
```c
// common/params_keys.h - 在 CarrotPilot 段新增
const char CARROT_ZMQ_AUTH_TOKEN[] = "CarrotZMQAuthToken";
const char CARROT_FTP_ENABLED[]     = "CarrotFTPEnabled";
const char CARROT_FTP_HOST[]        = "CarrotFTPHost";
const char CARROT_FTP_USER[]        = "CarrotFTPUser";
const char CARROT_FTP_PASS[]        = "CarrotFTPPass";
const char CARROT_AUTO_TURN[]       = "CarrotAutoTurnControl";
// ... 对应 UnifiedParams 中所有 key
```

### 4.6 测试覆盖

**现状**: `selfdrive/carrot/` 下无任何 `test_*.py`（已核实），CarrotPilot 专属逻辑当前**零测试覆盖**。
测试框架可用：`pytest` + `pytest-xdist` + `conftest.py` 的 `OpenpilotPrefix` 沙箱（隔离 params/shm）。

**新增测试**（完整用例与断言见 §6.3）:
```
selfdrive/carrot/tests/
  test_overpass_filter.py     # §2.1 slot 换绑 + Track/dict 一致性 + 3s 清理
  test_cross_validate.py      # §2.2 一致/ghost/速度不匹配三档
  test_stopping.py            # §2.4 停距/jerk/e2eStopped 无蠕行
  test_web_whitelist.py       # §1.3 白名单键 + 绑定地址 127.0.0.1
  test_zmq_auth.py           # §1.1 token + cmd 白名单 + 无 shell=True
  test_udp_filter.py         # §1.4/1.5 白名单 IP 通过 / 非白名单丢弃
  test_nvme.py               # §3.5 无 NVMe 返回 [] 不抛异常
```

**回归安全网**：每项修改合入前须通过 §6.2 的 L0→L3 门禁（含 process_replay 基线比对、`test_models.py -k test_hyundai`、libsafety 安全限值不放宽、`tools/op.sh lint` 全绿、controls 改动保留 `*_LEGACY` A/B 开关）。

---

## 5. 执行路线图

### 5.1 时间线

```
Week 1 (P0 安全)
├─ Day 1-2: S-1 ZMQ 认证 + 命令白名单
├─ Day 2-3: S-2 FTP 凭据参数化 + 密码轮换
├─ Day 3-4: S-3 Web 参数白名单 + CORS
├─ Day 4-5: S-4/S-5 UDP IP 白名单（carrot_man + amap_navi）
└─ Day 5:   全量安全测试 + 回归

Week 2 (P1 算法)
├─ Day 1-2: OP-06 停止分支解析解（longcontrol.py）+ L1 test_stopping
├─ Day 2-3: OP-01 _is_overpass 6 调用点统一 + 位置 key 修正 + L1 test_overpass_filter
├─ Day 3-4: OP-04 视觉-雷达交叉验证 + L1 test_cross_validate
├─ Day 4-5: OP-05 Custin 扭矩参数标定（需实车数据）
└─ Day 5:   停止距离 + 过桥场景回放验证（L2 process_replay 回归门）

每项 P1 修改合入前必须通过 §6 的 L0+L1+L2（controls 层）+L3 门禁

Week 3-4 (P2 硬件)
├─ GPU 功耗管理（modeld 推理时锁频）
├─ CPU 频率策略（gold core 2.8GHz）
├─ 风扇曲线修复
├─ UFS noop 调度器
├─ NVMe 轮询修复
└─ ignition 去抖

Month 2 (P3 工程)
├─ ruff format 基线
├─ 日志脱敏
├─ 参数键注册
└─ 单元测试补全
```

### 5.2 依赖关系

```
S-1~S-5 (P0) ──→ 所有 P1/P2 工作的前置条件
                  （安全漏洞未修复前，不建议上实车测试新功能）

OP-06 修正 ──→ OP-01 修正
（停止距离计算依赖 overpass 过滤准确性）

OP-05 标定 ──→ 需实车 CAN 数据
（无法在 PC 上完成，需 Comma 3 挂载 Custin）
```

### 5.3 风险登记

| 风险 | 影响 | 缓解 |
|------|------|------|
| OP-06 解析解在低速（<5km/h）退化 | 停止距离误差增大 | 低速时切回固定减速度模式 |
| GPU 降频影响模型推理延迟 | controlsd 周期漂移 | 推理前 1 秒锁高频，推理后解锁 |
| CPU 2.8GHz 导致热节流 | 长时间行驶降频 | 风扇曲线修复 + 温度监控 |
| ZMQ 认证破坏现有 CarrotMan 手机端协议 | 功能回退 | 提供 `ZMQAuthToken=legacy` 兼容模式，过渡期 2 个版本 |

---

## 6. 正确性保证与测试验证方案

> 本节回答"如何保证方案正确"与"是否有严格测试验证方案"。
> 核心结论：**方案不能仅靠文档自证，必须以代码库现有测试基础设施 + 可执行验证 + 回归门保证。**

### 6.0 诚实评估（本方案已知缺口）

在撰写本方案时，对关键代码做了二次核实，确认以下事实与 V1 描述不一致，**已在本文修正**：

| V1 描述 | 核实结果 | 本文修正位置 |
|---------|----------|-------------|
| `_is_overpass` 有 4 个调用点 | 实际 **6 个**调用点（:537/573/582/625/728/740），且 Track 版用 `yRel`、dict 版用 `dPath` 两套标准 | §2.1 |
| 天桥过滤"只缺 dRel 字段" | 更深缺陷：`_overpass_tracker` 用 slot 号做 key，`stable_count` 每帧被重置**永不达 5**，过滤实际从不触发 | §2.1, §2.5 |
| S-3 仅"无白名单写参" | 叠加 `HTTPServer(('0.0.0.0', port))` 全网卡监听 + CORS `*`，同网段可直接写参 | §1.3 |
| 安全/算法修改已可直接落地 | 行号基于 `24b7ff2`，**合并前必须重新确认**（代码可能已变动） | 全文 |

**结论**：方案的"正确性"= ① 事实经代码核实 ② 修正实现可编译可运行 ③ 有可执行测试与回归门。**仅①不足以保证正确，必须②③闭环。**

### 6.1 测试基础设施现状（已核实）

```
可用工具（pyproject.toml 已声明）:
  pytest, pytest-xdist, pytest-timeout, pytest-mock, pytest-repeat, pytest-randomly
  conftest.py 提供 OpenpilotPrefix 沙箱（重定向 /data/params、/dev/shm、日志）
  pytest marker: slow / tici / skip_tici_setup
  selfdrive/test/process_replay/  提供回放回归框架（ref_commit 锚点）

缺口（已核实）:
  selfdrive/carrot/ 下无任何 test_*.py（除 lidar_speed_test.py 一个孤立脚本）
  → CarrotPilot 专属逻辑当前零测试覆盖，§4.6 的测试全部需从零新建
  → 本预编译交付树无 .cc 源码，scons 全量 C++ 构建不可用
    → C++ libsafety 回归需走 pytest-cpp（依赖预编译 shared lib），
      或在完整源码树执行，本树只能跑 Python 层
```

### 6.2 分层验证策略（L0→L3）

每个修改项必须通过以下**全部**层级才可合入：

```
L0  静态     ruff check + mypy + ruff format --check
            确认无语法/类型/风格回归；确认 import 规则（TID251）未被破坏
L1  单元     pytest -n0 selfdrive/carrot/tests/  （新建于 §4.6）
            用 OpenpilotPrefix 沙箱隔离 params/shm，mock radar_state/params
L2  集成     进程回放 process_replay（修改 controls 层时强制）
            python3 selfdrive/test/process_replay/test_processes.py -j$(nproc)
            cat selfdrive/test/process_replay/diff.txt   与 ref_commit 基线比对
L3  实车/仿真
            仿真: source selfdrive/test/setup_xvfb.sh && pytest -s tools/sim/tests/test_metadrive_bridge.py
            实车: 按 §6.3 矩阵采集 CAN 日志，比对输出
```

**门禁规则**：L1 全绿 + L2 diff 在阈值内（controls 类修改）+ L3 场景验收达标，三者缺一不可。安全类（§1）额外要求 L3 含渗透项。

### 6.3 逐修改项的验证用例（可执行）

| 修改项 | L1 单元测试（`selfdrive/carrot/tests/`） | L2/L3 回归验收 |
|--------|-------------------------------------------|----------------|
| §2.1 OP-01 天桥 | `test_overpass_filter.py`：①slot 换绑场景 8 帧重分配，断言 `_should_filter_lead` 在 5 帧后返回 True（验证位置 key 修复）②静止非中心目标返回 False ③3s 超时清理 ④Track/dict 两输入路径一致性 | 回放过桥 log，断言对应帧 `radarState.leadOne.status=False` 且 MPC 无减速 |
| §2.4 OP-06 停止 | `test_stopping.py`：固定 `v_ego`/`stop_distance` 序列，断言 100→0 总停止距离 25±1.5m；断言 `jerk<3.0 m/s³`；断言 `e2eStopped` 时 `actual_stop_distance==0`（无蠕行） | process_replay 比对 `controlsd` 输出；实车 100→0 停距实测 |
| §2.2 OP-04 交叉验证 | `test_cross_validate.py`：一致目标（Δv<1.5,Δy<1.2,Δd<15）→True；ghost 目标（雷达无效）→False；速度不匹配→False | 回放含 lead log，断言无 ghost braking |
| §2.6 F-14 类型 | `test_obstacle_type.py`：v_abs 0/0.5/2/10 四档断言 pedestrian/two_wheel/None | 仿真 `tools/sim` 10-60km/h 两轮车场景 |
| §1.1 S-1 ZMQ | `test_zmq_auth.py`：无 token→`auth_failed`；错 token→`auth_failed`；正确 token+非白名单 cmd→`cmd_not_allowed`；断言代码无 `shell=True`（静态扫描） | `nc` 扫描 7710 无 RCE 向量；`grep shell=True carrot_man.py` 应 0 命中 |
| §1.3 S-3 Web | `test_web_whitelist.py`：白名单键写入成功；非白名单键写入被拒 + 日志记录；断言绑定地址为 `127.0.0.1` | `curl` 非白名单键→拒绝；`netstat` 确认仅 127.0.0.1:8088 |
| §1.2 S-2 FTP | 静态断言 `grep -rn Ekdrmsvkdlffjt7710` 全树 0 命中 | 代码搜索 |
| §1.4/1.5 S-4/S-5 | `test_udp_filter.py`：白名单 IP 包通过；非白名单 IP 包被丢 | `scapy` 从非白名单 IP 发包→丢弃 |
| §3.5 NVMe | `test_nvme.py`：`/dev/nvme0n1` 不存在→返回 `[]` 不抛异常 | 无 NVMe 设备 `hardwared` 无异常日志 |

### 6.4 回归安全网（防止修复引入新缺陷）

1. **基线快照**：修改前先跑 `process_replay` 生成 `ref_commit` 基线；每项修改后重跑，diff 超阈值即回滚。
2. **`selfdrive/car/tests/test_models.py`**：Car/扭矩相关改动（OP-05）后必跑，`-k test_hyundai` 保 Custin 指纹不回归。
3. **libsafety（C++，pytest-cpp）**：若改动触及 `pandad`/safety 限值，走 `opendbc/safety/tests/libsafety/` 验证安全限值未被放宽。
4. **静态门禁**：CI 跑 `tools/op.sh lint`（ruff + check_shebang + mypy + codespell），任何 P0/P1 提交前必须全绿。
5. **双分支对照**：对 controls 层修改，保留旧实现于 `LONGCONTROL_LEGACY` 参数开关，实车 A/B 对照 1 周后再删旧路径。

### 6.5 验证结论声明

- 本方案**尚未**在完整源码树跑通 L0-L3，因为当前预编译交付树缺 `.cc` 源码、无法全量 scons 构建；Python 层 L0/L1 可在本树执行，L2/L3 需在完整源码树或实车执行。
- 所有"验收标准"是**可判定的数值/日志断言**，非主观描述，便于逐条打钩。
- 合并前必须重跑 §6.0 的二次核实（行号可能漂移）。

---

## 7. 附录

### 7.1 与原方案对照表

| 原 ID | 原方案 | V2 审计判定 | 本方案修正 |
|-------|--------|-------------|-----------|
| OP-01 | `_is_overpass` 加 1 处过滤 | F-06 Critical（实际 6 处 + slot key 致过滤永不触发 + LeadDataV3 缺 dRel） | §2.1 统一 6 调用点 + 位置 key |
| OP-04 | 视觉-雷达距离匹配 | F-06 Critical（LeadDataV3 无 dRel） | §2.2 相对速度 + 横向位置匹配 |
| OP-05 | `substitute.toml` 加 Custin 条目 | F-01 Blocker（与 override.toml 冲突 RuntimeError） | §2.3 只保留 override.toml + 实车标定 |
| OP-06 | 停止分支加 floor | F-04 Blocker（乘法反馈 100Hz） | §2.4 解析等距减速 + jerk 限制 |
| OP-07 | GPU 功耗管理 | 可行但需补 modeld 锁频 | §3.1 |
| OP-08 | CPU 频率策略 | 可行 | §3.2 |
| OP-09 | 风扇曲线 | commit bb8c576 弱化 | §3.3 |
| OP-10 | 工程基线 | 可行 | §4 |

### 7.2 关键文件索引

| 文件 | 修改项 |
|------|--------|
| `selfdrive/carrot/carrot_man.py` | S-1, S-2, S-4 |
| `selfdrive/carrot/web_interface.py` | S-3 |
| `selfdrive/carrot/amap_navi.py` | S-5 |
| `selfdrive/controls/radard.py` | OP-01, OP-04, N-1 |
| `selfdrive/controls/lib/longcontrol.py` | OP-06 |
| `selfdrive/controls/lib/lateral_planner.py` | F-14 |
| `opendbc_repo/opendbc/car/hyundai/radar_interface.py` | N-1 |
| `opendbc_repo/opendbc/car/torque_data/override.toml` | OP-05 |
| `system/hardware/tici/hardware.py` | §3.1-§3.5 |
| `system/hardware/hardwared.py` | §3.6 |
| `common/params_keys.h` | §4.5 |

### 7.3 验收测试矩阵（L3 实车/回放）

> L0/L1 逐修改项用例见 §6.3；本表为 L3 场景验收。

| 测试场景 | 覆盖项 | 工具 / 判定断言 |
|----------|--------|------|
| 过桥（含 slot 重分配） | OP-01, N-1 | 回放 overpass log；断言 `leadOne.status=False` 且 MPC 无减速 |
| 红灯停车（100→0 km/h） | OP-06 | 实车 CAN；停距 25±1.5m，jerk<3.0，e2eStopped 无蠕行 |
| 两轮车近距离（10-60km/h） | F-14 | 仿真 `tools/sim`；躲避偏移 ≤0.55m 且平滑 |
| 视觉-雷达一致目标 | OP-04 | 回放含 lead log；无 ghost braking |
| ZMQ 7710 无认证请求 | S-1 | `nc` + `grep shell=True`；无 RCE 向量 |
| Web 8088 非白名单键 | S-3 | `curl` 非白名单键→拒绝；`netstat` 仅 127.0.0.1:8088 |
| 非白名单 UDP 源 | S-4/S-5 | `scapy` 非白名单 IP 发包→丢弃 |
| GPU 待机功耗 | §3.1 | `powertop` 待机降 ~2W，推理时性能不变 |
| CPU 满载温度 | §3.2, §3.3 | `stress-ng` + 风扇监控；75°C 不 throttle |

---

*本方案由 Agnes AI 生成，基于 16+ 份审计文档与 cp 分支代码交叉验证。§6.0 列出二次核实发现的 V1 偏差；所有行号基于 HEAD `24b7ff2`，合并前需重新确认。*
