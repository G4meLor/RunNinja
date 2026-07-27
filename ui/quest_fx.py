"""Quest completion juice — toast, medal/amber burst, animated checkmark.

A self-contained fx layer for the quests screen.  When a daily quest
completes (auto-claimed by ``core/quests.update_daily_progress``), the
screen routes the completion here and the system fires:

  * a small medal + amber particle burst at the quest row,
  * an expanding ring radiating from the row,
  * a floating "+N medals  +N amber" reward text that rises and fades,
  * a transient toast banner at the top of the quest panel,
  * a per-quest completion pulse the screen reads to animate the
    "✓ Claimed" checkmark (scale-in + fade-in).

``claim_all(x, y, medals, amber)`` drives the "Claim All" button: a
bigger consolidated burst + toast.

``countdown(state)`` returns ``(h, m)`` until the next daily refresh
(``state.daily_refresh``), for the screen to draw a "refreshes in
HH:MM" timer.

All rendering uses pygame primitives + cached theme fonts.  Effect
slots live in fixed pools and rendered text surfaces are cached at
spawn time, so the per-frame hot path performs zero allocations once
warm.

Integration (see docs/specs/quest_fx.md):
  * ``QuestsScreen`` owns one ``QuestFxSystem``.
  * Each ``update``, the screen diffs ``state.daily_quests``'s
    ``claimed`` flags against a ``_seen_claims`` set and calls
    ``fx.on_complete(row_x, row_y, medals, amber, quest_id, name)``
    for each newly-claimed quest.  (``core/quests.update_daily_progress``
    already returns the completed list — the runner may stash it for
    the screen to drain instead; both reach the same fx.)
  * ``QuestsScreen.draw`` reads ``fx.checkmark_anim(quest_id)`` to
    animate the "✓ Claimed" checkmark, draws the countdown via
    ``fx.countdown(state)``, then calls ``fx.draw(surf)``.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import pygame

from theme import C, font_sm, font_md
from utils import clamp, ease_out_cubic


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_BURST_LIFE      = 0.60    # particle lifetime (s)
_BURST_SPEED     = 150.0   # particle initial speed (px/s)
_BURST_GRAVITY   = 220.0   # particle gravity (px/s^2)
_BURST_COUNT     = 16      # particles per completion (split medal/amber)
_PART_SIZE       = 3       # particle radius (px)

_RING_DUR        = 0.55    # expanding ring lifetime (s)
_RING_MAX_R      = 54      # peak ring radius (px)

_FLOAT_DUR       = 0.90    # floating reward text lifetime (s)
_FLOAT_RISE      = 38      # pixels the text rises over its life

_PULSE_DUR       = 0.60    # "✓ Claimed" checkmark animation length (s)

_TOAST_LIFE      = 3.0     # toast banner lifetime (s)
_TOAST_Y         = 108     # toast banner top y (below the currency pills)

# Pool sizes — generous enough for rapid multi-completions without growth.
_MAX_PARTICLES   = 80
_MAX_FLOATS     = 6
_MAX_PULSES     = 6       # one per daily quest + buffer
_MAX_TOASTS     = 3

# Reward colors (match the currency pills on the quests screen).
_MEDAL_COLOR = (200, 200, 220)
_AMBER_COLOR = (255, 180, 60)


# ---------------------------------------------------------------------------
# Effect slots (stored once, mutated in place)
# ---------------------------------------------------------------------------
class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life",
                 "color", "size", "active")

    def __init__(self) -> None:
        self.x = 0.0; self.y = 0.0; self.vx = 0.0; self.vy = 0.0
        self.life = 0.0; self.max_life = 0.0
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.size = _PART_SIZE
        self.active = False


class _FloatText:
    __slots__ = ("text", "x", "y0", "y", "color", "t",
                 "active", "img", "shadow")

    def __init__(self) -> None:
        self.text = ""
        self.x = 0; self.y0 = 0; self.y = 0
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.t = 0.0
        self.active = False
        self.img: Optional[pygame.Surface] = None
        self.shadow: Optional[pygame.Surface] = None


class _Pulse:
    __slots__ = ("quest_id", "x", "y", "color", "t", "active")

    def __init__(self) -> None:
        self.quest_id = ""
        self.x = 0; self.y = 0
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.t = 0.0
        self.active = False


class _Toast:
    __slots__ = ("text", "color", "t", "max_life",
                 "active", "img", "bg")

    def __init__(self) -> None:
        self.text = ""
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.t = 0.0
        self.max_life = _TOAST_LIFE
        self.active = False
        self.img: Optional[pygame.Surface] = None
        self.bg: Optional[pygame.Surface] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ease_out_back(t: float, s: float = 1.70158) -> float:
    """Overshooting ease-out — a subtle bounce on the checkmark scale-in."""
    t = clamp(t, 0.0, 1.0)
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def _split_burst(count: int) -> Tuple[int, int]:
    half = count // 2
    return half, count - half


# ---------------------------------------------------------------------------
# The system
# ---------------------------------------------------------------------------
class QuestFxSystem:
    """Owns the quest-completion fx layer for the quests screen.

    Construct one per ``QuestsScreen`` (or share one on the game object).
    All state lives on the instance, so the hot path performs zero
    allocations once the pools are warm.
    """

    def __init__(self) -> None:
        # Fixed pools — recycled, never grown.
        self._particles: List[_Particle] = [_Particle() for _ in range(_MAX_PARTICLES)]
        self._floats: List[_FloatText] = [_FloatText() for _ in range(_MAX_FLOATS)]
        self._pulses: List[_Pulse] = [_Pulse() for _ in range(_MAX_PULSES)]
        self._toasts: List[_Toast] = [_Toast() for _ in range(_MAX_TOASTS)]
        # Per-quest pulse progress, so callers can ask "is this quest pulsing?".
        self._pulse_t: Dict[str, float] = {}
        # Reusable scratch surfaces — grown lazily, then reused.
        self._part_surf: Optional[pygame.Surface] = None
        self._part_surf_size: int = 0
        self._ring_surf: Optional[pygame.Surface] = None
        self._ring_surf_size: int = 0
        # Polish hooks the screen may set.
        self.sound_on: bool = True
        self.on_shake: Optional[object] = None   # callable(amp, dur)

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------
    def on_complete(self, x: float, y: float, medals: int, amber: int,
                    quest_id: str = "", name: str = "") -> None:
        """Fire the completion juice for one daily quest.

        ``x, y`` is the quest row's centre (screen coordinates), used as
        the burst + ring origin.  ``medals`` / ``amber`` are the rewards
        (from ``DailyQuest.reward_medals`` / ``DailyQuest.reward_amber``).
        ``quest_id`` registers a per-quest pulse the screen reads to
        animate the "✓ Claimed" checkmark.  ``name`` is shown in the toast.
        """
        # --- Particle burst (half medals, half amber) ---
        n_medal, n_amber = _split_burst(_BURST_COUNT)
        self._spawn_burst(x, y, _MEDAL_COLOR, n_medal)
        self._spawn_burst(x, y, _AMBER_COLOR, n_amber)

        # --- Expanding ring + per-quest pulse ---
        col = _AMBER_COLOR if amber > 0 else _MEDAL_COLOR
        pslot = self._next_free(self._pulses)
        pslot.quest_id = quest_id
        pslot.x = int(x); pslot.y = int(y)
        pslot.color = col
        pslot.t = 0.0
        pslot.active = True
        if quest_id:
            self._pulse_t[quest_id] = 0.0

        # --- Floating reward text ---
        parts: List[str] = []
        if medals > 0:
            parts.append(f"+{medals} medals")
        if amber > 0:
            parts.append(f"+{amber} amber")
        text = "  ".join(parts) if parts else "Quest complete!"
        fslot = self._next_free(self._floats)
        fslot.text = text
        fslot.x = int(x)
        fslot.y0 = int(y) - 6
        fslot.y = fslot.y0
        fslot.color = C.gold
        fslot.t = 0.0
        fslot.active = True
        # Render the text + shadow once, at spawn time (not per frame).
        fnt = font_md(bold=True)
        fslot.img = fnt.render(text, True, C.gold)
        fslot.shadow = fnt.render(text, True, (0, 0, 0))

        # --- Toast banner ---
        label = f"Quest complete: {name}" if name else "Quest complete!"
        self._spawn_toast(label, col)

        # --- Sound + shake ---
        self._play("gacha")
        if self.on_shake is not None:
            try:
                self.on_shake(4.0, 0.25)
            except Exception:
                pass

    def claim_all(self, x: float, y: float, medals: int, amber: int) -> None:
        """Fire the "Claim All" celebration: a big burst + a consolidated toast.

        Called by the "Claim All" button the screen adds.  ``medals`` /
        ``amber`` are the *totals* across all claimed daily quests (the
        screen sums them) so the toast reads "+N medals  +M amber".
        """
        self._spawn_burst(x, y, _MEDAL_COLOR, 18)
        self._spawn_burst(x, y, _AMBER_COLOR, 18)
        # A bright ring, too.
        pslot = self._next_free(self._pulses)
        pslot.quest_id = ""
        pslot.x = int(x); pslot.y = int(y)
        pslot.color = C.gold
        pslot.t = 0.0
        pslot.active = True
        # Toast with the totals.
        label = f"All quests claimed!  +{medals} medals  +{amber} amber"
        self._spawn_toast(label, C.gold)
        self._play("ascend")
        if self.on_shake is not None:
            try:
                self.on_shake(6.0, 0.35)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Countdown + per-quest pulse queries
    # ------------------------------------------------------------------
    def countdown(self, state) -> Tuple[int, int]:
        """Return ``(h, m)`` until the next daily refresh.

        Reads ``state.daily_refresh`` (epoch seconds, set by
        ``core.quests.maybe_refresh_dailies`` to ``now + 24h``).  Returns
        ``(24, 0)`` when no refresh is scheduled yet.
        """
        refresh = float(getattr(state, "daily_refresh", 0.0) or 0.0)
        if refresh <= 0:
            return (24, 0)
        remaining = max(0.0, refresh - time.time())
        total_min = int(remaining // 60)
        h = total_min // 60
        m = total_min % 60
        return (h, m)

    def pulse_t(self, quest_id: str) -> float:
        """Pulse progress (0..1) for ``quest_id``'s completion animation.

        Returns 0.0 when no pulse is active for the quest (either it
        never pulsed, or the pulse has finished).  The screen uses this
        to scale/fade the "✓ Claimed" checkmark on the row.
        """
        t = self._pulse_t.get(quest_id)
        if t is None:
            return 0.0
        return clamp(t / _PULSE_DUR, 0.0, 1.0)

    def pulse_active(self, quest_id: str) -> bool:
        """True while ``quest_id``'s completion pulse is still animating."""
        return quest_id in self._pulse_t

    def has_pending(self) -> bool:
        """True if any completion pulse is still animating.

        Use for the "Claim All" button's enabled/visible state, or to
        keep the screen redrawing while juice is playing.
        """
        return bool(self._pulse_t)

    def checkmark_anim(self, quest_id: str) -> Tuple[float, int]:
        """Return ``(scale, alpha)`` for the "✓ Claimed" checkmark on
        ``quest_id``'s row.

        ``scale`` is 1.0 and ``alpha`` 255 when the quest is not actively
        pulsing (already settled); while pulsing, scale eases in from 0.6
        with a slight overshoot and alpha fades in over the first 40%.
        """
        t = self._pulse_t.get(quest_id)
        if t is None:
            return (1.0, 255)
        p = clamp(t / _PULSE_DUR, 0.0, 1.0)
        scale = 0.6 + 0.4 * _ease_out_back(p)
        alpha = int(255 * clamp(p * 2.5, 0.0, 1.0))
        return (scale, alpha)

    def reset(self) -> None:
        """Clear all pulses + per-quest pulse tracking.

        Call on daily refresh so stale quest ids don't keep the
        "Claim All" button live or block the checkmark settle.
        """
        for p in self._pulses:
            p.active = False
        self._pulse_t.clear()

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for p in self._particles:
            if not p.active:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += _BURST_GRAVITY * dt
            p.life -= dt
            if p.life <= 0:
                p.active = False

        for f in self._floats:
            if not f.active:
                continue
            f.t += dt
            if f.t >= _FLOAT_DUR:
                f.active = False
            else:
                eased = ease_out_cubic(f.t / _FLOAT_DUR)
                f.y = int(f.y0 - _FLOAT_RISE * eased)

        for p in self._pulses:
            if not p.active:
                continue
            p.t += dt
            if p.t >= _PULSE_DUR:
                p.active = False
                if p.quest_id:
                    self._pulse_t.pop(p.quest_id, None)
            elif p.quest_id:
                self._pulse_t[p.quest_id] = p.t

        for t in self._toasts:
            if not t.active:
                continue
            t.t += dt
            if t.t >= t.max_life:
                t.active = False

    # ------------------------------------------------------------------
    # Draw all active effects onto ``surf``.
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        for p in self._pulses:
            if p.active:
                self._draw_ring(surf, p)
        for p in self._particles:
            if p.active:
                self._draw_particle(surf, p)
        for f in self._floats:
            if f.active:
                self._draw_float(surf, f)
        # Toasts last so they sit on top of the quest rows.
        y = _TOAST_Y
        for t in self._toasts:
            if t.active:
                self._draw_toast(surf, t, y)
                y += (t.bg.get_height() + 6) if t.bg is not None else 30

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _spawn_burst(self, x: float, y: float,
                     color: Tuple[int, int, int], count: int) -> None:
        from utils import rng
        r = rng()
        for _ in range(count):
            slot = self._next_free(self._particles)
            ang = r.uniform(0, math.tau)
            sp = r.uniform(_BURST_SPEED * 0.4, _BURST_SPEED)
            life = _BURST_LIFE * r.uniform(0.7, 1.2)
            slot.x = float(x); slot.y = float(y)
            slot.vx = math.cos(ang) * sp
            slot.vy = math.sin(ang) * sp - 40.0   # bias upward
            slot.life = life
            slot.max_life = life
            slot.color = color
            slot.size = _PART_SIZE
            slot.active = True

    def _spawn_toast(self, label: str, color: Tuple[int, int, int]) -> None:
        tslot = self._next_free(self._toasts)
        tslot.text = label
        tslot.color = color
        tslot.t = 0.0
        tslot.max_life = _TOAST_LIFE
        tslot.active = True
        tf = font_sm(bold=True)
        tslot.img = tf.render(label, True, C.text)
        # Cache a bg surface sized to the text + padding (rendered once).
        if tslot.img is not None:
            iw = tslot.img.get_width(); ih = tslot.img.get_height()
            bw, bh = iw + 24, ih + 12
            bg = pygame.Surface((bw, bh), pygame.SRCALPHA).convert_alpha()
            pygame.draw.rect(bg, (*C.panel_lo, 230), bg.get_rect(), border_radius=8)
            pygame.draw.rect(bg, (*color, 230), bg.get_rect(), 1, border_radius=8)
            tslot.bg = bg

    @staticmethod
    def _next_free(pool: list) -> object:
        for slot in pool:
            if not slot.active:
                return slot
        return pool[0]   # pool exhausted — recycle the first slot

    def _draw_particle(self, surf: pygame.Surface, p: _Particle) -> None:
        a_frac = clamp(p.life / p.max_life, 0.0, 1.0)
        alpha = int(255 * a_frac)
        if alpha <= 0:
            return
        r = max(1, p.size)
        size = r * 2 + 2
        if self._part_surf is None or self._part_surf_size < size:
            self._part_surf = pygame.Surface(
                (size, size), pygame.SRCALPHA).convert_alpha()
            self._part_surf_size = size
        s = self._part_surf
        s.fill((0, 0, 0, 0))
        pygame.draw.circle(s, (*p.color, alpha), (size // 2, size // 2), r)
        surf.blit(s, (int(p.x) - size // 2, int(p.y) - size // 2))

    def _draw_ring(self, surf: pygame.Surface, p: _Pulse) -> None:
        pt = p.t / _RING_DUR
        if pt >= 1.0:
            return
        r = int(_RING_MAX_R * ease_out_cubic(pt))
        if r <= 0:
            return
        alpha = int(220 * (1.0 - pt))
        size = r * 2 + 4
        if self._ring_surf is None or self._ring_surf_size < size:
            self._ring_surf = pygame.Surface(
                (size, size), pygame.SRCALPHA).convert_alpha()
            self._ring_surf_size = size
        s = self._ring_surf
        s.fill((0, 0, 0, 0))
        pygame.draw.circle(s, (*p.color, alpha), (size // 2, size // 2), r, 2)
        surf.blit(s, (p.x - size // 2, p.y - size // 2))

    def _draw_float(self, surf: pygame.Surface, f: _FloatText) -> None:
        p = f.t / _FLOAT_DUR
        alpha = int(255 * (1.0 - ease_out_cubic(p)))
        if alpha <= 0 or f.img is None:
            return
        f.img.set_alpha(alpha)
        rect = f.img.get_rect(midtop=(f.x, f.y))
        if f.shadow is not None:
            f.shadow.set_alpha(min(180, alpha))
            surf.blit(f.shadow, (rect.x + 1, rect.y + 1))
        surf.blit(f.img, rect)

    def _draw_toast(self, surf: pygame.Surface, t: _Toast, y: int) -> None:
        # Fade in over 0.2s, hold, fade out over the last 15%.
        if t.bg is None or t.img is None:
            return
        life_frac = t.t / t.max_life
        if t.t < 0.2:
            a = int(255 * (t.t / 0.2))
        elif life_frac > 0.85:
            a = int(255 * (1.0 - (life_frac - 0.85) / 0.15))
        else:
            a = 255
        a = max(0, min(255, a))
        t.bg.set_alpha(a)
        t.img.set_alpha(a)
        x = (surf.get_width() - t.bg.get_width()) // 2
        surf.blit(t.bg, (x, y))
        surf.blit(t.img, (x + 12, y + 6))

    def _play(self, name: str) -> None:
        if not self.sound_on:
            return
        try:
            from assets import play
            play(name, True)
        except Exception:
            pass
