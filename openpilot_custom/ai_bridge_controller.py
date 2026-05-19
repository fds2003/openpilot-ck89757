#!/usr/bin/env python3
"""
AI车速控制桥接器
功能：从customReservedRawData0读取AI数据，转发到controlsState执行
解决：ai_speed_sender.py数据无法执行的问题
"""

import cereal.messaging as messaging
import json
import time
import argparse
import sys
import os
from datetime import datetime

# 添加openpilot路径
sys.path.append('/data/openpilot')

class AIBridgeController:
    def __init__(self):
        """初始化AI桥接器"""
        print("="*70)
        print("🌉 AI车速控制桥接器")
        print("="*70)
        
        # 1. 订阅AI数据通道
        self.ai_sub = messaging.SubMaster(['customReservedRawData0'])
        
        # 2. 发布到OpenPilot控制通道
        self.control_pub = messaging.PubMaster(['controlsState', 'carControl'])
        
        # 3. 状态变量
        self.bridge_active = False
        self.ai_message_count = 0
        self.forward_message_count = 0
        self.last_ai_message = None
        self.last_control_time = 0
        self.fault_detected = False
        self.fault_message = ""
        
        # 4. 配置参数
        self.config = {
            'update_interval': 0.1,       # 检查AI数据的频率
            'min_forward_interval': 0.5,  # 最小转发间隔
            'safety_timeout': 3.0,        # AI数据超时（秒）
            'max_speed_kmh': 120.0,       # 最大允许速度
            'smooth_acceleration': True   # 启用平滑加速度
        }
        
        print(f"📡 订阅: customReservedRawData0 (AI数据)")
        print(f"📤 发布: controlsState, carControl (控制指令)")
        print(f"⚙️  配置: 更新间隔 {self.config['update_interval']}秒")
        print("="*70)
    
    def parse_ai_message(self, data_bytes):
        """解析AI控制消息"""
        try:
            if not data_bytes:
                return None, "无数据"
            
            # 解析JSON
            json_str = data_bytes.decode('utf-8', errors='ignore')
            ai_data = json.loads(json_str)
            
            # 验证消息类型
            if ai_data.get('type') != 'ai_speed_control':
                return None, f"非AI控制消息: {ai_data.get('type')}"
            
            # 提取控制指令
            control_cmd = ai_data.get('control_command', {})
            if not control_cmd:
                return None, "无控制指令"
            
            target_speed_kmh = control_cmd.get('target_speed_kmh', 0)
            target_speed_ms = control_cmd.get('target_speed_ms', 0)
            
            if target_speed_kmh <= 0 and target_speed_ms <= 0:
                return None, "无效的目标车速"
            
            # 返回完整的AI数据
            return ai_data, "解析成功"
            
        except json.JSONDecodeError as e:
            return None, f"JSON解析失败: {e}"
        except Exception as e:
            return None, f"解析异常: {e}"
    
    def forward_to_controls_state(self, ai_data):
        """转发到controlsState通道"""
        try:
            control_cmd = ai_data.get('control_command', {})
            target_speed_kmh = control_cmd.get('target_speed_kmh', 0)
            target_speed_ms = control_cmd.get('target_speed_ms', 0)
            reason = control_cmd.get('reason', 'unknown')
            
            # 速度边界检查
            if target_speed_kmh > self.config['max_speed_kmh']:
                print(f"⚠️ 车速超限: {target_speed_kmh} > {self.config['max_speed_kmh']}")
                return False
            
            # 创建controlsState消息
            msg = messaging.new_message('controlsState')
            
            # 设置控制参数
            if hasattr(msg.controlsState, 'enabled'):
                setattr(msg.controlsState, 'enabled', True)
            if hasattr(msg.controlsState, 'active'):
                setattr(msg.controlsState, 'active', True)
            if hasattr(msg.controlsState, 'vCruise'):
                setattr(msg.controlsState, 'vCruise', float(target_speed_kmh))
            
            # 设置执行器
            if hasattr(msg.controlsState, 'actuators'):
                actuators = msg.controlsState.actuators
                
                # 计算加速度（从车速差估算）
                current_time = time.time()
                if self.last_control_time > 0 and self.last_ai_message:
                    last_speed = self.last_ai_message.get('control_command', {}).get('target_speed_kmh', 0)
                    time_diff = current_time - self.last_control_time
                    if time_diff > 0 and last_speed > 0:
                        speed_diff = target_speed_kmh - last_speed
                        acceleration = speed_diff / (time_diff * 3.6)  # km/h/s -> m/s²
                        acceleration = max(-2.0, min(2.0, acceleration))  # 限制范围
                    else:
                        acceleration = 0.0
                else:
                    acceleration = 0.0
                
                if hasattr(actuators, 'accel'):
                    setattr(actuators, 'accel', float(acceleration))
                if hasattr(actuators, 'steer'):
                    setattr(actuators, 'steer', 0.0)
                if hasattr(actuators, 'brake'):
                    setattr(actuators, 'brake', 0.0)
            
            # 发送消息
            self.control_pub.send('controlsState', msg)
            
            # 更新状态
            self.last_control_time = current_time
            self.forward_message_count += 1
            
            return True
            
        except Exception as e:
            print(f"❌ 转发到controlsState失败: {e}")
            return False
    
    def forward_to_car_control(self, ai_data):
        """转发到carControl通道（丰田卡罗拉备用）"""
        try:
            control_cmd = ai_data.get('control_command', {})
            target_speed_ms = control_cmd.get('target_speed_ms', 0)
            
            # 创建carControl消息
            msg = messaging.new_message('carControl')
            
            # 尝试多种丰田控制字段
            if hasattr(msg.carControl, 'cruiseSpeed'):
                setattr(msg.carControl, 'cruiseSpeed', float(target_speed_ms * 3.6))
            elif hasattr(msg.carControl, 'vCruise'):
                setattr(msg.carControl, 'vCruise', float(target_speed_ms))
            elif hasattr(msg.carControl, 'speed'):
                setattr(msg.carControl, 'speed', float(target_speed_ms))
            
            if hasattr(msg.carControl, 'enabled'):
                setattr(msg.carControl, 'enabled', True)
            
            # 发送消息
            self.control_pub.send('carControl', msg)
            
            return True
            
        except Exception as e:
            print(f"⚠️ 转发到carControl失败: {e}")
            return False
    
    def show_status(self, ai_data, parse_result, forward_success):
        """显示桥接器状态"""
        os.system('clear')
        
        print("="*70)
        print("🌉 AI车速控制桥接器 - 实时状态")
        print("="*70)
        
        # AI数据状态
        if ai_data:
            control_cmd = ai_data.get('control_command', {})
            print(f"📥 AI数据: ID {ai_data.get('id', 'N/A')}")
            print(f"🎯 目标车速: {control_cmd.get('target_speed_kmh', 0):.1f} km/h")
            print(f"📊 控制原因: {control_cmd.get('reason', 'unknown')}")
            print(f"📈 驾驶模式: {ai_data.get('driving_mode', 'N/A')}")
        else:
            print("📥 AI数据: 等待中...")
        
        # 解析结果
        print(f"\n🔍 解析结果: {parse_result}")
        
        # 转发状态
        if forward_success:
            print(f"📤 转发状态: ✅ 成功")
        else:
            print(f"📤 转发状态: ❌ 失败")
        
        # 桥接统计
        print(f"\n📊 桥接统计:")
        print(f"  AI消息数: {self.ai_message_count}")
        print(f"  转发消息: {self.forward_message_count}")
        
        if self.ai_message_count > 0 and self.forward_message_count > 0:
            success_rate = (self.forward_message_count / self.ai_message_count) * 100
            print(f"  转发成功率: {success_rate:.1f}%")
        
        # 故障状态
        if self.fault_detected:
            print(f"🔴 故障状态: {self.fault_message}")
        
        print(f"\n⏱️  时间: {datetime.now().strftime('%H:%M:%S')}")
        print("="*70)
        print("按 Ctrl+C 停止桥接器")
    
    def run_bridge(self, duration=0):
        """运行桥接器"""
        print(f"\n🔄 启动AI桥接器")
        print(f"📡 监听: customReservedRawData0")
        print(f"📤 转发: controlsState, carControl")
        
        if duration > 0:
            print(f"⏱️  运行时长: {duration} 秒")
        else:
            print("♾️  运行模式: 无限运行")
        
        print("="*60)
        
        self.bridge_active = True
        start_time = time.time()
        last_forward_time = 0
        
        try:
            while self.bridge_active:
                # 检查运行时长
                if duration > 0 and (time.time() - start_time) > duration:
                    print(f"\n⏱️ 达到运行时长，停止桥接器")
                    break
                
                # 检查故障状态
                if self.fault_detected:
                    print(f"🔴 检测到故障: {self.fault_message}")
                    time.sleep(3)
                    break
                
                # 检查AI数据
                self.ai_sub.update(0)
                
                if self.ai_sub.updated['customReservedRawData0']:
                    # 获取AI数据
                    data_bytes = self.ai_sub['customReservedRawData0'].data
                    self.ai_message_count += 1
                    
                    # 解析AI数据
                    ai_data, parse_result = self.parse_ai_message(data_bytes)
                    
                    if ai_data:
                        # 检查转发间隔
                        current_time = time.time()
                        if current_time - last_forward_time >= self.config['min_forward_interval']:
                            # 转发到controlsState
                            forward_success = self.forward_to_controls_state(ai_data)
                            
                            # 备用：转发到carControl
                            if forward_success:
                                self.forward_to_car_control(ai_data)
                            
                            # 更新最后转发时间
                            if forward_success:
                                last_forward_time = current_time
                                self.last_ai_message = ai_data
                        else:
                            forward_success = False
                            parse_result = f"转发间隔保护 ({current_time - last_forward_time:.1f}s < {self.config['min_forward_interval']}s)"
                    else:
                        forward_success = False
                else:
                    ai_data = None
                    parse_result = "无新AI数据"
                    forward_success = False
                
                # 显示状态
                self.show_status(ai_data, parse_result, forward_success)
                
                # 等待下一次检查
                time.sleep(self.config['update_interval'])
                
        except KeyboardInterrupt:
            print("\n🛑 用户中断桥接器")
        except Exception as e:
            print(f"❌ 桥接器运行错误: {e}")
            import traceback
            traceback.print_exc()
        
        # 停止桥接器
        self.stop_bridge()
    
    def stop_bridge(self):
        """停止桥接器"""
        self.bridge_active = False
        
        # 发送停止指令
        try:
            msg = messaging.new_message('controlsState')
            if hasattr(msg.controlsState, 'enabled'):
                setattr(msg.controlsState, 'enabled', False)
            if hasattr(msg.controlsState, 'active'):
                setattr(msg.controlsState, 'active', False)
            self.control_pub.send('controlsState', msg)
            print("✅ 已发送停止指令")
        except Exception as e:
            print(f"⚠️ 停止指令发送失败: {e}")
        
        # 显示最终统计
        self.show_final_stats()
    
    def show_final_stats(self):
        """显示最终统计"""
        print("\n" + "="*70)
        print("📊 AI桥接器 - 最终统计")
        print("="*70)
        print(f"AI消息总数: {self.ai_message_count}")
        print(f"转发消息数: {self.forward_message_count}")
        
        if self.ai_message_count > 0:
            success_rate = (self.forward_message_count / self.ai_message_count) * 100
            print(f"转发成功率: {success_rate:.1f}%")
        
        if self.last_ai_message:
            last_speed = self.last_ai_message.get('control_command', {}).get('target_speed_kmh', 0)
            print(f"最后目标车速: {last_speed:.1f} km/h")
        
        print("👋 AI桥接器已停止")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='AI车速控制桥接器 - 连接AI数据与OpenPilot控制',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 启动桥接器（无限运行）
  python3 ai_bridge_controller.py
  
  # 启动桥接器，运行30秒
  python3 ai_bridge_controller.py --duration 30
  
  # 设置高频率检查
  python3 ai_bridge_controller.py --interval 0.05
  
  # 显示帮助
  python3 ai_bridge_controller.py --help

工作流程:
  1. 监听 customReservedRawData0 通道获取AI数据
  2. 解析AI控制指令
  3. 转发到 controlsState 通道
  4. 备选转发到 carControl 通道
  5. 实时显示桥接状态
        """
    )
    
    parser.add_argument('--duration', type=int, default=0,
                       help='运行时长 (秒)，0表示无限运行')
    parser.add_argument('--interval', type=float, default=0.1,
                       help='AI数据检查间隔 (秒)，默认0.1')
    
    args = parser.parse_args()
    
    # 创建桥接器
    bridge = AIBridgeController()
    
    # 设置检查间隔
    if args.interval > 0:
        bridge.config['update_interval'] = args.interval
    
    # 运行桥接器
    bridge.run_bridge(duration=args.duration)

if __name__ == "__main__":
    main()