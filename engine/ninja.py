"""The ninja — the player's single hero on the road.

Unlike the old party system, Tap Ninja has one ninja whose stats come
from the run upgrades + skill tree + pets.  The ninja auto-attacks the
nearest enemy; the player can also tap to deal instant damage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import config as cfg
from core.state import GameState
from core.bonuses import aggregate_bonuses
from data import skill_tree as st
from utils import rng


@dataclass
class Ninja:
    hp: float = 100.0
    max_hp: float = 100.0
    x: float = 180.0
    y: float = 0.0
    attack_timer: float = 0.0
    alive: bool = True
    bob: float = 0.0
    slash_anim: float = 0.0       # slash animation timer
    last_damage: float = 0.0
    last_damage_timer: float = 0.0

    # Cached effective stats (recomputed by the runner each tick).
    tap_damage: float = 10.0
    auto_damage: float = 8.0
    attack_speed: float = 1.0    # attacks per second
    crit_chance: float = 0.05
    crit_dmg: float = 1.5

    def take_damage(self, raw: float) -> float:
        # Defense reduces incoming damage (flat, then %-style floor).
        dmg = max(0.0, raw - getattr(self, "defense", 0.0))
        self.hp -= dmg
        self.last_damage = dmg
        self.last_damage_timer = 0.6
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return dmg

    def heal(self, amount: float) -> None:
        self.hp = min(self.max_hp, self.hp + amount)

    def roll_crit(self) -> tuple[float, bool]:
        is_crit = rng().random() < self.crit_chance
        return (self.crit_dmg if is_crit else 1.0), is_crit


def compute_ninja_stats(state: GameState) -> dict:
    """Compute the ninja's effective combat stats from state."""
    evo = aggregate_bonuses(state)
    # Ascension tier multiplier (the prestige ladder's stat_mult).
    tier_mult = _ascend_tier_mult(state)
    # Base values from run upgrades, scaled by the ascension tier.
    tap_base = (10.0 + _upgrade_value(state, "tap_power")) * tier_mult
    tap_mult = 1.0 + _upgrade_value(state, "tap_mult") + evo.get("tap_pct", 0.0)
    tap_damage = tap_base * tap_mult

    auto_base = (8.0 + _upgrade_value(state, "auto_attack")) * tier_mult
    auto_mult = 1.0 + evo.get("atk_pct", 0.0)
    auto_damage = auto_base * auto_mult

    attack_speed = 1.0 + evo.get("speed_pct", 0.0) * 0.5
    crit_chance = 0.05 + _upgrade_value(state, "crit_chance") + evo.get("crit_pct", 0.0)
    crit_dmg = 1.5 + _upgrade_value(state, "crit_dmg") + evo.get("crit_dmg_pct", 0.0)

    # Max HP: base + vitality upgrade, × godai_water, × ascension tier.
    max_hp = (100.0 + _upgrade_value(state, "vitality")) * (1.0 + evo.get("godai_water", 0.0)) * tier_mult
    # Defense: reduces incoming damage (run upgrade + godai_water).
    defense = _upgrade_value(state, "defense")

    return {
        "tap_damage": max(1.0, tap_damage),
        "auto_damage": max(1.0, auto_damage),
        "attack_speed": max(0.2, attack_speed),
        "crit_chance": max(0.0, min(0.95, crit_chance)),
        "crit_dmg": max(1.0, crit_dmg),
        "max_hp": max(1.0, max_hp),
        "defense": max(0.0, defense),
    }


def _ascend_tier_mult(state: GameState) -> float:
    """The current ascension tier's stat multiplier (1.0 at Mortal)."""
    import config as cfg
    i = min(state.ascend_tier, len(cfg.ASCEND_TIERS) - 1)
    return cfg.ASCEND_TIERS[i][1]


def _upgrade_value(state: GameState, key: str) -> float:
    """Total effect of a run upgrade at its current level."""
    if state.upgrade_level(key) <= 0:
        return 0.0
    base = cfg.UPGRADE_BASE_EFFECT.get(key, 0.0)
    growth = cfg.UPGRADE_EFFECT_GROWTH.get(key, 1.0)
    lvl = state.upgrade_level(key)
    return base * (growth ** (lvl - 1)) * lvl


def make_ninja(state: GameState) -> Ninja:
    s = compute_ninja_stats(state)
    n = Ninja(
        hp=s["max_hp"], max_hp=s["max_hp"],
        tap_damage=s["tap_damage"], auto_damage=s["auto_damage"],
        attack_speed=s["attack_speed"], crit_chance=s["crit_chance"],
        crit_dmg=s["crit_dmg"],
    )
    n.defense = s.get("defense", 0.0)  # type: ignore[attr-defined]
    return n
