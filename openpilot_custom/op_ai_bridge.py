#!/usr/bin/env python3
"""
OpenPilot AI桥接器 - 完整修复版
功能：接收AI车速建议，并转发到OpenPilot消息总线
"""

import zmq
import json
import time
import sys
import os
import logging
from typing import Dict, Any, Optional

# 添加OpenPilot路径
sys.path.insert(0, '/data/openpilot')

try:
    from selfdrive.messaging import PubMaster, SubMaster, SpeedData, get_messaging_manager
    print("✅ 导入OpenPilot消息模块成功")
except ImportError as e:
    print(f"❌ 无法导入OpenPilot消息模块: {e}")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/op_ai_bridge.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("OpenPilotAIBridge")

class OpenPilotAIBridge:
    def __init__(self, config_path: str = "config.json"):
        """初始化AI桥接器"""
        self.config = self.load_config(config_path)
        self.running = True
        self.message_count = 0
        self.last_speed_received = 0
        
        # ZeroMQ通信
        self.context = zmq.Context()
        
        # 从AI系统接收消息（端口5580）
        self.ai_subscriber = self.context.socket(zmq.SUB)
        self.ai_subscriber.connect("tcp://localhost:5580")
        self.ai_subscriber.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # OpenPilot消息系统
        self.pm = PubMaster(['aiSpeedData', 'aiState'])
        
        # 心跳监控
        self.heartbeat_interval = 1.0
        self.last_heartbeat = time.time()
        
        logger.info("✅ OpenPilot AI桥接器初始化完成")
        logger.info(f"📡 监听端口: 5580 (AI车速建议)")
        logger.info(f"📤 发布到: aiSpeedData, aiState 主题")
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "ai_bridge": {
                "zmq_port": 5580,
                "op_publish_topics": ["aiSpeedData", "aiState"],
                "heartbeat_interval": 1.0,
                "timeout_seconds": 5.0
            }
        }
        
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # 合并配置
                for key, value in user_config.items():
                    if key in default_config and isinstance(value, dict) and isinstance(default_config[key], dict):
                        default_config[key].update(value)
                    else:
                        default_config[key] = value
        except FileNotFoundError:
            logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        except Exception as e:
            logger.error(f"加载配置错误: {e}")
        
        return default_config
    
    def process_ai_suggestion(self, data: Dict) -> Optional[Dict]:
        """处理AI车速建议"""
        try:
            msg_type = data.get("type", "")
            
            if msg_type == "ai_speed_suggestion":
                speed = data.get("speed", 0.0)
                reason = data.get("reason", "")
                confidence = data.get("confidence", 0.0)
                
                # 记录接收时间
                self.last_speed_received = time.time()
                self.message_count += 1
                
                # 创建OpenPilot格式的消息
                return {
                    "speed": float(speed),
                    "reason": reason,
                    "confidence": float(confidence),
                    "timestamp": int(time.time() * 1e9),
                    "message_id": self.message_count
                }
            
            elif msg_type == "system_status":
                logger.info(f"📊 AI系统状态: {data}")
                return None
                
        except Exception as e:
            logger.error(f"处理AI建议错误: {e}")
        
        return None
    
    def send_to_op(self, topic: str, data: Dict):
        """发送消息到OpenPilot"""
        try:
            # 创建OpenPilot消息格式
            msg = {
                "topic": topic,
                "valid": True,
                "logMonoTime": int(time.time() * 1e9),
                "data": data
            }
            
            # 通过PubMaster发送
            self.pm.send(topic, msg)
            
            logger.info(f"📤 发送到OpenPilot: {topic} | 速度={data.get('speed', 0):.1f}km/h")
            return True
            
        except Exception as e:
            logger.error(f"发送到OpenPilot失败: {e}")
            return False
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            # 发送心跳
            if time.time() - self.last_heartbeat > self.heartbeat_interval:
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "message_count": self.message_count,
                    "status": "healthy"
                }
                
                msg = {
                    "topic": "aiState",
                    "valid": True,
                    "logMonoTime": int(time.time() * 1e9),
                    "data": heartbeat_msg
                }
                
                self.pm.send("aiState", msg)
                self.last_heartbeat = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    def run(self):
        """主运行循环"""
        logger.info("🚀 OpenPilot AI桥接器开始运行")
        
        timeout = self.config["ai_bridge"].get("timeout_seconds", 5.0)
        
        while self.running:
            try:
                # 1. 接收AI建议
                try:
                    message = self.ai_subscriber.recv_string(zmq.NOBLOCK)
                    data = json.loads(message)
                    
                    # 处理建议
                    op_msg = self.process_ai_suggestion(data)
                    
                    if op_msg:
                        # 发送到OpenPilot
                        self.send_to_op("aiSpeedData", op_msg)
                        
                except zmq.Again:
                    # 无新消息
                    pass
                
                # 2. 健康检查
                if int(time.time()) % 2 == 0:  # 每2秒一次
                    self.health_check()
                
                # 3. 定期状态报告
                if int(time.time()) % 10 == 0:
                    logger.info(f"💓 状态: 已处理 {self.message_count} 条消息")
                
                time.sleep(0.01)  # 10ms
                
            except KeyboardInterrupt:
                logger.info("👋 收到中断信号")
                break
            except Exception as e:
                logger.error(f"运行错误: {e}")
                time.sleep(0.1)
    
    def stop(self):
        """停止桥接器"""
        self.running = False
        self.ai_subscriber.close()
        self.context.term()
        logger.info("🛑 OpenPilot AI桥接器已停止")

def signal_handler(sig, frame):
    """信号处理"""
    import signal
    logger.info(f"收到停止信号 {sig}")
    sys.exit(0)

def main():
    """主函数"""
    import signal
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        bridge = OpenPilotAIBridge()
        bridge.run()
    except KeyboardInterrupt:
        logger.info("👋 用户中断")
    except Exception as e:
        logger.error(f"主程序异常: {e}")
    finally:
        if 'bridge' in locals():
            bridge.stop()

if __name__ == "__main__":
    main()