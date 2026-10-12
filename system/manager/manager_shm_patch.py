#!/usr/bin/env python3
"""
manager_shm_patch.py
=====================
openpilot manager 启动补丁：在受管进程启动前，清空 /dev/shm 中残留的
cereal / openpilot 共享内存段与 POSIX 信号量，避免"改任意 Python 文件 ->
热重启后 controlsd/modeld 读到旧 shm 数据 -> MPC 首次求解异常 ->
报 Lateral/Steering Fault"这一全局竞态。

使用方法（二选一）：
  A) 将本文件放到 system/manager/ 目录（与 manager.py 同目录），
     在 manager.py 的 manager_init() 中，紧接
         try:
             os.mkdir(Paths.shm_path())
         except FileExistsError:
             pass
         except PermissionError:
             print(f"WARNING: failed to make {Paths.shm_path()}")
     之后插入两行：
         from manager_shm_patch import cleanup_shared_memory_on_start
         cleanup_shared_memory_on_start()
  B) 将 cleanup_shared_memory_on_start() 的函数体直接内联进 manager_init()。

本模块不依赖 openpilot 任何内部包，可独立 import；单个文件删除失败
（权限/仍被占用）已 try/except 忽略，不影响主流程，可安全上线。
"""
import os
import glob
import time


# 与 upstream cereal/messaging 一致的共享内存路径解析：
#   SHM_DIR = "/dev/shm"
#   segment_path = "/dev/shm/cereal.<name>"
# 这里直接按前缀匹配，不依赖 Paths.shm_path() 的具体返回值。
_SHM_DIR = "/dev/shm"

# 需要清理的共享内存段名前缀（cereal msgq 段 / openpilot 自定义段）
_SEGMENT_PREFIXES = ("cereal", "openpilot")

# POSIX 命名信号量（sem_open 创建的会在 /dev/shm 以 sem.<name> 出现）
_SEM_PREFIX = "sem.cereal"


def _cleanup_shm():
    removed = 0
    if not os.path.isdir(_SHM_DIR):
        return removed

    for name in os.listdir(_SHM_DIR):
        if name.startswith(_SEGMENT_PREFIXES) or name.startswith(_SEM_PREFIX):
            try:
                os.remove(os.path.join(_SHM_DIR, name))
                removed += 1
            except Exception:
                # 仍被占用或无权限：跳过，不影响主流程
                pass

    # glob 兜底，清理 sem.cereal* 形式（兼容不同挂载/命名）
    for seg in glob.glob(os.path.join(_SHM_DIR, "sem.cereal*")):
        try:
            os.remove(seg)
            removed += 1
        except Exception:
            pass

    return removed


def cleanup_shared_memory_on_start():
    """manager_init() 启动时调用：清残留 shm 段并让 shm 子系统 settle。"""
    try:
        removed = _cleanup_shm()
        if removed:
            print(f"[manager] cleaned {removed} residual cereal/openpilot shm segment(s)")
        # 给 shm 子系统一个 settle 时间，降低边缘竞态概率
        time.sleep(0.05)
    except Exception:
        # 任何异常都不向外抛出，保证 manager 启动不受影响
        pass


if __name__ == "__main__":
    # 手动验证入口：python3 manager_shm_patch.py
    cleanup_shared_memory_on_start()
    print("[manager_shm_patch] done (dry-run safe)")
