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

  def test_public_readonly_log_http_server(self):
    import threading
    import urllib.error
    import urllib.request
    try:
      from openpilot.selfdrive.carrot.log_monitor import make_log_http_server
    except ImportError:
      from selfdrive.carrot.log_monitor import make_log_http_server

    with tempfile.TemporaryDirectory() as tmp:
      srv = make_log_http_server(host="127.0.0.1", port=0, log_dir=tmp)
      port = srv.server_address[1]
      t = threading.Thread(target=srv.serve_forever, daemon=True)
      t.start()
      try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/logs", timeout=2) as resp:
          self.assertEqual(resp.status, 200)
          body = json.loads(resp.read().decode("utf-8"))
          self.assertEqual(body["total_errors"], 0)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
          self.assertEqual(resp.status, 200)
          html = resp.read().decode("utf-8")
          self.assertIn("C3", html)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/logs", data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
          urllib.request.urlopen(req, timeout=2)
        self.assertEqual(ctx.exception.code, 405)
      finally:
        srv.shutdown()
        srv.server_close()

  def test_carrot_man_starts_readonly_log_server(self):
    carrot_man = os.path.join(ROOT, "selfdrive", "carrot", "carrot_man.py")
    with open(carrot_man, encoding="utf-8") as f:
      text = f.read()
    self.assertIn("start_log_http_server", text)


if __name__ == "__main__":
  unittest.main()
