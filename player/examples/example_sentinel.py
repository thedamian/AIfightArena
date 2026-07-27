"""Example fighter script.

Files in this folder are hot-reloaded by the running match: save a change and
the fighter's tactics update mid-fight. Delete the file and the fighter leaves.

Contract:
    NAME       display name (string)
    CHARACTER  one of the twelve preset ids
    decide(me, world) -> Action

The lobby writes files here automatically from what players type in the web UI.
This one is hand-written and is here as a reference.
"""

NAME = "Sentinel"
CHARACTER = "aegis"

CLOSE = 130.0
POKE = 260.0


def decide(me, world):
    target = world.nearest_opponent()
    if target is None:
        return Action()

    # Recover first, argue later.
    if me.offstage or me.x < world.stage.ground_left or me.x > world.stage.ground_right:
        toward = 1 if me.x < world.stage.center_x else -1
        return Action(move=toward, jump=me.vy > 1 and me.jumps_left > 0)

    gap = me.distance_to(target)
    toward = me.direction_to(target)

    # Block incoming fire when it is worth blocking.
    if world.incoming_projectiles(200) and me.shield > 25 and me.on_ground:
        return Action(shield=True)

    # Punish anyone winding up next to us.
    if gap < CLOSE and target.attacking and me.can_dodge:
        return Action(move=-toward, dodge=True)

    if gap < CLOSE:
        heavy = target.hp_pct < 0.4 or target.stunned
        return Action(move=toward * 0.4, attack=HEAVY if heavy else LIGHT)

    if gap < POKE and me.ammo > 0:
        aim = (target.x - me.x, target.y - me.y)
        return Action(move=toward * 0.6, attack=SHOOT, aim=aim)

    # Close the gap, hopping over gaps in the floor.
    want_jump = target.is_above(me) and me.jumps_left > 0 and me.on_ground
    return Action(move=toward, jump=want_jump)
