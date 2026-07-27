"""Active-skill VFX: dramatic visuals for Kunai / Shuriken / Rope / Speed.

``SkillFxSystem.trigger(...)`` spawns short-lived effects when a skill
fires; ``update(dt)`` advances life timers; ``draw(surf)`` renders them
with pygame primitives and the cached sprite helpers from ``assets.py``.

Design constraints (enforced here):
- **pygame primitives only** for shapes — ``pygame.draw.*`` on small
  per-effect SRCALPHA overlays, then one ``blit`` to the screen.
- **cached surfaces where possible** — shuriken sprites are pre-rotated
  into a 24-bucket cache; ninja afterimages are pre-dimmed into a 5-level
  cache; the base ninja sprite comes from ``assets.ninja_surface``.
- **no per-frame allocations in hot loops** — every effect owns exactly
  one SRCALPHA surface created in ``__post_init__`` (i.e. at *spawn*
  time, inside ``trigger``, which runs on a button click — not in the
  per-frame ``update``/``draw``).  ``draw`` only ``fill``s, ``draw``s and
  ``blit``s; none of those allocate.

Each effect is a dataclass with a ``life`` / ``max_life`` timer; ``alive``
is ``life > 0`` and the system culls dead effects each tick.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import pygame

import config as cfg
from assets import ninja_surface
from utils import clamp, ease_out_cubic


# ---------------------------------------------------------------------------
# Palette + layout constants  (match Runner.activate_skill notify colors)
# ---------------------------------------------------------------------------
_SKILL_COLORS: dict[str, tuple[int, int, int]] = {
    "kunai":    (255, 120, 110),
    "shuriken": (180, 130, 255),
    "rope":     (130, 230, 160),
    "speed":    (255, 240, 120),
}

# Lane Y the screen uses for enemies (ROAD_TOP + ROAD_H//2 - 2 + 8).
_LANE_Y = cfg.ROAD_TOP + cfg.ROAD_H // 2 + 6
_NINJA_X = 180  # engine.enemy.PARTY_X


# ---------------------------------------------------------------------------
# Cached sprites  (built lazily once, reused forever)
# ---------------------------------------------------------------------------
_SHURIKEN_CACHE: dict[int, pygame.Surface] = {}
_NINJA_GHOST_CACHE: dict[int, pygame.Surface] = {}


def _shuriken_sprite(angle_deg: int) -> pygame.Surface:
    """A 4-point shuriken, cached per 15° rotation bucket (24 total)."""
    bucket = (int(angle_deg) // 15) * 15
    s = _SHURIKEN_CACHE.get(bucket)
    if s is not None:
        return s
    base = pygame.Surface((32, 32), pygame.SRCALPHA)
    cx, cy = 16, 16
    body = (220, 210, 240, 235)
    edge = (90, 70, 130, 235)
    for k in range(4):
        a = math.radians(bucket + k * 90)
        ca, sa = math.cos(a), math.sin(a)
        tip = (cx + 14 * ca, cy + 14 * sa)
        side1 = (cx + 4 * ca - 4 * sa, cy + 4 * sa + 4 * ca)
        side2 = (cx + 4 * ca + 4 * sa, cy + 4 * sa - 4 * ca)
        pygame.draw.polygon(base, body, [tip, side1, (cx, cy), side2])
        pygame.draw.polygon(base, edge, [tip, side1, (cx, cy), side2], 1)
    pygame.draw.circle(base, (240, 230, 255, 240), (cx, cy), 3)
    _SHURIKEN_CACHE[bucket] = base
    return base


def _ninja_ghost(level: int) -> pygame.Surface:
    """A pre-dimmed ninja afterimage, cached by dim level (0..4).

    Built by multiplying the cached ``ninja_surface`` by a uniform factor
    with ``BLEND_RGBA_MULT`` — this dims *and* adds transparency in one
    step, so we never depend on ``set_alpha`` semantics on a SRCALPHA
    surface (which pygame historically ignores).
    """
    level = max(0, min(4, int(level)))
    s = _NINJA_GHOST_CACHE.get(level)
    if s is None:
        base = ninja_surface(72).copy()
        factor = max(40, 200 - level * 40)  # 200,160,120,80,40
        base.fill((factor, factor, factor, factor),
                  special_flags=pygame.BLEND_RGBA_MULT)
        _NINJA_GHOST_CACHE[level] = base
        s = base
    return s


# ---------------------------------------------------------------------------
# Effects  (each is a dataclass with a life timer)
# ---------------------------------------------------------------------------
@dataclass
class _Effect:
    """Base: life timer + culling. Subclasses add fields + ``draw``."""
    life: float
    max_life: float

    def update(self, dt: float) -> None:
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0

    def draw(self, surf: pygame.Surface) -> None:
        raise NotImplementedError


@dataclass
class KunaiEffect(_Effect):
    """A single flying blade from the ninja to one enemy + impact flash."""
    sx: float = 0.0
    sy: float = 0.0
    tx: float = 0.0
    ty: float = 0.0
    color: tuple[int, int, int] = (255, 120, 110)
    travel: float = 0.22  # seconds to reach the target

    def __post_init__(self) -> None:
        m = 20
        x0 = int(min(self.sx, self.tx) - m)
        y0 = int(min(self.sy, self.ty) - m)
        x1 = int(max(self.sx, self.tx) + m)
        y1 = int(max(self.sy, self.ty) + m)
        self._ox, self._oy = x0, y0
        # One overlay for the whole path + impact. Allocated at spawn only.
        self._surf = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)),
                                    pygame.SRCALPHA)
        self._ang = math.atan2(self.ty - self.sy, self.tx - self.sx)

    def draw(self, target: pygame.Surface) -> None:
        elapsed = self.max_life - self.life
        self._surf.fill((0, 0, 0, 0))
        if elapsed < self.travel:
            t = elapsed / self.travel
            px = self.sx + (self.tx - self.sx) * t
            py = self.sy + (self.ty - self.sy) * t
            lx, ly = px - self._ox, py - self._oy
            ca, sa = math.cos(self._ang), math.sin(self._ang)
            # Elongated diamond blade pointing along travel.
            pts = [
                (lx + 9 * ca, ly + 9 * sa),
                (lx + 3 * sa, ly - 3 * ca),
                (lx - 7 * ca, ly - 7 * sa),
                (lx - 3 * sa, ly + 3 * ca),
            ]
            pygame.draw.polygon(self._surf, (*self.color, 240), pts)
            pygame.draw.polygon(self._surf, (255, 255, 255, 220), pts, 1)
            # Motion trail: three fading segments behind the blade.
            for k in range(1, 4):
                a = 170 - k * 50
                bx = lx - 9 * k * ca
                by = ly - 9 * k * sa
                pygame.draw.line(self._surf, (*self.color, a),
                                 (bx, by), (lx, ly), 2)
        else:
            ft = clamp((elapsed - self.travel) / max(1e-3, self.max_life - self.travel),
                       0.0, 1.0)
            r = int(4 + 16 * (1 - ft))
            a = int(220 * (1 - ft))
            cx_l = self.tx - self._ox
            cy_l = self.ty - self._oy
            pygame.draw.circle(self._surf, (*self.color, a),
                               (int(cx_l), int(cy_l)), r, 2)
            # Radiating spark lines.
            for k in range(6):
                ang = self._ang + (k - 2.5) * 0.5
                pygame.draw.line(self._surf, (255, 230, 200, a),
                                 (cx_l, cy_l),
                                 (cx_l + math.cos(ang) * r,
                                  cy_l + math.sin(ang) * r), 1)
        target.blit(self._surf, (self._ox, self._oy))


@dataclass
class ShurikenEffect(_Effect):
    """Expanding ring AOE centred on the ninja, with orbiting shurikens."""
    cx: float = 0.0
    cy: float = 0.0
    max_radius: float = 200.0
    color: tuple[int, int, int] = (180, 130, 255)

    def __post_init__(self) -> None:
        m = int(self.max_radius) + 24
        self._ox = int(self.cx) - m
        self._oy = int(self.cy) - m
        size = max(1, m * 2)
        self._surf = pygame.Surface((size, size), pygame.SRCALPHA)
        self._spin = 0.0
        self._n_shur = 4

    def update(self, dt: float) -> None:
        self.life -= dt
        self._spin += dt * 720.0  # degrees per second

    def draw(self, target: pygame.Surface) -> None:
        t = clamp(1.0 - self.life / self.max_life, 0.0, 1.0)
        et = ease_out_cubic(t)
        r = self.max_radius * et
        self._surf.fill((0, 0, 0, 0))
        cl = int(self.cx) - self._ox
        cll = int(self.cy) - self._oy
        # Filled shockwave disc.
        disc_a = int(70 * (1 - t))
        if disc_a > 0 and r > 0:
            pygame.draw.circle(self._surf, (*self.color, disc_a),
                               (cl, cll), int(r))
        # Three concentric rings, fading.
        for k, frac in enumerate((1.0, 0.7, 0.45)):
            rr = int(r * frac)
            a = int(230 * (1 - t) * (1 - k * 0.25))
            if rr > 0 and a > 0:
                pygame.draw.circle(self._surf, (*self.color, a),
                                   (cl, cll), rr, 3)
        # Orbiting shuriken sprites ride the leading edge.
        if t < 0.8:
            edge_r = r * 0.9
            for i in range(self._n_shur):
                ang = math.radians(self._spin + i * (360.0 / self._n_shur))
                sxp = cl + math.cos(ang) * edge_r - 16
                syp = cll + math.sin(ang) * edge_r - 16
                self._surf.blit(_shuriken_sprite(int(self._spin + i * 90)),
                                (int(sxp), int(syp)))
        target.blit(self._surf, (self._ox, self._oy))


@dataclass
class RopeEffect(_Effect):
    """Grappling line from the ninja to the target + pull-back flash."""
    sx: float = 0.0
    sy: float = 0.0
    tx: float = 0.0
    ty: float = 0.0
    color: tuple[int, int, int] = (130, 230, 160)

    def __post_init__(self) -> None:
        m = 24
        x0 = int(min(self.sx, self.tx) - m)
        y0 = int(min(self.sy, self.ty) - m)
        x1 = int(max(self.sx, self.tx) + m)
        y1 = int(max(self.sy, self.ty) + m)
        self._ox, self._oy = x0, y0
        self._surf = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)),
                                    pygame.SRCALPHA)
        self._dx = self.tx - self.sx
        self._dy = self.ty - self.sy
        self._ang = math.atan2(self._dy, self._dx)

    def draw(self, target: pygame.Surface) -> None:
        t = clamp(1.0 - self.life / self.max_life, 0.0, 1.0)
        self._surf.fill((0, 0, 0, 0))
        sl = self.sx - self._ox
        st = self.sy - self._oy
        tl_l = self.tx - self._ox
        ty_l = self.ty - self._oy
        # Phase 1 (t<0.5): line shoots out. Phase 2: pull flash + fade.
        if t < 0.5:
            reach = ease_out_cubic(t / 0.5)
            ex = sl + self._dx * reach
            ey = st + self._dy * reach
            a = 230
        else:
            ex, ey = tl_l, ty_l
            a = int(230 * (1 - (t - 0.5) / 0.5))
        # Zig-zag rope (8 segments, alternating perpendicular offset).
        perp_x = -math.sin(self._ang) * 3
        perp_y = math.cos(self._ang) * 3
        n_seg = 8
        pts = []
        for i in range(n_seg + 1):
            f = i / n_seg
            px = sl + (ex - sl) * f
            py = st + (ey - st) * f
            off = perp_x if (i % 2) else -perp_x
            ofy = perp_y if (i % 2) else -perp_y
            pts.append((px + off, py + ofy))
        if len(pts) >= 2:
            pygame.draw.lines(self._surf, (*self.color, a), False, pts, 2)
        # Hook triangle at the leading end.
        ca, sa = math.cos(self._ang), math.sin(self._ang)
        hook = [
            (ex + 9 * ca, ey + 9 * sa),
            (ex - 4 * ca + 5 * sa, ey - 4 * sa - 5 * ca),
            (ex - 4 * ca - 5 * sa, ey - 4 * sa + 5 * ca),
        ]
        pygame.draw.polygon(self._surf, (*self.color, a), hook)
        # Pull flash at the target (phase 2).
        if t >= 0.5:
            ft = (t - 0.5) / 0.5
            r = int(6 + 18 * ft)
            fa = int(210 * (1 - ft))
            pygame.draw.circle(self._surf, (255, 255, 220, fa),
                               (int(tl_l), int(ty_l)), r, 2)
        target.blit(self._surf, (self._ox, self._oy))


@dataclass
class SpeedEffect(_Effect):
    """Motion lines streaking back from the ninja + afterimage ghosts."""
    cx: float = 0.0
    cy: float = 0.0
    color: tuple[int, int, int] = (255, 240, 120)

    def __post_init__(self) -> None:
        # Overlay spans the ninja + room to the left for lines/ghosts.
        x0 = int(self.cx) - 100
        y0 = int(self.cy) - 50
        x1 = int(self.cx) + 40
        y1 = int(self.cy) + 50
        self._ox, self._oy = x0, y0
        self._surf = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)),
                                    pygame.SRCALPHA)
        # Pre-pick motion-line layout (relative to overlay) — no per-frame work.
        self._lines: list[tuple[int, int, int]] = []
        for i in range(6):
            rx = 30 + i * 14        # distance left of ninja
            ry = -18 + (i % 3) * 14
            ln = 18 + (i % 4) * 6
            self._lines.append((rx, ry, ln))

    def draw(self, target: pygame.Surface) -> None:
        t = clamp(1.0 - self.life / self.max_life, 0.0, 1.0)
        self._surf.fill((0, 0, 0, 0))
        cl = int(self.cx) - self._ox
        cll = int(self.cy) - self._oy
        # Motion lines streak left (backward) from the ninja, shifting over time.
        for i, (rx, ry, ln) in enumerate(self._lines):
            phase = (t * 4 + i * 0.3) % 1.0
            shift = int(phase * 20)
            a = int(190 * (1 - t) * (1 - phase))
            if a > 0:
                x0 = cl - rx - shift
                yy = cll + ry
                pygame.draw.line(self._surf, (*self.color, a),
                                 (x0, yy), (x0 + ln, yy), 2)
        # Afterimage ghosts of the ninja, offset left, dimmer the further out.
        for k in range(3):
            offset = 16 + k * 14
            ghost = _ninja_ghost(k + 1)  # levels 1,2,3 — dimmer further back
            gx = cl - offset - 36         # 72-px sprite, centre it on the point
            gy = cll - 36
            self._surf.blit(ghost, (int(gx), int(gy)))
        target.blit(self._surf, (self._ox, self._oy))


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class SkillFxSystem:
    """Owns the active-skill VFX layer.

    Wire-up (see docs/specs/skill_fx.md):

    * ``Runner.__init__``:  ``self.skill_fx = SkillFxSystem()``
    * ``Runner.activate_skill``:  call ``self.skill_fx.trigger(sid,
      self.ninja.x, self.ninja.y, self.world.enemies)`` **before**
      applying damage so the visual leads the damage flash.
    * ``Runner.update``:  ``self.skill_fx.update(dt)`` next to
      ``self.fx.update(dt)``.
    * ``GameScreen.draw``:  ``runner.skill_fx.draw(surf)`` after
      ``runner.fx.draw(surf)`` / particles.
    """

    def __init__(self) -> None:
        self.effects: list[_Effect] = []
        # Accessibility / polish hooks the runner/screen may set.
        self.reduced_motion: bool = False
        self.on_shake: Optional[Callable[[float, float], None]] = None

    # ------------------------------------------------------------------
    # Trigger  (called from Runner.activate_skill, on a button click)
    # ------------------------------------------------------------------
    def trigger(self, skill_id: str, ninja_x: float, ninja_y: float,
                enemies: list) -> None:
        """Spawn the VFX for one skill firing.

        Target selection mirrors ``Runner.activate_skill`` so the visuals
        land on the same enemies the damage does:

        * kunai    — nearest 5 alive enemies (smallest x)
        * shuriken — AOE ring centred on the ninja (hits all)
        * rope     — weakest alive non-boss enemy (min hp)
        * speed    — no targets; aura around the ninja
        """
        col = _SKILL_COLORS.get(skill_id, (255, 255, 255))
        nx = ninja_x + 14   # blade/hook origin: the ninja's leading hand
        ny = ninja_y - 4

        if skill_id == "kunai":
            targets = sorted((e for e in enemies if e.alive),
                             key=lambda e: e.x)[:5]
            for e in targets:
                ex = getattr(e, "x", nx + 200)
                ey = getattr(e, "y", _LANE_Y) or _LANE_Y
                self.effects.append(KunaiEffect(
                    life=0.34, max_life=0.34,
                    sx=nx, sy=ny, tx=float(ex), ty=float(ey), color=col,
                ))
        elif skill_id == "shuriken":
            alive = [e for e in enemies if e.alive]
            if alive:
                far = max(math.hypot(e.x - ninja_x,
                                     (getattr(e, "y", _LANE_Y) or _LANE_Y) - ninja_y)
                          for e in alive)
            else:
                far = 160.0
            max_r = clamp(far + 40.0, 120.0, float(cfg.WINDOW_W // 2))
            self.effects.append(ShurikenEffect(
                life=0.6, max_life=0.6,
                cx=ninja_x, cy=ninja_y, max_radius=max_r, color=col,
            ))
        elif skill_id == "rope":
            targets = [e for e in enemies
                       if e.alive and not getattr(e, "is_boss", False)]
            if targets:
                t = min(targets, key=lambda e: e.hp)
                self.effects.append(RopeEffect(
                    life=0.5, max_life=0.5,
                    sx=nx, sy=ny,
                    tx=float(t.x), ty=float(getattr(t, "y", _LANE_Y) or _LANE_Y),
                    color=col,
                ))
        elif skill_id == "speed":
            self.effects.append(SpeedEffect(
                life=0.7, max_life=0.7,
                cx=ninja_x, cy=ninja_y, color=col,
            ))

        # Optional screen-shake for the heavier skills.
        if self.on_shake is not None and not self.reduced_motion:
            if skill_id in ("shuriken", "kunai"):
                try:
                    self.on_shake(6.0 if skill_id == "kunai" else 8.0, 0.3)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Update / draw  (called every frame from the hot loop)
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for e in self.effects:
            e.update(dt)
        if self.effects:
            self.effects = [e for e in self.effects if e.alive]

    def draw(self, surf: pygame.Surface) -> None:
        for e in self.effects:
            e.draw(surf)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self.effects)

    def clear(self) -> None:
        self.effects.clear()
