#!/usr/bin/env python3
"""TDD tests for C3 lightweight swaglog error monitor (selfdrive/carrot/log_monitor.py)."""
import json
import os
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
WEB_IFACE = os.path.join(ROOT, "selfdrive", "carrot", "web_interface.py")


def _import_get_error_summary():
  try:
    from openpilot.selfdrive.carrot.log_monitor import get_error_summary
    return get_error_summary
  except ImportError:
    from selfdrive.carrot.log_monitor import get_error_summary
    return get_error_summary


class TestLogMonitor(unittest.TestCase):

  def test_empty_directory_returns_healthy_summary(self):
    get_error_summary = _import_get_error_summary()
    with tempfile.TemporaryDirectory() as tmp:
      res = get_error_summary(log_dir=tmp)
      self.assertEqual(res["total_errors"], 0)
      self.assertEqual(res["errors"], [])

  def test_parses_swaglog_errors_and_deduplicates(self):
    get_error_summary = _import_get_error_summary()
    with tempfile.TemporaryDirectory() as tmp:
      p = os.path.join(tmp, "swaglog.0000000001")
      lines = [
        json.dumps({"ctx": {"daemon": "manager"}, "level": "INFO", "levelnum": 20, "msg$s": "ok"}),
        "not-a-json-line",
        json.dumps({
          "ctx": {"daemon": "plannerd"},
          "level": "ERROR",
          "levelnum": 40,
          "filename": "long_mpc.py",
          "lineno": 358,
          "created": 1000.0,
          "msg$s": "crash",
          "exc_info": "Traceback...\nAssertionError: vRel convention violated",
        }),
        json.dumps({
          "ctx": {"daemon": "plannerd"},
          "level": "ERROR",
          "levelnum": 40,
          "filename": "long_mpc.py",
          "lineno": 358,
          "created": 1005.0,
          "msg$s": "crash",
          "exc_info": "Traceback...\nAssertionError: vRel convention violated",
        }),
        json.dumps({
          "ctx": {"daemon": "selfdrived"},
          "level": "ERROR",
          "levelnum": 40,
          "filename": "selfdrived.py",
          "lineno": 375,
          "created": 1006.0,
          "msg": {"event$s": "process_not_running", "not_running$s": "{'plannerd'}"},
        }),
      ]
      with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

      res = get_error_summary(log_dir=tmp)
      self.assertEqual(res["total_errors"], 3)
      self.assertEqual(len(res["errors"]), 2)
      # Most recent error first
      self.assertEqual(res["errors"][0]["daemon"], "selfdrived")
      self.assertEqual(res["errors"][1]["daemon"], "plannerd")
      self.assertEqual(res["errors"][1]["count"], 2)
      self.assertIn("AssertionError", res["errors"][1]["exc_tail"])

  def test_web_interface_exposes_logs_route(self):
    with open(WEB_IFACE, encoding="utf-8") as f:
      text = f.read()
    self.assertIn("'/logs'", text)
    self.assertIn("get_error_summary", text)


if __name__ == "__main__":
  unittest.main()
