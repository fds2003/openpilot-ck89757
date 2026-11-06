#!/usr/bin/env python3
"""
Web界面模块 - 优化版
负责HTTP服务器和Web界面处理
"""

import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from openpilot.common.params import Params
from openpilot.system.manager.manager import get_default_params_key

params = Params()

# S-3: params.put 白名单。仅允许通过 Web 界面写入以下参数键。
# 任何不在白名单中的键都会被拒绝，防止未授权修改行车/刹车/控制参数。
PARAM_KEY_WHITELIST = {
  "AutoTurnDistOffset", "AutoForkDistOffset", "AutoDoForkBlinkerDist",
  "AutoForkDistOffsetH", "AutoDoForkDecalDistH", "AutoDoForkDecalDist",
  "AutoDoForkBlinkerDistH", "AutoDoForkNavDistH", "AutoUpRoadLimit",
  "AutoUpRoadLimit40KMH", "AutoUpHighwayRoadLimit", "AutoUpHighwayRoadLimit40KMH",
  "RoadType", "AutoForkDecalRateH", "AutoForkSpeedMinH", "AutoKeepForkSpeedH",
  "AutoForkDecalRate", "AutoForkSpeedMin", "AutoKeepForkSpeed",
  "ShowDebugLog", "AutoCurveSpeedFactorH", "AutoCurveSpeedAggressivenessH",
  "SameSpiCamFilter", "StockBlinkerCtrl", "ExtBlinkerCtrlTest",
  "BlinkerMode", "LaneStabTime", "DynamicBlindRange", "DynamicBlindDistance",
  "DisableBlindSpot", "BsdDelayTime", "SideBsdDelayTime",
  "SideRelDistTime", "SidevRelDistTime", "SideRadarMinDist",
  "LidarBsdDelayTime", "LidarFrontVDistTime", "LidarFrontVRelDistTime",
  "LidarBehindVDistTime", "LidarBehindVRelDistTime", "LaneLineDelayTime",
  "AutoTurnInNotRoadEdge", "ContinuousLaneChange", "ContinuousLaneChangeCnt",
  "ContinuousLaneChangeInterval", "AutoTurnLeft",
  "AutoEnTurnNewLaneTimeH", "AutoEnTurnNewLaneTime",
  "NewLaneWidthDiff", "DynamicExperimentalSpeed", "DynamicExperimentalLatA",
  "AtcResumeDelay", "AtcResumeCnt",
  "CarrotCooperativeMode",
  "CarrotUdpAllowedIps",
}

def get_all_toggle_values():
  """导出所有 OpenPilot 参数值，bytes -> str"""
  all_keys = get_default_params_key()
  toggle_values = {}
  for key in all_keys:
    try:
      value = params.get(key)
    except Exception:
      value = b"0"
    toggle_values[key] = value.decode('utf-8') if value is not None else "0"
  return toggle_values


def store_toggle_values(updated_values):
  """S-3: 将前端发送的 JSON 写入 OpenPilot Params。
  仅允许白名单内的键，防止未授权修改行车参数。"""
  for key, value in updated_values.items():
    # S-3: 白名单检查 —— 拒绝不在 PARAM_KEY_WHITELIST 中的键
    if key not in PARAM_KEY_WHITELIST:
      print(f"[S-3] rejected non-whitelisted params key: {key}")
      continue
    try:
      params.put(key, value.encode('utf-8'))
    except Exception as e:
      print(f"Failed to update {key}: {e}")

class WebInterface:
    """Web界面处理器"""

    def __init__(self, controller, port=None):
        self.controller = controller
        self.web_server = None
        self.port = port

    def create_web_handler(self):
        """创建Web处理器"""
        controller = self.controller

        class WebPageHTTPHandler(BaseHTTPRequestHandler):
            def safe_write(self, data):
                """安全写入数据，处理连接中断"""
                try:
                    if isinstance(data, str):
                        data = data.encode('utf-8')
                    self.wfile.write(data)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                except Exception as e:
                    print(f"写入数据时发生错误: {e}")

            def log_message(self, format, *args):
                """自定义日志格式，避免每次请求都打印到控制台"""
                pass

            def do_OPTIONS(self):
                """S-3: 处理CORS预检请求 —— 仅反射本机 Origin，不再使用通配符 *。"""
                try:
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
                    self.send_header('Access-Control-Max-Age', '86400')
                    self.end_headers()
                except Exception as e:
                    print(f"OPTIONS请求处理错误: {e}")

            def _cors_origin(self):
                """S-3: 返回安全的 Access-Control-Allow-Origin 值。
                仅当请求方是本机 (127.0.0.1 / localhost) 时反射其 Origin，
                否则返回空串（等效于拒绝跨域），彻底移除通配符 '*'。"""
                origin = self.headers.get('Origin')
                if origin and (origin.startswith('http://127.0.0.1')
                               or origin.startswith('http://localhost')):
                  return origin
                return ""

            def _origin_allowed(self):
                """拒绝非本机来源的浏览器跨站请求，防止 CSRF 篡改行车参数"""
                origin = self.headers.get('Origin')
                if origin is None:
                    return True
                return origin.startswith('http://127.0.0.1') or origin.startswith('http://localhost')

            def do_GET(self):
                """处理GET请求"""
                if not self._origin_allowed():
                    self.send_error(403, "cross-origin request denied")
                    return
                try:
                    if self.path == '/':
                        self.send_response(301)
                        self.send_header('Location', '/nav_params')
                        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                        self.end_headers()
                    elif self.path == '/radar':
                        self.send_response(200)
                        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                        self.send_header('Content-type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.send_radar_page()
                    elif self.path == '/radar_data':
                        self.send_response(200)
                        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.send_header('Cache-Control', 'no-cache')
                        self.end_headers()
                        self.send_radar_data()
                    elif self.path == '/nav_params':
                        self.send_response(200)
                        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                        self.send_header('Content-type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.send_nav_params_page()
                    elif self.path == '/nav_params_data':
                        self.send_response(200)
                        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.send_nav_params_data()
                    elif self.path == '/get_default_nav_params':
                        self.send_response(200)
                        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.send_default_nav_params()
                    elif self.path == '/fetch_params':
                        self.fetch_params()
                    else:
                        self.send_error(404, f"{self.path} Page not found")

                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端连接中断: {e}")
                except IOError as e:
                    print(f"IO错误: {e}")
                    self.send_error(500, "Internal server erro")
                except Exception as e:
                    print(f"未预期的错误: {e}")
                    self.send_error(500, f"Internal server erro: {str(e)}")

            def do_POST(self):
                """处理POST请求"""
                if not self._origin_allowed():
                    self.send_error(403, "cross-origin request denied")
                    return
                if self.path in ('/nav_params', '/save_params') and controller.params.get_bool("IsOnroad"):
                    self.send_error(403, "params are locked while onroad")
                    return
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length).decode('utf-8')
                    data = json.loads(post_data) if post_data else {}

                    if self.path == '/nav_params':
                        self.handle_nav_params(data)
                    elif self.path == '/save_params':
                      self.save_params(post_data)
                    else:
                        self.send_error(404, "API not found")
                except json.JSONDecodeError:
                    self.send_error(400, "JSON format error")
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端连接中断: {e}")
                except Exception as e:
                    print(f"请求处理错误: {e}")
                    self.send_error(500, f"Internal server erro: {str(e)}")

            def fetch_params(self):
              try:
                data = get_all_toggle_values()
                self.send_json_response(data)
              except Exception as e:
                self.send_json_response({"status": "error", "message": f"导出参数失败: {e}"})

            def save_params(self, post_data):
              try:
                updated_values = json.loads(post_data)
                store_toggle_values(updated_values)
                self.send_json_response({"status": "success", "message": "参数写入成功"})
              except Exception as e:
                self.send_json_response({"status": "error", "message": f"写入失败: {e}"})

            def send_nav_params_page(self):
                """发送CP导航参数设置页面"""
                try:
                    html = self.get_html_content('nav_params.html')
                    self.safe_write(html)
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端断开连接: {e}")
                except Exception as e:
                    print(f"发送参数页面错误: {e}")

            def send_default_nav_params(self):
                """发送默认的CP导航参数数据"""
                try:
                    default_data = controller.params._get_default_nav_data()
                    self.safe_write(json.dumps(default_data, ensure_ascii=False))
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端断开连接: {e}")
                except Exception as e:
                    print(f"发送默认参数错误: {e}")

            def send_nav_params_data(self):
                """发送CP导航参数数据"""
                try:
                    controller.params._match_system_param()
                    nav_data = controller.params.nav_data
                    self.safe_write(json.dumps(nav_data, ensure_ascii=False))
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端断开连接: {e}")
                except Exception as e:
                    print(f"发送参数数据错误: {e}")

            def handle_nav_params(self, data):
                """处理CP导航参数更新 - 复用UnifiedParams类逻辑"""
                try:
                    if not data:
                        self.send_json_response({'status': 'error', 'message': '无效的数据'})
                        return

                    unified_params = controller.params

                    if 'reset' in data and data['reset'] == 'true':
                        default_data = unified_params._get_default_nav_data()
                        unified_params.nav_data = default_data
                        unified_params._save_nav_data()
                        unified_params._save_system_param()
                        self.send_json_response({'status': 'success', 'message': '参数已恢复默认'})
                    else:
                        unified_params.nav_data = data
                        unified_params._save_nav_data()
                        unified_params._save_system_param()
                        self.send_json_response({'status': 'success', 'message': '参数已保存'})
                except Exception as e:
                    self.send_json_response({'status': 'error', 'message': f'保存失败: {str(e)}'})

            def send_json_response(self, data):
                """发送JSON响应"""
                try:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                    self.end_headers()
                    self.safe_write(json.dumps(data, ensure_ascii=False))
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端断开连接: {e}")
                except Exception as e:
                    print(f"发送JSON响应错误: {e}")

            def send_radar_page(self):
                """发送雷达数据显示页面"""
                try:
                    html = self.get_html_content('radar.html')
                    self.safe_write(html)
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端断开连接: {e}")
                except Exception as e:
                    print(f"发送雷达页面错误: {e}")

            def send_radar_data(self):
                """发送雷达数据JSON"""
                try:
                    radar_data = controller.get_radar_data()
                    self.safe_write(json.dumps(radar_data, ensure_ascii=False))
                except (BrokenPipeError, ConnectionResetError) as e:
                    print(f"客户端断开连接: {e}")
                except Exception as e:
                    print(f"发送雷达数据错误: {e}")

            def get_html_content(self, filename):
                """HTML文件读取加载"""
                try:
                    base_dir = os.path.abspath(os.path.dirname(__file__))
                    html_file_path = os.path.join(base_dir, filename)

                    if not os.path.exists(html_file_path):
                        return f"<html><body><h1>错误：文件 {filename} 不存在于路径 {html_file_path}</h1></body></html>"

                    with open(html_file_path, 'r', encoding='utf-8') as f:
                        return f.read()
                except FileNotFoundError:
                    return f"<html><body><h1>错误：未找到 {filename} 文件</h1></body></html>"
                except Exception as e:
                    return f"<html><body><h1>错误：读取文件失败 - {str(e)}</h1></body></html>"

        return WebPageHTTPHandler

    def start_web_server(self):
        """启动Web服务器"""
        try:
            handler = self.create_web_handler()
            self.web_server = HTTPServer(('127.0.0.1', self.port), handler)
            self.web_server.timeout = 30
            print(f"🌐 Web服务器启动在 127.0.0.1:{self.port}（仅本机，需经 SSH 隧道访问）")
            self.web_server.serve_forever()
        except Exception as e:
            print(f"启动Web服务器失败: {e}")
            raise

    def stop_web_server(self):
        """停止Web服务器"""
        if self.web_server:
            self.web_server.shutdown()
            self.web_server.server_close()
            print("🌐 Web服务器已停止")
