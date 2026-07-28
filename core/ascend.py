"""Ascension: the prestige loop for Tap Ninja.

Ascending resets gold, run upgrades, zone, combo, and energy, but grants
Elixir based on the gold earned this run.  **Buildings persist through
ascension** (scaled by the tier stat_mult in ``total_gps`` so they stay
relevant) -- only gold and run upgrades reset.  Elixir is spent on the
permanent skill tree.  Requires reaching a minimum zone (this run),
reducible by the "ascend_cost_pct" bonus.
"""
from __future__ import annotations

import math

import config as cfg
from core.state import GameState
from core.bonuses import aggregate_bonuses


def ascend_requirement(state: GameState) -> int:
    """Minimum zone index (this run) required to ascend."""
    base = 5
    evo = aggregate_bonuses(state)
    reduction = evo.get("ascend_cost_pct", 0.0)
    return max(1, int(base * (1.0 - min(0.8, reduction))))


def can_ascend(state: GameState) -> bool:
    return state.zone_index >= ascend_requirement(state)


def elixir_gain(state: GameState) -> int:
    """Elixir that would be earned by ascending right now.

    Re-tuned for the persist-through-ascension economy.  Buildings now
    carry over (scaled by the tier stat_mult in ``total_gps``), so
    lifetime_gold grows faster on subsequent runs.  The diminish factor
    scales elixir-per-gold down on higher tiers so the post-ascension
    economy doesn't snowball:

        elixir = lifetime_gold * ELIXIR_RATE
                  * (1 - ELIXIR_DIMINISH * ascend_tier) * [bonuses]

    ELIXIR_RATE (cfg) is tuned so a first ascension at ~10k lifetime gold
    gives ~50 elixir (matching the Awakened soul_reward tier).  The
    diminish factor stays positive through all 7 tiers (tier 6 -> 0.40).
    """
    evo = aggregate_bonuses(state)
    mult = 1.0 + evo.get("elixir_pct", 0.0) + evo.get("godai_void", 0.0)
    # Stacking tokens (gp-permanent-scaling): elixir tokens are +1% each
    # to elixir gain. They are permanent (survive all prestige layers)
    # and sourced from daily quests + zone-boss milestones (NOT
    # achievements -- no double-counting with the Heritage passives).
    mult += evo.get("elixir_token_pct", 0.0)
    if state.lifetime_gold <= 0:
        return 0
    rate = getattr(cfg, "ELIXIR_RATE", 0.005)
    diminish = getattr(cfg, "ELIXIR_DIMINISH", 0.10)
    factor = max(0.0, 1.0 - diminish * state.ascend_tier)
    return int(math.floor(max(1, state.lifetime_gold * rate * factor) * mult))


def ascend(state: GameState) -> int:
    """Perform ascension; returns elixir gained (0 if not allowed).

    Buildings **persist** through ascension (they are not reset here);
    they are scaled by the tier stat_mult in ``total_gps`` so they stay
    relevant as the player climbs tiers.  Only gold, run upgrades, zone,
    combo, and energy reset.  The ``start_farms`` skill-tree perk
    guarantees a minimum farm count (it raises low farm counts to the
    perk value rather than overwriting a higher existing count).

    Heritage: completing a full ascension under a Dojo grants that
    dojo's heritage passive (a one-time per-dojo unlock). The generalist
    (``dojo == "none"``) grants the Earth heritage. Heritage is a set,
    so ascending twice under the same dojo doesn't duplicate the entry;
    the player can respec dojo freely between ascensions and collect all
    5 heritages (4 dojos + Earth) as the meta-goal.
    """
    if not can_ascend(state):
        return 0
    gained = elixir_gain(state)
    state.elixir += gained
    state.ascend_tier += 1
    state.total_ascensions += 1
    state.ascensions_today += 1
    # Reset run-scoped state.  Buildings persist (not reset).
    state.gold = 0.0
    state.upgrades = {}
    state.zone_index = 0
    state.zone_distance = 0.0
    state.combo = 0
    state.combo_timer = 0.0
    state.energy = state.energy_max
    state.energy_active = False
    # Ascension perk: guarantee a minimum farm count.  The "Homestead" perk
    # (start_farms) starts each ascension with N farms -- but only if the
    # player doesn't already have more (buildings persist, so a player who
    # ground farms keeps them).
    evo = aggregate_bonuses(state)
    start_farms = int(evo.get("start_farms", 0.0))
    if start_farms > 0:
        cur = state.building_level("farm")
        if cur < start_farms:
            state.buildings["farm"] = start_farms
    # Heritage: grant the dojo's heritage passive (one-time per dojo).
    # The generalist (no dojo) grants the Earth heritage -- the
    # utility/defense flavor, the 5th in the "collect all 5" meta-goal.
    if state.dojo == "none":
        state.heritage.add("earth")
    else:
        state.heritage.add(state.dojo)
    return gained


def ascend_progress(state: GameState) -> float:
    req = ascend_requirement(state)
    return min(1.0, state.zone_index / req) if req > 0 else 1.0
