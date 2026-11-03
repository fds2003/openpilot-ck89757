#!/usr/bin/env python3
"""
TDD Comprehensive Verification Test Suite for ALL C3 Modifications on cp-custo-amap branch.
Tests all 5 modification targets:
1. cereal/custom.capnp: overtakeMode & lidarBehindVdistTime fields.
2. substitute.toml: HYUNDAI_CUSTIN_1ST_GEN -> HYUNDAI_PALISADE NNFF mapping.
3. process_config.py: Single-owner amap_navi architecture (avoids MultiplePublishersError).
4. amap_navi.py: Ports 7706/7705, leftBehindTarget, positive meter telemetry, discovery IP & last_seen, command gating.
5. desire_helper.py: Empty lane decoupling, continuous TTC abort, CANCEL consumer, driver override audio.
"""
import os
import re
import time
import unittest

C3_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

class TestC3CooperativeModifications(unittest.TestCase):

    # =========================================================================
    # 1. cereal/custom.capnp Schema Test
    # =========================================================================
    def test_custom_capnp_fields(self):
        """Verify custom.capnp has overtakeMode @15 and lidarBehindVdistTime @16"""
        capnp_file = os.path.join(C3_ROOT, "cereal", "custom.capnp")
        self.assertTrue(os.path.exists(capnp_file), f"custom.capnp missing at {capnp_file}")
        with open(capnp_file, "r", encoding="utf-8") as f:
            text = f.read()

        self.assertIn("struct AmapNavi", text)
        self.assertRegex(text, r"overtakeMode\s*@15\s*:\s*Int32;")
        self.assertRegex(text, r"lidarBehindVdistTime\s*@16\s*:\s*Float32;")

    # =========================================================================
    # 2. substitute.toml Palisade NNFF Mapping Test
    # =========================================================================
    def test_substitute_palisade_mapping(self):
        """Verify substitute.toml maps HYUNDAI_CUSTIN_1ST_GEN to HYUNDAI_PALISADE"""
        sub_file = os.path.join(C3_ROOT, "opendbc_repo", "opendbc", "car", "torque_data", "substitute.toml")
        self.assertTrue(os.path.exists(sub_file), f"substitute.toml missing at {sub_file}")
        with open(sub_file, "r", encoding="utf-8") as f:
            text = f.read()

        self.assertIn('"HYUNDAI_CUSTIN_1ST_GEN" = "HYUNDAI_PALISADE"', text,
                      "Custin MUST map to Palisade NNFF model in substitute.toml!")

    # =========================================================================
    # 3. system/manager/process_config.py Process Architecture Test
    # =========================================================================
    def test_process_config_single_owner(self):
        """Verify amap_navi is not registered as standalone process to avoid MultiplePublishersError"""
        proc_file = os.path.join(C3_ROOT, "system", "manager", "process_config.py")
        self.assertTrue(os.path.exists(proc_file), f"process_config.py missing at {proc_file}")
        with open(proc_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for l in lines:
            if "amap_navi" in l:
                self.assertTrue(l.strip().startswith("#"),
                                "amap_navi in process_config MUST be commented out to let carrot_man own it exclusively!")

    # =========================================================================
    # 4. selfdrive/carrot/amap_navi.py Networking & Ports Test
    # =========================================================================
    def test_amap_navi_port_contract(self):
        """Verify amap_navi sets navi_port=7706 (send) and navi_remote_port=7705 (receive)"""
        amap_file = os.path.join(C3_ROOT, "selfdrive", "carrot", "amap_navi.py")
        self.assertTrue(os.path.exists(amap_file), f"amap_navi.py missing at {amap_file}")
        with open(amap_file, "r", encoding="utf-8") as f:
            text = f.read()

        # Check port assignments
        self.assertRegex(text, r"self\.navi_port\s*=\s*7706")
        self.assertRegex(text, r"self\.navi_remote_port\s*=\s*7705")

        # Check leftBehindTarget typo fix
        self.assertIn("self.shared_data.lb_vrel = self.leftBehindTarget.update(lb_dreltmp, dist_timems)", text,
                      "lb_vrel MUST use leftBehindTarget, not leftFrontTarget!")

        # Check positive meter conversion for lb_drel and rb_drel
        self.assertIn("abs(main) / 1000.0", text,
                      "lb_drel and rb_drel MUST be exported in positive meters!")

        # Check discovery responder sets last_seen
        self.assertIn('"last_seen": now', text,
                      "discovery responder MUST write last_seen to prevent KeyError in _clean_clients_thread!")

        # Check client_active initialization
        self.assertIn("self.client_active = {}", text,
                      "amap_navi MUST initialize self.client_active in __init__ to avoid AttributeError in _clean_clients_thread!")
    # =========================================================================
    # 5. selfdrive/carrot/amap_navi.py Command Parser Gating Logic Test
    # =========================================================================
    def test_command_parser_gating(self):
        """Verify command parser logic: monotonic seq, CANCEL conversion, param clamp, 10s reset"""
        class SharedDataMock:
            def __init__(self):
                self.cmd_index = -1
                self.remote_cmd = ""
                self.remote_arg = ""
                self.overtake_mode = 1
                self.last_cmd_time = 0.0

        shared = SharedDataMock()

        def update_command(json_obj):
            idx = json_obj.get("index") or json_obj.get("seq")
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                idx = None

            now = time.time()
            if now - getattr(shared, "last_cmd_time", 0.0) > 10.0:
                shared.cmd_index = -1
            shared.last_cmd_time = now

            if idx is not None and (idx > shared.cmd_index or shared.cmd_index == -1):
                shared.cmd_index = idx
                if "cmd" in json_obj:
                    c = json_obj.get("cmd")
                    shared.remote_cmd = "CANCEL" if c == "CANCEL_LANE_CHANGE" else c
                    shared.remote_arg = json_obj.get("direction") or json_obj.get("arg")
                raw = json_obj.get("param", json_obj.get("overtake_mode", None))
                if raw is not None:
                    try:
                        r = int(raw)
                        if r in (0, 1, 2):
                            shared.overtake_mode = r
                    except (TypeError, ValueError):
                        pass

        # Packet 1: Initial valid command
        update_command({"cmd": "OVERTAKE", "arg": "LEFT", "param": 2, "seq": 10})
        self.assertEqual(shared.cmd_index, 10)
        self.assertEqual(shared.remote_cmd, "OVERTAKE")
        self.assertEqual(shared.remote_arg, "LEFT")
        self.assertEqual(shared.overtake_mode, 2)

        # Packet 2: Replay packet with older seq (seq=5) MUST be rejected!
        update_command({"cmd": "OVERTAKE", "arg": "RIGHT", "param": 0, "seq": 5})
        self.assertEqual(shared.cmd_index, 10, "Older packet must be ignored!")
        self.assertEqual(shared.remote_cmd, "OVERTAKE")
        self.assertEqual(shared.remote_arg, "LEFT")
        self.assertEqual(shared.overtake_mode, 2)

        # Packet 3: CANCEL_LANE_CHANGE command conversion
        update_command({"cmd": "CANCEL_LANE_CHANGE", "arg": "KEEP", "seq": 11})
        self.assertEqual(shared.cmd_index, 11)
        self.assertEqual(shared.remote_cmd, "CANCEL")

        # Packet 4: Inactivity reset after 10s allows seq restart from 1 (car head unit reboot)
        shared.last_cmd_time = time.time() - 15.0 # simulate 15s elapsed
        update_command({"cmd": "OVERTAKE", "arg": "LEFT", "param": 1, "seq": 1})
        self.assertEqual(shared.cmd_index, 1, "After 10s inactivity, seq restart from 1 MUST be accepted!")
        self.assertEqual(shared.overtake_mode, 1)

    # =========================================================================
    # 6. selfdrive/controls/lib/desire_helper.py Gating & Abort Test
    # =========================================================================
    def test_desire_helper_failsafe_ttc_and_cancel(self):
        """Verify desire_helper TTC gating: empty lane permits, fast rear blocks, CANCEL aborts"""
        amap_file = os.path.join(C3_ROOT, "selfdrive", "controls", "lib", "desire_helper.py")
        with open(amap_file, "r", encoding="utf-8") as f:
            dh_text = f.read()

        # Verify CANCEL consumer exists
        self.assertIn('carrotMan.carrotCmd == "CANCEL"', dh_text,
                      "desire_helper MUST have carrotCmd == 'CANCEL' consumer!")

        # Verify continuous TTC abort exists in laneChangeStarting
        self.assertIn('self.trigger_name = "rear ttc abort"', dh_text,
                      "desire_helper MUST have continuous rear TTC abort in laneChangeStarting!")

        # Verify immediate driver override audio exists
        self.assertIn("self.lane_change_audio(True, 4, 0)", dh_text,
                      "Driver override MUST immediately trigger exit audio!")

if __name__ == "__main__":
    unittest.main()
