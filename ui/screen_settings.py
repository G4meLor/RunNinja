"""Settings screen for Tap Ninja."""
from __future__ import annotations

import os
import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel
from ui.widgets import Button
from core.state import SAVE_FILE
from core.quality import valid_tiers


# The three render-quality tiers, in the order the toggle cycles through
# them. ``low`` caps particles at 25% and disables glow/parallax; ``med``
# is the default; ``high`` is the full combat peak.
_QUALITY_ORDER = list(valid_tiers())
# Display labels for the tier (capitalised; the stored value is lowercase).
_QUALITY_LABELS = {"high": "High", "med": "Medium", "low": "Low"}


class SettingsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.btn_sound = Button((cfg.WINDOW_W // 2 - 160, 220, 320, 48), "",
                                on_click=self._toggle_sound)
        self.btn_motion = Button((cfg.WINDOW_W // 2 - 160, 290, 320, 48), "",
                                 on_click=self._toggle_motion)
        # Render-quality 3-way toggle. Cycles High -> Medium -> Low -> High.
        # When reduced_motion is on, the toggle is locked to Low (the gate
        # forces the low tier; the toggle reflects that rather than
        # letting the player pick a tier that would be silently overridden).
        self.btn_quality = Button((cfg.WINDOW_W // 2 - 160, 360, 320, 48), "",
                                  on_click=self._toggle_quality)
        self.btn_reset = Button((cfg.WINDOW_W // 2 - 160, 470, 320, 48),
                                "Reset all progress", on_click=self._reset, color=(160, 50, 60))
        self.buttons = [self.btn_back, self.btn_sound, self.btn_motion,
                        self.btn_quality, self.btn_reset]
        self.reset_confirm = 0.0

    def _toggle_sound(self):
        self.game.state.sound_on = not self.game.state.sound_on
        self.game.state.save()

    def _toggle_motion(self):
        self.game.state.reduced_motion = not self.game.state.reduced_motion
        self.game.state.save()
        # Re-apply the render tier to the particle system so the cap
        # tracks the effective tier immediately (reduced_motion forces
        # low; turning it off restores the stored tier's cap).
        self._apply_tier_to_particles()

    def _toggle_quality(self):
        """Cycle the render-quality tier High -> Medium -> Low -> High.

        Locked to Low while reduced_motion is on (the gate forces low;
        the toggle reflects the effective tier rather than letting the
        player pick a tier that would be silently overridden).
        """
        state = self.game.state
        if state.reduced_motion:
            return  # locked to Low (effective_render_quality() is "low")
        i = _QUALITY_ORDER.index(state.render_quality) \
            if state.render_quality in _QUALITY_ORDER else 1
        state.render_quality = _QUALITY_ORDER[(i + 1) % len(_QUALITY_ORDER)]
        state.save()
        self._apply_tier_to_particles()

    def _apply_tier_to_particles(self):
        """Rebind the particle system's cap to the effective tier.

        ``main.py`` sets the cap at construction; this re-applies it when
        the player toggles the tier (or reduced_motion) mid-session, so
        the cap tracks the effective tier without a restart.
        """
        from core.quality import particle_mult
        from engine.particles import ParticleSystem2
        q = self.game.state.effective_render_quality()
        self.game.particles.max_particles = int(
            particle_mult(q) * ParticleSystem2.DEFAULT_MAX_PARTICLES
        )

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
            self._apply_tier_to_particles()
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
        # Render-quality toggle: show the effective tier (Low when
        # reduced_motion is on) and lock the button while the gate is on.
        eff = state.effective_render_quality()
        self.btn_quality.label = f"Render quality: {_QUALITY_LABELS[eff]}"
        # Highlight the selected tier: green on high, neutral on med,
        # dim on low; greyed out (disabled look) when locked by
        # reduced_motion so the player sees the gate, not a silent
        # override.
        if state.reduced_motion:
            self.btn_quality.color = (90, 60, 60)
            self.btn_quality.enabled = False
        else:
            self.btn_quality.enabled = True
            if eff == "high":
                self.btn_quality.color = (60, 120, 90)
            elif eff == "med":
                self.btn_quality.color = (70, 90, 120)
            else:  # low (selected manually, not by the gate)
                self.btn_quality.color = (120, 90, 60)
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
        r = pygame.Rect(cfg.WINDOW_W // 2 - 200, 180, 400, 330)
        draw_panel(surf, r, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Accessibility", (r.x + 20, r.y + 16), font_md(bold=True), C.text)
        draw_text(surf, "Reduced motion disables shake & heavy particles.",
                  (r.x + 20, r.y + 40), font_xs(), C.text_dim)
        draw_text(surf, "Render quality caps particles & glow (Low = 60fps floor).",
                  (r.x + 20, r.y + 330 - 26), font_xs(), C.text_dim)
        for b in self.buttons:
            b.draw(surf)
        draw_text_center(surf, f"Save: {SAVE_FILE}",
                         (cfg.WINDOW_W // 2, cfg.WINDOW_H - 110), font_xs(), C.text_muted)
