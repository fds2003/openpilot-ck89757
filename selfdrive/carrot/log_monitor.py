#!/usr/bin/env python3
"""Lightweight C3 swaglog error aggregator and CLI monitor."""
import glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import time


def _extract_message(obj):
  msg = obj.get("msg$s")
  if msg:
    return str(msg)
  raw_msg = obj.get("msg")
  if isinstance(raw_msg, dict):
    event = raw_msg.get("event$s") or ""
    extra = {k: v for k, v in raw_msg.items() if k != "event$s"}
    return f"{event} {extra}".strip() if extra else str(event)
  return str(raw_msg or "")


def get_error_summary(log_dir="/data/log", max_files=5, limit=20):
  """Scan recent swaglog.* files and return deduplicated ERROR/crash summary."""
  if not os.path.isdir(log_dir):
    return {"total_errors": 0, "files_scanned": 0, "errors": []}

  files = sorted(
    glob.glob(os.path.join(log_dir, "swaglog.*")),
    key=lambda p: os.path.getmtime(p),
    reverse=True,
  )[:max_files]

  grouped = {}
  total_errors = 0

  for path in files:
    try:
      with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
          line = line.strip()
          if not line:
            continue
          try:
            obj = json.loads(line)
          except Exception:
            continue
          if not isinstance(obj, dict):
            continue

          levelnum = obj.get("levelnum", 0)
          exc_info = obj.get("exc_info")
          if levelnum < 40 and not exc_info:
            continue

          total_errors += 1
          ctx = obj.get("ctx") or {}
          daemon = ctx.get("daemon") or obj.get("module") or "unknown"
          filename = obj.get("filename") or ""
          lineno = obj.get("lineno") or 0
          message = _extract_message(obj)
          created = float(obj.get("created") or 0.0)
          exc_tail = ""
          if exc_info:
            exc_lines = [ln for ln in str(exc_info).splitlines() if ln.strip()]
            exc_tail = "\n".join(exc_lines[-3:])

          key = (daemon, filename, lineno, message)
          if key not in grouped:
            grouped[key] = {
              "daemon": daemon,
              "file": f"{filename}:{lineno}" if filename else "",
              "message": message,
              "exc_tail": exc_tail,
              "count": 1,
              "last_ts": created,
            }
          else:
            grouped[key]["count"] += 1
            if created >= grouped[key]["last_ts"]:
              grouped[key]["last_ts"] = created
              if exc_tail:
                grouped[key]["exc_tail"] = exc_tail
    except OSError:
      continue

  errors = sorted(grouped.values(), key=lambda x: x["last_ts"], reverse=True)[:limit]
  return {
    "total_errors": total_errors,
    "files_scanned": len(files),
    "errors": errors,
  }


_HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>C3 异常日志监控</title>
<style>
  body { font-family: system-ui, sans-serif; background: #111; color: #eee; margin: 16px; }
  h2 { margin: 0 0 8px; }
  .meta { color: #9ca3af; font-size: 14px; margin-bottom: 14px; }
  .ok { color: #34d399; font-weight: bold; }
  .card { background: #1f2937; border-left: 4px solid #ef4444; padding: 10px 12px; margin-bottom: 10px; border-radius: 4px; }
  .hdr { font-weight: 600; margin-bottom: 4px; }
  pre { margin: 6px 0 0; white-space: pre-wrap; word-break: break-all; color: #fca5a5; font-size: 12px; }
</style>
</head>
<body>
<h2>C3 异常日志监控</h2>
<div id="meta" class="meta">加载中...</div>
<div id="list"></div>
<script>
async function refresh() {
  try {
    const r = await fetch('/logs');
    const d = await r.json();
    document.getElementById('meta').textContent =
      `已扫描 ${d.files_scanned} 个日志文件 | 累计异常: ${d.total_errors} | 每5秒自动刷新`;
    const list = document.getElementById('list');
    if (!d.errors.length) {
      list.innerHTML = '<div class="ok">正常：最近日志无 ERROR 或崩溃记录</div>';
      return;
    }
    list.innerHTML = d.errors.map(e => {
      const ts = e.last_ts ? new Date(e.last_ts * 1000).toLocaleString() : 'unknown';
      return `<div class="card"><div class="hdr">[${ts}] (${e.count}x) ${e.daemon} ${e.file}</div><div>${e.message}</div>${e.exc_tail ? `<pre>${e.exc_tail}</pre>` : ''}</div>`;
    }).join('');
  } catch (err) {
    document.getElementById('meta').textContent = '拉取失败: ' + err;
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


def make_log_http_server(host="0.0.0.0", port=8089, log_dir="/data/log"):
  """Create a strictly read-only HTTP server exposing / and /logs."""
  class ReadOnlyLogHandler(BaseHTTPRequestHandler):
    def do_GET(self):
      if self.path == "/logs":
        payload = json.dumps(get_error_summary(log_dir=log_dir), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)
      elif self.path in ("/", "/index.html"):
        payload = _HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload)
      else:
        self.send_error(404, "Not Found")

    def _reject_write(self):
      self.send_error(405, "Method Not Allowed (read-only)")

    do_POST = _reject_write
    do_PUT = _reject_write
    do_DELETE = _reject_write
    do_PATCH = _reject_write

    def log_message(self, format, *args):
      return

  return ThreadingHTTPServer((host, port), ReadOnlyLogHandler)


def start_log_http_server(host=None, port=8089, log_dir="/data/log"):
  """Start the read-only log monitor HTTP server (blocking, intended for daemon thread)."""
  bind_host = host or os.environ.get("CARROT_LOG_BIND_HOST", "0.0.0.0")
  srv = make_log_http_server(host=bind_host, port=port, log_dir=log_dir)
  print(f"C3 read-only log monitor listening on http://{bind_host}:{port}/")
  srv.serve_forever()


def main():
  summary = get_error_summary()
  print(f"=== C3 Log Monitor (files={summary['files_scanned']}, total_errors={summary['total_errors']}) ===")
  if not summary["errors"]:
    print("OK: no ERROR/crash records in recent swaglogs.")
    return
  for item in summary["errors"]:
    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["last_ts"])) if item["last_ts"] else "unknown"
    print(f"[{ts_str}] ({item['count']}x) {item['daemon']} {item['file']} -> {item['message']}")
    if item["exc_tail"]:
      print(f"  {item['exc_tail'].replace(chr(10), ' | ')}")


if __name__ == "__main__":
  main()
