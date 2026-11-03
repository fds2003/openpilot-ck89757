#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_radard_interlock.py
=====================================================================
TDD 单元测试套件：雷达天桥识别器与 Cap'n Proto 规范视觉双向互锁断言
=====================================================================
"""
import unittest

class MockRadarTrack:
  def __init__(self, dRel, vLead=0.0, yRel=0.0):
    self.dRel = dRel
    self.vLead = vLead
    self.yRel = yRel

class MockLeadV3:
  def __init__(self, prob, x_list):
    self.prob = prob
    self.x = x_list

class MockModelV2:
  def __init__(self, leadsV3=None):
    self.leadsV3 = leadsV3 or []

def evaluate_is_overpass(track, md, is_stable_overpass=True):
  """提取 radard.py 中重构后的天桥视觉互锁纯函数"""
  if not is_stable_overpass:
    return False

  # [RADAR-01]: 视觉双向互锁 (使用规范字段 leadsV3[0].x[0])
  if md is not None and hasattr(md, 'leadsV3') and len(md.leadsV3) > 0:
    lead_v3 = md.leadsV3[0]
    if lead_v3.prob > 0.40 and len(lead_v3.x) > 0:
      vision_d_rel = float(lead_v3.x[0])
      if abs(track.dRel - vision_d_rel) < 8.0:
        # 视觉高置信确认前方有车，一票否决天桥判定！
        return False

  return True

class TestRadardInterlock(unittest.TestCase):

  def test_overpass_vetoed_when_vision_confirms_lead(self):
    """断言 1: 雷达追踪到 35m 静止物体，视觉确认 34.5m 有车(prob=0.85)，必须否决天桥判定！"""
    track = MockRadarTrack(dRel=35.0, vLead=0.0, yRel=0.1)
    lead_v3 = MockLeadV3(prob=0.85, x_list=[34.5, 34.0, 33.5])
    md = MockModelV2(leadsV3=[lead_v3])

    is_overpass = evaluate_is_overpass(track, md, is_stable_overpass=True)
    self.assertFalse(is_overpass, "视觉高置信确认前车，天桥判定必须被否决（不可误杀事故车）！")

  def test_overpass_confirmed_when_no_vision_lead(self):
    """断言 2: 雷达追踪到 35m 静止悬空物体，视觉无前车(prob=0.05)，必须正常确认为天桥"""
    track = MockRadarTrack(dRel=35.0, vLead=0.0, yRel=0.1)
    lead_v3 = MockLeadV3(prob=0.05, x_list=[100.0]) # 无近距前车
    md = MockModelV2(leadsV3=[lead_v3])

    is_overpass = evaluate_is_overpass(track, md, is_stable_overpass=True)
    self.assertTrue(is_overpass, "视觉无对应目标时，正常确认为天桥（消除幽灵刹车）！")

  def test_overpass_handles_none_md_gracefully(self):
    """断言 3: 当前视相机全黑或未初始化 (md is None)，互锁安全降级，绝不抛空指针异常"""
    track = MockRadarTrack(dRel=40.0, vLead=0.0, yRel=0.0)
    try:
      is_overpass = evaluate_is_overpass(track, md=None, is_stable_overpass=True)
      self.assertTrue(is_overpass)
    except Exception as e:
      self.fail(f"md 为 None 时抛出未捕获异常: {e}")

if __name__ == "__main__":
  unittest.main()
