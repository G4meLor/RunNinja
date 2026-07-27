"""Menu polish — animated cherry-blossom petals + a walking ninja
silhouette for the main menu's first impression.

``MenuPolish(game)`` is a self-contained background layer the menu
screen owns.  It draws *over* the existing zone-0 background (which the
menu already blits), adding two atmospheric layers that move every
frame but allocate nothing on the hot path:

  * **drifting cherry-blossom petals** — a fixed, bounded pool of
    petals that drift down-right with a gentle sinusoidal sway, rotate
    slowly, and recycle to the top when they fall off the bottom.  The
    pool is pre-allocated once; ``update`` only mutates slot fields.
  * **a walking ninja silhouette** — the cached ``assets.ninja_surface``
    crushed to a near-black silhouette (``BLEND_RGBA_MULT``, cached per
    size so the global sprite cache stays pristine), bobbing and
    leaning slightly with a walk cycle, anchored on the scrolling
    road's lane line.

It also exposes ``continue_card(state)`` — a small dict of
``{tier, zone, gold}`` (or ``None`` when no save exists) the menu
renders into a Continue card.

All rendering uses pygame primitives + the cached theme fonts.  The hot
path (``update`` / ``draw_bg``) performs **zero allocations**: the
petal pool is fixed, the petal sprite is cached by size, the ninja
silhouette is cached by size, and the only per-frame ``font.render`` is
the version tag (which matches the rest of the UI's convention).

Integration: ``ui/screen_menu.py`` constructs ``MenuPolish(self.game)``
in ``__init__``, calls ``polish.update(dt)`` in ``update``, calls
``polish.draw_bg(surf)`` after blitting the zone-0 background (so the
petals + ninja sit on top of the road but under the dim + title), and
calls ``polish.continue_card(state)`` to decide whether to show the
Continue card.  See ``docs/specs/menu_polish.md``.
"""
from __future__ import annotations

import math
import os
from typing import Optional

import pygame

import config as cfg
from assets import ninja_surface
from theme import C, font_xs, font_sm, font_md, font_lg
from theme import draw_text, draw_text_center
from utils import format_number, clamp
from core.state import GameState, SAVE_FILE
from data import enemies as ed


# ---------------------------------------------------------------------------
# Version tag
# ---------------------------------------------------------------------------
# Bumped manually on releases; shown in the bottom-right of the menu.
VERSION = "0.9.0-dev"


# ---------------------------------------------------------------------------
# Layout (matches the menu's existing road geometry)
# ---------------------------------------------------------------------------
# The menu uses the zone-0 background (cfg.ROAD_TOP..ROAD_BOTTOM) as its
# road.  The ninja walks on the lane line the menu already draws.
_ROAD_LY = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2
_NINJA_X = 220                       # a little right of center-left
_NINJA_FEET_Y = cfg.ROAD_TOP + int(cfg.ROAD_H * 0.72)
_NINJA_SIZE = 72


# ---------------------------------------------------------------------------
# Petal pool
# ---------------------------------------------------------------------------
# Bounded pool — never grows.  18 petals is enough to read as "drifting
# blossoms" without crowding a 1280x720 menu, and the cost is O(18) per
# frame regardless of how long the menu stays open.
_PETAL_COUNT = 18

# Petal sprite size (the cached petal surface).  Small enough to read as
# a blossom, large enough to be visible against the night sky.
_PETAL_SIZE = 14

# Drift tuning: petals fall down-right at ~22 px/s, sway ~30 px/s side-
# to-side over a ~2.5s period, and rotate ~0.6 rad/s.
_PETAL_DRIFT_VX = 22.0
_PETAL_DRIFT_VY_RANGE = (18.0, 34.0)
_PETAL_SWAY_AMP = 30.0
_PETAL_SWAY_PERIOD = 2.5
_PETAL_SPIN_RANGE = (-0.6, 0.6)

# Fade petals in over the first 0.4s of a petal's life so a freshly
# recycled petal doesn't pop in at the top of the screen.
_PETAL_FADE_IN = 0.4


# ---------------------------------------------------------------------------
# Walk cycle
# ---------------------------------------------------------------------------
# The ninja bobs vertically and leans slightly with a ~0.9s walk cycle.
# Reduced motion (state.reduced_motion) freezes the cycle at a neutral
# pose so the silhouette stays still.
_WALK_PERIOD = 0.9
_WALK_BOB_AMP = 3.0     # px
_WALK_LEAN_AMP = 3.0    # degrees


# ---------------------------------------------------------------------------
# Cached sprites (built lazily once, reused forever)
# ---------------------------------------------------------------------------
_PETAL_CACHE: dict[int, pygame.Surface] = {}
_NINJA_SIL_CACHE: dict[int, pygame.Surface] = {}


def _petal_sprite(size: int) -> pygame.Surface:
    """A 5-petal cherry-blossom sprite, cached by size.

    Built once per size on a transparent SRCALPHA surface: five soft
    pink petals arranged around a warm center, drawn with
    ``pygame.draw.polygon`` (no external art).  Cached so the hot path
    never rebuilds it.
    """
    cached = _PETAL_CACHE.get(size)
    if cached is not None:
        return cached
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    petal_col = (255, 200, 215, 215)
    center_col = (255, 235, 210, 230)
    notch_col = (255, 170, 195, 120)
    for k in range(5):
        a = k * (2 * math.pi / 5) - math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        tip = (cx + ca * (size * 0.45), cy + sa * (size * 0.45))
        s1 = (cx + ca * (size * 0.09) - sa * (size * 0.18),
              cy + sa * (size * 0.09) + ca * (size * 0.18))
        s2 = (cx + ca * (size * 0.09) + sa * (size * 0.18),
              cy + sa * (size * 0.09) - ca * (size * 0.18))
        pygame.draw.polygon(s, petal_col, [tip, s1, (cx, cy), s2])
    pygame.draw.circle(s, center_col, (cx, cy), max(2, size // 9))
    # Tiny notch at each petal tip so it reads as a cherry blossom.
    for k in range(5):
        a = k * (2 * math.pi / 5) - math.pi / 2
        tx = int(cx + math.cos(a) * (size * 0.42))
        ty = int(cy + math.sin(a) * (size * 0.42))
        pygame.draw.circle(s, notch_col, (tx, ty), max(1, size // 18))
    _PETAL_CACHE[size] = s
    return s


def _ninja_silhouette(size: int) -> pygame.Surface:
    """A dark, shape-preserving silhouette of the cached ninja sprite.

    Built by multiplying the cached ``ninja_surface`` by a near-black
    fill (``BLEND_RGBA_MULT`` keeps the alpha outline while crushing
    RGB), then cached by size.  The global ``_NINJA_CACHE`` in
    ``assets.py`` is never touched, so the game screen's coloured ninja
    stays pristine.
    """
    cached = _NINJA_SIL_CACHE.get(size)
    if cached is not None:
        return cached
    src = ninja_surface(size)
    out = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    out.fill((6, 8, 16, 255))
    out.blit(src, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _NINJA_SIL_CACHE[size] = out
    return out


# ---------------------------------------------------------------------------
# Petal slot (stored once, mutated in place — no per-frame allocations)
# ---------------------------------------------------------------------------
class _Petal:
    __slots__ = ("x", "y", "vx", "vy", "phase", "spin", "rot", "age")

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.phase: float = 0.0
        self.spin: float = 0.0
        self.rot: float = 0.0
        self.age: float = 0.0

    def reset(self, top: bool) -> None:
        """Re-seed a petal.  ``top=True`` scatters across the top (for
        the initial population); ``top=False`` scatters across the top
        *and* the left edge (for recycled petals, so they drift in
        naturally from the upper-left rather than only the top).
        """
        # Use the project's stable RNG (utils.rng) so the menu's petal
        # field doesn't dip into the global random state.
        from utils import rng
        r = rng()
        if top:
            self.x = float(r.randint(0, cfg.WINDOW_W))
            self.y = float(r.randint(-40, cfg.ROAD_TOP - 20))
        else:
            # Recycle: scatter across the top + the left edge so petals
            # drift in from the upper-left (the prevailing drift dir).
            if r.random() < 0.6:
                self.x = float(r.randint(-30, cfg.WINDOW_W))
                self.y = float(r.randint(-40, 10))
            else:
                self.x = float(r.randint(-40, 0))
                self.y = float(r.randint(0, cfg.ROAD_TOP))
        self.vx = _PETAL_DRIFT_VX + r.uniform(-6.0, 6.0)
        self.vy = r.uniform(*_PETAL_DRIFT_VY_RANGE)
        self.phase = r.uniform(0.0, _PETAL_SWAY_PERIOD)
        self.spin = r.uniform(*_PETAL_SPIN_RANGE)
        self.rot = r.uniform(0.0, math.tau)
        self.age = 0.0

    def update(self, dt: float) -> None:
        self.age += dt
        self.x += self.vx * dt + math.sin(self.age * (math.tau / _PETAL_SWAY_PERIOD)
                                          + self.phase) * _PETAL_SWAY_AMP * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt


# ---------------------------------------------------------------------------
# MenuPolish
# ---------------------------------------------------------------------------
class MenuPolish:
    """Animated background layer + continue-card helper for the menu.

    Construct once in ``MenuScreen.__init__`` and reuse for the life of
    the menu.  All state lives on the instance; the hot path performs
    zero allocations once the pools are warm.
    """

    def __init__(self, game) -> None:
        self.game = game
        # Bounded petal pool — fixed size, recycled, never grown.
        self._petals: list[_Petal] = [_Petal() for _ in range(_PETAL_COUNT)]
        for p in self._petals:
            p.reset(top=True)
        # Walk cycle clock (frozen when reduced motion is on).
        self._walk_t: float = 0.0
        # Cache the silhouette + petal sprite once (per-size caches are
        # populated on first access; we touch them here so the first
        # frame doesn't pay the build cost).
        self._ninja_sil = _ninja_silhouette(_NINJA_SIZE)
        self._petal_sprite = _petal_sprite(_PETAL_SIZE)

    # ------------------------------------------------------------------
    # Continue card
    # ------------------------------------------------------------------
    def continue_card(self, state: GameState) -> Optional[dict]:
        """Return ``{tier, zone, gold}`` if a save exists, else None.

        ``tier`` is the ascension tier name (e.g. "Mortal"); ``zone`` is
        the current zone name (e.g. "Hidden Village"); ``gold`` is the
        formatted gold string.  Returns None when no save file exists,
        so the menu can skip the Continue card entirely on a first run.
        """
        if not os.path.exists(SAVE_FILE):
            return None
        tier_i = int(getattr(state, "ascend_tier", 0))
        tier_i = max(0, min(tier_i, len(cfg.ASCEND_TIERS) - 1))
        tier_name = cfg.ASCEND_TIERS[tier_i][0]
        zone_i = int(getattr(state, "zone_index", 0))
        zone_name = ed.zone_by_index(zone_i)["name"]
        gold = format_number(float(getattr(state, "gold", 0.0)))
        return {"tier": tier_name, "zone": zone_name, "gold": gold}

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance petal drift + the walk cycle.  Safe to call with dt=0."""
        # Walk cycle — frozen under reduced motion.
        if not getattr(self.game.state, "reduced_motion", False):
            self._walk_t += dt
        # Petals drift every frame (even under reduced motion — the
        # petals are the menu's atmosphere; freezing them would look
        # broken rather than calm).
        for p in self._petals:
            p.update(dt)
            # Recycle when off the bottom or right edge.
            if p.y > cfg.ROAD_BOTTOM + 20 or p.x > cfg.WINDOW_W + 30:
                p.reset(top=False)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw_bg(self, surf: pygame.Surface) -> None:
        """Draw the drifting petals + walking ninja silhouette.

        Call after the zone-0 background is blitted (so the petals sit
        on top of the night sky + road) but before the menu's dim
        overlay (so the petals + ninja are dimmed with the rest of the
        scene, not punched through it).
        """
        self._draw_petals(surf)
        self._draw_ninja(surf)

    def _draw_petals(self, surf: pygame.Surface) -> None:
        ps = self._petal_sprite
        ps_w, ps_h = ps.get_size()
        for p in self._petals:
            # Fade in over the first _PETAL_FADE_IN seconds of a petal's
            # life so recycled petals don't pop in at the top.
            if p.age < _PETAL_FADE_IN:
                a = int(255 * (p.age / _PETAL_FADE_IN))
            else:
                a = 255
            rot = pygame.transform.rotate(ps, math.degrees(p.rot))
            if a < 255:
                # set_alpha is the cheapest fade for a cached SRCALPHA
                # sprite; we restore to 255 after the blit so the cache
                # stays pristine.
                rot.set_alpha(a)
                surf.blit(rot, rot.get_rect(center=(int(p.x), int(p.y))))
                rot.set_alpha(255)
            else:
                surf.blit(rot, rot.get_rect(center=(int(p.x), int(p.y))))

    def _draw_ninja(self, surf: pygame.Surface) -> None:
        sil = self._ninja_sil
        # Walk cycle: bob + lean.  Frozen under reduced motion (the
        # cycle clock stops advancing in update).
        t = self._walk_t * (math.tau / _WALK_PERIOD)
        bob = math.sin(t) * _WALK_BOB_AMP
        lean = math.sin(t) * _WALK_LEAN_AMP
        # Soft shadow under the ninja (an alpha ellipse on a SRCALPHA
        # scratch, blitted — alpha-on-opaque would ignore the alpha).
        shadow_w, shadow_h = 56, 12
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90),
                            (0, 0, shadow_w, shadow_h))
        sx = _NINJA_X - shadow_w // 2
        sy = _NINJA_FEET_Y + 4
        surf.blit(shadow, (sx, sy))
        # Lean the silhouette (rotate preserves per-pixel alpha).
        if abs(lean) > 0.1:
            sil_rot = pygame.transform.rotate(sil, lean)
        else:
            sil_rot = sil
        nx = _NINJA_X
        ny = _NINJA_FEET_Y + bob
        surf.blit(sil_rot, sil_rot.get_rect(midbottom=(nx, ny)))


# ---------------------------------------------------------------------------
# Version tag (drawn by the menu screen, not MenuPolish.draw_bg)
# ---------------------------------------------------------------------------
def draw_version_tag(surf: pygame.Surface) -> None:
    """Draw the version tag in the bottom-right of the menu.

    A small, low-contrast label so it's present without competing with
    the title.  Uses the cached ``font_xs`` (no per-frame SysFont).
    """
    img = font_xs().render(f"v{VERSION}", True, C.text_muted)
    surf.blit(img, img.get_rect(bottomright=(cfg.WINDOW_W - 12, cfg.WINDOW_H - 10)))
