# /player — the fighter scripts

Every fighter in the arena is one `.py` file in this folder. The running game
watches the folder and reacts within about a second:

| you do this          | the game does this                               |
|----------------------|--------------------------------------------------|
| add a file           | a new fighter walks into the match               |
| edit a file          | that fighter's tactics swap out mid-fight        |
| delete a file        | that fighter leaves                              |
| write a broken file  | the fighter keeps its last working brain         |

Files starting with `_` are ignored. `examples/` is a subfolder, so nothing in
it is loaded — copy a file up one level to put it in the fight.

Normally you do not write these by hand: the lobby at `http://<host>:8100`
generates them from what players type. `tools/seed_bots.py` writes a few
hand-made ones if you want a match without the lobby.

## The contract

```python
NAME = "Sentinel"        # display name, shown above the fighter
CHARACTER = "aegis"      # one of the twelve preset ids

def decide(me, world):
    return Action(move=1, attack=LIGHT)
```

`decide` is called about 20 times a second. It must return an `Action` (or a
dict with the same keys). Returning `None` means "do nothing this frame".

### Characters

`vanta` `kindle` `bulwark` `zephyr` `ironclad` `nyx` `volt` `terra` `quill`
`ember` `saber` `aegis`

The id you pick decides every number about your fighter — speed, health,
damage, reload rate, weight, reach, shield. Behaviour is the only thing the
script controls. An unknown id falls back to `vanta`.

### Action

| field      | type          | meaning                                          |
|------------|---------------|--------------------------------------------------|
| `move`     | -1.0 … 1.0    | walk left/right                                  |
| `jump`     | bool          | jump; works twice (double jump)                  |
| `attack`   | `LIGHT` / `HEAVY` / `SHOOT` / `None` | fast poke / big knockback / ranged shot |
| `aim`      | `(dx, dy)`    | direction for `SHOOT`                            |
| `shield`   | bool          | block; drains shield, ground only                |
| `dodge`    | bool          | roll with brief invulnerability, has a cooldown  |
| `fastfall` | bool          | fall faster while airborne                       |
| `drop`     | bool          | fall through a soft platform                     |

### What you can read

`me` and each opponent expose:

```
x, y            position — y grows DOWNWARD, so a smaller y is higher up
vx, vy          velocity
hp, max_hp, hp_pct, stocks, alive
facing          1 right, -1 left
on_ground, jumps_left, offstage
ammo, max_ammo, reloading, reload_progress
shield, max_shield, shielding, shield_broken
dodging, can_dodge, invulnerable, stunned, attacking
distance_to(o), dx_to(o), dy_to(o), direction_to(o), is_above(o), is_below(o)
```

`me.stats` additionally holds the concrete numbers for your character
(read-only).

`world` exposes:

```
me, opponents, living_opponents
nearest_opponent(), weakest_opponent(), strongest_opponent()   -> may be None
projectiles, incoming_projectiles(radius=260)
platforms      x, y, width, height, left, right, center_x, top, passthrough
stage          width, height, center_x, ground_y, ground_left, ground_right,
               blast_left, blast_right, blast_top, blast_bottom
threat_level() 0..1
tick, time
```

Also available: `math` (plus `math.clamp`, `math.sign`, `math.lerp`) and
`random` (plus `random.chance(p)`).

## The sandbox

These files are generated from text typed into a public webpage, so they run
under real restrictions. Rejected outright:

- `import` of anything
- `while` loops (use `for` over a range or list)
- `eval`, `exec`, `open`, `getattr`, `setattr`, `globals`, `locals`, `__import__`
- any name or attribute starting with `_`
- decorators, generators, `async`, `with`, `global`/`nonlocal`
- files over 24 KB, or without a `decide` function

At runtime each `decide()` call gets a line and time budget. Overrun it and the
call is aborted and the fighter idles that frame; a script that fails 25 times
in a row is switched off and shown as broken on the main screen.

Module-level state persists between calls, so a dict is a fine place to
remember things:

```python
MEMORY = {"last_seen": 0}

def decide(me, world):
    MEMORY["last_seen"] = world.tick
    ...
```
