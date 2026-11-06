#!/usr/bin/env python3
"""TDD: lane_runner 运行时前置条件检查与依赖声明契约。"""
import os
import tempfile
import unittest
from unittest import mock

from selfdrive.carrot import lane_runtime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestCheckRuntime(unittest.TestCase):

    def test_missing_onnxruntime(self):
        with mock.patch.object(lane_runtime.importlib.util, "find_spec", return_value=None):
            ok, msg = lane_runtime.check_runtime("/nonexistent/lane.onnx")
        self.assertFalse(ok)
        self.assertIn("onnxruntime", msg)

    def test_missing_model(self):
        with mock.patch.object(lane_runtime.importlib.util, "find_spec", return_value=object()):
            ok, msg = lane_runtime.check_runtime("/nonexistent/lane.onnx")
        self.assertFalse(ok)
        self.assertIn("/nonexistent/lane.onnx", msg)

    def test_ready(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            with mock.patch.object(lane_runtime.importlib.util, "find_spec", return_value=object()):
                ok, msg = lane_runtime.check_runtime(path)
            self.assertTrue(ok)
            self.assertEqual(msg, "")
        finally:
            os.remove(path)


class TestDependencyContract(unittest.TestCase):

    def test_lane_requirements_declares_onnxruntime(self):
        # 不写入 pyproject/uv.lock：避免镜像源改写全局锁文件；C3 用独立 requirements 安装
        text = read("selfdrive/carrot/requirements_lane.txt")
        self.assertIn("onnxruntime", text)

    def test_process_config_includes_lane_runner(self):
        text = read("system/manager/process_config.py")
        self.assertIn('PythonProcess("lane_runner", "selfdrive.carrot.lane_runner"', text)


if __name__ == "__main__":
    unittest.main()
