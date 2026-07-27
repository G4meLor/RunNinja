"""Ninja attack FX: katana slash arc + lunge + hit spark.

Makes the ninja visibly slash on tap and auto-attack. ``on_slash`` fires
three things:

  * a **katana arc/trail** — a curved polyline (quadratic Bezier) from the
    ninja's leading hand to the target that sweeps along its path, then
    fades. Crit arcs are gold, thicker, and sweep a wider arc.
  * a **lunge** — the ninja's render position shifts toward the target
    briefly, then eases back. The screen reads ``lunge_offset()`` each
    frame and adds it to the ninja's blit position.
  * a **hit spark** — a small expanding ring + radiating sparks at the
    target, gold for crits, light for normal hits.

Pure state; pygame primitives; **no per-frame allocations** in the hot
loop. Each arc owns one SRCALPHA overlay created at spawn time (inside
``on_slash``, which runs on tap / auto-attack -- not in ``update`` /
``draw``). ``draw`` only ``fill``s, ``draw``s, and ``blit``s.

Integration (see docs/specs/ninja_fx.md):

  * ``Runner`` owns one ``NinjaFxSystem`` and calls ``on_slash`` from its
    ``_on_enemy_dmg`` callback, which fires on every enemy damage event
    (tap, auto-attack, skill damage) with the right ``is_crit`` and
    target position -- so tap + auto-attack hits are covered without
    editing ``engine/enemy.py``.
  * ``GameScreen.draw`` applies ``lunge_offset()`` to the ninja's blit
    position and calls ``draw(surf)`` to render the arcs + hit sparks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config as cfg
from theme import C
from utils import clamp, ease_out_cubic


# ---------------------------------------------------------------------------
# Layout  (mirror the screen's ninja / enemy lane coordinates)
# ---------------------------------------------------------------------------
# The screen draws the ninja at nx=180, ny=ROAD_TOP+ROAD_H//2-2-30 (+bob),
# blit midbottom=(nx, ny+50); enemies sit on the lane at
# ey=ROAD_TOP+ROAD_H//2-2+8. These constants mirror those so the arcs
# line up with the drawn sprites without any coordinate plumbing.
_NINJA_X = 180                         # engine.enemy.PARTY_X
_LANE_Y = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2
_NINJA_Y_BASE = _LANE_Y - 30           # screen's ny at bob=0
_HAND_DX = 14                          # leading-hand offset from ninja x
_HAND_DY = 14                           # body-center offset from ny


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_ARC_LIFE = 0.28                       # normal arc lifetime (s)
_ARC_LIFE_CRIT = 0.34                  # crit arc lifetime (s)
_SWEEP_TIME = 0.10                     # arc sweep reaches target at this t
_SWEEP_NORMAL = 34.0                   # perpendicular arc bulge (px)
_SWEEP_CRIT = 58.0                     # crit bulges a wider arc
_ARC_SEGMENTS = 14                     # Bezier sample points per arc
_ARC_WIDTH = 3                         # polyline thickness (normal)
_ARC_WIDTH_CRIT = 4                    # polyline thickness (crit)

_SPARK_R_MAX = 22                      # expanding ring peak radius (normal)
_SPARK_R_MAX_CRIT = 30                 # expanding ring peak radius (crit)
_SPARK_RAYS = 7                        # radiating spark lines
_SPARK_RAY_LEN = 14                    # spark ray length beyond the ring

_LUNGE_DUR = 0.22                      # lunge return time (s)
_LUNGE_MAX = 22.0                      # peak lunge distance (px)
_LUNGE_MAX_CRIT = 30.0                 # crit lunges a bit further
_LUNGE_Y_CAP = 8.0                    # clamp the vertical lunge component

# Palette  (cool steel for normal hits, gold for crits)
_COL_NORMAL = (230, 240, 255)
_COL_NORMAL_HI = (255, 255, 255)
_COL_CRIT = C.gold
_COL_CRIT_HI = (255, 245, 200)
_COL_SPARK_NORMAL = (255, 250, 230)
_COL_SPARK_CRIT = C.gold


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------
@dataclass
class _SlashArc:
    """One katana arc + hit spark from the ninja to a target.

    The overlay surface is created once in ``__post_init__`` (at spawn
    time, inside ``on_slash``); ``draw`` only clears, draws, and blits.
    The Bezier points and spark-ray directions are pre-computed once, so
    the per-frame work is just a ``fill``, a couple of ``draw`` calls, and
    a ``blit``.
    """
    sx: float
    sy: float
    tx: float
    ty: float
    is_crit: bool
    life: float
    max_life: float
    color: tuple
    hi_color: tuple
    spark_color: tuple
    width: int

    def __post_init__(self) -> None:
        # Overlay bounds: cover the arc bulge + spark with margin. The arc
        # bulges perpendicular to the line (upward), the spark expands
        # radially from the target, so pad generously on all sides.
        m = int(_SPARK_R_MAX_CRIT + _SPARK_RAY_LEN) + 8
        x0 = int(min(self.sx, self.tx) - m)
        y0 = int(min(self.sy, self.ty) - m - int(_SWEEP_CRIT))
        x1 = int(max(self.sx, self.tx) + m)
        y1 = int(max(self.sy, self.ty) + m)
        self._ox, self._oy = x0, y0
        self._surf = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)),
                                    pygame.SRCALPHA)
        # Quadratic Bezier from start to end with a perpendicular control
        # point (the katana sweep). The control point sits above the
        # midpoint so the arc bulges upward (an overhead chop read).
        dx = self.tx - self.sx
        dy = self.ty - self.sy
        length = math.hypot(dx, dy)
        if length > 0.0:
            perp_x = dy / length
            perp_y = -dx / length
        else:
            perp_x = 0.0
            perp_y = -1.0
        sweep = _SWEEP_CRIT if self.is_crit else _SWEEP_NORMAL
        sweep = min(sweep, max(8.0, length * 0.35))
        mxh = (self.sx + self.tx) * 0.5 + perp_x * sweep
        myh = (self.sy + self.ty) * 0.5 + perp_y * sweep
        # Pre-compute the Bezier points in overlay-local coordinates.
        self._pts: list[tuple[float, float]] = []
        for i in range(_ARC_SEGMENTS + 1):
            t = i / _ARC_SEGMENTS
            u = 1.0 - t
            bx = u * u * self.sx + 2.0 * u * t * mxh + t * t * self.tx
            by = u * u * self.sy + 2.0 * u * t * myh + t * t * self.ty
            self._pts.append((bx - self._ox, by - self._oy))
        # Target in overlay-local coords (the hit-spark anchor).
        self._tlx = self.tx - self._ox
        self._tly = self.ty - self._oy
        # Pre-pick spark-ray directions (evenly around the circle -- a
        # star-burst hit spark). No per-frame randomness.
        self._rays: list[tuple[float, float]] = []
        for i in range(_SPARK_RAYS):
            ang = i * (math.tau / _SPARK_RAYS)
            self._rays.append((math.cos(ang), math.sin(ang)))

    def update(self, dt: float) -> None:
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0

    def draw(self, target: pygame.Surface) -> None:
        elapsed = self.max_life - self.life
        self._surf.fill((0, 0, 0, 0))
        # Phase 1 (elapsed < _SWEEP_TIME): the arc sweeps from ninja to
        # target -- a progressive draw along the Bezier with a bright
        # leading-edge dot at the sweep tip.
        # Phase 2: the full arc + hit spark fade out together.
        if elapsed < _SWEEP_TIME:
            sweep_t = elapsed / _SWEEP_TIME
            n = max(2, int(len(self._pts) * sweep_t))
            pts = self._pts[:n]
            alpha = 255
        else:
            pts = self._pts
            fade_t = (elapsed - _SWEEP_TIME) / max(1e-3, self.max_life - _SWEEP_TIME)
            fade_t = clamp(fade_t, 0.0, 1.0)
            alpha = int(255 * (1.0 - ease_out_cubic(fade_t)))
        if alpha <= 0:
            target.blit(self._surf, (self._ox, self._oy))
            return
        # Outer arc (color) + inner core (hi_color) for a shiny edge.
        if len(pts) >= 2:
            pygame.draw.lines(self._surf, (*self.color, alpha),
                              False, pts, self.width)
            core_w = max(1, self.width - 2)
            pygame.draw.lines(self._surf, (*self.hi_color, alpha),
                              False, pts, core_w)
        # Leading-edge highlight: a bright dot at the sweep tip (phase 1).
        if elapsed < _SWEEP_TIME and pts:
            tip = pts[-1]
            pygame.draw.circle(self._surf, (*self.hi_color, alpha),
                               (int(tip[0]), int(tip[1])),
                               max(3, self.width))
        # Hit spark: fires once the sweep reaches the target. An expanding
        # ring + radiating star-burst rays, fading over the post-sweep life.
        if elapsed >= _SWEEP_TIME:
            ft = (elapsed - _SWEEP_TIME) / max(1e-3, self.max_life - _SWEEP_TIME)
            ft = clamp(ft, 0.0, 1.0)
            r_max = _SPARK_R_MAX_CRIT if self.is_crit else _SPARK_R_MAX
            r = int(4 + r_max * ease_out_cubic(ft))
            a = int(230 * (1.0 - ft))
            if r > 0 and a > 0:
                cx_l = int(self._tlx)
                cy_l = int(self._tly)
                pygame.draw.circle(self._surf, (*self.spark_color, a),
                                   (cx_l, cy_l), r, 2)
                for ca, sa in self._rays:
                    x0 = cx_l + ca * 4
                    y0 = cy_l + sa * 4
                    x1 = cx_l + ca * (r + _SPARK_RAY_LEN)
                    y1 = cy_l + sa * (r + _SPARK_RAY_LEN)
                    pygame.draw.line(self._surf, (*self.spark_color, a),
                                     (x0, y0), (x1, y1), 2)
        target.blit(self._surf, (self._ox, self._oy))


@dataclass
class _Lunge:
    """The ninja's brief render offset toward the target, easing back.

    On ``reset`` the offset snaps to the max (the ninja lunges forward);
    ``update`` eases it back to zero over ``max_life`` with a quadratic
    ease-out (fast initial return, slow settle), so the ninja snaps
    forward then settles back -- a classic lunge-and-recover.
    """
    dx: float = 0.0
    dy: float = 0.0
    max_dx: float = 0.0
    max_dy: float = 0.0
    life: float = 0.0
    max_life: float = 0.0

    def reset(self, dx: float, dy: float, dur: float) -> None:
        self.max_dx = dx
        self.max_dy = dy
        self.dx = dx
        self.dy = dy
        self.life = dur
        self.max_life = dur

    def update(self, dt: float) -> None:
        if self.life <= 0.0:
            self.dx = 0.0
            self.dy = 0.0
            return
        self.life -= dt
        if self.life <= 0.0:
            self.life = 0.0
            self.dx = 0.0
            self.dy = 0.0
            return
        # Quadratic ease-out return: factor 1 -> 0, fast at first, slow
        # at the end. (life/max_life is 1 at peak, 0 at rest.)
        factor = (self.life / self.max_life) ** 2
        self.dx = self.max_dx * factor
        self.dy = self.max_dy * factor


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class NinjaFxSystem:
    """Owns the ninja's slash arcs + lunge.

    Wire-up (see docs/specs/ninja_fx.md):

    * ``Runner.__init__``:  ``self.ninja_fx = NinjaFxSystem()``
    * ``Runner._on_enemy_dmg``:  call ``self.ninja_fx.on_slash(self.ninja,
      x, y, is_crit)`` -- fires on tap, auto-attack, and skill damage, so
      tap + auto-attack hits are covered without editing ``engine/enemy.py``.
    * ``Runner.update``:  ``self.ninja_fx.update(dt)`` next to
      ``self.fx.update(dt)``.
    * ``GameScreen.draw``:  add ``runner.ninja_fx.lunge_offset()`` to the
      ninja's blit position, then ``runner.ninja_fx.draw(surf)`` after the
      ninja is drawn.
    """

    def __init__(self) -> None:
        self._arcs: list[_SlashArc] = []
        self._lunge = _Lunge()
        # Accessibility: skip the lunge when True (arcs + sparks still
        # play -- they are brief flashes, not unsettling motion).
        self.reduced_motion: bool = False

    # ------------------------------------------------------------------
    # Spawn  (called from the runner on tap / auto-attack / skill hit)
    # ------------------------------------------------------------------
    def on_slash(self, ninja, target_x: float, target_y: float,
                 is_crit: bool = False) -> None:
        """Spawn the katana arc + lunge + hit spark for one slash.

        ``ninja`` is the ``engine.ninja.Ninja``; only its ``x`` / ``y``
        are read for the arc origin (the leading hand at body-center
        height). ``target_x`` / ``target_y`` are the enemy's screen-lane
        position (the screen sets ``enemy.y`` each frame). ``is_crit``
        gold-ens and enlarges the arc, spark, and lunge.
        """
        nx = float(getattr(ninja, "x", _NINJA_X))
        ny = float(getattr(ninja, "y", _NINJA_Y_BASE))
        if ny < 1.0:
            ny = _NINJA_Y_BASE       # first-frame fallback before draw sets it
        sx = nx + _HAND_DX
        sy = ny + _HAND_DY
        tx = float(target_x)
        ty = float(target_y)
        life = _ARC_LIFE_CRIT if is_crit else _ARC_LIFE
        self._arcs.append(_SlashArc(
            sx=sx, sy=sy, tx=tx, ty=ty, is_crit=is_crit,
            life=life, max_life=life,
            color=_COL_CRIT if is_crit else _COL_NORMAL,
            hi_color=_COL_CRIT_HI if is_crit else _COL_NORMAL_HI,
            spark_color=_COL_SPARK_CRIT if is_crit else _COL_SPARK_NORMAL,
            width=_ARC_WIDTH_CRIT if is_crit else _ARC_WIDTH,
        ))
        # Lunge: shift the ninja toward the target, ease back. Skip for
        # reduced-motion (the ninja stays planted).
        if not self.reduced_motion:
            dx = tx - nx
            dy = ty - sy
            dist = math.hypot(dx, dy)
            if dist > 0.0:
                ux = dx / dist
                uy = dy / dist
            else:
                ux = 1.0
                uy = 0.0
            mag = _LUNGE_MAX_CRIT if is_crit else _LUNGE_MAX
            ldx = ux * mag
            ldy = clamp(uy * mag, -_LUNGE_Y_CAP, _LUNGE_Y_CAP)
            self._lunge.reset(ldx, ldy, _LUNGE_DUR)

    # ------------------------------------------------------------------
    # Update / draw  (called every frame from the hot loop)
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for a in self._arcs:
            a.update(dt)
        if self._arcs:
            self._arcs = [a for a in self._arcs if a.alive]
        self._lunge.update(dt)

    def draw(self, surf: pygame.Surface) -> None:
        for a in self._arcs:
            a.draw(surf)

    # ------------------------------------------------------------------
    # Lunge  (the screen reads this each frame)
    # ------------------------------------------------------------------
    def lunge_offset(self) -> tuple[float, float]:
        """Current (dx, dy) to add to the ninja's render position."""
        return (self._lunge.dx, self._lunge.dy)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self._arcs) or self._lunge.life > 0.0

    def clear(self) -> None:
        """Drop all arcs and reset the lunge (call on ascension / new run)."""
        self._arcs.clear()
        self._lunge.dx = 0.0
        self._lunge.dy = 0.0
        self._lunge.max_dx = 0.0
        self._lunge.max_dy = 0.0
        self._lunge.life = 0.0
        self._lunge.max_life = 0.0
