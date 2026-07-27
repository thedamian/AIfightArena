"""The read-only view of the match that player scripts are handed.

Everything in here is deliberately plain: public attributes, simple methods,
no references back to live simulation objects. A script can poke at any of it
without being able to mutate the match.
"""
from __future__ import annotations

import math
from types import MappingProxyType


class Action:
    """What a script returns from `decide(me, world)`.

    Every field is optional. Anything omitted means "do nothing this frame".

        return Action(move=1, jump=True, attack="light")
    """

    LIGHT = "light"
    HEAVY = "heavy"
    SHOOT = "shoot"

    def __init__(
        self,
        move: float = 0.0,
        jump: bool = False,
        attack: str | None = None,
        aim: tuple[float, float] | None = None,
        shield: bool = False,
        dodge: bool = False,
        fastfall: bool = False,
        drop: bool = False,
    ):
        self.move = _clamp(_num(move), -1.0, 1.0)
        self.jump = bool(jump)
        self.attack = attack if attack in (self.LIGHT, self.HEAVY, self.SHOOT) else None
        self.aim = _norm_aim(aim)
        self.shield = bool(shield)
        self.dodge = bool(dodge)
        self.fastfall = bool(fastfall)
        self.drop = bool(drop)

    def __repr__(self) -> str:
        return (f"Action(move={self.move:.2f}, jump={self.jump}, attack={self.attack!r}, "
                f"shield={self.shield}, dodge={self.dodge})")


def coerce_action(value) -> Action:
    """Scripts may return an Action, a dict, or nothing at all."""
    if isinstance(value, Action):
        return value
    if isinstance(value, dict):
        allowed = ("move", "jump", "attack", "aim", "shield", "dodge", "fastfall", "drop")
        return Action(**{k: v for k, v in value.items() if k in allowed})
    return IDLE


class FighterView:
    """A snapshot of one fighter. `world.me` is your own; opponents are the rest."""

    def __init__(self, f, is_me: bool):
        self.id = f.id
        self.name = f.name
        self.character = f.preset.id
        self.character_name = f.preset.name

        self.x = f.x
        self.y = f.y
        self.vx = f.vx
        self.vy = f.vy
        self.width = f.width
        self.height = f.height

        self.hp = round(f.hp, 1)
        self.max_hp = f.stats["max_hp"]
        self.hp_pct = round(f.hp / f.stats["max_hp"], 3) if f.stats["max_hp"] else 0.0
        self.stocks = f.stocks
        self.alive = f.alive
        self.facing = f.facing                    # 1 = right, -1 = left
        self.on_ground = f.on_ground
        self.jumps_left = f.jumps_left

        self.ammo = f.ammo
        self.max_ammo = f.stats["magazine"]
        self.reloading = f.reload_timer > 0
        self.reload_progress = round(1.0 - f.reload_timer / max(1, f.stats["reload_ticks"]), 3)

        self.shield = round(f.shield, 1)
        self.max_shield = f.stats["shield_max"]
        self.shielding = f.shielding
        self.shield_broken = f.shield_break_timer > 0
        self.dodging = f.dodge_timer > 0
        self.can_dodge = f.dodge_cooldown <= 0
        self.invulnerable = f.invuln > 0
        self.stunned = f.hitstun > 0
        self.attacking = f.attack_timer > 0
        self.offstage = f.offstage

        # Only your own view exposes the full stat block, and it is read-only:
        # a script that tries to write itself more health gets a TypeError
        # rather than a quietly-ignored assignment.
        self.stats = MappingProxyType(dict(f.stats)) if is_me else None

    def distance_to(self, other) -> float:
        return math.hypot(other.x - self.x, other.y - self.y)

    def dx_to(self, other) -> float:
        return other.x - self.x

    def dy_to(self, other) -> float:
        return other.y - self.y

    def direction_to(self, other) -> float:
        """-1 if the target is to your left, 1 if to the right."""
        d = other.x - self.x
        return 0.0 if d == 0 else (1.0 if d > 0 else -1.0)

    def is_above(self, other) -> bool:
        return self.y + self.height < other.y

    def is_below(self, other) -> bool:
        return self.y > other.y + other.height

    def __repr__(self) -> str:
        return f"<{self.name} {self.character_name} hp={self.hp} stocks={self.stocks}>"


class ProjectileView:
    def __init__(self, p):
        self.x = p.x
        self.y = p.y
        self.vx = p.vx
        self.vy = p.vy
        self.damage = p.damage
        self.owner_id = p.owner_id

    def __repr__(self) -> str:
        return f"<shot ({self.x:.0f},{self.y:.0f})>"


class PlatformView:
    def __init__(self, p):
        self.x = p.x
        self.y = p.y
        self.width = p.width
        self.height = p.height
        self.passthrough = p.passthrough

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def top(self) -> float:
        return self.y


class StageView:
    def __init__(self, stage, cfg):
        self.width = cfg.WORLD_W
        self.height = cfg.WORLD_H
        self.blast_left = cfg.BLAST_LEFT
        self.blast_right = cfg.BLAST_RIGHT
        self.blast_top = cfg.BLAST_TOP
        self.blast_bottom = cfg.BLAST_BOTTOM
        self.center_x = cfg.WORLD_W / 2
        main = stage.main
        self.ground_y = main.y
        self.ground_left = main.x
        self.ground_right = main.x + main.width


class WorldView:
    """Handed to `decide()` as the second argument."""

    def __init__(self, me: FighterView, others: list[FighterView],
                 projectiles: list[ProjectileView], platforms: list[PlatformView],
                 stage: StageView, tick: int):
        self.me = me
        self.opponents = others
        self.projectiles = projectiles
        self.platforms = platforms
        self.stage = stage
        self.tick = tick
        self.time = round(tick / 60.0, 2)

    @property
    def living_opponents(self) -> list[FighterView]:
        return [o for o in self.opponents if o.alive]

    def nearest_opponent(self) -> FighterView | None:
        alive = self.living_opponents
        if not alive:
            return None
        return min(alive, key=lambda o: self.me.distance_to(o))

    def weakest_opponent(self) -> FighterView | None:
        alive = self.living_opponents
        if not alive:
            return None
        return min(alive, key=lambda o: (o.stocks, o.hp))

    def strongest_opponent(self) -> FighterView | None:
        alive = self.living_opponents
        if not alive:
            return None
        return max(alive, key=lambda o: (o.stocks, o.hp))

    def incoming_projectiles(self, radius: float = 260.0) -> list[ProjectileView]:
        """Shots not fired by you that are heading roughly your way."""
        out = []
        for p in self.projectiles:
            if p.owner_id == self.me.id:
                continue
            if math.hypot(p.x - self.me.x, p.y - self.me.y) > radius:
                continue
            if (p.x < self.me.x and p.vx > 0) or (p.x > self.me.x and p.vx < 0):
                out.append(p)
        return out

    def threat_level(self) -> float:
        """Rough 0-1 danger score: how much trouble you are in right now."""
        near = self.nearest_opponent()
        score = 1.0 - self.me.hp_pct
        if near is not None and self.me.distance_to(near) < 220:
            score += 0.35
        if self.me.offstage:
            score += 0.4
        return _clamp(score, 0.0, 1.0)


# --------------------------------------------------------------------- utils
def _num(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f or f in (float("inf"), float("-inf")) else f


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _norm_aim(aim) -> tuple[float, float] | None:
    if aim is None:
        return None
    try:
        dx, dy = _num(aim[0]), _num(aim[1])
    except (TypeError, IndexError, KeyError):
        return None
    mag = math.hypot(dx, dy)
    if mag < 1e-6:
        return None
    return (dx / mag, dy / mag)


# Defined last: Action's constructor leans on the helpers above.
IDLE = Action()
