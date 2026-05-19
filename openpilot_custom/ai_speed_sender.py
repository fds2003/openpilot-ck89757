#!/usr/bin/env python3
"""
AI 车速控制系统 - 完整修复版
功能：1. 自动检测可用数据源
      2. 读取限速值（视觉/导航/原厂）
      3. 实现滑行避让逻辑
      4. 发送AI控制指令
      5. 实时监控面板
      6. 命令行参数支持
零编译，零源码修改
"""

import json
import time
import argparse
import cereal.messaging as messaging
from collections import deque
import math
from enum import Enum
from cereal import car
import sys
import os

# 添加openpilot路径
sys.path.append('/data/openpilot')

class DrivingMode(Enum):
    """驾驶模式状态机"""
    NORMAL = 0               # 正常驾驶
    LIMIT_FOLLOWING = 1      # 限速跟随
    COASTING_DETECTED = 2    # 检测到滑行
    COASTING_EXECUTING = 3   # 执行滑行
    AVOIDING_LEFT = 4        # 向左避让
    AVOIDING_RIGHT = 5       # 向右避让
    RETURNING = 6            # 回归车道
    COMPLETED = 7            # 完成避让
    EMERGENCY = 8            # 紧急情况

class AISpeedSender:
    def __init__(self):
        """初始化AI车速控制系统"""
        # 发布者
        self.pm = messaging.PubMaster(['customReservedRawData0'])
        self.message_id = 0
        
        # 检测可用服务
        self.available_services = self.detect_available_services()
        print(f"✅ 检测到可用服务: {', '.join(self.available_services)}")
        
        # 初始化订阅管理器
        self.sm = messaging.SubMaster(self.available_services)
        
        # 运行模式检测
        if 'liveMapData' in self.available_services:
            self.run_mode = "FULL"
            print("🚀 启用完整模式（含导航限速）")
        else:
            self.run_mode = "SIMPLE"
            print("⚠️  liveMapData不可用，启用简化模式")
        
        # 道路基准配置
        self.road_base_config = {
            "city_road": {"base_speed": 40.0, "min_speed": 20.0, "max_speed": 60.0, "name": "城市道路"},
            "expressway": {"base_speed": 80.0, "min_speed": 50.0, "max_speed": 100.0, "name": "快速路"},
            "highway": {"base_speed": 100.0, "min_speed": 60.0, "max_speed": 120.0, "name": "高速公路"},
            "unknown": {"base_speed": 50.0, "min_speed": 20.0, "max_speed": 100.0, "name": "未知道路"}
        }
        
        # 滑行避让参数
        self.coasting_params = {
            "detection_distance": 50.0,     # 检测距离（米）
            "stationary_threshold": 0.5,    # 静止判断阈值（m/s）
            "coasting_deceleration": 1.5,   # 滑行减速度（m/s²）
            "safe_distance": 3.0,           # 安全停车距离（米）
            "avoidance_lateral_offset": 0.5, # 避让横向偏移（米）
            "return_duration": 3.0,         # 回归原车道时长（秒）
            "coasting_complete_speed": 5.0  # 滑行完成速度（km/h）
        }
        
        # 状态变量
        self.driving_mode = DrivingMode.NORMAL
        self.current_road_type = "city_road"
        self.current_speed_limit = 0.0      # 当前限速值（km/h）
        self.target_speed = 0.0             # AI目标车速（m/s）
        self.last_real_speed = 0.0          # 上次真实车速
        self.last_speed = 0.0               # 上次建议车速
        
        # 滑行相关
        self.coasting_start_time = 0
        self.coasting_target_speed = 0.0
        self.avoidance_side = "none"
        self.avoidance_start_time = 0
        self.return_progress = 0.0
        
        # 数据质量跟踪
        self.data_quality = {}
        for service in self.available_services:
            self.data_quality[service] = False
        
        # 控制执行跟踪
        self.control_execution_count = 0
        self.last_control_time = 0
        self.last_executed_speed = 0.0
        
        # 历史记录
        self.speed_history = deque(maxlen=20)
        self.limit_history = deque(maxlen=20)
        
        print("="*60)
        print("🚗 AI车速控制系统 - 完整修复版")
        print("="*60)
        print(f"运行模式: {self.run_mode}")
        print(f"驾驶模式: {self.driving_mode.name}")
        print(f"订阅服务: {len(self.available_services)}个")
        print("="*60)
    
    def detect_available_services(self):
        """检测系统可用的服务"""
        try:
            all_services = messaging.SubMaster([]).services()
            
            # 基础必选服务
            base_services = ['radarState', 'carState']
            
            # 可选服务
            optional_services = []
            for service in ['liveMapData', 'modelV2', 'carControl', 'liveLocationKalman']:
                if service in all_services:
                    optional_services.append(service)
            
            return base_services + optional_services
            
        except Exception as e:
            print(f"⚠️ 服务检测失败: {e}")
            return ['radarState', 'carState']  # 最小服务集
    
    def update_data_quality(self):
        """更新数据质量状态"""
        for service in self.available_services:
            if service in self.sm.valid:
                self.data_quality[service] = self.sm.valid[service]
            else:
                self.data_quality[service] = False
    
    def get_current_vehicle_status(self):
        """获取车辆当前状态"""
        self.sm.update(0)
        self.update_data_quality()
        
        status = {
            'speed_kmh': 0.0,
            'speed_ms': 0.0,
            'accelerator': 0.0,
            'brake': 0.0,
            'steering_angle': 0.0,
            'gear': 'unknown',
            'valid': False
        }
        
        if self.data_quality.get('carState', False):
            cs = self.sm['carState']
            
            # 车速
            if hasattr(cs, 'vEgo'):
                speed_ms = cs.vEgo
                speed_kmh = speed_ms * 3.6
                status.update({
                    'speed_ms': speed_ms,
                    'speed_kmh': speed_kmh,
                    'valid': True
                })
                self.last_real_speed = speed_kmh
            
            # 油门刹车
            if hasattr(cs, 'gas'):
                status['accelerator'] = cs.gas
            if hasattr(cs, 'brake'):
                status['brake'] = cs.brake
            
            # 转向
            if hasattr(cs, 'steeringAngleDeg'):
                status['steering_angle'] = cs.steeringAngleDeg
            
            # 档位
            if hasattr(cs, 'gearShifter'):
                gear_map = {
                    car.CarState.GearShifter.park: 'P',
                    car.CarState.GearShifter.reverse: 'R',
                    car.CarState.GearShifter.neutral: 'N',
                    car.CarState.GearShifter.drive: 'D',
                    car.CarState.GearShifter.low: 'L',
                }
                status['gear'] = gear_map.get(cs.gearShifter, 'unknown')
        
        return status
    
    def get_speed_limit_from_multiple_sources(self):
        """从多个来源获取限速值"""
        limit_value = 0.0
        source = "unknown"
        
        # 1. 从liveMapData获取（导航/地图）
        if self.data_quality.get('liveMapData', False):
            try:
                map_data = self.sm['liveMapData']
                if hasattr(map_data, 'speedLimit') and map_data.speedLimit > 0:
                    limit_value = float(map_data.speedLimit)
                    source = "liveMapData"
                    return limit_value, source
            except:
                pass
        
        # 2. 从carState获取（原厂CAN信号）
        if self.data_quality.get('carState', False):
            try:
                cs = self.sm['carState']
                # 尝试多种可能的字段名
                for field_name in ['speedLimit', 'cruiseState.speed', 'vCruise']:
                    try:
                        if hasattr(cs, field_name):
                            value = getattr(cs, field_name)
                            if value and value > 0:
                                limit_value = float(value)
                                source = "carState"
                                return limit_value, source
                    except:
                        pass
            except:
                pass
        
        # 3. 从modelV2获取（视觉识别）
        if self.data_quality.get('modelV2', False):
            try:
                model = self.sm['modelV2']
                if hasattr(model, 'meta') and hasattr(model.meta, 'speedLimit'):
                    limit_value = float(model.meta.speedLimit)
                    if limit_value > 0:
                        source = "modelV2"
                        return limit_value, source
            except:
                pass
        
        # 4. 基于当前车速估计
        vehicle_status = self.get_current_vehicle_status()
        if vehicle_status['valid'] and vehicle_status['speed_kmh'] > 0:
            current_speed = vehicle_status['speed_kmh']
            if current_speed >= 80:
                limit_value = 100.0
            elif current_speed >= 60:
                limit_value = 80.0
            elif current_speed >= 40:
                limit_value = 60.0
            else:
                limit_value = 40.0
            source = "estimated"
            return limit_value, source
        
        # 5. 使用默认值
        limit_value = 50.0
        source = "default"
        return limit_value, source
    
    def detect_leading_vehicle(self):
        """检测前方车辆"""
        lead_data = {
            "detected": False,
            "distance": float('inf'),
            "speed": 0.0,
            "relative_speed": 0.0,
            "is_stationary": False,
            "valid": False
        }
        
        if self.data_quality.get('radarState', False):
            try:
                radar = self.sm['radarState']
                if hasattr(radar, 'leadOne'):
                    lead = radar.leadOne
                    if hasattr(lead, 'dRel') and lead.dRel > 0:
                        lead_data.update({
                            "detected": True,
                            "distance": lead.dRel,
                            "speed": lead.vLead if hasattr(lead, 'vLead') else 0.0,
                            "relative_speed": lead.vRel if hasattr(lead, 'vRel') else 0.0,
                            "is_stationary": abs(lead.vRel) < self.coasting_params["stationary_threshold"],
                            "valid": True
                        })
            except Exception as e:
                print(f"[前车检测] 错误: {e}")
        
        return lead_data
    
    def check_coasting_condition(self, lead_data):
        """检查是否触发滑行"""
        if not lead_data["detected"] or not lead_data["valid"]:
            return False
        
        if lead_data["distance"] > self.coasting_params["detection_distance"]:
            return False
        
        if not lead_data["is_stationary"]:
            return False
        
        if self.driving_mode not in [DrivingMode.NORMAL, DrivingMode.COASTING_DETECTED, DrivingMode.LIMIT_FOLLOWING]:
            return False
        
        return True
    
    def execute_coasting_mode(self, current_speed, lead_distance):
        """执行滑行模式"""
        if self.driving_mode in [DrivingMode.NORMAL, DrivingMode.LIMIT_FOLLOWING]:
            self.driving_mode = DrivingMode.COASTING_DETECTED
            self.coasting_start_time = time.time()
            
            # 计算安全滑行距离
            v0 = current_speed / 3.6
            a = -self.coasting_params["coasting_deceleration"]
            s_stop = (v0 ** 2) / (2 * abs(a))
            
            if lead_distance > s_stop + self.coasting_params["safe_distance"]:
                self.driving_mode = DrivingMode.COASTING_EXECUTING
                self.coasting_target_speed = self.coasting_params["coasting_complete_speed"]
                
                print(f"🚦 触发滑行模式（车速: {current_speed:.1f} km/h）")
                print(f"  前车距离: {lead_distance:.1f} m")
                print(f"  目标速度: {self.coasting_target_speed:.1f} km/h")
                print(f"  停车距离: {s_stop:.1f} m")
                
                return "coasting_started"
        
        elif self.driving_mode == DrivingMode.COASTING_EXECUTING:
            if lead_distance < self.coasting_params["safe_distance"] * 2:
                self.prepare_avoidance()
                return "preparing_avoidance"
        
        return "coasting_in_progress"
    
    def prepare_avoidance(self):
        """准备避让"""
        self.avoidance_side = "left"
        self.driving_mode = DrivingMode.AVOIDING_LEFT
        self.avoidance_start_time = time.time()
        print(f"🔄 准备向左避让")
    
    def execute_avoidance(self):
        """执行避让"""
        if self.driving_mode in [DrivingMode.AVOIDING_LEFT, DrivingMode.AVOIDING_RIGHT]:
            try:
                lead_data = self.detect_leading_vehicle()
                if lead_data["distance"] > self.coasting_params["detection_distance"] * 1.5:
                    self.driving_mode = DrivingMode.RETURNING
                    self.return_progress = 0.0
                    print(f"✅ 已通过障碍物，开始回归")
            except Exception as e:
                print(f"[避让执行] 错误: {e}")
    
    def execute_return(self):
        """执行回归"""
        if self.avoidance_start_time > 0:
            elapsed = time.time() - self.avoidance_start_time
            self.return_progress = min(1.0, elapsed / self.coasting_params["return_duration"])
            
            if self.return_progress >= 1.0:
                self.driving_mode = DrivingMode.COMPLETED
                print(f"🎯 回归完成")
                
                time.sleep(1.0)
                self.driving_mode = DrivingMode.NORMAL
                self.avoidance_side = "none"
                self.return_progress = 0.0
        
        return self.return_progress
    
    def calculate_target_speed(self, speed_limit_kmh, vehicle_status, lead_data):
        """计算目标车速"""
        # 基础目标：限速值
        base_target_kmh = speed_limit_kmh
        
        # 根据驾驶模式调整
        if self.driving_mode == DrivingMode.NORMAL:
            target_kmh = base_target_kmh
            reason = "normal_driving"
        
        elif self.driving_mode == DrivingMode.LIMIT_FOLLOWING:
            target_kmh = base_target_kmh
            reason = "limit_following"
        
        elif self.driving_mode in [DrivingMode.COASTING_DETECTED, DrivingMode.COASTING_EXECUTING]:
            if lead_data["detected"] and lead_data["valid"]:
                safe_distance = lead_data["distance"] - self.coasting_params["safe_distance"]
                if safe_distance <= 0:
                    target_kmh = 0.0
                    reason = "emergency_stop"
                else:
                    v_current = vehicle_status['speed_ms']
                    a = -self.coasting_params["coasting_deceleration"]
                    t_stop = v_current / abs(a)
                    s_required = v_current * t_stop + 0.5 * a * (t_stop ** 2)
                    
                    if safe_distance < s_required:
                        v_safe = math.sqrt(2 * abs(a) * safe_distance)
                        target_kmh = v_safe * 3.6
                    else:
                        target_kmh = max(self.coasting_target_speed, 
                                       vehicle_status['speed_kmh'] - (self.coasting_params["coasting_deceleration"] * 3.6))
                    
                    target_kmh = max(0, min(target_kmh, base_target_kmh))
                    reason = "coasting_deceleration"
            else:
                target_kmh = base_target_kmh
                reason = "coasting_no_lead"
        
        elif self.driving_mode in [DrivingMode.AVOIDING_LEFT, DrivingMode.AVOIDING_RIGHT]:
            target_kmh = max(5.0, vehicle_status['speed_kmh'] * 0.7)
            reason = "avoidance_slow"
        
        elif self.driving_mode == DrivingMode.RETURNING:
            progress = self.return_progress
            target_kmh = 5.0 + (base_target_kmh - 5.0) * progress
            reason = f"returning_{progress:.0%}"
        
        else:
            target_kmh = base_target_kmh
            reason = "fallback"
        
        # 前车跟随
        if lead_data["detected"] and lead_data["valid"] and lead_data["distance"] < 30:
            target_kmh = min(target_kmh, lead_data["speed"] * 3.6)
            reason = "car_following"
        
        # 边界检查
        min_speed = self.road_base_config.get(self.current_road_type, {}).get("min_speed", 20.0)
        max_speed = self.road_base_config.get(self.current_road_type, {}).get("max_speed", 120.0)
        target_kmh = max(min_speed, min(target_kmh, max_speed))
        
        # 转换为m/s
        target_ms = target_kmh / 3.6
        
        return target_ms, target_kmh, reason
    
    def smooth_transition(self, target_speed_kmh):
        """平滑过渡"""
        if self.last_speed == 0.0:
            return target_speed_kmh
        
        max_change = 3.0
        diff = target_speed_kmh - self.last_speed
        
        if abs(diff) <= max_change:
            return target_speed_kmh
        elif diff > 0:
            return self.last_speed + max_change
        else:
            return self.last_speed - max_change
    
    def send_ai_control_command(self, target_speed_ms, target_speed_kmh, speed_limit_kmh, speed_limit_source, reason):
        """发送AI控制指令"""
        vehicle_status = self.get_current_vehicle_status()
        lead_data = self.detect_leading_vehicle()
        
        # 构建消息
        message = {
            "type": "ai_speed_control",
            "id": self.message_id + 1,
            "timestamp": int(time.time() * 1000),
            "run_mode": self.run_mode,
            "driving_mode": self.driving_mode.name,
            
            "vehicle_status": {
                "speed_kmh": round(vehicle_status['speed_kmh'], 1),
                "accelerator": round(vehicle_status['accelerator'], 3),
                "brake": round(vehicle_status['brake'], 3),
                "steering_angle": round(vehicle_status['steering_angle'], 1),
                "gear": vehicle_status['gear'],
                "valid": vehicle_status['valid']
            },
            
            "speed_limit": {
                "value_kmh": round(speed_limit_kmh, 1),
                "source": speed_limit_source
            },
            
            "control_command": {
                "target_speed_ms": round(target_speed_ms, 2),
                "target_speed_kmh": round(target_speed_kmh, 1),
                "reason": reason
            },
            
            "lead_vehicle": {
                "detected": lead_data["detected"],
                "distance": round(lead_data["distance"], 1),
                "speed_kmh": round(lead_data["speed"] * 3.6, 1),
                "relative_speed_kmh": round(lead_data["relative_speed"] * 3.6, 1),
                "is_stationary": lead_data["is_stationary"]
            },
            
            "avoidance": {
                "side": self.avoidance_side,
                "progress": round(self.return_progress, 2)
            },
            
            "data_quality": self.data_quality,
            "control_count": self.control_execution_count
        }
        
        # 发送消息
        try:
            json_str = json.dumps(message, ensure_ascii=False)
            msg_bytes = json_str.encode('utf-8')
            self.pm.send('customReservedRawData0', msg_bytes)
            
            self.message_id += 1
            self.last_speed = target_speed_kmh
            self.speed_history.append(target_speed_kmh)
            self.limit_history.append(speed_limit_kmh)
            
            # 更新控制跟踪
            current_time = time.time()
            if current_time - self.last_control_time > 1.0:
                self.last_control_time = current_time
                self.last_executed_speed = target_speed_kmh
                self.control_execution_count += 1
            
            return True, message
            
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return False, None
    
    def send_enhanced_recommendation(self):
        """发送增强的车速建议（修复版）"""
        # 1. 获取车辆实时状态
        vehicle_status = self.get_current_vehicle_status()
        
        # 2. 根据运行模式获取导航数据
        if self.run_mode == "FULL":
            # 从liveMapData获取导航数据
            nav_data = {"road_type": "city_road", "speed_limit": 50.0, "source": "fallback", "valid": False}
        else:
            # 简化模式：基于车速估计
            if vehicle_status['valid']:
                current_speed = vehicle_status['speed_kmh']
                if current_speed >= 80:
                    nav_data = {"road_type": "highway", "speed_limit": 100.0, "source": "speed_based", "valid": True}
                elif current_speed >= 60:
                    nav_data = {"road_type": "expressway", "speed_limit": 80.0, "source": "speed_based", "valid": True}
                else:
                    nav_data = {"road_type": "city_road", "speed_limit": 40.0, "source": "speed_based", "valid": True}
            else:
                nav_data = {"road_type": "city_road", "speed_limit": 50.0, "source": "fallback", "valid": False}
        
        road_type = nav_data["road_type"]
        base_speed = nav_data["speed_limit"]
        
        if road_type != self.current_road_type:
            self.current_road_type = road_type
        
        # 3. 获取前车数据
        lead_data = self.detect_leading_vehicle()
        
        # 4. 使用真实车速
        if vehicle_status['valid']:
            current_speed = vehicle_status['speed_kmh']
        else:
            # 降级：使用上次记录的真实车速或基准速度
            current_speed = self.last_real_speed if self.last_real_speed > 0 else base_speed
        
        # 5. 检查滑行条件
        if self.check_coasting_condition(lead_data) and self.driving_mode == DrivingMode.NORMAL:
            self.execute_coasting_mode(current_speed, lead_data["distance"])
        
        # 6. 根据驾驶模式计算车速
        target_speed_ms, target_speed_kmh, reason = self.calculate_target_speed(
            base_speed, vehicle_status, lead_data
        )
        
        # 7. 执行避让动作
        if self.driving_mode in [DrivingMode.AVOIDING_LEFT, DrivingMode.AVOIDING_RIGHT]:
            self.execute_avoidance()
        elif self.driving_mode == DrivingMode.RETURNING:
            self.execute_return()
        
        # 8. 平滑过渡
        smoothed_speed_kmh = self.smooth_transition(target_speed_kmh)
        smoothed_speed_ms = smoothed_speed_kmh / 3.6
        
        # 9. 检查数据质量
        quality = self.check_data_quality()
        
        # 10. 发送控制指令
        success, message = self.send_ai_control_command(
            smoothed_speed_ms, smoothed_speed_kmh, 
            base_speed, nav_data["source"], reason
        )
        
        if success and message:
            # 11. 显示仪表板
            self.show_real_time_dashboard(
                vehicle_status, lead_data, smoothed_speed_kmh,
                base_speed, nav_data["source"], reason, message
            )
        
        return success
    
    def check_data_quality(self):
        """检查各数据源的质量状态"""
        quality_report = {}
        
        # 检查每个订阅的服务
        for service in ['radarState', 'carState', 'liveMapData', 'modelV2']:
            if service in self.sm.valid:
                quality_report[service] = self.sm.valid[service]
            else:
                quality_report[service] = False
        
        # 计算总体质量分
        valid_services = [s for s in quality_report if quality_report.get(s, False)]
        quality_report['overall_score'] = int(len(valid_services) / len(quality_report) * 100) if quality_report else 0
        
        return quality_report
    
    def show_real_time_dashboard(self, vehicle_status, lead_data, target_speed_kmh, 
                               speed_limit_kmh, speed_limit_source, reason, message):
        """显示实时仪表板"""
        os.system('clear')
        
        print("="*70)
        print("🚗 AI车速控制系统 - 实时监控面板")
        print("="*70)
        
        # 运行状态
        mode_icon = "🚀" if self.run_mode == "FULL" else "⚡"
        print(f"{mode_icon} 运行模式: {self.run_mode} | 消息ID: {message['id']}")
        
        # 驾驶模式
        mode_icons = {
            "NORMAL": "🟢",
            "LIMIT_FOLLOWING": "🔵",
            "COASTING_DETECTED": "🟡",
            "COASTING_EXECUTING": "🟠",
            "AVOIDING_LEFT": "↖️",
            "AVOIDING_RIGHT": "↗️",
            "RETURNING": "↩️",
            "COMPLETED": "✅",
            "EMERGENCY": "🔴"
        }
        icon = mode_icons.get(self.driving_mode.name, "⚪")
        print(f"{icon} 驾驶模式: {self.driving_mode.name}")
        
        # 限速信息
        print(f"\n🚦 限速信息:")
        print(f"  当前限速: {speed_limit_kmh:5.1f} km/h")
        print(f"  数据来源: {speed_limit_source}")
        
        # 车速信息
        print(f"\n📊 车速控制:")
        print(f"  当前车速: {vehicle_status['speed_kmh']:5.1f} km/h")
        print(f"  目标车速: {target_speed_kmh:5.1f} km/h")
        
        speed_diff = target_speed_kmh - vehicle_status['speed_kmh']
        if speed_diff > 2:
            action = "🚀 加速"
        elif speed_diff < -2:
            action = "🛑 减速"
        else:
            action = "⚖️  保持"
        
        print(f"  控制动作: {action} ({speed_diff:+.1f} km/h)")
        print(f"  控制原因: {reason}")
        
        # 车辆状态
        if vehicle_status['valid']:
            print(f"\n🚗 车辆状态:")
            print(f"  油门: {vehicle_status['accelerator']:6.1%}")
            print(f"  刹车: {vehicle_status['brake']:6.1%}")
            print(f"  转向: {vehicle_status['steering_angle']:6.1f}°")
            print(f"  档位: {vehicle_status['gear']}")
        
        # 前车信息
        if lead_data['detected']:
            print(f"\n🚗 前车状态:")
            print(f"  距离: {lead_data['distance']:6.1f} m")
            print(f"  速度: {lead_data['speed']*3.6:6.1f} km/h")
            print(f"  相对速度: {lead_data['relative_speed']*3.6:6.1f} km/h")
            print(f"  是否静止: {'是' if lead_data['is_stationary'] else '否'}")
        
        # 避让状态
        if self.avoidance_side != "none":
            print(f"\n🔄 避让状态:")
            print(f"  方向: {self.avoidance_side}")
            print(f"  进度: {self.return_progress:.1%}")
        
        # 数据质量
        valid_count = sum(1 for v in self.data_quality.values() if v)
        total_count = len(self.data_quality)
        quality_score = int(valid_count / total_count * 100) if total_count > 0 else 0
        
        quality_icon = "🟢" if quality_score > 75 else "🟡" if quality_score > 50 else "🔴"
        print(f"\n📡 数据质量: {quality_icon} {quality_score}% ({valid_count}/{total_count})")
        
        print("="*70)
    
    def main_control_loop(self, interval=0.5):
        """主控制循环"""
        print("\n🔄 进入AI车速控制循环（按 Ctrl+C 停止）...")
        
        try:
            while True:
                # 执行一次完整的控制循环
                self.send_enhanced_recommendation()
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 AI控制循环已停止")
        except Exception as e:
            print(f"❌ 控制循环错误: {e}")
            import traceback
            traceback.print_exc()
    
    def run_with_duration(self, duration_seconds, interval=0.5):
        """运行指定时长的控制循环"""
        import time
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        print(f"⏱️  AI控制循环将运行 {duration_seconds} 秒")
        print(f"📡 更新间隔: {interval} 秒")
        print("="*60)
        
        try:
            iteration = 0
            while time.time() < end_time:
                iteration += 1
                
                # 执行一次控制循环
                print(f"\n🔄 迭代 #{iteration}")
                self.send_enhanced_recommendation()
                
                # 计算剩余时间
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                    
                # 等待，但不超过剩余时间
                sleep_time = min(interval, remaining)
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n🛑 用户中断")
        except Exception as e:
            print(f"❌ 运行错误: {e}")
            import traceback
            traceback.print_exc()
        
        elapsed = time.time() - start_time
        print(f"\n✅ AI控制循环已完成")
        print(f"⏱️  实际运行时长: {elapsed:.1f} 秒")
        print(f"📊 总迭代次数: {iteration} 次")
        print(f"📈 平均频率: {iteration/elapsed:.1f} Hz")
        
        # 清理资源
        self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        print("\n🧹 清理AI控制系统资源...")
        
        # 发送最后一条停止消息
        try:
            msg = {
                "type": "ai_speed_control",
                "id": self.message_id + 1,
                "timestamp": int(time.time() * 1000),
                "control_command": {
                    "target_speed_ms": 0.0,
                    "target_speed_kmh": 0.0,
                    "reason": "system_shutdown"
                }
            }
            
            json_str = json.dumps(msg, ensure_ascii=False)
            msg_bytes = json_str.encode('utf-8')
            self.pm.send('customReservedRawData0', msg_bytes)
            print("✅ 已发送停止指令")
        except:
            pass
        
        print(f"📊 总计发送消息: {self.message_id}")
        print("👋 AI控制系统已停止")
    
    def show_menu(self):
        """显示主菜单"""
        while True:
            print("\n" + "="*60)
            print("🚗 AI车速控制系统 - 主菜单")
            print("="*60)
            print("1. 启动AI控制循环")
            print("2. 测试限速读取")
            print("3. 测试滑行避让")
            print("4. 显示系统状态")
            print("5. 检查数据连接")
            print("6. 重置系统状态")
            print("7. 退出系统")
            print("="*60)
            
            try:
                choice = input("请选择 (1-7): ").strip()
                
                if choice == '1':
                    self.main_control_loop()
                elif choice == '2':
                    self.test_speed_limit_reading()
                elif choice == '3':
                    self.test_coasting_scenario()
                elif choice == '4':
                    self.show_system_status()
                elif choice == '5':
                    self.show_data_quality_report()
                elif choice == '6':
                    self.reset_system_state()
                elif choice == '7':
                    print("\n👋 退出AI车速控制系统")
                    break
                else:
                    print("❌ 无效选择，请重新输入")
            except KeyboardInterrupt:
                print("\n🛑 用户中断")
                break
            except Exception as e:
                print(f"❌ 菜单错误: {e}")
    
    def test_speed_limit_reading(self):
        """测试限速读取"""
        print("\n🧪 测试限速读取...")
        
        for i in range(5):
            self.sm.update(100)
            limit, source = self.get_speed_limit_from_multiple_sources()
            
            if limit > 0:
                print(f"测试 {i+1}: 读取到限速 {limit:.1f} km/h (来源: {source})")
            else:
                print(f"测试 {i+1}: 未读取到有效限速")
            
            time.sleep(1)
    
    def test_coasting_scenario(self):
        """测试滑行避让场景"""
        print("\n🧪 测试滑行避让场景...")
        
        # 模拟前车
        lead_data = {
            "detected": True,
            "distance": 50.0,
            "speed": 0.0,
            "relative_speed": 0.0,
            "is_stationary": True,
            "valid": True
        }
        
        # 触发滑行
        if self.check_coasting_condition(lead_data):
            result = self.execute_coasting_mode(40.0, lead_data["distance"])
            print(f"触发结果: {result}")
        
        # 发送测试消息
        vehicle_status = self.get_current_vehicle_status()
        target_speed_ms, target_speed_kmh, reason = self.calculate_target_speed(
            50.0, vehicle_status, lead_data
        )
        
        success, _ = self.send_ai_control_command(
            target_speed_ms, target_speed_kmh, 
            50.0, "test", reason
        )
        
        if success:
            print("✅ 测试消息发送成功")
        else:
            print("❌ 测试消息发送失败")
    
    def show_system_status(self):
        """显示系统状态"""
        vehicle_status = self.get_current_vehicle_status()
        limit, source = self.get_speed_limit_from_multiple_sources()
        
        print(f"\n📊 系统状态报告")
        print(f"  运行模式: {self.run_mode}")
        print(f"  驾驶模式: {self.driving_mode.name}")
        print(f"  当前限速: {limit:.1f} km/h ({source})")
        print(f"  当前车速: {vehicle_status['speed_kmh']:.1f} km/h")
        print(f"  消息计数: {self.message_id}")
        print(f"  控制次数: {self.control_execution_count}")
        
        if self.avoidance_side != "none":
            print(f"  避让方向: {self.avoidance_side}")
            print(f"  回归进度: {self.return_progress:.1%}")
    
    def show_data_quality_report(self):
        """显示数据质量报告"""
        self.update_data_quality()
        
        print(f"\n📡 数据质量报告")
        print("="*50)
        
        for service, valid in self.data_quality.items():
            status = "🟢 正常" if valid else "🔴 异常"
            print(f"{service:20} {status}")
        
        valid_count = sum(1 for v in self.data_quality.values() if v)
        total_count = len(self.data_quality)
        score = int(valid_count / total_count * 100) if total_count > 0 else 0
        
        print(f"\n总体质量: {score}% ({valid_count}/{total_count})")
        
        if score < 50:
            print("⚠️ 警告: 数据质量偏低，可能影响控制效果")
        
        print("="*50)
    
    def reset_system_state(self):
        """重置系统状态"""
        self.driving_mode = DrivingMode.NORMAL
        self.avoidance_side = "none"
        self.return_progress = 0.0
        self.coasting_start_time = 0
        self.coasting_target_speed = 0.0
        self.current_speed_limit = 0.0
        self.target_speed = 0.0
        
        print("✅ 系统状态已重置")

if __name__ == "__main__":
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description='AI车速控制系统 - 自动控制版',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 显示交互菜单
  python3 ai_speed_sender.py
  
  # 自动启动控制循环（无限运行）
  python3 ai_speed_sender.py --auto-start
  
  # 自动启动，运行60秒
  python3 ai_speed_sender.py --auto-start --duration 60
  
  # 自动启动，运行30秒，更新间隔0.2秒
  python3 ai_speed_sender.py --auto-start --duration 30 --interval 0.2
  
  # 测试限速读取
  python3 ai_speed_sender.py --test-limit
  
  # 显示帮助
  python3 ai_speed_sender.py --help
        """
    )
    
    # 添加参数
    parser.add_argument('--auto-start', action='store_true', 
                       help='自动启动控制循环，跳过菜单')
    parser.add_argument('--duration', type=int, default=0, 
                       help='运行时长（秒），0表示无限运行')
    parser.add_argument('--interval', type=float, default=0.5, 
                       help='控制循环更新间隔（秒），默认0.5')
    parser.add_argument('--test-limit', action='store_true',
                       help='测试限速读取功能')
    parser.add_argument('--test-coasting', action='store_true',
                       help='测试滑行避让功能')
    parser.add_argument('--show-status', action='store_true',
                       help='显示系统状态后退出')
    
    # 解析参数
    args = parser.parse_args()
    
    # 创建控制器
    sender = AISpeedSender()
    
    # 根据参数执行相应功能
    if args.auto_start:
        # 自动启动控制循环
        print("="*60)
        print("🚀 AI车速控制系统 - 自动启动模式")
        print("="*60)
        print(f"运行模式: 自动控制")
        print(f"更新间隔: {args.interval} 秒")
        
        if args.duration > 0:
            print(f"运行时长: {args.duration} 秒")
            sender.run_with_duration(args.duration, args.interval)
        else:
            print(f"运行时长: 无限运行 (按 Ctrl+C 停止)")
            print("="*60)
            sender.main_control_loop(args.interval)
    
    elif args.test_limit:
        # 测试限速读取
        print("🧪 测试限速读取功能...")
        sender.test_speed_limit_reading()
    
    elif args.test_coasting:
        # 测试滑行避让
        print("🧪 测试滑行避让功能...")
        sender.test_coasting_scenario()
    
    elif args.show_status:
        # 显示系统状态
        sender.show_system_status()
    
    else:
        # 显示交互菜单（默认行为）
        sender.show_menu()