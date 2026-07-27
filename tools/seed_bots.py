"""Fill /player with demo fighters so you can watch a full 8-way match.

    python tools/seed_bots.py 8      # write 8 bots
    python tools/seed_bots.py clear  # remove them again

These are hand-written stand-ins for what the lobby's LLM produces. They only
touch generated files (bot_*.py) and never the example_* references.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.config import PLAYER_DIR      # noqa: E402

AGGRESSIVE = '''\
NAME = "{name}"
CHARACTER = "{char}"

def decide(me, world):
    target = world.nearest_opponent()
    if target is None:
        return Action()
    if me.offstage:
        return Action(move=1 if me.x < world.stage.center_x else -1, jump=me.jumps_left > 0)
    gap = me.distance_to(target)
    toward = me.direction_to(target)
    if gap < 120:
        return Action(move=toward * 0.5, attack=HEAVY if target.stunned else LIGHT)
    if gap < 330 and me.ammo > 0:
        return Action(move=toward, attack=SHOOT, aim=(target.x - me.x, target.y - me.y))
    return Action(move=toward, jump=target.is_above(me) and me.jumps_left > 0)
'''

CAMPER = '''\
NAME = "{name}"
CHARACTER = "{char}"

def decide(me, world):
    target = world.nearest_opponent()
    if target is None:
        return Action()
    if me.offstage:
        return Action(move=1 if me.x < world.stage.center_x else -1, jump=me.jumps_left > 0)
    gap = me.distance_to(target)
    toward = me.direction_to(target)
    if world.incoming_projectiles(180) and me.shield > 30:
        return Action(shield=True)
    if gap < 150:
        if me.can_dodge:
            return Action(move=-toward, dodge=True)
        return Action(move=-toward * 0.8, attack=LIGHT)
    if me.ammo > 0:
        return Action(move=-toward * 0.25, attack=SHOOT, aim=(target.x - me.x, target.y - me.y))
    return Action(move=-toward * 0.6, shield=me.shield > 60)
'''

OPPORTUNIST = '''\
NAME = "{name}"
CHARACTER = "{char}"

def decide(me, world):
    prey = world.weakest_opponent()
    if prey is None:
        return Action()
    if me.offstage:
        return Action(move=1 if me.x < world.stage.center_x else -1, jump=me.jumps_left > 0)
    gap = me.distance_to(prey)
    toward = me.direction_to(prey)
    if me.hp_pct < 0.3 and gap < 260:
        return Action(move=-toward, jump=me.jumps_left > 0, shield=me.on_ground)
    if gap < 115:
        return Action(move=toward * 0.4, attack=HEAVY if prey.hp_pct < 0.5 else LIGHT)
    if gap < 360 and me.ammo > 0:
        return Action(move=toward * 0.7, attack=SHOOT, aim=(prey.x - me.x, prey.y - me.y))
    return Action(move=toward, jump=prey.is_above(me) and me.jumps_left > 0, fastfall=prey.is_below(me))
'''

BOTS = [
    ("bot_torch", "Torch", "ember", AGGRESSIVE),
    ("bot_pylon", "Pylon", "bulwark", CAMPER),
    ("bot_dart", "Dart", "zephyr", OPPORTUNIST),
    ("bot_anvil", "Anvil", "ironclad", AGGRESSIVE),
    ("bot_scope", "Scope", "quill", CAMPER),
    ("bot_whisper", "Whisper", "nyx", OPPORTUNIST),
    ("bot_edge", "Edge", "saber", AGGRESSIVE),
    ("bot_drift", "Drift", "vanta", OPPORTUNIST),
]


def clear() -> int:
    removed = 0
    for path in PLAYER_DIR.glob("bot_*.py"):
        path.unlink()
        removed += 1
    print(f"removed {removed} demo bots")
    return 0


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "6"
    if arg == "clear":
        return clear()

    count = max(1, min(8, int(arg)))
    clear()
    for slug, name, char, template in BOTS[:count]:
        (PLAYER_DIR / f"{slug}.py").write_text(
            template.format(name=name, char=char), encoding="utf-8")
        print(f"  wrote {slug}.py  {name} ({char})")
    print(f"{count} demo bots in {PLAYER_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
