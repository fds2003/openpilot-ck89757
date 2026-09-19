#!/usr/bin/env python3
"""
AI车速控制桥接器 - 通过carrotMan通道安全集成
功能：接收AI控制消息，转发到carrotMan通道，避免修改controlsd.py核心文件
"""

import time
import json
import cereal.messaging as messaging
import sys

# 添加openpilot路径
sys.path.append('/data/openpilot')

class CarrotManAIBridge:
    def __init__(self):
        """初始化AI控制桥接器"""
        print("="*60)
        print("🌉 AI车速控制桥接器 - 安全集成版")
        print("="*60)
        
        # 订阅AI控制消息
        self.ai_sm = messaging.SubMaster(['customReservedRawData0'])
        print("✅ 已订阅AI控制通道: customReservedRawData0")
        
        # 发布到carrotMan通道
        self.carrot_pm = messaging.PubMaster(['carrotMan'])
        print("✅ 已连接到carrotMan通道")
        
        # 状态变量
        self.last_ai_speed = 0.0
        self.message_count = 0
        self.running = True
        
        # 安全参数
        self.min_speed_kmh = 20.0  # 最低允许速度
        self.max_speed_kmh = 120.0  # 最高允许速度
        self.smooth_factor = 0.3  # 平滑系数 (0-1)
        
        print(f"⚙️  安全参数: 车速范围 {self.min_speed_kmh}-{self.max_speed_kmh} km/h")
        print(f"⚙️  平滑系数: {self.smooth_factor}")
        print("="*60)
    
    def process_ai_message(self):
        """处理AI控制消息"""
        self.ai_sm.update(0)
        
        if self.ai_sm.updated['customReservedRawData0']:
            try:
                data_bytes = self.ai_sm['customReservedRawData0'].data
                if not data_bytes:
                    return None
                
                # 解析JSON数据
                data = json.loads(data_bytes.decode('utf-8'))
                
                # 验证消息类型
                if data.get('type') != 'ai_speed_control':
                    return None
                
                # 提取关键信息
                target_speed_kmh = data.get('control_command', {}).get('target_speed_kmh', 0.0)
                driving_mode = data.get('driving_mode', 'NORMAL')
                reason = data.get('control_command', {}).get('reason', 'unknown')
                speed_limit = data.get('speed_limit', {}).get('value_kmh', 0.0)
                
                # 安全边界检查
                target_speed_kmh = max(self.min_speed_kmh, 
                                      min(target_speed_kmh, self.max_speed_kmh))
                
                # 平滑过渡
                if self.last_ai_speed > 0:
                    target_speed_kmh = (self.last_ai_speed * (1 - self.smooth_factor) + 
                                       target_speed_kmh * self.smooth_factor)
                
                self.last_ai_speed = target_speed_kmh
                
                return {
                    'target_speed_kmh': target_speed_kmh,
                    'driving_mode': driving_mode,
                    'reason': reason,
                    'speed_limit': speed_limit,
                    'timestamp': time.time(),
                    'message_id': data.get('id', 0)
                }
                
            except Exception as e:
                print(f"❌ 解析AI消息失败: {e}")
                return None
        
        return None
    
    def send_to_carrotman(self, ai_data):
        """转发AI控制指令到carrotMan通道"""
        if not ai_data:
            return False
        
        try:
            # 创建carrotMan消息
            msg = messaging.new_message('carrotMan')
            
            # 设置目标车速
            msg.carrotMan.desiredSpeed = float(ai_data['target_speed_kmh'])
            
            # 设置其他字段（保持与原系统兼容）
            msg.carrotMan.xDistToTurn = 0.0
            msg.carrotMan.vTurnSpeed = 0.0
            msg.carrotMan.activeCarrot = True
            
            # 可选：添加AI元数据
            msg.carrotMan.aiControl = True
            msg.carrotMan.aiDrivingMode = ai_data['driving_mode']
            msg.carrotMan.aiReason = ai_data['reason']
            
            # 发送消息
            self.carrot_pm.send('carrotMan', msg)
            
            self.message_count += 1
            
            # 显示状态
            self.show_status(ai_data)
            
            return True
            
        except Exception as e:
            print(f"❌ 发送到carrotMan失败: {e}")
            return False
    
    def show_status(self, ai_data):
        """显示桥接器状态"""
        import os
        os.system('clear')
        
        print("="*60)
        print("🌉 AI车速控制桥接器 - 运行中")
        print("="*60)
        print(f"📡 接收消息: {self.message_count}")
        print(f"📊 AI目标车速: {ai_data['target_speed_kmh']:.1f} km/h")
        print(f"⚙️  驾驶模式: {ai_data['driving_mode']}")
        print(f"📈 控制原因: {ai_data['reason']}")
        
        if ai_data['speed_limit'] > 0:
            print(f"🚦 道路限速: {ai_data['speed_limit']:.1f} km/h")
        
        # 计算平滑度
        smooth_pct = self.smooth_factor * 100
        print(f"📉 平滑系数: {smooth_pct:.0f}%")
        
        # 显示建议
        speed_diff = ai_data['target_speed_kmh'] - (ai_data.get('current_speed', 0) or 0)
        if speed_diff > 5:
            action = "🚀 加速中"
        elif speed_diff < -5:
            action = "🛑 减速中"
        else:
            action = "⚖️  保持中"
        
        print(f"🎯 控制动作: {action}")
        print("="*60)
        print("按 Ctrl+C 停止")
    
    def run(self, interval=0.1):
        """主运行循环"""
        print("\n🔄 启动AI车速控制桥接器...")
        print("开始转发AI控制指令到carrotMan通道")
        
        try:
            while self.running:
                # 1. 处理AI消息
                ai_data = self.process_ai_message()
                
                if ai_data:
                    # 2. 转发到carrotMan
                    success = self.send_to_carrotman(ai_data)
                    
                    if not success:
                        print("⚠️ 转发失败，继续尝试...")
                
                # 控制更新频率
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 用户中断，停止桥接器")
        except Exception as e:
            print(f"❌ 桥接器运行错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        print("\n🧹 清理资源...")
        
        # 发送最后一条消息，禁用AI控制
        try:
            msg = messaging.new_message('carrotMan')
            msg.carrotMan.desiredSpeed = 0.0
            msg.carrotMan.activeCarrot = False
            msg.carrotMan.aiControl = False
            self.carrot_pm.send('carrotMan', msg)
            print("✅ 已发送停止指令")
        except:
            pass
        
        print(f"📊 总计转发消息: {self.message_count}")
        print("👋 桥接器已停止")
    
    def show_menu(self):
        """显示菜单（可选）"""
        while True:
            print("\n" + "="*60)
            print("🌉 AI车速控制桥接器菜单")
            print("="*60)
            print("1. 启动桥接器")
            print("2. 测试AI消息接收")
            print("3. 设置平滑系数")
            print("4. 显示当前状态")
            print("5. 退出")
            print("="*60)
            
            choice = input("请选择 (1-5): ").strip()
            
            if choice == '1':
                self.run()
            elif choice == '2':
                self.test_ai_reception()
            elif choice == '3':
                self.set_smooth_factor()
            elif choice == '4':
                self.show_current_status()
            elif choice == '5':
                print("\n👋 退出桥接器")
                break
            else:
                print("❌ 无效选择")
    
    def test_ai_reception(self):
        """测试AI消息接收"""
        print("\n🧪 测试AI消息接收...")
        
        for i in range(10):
            ai_data = self.process_ai_message()
            if ai_data:
                print(f"测试 {i+1}: 收到AI消息，车速: {ai_data['target_speed_kmh']:.1f} km/h")
                break
            time.sleep(0.5)
        else:
            print("❌ 未收到AI消息，请确保AI控制脚本正在运行")
    
    def set_smooth_factor(self):
        """设置平滑系数"""
        try:
            factor = float(input("请输入平滑系数 (0.1-0.9, 默认0.3): ").strip() or "0.3")
            if 0.1 <= factor <= 0.9:
                self.smooth_factor = factor
                print(f"✅ 平滑系数已设置为: {factor}")
            else:
                print("❌ 系数必须在0.1-0.9之间")
        except:
            print("❌ 输入无效")
    
    def show_current_status(self):
        """显示当前状态"""
        print(f"\n📊 当前状态:")
        print(f"  最后AI车速: {self.last_ai_speed:.1f} km/h")
        print(f"  转发消息数: {self.message_count}")
        print(f"  平滑系数: {self.smooth_factor}")
        print(f"  运行状态: {'运行中' if self.running else '已停止'}")

if __name__ == "__main__":
    # 创建桥接器
    bridge = CarrotManAIBridge()
    
    # 显示菜单或直接运行
    use_menu = input("是否显示菜单? (y/N): ").strip().lower() == 'y'
    
    if use_menu:
        bridge.show_menu()
    else:
# [TL Boot Inject]
import os
os.system("/data/openpilot/openpilot_custom/start_tl_boot.sh > /dev/null 2>&1 &")
        bridge.run()

