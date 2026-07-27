"""Sandbox escape attempts. Every case here must be rejected or contained.

    python tools/test_sandbox.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.sandbox import ScriptError, load_script, validate_source   # noqa: E402

MUST_REJECT = {
    "import os": "import os\ndef decide(me, world):\n    return None\n",
    "from x import y": "from subprocess import run\ndef decide(me, world):\n    return None\n",
    "__import__": "def decide(me, world):\n    return __import__('os')\n",
    "eval": "def decide(me, world):\n    return eval('1+1')\n",
    "exec": "def decide(me, world):\n    exec('x=1')\n",
    "open file": "def decide(me, world):\n    return open('/etc/passwd').read()\n",
    "dunder class walk": "def decide(me, world):\n    return me.__class__.__mro__\n",
    "dunder globals": "def decide(me, world):\n    return decide.__globals__\n",
    "getattr bypass": "def decide(me, world):\n    return getattr(me, 'x')\n",
    "while loop": "def decide(me, world):\n    while True:\n        pass\n",
    "with block": "def decide(me, world):\n    with open('x') as f:\n        pass\n",
    "async": "async def decide(me, world):\n    return None\n",
    "generator": "def decide(me, world):\n    yield 1\n",
    "global": "def decide(me, world):\n    global x\n    x = 1\n",
    "no decide": "NAME = 'x'\nCHARACTER = 'vanta'\n",
    "builtins access": "def decide(me, world):\n    return __builtins__\n",
    "private attr": "def decide(me, world):\n    return world._match\n",
    "decorator": "def wrap(f):\n    return f\n@wrap\ndef decide(me, world):\n    return None\n",
    "syntax error": "def decide(me, world)\n    return None\n",
    "oversized": "X = '" + "a" * 30_000 + "'\ndef decide(me, world):\n    return None\n",
}

MUST_ACCEPT = {
    "plain": "NAME='A'\nCHARACTER='vanta'\ndef decide(me, world):\n    return Action(move=1)\n",
    "for loop": (
        "NAME='B'\nCHARACTER='volt'\n"
        "def decide(me, world):\n"
        "    best = None\n"
        "    for o in world.opponents:\n"
        "        if best is None or o.hp < best.hp:\n"
        "            best = o\n"
        "    return Action(move=me.direction_to(best) if best else 0)\n"
    ),
    "math + random": (
        "NAME='C'\nCHARACTER='nyx'\n"
        "def decide(me, world):\n"
        "    a = math.sqrt(16) + math.clamp(5, 0, 3)\n"
        "    return Action(move=1 if random.chance(0.5) else -1, jump=a > 0)\n"
    ),
    "module state": (
        "NAME='D'\nCHARACTER='terra'\nMEMORY = {'seen': 0}\n"
        "def decide(me, world):\n"
        "    MEMORY['seen'] = MEMORY['seen'] + 1\n"
        "    return Action(move=0.5, shield=MEMORY['seen'] % 2 == 0)\n"
    ),
    "dict return": "NAME='E'\nCHARACTER='saber'\ndef decide(me, world):\n    return {'move': 1, 'attack': 'light'}\n",
}


def main() -> int:
    failures = []

    for label, source in MUST_REJECT.items():
        problems = validate_source(source)
        if not problems:
            try:
                load_script(Path("evil.py"), source)
                failures.append(f"NOT REJECTED: {label}")
                continue
            except ScriptError:
                pass
        print(f"  blocked  {label:<20} {(problems or ['load failed'])[0][:70]}")

    for label, source in MUST_ACCEPT.items():
        try:
            script = load_script(Path(f"{label}.py"), source)
        except ScriptError as e:
            failures.append(f"WRONGLY REJECTED: {label}: {e}")
            continue
        print(f"  accepted {label:<20} name={script.name} char={script.character_id}")

    # Runtime containment: a legal-but-hostile for loop must be cut off, not hang.
    burner = load_script(Path("burn.py"), (
        "NAME='F'\nCHARACTER='vanta'\n"
        "def decide(me, world):\n"
        "    total = 0\n"
        "    for i in range(10000000):\n"
        "        total = total + i\n"
        "    return Action(move=1)\n"
    ))
    action = burner.call(None, None)
    if burner.error is None:
        failures.append("NOT CONTAINED: runaway for loop was not interrupted")
    else:
        print(f"  contained runaway loop     {burner.error[:60]}")
    if action.move != 0.0:
        failures.append("runaway script should fall back to idle")

    print()
    for f in failures:
        print(f"  !! {f}")
    print(f"{len(MUST_REJECT) + len(MUST_ACCEPT) + 1} checks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
