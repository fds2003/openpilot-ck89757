# 北京现代库斯途 Comma 3 智能领航专车文档库

本目录汇总了北京现代库斯途（Hyundai Custin 2021~2024 款）在 Comma 3 / Comma 3X（分支: `cp-custo-amap`）上的全套专车级技术文档与操作指南：

---

## 📚 专车核心文档索引

1. **[现代库斯途 Comma 3 全景技术架构终极手册](../../COMMA3_CUSTIN_MASTER_GUIDE.md)**  
   * 芯片级实测报告 (SDA845 / 4GB RAM / 64GB UFS / Panda STM32)；
   * 车身物理参数与现代 CAN 协议 DBC 配置；
   * 12 项专车动力学深度调校与日常单行监控命令。

2. **[高德协同领航技术设计与通信规范](COOPERATIVE_PILOT.md)**  
   * UDP 4210/5510 探针自动发现与动态 IP 学习；
   * UDP 7706 20Hz 遥测下行与 UDP 7705 指令上行契约；
   * 三级超车决策与激光雷达 TTC 持续安全门禁机制。

3. **[车辆动力学特性与专属调优规范](VEHICLE_DYNAMICS.md)**（2026-11-03 二次复核，基线 1daa094；详见 31 号审核意见 / 33 号修订记录及其更正声明）  
   * 已实现：帕里斯帝 NNFF 力矩映射、mass=1754 / SEND_LFA、CUSTIN 专属 steerActuatorDelay=0.15 与 startAccel=1.0、7座 MPV 5.0s 平缓变道（16aff86）；
   * 仍未实现：红灯停稳锁零（条件相反）、150ms 前馈、0.08g / Jerk 限幅；
   * 已撤回：1.65W 温控数字与 GPU 轨"释放"描述；override.toml 的 CUSTIN 条目已被 39ded30 删除；
   * 原厂全液晶仪表盘 0x485 联动（部分实现）。

4. **[安装器原理与一键刷机协议](../../INSTALLER_GUIDE.md)**  
   * Comma 3 ELF 格式安装器原理与一键刷机指引。

5. **[车机端开源中继协同工程 (AmapNavi-Reborn)](https://github.com/fds2003/AmapNavi-Reborn)**  
   * 运行于库斯途车机 960x1280 竖屏上的轻量级中继 App。
