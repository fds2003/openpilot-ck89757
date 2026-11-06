#!/usr/bin/env bash
# C3 一键更新：拉取 cp-custo-amap、修权限、装依赖、校验模型、重启并自检
#
# 用法：
#   ./selfdrive/carrot/scripts/c3_update.sh              # 更新 + 装依赖 + 重启 manager
#   ./selfdrive/carrot/scripts/c3_update.sh --reboot     # 更新后整机重启
#   ./selfdrive/carrot/scripts/c3_update.sh --no-restart  # 只更新，不重启
#   ./selfdrive/carrot/scripts/c3_update.sh --check       # 只做健康检查，不改代码
#   ./selfdrive/carrot/scripts/c3_update.sh --force       # 丢弃本地改动后更新
#   ./selfdrive/carrot/scripts/c3_update.sh --clean       # 额外 git clean -xdff（会删未跟踪文件）
#
# 退出码：0 成功；1 前置/校验失败；2 参数错误

set -euo pipefail

REPO_DIR="${REPO_DIR:-/data/openpilot}"
DEFAULT_BRANCH="cp-custo-amap"
BRANCH="$DEFAULT_BRANCH"
REMOTE="origin"
MODE="restart"        # restart | reboot | none
FORCE=0
CLEAN=0
INSTALL_DEPS=1
CHECK_ONLY=0
MODEL_PATH="selfdrive/carrot/models/lane.onnx"
MODEL_SHA="d3761c185daf33897ff3ff5edf28115c5dc829c06c538033accb616d6c67528c"

log()  { printf '[%-5s] %s\n' "$1" "$2"; }
ok()   { log "OK"   "$1"; }
warn() { log "WARN" "$1"; }
fail() { log "FAIL" "$1"; exit 1; }

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)      BRANCH="${2:?--branch 需要参数}"; shift 2 ;;
    --reboot)      MODE="reboot"; shift ;;
    --no-restart)  MODE="none"; shift ;;
    --no-deps)     INSTALL_DEPS=0; shift ;;
    --force)       FORCE=1; shift ;;
    --clean)       CLEAN=1; shift ;;
    --check)       CHECK_ONLY=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---------- 0. 前置 ----------
cd "$REPO_DIR" 2>/dev/null || fail "仓库目录不存在: $REPO_DIR"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "不是 git 仓库: $REPO_DIR"

if [[ $CHECK_ONLY -eq 0 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    if [[ $FORCE -eq 1 ]]; then
      warn "丢弃本地改动（--force）"
      git reset --hard HEAD
    else
      fail "工作区有未提交改动；先提交，或加 --force"
    fi
  fi

  # ---------- 1. 拉取 ----------
  log "INFO" "fetch $REMOTE/$BRANCH"
  git fetch "$REMOTE" "$BRANCH" || fail "git fetch 失败（检查网络/仓库地址）"
  git checkout --force -B "$BRANCH" FETCH_HEAD || fail "checkout 失败"
  git reset --hard FETCH_HEAD || fail "reset 失败"
  ok "代码已更新到 $(git log --oneline -1)"

  if [[ $CLEAN -eq 1 ]]; then
    warn "执行 git clean -xdff（会删除未跟踪文件）"
    git clean -xdff
  fi
fi

# ---------- 2. 权限 ----------
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R comma:comma "$REPO_DIR" || warn "chown 失败"
  ok "已修正属主 comma:comma"
else
  warn "非 root，跳过 chown；若 manager 报 Permission denied，用 sudo 重跑"
fi

# ---------- 3. 依赖 ----------
if [[ $INSTALL_DEPS -eq 1 ]]; then
  REQ="selfdrive/carrot/requirements_lane.txt"
  [[ -f "$REQ" ]] || fail "缺少 $REQ"
  log "INFO" "安装车道推理依赖"
  if ! python3 -m pip install -r "$REQ" >/tmp/c3_update_pip.log 2>&1; then
    if grep -q "externally-managed-environment" /tmp/c3_update_pip.log; then
      warn "PEP 668 环境，改用 --break-system-packages"
      python3 -m pip install --break-system-packages -r "$REQ" || fail "pip 安装失败，见 /tmp/c3_update_pip.log"
    else
      tail -20 /tmp/c3_update_pip.log
      fail "pip 安装失败"
    fi
  fi
  ok "onnxruntime 已安装"
fi

# ---------- 4. 校验 ----------
python3 - <<'PY' || fail "onnxruntime 导入失败"
import onnxruntime
print("onnxruntime", onnxruntime.__version__)
PY

[[ -f "$MODEL_PATH" ]] || fail "模型缺失: $MODEL_PATH"
echo "$MODEL_SHA  $MODEL_PATH" | sha256sum -c - >/dev/null || fail "模型哈希不一致: $MODEL_PATH"
ok "模型校验通过"

python3 -m py_compile \
  selfdrive/carrot/lane_runner.py \
  selfdrive/carrot/lane_postprocess.py \
  selfdrive/carrot/lane_image.py \
  selfdrive/carrot/lane_protocol.py \
  selfdrive/carrot/lane_runtime.py \
  selfdrive/carrot/cooperative_mode.py \
  selfdrive/carrot/udp_trust.py \
  selfdrive/carrot/traffic_light.py \
  selfdrive/carrot/amap_navi.py \
  selfdrive/carrot/carrot_man.py \
  || fail "Python 语法检查失败"
ok "Python 语法检查通过"

# ---------- 5. 参数 ----------
python3 - "$BRANCH" <<'PY' || fail "参数写入失败"
import sys
from openpilot.common.params import Params
branch = sys.argv[1]
p = Params()
p.put("UpdaterTargetBranch", branch)
if p.get("CarrotCooperativeMode") is None:
    p.put_bool("CarrotCooperativeMode", True)
print("UpdaterTargetBranch =", p.get("UpdaterTargetBranch"))
print("CarrotCooperativeMode =", p.get_bool("CarrotCooperativeMode"))
PY
ok "参数已设置"

# ---------- 6. 重启 ----------
case "$MODE" in
  restart)
    if command -v systemctl >/dev/null 2>&1; then
      log "INFO" "重启 manager"
      sudo systemctl restart comma || fail "systemctl restart comma 失败"
      ok "manager 已重启"
    else
      warn "无 systemctl，请手动重启 manager"
    fi
    ;;
  reboot)
    log "INFO" "整机重启"
    sudo reboot
    ;;
  none)
    warn "跳过重启（--no-restart），新代码不会生效"
    ;;
esac

# ---------- 7. 自检 ----------
if [[ "$MODE" == "restart" ]]; then
  sleep 5
fi

echo
echo "===== 自检 ====="
echo "-- 进程（carrot_man 应只有 1 个）"
pgrep -af 'carrot_man|lane_runner|selfdrive.carrot.lane' || true

echo "-- 车机面对端口（每端口应只有一个 owner）"
ss -ulnp 2>/dev/null | grep -E ':(4210|4211|4213|4215|7705|7706)\b' || true

echo "-- 管理端口（应仅 127.0.0.1）"
ss -ulnp 2>/dev/null | grep -E ':(7710|7709|12345)\b' || true

echo "-- 关键日志"
for d in /data/media/0/realdata/rlog /data/media/0/realdata; do
  [[ -d "$d" ]] || continue
  grep -aE "MultiplePublishers|lane_runner disabled|UDP rejected|bind error" "$d"/* 2>/dev/null | tail -5 || true
done

echo
echo "提示：lane_runner / lane 是 only_onroad，驻车时不出现；上路后再复查。"
echo "完成。"
