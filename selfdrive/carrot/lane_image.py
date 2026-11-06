#!/usr/bin/env python3
"""VisionIPC NV12 帧 -> 416x416 RGB 输入张量（纯 numpy）。

C3 的 camerad 通过 VisionIPC 提供 NV12（Y 平面 + 交错 UV）。
模型契约：RGB 通道顺序、/255 归一化、NCHW、batch=1。
"""
import numpy as np

INPUT_SIZE = 416


def nv12_to_rgb(data, width, height, stride):
    """NV12 -> (height, width, 3) uint8 RGB（BT.601 limited range）。"""
    buf = np.frombuffer(data, dtype=np.uint8)
    y_size = stride * height
    if buf.size < y_size + stride * (height // 2):
        raise ValueError("NV12 buffer too small")

    y = buf[:y_size].reshape(height, stride)[:, :width].astype(np.float32)
    uv = buf[y_size:y_size + stride * (height // 2)].reshape(height // 2, stride)[:, :width]
    u = uv[:, 0::2].astype(np.float32)
    v = uv[:, 1::2].astype(np.float32)

    # 色度上采样到与亮度同尺寸
    u = np.repeat(np.repeat(u, 2, axis=0), 2, axis=1)
    v = np.repeat(np.repeat(v, 2, axis=0), 2, axis=1)
    if u.shape != y.shape:
        u = np.resize(u, y.shape)
        v = np.resize(v, y.shape)

    yf = (y - 16.0) * 1.164
    uf = u - 128.0
    vf = v - 128.0

    r = yf + 1.596 * vf
    g = yf - 0.813 * vf - 0.391 * uf
    b = yf + 2.018 * uf
    rgb = np.stack([r, g, b], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def resize_nearest(img, size):
    """最近邻缩放到 (size, size)，避免引入 cv2 依赖。"""
    h, w = img.shape[:2]
    if h == size and w == size:
        return img
    ys = np.clip((np.arange(size) * h) // size, 0, h - 1)
    xs = np.clip((np.arange(size) * w) // size, 0, w - 1)
    return img[ys][:, xs]


def to_input_tensor(rgb, size=INPUT_SIZE):
    """(H,W,3) uint8 RGB -> (1,3,size,size) float32 [0,1]。"""
    resized = resize_nearest(rgb, size).astype(np.float32) / 255.0
    return np.transpose(resized, (2, 0, 1))[None, ...]
