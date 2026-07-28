"""Building economy: buying buildings, total gold/sec, upgrade costs.

The total passive income is the sum of each building's contribution,
scaled by global multipliers from the skill tree, pets, and run
upgrades.
"""
from __future__ import annotations

import math

import config as cfg
from data import buildings as bd
from core.state import GameState
from core.bonuses import aggregate_bonuses


def _upgrade_pct(state: GameState, key: str) -> float:
    """Total % effect of a multiplicative run upgrade (mirrors runner)."""
    if state.upgrade_level(key) <= 0:
        return 0.0
    base = cfg.UPGRADE_BASE_EFFECT.get(key, 0.0)
    growth = cfg.UPGRADE_EFFECT_GROWTH.get(key, 1.0)
    lvl = state.upgrade_level(key)
    return base * (growth ** (lvl - 1)) * lvl


def building_cost(state: GameState, bid: str, current_level: int | None = None) -> float:
    """Cost to buy the next level of building ``bid``."""
    b = bd.BY_ID[bid]
    lvl = state.building_level(bid) if current_level is None else current_level
    base = bd.building_cost(b, lvl)
    evo = aggregate_bonuses(state)
    discount = evo.get("building_cost_pct", 0.0)
    return base * (1.0 - min(0.5, discount))


def can_buy(state: GameState, bid: str, n: int = 1) -> bool:
    return state.gold >= total_cost(state, bid, n)


def total_cost(state: GameState, bid: str, n: int) -> float:
    """Total cost to buy ``n`` levels of building ``bid`` from current."""
    b = bd.BY_ID[bid]
    lvl = state.building_level(bid)
    evo = aggregate_bonuses(state)
    discount = evo.get("building_cost_pct", 0.0)
    raw = bd.total_cost(b, lvl, n)
    return raw * (1.0 - min(0.5, discount))


def buy(state: GameState, bid: str, n: int = 1) -> int:
    """Buy up to ``n`` levels of building ``bid``; returns levels bought."""
    if n <= 0:
        return 0
    b = bd.BY_ID[bid]
    # Clamp n to what the player can afford.
    if not can_buy(state, bid, n):
        n = buy_max(state, bid)
    if n <= 0:
        return 0
    cost = total_cost(state, bid, n)
    if state.gold < cost:
        return 0
    state.gold -= cost
    state.buildings[bid] = state.building_level(bid) + n
    return n


def buy_max(state: GameState, bid: str) -> int:
    """Max levels of building ``bid`` the current gold can afford."""
    b = bd.BY_ID[bid]
    lvl = state.building_level(bid)
    evo = aggregate_bonuses(state)
    discount = evo.get("building_cost_pct", 0.0)
    g = b.cost_growth
    c0 = bd.building_cost(b, lvl) * (1.0 - min(0.5, discount))
    if state.gold < c0:
        return 0
    n = math.log(state.gold * (g - 1) / c0 + 1) / math.log(g)
    return max(0, int(n))


def building_gps(state: GameState, bid: str) -> float:
    """Gold/sec contributed by building ``bid`` at its current level.

    Scaled by the ascension tier ``stat_mult`` (buildings persist through
    ascension; their output scales with the tier so they stay relevant).
    """
    b = bd.BY_ID[bid]
    return bd.building_gps(b, state.building_level(b.id)) * _tier_mult(state)


def _tier_mult(state: GameState) -> float:
    """The current ascension tier's stat multiplier (1.0 at Mortal).

    Buildings persist through ascension; their output is scaled by the
    tier ``stat_mult`` so they stay relevant as the player climbs tiers.
    Mirrors ``engine.ninja._ascend_tier_mult`` (kept local to avoid a
    cross-module dependency for a one-line lookup).
    """
    import config as cfg
    i = min(state.ascend_tier, len(cfg.ASCEND_TIERS) - 1)
    return cfg.ASCEND_TIERS[i][1]


def total_gps(state: GameState) -> float:
    """Total passive gold/sec from all buildings, with all multipliers.

    Building output is scaled by the ascension tier ``stat_mult`` so
    persisted buildings stay relevant after ascension (buildings carry
    over but the tier multiplier accelerates their gold/sec to match the
    higher-tier zone economy).
    """
    evo = aggregate_bonuses(state)
    gps_mult = (1.0 + evo.get("gps_pct", 0.0) + evo.get("godai_wind", 0.0)
                + _upgrade_pct(state, "building_output"))
    tier_mult = _tier_mult(state)
    total = 0.0
    for b in bd.BUILDINGS:
        total += bd.building_gps(b, state.building_level(b.id))
    return total * gps_mult * tier_mult


def upgrade_cost(state: GameState, key: str) -> float:
    """Cost to buy the next level of run upgrade ``key``."""
    base = cfg.UPGRADE_BASE_COST.get(key, 25)
    growth = cfg.UPGRADE_COST_GROWTH
    lvl = state.upgrade_level(key)
    evo = aggregate_bonuses(state)
    discount = evo.get("upgrade_cost_pct", 0.0)
    return base * (growth ** lvl) * (1.0 - min(0.5, discount))


def can_upgrade(state: GameState, key: str) -> bool:
    if state.upgrade_level(key) >= cfg.UPGRADE_MAX_LEVEL:
        return False
    return state.gold >= upgrade_cost(state, key)


def apply_upgrade(state: GameState, key: str) -> bool:
    if not can_upgrade(state, key):
        return False
    state.gold -= upgrade_cost(state, key)
    state.upgrades[key] = state.upgrade_level(key) + 1
    return True
