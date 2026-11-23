#!/usr/bin/env python3
"""
TDD tests for P1-4: 指令解析与 echo_cmd 网关必须复用生产逻辑。

- 生产 falsy-0 bug：`json_obj.get("index") or json_obj.get("seq")` 在
  index=0（车机重启后第一条指令的合法序号）时为假值被跳过 → 静默丢弃。
  修复：显式 `if "index" in json_obj` 判断（生产 parse_remote_command）。
- 测试不得抄写生产逻辑副本（test_security_switches 的 shell=True 副本
  与生产白名单语义背离）——统一 import 生产函数。
"""
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "selfdrive", "carrot", "tests"))

from test_quality_fixes_q4_q5_q6 import _install_stubs, _load_module

AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")

_install_stubs()
amap = _load_module("amap_navi_p14", AMAP_NAVI)


def make_shared():
  return amap.SharedData()


class TestParseRemoteCommand:

  def test_index_zero_first_command_not_dropped(self):
    """P1-4 核心：index=0 是车机重启后首条指令的合法序号，不得被 falsy 判断丢弃"""
    shared = make_shared()
    amap.parse_remote_command({"cmd": "LANECHANGE", "arg": "LEFT", "index": 0}, shared)
    assert shared.cmd_index == 0, f"index=0 被丢弃, cmd_index={shared.cmd_index}"
    assert shared.remote_cmd == "LANECHANGE"

  def test_seq_fallback_when_index_missing(self):
    shared = make_shared()
    amap.parse_remote_command({"cmd": "LANECHANGE", "arg": "LEFT", "seq": 5}, shared)
    assert shared.cmd_index == 5
    assert shared.remote_cmd == "LANECHANGE"

  def test_older_seq_rejected(self):
    shared = make_shared()
    amap.parse_remote_command({"cmd": "LANECHANGE", "arg": "LEFT", "index": 10}, shared)
    amap.parse_remote_command({"cmd": "LANECHANGE", "arg": "RIGHT", "index": 5}, shared)
    assert shared.cmd_index == 10
    assert shared.remote_cmd == "LANECHANGE"
    assert shared.remote_arg == "LEFT"  # 旧包不得覆盖

  def test_cancel_command_mapping(self):
    shared = make_shared()
    amap.parse_remote_command({"cmd": "CANCEL_LANE_CHANGE", "index": 3}, shared)
    assert shared.remote_cmd == "CANCEL"

  def test_overtake_param_clamped(self):
    shared = make_shared()
    amap.parse_remote_command({"cmd": "OVERTAKE", "arg": "LEFT", "index": 1, "param": 9}, shared)
    assert shared.overtake_mode == 1  # 9 越界 → 保持默认 1
    amap.parse_remote_command({"cmd": "OVERTAKE", "arg": "LEFT", "index": 2, "param": 0}, shared)
    assert shared.overtake_mode == 0


class TestEchoCmdGate:

  def _gate(self, params, is_onroad):
    from openpilot.selfdrive.carrot.echo_cmd_gate import handle_echo_cmd
    whitelist = {
      "params_dump": lambda: (0, "ok-out", "ok-err"),
    }
    return handle_echo_cmd({"echo_cmd": self.cmd}, params, is_onroad, whitelist)

  def test_disabled_by_default(self):
    class P:
      def get_bool(self, key): return False
    self.cmd = "params_dump"
    resp = self._gate(P(), False)
    assert resp["exitStatus"] == -1 and "disabled" in resp["error"]

  def test_locked_onroad_423(self):
    class P:
      def get_bool(self, key): return True
    self.cmd = "params_dump"
    resp = self._gate(P(), True)
    assert resp["exitStatus"] == 423

  def test_not_in_whitelist_rejected(self):
    class P:
      def get_bool(self, key): return True
    self.cmd = "denied_cmd"  # 不在白名单
    resp = self._gate(P(), False)
    assert resp["exitStatus"] == -3

  def test_whitelisted_executes(self):
    class P:
      def get_bool(self, key): return True
    self.cmd = "params_dump"
    resp = self._gate(P(), False)
    assert resp["exitStatus"] == 0 and resp["result"] == "ok-out"
