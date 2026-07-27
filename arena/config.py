"""Shared paths, tunables and environment wiring."""
from __future__ import annotations

import os
import socket
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PLAYER_DIR = ROOT / "player"
RUNTIME_DIR = ROOT / "runtime"
PLAYER_DIR.mkdir(exist_ok=True)
RUNTIME_DIR.mkdir(exist_ok=True)

GAME_PORT = int(os.getenv("GAME_PORT", "8000"))
LOBBY_PORT = int(os.getenv("LOBBY_PORT", "8100"))
GAME_URL = f"http://127.0.0.1:{GAME_PORT}"
LOBBY_URL = f"http://127.0.0.1:{LOBBY_PORT}"

INTERNAL_TOKEN = os.getenv("ARENA_INTERNAL_TOKEN", "change-me-local-dev")


def lan_ip() -> str:
    """The address phones on the same network can actually reach.

    Opens a UDP socket toward a public address to find which local interface
    the routing table would use. No packets are sent and nothing is contacted.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        sock.close()


LOBBY_PUBLIC_URL = f"http://{lan_ip()}:{LOBBY_PORT}"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

# ---------------------------------------------------------------- simulation
TICK_RATE = 60                 # physics steps per second
THINK_EVERY = 3                # run bot scripts every N ticks (20 Hz)
MAX_PLAYERS = 8
STOCKS = int(os.getenv("STOCKS", "3"))

GRAVITY = 0.62
MAX_FALL_SPEED = 15.0
GROUND_FRICTION = 0.80
AIR_FRICTION = 0.94
AIR_CONTROL = 0.42
JUMP_VELOCITY = -13.2
DOUBLE_JUMP_VELOCITY = -11.8
MAX_JUMPS = 2
FASTFALL_SPEED = 18.0

RESPAWN_DELAY = 90             # ticks of the respawn platform pause
INVULN_TICKS = 100             # i-frames after respawning
HITSTUN_PER_KB = 3.2

SHIELD_MAX = 100.0
SHIELD_DRAIN = 1.1
SHIELD_REGEN = 0.55
DODGE_TICKS = 22
DODGE_IFRAMES = 13
DODGE_COOLDOWN = 36

# Stage / camera space. The renderer scales this to the browser viewport.
WORLD_W = 1600
WORLD_H = 900

# Blast zones: leaving these in any direction is a KO.
BLAST_LEFT = -320
BLAST_RIGHT = WORLD_W + 320
BLAST_TOP = -420
BLAST_BOTTOM = WORLD_H + 300
