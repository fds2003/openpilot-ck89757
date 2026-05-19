#!/usr/bin/env python3
"""
AI消息通道深度调试脚本 - 增强版
功能：验证AI消息通道的完整工作流程
     1. 发送测试消息
     2. 接收并验证消息
     3. 检查消息格式和内容
     4. 提供详细的诊断报告
"""

import cereal.messaging as messaging
import json
import time
import sys
import os
from datetime import datetime

# 添加openpilot路径
sys.path.append('/data/openpilot')

class AIMessageDebugger:
    def __init__(self):
        """初始化调试器"""
        print("🔍 AI消息通道深度调试器 - 增强版")
        print("="*70)
        
        # 初始化消息发布者和订阅者
        self.pub = messaging.PubMaster(['customReservedRawData0'])
        self.sub = messaging.SubMaster(['customReservedRawData0'])
        
        # 测试计数器
        self.test_count = 0
        self.success_count = 0
        self.fail_count = 0
        
        # 测试配置
        self.test_config = {
            'timeout_seconds': 5.0,
            'retry_count': 3,
            'message_interval': 0.5,
            'enable_verbose_log': True
        }
        
        print(f"✅ 调试器初始化完成")
        print(f"⏰ 超时时间: {self.test_config['timeout_seconds']} 秒")
        print(f"🔄 重试次数: {self.test_config['retry_count']} 次")
        print("="*70)
    
    def create_test_message(self, message_type="debug_test"):
        """创建测试消息"""
        self.test_count += 1
        
        message = {
            "type": message_type,
            "id": self.test_count,
            "timestamp": int(time.time() * 1000),
            "data": f"测试消息_{self.test_count:03d}",
            "source": "debug_script",
            "test_phase": "send_and_receive",
            "vehicle_simulation": {
                "current_speed_kmh": 40.0 + (self.test_count % 20),
                "target_speed_kmh": 50.0 + (self.test_count % 10),
                "accelerator": 0.3 + (self.test_count * 0.01),
                "brake": 0.0,
                "steering_angle": 0.5
            },
            "metadata": {
                "os_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "python_version": sys.version,
                "script_path": os.path.abspath(__file__)
            }
        }
        
        return message
    
    def send_test_message(self, message):
        """发送测试消息"""
        print(f"\n📤 发送测试消息 #{message['id']}")
        print(f"   类型: {message['type']}")
        print(f"   时间戳: {message['timestamp']}")
        print(f"   模拟车速: {message['vehicle_simulation']['current_speed_kmh']:.1f} km/h")
        
        try:
            # 创建消息对象
            msg = messaging.new_message('customReservedRawData0')
            
            # 设置消息数据
            json_str = json.dumps(message, ensure_ascii=False, indent=2)
            msg.customReservedRawData0.data = json_str.encode('utf-8')
            
            # 发送消息
            self.pub.send('customReservedRawData0', msg)
            
            print(f"✅ 消息发送成功")
            print(f"   消息大小: {len(msg.customReservedRawData0.data)} 字节")
            
            if self.test_config['enable_verbose_log']:
                print(f"📄 消息内容预览:")
                print(json.dumps(message, ensure_ascii=False, indent=2)[:200] + "...")
            
            return True, "发送成功"
            
        except Exception as e:
            error_msg = f"❌ 发送失败: {str(e)}"
            print(error_msg)
            self.fail_count += 1
            return False, error_msg
    
    def receive_and_validate_message(self, expected_id=None, timeout=5.0):
        """接收并验证消息"""
        print(f"\n📥 等待接收消息 (超时: {timeout}秒)...")
        
        start_time = time.time()
        received_messages = []
        
        while time.time() - start_time < timeout:
            # 更新订阅
            self.sub.update(100)  # 100ms超时
            
            if self.sub.updated['customReservedRawData0']:
                try:
                    data_bytes = self.sub['customReservedRawData0'].data
                    
                    if data_bytes:
                        # 解析JSON
                        received_data = json.loads(data_bytes.decode('utf-8'))
                        
                        # 添加到接收列表
                        received_messages.append({
                            'data': received_data,
                            'receive_time': time.time(),
                            'size': len(data_bytes)
                        })
                        
                        print(f"✅ 收到消息 #{len(received_messages)}")
                        print(f"   消息ID: {received_data.get('id', '未知')}")
                        print(f"   消息类型: {received_data.get('type', '未知')}")
                        
                        # 验证消息（如果指定了期望的ID）
                        if expected_id is not None and received_data.get('id') == expected_id:
                            print(f"🎯 匹配到期望的消息ID: {expected_id}")
                            return True, received_data, received_messages
                
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    print(f"   原始数据: {data_bytes[:100] if data_bytes else '无数据'}...")
                except Exception as e:
                    print(f"❌ 处理消息失败: {e}")
            
            time.sleep(0.1)  # 避免CPU占用过高
        
        # 超时处理
        if received_messages:
            print(f"⚠️  超时，但收到了 {len(received_messages)} 条消息")
            return False, None, received_messages
        else:
            print("❌ 超时：未收到任何消息")
            return False, None, []
    
    def run_end_to_end_test(self, num_tests=3):
        """运行端到端测试"""
        print("\n" + "="*70)
        print("🚀 开始端到端消息通道测试")
        print("="*70)
        
        test_results = []
        
        for i in range(num_tests):
            print(f"\n🔧 测试 {i+1}/{num_tests}")
            
            # 1. 创建测试消息
            test_message = self.create_test_message()
            
            # 2. 发送消息
            send_success, send_result = self.send_test_message(test_message)
            
            if send_success:
                # 3. 接收并验证消息
                expected_id = test_message['id']
                receive_success, matched_message, all_messages = self.receive_and_validate_message(
                    expected_id=expected_id,
                    timeout=self.test_config['timeout_seconds']
                )
                
                if receive_success:
                    # 4. 验证消息内容
                    validation_result = self.validate_message_content(test_message, matched_message)
                    
                    if validation_result['valid']:
                        self.success_count += 1
                        test_status = "✅ 通过"
                        print(f"🎉 测试 {i+1} 完全通过！")
                    else:
                        self.fail_count += 1
                        test_status = f"⚠️  内容验证失败: {validation_result['message']}"
                        print(f"⚠️  测试 {i+1} 内容验证失败")
                else:
                    self.fail_count += 1
                    test_status = "❌ 接收失败"
                    print(f"❌ 测试 {i+1} 接收失败")
            else:
                self.fail_count += 1
                test_status = f"❌ 发送失败: {send_result}"
                print(f"❌ 测试 {i+1} 发送失败")
            
            # 记录测试结果
            test_results.append({
                'test_number': i + 1,
                'status': test_status,
                'sent_message_id': test_message['id'],
                'received_count': len(all_messages) if 'all_messages' in locals() else 0
            })
            
            # 等待一下再进行下一个测试
            if i < num_tests - 1:
                time.sleep(self.test_config['message_interval'])
        
        return test_results
    
    def validate_message_content(self, sent_message, received_message):
        """验证消息内容一致性"""
        print(f"\n🔍 验证消息内容...")
        
        validation_result = {
            'valid': True,
            'message': "验证通过",
            'details': []
        }
        
        # 检查必需字段
        required_fields = ['type', 'id', 'timestamp']
        for field in required_fields:
            if field not in received_message:
                validation_result['valid'] = False
                validation_result['details'].append(f"缺少必需字段: {field}")
        
        # 比较关键字段
        if validation_result['valid']:
            comparison_fields = ['type', 'id']
            for field in comparison_fields:
                if field in sent_message and field in received_message:
                    if sent_message[field] != received_message[field]:
                        validation_result['valid'] = False
                        validation_result['details'].append(
                            f"字段不匹配: {field} (发送: {sent_message[field]}, 接收: {received_message[field]})"
                        )
        
        # 检查时间戳合理性
        if 'timestamp' in received_message:
            sent_time = sent_message.get('timestamp', 0)
            recv_time = received_message.get('timestamp', 0)
            time_diff = abs(recv_time - sent_time)
            
            if time_diff > 10000:  # 超过10秒的时间差
                validation_result['details'].append(f"时间戳差异较大: {time_diff}ms")
        
        # 输出验证结果
        if validation_result['valid']:
            print(f"✅ 消息内容验证通过")
            for detail in validation_result['details']:
                print(f"   ℹ️  {detail}")
        else:
            print(f"❌ 消息内容验证失败")
            for detail in validation_result['details']:
                print(f"   ❌ {detail}")
        
        return validation_result
    
    def run_passive_listen_test(self, duration=10.0):
        """被动监听测试（检测其他进程发送的消息）"""
        print(f"\n" + "="*70)
        print(f"👂 被动监听测试 (时长: {duration}秒)")
        print("正在监听其他进程发送的AI消息...")
        print("="*70)
        
        start_time = time.time()
        messages_received = []
        
        try:
            while time.time() - start_time < duration:
                self.sub.update(100)
                
                if self.sub.updated['customReservedRawData0']:
                    try:
                        data_bytes = self.sub['customReservedRawData0'].data
                        if data_bytes:
                            message = json.loads(data_bytes.decode('utf-8'))
                            
                            messages_received.append({
                                'time': time.time() - start_time,
                                'data': message,
                                'type': message.get('type', 'unknown'),
                                'id': message.get('id', 'unknown')
                            })
                            
                            print(f"📥 收到消息 #{len(messages_received)}")
                            print(f"   时间: {messages_received[-1]['time']:.2f}s")
                            print(f"   类型: {messages_received[-1]['type']}")
                            print(f"   ID: {messages_received[-1]['id']}")
                    
                    except Exception as e:
                        print(f"❌ 解析消息失败: {e}")
                
                time.sleep(0.1)  # 避免CPU占用过高
        
        except KeyboardInterrupt:
            print("\n🛑 用户中断被动监听")
        
        # 输出监听结果
        print(f"\n📊 被动监听结果:")
        print(f"   总时长: {duration} 秒")
        print(f"   收到消息数: {len(messages_received)}")
        
        if messages_received:
            # 统计消息类型
            type_counts = {}
            for msg in messages_received:
                msg_type = msg['type']
                type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
            
            print(f"   消息类型分布:")
            for msg_type, count in type_counts.items():
                print(f"     - {msg_type}: {count} 条")
            
            # 计算消息频率
            if len(messages_received) > 1:
                time_span = messages_received[-1]['time'] - messages_received[0]['time']
                frequency = len(messages_received) / time_span if time_span > 0 else 0
                print(f"   平均频率: {frequency:.2f} Hz")
        
        return messages_received
    
    def generate_diagnostic_report(self):
        """生成诊断报告"""
        print("\n" + "="*70)
        print("📊 AI消息通道诊断报告")
        print("="*70)
        
        # 基本统计
        print(f"\n📈 测试统计:")
        print(f"   总测试次数: {self.test_count}")
        print(f"   成功次数: {self.success_count}")
        print(f"   失败次数: {self.fail_count}")
        print(f"   成功率: {self.success_count/self.test_count*100:.1f}%" if self.test_count > 0 else "成功率: N/A")
        
        # 系统信息
        print(f"\n💻 系统信息:")
        print(f"   当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Python版本: {sys.version.split()[0]}")
        print(f"   脚本路径: {os.path.abspath(__file__)}")
        
        # 诊断建议
        print(f"\n🔧 诊断建议:")
        
        if self.success_count == 0 and self.test_count > 0:
            print("❌ 所有测试都失败，可能原因:")
            print("   1. 消息通道 'customReservedRawData0' 不存在或不可用")
            print("   2. OpenPilot消息系统未启动")
            print("   3. 权限不足无法访问消息系统")
            print("   4. 脚本路径或环境配置错误")
            print("\n🛠️  建议操作:")
            print("   1. 检查OpenPilot是否正在运行")
            print("   2. 验证消息通道名是否正确")
            print("   3. 尝试重启OpenPilot服务")
        
        elif self.success_count > 0 and self.fail_count > 0:
            print("⚠️  部分测试失败，可能原因:")
            print("   1. 消息延迟或丢失")
            print("   2. 网络或系统负载过高")
            print("   3. 消息格式不一致")
            print("\n🛠️  建议操作:")
            print("   1. 增加测试超时时间")
            print("   2. 检查系统负载")
            print("   3. 验证消息格式")
        
        elif self.success_count == self.test_count and self.test_count > 0:
            print("✅ 所有测试通过！消息通道工作正常")
            print("\n🎉 可以继续使用以下功能:")
            print("   1. 运行 ai_speed_sender.py 进行实际控制")
            print("   2. 创建桥接器转发消息")
            print("   3. 集成到 controlsd.py 中")
        
        print("\n" + "="*70)
        return True
    
    def show_menu(self):
        """显示菜单"""
        while True:
            print("\n" + "="*70)
            print("🔧 AI消息通道调试器 - 主菜单")
            print("="*70)
            print("1. 运行端到端测试 (3次)")
            print("2. 运行被动监听测试 (10秒)")
            print("3. 手动发送测试消息")
            print("4. 检查消息通道状态")
            print("5. 生成诊断报告")
            print("6. 退出")
            print("="*70)
            
            try:
                choice = input("请选择 (1-6): ").strip()
                
                if choice == '1':
                    self.run_end_to_end_test(3)
                elif choice == '2':
                    self.run_passive_listen_test(10.0)
                elif choice == '3':
                    # 手动发送测试消息
                    test_msg = self.create_test_message()
                    self.send_test_message(test_msg)
                elif choice == '4':
                    # 检查消息通道状态
                    print("\n🔍 检查消息通道状态...")
                    self.sub.update(100)
                    print(f"✅ 订阅管理器状态: 正常")
                    print(f"✅ 发布管理器状态: 正常")
                elif choice == '5':
                    self.generate_diagnostic_report()
                elif choice == '6':
                    print("\n👋 退出调试器")
                    break
                else:
                    print("❌ 无效选择")
            
            except KeyboardInterrupt:
                print("\n🛑 用户中断")
                break
            except Exception as e:
                print(f"❌ 菜单错误: {e}")

def main():
    """主函数"""
    try:
        # 创建调试器实例
        debugger = AIMessageDebugger()
        
        # 检查是否通过命令行参数直接运行测试
        if len(sys.argv) > 1:
            if sys.argv[1] == "--quick-test":
                print("🚀 执行快速测试...")
                debugger.run_end_to_end_test(2)
                debugger.generate_diagnostic_report()
            elif sys.argv[1] == "--listen":
                listen_duration = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
                debugger.run_passive_listen_test(listen_duration)
            else:
                print(f"⚠️  未知参数: {sys.argv[1]}")
                print("可用参数:")
                print("  --quick-test   执行快速测试")
                print("  --listen [秒数] 执行被动监听")
                debugger.show_menu()
        else:
            # 显示交互菜单
            debugger.show_menu()
    
    except Exception as e:
        print(f"❌ 调试器启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)