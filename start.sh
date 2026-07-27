#!/usr/bin/env bash
# Bring up both processes: the arena and the lobby.
set -euo pipefail

cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Setting up .venv ..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — add your OPENAI_API_KEY to it."
fi

GAME_PORT="$(grep -E '^GAME_PORT=' .env | cut -d= -f2 || true)"
LOBBY_PORT="$(grep -E '^LOBBY_PORT=' .env | cut -d= -f2 || true)"
GAME_PORT="${GAME_PORT:-8000}"
LOBBY_PORT="${LOBBY_PORT:-8100}"

mkdir -p runtime
cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$PY" -m game_app.server 2>&1 | sed 's/^/[game ] /' &
"$PY" -m web_app.server  2>&1 | sed 's/^/[lobby] /' &

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

wait
