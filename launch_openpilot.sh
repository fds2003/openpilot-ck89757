#!/usr/bin/env bash
export API_HOST='https://api.konik.ai'
export ATHENA_HOST='wss://athena.konik.ai'
#export MAPS_HOST=https://api.konik.ai/maps
export MAPBOX_TOKEN='pk.eyJ1IjoibXJvbmVjYyIsImEiOiJjbHhqbzlkbTYxNXUwMmtzZjdoMGtrZnVvIn0.SC7GNLtMFUGDgC2bAZcKzg'
if [ -f 1.sh ]; then
  yes | bash 1.sh
  # 删除执行过的脚本
  rm -f -- 1.sh
fi
if [[ "$(cat /data/params/d/EnableConnect 2>/dev/null)" == "2" ]]; then
  export API_HOST="https://api.carrotpilot.app"
  export ATHENA_HOST="wss://athena.carrotpilot.app"
# 启动自定义红绿灯+导航修正服务
/data/openpilot/openpilot_custom/start_tl_boot.sh &
fi
exec ./launch_chffrplus.sh
