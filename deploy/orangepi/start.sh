#!/usr/bin/env bash
set -euo pipefail
# Start All-Sky (and optional INDI) on Orange Pi or a development host.
# Does not require root. Use install.sh for systemd/boot autostart.

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="${ALLSKY_PORT:-8080}"
INDI_PORT="${ALLSKY_INDI_PORT:-7624}"
TMUX_CONF="/exec-daemon/tmux.portal.conf"
SESSION="allsky-orgpi"
INDI_SESSION="allsky-indi"

need() { command -v "$1" >/dev/null 2>&1; }

tmux_cmd() {
  if [[ -f "$TMUX_CONF" ]]; then
    tmux -f "$TMUX_CONF" "$@"
  else
    tmux "$@"
  fi
}

ensure_session() {
  local name="$1" cwd="$2"
  shift 2
  tmux_cmd has-session -t "=$name" 2>/dev/null && tmux_cmd kill-session -t "$name"
  tmux_cmd new-session -d -s "$name" -c "$cwd" -- "$@"
}

if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

if [[ ! -d "$ROOT/frontend/dist" ]]; then
  if need npm; then
    echo "构建前端…"
    (cd "$ROOT/frontend" && npm install && npm run build)
  else
    echo "警告：没有 frontend/dist，界面将只有 API。"
  fi
fi

mkdir -p "$ROOT/data/images" "$ROOT/data/stacks"

pkill -f "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}" 2>/dev/null || true
sleep 0.4

export ALLSKY_ROOT="$ROOT"
export ALLSKY_DATA="$ROOT/data"
export ALLSKY_HOST="0.0.0.0"
export ALLSKY_PORT="$PORT"

ensure_session "$SESSION" "$ROOT/backend" \
  "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

if need indiserver; then
  pkill -f "indiserver -p ${INDI_PORT}" 2>/dev/null || true
  ensure_session "$INDI_SESSION" "$ROOT" \
    indiserver -p "$INDI_PORT" indi_simulator_ccd indi_simulator_telescope indi_simulator_focus indi_simulator_wheel
  echo "INDI 模拟器已启动 :$INDI_PORT"
else
  echo "未安装 indiserver，使用内置模拟器（无需真实相机）。"
  echo "橙派上可: sudo apt install indi-bin  然后重新运行本脚本。"
fi

echo "等待 All-Sky 就绪…"
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "All-Sky 进程已启动"
    echo "  tmux 会话: $SESSION"
    echo "  地址: http://${IP:-127.0.0.1}:${PORT}"
    curl -sS "http://127.0.0.1:${PORT}/api/health"
    echo
    tmux_cmd ls 2>/dev/null || true
    exit 0
  fi
  sleep 0.25
done
echo "启动超时。最近日志："
tmux_cmd capture-pane -pt "$SESSION:0.0" 2>/dev/null || true
exit 1
