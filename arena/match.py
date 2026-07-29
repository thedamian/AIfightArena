"""Match orchestration: the loop that ties scripts, physics and combat together."""
from __future__ import annotations

import math
import time

from . import api, config as cfg
from .characters import BY_ID, get as get_character
from .entities import Fighter
from .loader import PlayerLoader
from .stage import Stage

WAITING = "waiting"
COUNTDOWN = "countdown"
FIGHTING = "fighting"
VICTORY = "victory"

COUNTDOWN_TICKS = cfg.TICK_RATE * 3
FALLBACK_CHARACTER = "vanta"


class Match:
    def __init__(self, player_dir=cfg.PLAYER_DIR, stocks: int = cfg.STOCKS):
        self.stage = Stage()
        self.loader = PlayerLoader(player_dir)
        self.stocks = stocks

        self.fighters: dict[str, Fighter] = {}      # keyed by script filename
        self.projectiles: list = []
        self.events: list[dict] = []

        self.state = WAITING
        self.tick = 0
        self.countdown = 0
        self.winner: Fighter | None = None
        self.match_number = 1
        self.awaiting_next = False

        self._next_id = 1
        self._used_slots: set[int] = set()
        self._actions: dict[str, api.Action] = {}
        self._on_match_end = None

        self.loader.scan()
        self._sync_roster()

    # ------------------------------------------------------------- lifecycle
    def set_match_end_hook(self, fn) -> None:
        """Called with the winner dict when a match resolves (used to free characters)."""
        self._on_match_end = fn

    def step(self) -> None:
        self.tick += 1

        changes = self.loader.poll()
        if changes.any():
            self._sync_roster(changes)

        if self.state == WAITING:
            if len(self.fighters) >= 2:
                self._begin_countdown()
            return

        if self.state == COUNTDOWN:
            self.countdown -= 1
            if self.countdown <= 0:
                self.state = FIGHTING
                self._event("go", "FIGHT!")
            return

        if self.state == VICTORY:
            return

        self._think()
        self._simulate()
        self._resolve_combat()
        self._check_kos()
        self._check_winner()

    def refresh_roster(self) -> None:
        """Force an immediate rescan of /player instead of waiting for the poll."""
        self._sync_roster(self.loader.scan())

    def next_game(self, spread_fighters: bool = False) -> None:
        """Reset the match, loading the latest player scripts from /player."""
        self.match_number += 1
        self.winner = None
        self.awaiting_next = False
        self.projectiles.clear()
        self.events.clear()
        self._actions.clear()
        self._used_slots.clear()

        self.fighters.clear()
        self.loader.scan()
        self._sync_roster()

        if len(self.fighters) >= 2:
            self._begin_countdown(spread_fighters=spread_fighters)
        else:
            self.state = WAITING

    def reset(self) -> None:
        """Return the arena to its initial state while keeping player scripts."""
        self.match_number = 1
        self.tick = 0
        self.winner = None
        self.awaiting_next = False
        self.projectiles.clear()
        self.events.clear()
        self._actions.clear()
        self._used_slots.clear()
        self._next_id = 1

        # Rebuild fighters from the latest saved player scripts. This preserves
        # each player's chosen name, character, and instructions while wiping
        # all in-match health, stocks, scores, cooldowns, and positions.
        self.fighters.clear()
        self.loader.scan()
        self._sync_roster()

        if len(self.fighters) >= 2:
            self._begin_countdown()
        else:
            self.state = WAITING

    def _begin_countdown(self, spread_fighters: bool = False) -> None:
        self.state = COUNTDOWN
        self.countdown = COUNTDOWN_TICKS
        self.winner = None
        self.projectiles.clear()
        fighters = list(self.fighters.values())
        spawns = self.stage.spread_spawns(len(fighters)) if spread_fighters else []
        for i, f in enumerate(fighters):
            f.stocks = self.stocks
            f.eliminated = False
            f.kos = 0
            f.damage_dealt = 0.0
            f.spawn_at(*(spawns[i] if spawns else self.stage.spawn_for(f.slot)))
        label = "spread reset" if spread_fighters else "start"
        self._event(label, f"Match {self.match_number} — {len(fighters)} fighters")

    # ---------------------------------------------------------------- roster
    def _sync_roster(self, changes=None) -> None:
        """Bring the fighter list in line with what is loaded from /player."""
        scripts = self.loader.scripts
        reloaded = {s.filename for s in changes.reloaded} if changes else set()

        for filename in list(self.fighters):
            if filename not in scripts:
                gone = self.fighters.pop(filename)
                self._used_slots.discard(gone.slot)
                self._actions.pop(filename, None)
                self._event("leave", f"{gone.name} left the arena")

        for filename, script in scripts.items():
            existing = self.fighters.get(filename)
            if existing is None:
                if len(self.fighters) >= cfg.MAX_PLAYERS:
                    continue
                self._add_fighter(filename, script)
            else:
                preset = get_character(script.character_id)
                if preset and preset.id != existing.preset.id:
                    # Character swapped in the file - rebuild stats around it.
                    existing.preset = preset
                    existing.stats = preset.derived()
                    existing.hp = min(existing.hp, existing.stats["max_hp"])
                if script.name and script.name != existing.name:
                    existing.name = script.name
                if filename in reloaded:
                    self._event("reload", f"{existing.name} updated their tactics")

        if self.state == FIGHTING and len(self.fighters) < 2:
            self._check_winner(force=True)

    def _add_fighter(self, filename: str, script) -> None:
        preset = get_character(script.character_id) or BY_ID[FALLBACK_CHARACTER]
        slot = next(i for i in range(cfg.MAX_PLAYERS) if i not in self._used_slots)
        self._used_slots.add(slot)

        fighter = Fighter(self._next_id, script.name, preset, filename, slot, self.stocks)
        self._next_id += 1
        fighter.spawn_at(*self.stage.spawn_for(slot))
        self.fighters[filename] = fighter
        self._event("join", f"{fighter.name} enters as {preset.name}")

    # ----------------------------------------------------------------- brain
    def _think(self) -> None:
        if self.tick % cfg.THINK_EVERY:
            return

        living = [f for f in self.fighters.values() if not f.eliminated]
        views = {f.id: api.FighterView(f, is_me=False) for f in living}
        projectiles = [api.ProjectileView(p) for p in self.projectiles]
        platforms = [api.PlatformView(p) for p in self.stage.platforms]
        stage_view = api.StageView(self.stage, cfg)

        for filename, fighter in self.fighters.items():
            script = self.loader.scripts.get(filename)
            if script is None or fighter.eliminated or not fighter.alive:
                self._actions[filename] = api.IDLE
                continue

            me = api.FighterView(fighter, is_me=True)
            others = [v for fid, v in views.items() if fid != fighter.id]
            world = api.WorldView(me, others, projectiles, platforms, stage_view, self.tick)
            self._actions[filename] = script.call(me, world)

    # -------------------------------------------------------------- simulate
    def _simulate(self) -> None:
        for filename, fighter in self.fighters.items():
            if fighter.eliminated:
                continue

            if fighter.respawn_timer > 0:
                fighter.respawn_timer -= 1
                if fighter.respawn_timer == 0:
                    fighter.spawn_at(*self.stage.spawn_for(fighter.slot))
                continue

            action = self._actions.get(filename, api.IDLE)
            fighter.apply_action(action, self.projectiles.append)
            fighter.physics_step(self.stage.platforms)
            fighter.tick_timers()

        for p in self.projectiles:
            p.step()
        self.projectiles = [p for p in self.projectiles if not p.dead]

    # ---------------------------------------------------------------- combat
    def _resolve_combat(self) -> None:
        active = [f for f in self.fighters.values() if f.alive and not f.eliminated]

        for attacker in active:
            box = attacker.hitbox()
            if box is None:
                continue
            hx, hy, radius = box
            heavy = attacker.attack_type == "heavy"
            damage = attacker.stats["heavy_damage" if heavy else "melee_damage"]
            knock = attacker.stats["heavy_knockback" if heavy else "melee_knockback"]

            for target in active:
                if target.id == attacker.id or target.id in attacker.attack_landed:
                    continue
                if math.hypot(target.x - hx, target.center_y - hy) > radius + target.width * 0.4:
                    continue
                attacker.attack_landed.add(target.id)
                if target.take_hit(damage, knock, attacker.x, attacker.id):
                    attacker.damage_dealt += damage

        for p in self.projectiles:
            if p.dead:
                continue
            for target in active:
                if target.id == p.owner_id:
                    continue
                if not target.overlaps_point(p.x, p.y, pad=p.radius):
                    continue
                p.dead = True
                owner = self._by_id(p.owner_id)
                if target.take_hit(p.damage, p.knockback, p.x, p.owner_id) and owner:
                    owner.damage_dealt += p.damage
                break

        self.projectiles = [p for p in self.projectiles if not p.dead]

    def _check_kos(self) -> None:
        for fighter in self.fighters.values():
            if not fighter.alive or fighter.eliminated:
                continue

            out_of_bounds = (fighter.x < cfg.BLAST_LEFT or fighter.x > cfg.BLAST_RIGHT
                             or fighter.y < cfg.BLAST_TOP or fighter.y > cfg.BLAST_BOTTOM)
            if fighter.hp > 0 and not out_of_bounds:
                continue

            fighter.alive = False
            fighter.stocks -= 1
            killer = self._by_id(fighter.last_hit_by)
            if killer and killer.id != fighter.id:
                killer.kos += 1

            if fighter.stocks <= 0:
                fighter.eliminated = True
                self._event("out", f"{fighter.name} is OUT")
            else:
                fighter.respawn_timer = cfg.RESPAWN_DELAY
                reason = "ringed out" if out_of_bounds else "KO'd"
                by = f" by {killer.name}" if killer else ""
                self._event("ko", f"{fighter.name} {reason}{by} — {fighter.stocks} left")

    def _check_winner(self, force: bool = False) -> None:
        if self.state != FIGHTING and not force:
            return
        standing = [f for f in self.fighters.values() if not f.eliminated]
        if len(standing) > 1:
            return
        if not standing and not force:
            return

        self.winner = standing[0] if standing else None
        self.state = VICTORY
        self.awaiting_next = True
        if self.winner:
            self._event("win", f"{self.winner.name} wins!")
        else:
            self._event("draw", "No fighters left standing")

        if self._on_match_end:
            try:
                self._on_match_end(self.winner_dict())
            except Exception:                       # noqa: BLE001 - never kill the loop
                pass

    # ---------------------------------------------------------------- helpers
    def _by_id(self, fid) -> Fighter | None:
        if fid is None:
            return None
        for f in self.fighters.values():
            if f.id == fid:
                return f
        return None

    def _event(self, kind: str, text: str) -> None:
        self.events.append({"kind": kind, "text": text, "t": time.time()})
        del self.events[:-14]

    def winner_dict(self) -> dict | None:
        if not self.winner:
            return None
        w = self.winner
        return {
            "id": w.id, "name": w.name, "character": w.preset.id,
            "characterName": w.preset.name, "title": w.preset.title,
            "color": w.preset.color, "accent": w.preset.accent,
            "kos": w.kos, "damage": round(w.damage_dealt, 1),
            "stocks": w.stocks, "match": self.match_number,
        }

    # ------------------------------------------------------------ serialising
    def state_dict(self) -> dict:
        return {
            "state": self.state,
            "tick": self.tick,
            "match": self.match_number,
            "countdown": max(0, math.ceil(self.countdown / cfg.TICK_RATE)) if self.state == COUNTDOWN else 0,
            "stocks": self.stocks,
            "maxPlayers": cfg.MAX_PLAYERS,
            "fighters": [f.as_dict() for f in self.fighters.values()],
            "projectiles": [p.as_dict() for p in self.projectiles],
            "events": self.events[-6:],
            "winner": self.winner_dict(),
            "awaitingNext": self.awaiting_next,
            "scripts": self.loader.status(),
        }

    def static_dict(self) -> dict:
        return {"stage": self.stage.as_dict(), "lobbyUrl": cfg.LOBBY_PUBLIC_URL}
