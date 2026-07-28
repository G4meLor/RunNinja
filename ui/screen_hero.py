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
from ui.widgets import Button
from utils import format_number
from engine.ninja import compute_ninja_stats, _upgrade_value, _ascend_tier_mult
from core.bonuses import aggregate_bonuses
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
        self.buttons = [self.btn_back]
        self._ninja_big: pygame.Surface | None = None  # cached scaled sprite

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def handle(self, event):
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        for b in self.buttons:
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
            pet_b[p.buff_key] = pet_b.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond)
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
            parts.append(f"base {format_number(10.0)}")
            upf = uv("tap_power")
            if upf > 0:
                parts.append(f"upg +{format_number(upf)}")
            upm = uv("tap_mult")
            if upm > 0:
                parts.append(f"upg +{upm * 100:.0f}%")
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
                bonus = pet_def.pet_bonus(p, bond)
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
