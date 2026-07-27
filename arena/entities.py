"""Fighters and projectiles: movement, attacks, damage and knockback."""
from __future__ import annotations

import math

from . import config as cfg
from .characters import CharacterPreset

# Attack frame data: (windup, active, recovery)
FRAMES = {
    "light": (4, 4, 9),
    "heavy": (13, 6, 21),
    "shoot": (4, 1, 11),
}

FIGHTER_W = 54.0
FIGHTER_H = 88.0


class Projectile:
    __slots__ = ("x", "y", "vx", "vy", "damage", "knockback", "owner_id",
                 "life", "color", "dead", "radius")

    def __init__(self, x, y, vx, vy, damage, knockback, owner_id, life, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.knockback = knockback
        self.owner_id = owner_id
        self.life = life
        self.color = color
        self.radius = 9.0
        self.dead = False

    def step(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.vy += cfg.GRAVITY * 0.14        # a gentle arc, not a laser
        self.life -= 1
        if (self.life <= 0 or self.x < cfg.BLAST_LEFT or self.x > cfg.BLAST_RIGHT
                or self.y > cfg.BLAST_BOTTOM):
            self.dead = True

    def as_dict(self) -> dict:
        return {"x": round(self.x, 1), "y": round(self.y, 1),
                "vx": round(self.vx, 2), "vy": round(self.vy, 2),
                "c": self.color, "o": self.owner_id}


class Fighter:
    def __init__(self, fid: int, name: str, preset: CharacterPreset,
                 script_file: str, slot: int, stocks: int):
        self.id = fid
        self.name = name
        self.preset = preset
        self.script_file = script_file
        self.slot = slot
        self.stats = preset.derived()

        self.width = FIGHTER_W
        self.height = FIGHTER_H
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1

        self.hp = self.stats["max_hp"]
        self.stocks = stocks
        self.alive = True
        self.eliminated = False
        self.on_ground = False
        self.jumps_left = cfg.MAX_JUMPS

        self.ammo = int(self.stats["magazine"])
        self.reload_timer = 0

        self.shield = self.stats["shield_max"]
        self.shielding = False
        self.shield_break_timer = 0

        self.dodge_timer = 0
        self.dodge_cooldown = 0
        self.dodge_dir = 0

        self.attack_type: str | None = None
        self.attack_timer = 0
        self.attack_total = 0
        self.attack_landed: set[int] = set()

        self.hitstun = 0
        self.invuln = cfg.INVULN_TICKS
        self.respawn_timer = 0
        self.drop_timer = 0
        self.offstage = False

        self.damage_dealt = 0.0
        self.kos = 0
        self.last_hit_by: int | None = None

        # Purely cosmetic, consumed by the renderer.
        self.fx_flash = 0
        self.fx_hit = 0

    # ------------------------------------------------------------- geometry
    @property
    def left(self) -> float:
        return self.x - self.width / 2

    @property
    def right(self) -> float:
        return self.x + self.width / 2

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def overlaps_point(self, px: float, py: float, pad: float = 0.0) -> bool:
        return (self.left - pad <= px <= self.right + pad
                and self.top - pad <= py <= self.bottom + pad)

    # ---------------------------------------------------------------- state
    def spawn_at(self, x: float, y: float) -> None:
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.hp = self.stats["max_hp"]
        self.ammo = int(self.stats["magazine"])
        self.reload_timer = 0
        self.shield = self.stats["shield_max"]
        self.shield_break_timer = 0
        self.shielding = False
        self.dodge_timer = self.dodge_cooldown = 0
        self.attack_type = None
        self.attack_timer = 0
        self.hitstun = 0
        self.invuln = cfg.INVULN_TICKS
        self.jumps_left = cfg.MAX_JUMPS
        self.alive = True
        self.respawn_timer = 0
        self.fx_flash = 0

    @property
    def busy(self) -> bool:
        """Locked out of new actions."""
        return self.hitstun > 0 or self.attack_timer > 0 or self.dodge_timer > 0

    # --------------------------------------------------------------- intent
    def apply_action(self, action, spawn_projectile) -> None:
        """Turn one Action into this frame's intent."""
        if not self.alive or self.hitstun > 0:
            return

        # Timers that gate everything else.
        if self.dodge_timer > 0:
            return

        if self.shield_break_timer > 0:
            self.shielding = False
        else:
            self.shielding = bool(action.shield) and self.attack_timer <= 0 and self.on_ground

        if action.dodge and self.dodge_cooldown <= 0 and self.attack_timer <= 0:
            self.dodge_timer = cfg.DODGE_TICKS
            self.dodge_cooldown = cfg.DODGE_COOLDOWN
            self.dodge_dir = int(math.copysign(1, action.move)) if action.move else self.facing
            self.vx = self.dodge_dir * self.stats["move_speed"] * 1.55
            self.shielding = False
            return

        if self.shielding:
            self.vx *= 0.6
            return

        # Movement.
        move = action.move
        if abs(move) > 0.08:
            self.facing = 1 if move > 0 else -1
            target = move * self.stats["move_speed"]
            accel = self.stats["accel"] * (1.0 if self.on_ground else cfg.AIR_CONTROL)
            self.vx += (target - self.vx) * min(1.0, accel)

        if action.drop and self.on_ground:
            self.drop_timer = 12

        if action.jump and self.jumps_left > 0 and self.attack_timer <= 0:
            mult = self.stats["jump_mult"]
            if self.on_ground:
                self.vy = cfg.JUMP_VELOCITY * mult
            else:
                self.vy = cfg.DOUBLE_JUMP_VELOCITY * mult
                if abs(move) > 0.3:
                    self.vx = move * self.stats["move_speed"]
            self.jumps_left -= 1
            self.on_ground = False

        if action.fastfall and not self.on_ground and self.vy > 0:
            self.vy = min(cfg.FASTFALL_SPEED, self.vy + 2.2)

        # Attacks.
        if action.attack and self.attack_timer <= 0:
            if action.attack == "shoot":
                self._try_shoot(action.aim, spawn_projectile)
            else:
                windup, active, recovery = FRAMES[action.attack]
                self.attack_type = action.attack
                self.attack_total = windup + active + recovery
                self.attack_timer = self.attack_total
                self.attack_landed = set()

    def _try_shoot(self, aim, spawn_projectile) -> None:
        if self.ammo <= 0 or self.reload_timer > 0:
            if self.ammo <= 0 and self.reload_timer <= 0:
                self.reload_timer = int(self.stats["reload_ticks"])
            return

        windup, active, recovery = FRAMES["shoot"]
        self.attack_type = "shoot"
        self.attack_total = windup + active + recovery
        self.attack_timer = self.attack_total
        self.attack_landed = set()

        dx, dy = (aim if aim else (float(self.facing), 0.0))
        if dx:
            self.facing = 1 if dx > 0 else -1
        speed = self.stats["shot_speed"]
        life = int(self.stats["shot_range"] / max(1.0, speed))

        self.ammo -= 1
        if self.ammo <= 0:
            self.reload_timer = int(self.stats["reload_ticks"])

        spawn_projectile(Projectile(
            x=self.x + self.facing * (self.width * 0.55),
            y=self.center_y - 6,
            vx=dx * speed, vy=dy * speed - 1.0,
            damage=self.stats["shot_damage"],
            knockback=self.stats["shot_knockback"],
            owner_id=self.id, life=life, color=self.preset.accent,
        ))

    # -------------------------------------------------------------- physics
    def physics_step(self, platforms) -> None:
        if not self.alive:
            return

        self.vy = min(cfg.MAX_FALL_SPEED, self.vy + cfg.GRAVITY)

        if self.on_ground and self.dodge_timer <= 0:
            self.vx *= cfg.GROUND_FRICTION
        elif not self.on_ground:
            self.vx *= cfg.AIR_FRICTION

        prev_bottom = self.bottom
        self.x += self.vx
        self.y += self.vy

        self.on_ground = False
        if self.vy >= 0 and self.drop_timer <= 0:
            for p in platforms:
                if not (p.left - self.width / 2 < self.x < p.right + self.width / 2):
                    continue
                if prev_bottom <= p.top + 2 and self.bottom >= p.top:
                    self.y = p.top - self.height
                    self.vy = 0.0
                    self.on_ground = True
                    self.jumps_left = cfg.MAX_JUMPS
                    break

        main = platforms[0]
        self.offstage = not (main.left - 40 < self.x < main.right + 40) or self.y > main.top + 120

    def tick_timers(self) -> None:
        for attr in ("hitstun", "invuln", "dodge_cooldown", "drop_timer",
                     "shield_break_timer", "fx_flash", "fx_hit"):
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, v - 1)

        if self.dodge_timer > 0:
            self.dodge_timer -= 1
            if self.dodge_timer == 0:
                self.vx *= 0.35

        if self.attack_timer > 0:
            self.attack_timer -= 1
            if self.attack_timer == 0:
                self.attack_type = None

        if self.reload_timer > 0:
            self.reload_timer -= 1
            if self.reload_timer == 0:
                self.ammo = int(self.stats["magazine"])

        if self.shielding:
            self.shield -= cfg.SHIELD_DRAIN
            if self.shield <= 0:
                self.shield = 0.0
                self.shielding = False
                self.shield_break_timer = 120
                self.hitstun = 60
        else:
            self.shield = min(self.stats["shield_max"],
                              self.shield + self.stats["shield_regen"])

    # --------------------------------------------------------------- combat
    @property
    def attack_phase(self) -> str | None:
        """'windup' | 'active' | 'recovery' for the current attack."""
        if not self.attack_type or self.attack_timer <= 0:
            return None
        windup, active, _ = FRAMES[self.attack_type]
        elapsed = self.attack_total - self.attack_timer
        if elapsed < windup:
            return "windup"
        if elapsed < windup + active:
            return "active"
        return "recovery"

    def hitbox(self) -> tuple[float, float, float] | None:
        """(x, y, radius) of the melee hitbox while it is active."""
        if self.attack_phase != "active" or self.attack_type not in ("light", "heavy"):
            return None
        reach = self.stats["melee_range"] * (1.0 if self.attack_type == "light" else 1.18)
        return (self.x + self.facing * reach * 0.62, self.center_y, reach * 0.55)

    @property
    def invulnerable(self) -> bool:
        if self.invuln > 0:
            return True
        # I-frames sit at the start of a dodge, so the timer is still high.
        return self.dodge_timer > cfg.DODGE_TICKS - cfg.DODGE_IFRAMES

    def take_hit(self, damage: float, knockback: float, from_x: float,
                 attacker_id: int | None) -> bool:
        """Apply a hit. Returns True if it connected (False if blocked/dodged)."""
        if not self.alive or self.invulnerable:
            return False

        if self.shielding and self.shield > 0:
            absorbed = damage * 1.9
            self.shield -= absorbed
            self.fx_flash = 8
            if self.shield <= 0:
                self.shield = 0.0
                self.shielding = False
                self.shield_break_timer = 120
                self.hitstun = 60
            return False

        self.hp = max(0.0, self.hp - damage)
        self.last_hit_by = attacker_id
        self.fx_hit = 10

        # Knockback grows as health drops - the low-health player is the one
        # who gets launched, which is what makes ring-outs happen.
        hp_pct = self.hp / self.stats["max_hp"] if self.stats["max_hp"] else 0.0
        scaling = 1.0 + (1.0 - hp_pct) * 1.85
        power = knockback * scaling / self.stats["weight"]

        direction = 1.0 if self.x >= from_x else -1.0
        self.vx = direction * power * 0.92
        self.vy = -abs(power) * 0.58 - 2.2
        self.hitstun = int(min(48, power * cfg.HITSTUN_PER_KB * 0.35) + 6)
        self.attack_timer = 0
        self.attack_type = None
        self.shielding = False
        return True

    # ----------------------------------------------------------- serialising
    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "char": self.preset.id,
            "charName": self.preset.name,
            "color": self.preset.color,
            "accent": self.preset.accent,
            "file": self.script_file,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),
            "w": self.width,
            "h": self.height,
            "facing": self.facing,
            "hp": round(self.hp, 1),
            "maxHp": self.stats["max_hp"],
            "stocks": self.stocks,
            "alive": self.alive,
            "eliminated": self.eliminated,
            "ammo": self.ammo,
            "maxAmmo": int(self.stats["magazine"]),
            "reloading": self.reload_timer > 0,
            "shield": round(self.shield, 1),
            "maxShield": self.stats["shield_max"],
            "shielding": self.shielding,
            "shieldBroken": self.shield_break_timer > 0,
            "dodging": self.dodge_timer > 0,
            "invuln": self.invuln > 0,
            "onGround": self.on_ground,
            "attack": self.attack_type,
            "phase": self.attack_phase,
            "hitstun": self.hitstun > 0,
            "flash": self.fx_flash,
            "hit": self.fx_hit,
            "kos": self.kos,
            "damage": round(self.damage_dealt, 1),
            "respawning": self.respawn_timer > 0,
        }
