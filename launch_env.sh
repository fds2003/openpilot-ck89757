#!/usr/bin/bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

export ATHENA_HOST='ws://op.caminfo.cn:7776'
export API_HOST='http://op.caminfo.cn:7777'
export MAPBOX_TOKEN='sk.eyJ1IjoibWF3ZWl5dXdlaXdlaSIsImEiOiJjbG15NHN1dDMwdWc5MmxwaDdkZ3Z5dHNyIn0.pk06qTKkAZyBC1Z37v8i0A'


if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="10.1"
fi

export STAGING_ROOT="/data/safe_staging"

# 库斯途专属：时区兜底逻辑（当 /data/etc/localtime 为空或缺失时，默认定向到 Asia/Shanghai）
if [ -d "/data/etc" ] && [ ! -s "/data/etc/localtime" ]; then
  if [ -f "/usr/share/zoneinfo/Asia/Shanghai" ]; then
    sudo rm -f /data/etc/localtime 2>/dev/null || true
    sudo ln -sf /usr/share/zoneinfo/Asia/Shanghai /data/etc/localtime 2>/dev/null || true
    echo "[launch_env] Timezone fallback applied: Asia/Shanghai"
  fi
fi

# 库斯途专属：支持本地个性化环境配置优先覆盖（如私有服务器、个人 Mapbox Token 等）
LOCAL_ENV_FILE="$(dirname "$0")/launch_env.local"
if [ -f "$LOCAL_ENV_FILE" ]; then
  source "$LOCAL_ENV_FILE"
fi

