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
    """Compute the ninja's effective combat stats from state.

    Stacking order (documented in ``config.MAX_TOTAL_DAMAGE_MULT``):
      base
        * tier_mult          (ascension tier stat_mult, 1.6 ** tier)
        * run upgrades       (tap_power, tap_mult, auto_attack, ...)
        * evo                (skill tree + pets + dojo + heritage, additive pct)
        * godai_element      (Godai Elements branch, %-on-base in each stat)
      then clamped per-stat.

    The dojo + heritage buffs are ADDITIVE pct on the base stat, layered
    alongside the skill-tree/pet bonuses in ``evo``. Each dojo buffs its
    mapped stat (tap for iaijutsu, auto for kage_bunshin, crit_dmg for
    shikigami, attack_speed for kusari_gama); Earth heritage buffs
    max_hp (utility/defense flavor). The buffs compose cleanly with the
    Godai element multipliers (which are %-on-base in their own stats)
    because each layer touches its own stat -- no interference.
    """
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

    # ---- Build specialization (Dojos) + Heritage ----
    # Each dojo adds a flat pct to its mapped stat. The buffs are
    # ADDITIVE on the base stat (never a multiplier on a multiplier), so
    # they compose cleanly with the Godai element multipliers above
    # (which are %-on-base in their own stats). Specialization is NOT
    # mutually-exclusive: a generalist (no dojo) is viable; choosing a
    # dojo only ADDS to the chosen stat, never reduces another.
    dojo_kage_bunshin = evo.get("dojo_kage_bunshin", 0.0)  # idle -> auto
    dojo_iaijutsu = evo.get("dojo_iaijutsu", 0.0)          # tap-burst -> tap
    dojo_shikigami = evo.get("dojo_shikigami", 0.0)        # summon -> crit_dmg
    dojo_kusari_gama = evo.get("dojo_kusari_gama", 0.0)    # multi-hit -> attack_speed
    auto_damage *= (1.0 + dojo_kage_bunshin)
    tap_damage *= (1.0 + dojo_iaijutsu)
    crit_dmg += dojo_shikigami  # crit_dmg is a flat multiplier (1.5 + bonuses), so add flat
    attack_speed *= (1.0 + dojo_kusari_gama * 0.5)  # mirror the speed_pct 0.5 factor

    # Heritage passives: each collected heritage adds a small permanent
    # buff to its mapped stat. Same mapping as the dojos, plus Earth
    # (the generalist's utility/defense heritage) which buffs max_hp.
    heritage_kage_bunshin = evo.get("heritage_kage_bunshin", 0.0)
    heritage_iaijutsu = evo.get("heritage_iaijutsu", 0.0)
    heritage_shikigami = evo.get("heritage_shikigami", 0.0)
    heritage_kusari_gama = evo.get("heritage_kusari_gama", 0.0)
    heritage_earth = evo.get("heritage_earth", 0.0)
    auto_damage *= (1.0 + heritage_kage_bunshin)
    tap_damage *= (1.0 + heritage_iaijutsu)
    crit_dmg += heritage_shikigami
    attack_speed *= (1.0 + heritage_kusari_gama * 0.5)
    max_hp *= (1.0 + heritage_earth)

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
    """The current ascension tier's stat multiplier (1.0 at Mortal).

    ``1.6 ** tier`` -- the exponential tier ladder. The 7 ``ASCEND_TIERS``
    names (Mortal, Awakened, ...) remain as labels for the ascend UI; the
    flat ``stat_mult`` column they used to carry is replaced by this
    formula (steeper at high tiers so the post-ascension economy keeps
    pace with the cycling zones).
    """
    return 1.6 ** state.ascend_tier


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
