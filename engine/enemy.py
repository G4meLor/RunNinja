"""Enemy + combat tick for Tap Ninja.

Enemies spawn from the right and walk toward the ninja.  The ninja
auto-attacks the nearest enemy; the player can tap for instant damage.
Combo builds per kill and decays after a window.  Active skills fire on
cooldown.  The ninja can take damage from enemies that reach it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import config as cfg
from data import enemies as ed
from utils import rng


PARTY_X = 180
ENEMY_START_X = 1300
ENEMY_ATTACK_RANGE = 230


@dataclass
class Enemy:
    edef: object
    name: str
    shape: str
    hue: int
    hp: float
    max_hp: float
    dmg: float
    gold: float
    speed: float
    size: int
    rare_drop: float
    x: float = ENEMY_START_X
    y: float = 0.0
    attack_timer: float = 0.0
    alive: bool = True
    is_boss: bool = False
    is_elite: bool = False
    is_miniboss: bool = False
    flash: float = 0.0
    last_damage_timer: float = 0.0
    bob: float = 0.0


def spawn_enemy(edef, *, hp: float, dmg: float, gold: float) -> Enemy:
    return Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
                 hp=hp, max_hp=hp, dmg=dmg, gold=gold,
                 speed=edef.speed, size=edef.size, rare_drop=edef.rare_drop)


def spawn_boss(bdef, *, hp: float, dmg: float, gold: float) -> Enemy:
    return Enemy(edef=bdef, name=bdef.name, shape=bdef.shape, hue=bdef.hue,
                 hp=hp, max_hp=hp, dmg=dmg, gold=gold,
                 speed=bdef.speed * 0.6, size=bdef.size, rare_drop=bdef.rare_drop,
                 is_boss=True)


def spawn_miniboss(bdef, *, hp: float, dmg: float, gold: float) -> Enemy:
    """A mini-boss: a boss-statted enemy that is NOT the zone boss.

    Built at 0.4x the zone boss stats by the caller. It blocks progress
    until killed (the world gates ``zone_distance`` on ``miniboss_active``).
    ``is_boss`` stays False so the runner's boss-FX/loot path does not fire
    on a mini-boss; ``is_miniboss`` is True so the world releases the
    progress block on kill.
    """
    return Enemy(edef=bdef, name=bdef.name, shape=bdef.shape, hue=bdef.hue,
                 hp=hp, max_hp=hp, dmg=dmg, gold=gold,
                 speed=bdef.speed * 0.6, size=bdef.size,
                 rare_drop=bdef.rare_drop,
                 is_boss=False, is_miniboss=True)


def nearest_enemy(enemies: list[Enemy]) -> Optional[Enemy]:
    best = None
    best_x = float("inf")
    for e in enemies:
        if e.alive and e.x < best_x:
            best = e
            best_x = e.x
    return best


# FX callbacks (set by the runner).
# DEPRECATED: these module globals are kept as aliases that forward to the
# Runner-owned EventBus for one release. New code should emit events via
# the bus (``engine.eventbus``), not call these globals directly.
_bus = None  # set by the runner via set_event_bus()


def set_event_bus(bus) -> None:
    """Wire the Runner-owned EventBus. Called once by the Runner."""
    global _bus
    _bus = bus


def _emit(name: str, *args, **kwargs) -> None:
    """Emit an event on the bus if wired; else fall back to the legacy global."""
    if _bus is not None:
        _bus.emit(name, *args, **kwargs)


# Legacy module-global FX callbacks (deprecated; forward to the bus when
# the runner wires them). New code should use ``_emit("enemy_dmg", ...)``.
on_enemy_dmg = None   # (x, y, amount, *, is_crit, is_boss)
on_ninja_dmg = None   # (x, y, amount)


def _apply_damage(enemy: Enemy, amount: float, *, is_crit: bool = False) -> None:
    enemy.hp -= amount
    enemy.last_damage_timer = 0.6
    enemy.flash = 0.12
    # Emit via the bus (preferred). The deprecated ``on_enemy_dmg`` global
    # is wired by the Runner to forward to the bus, so we do NOT also call
    # it directly here — that would double-fire the event.
    _emit("enemy_dmg", enemy.x, enemy.y, amount,
          is_crit=is_crit, is_boss=enemy.is_boss)
    if enemy.hp <= 0:
        enemy.hp = 0
        enemy.alive = False


def tap(ninja, enemies: list[Enemy], *, combo_mult: float, gold_mult: float,
        on_kill=None) -> Optional[Enemy]:
    """The player taps — deal tap_damage to the nearest enemy."""
    target = nearest_enemy(enemies)
    if target is None:
        return None
    mult, is_crit = ninja.roll_crit()
    dmg = ninja.tap_damage * mult * combo_mult
    _apply_damage(target, dmg, is_crit=is_crit)
    ninja.slash_anim = 0.15
    if not target.alive and on_kill is not None:
        on_kill(target)
    return target


def tick_combat(ninja, enemies: list[Enemy], dt: float, *,
                combo_mult: float, gold_mult: float,
                auto_active: bool, on_kill=None) -> None:
    """Advance one combat tick."""
    # Enemies move + attack.
    for e in enemies:
        if e.flash > 0:
            e.flash -= dt
        e.last_damage_timer -= dt
        if not e.alive:
            continue
        dist = e.x - PARTY_X
        if dist > ENEMY_ATTACK_RANGE:
            e.x -= e.speed * dt
        else:
            e.attack_timer += dt
            if e.attack_timer >= 1.0:
                e.attack_timer -= 1.0
                if ninja.alive:
                    dmg = ninja.take_damage(e.dmg)
                    # Emit via the bus (preferred). The deprecated
                    # ``on_ninja_dmg`` global is wired by the Runner to
                    # forward to the bus, so we do NOT also call it
                    # directly here — that would double-fire the event.
                    _emit("ninja_dmg", ninja.x, ninja.y, dmg)
        e.bob += dt

    # Ninja auto-attacks.
    if ninja.alive:
        ninja.bob += dt
        if ninja.slash_anim > 0:
            ninja.slash_anim -= dt
        if ninja.last_damage_timer > 0:
            ninja.last_damage_timer -= dt
        speed_mult = 2.0 if auto_active else 1.0
        ninja.attack_timer += dt
        period = 1.0 / max(0.1, ninja.attack_speed * speed_mult)
        while ninja.attack_timer >= period:
            ninja.attack_timer -= period
            target = nearest_enemy(enemies)
            if target is not None:
                mult, is_crit = ninja.roll_crit()
                dmg = ninja.auto_damage * mult * combo_mult
                _apply_damage(target, dmg, is_crit=is_crit)
                if not target.alive and on_kill is not None:
                    on_kill(target)
