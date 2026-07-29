"""Hero / Ninja loadout screen — the character sheet.

A dedicated menu for the ninja itself: large sprite, current ascension
tier + stat multiplier, all effective stats (tap damage, auto damage,
attack speed, crit chance, crit dmg, max HP, defense) with a per-source
breakdown (base + upgrades + skill tree + pets + ascension tier), the
equipped pets, and an ascension-tier ladder mini-view.  Reads ninja
stats live via ``compute_ninja_stats`` + ``aggregate_bonuses``.
"""
from __future__ import annotations

import pygame

import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill
from utils import format_number
from engine.ninja import compute_ninja_stats, _upgrade_value, _ascend_tier_mult
from core.bonuses import (aggregate_bonuses, forge_enhance, forge_reroll,
                          forge_salvage, forge_buy_legendary)
from data import skill_tree as st
from data import pets as pet_def


# Tier accent (matches the ascend screen's purple).
_TIER_COL = (150, 80, 220)

# User-friendly labels for the aggregate-bonus effect keys.
_BUFF_LABELS = {
    "firefly_gold": "Firefly Gold",
    "gold_pct": "Gold Gain",
    "crit_dmg_pct": "Crit Dmg",
    "speed_pct": "Speed",
    "firefly_value": "Firefly Value",
    "gps_pct": "Building GPS",
    "upgrade_cost_pct": "Upgrade Cost",
    "building_cost_pct": "Building Cost",
    "quest_reward_pct": "Quest Reward",
    "firefly_spawn": "Firefly Spawn",
    "energy_regen": "Energy Regen",
    "elixir_pct": "Elixir Gain",
    "godai_water": "Hero Power",
    "tap_pct": "Tap Dmg",
    "atk_pct": "Auto Dmg",
    "crit_pct": "Crit Chance",
}


class HeroScreen:
    """Character-sheet screen for the ninja."""

    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        # Forge toggle: opens the Forge panel (enhance/reroll/salvage +
        # Amber-Shop). The Forge is a one-time management action (no active
        # play required) -- the toggle is a panel switch, not a combat
        # action.
        self.btn_forge = Button((cfg.WINDOW_W - 180, cfg.WINDOW_H - 60,
                                 160, 44), "Forge",
                                on_click=self._toggle_forge,
                                color=(90, 60, 130))
        self.buttons = [self.btn_back, self.btn_forge]
        self._ninja_big: pygame.Surface | None = None  # cached scaled sprite
        # Forge panel state. The per-slot action buttons are CACHED on
        # ``self._forge_btns`` and rebuilt only when the gear/currency state
        # that affects their ``enabled`` flag changes (see
        # ``_rebuild_forge_buttons``). The cache is essential: a fresh
        # ``Button`` has ``pressed=False``, so if ``handle`` rebuilt the
        # buttons on every event, the MOUSEBUTTONDOWN that sets
        # ``pressed=True`` and the MOUSEBUTTONUP that checks ``pressed``
        # would hit different objects and the click would never fire (the
        # DOWN button is discarded before UP arrives). Caching the buttons
        # for the lifetime of a single gear/currency state keeps the
        # DOWN+UP pair on the same object so ``on_click`` fires.
        self._forge_open: bool = False
        self._forge_btns: list[Button] = []
        # Snapshot of the state used to build ``_forge_btns`` (the gear
        # dict + gold + amber). When the live state diverges from the
        # snapshot, ``_rebuild_forge_buttons`` rebuilds the buttons. The
        # snapshot is a tuple of (gear-tuple, gold, amber) -- the gear
        # dict is frozen as a tuple of (slot, affix, value, rarity) tuples
        # so it is hashable + comparable.
        self._forge_btn_state: tuple | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        # Forge panel: per-slot action buttons (enhance/reroll/salvage +
        # buy_legendary). The buttons are cached on ``self._forge_btns``
        # (rebuilt only when the gear/currency state changes) so the
        # MOUSEBUTTONDOWN + MOUSEBUTTONUP pair hits the same Button object
        # and ``on_click`` fires.
        if self._forge_open:
            for b in self._forge_btns:
                b.handle(event)

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)
        if self._forge_open:
            # Rebuild the forge buttons if the state that affects their
            # ``enabled`` flag has changed (e.g. the player spent gold and
            # can no longer afford Enhance). The rebuild is cheap (16
            # buttons) and only happens when the snapshot diverges.
            self._maybe_rebuild_forge_buttons()
            for b in self._forge_btns:
                b.update(dt)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)

        # Title.
        draw_text_center(surf, "Hero", (cfg.WINDOW_W // 2, 36),
                         font_xl(bold=True), C.text)
        draw_text_center(surf, "Ninja loadout — stats and source breakdown.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)

        # Live stats + per-source breakdown.
        stats = compute_ninja_stats(state)
        bd = self._compute_breakdown(state)

        self._draw_left_panel(surf, state, stats)
        self._draw_stat_table(surf, state, stats, bd)
        self._draw_tier_ladder(surf, state)
        self._draw_equipped_pets(surf, state)
        if self._forge_open:
            # Rebuild the forge buttons if the state has changed (so the
            # drawn buttons match the live enabled state), then draw the
            # panel chrome + the buttons.
            self._maybe_rebuild_forge_buttons()
            self._draw_forge_panel(surf, state)
            for b in self._forge_btns:
                b.draw(surf)

        for b in self.buttons:
            b.draw(surf)

    # -----------------------------------------------------------------
    # Source breakdown
    # -----------------------------------------------------------------
    def _compute_breakdown(self, state) -> dict:
        """Split aggregate_bonuses into skill-tree and pet contributions."""
        evo = aggregate_bonuses(state)
        skill_b: dict[str, float] = {}
        for n in st.NODES:
            if n.id in state.skill_tree:
                skill_b[n.effect_key] = skill_b.get(n.effect_key, 0.0) + n.effect_value
        pet_b: dict[str, float] = {}
        for pid in state.equipped_pets:
            bond = state.pet_bond(pid)
            if bond <= 0:
                continue
            p = pet_def.BY_ID.get(pid)
            if p is None:
                continue
            stars = state.pet_stars.get(pid, 0)
            prestiges = state.pet_prestiges.get(pid, 0)
            pet_b[p.buff_key] = pet_b.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond, stars, prestiges)
        tier_mult = _ascend_tier_mult(state)
        return {"tier_mult": tier_mult, "skill_b": skill_b, "pet_b": pet_b, "evo": evo}

    # -----------------------------------------------------------------
    # Left panel: large ninja sprite + tier badge + HP
    # -----------------------------------------------------------------
    def _draw_left_panel(self, surf, state, stats):
        panel = pygame.Rect(40, 100, 360, 370)
        draw_panel(surf, panel, fill=C.panel, border=C.panel_border)

        # Large ninja sprite (scaled once from the cached 64px sprite).
        ns = self._large_ninja()
        nx = panel.centerx - ns.get_width() // 2
        ny = panel.y + 24
        ninja = self.game.runner.ninja
        if not ninja.alive:
            gs = ns.copy()
            gs.fill((10, 10, 20, 120), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(gs, (nx, ny))
            draw_text_center(surf, "DOWN",
                             (panel.centerx, ny + ns.get_height() // 2),
                             font_md(bold=True), C.text_bad)
        else:
            surf.blit(ns, (nx, ny))

        # Tier badge.
        i = min(state.ascend_tier, len(cfg.ASCEND_TIERS) - 1)
        tier_name = cfg.ASCEND_TIERS[i][0]
        tier_mult = 1.6 ** state.ascend_tier
        by = ny + ns.get_height() + 20
        draw_text_center(surf, tier_name, (panel.centerx, by),
                         font_lg(bold=True), _TIER_COL)
        draw_text_center(surf, f"stat multiplier  x{tier_mult:.2f}",
                         (panel.centerx, by + 28), font_sm(), C.text_dim)
        draw_text_center(surf,
                         f"ascension #{state.ascend_tier}  -  {state.total_ascensions} total",
                         (panel.centerx, by + 50), font_xs(), C.text_muted)

        # Live HP bar.
        hp_y = by + 72
        draw_text(surf, "HP", (panel.x + 20, hp_y), font_xs(bold=True), C.text_dim)
        hp_val = f"{format_number(ninja.hp)} / {format_number(ninja.max_hp)}"
        hp_img = font_xs().render(hp_val, True, C.text)
        surf.blit(hp_img, (panel.right - 20 - hp_img.get_width(), hp_y))
        br = pygame.Rect(panel.x + 20, hp_y + 16, panel.w - 40, 10)
        draw_bar(surf, br, ninja.hp / max(1, ninja.max_hp),
                 fill=C.hp, bg=C.hp_bg, border=C.panel_border)

    def _large_ninja(self) -> pygame.Surface:
        """Cached 192px ninja sprite (scaled from the 64px cached sprite)."""
        if self._ninja_big is None:
            from assets import ninja_surface
            ns = ninja_surface(64)
            self._ninja_big = pygame.transform.scale(ns, (192, 192))
        return self._ninja_big

    # -----------------------------------------------------------------
    # Stat table (right panel)
    # -----------------------------------------------------------------
    def _draw_stat_table(self, surf, state, stats, bd):
        panel = pygame.Rect(420, 100, 820, 370)
        draw_panel(surf, panel, fill=C.panel, border=C.panel_border)

        tier_mult = bd["tier_mult"]
        skill_b = bd["skill_b"]
        pet_b = bd["pet_b"]

        rows = [
            ("tap_damage", "Tap Damage", C.text_bad),
            ("auto_damage", "Auto Damage", C.gold),
            ("attack_speed", "Attack Speed", C.exp),
            ("crit_chance", "Crit Chance", C.text_warn),
            ("crit_dmg", "Crit Damage", C.text_warn),
            ("max_hp", "Max HP", C.hp),
            ("defense", "Defense", C.shield),
        ]

        row_h = 50
        y0 = panel.y + 14
        for i, (key, label, col) in enumerate(rows):
            y = y0 + i * row_h
            # Label.
            draw_text(surf, label, (panel.x + 20, y), font_md(bold=True), C.text)
            # Value (right-aligned, colored).
            val = stats[key]
            val_str = self._format_stat(key, val)
            val_img = font_lg(bold=True).render(val_str, True, col)
            surf.blit(val_img, (panel.right - 20 - val_img.get_width(), y - 4))
            # Source breakdown.
            bk = self._breakdown_str(state, key, tier_mult, skill_b, pet_b)
            draw_text(surf, bk, (panel.x + 20, y + 24), font_xs(), C.text_dim)

    @staticmethod
    def _format_stat(key: str, val: float) -> str:
        if key == "attack_speed":
            return f"{val:.2f}/s"
        if key == "crit_chance":
            return f"{val * 100:.1f}%"
        if key == "crit_dmg":
            return f"{val:.2f}x"
        return format_number(val)

    @staticmethod
    def _breakdown_str(state, key, tier_mult, skill_b, pet_b) -> str:
        """Compact per-source breakdown matching the compute_ninja_stats formula."""
        def uv(k: str) -> float:
            return _upgrade_value(state, k)

        parts: list[str] = []

        if key == "tap_damage":
            # Task 24: base 10.0 scaled by TAP_BASE_SCALE (0.2) -> 2.0.
            parts.append(f"base {format_number(10.0 * cfg.TAP_BASE_SCALE)}")
            upf = uv("tap_power")
            if upf > 0:
                parts.append(f"upg +{format_number(upf)}")
            upm = uv("tap_mult")
            if upm > 0:
                parts.append(f"upg +{upm * 100:.0f}%")
            # tap_mastery (Task 22): +% tap damage capstone.
            upm2 = uv("tap_mastery")
            if upm2 > 0:
                parts.append(f"mastery +{upm2 * 100:.0f}%")
            sk = skill_b.get("tap_pct", 0.0)
            if sk > 0:
                parts.append(f"skill +{sk * 100:.0f}%")
            pt = pet_b.get("tap_pct", 0.0)
            if pt > 0:
                parts.append(f"pet +{pt * 100:.0f}%")
            if tier_mult != 1.0:
                parts.append(f"tier x{tier_mult:.2f}")

        elif key == "auto_damage":
            parts.append(f"base {format_number(8.0)}")
            upf = uv("auto_attack")
            if upf > 0:
                parts.append(f"upg +{format_number(upf)}")
            # auto_mult (Task 24): +% auto-attack damage (mirrors tap_mult).
            uam = uv("auto_mult")
            if uam > 0:
                parts.append(f"upg +{uam * 100:.0f}%")
            sk = skill_b.get("atk_pct", 0.0)
            if sk > 0:
                parts.append(f"skill +{sk * 100:.0f}%")
            pt = pet_b.get("atk_pct", 0.0)
            if pt > 0:
                parts.append(f"pet +{pt * 100:.0f}%")
            if tier_mult != 1.0:
                parts.append(f"tier x{tier_mult:.2f}")

        elif key == "attack_speed":
            parts.append("base 1.00/s")
            sp = skill_b.get("speed_pct", 0.0)
            if sp > 0:
                parts.append(f"skill +{sp * 50:.0f}%")
            pp = pet_b.get("speed_pct", 0.0)
            if pp > 0:
                parts.append(f"pet +{pp * 50:.0f}%")

        elif key == "crit_chance":
            parts.append("base 5%")
            up = uv("crit_chance")
            if up > 0:
                parts.append(f"upg +{up * 100:.0f}%")
            sk = skill_b.get("crit_pct", 0.0)
            if sk > 0:
                parts.append(f"skill +{sk * 100:.0f}%")
            pt = pet_b.get("crit_pct", 0.0)
            if pt > 0:
                parts.append(f"pet +{pt * 100:.0f}%")

        elif key == "crit_dmg":
            parts.append("base 1.50x")
            up = uv("crit_dmg")
            if up > 0:
                parts.append(f"upg +{up:.2f}")
            sk = skill_b.get("crit_dmg_pct", 0.0)
            if sk > 0:
                parts.append(f"skill +{sk * 100:.0f}%")
            pt = pet_b.get("crit_dmg_pct", 0.0)
            if pt > 0:
                parts.append(f"pet +{pt * 100:.0f}%")

        elif key == "max_hp":
            parts.append(f"base {format_number(100.0)}")
            up = uv("vitality")
            if up > 0:
                parts.append(f"upg +{format_number(up)}")
            sk = skill_b.get("godai_water", 0.0)
            if sk > 0:
                parts.append(f"skill +{sk * 100:.0f}%")
            pt = pet_b.get("godai_water", 0.0)
            if pt > 0:
                parts.append(f"pet +{pt * 100:.0f}%")
            if tier_mult != 1.0:
                parts.append(f"tier x{tier_mult:.2f}")

        elif key == "defense":
            up = uv("defense")
            if up > 0:
                parts.append(f"upg +{format_number(up)}")
            else:
                parts.append("base 0")

        return "  -  ".join(parts)

    # -----------------------------------------------------------------
    # Ascension tier ladder mini-view
    # -----------------------------------------------------------------
    def _draw_tier_ladder(self, surf, state):
        panel = pygame.Rect(40, 490, 1200, 60)
        draw_panel(surf, panel, fill=C.panel_lo, border=C.panel_border)
        draw_text(surf, "Ascension Ladder",
                  (panel.x + 14, panel.y + 4), font_xs(bold=True), C.text_dim)

        n = len(cfg.ASCEND_TIERS)
        margin = 20
        slot_w = (panel.w - 2 * margin) // n
        y0 = panel.y + 24
        cur = min(state.ascend_tier, n - 1)
        for i, tier in enumerate(cfg.ASCEND_TIERS):
            name = tier[0]
            # The live tier multiplier is 1.6 ** tier (the flat stat_mult
            # column is deprecated; the names remain as labels).
            mult = 1.6 ** i
            x = panel.x + margin + i * slot_w
            r = pygame.Rect(x + 4, y0, slot_w - 8, 28)
            is_cur = (i == cur)
            is_past = (i < cur)
            if is_cur:
                fill = (_TIER_COL[0] // 3, _TIER_COL[1] // 3, _TIER_COL[2] // 3)
                border_c = _TIER_COL
                bw = 2
            elif is_past:
                fill = (28, 24, 40)
                border_c = (80, 60, 120)
                bw = 1
            else:
                fill = C.panel_lo
                border_c = C.panel_border
                bw = 1
            pygame.draw.rect(surf, fill, r, border_radius=4)
            pygame.draw.rect(surf, border_c, r, bw, border_radius=4)
            tc = C.text if is_cur else (C.text_dim if is_past else C.text_muted)
            nm = name if len(name) <= 11 else name[:10] + "…"
            draw_text_center(surf, nm, (r.centerx, r.y + 4),
                             font_xs(bold=True), tc)
            draw_text_center(surf, f"x{mult:.2f}", (r.centerx, r.y + 18),
                             font_xs(), tc)

    # -----------------------------------------------------------------
    # Equipped pets row
    # -----------------------------------------------------------------
    def _draw_equipped_pets(self, surf, state):
        panel = pygame.Rect(40, 560, 1200, 90)
        draw_panel(surf, panel, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Equipped Pets",
                  (panel.x + 14, panel.y + 6), font_xs(bold=True), C.text_dim)

        slots = 3
        margin = 20
        card_w = (panel.w - 2 * margin - (slots - 1) * 16) // slots
        card_h = 56
        y0 = panel.y + 24
        from assets import pet_surface
        for i in range(slots):
            x = panel.x + margin + i * (card_w + 16)
            r = pygame.Rect(x, y0, card_w, card_h)
            if i < len(state.equipped_pets):
                pid = state.equipped_pets[i]
                p = pet_def.BY_ID.get(pid)
                if p is None:
                    continue
                bond = state.pet_bond(pid)
                stars = state.pet_stars.get(pid, 0)
                prestiges = state.pet_prestiges.get(pid, 0)
                bonus = pet_def.pet_bonus(p, bond, stars, prestiges)
                draw_panel(surf, r, fill=C.panel_hi, border=C.gold, border_w=1)
                ps = pet_surface(p.id, p.hue, 48)
                surf.blit(ps, (r.x + 8, r.y + 4))
                draw_text(surf, p.name, (r.x + 64, r.y + 6),
                         font_sm(bold=True), C.text)
                draw_text(surf, f"Bond {bond}/10", (r.x + 64, r.y + 24),
                         font_xs(), C.text_dim)
                bl = _BUFF_LABELS.get(p.buff_key, p.buff_key)
                if bond > 0:
                    bv = f"+{bonus * 100:.1f}%"
                    bc = C.text_good
                else:
                    bv = "no bonus"
                    bc = C.text_muted
                draw_text(surf, f"{bl} {bv}", (r.x + 64, r.y + 40),
                         font_xs(), bc)
            else:
                draw_panel(surf, r, fill=C.panel_lo, border=C.panel_border)
                draw_text_center(surf, "Empty", r.center, font_sm(), C.text_muted)

    # -----------------------------------------------------------------
    # Forge panel (cnt-gear-loot-forge, Task 33)
    # -----------------------------------------------------------------
    # A one-time management panel: enhance (gold), reroll (amber), salvage
    # (amber back), and the Amber-Shop (buy a guaranteed legendary with
    # amber). No affix requires active play -- the Forge is a pure state
    # mutation (the forge functions in ``core.bonuses`` are pure; no runner,
    # no combat). The Amber-Shop is a complementary amber sink INSIDE this
    # system (same module, same ``state.gear`` data model), not a separate
    # layer.
    #
    # Layout constants: shared between ``_rebuild_forge_buttons`` (which
    # positions the per-slot action buttons) and ``_draw_forge_panel``
    # (which draws the panel chrome + the per-slot rows). The two methods
    # read the same constants so the buttons always align with the rows.
    _FORGE_PANEL_RECT = (40, 100, 1200, 460)
    _FORGE_ROW_H = 80
    _FORGE_ROW_Y0 = 156  # panel.y (100) + 56 (below the header)

    def _toggle_forge(self):
        self._forge_open = not self._forge_open
        # Clear the cache so the next ``update``/``draw`` rebuilds the
        # buttons for the new panel state (fresh buttons have
        # ``pressed=False``, so a toggle mid-click does not leave a stale
        # ``pressed=True`` on a discarded button).
        self._forge_btns = []
        self._forge_btn_state = None

    def _forge_state_snapshot(self) -> tuple:
        """A hashable snapshot of the state that affects the forge buttons'
        ``enabled`` flags.

        The snapshot is ``(gear-tuple, gold, amber)`` where ``gear-tuple``
        is a tuple of ``(slot, affix, value, rarity)`` tuples sorted by
        slot. The snapshot is used by ``_maybe_rebuild_forge_buttons`` to
        detect when the live state has diverged from the state the cached
        buttons were built for (e.g. the player spent gold and can no
        longer afford Enhance, or a boss drop added a new piece).
        """
        state = self.game.state
        gear_tuple = tuple(
            (slot, g.get("affix"), g.get("value"), g.get("rarity"))
            for slot, g in state.gear.items()
        )
        return (gear_tuple, state.gold, state.amber)

    def _maybe_rebuild_forge_buttons(self) -> None:
        """Rebuild ``self._forge_btns`` if the gear/currency state has
        changed since the last build.

        The rebuild is cheap (16 buttons) and only happens when the
        snapshot diverges, so the per-frame cost is a tuple comparison +
        a list rebuild only when the state actually changed. The buttons
        are cached for the lifetime of a single gear/currency state so the
        MOUSEBUTTONDOWN + MOUSEBUTTONUP pair hits the same Button object
        and ``on_click`` fires (a fresh button has ``pressed=False``, so
        rebuilding on every event would break the DOWN+UP contract).
        """
        snap = self._forge_state_snapshot()
        if snap == self._forge_btn_state:
            return  # state unchanged -- keep the cached buttons
        self._forge_btn_state = snap
        self._forge_btns = self._build_forge_buttons()

    def _build_forge_buttons(self) -> list[Button]:
        """Build the per-slot action buttons for the current state.

        Four buttons per slot: Enhance (gold), Reroll (amber), Salvage
        (amber back), and Buy Legendary (amber, the Amber-Shop). The
        buttons are positioned by the shared layout constants (``_FORGE_*``)
        so they align with the rows drawn by ``_draw_forge_panel``. The
        ``enabled`` flag on each button reflects the current state (a
        piece must exist for Enhance/Reroll/Salvage; the player must be
        able to afford the gold/amber cost).
        """
        state = self.game.state
        buttons: list[Button] = []
        px, py, pw, ph = self._FORGE_PANEL_RECT
        for i, slot in enumerate(cfg.GEAR_SLOTS):
            y = self._FORGE_ROW_Y0 + i * self._FORGE_ROW_H
            g = state.gear.get(slot)
            # Enhance: gold sink, enabled if the slot has a piece + the
            # piece is not maxed + the player can afford the gold cost.
            can_enhance = (g is not None
                           and g.get("value", 0.0) < cfg.FORGE_ENHANCE_MAX_VALUE
                           and state.gold >= cfg.FORGE_ENHANCE_GOLD)
            btn_enh = Button((px + 280, y + 16, 130, 44), "Enhance",
                             on_click=lambda s=slot: self._do_enhance(s),
                             enabled=can_enhance, color=(150, 110, 60))
            # Reroll: amber sink, enabled if the slot has a piece + the
            # player can afford the amber cost.
            can_reroll = (g is not None
                          and state.amber >= cfg.FORGE_REROLL_AMBER)
            btn_reroll = Button((px + 420, y + 16, 130, 44), "Reroll",
                                on_click=lambda s=slot: self._do_reroll(s),
                                enabled=can_reroll, color=(90, 60, 130))
            # Salvage: returns amber, enabled if the slot has a piece.
            can_salvage = g is not None
            btn_salv = Button((px + 560, y + 16, 130, 44), "Salvage",
                              on_click=lambda s=slot: self._do_salvage(s),
                              enabled=can_salvage, color=(120, 60, 60))
            # Buy Legendary (Amber-Shop): amber sink, enabled if the player
            # can afford the amber cost. Replaces any existing piece in the
            # slot (one piece per slot).
            can_buy = state.amber >= cfg.FORGE_LEGENDARY_AMBER
            btn_buy = Button((px + 700, y + 16, 180, 44),
                             "Buy Legendary",
                             on_click=lambda s=slot: self._do_buy_legendary(s),
                             enabled=can_buy, color=(180, 120, 60))
            buttons.extend([btn_enh, btn_reroll, btn_salv, btn_buy])
        return buttons

    def _do_enhance(self, slot: str):
        state = self.game.state
        if forge_enhance(state, slot):
            from assets import play
            play("gacha", state.sound_on)
            state.save()

    def _do_reroll(self, slot: str):
        state = self.game.state
        if forge_reroll(state, slot):
            from assets import play
            play("gacha", state.sound_on)
            state.save()

    def _do_salvage(self, slot: str):
        state = self.game.state
        if forge_salvage(state, slot) > 0:
            from assets import play
            play("gacha", state.sound_on)
            state.save()

    def _do_buy_legendary(self, slot: str):
        state = self.game.state
        if forge_buy_legendary(state, slot):
            from assets import play
            play("ascend", state.sound_on)
            state.save()

    def _draw_forge_panel(self, surf, state):
        """Draw the Forge panel: 4 slot rows + the Amber-Shop header.

        Each row shows the slot's current piece (affix + value + rarity)
        and the 4 action buttons (Enhance / Reroll / Salvage / Buy
        Legendary). The buttons themselves are cached on
        ``self._forge_btns`` (built by ``_build_forge_buttons`` and drawn
        from ``draw``); this method draws the panel chrome + the piece
        info so the buttons align with the rows. The layout constants
        (``_FORGE_PANEL_RECT``, ``_FORGE_ROW_H``, ``_FORGE_ROW_Y0``) are
        shared with ``_build_forge_buttons`` so the two never diverge.
        """
        px, py, pw, ph = self._FORGE_PANEL_RECT
        panel = pygame.Rect(px, py, pw, ph)
        draw_panel(surf, panel, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Gear Forge",
                  (panel.x + 14, panel.y + 6), font_md(bold=True), C.gold)
        draw_text(surf,
                  "Enhance (gold)  -  Reroll (amber)  -  Salvage (amber)  "
                  "-  Amber-Shop (legendary)",
                  (panel.x + 160, panel.y + 8), font_xs(), C.text_dim)

        # Currency pills (gold + amber) so the player can see the sinks.
        cpx = panel.right - 240
        cpy = panel.y + 8
        currency_pill(surf, cpx, cpy, "Gold", format_number(state.gold),
                      C.gold)
        currency_pill(surf, cpx + 130, cpy, "Amber", str(state.amber),
                      (255, 180, 60))

        # Per-slot rows.
        for i, slot in enumerate(cfg.GEAR_SLOTS):
            y = self._FORGE_ROW_Y0 + i * self._FORGE_ROW_H
            r = pygame.Rect(panel.x + 14, y, panel.w - 28,
                            self._FORGE_ROW_H - 8)
            draw_panel(surf, r, fill=C.panel_lo, border=C.panel_border)
            # Slot label.
            draw_text(surf, slot.capitalize(),
                      (r.x + 12, r.y + 8), font_sm(bold=True), C.text)
            # Current piece (or "Empty").
            g = state.gear.get(slot)
            if g is not None:
                affix = g.get("affix", "")
                value = g.get("value", 0.0)
                rarity = g.get("rarity", "common")
                bl = _BUFF_LABELS.get(affix, affix)
                draw_text(surf, f"{bl} +{value * 100:.1f}%",
                          (r.x + 12, r.y + 30), font_xs(), C.text)
                draw_text(surf, f"{rarity}",
                          (r.x + 12, r.y + 48), font_xs(), C.text_dim)
            else:
                draw_text(surf, "Empty",
                          (r.x + 12, r.y + 30), font_xs(), C.text_muted)

        # Footer: the forge cost constants (so the player can see the
        # sinks before clicking).
        fy = panel.y + panel.h - 56
        draw_text(surf,
                  f"Enhance: {format_number(cfg.FORGE_ENHANCE_GOLD)} gold  "
                  f"-  Reroll: {cfg.FORGE_REROLL_AMBER} amber  "
                  f"-  Salvage: {cfg.FORGE_SALVAGE_AMBER_BASE}x rarity amber  "
                  f"-  Legendary: {cfg.FORGE_LEGENDARY_AMBER} amber",
                  (panel.x + 14, fy), font_xs(), C.text_dim)
        draw_text(surf,
                  "The Forge is a one-time management action -- no active "
                  "play required. The Amber-Shop is a complementary amber "
                  "sink inside this system.",
                  (panel.x + 14, fy + 18), font_xs(), C.text_muted)
