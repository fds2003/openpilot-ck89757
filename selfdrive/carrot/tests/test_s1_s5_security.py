#!/usr/bin/env python3
"""
TDD tests for S-1~S-5 security findings.

These tests assert the POST-FIX state (vulnerabilities removed).
They are GREEN after the security patches land; they FAIL on a clean
(pre-fix) tree, correctly signalling that the vulnerability is present.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CARROT_MAN = os.path.join(ROOT, "selfdrive", "carrot", "carrot_man.py")
WEB_IFACE = os.path.join(ROOT, "selfdrive", "carrot", "web_interface.py")
AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")


def _read(path):
  with open(path, encoding="utf-8") as f:
    return f.read()


class TestS1ZmqRce(unittest.TestCase):
  """S-1: ZMQ 7710 loopback bind + HMAC token + echo_cmd whitelist (no shell=True)."""

  def test_shell_true_echo_cmd_removed(self):
    """Post-fix: echo_cmd no longer runs through shell=True."""
    text = _read(CARROT_MAN)
    m = re.search(r"subprocess\.run\(json_obj\['echo_cmd'\],\s*shell\s*=\s*True", text)
    self.assertIsNone(m, "S-1 GREEN: shell=True echo_cmd must be removed")

  def test_echo_cmd_whitelist_present(self):
    """Post-fix: echo_cmd restricted to a named whitelist of safe commands."""
    text = _read(CARROT_MAN)
    self.assertIn("echo_cmd_whitelist", text, "S-1 GREEN: echo_cmd whitelist expected")

  def test_zmq_bind_loopback(self):
    """Post-fix: ZMQ binds to 127.0.0.1:7710, not tcp://*:7710."""
    text = _read(CARROT_MAN)
    self.assertNotIn('tcp://*:7710', text, "S-1 GREEN: wildcard 7710 bind must be gone")
    self.assertIn('tcp://127.0.0.1:7710', text, "S-1 GREEN: loopback 7710 bind expected")

  def test_token_auth_on_zmq(self):
    """Post-fix: ZMQ channel enforces a shared-token check."""
    text = _read(CARROT_MAN)
    self.assertIn("_zmq_token", text, "S-1 GREEN: ZMQ token auth expected")
    self.assertIn("compare_digest", text, "S-1 GREEN: constant-time token compare expected")


class TestS2FtpHardcodedCreds(unittest.TestCase):
  """S-2: FTP credentials parameterized + default-disabled."""

  def test_ftp_server_hardcoded_removed(self):
    """Post-fix: no hardcoded FTP server host in source."""
    text = _read(CARROT_MAN)
    self.assertNotIn("shind0.synology.me", text,
                     "S-2 GREEN: hardcoded FTP server must be removed")

  def test_ftp_password_hardcoded_removed(self):
    """Post-fix: the leaked password string must not appear in source."""
    text = _read(CARROT_MAN)
    self.assertNotIn("Ekdrmsvkdlffjt7710", text,
                     "S-2 GREEN: hardcoded FTP password must be removed")

  def test_ftp_env_injected_and_gated(self):
    """Post-fix: credentials come from env vars and are gated behind an opt-in flag."""
    text = _read(CARROT_MAN)
    self.assertIn("CARROT_FTP_SERVER", text, "S-2 GREEN: env-injected FTP server expected")
    self.assertIn("CARROT_FTP_TELEMETRY_ENABLED", text, "S-2 GREEN: default-off FTP gate expected")


class TestS3WebInterfaceCORSAndParams(unittest.TestCase):
  """S-3: HTTP 8088 with whitelist-gated params.put + no wildcard CORS."""

  def test_cors_wildcard_removed(self):
    text = _read(WEB_IFACE)
    self.assertNotIn("Access-Control-Allow-Origin', '*'", text,
                     "S-3 GREEN: wildcard CORS must be removed")

  def test_params_put_whitelist_guard(self):
    """Post-fix: params.put is gated by a key whitelist."""
    text = _read(WEB_IFACE)
    self.assertIn("PARAM_KEY_WHITELIST", text,
                  "S-3 GREEN: params whitelist expected")
    self.assertIn("if key not in PARAM_KEY_WHITELIST", text,
                  "S-3 GREEN: whitelist guard expected")


class TestS4AmapNaviUdpBinds(unittest.TestCase):
  """S-4: amap_navi.py head-unit UDP ports use CARROT_BIND_HOST (default 0.0.0.0) + source whitelist."""

  def test_amap_navi_bind_host_configurable(self):
    text = _read(AMAP_NAVI)
    self.assertIn('os.environ.get("CARROT_BIND_HOST", "0.0.0.0")', text,
                  "S-4 GREEN: bind host must be configurable, default 0.0.0.0")
    for port in ("4210", "self.navi_remote_port", "self.lane_port", "self.listen_port"):
      self.assertIn("bind((self.bind_host, %s))" % port, text,
                    f"S-4 GREEN: bind {port} must use self.bind_host")

  def test_amap_navi_no_hardcoded_loopback(self):
    text = _read(AMAP_NAVI)
    m = re.search(r"bind\(\('127\.0\.0\.1',\s*(4210|self\.navi_remote_port|self\.lane_port|self\.listen_port)\)", text)
    self.assertIsNone(m, "S-4 GREEN: head-unit ports must not be hardcoded to 127.0.0.1")

  def test_amap_navi_source_whitelist(self):
    text = _read(AMAP_NAVI)
    self.assertIn("_udp_trusted", text, "S-4 GREEN: source-IP whitelist expected")


class TestS5CarrotManUdpBinds(unittest.TestCase):
  """S-5: carrot_man.py legacy UDP uses CARROT_BIND_HOST; management ports stay loopback."""

  def test_udp_7706_bind_host_configurable(self):
    text = _read(CARROT_MAN)
    self.assertIn('os.environ.get("CARROT_BIND_HOST", "0.0.0.0")', text,
                  "S-5 GREEN: bind host must be configurable, default 0.0.0.0")
    m = re.search(r"sock\.bind\(\(self\.bind_host,\s*self\.carrot_man_port\)\)", text)
    self.assertIsNotNone(m, "S-5 GREEN: UDP 7706 must use self.bind_host")

  def test_udp_12345_loopback_bind(self):
    text = _read(CARROT_MAN)
    m = re.search(r"sock\.bind\(\('127\.0\.0\.1',\s*12345\)\)", text)
    self.assertIsNotNone(m, "S-5 GREEN: UDP 12345 loopback bind expected")

  def test_udp_source_whitelist(self):
    text = _read(CARROT_MAN)
    self.assertIn("_udp_trusted", text, "S-5 GREEN: source-IP whitelist expected")


if __name__ == "__main__":
  unittest.main()
