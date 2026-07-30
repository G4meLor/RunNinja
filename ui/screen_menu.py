"""Main menu / title screen for Tap Ninja."""
from __future__ import annotations

import os
import math
import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl, font_huge
from theme import draw_text, draw_text_center, draw_panel
from ui.widgets import Button
from core.state import SAVE_FILE


class MenuScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_play = Button((cfg.WINDOW_W // 2 - 120, cfg.WINDOW_H // 2 + 40, 240, 56),
                                "Play", on_click=self._play, color=(60, 120, 90))
        self.btn_settings = Button((cfg.WINDOW_W // 2 - 120, cfg.WINDOW_H // 2 + 110, 240, 44),
                                    "Settings", on_click=lambda: self.game.set_screen("settings"))
        self.buttons = [self.btn_play, self.btn_settings]
        self.lane_scroll = 0.0
        self.t = 0.0
        self.has_save = os.path.exists(SAVE_FILE)
        # Daily login reward modal state. ``self._login_reward_active`` is
        # set True in ``update`` whenever ``self.game._login_reward`` is not
        # None (the streak reward was applied on load but not yet shown);
        # a MOUSEBUTTONDOWN dismisses it (handled in ``handle`` BEFORE the
        # button loop so the click dismisses the modal instead of also
        # triggering Play/Settings). The reward is amber (the streak reward
        # is amber).
        self._login_reward_active = False

    def _play(self):
        self.game.set_screen("game")

    def handle(self, event):
        # Login reward modal: a MOUSEBUTTONDOWN button 1 dismisses the
        # modal. Handled BEFORE the button loop so the click dismisses the
        # modal instead of also triggering Play/Settings. The reward has
        # already been applied in ``main.py`` (the streak reward is granted
        # on load); the modal only shows the streak + the amber reward.
        if self._login_reward_active:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._login_reward_active = False
                # Clear the game's pending reward so the modal does not
                # re-open on the next menu visit.
                self.game._login_reward = None
            return
        # Task 37 (pl-music-sfx): pass ``state.sound_on`` to each button
        # so the UI click sound is gated on the SFX toggle.
        state = self.game.state
        for b in self.buttons:
            b.sound_on = state.sound_on
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        self.t += dt
        self.lane_scroll = (self.lane_scroll + 60 * dt) % 60
        self.has_save = os.path.exists(SAVE_FILE)
        self.btn_play.label = "Continue" if self.has_save else "Begin"
        for b in self.buttons:
            b.update(dt)
        # Login reward modal: keep it active while the game has a pending
        # reward (``self.game._login_reward`` is set on load in main.py
        # when a new-day streak reward was granted). Do not clear it here
        # (the reward is cleared on dismiss in ``handle``). The attribute
        # always exists on Game (it is set to None when no reward), so
        # this is safe even when no reward is pending.
        reward = getattr(self.game, "_login_reward", None)
        if reward is not None:
            self._login_reward_active = True

    def draw(self, surf):
        from assets import background
        bg = background(0, 270)
        surf.blit(bg, (0, 0))
        ly = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2
        for x in range(-60, cfg.WINDOW_W, 60):
            xx = (x - self.lane_scroll) % (cfg.WINDOW_W + 60) - 30
            pygame.draw.rect(surf, C.lane_line, (xx, ly, 30, 4))
        dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 110))
        surf.blit(dim, (0, 0))
        bob = math.sin(self.t * 1.5) * 4
        title_y = 160 + bob
        draw_text_center(surf, "Tap Ninja", (cfg.WINDOW_W // 2, title_y),
                         font_huge(bold=True), C.text)
        draw_text_center(surf, "an idle adventure on the endless road",
                         (cfg.WINDOW_W // 2, title_y + 60), font_md(), C.text_dim)
        tip_a = int(140 + 80 * math.sin(self.t * 2))
        draw_text_center(surf, "click the road to attack  ·  0-9 + H/B/G/C to switch screens  ·  P to pause",
                         (cfg.WINDOW_W // 2, cfg.WINDOW_H - 40), font_xs(), (tip_a, tip_a, tip_a))
        for b in self.buttons:
            b.draw(surf)
        # Login reward modal (drawn last so it overlays the menu). Uses the
        # welcome-modal pattern from screen_game.py: a dim SRCALPHA overlay
        # + a centered panel + draw_text_center. The reward is amber (the
        # streak reward is amber; the HUD amber pill uses (255, 180, 60)).
        if self._login_reward_active:
            self._draw_login_reward(surf)

    def _draw_login_reward(self, surf) -> None:
        """Draw the daily login reward modal.

        A dim SRCALPHA overlay + a centered panel showing the login streak
        + the amber reward, with "click to collect" text. The reward has
        already been applied in ``main.py`` (the streak reward is granted
        on load); this modal only surfaces the streak + the reward to the
        player. Dismissed by a click in ``handle`` (which clears
        ``self.game._login_reward``).

        The reward is amber (the streak reward is amber; the HUD amber pill
        uses (255, 180, 60)). The "click to collect" text pulses (matching
        the welcome modal's pulsing collect prompt) so the player notices
        the modal is interactive.
        """
        reward = getattr(self.game, "_login_reward", None)
        # Defensive: the modal should only be drawn when active, but guard
        # against a None reward (e.g. cleared between update + draw) so we
        # never crash.
        if reward is None:
            self._login_reward_active = False
            return
        streak, amount = reward
        # Dim overlay (the modal is an overlay over the menu).
        dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        surf.blit(dim, (0, 0))
        # Centered panel (the welcome-modal pattern).
        cw, ch = 480, 240
        cx, cy = cfg.WINDOW_W // 2, cfg.WINDOW_H // 2
        r = pygame.Rect(0, 0, cw, ch)
        r.center = (cx, cy)
        draw_panel(surf, r, fill=(22, 26, 46),
                   border=C.panel_border_hi, border_w=2, radius=16)
        # Title + streak + amber reward + "click to collect".
        draw_text_center(surf, "Daily Login Reward",
                         (cx, r.y + 36), font_xl(bold=True), C.text)
        draw_text_center(surf, f"Login streak: {streak} day"
                         + ("" if streak == 1 else "s"),
                         (cx, r.y + 80), font_md(), C.text_dim)
        draw_text_center(surf, f"+{amount} Amber",
                         (cx, r.y + 120), font_lg(bold=True),
                         (255, 180, 60))
        # Pulsing "click to collect" prompt (matches the welcome modal).
        a = int(180 + 60 * math.sin(self.t * 6))
        draw_text_center(surf, "click to collect",
                         (cx, r.bottom - 24), font_sm(), (a, a, a))
