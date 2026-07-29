"""Pets screen: collection grid, equip up to 3, bond levels, pet gacha.

Gacha fairness bundle (Task 19):
  * The pull odds (with the soft-pity ramp) are shown in an odds panel.
  * A spark-shop button trades 40 pity tokens for an unlocked non-maxed
    pet. Tokens are cumulative across banners.

Task 36 (pl-hints-nav-tooltips): a TooltipManager with callable-text
(live values from state) for every pet. The tooltip shows the pet's
name, description, bond, bonus, and equip status.
"""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill
from ui.cb_symbols import rarity_symbol  # Task 38: color-blind-safe symbols
from ui.tooltip import TooltipManager
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
        # Spark shop: trade 40 pity tokens for an unlocked non-maxed pet.
        # Opens a sub-panel where the player picks a pet to claim.
        self.btn_spark = Button((cfg.WINDOW_W - 220, cfg.WINDOW_H - 80, 200, 50),
                                f"Spark Shop ({cfg.SPARK_SHOP_COST})",
                                on_click=self._toggle_spark, color=(70, 50, 110))
        self.buttons = [self.btn_back, self.btn_pull, self.btn_pull10, self.btn_spark]
        self.pet_rects: dict[str, pygame.Rect] = {}
        self.spark_rects: dict[str, pygame.Rect] = {}
        self.anim_result = None
        self.anim_t = 0.0
        self.spark_open: bool = False
        # Task 36: a TooltipManager with callable-text (live values from
        # state) for every pet.
        self.tooltips = TooltipManager()

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

    def _toggle_spark(self):
        self.spark_open = not self.spark_open

    def _spark_trade(self, pid):
        state = self.game.state
        if gacha.spark_shop_trade(state, pid):
            from assets import play
            play("gacha", state.sound_on)
            self.spark_open = False
            self.game.state.save()

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Spark shop clicks take priority when the panel is open.
            if self.spark_open:
                for pid, r in self.spark_rects.items():
                    if r.collidepoint(event.pos):
                        self._spark_trade(pid)
                        return
                # Click outside the panel closes it.
                self.spark_open = False
                return
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
        self.btn_spark.enabled = state.pity_tokens >= cfg.SPARK_SHOP_COST
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
        x += currency_pill(surf, x, y, "Tokens", str(state.pity_tokens), (200, 160, 255)) + 10
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

        # Odds panel (visible odds UI): the pull rates after the soft-pity
        # ramp, so the player can see the fairness at work.
        self._draw_odds(surf, state)

        # Spark shop panel (when open): pick an unlocked non-maxed pet.
        if self.spark_open:
            self._draw_spark_panel(surf, state)

        # Pull animation.
        if self.anim_result:
            self._draw_pull_anim(surf)

        for b in self.buttons:
            b.draw(surf)
        # Task 36: register a tooltip per pet with live values (the pet's
        # name, description, bond, bonus, and equip status — a callable-
        # text form so the tooltip reflects the current state when
        # hovered).
        self.tooltips.clear()
        for pid, r in self.pet_rects.items():
            tip = self._pet_tooltip(pid)
            self.tooltips.register(f"pet:{pid}", r, tip)
        self.tooltips.update(pygame.mouse.get_pos())
        self.tooltips.draw(surf)

    def _pet_tooltip(self, pid: str):
        """A callable tooltip for a pet (live values from state)."""
        def _text():
            state = self.game.state
            p = pet_def.BY_ID.get(pid)
            if p is None:
                return ""
            unlocked = pet_def.is_unlocked(p, state)
            if not unlocked:
                return f"{p.name}\nLocked — {p.unlock}"
            owned = pid in state.pets
            equipped = pid in state.equipped_pets
            bond = state.pet_bond(pid)
            stars = state.pet_stars.get(pid, 0)
            prestiges = state.pet_prestiges.get(pid, 0)
            bonus = pet_def.pet_bonus(p, bond, stars, prestiges)
            status = "EQUIPPED" if equipped else ("Owned" if owned else "Not owned")
            return (f"{p.name}\n{p.desc}\n"
                    f"Bond: {bond}/10  Stars: {stars}/{pet_def.PET_STAR_MAX}\n"
                    f"Bonus: +{format_number(bonus)} {p.buff_key}\n"
                    f"Prestiges: {prestiges}\n{status}")
        return _text

    def _draw_odds(self, surf, state):
        """Draw the pull-odds panel (visible odds UI).

        Shows the 5 rarity tiers with their current rates (after the
        soft-pity ramp) and the rarity color so the player can read the
        fairness at a glance. Placed in the top-right corner.
        """
        rates = gacha.pull_rates(state)
        # Panel geometry (top-right).
        pw, ph = 200, 150
        px = cfg.WINDOW_W - pw - 16
        py = 100
        r = pygame.Rect(px, py, pw, ph)
        draw_panel(surf, r, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Pull Odds", (r.x + 10, r.y + 6), font_sm(bold=True), C.text)
        # Each rarity row: color swatch + label + percent.
        # Task 38 (pl-accessibility): a color-blind-safe symbol is blitted
        # alongside the color swatch so color-blind players can tell the
        # rarities apart without relying on hue (the symbol is the
        # redundant cue; the color stays).
        y = r.y + 28
        for rar in ("common", "rare", "epic", "legendary", "mythic"):
            col = C.rarity.get(rar, C.text)
            rate = rates.get(rar, 0.0)
            # Color swatch.
            pygame.draw.rect(surf, col, (r.x + 10, y + 2, 10, 10), border_radius=2)
            # Color-blind-safe symbol overlay (a shape per rarity).
            sym = rarity_symbol(rar, 14)
            surf.blit(sym, (r.x + 8, y))
            # Label.
            draw_text(surf, rar.capitalize(), (r.x + 26, y), font_xs(), C.text_dim)
            # Percent (right-aligned).
            pct = f"{rate * 100:.1f}%"
            img = font_xs(bold=True).render(pct, True, C.text)
            surf.blit(img, (r.right - img.get_width() - 10, y))
            y += 22

    def _draw_spark_panel(self, surf, state):
        """Draw the spark-shop panel: pick an unlocked non-maxed pet.

        A modal-ish overlay listing every unlocked non-maxed pet. Click
        one to trade 40 pity tokens for it. Maxed pets (bond 10 + star
        12) are hidden — they can't be traded for.
        """
        # Dim backdrop.
        veil = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        veil.fill((4, 6, 18, 170))
        surf.blit(veil, (0, 0))
        # Panel geometry (centered).
        pw, ph = 760, 460
        px = (cfg.WINDOW_W - pw) // 2
        py = (cfg.WINDOW_H - ph) // 2
        r = pygame.Rect(px, py, pw, ph)
        draw_panel(surf, r, fill=C.panel, border=C.panel_border_hi, border_w=2)
        draw_text_center(surf, "Spark Shop", (r.centerx, r.y + 24),
                         font_xl(bold=True), C.text)
        draw_text_center(surf,
                         f"Trade {cfg.SPARK_SHOP_COST} pity tokens for any unlocked pet.",
                         (r.centerx, r.y + 56), font_sm(), C.text_dim)
        draw_text_center(surf, f"You have {state.pity_tokens} tokens.",
                         (r.centerx, r.y + 76), font_sm(bold=True), C.gold)
        # Grid of unlocked non-maxed pets.
        self.spark_rects = {}
        grid_x = r.x + 24; grid_y = r.y + 100
        card_w, card_h = 200, 80
        cols = 5
        from assets import pet_surface
        for i, p in enumerate(pet_def.PETS):
            if not pet_def.is_unlocked(p, state):
                continue
            # Maxed pets (bond 10 + star 12) are removed from the shop.
            if p.id in state.pets and gacha._is_maxed(state, p.id):
                continue
            r_idx, c_idx = divmod(i, cols)
            cx = grid_x + c_idx * (card_w + 12)
            cy = grid_y + r_idx * (card_h + 12)
            cr = pygame.Rect(cx, cy, card_w, card_h)
            self.spark_rects[p.id] = cr
            owned = p.id in state.pets
            fill = C.panel if owned else (24, 26, 46)
            border = C.gold if owned else C.panel_border
            draw_panel(surf, cr, fill=fill, border=border, border_w=1)
            surf.blit(pet_surface(p.id, p.hue, 40), (cr.x + 8, cr.y + 20))
            draw_text(surf, p.name, (cr.x + 56, cr.y + 12),
                      font_sm(bold=True), C.text)
            if owned:
                draw_text(surf, "+1 star", (cr.x + 56, cr.y + 32),
                          font_xs(), C.text_dim)
            else:
                draw_text(surf, "NEW", (cr.x + 56, cr.y + 32),
                          font_xs(bold=True), C.text_good)
            # Cost tag (right-aligned).
            cost_img = font_xs(bold=True).render(f"{cfg.SPARK_SHOP_COST}T",
                                                 True, C.gold)
            surf.blit(cost_img, (cr.right - cost_img.get_width() - 8,
                                cr.y + 8))
        draw_text_center(surf, "Click a pet to claim. Click outside to close.",
                         (r.centerx, r.bottom - 24), font_xs(), C.text_muted)

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
