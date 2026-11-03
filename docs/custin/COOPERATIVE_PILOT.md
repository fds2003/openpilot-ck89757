# Comma 3 库斯途高德协同领航技术设计与通信规范

> **适配分支**：`cp-custo-amap`  
> **协同对端**：[AmapNavi-Reborn (现代库斯途车机端)](https://github.com/fds2003/AmapNavi-Reborn)  
> **通信介质**：车载局域网 (手机无线热点或车载 Wi-Fi，无需外网流量)

---

## 一、双端网络拓扑与端口矩阵

```
 ┌─────────────────────────────────────────────────────────────┐
 │       车机端：北京现代库斯途 (Android 4.4.3 / 160 dpi)      │
 │  • 运行高德地图车机版 (标准广播源) + AmapNavi-Reborn        │
 │  • 监听端口: UDP 7706 (收遥测) / UDP 5510 (收探针回包)      │
 │  • 发送目标: UDP 7705 (发控制指令) / UDP 4210 (发发现广播)  │
 └──────────────────────────────┬──────────────────────────────┘
                                │ 车载 Wi-Fi 局域网
 ┌──────────────────────────────▼──────────────────────────────┐
 │           C3 端：Comma 3 / Comma 3X (SDA845 / AGNOS)        │
 │  • 运行 openpilot cp-custo-amap 分支                        │
 │  • 监听端口: UDP 7705 (收控制指令) / UDP 4210 (收发现广播)  │
 │  • 发送目标: UDP 7706 (向车机推遥测) / UDP 5510 (回探针应答)│
 └─────────────────────────────────────────────────────────────┘
```

---

## 二、核心通信协议契约

### 1. 设备发现与动态 IP 学习 (UDP 4210 / 5510)
- 车机启动时向 `255.255.255.255:4210` 广播探针：`{"cmd":"discover","port":5510}` 及 `c3_ping`；
- C3 端 `_discovery_responder_thread` 监听 4210，收到探针后：
  1. 动态探测自身在当前局域网内的真实 IP（如 `192.168.43.128`）；
  2. 向车机回送 `c3_pong` 响应包：
     ```json
     {
       "resp": "c3_pong",
       "device": "comma3",
       "status": "ready",
       "device_id": "c3",
       "auth": true,
       "ip": "192.168.43.128",
       "version": "openpilot-cp-custo"
     }
     ```
  3. 登记车机 IP 至活跃客户端列表，激活后续遥测与指令的双向单播通道。

### 2. 感知融合遥测下行 (UDP 7706, 20Hz 定频)
C3 每 50ms 向车机单播 81 项高精感知与车辆状态数据：
```json
{
  "active": true,
  "v_ego": 27.78,
  "v_ego_kph": 100.0,
  "steer_angle": -0.85,
  "gas_press": false,
  "brake_press": false,
  "engaged": true,
  "v_cruise": 100,
  "lead1": true,
  "drel": 42.5,
  "vrel": -1.2,
  "left_blindspot": false,
  "right_blindspot": false,
  "lidar_behind_vdist_time": 4.25,
  "lb_drel": 35.0,
  "rb_drel": 40.0
}
```

### 3. 上行控制指令与超车触发 (UDP 7705, 事件触发)
车机根据高德地图车道建议与用户触控向 C3 发送指令：
```json
{
  "cmd": "OVERTAKE",
  "arg": "LEFT",
  "direction": "LEFT",
  "param": 1,
  "seq": 1024,
  "index": 1024,
  "v_cruise": 100,
  "blinker": 1,
  "timestamp": 1730592000000
}
```
* `param`：三级超车风格（`0`: 激进 TTC $\ge 1.8\text{s}$, `1`: 常规 TTC $\ge 2.5\text{s}$, `2`: 保守 TTC $\ge 3.5\text{s}$）；
* `cmd: "CANCEL"` / `"CANCEL_LANE_CHANGE"`：紧急撤销变道指令，C3 在 50ms 内立即中止转向并回正车身。

---

## 三、安全看门狗与功能安全设计 (Failsafe)

1. **变道执行期持续 TTC 复检**：
   在 `desire_helper.py` 的变道切入阶段（`laneChangeStarting`），系统持续以 20Hz 复检后方激光雷达时距。若后方突然出现高速急追车辆（$\text{TTC} < \text{门限}$），系统在尚未完全跨线前立即中止变道并拉回原车道；
2. **驾驶员接管绝对最高优先级 (20ms 熔断)**：
   变道全流程中，方向盘力矩传感器检测到反抗打盘时，系统在下一帧无条件注销变道状态，交还人工控制；
3. **通信离线安全降级**：
   若随车 Wi-Fi 断开超过 1.0 秒，系统自动回退至标准“单车道自适应巡航与车道居中保持”，绝不引发任何非预期转向。
