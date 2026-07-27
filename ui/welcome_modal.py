"""Polished offline-progress "welcome back" modal for Tap Ninja.

A celebratory card that dims the backdrop, scales in with an ease-out,
and animates the gold + enemies-slain counters from 0 up to the earned
amount over ~1.5s.  A tap (or Enter/Space) collects; ``handle`` returns
True so the screen can apply the rewards and fire a particle burst.

Drawn entirely with pygame primitives + the cached theme fonts.
"""
from __future__ import annotations

import math

import pygame

import config as cfg
from theme import (
    C, font_sm, font_md, font_lg, font_xl, draw_text_center,
)
from utils import format_number, clamp, ease_out_cubic, lighten
from core import offline


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
_SCALE_DUR = 0.35      # card scale-in
_DIM_DUR = 0.25        # backdrop fade
_COUNT_START = 0.15    # count-up begins shortly after the card appears
_COUNT_DUR = 1.5       # count-up length (eased)
_COLLECT_FADE = 0.40   # post-collect fade-out

_CARD_W, _CARD_H = 560, 280


def _ease_out_back(t: float, s: float = 1.70158) -> float:
    """Overshooting ease-out — a subtle bounce on the scale-in."""
    t = clamp(t, 0.0, 1.0)
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


class WelcomeModal:
    """Self-contained welcome-back overlay.

    Lifecycle::

        modal = WelcomeModal()
        modal.set(report)            # report = offline.compute(state)
        while modal.active:
            modal.update(dt)
            modal.draw(surf)
            if modal.handle(event):  # click to collect
                offline.apply(state, report)
                particles.burst(...)        # caller's celebration
    """

    def __init__(self) -> None:
        self._report: dict | None = None
        self._active: bool = False
        self._t: float = 0.0
        self._collected: bool = False
        self._collect_t: float = 0.0

    # -- state -----------------------------------------------------------
    def set(self, report: dict | None) -> None:
        """Install a new offline report and (re)start the intro animation.

        Passing ``None`` or a non-applied report deactivates the modal.
        """
        self._report = report
        self._active = bool(report and report.get("applied"))
        self._t = 0.0
        self._collected = False
        self._collect_t = 0.0

    @property
    def active(self) -> bool:
        return self._active

    # -- animation curves ------------------------------------------------
    def _scale(self) -> float:
        return _ease_out_back(self._t / _SCALE_DUR)

    def _dim(self) -> float:
        return ease_out_cubic(min(1.0, self._t / _DIM_DUR))

    def _count(self) -> float:
        return ease_out_cubic(
            clamp((self._t - _COUNT_START) / _COUNT_DUR, 0.0, 1.0)
        )

    # -- frame -----------------------------------------------------------
    def update(self, dt: float) -> None:
        if not self._active:
            return
        self._t += dt
        if self._collected:
            self._collect_t += dt
            if self._collect_t >= _COLLECT_FADE:
                self._active = False

    def handle(self, event: pygame.event.Event) -> bool:
        """Consume a collect click/keypress; returns True on the collect."""
        if not self._active or self._collected:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._collected = True
            return True
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_RETURN, pygame.K_SPACE,
        ):
            self._collected = True
            return True
        return False

    def draw(self, surf: pygame.Surface) -> None:
        if not self._active or self._report is None:
            return
        cx, cy = cfg.WINDOW_W // 2, cfg.WINDOW_H // 2

        # -- Dim backdrop ------------------------------------------------
        dim_alpha = int(170 * self._dim())
        if self._collected:
            dim_alpha = int(dim_alpha * max(0.0, 1.0 - self._collect_t / _COLLECT_FADE))
        if dim_alpha > 0:
            dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, dim_alpha))
            surf.blit(dim, (0, 0))

        # -- Card (built full-size, then scaled for the ease-in) ---------
        scale = self._scale()
        if self._collected:
            scale *= max(0.0, 1.0 - self._collect_t / _COLLECT_FADE)
        scale = max(0.02, scale)

        card = pygame.Surface((_CARD_W, _CARD_H), pygame.SRCALPHA)
        self._draw_card(card, self._count())
        sw = max(1, int(_CARD_W * scale))
        sh = max(1, int(_CARD_H * scale))
        card = pygame.transform.smoothscale(card, (sw, sh))
        surf.blit(card, card.get_rect(center=(cx, cy)))

    # -- card contents ---------------------------------------------------
    def _draw_card(self, card: pygame.Surface, count_t: float) -> None:
        r = card.get_rect()
        cx = r.centerx
        report = self._report

        # Soft celebratory glow behind the panel.
        glow = pygame.Surface(r.size, pygame.SRCALPHA)
        for i in range(4):
            gr = r.inflate(-20 - i * 28, -20 - i * 28)
            if gr.w > 0 and gr.h > 0:
                pygame.draw.rect(glow, (255, 205, 90, 16), gr, border_radius=26)
        card.blit(glow, (0, 0))

        # Panel + border.
        pygame.draw.rect(card, C.panel, r, border_radius=16)
        pygame.draw.rect(card, C.panel_border_hi, r, 2, border_radius=16)

        # Top sheen.
        sheen = pygame.Surface((r.w, 44), pygame.SRCALPHA)
        for y in range(44):
            a = int(38 * (1 - y / 44))
            pygame.draw.line(sheen, (255, 255, 255, a), (0, y), (r.w, y))
        card.blit(sheen, (0, 0))

        # Title + subtitle.
        draw_text_center(card, "Welcome back", (cx, 44), font_xl(bold=True), C.text)
        dur = offline.format_duration(int(report.get("seconds", 0)))
        draw_text_center(card, f"Away for {dur}", (cx, 82), font_md(), C.text_dim)

        # Divider.
        pygame.draw.line(card, C.panel_border, (r.x + 40, 108), (r.right - 40, 108), 1)

        # Counters — count up from 0 to the earned amount.
        gold_now = int(count_t * report.get("gold", 0))
        kills_now = int(count_t * report.get("kills", 0))
        self._draw_counter(card, cx, 132, C.gold, C.coin, "coin",
                           f"+{format_number(gold_now)}", "gold")
        self._draw_counter(card, cx, 192, C.soul, C.soul, "soul",
                           f"+{kills_now}", "enemies slain")

        # "tap to collect" prompt — only once the count has nearly landed.
        if self._collected:
            draw_text_center(card, "collected!", (cx, r.bottom - 28),
                             font_sm(bold=True), C.text_good)
        elif count_t > 0.7:
            pulse = 0.55 + 0.45 * math.sin(self._t * 6.0)
            col = (int(C.text[0] * pulse), int(C.text[1] * pulse), int(C.text[2] * pulse))
            draw_text_center(card, "tap to collect", (cx, r.bottom - 28),
                             font_sm(bold=True), col)

    def _draw_counter(self, card: pygame.Surface, cx: int, cy: int,
                      color, icon_color, icon: str, value: str, label: str) -> None:
        """A centered [icon] + value + label block."""
        val_img = font_lg(bold=True).render(value, True, color)
        lbl_img = font_sm().render(label, True, C.text_dim)
        icon_r = 12
        gap = 14
        total_w = icon_r * 2 + gap + val_img.get_width()
        start_x = cx - total_w // 2
        ix = start_x + icon_r

        if icon == "coin":
            pygame.draw.circle(card, icon_color, (ix, cy), icon_r)
            pygame.draw.circle(card, lighten(icon_color, 1.15), (ix, cy), icon_r - 5)
            pygame.draw.circle(card, C.panel_border, (ix, cy), icon_r, 1)
        else:  # soul diamond
            pts = [(ix, cy - icon_r), (ix + icon_r, cy), (ix, cy + icon_r), (ix - icon_r, cy)]
            pygame.draw.polygon(card, icon_color, pts)
            inner = icon_r - 5
            pygame.draw.polygon(
                card, lighten(icon_color, 1.15),
                [(ix, cy - inner), (ix + inner, cy), (ix, cy + inner), (ix - inner, cy)],
            )

        vx = start_x + icon_r * 2 + gap
        card.blit(val_img, (vx, cy - val_img.get_height() // 2))
        card.blit(
            lbl_img,
            lbl_img.get_rect(midtop=(vx + val_img.get_width() // 2, cy + 18)),
        )
