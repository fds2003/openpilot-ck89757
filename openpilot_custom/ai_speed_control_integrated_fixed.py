#!/usr/bin/env python3
"""
AI车速控制系统 - 修复版
修复了 liveMapData 服务名称问题
"""

import json
import time
import argparse
import cereal.messaging as messaging
import sys
import os
from datetime import datetime

# 添加openpilot路径
sys.path.append('/data/openpilot')

class AISpeedControlIntegrated:
    def __init__(self, base_target_speed=60.0):
        """初始化修复版控制器"""
        print("="*70)
        print("🚗 AI车速控制系统 - 修复版")
        print("="*70)
        
        # 基本参数
        self.base_target_speed = float(base_target_speed)
        self.update_interval = 1.0
        self.duration = 0
        
        # 状态变量
        self.current_speed_kmh = 0.0
        self.iteration_count = 0
        self.is_running = False
        self.start_time = 0
        
        # 导航限速相关
        self.nav_speed_limit = 0.0
        self.nav_limit_source = "none"
        self.last_nav_update = 0
        
        # 修复：先探测可用的服务名称
        print("🔍 探测可用的消息服务...")
        available_services = self._detect_available_services()
        print(f"✅ 可用服务: {', '.join(available_services)}")
        
        # 选择正确的导航服务名称
        navigation_services = ['liveMap', 'liveMapData', 'navi', 'navigation', 'liveLocationKalman']
        self.nav_service_name = None
        
        for service in navigation_services:
            if service in available_services:
                self.nav_service_name = service
                break
        
        if self.nav_service_name:
            print(f"✅ 使用导航服务: {self.nav_service_name}")
        else:
            print("⚠️ 未找到导航服务，将使用车速估算")
            self.nav_service_name = None
        
        # 初始化消息系统
        services_to_subscribe = ['carState', 'radarState']
        if self.nav_service_name:
            services_to_subscribe.append(self.nav_service_name)
        
        self.sm = messaging.SubMaster(services_to_subscribe)
        self.pm = messaging.PubMaster(['customReservedRawData0'])
        
        print(f"⚙️  控制参数:")
        print(f"   基础目标: {self.base_target_speed:.1f} km/h")
        print(f"   更新间隔: {self.update_interval:.1f} 秒")
        print(f"📡 订阅服务: {', '.join(services_to_subscribe)}")
        print("="*70)
    
    def _detect_available_services(self):
        """探测可用的消息服务"""
        try:
            all_services = messaging.SubMaster([]).services()
            return list(all_services.keys())
        except Exception as e:
            print(f"⚠️ 服务探测失败: {e}")
            return ['carState', 'radarState']  # 最小服务集
    
    def get_vehicle_status_safe(self):
        """安全获取车辆状态"""
        self.sm.update(0)
        
        if 'carState' in self.sm.valid and self.sm.valid['carState']:
            cs = self.sm['carState']
            if hasattr(cs, 'vEgo'):
                self.current_speed_kmh = cs.vEgo * 3.6
                return {
                    'speed_kmh': self.current_speed_kmh,
                    'speed_ms': cs.vEgo,
                    'valid': True
                }
        
        return {'speed_kmh': 0.0, 'speed_ms': 0.0, 'valid': False}
    
    def get_navigation_speed_limit(self):
        """获取导航限速（支持多种消息格式）"""
        self.sm.update(0)
        
        # 如果找到了导航服务
        if self.nav_service_name and self.nav_service_name in self.sm.valid and self.sm.valid[self.nav_service_name]:
            try:
                nav_data = self.sm[self.nav_service_name]
                
                # 尝试从导航数据中提取限速信息
                speed_limit = self._extract_speed_limit_from_nav(nav_data)
                
                if speed_limit > 0:
                    self.nav_speed_limit = speed_limit
                    self.nav_limit_source = self.nav_service_name
                    self.last_nav_update = time.time()
                    return self.nav_speed_limit, self.nav_limit_source
                    
            except Exception as e:
                print(f"⚠️ 导航限速解析失败: {e}")
        
        # 2. 从carState获取巡航速度
        if 'carState' in self.sm.valid and self.sm.valid['carState']:
            try:
                cs = self.sm['carState']
                if hasattr(cs, 'cruiseState'):
                    cruise_state = cs.cruiseState
                    if hasattr(cruise_state, 'speed') and cruise_state.speed > 0:
                        self.nav_speed_limit = cruise_state.speed
                        self.nav_limit_source = "cruiseControl"
                        return self.nav_speed_limit, self.nav_limit_source
            except:
                pass
        
        # 3. 检查是否有缓存数据
        if time.time() - self.last_nav_update < 5.0 and self.nav_speed_limit > 0:
            return self.nav_speed_limit, f"{self.nav_limit_source}_cached"
        
        # 4. 默认值
        self.nav_speed_limit = 0.0
        self.nav_limit_source = "none"
        return 0.0, "none"
    
    def _extract_speed_limit_from_nav(self, nav_data):
        """从导航数据中提取限速值（支持多种格式）"""
        speed_limit = 0.0
        
        # 尝试各种可能的字段名
        possible_fields = [
            'speedLimit',
            'speedLimitValue',
            'speedLimitKmh',
            'speed_limit',
            'speed_limit_value',
            'currentSpeedLimit',
            'limitSpeed'
        ]
        
        for field in possible_fields:
            if hasattr(nav_data, field):
                value = getattr(nav_data, field)
                if isinstance(value, (int, float)) and value > 0:
                    speed_limit = float(value)
                    print(f"📡 从 {field} 字段获取到限速: {speed_limit} km/h")
                    return speed_limit
        
        # 如果是 liveMap 服务，可能有特定结构
        if hasattr(nav_data, 'meta') and hasattr(nav_data.meta, 'speedLimit'):
            value = nav_data.meta.speedLimit
            if value > 0:
                speed_limit = float(value)
                print(f"📡 从 meta.speedLimit 字段获取到限速: {speed_limit} km/h")
                return speed_limit
        
        return speed_limit
    
    def calculate_final_target_speed(self):
        """计算最终目标车速"""
        # 1. 获取导航限速
        nav_limit, nav_source = self.get_navigation_speed_limit()
        
        # 2. 获取当前车速
        vehicle_status = self.get_vehicle_status_safe()
        current_speed = vehicle_status['speed_kmh']
        
        # 3. 计算目标车速策略
        if nav_limit > 0:
            # 优先使用导航限速
            target_speed = nav_limit
            reason = f"nav_limit_{nav_source}"
            
            # 平滑过渡
            if abs(target_speed - current_speed) > 20:
                if target_speed > current_speed:
                    target_speed = min(target_speed, current_speed + 5.0)
                    reason = f"nav_limit_ramp_up_{nav_source}"
                else:
                    target_speed = max(target_speed, current_speed - 5.0)
                    reason = f"nav_limit_ramp_down_{nav_source}"
        
        else:
            # 导航限速不可用，使用基础目标
            target_speed = self.base_target_speed
            reason = "base_target"
            
            # 根据当前车速微调
            if current_speed > 0:
                if current_speed > target_speed + 10:
                    target_speed = min(target_speed, current_speed - 5.0)
                    reason = "current_too_fast"
                elif current_speed < target_speed - 10:
                    target_speed = max(target_speed, current_speed + 5.0)
                    reason = "current_too_slow"
        
        # 4. 安全边界检查
        target_speed = max(10.0, min(target_speed, 120.0))
        
        return target_speed, reason, nav_limit, nav_source
    
    def send_ai_speed_command(self, target_speed_kmh, reason, nav_limit=0.0, nav_source="none"):
        """发送AI车速命令"""
        vehicle_status = self.get_vehicle_status_safe()
        
        # 构建消息
        message = {
            "type": "ai_speed_control",
            "id": self.iteration_count + 1,
            "timestamp": int(time.time() * 1000),
            "version": "fixed_1.0",
            
            "vehicle_status": {
                "speed_kmh": round(vehicle_status['speed_kmh'], 1),
                "valid": vehicle_status['valid']
            },
            
            "navigation": {
                "limit_kmh": round(nav_limit, 1) if nav_limit > 0 else 0.0,
                "source": nav_source,
                "age_sec": round(time.time() - self.last_nav_update, 1) if self.last_nav_update > 0 else 999
            },
            
            "control": {
                "target_speed_kmh": round(target_speed_kmh, 1),
                "reason": reason,
                "base_target": round(self.base_target_speed, 1)
            }
        }
        
        try:
            # 发送到customReservedRawData0通道
            json_str = json.dumps(message, ensure_ascii=False)
            msg_bytes = json_str.encode('utf-8')
            self.pm.send('customReservedRawData0', msg_bytes)
            
            self.iteration_count += 1
            return True, message
            
        except Exception as e:
            print(f"❌ 发送命令失败: {e}")
            return False, None
    
    def show_integrated_dashboard(self, vehicle_status, target_speed_kmh, reason, nav_limit, nav_source):
        """显示集成版仪表板"""
        os.system('clear')
        
        print("="*70)
        print("🚗 AI车速控制系统 - 修复版")
        print("="*70)
        
        # 车辆状态
        if vehicle_status['valid']:
            speed_kmh = vehicle_status['speed_kmh']
            print(f"📈 当前车速: {speed_kmh:6.1f} km/h")
            
            # 速度条
            speed_percent = min(100, int(speed_kmh / 120 * 100))
            bar_length = 20
            filled = int(bar_length * speed_percent / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            print(f"   {bar} {speed_percent}%")
        else:
            print(f"📈 当前车速: 无效")
        
        # 导航限速
        if nav_limit > 0:
            limit_status = f"{nav_limit:6.1f} km/h ({nav_source})"
        else:
            limit_status = "无有效限速"
        print(f"🚦 导航限速: {limit_status}")
        
        # 控制状态
        print(f"\n🎯 目标车速: {target_speed_kmh:6.1f} km/h")
        print(f"🔧 控制原因: {reason}")
        
        # 速度差异
        if vehicle_status['valid']:
            speed_diff = target_speed_kmh - vehicle_status['speed_kmh']
            if speed_diff > 5:
                action = "🚀 加速"
            elif speed_diff < -5:
                action = "🛑 减速"
            else:
                action = "⚖️  保持"
            print(f"📈 控制动作: {action} ({speed_diff:+.1f} km/h)")
        
        # 运行统计
        elapsed = time.time() - self.start_time if self.start_time > 0 else 0
        print(f"\n📊 运行统计:")
        print(f"  迭代次数: {self.iteration_count}")
        print(f"  运行时间: {elapsed:.1f} 秒")
        print(f"  基础目标: {self.base_target_speed:.1f} km/h")
        
        if elapsed > 0 and self.iteration_count > 0:
            print(f"  平均频率: {self.iteration_count/elapsed:.1f} Hz")
        
        print("="*70)
        print("按 Ctrl+C 停止控制")
    
    def safe_cleanup(self):
        """安全清理"""
        print("\n🧹 开始安全清理...")
        
        try:
            # 发送停止消息
            msg = {
                "type": "ai_speed_control",
                "id": 9999,
                "timestamp": int(time.time() * 1000),
                "control": {
                    "target_speed_kmh": 0.0,
                    "reason": "system_shutdown"
                }
            }
            
            json_str = json.dumps(msg, ensure_ascii=False)
            msg_bytes = json_str.encode('utf-8')
            self.pm.send('customReservedRawData0', msg_bytes)
            
            time.sleep(0.5)
            print("✅ 安全清理完成")
            return True
            
        except Exception as e:
            print(f"⚠️ 清理过程出错: {e}")
            return False
    
    def run_control_loop(self, duration=0):
        """运行控制循环"""
        print(f"\n🔄 启动控制循环")
        print(f"🎯 基础目标: {self.base_target_speed:.1f} km/h")
        
        if self.nav_service_name:
            print(f"💡 导航服务: {self.nav_service_name} (优先使用)")
        else:
            print(f"💡 导航服务: 未找到 (使用车速估算)")
        
        if duration > 0:
            print(f"⏱️  运行时长: {duration} 秒")
        else:
            print("♾️  运行模式: 无限循环")
        
        print(f"📡 更新间隔: {self.update_interval:.1f} 秒")
        print("="*60)
        
        self.is_running = True
        self.start_time = time.time()
        
        try:
            while self.is_running:
                # 检查运行时长
                if duration > 0 and (time.time() - self.start_time) > duration:
                    print(f"\n⏱️ 达到运行时长，停止控制")
                    break
                
                # 获取车辆状态
                vehicle_status = self.get_vehicle_status_safe()
                
                # 计算目标车速
                target_speed, reason, nav_limit, nav_source = self.calculate_final_target_speed()
                
                # 发送控制命令
                success, message = self.send_ai_speed_command(target_speed, reason, nav_limit, nav_source)
                
                if success:
                    # 显示仪表板
                    self.show_integrated_dashboard(vehicle_status, target_speed, reason, nav_limit, nav_source)
                else:
                    print(f"⚠️ 第{self.iteration_count}次控制失败")
                
                time.sleep(self.update_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 用户中断控制")
        except Exception as e:
            print(f"❌ 控制循环错误: {e}")
        finally:
            # 安全清理
            self.is_running = False
            self.safe_cleanup()
            self.show_final_stats()
    
    def show_final_stats(self):
        """显示最终统计"""
        if self.start_time == 0:
            return
        
        elapsed = time.time() - self.start_time
        
        print("\n" + "="*70)
        print("📊 AI车速控制系统 - 最终统计")
        print("="*70)
        print(f"运行时长: {elapsed:.1f} 秒")
        print(f"迭代次数: {self.iteration_count}")
        
        if elapsed > 0 and self.iteration_count > 0:
            print(f"平均频率: {self.iteration_count/elapsed:.1f} Hz")
        
        print(f"基础目标: {self.base_target_speed:.1f} km/h")
        print(f"最终车速: {self.current_speed_kmh:.1f} km/h")
        print(f"导航限源: {self.nav_limit_source}")
        print(f"导航限速: {self.nav_speed_limit:.1f} km/h")
        
        print("="*70)
        print("👋 AI车速控制系统已停止")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='AI车速控制系统 - 修复版',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基础运行
  python3 ai_speed_control_integrated_fixed.py
  
  # 指定目标车速
  python3 ai_speed_control_integrated_fixed.py --speed 80
  
  # 运行30秒测试
  python3 ai_speed_control_integrated_fixed.py --duration 30
  
  # 高频率更新
  python3 ai_speed_control_integrated_fixed.py --interval 0.5
  
修复内容:
  - 自动探测可用消息服务
  - 支持多种导航服务名: liveMap, liveMapData, navi等
  - 避免KeyError错误
        """
    )
    
    parser.add_argument('--speed', type=float, default=60.0,
                       help='基础目标车速 (km/h)，默认60.0')
    parser.add_argument('--duration', type=int, default=0,
                       help='运行时长 (秒)，0表示无限运行')
    parser.add_argument('--interval', type=float, default=1.0,
                       help='控制更新间隔 (秒)，默认1.0')
    
    args = parser.parse_args()
    
    # 创建控制器
    controller = AISpeedControlIntegrated(base_target_speed=args.speed)
    controller.update_interval = args.interval
    
    # 运行控制循环
    controller.run_control_loop(duration=args.duration)

if __name__ == "__main__":
    main()
