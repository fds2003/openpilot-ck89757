#!/usr/bin/env python3
"""
AI 控制车速模块 - 消息注入方案
不修改 controlsd.py，通过消息总线注入控制指令
"""

import time
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
import json
import numpy as np

class AIControlModule:
    def __init__(self):
        # 消息发布/订阅
        self.pm = messaging.PubMaster(['carControl'])
        self.sm = messaging.SubMaster([
            'carState',          # 车辆状态
            'radarState',        # 雷达数据
            'longitudinalPlan',  # 纵向规划
            'modelV2',          # 模型输出
            'aiSpeedData'       # AI 车速建议（自定义）
        ])
        
        # 参数管理
        self.params = Params()
        self.ai_enabled = True
        self.ai_confidence_threshold = 0.7
        self.max_ai_override = 5.0  # AI 最大速度调整 (m/s)
        
        # 状态变量
        self.last_ai_update = 0
        self.ai_suggested_speed = 0
        self.ai_reason = ""
        
        # 控制滤波器
        self.speed_history = []
        self.history_size = 10
        
        print("✅ AI 控制模块初始化完成")
    
    def process_ai_suggestion(self, ai_data):
        """处理 AI 车速建议"""
        if not ai_data or not hasattr(ai_data, 'speed'):
            return None
        
        # 提取 AI 建议
        ai_speed = ai_data.speed
        confidence = getattr(ai_data, 'confidence', 0.0)
        reason = getattr(ai_data, 'reason', '')
        
        # 置信度检查
        if confidence < self.ai_confidence_threshold:
            print(f"⚠️ AI 置信度不足: {confidence:.2f} < {self.ai_confidence_threshold}")
            return None
        
        # 平滑滤波
        self.speed_history.append(ai_speed)
        if len(self.speed_history) > self.history_size:
            self.speed_history.pop(0)
        
        smoothed_speed = np.mean(self.speed_history) if self.speed_history else ai_speed
        
        self.ai_suggested_speed = smoothed_speed
        self.ai_reason = reason
        self.last_ai_update = time.time()
        
        print(f"🧠 AI 建议: {ai_speed:.1f}m/s -> 平滑: {smoothed_speed:.1f}m/s ({reason})")
        return smoothed_speed
    
    def calculate_target_speed(self, current_speed, cruise_speed, ai_speed):
        """计算目标速度（结合当前速度、巡航速度和 AI 建议）"""
        if not self.ai_enabled or time.time() - self.last_ai_update > 3.0:
            # AI 建议过期，使用巡航速度
            return cruise_speed
        
        # 安全边界检查
        safe_ai_speed = np.clip(
            ai_speed,
            current_speed - self.max_ai_override,
            current_speed + self.max_ai_override
        )
        
        # 混合策略：70% AI 建议 + 30% 巡航速度
        target_speed = 0.7 * safe_ai_speed + 0.3 * cruise_speed
        
        # 确保不低于最小速度
        target_speed = max(target_speed, 5.0)  # 最低 5 m/s (18 km/h)
        
        return target_speed
    
    def create_control_message(self, target_speed, car_state):
        """创建控制消息"""
        msg = messaging.new_message('carControl')
        
        # 车辆控制
        cc = msg.carControl
        cc.enabled = True
        
        # 纵向控制
        cc.longActive = True
        
        # 设置期望速度
        cc.cruiseControl.speed = target_speed
        
        # 加速度控制
        current_speed = car_state.vEgo
        speed_diff = target_speed - current_speed
        
        # 根据速度差计算加速度
        if speed_diff > 2.0:
            cc.actuators.accel = 0.5  # 中等加速
        elif speed_diff > 0.5:
            cc.actuators.accel = 0.2  # 轻度加速
        elif speed_diff < -2.0:
            cc.actuators.accel = -0.5  # 中等减速
        elif speed_diff < -0.5:
            cc.actuators.accel = -0.2  # 轻度减速
        else:
            cc.actuators.accel = 0.0  # 保持
        
        # 安全限制
        cc.actuators.accel = np.clip(cc.actuators.accel, -1.0, 1.0)
        
        return msg
    
    def run_once(self):
        """单次运行循环"""
        self.sm.update()
        
        if not self.sm.updated['aiSpeedData']:
            return
        
        # 获取当前状态
        car_state = self.sm['carState']
        radar_state = self.sm['radarState']
        
        # 处理 AI 建议
        ai_data = self.sm['aiSpeedData']
        ai_speed = self.process_ai_suggestion(ai_data)
        
        if ai_speed is None:
            return
        
        # 计算目标速度
        current_speed = car_state.vEgo
        cruise_speed = getattr(car_state, 'vCruise', current_speed + 5.0)
        
        target_speed = self.calculate_target_speed(
            current_speed, 
            cruise_speed, 
            ai_speed
        )
        
        # 创建并发送控制消息
        control_msg = self.create_control_message(target_speed, car_state)
        self.pm.send('carControl', control_msg)
        
        # 日志输出
        print(f"🎯 控制指令: {current_speed:.1f} -> {target_speed:.1f} m/s "
              f"(AI: {ai_speed:.1f}, 巡航: {cruise_speed:.1f})")
    
    def run(self):
        """主运行循环"""
        rk = Ratekeeper(20, print_delay_threshold=None)  # 20Hz
        
        while True:
            self.run_once()
            rk.keep_time()

def main():
    module = AIControlModule()
    module.run()

if __name__ == "__main__":
    main()