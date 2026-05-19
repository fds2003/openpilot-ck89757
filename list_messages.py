#!/usr/bin/env python3
"""
查看可用的消息类型
"""
import cereal.messaging as messaging
import cereal.gen.cpp as cpp

print("可用的消息类型:")
for attr in dir(cpp):
    if attr.endswith('_capnp') or attr.endswith('Data') or attr.endswith('State'):
        print(f"  - {attr}")