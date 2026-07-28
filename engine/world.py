"""World: zones, distance, enemy spawning, firefly spawning, boss.

Pure state — no drawing.  The renderer reads positions.
"""
from __future__ import annotations

import math

import config as cfg
from data import enemies as ed
from engine.enemy import Enemy, spawn_enemy, spawn_boss
from utils import rng


class World:
    def __init__(self) -> None:
        self.zone_index = 0
        self.zone_distance = 0.0
        self.total_distance = 0.0
        self.enemies: list[Enemy] = []
        self.spawn_timer = 0.0
        self.boss_active = False
        self.firefly_timer = 0.0
        self.fireflies: list = []   # engine.firefly.Firefly
        # Runner-owned EventBus (wired by the Runner via set_event_bus).
        # When None, the legacy module-global callbacks below are used.
        self._bus = None

    @property
    def zone(self) -> dict:
        return ed.zone_by_index(self.zone_index)

    @property
    def zone_name(self) -> str:
        return self.zone["name"]

    @property
    def zone_id(self) -> str:
        return self.zone["id"]

    def zone_progress(self) -> float:
        return min(1.0, self.zone_distance / cfg.ZONE_DISTANCE)

    # --- Stat scaling ---
    def zone_hp(self, edef) -> float:
        return (cfg.ZONE_HP_BASE * (cfg.ZONE_HP_GROWTH ** self.zone_index)
                * edef.hp_mult)

    def zone_dmg(self, edef) -> float:
        return (cfg.ZONE_DMG_BASE * (cfg.ZONE_DMG_GROWTH ** self.zone_index)
                * edef.dmg_mult)

    def zone_gold(self, edef) -> float:
        return (cfg.ZONE_GOLD_BASE * (cfg.ZONE_GOLD_GROWTH ** self.zone_index)
                * edef.gold_mult)

    def spawn_interval(self, density_pct: float = 0.0) -> float:
        base = cfg.SPAWN_INTERVAL * (cfg.SPAWN_INTERVAL_MIN / cfg.SPAWN_INTERVAL) ** min(1.0, self.zone_index / 8.0)
        base = max(cfg.SPAWN_INTERVAL_MIN, base)
        base *= (1.0 - min(0.8, density_pct))
        return max(cfg.SPAWN_INTERVAL_MIN, base)

    def update(self, dt: float, *, paused: bool, density_pct: float = 0.0,
               firefly_spawn_pct: float = 0.0) -> None:
        if paused:
            return
        # Spawn enemies.
        self.spawn_timer += dt
        interval = self.spawn_interval(density_pct)
        while self.spawn_timer >= interval:
            self.spawn_timer -= interval
            if not self.boss_active and len(self.enemies) < 6:
                self._spawn_regular()

        # Firefly spawning.
        self.firefly_timer += dt
        firefly_interval = 25.0 / (1.0 + firefly_spawn_pct)
        if self.firefly_timer >= firefly_interval:
            self.firefly_timer -= firefly_interval
            self._spawn_firefly()

        # Distance.
        if not self.boss_active:
            self.zone_distance += dt * 10.0
            self.total_distance += dt * 10.0
            if self.zone_distance >= cfg.ZONE_DISTANCE:
                self._enter_boss()

    def _spawn_regular(self) -> None:
        pool = self.zone["enemies"]
        edef = rng().choice(pool)
        e = spawn_enemy(edef, hp=self.zone_hp(edef), dmg=self.zone_dmg(edef),
                        gold=self.zone_gold(edef))
        self.enemies.append(e)

    def _enter_boss(self) -> None:
        if self.boss_active:
            return
        self.boss_active = True
        bdef = ed.boss_for_zone(self.zone_id)
        boss = spawn_boss(bdef, hp=self.zone_hp(bdef), dmg=self.zone_dmg(bdef),
                          gold=self.zone_gold(bdef))
        self.enemies.append(boss)
        # Boss intro FX: emit via the bus (preferred). The deprecated
        # ``on_boss_spawn`` global is wired by the Runner to forward to
        # the bus, so we do NOT also call it directly here — that would
        # double-fire the event.
        if self._bus is not None:
            self._bus.emit("boss_spawn", boss.name, boss.hue)

    # Hook the runner sets to trigger boss intro FX (deprecated; the bus
    # is preferred).
    on_boss_spawn = None

    def _spawn_firefly(self) -> None:
        from engine.firefly import spawn_firefly
        x = rng().uniform(400, 1200)
        y = rng().uniform(120, 380)
        ff = spawn_firefly(x, y, size_bonus=self.firefly_size_bonus)
        self.fireflies.append(ff)
        # Firefly spawn FX: emit via the bus (preferred). The deprecated
        # ``on_firefly_spawn`` global is wired by the Runner to forward to
        # the bus, so we do NOT also call it directly here — that would
        # double-fire the event.
        if self._bus is not None:
            self._bus.emit("firefly_spawn", ff)

    # Set by the runner so firefly size scales with the fly_size1 bonus.
    firefly_size_bonus = 0.0
    on_firefly_spawn = None

    def on_enemy_killed(self, enemy: Enemy) -> None:
        if enemy.is_boss:
            self.boss_active = False
            self.zone_index += 1
            self.zone_distance = 0.0

    def set_event_bus(self, bus) -> None:
        """Wire the Runner-owned EventBus. Called once by the Runner."""
        self._bus = bus

    def reset_for_ascension(self) -> None:
        self.zone_index = 0
        self.zone_distance = 0.0
        self.enemies.clear()
        self.fireflies.clear()
        self.spawn_timer = 0.0
        self.firefly_timer = 0.0
        self.boss_active = False
