# Repository Guidelines

## Project Overview

**openpilot** is an open-source operating system for robotics and an advanced Level 2 driver assistance system (ADAS). It performs automated lane centering, adaptive cruise control (longitudinal control), automated lane changes, and vision-based driver attention monitoring.

**carrotpilot** (this repository: `openpilot-ck89757`, branch `cp`, remote `https://github.com/fds2003/openpilot-ck89757.git`, HEAD commit `24b7ff2`) is an extended fork designed for international and domestic market vehicles (predominantly Hyundai, Kia, and Genesis — HKG), with full platform support for the **Hyundai Custin 1st Gen** (`HYUNDAI_CUSTIN_1ST_GEN`). Key enhancements include:
- Domestic navigation telemetry integration (Amap / 高德地图 over UDP, CarrotMan companion app).
- Instrument cluster lighting (`LFAHDA_MFC` packet injection for Hyundai dash lane lines and steering wheel icon).
- Enhanced lateral safety: Model confidence filtering, 82% half-lane-width departure pullback (`DEVIATION_CORRECT_STEP = 0.22m`), 0.55m two-wheeler/pedestrian avoidance, and cornering speed smoothing.
- Longitudinal smoothness: Anti-creeping at standstill (`e2eStopped` lock to 0m), overpass/gantry radar filtering (`_is_overpass`), softened MPC jerk penalties, lead speed clamping, and green-light minimum speed floor (`90%`).
- System lifecycle stability: Startup shared memory cleanup (`manager_shm_patch.py`) and boot timezone fallback (`Asia/Shanghai`).

### Execution Targets
- **Embedded Device (comma 3 / 3X)**: Architecture `larch64` (`aarch64` running AGNOS, comma's Ubuntu-based automotive OS on Qualcomm Snapdragon 845 / QCOM2). Target Python runtime is Python 3.11.4 (`/usr/local/pyenv/versions/3.11.4/bin/python3`).
- **Workstation / CI**: Linux `x86_64` (Ubuntu 24.04 LTS), Linux `aarch64`, or macOS `Darwin` (simulation, log replay).
- **Windows is NOT a supported execution target**: SCons asserts Unix `uname -m`, directory symlinks degrade to plaintext files on NTFS, and linting/launch scripts require POSIX bash.

### Prebuilt Delivery Distribution State
- **`.cc` Count is 0 across the entire repository**: All original C++ `.cc` source files were stripped in this distribution tree. Prebuilt ELF binaries are already provided (55 ELFs whole tree / 36 project tree).
- **Surviving Components**: 1,376 `*.py` files, Cython sources (`.pyx` and generated `.cpp`), 714 C/C++ headers (`*.h`), 150 DBC files, and prebuilt ELF binaries.
- **Development Consequence**: SCons cannot build native C++ binaries from scratch in this workspace. Day-to-day development and algorithmic tuning take place on the **Python and Cython layers**.

---

## Architecture & Data Flow

```
                                    +--------------------+
                                    |    Sensor Inputs   |
                                    | Cameras, IMU, GPS  |
                                    +---------+----------+
                                              |
                          Frames via VisionIPC| IMU/GPS via msgq
                                              v
+------------------+             +------------+-----------+
|  User Interface  |             |      Perception        |
|  selfdrive/ui    |<------------|  camerad, sensord,     |
|  Qt5/QML/NanoVG  |             |  ubloxd, modeld        |
+------------------+             +------------+-----------+
         ^                                    |
         | SubMaster(modelV2, carState...)    | Vision & EKF state
         |                                    v
+--------+---------+             +------------+-----------+
|    Settings      |             |   State & Planning     |
|  common/params   |             | locationd, rednose EKF,|
| (Persistent KV)  |             | plannerd (MPC solver)  |
+------------------+             +------------+-----------+
         |                                    |
         | Params                             | Path & speed plan
         v                                    v
+------------------+             +------------+-----------+
| System Manager   |             |   Vehicle Controls     |
| system/manager   |             | controlsd (100 Hz loop)|
| process supervisor             +------------+-----------+
+------------------+                          |
                                              | sendcan (Actuators)
                                              v
                                 +------------+-----------+
                                 |  Panda Safety Firewall |
                                 |  pandad / C safety lib |
                                 +------------+-----------+
                                              |
                                              v
                                       Vehicle CAN Bus
```

### IPC & Messaging Core (`cereal`)
- Inter-process communication uses **Cap'n Proto** binary serialization paired with **msgq** (lock-free POSIX shared memory ring buffer) and **VisionIPC** (raw camera frame buffers).
- All message types inherit from the polymorphic `Event` union inside `cereal/log.capnp`. Every event provides:
  - `logMonoTime`: 64-bit nanosecond monotonic timestamp.
  - `valid`: Boolean indicating data validity.
- **Strict SI Units**: All physical quantities use SI units ($m$, $m/s$, $m/s^2$, $rad$, $rad/s$) unless explicitly suffixed (e.g., `Deg`, `Kph`).

### CarrotPilot Extension Surface
1. **Cap'n Proto Custom Slots**: Reuses upstream extension slots to maintain log replay compatibility:
   - `customReserved0` → `carrotMan` (`cereal/log.capnp:2695`, defined in `cereal/custom.capnp:14-55`): navigation cues, speed camera warnings, road limits, ATC turn metadata.
   - `customReserved1` → `amapNavi` (`cereal/log.capnp:2696`, defined in `cereal/custom.capnp:57-73`): blind spot radar flags, lane status, ultrasonic/LiDAR distances.
2. **External Navigation & Telemetry Channels**:
   - UDP **7706** (recv) / **7705** (broadcast): CarrotMan companion app protocol.
   - UDP **12345**: KISA / T-Map / Waze text protocol (`key:value/`).
   - ZMQ REP **`tcp://*:7710`**: Remote command & status channel.
   - HTTP **8088**: Web interface (`selfdrive/carrot/web_interface.py`).
3. **Core Algorithmic Adaptations on `cp`**:
   - **Perception Confidence Filters** (`selfdrive/modeld/parse_model_outputs.py:103,108`): Zeroes out `lane_lines_prob <= 0.2` and `lead_prob <= 0.35` to eliminate road surface reflection jitter and ghost braking.
   - **Lane Departure Correction** (`selfdrive/controls/lib/lane_planner_2.py:290-302`): Triggers a 22 cm/frame corrective pullback (`DEVIATION_CORRECT_STEP = 0.22m`) when lateral displacement exceeds 82% of half-lane width (`DEVIATION_NORM_THRESH = 0.82`).
   - **Two-Wheeler / Pedestrian Avoidance** (`lane_planner_2.py` & `lateral_planner.py`): In the 10–60 km/h speed window, detects right-side near targets (lateral -0.3 to 1.6m, longitudinal <25m) and applies up to `0.55m` leftward offset with first-order smoothing (`alpha = 0.12`).
   - **Radar Overpass Filter** (`selfdrive/controls/radard.py:485-555`): `_is_overpass` tracks stationary, centered targets across 5+ frames to suppress false deceleration under overhead bridges and sign gantries.
   - **Longitudinal MPC & Stopping** (`long_mpc.py` & `carrot_functions.py`): Softens jerk penalties (`J_EGO_COST = 4.3`, `jerk_factor *= 0.78`), clamps cruise targets to lead vehicle speed with `vRel > -1.0` guard, and forces `actual_stop_distance = 0.0` upon `e2eStopped` to eliminate red-light creep.

---

## Key Directories

| Directory | Purpose |
| :--- | :--- |
| `cereal/` | Cap'n Proto messaging schema definitions (`log.capnp`, `car.capnp`, `custom.capnp`), service registry (`services.py`), and generated Python bindings |
| `common/` | Foundational utilities: `Params` KV store (`params.py`, `params_pyx.pyx`), `Ratekeeper`, `swaglog` logging, filter utilities |
| `selfdrive/carrot/` | **CarrotPilot core**: `carrot_serv.py` (telemetry/speed logic), `amap_navi.py` (navigation ingest), `carrot_man.py` (UDP/ZMQ daemon), `carrot_functions.py` (`CarrotPlanner`), `config.py` (`UnifiedParams`), `web_interface.py` |
| `selfdrive/controls/` | Core vehicle control loops: `controlsd.py` (100 Hz), `plannerd.py` (20 Hz), `radard.py`, lateral/longitudinal MPC solvers (`lib/longitudinal_mpc_lib/`, `lib/lane_planner_2.py`) |
| `selfdrive/car/` | Vehicle daemon `card.py`, cruise control state, brand ports interface |
| `opendbc_repo/opendbc/` | Vehicle CAN DBC files, brand controllers (including HKG `hyundai/`), torque parameters (`torque_data/override.toml`), and safety code |
| `selfdrive/modeld/` | Neural network execution wrappers (TinyGrad driving model runners) and parser (`parse_model_outputs.py`) |
| `selfdrive/ui/` | Qt5 / QML / NanoVG dashboard, HUD rendering, prebuilt UI binary (`ui`) |
| `selfdrive/locationd/` | Sensor fusion, PoseKalman EKF (`locationd.py`), camera calibration (`calibrationd.py`), parameter learning (`paramsd.py`) |
| `system/manager/` | Supervisor daemon: `manager.py`, `process_config.py`, startup shared memory cleanup (`manager_shm_patch.py`), build runner (`build.py`) |
| `system/hardware/tici/` | Comma 3 hardware platform definitions, power management, thermal governance |
| `tools/` | Developer tools: `replay` (drive log replay), `cabana` (CAN reverse-engineering), `sim` (MetaDrive bridge) |

---

## Development Commands

### Environment Setup
All imports assume the **repository root is on `PYTHONPATH`** so that the `openpilot` namespace resolves cleanly:

```bash
# Export paths and enforce warning checks
export PYTHONPATH=$PWD
export PYTHONWARNINGS=error

# Synchronize locked dependencies via uv
tools/install_python_dependencies.sh
# or manually:
uv sync --frozen --all-extras
source .venv/bin/activate
```

### Static Analysis & Linting
```bash
# Fast lint check (Ruff + basic checks, skips slow mypy and codespell passes)
tools/op.sh lint --fast

# Complete lint suite (Ruff, check_shebang, check_large_files, mypy, codespell)
scripts/lint/lint.sh
# or via op helper:
tools/op.sh lint

# Run Ruff linter directly
ruff check . --quiet

# Check code formatting (2 spaces, quote preservation)
ruff format --check
# Format files in-place
ruff format

# Static type analysis with mypy
mypy common selfdrive system tools
```

### Running Daemons Standalone
```bash
# Launch full supervisor (starts all managed daemons based on offroad/onroad state)
python3 system/manager/manager.py

# Run controlsd standalone for debugging
python3 selfdrive/controls/controlsd.py

# Launch Qt on-device UI binary
./selfdrive/ui/ui

# Launch MetaDrive simulator bridge
source selfdrive/test/setup_xvfb.sh
source selfdrive/test/setup_vsound.sh
python3 tools/sim/run_bridge.py
```

### SCons Build Commands (Reference)
```bash
# Standard compilation across all available CPU cores
scons -j$(nproc)

# Device build with progress UI and core count throttling
python3 system/manager/build.py

# Generate compile_commands.json for clangd/LSP
scons -j$(nproc) --compile_db
```
*(Note: As described in Prebuilt Delivery Distribution State, full C++ rebuilding from source will fail due to absent `.cc` files; build commands apply when compiling Cython extensions or working on full source trees).*

---

## Code Conventions & Common Patterns

### Formatting & Line Endings
- **Strictly 2 Spaces Indentation**: Python (`*.py`), Cython (`*.pyx`, `*.pxd`), C++, and JSON files MUST use **2 spaces** per indentation level (`.editorconfig`, `pyproject.toml:204`). Do **NOT** use 4 spaces.
- **Line Length**: Max 160 characters (`pyproject.toml:224`).
- **Quote Style**: Preserved as authored (`[tool.ruff.format] quote-style = "preserve"`).
- **Line Endings**: Unix LF (`\n`) strictly required. CRLF line endings are forbidden (`core.autocrlf=false`).

### Naming Conventions
- **Python**: `snake_case` for functions, variables, and module filenames; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants.
- **C++**: `camelCase` for methods and member variables; `PascalCase` for classes and structs.
- **Cap'n Proto Fields**: `camelCase` following Cap'n Proto standard. Non-SI fields MUST include their unit suffix (e.g., `steeringAngleDeg`, `vEgoKph`).

### Banned APIs & Import Rules (`TID251`)
Defined in `pyproject.toml:240-249`. Unqualified imports of top-level modules are forbidden:
- ❌ `import selfdrive.x` / `from common import params`
- ✅ `import openpilot.selfdrive.x` / `from openpilot.common.params import Params`
- ❌ `import unittest` / `pytest.main`
- ✅ Use `pytest` for all test execution.

### IPC & PubSub Patterns
```python
from cereal import messaging

# Subscribing to messages in a loop
sm = messaging.SubMaster(['carState', 'modelV2', 'controlsState', 'carrotMan'])
while True:
  sm.update(100) # 100 ms timeout
  if sm.updated['modelV2']:
    path_plan = sm['modelV2'].position

# Publishing messages
pm = messaging.PubMaster(['customReserved0'])
msg = messaging.new_message('customReserved0')
msg.customReserved0.active = True
pm.send('customReserved0', msg)
```

### State Management (`Params` vs. `UnifiedParams`)
1. **`Params` (`openpilot.common.params`)**:
   - C++/Cython persistent key-value store targeting `/data/params` (or memory-backed `/dev/shm/params`).
   - Keys are strictly validated against `common/params_keys.h`. Accessing undefined keys raises `UnknownKeyName`.
   ```python
   from openpilot.common.params import Params
   params = Params()
   params.put_bool("OpenpilotEnabledToggle", True)
   is_enabled = params.get_bool("OpenpilotEnabledToggle")
   ```
2. **`UnifiedParams` (`openpilot.selfdrive.carrot.config`)**:
   - Singleton providing dynamic key-value access for CarrotPilot toggles, safely falling back to `selfdrive/carrot/nav_params.json` when a key is not present in the strict C++ params schema.
   ```python
   from openpilot.selfdrive.carrot.config import UnifiedParams
   u_params = UnifiedParams()
   val = u_params.get_int("AutoTurnControl", 0)
   ```

### Real-Time Determinism (`Ratekeeper`)
- High-frequency loops must use `Ratekeeper` to prevent CPU starvation and monitor execution lag:
  ```python
  from openpilot.common.realtime import Ratekeeper
  rk = Ratekeeper(100.0, print_delay_threshold=None) # 100 Hz
  while True:
    step()
    rk.monitor_time()
  ```

### Non-blocking Telemetry (`cloudlog`)
- Control loops must never perform blocking disk I/O. Structured logging is routed non-blockingly via `cloudlog` over ZeroMQ IPC:
  ```python
  from openpilot.common.swaglog import cloudlog
  cloudlog.warning("Event detected without blocking control cycle")
  ```

---

## Important Files

| File | Significance |
| :--- | :--- |
| `launch_chffrplus.sh` | Main device startup script: executes timezone fallback (`Asia/Shanghai`), overlay staging, environment initialization, and invokes `manager.py` |
| `launch_openpilot.sh` | Entrypoint setting API/Athena endpoints (`konik.ai` / `carrotpilot.app`) and Mapbox tokens |
| `launch_env.sh` | Sets platform thread limits (`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`) to prevent core starvation |
| `system/manager/manager.py` | Main process supervisor orchestrating daemon lifecycles and health monitoring |
| `system/manager/process_config.py` | Declarative process manifest defining execution triggers (`always_run`, `only_onroad`, `only_offroad`) |
| `system/manager/manager_shm_patch.py` | Sanitizes `/dev/shm` shared memory and POSIX semaphores on boot to prevent race faults |
| `selfdrive/controls/controlsd.py` | 100 Hz hard real-time vehicle control loop entrypoint |
| `selfdrive/controls/plannerd.py` | 20 Hz trajectory planning loop incorporating lateral and longitudinal MPC solvers |
| `selfdrive/carrot/carrot_man.py` | Master CarrotPilot telemetry daemon managing UDP/ZMQ networking and companion integration |
| `opendbc_repo/opendbc/car/hyundai/values.py` | Vehicle platform specs, ABS ECU fingerprints, and CAN bus identifiers (`HYUNDAI_CUSTIN_1ST_GEN`) |
| `opendbc_repo/opendbc/car/hyundai/interface.py` | Hyundai vehicle interface setting `startAccel = 1.0` and `SEND_LFA` camera detection |
| `opendbc_repo/opendbc/car/hyundai/hyundaican.py` | Generates CAN packets (`create_lfahda_mfc` for dash steering wheel and lane icons) |
| `cereal/log.capnp` & `custom.capnp` | Primary Cap'n Proto messaging definitions including CarrotPilot `carrotMan` and `amapNavi` |
| `pyproject.toml` & `uv.lock` | Python environment requirements, Ruff linting rules, and pytest configurations |

---

## Runtime/Tooling Preferences

- **Python Runtime**: Python 3.11 / 3.12 (`requires-python = ">=3.11, <3.13"`). Device runs Python 3.11.4 in pyenv (`/usr/local/pyenv/versions/3.11.4/bin/python3`).
- **Package Manager**: **`uv`** (Astral). Dependencies are declared in `pyproject.toml` and resolved in `uv.lock`.
- **C/C++ Compilers**: **Clang / Clang++** (`CFLAGS = -std=gnu11`, `CXXFLAGS = -std=c++1z` [C++17]).
- **Build System**: **SCons** exclusively. Do NOT introduce CMake, Makefiles, or secondary build runners.
- **SCons Cache Path**: Device uses `/data/scons_cache`; PC / CI uses `/tmp/scons_cache`.
- **No Node.js / Bun Runtime**: The core repository does not use JavaScript or TypeScript runtimes.

---

## Testing & QA

### Test Frameworks & Isolation
- **Python**: `pytest` utilizing `pytest-xdist` for parallelism (`-n auto --dist=loadgroup`).
- **C++**: `Catch2` (compiled via SCons; bridged to pytest via `pytest-cpp`).
- **Test Sandboxing (`OpenpilotPrefix`)**: Defined in `openpilot.common.prefix`. Every test runs within a randomized 15-character UUID sandbox redirecting `/data/params`, logs, and `/dev/shm` IPC paths, ensuring zero collision with active daemons or parallel workers.
- **Root Fixture Behavior (`conftest.py`)**:
  - Automatically seeds `random.seed(0)`.
  - Snapshots and restores environment variables (`clean_env`).
  - Calls `manager_cleanup()` after each test to terminate child processes.
  - Automatically skips `tici`-marked tests on PC environments.

### Test Execution Commands
```bash
# Run fast unit tests (excluding slow markers)
MAX_EXAMPLES=1 pytest -m 'not slow'

# Run a single test file / test case without xdist
pytest -p no:randomly -n0 -s selfdrive/car/tests/test_models.py -k "test_hyundai"

# Run car model interface & fingerprinting regression tests (sharded across CI jobs)
NUM_JOBS=4 JOB_ID=0 pytest selfdrive/car/tests/test_models.py

# Process replay regression (standalone script; checks outputs against ref_commit)
python3 selfdrive/test/process_replay/test_processes.py -j$(nproc)
# Review replay diffs:
cat selfdrive/test/process_replay/diff.txt

# Run UI translation verification
source selfdrive/test/setup_xvfb.sh
QT_QPA_PLATFORM=offscreen ./selfdrive/ui/tests/test_translations

# Run UI screenshot regression runner
source selfdrive/test/setup_xvfb.sh
python3 selfdrive/ui/tests/test_ui/run.py

# Run MetaDrive simulator closed-loop bridge test
source selfdrive/test/setup_xvfb.sh
source selfdrive/test/setup_vsound.sh
CI=1 pytest -s tools/sim/tests/test_metadrive_bridge.py
```

### Mocking & Simulation Environments
- **Virtual Display & Audio**: Graphical and audio tests must source `selfdrive/test/setup_xvfb.sh` (`Xvfb :99` at 2160x1080) and `selfdrive/test/setup_vsound.sh` (virtual PulseAudio null sink).
- **Panda Safety Emulation (`libsafety`)**: `opendbc/safety/tests/libsafety/libsafety_py.py` wraps compiled panda safety C code in a CFFI interface, allowing validation of vehicle safety limits without physical hardware.
- **Process Replay Reference Commit**: `selfdrive/test/process_replay/ref_commit` anchors the regression baseline. Any deliberate algorithmic change requiring baseline updates must be verified with a full, unfiltered replay run via `--update-refs`.
