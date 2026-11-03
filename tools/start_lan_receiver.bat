@echo off
chcp 65001 >nul
title Comma 3 局域网电脑文件接收服务
cd /d "%~dp0"

echo 正在检查 Python 与依赖环境...
python -c "import pyftpdlib" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在自动安装 pyftpdlib 依赖库...
    pip install pyftpdlib
)

python lan_pc_receiver.py
pause
