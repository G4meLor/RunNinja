"""Floating damage numbers, polished.

A self-contained ``DamageFxSystem`` that replaces the plain-text floating
damage numbers from ``engine/fx.FXLayer.damage`` with typed, animated
variants:

  * **normal hit**  — small white number, gentle rise + fade.
  * **crit**        — larger, gold, ``★``-prefixed, with a brief scale-pop
                      animation (1.4 -> 1.0 over ~0.2 s) and a faster rise.
  * **boss hit**    — red, slightly bigger, with a small horizontal shake
                      while it lives (so boss damage feels weighty).
  * **block**       — small gray ``block N`` text shown when the ninja's
                      defense absorbs part of an incoming hit.

Design constraints (enforced here, matching the rest of the engine FX
modules):

  * **pygame primitives only** — ``font.render`` + ``surf.blit`` +
    ``set_alpha``; no external assets.
  * **pooled** — a fixed pool of ``_FloatText`` slots is recycled; the
    hot path never appends to or grows a list. When the pool is full the
    oldest active slot is reused.
  * **no per-frame allocations** — ``update`` only mutates slot fields;
    ``draw`` renders the cached font each frame (fonts themselves are
    cached in ``theme``) and calls ``set_alpha`` on the freshly rendered
    surface (``font.render`` is unavoidable but is the same pattern the
    existing ``FXLayer.draw`` / ``FireflyFxSystem.draw`` use, and the
    text count is small and bounded by the pool).

Integration (see ``docs/specs/damage_fx.md``):

  * ``Runner.__init__``:  ``self.damage_fx = DamageFxSystem()``.
  * ``Runner._on_enemy_dmg``:  call ``self.damage_fx.hit(x, y, amount,
    is_crit=is_crit, is_boss=is_boss)``.
  * ``Runner._on_ninja_dmg``:  call ``self.damage_fx.hit(x, y, amount,
    is_boss=False, blocked=<absorbed>)`` so a block label shows when
    defense absorbs part of the hit.
  * ``Runner.update``:  ``self.damage_fx.update(dt)`` next to
    ``self.fx.update(dt)``.
  * ``GameScreen.draw``:  ``runner.damage_fx.draw(surf)`` in place of
    (or alongside) ``runner.fx.draw(surf)``.
"""
from __future__ import annotations

import math

import pygame

from theme import C, font_sm, font_md, font_lg
from utils import clamp, ease_out_cubic


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_POOL_SIZE = 48           # max concurrent floating numbers; recycled

_LIFE_NORMAL = 0.7        # seconds a normal hit lives
_LIFE_CRIT = 0.9         # seconds a crit lives (longer so the pop reads)
_LIFE_BOSS = 0.8         # seconds a boss hit lives
_LIFE_BLOCK = 0.6        # seconds a block label lives

_RISE_NORMAL = -70.0     # px/s upward velocity for normal hits
_RISE_CRIT = -90.0       # px/s upward velocity for crits
_RISE_BOSS = -80.0       # px/s upward velocity for boss hits
_RISE_BLOCK = -55.0      # px/s upward velocity for block text
_GRAVITY = 60.0         # px/s^2 deceleration of the rise (settle)

_CRIT_POP_TIME = 0.2     # seconds the crit scale-pop lasts
_CRIT_POP_FROM = 1.4     # starting scale for the pop
_CRIT_POP_TO = 1.0       # ending scale for the pop

_BOSS_SHAKE_AMP = 2.0    # px of horizontal shake on boss hits
_BOSS_SHAKE_FREQ = 30.0  # rad/s of the boss shake

# Per-type colors.
_COL_NORMAL = C.text               # near-white
_COL_CRIT = C.gold                 # warm gold
_COL_BOSS = (255, 90, 100)        # vivid red
_COL_BLOCK = C.text_muted         # dim gray


# ---------------------------------------------------------------------------
# Pooled floating-number slot
# ---------------------------------------------------------------------------
class _FloatText:
    """One reusable floating damage number.

    Stored once in the pool and mutated in place; the hot path never
    allocates a new ``_FloatText``.
    """
    __slots__ = (
        "x", "y", "vy", "text", "color", "life", "max_life",
        "kind", "size_pop_t", "size_pop_max", "shake_phase", "active",
    )

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.vy: float = 0.0
        self.text: str = ""
        self.color: tuple[int, int, int] = (255, 255, 255)
        self.life: float = 0.0
        self.max_life: float = 0.0
        # "normal" | "crit" | "boss" | "block"
        self.kind: str = "normal"
        # Crit scale-pop timer (counts up from 0 to size_pop_max).
        self.size_pop_t: float = 0.0
        self.size_pop_max: float = 0.0
        # Boss shake phase (radians, advanced in update).
        self.shake_phase: float = 0.0
        self.active: bool = False

    def update(self, dt: float) -> None:
        self.y += self.vy * dt
        self.vy += _GRAVITY * dt
        self.life -= dt
        if self.size_pop_max > 0.0:
            self.size_pop_t += dt
        if self.kind == "boss":
            self.shake_phase += dt * _BOSS_SHAKE_FREQ
        if self.life <= 0.0:
            self.active = False

    # Scale factor for the crit pop. 1.0 when no pop is active or once
    # the pop has finished; otherwise eases from _CRIT_POP_FROM down to
    # _CRIT_POP_TO over the pop window.
    @property
    def scale(self) -> float:
        if self.size_pop_max <= 0.0:
            return 1.0
        if self.size_pop_t >= self.size_pop_max:
            return _CRIT_POP_TO
        p = self.size_pop_t / self.size_pop_max
        p = ease_out_cubic(clamp(p, 0.0, 1.0))
        return _CRIT_POP_FROM + (_CRIT_POP_TO - _CRIT_POP_FROM) * p

    # Horizontal shake offset for boss hits, 0 otherwise.
    @property
    def shake_dx(self) -> float:
        if self.kind != "boss":
            return 0.0
        # Fade the shake out with life so it settles before disappearing.
        a = clamp(self.life / self.max_life, 0.0, 1.0)
        return math.sin(self.shake_phase) * _BOSS_SHAKE_AMP * a


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class DamageFxSystem:
    """Owns the polished floating damage numbers.

    Construct one on the ``Runner`` (next to ``self.fx = FXLayer()``) and
    drive it from the combat callbacks. All state lives on the instance,
    so the hot path performs zero allocations once the pool is warm.
    """

    def __init__(self) -> None:
        # Fixed pool — recycled, never grown.
        self._pool: list[_FloatText] = [_FloatText() for _ in range(_POOL_SIZE)]
        # Per-frame alpha fade threshold (mirrors FXLayer.draw).
        self._fade_thresh = 0.6

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def hit(self, x: float, y: float, amount: float, *,
            is_crit: bool = False, is_boss: bool = False,
            blocked: float = 0.0) -> None:
        """Spawn a floating damage number for one hit.

        Parameters
        ----------
        x, y      : spawn position (screen coords; the runner passes the
                    enemy/ninja position).
        amount    : damage dealt (the number to display). Ignored when
                    ``blocked > 0`` and the hit was fully absorbed — in
                    that case only the block label is shown.
        is_crit   : render as a crit (gold, ★, scale-pop).
        is_boss   : render as a boss hit (red, bigger, shake).
        blocked   : amount absorbed by the ninja's defense. When > 0 an
                    extra ``block N`` label is spawned; when the hit was
                    fully absorbed (``amount <= 0``), only the block
                    label is shown.
        """
        # Pick a free slot, or recycle the one with the least remaining
        # life (so we never overwrite a freshly-spawned number).
        slot = self._next_free()
        slot.active = True
        slot.x = x
        slot.y = y - 8.0
        slot.shake_phase = 0.0
        slot.size_pop_t = 0.0
        slot.size_pop_max = 0.0

        # --- Block label (defense absorbed part of the hit). ---
        if blocked > 0.0:
            block_slot = self._next_free()
            block_slot.active = True
            block_slot.x = x + 14.0
            block_slot.y = y - 22.0
            block_slot.vy = _RISE_BLOCK
            block_slot.text = f"block {int(round(blocked))}"
            block_slot.color = _COL_BLOCK
            block_slot.life = _LIFE_BLOCK
            block_slot.max_life = _LIFE_BLOCK
            block_slot.kind = "block"
            block_slot.size_pop_t = 0.0
            block_slot.size_pop_max = 0.0
            block_slot.shake_phase = 0.0
            # If the hit was fully absorbed, skip the damage number.
            if amount <= 0.0:
                slot.active = False
                return

        # --- Decide kind / color / size / animation. ---
        if is_crit:
            slot.kind = "crit"
            slot.color = _COL_CRIT
            slot.vy = _RISE_CRIT
            slot.life = _LIFE_CRIT
            slot.max_life = _LIFE_CRIT
            slot.text = f"★{int(round(amount))}"   # ★ prefix
            slot.size_pop_max = _CRIT_POP_TIME
        elif is_boss:
            slot.kind = "boss"
            slot.color = _COL_BOSS
            slot.vy = _RISE_BOSS
            slot.life = _LIFE_BOSS
            slot.max_life = _LIFE_BOSS
            slot.text = f"{int(round(amount))}"
        else:
            slot.kind = "normal"
            slot.color = _COL_NORMAL
            slot.vy = _RISE_NORMAL
            slot.life = _LIFE_NORMAL
            slot.max_life = _LIFE_NORMAL
            slot.text = f"{int(round(amount))}"

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for s in self._pool:
            if s.active:
                s.update(dt)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        for s in self._pool:
            if not s.active:
                continue
            a = clamp(s.life / s.max_life, 0.0, 1.0)
            alpha = int(255 * a) if a > self._fade_thresh \
                else int(255 * (a / self._fade_thresh))
            if alpha <= 0:
                continue
            # Pick the font per kind: crit = lg bold, boss = md bold,
            # normal = sm, block = sm.
            if s.kind == "crit":
                f = font_lg(bold=True)
            elif s.kind == "boss":
                f = font_md(bold=True)
            else:
                f = font_sm(bold=(s.kind == "block"))
            img = f.render(s.text, True, s.color)
            # Crit scale-pop: scale the rendered surface around its center.
            scale = s.scale
            if abs(scale - 1.0) > 0.01:
                w = max(1, int(img.get_width() * scale))
                h = max(1, int(img.get_height() * scale))
                img = pygame.transform.smoothscale(img, (w, h))
            if alpha < 255:
                img.set_alpha(alpha)
            dx = s.shake_dx
            rect = img.get_rect(center=(int(s.x + dx), int(s.y)))
            surf.blit(img, rect)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    @property
    def active_count(self) -> int:
        return sum(1 for s in self._pool if s.active)

    def clear(self) -> None:
        for s in self._pool:
            s.active = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _next_free(self) -> _FloatText:
        """Return a free slot, or recycle the one with the least life."""
        free: _FloatText | None = None
        # Least remaining life among active slots (for recycling).
        least: _FloatText | None = None
        least_life = float("inf")
        for s in self._pool:
            if not s.active:
                return s
            if s.life < least_life:
                least_life = s.life
                least = s
        # Pool exhausted — recycle the soonest-to-die slot.
        return least if least is not None else self._pool[0]
