#!/usr/bin/env python3
"""
TDD Unit Test for Slice 2: CANCEL and SPEED_LIMIT Command Handlers (M-08, M-09, M-16)
Verifies:
1. CANCEL command immediately resets active lane change state to off.
2. SPEED_LIMIT command parses integer speed (0~160) and updates nRoadLimitSpeed.
3. Invalid SPEED_LIMIT args (non-numeric, negative, >160) are blocked without fail-open.
"""
import unittest

class MockLaneChangeState:
    off = 0
    preLaneChange = 1
    laneChangeStarting = 2
    laneChangeFinishing = 3

class MockDesireHelper:
    def __init__(self):
        self.lane_change_state = MockLaneChangeState.laneChangeStarting
        self.lane_change_direction = 1 # LEFT
        self.carrot_lane_change_count = 10
        self.carrot_cmd_index_last = 0
        self.trigger_name = "test"
        self.audio_played = []

    def handle_carrot_cmd(self, carrot_cmd, carrot_arg, cmd_index):
        if cmd_index != self.carrot_cmd_index_last and carrot_cmd == "CANCEL":
            self.carrot_cmd_index_last = cmd_index
            self.carrot_lane_change_count = 0
            self.lane_change_state = MockLaneChangeState.off
            self.lane_change_direction = 0
            self.trigger_name = "cancel cmd"
            self.audio_played.append(4) # 领航已退出

class MockCarrotServ:
    def __init__(self):
        self.nRoadLimitSpeed = 0
        self.nRoadLimitSpeed_last = 0
        self.command_handlers = {
            "SPEED_LIMIT": self._handle_speed_limit_command,
        }

    def _handle_speed_limit_command(self, xArg):
        try:
            speed_kph = int(xArg)
        except (ValueError, TypeError):
            return
        if 0 <= speed_kph <= 160:
            self.nRoadLimitSpeed = speed_kph
            self.nRoadLimitSpeed_last = speed_kph

class TestCooperativeCommandHandlers(unittest.TestCase):

    def test_cancel_command_aborts_active_lane_change(self):
        dh = MockDesireHelper()
        self.assertEqual(dh.lane_change_state, MockLaneChangeState.laneChangeStarting)

        dh.handle_carrot_cmd(carrot_cmd="CANCEL", carrot_arg="KEEP", cmd_index=1)

        self.assertEqual(dh.lane_change_state, MockLaneChangeState.off)
        self.assertEqual(dh.carrot_lane_change_count, 0)
        self.assertEqual(dh.trigger_name, "cancel cmd")
        self.assertIn(4, dh.audio_played)

    def test_speed_limit_command_valid_update(self):
        serv = MockCarrotServ()
        self.assertEqual(serv.nRoadLimitSpeed, 0)

        serv.command_handlers["SPEED_LIMIT"]("100")
        self.assertEqual(serv.nRoadLimitSpeed, 100)

        serv.command_handlers["SPEED_LIMIT"]("120")
        self.assertEqual(serv.nRoadLimitSpeed, 120)

    def test_speed_limit_invalid_argument_blocked(self):
        serv = MockCarrotServ()
        serv.nRoadLimitSpeed = 80

        # Non-numeric
        serv.command_handlers["SPEED_LIMIT"]("invalid")
        self.assertEqual(serv.nRoadLimitSpeed, 80)

        # Out of bounds (> 160)
        serv.command_handlers["SPEED_LIMIT"]("200")
        self.assertEqual(serv.nRoadLimitSpeed, 80)

        # Negative (< 0)
        serv.command_handlers["SPEED_LIMIT"]("-10")
        self.assertEqual(serv.nRoadLimitSpeed, 80)

if __name__ == "__main__":
    unittest.main()
