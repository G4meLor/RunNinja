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

Task 35 (gp-reincarnation-perks) additions:
  * **Reincarnation panel**: a Reincarnation button + Soul Tree panel,
    gated behind Singularity (tier 6) + 10 ascensions. Reincarnation is
    the HARD reset above ascension (resets ascend_tier + elixir +
    skill_tree); the Soul Tree perks (permanent, in ``state.soul_tree``)
    persist and modify how the new run starts. The Cosmic Forge (max 10)
    is the persistent anchor -- it survives reincarnation.
  * **Soul Tree panel**: the 4 perks (start_zone_3, extra_equip_slot,
    keep_skill_tree, fifth_active_skill), their soul cost, and whether
    they're unlocked. Clicking a perk purchases it (spends souls, adds
    to ``state.soul_tree``). The perks are permanent run-breaking verbs.
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
        # Task 35: Reincarnation button (gated behind Singularity + 10
        # ascensions). The button is enabled only when the gate is met;
        # it confirms like the Ascend button (a two-click confirm so the
        # hard reset is not a misclick).
        self.btn_reincarnate = Button(
            (cfg.WINDOW_W - 280, cfg.WINDOW_H - 100, 240, 60),
            "Reincarnate", on_click=self._do_reincarnate,
            color=(180, 120, 255))
        self.buttons.append(self.btn_reincarnate)
        self.reincarnate_pending = False
        self.reincarnate_t = 0.0
        # Task 35: Soul Tree perk buttons (cached like the forge buttons
        # in screen_hero -- the MOUSEBUTTONDOWN + MOUSEBUTTONUP pair must
        # hit the same Button object so ``on_click`` fires). Rebuilt
        # when the soul/soul_tree state changes.
        self._soul_btns: list[Button] = []
        self._soul_btn_state: tuple | None = None

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

    def _do_reincarnate(self):
        """Reincarnation confirm: a two-click confirm like Ascend.

        The first click arms the confirm (the label flips to "Confirm
        Reincarnate?" + a 3s window); the second click within the window
        performs the hard reset. The reset is gated by ``can_reincarnate``
        (Singularity + 10 ascensions); the button is disabled when the
        gate is not met, so this only fires when the player is eligible.
        """
        state = self.game.state
        if self.reincarnate_pending:
            if asc.reincarnate(state):
                self.game.runner.reset_for_ascension()
                self.game.shake(14, 0.8)
                from assets import play
                play("ascend", state.sound_on)
                self.game.state.save()
            self.reincarnate_pending = False
        else:
            self.reincarnate_pending = True
            self.reincarnate_t = 3.0

    def _do_purchase_perk(self, perk_id: str) -> None:
        """Purchase a Soul Tree perk (spends souls, adds to soul_tree)."""
        state = self.game.state
        if asc.purchase_soul_tree_perk(state, perk_id):
            from assets import play
            play("gacha", state.sound_on)
            state.save()

    def _soul_btn_snapshot(self, state) -> tuple:
        """A hashable snapshot of the state that affects the perk buttons."""
        return (tuple(sorted(state.soul_tree)), state.souls)

    def _maybe_rebuild_soul_buttons(self) -> None:
        """Rebuild the Soul Tree perk buttons when the state changes.

        The buttons are cached so the MOUSEBUTTONDOWN + MOUSEBUTTONUP
        pair hits the same Button object (same pattern as the forge
        buttons in screen_hero). Rebuilt when the soul_tree set or the
        souls balance changes.
        """
        state = self.game.state
        snap = self._soul_btn_snapshot(state)
        if snap == self._soul_btn_state:
            return
        self._soul_btn_state = snap
        self._soul_btns = []
        from data.skill_tree import SOUL_TREE_PERKS
        for i, perk in enumerate(SOUL_TREE_PERKS):
            unlocked = perk.id in state.soul_tree
            can = (not unlocked) and state.souls >= perk.cost
            # The button label shows the perk name + cost (or "Unlocked").
            if unlocked:
                label = f"{perk.name} - Unlocked"
                enabled = False
            elif can:
                label = f"{perk.name} ({perk.cost} souls)"
                enabled = True
            else:
                label = f"{perk.name} ({perk.cost} souls)"
                enabled = False
            # Layout: a single column in the Soul Tree panel area. The
            # panel is at x=890, y=130, w=380, h=530. The grid starts at
            # y=260 (below the "Soul Tree" header at y=260). Each button
            # is 348x48 (panel.w - 32 margin); the 4 perks stack
            # vertically (4 rows x 1 column) so the labels fit.
            row = i
            bx = 906
            by = 260 + row * 56
            btn = Button((bx, by, 348, 48), label,
                         on_click=lambda pid=perk.id: self._do_purchase_perk(pid),
                         enabled=enabled, color=(180, 120, 255))
            self._soul_btns.append(btn)

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        # Soul Tree perk buttons (cached; rebuilt in update/draw).
        for b in self._soul_btns:
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
        # Task 35: Reincarnation button state (gated + confirm).
        can_reinc = asc.can_reincarnate(state)
        self.btn_reincarnate.enabled = can_reinc
        if self.reincarnate_pending:
            self.reincarnate_t -= dt
            if self.reincarnate_t <= 0:
                self.reincarnate_pending = False
            self.btn_reincarnate.label = "Confirm Reincarnate?"
            self.btn_reincarnate.color = (220, 80, 80)
        else:
            self.btn_reincarnate.label = "Reincarnate"
            self.btn_reincarnate.color = (180, 120, 255)
        # Rebuild the Soul Tree perk buttons if the state changed.
        self._maybe_rebuild_soul_buttons()
        for b in self.buttons:
            b.update(dt)
        for b in self._soul_btns:
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

        # -----------------------------------------------------------------
        # Task 35 (gp-reincarnation-perks): Reincarnation + Soul Tree panel
        # -----------------------------------------------------------------
        # A Reincarnation panel + Soul Tree, gated behind Singularity (tier
        # 6) + 10 ascensions. The panel shows the Cosmic Forge count
        # (current/max 10), the Souls balance, the Reincarnation button,
        # and the 4 Soul Tree perks (with their soul cost + unlocked
        # state). The panel is always shown (so the player can see the
        # gate); the Reincarnation button is disabled when the gate is not
        # met. The perks are clickable when the player can afford them.
        # The panel is placed to the RIGHT of the ascend panels (which are
        # centered at WINDOW_W // 2 - 240 = 400, width 480 -> right edge at
        # 880). The Soul Tree panel starts at x = 890 (10px gap) and is
        # 380px wide (right edge at 1270, 10px margin from WINDOW_W=1280).
        # The layout math: panel.left (890) >= ascend.right (880) + 10, and
        # panel.right (1270) <= WINDOW_W (1280) - 10.
        soul_panel = pygame.Rect(890, 130, 380, 530)
        draw_panel(surf, soul_panel, fill=(30, 20, 50), border=(180, 120, 255),
                  border_w=2)
        draw_text(surf, "Reincarnation",
                  (soul_panel.x + 16, soul_panel.y + 10),
                  font_md(bold=True), (180, 120, 255))
        draw_text(surf,
                  "Hard reset for Souls + Soul Tree perks.",
                  (soul_panel.x + 16, soul_panel.y + 36),
                  font_xs(), C.text_dim)
        # Cosmic Forge count (the persistent anchor, max 10).
        forge_y = soul_panel.y + 64
        draw_text(surf, f"Cosmic Forge: {state.cosmic_forge}/10",
                  (soul_panel.x + 16, forge_y), font_sm(bold=True),
                  C.gold)
        forge_bar = pygame.Rect(soul_panel.x + 16, forge_y + 20, 160, 10)
        draw_bar(surf, forge_bar, state.cosmic_forge / 10.0,
                 fill=C.gold, bg=C.mp_bg, border=C.panel_border)
        # Souls balance (the reincarnation currency).
        draw_text(surf, f"Souls: {state.souls}",
                  (soul_panel.x + 200, forge_y), font_sm(bold=True),
                  C.soul)
        # Reincarnation gate status (what's missing).
        gate_y = soul_panel.y + 100
        can_reinc = asc.can_reincarnate(state)
        if can_reinc:
            draw_text(surf, "Gate: READY",
                      (soul_panel.x + 16, gate_y), font_sm(bold=True),
                      C.text_good)
        else:
            tier_name = cfg.ASCEND_TIERS[
                min(state.ascend_tier, len(cfg.ASCEND_TIERS) - 1)][0]
            need_tier = max(0, asc.SINGULARITY_TIER - state.ascend_tier)
            need_asc = max(0, asc.REINCARNATION_ASCENSION_GATE
                           - state.total_ascensions)
            draw_text(surf,
                      f"Gate: need Singularity"
                      f" (+{need_tier} tier, +{need_asc} asc)",
                      (soul_panel.x + 16, gate_y), font_xs(), C.text_warn)
        # Soul Tree perks (the 4 run-breaking verbs).
        tree_y = soul_panel.y + 130
        draw_text(surf, "Soul Tree",
                  (soul_panel.x + 16, tree_y), font_md(bold=True),
                  (180, 120, 255))
        draw_text(surf,
                  "Each perk is a run-breaking verb.",
                  (soul_panel.x + 16, tree_y + 22), font_xs(),
                  C.text_dim)
        # The perk buttons are cached on ``self._soul_btns`` (built in
        # ``_maybe_rebuild_soul_buttons``); draw them after the panel
        # chrome so they align with the rows.
        for b in self._soul_btns:
            b.draw(surf)
        # Perk descriptions (below the buttons).
        from data.skill_tree import SOUL_TREE_PERKS
        desc_y = soul_panel.y + 260
        for i, perk in enumerate(SOUL_TREE_PERKS):
            unlocked = perk.id in state.soul_tree
            color = C.text_good if unlocked else C.text_dim
            draw_text(surf, f"{perk.name}: {perk.desc}",
                      (soul_panel.x + 16, desc_y + i * 22),
                      font_xs(), color)

        for b in self.buttons:
            b.draw(surf)
