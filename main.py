"""Tap Ninja — an idle adventure on the endless road.

Self-contained pygame idle game inspired by Tap Ninja: tap/auto-attack
enemies, earn gold, buy buildings & upgrades, ascend for Elixir, spend
it on a permanent skill tree, collect pets, catch fireflies, and push
to ever-deeper zones.

Run with:  python3 main.py
"""
from __future__ import annotations

import os
import math
import time

import pygame

import config as cfg
from utils import rng
from core.state import GameState
from core.quality import particle_mult
from core.login_streak import check_streak, apply_streak
from engine.runner import Runner
from assets import init_sfx, make_music_sound, root_hz_for_zone
from engine.particles import ParticleSystem2
from ui.screen_menu import MenuScreen
from ui.screen_game import GameScreen
from ui.screen_buildings import BuildingsScreen
from ui.screen_upgrades import UpgradesScreen
from ui.screen_skilltree import SkillTreeScreen
from ui.screen_pets import PetsScreen
from ui.screen_ascend import AscendScreen
from ui.screen_quests import QuestsScreen
from ui.screen_records import RecordsScreen
from ui.screen_settings import SettingsScreen
from ui.screen_cosmetics import CosmeticsScreen
from ui.screen_bestiary import BestiaryScreen
from ui.screen_hero import HeroScreen
from ui.screen_godai import GodaiScreen
from ui.screen_menuhub import MenuHubScreen


class Game:
    def __init__(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "x11")
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        self.screen = pygame.display.set_mode((cfg.WINDOW_W, cfg.WINDOW_H))
        pygame.display.set_caption("Tap Ninja — an idle adventure")
        self.clock = pygame.time.Clock()

        self.state = GameState.load()
        if self.state.pet_pulls == 0 and self.state.monsters_killed == 0:
            self.state.gold += 200
        # Task 38 (pl-accessibility): apply the saved accessibility
        # settings at startup so the high-contrast palette, text scale,
        # and dyslexia font are active from the first frame. Each is
        # independent of music (the toggles are separate state fields).
        from theme import (apply_high_contrast, apply_text_scale,
                           apply_dyslexia_font)
        apply_high_contrast(self.state)
        apply_text_scale(self.state)
        apply_dyslexia_font(self.state)
        # Daily login streak reward (on load).
        streak, reward, is_new_day = check_streak(self.state)
        if is_new_day and reward > 0:
            apply_streak(self.state, reward)
            self._login_reward = (streak, reward)
        else:
            self._login_reward = None

        self.runner = Runner(self.state)
        # ParticleSystem2 is the sole particle system: fully pooled (zero
        # per-frame Surface allocations after warm-up) and API-compatible
        # with the legacy assets.ParticleSystem (burst/trail/update/draw).
        # The death/firefly/combo FX systems keep their own internal pools
        # for now (they are already pooled); this is the main road-FX pool.
        # The render tier caps the active-particle count per quality
        # (high=600, med=360, low=150); reduced_motion forces the low
        # tier via effective_render_quality() so the two gates never
        # diverge.
        _q = self.state.effective_render_quality()
        self.particles = ParticleSystem2(
            max_particles=int(particle_mult(_q) * ParticleSystem2.DEFAULT_MAX_PARTICLES)
        )
        init_sfx()
        # Wire the death-FX screen-shake callback (boss deaths shake).
        # reduced_motion forces the low tier, so the death-FX gate reads
        # the same flag the tier does (the two never diverge).
        self.runner.death_fx.on_shake = self.shake
        self.runner.death_fx.reduced_motion = self.state.reduced_motion

        self.shake_t = 0.0
        self.shake_amp = 0.0
        self.hitstop = 0.0

        # --- Generative music loop (Task 37 / pl-music-sfx) ---
        # A background ambient music loop gated on ``state.music_on``
        # (SEPARATE from ``state.sound_on`` -- the SFX gate). The loop
        # plays the current zone's segment (a 4-bar generative drone +
        # koto melody + taiko percussion keyed to the zone hue); when the
        # segment ends (or the zone changes), it generates the next
        # segment (re-rolled) at the new root_hz and crossfades. The
        # output is scaled by ``state.volume``. The loop is non-blocking:
        # two reserved mixer channels (the primary for the current
        # segment, the secondary for the outgoing segment during a
        # crossfade) + ``get_busy()`` checks each frame. The crossfade is
        # a true overlap: on a zone change, the old segment fades out on
        # the secondary channel while the new segment fades in on the
        # primary (no hard cut, no sudden silence -- the two segments
        # overlap for ~1s).
        self._music_channel = None        # primary (the current/new segment)
        self._music_channel_b = None     # secondary (the outgoing segment during a crossfade)
        self._music_current = None        # the currently-playing Sound (on the primary)
        self._music_outgoing = None       # the outgoing Sound (on the secondary, fading out)
        self._music_zone_index = -1       # the zone the current segment is for
        self._music_cycle_seed = 0        # per-cycle seed (re-rolled each cycle)
        self._music_fade = 0.0           # crossfade timer (0 = not fading; >0 = fading)
        # ``_music_fade_dir``: +1 = fading in a new segment (the primary
        # ramps up); -1 = crossfading (the primary ramps up, the outgoing
        # on the secondary ramps down). 0 = not fading.
        self._music_fade_dir = 0
        try:
            if pygame.mixer.get_init():
                # Reserve two channels for the music (channels 0 + 1).
                # The SFX use the default pool (channels 2..7); the music
                # is on its own channels so it doesn't cut SFX and vice
                # versa. Channel 0 is the primary (the current segment);
                # channel 1 is the secondary (the outgoing segment during
                # a crossfade).
                self._music_channel = pygame.mixer.Channel(0)
                self._music_channel_b = pygame.mixer.Channel(1)
        except Exception:
            self._music_channel = None
            self._music_channel_b = None

        self.screens = {
            "menu": MenuScreen(self),
            "game": GameScreen(self),
            "buildings": BuildingsScreen(self),
            "upgrades": UpgradesScreen(self),
            "skilltree": SkillTreeScreen(self),
            "pets": PetsScreen(self),
            "ascend": AscendScreen(self),
            "quests": QuestsScreen(self),
            "records": RecordsScreen(self),
            "settings": SettingsScreen(self),
            "cosmetics": CosmeticsScreen(self),
            "bestiary": BestiaryScreen(self),
            "hero": HeroScreen(self),
            "godai": GodaiScreen(self),
            "menuhub": MenuHubScreen(self),
        }
        self.current_screen = "menu"
        self.paused = False
        self.show_fps = False
        self._save_timer = 0.0

    def set_screen(self, name):
        if name in self.screens:
            # Only compute offline progress on a real load (initial menu→game
            # transition), not on every in-session screen switch — otherwise
            # the player could double-collect by bouncing between screens.
            self.current_screen = name

    def toggle_pause(self):
        self.paused = not self.paused

    def shake(self, amp=6.0, dur=0.25):
        # The low tier (which reduced_motion forces) disables shake;
        # med/high allow it. Reading the effective tier keeps this gate
        # on the same code path as the render tier.
        if self.state.effective_render_quality() == "low":
            return
        self.shake_amp = max(self.shake_amp, amp)
        self.shake_t = max(self.shake_t, dur)

    def hitstop_for(self, dur=0.08):
        # Hitstop is a motion-heavy effect; gate it on the same tier
        # path as shake (low disables, med/high allow).
        if self.state.effective_render_quality() == "low":
            return
        self.hitstop = max(self.hitstop, dur)

    def shake_offset(self):
        if self.shake_t <= 0 or self.state.effective_render_quality() == "low":
            return (0, 0)
        return (int(rng().uniform(-1, 1) * self.shake_amp),
                int(rng().uniform(-1, 1) * self.shake_amp))

    def run(self):
        running = True
        last = time.monotonic()
        while running:
            now = time.monotonic()
            dt = min(0.05, now - last)
            last = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.current_screen != "game":
                            self.set_screen("game")
                        else:
                            self.paused = not self.paused
                    elif event.key == pygame.K_p:
                        self.paused = not self.paused
                    elif event.key == pygame.K_F1:
                        self.show_fps = not self.show_fps
                    elif event.key == pygame.K_0:
                        self.set_screen("menu")
                    elif event.key == pygame.K_1:
                        self.set_screen("game")
                    elif event.key == pygame.K_2:
                        self.set_screen("buildings")
                    elif event.key == pygame.K_3:
                        self.set_screen("upgrades")
                    elif event.key == pygame.K_4:
                        self.set_screen("skilltree")
                    elif event.key == pygame.K_5:
                        self.set_screen("pets")
                    elif event.key == pygame.K_6:
                        self.set_screen("ascend")
                    elif event.key == pygame.K_7:
                        self.set_screen("quests")
                    elif event.key == pygame.K_8:
                        self.set_screen("records")
                    elif event.key == pygame.K_9:
                        self.set_screen("settings")
                    elif event.key == pygame.K_h:
                        self.set_screen("hero")
                    elif event.key == pygame.K_b:
                        self.set_screen("bestiary")
                    elif event.key == pygame.K_g:
                        self.set_screen("godai")
                    elif event.key == pygame.K_c:
                        self.set_screen("cosmetics")
                    elif event.key == pygame.K_m:
                        self.set_screen("menuhub")
                self.screens[self.current_screen].handle(event)

            self._update(dt)
            self.screens[self.current_screen].draw(self.screen)
            if self.show_fps:
                self._draw_fps()
            if self.paused and self.current_screen == "game":
                self._draw_pause()
            pygame.display.flip()
            self.clock.tick(cfg.FPS_CAP)

        self.state.save()
        pygame.quit()

    def _update(self, dt):
        if self.hitstop > 0:
            self.hitstop -= dt
            scaled = dt * 0.05
        else:
            scaled = dt
        if self.shake_t > 0:
            self.shake_t -= dt
            self.shake_amp *= math.exp(-dt * 8)
            if self.shake_t <= 0:
                self.shake_amp = 0.0

        # The simulation (buildings, combat, fireflies, energy, quests) runs on
        # every screen so the idle loop keeps earning while the player browses
        # buildings/upgrades/etc.  Only the road FX/particles are gated to the
        # game screen.
        if not self.paused:
            self.runner.update(scaled)
            self.state.playtime += scaled
        if self.current_screen == "game" and not self.paused:
            self._update_particles(scaled)
        else:
            self._update_particles(dt)
            self.runner.update_fx(dt)
        # Autosave regardless of screen.
        self._save_timer += dt
        if self._save_timer >= 15.0:
            self._save_timer = 0.0
            self.state.save()
        self.screens[self.current_screen].update(dt)
        # Generative music loop (Task 37 / pl-music-sfx): plays the
        # current zone's ambient segment, re-rolling each cycle and
        # crossfading on zone changes. Gated on ``state.music_on``
        # (SEPARATE from ``state.sound_on``); scaled by ``state.volume``.
        # Non-blocking: a reserved channel + ``get_busy()`` checks each
        # frame; the crossfade is a 1s overlap.
        self._update_music(dt)

    def _update_music(self, dt):
        """The generative music loop.

        Plays the current zone's ambient segment (a 4-bar generative
        drone + koto + taiko keyed to the zone hue); when the segment
        ends (or the zone changes), generates the next segment (re-rolled)
        and crossfades. Gated on ``state.music_on``; scaled by
        ``state.volume``. Non-blocking (two reserved channels +
        ``get_busy()`` checks). Degrades gracefully (no crash if the
        mixer is gone).

        Crossfade: on a zone change, the old segment is NOT hard-cut.
        It moves to the secondary channel (channel 1) and fades out over
        ~1s, while the new segment fades in on the primary (channel 0).
        The two segments overlap for ~1s (a true crossfade, no sudden
        silence, no jarring key change). On a segment end (the old
        segment ended naturally), the new segment fades in on the primary
        (no outgoing to fade out -- the old already ended).
        """
        try:
            # Gate: music_on is SEPARATE from sound_on. If music is off,
            # stop the current segment and return (don't generate).
            if not self.state.music_on:
                self._stop_music()
                return
            ch = self._music_channel
            if ch is None:
                return  # no mixer; nothing to play
            # Crossfade in progress: ramp the primary (new) up + the
            # secondary (outgoing) down over ~1s. The two segments overlap
            # (a true crossfade -- no hard cut, no sudden silence).
            if self._music_fade > 0:
                self._music_fade -= dt
                # t goes 0 -> 1 over the fade (the new ramps up, the old
                # ramps down).
                t = 1.0 - max(0.0, self._music_fade / 1.0)
                if self._music_current is not None:
                    try: self._music_current.set_volume(self.state.volume * t)
                    except Exception: pass
                if self._music_fade_dir < 0 and self._music_outgoing is not None:
                    # Crossfade: the outgoing ramps down.
                    try: self._music_outgoing.set_volume(self.state.volume * (1 - t))
                    except Exception: pass
                if self._music_fade <= 0:
                    self._music_fade = 0.0
                    self._music_fade_dir = 0
                    # Crossfade done: stop + drop the outgoing.
                    if self._music_outgoing is not None:
                        try: self._music_outgoing.stop()
                        except Exception: pass
                        self._music_outgoing = None
                        if self._music_channel_b is not None:
                            try: self._music_channel_b.stop()
                            except Exception: pass
                return
            # Not fading: keep the current segment's volume scaled by
            # state.volume (so the slider takes effect live).
            if self._music_current is not None:
                try: self._music_current.set_volume(self.state.volume)
                except Exception: pass
            # Did the zone change? If so, start a crossfade to a new
            # segment at the new root_hz (the old segment moves to the
            # secondary + fades out; the new fades in on the primary; no
            # hard cut, no sudden silence). If there's no current segment
            # yet (the first segment), just fade in.
            if self.state.zone_index != self._music_zone_index:
                if self._music_current is None:
                    self._start_music_segment(fade=True)
                else:
                    self._start_music_segment(crossfade=True)
                return
            # Is the current segment done? If so, re-roll the next cycle
            # (a new segment at the same root_hz, re-seeded, faded in --
            # the old ended naturally so no outgoing to crossfade). Only
            # do this if we're not in the middle of a fade-in (the
            # primary may report not-busy during the fade-in if the
            # segment is very short; the fade-in completes first).
            if not ch.get_busy() and self._music_fade <= 0:
                self._start_music_segment(fade=True)
        except Exception:
            # Degrade gracefully: never crash the game over music.
            pass

    def _stop_music(self):
        """Stop the music and clear the loop state (music_on turned off)."""
        try:
            ch = self._music_channel
            if ch is not None:
                ch.stop()
            if self._music_channel_b is not None:
                self._music_channel_b.stop()
            if self._music_current is not None:
                try: self._music_current.stop()
                except Exception: pass
            if self._music_outgoing is not None:
                try: self._music_outgoing.stop()
                except Exception: pass
        except Exception:
            pass
        self._music_current = None
        self._music_outgoing = None
        self._music_fade = 0.0
        self._music_fade_dir = 0
        self._music_zone_index = -1

    def _start_music_segment(self, *, fade: bool = False, crossfade: bool = False):
        """Generate + play a new segment at the current zone's root_hz.

        Generates a new segment (re-rolled with a fresh seed) at the
        current zone's root_hz (mapped from the zone hue) and plays it
        on the primary music channel. If ``fade``, the segment fades in
        over ~1s (the old segment ended naturally; no outgoing to fade
        out). If ``crossfade``, the old segment moves to the secondary
        channel and fades out while the new segment fades in on the
        primary (a true overlap crossfade -- no hard cut, no sudden
        silence, no jarring key change). Degrades gracefully if the
        mixer is unavailable or the segment fails to generate.
        """
        from data.enemies import zone_by_index
        try:
            zone = zone_by_index(self.state.zone_index)
            root_hz = root_hz_for_zone(self.state.zone_index, zone.get("hue", 0))
        except Exception:
            root_hz = 220.0
        # Re-roll the cycle seed (non-repetition).
        self._music_cycle_seed = int(rng().random() * (1 << 31))
        snd = make_music_sound(root_hz, bars=4, seed=self._music_cycle_seed)
        if snd is None:
            return  # mixer unavailable; degrade gracefully
        ch = self._music_channel
        if ch is None:
            return
        try:
            if crossfade:
                # Move the current segment to the secondary channel +
                # fade it out while the new segment fades in on the
                # primary. The two segments overlap for ~1s (a true
                # crossfade -- no hard cut, no sudden silence).
                if self._music_current is not None and self._music_channel_b is not None:
                    # The outgoing keeps its current volume (it'll ramp
                    # down during the fade). Move it to the secondary.
                    self._music_outgoing = self._music_current
                    try: self._music_channel_b.play(self._music_outgoing)
                    except Exception: pass
                # The new segment starts at volume 0 and ramps up.
                snd.set_volume(0.0)
                self._music_fade = 1.0
                self._music_fade_dir = -1  # crossfade (outgoing ramps down)
            elif fade:
                # Fade-in only (the old segment ended naturally; no
                # outgoing to crossfade). Start at volume 0 + ramp up.
                snd.set_volume(0.0)
                self._music_fade = 1.0
                self._music_fade_dir = 1   # fade-in (no outgoing)
            else:
                snd.set_volume(self.state.volume)
                self._music_fade = 0.0
                self._music_fade_dir = 0
            ch.play(snd)
            self._music_current = snd
            self._music_zone_index = self.state.zone_index
        except Exception:
            pass

    def _update_particles(self, dt):
        # Death bursts are handled by DeathFxSystem (wired in the runner);
        # this advances the pooled ParticleSystem2 used for hit sparks.
        self.particles.update(dt)

    def _draw_fps(self):
        from theme import font_sm, C as TC
        s = font_sm().render(f"FPS {self.clock.get_fps():.0f}", True, TC.text_dim)
        self.screen.blit(s, (cfg.WINDOW_W - 70, 4))

    def _draw_pause(self):
        from theme import C as TC, font_xl
        ov = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 120))
        self.screen.blit(ov, (0, 0))
        s = font_xl(bold=True).render("PAUSED  —  press P to resume", True, TC.text)
        self.screen.blit(s, s.get_rect(center=(cfg.WINDOW_W // 2, cfg.WINDOW_H // 2)))


C_text_bad = (255, 110, 120)


def main():
    Game().run()


if __name__ == "__main__":
    main()
