#!/usr/bin/env python3
"""YOLO-seg 车道线后处理（纯 numpy，等价移植自 APK `LaneDetect.postProcess`）.

模型契约：
- output0: (1, 42, N) —— 0:4 = cx,cy,w,h（输入像素）；4:10 = 6 类分数；10:42 = 32 掩膜系数
- output1: (1, 32, 104, 104) —— 原型掩膜，proto_size = 104

类别映射（与原版 CLASS_TO_TYPE 一致）：
- 0 / 2 / 5 -> 实线
- 1         -> 虚线
- 3 / 4     -> 忽略
"""
from dataclasses import dataclass

import numpy as np

NUM_CLASSES = 6
NUM_COEFFS = 32
INPUT_SIZE = 416
PROTO_SIZE = 104

CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.5

# True = 实线，False = 虚线
CLASS_TO_SOLID = {0: True, 1: False, 2: True, 5: True}
IGNORE_CLASSES = frozenset((3, 4))


@dataclass(frozen=True)
class Detection:
    cls: int
    score: float
    box: tuple  # (x1, y1, x2, y2) in input pixels
    mask: np.ndarray  # bool (PROTO_SIZE, PROTO_SIZE)


@dataclass(frozen=True)
class LaneTypes:
    left_solid: bool
    right_solid: bool
    left_found: bool
    right_found: bool


def _unbatch(a):
    a = np.asarray(a, dtype=np.float32)
    while a.ndim > 2 and a.shape[0] == 1:
        a = a[0]
    return a


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a[2]
    bx1, by1, bx2, by2 = b[2]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0.0 else 0.0


def _compose_mask(coeff, proto, box, input_size=INPUT_SIZE, proto_size=PROTO_SIZE):
    mask = np.zeros((proto_size, proto_size), dtype=bool)
    x1, y1, x2, y2 = box
    px1 = int(np.clip(int(x1 / input_size * proto_size), 0, proto_size - 1))
    py1 = int(np.clip(int(y1 / input_size * proto_size), 0, proto_size - 1))
    px2 = int(np.clip(int(x2 / input_size * proto_size), 0, proto_size - 1))
    py2 = int(np.clip(int(y2 / input_size * proto_size), 0, proto_size - 1))
    if py1 > py2 or px1 > px2:
        return mask
    sub = proto[:, py1:py2 + 1, px1:px2 + 1]
    if sub.size == 0:
        return mask
    dot = np.tensordot(coeff, sub, axes=(0, 0))
    mask[py1:py2 + 1, px1:px2 + 1] = dot > 0.0
    return mask


def decode(preds, proto, conf=CONF_THRESHOLD, iou=IOU_THRESHOLD,
           input_size=INPUT_SIZE, proto_size=PROTO_SIZE):
    """把模型原始输出解码为 Detection 列表（已做置信度过滤与同类 NMS）。"""
    preds = _unbatch(preds)
    proto = _unbatch(proto)
    if preds.ndim != 2 or preds.shape[0] != 4 + NUM_CLASSES + NUM_COEFFS:
        raise ValueError(f"unexpected preds shape: {preds.shape}")
    if proto.ndim != 3 or proto.shape[0] != NUM_COEFFS:
        raise ValueError(f"unexpected proto shape: {proto.shape}")

    scores = preds[4:4 + NUM_CLASSES]
    cls = scores.argmax(axis=0)
    score = scores.max(axis=0)
    keep = np.nonzero(score >= conf)[0]
    if keep.size == 0:
        return []
    order = keep[np.argsort(-score[keep])]

    anchors = []
    for i in order:
        cx, cy, w, h = (float(v) for v in preds[0:4, i])
        box = (cx - w * 0.5, cy - h * 0.5, cx + w * 0.5, cy + h * 0.5)
        anchors.append((int(cls[i]), float(score[i]), box, preds[10:10 + NUM_COEFFS, i]))

    kept = []
    for a in anchors:
        if all(a[0] != k[0] or _iou(a, k) <= iou for k in kept):
            kept.append(a)

    return [
        Detection(c, s, box, _compose_mask(coeff, proto, box, input_size, proto_size))
        for c, s, box, coeff in kept
    ]


def select_lane_types(detections, proto_size=PROTO_SIZE):
    """按原版 selectLanes：取每条线最底部行，按中心分左右，选最靠近图像底边的一条。"""
    half = proto_size / 2.0
    left, right = [], []

    for det in detections:
        if det.cls in IGNORE_CLASSES:
            continue
        ys, xs = np.nonzero(det.mask)
        if ys.size == 0:
            continue
        bottom = int(ys.max())
        if bottom < proto_size // 2:
            continue
        cx = float(xs[ys == bottom].mean())
        (left if cx < half else right).append((det, bottom, cx))

    def pick(cands):
        if not cands:
            return None
        return min(cands, key=lambda t: (t[2] - half) ** 2 + 2.0 * (t[1] - (proto_size - 1)) ** 2)

    l, r = pick(left), pick(right)
    return LaneTypes(
        left_solid=bool(CLASS_TO_SOLID.get(l[0].cls, False)) if l else False,
        right_solid=bool(CLASS_TO_SOLID.get(r[0].cls, False)) if r else False,
        left_found=l is not None,
        right_found=r is not None,
    )
