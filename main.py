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
from core.login_streak import check_streak, apply_streak
from engine.runner import Runner
from assets import ParticleSystem, init_sfx
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
        # Daily login streak reward (on load).
        streak, reward, is_new_day = check_streak(self.state)
        if is_new_day and reward > 0:
            apply_streak(self.state, reward)
            self._login_reward = (streak, reward)
        else:
            self._login_reward = None

        self.runner = Runner(self.state)
        self.particles = ParticleSystem()
        init_sfx()
        # Wire the death-FX screen-shake callback (boss deaths shake).
        self.runner.death_fx.on_shake = self.shake
        self.runner.death_fx.reduced_motion = self.state.reduced_motion

        self.shake_t = 0.0
        self.shake_amp = 0.0
        self.hitstop = 0.0

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
        if self.state.reduced_motion:
            return
        self.shake_amp = max(self.shake_amp, amp)
        self.shake_t = max(self.shake_t, dur)

    def hitstop_for(self, dur=0.08):
        if self.state.reduced_motion:
            return
        self.hitstop = max(self.hitstop, dur)

    def shake_offset(self):
        if self.shake_t <= 0 or self.state.reduced_motion:
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

    def _update_particles(self, dt):
        # Death bursts are now handled by DeathFxSystem (wired in the runner),
        # so this just advances the legacy particle pool used for hit sparks.
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
