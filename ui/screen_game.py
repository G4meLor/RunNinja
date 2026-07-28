"""Main gameplay screen: the road, ninja, enemies, fireflies, HUD, combo,
energy, and active-skill buttons.
"""
from __future__ import annotations

import math
import pygame

import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_bar, draw_panel
from ui.widgets import Button, currency_pill
from utils import format_number


class GameScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.lane_scroll = 0.0
        self.toasts: list = []
        self._bg_key = None
        self.welcome_pending = None
        self.welcome_t = 0.0
        self._init_welcome()
        # Active-skill buttons (built when skills are unlocked).
        self.skill_buttons: list[Button] = []
        self._build_skill_buttons()
        # Combo Finisher buttons (always present; enabled when charges > 0).
        self.finisher_buttons: list[Button] = []
        self._build_finisher_buttons()
        # Energy button.
        self.btn_energy = Button(
            (cfg.WINDOW_W - 180, cfg.WINDOW_H - 60, 160, 44),
            "Auto Katana", on_click=self._toggle_energy,
        )
        # Nav buttons.
        self.nav_buttons: list[Button] = []
        self._build_nav()

    def _build_nav(self) -> None:
        y = 8
        x = cfg.WINDOW_W - 8
        labels = [
            ("Cosmetics", lambda: self.game.set_screen("cosmetics")),
            ("Bestiary", lambda: self.game.set_screen("bestiary")),
            ("Godai", lambda: self.game.set_screen("godai")),
            ("Hero", lambda: self.game.set_screen("hero")),
            ("Records", lambda: self.game.set_screen("records")),
            ("Settings", lambda: self.game.set_screen("settings")),
            ("Quests", lambda: self.game.set_screen("quests")),
            ("Pets", lambda: self.game.set_screen("pets")),
            ("Skills", lambda: self.game.set_screen("skilltree")),
            ("Upgrades", lambda: self.game.set_screen("upgrades")),
            ("Buildings", lambda: self.game.set_screen("buildings")),
            ("Ascend", lambda: self.game.set_screen("ascend")),
        ]
        for label, cb in reversed(labels):
            w = 64
            x -= w + 4
            btn = Button((x, y, w, 32), label, on_click=cb)
            self.nav_buttons.insert(0, btn)

    def _build_skill_buttons(self) -> None:
        self.skill_buttons = []
        runner = self.game.runner
        x = 16
        for sid, sk in runner.skills.items():
            btn = Button((x, cfg.WINDOW_H - 60, 130, 44), sk.name,
                         on_click=lambda s=sid: self._fire_skill(s))
            self.skill_buttons.append(btn)
            x += 140

    def _build_finisher_buttons(self) -> None:
        """Build the 4 combo-finisher buttons.

        Each button shows the finisher's name; the charge count is drawn
        next to it (in the combo HUD area). The buttons are always
        present; they're disabled when the player has fewer charges than
        the finisher's cost (the runner's ``activate_finisher`` is the
        source of truth — it no-ops and notifies if charges are short).
        """
        from engine.runner import FINISHERS
        self.finisher_buttons = []
        # Place the finisher buttons in a row above the skill buttons
        # (cfg.WINDOW_H - 110) so they don't overlap the skill row.
        x = 16
        y = cfg.WINDOW_H - 110
        for fid, (name, cost, _kind) in FINISHERS.items():
            btn = Button((x, y, 150, 40), name,
                         on_click=lambda f=fid: self._fire_finisher(f))
            self.finisher_buttons.append(btn)
            x += 156
        self._finisher_ids = list(FINISHERS.keys())

    def _fire_finisher(self, fid: str) -> None:
        """Spend charges on a combo finisher (called by the finisher buttons)."""
        self.game.runner.activate_finisher(fid)
        from assets import play
        play("skill", self.game.state.sound_on)

    def _fire_skill(self, sid: str) -> None:
        self.game.runner.activate_skill(sid)
        from assets import play
        play("skill", self.game.state.sound_on)

    def _toggle_energy(self) -> None:
        self.game.runner.toggle_energy()

    def _init_welcome(self) -> None:
        from core import offline
        report = offline.compute(self.game.state)
        if report.get("applied"):
            self.welcome_pending = report

    def handle(self, event: pygame.event.Event) -> None:
        if self.welcome_pending:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                from core import offline
                offline.apply(self.game.state, self.welcome_pending)
                self._welcome_notify(self.welcome_pending)
                self.welcome_pending = None
            return
        # Tap on the road.
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and cfg.ROAD_TOP <= event.pos[1] <= cfg.ROAD_BOTTOM):
            self.game.runner.tap_at(event.pos[0], event.pos[1])
            from assets import play
            play("tap", self.game.state.sound_on)
        for b in self.nav_buttons + self.skill_buttons + self.finisher_buttons:
            b.handle(event)
        self.btn_energy.handle(event)

    def update(self, dt: float) -> None:
        for b in self.nav_buttons + self.skill_buttons + self.finisher_buttons:
            b.update(dt)
        self.btn_energy.update(dt)
        # Refresh skill buttons if the runner's skill set changed.
        if len(self.skill_buttons) != len(self.game.runner.skills):
            self._build_skill_buttons()
        # Lane scroll.
        self.lane_scroll = (self.lane_scroll + 90 * dt) % 60
        # Toasts.
        for t in self.toasts:
            t.update(dt)
        self.toasts = [t for t in self.toasts if t.alive]
        # Welcome.
        if self.welcome_pending:
            self.welcome_t = min(1.0, self.welcome_t + dt * 3)

    def draw(self, surf: pygame.Surface) -> None:
        runner = self.game.runner
        state = self.game.state
        world = runner.world
        ox, oy = self.game.shake_offset()

        from assets import background
        # The background keys on (zone_index, hue); past zone 9 the 9
        # themed zones repeat, so the in-cycle zone index (0..8) keeps
        # the cache keyed by the visible zone while the cycle scales
        # stats. This avoids unbounded background cache growth.
        bg = background(world.zone_in_cycle, world.zone["hue"])
        surf.blit(bg, (ox, oy))

        ly = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2
        for x in range(-60, cfg.WINDOW_W, 60):
            xx = (x - self.lane_scroll) % (cfg.WINDOW_W + 60) - 30
            pygame.draw.rect(surf, C.lane_line, (xx, ly + oy, 30, 4))

        # Enemies.
        from assets import enemy_surface
        for e in world.enemies:
            if not e.alive and e.last_damage_timer <= -0.3:
                continue
            es = enemy_surface(e.edef, size=e.size * 2)
            ex = int(e.x) + ox
            ey = ly + 8 + oy
            e.y = ey
            if not e.alive:
                fade = max(0.0, (e.last_damage_timer + 0.3) / 0.3)
                es = es.copy()
                es.set_alpha(int(255 * fade))
            # Elites get a distinct red-orange tint so they read as a
            # tougher variant at a glance. The mini-boss keeps the boss
            # red — it is already a boss-statted enemy.
            if e.is_elite and e.alive:
                tint = pygame.Surface(es.get_size(), pygame.SRCALPHA)
                tint.fill((255, 140, 60, 90))
                es = es.copy()
                es.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            if e.flash > 0 and e.alive:
                flash = pygame.Surface(es.get_size(), pygame.SRCALPHA)
                flash.fill((255, 255, 255, int(120 * e.flash / 0.12)))
                es = es.copy()
                es.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(es, es.get_rect(midbottom=(ex, ey + 30)))
            if e.max_hp > 0 and e.alive:
                bw = max(28, e.size)
                br = pygame.Rect(ex - bw // 2, ey - 18, bw, 5)
                # Elites get the warning-amber bar; the boss + mini-boss
                # keep the red boss bar so the threat read stays consistent.
                if e.is_boss or e.is_miniboss:
                    bar_fill = C.text_bad
                elif e.is_elite:
                    bar_fill = C.text_warn
                else:
                    bar_fill = C.hp
                draw_bar(surf, br, e.hp / e.max_hp,
                         fill=bar_fill,
                         bg=C.hp_bg, border=C.panel_border)
            if (e.is_boss or e.is_miniboss) and e.alive:
                draw_text_center(surf, e.name, (ex, ey - 28), font_sm(bold=True), C.text_warn)
            if e.is_elite and e.alive:
                draw_text_center(surf, "ELITE", (ex, ey - 44), font_xs(bold=True), C.text_warn)

        # Ninja.
        from assets import ninja_surface
        ns = ninja_surface(72)
        bob = math.sin(runner.ninja.bob * 4) * 2
        nx = 180 + ox
        ny = ly - 30 + bob + oy
        runner.ninja.y = ny
        if not runner.ninja.alive:
            gs = ns.copy()
            gs.fill((10, 10, 20, 120), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(gs, gs.get_rect(midbottom=(nx, ny + 50)))
        else:
            surf.blit(ns, ns.get_rect(midbottom=(nx, ny + 50)))
        if runner.ninja.max_hp > 0:
            br = pygame.Rect(nx - 24, ny - 16, 48, 5)
            draw_bar(surf, br, runner.ninja.hp / runner.ninja.max_hp,
                     fill=C.hp, bg=C.hp_bg, border=C.panel_border)

        # Fireflies.
        from assets import firefly_surface
        for f in world.fireflies:
            fs = firefly_surface(max(6, int(f.size)), f.hue)
            surf.blit(fs, fs.get_rect(center=(int(f.x) + ox, int(f.y) + oy)))

        # FX + particles + death animations + combo milestones + skill VFX.
        runner.fx.draw(surf)
        self.game.particles.draw(surf)
        runner.death_fx.draw(surf)
        runner.combo_fx.draw(surf)
        runner.ninja_fx.draw(surf)
        runner.skill_fx.draw(surf)
        runner.firefly_fx.draw(surf)
        # Boss/mini-boss intro + health bar overlay. The mini-boss intro
        # is brief and does not keep a persistent bar; the zone boss bar
        # stays until the boss dies.
        if runner.boss_fx.active:
            boss = next((e for e in world.enemies if e.is_boss and e.alive), None)
            if boss is None:
                # Mini-boss intro path: no persistent boss entity to track.
                pct = 1.0
            else:
                pct = boss.hp / boss.max_hp if boss.max_hp > 0 else 0
            runner.boss_fx.draw(surf, pct)
        # Zone transition overlay.
        if runner.zone_fx.active:
            runner.zone_fx.draw(surf)

        # HUD.
        self._draw_hud(surf, state, world)

        # Combo (big, center).
        if state.combo >= 1:
            combo_m = runner.combo_mult()
            txt = f"x{combo_m:.1f}  (combo {state.combo})"
            col = C.gold if state.combo < 50 else (C.text_warn if state.combo < 100 else C.text_bad)
            draw_text_center(surf, txt, (cfg.WINDOW_W // 2, cfg.ROAD_TOP + 30),
                             font_lg(bold=True), col)

        # Notifications.
        y = cfg.ROAD_TOP + 70
        for (text, life, color) in runner.notifications[-6:]:
            a = max(0, min(1, life / 3.0))
            img = font_md(bold=True).render(text, True, color)
            img.set_alpha(int(255 * a))
            r = img.get_rect(midtop=(cfg.WINDOW_W // 2, y))
            surf.blit(img, r)
            y += r.h + 4

        # Boss banner.
        if world.boss_active:
            banner = pygame.Rect(0, cfg.ROAD_TOP, cfg.WINDOW_W, 28)
            bg2 = pygame.Surface(banner.size, pygame.SRCALPHA)
            pygame.draw.rect(bg2, (40, 10, 20, 200), bg2.get_rect())
            surf.blit(bg2, banner.topleft)
            draw_text_center(surf, "BOSS", (cfg.WINDOW_W // 2, cfg.ROAD_TOP + 14),
                             font_md(bold=True), C.text_bad)

        # Skill buttons + energy.
        for b in self.skill_buttons:
            b.draw(surf)
        self.btn_energy.draw(surf)
        # Energy bar above the button.
        ebr = pygame.Rect(cfg.WINDOW_W - 180, cfg.WINDOW_H - 70, 160, 6)
        draw_bar(surf, ebr, state.energy / state.energy_max,
                 fill=C.mp, bg=C.mp_bg, border=C.panel_border)

        # Combo Finisher buttons + charge count. The buttons are drawn
        # in a row above the skill buttons; each shows the finisher name
        # and is enabled only when the player has enough charges. The
        # charge count is drawn as a small label above the row.
        from engine.runner import FINISHERS
        charges = state.combo_charges
        # Charge count label (top-left of the finisher row).
        chg_x = 16
        chg_y = cfg.WINDOW_H - 130
        chg_text = f"Charges: {charges}"
        draw_text(surf, chg_text, (chg_x, chg_y), font_sm(bold=True), C.gold)
        for i, b in enumerate(self.finisher_buttons):
            fid = self._finisher_ids[i] if i < len(self._finisher_ids) else None
            if fid is not None:
                _name, cost, _kind = FINISHERS[fid]
                # Enable the button only when the player has enough charges.
                b.enabled = charges >= cost
                # Phantom Step needs combo >= 100 too; show it as
                # disabled (but still spendable on click — the runner
                # refunds the charges with a notification if combo < 100).
                if fid == "phantom_step" and state.combo < 100:
                    b.enabled = False
            b.draw(surf)

        # Nav buttons.
        for b in self.nav_buttons:
            b.draw(surf)

        # Welcome modal.
        if self.welcome_pending:
            self._draw_welcome(surf)

    def _draw_hud(self, surf, state, world) -> None:
        pygame.draw.rect(surf, C.panel_lo, (0, 0, cfg.WINDOW_W, cfg.HUD_H))
        pygame.draw.line(surf, C.panel_border, (0, cfg.HUD_H), (cfg.WINDOW_W, cfg.HUD_H), 1)
        x = 16; y = 10
        x += currency_pill(surf, x, y, "Gold", format_number(state.gold), C.gold) + 10
        x += currency_pill(surf, x, y, "Elixir", format_number(state.elixir), (120, 220, 200)) + 10
        x += currency_pill(surf, x, y, "Amber", format_number(state.amber), (255, 180, 60)) + 10
        currency_pill(surf, x, y, "Medals", format_number(state.medals), (200, 200, 220))
        # Zone + cycle. Past zone 9 the 9 themed zones repeat at scaled
        # stats; the cycle (``zone_index // 9``) is the post-endgame
        # progression, so the HUD always surfaces it. The in-cycle zone
        # (``zone_index % 9``) is the zone the player sees (1-9).
        in_cycle = world.zone_in_cycle
        cycle = world.cycle
        if cycle > 0:
            zone_label = (f"{world.zone_name}  —  Zone {in_cycle + 1}"
                          f"  (Cycle {cycle + 1})")
        else:
            zone_label = f"{world.zone_name}  —  Zone {in_cycle + 1}"
        draw_text_center(surf, zone_label,
                         (cfg.WINDOW_W // 2, 18), font_md(bold=True), C.text)
        zb = pygame.Rect(cfg.WINDOW_W // 2 - 140, 38, 280, 10)
        draw_bar(surf, zb, world.zone_progress(), fill=C.exp, bg=C.mp_bg, border=C.panel_border)

    def _draw_welcome(self, surf) -> None:
        from core import offline
        report = self.welcome_pending
        dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, int(160 * self.welcome_t)))
        surf.blit(dim, (0, 0))
        cw, ch = 560, 220
        cx, cy = cfg.WINDOW_W // 2, cfg.WINDOW_H // 2
        r = pygame.Rect(0, 0, cw, ch)
        r.center = (cx, cy)
        draw_panel(surf, r, fill=(22, 26, 46), border=C.panel_border_hi, border_w=2, radius=16)
        draw_text_center(surf, "Welcome back", (cx, r.y + 36), font_xl(bold=True), C.text)
        dur = offline.format_duration(report["seconds"])
        draw_text_center(surf, f"Away for {dur}", (cx, r.y + 76), font_md(), C.text_dim)
        draw_text_center(surf, f"+{format_number(report['gold'])} gold",
                         (cx, r.y + 116), font_lg(bold=True), C.gold)
        draw_text_center(surf, f"+{report['kills']} enemies slain",
                         (cx, r.y + 150), font_sm(), C.text_dim)
        a = int(180 + 60 * math.sin(self.welcome_t * 6))
        draw_text_center(surf, "click to collect", (cx, r.bottom - 24),
                         font_sm(), (a, a, a))

    def _welcome_notify(self, report) -> None:
        from core import offline
        dur = offline.format_duration(report["seconds"])
        self.notify(f"While away {dur}: +{format_number(report['gold'])} gold", C.gold)

    def notify(self, text: str, color=C.text) -> None:
        from ui.widgets import Toast
        self.toasts.append(Toast(text, life=3.0, color=color))
        if len(self.toasts) > 6:
            self.toasts.pop(0)
