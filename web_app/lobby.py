"""Lobby state: who has joined, which characters are claimed, which scripts exist.

Character exclusivity lives here. A character is claimed the moment a player
selects it and stays claimed for the rest of the match; when the match ends the
game process calls back and everything is released for the next round.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field

from arena import config as cfg
from arena.characters import ROSTER, get as get_character

log = logging.getLogger("arena.lobby")

# Generated scripts are always named by us, never by the player.
SCRIPT_PREFIX = "p_"


@dataclass
class Player:
    sid: str
    name: str
    character_id: str | None = None
    brief: str = ""
    script_file: str | None = None
    note: str = ""
    ready: bool = False
    joined_at: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "name": self.name,
            "character": self.character_id,
            "ready": self.ready,
            "note": self.note,
            "hasScript": bool(self.script_file),
        }


class Lobby:
    def __init__(self):
        self._lock = threading.RLock()
        self.players: dict[str, Player] = {}
        self.claims: dict[str, str] = {}          # character_id -> sid
        self.last_winner: dict | None = None
        self.round_id = 1

    # ----------------------------------------------------------------- join
    def join(self, name: str) -> Player:
        name = (name or "").strip()[:18] or "Player"
        with self._lock:
            sid = secrets.token_urlsafe(12)
            player = Player(sid=sid, name=name)
            self.players[sid] = player
            log.info("%s joined", name)
            return player

    def get(self, sid: str | None) -> Player | None:
        return self.players.get(sid or "")

    def rename(self, player: Player, name: str) -> None:
        with self._lock:
            player.name = (name or "").strip()[:18] or player.name

    # ------------------------------------------------------------- selection
    def claim(self, player: Player, character_id: str) -> tuple[bool, str]:
        preset = get_character(character_id)
        if preset is None:
            return False, "That character does not exist."

        with self._lock:
            holder = self.claims.get(preset.id)
            if holder and holder != player.sid:
                return False, f"{preset.name} has already been taken."
            if player.character_id == preset.id:
                return True, f"You are already {preset.name}."
            if player.character_id:
                return False, ("You already locked in "
                               f"{get_character(player.character_id).name} for this match.")
            if len(self.claims) >= cfg.MAX_PLAYERS:
                return False, f"The arena is full ({cfg.MAX_PLAYERS} fighters)."

            self.claims[preset.id] = player.sid
            player.character_id = preset.id
            player.ready = False
            player.note = ""
            log.info("%s locked in %s", player.name, preset.name)
            return True, f"You are {preset.name}."

    def release(self, player: Player) -> None:
        """Give a character back before the match starts."""
        with self._lock:
            if player.character_id:
                self.claims.pop(player.character_id, None)
            if player.script_file:
                (cfg.PLAYER_DIR / player.script_file).unlink(missing_ok=True)
            player.character_id = None
            player.script_file = None
            player.brief = ""
            player.note = ""
            player.ready = False

    # --------------------------------------------------------------- scripts
    def script_path(self, player: Player):
        return cfg.PLAYER_DIR / f"{SCRIPT_PREFIX}{player.character_id}_{player.sid[:6]}.py"

    def write_script(self, player: Player, source: str, brief: str, note: str) -> str:
        with self._lock:
            path = self.script_path(player)
            path.write_text(source, encoding="utf-8")
            player.script_file = path.name
            player.brief = brief
            player.note = note
            player.ready = True
            log.info("wrote %s for %s (%s)", path.name, player.name, note)
            return path.name

    # ----------------------------------------------------------------- reset
    def reset_for_next_match(self, winner: dict | None) -> int:
        """Free every character and delete every script the lobby generated."""
        with self._lock:
            self.last_winner = winner
            self.round_id += 1
            self.claims.clear()

            removed = 0
            for path in cfg.PLAYER_DIR.glob(f"{SCRIPT_PREFIX}*.py"):
                try:
                    path.unlink()
                    removed += 1
                except OSError as e:
                    log.warning("could not remove %s: %s", path.name, e)

            for player in self.players.values():
                player.character_id = None
                player.script_file = None
                player.brief = ""
                player.note = ""
                player.ready = False

            log.info("match ended — released all characters, removed %s scripts", removed)
            return removed

    # ------------------------------------------------------------- rendering
    def roster_state(self, viewer: Player | None) -> dict:
        with self._lock:
            taken = {}
            for character_id, sid in self.claims.items():
                holder = self.players.get(sid)
                taken[character_id] = holder.name if holder else "another player"

            return {
                "roundId": self.round_id,
                "maxPlayers": cfg.MAX_PLAYERS,
                "characters": [
                    {
                        **c.public(),
                        "takenBy": taken.get(c.id),
                        "mine": bool(viewer and viewer.character_id == c.id),
                    }
                    for c in ROSTER
                ],
                "players": [p.public() for p in
                            sorted(self.players.values(), key=lambda p: p.joined_at)],
                "you": (
                    {
                        "name": viewer.name,
                        "character": viewer.character_id,
                        "ready": viewer.ready,
                        "note": viewer.note,
                        "brief": viewer.brief,
                        "scriptFile": viewer.script_file,
                    }
                    if viewer else None
                ),
                "lastWinner": self.last_winner,
            }
