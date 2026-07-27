"""Headless match runner: plays a full match in the terminal.

    python tools/smoke_match.py [max_seconds]

Useful for balance tuning and for checking a script in /player actually works
without opening a browser.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena import config as cfg           # noqa: E402
from arena.match import Match, VICTORY    # noqa: E402


def main() -> int:
    limit_seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    match = Match()

    print(f"stage: {match.stage.name}")
    print(f"loaded scripts: {[s['file'] for s in match.loader.status()]}")
    for f in match.fighters.values():
        print(f"  {f.name:<14} {f.preset.name:<10} hp={f.stats['max_hp']:.0f} "
              f"spd={f.stats['move_speed']:.1f} mag={int(f.stats['magazine'])}")
    if len(match.fighters) < 2:
        print("need at least 2 scripts in /player")
        return 1

    seen = 0
    max_ticks = int(limit_seconds * cfg.TICK_RATE)
    for _ in range(max_ticks):
        match.step()
        while seen < len(match.events):
            print(f"  [{match.tick // cfg.TICK_RATE:>3}s] {match.events[seen]['text']}")
            seen += 1
        if match.state == VICTORY:
            break

    print(f"\nfinal state: {match.state} after {match.tick / cfg.TICK_RATE:.1f}s")
    for f in sorted(match.fighters.values(), key=lambda f: (-f.stocks, -f.kos)):
        print(f"  {f.name:<14} stocks={f.stocks} kos={f.kos} dmg={f.damage_dealt:6.1f} "
              f"hp={f.hp:5.1f} {'OUT' if f.eliminated else ''}")

    errors = [s for s in match.loader.status() if not s["ok"]]
    for e in errors:
        print(f"  script error in {e['file']}: {e['error']}")

    if match.state != VICTORY:
        print("no winner within the time limit")
        return 2
    print(f"winner: {match.winner_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
