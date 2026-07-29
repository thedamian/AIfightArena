"""Stage geometry: one main platform plus soft (pass-through) platforms."""
from __future__ import annotations

from dataclasses import dataclass

from . import config as cfg


@dataclass(frozen=True)
class Platform:
    x: float
    y: float
    width: float
    height: float
    passthrough: bool = False

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.width, "h": self.height,
                "soft": self.passthrough}


class Stage:
    """`Skyline Terrace` - a floating plaza above a city at dusk."""

    name = "Skyline Terrace"

    def __init__(self):
        ground_y = cfg.WORLD_H - 240
        main_w = 940
        main_x = (cfg.WORLD_W - main_w) / 2

        self.main = Platform(main_x, ground_y, main_w, 46)
        self.platforms: list[Platform] = [
            self.main,
            Platform(main_x + 60, ground_y - 190, 240, 20, passthrough=True),
            Platform(cfg.WORLD_W / 2 - 130, ground_y - 340, 260, 20, passthrough=True),
            Platform(main_x + main_w - 300, ground_y - 190, 240, 20, passthrough=True),
        ]

        # Where fighters drop in from at match start and after a KO.
        self.spawn_points: list[tuple[float, float]] = [
            (main_x + main_w * f, ground_y - 300)
            for f in (0.12, 0.30, 0.48, 0.66, 0.84, 0.21, 0.57, 0.75)
        ]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "platforms": [p.as_dict() for p in self.platforms],
            "world": {"w": cfg.WORLD_W, "h": cfg.WORLD_H},
            "blast": {"l": cfg.BLAST_LEFT, "r": cfg.BLAST_RIGHT,
                      "t": cfg.BLAST_TOP, "b": cfg.BLAST_BOTTOM},
        }

    def spawn_for(self, index: int) -> tuple[float, float]:
        return self.spawn_points[index % len(self.spawn_points)]

    def spread_spawns(self, count: int) -> list[tuple[float, float]]:
        """Return ground-level spawns distributed across the widest platform."""
        if count <= 0:
            return []

        # Keep fighters inside the platform edges while maximizing the minimum
        # horizontal distance between them. The tiny vertical offset lets the
        # first physics step settle each fighter onto the main platform.
        edge_padding = 42
        left = self.main.left + edge_padding
        right = self.main.right - edge_padding
        y = self.main.top - 88
        if count == 1:
            return [((left + right) / 2, y)]

        gap = (right - left) / (count - 1)
        return [(left + gap * index, y) for index in range(count)]
