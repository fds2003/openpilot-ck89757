#!/usr/bin/env python3
"""
manager_shm_patch.py
=====================
openpilot 启动环境隔离补丁 (移植自 cp 分支):
在受管进程拉起前，清空 /dev/shm 中残留的 cereal / openpilot 共享内存与 POSIX 信号量，
杜绝热重启后读到旧状态导致的 Steering Fault / Lateral Fault 竞态死锁。
"""
import os
import glob
import time

_SHM_DIR = "/dev/shm"
_SEGMENT_PREFIXES = ("cereal", "openpilot")
_SEM_PREFIX = "sem.cereal"

def _cleanup_shm() -> int:
  removed = 0
  if not os.path.isdir(_SHM_DIR):
    return removed

  for name in os.listdir(_SHM_DIR):
    if name.startswith(_SEGMENT_PREFIXES) or name.startswith(_SEM_PREFIX):
      try:
        os.remove(os.path.join(_SHM_DIR, name))
        removed += 1
      except Exception:
        pass

  for seg in glob.glob(os.path.join(_SHM_DIR, "sem.cereal*")):
    try:
      os.remove(seg)
      removed += 1
    except Exception:
      pass

  return removed

def cleanup_shared_memory_on_start() -> None:
  """在 manager_init() 早期调用: 清除脏段并给予内核 50ms settle 窗口"""
  try:
    removed = _cleanup_shm()
    if removed:
      print(f"[manager] Cleaned {removed} residual cereal/openpilot shm segment(s)")
    time.sleep(0.05)
  except Exception:
    pass

if __name__ == "__main__":
  cleanup_shared_memory_on_start()
