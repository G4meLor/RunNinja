"""Polished particle system for Tap Ninja.

A drop-in upgrade of ``assets.ParticleSystem`` with richer particle
shapes, color fade over life, gravity variation, additive-blended
glows, ring bursts, spark bursts, and an optional screen-edge bounce.
**Pooled** — no per-frame allocations in the hot loop after warm-up.

Shapes (``shape=`` kwarg on every spawner):
  * ``"circle"`` — soft disc (default; matches the old look)
  * ``"spark"``  — elongated diamond aligned with the velocity vector
                  (good for crits / impact lines)
  * ``"star"``   — 5-point star (good for skill AOE / pickups)

Drawing:
  * ``glow=True`` particles blit with ``pygame.BLEND_RGBA_ADD`` for the
    neon-arcade additive look; non-glow particles blit normally.
  * Alpha fades to 0 over ``life``; the color optionally lerps toward
    ``fade_color`` (default: alpha-only fade).

Pooling:
  * Dead particles return to a free list and are reused by the next
    ``burst`` / ``burst_ring`` / ``spark_burst`` / ``trail`` — no
    ``Particle`` is allocated after warm-up. ``update`` compacts the
    active list in place (swap-and-pop), so there is no per-frame list
    comprehension either. The per-(shape, size) scratch surfaces used
    for drawing are cached lazily and reused forever.

API (compatible with ``assets.ParticleSystem``):

  burst(x, y, color, count=12, speed=120, life=0.4, size=3, ...)
  trail(x, y, color, count=1, size=2)
  burst_ring(x, y, color, radius=60, count=24, life=0.5, ...)
  spark_burst(x, y, color, count=10, speed=200, life=0.3, ...)
  update(dt)
  draw(surf)
  clear()
  active  -> bool
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import pygame

import config as cfg
from utils import rng, lerp_color


# ---------------------------------------------------------------------------
# Shape constants  (string IDs keep the public API pickle-friendly)
# ---------------------------------------------------------------------------
SHAPE_CIRCLE = "circle"
SHAPE_SPARK = "spark"
SHAPE_STAR = "star"

# Default screen bounds for the bounce option (the whole window).
_DEFAULT_BOUNDS: Tuple[int, int, int, int] = (0, 0, cfg.WINDOW_W, cfg.WINDOW_H)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _star_points(cx: float, cy: float, outer: float, inner: float,
                 n: int = 5, rot: float = 0.0) -> list[tuple[float, float]]:
    """Vertex list for an n-point star, rotated by ``rot`` radians."""
    pts = []
    step = math.pi / n
    for i in range(n * 2):
        r = outer if (i & 1) == 0 else inner
        a = rot + i * step
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


# ---------------------------------------------------------------------------
# Particle  (pooled; __slots__ for cache friendliness)
# ---------------------------------------------------------------------------
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life",
                 "color", "fade_color", "size", "gravity",
                 "shape", "glow", "spin", "spin_speed",
                 "bounce", "damping", "alive")

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.life = 0.0
        self.max_life = 0.0
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.fade_color: Optional[Tuple[int, int, int]] = None
        self.size = 3
        self.gravity = 0.0
        self.shape = SHAPE_CIRCLE
        self.glow = False
        self.spin = 0.0
        self.spin_speed = 0.0
        self.bounce = False
        self.damping = 0.6
        self.alive = False

    def reset(self, x: float, y: float, vx: float, vy: float,
              life: float, color: Tuple[int, int, int], *,
              size: int = 3, gravity: float = 0.0,
              shape: str = SHAPE_CIRCLE, glow: bool = False,
              fade_color: Optional[Tuple[int, int, int]] = None,
              spin: float = 0.0, spin_speed: float = 0.0,
              bounce: bool = False, damping: float = 0.6) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.fade_color = fade_color
        self.size = size
        self.gravity = gravity
        self.shape = shape
        self.glow = glow
        self.spin = spin
        self.spin_speed = spin_speed
        self.bounce = bounce
        self.damping = damping
        self.alive = True


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class ParticleSystem2:
    """Pooled, shape-aware particle system with additive glow.

    Construct once (e.g. in ``Game.__init__`` as the sole particle system),
    call the spawners on events, then ``update(dt)`` and ``draw(surf)``
    every frame.
    """

    # Default active-particle cap. Generous enough that the default tier
    # never visually clips a combat peak, but bounded so a runaway spawn
    # loop can't balloon the active list. Task 10's render-tier will
    # rebind this per quality tier (low/med/high); for now it is a fixed
    # max.
    DEFAULT_MAX_PARTICLES = 600

    def __init__(self, *, bounce: bool = False,
                 bounce_bounds: Optional[Tuple[int, int, int, int]] = None,
                 default_glow: bool = False,
                 max_particles: Optional[int] = None) -> None:
        self._active: list[Particle] = []
        self._pool: list[Particle] = []
        self._scratch_cache: dict[tuple, pygame.Surface] = {}
        # System-wide defaults; per-call kwargs override these.
        self.bounce = bounce
        self.bounce_bounds: Tuple[int, int, int, int] = (
            bounce_bounds if bounce_bounds is not None else _DEFAULT_BOUNDS)
        self.default_glow = default_glow
        self.max_particles: int = (
            max_particles if max_particles is not None
            else self.DEFAULT_MAX_PARTICLES)

    # ------------------------------------------------------------------
    # Pool plumbing
    # ------------------------------------------------------------------
    def _acquire(self) -> Particle:
        if self._pool:
            return self._pool.pop()
        return Particle()

    def _release(self, p: Particle) -> None:
        p.alive = False
        self._pool.append(p)

    def _spawn(self, count: int) -> list[Particle]:
        """Acquire up to ``count`` particles without exceeding the cap.

        Returns the list of freshly acquired (not yet reset) particles.
        Spawners reset each one with the per-call parameters. The cap
        keeps the active list bounded per quality tier; once it is hit,
        further spawns in the same call are dropped (the visual stays
        readable — a saturated burst just renders fewer shards).
        """
        room = self.max_particles - len(self._active)
        if room <= 0:
            return []
        n = count if count < room else room
        out: list[Particle] = []
        for _ in range(n):
            out.append(self._acquire())
        self._active.extend(out)
        return out

    def _scratch(self, shape: str, bucket: int) -> pygame.Surface:
        """A cached SRCALPHA scratch for (shape, size-bucket) drawing."""
        key = (shape, bucket)
        s = self._scratch_cache.get(key)
        if s is None:
            if shape == SHAPE_CIRCLE:
                side = bucket * 2 + 2
            elif shape == SHAPE_STAR:
                side = int(bucket * 3.4) + 2
            else:  # spark — room for the elongated diamond in any orientation
                side = int(bucket * 4.6) + 2
            side = max(4, side)
            s = pygame.Surface((side, side), pygame.SRCALPHA)
            self._scratch_cache[key] = s
        return s

    # ------------------------------------------------------------------
    # Spawners  (all kwargs beyond the old signature are keyword-only)
    # ------------------------------------------------------------------
    def burst(self, x: float, y: float, color: Tuple[int, int, int],
              count: int = 12, speed: float = 120, life: float = 0.4,
              size: int = 3, *, shape: str = SHAPE_CIRCLE,
              gravity: float = 200.0, glow: Optional[bool] = None,
              fade_color: Optional[Tuple[int, int, int]] = None,
              bounce: Optional[bool] = None, damping: float = 0.6) -> None:
        """Radial burst — compatible with ``assets.ParticleSystem.burst``.

        Defaults match the old system (gravity=200, plain circles, alpha
        fade). Pass ``shape=SHAPE_SPARK`` / ``SHAPE_STAR``, ``glow=True``,
        ``fade_color=...`` or ``bounce=True`` to enrich it.
        """
        if glow is None:
            glow = self.default_glow
        if bounce is None:
            bounce = self.bounce
        r = rng()
        for p in self._spawn(count):
            ang = r.uniform(0, math.tau)
            sp = r.uniform(speed * 0.4, speed)
            p.reset(x, y, math.cos(ang) * sp, math.sin(ang) * sp,
                    life * r.uniform(0.6, 1.2), color,
                    size=size, gravity=gravity, shape=shape, glow=glow,
                    fade_color=fade_color, bounce=bounce, damping=damping,
                    spin=r.uniform(0, math.tau),
                    spin_speed=r.uniform(-6.0, 6.0))

    def trail(self, x: float, y: float, color: Tuple[int, int, int],
              count: int = 1, size: int = 2, *, shape: str = SHAPE_CIRCLE,
              life: float = 0.3, glow: Optional[bool] = None,
              fade_color: Optional[Tuple[int, int, int]] = None) -> None:
        """Soft trail puff — compatible with ``assets.ParticleSystem.trail``."""
        if glow is None:
            glow = self.default_glow
        r = rng()
        for p in self._spawn(count):
            p.reset(x + r.uniform(-2, 2), y + r.uniform(-2, 2),
                    r.uniform(-10, 10), r.uniform(-10, 10),
                    life, color, size=size, gravity=0.0, shape=shape,
                    glow=glow, fade_color=fade_color,
                    spin=r.uniform(0, math.tau),
                    spin_speed=r.uniform(-2.0, 2.0))

    def burst_ring(self, x: float, y: float, color: Tuple[int, int, int],
                   radius: float = 60, count: int = 24, life: float = 0.5,
                   size: int = 3, *, shape: str = SHAPE_STAR,
                   gravity: float = 0.0, expand: float = 80.0,
                   glow: Optional[bool] = None,
                   fade_color: Optional[Tuple[int, int, int]] = None,
                   spin: bool = True) -> None:
        """Particles placed evenly on a circle of ``radius`` around (x, y).

        Each particle gets a small outward velocity (``expand``) so the
        ring swells slightly then settles — good for skill AOE markers
        and pickup pops. Stars by default so the ring reads as a sparkle
        halo, not a dotted line.
        """
        if glow is None:
            glow = self.default_glow
        r = rng()
        # Divide by the *actual* spawned count, not the requested ``count``,
        # so the angles span the full circle even when the cap clips
        # (otherwise the shards bunch into a wedge).
        spawned = self._spawn(count)
        n = len(spawned)
        for i, p in enumerate(spawned):
            ang = (i / n) * math.tau + r.uniform(-0.05, 0.05) if n else 0.0
            sp = expand * r.uniform(0.7, 1.0)
            px = x + math.cos(ang) * radius
            py = y + math.sin(ang) * radius
            p.reset(px, py, math.cos(ang) * sp, math.sin(ang) * sp,
                    life * r.uniform(0.8, 1.2), color,
                    size=size, gravity=gravity, shape=shape, glow=glow,
                    fade_color=fade_color,
                    spin=(ang if spin else r.uniform(0, math.tau)),
                    spin_speed=r.uniform(-4.0, 4.0))

    def spark_burst(self, x: float, y: float, color: Tuple[int, int, int],
                    count: int = 10, speed: float = 200, life: float = 0.3,
                    size: int = 4, *, gravity: float = 120.0,
                    glow: Optional[bool] = None,
                    fade_color: Optional[Tuple[int, int, int]] = None,
                    bounce: Optional[bool] = None,
                    damping: float = 0.6) -> None:
        """Elongated spark burst — the crit / impact-line special.

        Each spark is a ``SHAPE_SPARK`` diamond aligned with its velocity,
        so the burst reads as a starburst of streaks rather than dots.
        Defaults to ``glow=True`` so crits pop additively over the scene.
        """
        if glow is None:
            glow = True if self.default_glow is False else self.default_glow
        if bounce is None:
            bounce = self.bounce
        r = rng()
        for p in self._spawn(count):
            ang = r.uniform(0, math.tau)
            sp = r.uniform(speed * 0.6, speed)
            p.reset(x, y, math.cos(ang) * sp, math.sin(ang) * sp,
                    life * r.uniform(0.7, 1.2), color,
                    size=size, gravity=gravity, shape=SHAPE_SPARK,
                    glow=glow, fade_color=fade_color,
                    bounce=bounce, damping=damping,
                    spin=ang, spin_speed=r.uniform(-3.0, 3.0))

    # ------------------------------------------------------------------
    # Update  (in-place compaction — no list allocation)
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        active = self._active
        bx0, by0, bx1, by1 = self.bounce_bounds
        i = 0
        while i < len(active):
            p = active[i]
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += p.gravity * dt
            if p.bounce:
                if p.x < bx0:
                    p.x = bx0
                    p.vx = -p.vx * p.damping
                elif p.x > bx1:
                    p.x = bx1
                    p.vx = -p.vx * p.damping
                if p.y < by0:
                    p.y = by0
                    p.vy = -p.vy * p.damping
                elif p.y > by1:
                    p.y = by1
                    p.vy = -p.vy * p.damping
            p.spin += p.spin_speed * dt
            p.life -= dt
            if p.life <= 0:
                self._release(p)
                last = len(active) - 1
                active[i] = active[last]
                active.pop()
            else:
                i += 1

    # ------------------------------------------------------------------
    # Draw  (cached scratch surfaces, additive blend for glows)
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        for p in self._active:
            max_life = p.max_life
            frac = p.life / max_life if max_life > 0 else 0.0
            if frac < 0.0:
                frac = 0.0
            elif frac > 1.0:
                frac = 1.0
            # Color fade: lerp toward fade_color over life (start→end).
            if p.fade_color is not None:
                col = lerp_color(p.color, p.fade_color, 1.0 - frac)
            else:
                col = p.color
            r, g, b = col
            bucket = max(1, int(p.size))
            scratch = self._scratch(p.shape, bucket)
            sw, sh_ = scratch.get_size()
            cx, cy = sw // 2, sh_ // 2
            scratch.fill((0, 0, 0, 0))

            if p.glow:
                # Premultiply by frac so additive dimming tracks life.
                cr = int(r * frac)
                cg = int(g * frac)
                cb = int(b * frac)
                fill_col = (cr, cg, cb, 255)
            else:
                fill_col = (r, g, b, int(255 * frac))

            if p.shape == SHAPE_CIRCLE:
                pygame.draw.circle(scratch, fill_col, (cx, cy), bucket)
            elif p.shape == SHAPE_STAR:
                outer = bucket * 1.6
                inner = bucket * 0.7
                pts = _star_points(cx, cy, outer, inner, n=5, rot=p.spin)
                pygame.draw.polygon(scratch, fill_col, pts)
            else:  # SHAPE_SPARK — elongated diamond along velocity
                ang = math.atan2(p.vy, p.vx) if (p.vx or p.vy) else p.spin
                L = bucket * 1.8
                W = bucket * 0.5
                ca, sa = math.cos(ang), math.sin(ang)
                pts = [
                    (cx + L * ca, cy + L * sa),            # leading tip
                    (cx + W * sa, cy - W * ca),           # right shoulder
                    (cx - L * 0.6 * ca, cy - L * 0.6 * sa),  # tail
                    (cx - W * sa, cy + W * ca),           # left shoulder
                ]
                pygame.draw.polygon(scratch, fill_col, pts)

            tx = int(p.x) - cx
            ty = int(p.y) - cy
            if p.glow:
                surf.blit(scratch, (tx, ty),
                          special_flags=pygame.BLEND_RGBA_ADD)
            else:
                surf.blit(scratch, (tx, ty))

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self._active)

    def __len__(self) -> int:
        return len(self._active)

    def clear(self) -> None:
        """Return all live particles to the pool (e.g. on screen change)."""
        for p in self._active:
            self._release(p)
        self._active.clear()
