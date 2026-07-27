"""Polished energy / Auto Katana widget for the game screen.

Replaces the flat ``btn_energy`` + 6px bar in ``ui/screen_game.py`` with a
self-contained widget: a status label with remaining time, a gradient-
filled energy bar, a "ready" pulse when full, a "depleting" warning glow
when low, a lockout indicator, and a toggle button whose label cycles
through ``Engage`` / ``Active`` / ``Recharging``.

All rendering uses pygame primitives + the cached theme fonts.  The hot
path performs no per-frame allocations: the glow overlay is drawn into a
single reused SRCALPHA scratch surface (allocated once when the bar size
is known, then reused), the gradient fill is drawn line-by-line with
``pygame.draw.line`` (no surface allocation), and the static title
surface is rendered once at construction.  The only per-frame
``font.render`` is the dynamic remaining-time label, which changes every
frame (this matches the codebase convention — see ``draw_text_center``).

State is read from ``game.state`` (``energy`` / ``energy_max`` /
``energy_active`` / ``energy_lockout``) and toggles through
``game.runner.toggle_energy()``; the widget writes no state itself.
"""
from __future__ import annotations

import math
import pygame

from theme import C, font_sm, gradient_v
from ui.widgets import Button
from utils import clamp


# ---------------------------------------------------------------------------
# Layout (relative to the widget rect)
# ---------------------------------------------------------------------------
_LABEL_H = 16      # status + remaining-time row
_BAR_H = 10        # gradient energy bar
_GAP = 4           # spacing between rows

# Thresholds
_LOW_PCT = 0.20          # below this fraction of max -> "depleting" warn
_READY_PCT = 0.999       # at/above this -> "ready" pulse
_PULSE_PERIOD = 1.6      # seconds per ready-pulse cycle
_WARN_PERIOD = 0.8       # seconds per warn-glow cycle
_GLOW_PAD = 4            # padding around the bar for the glow scratch

# Gradient ends
_FILL_TOP = (170, 220, 255)          # bright end (idle / charging)
_FILL_BOT = (90, 160, 220)          # dark end (idle / charging)
_FILL_TOP_ACTIVE = (255, 230, 150)  # bright end (auto-katana running)
_FILL_BOT_ACTIVE = (220, 170, 80)   # dark end (auto-katana running)
_WARN_COLOR = (255, 110, 120)       # depleting warn glow
_LOCK_COLOR = (255, 180, 90)        # lockout stripe tint
_ACTIVE_BTN = (50, 78, 66)          # toggle-button tint while running


def _format_time(seconds: float) -> str:
    """Compact ``Nh Nm`` / ``Nm SSs`` / ``s.s`` formatting for the timer."""
    s = max(0.0, float(seconds))
    if s >= 60:
        m, ss = divmod(int(s), 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}h {m}m"
        return f"{m}m {ss:02d}s"
    return f"{s:.1f}s"


class EnergyWidget:
    """A self-contained energy / Auto Katana widget.

    Lifecycle::

        w = EnergyWidget(rect, game)
        w.handle(event)    # click the toggle button
        w.update(dt)       # advance pulse/warn clocks + refresh label
        w.draw(surf)       # label + gradient bar + glow + button
    """

    def __init__(self, rect, game) -> None:
        self.rect = pygame.Rect(rect)
        self.game = game

        x, y, w = self.rect.x, self.rect.y, self.rect.w
        self._label_rect = pygame.Rect(x, y, w, _LABEL_H)
        self._bar_rect = pygame.Rect(x, y + _LABEL_H + _GAP, w, _BAR_H)
        btn_y = self._bar_rect.bottom + _GAP
        btn_h = max(0, self.rect.bottom - btn_y)
        self._button_rect = pygame.Rect(x, btn_y, w, btn_h)

        # Toggle button (reuses the standard Button widget for hover/press).
        self.button = Button(self._button_rect, "Engage",
                             on_click=self._toggle)

        # Animation clocks.
        self._pulse_t = 0.0
        self._warn_t = 0.0

        # Cached static title surface (rendered once at construction).
        self._title_font = font_sm(bold=True)
        self._title_img = self._title_font.render("Auto Katana", True, C.text)
        self._status_font = font_sm()

        # Reused SRCALPHA scratch surface for translucent glows; allocated
        # lazily once the bar size is known, then reused -- never
        # re-allocated per frame.
        self._glow_surf: pygame.Surface | None = None
        self._glow_size: tuple[int, int] = (0, 0)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        """Route mouse events to the toggle button (click to toggle)."""
        self.button.handle(event)

    def _toggle(self) -> None:
        self.game.runner.toggle_energy()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance the pulse/warn clocks and refresh the button label.

        ``dt`` is seconds.  The animation clocks are gated by the
        reduced-motion setting (they hold still when motion is reduced,
        so the glow is shown statically without oscillation).
        """
        state = self.game.state
        if not state.reduced_motion:
            self._pulse_t = (self._pulse_t + dt) % _PULSE_PERIOD
            self._warn_t = (self._warn_t + dt) % _WARN_PERIOD
        active = state.energy_active
        self.button.label = self._button_label(state)
        # Disabling the button during lockout signals "you can't toggle
        # yet"; ``toggle_energy`` itself also guards, so this is cosmetic.
        self.button.enabled = state.energy_lockout <= 0
        self.button.color = _ACTIVE_BTN if active else C.btn
        self.button.update(dt)

    @staticmethod
    def _button_label(state) -> str:
        if state.energy_active:
            return "Active"
        if state.energy_lockout > 0:
            return "Recharging"
        return "Engage"

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        """Render the label, the gradient bar with glow, and the button."""
        state = self.game.state
        emax = state.energy_max
        pct = clamp(state.energy / emax, 0.0, 1.0) if emax > 0 else 0.0
        active = state.energy_active
        lockout = state.energy_lockout

        self._draw_label(surf, state, pct, active, lockout)
        self._draw_bar(surf, pct, active, lockout)
        self.button.draw(surf)

    def _draw_label(self, surf, state, pct, active, lockout) -> None:
        r = self._label_rect
        # Title (cached) on the left.
        surf.blit(self._title_img, (r.x, r.y + 1))
        # Status + remaining time on the right.
        text, color = self._status_text(state, pct, active, lockout)
        img = self._status_font.render(text, True, color)
        surf.blit(img, (r.right - img.get_width(), r.y + 1))

    @staticmethod
    def _status_text(state, pct, active, lockout):
        if active:
            return _format_time(state.energy), C.text_good
        if lockout > 0:
            return _format_time(lockout), C.text_warn
        if pct >= _READY_PCT:
            return "READY", C.text_good
        return _format_time(state.energy), C.text_dim

    def _draw_bar(self, surf, pct, active, lockout) -> None:
        r = self._bar_rect
        # Background trough.
        pygame.draw.rect(surf, C.mp_bg, r, border_radius=3)
        # Gradient fill (current energy).  Active state uses a warm gold
        # gradient; idle/charging uses the cool blue mp gradient.
        if pct > 0:
            fill_w = max(2, int(r.w * pct))
            fill_rect = pygame.Rect(r.x, r.y, fill_w, r.h)
            if active:
                top, bot = _FILL_TOP_ACTIVE, _FILL_BOT_ACTIVE
            else:
                top, bot = _FILL_TOP, _FILL_BOT
            clip = surf.get_clip()
            surf.set_clip(r)
            gradient_v(surf, fill_rect, top, bot)
            surf.set_clip(clip)
        # Glow / lockout overlays (mutually exclusive by state).
        if lockout > 0:
            self._draw_lockout(surf)
        elif active and pct < _LOW_PCT:
            self._draw_warn_glow(surf)
        elif not active and pct >= _READY_PCT:
            self._draw_ready_pulse(surf)
        # Crisp border on top.
        pygame.draw.rect(surf, C.panel_border, r, 1, border_radius=3)

    # ------------------------------------------------------------------
    # Glow overlays -- all drawn into one reused SRCALPHA scratch surface
    # ------------------------------------------------------------------
    def _glow(self) -> pygame.Surface:
        r = self._bar_rect
        size = (r.w + _GLOW_PAD * 2, r.h + _GLOW_PAD * 2)
        if self._glow_surf is None or self._glow_size != size:
            self._glow_surf = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
            self._glow_size = size
        return self._glow_surf

    def _draw_ready_pulse(self, surf) -> None:
        """Soft green pulse around the bar when energy is full and idle."""
        r = self._bar_rect
        pad = _GLOW_PAD
        g = self._glow()
        g.fill((0, 0, 0, 0))
        pulse = 0.5 + 0.5 * math.sin(self._pulse_t * 2 * math.pi / _PULSE_PERIOD)
        alpha = int(70 + 110 * pulse)
        inner = pygame.Rect(pad, pad, r.w, r.h)
        # Three nested glowing outlines; innermost brightest.
        for i in range(3):
            layer = inner.inflate((i + 1) * 2, (i + 1) * 2)
            a = max(0, alpha - i * 28)
            pygame.draw.rect(g, (*C.text_good, a), layer, 1, border_radius=4)
        surf.blit(g, (r.x - pad, r.y - pad))

    def _draw_warn_glow(self, surf) -> None:
        """Fast red pulse around the bar while auto-katana is depleting."""
        r = self._bar_rect
        pad = _GLOW_PAD
        g = self._glow()
        g.fill((0, 0, 0, 0))
        pulse = 0.5 + 0.5 * math.sin(self._warn_t * 2 * math.pi / _WARN_PERIOD)
        alpha = int(90 + 120 * pulse)
        inner = pygame.Rect(pad, pad, r.w, r.h)
        for i in range(2):
            layer = inner.inflate((i + 1) * 2, (i + 1) * 2)
            a = max(0, alpha - i * 40)
            pygame.draw.rect(g, (*_WARN_COLOR, a), layer, 1, border_radius=4)
        surf.blit(g, (r.x - pad, r.y - pad))

    def _draw_lockout(self, surf) -> None:
        """Dim the bar and overlay diagonal stripes while locked out."""
        r = self._bar_rect
        pad = _GLOW_PAD
        g = self._glow()
        g.fill((0, 0, 0, 0))
        inner = pygame.Rect(pad, pad, r.w, r.h)
        # Dim the bar (the gradient fill shows through, dimmed).
        pygame.draw.rect(g, (18, 20, 34, 130), inner, border_radius=3)
        # Diagonal stripes, clipped to the bar area.
        g.set_clip(inner)
        stripe = (*_LOCK_COLOR, 70)
        for i in range(-r.h, r.w + r.h, 6):
            pygame.draw.line(g, stripe, (i, pad), (i + r.h, pad + r.h), 2)
        g.set_clip(None)
        surf.blit(g, (r.x - pad, r.y - pad))
