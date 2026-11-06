#!/usr/bin/env python3
"""
TDD Contract Test: 车机侧 UDP 接收端口必须可配置且默认对局域网开放。

背景：
- S-4/S-5 曾把 4210/4211/4213/7705/7706 全部绑到 127.0.0.1，导致车机（另一台主机）
  无法登记为 client，遥测也发不出去。
- 修复口径：车机面对的 5 个 UDP 口改由 CARROT_BIND_HOST 控制，默认 0.0.0.0；
  管理通道（7710 ZMQ / 7709 路由 / 12345 Kisa）保持 loopback 不变。
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class TestCarrotBindHost(unittest.TestCase):

    def test_amap_navi_bind_host_configurable(self):
        src = read("amap_navi.py")
        self.assertIn('os.environ.get("CARROT_BIND_HOST", "0.0.0.0")', src)
        for port in ("4210", "self.navi_remote_port", "self.lane_port", "self.listen_port"):
            self.assertIn("bind((self.bind_host, %s))" % port, src, port)

    def test_carrot_man_bind_host_configurable(self):
        src = read("carrot_man.py")
        self.assertIn('os.environ.get("CARROT_BIND_HOST", "0.0.0.0")', src)
        self.assertIn("bind((self.bind_host, self.carrot_man_port))", src)

    def test_no_hardcoded_loopback_on_headunit_ports(self):
        patterns = [
            r"bind\(\('127\.0\.0\.1', 4210\)",
            r"bind\(\('127\.0\.0\.1', 4211\)",
            r"bind\(\('127\.0\.0\.1', 4213\)",
            r"bind\(\('127\.0\.0\.1', 7705\)",
            r"bind\(\('127\.0\.0\.1', 7706\)",
        ]
        for name in ("amap_navi.py", "carrot_man.py"):
            src = read(name)
            for pat in patterns:
                self.assertIsNone(re.search(pat, src), "%s still hardcodes %s" % (name, pat))

    def test_management_channels_stay_loopback(self):
        amap = read("amap_navi.py")
        man = read("carrot_man.py")
        self.assertIn('socket.bind("tcp://127.0.0.1:7710")', man)
        self.assertIn("sock.bind(('127.0.0.1', 12345))", man)
        self.assertIn("host = '127.0.0.1'", man)
        self.assertNotIn('bind(("0.0.0.0", 7710))', man)
        self.assertIn("self.bind_host", amap)


if __name__ == "__main__":
    unittest.main()
