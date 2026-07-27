"""Fireflies: special targets that spawn periodically and grant bonus gold.

Catching one (tap or auto) gives a gold windfall scaled by the combo,
the firefly multipliers (skill tree + pets), and the current combo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from utils import rng


@dataclass
class Firefly:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    hue: int = 60


def spawn_firefly(x: float, y: float, *, base_size: float = 8.0,
                  size_bonus: float = 0.0) -> Firefly:
    ang = rng().uniform(0, math.tau)
    return Firefly(
        x=x, y=y,
        vx=math.cos(ang) * rng().uniform(20, 60),
        vy=math.sin(ang) * rng().uniform(20, 60),
        life=8.0, max_life=8.0,
        size=base_size * (1.0 + size_bonus), hue=60,
    )


def update_fireflies(fireflies: list[Firefly], dt: float) -> None:
    for f in fireflies:
        f.x += f.vx * dt
        f.y += f.vy * dt
        # Bounce off the road bounds (roughly).
        if f.y < 100 or f.y > 400:
            f.vy *= -1
        f.life -= dt
    fireflies[:] = [f for f in fireflies if f.life > 0]


def catch_firefly(firefly: Firefly, *, base_gold: float, combo_mult: float,
                  firefly_gold_mult: float, firefly_value_mult: float) -> float:
    """Return the gold earned from catching a firefly."""
    gold = base_gold * firefly_gold_mult * firefly_value_mult * combo_mult
    return gold
