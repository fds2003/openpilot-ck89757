#!/usr/bin/env python3
"""TDD: 协同模式——车机意图优先时禁用 C3 自主 ATC。"""
import os

from selfdrive.carrot.cooperative_mode import (
    HU_ALIVE_TIMEOUT_S,
    auto_turn_allowed,
    hu_alive,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestHuAlive:

    def test_never_seen(self):
        assert not hu_alive(None, now=1000.0)

    def test_recent_probe(self):
        assert hu_alive(990.0, now=1000.0)

    def test_stale_probe(self):
        assert not hu_alive(980.0, now=1000.0)

    def test_timeout_defaults_to_15s(self):
        # 车机每 5s 探针一次，15s = 连续丢失 3 次才判定失联
        assert HU_ALIVE_TIMEOUT_S == 15.0
        assert hu_alive(985.0, now=1000.0)
        assert not hu_alive(984.0, now=1000.0)


class TestAutoTurnAllowed:

    def test_legacy_mode_keeps_c3_autonomous(self):
        # 协同模式关闭：保持原行为，C3 自主 ATC 可用
        assert auto_turn_allowed(cooperative_mode=False, is_hu_alive=True)

    def test_cooperative_with_hu_alive_blocks_c3(self):
        # 协同模式 + 车机在线：只执行车机意图
        assert not auto_turn_allowed(cooperative_mode=True, is_hu_alive=True)

    def test_cooperative_without_hu_falls_back(self):
        # 车机失联：回退 C3 自主，避免双端都失效
        assert auto_turn_allowed(cooperative_mode=True, is_hu_alive=False)


class TestWiring:

    def test_carrot_serv_gates_auto_turn(self):
        text = read("selfdrive/carrot/carrot_serv.py")
        assert "CarrotCooperativeMode" in text
        assert "auto_turn_allowed" in text

    def test_gate_preserves_speed_planning(self):
        # atc_desired 是限速值（250=无限制），不能早退成 0（会被当成刹停）
        text = read("selfdrive/carrot/carrot_serv.py")
        assert 'atc_type = "none"' in text
        assert 'return 0, "none", 0, 0, 0' not in text

    def test_web_whitelist_allows_toggle(self):
        # 8088 参数页必须允许写该键，否则功能无法在现场切换
        text = read("selfdrive/carrot/web_interface.py")
        assert '"CarrotCooperativeMode"' in text

    def test_carrot_man_updates_hu_alive(self):
        text = read("selfdrive/carrot/carrot_man.py")
        assert "hu_alive(" in text


if __name__ == "__main__":
    unittest.main()
