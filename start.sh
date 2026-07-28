#!/usr/bin/env bash
# Bring up both processes: the arena and the lobby.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found on PATH. Install it from https://docs.astral.sh/uv/" >&2
  exit 1
fi

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Setting up .venv ..."
  uv venv .venv
fi

# Reconcile dependencies even when .venv already exists. This is quick when
# requirements are already installed and prevents an incomplete environment
# from making both servers exit immediately.
uv pip install --python "$PY" -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — add your OPENAI_API_KEY to it."
fi

GAME_PORT="$(grep -E '^GAME_PORT=' .env | cut -d= -f2 || true)"
LOBBY_PORT="$(grep -E '^LOBBY_PORT=' .env | cut -d= -f2 || true)"
GAME_PORT="${GAME_PORT:-8000}"
LOBBY_PORT="${LOBBY_PORT:-8100}"

mkdir -p runtime

# Keep stdout and stderr separate: it preserves errors and avoids platform-
# specific process-redirection limitations while still streaming both below.
GAME_OUT_LOG="runtime/game.out.log"
GAME_ERR_LOG="runtime/game.err.log"
LOBBY_OUT_LOG="runtime/lobby.out.log"
LOBBY_ERR_LOG="runtime/lobby.err.log"
: >"$GAME_OUT_LOG"
: >"$GAME_ERR_LOG"
: >"$LOBBY_OUT_LOG"
: >"$LOBBY_ERR_LOG"

GAME_PID=""
LOBBY_PID=""
TAIL_PIDS=()
CLEANED_UP=0

stop_pid() {
  local pid="$1"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  if [ "$CLEANED_UP" -eq 1 ]; then
    return
  fi
  CLEANED_UP=1

  local pid
  for pid in "${TAIL_PIDS[@]}"; do
    stop_pid "$pid"
  done
  stop_pid "$GAME_PID"
  stop_pid "$LOBBY_PID"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

PYTHONUNBUFFERED=1 uv run --python "$PY" python -m game_app.server >"$GAME_OUT_LOG" 2>"$GAME_ERR_LOG" &
GAME_PID=$!
PYTHONUNBUFFERED=1 uv run --python "$PY" python -m web_app.server >"$LOBBY_OUT_LOG" 2>"$LOBBY_ERR_LOG" &
LOBBY_PID=$!

tail -n 0 -F "$GAME_OUT_LOG" | sed 's/^/[game ] /' & TAIL_PIDS+=("$!")
tail -n 0 -F "$GAME_ERR_LOG" | sed 's/^/[game!] /' & TAIL_PIDS+=("$!")
tail -n 0 -F "$LOBBY_OUT_LOG" | sed 's/^/[lobby] /' & TAIL_PIDS+=("$!")
tail -n 0 -F "$LOBBY_ERR_LOG" | sed 's/^/[lobby!] /' & TAIL_PIDS+=("$!")

sleep 2
# Players join from their phones, so print the LAN address rather than
# localhost. The default route's interface is the one that actually works.
lan_ip() {
  local iface
  iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
  if [ -n "$iface" ]; then
    ipconfig getifaddr "$iface" 2>/dev/null && return
  fi
  for iface in en0 en1 en2 wlan0 eth0; do
    ipconfig getifaddr "$iface" 2>/dev/null && return
  done
  hostname -I 2>/dev/null | awk '{print $1}' && return
  echo localhost
}
IP="$(lan_ip)"
IP="${IP:-localhost}"

cat <<EOF

  AI FIGHT ARENA

  Main screen (put this on the TV)   http://localhost:${GAME_PORT}
  Lobby (players join on their phone) http://${IP}:${LOBBY_PORT}

  Fighter scripts live in ./player — add, edit or delete them while a match
  is running and the arena keeps up.

  Ctrl-C to stop both.

EOF

# Keep the launcher alive while both servers run. If either exits, print its
# full logs so startup failures are immediately visible instead of silent.
while kill -0 "$GAME_PID" 2>/dev/null && kill -0 "$LOBBY_PID" 2>/dev/null; do
  sleep 0.2
done

if ! kill -0 "$GAME_PID" 2>/dev/null; then
  echo "Game server exited. Full logs:" >&2
  sed 's/^/[game ] /' "$GAME_OUT_LOG" >&2
  sed 's/^/[game!] /' "$GAME_ERR_LOG" >&2
fi

if ! kill -0 "$LOBBY_PID" 2>/dev/null; then
  echo "Lobby server exited. Full logs:" >&2
  sed 's/^/[lobby] /' "$LOBBY_OUT_LOG" >&2
  sed 's/^/[lobby!] /' "$LOBBY_ERR_LOG" >&2
fi

exit 1
