#!/usr/bin/env python3
import os
import time
import numpy as np
from casadi import SX, vertcat, sin, cos
from openpilot.selfdrive.modeld.constants import ModelConstants
if __name__ == '__main__':
  from openpilot.third_party.acados.acados_template import AcadosModel, AcadosOcp, AcadosOcpSolver
else:
  from openpilot.selfdrive.controls.lib.lateral_mpc_lib.c_generated_code.acados_ocp_solver_pyx import AcadosOcpSolverCython

LAT_MPC_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(LAT_MPC_DIR, "c_generated_code")
JSON_FILE = os.path.join(LAT_MPC_DIR, "acados_ocp_lat.json")

X_DIM = 4
P_DIM = 2
COST_E_DIM = 3
COST_DIM = COST_E_DIM + 2
SPEED_OFFSET = 2.0
MODEL_NAME = 'lat'
ACADOS_SOLVER_TYPE = 'SQP_RTI'

# 保留32步预瞄，保证转弯路径完整
N = 32
T_IDXS_FULL = np.array(ModelConstants.T_IDXS)
SAFE_N = min(N, len(T_IDXS_FULL) - 1)
Tf = T_IDXS_FULL[SAFE_N]

# 【优化】降低阈值，更早识别路口右转/小半径弯道
last_nav_gain = 1.0
HEADING_DIFF_THRESH = 0.045
BIG_TURN_DIFF_THRESH = 0.080

# 路径条兜底缓存
last_valid_x_sol = np.zeros((N+1, X_DIM))
last_valid_u_sol = np.zeros((N, 1))

def gen_lat_model():
  model = AcadosModel()
  model.name = MODEL_NAME
  x_ego = SX.sym('x_ego')
  y_ego = SX.sym('y_ego')
  psi_ego = SX.sym('psi_ego')
  psi_rate_ego = SX.sym('psi_rate_ego')
  model.x = vertcat(x_ego, y_ego, psi_ego, psi_rate_ego)

  v_ego = SX.sym('v_ego')
  rotation_radius = SX.sym('rotation_radius')
  model.p = vertcat(v_ego, rotation_radius)

  psi_accel_ego = SX.sym('psi_accel_ego')
  model.u = vertcat(psi_accel_ego)

  x_ego_dot = SX.sym('x_ego_dot')
  y_ego_dot = SX.sym('y_ego_dot')
  psi_ego_dot = SX.sym('psi_ego_dot')
  psi_rate_ego_dot = SX.sym('psi_rate_ego_dot')
  model.xdot = vertcat(x_ego_dot, y_ego_dot, psi_ego_dot, psi_rate_ego_dot)

  f_expl = vertcat(
    v_ego * cos(psi_ego) - rotation_radius * sin(psi_ego) * psi_rate_ego,
    v_ego * sin(psi_ego) + rotation_radius * cos(psi_ego) * psi_rate_ego,
    psi_rate_ego,
    psi_accel_ego
  )
  model.f_impl_expr = model.xdot - f_expl
  model.f_expl_expr = f_expl
  return model

def gen_lat_ocp():
  ocp = AcadosOcp()
  ocp.model = gen_lat_model()
  ocp.dims.N = N
  ocp.cost.cost_type = 'NONLINEAR_LS'
  ocp.cost.cost_type_e = 'NONLINEAR_LS'

  Q = np.diag(np.zeros(COST_E_DIM))
  QR = np.diag(np.zeros(COST_DIM))
  ocp.cost.W = QR
  ocp.cost.W_e = Q

  y_ego, psi_ego, psi_rate_ego = ocp.model.x[1], ocp.model.x[2], ocp.model.x[3]
  psi_rate_ego_dot = ocp.model.u[0]
  v_ego = ocp.model.p[0]

  ocp.parameter_values = np.zeros((P_DIM, ))
  ocp.cost.yref = np.zeros((COST_DIM, ))
  ocp.cost.yref_e = np.zeros((COST_E_DIM, ))

  v_ego_offset = v_ego + SPEED_OFFSET
  ocp.model.cost_y_expr = vertcat(
    y_ego,
    v_ego_offset * psi_ego,
    v_ego_offset * psi_rate_ego,
    0.4 * v_ego_offset * psi_rate_ego_dot,
    psi_rate_ego_dot / (v_ego + 0.5)
  )
  ocp.model.cost_y_expr_e = vertcat(
    y_ego,
    v_ego_offset * psi_ego,
    v_ego_offset * psi_rate_ego
  )

  ocp.constraints.constr_type = 'BGH'
  ocp.constraints.idxbx = np.array([2, 3])
  # 【优化】小幅放宽转向角速度上限，提升右转执行响应
  ocp.constraints.ubx = np.array([np.radians(130), np.radians(105)])
  ocp.constraints.lbx = np.array([-np.radians(130), -np.radians(105)])

  x0 = np.zeros((X_DIM,))
  ocp.constraints.x0 = x0

  # 求解器配置保持不变
  ocp.solver_options.qp_solver = 'PARTIAL_CONDENSING_HPIPM'
  ocp.solver_options.hessian_approx = 'GAUSS_NEWTON'
  ocp.solver_options.integrator_type = 'ERK'
  ocp.solver_options.nlp_solver_type = ACADOS_SOLVER_TYPE
  ocp.solver_options.qp_solver_iter_max = 1
  ocp.solver_options.qp_solver_cond_N = 1
  ocp.solver_options.tf = Tf
  ocp.solver_options.shooting_nodes = T_IDXS_FULL[:N+1]
  ocp.code_export_directory = EXPORT_DIR
  return ocp

class LateralMpc:
  def __init__(self, x0=None):
    if x0 is None:
      x0 = np.zeros(X_DIM)
    self.solver = AcadosOcpSolverCython(MODEL_NAME, ACADOS_SOLVER_TYPE, N)
    self.nav_gain = 1.0
    self.reset(x0)

  def reset(self, x0=None):
    global last_nav_gain, last_valid_x_sol, last_valid_u_sol
    if x0 is None:
      x0 = np.zeros(X_DIM)
    self.x_sol = np.zeros((N+1, X_DIM))
    self.u_sol = np.zeros((N, 1))
    self.yref = np.zeros((N+1, COST_DIM))

    for i in range(N):
      self.solver.cost_set(i, "yref", self.yref[i])
    self.solver.cost_set(N, "yref", self.yref[N][:COST_E_DIM])

    for i in range(N+1):
      self.solver.set(i, 'x', np.zeros(X_DIM))
      self.solver.set(i, 'p', np.zeros(P_DIM))

    self.solver.constraints_set(0, "lbx", x0)
    self.solver.constraints_set(0, "ubx", x0)
    self.solver.solve()

    self.solution_status = 0
    self.solve_time = 0.0
    self.cost = 0
    last_nav_gain = 1.0
    last_valid_x_sol = self.x_sol.copy()
    last_valid_u_sol = self.u_sol.copy()

  def set_weights(self, path_weight, heading_weight, lat_accel_weight, lat_jerk_weight, steering_rate_weight,
                  is_u_turn=False, is_high_speed=False, v_kph=0.0, is_big_turn=False):
    # U型掉头：流畅循迹
    if is_u_turn:
      path_weight = 1.65
      heading_weight = 2.05
      lat_accel_weight = 0.85
      lat_jerk_weight = 0.60
      steering_rate_weight = 1.0
    # 大角度右转/急弯（重点强化）
    elif is_big_turn:
      path_weight = 1.85 * self.nav_gain
      heading_weight = 2.0 * self.nav_gain
      lat_accel_weight = 0.65
      lat_jerk_weight = 0.50
      steering_rate_weight = 0.80
    # 高速＞100km/h：优先稳定
    elif is_high_speed:
      path_weight = 1.15
      heading_weight = 1.30
      lat_accel_weight = 0.55
      lat_jerk_weight = 0.35
      steering_rate_weight = 1.7
    # 中低速 30~100km/h 常规弯道
    elif v_kph > 30:
      path_weight = 1.80 * self.nav_gain
      heading_weight = 2.05
      lat_accel_weight = 0.85
      lat_jerk_weight = 0.65
      steering_rate_weight = 1.40
    # 【核心优化】低速＜30km/h 城市路口/小半径右转（最强跟随）
    else:
      path_weight = 2.10 * self.nav_gain
      heading_weight = 1.80
      lat_accel_weight = 0.50
      lat_jerk_weight = 0.40
      steering_rate_weight = 0.60

    W = np.asfortranarray(np.diag([path_weight, heading_weight, lat_accel_weight, lat_jerk_weight, steering_rate_weight]))
    for i in range(N):
      self.solver.cost_set(i, 'W', W)
    self.solver.cost_set(N, 'W', W[:COST_E_DIM,:COST_E_DIM])

  def run(self, x0, p, y_pts, heading_pts, yaw_rate_pts, turn_y_pts=None):
    global last_nav_gain, last_valid_x_sol, last_valid_u_sol
    x0_cp = np.copy(x0)
    p_cp = np.copy(p)
    turn_active = (turn_y_pts is not None) and (len(turn_y_pts) > 0)
    if turn_active and len(turn_y_pts) > N+1:
      turn_y_pts = turn_y_pts[:N+1]

    self.solver.constraints_set(0, "lbx", x0_cp)
    self.solver.constraints_set(0, "ubx", x0_cp)
    self.yref[:,0] = turn_y_pts if turn_active else y_pts

    v_ego = p_cp[0, 0]
    v_kph = v_ego * 3.6
    is_high_speed = v_kph > 100

    # 航向偏差识别转弯
    heading_diff = np.max(np.abs(heading_pts)) if len(heading_pts) > 0 else 0.0
    is_big_turn = heading_diff > BIG_TURN_DIFF_THRESH

    # 动态导航增益
    if is_big_turn:
        target_gain = 1.40
    elif heading_diff > HEADING_DIFF_THRESH:
        target_gain = 1.20
    else:
        target_gain = 1.0

    # 导航激活 转弯额外增强
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_ACTIVE
        if NAV_ACTIVE and is_big_turn:
            target_gain *= 1.12
    except:
        pass

    # 【优化】加快增益响应，转弯即时生效，同时保留防抖
    self.nav_gain = 0.80 * last_nav_gain + 0.20 * target_gain
    last_nav_gain = self.nav_gain

    self.yref[:,1] = heading_pts * (v_ego + SPEED_OFFSET)
    self.yref[:,2] = yaw_rate_pts * (v_ego + SPEED_OFFSET)

    for i in range(N):
      self.solver.set(i, "yref", self.yref[i])
      self.solver.set(i, "p", p_cp[i])
    self.solver.set(N, "p", p_cp[N])
    self.solver.cost_set(N, "yref", self.yref[N][:COST_E_DIM])

    # 加载分场景权重
    self.set_weights(0,0,0,0,0,False,is_high_speed,v_kph,is_big_turn)

    t = time.monotonic()
    try:
      self.solution_status = self.solver.solve()
      self.solve_time = time.monotonic() - t

      tmp_x = np.zeros_like(self.x_sol)
      tmp_u = np.zeros_like(self.u_sol)
      for i in range(N+1):
        tmp_x[i] = self.solver.get(i, 'x')
      for i in range(N):
        tmp_u[i] = self.solver.get(i, 'u')

      # 有效性校验 & 更新兜底缓存
      if np.all(np.isfinite(tmp_x)) and np.all(np.isfinite(tmp_u)) and self.solution_status == 0:
        self.x_sol = tmp_x.copy()
        self.u_sol = tmp_u.copy()
        last_valid_x_sol = self.x_sol.copy()
        last_valid_u_sol = self.u_sol.copy()
      else:
        self.x_sol = last_valid_x_sol.copy()
        self.u_sol = last_valid_u_sol.copy()

      self.cost = self.solver.get_cost()
    except Exception:
      # 异常强制兜底，路径条不消失
      self.x_sol = last_valid_x_sol.copy()
      self.u_sol = last_valid_u_sol.copy()
      self.solution_status = -1
      self.solve_time = time.monotonic() - t
      self.cost = 0

if __name__ == "__main__":
  ocp = gen_lat_ocp()
  AcadosOcpSolver.generate(ocp, json_file=JSON_FILE)