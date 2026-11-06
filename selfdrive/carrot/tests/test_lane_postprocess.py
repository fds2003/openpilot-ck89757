#!/usr/bin/env python3
"""TDD: YOLO-seg 后处理与左右车道选择（纯 numpy，可在 PC 上验证）。"""
import unittest

import numpy as np

from selfdrive.carrot.lane_postprocess import (
    Detection,
    LaneTypes,
    decode,
    select_lane_types,
)


def make_preds(anchors):
    """anchors: [(cx, cy, w, h, cls, score), ...] -> (42, N)"""
    preds = np.zeros((42, len(anchors)), dtype=np.float32)
    for i, (cx, cy, w, h, cls, score) in enumerate(anchors):
        preds[0, i] = cx
        preds[1, i] = cy
        preds[2, i] = w
        preds[3, i] = h
        preds[4 + cls, i] = score
    return preds


def make_det(cls, cx, bottom=103, proto=104, score=0.9):
    mask = np.zeros((proto, proto), dtype=bool)
    mask[bottom, cx] = True
    return Detection(cls=cls, score=score, box=(0.0, 0.0, 1.0, 1.0), mask=mask)


class TestDecode(unittest.TestCase):

    def test_confidence_filter(self):
        preds = make_preds([
            (100.0, 200.0, 20.0, 40.0, 0, 0.90),
            (300.0, 200.0, 20.0, 40.0, 1, 0.10),
        ])
        proto = np.zeros((32, 104, 104), dtype=np.float32)
        dets = decode(preds, proto, conf=0.25, iou=0.5)
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0].cls, 0)

    def test_nms_suppresses_same_class_overlap(self):
        preds = make_preds([
            (100.0, 200.0, 40.0, 40.0, 0, 0.90),
            (102.0, 202.0, 40.0, 40.0, 0, 0.80),
        ])
        proto = np.zeros((32, 104, 104), dtype=np.float32)
        dets = decode(preds, proto, conf=0.25, iou=0.5)
        self.assertEqual(len(dets), 1)
        self.assertAlmostEqual(dets[0].score, 0.90, places=5)

    def test_nms_keeps_different_classes(self):
        preds = make_preds([
            (100.0, 200.0, 40.0, 40.0, 0, 0.90),
            (102.0, 202.0, 40.0, 40.0, 1, 0.80),
        ])
        proto = np.zeros((32, 104, 104), dtype=np.float32)
        dets = decode(preds, proto, conf=0.25, iou=0.5)
        self.assertEqual(len(dets), 2)
        self.assertEqual({d.cls for d in dets}, {0, 1})

    def test_box_converted_to_pixels(self):
        preds = make_preds([(100.0, 200.0, 20.0, 40.0, 0, 0.90)])
        proto = np.zeros((32, 104, 104), dtype=np.float32)
        det = decode(preds, proto)[0]
        self.assertAlmostEqual(det.box[0], 90.0)
        self.assertAlmostEqual(det.box[1], 180.0)
        self.assertAlmostEqual(det.box[2], 110.0)
        self.assertAlmostEqual(det.box[3], 220.0)

    def test_mask_composition(self):
        coeff = np.zeros(32, dtype=np.float32)
        coeff[0] = 1.0
        proto = np.zeros((32, 104, 104), dtype=np.float32)
        proto[0, 50:60, 20:30] = 1.0
        preds = make_preds([(100.0, 220.0, 80.0, 80.0, 0, 0.90)])  # 416->104: x[15,35] y[45,65]
        preds[10:42, 0] = coeff
        det = decode(preds, proto)[0]
        self.assertTrue(det.mask[52, 24])
        self.assertFalse(det.mask[0, 0])


class TestSelectLaneTypes(unittest.TestCase):

    def test_left_solid_right_dashed(self):
        result = select_lane_types([make_det(0, cx=20), make_det(1, cx=80)])
        self.assertIsInstance(result, LaneTypes)
        self.assertTrue(result.left_solid)
        self.assertFalse(result.right_solid)
        self.assertTrue(result.left_found)
        self.assertTrue(result.right_found)

    def test_no_lines(self):
        result = select_lane_types([])
        self.assertFalse(result.left_found)
        self.assertFalse(result.right_found)
        self.assertFalse(result.left_solid)
        self.assertFalse(result.right_solid)

    def test_ignored_classes(self):
        result = select_lane_types([make_det(3, cx=20), make_det(4, cx=80)])
        self.assertFalse(result.left_found)
        self.assertFalse(result.right_found)

    def test_line_above_half_dropped(self):
        # bottom=40 < proto_size/2(52) -> 不参与判定
        result = select_lane_types([make_det(0, cx=20, bottom=40)])
        self.assertFalse(result.left_found)

    def test_nearest_center_line_wins(self):
        # 两条左侧候选：cx=10 与 cx=40，靠近中心(52)的 cx=40 应胜出（虚线）
        result = select_lane_types([make_det(0, cx=10), make_det(1, cx=40)])
        self.assertTrue(result.left_found)
        self.assertFalse(result.left_solid)


if __name__ == "__main__":
    unittest.main()
