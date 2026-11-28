#!/usr/bin/env python3
"""TDD: lane_runner 回传 amap_navi 的 UDP 载荷契约。"""
import json

from selfdrive.carrot.lane_protocol import (
    LANE_UDP_HOST,
    LANE_UDP_PORT,
    build_lane_payload,
)


class TestLanePayload:

    def test_target_is_local_4213(self):
        # 不能发往 LAN 广播，否则会绕过 amap_navi 的唯一发布者路径
        assert LANE_UDP_HOST == "127.0.0.1"
        assert LANE_UDP_PORT == 4213

    def test_payload_matches_amap_navi_lane_contract(self):
        payload = json.loads(build_lane_payload(left_solid=True, right_solid=False, valid=True))
        assert payload["resp"] == "lane"
        assert payload["port"] == 4212
        assert payload["left_lane"] == 1
        assert payload["right_lane"] == 0
        assert payload["lane_valid"] == 1
        assert payload["sup_lidar_l"] == 0
        assert payload["sup_lidar_r"] == 0

    def test_invalid_when_no_line(self):
        payload = json.loads(build_lane_payload(left_solid=False, right_solid=False, valid=False))
        assert payload["lane_valid"] == 0


if __name__ == "__main__":
    unittest.main()
