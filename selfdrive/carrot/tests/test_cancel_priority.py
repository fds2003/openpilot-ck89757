#!/usr/bin/env python3
"""
TDD Contract Test for P0-1: CANCEL 指令消费优先级

背景（跨端核对 AmapNavi-Reborn 确认）：
- 车机端断联（LinkHealth LOST）自动发送 CANCEL_LANE_CHANGE ×3（同一 seq），
  C3 端 amap_navi 去重（idx > cmd_index）只消费第 1 包；
- C3 端 desire_helper 的 CANCEL 分支位于 `carrot_lane_change_count > 0`
  分支之后的 elif——OVERTAKE 置 count=400 帧（20s），期间 CANCEL 被吞，
  重发同 seq 也被去重丢弃 → 断联撤销变道彻底失效。
- 契约要求（COOPERATIVE_PILOT.md）：CANCEL 指令 50ms 内立即中止变道，
  即 CANCEL 消费分支必须位于 OVERTAKE/LANECHANGE 计数分支之前，
  与触发计数互不阻塞。

本测试为源码契约测试（行为级单测依赖设备端 params .so，见 20 号文档）：
断言 desire_helper.py 中 CANCEL 消费分支出现在计数分支之前，
且 CANCEL 分支自身为独立 if（不挂在其它条件的 elif 链上）。
"""
import pytest
from pathlib import Path

DESIRE_HELPER = Path("selfdrive/controls/lib/desire_helper.py")


class TestCancelPriority:

  @pytest.fixture(autouse=True)
  def _setup(self):
    self.src = DESIRE_HELPER.read_text()

  def _pos(self, needle: str) -> int:
    pos = self.src.find(needle)
    assert pos > 0, f"未找到锚点: {needle}"
    return pos

  def test_cancel_branch_appears_before_count_branch(self):
    cancel_pos = self._pos('carrotMan.carrotCmd == "CANCEL"')
    count_pos = self._pos("if self.carrot_lane_change_count > 0:")
    assert cancel_pos < count_pos

  def test_cancel_branch_is_independent_if(self):
    # CANCEL 分支必须是独立 if（不被上一分支的 elif 链阻挡）
    cancel_pos = self._pos('carrotMan.carrotCmd == "CANCEL"')
    line_start = self.src.rfind("\n", 0, cancel_pos) + 1
    line = self.src[line_start:cancel_pos]
    assert "if " in line, "CANCEL 消费分支应为独立 if 判断"
    assert "elif" not in line, "CANCEL 消费分支不得挂在 elif 链上"


if __name__ == "__main__":
  unittest.main()
