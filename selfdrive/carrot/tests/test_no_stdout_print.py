#!/usr/bin/env python3
"""
TDD Contract Test for P1-3: desire_helper.py 控制循环禁止 print 直写 stdout

AGENTS.md：控制循环不得执行阻塞 I/O——print 直写 stdout 在设备上为
行缓冲阻塞调用，100Hz 循环内存在卡帧风险；结构化日志应走 cloudlog
（ZMQ IPC 非阻塞）。契约：
1. 不得存在未注释的 print( 调用（注释掉的历史调试不受影响）
2. cloudlog 已导入（from openpilot.common.swaglog import cloudlog）
"""
import re
import unittest
from pathlib import Path

DESIRE_HELPER = Path("selfdrive/controls/lib/desire_helper.py")


class TestNoStdoutPrint(unittest.TestCase):

  def setUp(self):
    self.lines = DESIRE_HELPER.read_text().split('\n')

  def test_no_active_print_calls(self):
    bad = []
    for i, l in enumerate(self.lines, 1):
      code = l.split('#')[0] if not l.lstrip().startswith('#') else ''
      # 简易去注释：字符串内 # 不影响本文件实际形态，仅查行首非注释出现
      code = l
      stripped = code.strip()
      if stripped.startswith('#'):
        continue
      if re.search(r'(?<![#\w])print\(', code):
        bad.append(f"L{i}: {stripped[:60]}")
    self.assertEqual(bad, [], f"desire_helper.py 存在 stdout print 调用（应改 cloudlog）:\n" + "\n".join(bad))

  def test_cloudlog_imported(self):
    src = DESIRE_HELPER.read_text()
    self.assertIn("from openpilot.common.swaglog import cloudlog", src)


if __name__ == "__main__":
  unittest.main()
