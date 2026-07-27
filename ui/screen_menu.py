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

    def _play(self):
        self.game.set_screen("game")

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        self.t += dt
        self.lane_scroll = (self.lane_scroll + 60 * dt) % 60
        self.has_save = os.path.exists(SAVE_FILE)
        self.btn_play.label = "Continue" if self.has_save else "Begin"
        for b in self.buttons:
            b.update(dt)

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
        draw_text_center(surf, "click the road to attack  ·  1-9 to switch screens  ·  P to pause",
                         (cfg.WINDOW_W // 2, cfg.WINDOW_H - 40), font_xs(), (tip_a, tip_a, tip_a))
        for b in self.buttons:
            b.draw(surf)
