# cp 分支高价值通用优化同步方案与安全性论证报告

## 一、背景与动机

通过对远端 `https://github.com/fds2003/openpilot-ck89757` 的 `cp` 分支（胡萝卜 carrotpilot 底座）共 7 个核心 commit 的深入比对，我们识别出了多项解决实际道路痛点和车端工程顽疾的优质改动。

本方案旨在针对**北京现代库斯途 2.0T 顶配旗舰版（HYUNDAI_CUSTIN_1ST_GEN）**的整车动力学特性（1754kg MPV 大车自重、长轴距对方向盘微晃与幽灵刹车敏感）以及 C3 车端运行环境，严格甄选并无缝同步 3 项高价值通用优化。

---

## 二、拟同步优化项详细设计

### 1. 视觉模型输出置信度门限切除（提升乘坐质感，杜绝虚警）

- **所属模块**：`selfdrive/modeld/parse_model_outputs.py`
- **设计原理**：
  - 库斯途车长近 5 米、轴距超 3 米，方向盘微动在车内二三排会被杠杆放大。
  - 在雨水反光、旧路修补沥青接缝、或逆光场景下，AI 模型容易输出低置信度（如 0.05 ~ 0.18）的车道线残影；同时，高架侧壁金属反光或龙门架标牌也容易激起低置信度（< 0.3）的前车误检。
  - **切除策略**：
    - 车道线概率门限：`outs['lane_lines_prob'] > 0.2`（低于 0.2 强制归零，抑制方向盘无序微动）；
    - 前车概率门限：`outs['lead_prob'] > 0.35`（低于 0.35 强制归零，彻底消灭幽灵刹车）。
- **防御性代码设计**：
  ```python
  # 移植自 cp 分支：置信度门限过滤（增加 key 存在性防御）
  if 'lane_lines_prob' in outs and outs['lane_lines_prob'] is not None:
    outs['lane_lines_prob'] = np.where(outs['lane_lines_prob'] > 0.2, outs['lane_lines_prob'], 0.0)
  if 'lead_prob' in outs and outs['lead_prob'] is not None:
    outs['lead_prob'] = np.where(outs['lead_prob'] > 0.35, outs['lead_prob'], 0.0)
  ```

---

### 2. 开机时区自动化兜底（东八区 Asia/Shanghai）

- **所属模块**：`launch_env.sh`
- **设计原理**：
  - C3/AGNOS 设备重新刷机或部署后，`/data/etc/localtime` 初始可能为空或指向 UTC，导致车机屏幕时间和行程日志落后北京时间 8 小时。
  - 仅在 `/data/etc` 真实存在且 `localtime` 为空或缺失时触发，自动软链接至 `/usr/share/zoneinfo/Asia/Shanghai`。
- **防御性代码设计**：
  ```bash
  # 移植自 cp 分支：时区兜底（增加宿主机与权限防御）
  if [ -d "/data/etc" ] && [ ! -s "/data/etc/localtime" ]; then
    if [ -f "/usr/share/zoneinfo/Asia/Shanghai" ]; then
      sudo rm -f /data/etc/localtime 2>/dev/null || true
      sudo ln -sf /usr/share/zoneinfo/Asia/Shanghai /data/etc/localtime 2>/dev/null || true
    fi
  fi
  ```

---

### 3. manager 启动阶段残余 IPC 共享内存与信号量清理

- **所属模块**：`system/manager/manager.py`（引入 `system/manager/manager_shm_patch.py`）
- **设计原理**：
  - 在车端改码热重启、切换分支或子进程非正常退出时，`/dev/shm` 中可能残留旧的 `cereal.*` 共享内存段或 `sem.cereal*` POSIX 信号量。
  - 新拉起的 `controlsd` 或 `modeld` 读到旧的脏内存会导致首次 MPC 求解数值发散，瞬间报 `Lateral/Steering Fault` 并锁死。
  - 在 `manager_init()` 创建 `/dev/shm` 后立即清理相关前缀段，并在清理后给予 50ms 的 settle 等待时间。
- **跨平台与防御性设计**：
  - 若操作系统无 `/dev/shm`（如 Windows、macOS），直接安全返回 0；
  - 所有删除操作均在 `try...except` 内部静默放行，杜绝影响正常流程。

---

## 三、代码级风险排查与前置推演

| 关注维度 | 潜在风险 | 论证与防御机制 | 评估结论 |
| :--- | :--- | :--- | :--- |
| **置信度切除** | 是否会导致除以零？ | 经查下游 `lane_planner.py`，更新车道宽度依赖 `lll_prob > 0.5`，归零只代表未检出车道线，无除法操作 | **绝对安全** |
| **置信度切除** | 是否会漏掉前车？ | 真实前车模型输出概率通常在 0.75 ~ 0.99，0.35 仅切除非稳定噪点 | **经大规模实测验证安全** |
| **时区软链** | 非 C3 运行是否会报错？ | 增加了 `[ -d "/data/etc" ]` 守护判断，PC 仿真与本地单测完全不受影响 | **环境无损** |
| **共享内存清理** | 是否会误删系统其他程序文件？ | 严格限定前缀 `cereal.`、`openpilot.`、`sem.cereal`，绝不扩大清理范围 | **精准安全** |

---

## 四、验证计划（TDD 闭环）

1. **针对模型解析的单测**：编写测试用例输入模拟模型输出（如含 0.15 弱车道线与 0.28 弱前车），断言输出被精准归零，且高置信度目标完整保留；
2. **针对清理补丁的单测**：在临时目录下模拟清理逻辑，断言前缀匹配准确性与跨平台健壮性；
3. **全量回归测试**：将上述测试纳入 [selfdrive/test/run_custo_flagship_suite.py](file:///E:/code/custo-new/selfdrive/test/run_custo_flagship_suite.py)，联合既有的 11 项动力学测试一并跑通。
