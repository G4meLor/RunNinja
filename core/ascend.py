"""Ascension: the prestige loop for Tap Ninja.

Ascending resets gold, buildings, run upgrades, zone, combo, and energy,
but grants Elixir based on the gold earned this run.  Elixir is spent
on the permanent skill tree.  Requires reaching a minimum zone (this
run), reducible by the "ascend_cost_pct" bonus.
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
    """Elixir that would be earned by ascending right now."""
    evo = aggregate_bonuses(state)
    mult = 1.0 + evo.get("elixir_pct", 0.0) + evo.get("godai_void", 0.0)
    if state.lifetime_gold <= 0:
        return 0
    # Floor of 50 so the first ascension always feels worthwhile; the sqrt
    # curve takes over above 2500 lifetime gold.
    return int(math.floor(max(50.0, state.lifetime_gold ** 0.5) * mult))


def ascend(state: GameState) -> int:
    """Perform ascension; returns elixir gained (0 if not allowed)."""
    if not can_ascend(state):
        return 0
    gained = elixir_gain(state)
    state.elixir += gained
    state.ascend_tier += 1
    state.total_ascensions += 1
    state.ascensions_today += 1
    # Reset run-scoped state.
    state.gold = 0.0
    state.buildings = {}
    state.upgrades = {}
    state.zone_index = 0
    state.zone_distance = 0.0
    state.combo = 0
    state.combo_timer = 0.0
    state.energy = state.energy_max
    state.energy_active = False
    # Ascension perk: start with N farms.
    evo = aggregate_bonuses(state)
    start_farms = int(evo.get("start_farms", 0.0))
    if start_farms > 0:
        state.buildings["farm"] = start_farms
    return gained


def ascend_progress(state: GameState) -> float:
    req = ascend_requirement(state)
    return min(1.0, state.zone_index / req) if req > 0 else 1.0
