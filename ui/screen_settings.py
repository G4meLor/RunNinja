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
from utils import clamp


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
        # Task 37 (pl-music-sfx): a SEPARATE music toggle, distinct from
        # the Sound/SFX toggle above. ``music_on`` is gated on its own
        # state field (``state.music_on``), NOT on ``state.sound_on``.
        # The two toggles are independent (a player can have SFX on +
        # music off, or music on + SFX off, or both, or neither).
        self.btn_music = Button((cfg.WINDOW_W // 2 - 160, 290, 320, 48), "",
                                on_click=self._toggle_music)
        self.btn_motion = Button((cfg.WINDOW_W // 2 - 160, 360, 320, 48), "",
                                 on_click=self._toggle_motion)
        # Render-quality 3-way toggle. Cycles High -> Medium -> Low -> High.
        # When reduced_motion is on, the toggle is locked to Low (the gate
        # forces the low tier; the toggle reflects that rather than
        # letting the player pick a tier that would be silently overridden).
        self.btn_quality = Button((cfg.WINDOW_W // 2 - 160, 430, 320, 48), "",
                                  on_click=self._toggle_quality)
        self.btn_reset = Button((cfg.WINDOW_W // 2 - 160, 540, 320, 48),
                                "Reset all progress", on_click=self._reset, color=(160, 50, 60),
                                sound="ui_confirm")
        self.buttons = [self.btn_back, self.btn_sound, self.btn_music,
                        self.btn_motion, self.btn_quality, self.btn_reset]
        # Task 37 (pl-music-sfx): a volume slider for ``state.volume``
        # (0.0..1.0). The slider sets ``state.volume`` and saves. The
        # slider rect is below the music toggle; the player drags the
        # handle to set the volume.
        self._slider_rect = pygame.Rect(cfg.WINDOW_W // 2 - 160, 500, 320, 16)
        self._slider_dragging = False
        self.reset_confirm = 0.0

    def _toggle_sound(self):
        self.game.state.sound_on = not self.game.state.sound_on
        self.game.state.save()

    def _toggle_music(self):
        # Task 37 (pl-music-sfx): a SEPARATE music toggle, distinct from
        # the Sound/SFX toggle. Gated on ``state.music_on``, NOT on
        # ``state.sound_on``. The two toggles are independent.
        self.game.state.music_on = not self.game.state.music_on
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
        # Task 37 (pl-music-sfx): pass ``state.sound_on`` to each button
        # so the UI click sound is gated on the SFX toggle (the sound is
        # a layered SFX, ``ui_click``/``ui_confirm``, not a pure sine).
        state = self.game.state
        for b in self.buttons:
            b.sound_on = state.sound_on
        for b in self.buttons:
            b.handle(event)
        # Task 37 (pl-music-sfx): the volume slider. Handle mouse events
        # for the slider rect (drag the handle to set the volume).
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._slider_rect.collidepoint(event.pos):
                self._slider_dragging = True
                self._set_volume_from_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._slider_dragging:
                self._slider_dragging = False
                self.game.state.save()
        elif event.type == pygame.MOUSEMOTION:
            if self._slider_dragging:
                self._set_volume_from_x(event.pos[0])

    def _set_volume_from_x(self, x):
        """Set ``state.volume`` from a mouse x position on the slider."""
        r = self._slider_rect
        pct = (x - r.x) / max(1, r.w)
        self.game.state.volume = clamp(pct, 0.0, 1.0)

    def update(self, dt):
        state = self.game.state
        self.btn_sound.label = f"Sound: {'ON' if state.sound_on else 'OFF'}"
        self.btn_sound.color = (60, 120, 90) if state.sound_on else (90, 60, 60)
        # Task 37 (pl-music-sfx): the music toggle (SEPARATE from the
        # Sound/SFX toggle). Green on / red off, same as the Sound
        # toggle, but gated on ``state.music_on`` (NOT ``sound_on``).
        self.btn_music.label = f"Music: {'ON' if state.music_on else 'OFF'}"
        self.btn_music.color = (60, 120, 90) if state.music_on else (90, 60, 60)
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
        # The panel is taller now (it holds the music toggle + the volume
        # slider + the existing toggles). The buttons are laid out below.
        r = pygame.Rect(cfg.WINDOW_W // 2 - 200, 180, 400, 430)
        draw_panel(surf, r, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Accessibility", (r.x + 20, r.y + 16), font_md(bold=True), C.text)
        draw_text(surf, "Reduced motion disables shake & heavy particles.",
                  (r.x + 20, r.y + 40), font_xs(), C.text_dim)
        draw_text(surf, "Render quality caps particles & glow (Low = 60fps floor).",
                  (r.x + 20, r.y + 430 - 26), font_xs(), C.text_dim)
        for b in self.buttons:
            b.draw(surf)
        # Task 37 (pl-music-sfx): the volume slider. A horizontal slider
        # for ``state.volume`` (0.0..1.0). The slider is below the music
        # toggle (which is below the Sound toggle). The player drags the
        # handle to set the volume; the value is shown as a percentage.
        from theme import draw_bar
        sr = self._slider_rect
        # Label + value.
        draw_text(surf, "Music volume",
                  (sr.x, sr.y - 18), font_xs(), C.text_dim)
        draw_text(surf, f"{int(self.game.state.volume * 100)}%",
                  (sr.right - 40, sr.y - 18), font_xs(), C.text)
        # The track + the fill.
        draw_bar(surf, sr, self.game.state.volume,
                 fill=C.hp, bg=C.hp_bg, border=C.panel_border, radius=3)
        # The handle (a small circle at the fill's right edge).
        hx = sr.x + int(sr.w * self.game.state.volume)
        pygame.draw.circle(surf, C.text, (hx, sr.centery), 7)
        pygame.draw.circle(surf, C.panel_border, (hx, sr.centery), 7, 1)
        draw_text_center(surf, f"Save: {SAVE_FILE}",
                         (cfg.WINDOW_W // 2, cfg.WINDOW_H - 110), font_xs(), C.text_muted)
