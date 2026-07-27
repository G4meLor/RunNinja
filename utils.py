"""Misc small utilities: timing helpers, RNG wrapper, id helpers.

Kept dependency-free so any module can import it safely.
"""
from __future__ import annotations

import hashlib
import random
from typing import Sequence, TypeVar

T = TypeVar("T")


# A single, deterministic-per-run RNG.  We re-seed from the clock at
# startup but expose a stable object so other modules don't reach into
# the global ``random`` state.
_rng = random.Random()


def seed(s: int | None = None) -> None:
    _rng.seed(s)


def rng() -> random.Random:
    return _rng


def rand_float(lo: float, hi: float) -> float:
    return _rng.uniform(lo, hi)


def rand_int(lo: int, hi: int) -> int:
    return _rng.randint(lo, hi)


def chance(p: float) -> bool:
    return _rng.random() < p


def weighted_choice(items: Sequence[T], weights: Sequence[float]) -> T:
    return _rng.choices(items, weights=weights, k=1)[0]


def stable_id(*parts: object) -> str:
    """A short, stable hex id from arbitrary parts — for save keys."""
    h = hashlib.md5(repr(tuple(parts)).encode()).hexdigest()
    return h[:8]


class Timer:
    """A simple countdown timer that supports pause/resume."""

    __slots__ = ("duration", "elapsed", "running")

    def __init__(self, duration: float) -> None:
        self.duration = duration
        self.elapsed = 0.0
        self.running = True

    def tick(self, dt: float) -> None:
        if self.running:
            self.elapsed += dt

    @property
    def done(self) -> bool:
        return self.elapsed >= self.duration

    @property
    def pct(self) -> float:
        return 1.0 if self.duration <= 0 else min(1.0, self.elapsed / self.duration)

    def reset(self) -> None:
        self.elapsed = 0.0
        self.running = True


class Cooldown:
    """A repeating cooldown; ``ready`` is True once it has elapsed."""

    __slots__ = ("period", "_t")

    def __init__(self, period: float) -> None:
        self.period = period
        self._t = 0.0

    def tick(self, dt: float) -> bool:
        self._t += dt
        if self._t >= self.period:
            self._t -= self.period
            return True
        return False

    def fraction(self) -> float:
        return self._t / self.period if self.period > 0 else 0.0


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def format_number(n: float) -> str:
    """Compact integer formatting: 1.5k, 2.3M, 4.7B, ... up to absurd scale."""
    if n is None:
        return "0"
    n = float(n)
    if abs(n) < 1000:
        return f"{int(round(n))}"
    units = ["", "k", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]
    u = 0
    while abs(n) >= 1000 and u < len(units) - 1:
        n /= 1000.0
        u += 1
    if abs(n) >= 100:
        return f"{n:.0f}{units[u]}"
    return f"{n:.1f}{units[u]}"


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def darken(color: tuple[int, int, int], factor: float = 0.7) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def lighten(color: tuple[int, int, int], factor: float = 1.3) -> tuple[int, int, int]:
    return (min(255, int(color[0] * factor)),
            min(255, int(color[1] * factor)),
            min(255, int(color[2] * factor)))
