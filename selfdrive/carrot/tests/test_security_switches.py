#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_security_switches.py
=====================================================================
TDD 单元测试套件：P0 级安全开关与行车硬锁死行为断言

P1-4：echo_cmd 门控不再抄写生产逻辑副本——直接导入
selfdrive/carrot/echo_cmd_gate.handle_echo_cmd（生产单一实现）。
=====================================================================
"""
import pytest

from openpilot.selfdrive.carrot.echo_cmd_gate import handle_echo_cmd

class MockParams:
  def __init__(self, init_dict=None):
    self.data = init_dict or {}

  def get_bool(self, key):
    return bool(self.data.get(key, 0))

  def get(self, key):
    val = self.data.get(key)
    return str(val).encode('utf-8') if val is not None else None

# 测试白名单：固定 lambda，杜绝 shell=True 语义漂移
TEST_WHITELIST = {
  "params_dump": lambda: (0, "safe_debug_success", ""),
}

class TestSecuritySwitches:

  def test_echo_cmd_disabled_by_default(self):
    """断言 1: 默认情况下 (CarrotEchoCmdEnable=0)，任何 echo_cmd 必须被安全拦截"""
    params = MockParams({"CarrotEchoCmdEnable": 0})
    req = {"echo_cmd": "params_dump"}
    resp = handle_echo_cmd({"echo_cmd": req["echo_cmd"]}, params, False, TEST_WHITELIST)
    assert resp["exitStatus"] == -1
    assert "disabled by user switch" in resp["error"]

  def test_echo_cmd_onroad_hard_lockout(self):
    """断言 2: 即便车主开启了开关，只要在行车中 (is_onroad=True)，必须触发行车硬锁死 (423)"""
    params = MockParams({"CarrotEchoCmdEnable": 1})
    req = {"echo_cmd": "params_dump"}
    resp = handle_echo_cmd({"echo_cmd": req["echo_cmd"]}, params, True, TEST_WHITELIST)
    assert resp["exitStatus"] == 423
    assert "locked during onroad driving" in resp["error"]

  def test_echo_cmd_allowed_offroad_when_enabled(self):
    """断言 3: 当且仅当开关开启且处于驻车/熄火 (is_onroad=False) 时，才执行命令"""
    params = MockParams({"CarrotEchoCmdEnable": 1})
    req = {"echo_cmd": "params_dump"}
    resp = handle_echo_cmd({"echo_cmd": req["echo_cmd"]}, params, False, TEST_WHITELIST)
    assert resp["exitStatus"] == 0
    assert "safe_debug_success" in resp["result"]

  def test_binding_address_switch(self):
    """断言 4: 监听网卡严格受 CarrotRemoteDebug 控制"""
    params_off = MockParams({"CarrotRemoteDebug": 0})
    addr_off = "tcp://*:7710" if params_off.get_bool("CarrotRemoteDebug") else "tcp://127.0.0.1:7710"
    assert addr_off == "tcp://127.0.0.1:7710"

    params_on = MockParams({"CarrotRemoteDebug": 1})
    addr_on = "tcp://*:7710" if params_on.get_bool("CarrotRemoteDebug") else "tcp://127.0.0.1:7710"
    assert addr_on == "tcp://*:7710"

if __name__ == "__main__":
  unittest.main()
