#!/usr/bin/env python3
"""
限速值对接AI车速控制系统
功能：读取车辆实时限速（LIMIT 值），将其发送给AI控制系统
用法：python3 limit_to_ai_control.py
"""

import time
import json
import cereal.messaging as messaging
from enum import Enum

class DrivingMode(Enum):
    """驾驶模式"""
    LIMIT_FOLLOWING = 1  # 限速跟随
    CRUISE = 2           # 定速巡航
    COASTING = 3         # 滑行避让

class LimitSpeedController:
    def __init__(self):
        """初始化控制器"""
        print("="*60)
        print("🚗 限速值对接AI车速控制系统")
        print("="*60)
        
        # 创建发布者
        self.pm = messaging.PubMaster(['customReservedRawData0'])
        
        # 尝试订阅所有可能包含限速的通道
        self.services = self.detect_speed_limit_sources()
        self.sm = messaging.SubMaster(self.services)
        
        # 状态变量
        self.current_speed_limit = 0.0  # 当前限速值 (km/h)
        self.target_speed = 0.0         # AI目标车速 (m/s)
        self.last_limit_time = 0
        self.driving_mode = DrivingMode.LIMIT_FOLLOWING
        self.message_id = 0
        
        print(f"✅ 已订阅服务: {', '.join(self.services)}")
        print("="*60)
    
    def detect_speed_limit_sources(self):
        """检测可用的限速数据源"""
        try:
            all_services = messaging.SubMaster([]).services()
            
            # 优先级：liveMapData > carState > modelV2
            priority_services = ['liveMapData', 'carState', 'modelV2', 'radarState']
            
            detected = []
            for service in priority_services:
                if service in all_services:
                    detected.append(service)
            
            # 确保至少有一个服务
            if not detected:
                detected = ['radarState']  # 最低要求
            
            return detected
        except Exception as e:
            print(f"⚠️ 服务检测失败: {e}")
            return ['radarState']
    
    def get_current_speed_limit(self):
        """从多个来源获取当前限速值"""
        self.sm.update(0)
        
        # 1. 从 liveMapData 获取（导航/地图限速）
        if 'liveMapData' in self.sm.valid and self.sm.valid['liveMapData']:
            try:
                map_data = self.sm['liveMapData']
                if hasattr(map_data, 'speedLimit') and map_data.speedLimit > 0:
                    limit = float(map_data.speedLimit)
                    if limit != self.current_speed_limit:
                        print(f"📡 从导航获取限速: {limit} km/h")
                        return limit, "navigation"
            except:
                pass
        
        # 2. 从 carState 获取（原厂CAN信号）
        if 'carState' in self.sm.valid and self.sm.valid['carState']:
            try:
                car_state = self.sm['carState']
                # 不同车型字段名可能不同，尝试常见字段
                for field in ['speedLimit', 'cruiseState.speed', 'vCruise']:
                    if hasattr(car_state, field.replace('.', '.')):
                        # 递归获取嵌套属性
                        value = getattr_nested(car_state, field)
                        if value and value > 0:
                            limit = float(value)
                            if limit != self.current_speed_limit:
                                print(f"🚗 从车辆获取限速: {limit} km/h")
                                return limit, "vehicle"
            except:
                pass
        
        # 3. 从 modelV2 获取（视觉识别限速牌）
        if 'modelV2' in self.sm.valid and self.sm.valid['modelV2']:
            try:
                model_data = self.sm['modelV2']
                if hasattr(model_data, 'meta') and hasattr(model_data.meta, 'speedLimit'):
                    limit = float(model_data.meta.speedLimit)
                    if limit > 0 and limit != self.current_speed_limit:
                        print(f"👁️ 从视觉获取限速: {limit} km/h")
                        return limit, "vision"
            except:
                pass
        
        # 没有新限速，返回当前值
        return self.current_speed_limit, "unchanged"
    
    def calculate_target_speed(self, speed_limit_kmh, source):
        """基于限速值计算AI目标车速"""
        if speed_limit_kmh <= 0:
            return 0.0
        
        # 基础目标：限速值本身
        target_kmh = speed_limit_kmh
        
        # 根据数据源调整策略
        if source == "navigation":
            # 导航限速：使用精确值
            target_kmh = speed_limit_kmh
        elif source == "vision":
            # 视觉限速：稍保守（-2 km/h）
            target_kmh = max(0, speed_limit_kmh - 2)
        elif source == "vehicle":
            # 车辆信号：跟随原厂设置
            target_kmh = speed_limit_kmh
        
        # 获取前车信息（用于跟车）
        leading_speed = self.get_leading_vehicle_speed()
        if leading_speed > 0 and leading_speed < target_kmh:
            # 前车较慢，跟随前车
            target_kmh = leading_speed - 2  # 保持安全距离
        
        # 转换为 m/s（Openpilot内部单位）
        target_ms = target_kmh / 3.6
        
        return target_ms
    
    def get_leading_vehicle_speed(self):
        """获取前车速度（用于跟车）"""
        if 'radarState' in self.sm.valid and self.sm.valid['radarState']:
            try:
                radar = self.sm['radarState']
                if hasattr(radar, 'leadOne') and hasattr(radar.leadOne, 'vLead'):
                    v_lead = radar.leadOne.vLead
                    if v_lead > 0:
                        return v_lead * 3.6  # m/s -> km/h
            except:
                pass
        return 0.0
    
    def send_ai_control_command(self, target_speed_ms, speed_limit_kmh, source):
        """发送AI控制指令"""
        current_time = time.time()
        
        # 构建控制消息
        control_msg = {
            "type": "speed_control",
            "id": self.message_id,
            "timestamp": int(current_time * 1000),
            "driving_mode": self.driving_mode.name,
            "speed_limit_kmh": round(speed_limit_kmh, 1),
            "speed_limit_source": source,
            "target_speed_ms": round(target_speed_ms, 2),
            "target_speed_kmh": round(target_speed_ms * 3.6, 1),
            "control_flags": {
                "limit_following": True,
                "smooth_accel": True,
                "safe_following": True
            }
        }
        
        # 转换为JSON并发送
        try:
            json_str = json.dumps(control_msg, ensure_ascii=False)
            msg_bytes = json_str.encode('utf-8')
            self.pm.send('customReservedRawData0', msg_bytes)
            
            self.message_id += 1
            
            # 显示状态
            self.show_control_status(control_msg)
            return True
            
        except Exception as e:
            print(f"❌ 发送控制指令失败: {e}")
            return False
    
    def show_control_status(self, control_msg):
        """显示控制状态"""
        import os
        os.system('clear')
        
        print("="*60)
        print("🚗 AI限速跟随控制系统")
        print("="*60)
        print(f"📊 当前限速: {control_msg['speed_limit_kmh']} km/h")
        print(f"📡 数据来源: {control_msg['speed_limit_source']}")
        print(f"🎯 目标车速: {control_msg['target_speed_kmh']} km/h")
        print(f"⚙️  驾驶模式: {control_msg['driving_mode']}")
        
        # 获取当前车速
        if 'carState' in self.sm.valid and self.sm.valid['carState']:
            try:
                car_state = self.sm['carState']
                if hasattr(car_state, 'vEgo'):
                    current_speed = car_state.vEgo * 3.6
                    print(f"📈 当前车速: {current_speed:.1f} km/h")
                    
                    # 计算速度差
                    speed_diff = control_msg['target_speed_kmh'] - current_speed
                    if speed_diff > 2:
                        action = "🚀 加速"
                    elif speed_diff < -2:
                        action = "🛑 减速"
                    else:
                        action = "⚖️  保持"
                    
                    print(f"📈 控制动作: {action} ({speed_diff:+.1f} km/h)")
            except:
                pass
        
        # 显示前车状态
        lead_speed = self.get_leading_vehicle_speed()
        if lead_speed > 0:
            print(f"🚗 前车速度: {lead_speed:.1f} km/h")
        
        print(f"🆔 消息ID: {control_msg['id']}")
        print("="*60)
    
    def run_continuous_mode(self, interval=0.5):
        """连续运行模式"""
        print("\n🔄 进入连续发送模式（按 Ctrl+C 停止）...")
        print("开始读取限速值并发送AI控制指令...")
        
        try:
            while True:
                # 1. 获取当前限速
                speed_limit, source = self.get_current_speed_limit()
                
                if speed_limit > 0 and speed_limit != self.current_speed_limit:
                    self.current_speed_limit = speed_limit
                    self.last_limit_time = time.time()
                    
                    # 2. 计算目标车速
                    target_speed = self.calculate_target_speed(speed_limit, source)
                    
                    # 3. 发送控制指令
                    self.send_ai_control_command(target_speed, speed_limit, source)
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 连续发送已停止")
        except Exception as e:
            print(f"❌ 运行错误: {e}")
    
    def show_menu(self):
        """显示菜单"""
        while True:
            print("\n" + "="*60)
            print("🚗 限速值对接AI控制系统")
            print("="*60)
            print("1. 测试限速读取")
            print("2. 单次发送控制指令")
            print("3. 连续发送模式")
            print("4. 显示当前状态")
            print("5. 退出")
            print("="*60)
            
            choice = input("请选择 (1-5): ").strip()
            
            if choice == '1':
                self.test_speed_limit_reading()
            elif choice == '2':
                self.send_single_command()
            elif choice == '3':
                self.run_continuous_mode()
            elif choice == '4':
                self.show_current_status()
            elif choice == '5':
                print("\n👋 退出程序")
                break
            else:
                print("❌ 无效选择")
    
    def test_speed_limit_reading(self):
        """测试限速读取功能"""
        print("\n🧪 测试限速读取...")
        
        for i in range(5):
            speed_limit, source = self.get_current_speed_limit()
            if speed_limit > 0:
                print(f"测试 {i+1}: 读取到限速 {speed_limit} km/h (来源: {source})")
            else:
                print(f"测试 {i+1}: 未读取到限速值")
            time.sleep(1)
    
    def send_single_command(self):
        """发送单次控制指令"""
        speed_limit, source = self.get_current_speed_limit()
        
        if speed_limit > 0:
            target_speed = self.calculate_target_speed(speed_limit, source)
            success = self.send_ai_control_command(target_speed, speed_limit, source)
            
            if success:
                print("✅ 控制指令发送成功")
            else:
                print("❌ 控制指令发送失败")
        else:
            print("⚠️ 未检测到限速值，无法发送指令")
    
    def show_current_status(self):
        """显示当前状态"""
        print(f"\n📊 当前状态:")
        print(f"  当前限速: {self.current_speed_limit} km/h")
        print(f"  驾驶模式: {self.driving_mode.name}")
        print(f"  已发送消息: {self.message_id} 条")

# 辅助函数：递归获取嵌套属性
def getattr_nested(obj, attr_path):
    """递归获取嵌套属性"""
    try:
        parts = attr_path.split('.')
        current = obj
        for part in parts:
            current = getattr(current, part)
        return current
    except:
        return None

if __name__ == "__main__":
    # 设置Python路径
    import sys
    sys.path.append('/data/openpilot')
    
    controller = LimitSpeedController()
    controller.show_menu()
