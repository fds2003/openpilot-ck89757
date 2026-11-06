#!/usr/bin/env python3
"""TDD: 车机 UDP 源信任策略。

目标：替换"首连即学习"的宽松行为。
- 回环永远允许；
- 已学习或显式白名单中的 IP 允许；
- 配置了显式白名单时进入严格模式，同网段也不再自动学习；
- 未配置白名单时，仅允许同网段主机并学习；
- 本地 IP 未知或非法时一律拒绝（fail-closed）。
"""
import os
import unittest

from selfdrive.carrot.udp_trust import evaluate, parse_allowed, same_subnet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestSameSubnet(unittest.TestCase):

    def test_same_24(self):
        self.assertTrue(same_subnet("192.168.43.5", "192.168.43.120"))

    def test_different_24(self):
        self.assertFalse(same_subnet("192.168.3.5", "192.168.43.120"))

    def test_invalid_local(self):
        self.assertFalse(same_subnet("192.168.43.5", ""))

    def test_ipv6_uses_64(self):
        self.assertTrue(same_subnet("fe80::1", "fe80::2"))


class TestEvaluate(unittest.TestCase):

    def test_loopback_always_trusted(self):
        self.assertEqual(evaluate("127.0.0.1", "192.168.43.120", set(), set()), (True, False))

    def test_same_subnet_learned_when_no_allowlist(self):
        self.assertEqual(evaluate("192.168.43.5", "192.168.43.120", set(), set()), (True, True))

    def test_other_subnet_rejected(self):
        self.assertEqual(evaluate("10.0.0.9", "192.168.43.120", set(), set()), (False, False))

    def test_learned_ip_trusted(self):
        self.assertEqual(evaluate("10.0.0.9", "192.168.43.120", {"10.0.0.9"}, set()), (True, False))

    def test_allowlist_strict_mode(self):
        allowed = {"192.168.43.5"}
        self.assertEqual(evaluate("192.168.43.5", "192.168.43.120", set(), allowed), (True, False))
        # 显式白名单存在时，同网段未列出的主机也不再自动学习
        self.assertEqual(evaluate("192.168.43.6", "192.168.43.120", set(), allowed), (False, False))

    def test_unknown_local_ip_fails_closed(self):
        self.assertEqual(evaluate("192.168.43.5", "", set(), set()), (False, False))


class TestParseAllowed(unittest.TestCase):

    def test_none(self):
        self.assertEqual(parse_allowed(None), set())

    def test_bytes(self):
        self.assertEqual(parse_allowed(b"192.168.43.5, 192.168.43.6"), {"192.168.43.5", "192.168.43.6"})

    def test_empty_entries(self):
        self.assertEqual(parse_allowed(" , 10.0.0.1 , "), {"10.0.0.1"})


class TestWiring(unittest.TestCase):

    def test_amap_navi_uses_trust_policy(self):
        text = read("selfdrive/carrot/amap_navi.py")
        self.assertIn("udp_trust", text)
        self.assertIn("CarrotUdpAllowedIps", text)

    def test_carrot_man_uses_trust_policy(self):
        text = read("selfdrive/carrot/carrot_man.py")
        self.assertIn("udp_trust", text)
        self.assertIn("CarrotUdpAllowedIps", text)


if __name__ == "__main__":
    unittest.main()
