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
# 保留原32步长预瞄，保证转弯路径完整不截断
N = 32
# 安全获取时间序列，防止索引越界
T_IDXS_FULL = np.array(ModelConstants.T_IDXS)
# 边界截断：严格匹配数组下标 0 ~ len(T_IDXS_FULL)-1
SAFE_N = min(N, len(T_IDXS_FULL) - 1)
Tf = T_IDXS_FULL[SAFE_N]
# 新增全局：航向增益平滑缓存、大弯判定阈值、求解兜底缓存
last_nav_gain = 1.0
HEADING_DIFF_THRESH = 0.08
BIG_TURN_DIFF_THRESH = 0.15
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
  # 放大最大转向角度 & 转向角速度（保留原有配置）
  ocp.constraints.ubx = np.array([np.radians(130), np.radians(100)])
  ocp.constraints.lbx = np.array([-np.radians(130), -np.radians(100)])
  x0 = np.zeros((X_DIM,))
  ocp.constraints.x0 = x0
  # 求解器配置（保留原有迭代逻辑）
  ocp.solver_options.qp_solver = 'PARTIAL_CONDENSING_HPIPM'
  ocp.solver_options.hessian_approx = 'GAUSS_NEWTON'
  ocp.solver_options.integrator_type = 'ERK'
  ocp.solver_options.nlp_solver_type = ACADOS_SOLVER_TYPE
  ocp.solver_options.qp_solver_iter_max = 1
  ocp.solver_options.qp_solver_cond_N = 1
  ocp.solver_options.tf = Tf
  # 切片严格匹配预测步数，维度完全对齐
  ocp.solver_options.shooting_nodes = T_IDXS_FULL[:N+1]
  ocp.code_export_directory = EXPORT_DIR
  return ocp

class LateralMpc:
  def __init__(self, x0=None):
    if x0 is None:
      x0 = np.zeros(X_DIM)
    self.solver = AcadosOcpSolverCython(MODEL_NAME, ACADOS_SOLVER_TYPE, N)
    self.nav_gain = 1.0    # 接收amap导航增益
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
    # 重置兜底缓存
    last_valid_x_sol = self.x_sol.copy()
    last_valid_u_sol = self.u_sol.copy()

  def set_weights(self, path_weight, heading_weight, lat_accel_weight, lat_jerk_weight, steering_rate_weight,
                  is_u_turn=False, is_high_speed=False, v_kph=0.0, is_big_turn=False):
    # 掉头场景权重（原始不变）
    if is_u_turn:
      path_weight = 1.5
      heading_weight = 2.2
      lat_accel_weight = 1.0
      lat_jerk_weight = 0.7
      steering_rate_weight = 1.2
    # 大角度转弯/窄路口弯（原始不变）
    elif is_big_turn:
      path_weight = 1.6 * self.nav_gain
      heading_weight = 2.3 * self.nav_gain
      lat_accel_weight = 0.9
      lat_jerk_weight = 0.65
      steering_rate_weight = 1.3
    # ========= 仅优化高速>100km/h：解除过度转向限制，提升过弯跟随 =========
    elif is_high_speed:
      path_weight = 1.10
      heading_weight = 1.35
      lat_accel_weight = 0.55
      lat_jerk_weight = 0.35
      steering_rate_weight = 1.8
    # 中低速 30~100km/h（原始不变）
    elif v_kph > 30:
      path_weight = 1.75 * self.nav_gain
      heading_weight = 2.1 * self.nav_gain
      lat_accel_weight = 1.0
      lat_jerk_weight = 0.75
      steering_rate_weight = 1.6
    # 低速＜30km/h 路口右转（原始不变）
    else:
      path_weight = 1.55 * self.nav_gain
      heading_weight = 2.6
      lat_accel_weight = 1.15
      lat_jerk_weight = 0.65
      steering_rate_weight = 1.1

    W = np.asfortranarray(np.diag([path_weight, heading_weight, lat_accel_weight, lat_jerk_weight, steering_rate_weight]))
    for i in range(N):
      self.solver.cost_set(i, 'W', W)
    self.solver.cost_set(N, 'W', W[:COST_E_DIM,:COST_E_DIM])

  def run(self, x0, p, y_pts, heading_pts, yaw_rate_pts):
    global last_nav_gain, last_valid_x_sol, last_valid_u_sol
    x0_cp = np.copy(x0)
    p_cp = np.copy(p)
    self.solver.constraints_set(0, "lbx", x0_cp)
    self.solver.constraints_set(0, "ubx", x0_cp)
    self.yref[:,0] = y_pts
    v_ego = p_cp[0, 0]
    v_kph = v_ego * 3.6
    is_high_speed = v_kph > 100
    # 检测航向偏差，区分普通转弯 / 大角度急转弯（原始逻辑不变）
    heading_diff = np.max(np.abs(heading_pts)) if len(heading_pts) > 0 else 0.0
    is_big_turn = heading_diff > BIG_TURN_DIFF_THRESH
    # 导航增益一阶低通平滑，杜绝突变抖动（原始逻辑不变）
    if heading_diff > HEADING_DIFF_THRESH:
        target_gain = 1.3
    else:
        target_gain = 1.0
    self.nav_gain = 0.85 * last_nav_gain + 0.15 * target_gain
    last_nav_gain = self.nav_gain
    self.yref[:,1] = heading_pts * (v_ego + SPEED_OFFSET)
    self.yref[:,2] = yaw_rate_pts * (v_ego + SPEED_OFFSET)
    for i in range(N):
      self.solver.set(i, "yref", self.yref[i])
      self.solver.set(i, "p", p_cp[i])
    self.solver.set(N, "p", p_cp[N])
    self.solver.cost_set(N, "yref", self.yref[N][:COST_E_DIM])
    # 按场景加载权重
    self.set_weights(0,0,0,0,0,False,is_high_speed,v_kph,is_big_turn)

    # 求解 + 异常兜底，保证路径条正常显示
    t = time.monotonic()
    try:
      self.solution_status = self.solver.solve()
      self.solve_time = time.monotonic() - t

      # 读取求解结果
      tmp_x = np.zeros_like(self.x_sol)
      tmp_u = np.zeros_like(self.u_sol)
      for i in range(N+1):
        tmp_x[i] = self.solver.get(i, 'x')
      for i in range(N):
        tmp_u[i] = self.solver.get(i, 'u')

      # 校验结果有效性，正常则更新缓存
      if np.all(np.isfinite(tmp_x)) and np.all(np.isfinite(tmp_u)) and self.solution_status == 0:
        self.x_sol = tmp_x.copy()
        self.u_sol = tmp_u.copy()
        last_valid_x_sol = self.x_sol.copy()
        last_valid_u_sol = self.u_sol.copy()
      else:
        # 结果异常，沿用历史有效数据
        self.x_sol = last_valid_x_sol.copy()
        self.u_sol = last_valid_u_sol.copy()

      self.cost = self.solver.get_cost()
    except Exception:
      # 捕获异常，强制兜底，路径条不消失
      self.x_sol = last_valid_x_sol.copy()
      self.u_sol = last_valid_u_sol.copy()
      self.solution_status = -1
      self.solve_time = time.monotonic() - t
      self.cost = 0

if __name__ == "__main__":
  ocp = gen_lat_ocp()
  AcadosOcpSolver.generate(ocp, json_file=JSON_FILE)