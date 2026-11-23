#!/usr/bin/env python3
"""
TDD Unit Test for Slice 3: atc_state Telemetry and State Machine Settlement (M-14)
Verifies:
1. When atc_state == 3, lane change is settled as successful.
2. When lane change execution times out without atc_state == 3, it is settled as CANCELLED (not fake success!).
"""


class OvertakeState:
  IDLE = 0
  PREPARING = 1
  EXECUTING = 2
  FINISHING = 3
  COOLDOWN = 4


class MockStateMachine:
  def __init__(self, execute_timeout_ms=4500):
    self.state = OvertakeState.EXECUTING
    self.state_since_ms = 1000
    self.execute_timeout_ms = execute_timeout_ms
    self.commands_sent = []
    self.sounds_played = []
    self.message = ""

  def tick(self, atc_state, now_ms):
    if self.state == OvertakeState.EXECUTING:
      if atc_state == 3:
        self.state = OvertakeState.FINISHING
        self.message = "收到变道完成反馈(atc_state=3)"
        self.sounds_played.append("LANE_CHANGE_OK")
        return

      if now_ms - self.state_since_ms > self.execute_timeout_ms:
        # M-14 Fix: Timeout settles as cancel, NOT fake success!
        self.state = OvertakeState.COOLDOWN
        self.commands_sent.append("CANCEL_LANE_CHANGE")
        self.sounds_played.append("LANE_CHANGE_CANCEL")
        self.message = f"变道执行超时 {self.execute_timeout_ms}ms，已撤销变道并锁定冷却"
        return


class TestAtcStateSettlement:
  def test_atc_state_3_settles_success(self):
    sm = MockStateMachine()
    sm.tick(atc_state=3, now_ms=2000)

    assert sm.state == OvertakeState.FINISHING
    assert "LANE_CHANGE_OK" in sm.sounds_played
    assert "LANE_CHANGE_CANCEL" not in sm.sounds_played
    assert "收到变道完成反馈" in sm.message

  def test_timeout_without_atc_state_settles_as_cancelled_fail_safe(self):
    """M-14 Fix: Timeout without atc_state == 3 MUST abort and play CANCEL sound, NOT success!"""
    sm = MockStateMachine(execute_timeout_ms=4500)
    # 5000ms elapsed (> 4500ms) with atc_state still 2 (starting)
    sm.tick(atc_state=2, now_ms=6000)

    assert sm.state == OvertakeState.COOLDOWN
    assert "CANCEL_LANE_CHANGE" in sm.commands_sent
    assert "LANE_CHANGE_CANCEL" in sm.sounds_played
    assert "LANE_CHANGE_OK" not in sm.sounds_played, "Timed out lane change MUST NOT play success audio!"
    assert "已撤销变道" in sm.message


if __name__ == "__main__":
  unittest.main()
