#!/usr/bin/env python3
"""TDD: VisionIPC NV12 帧到模型输入张量（纯 numpy）。"""
import unittest

import numpy as np

from selfdrive.carrot.lane_image import nv12_to_rgb, to_input_tensor


def make_nv12(y_value, uv_value=128, width=4, height=4, stride=4):
    y = np.full((height, stride), y_value, dtype=np.uint8)
    uv = np.full((height // 2, stride), uv_value, dtype=np.uint8)
    return np.concatenate([y.ravel(), uv.ravel()]).tobytes()


class TestNv12ToRgb(unittest.TestCase):

    def test_black_frame(self):
        rgb = nv12_to_rgb(make_nv12(16), 4, 4, 4)
        self.assertEqual(rgb.shape, (4, 4, 3))
        self.assertTrue((rgb < 8).all())

    def test_white_frame(self):
        rgb = nv12_to_rgb(make_nv12(235), 4, 4, 4)
        self.assertTrue((rgb > 240).all())

    def test_stride_larger_than_width(self):
        # stride 6 > width 4，右侧两列填充应被裁掉
        rgb = nv12_to_rgb(make_nv12(16, width=4, height=4, stride=6), 4, 4, 6)
        self.assertEqual(rgb.shape, (4, 4, 3))


class TestInputTensor(unittest.TestCase):

    def test_shape_and_range(self):
        rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
        tensor = to_input_tensor(rgb, size=416)
        self.assertEqual(tensor.shape, (1, 3, 416, 416))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertAlmostEqual(float(tensor.max()), 1.0, places=5)
        self.assertAlmostEqual(float(tensor.min()), 1.0, places=5)

    def test_channel_order_rgb(self):
        rgb = np.zeros((8, 8, 3), dtype=np.uint8)
        rgb[:, :, 0] = 255  # R
        tensor = to_input_tensor(rgb, size=8)
        self.assertAlmostEqual(float(tensor[0, 0].mean()), 1.0, places=5)
        self.assertAlmostEqual(float(tensor[0, 1].mean()), 0.0, places=5)
        self.assertAlmostEqual(float(tensor[0, 2].mean()), 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
