#!/usr/bin/env python3
"""
TDD Contract Test for 库斯途参数基线（标定种子值回归锁）。

背景：BsdDelayTime 种子 20→10（减少盲区提示尾音）当初未走 TDD，本测试
补上回归锁，并将本次会话调校的全部标定种子值一并锁定，防止后续改动
无意回退这些针对库斯途实测确认过的值。

锁定的基线（每项对应一次独立修复提交）：
- DisableDM=0          默认开启驾驶监控
- SteerActuatorDelay=15  与 interface.py Custin 0.15s 标定对齐
- BsdDelayTime=10       盲区尾音 1.0s（减少误报）
- RearRadarEnable 不入种子表（UnifiedParams 回退 config.py 默认 0 = 未装雷达）
"""
import ast
import unittest
from pathlib import Path

MANAGER = Path("system/manager/manager.py")

# 库斯途参数基线：种子键 → 期望值
BASELINE = {
  "DisableDM": "0",
  "SteerActuatorDelay": "15",
  "BsdDelayTime": "10",
}


class TestCustinParamBaseline(unittest.TestCase):

  def setUp(self):
    src = MANAGER.read_text()
    tree = ast.parse(src)
    self.seeds = {}
    for node in ast.walk(tree):
      if isinstance(node, ast.FunctionDef) and node.name == "get_default_params":
        for n in ast.walk(node):
          if isinstance(n, ast.Tuple) and len(n.elts) == 2:
            try:
              k = ast.literal_eval(n.elts[0])
              v = ast.literal_eval(n.elts[1])
              self.seeds[k] = v
            except (ValueError, SyntaxError):
              pass

  def test_baseline_seeds(self):
    mismatch = {k: (self.seeds.get(k), v) for k, v in BASELINE.items()
                if self.seeds.get(k) != v}
    self.assertEqual(mismatch, {},
                     "库斯途标定种子值被改动（如有意调整请同步更新本基线测试）:\n"
                     + "\n".join(f"{k}: 现值={got} 期望={exp}" for k, (got, exp) in mismatch.items()))


if __name__ == "__main__":
  unittest.main()
