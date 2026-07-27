"""The twelve selectable fighters.

Presets are stats only. Behaviour always comes from a script in /player.
Stat sliders run 1-10 and are converted to concrete simulation numbers by
`CharacterPreset.derived()` so designers can tune the sliders without touching
the physics code.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class CharacterPreset:
    id: str
    name: str
    title: str
    blurb: str
    color: str          # primary body colour
    accent: str         # trail / projectile colour

    speed: int          # ground + air movement
    strength: int       # melee damage and knockback
    health: int         # raw hit points
    reload_rate: int    # how fast the ranged weapon refills
    weight: int         # knockback resistance (heavier = harder to launch)
    jump: int           # jump height
    reach: int          # melee + projectile range
    shielding: int      # shield pool and regeneration

    def derived(self) -> dict:
        """Concrete numbers the simulation actually uses."""
        return {
            "max_hp": float(self.health),
            "move_speed": 3.6 + self.speed * 0.46,
            "accel": 0.55 + self.speed * 0.075,
            "jump_mult": 0.82 + self.jump * 0.042,
            "weight": 0.62 + self.weight * 0.076,
            "melee_damage": 4.0 + self.strength * 1.15,
            "heavy_damage": 8.0 + self.strength * 2.05,
            "melee_range": 46.0 + self.reach * 5.2,
            "melee_knockback": 5.0 + self.strength * 0.72,
            "heavy_knockback": 11.0 + self.strength * 1.28,
            "shot_damage": 3.2 + self.strength * 0.62 + self.reach * 0.34,
            "shot_speed": 11.0 + self.reach * 0.92,
            "shot_range": 300.0 + self.reach * 62.0,
            "shot_knockback": 3.0 + self.strength * 0.38,
            "magazine": max(1, round(1 + self.reload_rate * 0.65)),
            "reload_ticks": int(150 / (0.8 + self.reload_rate * 0.52)),
            "shield_max": 60.0 + self.shielding * 7.0,
            "shield_regen": 0.25 + self.shielding * 0.055,
        }

    def public(self) -> dict:
        d = asdict(self)
        d["derived"] = {k: round(v, 2) for k, v in self.derived().items()}
        return d


ROSTER: list[CharacterPreset] = [
    CharacterPreset(
        id="vanta", name="Vanta", title="The Even Blade",
        blurb="No weakness, no gimmick. Good at everything, best at nothing.",
        color="#5b8cff", accent="#9fc0ff",
        speed=5, strength=5, health=115, reload_rate=5, weight=5, jump=5, reach=5, shielding=5,
    ),
    CharacterPreset(
        id="kindle", name="Kindle", title="Spark Runner",
        blurb="Gets in your face and never leaves. Fragile if you can catch her.",
        color="#ff7a3d", accent="#ffd08a",
        speed=8, strength=5, health=95, reload_rate=6, weight=3, jump=7, reach=4, shielding=4,
    ),
    CharacterPreset(
        id="bulwark", name="Bulwark", title="Standing Wall",
        blurb="Enormous health pool and a shield that refuses to break.",
        color="#4a9d7f", accent="#a8e6cf",
        speed=3, strength=6, health=165, reload_rate=3, weight=9, jump=3, reach=5, shielding=9,
    ),
    CharacterPreset(
        id="zephyr", name="Zephyr", title="Hairline Margin",
        blurb="The fastest thing on the stage. One clean hit and it's over.",
        color="#39e0d8", accent="#c2fffb",
        speed=10, strength=7, health=80, reload_rate=6, weight=2, jump=9, reach=4, shielding=2,
    ),
    CharacterPreset(
        id="ironclad", name="Ironclad", title="Slow Verdict",
        blurb="Every heavy swing is a stock. Landing one is the hard part.",
        color="#8d8fa6", accent="#d7d9e8",
        speed=2, strength=10, health=150, reload_rate=2, weight=10, jump=3, reach=6, shielding=6,
    ),
    CharacterPreset(
        id="nyx", name="Nyx", title="Quiet Exit",
        blurb="Burst damage from bad angles. Punishes anyone who whiffs.",
        color="#a25bff", accent="#e0c2ff",
        speed=8, strength=8, health=88, reload_rate=5, weight=3, jump=8, reach=5, shielding=3,
    ),
    CharacterPreset(
        id="volt", name="Volt", title="Full Auto",
        blurb="Reloads before you finish blinking. Death by a thousand pellets.",
        color="#ffd23d", accent="#fff3b0",
        speed=6, strength=4, health=105, reload_rate=10, weight=4, jump=6, reach=6, shielding=4,
    ),
    CharacterPreset(
        id="terra", name="Terra", title="Long Winter",
        blurb="Wins by still being there. Grinds matches into attrition.",
        color="#b07a4a", accent="#e8c9a5",
        speed=4, strength=6, health=145, reload_rate=4, weight=8, jump=4, reach=5, shielding=7,
    ),
    CharacterPreset(
        id="quill", name="Quill", title="Across The Stage",
        blurb="Hits from the other blast zone. Helpless up close.",
        color="#5fd35f", accent="#c6f5c6",
        speed=5, strength=7, health=92, reload_rate=2, weight=4, jump=6, reach=10, shielding=3,
    ),
    CharacterPreset(
        id="ember", name="Ember", title="Close Weather",
        blurb="Mid-range pressure with just enough beef to trade.",
        color="#ff4f6d", accent="#ffb3c1",
        speed=6, strength=7, health=110, reload_rate=6, weight=5, jump=6, reach=6, shielding=5,
    ),
    CharacterPreset(
        id="saber", name="Saber", title="Zero Range",
        blurb="Melee specialist with reach for days. Barely carries a gun.",
        color="#ff9ff3", accent="#ffe0fb",
        speed=7, strength=9, health=100, reload_rate=1, weight=4, jump=7, reach=8, shielding=4,
    ),
    CharacterPreset(
        id="aegis", name="Aegis", title="Counter-Clock",
        blurb="Blocks everything, then makes you regret the swing.",
        color="#4fc3ff", accent="#c4ecff",
        speed=5, strength=6, health=125, reload_rate=4, weight=7, jump=5, reach=6, shielding=10,
    ),
]

BY_ID: dict[str, CharacterPreset] = {c.id: c for c in ROSTER}


def get(character_id: str) -> CharacterPreset | None:
    return BY_ID.get((character_id or "").strip().lower())


def roster_public() -> list[dict]:
    return [c.public() for c in ROSTER]
