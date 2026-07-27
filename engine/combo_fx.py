"""Combo milestone celebration FX for Tap Ninja.

When the running combo crosses a milestone (10, 25, 50, 100, 200) the
``ComboFxSystem`` fires a celebratory burst:

* a **big banner** with the milestone label that scales in with
  ``ease_out_cubic``, holds, then fades out;
* an **expanding gold ring** radiating from the kill position;
* a **gold particle burst** at the kill position;
* a brief **full-screen flash**.

Milestone gold is awarded by the runner (see ``docs/specs/combo_fx.md``).

Pure pygame primitives, cached theme fonts, fixed effect pools, and
reusable scratch surfaces — zero per-frame allocations once warm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config as cfg
from theme import C, font_huge, font_lg
from utils import rng, clamp, ease_out_cubic, format_number, lerp_color


# ---------------------------------------------------------------------------
# Milestone tables
# ---------------------------------------------------------------------------
MILESTONES: dict[int, str] = {
    10:  "Nice!",
    25:  "Combo!",
    50:  "Fury!",
    100: "Storm!",
    200: "Legend!",
}

# Base gold awarded per milestone hit.  The runner multiplies this by its
# own gold multiplier (upgrades / evolution bonuses) before awarding, so
# the numbers below are the *base* values.
MILESTONE_GOLD: dict[int, float] = {
    10:  100.0,
    25:  500.0,
    50:  2_500.0,
    100: 15_000.0,
    200: 100_000.0,
}


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_BANNER_INTRO  = 0.30   # scale-in (ease-out) seconds
_BANNER_HOLD    = 0.80   # hold at full scale seconds
_BANNER_FADE    = 0.55   # fade-out seconds
_RING_DUR       = 0.70   # expanding ring lifetime (s)
_RING_MAX_R     = 180    # peak ring radius (px)
_FLASH_DUR      = 0.32   # full-screen flash lifetime (s)
_FLASH_PEAK     = 0.45   # peak flash alpha fraction (0..1)
_PARTICLE_COUNT = 26     # gold particles per burst
_MAX_PARTICLES  = 96     # particle pool size
_MAX_RINGS      = 4      # ring slot pool size
_PARTICLE_MAX_R = 5      # largest particle radius (px)
_SCALE_STEPS    = 14     # cached text scale steps (discrete; no per-frame alloc)
_SCALE_MIN       = 0.55   # smallest intro scale (fraction of full size)


# ---------------------------------------------------------------------------
# Effect slots
# ---------------------------------------------------------------------------
@dataclass
class _Particle:
    """A gold spark. Pooled — recycled via ``reset``; never re-allocated."""
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    life: float = 0.0
    max_life: float = 1.0
    size: int = 3
    alive: bool = False

    def reset(self, x: float, y: float, vx: float, vy: float,
              life: float, size: int) -> None:
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.size = size; self.alive = True

    def update(self, dt: float) -> None:
        if not self.alive:
            return
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 220.0 * dt                 # gravity
        self.vx *= max(0.0, 1.0 - 1.8 * dt)  # air drag
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf: pygame.Surface, scratch: pygame.Surface) -> None:
        if not self.alive:
            return
        a = clamp(self.life / self.max_life, 0.0, 1.0)
        alpha = int(255 * a)
        if alpha <= 0:
            return
        r = max(1, self.size)
        c = scratch.get_width() // 2
        scratch.fill((0, 0, 0, 0))
        pygame.draw.circle(scratch, (255, 205, 90, alpha), (c, c), r)
        if r > 1:
            pygame.draw.circle(scratch, (255, 240, 180, alpha), (c, c), r - 1)
        surf.blit(scratch, (int(self.x) - c, int(self.y) - c))


@dataclass
class _Ring:
    """An expanding ring radiating from the kill position."""
    x: float = 0.0
    y: float = 0.0
    age: float = 0.0
    alive: bool = False


@dataclass
class _Banner:
    """The big milestone label + subtext. One at a time."""
    milestone: int = 0
    label: str = ""
    gold: float = 0.0
    age: float = 0.0
    alive: bool = False
    sub_img: object = None   # rendered subtext (built once per trigger)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class ComboFxSystem:
    """Owns the combo-milestone celebration FX.

    The runner calls ``check`` / ``trigger`` on kills; the screen calls
    ``update`` (via the runner) and ``draw``.
    """

    # -- lifecycle --------------------------------------------------------
    def __init__(self) -> None:
        self._banner: _Banner = _Banner()
        self._rings: list[_Ring] = []
        self._particles: list[_Particle] = []
        self._flash: float = 0.0
        # Reusable scratch surfaces (lazy, grown once, never per-frame).
        self._ring_scratch: pygame.Surface | None = None
        self._part_scratch: pygame.Surface | None = None
        self._flash_surf: pygame.Surface | None = None
        # Cached label/shadow surfaces, per milestone, per scale step.
        self._label_cache: dict[int, list[pygame.Surface]] = {}
        self._shadow_cache: dict[int, list[pygame.Surface]] = {}

    def reset(self) -> None:
        """Clear all active FX (call on ascension / new run)."""
        self._banner.alive = False
        for r in self._rings:
            r.alive = False
        for p in self._particles:
            p.alive = False
        self._flash = 0.0

    @property
    def active(self) -> bool:
        """True if anything is currently animating (cheap draw gate)."""
        if self._banner.alive or self._flash > 0:
            return True
        for r in self._rings:
            if r.alive:
                return True
        for p in self._particles:
            if p.alive:
                return True
        return False

    # -- public API -------------------------------------------------------
    def check(self, combo: int) -> dict | None:
        """Pure lookup: return milestone info for ``combo``, or None.

        No side effects.  The runner uses this to decide whether to fire
        and to read the base gold reward.
        """
        label = MILESTONES.get(combo)
        if label is None:
            return None
        return {"milestone": combo, "label": label, "gold": MILESTONE_GOLD[combo]}

    def trigger(self, combo: int, x: float, y: float, *,
                gold: float | None = None) -> dict | None:
        """Fire the celebration for ``combo`` at kill position ``(x, y)``.

        ``gold`` overrides the displayed/returned amount (the runner passes
        the post-multiplier award so the banner shows what the player
        actually gains).  Returns the milestone info dict (with the
        effective gold), or None if ``combo`` is not a milestone.
        """
        info = self.check(combo)
        if info is None:
            return None
        award = float(gold) if gold is not None else info["gold"]
        self._spawn_banner(combo, info["label"], award)
        self._spawn_ring(x, y)
        self._spawn_particles(x, y)
        self._flash = _FLASH_DUR
        return {"milestone": combo, "label": info["label"], "gold": award}

    def update(self, dt: float) -> None:
        # Banner.
        b = self._banner
        if b.alive:
            b.age += dt
            if b.age >= _BANNER_INTRO + _BANNER_HOLD + _BANNER_FADE:
                b.alive = False
        # Rings.
        for r in self._rings:
            if r.alive:
                r.age += dt
                if r.age >= _RING_DUR:
                    r.alive = False
        # Particles.
        for p in self._particles:
            p.update(dt)
        # Flash.
        if self._flash > 0:
            self._flash -= dt
            if self._flash < 0:
                self._flash = 0.0

    def draw(self, surf: pygame.Surface) -> None:
        """Draw rings + particles + banner + flash. Cheap to call every frame."""
        self._draw_rings(surf)
        self._draw_particles(surf)
        self._draw_banner(surf)
        self._draw_flash(surf)

    # -- spawners --------------------------------------------------------
    def _spawn_banner(self, milestone: int, label: str, gold: float) -> None:
        sub_text = f"Combo x{milestone}   +{format_number(gold)} gold"
        b = self._banner
        b.milestone = milestone
        b.label = label
        b.gold = gold
        b.age = 0.0
        b.alive = True
        # Render subtext once per trigger (not per frame).
        b.sub_img = font_lg(bold=True).render(sub_text, True, C.coin)

    def _spawn_ring(self, x: float, y: float) -> None:
        for r in self._rings:
            if not r.alive:
                r.x = x; r.y = y; r.age = 0.0; r.alive = True
                return
        if len(self._rings) < _MAX_RINGS:
            self._rings.append(_Ring(x=x, y=y, age=0.0, alive=True))
        else:
            oldest = min(self._rings, key=lambda r: r.age)
            oldest.x = x; oldest.y = y; oldest.age = 0.0; oldest.alive = True

    def _spawn_particles(self, x: float, y: float) -> None:
        for _ in range(_PARTICLE_COUNT):
            ang = rng().uniform(0, math.tau)
            sp = rng().uniform(120, 260)
            vx = math.cos(ang) * sp
            vy = math.sin(ang) * sp - 60.0      # bias upward
            life = rng().uniform(0.5, 0.9)
            size = rng().randint(2, 4)
            self._emit_particle(x, y, vx, vy, life, size)

    def _emit_particle(self, x: float, y: float, vx: float, vy: float,
                       life: float, size: int) -> None:
        pool = self._particles
        for p in pool:
            if not p.alive:
                p.reset(x, y, vx, vy, life, size)
                return
        if len(pool) < _MAX_PARTICLES:
            p = _Particle()
            p.reset(x, y, vx, vy, life, size)
            pool.append(p)
        else:
            # Pool full: overwrite the slot closest to expiring.
            oldest = min(pool, key=lambda p: p.life)
            oldest.reset(x, y, vx, vy, life, size)

    # -- draw helpers -----------------------------------------------------
    def _draw_rings(self, surf: pygame.Surface) -> None:
        scratch = self._ring_scratch
        if scratch is None:
            size = _RING_MAX_R * 2 + 8
            scratch = pygame.Surface((size, size), pygame.SRCALPHA).convert_alpha()
            self._ring_scratch = scratch
        c = scratch.get_width() // 2
        for r in self._rings:
            if not r.alive:
                continue
            t = r.age / _RING_DUR
            if t > 1.0:
                t = 1.0
            rad = int(_RING_MAX_R * ease_out_cubic(t))
            alpha = int(255 * (1.0 - t))
            if alpha <= 0 or rad < 2:
                continue
            width = max(2, int(6 * (1.0 - t)))
            col = lerp_color(C.gold, (255, 255, 230), t)
            scratch.fill((0, 0, 0, 0))
            pygame.draw.circle(scratch, (*col, alpha), (c, c), rad, width)
            surf.blit(scratch, (int(r.x) - c, int(r.y) - c))

    def _draw_particles(self, surf: pygame.Surface) -> None:
        scratch = self._part_scratch
        if scratch is None:
            d = _PARTICLE_MAX_R * 2 + 2
            scratch = pygame.Surface((d, d), pygame.SRCALPHA).convert_alpha()
            self._part_scratch = scratch
        for p in self._particles:
            p.draw(surf, scratch)

    def _draw_banner(self, surf: pygame.Surface) -> None:
        b = self._banner
        if not b.alive:
            return
        t = b.age
        intro_end = _BANNER_INTRO
        hold_end = _BANNER_INTRO + _BANNER_HOLD
        # Phase -> (scale, alpha).
        if t < intro_end:
            s = ease_out_cubic(t / intro_end)
            scale = _SCALE_MIN + (1.0 - _SCALE_MIN) * s
            alpha = 255
        elif t < hold_end:
            scale = 1.0
            alpha = 255
        else:
            scale = 1.0
            ft = (t - hold_end) / _BANNER_FADE
            if ft > 1.0:
                ft = 1.0
            alpha = int(255 * (1.0 - ft))
        if alpha <= 0:
            return

        labels = self._ensure_label_cache(b.milestone)
        shadows = self._ensure_shadow_cache(b.milestone)
        idx = int((scale - _SCALE_MIN) / max(1e-6, 1.0 - _SCALE_MIN)
                  * (_SCALE_STEPS - 1))
        if idx < 0:
            idx = 0
        elif idx >= _SCALE_STEPS:
            idx = _SCALE_STEPS - 1
        label_surf = labels[idx]
        shadow_surf = shadows[idx]

        cx = cfg.WINDOW_W // 2
        cy = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 24

        # Drop shadow (offset, dimmer) for punch.
        shadow_surf.set_alpha(int(alpha * 0.6))
        surf.blit(shadow_surf, shadow_surf.get_rect(center=(cx + 3, cy + 3)))
        # Label.
        label_surf.set_alpha(alpha)
        lr = label_surf.get_rect(center=(cx, cy))
        surf.blit(label_surf, lr)
        # Subtext (combo + gold), fades with the banner.
        if b.sub_img is not None:
            b.sub_img.set_alpha(alpha)
            surf.blit(b.sub_img,
                      b.sub_img.get_rect(center=(cx, cy + lr.h // 2 + 14)))

    def _draw_flash(self, surf: pygame.Surface) -> None:
        if self._flash <= 0:
            return
        t = 1.0 - (self._flash / _FLASH_DUR)   # 0 at start -> 1 at end
        if t > 1.0:
            t = 1.0
        alpha = int(255 * _FLASH_PEAK * (1.0 - t))
        if alpha <= 0:
            return
        ov = self._flash_surf
        if ov is None:
            ov = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H),
                                pygame.SRCALPHA).convert_alpha()
            self._flash_surf = ov
        ov.fill((255, 235, 180, alpha))
        surf.blit(ov, (0, 0))

    # -- cache builders (one-time, lazy) ----------------------------------
    def _ensure_label_cache(self, milestone: int) -> list[pygame.Surface]:
        cached = self._label_cache.get(milestone)
        if cached is not None:
            return cached
        label = MILESTONES[milestone]
        base = font_huge(bold=True).render(label, True, C.gold).convert_alpha()
        steps = self._build_scaled_steps(base)
        self._label_cache[milestone] = steps
        return steps

    def _ensure_shadow_cache(self, milestone: int) -> list[pygame.Surface]:
        cached = self._shadow_cache.get(milestone)
        if cached is not None:
            return cached
        label = MILESTONES[milestone]
        base = font_huge(bold=True).render(label, True, (20, 14, 30)).convert_alpha()
        steps = self._build_scaled_steps(base)
        self._shadow_cache[milestone] = steps
        return steps

    @staticmethod
    def _build_scaled_steps(base: pygame.Surface) -> list[pygame.Surface]:
        bw, bh = base.get_size()
        steps: list[pygame.Surface] = []
        for i in range(_SCALE_STEPS):
            t = i / max(1, _SCALE_STEPS - 1)
            scale = _SCALE_MIN + (1.0 - _SCALE_MIN) * t
            sw = max(1, int(bw * scale))
            sh = max(1, int(bh * scale))
            steps.append(pygame.transform.smoothscale(base, (sw, sh)))
        return steps
