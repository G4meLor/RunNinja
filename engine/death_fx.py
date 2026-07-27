"""Death FX: satisfying enemy death animations.

Replaces the old fade-only corpse with a layered death sequence:
  * a colored particle burst (tinted by the enemy's hue)
  * a rising "soul" orb for bosses
  * gold coins arcing up toward the HUD gold pill
  * an expanding flash / shockwave ring
  * a shrinking + fading corpse that reuses the cached enemy_surface

Pure state; the renderer reads it.  No per-frame Surface allocations in
the hot loop -- the glow scratch is pre-allocated once and reused (cleared
per element), and the corpse's scaled copies are built once at spawn time
via ``pygame.transform.scale`` of the cached enemy_surface (so the global
``_ENEMY_CACHE`` is never mutated).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pygame

import config as cfg
from assets import enemy_surface, hsl
from theme import C
from utils import rng, clamp, ease_out_cubic


# HUD gold-pill icon center (see ui.screen_game._draw_hud + currency_pill:
# the pill is drawn at x=16, y=10 and its icon circle at x+14, y+14).
GOLD_PILL_TARGET = (30, 24)

# One pre-allocated SRCALPHA scratch, large enough for the expanding flash
# ring.  Cleared and reused per element -- never reallocated in the loop.
_SCRATCH_SIZE = 128


class _Burst:
    """One colored shard from the death burst."""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size")

    def __init__(self, x, y, vx, vy, life, size):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life; self.size = size


class _Coin:
    """One gold coin arcing toward the HUD gold pill."""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size")

    def __init__(self, x, y, vx, vy, life, size):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life; self.size = size


@dataclass
class DeathFx:
    """State for a single enemy's death animation.

    The core fields (x, y, edef, t, max_t, is_boss) match the spawn
    contract; the rest is auxiliary state built once at spawn time and
    mutated each tick.
    """
    x: float
    y: float
    edef: object
    t: float
    max_t: float
    is_boss: bool
    hue: int = 0
    burst_color: tuple = (255, 255, 255)
    bursts: list = field(default_factory=list)
    coins: list = field(default_factory=list)
    soul_life: float = 0.0
    soul_max: float = 0.0
    flash_life: float = 0.0
    flash_max: float = 0.0
    corpse_size: int = 48
    corpse_surfs: list = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.t < self.max_t


class DeathFxSystem:
    """Owns all active DeathFx and renders them with cached surfaces."""

    def __init__(self) -> None:
        self.fx: list[DeathFx] = []
        # Screen-shake callback (amp, dur) -- wired by the runner to
        # ``Game.shake``.  Boss deaths trigger it; Game.shake itself
        # no-ops when ``state.reduced_motion`` is set.
        self.on_shake = None
        # When True, skip flash / soul / shake for accessibility.
        self.reduced_motion = False
        self._scratch: pygame.Surface | None = None

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------
    def _scratch_surf(self) -> pygame.Surface:
        if self._scratch is None:
            self._scratch = pygame.Surface(
                (_SCRATCH_SIZE, _SCRATCH_SIZE), pygame.SRCALPHA
            ).convert_alpha()
        return self._scratch

    def _glow(self, surf: pygame.Surface, cx: int, cy: int, radius: int,
              color: tuple, alpha: int, ring: bool = False) -> None:
        """Blit a translucent circle / ring via the reusable scratch surface.

        Drawing the shape on an SRCALPHA scratch and blitting is the only
        way to get real translucency with pygame primitives on the opaque
        screen; the scratch is cleared per call so no per-frame Surface
        is allocated.
        """
        if alpha <= 0 or radius <= 0:
            return
        # Cap the radius so the shape fits inside the fixed scratch.
        max_r = (_SCRATCH_SIZE - 6) // 2
        if radius > max_r:
            radius = max_r
        s = self._scratch_surf()
        s.fill((0, 0, 0, 0))
        mid = _SCRATCH_SIZE // 2
        if ring:
            pygame.draw.circle(s, (*color, alpha), (mid, mid),
                               radius, max(2, radius // 6))
        else:
            pygame.draw.circle(s, (*color, alpha), (mid, mid), radius)
        surf.blit(s, (cx - mid, cy - mid))

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def spawn(self, enemy) -> None:
        """Create a DeathFx for a freshly killed enemy.

        ``enemy`` is an engine.enemy.Enemy; only its edef / hue / size /
        position / is_boss are read, so this is safe to call from the
        runner's kill path before the renderer runs.
        """
        is_boss = bool(getattr(enemy, "is_boss", False))
        hue = int(getattr(enemy, "hue", 0))
        edef = getattr(enemy, "edef", None)
        dx = float(enemy.x)
        # Match the renderer's lane center (see ui.screen_game.draw).
        dy = float(cfg.ROAD_TOP + cfg.ROAD_H // 2)
        max_t = 0.95 if is_boss else 0.6
        fx = DeathFx(x=dx, y=dy, edef=edef, t=0.0, max_t=max_t, is_boss=is_boss)
        fx.hue = hue
        fx.burst_color = hsl(hue, 0.85, 0.6)

        # --- Corpse: pre-compute shrinking copies of the cached surface.
        # ``pygame.transform.scale`` returns a brand-new Surface, so the
        # global _ENEMY_CACHE is never touched; set_alpha later only
        # mutates these per-death copies.
        esize = int(getattr(enemy, "size", 24)) * 2
        fx.corpse_size = esize
        base = enemy_surface(edef, size=esize)
        steps = 8
        fx.corpse_surfs = []
        for i in range(steps):
            scale = 1.0 - 0.7 * (i / (steps - 1))   # 1.0 -> 0.3
            if scale <= 0.05:
                continue
            w = max(1, int(base.get_width() * scale))
            h = max(1, int(base.get_height() * scale))
            fx.corpse_surfs.append(pygame.transform.scale(base, (w, h)))

        # --- Colored particle burst (tinted by enemy hue).
        count = 30 if is_boss else 12
        speed = 240 if is_boss else 160
        for _ in range(count):
            ang = rng().uniform(0, math.tau)
            sp = rng().uniform(speed * 0.4, speed)
            fx.bursts.append(_Burst(
                dx, dy,
                math.cos(ang) * sp, math.sin(ang) * sp,
                rng().uniform(0.30, 0.55), rng().uniform(2, 4),
            ))

        # --- Gold coins arcing toward the HUD gold pill.
        coin_count = 10 if is_boss else 5
        tx, ty = GOLD_PILL_TARGET
        base_ang = math.atan2(ty - dy, tx - dx)
        for _ in range(coin_count):
            ang = base_ang + rng().uniform(-0.5, 0.5)
            sp = rng().uniform(240, 360)
            fx.coins.append(_Coin(
                dx + rng().uniform(-8, 8), dy + rng().uniform(-8, 8),
                math.cos(ang) * sp, math.sin(ang) * sp,
                rng().uniform(0.55, 0.8), rng().uniform(3, 5),
            ))

        # --- Rising soul (bosses only).
        if is_boss and not self.reduced_motion:
            fx.soul_max = 0.9
            fx.soul_life = 0.9

        # --- Flash / shockwave.
        if not self.reduced_motion:
            fx.flash_max = 0.20 if is_boss else 0.13
            fx.flash_life = fx.flash_max

        # --- Boss screen-shake via the runner-wired callback.
        if is_boss and self.on_shake is not None:
            try:
                self.on_shake(8.0, 0.4)
            except Exception:
                pass

        self.fx.append(fx)

    def update(self, dt: float) -> None:
        for fx in self.fx:
            fx.t += dt

            # Burst shards: fly out, fall under gravity, drag in air.
            for b in fx.bursts:
                b.x += b.vx * dt
                b.y += b.vy * dt
                b.vy += 240 * dt
                b.vx *= math.exp(-dt * 2.0)
                b.life -= dt
            fx.bursts = [b for b in fx.bursts if b.life > 0]

            # Coins: arc out on initial velocity, then home into the pill.
            tx, ty = GOLD_PILL_TARGET
            for c in fx.coins:
                c.x += c.vx * dt
                c.y += c.vy * dt
                c.x += (tx - c.x) * min(1.0, dt * 5.0)
                c.y += (ty - c.y) * min(1.0, dt * 5.0)
                c.vx *= math.exp(-dt * 2.0)
                c.vy *= math.exp(-dt * 2.0)
                c.life -= dt
            fx.coins = [c for c in fx.coins if c.life > 0]

            if fx.soul_life > 0:
                fx.soul_life -= dt
            if fx.flash_life > 0:
                fx.flash_life -= dt

        self.fx = [f for f in self.fx if f.t < f.max_t]

    def draw(self, surf: pygame.Surface) -> None:
        for fx in self.fx:
            p = fx.t / fx.max_t if fx.max_t > 0 else 1.0
            p = clamp(p, 0.0, 1.0)
            cx, cy = int(fx.x), int(fx.y)

            # Corpse: shrink + fade using the pre-scaled copies.
            if fx.corpse_surfs:
                idx = min(len(fx.corpse_surfs) - 1,
                          int(p * len(fx.corpse_surfs)))
                cs = fx.corpse_surfs[idx]
                alpha = int(255 * (1.0 - ease_out_cubic(p)))
                if alpha > 0:
                    cs.set_alpha(alpha)
                    surf.blit(cs, cs.get_rect(center=(cx, cy)))

            # Flash: expanding shockwave ring.
            if fx.flash_life > 0 and fx.flash_max > 0:
                fp = 1.0 - (fx.flash_life / fx.flash_max)
                radius = int(10 + 46 * ease_out_cubic(fp))
                alpha = int(210 * (1.0 - fp))
                self._glow(surf, cx, cy, radius, (255, 255, 255), alpha, ring=True)

            # Burst shards.
            for b in fx.bursts:
                a = int(255 * clamp(b.life / b.max_life, 0.0, 1.0))
                self._glow(surf, int(b.x), int(b.y), int(b.size),
                           fx.burst_color, a)

            # Rising soul (bosses).
            if fx.soul_life > 0 and fx.soul_max > 0:
                sp = 1.0 - (fx.soul_life / fx.soul_max)
                sx = cx
                sy = int(fx.y - 54 * ease_out_cubic(sp))
                a = int(220 * (1.0 - sp))
                self._glow(surf, sx, sy, 16, C.soul, a // 2)
                self._glow(surf, sx, sy, 7, (225, 205, 255), a)

            # Gold coins.
            for c in fx.coins:
                a = int(255 * clamp(c.life / c.max_life, 0.0, 1.0))
                self._glow(surf, int(c.x), int(c.y), int(c.size), C.gold, a)
