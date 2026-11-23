#!/usr/bin/env python3
"""
TDD Contract Test for P2-2: _clean_clients_thread 异常处理收窄

问题：`except (KeyError, RuntimeError, Exception)` 把预期异常与兜底
混在一个 handler 里无声吞掉（print 一行无栈追踪），掩盖真实缺陷。
契约：
1. 预期异常收窄为 (KeyError, RuntimeError, TypeError)（字典竞态/迭代变更/畸形客户端帧）
2. 兜底改 cloudlog.exception（带栈追踪上报，不再无声吞掉）
3. 看门狗线程保留存活能力（兜底后继续循环）
"""
import unittest
from pathlib import Path

AMAP_NAVI = Path("selfdrive/carrot/amap_navi.py")


class TestCleanClientsExceptionNarrowing(unittest.TestCase):

  def setUp(self):
    self.src = AMAP_NAVI.read_text()
    start = self.src.find("def _clean_clients_thread")
    end = self.src.find("def navi_broadcast_info")
    self.body = self.src[start:end]

  def test_broad_exception_tuple_removed(self):
    self.assertNotIn("except (KeyError, RuntimeError, Exception)", self.body,
                     "P2-2: 预期异常与兜底 Exception 混列，须收窄")

  def test_expected_exceptions_narrowed(self):
    self.assertIn("except (KeyError, RuntimeError, TypeError)", self.body)

  def test_fallback_logs_with_traceback(self):
    self.assertIn("cloudlog.exception", self.body,
                  "P2-2: 兜底必须 cloudlog.exception 带栈追踪，不得无声吞掉")


if __name__ == "__main__":
  unittest.main()
