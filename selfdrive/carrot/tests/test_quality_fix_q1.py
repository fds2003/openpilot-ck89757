#!/usr/bin/env python3
"""
TDD tests for 19号文档 C3 端「规划」档质量修复 Q-1（SharedData 读写锁不一致）。

- Q-1: 读路径 make_*_message 裸读 self.shared_data（50+ 裸可变字段），
       与 20Hz 写线程（_data_deal_thread 等持 self._lock 的写者）并发时
       可能读到"半更新"帧（多字段组合读撕裂）。
       修复：读路径先 with self._lock: 锁内一次性快照复制关键字段到局部 dict
       （dict 型字段浅拷贝），锁外基于快照构建消息（方案 A，零行为风险）。

测试分三类：
1. 行为黄金值（单线程确定性）：修复前后相同 SharedData 输入下
   make_navi_message / make_blinker_message 逐字段输出一致。
2. 线程安全回归（多写 + 多读并发）：写线程在同一把锁内原子修改
   behind_ttc（X）+ lidar_lbblind（Y），读线程调 make_navi_message()
   后断言帧内两字段不出现"交叉撕裂"（X 旧 + Y 新 / X 新 + Y 旧）。
   CPython GIL 下裸读单个原子字段本身不撕裂，跨字段组合撕裂需
   调度介入才偶发暴露；修复后快照锁保证恒不撕裂，测试稳定全绿。
3. 源码静态检查：make_navi_message / make_blinker_message 已走
   锁内快照（_shared_snapshot / with self._lock），不直接裸读
   self.shared_data 字段。

stub 模式复用 test_quality_fixes_q4_q5_q6.py（_install_stubs / _SM /
_mk_serv），两文件独立可跑。
"""
import json
import os
import sys
import threading
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from test_quality_fixes_q4_q5_q6 import (
  _install_stubs, _load_module, _mk_serv, _SM,
)

AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")


def _load_fresh():
  """每个测试类独立加载 amap_navi，避免互相污染模块级状态。"""
  _install_stubs()
  return _load_module("amap_navi_q1", AMAP_NAVI)


class TestQ1GoldenValues(unittest.TestCase):
  """Q-1: 快照化后广播帧黄金值回归（单线程确定性，防快照化改变输出）。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def _mk(self, **sd_kw):
    amap = self.amap_navi
    sd = amap.SharedData()
    sd.carState = True
    sd.v_cruise_kph = 60
    sd.v_ego_kph = 55
    for k, v in sd_kw.items():
      setattr(sd, k, v)
    return _mk_serv(sd)

  def test_navi_golden_with_carstate_fields(self):
    """carState=True + 车辆状态字段齐全时，navi 帧逐字段与重构前一致。"""
    serv = self._mk(
      vEgo=12.5, aEgo=1.1, steer_angle=3.3,
      driver_steering=True, gas_press=True, break_press=False,
      engaged=False, left_blindspot=1, right_blindspot=0,
      behind_ttc=2.5, lidar_lbblind=True, lidar_rbblind=False,
      lf_vrel=1.2, rf_vrel=0.8, lb_vrel=2.0, rb_vrel=1.5,
      main_lb_drel=-5000, main_rb_drel=5000,
      lf_drel={0: 5000}, lidar_l=True, lidar_r=False,
      camera_l=True, camera_r=False,
      roadcate=1, lat_a=0.123, max_curve=0.0456,
      op_blocked=False, road_blocked=False,
      cruise_valid=True, selfdrive_active=True,
    )
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(msg.get("vego"), 12.5)
    self.assertEqual(msg.get("aego"), 1.1)
    self.assertEqual(msg.get("steer_angle"), 3.3)
    self.assertIs(msg.get("driver_steering"), True)
    self.assertIs(msg.get("gas_press"), True)
    self.assertIs(msg.get("brake_press"), False)
    self.assertIs(msg.get("engaged"), False)
    self.assertEqual(msg.get("left_blindspot"), 1)
    self.assertEqual(msg.get("right_blindspot"), 0)
    self.assertEqual(msg.get("lidar_behind_vdist_time"), 2.5)
    self.assertIs(msg.get("lidar_lbblind"), True)
    self.assertIs(msg.get("lidar_rbblind"), False)
    self.assertEqual(msg.get("lf_vrel"), 4, "1.2*3.6=4.32 -> int 4")
    self.assertEqual(msg.get("rf_vrel"), 2, "0.8*3.6=2.88 -> int 2")
    self.assertEqual(msg.get("lb_vrel"), 7, "2.0*3.6=7.2 -> int 7")
    self.assertEqual(msg.get("rb_vrel"), 5, "1.5*3.6=5.4 -> int 5")
    self.assertEqual(msg.get("lb_drel"), 5.0, "main_lb_drel(mm) 取绝对值转米")
    self.assertEqual(msg.get("rb_drel"), 5.0)
    self.assertEqual(msg.get("lf_drel"), 5000, "per-lidar dict idx0 仍广播")
    self.assertIs(msg.get("lidar_l"), True)
    self.assertIs(msg.get("lidar_r"), False)
    self.assertIs(msg.get("camera_l"), True)
    self.assertIs(msg.get("camera_r"), False)
    self.assertEqual(msg.get("roadcate"), 1)
    self.assertEqual(msg.get("lat_a"), 0.12, "round2")
    self.assertEqual(msg.get("max_curve"), 0.05, "round2")
    self.assertIs(msg.get("op_blocked"), False)
    self.assertIs(msg.get("road_blocked"), False)
    self.assertEqual(msg.get("v_cruise_kph"), 60)
    self.assertEqual(msg.get("v_ego_kph"), 55)
    self.assertIs(msg.get("active"), True, "cruise_valid=True")
    # blind_enable: (lidar_l or camera_l) and (lidar_r or camera_r)
    # lidar_r/camera_r 为 False -> 右设备离线 -> blind_enable=False
    self.assertIs(msg.get("blind_enable"), False)

  def test_navi_golden_none_fields_absent(self):
    """carState 字段为 None 时对应键缺席（保持重构前逐字段行为）。"""
    serv = self._mk(lf_drel={})
    msg = json.loads(serv.make_navi_message())
    for k in ("vego", "aego", "steer_angle", "gas_press", "brake_press",
              "left_blindspot", "right_blindspot", "lf_drel"):
      self.assertNotIn(k, msg, f"None 字段 {k} 键应缺席")
    # sd.selfdrive_active 默认 False -> _apply_cruise_state 推导
    # cruise_enable=False -> engaged=False（非 None 透传，走 sm 推导链）
    self.assertIs(msg.get("engaged"), False,
                  "selfdrive_active=False -> cruise_enable=False -> engaged=False")

  def test_blinker_golden(self):
    """blinker 帧：gas/break 透传（快照后行为一致）。

    blinker_ctrl 分支依赖 modelV2.meta.blinker（_Meta stub 无该属性，
    hasattr=False 分支不触发），故只断言不出现 blinker 键 + gas/break 透传。
    """
    serv = self._mk(engaged=False, gas_press=True, break_press=True,
                    blinker_ctrl=1)
    serv.stockBlinkerCtrl = 0
    msg = json.loads(serv.make_blinker_message())
    self.assertIs(msg.get("gas_press"), True)
    self.assertIs(msg.get("brake_press"), True)
    self.assertNotIn("blinker", msg, "meta 无 blinker 属性时键应缺席")

  def test_blinker_ctrl_branch_with_meta(self):
    """blinker_ctrl 分支：给 meta 挂 blinker 属性后，BLINKER_LEFT + stock=0
    应广播 blinker='left'（快照化不改变分支行为）。"""
    serv = self._mk(engaged=False, blinker_ctrl=1)
    serv.stockBlinkerCtrl = 0
    # 给 _Meta stub 挂上 blinker 属性（make_blinker_message 读 meta.blinker）
    meta = serv.sm['modelV2'].meta
    meta.blinker = "none"  # 触发 BLINKER_LEFT 分支（meta.blinker == "none"）
    msg = json.loads(serv.make_blinker_message())
    self.assertEqual(msg.get("blinker"), "left", "BLINKER_LEFT + stock=0")

  def test_snapshot_dict_is_copy_not_reference(self):
    """快照浅拷贝 per-lidar dict：构建期写线程向原 dict 加 key 不得进已发帧。"""
    serv = self._mk(lf_drel={0: 100, 1: 200})
    sd = serv.shared_data
    def writer():
      time.sleep(0.002)
      sd.lf_drel[2] = 300  # 读路径快照之后追加
    t = threading.Thread(target=writer)
    t.start()
    # make_navi_message 内部先取快照再构建；writer 的 sleep 保证发生在快照之后
    msg = json.loads(serv.make_navi_message())
    t.join()
    self.assertEqual(msg.get("lf_drel"), 100, "idx0 值不受后续写入影响")
    self.assertEqual(msg.get("lf_drel1"), 200, "idx1 值取自快照时刻")
    self.assertNotIn("lf_drel2", msg, "快照后追加的 key 不得进已发帧")


class TestQ1ThreadTearing(unittest.TestCase):
  """Q-1: 多写多读并发撕裂回归（写者锁内原子改 X+Y，读者不得读到交叉帧）。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def _mk_serv_full(self):
    sd = self.amap_navi.SharedData()
    serv = _mk_serv(sd)
    serv.disableBlindSpot = False
    return serv

  def test_no_torn_read_under_concurrent_writers(self):
    """N 写 × M 读并发：写线程在同一把锁内先设 behind_ttc=X 再设
    lidar_lbblind=Y（原子），读线程调 make_navi_message() 后断言
    lidar_behind_vdist_time / lidar_lbblind 不出现 (X旧,Y新)/(X新,Y旧) 交叉。

    单一写线程确定性循环（i 轮：x=0.1+0.1*(i%5), y=(i%2)==0），
    轮次配对表 {0.1:False, 0.2:True, 0.3:False, 0.4:True, 0.5:False}；
    多个写线程会各自计数导致配对不可判定，故撕裂判定用 1 写 + 4 读，
    另设 1 个干扰写线程（无配对语义，仅制造锁竞争）。
    合法帧 = (t, b) 落在配对表内；读到表外组合即为跨写时刻撕裂。

    注：CPython GIL 下单线程串行执行，裸读两个原子字段本身不撕裂；
    撕裂需调度在两次裸读之间切换写线程才暴露。修复后读路径锁内快照，
    恒不撕裂。本测试以确定性配对表 + 足量并发窗口验证帧内一致性
    （修复后稳定全绿；修复前若调度介入则偶发暴露，配合静态检查兜底）。
    """
    serv = self._mk_serv_full()
    sd = serv.shared_data
    errors = []
    stop = threading.Event()
    read_done = [0]
    # 配对表与 writer 内注释一致：{0.1:F, 0.2:F, 0.3:T, 0.4:T, 0.5:T}
    pairs = {0.1: False, 0.2: False, 0.3: True, 0.4: True, 0.5: True}

    def writer():
      i = 0
      while not stop.is_set():
        i += 1
        # 配对语义：以 x 值唯一决定 y（x=0.1+0.1*((i-1)%5)，y=(x>=0.3)）
        # 轮次 (i-1)=0..4 -> x=0.1..0.5 -> y=False,False,True,True,True
        # 配对表：{0.1:F, 0.2:F, 0.3:T, 0.4:T, 0.5:T}（x 与 y 一一对应，
        # 同一 x 值永远对应同一 y，多轮循环不产生歧义）
        x_k = round(0.1 + ((i - 1) % 5) * 0.1, 1)
        y_k = (x_k >= 0.3)
        with serv._lock:
          # 原子写：两字段同一逻辑时刻更新（与 _data_deal_thread 同锁写者一致）
          sd.behind_ttc = x_k
          sd.lidar_lbblind = y_k
        time.sleep(0.0005)  # 节流：给读者观测窗口（≈0.5ms/轮 × 多轮）

    def noise_writer():
      # 干扰写线程：同锁改不相干字段（制造锁竞争，不参与配对判定）
      i = 0
      while not stop.is_set():
        i += 1
        with serv._lock:
          sd.left_lane = i % 3
        time.sleep(0.001)

    def reader():
      while not stop.is_set():
        try:
          msg = json.loads(serv.make_navi_message())
          t = round(msg.get("lidar_behind_vdist_time"), 1)
          b = msg.get("lidar_lbblind")
          # 帧内一致性：(t, b) 必须落在写者配对表内
          if t not in pairs or b is not pairs[t]:
            errors.append(f"读线程撕裂值: t={t}, b={b} (期望 b={pairs.get(t)})")
          read_done[0] += 1
        except Exception as e:
          errors.append(f"读线程异常: {e!r}")

    threads = ([threading.Thread(target=writer),
                threading.Thread(target=noise_writer)] +
               [threading.Thread(target=reader) for _ in range(4)])
    for t in threads:
      t.start()
    time.sleep(0.4)  # 并发窗口（足够多轮写读交错）
    stop.set()
    for t in threads:
      t.join()
    self.assertTrue(read_done[0] > 100, f"读线程应完成足够迭代（实际 {read_done[0]}）")
    self.assertEqual(errors, [], f"出现撕裂/异常读: {errors[:5]}")

  def test_read_frame_internally_consistent_pair(self):
    """精确撕裂判定：写者按配对表 (x -> y) 锁内原子写，读者帧内
    t/b 必须成对出现；写者带节流（1000 轮 × 0.2ms ≈ 0.2s 窗口），
    保证读者 200 轮迭代内能观测到多种配对。"""
    serv = self._mk_serv_full()
    sd = serv.shared_data
    seen_pairs = {}
    lock = threading.Lock()
    # 配对表：x -> y（写者按 x 决定 y，读到的 (t, b) 必须落在表内）
    pairs = {0.1: False, 0.2: True, 0.3: False, 0.4: True, 0.5: False}

    def writer():
      for i in range(1000):
        xv = round(0.1 + (i % 5) * 0.1, 1)
        with serv._lock:
          sd.behind_ttc = xv
          sd.lidar_lbblind = pairs[xv]
        time.sleep(0.0002)  # 节流：给读者留观测窗口（总时长 ≈ 0.2s）

    def reader():
      for _ in range(200):
        try:
          msg = json.loads(serv.make_navi_message())
          t = round(msg.get("lidar_behind_vdist_time"), 1)
          b = msg.get("lidar_lbblind")
          with lock:
            seen_pairs[(t, b)] = seen_pairs.get((t, b), 0) + 1
        except Exception:
          pass

    # 单写线程保证配对表语义；3 读线程并发
    threads = [threading.Thread(target=writer)] + \
              [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    bad = [(t, b) for (t, b) in seen_pairs
           if b is not pairs.get(round(t, 1))]
    self.assertEqual(bad, [], f"出现撕裂配对（t 与 b 取自不同写时刻）: {bad[:5]}")
    self.assertGreaterEqual(len(seen_pairs), 2, "应观测到至少 2 种配对")


class TestQ1ReadPathLockSnapshot(unittest.TestCase):
  """Q-1: 源码静态检查——读路径已锁内快照，不再裸读 self.shared_data。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def test_snapshot_method_exists_and_holds_lock(self):
    amap = self.amap_navi
    self.assertTrue(callable(getattr(amap.AmapNaviServ, "_shared_snapshot", None)),
                    "Q-1 RED: 应存在 AmapNaviServ._shared_snapshot")
    import inspect
    src = inspect.getsource(amap.AmapNaviServ._shared_snapshot)
    self.assertIn("with self._lock:", src, "Q-1 RED: 快照应在 self._lock 临界区内完成")

  def test_navi_and_blinker_use_snapshot(self):
    amap = self.amap_navi
    import inspect
    navi_src = inspect.getsource(amap.AmapNaviServ.make_navi_message)
    blinker_src = inspect.getsource(amap.AmapNaviServ.make_blinker_message)
    self.assertIn("self._shared_snapshot()", navi_src,
                  "Q-1 RED: make_navi_message 应取锁内快照")
    self.assertIn("self._shared_snapshot()", blinker_src,
                  "Q-1 RED: make_blinker_message 应取锁内快照")
    # 快照之后不得再直接裸读 self.shared_data.<field>
    self.assertNotIn("self.shared_data.behind_ttc", navi_src,
                     "Q-1 RED: 读路径不应裸读 self.shared_data.behind_ttc")
    self.assertNotIn("self.shared_data.lf_drel", navi_src,
                     "Q-1 RED: 读路径不应裸读 self.shared_data.lf_drel")

  def test_no_nested_lock_in_read_path(self):
    """读路径不产生嵌套锁获取（_shared_snapshot 内不再调用其他持锁方法）。"""
    amap = self.amap_navi
    import inspect
    snap_src = inspect.getsource(amap.AmapNaviServ._shared_snapshot)
    # 快照临界区内只允许读 self.shared_data 字段并 return，不得再 with self._lock
    self.assertEqual(snap_src.count("with self._lock:"), 1,
                     "Q-1: _shared_snapshot 应恰好一段锁临界区（无嵌套）")


if __name__ == "__main__":
  unittest.main()
