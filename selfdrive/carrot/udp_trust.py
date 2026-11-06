#!/usr/bin/env python3
"""车机 UDP 源信任策略。

替换原先"首连即学习"的宽松行为：
- 回环永远允许；
- 已学习或显式白名单中的 IP 允许；
- 配置了显式白名单（CarrotUdpAllowedIps）时进入严格模式，同网段也不再自动学习；
- 未配置白名单时，仅允许同网段主机并学习；
- 本地 IP 未知或非法时拒绝（fail-closed）。
"""
import ipaddress


def parse_allowed(raw):
    """解析 Params 中的逗号分隔 IP 列表（bytes 或 str）。"""
    if raw is None:
        return set()
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    return {part.strip() for part in str(raw).split(",") if part.strip()}


def same_subnet(ip, local_ip, prefix=None):
    if not local_ip:
        return False
    try:
        if prefix is None:
            prefix = 64 if ":" in str(local_ip) else 24
        network = ipaddress.ip_network(f"{local_ip}/{prefix}", strict=False)
        return ipaddress.ip_address(ip) in network
    except ValueError:
        return False


def evaluate(ip, local_ip, learned, allowed, prefix=None):
    """返回 (trusted, should_learn)。"""
    if ip in ("127.0.0.1", "::1"):
        return True, False
    if ip in learned or ip in allowed:
        return True, False
    if allowed:
        # 显式白名单启用后不再自动学习，避免任意同网段主机抢占
        return False, False
    if same_subnet(ip, local_ip, prefix):
        return True, True
    return False, False
