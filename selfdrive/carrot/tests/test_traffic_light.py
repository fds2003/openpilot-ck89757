#!/usr/bin/env python3
"""TDD: adbridge 4215 红绿灯 -> C3 traffic_state。"""
import os
import unittest

from selfdrive.carrot.traffic_light import (
    BRIDGE_FRESH_S,
    TRAFFIC_GREEN,
    TRAFFIC_NONE,
    TRAFFIC_RED,
    bridge_state_allowed,
    is_fresh,
    state_from_wire,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestStateFromWire(unittest.TestCase):

    def test_red(self):
        self.assertEqual(state_from_wire("red"), TRAFFIC_RED)

    def test_green(self):
        self.assertEqual(state_from_wire("green"), TRAFFIC_GREEN)

    def test_unknown(self):
        for value in (None, "", "yellow", "off"):
            self.assertEqual(state_from_wire(value), TRAFFIC_NONE)


class TestFreshness(unittest.TestCase):

    def test_never_seen(self):
        self.assertFalse(is_fresh(0.0, now=1000.0))

    def test_recent(self):
        self.assertTrue(is_fresh(999.0, now=1000.0))

    def test_stale(self):
        self.assertFalse(is_fresh(996.0, now=1000.0))

    def test_timeout_is_3s(self):
        self.assertEqual(BRIDGE_FRESH_S, 3.0)


class TestPrecedence(unittest.TestCase):

    def test_bridge_used_when_no_detect(self):
        self.assertTrue(bridge_state_allowed(0, 999.0, now=1000.0))

    def test_detect_has_priority(self):
        # DETECT 活跃（count>0）时不采用 bridge 状态
        self.assertFalse(bridge_state_allowed(5, 999.0, now=1000.0))

    def test_stale_bridge_rejected(self):
        self.assertFalse(bridge_state_allowed(0, 990.0, now=1000.0))


class TestWiring(unittest.TestCase):

    def test_amap_navi_receives_4215(self):
        text = read("selfdrive/carrot/amap_navi.py")
        self.assertIn("_traffic_light_recv_thread", text)
        self.assertIn("4215", text)

    def test_carrot_man_applies_bridge_state(self):
        text = read("selfdrive/carrot/carrot_man.py")
        self.assertIn("bridge_state_allowed", text)


if __name__ == "__main__":
    unittest.main()
