#!/usr/bin/env python3
"""
TDD tests for S-1~S-5 security findings.

These tests assert the POST-FIX state (vulnerabilities removed).
They are GREEN after the security patches land; they FAIL on a clean
(pre-fix) tree, correctly signalling that the vulnerability is present.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CARROT_MAN = os.path.join(ROOT, "selfdrive", "carrot", "carrot_man.py")
WEB_IFACE = os.path.join(ROOT, "selfdrive", "carrot", "web_interface.py")
AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")


def _read(path):
  with open(path, encoding="utf-8") as f:
    return f.read()


class TestS1ZmqRce:
  """S-1: ZMQ 7710 loopback bind + HMAC token + echo_cmd whitelist (no shell=True)."""

  def test_shell_true_echo_cmd_removed(self):
    """Post-fix: echo_cmd no longer runs through shell=True."""
    text = _read(CARROT_MAN)
    m = re.search(r"subprocess\.run\(json_obj\['echo_cmd'\],\s*shell\s*=\s*True", text)
    assert m is None

  def test_echo_cmd_whitelist_present(self):
    """Post-fix: echo_cmd restricted to a named whitelist of safe commands."""
    text = _read(CARROT_MAN)
    assert "echo_cmd_whitelist" in text, "S-1 GREEN: echo_cmd whitelist expected"

  def test_zmq_bind_loopback(self):
    """Post-fix: ZMQ binds to 127.0.0.1:7710, not tcp://*:7710."""
    text = _read(CARROT_MAN)
    assert 'tcp://*:7710' not in text, "S-1 GREEN: wildcard 7710 bind must be gone"
    assert 'tcp://127.0.0.1:7710' in text, "S-1 GREEN: loopback 7710 bind expected"

  def test_token_auth_on_zmq(self):
    """Post-fix: ZMQ channel enforces a shared-token check."""
    text = _read(CARROT_MAN)
    assert "_zmq_token" in text, "S-1 GREEN: ZMQ token auth expected"
    assert "compare_digest" in text, "S-1 GREEN: constant-time token compare expected"


class TestS2FtpHardcodedCreds:
  """S-2: FTP credentials parameterized + default-disabled."""

  def test_ftp_server_hardcoded_removed(self):
    """Post-fix: no hardcoded FTP server host in source."""
    text = _read(CARROT_MAN)
    assert "shind0.synology.me" not in text, "S-2 GREEN: hardcoded FTP server must be removed"

  def test_ftp_password_hardcoded_removed(self):
    """Post-fix: the leaked password string must not appear in source."""
    text = _read(CARROT_MAN)
    assert "Ekdrmsvkdlffjt7710" not in text, "S-2 GREEN: hardcoded FTP password must be removed"

  def test_ftp_env_injected_and_gated(self):
    """Post-fix: credentials come from env vars and are gated behind an opt-in flag."""
    text = _read(CARROT_MAN)
    assert "CARROT_FTP_SERVER" in text, "S-2 GREEN: env-injected FTP server expected"
    assert "CARROT_FTP_TELEMETRY_ENABLED" in text, "S-2 GREEN: default-off FTP gate expected"


class TestS3WebInterfaceCORSAndParams:
  """S-3: HTTP 8088 with whitelist-gated params.put + no wildcard CORS."""

  def test_cors_wildcard_removed(self):
    text = _read(WEB_IFACE)
    assert "Access-Control-Allow-Origin', '*'" not in text, "S-3 GREEN: wildcard CORS must be removed"

  def test_params_put_whitelist_guard(self):
    """Post-fix: params.put is gated by a key whitelist."""
    text = _read(WEB_IFACE)
    assert "PARAM_KEY_WHITELIST" in text, "S-3 GREEN: params whitelist expected"
    assert "if key not in PARAM_KEY_WHITELIST" in text, "S-3 GREEN: whitelist guard expected"


class TestS4AmapNaviUdpBinds:
  """S-4: amap_navi.py head-unit UDP ports use CARROT_BIND_HOST (default 0.0.0.0) + source whitelist."""

  def test_amap_navi_bind_host_configurable(self):
    text = _read(AMAP_NAVI)
    assert 'os.environ.get("CARROT_BIND_HOST", "0.0.0.0")' in text, "S-4 GREEN: bind host must be configurable, default 0.0.0.0"
    for port in ("4210", "self.navi_remote_port", "self.lane_port", "self.listen_port"):
      assert "bind((self.bind_host, %s))" % port in text, f"S-4 GREEN: bind {port} must use self.bind_host"

  def test_amap_navi_no_hardcoded_loopback(self):
    text = _read(AMAP_NAVI)
    m = re.search(r"bind\(\('127\.0\.0\.1',\s*(4210|self\.navi_remote_port|self\.lane_port|self\.listen_port)\)", text)
    assert m is None

  def test_amap_navi_source_whitelist(self):
    text = _read(AMAP_NAVI)
    assert "_udp_trusted" in text, "S-4 GREEN: source-IP whitelist expected"


class TestS5CarrotManUdpBinds:
  """S-5: carrot_man.py legacy UDP uses CARROT_BIND_HOST; management ports stay loopback."""

  def test_udp_7706_bind_host_configurable(self):
    text = _read(CARROT_MAN)
    assert 'os.environ.get("CARROT_BIND_HOST", "0.0.0.0")' in text, "S-5 GREEN: bind host must be configurable, default 0.0.0.0"
    m = re.search(r"sock\.bind\(\(self\.bind_host,\s*self\.carrot_man_port\)\)", text)
    assert m is not None

  def test_udp_12345_loopback_bind(self):
    text = _read(CARROT_MAN)
    m = re.search(r"sock\.bind\(\('127\.0\.0\.1',\s*12345\)\)", text)
    assert m is not None

  def test_udp_source_whitelist(self):
    text = _read(CARROT_MAN)
    assert "_udp_trusted" in text, "S-5 GREEN: source-IP whitelist expected"


if __name__ == "__main__":
  unittest.main()
