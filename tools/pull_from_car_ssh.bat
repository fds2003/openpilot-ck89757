@echo off
chcp 65001 >nul
title 从 Comma 3 一键拉取日志与视频 (SSH/SCP)
cd /d "%~dp0"

set CAR_IP=192.168.3.128
set LOCAL_BACKUP_DIR=..\received_from_car\ssh_pull_%date:~0,4%%date:~5,2%%date:~8,2%

echo =======================================================
echo 🚗【现代库斯途 Comma 3】局域网电脑无线文件同步 (SSH)
echo =======================================================
echo 正在连接车机: %CAR_IP% ...
if not exist "%LOCAL_BACKUP_DIR%" mkdir "%LOCAL_BACKUP_DIR%"

echo 1. 正在同步系统日志与崩溃转储 (/data/media/carrot_logs)...
scp -r -o ConnectTimeout=5 comma@%CAR_IP%:/data/media/carrot_logs "%LOCAL_BACKUP_DIR%\" 2>nul
if %errorlevel% equ 0 (
    echo    - 日志同步成功！
) else (
    echo    - 提示: 未检测到新日志或车机离线。
)

echo 2. 正在同步 tmux 控制日志 (/data/media/tmux.log)...
scp -o ConnectTimeout=5 comma@%CAR_IP%:/data/media/tmux.log "%LOCAL_BACKUP_DIR%\" 2>nul

echo =======================================================
echo ✅ 同步任务执行完毕！
echo 📂 文件已保存至: %LOCAL_BACKUP_DIR%
echo =======================================================
pause
