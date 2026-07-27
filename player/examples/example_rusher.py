"""A second reference fighter, so the arena has someone to fight.

Aggressive, forward-biased, mostly melee. Deliberately simple.
"""

NAME = "Rusher"
CHARACTER = "kindle"


def decide(me, world):
    target = world.nearest_opponent()
    if target is None:
        return Action()

    # Never chase off the edge.
    if me.offstage:
        home = 1 if me.x < world.stage.center_x else -1
        return Action(move=home, jump=me.jumps_left > 0)

    gap = me.distance_to(target)
    toward = me.direction_to(target)
    beyond_edge = target.x < world.stage.ground_left or target.x > world.stage.ground_right

    if gap < 110:
        if target.shielding and me.can_dodge:
            return Action(move=toward, dodge=True)
        return Action(move=toward * 0.5, attack=HEAVY if target.stunned else LIGHT)

    if beyond_edge and gap < 300:
        return Action(move=toward * 0.3, attack=SHOOT, aim=(target.x - me.x, target.y - me.y))

    if gap < 340 and me.ammo > 0 and random.chance(0.4):
        return Action(move=toward, attack=SHOOT, aim=(target.x - me.x, target.y - me.y))

    return Action(
        move=toward,
        jump=(target.is_above(me) or me.vy > 6) and me.jumps_left > 0,
        fastfall=target.is_below(me),
    )
