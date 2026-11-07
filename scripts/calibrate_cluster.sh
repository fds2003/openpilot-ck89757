#!/bin/bash
# 库斯途 Reborn 仪表投影 · 真车标定脚本
#
# 用途：在 HSAE 车机上逐项验证 ADAS 电子地平线（transact 14）与 TBT 图标，
#       把仪表实际反应对照 Reborn 发送的字节，固化字段语义名（见 13/17 号文档）。
#
# 前提：
#   - 车机已装 Reborn v1.4.0+，且是系统应用/平台签名（可写 HSAE 仪表）
#   - adb 能连到车机（USB 或 192.168.x.x）
#   - 本脚本在 PC 端（Git Bash / WSL）运行
#
# 用法：
#   ./calibrate_cluster.sh            # 全流程（probe + 逐帧）
#   ./calibrate_cluster.sh --seq 96   # 只发某个 displayType 标定帧
#   ./calibrate_cluster.sh --adas      # 只发 ADAS 测试帧
#
# 观察要点：每发一帧，立即看仪表对应区域（箭头/限速/弯道/罗盘/进度）反应，
#           记录“帧类型 + 仪表反应”，再回填到 AdasPayloadCodec 注释与 SegmentFields 语义名。

set -u
DEV="${ADB_DEVICE:-}"
if [ -n "$DEV" ]; then ADB="adb -s $DEV"; else ADK=""; ADB="adb"; fi
PKG=tech.touka.amapnavi
ACT="$PKG/.ui.main.MainActivity"

log() { printf "\n\033[1;34m== %s ==\033[0m\n" "$1"; }
step() { printf "\033[1;32m▶ %s\033[0m\n" "$1"; }
note() { printf "\033[36m  观察：%s\033[0m\n" "$1"; }

# 打开 App 并停在「仪表投影」一级页
open_cluster_page() {
  $ADB shell am force-stop "$PKG" >/dev/null 2>&1
  $ADB shell am start -n "$ACT" >/dev/null 2>&1
  sleep 3
  # 点「仪表投影」一级按钮（坐标按 960x1280 布局，实际以 uiautomator 为准）
  $ADB shell input tap 450 300
  sleep 2
}

# 在 UI 上点某个按钮文本（用 uiautomator 定位 bounds 再 tap）
tap_text() {
  local txt="$1"
  $ADB shell "uiautomator dump /sdcard/calib.xml" >/dev/null 2>&1
  $ADB pull /sdcard/calib.xml /tmp/calib_ui.xml >/dev/null 2>&1
  local bnd
  bnd=$(python - "$txt" <<'PY'
import re,sys
txt=sys.argv[1]
try:
    s=open('/tmp/calib_ui.xml',encoding='utf-8',errors='ignore').read()
    m=re.search(r'<node[^>]*text="'+re.escape(txt)+r'"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',s)
    if m:
        x,y,w,h=int(m.group(1)),int(m.group(2)),int(m.group(3)),int(m.group(4))
        print(f"{(x+w)//2} {(y+h)//2}")
except Exception: pass
PY
)
  if [ -n "$bnd" ]; then
    step "点按钮「$txt」 @ $bnd"
    $ADB shell input tap $bnd
  else
    printf "\033[33m  找不到按钮「$txt」（可能需先滚动页面）\033[0m\n"
  fi
  sleep 1.5
}

# 读 HSAE 服务可达性（通过 App 状态文本）
check_probe() {
  step "检测 HSAE 服务"
  tap_text "检测 HSAE 服务"
  sleep 1
  $ADB shell "uiautomator dump /sdcard/calib.xml" >/dev/null 2>&1
  $ADB pull /sdcard/calib.xml /tmp/calib_ui.xml >/dev/null 2>&1
  python - <<'PY'
import re
s=open('/tmp/calib_ui.xml',encoding='utf-8',errors='ignore').read()
m=re.search(r'text="([^"]*(HSAE|服务|权限|接管)[^"]*)"',s)
print("  状态：", m.group(1) if m else "未读到")
PY
}

# 发一帧 displayType 标定帧（直接调 App 内部不现实，走 UI 的 spinner + 按钮）
# 简化：通过 UI 选择 spinner 值再点「发送标定帧」。这里逐个发关键码。
send_display_type() {
  local code="$1" label="$2"
  step "标定 displayType=$code（$label）"
  note "$label —— 看仪表箭头区是否出现对应图标"
  # 打开 spinner 选对应项（spinner 项文本含 "65 直行" 之类）
  $ADB shell "uiautomator dump /sdcard/calib.xml" >/dev/null 2>&1
  $ADB pull /sdcard/calib.xml /tmp/calib_ui.xml >/dev/null 2>&1
  local item="$code $label"
  python - "$item" <<'PY'
import re,sys
txt=sys.argv[1]
s=open('/tmp/calib_ui.xml',encoding='utf-8',errors='ignore').read()
m=re.search(r'<node[^>]*text="'+re.escape(txt)+r'"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',s)
if m:
    print(f"{(int(m.group(1))+int(m.group(3)))//2} {(int(m.group(2))+int(m.group(4)))//2}")
PY
  # 若 spinner 已显示该值则直接点「发送标定帧」
  tap_text "发送标定帧"
  sleep 1
}

main() {
  case "${1:-all}" in
    --seq)
      open_cluster_page
      send_display_type "${2:-65}" "直行"
      return ;;
    --adas)
      open_cluster_page
      step "发送 ADAS Position 测试帧（type 458）"
      note "看仪表是否有 ADAS 车道/航向区反应（零值帧）"
      tap_text "发送 ADAS Position 测试帧"
      return ;;
    --ux2)
      run_ux2_calibration
      return ;;
  esac

  log "1. 打开仪表投影页"
  open_cluster_page

  log "2. 检测 HSAE 服务"
  check_probe

  log "3. TBT 图标标定（逐 displayType）"
  for c in 65 66 67 68 69 70 71 72; do
    case $c in
      65) l="直行";; 66) l="右前";; 67) l="右转";; 68) l="右后";;
      69) l="左后";; 70) l="左转";; 71) l="左前";; 72) l="掉头";;
    esac
    send_display_type "$c" "$l"
  done

  log "4. 实验性图标候选码（环岛/收费站/匝道）"
  for c in 96 97 99 100 102 104 105 107; do
    case $c in
      96) l="环岛";; 97) l="环岛出口";; 99) l="环岛档位";; 100) l="环岛档位";;
      102) l="环岛档位";; 104) l="环岛档位";; 105) l="环岛档位";; 107) l="环岛档位";;
    esac
    send_display_type "$c" "$l"
  done
  send_display_type 212 "收费站"
  send_display_type 176 "渡口"
  send_display_type 178 "驶出渡口"

  log "5. ADAS 电子地平线测试帧"
  tap_text "发送 ADAS Position 测试帧"
  note "若仪表无反应：勾选「ADAS 电子地平线」开关后进入真实导航再观察"

  log "完成"
  echo "请把每帧的仪表反应记录下来，回填到："
  echo "  - cluster/AdasPayloadCodec.kt（字段语义注释）"
  echo "  - cluster/ClusterMapper.mapTurnType（图标候选码）"
  echo "  - docs/custin-cooperative/17_未完成工作与剩余事项.md（勾选 [实车]）"
}

# ============================================================================
# UX-2 专项：高德转向图标 → 候选 displayType 逐一标定
# 每个候选码发送后暂停 WAIT 秒供人观察仪表，并写入可回填的 CSV 记录。
# 高德图标枚举（ClusterMapper.mapTurnType 的 key）与候选码映射：
#   11 进环岛→96   12 出环岛→97   14 收费站→212
#   15 驶出匝道→178  17 靠右→66    20 驶出高速→178
# ============================================================================
UX2_WAIT="${UX2_WAIT:-3}"   # 每个候选码后观察等待秒数，可用 UX2_WAIT=10 覆盖
UX2_CSV="${UX2_CSV:-$(pwd)/ux2_calibration.csv}"

run_ux2_calibration() {
  log "UX-2 专项标定：转向图标候选码"
  open_cluster_page
  check_probe
  # 生成 CSV 表头
  cat > "$UX2_CSV" <<CSV
gaode_icon,candidate_code,meaning,cluster_reaction,correct_code,notes
CSV
  step "记录写入 $UX2_CSV；每帧发后等 ${UX2_WAIT}s 观察，逐行填 cluster_reaction/correct_code"

  # icon 候选码 含义
  UX2_CODES="11:96:进环岛 12:97:出环岛 14:212:收费站 15:178:驶出匝道 17:66:靠右 20:178:驶出高速"
  for entry in $UX2_CODES; do
    icon="${entry%%:*}"; rest="${entry#*:}"
    code="${rest%%:*}"; meaning="${rest#*:}"
    step "发候选码 $code（高德图标 ${icon}=$meaning）"
    note "观察仪表箭头区：$meaning 应显示为？记录到 CSV 对应行"
    # spinner 选 "$code $meaning" 再点发送（沿用 send_display_type 逻辑，此处直接发码）
    send_display_type "$code" "$meaning"
    # 写一行占位 CSV（人填 cluster_reaction/correct_code）
    echo "$icon,$code,$meaning,,,,待观察" >> "$UX2_CSV"
    sleep "$UX2_WAIT"
  done

  log "UX-2 标定完成"
  echo "对照 $UX2_CSV 逐行填：仪表实际反应 / 正确的 displayType。"
  echo "回填 cluster/ClusterMapper.mapTurnType 的候选码后，把 18 号 UX-2 与 17 号 [实车] 勾选。"
}

main "$@"
