#!/usr/bin/env python3
"""C3 端车道线推理守护进程.

VisionIPC 前视帧 -> lane.onnx -> 后处理 -> 本地 UDP 4213 回传 amap_navi。

设计说明（重要）：
- `amapNavi` 的唯一发布者是 carrot_man 内嵌的 AmapNaviServ。
  本进程**不**创建 PubMaster(['amapNavi'])，避免 MultiplePublishersError。
- 结果通过 UDP 127.0.0.1:4213 交给 amap_navi._lane_recv_thread，
  再由唯一发布者写入 amapNavi.leftLine/rightLine 并随遥测回传车机。

依赖：
- onnxruntime（AGNOS 上可优先 onnxruntime-opencl，缺失时自动回退 CPU）
- numpy
- openpilot 自带 msgq / cereal
"""
import os
import socket
import time

import numpy as np

from openpilot.common.realtime import Ratekeeper
from openpilot.selfdrive.carrot.lane_image import nv12_to_rgb, to_input_tensor
from openpilot.selfdrive.carrot.lane_postprocess import decode, select_lane_types
from openpilot.selfdrive.carrot.lane_protocol import (
  LANE_UDP_HOST,
  LANE_UDP_PORT,
  build_lane_payload,
)
from openpilot.selfdrive.carrot.lane_runtime import check_runtime

MODEL_PATH = os.environ.get("LANE_MODEL_PATH", "/data/openpilot/selfdrive/carrot/models/lane.onnx")
INPUT_SIZE = 416


class LaneRunner:
  def __init__(self, model_path=MODEL_PATH, host=LANE_UDP_HOST, port=LANE_UDP_PORT):
    try:
      import onnxruntime as ort
    except ImportError as e:
      raise RuntimeError(
        "lane_runner requires onnxruntime: pip install onnxruntime-opencl (or onnxruntime)"
      ) from e

    if not os.path.exists(model_path):
      raise FileNotFoundError(f"lane model not found: {model_path}")

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    available = ort.get_available_providers()
    providers = [p for p in ("OpenCLExecutionProvider", "CPUExecutionProvider") if p in available]
    if not providers:
      providers = ["CPUExecutionProvider"]

    self.session = ort.InferenceSession(model_path, sess_options=so, providers=providers)
    self.input_name = self.session.get_inputs()[0].name
    self.output_names = [o.name for o in self.session.get_outputs()]

    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.addr = (host, port)
    self.last_frame_ms = 0

  def _split_outputs(self, outputs):
    by_name = dict(zip(self.output_names, outputs))
    preds = by_name.get("output0")
    proto = by_name.get("output1")
    if preds is None or proto is None:
      preds = proto = None
      for out in outputs:
        arr = np.asarray(out)
        if arr.ndim >= 3 and arr.shape[-1] == 104:
          proto = out
        else:
          preds = out
    return preds, proto

  def process_frame(self, rgb):
    tensor = to_input_tensor(rgb, INPUT_SIZE)
    outputs = self.session.run(None, {self.input_name: tensor})
    preds, proto = self._split_outputs(outputs)
    detections = decode(preds, proto)
    lanes = select_lane_types(detections)
    valid = lanes.left_found or lanes.right_found
    payload = build_lane_payload(lanes.left_solid, lanes.right_solid, valid)
    self.sock.sendto(payload.encode("utf-8"), self.addr)
    return lanes

  def run(self):
    from msgq.visionipc.visionipc_pyx import VisionIpcClient, VisionStreamType

    client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_ROAD, False)
    while not client.connect(False):
      time.sleep(0.5)

    rk = Ratekeeper(20, print_delay_threshold=None)
    while True:
      buf = client.recv()
      if buf is None:
        continue
      rgb = nv12_to_rgb(buf.data, buf.width, buf.height, buf.stride)
      try:
        self.process_frame(rgb)
      except Exception as e:
        # 单帧异常不退出守护进程
        print(f"lane_runner frame error: {e}")
      self.last_frame_ms = int(time.time() * 1000)
      rk.keep_time()


def main():
  ok, msg = check_runtime(MODEL_PATH)
  if not ok:
    # 明确退出，避免 manager 反复重启刷日志
    print(f"lane_runner disabled: {msg}")
    return
  LaneRunner().run()


if __name__ == "__main__":
  main()
