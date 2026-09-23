#!/usr/bin/env bash
# ============================================================
# install_cpv9.sh — 在 comma 3X (C3) 上把 openpilot 切换成
#                   cpv9-corolla / toyota-19-corolla 分支
#
# 用法（在设备上执行）:
#     ssh comma@<设备IP>
#     bash /data/openpilot/tools/install_cpv9.sh
#
# 原理: 原地改 origin + 强制切分支。
#       这样能【保留】旧版本已编译的 .so，省掉 30 分钟的 scons 重编。
# ============================================================
set -euo pipefail

REPO="https://cheng_kang%40foxmail.com:ck1104@gitee.com/xiansfyt/cpv9-corolla.git"
BRANCH="toyota-19-corolla"
DIR="/data/openpilot"

if [ ! -d "$DIR/.git" ]; then
  echo "!! $DIR 不是 git 仓库，无法原地切换。请改用『全新克隆』方式（见 README 说明）。"
  exit 1
fi

git config --global --add safe.directory "$DIR" 2>/dev/null || true

echo "==> [1/5] 备份当前 remote / 分支（出问题好回滚）"
{
  echo "--- 旧 remote ---"
  git -C "$DIR" remote -v
  echo "--- 旧分支 ---"
  git -C "$DIR" rev-parse --abbrev-ref HEAD
  echo "--- 旧 commit ---"
  git -C "$DIR" rev-parse HEAD
} | tee /data/cpv9_backup.txt

echo
echo "==> [2/5] 把 origin 指向 Gitee"
git -C "$DIR" remote set-url origin "$REPO"

echo
echo "==> [3/5] 拉取代码（depth 1 快速同步）"
git -C "$DIR" fetch --depth 1 --progress origin "$BRANCH"

echo
echo "==> [4/5] 强制切到 $BRANCH（未跟踪的编译产物 .so 会被保留）"
git -C "$DIR" checkout -f -B "$BRANCH" "origin/$BRANCH"
git -C "$DIR" reset --hard "origin/$BRANCH"

echo
echo "==> [5/5] 当前版本"
git -C "$DIR" log --oneline -1

echo
echo "✅ 代码切换完成。"
echo
echo "下一步:"
echo "  1) 重启生效:  sudo reboot"
echo "  2) 重启后若 UI 起不来（编译产物不兼容），执行强制重编:"
echo "       rm -f $DIR/prebuilt && cd $DIR && ./launch_openpilot.sh"
echo "  3) 识别车型自检:  python3 $DIR/tools/check_custin_fw.py"
