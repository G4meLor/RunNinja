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


# ---------------------------------------------------------------------------
# Godai elemental type chart (Task 21 / gp-godai-fusion)
# ---------------------------------------------------------------------------
# A 4-cycle type chart: void > wind > fire > water > void. Each element is
# 2x strong against the next in the cycle and 0.5x weak against the
# previous. "none" (the default attunement) is 1x against everything so the
# system is OPTIONAL — idle players are never worse than 1x. The chart is
# read by ``element_mult(attuned, enemy_element)`` and applied in
# ``_apply_damage`` (``dmg *= element_mult(state.attuned_element, enemy.element)``).
#
# The 4-cycle (clockwise): each attacker is 2x vs the next, 0.5x vs the
# previous, 1x vs itself and "none".
#   void  -> wind 2x, fire 1x, water 0.5x, void 1x, none 1x
#   wind  -> fire 2x, water 1x, void 0.5x, wind 1x, none 1x
#   fire  -> water 2x, void 1x, wind 0.5x, fire 1x, none 1x
#   water -> void 2x, wind 1x, fire 0.5x, water 1x, none 1x
_TYPE_CHART: dict[str, dict[str, float]] = {
    "void":  {"wind": 2.0, "fire": 1.0, "water": 0.5, "void": 1.0, "none": 1.0},
    "wind":  {"fire": 2.0, "water": 1.0, "void": 0.5, "wind": 1.0, "none": 1.0},
    "fire":  {"water": 2.0, "void": 1.0, "wind": 0.5, "fire": 1.0, "none": 1.0},
    "water": {"void": 2.0, "wind": 1.0, "fire": 0.5, "water": 1.0, "none": 1.0},
    "none":  {k: 1.0 for k in ("void", "wind", "fire", "water", "none")},
}


def element_mult(attuned: str, enemy_element: str) -> float:
    """The elemental damage multiplier for ``attuned`` vs ``enemy_element``.

    Returns 2.0 for advantage (the 4-cycle), 0.5 for disadvantage, 1.0 for
    neutral / same / "none". ``attuned == "none"`` (the default) returns
    1.0 for every enemy element so the system is OPTIONAL — idle players
    are never worse than 1x. Unknown elements fall back to 1.0 (no crash).
    """
    return _TYPE_CHART.get(attuned, {}).get(enemy_element, 1.0)


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
    # Task 30 (gfx-sprite-sheet-anim): the bandit shape has a multi-frame
    # idle cycle; the bob timer selects the frame (see
    # assets.enemy_frame). No new state here — the bob timer is the
    # existing one; this comment is the cross-reference.
    # Boss soft-phase scaling (Task 13): the phase is DERIVED from HP each
    # tick (no new state machine, just scaling). ``attack_interval`` scales
    # down as HP drops so the boss attacks faster; ``attack_pattern`` is a
    # label for the current attack layer (melee/projectile/hazard/summon).
    # ``shield`` is a flat HP buffer armed at phase 3 that sustained
    # auto-attack DPS breaks through (no regeneration). All four fields are
    # transient -- they live on the Enemy, not GameState.
    phase: int = 0
    attack_interval: float = 1.0
    attack_pattern: str = "melee"
    shield: float = 0.0
    shield_max: float = 0.0
    # Yokai Portal boss variant (Task 16): a 5% chance for a boss to be a
    # Yokai Portal variant that, when killed, jumps ``zone_distance`` by a
    # chunk (the "zooming through zones" skip). The boss is still killed
    # normally (is_boss=True) so the normal boss-kill path fires (zone
    # advance, bosses_killed++, bestiary/achievement reveals) — only the
    # zone bar ALSO jumps. Transient — no state is kept on GameState.
    is_yokai_portal: bool = False
    # Godai elemental affinity (Task 21 / gp-godai-fusion). Copied from
    # the EnemyDef at spawn time so the type chart can read it without
    # reaching back through ``edef`` (the edef is kept for the bestiary
    # reveal path). One of "none", "void", "wind", "fire", "water".
    # "none" means the type chart is a no-op for this enemy (1x vs any
    # attunement). Transient — lives on the Enemy, not GameState.
    element: str = "none"


def spawn_enemy(edef, *, hp: float, dmg: float, gold: float) -> Enemy:
    return Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
                 hp=hp, max_hp=hp, dmg=dmg, gold=gold,
                 speed=edef.speed, size=edef.size, rare_drop=edef.rare_drop,
                 element=getattr(edef, "element", "none"))


def spawn_boss(bdef, *, hp: float, dmg: float, gold: float) -> Enemy:
    return Enemy(edef=bdef, name=bdef.name, shape=bdef.shape, hue=bdef.hue,
                 hp=hp, max_hp=hp, dmg=dmg, gold=gold,
                 speed=bdef.speed * 0.6, size=bdef.size, rare_drop=bdef.rare_drop,
                 is_boss=True,
                 element=getattr(bdef, "element", "none"))


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
                 is_boss=False, is_miniboss=True,
                 element=getattr(bdef, "element", "none"))


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


# ---------------------------------------------------------------------------
# Boss soft-phase scaling (Task 13)
# ---------------------------------------------------------------------------
# The attack-pattern library + shield tuning live in ``data/enemies.py``
# (``ed.BOSS_PHASE_PATTERNS``, ``ed.BOSS_SHIELD_FRACTION``) so they are the
# single source of truth for re-tuning (see gap #4: re-test the shield
# after Task 24 / gp-tap-auto-rebalance lands). This module references them
# via the ``ed`` alias (``from data import enemies as ed`` above).

def _boss_phase_from_hp(boss: Enemy) -> int:
    """Derive the boss phase from HP thresholds (no state machine).

    Returns 0/1/2/3 at 100/75/50/25% HP milestones. The thresholds are
    checked lowest-first so the deepest phase wins (the brief's specimen
    order -- 1 if <0.75 else 2 if <0.5... -- made 2 and 3 unreachable).
    """
    if boss.max_hp <= 0:
        return 0
    ratio = boss.hp / boss.max_hp
    if ratio < 0.25:
        return 3
    if ratio < 0.5:
        return 2
    if ratio < 0.75:
        return 1
    return 0


def _update_boss_phase(boss: Enemy) -> int:
    """Update the boss's phase from HP. Returns the new phase.

    Scales ``attack_interval`` down as HP drops, sets the ``attack_pattern``
    label per phase, and arms the shield at phase 3 (a flat HP buffer that
    sustained auto-attack DPS breaks through -- no regeneration). Emits a
    ``boss_phase`` event on the bus when the phase changes so the runner
    can trigger phase-transition visuals (nameplate flash + banner + hue
    shift, no pause).
    """
    old_phase = boss.phase
    new_phase = _boss_phase_from_hp(boss)
    if new_phase != old_phase:
        boss.phase = new_phase
        boss.attack_interval = 1.0 / (1.0 + 0.3 * new_phase)
        boss.attack_pattern = ed.BOSS_PHASE_PATTERNS.get(new_phase, "melee")
        # Arm the shield at phase 3 (breakable by sustained auto-attack DPS).
        # The shield does NOT regenerate, so sustained DPS depletes it and
        # the boss takes full damage once the shield is gone.
        if new_phase == 3 and boss.shield <= 0:
            boss.shield_max = boss.max_hp * ed.BOSS_SHIELD_FRACTION
            boss.shield = boss.shield_max
        # Emit the phase transition event so the runner can fire the
        # nameplate flash + banner + hue shift (no pause).
        _emit("boss_phase", boss.name, boss.hue, old_phase, new_phase)
    return new_phase


def _apply_damage(enemy: Enemy, amount: float, *, is_crit: bool = False,
                  attuned: str = "none") -> None:
    # Godai elemental multiplier (Task 21): multiply the incoming damage
    # by ``element_mult(attuned, enemy.element)``. ``attuned`` defaults to
    # "none" (1x) so callers that don't pass it get the idle floor — the
    # system is OPTIONAL. The runner passes ``state.attuned_element`` so
    # the live combat tick uses the player's attunement.
    amount *= element_mult(attuned, enemy.element)
    # Boss shield at phase 3: damage goes to the shield first, then HP.
    # The shield is a flat HP buffer that sustained auto-attack DPS breaks
    # through; it does NOT regenerate, so once it's depleted the boss takes
    # full damage. This is scaling (an extra HP buffer), not a new state
    # machine -- the boss still attacks on the same attack_timer.
    if enemy.is_boss and enemy.shield > 0:
        absorbed = min(enemy.shield, amount)
        enemy.shield -= absorbed
        amount -= absorbed
    enemy.hp -= amount
    enemy.last_damage_timer = 0.6
    enemy.flash = 0.12
    # Emit via the bus (preferred). The deprecated ``on_enemy_dmg`` global
    # is wired by the Runner to forward to the bus, so we do NOT also call
    # it directly here — that would double-fire the event. Skip the emit
    # when the shield absorbed the entire hit (amount == 0) so the damage
    # FX does not render a "0" -- the boss still flashes via ``flash`` and
    # ``last_damage_timer`` above, so the hit is visible without a number.
    if amount > 0:
        _emit("enemy_dmg", enemy.x, enemy.y, amount,
              is_crit=is_crit, is_boss=enemy.is_boss)
    if enemy.hp <= 0:
        enemy.hp = 0
        enemy.alive = False


def tap(ninja, enemies: list[Enemy], *, combo_mult: float, gold_mult: float,
        on_kill=None, attuned: str = "none") -> tuple[Optional[Enemy], float, bool]:
    """The player taps — deal tap_damage to the nearest enemy.

    Returns ``(target, dmg_dealt, is_crit)``: the tapped enemy (or None
    if no target was in range), the actual damage applied to the target
    (after the crit roll + combo multiplier; before the boss shield
    absorption — i.e. the raw damage the tap dealt), and whether the
    tap was a crit. The caller (``Runner.tap``) uses ``dmg_dealt`` for
    the Cleave overkill condition so the cleave fires based on the
    ACTUAL damage dealt, not a separate roll.

    ``attuned`` is the player's current Godai attunement (default "none"
    = 1x); it flows into ``_apply_damage`` so the tap respects the type
    chart.
    """
    target = nearest_enemy(enemies)
    if target is None:
        return None, 0.0, False
    mult, is_crit = ninja.roll_crit()
    dmg = ninja.tap_damage * mult * combo_mult
    _apply_damage(target, dmg, is_crit=is_crit, attuned=attuned)
    ninja.slash_anim = 0.15
    if not target.alive and on_kill is not None:
        on_kill(target)
    return target, dmg, is_crit


def tick_combat(ninja, enemies: list[Enemy], dt: float, *,
                combo_mult: float, gold_mult: float,
                auto_active: bool, on_kill=None,
                attuned: str = "none") -> None:
    """Advance one combat tick.

    ``attuned`` is the player's current Godai attunement (default "none"
    = 1x); it flows into ``_apply_damage`` so every auto-attack respects
    the type chart.
    """
    # Enemies move + attack.
    for e in enemies:
        if e.flash > 0:
            e.flash -= dt
        e.last_damage_timer -= dt
        if not e.alive:
            continue
        # Boss soft-phase scaling: derive the phase from HP each tick (no
        # new state machine, just scaling). This sets ``attack_interval``
        # (faster attacks as HP drops) and arms the shield at phase 3
        # before the boss acts. The phase transition event fires here.
        if e.is_boss:
            _update_boss_phase(e)
        dist = e.x - PARTY_X
        if dist > ENEMY_ATTACK_RANGE:
            e.x -= e.speed * dt
        else:
            e.attack_timer += dt
            # Boss attack_interval scales down as HP drops (phase derived
            # from HP above). Regular enemies use the base 1.0s interval.
            interval = e.attack_interval if e.is_boss else 1.0
            if e.attack_timer >= interval:
                e.attack_timer -= interval
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
                _apply_damage(target, dmg, is_crit=is_crit, attuned=attuned)
                if not target.alive and on_kill is not None:
                    on_kill(target)
