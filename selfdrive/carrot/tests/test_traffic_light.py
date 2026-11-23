#!/usr/bin/env python3
"""TDD: adbridge 4215 红绿灯 -> C3 traffic_state。"""
import os

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


class TestStateFromWire:

    def test_red(self):
        assert state_from_wire("red") == TRAFFIC_RED

    def test_green(self):
        assert state_from_wire("green") == TRAFFIC_GREEN

    def test_unknown(self):
        for value in (None, "", "yellow", "off"):
            assert state_from_wire(value) == TRAFFIC_NONE


class TestFreshness:

    def test_never_seen(self):
        assert not is_fresh(0.0, now=1000.0)

    def test_recent(self):
        assert is_fresh(999.0, now=1000.0)

    def test_stale(self):
        assert not is_fresh(996.0, now=1000.0)

    def test_timeout_is_3s(self):
        assert BRIDGE_FRESH_S == 3.0


class TestPrecedence:

    def test_bridge_used_when_no_detect(self):
        assert bridge_state_allowed(0, 999.0, now=1000.0)

    def test_detect_has_priority(self):
        # DETECT 活跃（count>0）时不采用 bridge 状态
        assert not bridge_state_allowed(5, 999.0, now=1000.0)

    def test_stale_bridge_rejected(self):
        assert not bridge_state_allowed(0, 990.0, now=1000.0)


class TestWiring:

    def test_amap_navi_receives_4215(self):
        text = read("selfdrive/carrot/amap_navi.py")
        assert "_traffic_light_recv_thread" in text
        assert "4215" in text

    def test_carrot_man_applies_bridge_state(self):
        text = read("selfdrive/carrot/carrot_man.py")
        assert "bridge_state_allowed" in text


if __name__ == "__main__":
    unittest.main()
