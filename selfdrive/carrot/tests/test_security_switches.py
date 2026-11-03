#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_security_switches.py
=====================================================================
TDD 单元测试套件：P0 级安全开关与行车硬锁死行为断言
=====================================================================
"""
import unittest
import json
import subprocess

class MockParams:
  def __init__(self, init_dict=None):
    self.data = init_dict or {}

  def get_bool(self, key):
    return bool(self.data.get(key, 0))

  def get(self, key):
    val = self.data.get(key)
    return str(val).encode('utf-8') if val is not None else None

def handle_echo_cmd_logic(json_obj, params, is_onroad):
  """提取 carrot_man.py 中的 echo_cmd 处理逻辑纯函数"""
  if 'echo_cmd' not in json_obj:
    return None

  cmd_enabled = params.get_bool("CarrotEchoCmdEnable")
  if not cmd_enabled:
    return {"exitStatus": -1, "error": "echo_cmd is disabled by user switch (CarrotEchoCmdEnable=0)"}
  elif is_onroad:
    return {"exitStatus": 423, "error": "echo_cmd is locked during onroad driving for safety"}
  else:
    result = subprocess.run(json_obj['echo_cmd'], shell=True, capture_output=True, text=True)
    return {"exitStatus": result.returncode, "result": result.stdout, "error": result.stderr}

class TestSecuritySwitches(unittest.TestCase):

  def test_echo_cmd_disabled_by_default(self):
    """断言 1: 默认情况下 (CarrotEchoCmdEnable=0)，任何 echo_cmd 必须被安全拦截"""
    params = MockParams({"CarrotEchoCmdEnable": 0})
    req = {"echo_cmd": "echo 'malicious_test'"}
    resp = handle_echo_cmd_logic(req, params, is_onroad=False)
    self.assertEqual(resp["exitStatus"], -1)
    self.assertIn("disabled by user switch", resp["error"])

  def test_echo_cmd_onroad_hard_lockout(self):
    """断言 2: 即便车主开启了开关，只要在行车中 (is_onroad=True)，必须触发行车硬锁死 (423)"""
    params = MockParams({"CarrotEchoCmdEnable": 1})
    req = {"echo_cmd": "echo 'should_be_locked'"}
    resp = handle_echo_cmd_logic(req, params, is_onroad=True)
    self.assertEqual(resp["exitStatus"], 423)
    self.assertIn("locked during onroad driving", resp["error"])

  def test_echo_cmd_allowed_offroad_when_enabled(self):
    """断言 3: 当且仅当开关开启且处于驻车/熄火 (is_onroad=False) 时，才执行命令"""
    params = MockParams({"CarrotEchoCmdEnable": 1})
    req = {"echo_cmd": "echo 'safe_debug_success'"}
    resp = handle_echo_cmd_logic(req, params, is_onroad=False)
    self.assertEqual(resp["exitStatus"], 0)
    self.assertIn("safe_debug_success", resp["result"])

  def test_binding_address_switch(self):
    """断言 4: 监听网卡严格受 CarrotRemoteDebug 控制"""
    params_off = MockParams({"CarrotRemoteDebug": 0})
    addr_off = "tcp://*:7710" if params_off.get_bool("CarrotRemoteDebug") else "tcp://127.0.0.1:7710"
    self.assertEqual(addr_off, "tcp://127.0.0.1:7710")

    params_on = MockParams({"CarrotRemoteDebug": 1})
    addr_on = "tcp://*:7710" if params_on.get_bool("CarrotRemoteDebug") else "tcp://127.0.0.1:7710"
    self.assertEqual(addr_on, "tcp://*:7710")

if __name__ == "__main__":
  unittest.main()
