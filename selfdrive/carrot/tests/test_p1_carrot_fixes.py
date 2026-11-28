#!/usr/bin/env python3
"""TDD tests for P1 fixes in selfdrive/carrot and controls."""
import ast
import os
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def _read_source(rel_path):
  with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
    return f.read()


def _extract_function(rel_path, func_name, extra_globals=None):
  source = _read_source(rel_path)
  tree = ast.parse(source)
  for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == func_name:
      mod = ast.Module(body=[node], type_ignores=[])
      ast.fix_missing_locations(mod)
      ns = dict(extra_globals or {})
      exec(compile(mod, rel_path, "exec"), ns)
      return ns[func_name]
  raise AssertionError(f"{func_name} not found in {rel_path}")


def _extract_method(rel_path, class_name, method_name, extra_globals=None):
  source = _read_source(rel_path)
  tree = ast.parse(source)
  for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == class_name:
      for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == method_name:
          mod = ast.Module(body=[item], type_ignores=[])
          ast.fix_missing_locations(mod)
          ns = dict(extra_globals or {})
          exec(compile(mod, rel_path, "exec"), ns)
          return ns[method_name]
  raise AssertionError(f"{class_name}.{method_name} not found in {rel_path}")


class TestBsdSpeedKeepTime(unittest.TestCase):

  def test_bsd_speed_keep_time_uses_max_not_min(self):
    source = _read_source("selfdrive/carrot/carrot_serv.py")
    tree = ast.parse(source)
    assigns = []
    for node in ast.walk(tree):
      if isinstance(node, ast.Assign):
        for target in node.targets:
          if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "bsd_speed_keep_time"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
          ):
            assigns.append(node.value.func.id)
    self.assertIn("max", assigns, "bsd_speed_keep_time countdown must use max(-1, ...) instead of min(-1, ...)")
    self.assertNotIn("min", assigns, "min(-1, bsd_speed_keep_time - 1) immediately clamps countdown to -1!")


class TestComputeDeltaVDistanceTerm(unittest.TestCase):

  def setUp(self):
    self.serv = types.SimpleNamespace()
    for m in ("compute_delta_v_for_front", "compute_delta_v_for_rear"):
      fn = _extract_method("selfdrive/carrot/carrot_serv.py", "CarrotServ", m)
      setattr(self.serv, m, types.MethodType(fn, self.serv))

  def test_front_decel_stronger_at_closer_distance(self):
    # v_rel=-1.0, speed_up_enable=False -> decel branch: closer car (10m) must decel more than 40m
    dv_10m = self.serv.compute_delta_v_for_front(10000, -1.0, 20.0, False, True)
    dv_40m = self.serv.compute_delta_v_for_front(40000, -1.0, 20.0, False, True)
    dv_50m = self.serv.compute_delta_v_for_front(50000, -1.0, 20.0, False, True)
    self.assertLess(dv_10m, dv_40m, "Closer front car (10m) should trigger stronger deceleration than 40m")
    self.assertAlmostEqual(dv_40m, dv_50m, places=6, msg="Beyond 40m distance term should clamp to 0")

  def test_front_faster_decel_stronger_at_closer_distance(self):
    # v_rel=1.0, speed_up_enable=False -> decel branch when front is faster
    dv_10m = self.serv.compute_delta_v_for_front(10000, 1.0, 20.0, False, True)
    dv_40m = self.serv.compute_delta_v_for_front(40000, 1.0, 20.0, False, True)
    self.assertLess(dv_10m, dv_40m)

  def test_rear_accel_stronger_at_closer_distance(self):
    # v_rel=1.0, d=10m (close_time=10s > 2s), speed_up_enable=True -> accel more at 10m than 40m
    dv_10m = self.serv.compute_delta_v_for_rear(10000, 1.0, 20.0, True, False)
    dv_40m = self.serv.compute_delta_v_for_rear(40000, 1.0, 20.0, True, False)
    dv_50m = self.serv.compute_delta_v_for_rear(50000, 1.0, 20.0, True, False)
    self.assertGreater(dv_10m, dv_40m, "Closer rear car (10m) should trigger stronger acceleration than 40m")
    self.assertAlmostEqual(dv_40m, dv_50m, places=6)

  def test_rear_slower_accel_stronger_at_closer_distance(self):
    # v_rel=-0.5, speed_up_enable=True -> accel branch when rear is slower
    dv_10m = self.serv.compute_delta_v_for_rear(10000, -0.5, 20.0, True, False)
    dv_40m = self.serv.compute_delta_v_for_rear(40000, -0.5, 20.0, True, False)
    self.assertGreater(dv_10m, dv_40m)


class TestDefaultDmEnabled(unittest.TestCase):

  def test_default_disable_dm_is_zero(self):
    fake_log = types.SimpleNamespace(LongitudinalPersonality=types.SimpleNamespace(standard=1))
    get_default_params = _extract_function("system/manager/manager.py", "get_default_params", {"log": fake_log})
    defaults = dict(get_default_params())
    self.assertEqual(defaults.get("DisableDM"), "0", "Driver monitoring should be enabled by default (DisableDM='0')")


class TestZmqRepAndHmac(unittest.TestCase):

  def test_zmq_malformed_json_replies_before_continue(self):
    source = _read_source("selfdrive/carrot/carrot_man.py")
    tree = ast.parse(source)
    zmq_fn = None
    for node in ast.walk(tree):
      if isinstance(node, ast.FunctionDef) and node.name == "carrot_cmd_zmq":
        zmq_fn = node
        break
    self.assertIsNotNone(zmq_fn)

    # Locate try/except around json.loads(msg_text)
    found_handler = None
    for node in ast.walk(zmq_fn):
      if isinstance(node, ast.ExceptHandler):
        src_seg = ast.get_source_segment(source, node) or ""
        if "JSONDecodeError" in src_seg:
          found_handler = src_seg
          break
    self.assertIsNotNone(found_handler)
    self.assertIn("socket.send(", found_handler, "ZMQ REP must send error reply on malformed JSON to avoid state machine deadlock")
    self.assertIn("continue", found_handler)

  def test_zmq_hmac_does_not_truncate_raw_message(self):
    source = _read_source("selfdrive/carrot/carrot_man.py")
    self.assertNotIn("raw_message[:64]", source, "ZMQ HMAC must cover full canonical payload, not raw_message[:64]")


class TestWebNavParamsWhitelistAndLaneBind(unittest.TestCase):

  def test_handle_nav_params_enforces_whitelist_and_merges(self):
    source = _read_source("selfdrive/carrot/web_interface.py")
    tree = ast.parse(source)
    handler_src = None
    for node in ast.walk(tree):
      if isinstance(node, ast.FunctionDef) and node.name == "handle_nav_params":
        handler_src = ast.get_source_segment(source, node)
        break
    self.assertIsNotNone(handler_src)
    self.assertIn("PARAM_KEY_WHITELIST", handler_src, "/nav_params must enforce PARAM_KEY_WHITELIST")
    self.assertNotIn("unified_params.nav_data = data", handler_src, "/nav_params must merge instead of overwriting nav_data")

  def test_lane_http_not_hardcoded_wildcard(self):
    source = _read_source("selfdrive/carrot/lane.py")
    self.assertNotIn("run_simple('0.0.0.0', 8888", source, "lane.py HTTP stream must not hardcode 0.0.0.0:8888")


class TestRadardOverpassTracker(unittest.TestCase):

  def _make_radard(self):
    fake_cloudlog = types.SimpleNamespace(warning=lambda *a, **kw: None)
    rd = types.SimpleNamespace(_overpass_tracker={}, _overpass_frame=0)
    rd._lead_position_key = staticmethod(lambda drel, yrel: (round(float(drel), 1), round(float(yrel), 1)))
    fn_update = _extract_method(
      "selfdrive/controls/radard.py",
      "RadarD",
      "_update_overpass_tracker",
      {"cloudlog": fake_cloudlog},
    )
    rd._update_overpass_tracker = types.MethodType(fn_update, rd)
    return rd

  def test_same_frame_idempotent_no_double_count(self):
    rd = self._make_radard()
    track = types.SimpleNamespace(dRel=30.0, vLead=0.0, yRel=0.0, identifier=1)
    # Simulate 3 frames where each frame calls _update_overpass_tracker twice (get_lead + compute_leads)
    for frame in (1, 2, 3):
      rd._overpass_frame = frame
      self.assertFalse(rd._update_overpass_tracker(track))
      self.assertFalse(rd._update_overpass_tracker(track))
    key = (30.0, 0.0)
    self.assertEqual(rd._overpass_tracker[key]["stable_count"], 3)

  def test_stale_overpass_entries_pruned(self):
    rd = self._make_radard()
    fn_prune = _extract_method("selfdrive/controls/radard.py", "RadarD", "_prune_overpass_tracker")
    rd._prune_overpass_tracker = types.MethodType(fn_prune, rd)
    track = types.SimpleNamespace(dRel=30.0, vLead=0.0, yRel=0.0, identifier=1)
    rd._overpass_frame = 1
    rd._update_overpass_tracker(track)
    self.assertIn((30.0, 0.0), rd._overpass_tracker)
    rd._overpass_frame = 25
    rd._prune_overpass_tracker()
    self.assertNotIn((30.0, 0.0), rd._overpass_tracker)


class TestAmapNaviLockCompleteness(unittest.TestCase):

  def test_make_lidar_message_uses_shared_snapshot(self):
    source = _read_source("selfdrive/carrot/amap_navi.py")
    tree = ast.parse(source)
    fn_src = None
    for node in ast.walk(tree):
      if isinstance(node, ast.FunctionDef) and node.name == "make_lidar_message":
        fn_src = ast.get_source_segment(source, node)
        break
    self.assertIsNotNone(fn_src)
    self.assertIn("_shared_snapshot()", fn_src)
    self.assertIn("_build_base_fields(snap)", fn_src)
    self.assertIn("_apply_cruise_state(msg, snap)", fn_src)

  def test_make_navi_message_uses_snap_for_blindspot(self):
    source = _read_source("selfdrive/carrot/amap_navi.py")
    self.assertIn("self.left_blindspot(snap)", source)
    self.assertIn("self.right_blindspot(snap)", source)

  def test_clients_copy_is_per_entry_copy(self):
    source = _read_source("selfdrive/carrot/amap_navi.py")
    self.assertNotIn('getattr(self, "clients", {}).copy()', source, "Shallow clients.copy() shares nested info dicts across threads")


class TestDmonitoringMetadataPresent(unittest.TestCase):

  def test_dmonitoring_metadata_pkl_exists_and_valid(self):
    import pickle
    meta_path = os.path.join(ROOT, "selfdrive", "modeld", "models", "dmonitoring_model_metadata.pkl")
    self.assertTrue(os.path.exists(meta_path), f"Missing {meta_path}")
    with open(meta_path, "rb") as f:
      meta = pickle.load(f)
    self.assertEqual(meta["input_shapes"]["input_img"], (1, 1382400))
    self.assertEqual(meta["input_shapes"]["calib"], (1, 3))
    for k in ("wheel_on_right", "face_descs_lhd", "face_prob_lhd", "using_phone_prob_lhd"):
      self.assertIn(k, meta["output_slices"])

  def test_sconscript_includes_dmonitoring_metadata(self):
    source = _read_source("selfdrive/modeld/SConscript")
    self.assertIn("for model_name in ['driving_vision', 'driving_policy', 'dmonitoring_model']:", source)


if __name__ == "__main__":
  unittest.main()
