#!/usr/bin/env python3
"""
tools/lan_pc_receiver.py
====================================================================
现代库斯途 Comma 3 车机专用 —— 局域网电脑一键日志与文件接收端 (LAN PC Receiver)

【用途】：
运行于车主身边的局域网电脑（Windows / Mac / Linux）。
车机连接家庭 Wi-Fi 后，会自动将崩溃日志、行车记录和参数推送到本电脑，自动归档保存。

【使用方法】：
1. 首次运行前在电脑终端安装依赖: pip install pyftpdlib
2. 双击运行本脚本（或运行 start_lan_receiver.bat）
3. 脚本会自动检测并打印出当前电脑的局域网 IP，在车机屏幕设置中填入该 IP 即可！
====================================================================
"""

import os
import sys
import socket

def get_lan_ip():
  """自动获取当前电脑在局域网中的真实 IPv4 地址"""
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    # 向常用路由器网关或公网 DNS 尝试发起探测连接以获取本机出口 IP
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
  except Exception:
    ip = '127.0.0.1'
  finally:
    s.close()
  return ip

def run_ftp_receiver():
  try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
  except ImportError:
    print("=" * 65)
    print("❌ 未检测到 pyftpdlib 依赖库！")
    print("👉 请在电脑命令行执行以下命令安装:")
    print("   pip install pyftpdlib")
    print("=" * 65)
    sys.exit(1)

  lan_ip = get_lan_ip()
  save_dir = os.path.abspath("./received_from_car")
  os.makedirs(save_dir, exist_ok=True)

  # 配置权限：允许车机上传与写入
  authorizer = DummyAuthorizer()
  # 用户名 carrotpilot，密码 123456（可与车机设置保持一致）
  authorizer.add_user("carrotpilot", "123456", save_dir, perm="elradfmwMT")

  handler = FTPHandler
  handler.authorizer = authorizer
  handler.banner = "=== Comma 3 Custin LAN PC Receiver Ready ==="

  # 监听本地 8021 端口 (对应车机 CarrotPilot 默认端口)
  PORT = 8021
  server = FTPServer(("0.0.0.0", PORT), handler)

  print("=" * 65)
  print("🚗【现代库斯途 Comma 3】局域网电脑文件接收服务已就绪")
  print("=" * 65)
  print(f"📡 您的电脑局域网 IP 地址为 : \033[1;32m{lan_ip}\033[0m")
  print(f"🔌 接收服务监听端口号       : \033[1;32m{PORT}\033[0m")
  print(f"📂 文件自动保存目录         : {save_dir}")
  print("-" * 65)
  print("📱【车机屏幕配置指引】：")
  print(f"   1. 在车机设置中开启【上传功能】开关")
  print(f"   2. 服务器地址填写: {lan_ip}")
  print(f"   3. 端口填写: {PORT}")
  print(f"   4. 账号/密码填写: carrotpilot / 123456")
  print("-" * 65)
  print("💡 状态: 正在等待车机连接传输 (按 Ctrl+C 可停止服务)...")
  print("=" * 65)

  try:
    server.serve_forever()
  except KeyboardInterrupt:
    print("\n🛑 接收服务已由用户手动停止。")

if __name__ == "__main__":
  run_ftp_receiver()
