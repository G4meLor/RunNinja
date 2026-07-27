"""Settings screen for Tap Ninja."""
from __future__ import annotations

import os
import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel
from ui.widgets import Button
from core.state import SAVE_FILE


class SettingsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.btn_sound = Button((cfg.WINDOW_W // 2 - 160, 220, 320, 48), "",
                                on_click=self._toggle_sound)
        self.btn_motion = Button((cfg.WINDOW_W // 2 - 160, 290, 320, 48), "",
                                 on_click=self._toggle_motion)
        self.btn_reset = Button((cfg.WINDOW_W // 2 - 160, 420, 320, 48),
                                "Reset all progress", on_click=self._reset, color=(160, 50, 60))
        self.buttons = [self.btn_back, self.btn_sound, self.btn_motion, self.btn_reset]
        self.reset_confirm = 0.0

    def _toggle_sound(self):
        self.game.state.sound_on = not self.game.state.sound_on
        self.game.state.save()

    def _toggle_motion(self):
        self.game.state.reduced_motion = not self.game.state.reduced_motion
        self.game.state.save()

    def _reset(self):
        if self.reset_confirm > 0:
            try: os.remove(SAVE_FILE)
            except OSError: pass
            from core.state import GameState
            self.game.state = GameState()
            self.game.state.gold += 200
            self.game.runner.state = self.game.state
            self.game.runner.reset_for_ascension()
            self.reset_confirm = 0.0
            self.game.set_screen("game")
        else:
            self.reset_confirm = 3.0

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        state = self.game.state
        self.btn_sound.label = f"Sound: {'ON' if state.sound_on else 'OFF'}"
        self.btn_sound.color = (60, 120, 90) if state.sound_on else (90, 60, 60)
        self.btn_motion.label = f"Reduced motion: {'ON' if state.reduced_motion else 'OFF'}"
        self.btn_motion.color = (60, 120, 90) if state.reduced_motion else (90, 60, 60)
        if self.reset_confirm > 0:
            self.reset_confirm -= dt
            if self.reset_confirm <= 0:
                self.btn_reset.label = "Reset all progress"
                self.btn_reset.color = (160, 50, 60)
            else:
                self.btn_reset.label = "Click again to confirm reset"
                self.btn_reset.color = (220, 80, 80)
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf):
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Settings", (cfg.WINDOW_W // 2, 60), font_xl(bold=True), C.text)
        draw_text_center(surf, "Tune the experience.",
                         (cfg.WINDOW_W // 2, 100), font_sm(), C.text_dim)
        r = pygame.Rect(cfg.WINDOW_W // 2 - 200, 180, 400, 280)
        draw_panel(surf, r, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Accessibility", (r.x + 20, r.y + 16), font_md(bold=True), C.text)
        draw_text(surf, "Reduced motion disables shake & heavy particles.",
                  (r.x + 20, r.y + 40), font_xs(), C.text_dim)
        for b in self.buttons:
            b.draw(surf)
        draw_text_center(surf, f"Save: {SAVE_FILE}",
                         (cfg.WINDOW_W // 2, cfg.WINDOW_H - 110), font_xs(), C.text_muted)
