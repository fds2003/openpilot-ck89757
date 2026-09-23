#!/usr/bin/env python3
"""
Comma 3 (C3) 专属 ELF 安装器制作工具
用于将官方 installer_elf 中的 Git 仓库地址和分支名替换为自定义地址。
"""

import sys
import os
import argparse

# 槽位定义（基于官方 0.9.7 installer_elf 二进制特征）
URL_MARKER = b"https://github.com/commaai/openpilot.git?"
URL_CHUNK_LEN = 105

BRANCH_MARKER = b"release3?"
BRANCH_CHUNK_LEN = 73

def make_installer(base_elf_path, git_url, branch, output_path):
    if not os.path.exists(base_elf_path):
        print(f"[错误] 基础 ELF 文件不存在: {base_elf_path}")
        print("请确保同目录下存在官方基线包 installer_elf")
        sys.exit(1)

    with open(base_elf_path, "rb") as f:
        data = bytearray(f.read())

    # 1. 验证 ELF 头
    if data[:4] != b"\x7fELF":
        print("[错误] 基础文件不是合法的 ELF 二进制文件！")
        sys.exit(1)

    # 2. 定位 URL
    idx_url = data.find(URL_MARKER)
    if idx_url == -1:
        # 如果不是原版，尝试通用匹配特征
        pos = data.find(b".git? ")
        if pos != -1:
            idx_url = data.rfind(b"http", 0, pos)
        if idx_url == -1:
            print("[错误] 未能在 ELF 中定位到 Git URL 槽位！")
            sys.exit(1)

    # 3. 定位 Branch
    idx_branch = data.find(BRANCH_MARKER, idx_url)
    if idx_branch == -1:
        idx_branch = data.find(b"\x00", idx_url + URL_CHUNK_LEN) + 1

    print(f"[*] 找到 URL 偏移: {idx_url} (槽位长度: {URL_CHUNK_LEN})")
    print(f"[*] 找到 Branch 偏移: {idx_branch} (槽位长度: {BRANCH_CHUNK_LEN})")

    # 4. 构造新数据块
    url_target = (git_url.strip() + "?").encode("utf-8")
    branch_target = (branch.strip() + "?").encode("utf-8")

    if len(url_target) > URL_CHUNK_LEN:
        print(f"[错误] Git URL 过长: {len(url_target)} 字节 (最大允许 {URL_CHUNK_LEN - 1} 字符)")
        sys.exit(1)

    if len(branch_target) > BRANCH_CHUNK_LEN:
        print(f"[错误] 分支名称过长: {len(branch_target)} 字节 (最大允许 {BRANCH_CHUNK_LEN - 1} 字符)")
        sys.exit(1)

    url_chunk = url_target + b" " * (URL_CHUNK_LEN - len(url_target))
    branch_chunk = branch_target + b" " * (BRANCH_CHUNK_LEN - len(branch_target))

    # 5. 替换并校验
    data[idx_url:idx_url + URL_CHUNK_LEN] = url_chunk
    data[idx_branch:idx_branch + BRANCH_CHUNK_LEN] = branch_chunk

    with open(output_path, "wb") as f:
        f.write(data)

    print(f"[√] 成功生成新安装器: {output_path}")
    print(f"    - 目标 URL : {git_url}")
    print(f"    - 目标分支 : {branch}")
    print(f"    - 文件大小 : {len(data)} 字节")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="制作 Comma 3 自定义安装器 ELF 文件")
    parser.add_argument("--base", default="installer_elf", help="底包 ELF 文件路径 (默认: installer_elf)")
    parser.add_argument("--url", required=True, help="自定义 Git 仓库完整地址 (如 http://git.utoohotel.com/ck89757/openpilot.git)")
    parser.add_argument("--branch", required=True, help="目标分支名 (如 cpv9-dev)")
    parser.add_argument("--output", "-o", default="installer", help="输出文件名 (默认: installer)")

    args = parser.parse_args()
    make_installer(args.base, args.url, args.branch, args.output)
