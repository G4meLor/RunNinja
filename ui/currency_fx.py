"""Currency pill FX: animated icons, +N floaters, and tooltips.

A self-contained ``CurrencyFxSystem`` that polishes the HUD currency
pills (Gold / Elixir / Amber / Medals):

* an **animated icon** — each pill's icon breathes with a soft glow
  ring that pulses, and briefly flashes when its currency ticks up;
* a **+N floater** — when a currency increases over a short window, a
  green "+N" text rises above the pill and fades;
* a **tooltip** — ``tooltip(name)`` returns a description string the
  screen can feed to its hover-tooltip manager.

Task 27 / pl-juice-polish additions:
  * ``count_up(old, new, duration, t)`` — a free function that animates
    a currency display from ``old`` to ``new`` over ``duration`` seconds
    (no instant snapping). The screen uses this to count up the gold
    pill when the player earns a chunk (e.g. a boss kill, an offline
    reward) instead of snapping to the new value.
  * ``gold_milestone_crossed(old, new)`` — returns the highest gold
    milestone (1k / 10k / 100k / 1M / ...) the player crossed between
    ``old`` and ``new`` (or None). The screen uses this to celebrate
    gold milestones (a brief flash + a toast).

All rendering uses pygame primitives + the cached theme fonts.  The
per-frame hot path performs zero allocations once warm: floater slots
live in a fixed pool, text surfaces are rendered once at spawn time,
and the glow/flash rings use a single reusable SRCALPHA scratch
surface (grown lazily, then reused).

Integration (see docs/specs/currency_fx.md):
  * ``GameScreen`` owns one ``CurrencyFxSystem``, calls ``snapshot(state)``
    once at construction, ``update(dt, state)`` each frame, and
    ``draw(surf, pill_rects)`` after drawing the pills.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

from theme import C, font_sm
from utils import format_number, ease_out_cubic, clamp, ease_in_out_cubic


# ---------------------------------------------------------------------------
# Task 27: Count-up currency + gold milestones
# ---------------------------------------------------------------------------
# Gold milestones (the values that trigger a celebration when crossed).
# Tuned so the first few milestones come quickly (1k, 10k) and the later
# ones are long-term goals (1M, 1B). The screen celebrates the highest
# milestone crossed in a single tick (so a boss kill that jumps from 900
# to 1,100 celebrates the 1k milestone, not the 10k).
_GOLD_MILESTONES: tuple[float, ...] = (
    1_000.0,
    10_000.0,
    100_000.0,
    1_000_000.0,
    10_000_000.0,
    100_000_000.0,
    1_000_000_000.0,
)


def count_up(old: float, new: float, duration: float, t: float) -> float:
    """Animate a currency display from ``old`` to ``new`` over ``duration``.

    Returns the displayed value at time ``t`` (seconds since the count-up
    started). At ``t=0`` returns ``old``; at ``t>=duration`` returns
    ``new`` (clamped, no overshoot). Midway, returns an eased value
    between ``old`` and ``new`` (no instant snapping).

    The easing is ``ease_in_out_cubic`` (a smooth ease-in + ease-out) so
    the count-up feels snappy at the start + settles at the end, rather
    than a linear ramp (which feels mechanical) or a pure ease-out (which
    front-loads the change and feels like a snap).

    ``duration`` <= 0 returns ``new`` immediately (the caller asked for
    an instant jump, not a count-up). ``old == new`` returns ``old`` (no
    change to animate).
    """
    if duration <= 0 or old == new:
        return new
    p = clamp(t / duration, 0.0, 1.0)
    eased = ease_in_out_cubic(p)
    return old + (new - old) * eased


def gold_milestone_crossed(old: float, new: float) -> Optional[float]:
    """The highest gold milestone crossed between ``old`` and ``new``.

    Returns the highest value in ``_GOLD_MILESTONES`` that is in the
    half-open interval (old, new] (i.e. the player was below it at
    ``old`` and reached it at ``new``). Returns None if no milestone was
    crossed (e.g. the gain was small, or the player was already past the
    highest milestone).

    The "highest" is the one the screen celebrates -- a boss kill that
    jumps from 900 to 1,100 crosses the 1k milestone; a gain from 9,000
    to 11,000 crosses the 10k milestone (the 1k milestone was already
    crossed in a previous tick). Returning the highest (not every crossed
    milestone) keeps the celebration to one per tick.
    """
    if new <= old:
        return None
    crossed: Optional[float] = None
    for m in _GOLD_MILESTONES:
        if old < m <= new:
            crossed = m
    return crossed


# ---------------------------------------------------------------------------
# Currency metadata
# ---------------------------------------------------------------------------
_CURRENCIES: Tuple[str, ...] = ("Gold", "Elixir", "Amber", "Medals")

# Pill label -> GameState attribute name.
_STATE_ATTR: Dict[str, str] = {
    "Gold": "gold",
    "Elixir": "elixir",
    "Amber": "amber",
    "Medals": "medals",
}

# Pill label -> icon color (matches the colors screen_game._draw_hud uses).
_ICON_COLOR: Dict[str, Tuple[int, int, int]] = {
    "Gold": C.gold,
    "Elixir": (120, 220, 200),
    "Amber": (255, 180, 60),
    "Medals": (200, 200, 220),
}

# Tooltip text (first line is the title, rendered bold by TooltipManager).
_TOOLTIPS: Dict[str, str] = {
    "Gold": (
        "Gold\n"
        "The soft currency. Dropped by monsters and produced by "
        "buildings every second. Spent on run upgrades and buildings; "
        "reset on ascension."
    ),
    "Elixir": (
        "Elixir\n"
        "The prestige currency. Earned by ascending, based on lifetime "
        "gold. Spent on permanent skill-tree nodes that persist across "
        "ascensions."
    ),
    "Amber": (
        "Amber\n"
        "The gacha currency. Earned from daily quests and achievements. "
        "Spent on pet pulls and cosmetic items."
    ),
    "Medals": (
        "Medals\n"
        "The milestone currency. Earned from daily quests and "
        "achievements. Tracks your long-term progress."
    ),
}


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_WINDOW = 0.50             # seconds — delta accumulation window
_MIN_GAIN = 1.0            # don't floater for sub-1 gains (avoids "+0")
_FLOAT_DUR = 1.00          # seconds — floater lifetime
_FLOAT_RISE = 20           # px — floater rises over its life
_PULSE_PERIOD = 2.4        # seconds — icon breathing period
_FLASH_DUR = 0.40          # seconds — icon flash on tick
_FLASH_MAX_R = 16          # px — peak flash ring radius
_MAX_FLOATS = 12           # floater pool size (3 per currency)
_GLOW_COLOR = (130, 230, 160)    # green for the +N text (C.text_good)


# ---------------------------------------------------------------------------
# Floater slot (pooled — recycled, never re-allocated)
# ---------------------------------------------------------------------------
class _Floater:
    __slots__ = ("name", "y_off", "img", "shadow", "t", "active")

    def __init__(self) -> None:
        self.name: str = ""
        self.y_off: float = 0.0
        self.img: Optional[pygame.Surface] = None
        self.shadow: Optional[pygame.Surface] = None
        self.t: float = 0.0
        self.active: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _brighten(color: Tuple[int, int, int], t: float = 0.5) -> Tuple[int, int, int]:
    """Blend ``color`` toward white by fraction ``t`` (0..1)."""
    return (min(255, int(color[0] + (255 - color[0]) * t)),
            min(255, int(color[1] + (255 - color[1]) * t)),
            min(255, int(color[2] + (255 - color[2]) * t)))


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class CurrencyFxSystem:
    """Owns the currency-pill fx layer for the HUD.

    Construct one per ``GameScreen`` (or share one on the game object).
    All state lives on the instance, so the hot path performs zero
    allocations once the pools are warm.

    Lifecycle::

        fx = CurrencyFxSystem()
        fx.snapshot(state)              # record baseline values
        fx.update(dt, state)            # each frame: deltas + floaters
        fx.draw(surf, pill_rects)      # after the pills are drawn
        fx.tooltip("Gold")             # -> description string
    """

    def __init__(self) -> None:
        # Per-currency baseline (value at the start of the current window).
        self._baseline: Dict[str, float] = {n: 0.0 for n in _CURRENCIES}
        # Window timer.
        self._window_t: float = 0.0
        # Per-currency flash timer (decays; >0 means flashing).
        self._flash: Dict[str, float] = {n: 0.0 for n in _CURRENCIES}
        # Fixed floater pool.
        self._floaters: List[_Floater] = [_Floater() for _ in range(_MAX_FLOATS)]
        # Reusable scratch surface for glow/flash rings (grown lazily).
        self._scratch: Optional[pygame.Surface] = None
        self._scratch_size: int = 0
        # Accessibility: skip the breathing pulse when True.
        self.reduced_motion: bool = False

    # ------------------------------------------------------------------
    # Baseline snapshot
    # ------------------------------------------------------------------
    def snapshot(self, state) -> None:
        """Record current currency values as the delta baseline.

        Call once at construction (or when the screen loads) so the first
        ``update`` doesn't treat the initial values as a gain.
        """
        for name in _CURRENCIES:
            self._baseline[name] = float(getattr(state, _STATE_ATTR[name], 0))

    # ------------------------------------------------------------------
    # Per-frame update: compute deltas, drive floaters
    # ------------------------------------------------------------------
    def update(self, dt: float, state) -> None:
        # Advance the window timer.
        self._window_t += dt
        # Decay per-currency flashes.
        for name in _CURRENCIES:
            if self._flash[name] > 0:
                self._flash[name] = max(0.0, self._flash[name] - dt)
        # Advance floaters (rise + fade).
        for f in self._floaters:
            if not f.active:
                continue
            f.t += dt
            if f.t >= _FLOAT_DUR:
                f.active = False
            else:
                eased = ease_out_cubic(f.t / _FLOAT_DUR)
                f.y_off = -_FLOAT_RISE * eased
        # Handle decreases (spending / ascension reset): re-baseline
        # immediately so a subsequent gain doesn't show a stale delta.
        for name in _CURRENCIES:
            current = float(getattr(state, _STATE_ATTR[name], 0))
            if current < self._baseline[name]:
                self._baseline[name] = current
        # Window flush: emit floaters for accumulated gains.
        if self._window_t < _WINDOW:
            return
        self._window_t = 0.0
        for name in _CURRENCIES:
            current = float(getattr(state, _STATE_ATTR[name], 0))
            gain = current - self._baseline[name]
            if gain >= _MIN_GAIN:
                self._spawn_floater(name, gain)
            self._baseline[name] = current

    # ------------------------------------------------------------------
    # Draw: animated icons + floaters over the pills
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface,
             pill_rects: Optional[Dict[str, pygame.Rect]] = None) -> None:
        """Render the animated icons and +N floaters over the pills.

        ``pill_rects`` maps the currency label ("Gold", "Elixir", ...) to
        the pygame.Rect of the pill on screen.  The screen builds this
        dict in ``_draw_hud`` while laying out the pills, then passes it
        here so the fx can position the icon glow/flash and the floaters.
        """
        if not pill_rects:
            pill_rects = {}
        t = pygame.time.get_ticks() / 1000.0
        # --- Animated icons (breathing glow + flash) ---
        for name, rect in pill_rects.items():
            if name not in _CURRENCIES:
                continue
            cx = rect.x + 14
            cy = rect.y + 14
            color = _ICON_COLOR[name]
            # Breathing glow ring (skipped in reduced-motion).
            if not self.reduced_motion:
                pulse = 0.5 + 0.5 * math.sin(t * (math.tau / _PULSE_PERIOD))
                ring_r = int(9 + 2 * pulse)
                ring_a = int(70 + 60 * pulse)
                self._draw_ring(surf, cx, cy, ring_r, color, ring_a, 2)
            # Flash on tick.
            flash_t = self._flash.get(name, 0.0)
            if flash_t > 0:
                p = 1.0 - flash_t / _FLASH_DUR
                r = int(8 + (_FLASH_MAX_R - 8) * ease_out_cubic(p))
                a = int(220 * (1.0 - p))
                self._draw_ring(surf, cx, cy, r, _brighten(color, 0.5), a, 2)
        # --- Floaters ---
        for f in self._floaters:
            if f.active:
                self._draw_floater(surf, f, pill_rects)

    # ------------------------------------------------------------------
    # Tooltip
    # ------------------------------------------------------------------
    def tooltip(self, currency_name: str) -> str:
        """Return a description string for ``currency_name``.

        The string may contain newlines (the first line is the title,
        rendered bold by ``TooltipManager``).  Returns "" for unknown
        currency names.
        """
        return _TOOLTIPS.get(currency_name, "")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _spawn_floater(self, name: str, gain: float) -> None:
        slot = self._next_free(self._floaters)
        text = f"+{format_number(gain)}"
        fnt = font_sm(bold=True)
        slot.name = name
        slot.img = fnt.render(text, True, _GLOW_COLOR)
        slot.shadow = fnt.render(text, True, (0, 0, 0))
        slot.y_off = 0.0
        slot.t = 0.0
        slot.active = True
        # Trigger the icon flash.
        self._flash[name] = _FLASH_DUR

    def _draw_floater(self, surf: pygame.Surface, f: _Floater,
                      pill_rects: Dict[str, pygame.Rect]) -> None:
        pill = pill_rects.get(f.name)
        if pill is None or f.img is None:
            return
        p = f.t / _FLOAT_DUR
        alpha = int(255 * (1.0 - ease_out_cubic(p)))
        if alpha <= 0:
            return
        x = pill.centerx
        y = pill.y + int(f.y_off)
        f.img.set_alpha(alpha)
        if f.shadow is not None:
            f.shadow.set_alpha(min(180, alpha))
            surf.blit(f.shadow, f.shadow.get_rect(midtop=(x + 1, y + 1)))
        surf.blit(f.img, f.img.get_rect(midtop=(x, y)))

    def _draw_ring(self, surf: pygame.Surface, cx: int, cy: int,
                   radius: int, color: Tuple[int, int, int],
                   alpha: int, width: int = 2) -> None:
        if alpha <= 0 or radius <= 0:
            return
        needed = radius * 2 + 4
        if self._scratch is None or self._scratch_size < needed:
            self._scratch = pygame.Surface(
                (needed, needed), pygame.SRCALPHA
            ).convert_alpha()
            self._scratch_size = needed
        s = self._scratch
        s.fill((0, 0, 0, 0))
        mid = self._scratch_size // 2
        pygame.draw.circle(s, (*color, alpha), (mid, mid), radius, width)
        surf.blit(s, (cx - mid, cy - mid))

    @staticmethod
    def _next_free(pool: List[_Floater]) -> _Floater:
        for slot in pool:
            if not slot.active:
                return slot
        return pool[0]  # pool exhausted — recycle the first slot
