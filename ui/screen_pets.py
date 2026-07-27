"""Pets screen: collection grid, equip up to 3, bond levels, pet gacha."""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill
from utils import format_number
from data import pets as pet_def
from core import gacha


class PetsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.btn_pull = Button((cfg.WINDOW_W // 2 - 200, cfg.WINDOW_H - 80, 180, 50),
                              f"Pull x1 ({gacha.PET_PULL_COST})",
                              on_click=self._pull1, color=(90, 60, 130))
        self.btn_pull10 = Button((cfg.WINDOW_W // 2 + 20, cfg.WINDOW_H - 80, 180, 50),
                                 f"Pull x10 ({gacha.PET_PULL_10_COST})",
                                 on_click=self._pull10, color=(90, 60, 130))
        self.buttons = [self.btn_back, self.btn_pull, self.btn_pull10]
        self.pet_rects: dict[str, pygame.Rect] = {}
        self.anim_result = None
        self.anim_t = 0.0

    def _pull1(self):
        state = self.game.state
        if gacha.pay(state):
            r = gacha.pull(state)
            self.anim_result = r
            self.anim_t = 0.0
            from assets import play
            play("gacha", state.sound_on)
            self.game.state.save()

    def _pull10(self):
        state = self.game.state
        if gacha.pay_10(state):
            results = gacha.multi_pull(state)
            self.anim_result = results[-1]
            self.anim_t = 0.0
            from assets import play
            play("gacha", state.sound_on)
            self.game.state.save()

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for pid, r in self.pet_rects.items():
                if r.collidepoint(event.pos):
                    self._toggle_equip(pid)
                    break

    def _toggle_equip(self, pid):
        state = self.game.state
        if pid in state.equipped_pets:
            state.unequip_pet(pid)
        else:
            state.equip_pet(pid)
        self.game.state.save()

    def update(self, dt):
        state = self.game.state
        self.btn_pull.enabled = gacha.can_afford(state)
        self.btn_pull10.enabled = gacha.can_afford_10(state)
        for b in self.buttons:
            b.update(dt)
        if self.anim_result:
            self.anim_t += dt
            if self.anim_t > 2.0:
                self.anim_result = None

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Pets", (cfg.WINDOW_W // 2, 36), font_xl(bold=True), C.text)
        draw_text_center(surf, "Equip up to 3. Click a pet to equip/unequip.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
        x = 16; y = 100
        x += currency_pill(surf, x, y, "Amber", format_number(state.amber), (255, 180, 60)) + 10
        currency_pill(surf, x, y, "Owned", f"{len(state.pets)}/{len(pet_def.PETS)}", C.text)

        # Pet grid.
        self.pet_rects = {}
        grid_x = 80; grid_y = 130
        card_w, card_h = 200, 90
        cols = 5
        for i, p in enumerate(pet_def.PETS):
            r_idx, c_idx = divmod(i, cols)
            px = grid_x + c_idx * (card_w + 12)
            py = grid_y + r_idx * (card_h + 12)
            r = pygame.Rect(px, py, card_w, card_h)
            self.pet_rects[p.id] = r
            owned = p.id in state.pets
            unlocked = pet_def.is_unlocked(p, state)
            equipped = p.id in state.equipped_pets
            if not unlocked:
                draw_panel(surf, r, fill=C.panel_lo, border=C.panel_border)
                draw_text_center(surf, "???", r.center, font_md(), C.text_muted)
                continue
            border = C.gold if equipped else C.panel_border
            fill = C.panel if owned else (20, 22, 36)
            draw_panel(surf, r, fill=fill, border=border, border_w=2 if equipped else 1)
            from assets import pet_surface
            surf.blit(pet_surface(p.id, p.hue, 48), (r.x + 10, r.y + 20))
            draw_text(surf, p.name, (r.x + 64, r.y + 12), font_sm(bold=True), C.text)
            if owned:
                bond = state.pet_bond(p.id)
                draw_text(surf, f"Bond {bond}/10", (r.x + 64, r.y + 32), font_xs(), C.text_dim)
                br = pygame.Rect(r.x + 64, r.y + 50, 120, 8)
                draw_bar(surf, br, bond / 10, fill=C.soul, bg=C.mp_bg, border=C.panel_border)
            else:
                draw_text(surf, "Not owned", (r.x + 64, r.y + 32), font_xs(), C.text_muted)
            if equipped:
                draw_text(surf, "EQUIPPED", (r.x + 10, r.y + 4), font_xs(bold=True), C.gold)

        # Pull animation.
        if self.anim_result:
            self._draw_pull_anim(surf)

        for b in self.buttons:
            b.draw(surf)

    def _draw_pull_anim(self, surf):
        r = self.anim_result
        p = pet_def.BY_ID.get(r.pet_id)
        if p is None:
            return
        scale = min(1.0, self.anim_t / 0.3)
        scale = 1 - (1 - scale) ** 3
        cw = int(360 * scale) + 40
        ch = int(300 * scale) + 40
        cx, cy = cfg.WINDOW_W // 2, cfg.WINDOW_H // 2
        rect = pygame.Rect(0, 0, cw, ch)
        rect.center = (cx, cy)
        col = C.gold if r.is_new else C.text_dim
        for i in range(4):
            gr = rect.inflate(i * 8, i * 8)
            glow = pygame.Surface(gr.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*col, 30 - i * 5), glow.get_rect(), border_radius=16)
            surf.blit(glow, gr.topleft)
        draw_panel(surf, rect, fill=(20, 22, 40), border=col, border_w=3, radius=16)
        from assets import pet_surface
        art = pet_surface(p.id, p.hue, 120)
        surf.blit(art, art.get_rect(center=(cx, rect.y + 140)))
        draw_text_center(surf, p.name, (cx, rect.y + 230), font_lg(bold=True), C.text)
        if r.is_new:
            draw_text_center(surf, "NEW!", (cx, rect.y + 262), font_md(bold=True), C.text_good)
        draw_text_center(surf, "click to continue", (cx, rect.bottom + 20), font_xs(), C.text_muted)
