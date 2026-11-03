## ⚠️ 법적 안내 / Legal Notice

🚫 대한민국 자동차관리법 개정안에 따라, 본 소프트웨어를 실제 차량에 장착하거나 주행에 사용하는 것은 법률에 위배될 수 있습니다.  
이 저장소에 있는 모든 소프트웨어는 **연구, 실험, 시뮬레이션 목적**으로만 제공됩니다.  
개발자는 본 소프트웨어의 실제 사용으로 인해 발생하는 **모든 법적 책임을 지지 않습니다.**

In accordance with the amended **Korean Motor Vehicle Management Act** (effective August 14, 2025),  
**modifying or installing software that affects the safe operation of a vehicle** is prohibited.

This software is provided **for research and educational use only**.  
The developer does **not take any responsibility** for real-world installation or usage.

**Carrotpilot에서 사용하는 차량(현대,기아)에 따라 Harness가 다릅니다..**
- CAN통신차량: Comma 정품 Harness, Camera에 연결
- CANFD-일반차량: Comma정품 Harness, Camera에 연결
- CANFD-HDA2(ADAS Module 장착)차량: 사제 Harness, ADAS Module에 연결
- 모든차량이 지원되는것이 아니니 반드시 확인바랍니다.
  
**In CarrotPilot, the harness used varies depending on the vehicle(HKG):**
* **CAN vehicles** Use the official Comma harness, connected to the camera.
* **CAN FD (standard) vehicles** Use the official Comma harness, connected to the camera.
* **CAN FD vehicles with HDA2 (ADAS module equipped)** Use an aftermarket harness, connected to the ADAS module.
* Please note that not all vehicles are supported.

---

## 🚗 库斯途 × Comma 3 高德协同领航定制分支 (`cp-custo-amap`)

本分支专为**北京现代库斯途 2021~2024 款（Hyundai Custin 1st Gen）**量身深度定制。结合现代原厂车机高德地图车机版与开源中继应用 [AmapNavi-Reborn](https://github.com/fds2003/AmapNavi-Reborn)，实现整车双向强实时协同领航与专属车辆动力学安全控制：

### 🌟 核心特性概览
* **高德地图双向毫秒级协同**：通过车载 Wi-Fi 局域网（UDP 4210/5510 探针握手，7706 下行 20Hz 81项遥测，7705 接收超车控制指令）；
* **三级超车风格与激光雷达 TTC 门禁**：支持激进 (1.8s) / 常规 (2.5s) / 保守 (3.5s) 超车风格，后方车辆快速逼近时刚性阻断，并在变道执行期持续复检；
* **紧急变道撤销与驾驶员接管**：车机下发 `CANCEL` 指令 50ms 内立即中止变道；方向盘物理反抗打盘下一帧瞬间交还人工控制；
* **现代库斯途专车动力学调优（设计目标，实现状态见 21 号修订版与 31 号审核意见）**：
  1. 帕里斯帝 NNFF 力矩映射 —— 已实现（substitute.toml:43）；
  2. 7座 MPV 平缓变道 S 曲线 / 0.08g / Jerk 限幅、150ms 前馈 —— 设计意图，代码中未实现；
  3. ret.startAccel = 1.0 —— Hyundai 平台全局默认值，非库斯途专属分支；
  4. 红灯停稳锁零 —— 代码条件与描述相反，未实现；
  5. 0x485 LFAHDA_MFC 仪表联动 —— 生成函数与报文 ID 属实，20Hz 频率与调用链未核实；
  6. Offroad CPU 大核下线属实；GPU 轨为强制开启（非释放），1.65W / 39℃ 无依据已撤回。

### 📚 库斯途专车文档库
* **[现代库斯途 Comma 3 全景技术架构终极手册](COMMA3_CUSTIN_MASTER_GUIDE.md)**
* **[高德协同领航技术设计与通信规范](docs/custin/COOPERATIVE_PILOT.md)**
* **[车辆动力学特性与专属调优规范](docs/custin/VEHICLE_DYNAMICS.md)**
* **[Comma 3 安装器原理与一键刷机协议](INSTALLER_GUIDE.md)**
* **[车机端配套开源工程 (AmapNavi-Reborn)](https://github.com/fds2003/AmapNavi-Reborn)**

---
<div align="center" style="text-align: center;">

<h1>carrotpilot</h1>

<h3>
  <a href="https://g4iwnl.gitbook.io/carrotpilot">Manual</a>
</h3>

![image](https://github.com/user-attachments/assets/4d80d256-7e66-4473-a289-04a50733b7e0)


<div align="center" style="text-align: center;">

<h1>openpilot</h1>

<p>
  <b>openpilot is an operating system for robotics.</b>
  <br>
  Currently, it upgrades the driver assistance system in 275+ supported cars.
</p>

<h3>
  <a href="https://docs.comma.ai">Docs</a>
  <span> · </span>
  <a href="https://docs.comma.ai/contributing/roadmap/">Roadmap</a>
  <span> · </span>
  <a href="https://github.com/commaai/openpilot/blob/master/docs/CONTRIBUTING.md">Contribute</a>
  <span> · </span>
  <a href="https://discord.comma.ai">Community</a>
  <span> · </span>
  <a href="https://comma.ai/shop">Try it on a comma 3X</a>
</h3>

Quick start: `bash <(curl -fsSL openpilot.comma.ai)`

![openpilot tests](https://github.com/commaai/openpilot/actions/workflows/selfdrive_tests.yaml/badge.svg)
[![codecov](https://codecov.io/gh/commaai/openpilot/branch/master/graph/badge.svg)](https://codecov.io/gh/commaai/openpilot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![X Follow](https://img.shields.io/twitter/follow/comma_ai)](https://x.com/comma_ai)
[![Discord](https://img.shields.io/discord/469524606043160576)](https://discord.comma.ai)

</div>

<table>
  <tr>
    <td><a href="https://youtu.be/NmBfgOanCyk" title="Video By Greer Viau"><img src="https://github.com/commaai/openpilot/assets/8762862/2f7112ae-f748-4f39-b617-fabd689c3772"></a></td>
    <td><a href="https://youtu.be/VHKyqZ7t8Gw" title="Video By Logan LeGrand"><img src="https://github.com/commaai/openpilot/assets/8762862/92351544-2833-40d7-9e0b-7ef7ae37ec4c"></a></td>
    <td><a href="https://youtu.be/SUIZYzxtMQs" title="A drive to Taco Bell"><img src="https://github.com/commaai/openpilot/assets/8762862/05ceefc5-2628-439c-a9b2-89ce77dc6f63"></a></td>
  </tr>
</table>


Using openpilot in a car
------

To use openpilot in a car, you need four things:
1. **Supported Device:** a comma 3/3X, available at [comma.ai/shop](https://comma.ai/shop/comma-3x).
2. **Software:** The setup procedure for the comma 3/3X allows users to enter a URL for custom software. Use the URL `openpilot.comma.ai` to install the release version.
3. **Supported Car:** Ensure that you have one of [the 275+ supported cars](docs/CARS.md).
4. **Car Harness:** You will also need a [car harness](https://comma.ai/shop/car-harness) to connect your comma 3/3X to your car.

We have detailed instructions for [how to install the harness and device in a car](https://comma.ai/setup). Note that it's possible to run openpilot on [other hardware](https://blog.comma.ai/self-driving-car-for-free/), although it's not plug-and-play.

### Branches
| branch           | URL                                    | description                                                                         |
|------------------|----------------------------------------|-------------------------------------------------------------------------------------|
| `release3`         | openpilot.comma.ai                      | This is openpilot's release branch.                                                 |
| `release3-staging` | openpilot-test.comma.ai                | This is the staging branch for releases. Use it to get new releases slightly early. |
| `nightly`          | openpilot-nightly.comma.ai             | This is the bleeding edge development branch. Do not expect this to be stable.      |
| `nightly-dev`      | installer.comma.ai/commaai/nightly-dev | Same as nightly, but includes experimental development features for some cars.      |

To start developing openpilot
------

openpilot is developed by [comma](https://comma.ai/) and by users like you. We welcome both pull requests and issues on [GitHub](http://github.com/commaai/openpilot).

* Join the [community Discord](https://discord.comma.ai)
* Check out [the contributing docs](docs/CONTRIBUTING.md)
* Check out the [openpilot tools](tools/)
* Read about the [development workflow](docs/WORKFLOW.md)
* Code documentation lives at https://docs.comma.ai
* Information about running openpilot lives on the [community wiki](https://github.com/commaai/openpilot/wiki)

Want to get paid to work on openpilot? [comma is hiring](https://comma.ai/jobs#open-positions) and offers lots of [bounties](https://comma.ai/bounties) for external contributors.

Safety and Testing
----

* openpilot observes [ISO26262](https://en.wikipedia.org/wiki/ISO_26262) guidelines, see [SAFETY.md](docs/SAFETY.md) for more details.
* openpilot has software-in-the-loop [tests](.github/workflows/selfdrive_tests.yaml) that run on every commit.
* The code enforcing the safety model lives in panda and is written in C, see [code rigor](https://github.com/commaai/panda#code-rigor) for more details.
* panda has software-in-the-loop [safety tests](https://github.com/commaai/panda/tree/master/tests/safety).
* Internally, we have a hardware-in-the-loop Jenkins test suite that builds and unit tests the various processes.
* panda has additional hardware-in-the-loop [tests](https://github.com/commaai/panda/blob/master/Jenkinsfile).
* We run the latest openpilot in a testing closet containing 10 comma devices continuously replaying routes.

Licensing
------

openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.

Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.

**THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
NO WARRANTY EXPRESSED OR IMPLIED.**

User Data and comma Account
------

By default, openpilot uploads the driving data to our servers. You can also access your data through [comma connect](https://connect.comma.ai/). We use your data to train better models and improve openpilot for everyone.

openpilot is open source software: the user is free to disable data collection if they wish to do so.

openpilot logs the road-facing cameras, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver-facing camera is only logged if you explicitly opt-in in settings. The microphone is not recorded.

By using openpilot, you agree to [our Privacy Policy](https://comma.ai/privacy). You understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.
