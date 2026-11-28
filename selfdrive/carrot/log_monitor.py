#!/usr/bin/env python3
"""Lightweight C3 swaglog error aggregator and CLI monitor."""
import glob
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
