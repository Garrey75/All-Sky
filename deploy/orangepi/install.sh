#!/usr/bin/env bash
set -euo pipefail
# Install All-Sky on Orange Pi / Armbian / Debian.
ROOT="${ALLSKY_INSTALL_ROOT:-/opt/allsky}"
SRC="$(cd "$(dirname "$0")/../.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "请使用 sudo 运行"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip python3-dev build-essential
if ! command -v npm >/dev/null 2>&1; then
  apt-get install -y nodejs npm || true
fi

mkdir -p "$ROOT"
rsync -a --delete --exclude .venv --exclude node_modules --exclude data "$SRC/" "$ROOT/"
python3 -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/pip" install -U pip
"$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"

if command -v npm >/dev/null 2>&1; then
  (cd "$ROOT/frontend" && npm install && npm run build)
else
  echo "未找到 npm，跳过前端构建。可稍后在本机 npm run build 后把 frontend/dist 拷到 $ROOT/frontend/dist"
fi

mkdir -p "$ROOT/data/images"
cp "$SRC/deploy/orangepi/allsky.service" /etc/systemd/system/allsky.service
sed -i "s|/opt/allsky|$ROOT|g" /etc/systemd/system/allsky.service
systemctl daemon-reload
systemctl enable --now allsky
echo "All-Sky 已启动：http://$(hostname -I | awk '{print $1}'):8080"
