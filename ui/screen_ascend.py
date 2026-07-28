"""Ascension screen: prestige ladder + confirm.

Task 27 / pl-juice-polish additions:
  * **Elixir-per-Minute readout**: a pacing readout computed from the
    ``config.py`` curves (the ``elixir_gain`` formula + the current
    ``lifetime_gold`` + ``ascend_tier``). The readout tells the player
    how fast they're earning elixir (a pacing cue, not a hard number).
  * **Recommended-ascend highlight**: the "If you ascend now" panel is
    highlighted (a golden border) when ``recommended_ascend`` is True --
    the elixir-per-ascension is high enough to be worth ascending now.
  * **Tome of Samsara section**: a panel that promotes the elixir-tree's
    top-tier node (``elixir_t6`` "Ouroboros") as the compounding
    elixir-growth anchor, with an "invest ~30%" tooltip + an
    "elixir per ascension" projection. The Tome is the SINGLE compounding
    elixir-growth loop (the unspent-elixir-as-multiplier is NOT
    implemented).
"""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill
from utils import format_number
from core import ascend as asc


class AscendScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_ascend = Button((cfg.WINDOW_W // 2 - 120, cfg.WINDOW_H - 100, 240, 60),
                                  "Ascend", on_click=self._do_ascend, color=(150, 80, 220))
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_ascend, self.btn_back]
        self.confirm_pending = False
        self.confirm_t = 0.0

    def _do_ascend(self):
        state = self.game.state
        if self.confirm_pending:
            gained = asc.ascend(state)
            if gained > 0:
                self.game.runner.reset_for_ascension()
                self.game.shake(10, 0.6)
                from assets import play
                play("ascend", state.sound_on)
                self.game.state.save()
            self.confirm_pending = False
        else:
            self.confirm_pending = True
            self.confirm_t = 3.0

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        state = self.game.state
        self.btn_ascend.enabled = asc.can_ascend(state)
        if self.confirm_pending:
            self.confirm_t -= dt
            if self.confirm_t <= 0:
                self.confirm_pending = False
            self.btn_ascend.label = "Confirm Ascend?"
            self.btn_ascend.color = (220, 80, 80)
        else:
            self.btn_ascend.label = "Ascend"
            self.btn_ascend.color = (150, 80, 220)
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Ascension", (cfg.WINDOW_W // 2, 36), font_xl(bold=True), (150, 80, 220))
        draw_text_center(surf, "Reset for Elixir and permanent power.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
        x = 16; y = 100
        x += currency_pill(surf, x, y, "Elixir", format_number(state.elixir), (120, 220, 200)) + 10
        currency_pill(surf, x, y, "Tier", str(state.ascend_tier), (150, 80, 220))

        # Current run stats + tier.
        r = pygame.Rect(cfg.WINDOW_W // 2 - 240, 130, 480, 120)
        draw_panel(surf, r, fill=(40, 24, 60), border=(150, 80, 220), border_w=2)
        draw_text_center(surf, "Current Run", (r.centerx, r.y + 14), font_xs(), C.text_dim)
        tier_name = cfg.ASCEND_TIERS[min(state.ascend_tier, len(cfg.ASCEND_TIERS) - 1)][0]
        tier_mult = 1.6 ** state.ascend_tier
        draw_text(surf, f"Tier: {tier_name} (x{tier_mult:.2f} stats)", (r.x + 20, r.y + 36), font_md(bold=True), (150, 80, 220))
        draw_text(surf, f"Lifetime gold: {format_number(state.lifetime_gold)}", (r.x + 20, r.y + 60), font_md(), C.text)
        draw_text(surf, f"Zone: {state.zone_index + 1}  ·  Combo: {state.combo}", (r.x + 20, r.y + 82), font_sm(), C.text_dim)
        draw_text(surf, f"Ascensions: {state.total_ascensions}", (r.x + 20, r.y + 100), font_sm(), C.text_dim)

        # Elixir-per-Minute readout (Task 27 / pl-juice-polish): a pacing
        # readout computed from the config.py curves. The readout tells the
        # player how fast they're earning elixir (a pacing cue, not a hard
        # number). Computed by ``asc.elixir_per_minute(state)``.
        epm = asc.elixir_per_minute(state)
        epm_rect = pygame.Rect(cfg.WINDOW_W // 2 - 240, 250, 480, 36)
        draw_panel(surf, epm_rect, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Elixir / min:", (epm_rect.x + 16, epm_rect.y + 8),
                  font_sm(), C.text_dim)
        draw_text(surf, format_number(epm), (epm_rect.x + 130, epm_rect.y + 8),
                  font_md(bold=True), (120, 220, 200))

        # Elixir preview (with recommended-ascend highlight).
        gain = asc.elixir_gain(state)
        recommended = asc.recommended_ascend(state)
        pr = pygame.Rect(cfg.WINDOW_W // 2 - 240, 296, 480, 80)
        # Task 27: highlight the panel (a golden border) when the ascend
        # is recommended (the elixir-per-ascension is high enough + the
        # player can ascend). The highlight is a soft cue, not a hard
        # gate -- the player can always ascend when ``can_ascend`` is True.
        border_color = C.gold if recommended else C.panel_border_hi
        draw_panel(surf, pr, fill=C.panel, border=border_color,
                   border_w=2 if recommended else 1)
        draw_text_center(surf, "If you ascend now:", (pr.centerx, pr.y + 14), font_xs(), C.text_dim)
        gain_color = C.gold if recommended else (120, 220, 200)
        draw_text_center(surf, f"+{gain} Elixir", (pr.centerx, pr.y + 40),
                         font_xl(bold=True), gain_color)
        if recommended:
            draw_text_center(surf, "Recommended!", (pr.centerx, pr.y + 64),
                             font_xs(bold=True), C.gold)

        # Tome of Samsara (Task 27): the compounding elixir-growth anchor.
        # A panel that promotes the elixir-tree's top-tier node
        # (``elixir_t6`` "Ouroboros") as the compounding anchor, with an
        # "invest ~30%" tooltip + an "elixir per ascension" projection.
        # The Tome is the SINGLE compounding elixir-growth loop (the
        # unspent-elixir-as-multiplier is NOT implemented).
        tome_tip = asc.tome_of_samsara_tooltip(state)
        tome_rect = pygame.Rect(cfg.WINDOW_W // 2 - 240, 386, 480, 70)
        tome_border = (120, 220, 200) if asc.TOME_OF_SAMSARA_NODE in state.skill_tree else C.panel_border
        draw_panel(surf, tome_rect, fill=C.panel, border=tome_border, border_w=2)
        draw_text(surf, "Tome of Samsara", (tome_rect.x + 16, tome_rect.y + 8),
                  font_md(bold=True), (120, 220, 200))
        # The tooltip's first line is the title (already drawn); the rest
        # is the body (the "invest ~30%" guidance + the projection).
        tip_lines = tome_tip.split("\n")
        if len(tip_lines) > 1:
            draw_text(surf, tip_lines[1], (tome_rect.x + 16, tome_rect.y + 32),
                      font_xs(), C.text_dim)
        if len(tip_lines) > 2:
            draw_text(surf, tip_lines[2], (tome_rect.x + 16, tome_rect.y + 50),
                      font_xs(), C.text_dim)

        # Requirement.
        req = asc.ascend_requirement(state)
        rr = pygame.Rect(cfg.WINDOW_W // 2 - 240, 470, 480, 60)
        draw_panel(surf, rr, fill=C.panel, border=C.panel_border)
        draw_text(surf, f"Required: zone {req} (you are at zone {state.zone_index + 1})",
                  (rr.x + 16, rr.y + 12), font_md(), C.text)
        bar = pygame.Rect(rr.x + 16, rr.y + 38, rr.w - 32, 12)
        draw_bar(surf, bar, asc.ascend_progress(state),
                 fill=(150, 80, 220), bg=C.mp_bg, border=C.panel_border)

        for b in self.buttons:
            b.draw(surf)
