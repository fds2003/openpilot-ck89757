#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_log_rotation.py
=====================================================================
TDD 单元测试套件：C3 日志滚动周期 (7天)、目录配额 (200MB) 与 FIFO 淘汰断言
=====================================================================
"""
import unittest
import os
import shutil
import tempfile
import time

def run_log_rotation_cleanup(log_dir, max_size_bytes=200 * 1024 * 1024, retention_secs=7 * 86400):
  """提取 log_rotation 的核心清理逻辑纯函数"""
  now_ts = time.time()
  
  # 1. 清理超过保留期的旧文件
  for fname in os.listdir(log_dir):
    fpath = os.path.join(log_dir, fname)
    if os.path.isfile(fpath) and (now_ts - os.path.getmtime(fpath) > retention_secs):
      try:
        os.remove(fpath)
      except Exception:
        pass

  # 2. 空间超额按 FIFO 清理
  total_size = sum(os.path.getsize(os.path.join(log_dir, f)) for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f)))
  if total_size > max_size_bytes:
    log_files = sorted([os.path.join(log_dir, f) for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f))],
                       key=os.path.getmtime)
    while total_size > (max_size_bytes * 0.75) and log_files:
      oldest = log_files.pop(0)
      total_size -= os.path.getsize(oldest)
      os.remove(oldest)
  return total_size

class TestLogRotation(unittest.TestCase):

  def setUp(self):
    self.test_dir = tempfile.mkdtemp(prefix="test_c3_logs_")

  def tearDown(self):
    shutil.rmtree(self.test_dir, ignore_errors=True)

  def test_retention_period_7_days(self):
    """断言 1: 超过 7 天的文件必须被清理，7 天以内的文件必须被完整保留"""
    now = time.time()
    
    # 创建一个 10 天前的旧日志
    old_file = os.path.join(self.test_dir, "crash_10_days_ago.tar.gz")
    with open(old_file, "wb") as f:
      f.write(b"old log data" * 100)
    old_time = now - (10 * 86400)
    os.utime(old_file, (old_time, old_time))

    # 创建一个 3 天前的新日志
    recent_file = os.path.join(self.test_dir, "crash_3_days_ago.tar.gz")
    with open(recent_file, "wb") as f:
      f.write(b"recent log data" * 100)
    recent_time = now - (3 * 86400)
    os.utime(recent_file, (recent_time, recent_time))

    # 执行清理
    run_log_rotation_cleanup(self.test_dir, retention_secs=7*86400)

    # 断言
    self.assertFalse(os.path.exists(old_file), "10 天前的旧日志应被自动物理删除！")
    self.assertTrue(os.path.exists(recent_file), "3 天内的日志必须被正常保留！")

  def test_directory_quota_fifo_eviction(self):
    """断言 2: 当目录总体积超过限额 (模拟 100KB) 时，按 FIFO 淘汰最老文件"""
    mock_quota = 100 * 1024 # 模拟 100KB 配额
    now = time.time()

    # 创建 5 个文件，每个 30KB (总计 150KB > 100KB)
    created_files = []
    for i in range(5):
      fpath = os.path.join(self.test_dir, f"log_file_{i}.log")
      with open(fpath, "wb") as f:
        f.write(b"X" * (30 * 1024))
      # 人为拉开创建时间，file_0 最老，file_4 最新
      mtime = now - (5 - i) * 100
      os.utime(fpath, (mtime, mtime))
      created_files.append(fpath)

    # 执行清理
    remaining_size = run_log_rotation_cleanup(self.test_dir, max_size_bytes=mock_quota)

    # 断言：总大小必须下降到配额的 75% (75KB) 以下
    self.assertLessEqual(remaining_size, mock_quota * 0.75)
    # 最老的 file_0 和 file_1 应最先被淘汰
    self.assertFalse(os.path.exists(created_files[0]), "最老的文件 file_0 必须首先被淘汰！")
    self.assertFalse(os.path.exists(created_files[1]), "次老的文件 file_1 必须被淘汰！")
    # 最新的 file_4 必须存活
    self.assertTrue(os.path.exists(created_files[4]), "最新的文件 file_4 必须完好保存！")

if __name__ == "__main__":
  unittest.main()
