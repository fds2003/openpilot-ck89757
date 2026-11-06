#!/usr/bin/env python3
"""lane_runner -> amap_navi 的本地 UDP 载荷契约。

设计约束：
- `amapNavi` 的唯一发布者是 carrot_man 内嵌的 AmapNaviServ；
  lane_runner 不能再建 PubMaster(['amapNavi'])，否则触发 MultiplePublishersError。
- 因此 lane_runner 走本地 UDP 4213，由 amap_navi._lane_recv_thread 消费，
  再由唯一发布者写入 amapNavi.leftLine/rightLine。
"""
import json

LANE_UDP_HOST = "127.0.0.1"
LANE_UDP_PORT = 4213
LANE_APP_PORT = 4212  # 与原版 APK 的 laneAppPort 保持一致


def build_lane_payload(left_solid, right_solid, valid):
    return json.dumps({
        "resp": "lane",
        "port": LANE_APP_PORT,
        "left_lane": 1 if left_solid else 0,
        "right_lane": 1 if right_solid else 0,
        "lane_valid": 1 if valid else 0,
        "sup_lidar_l": 0,
        "sup_lidar_r": 0,
    }, separators=(",", ":"))
