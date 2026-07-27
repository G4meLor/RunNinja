"""Offline progress simulation for Tap Ninja.

When the player closes the game and returns, compute what their
buildings + kills would have earned.  Capped at 8h.  Away-income
multipliers apply.
"""
from __future__ import annotations

import time

import config as cfg
from data import enemies as e
from core.state import GameState
from core.bonuses import aggregate_bonuses
from core.game_economy import total_gps, _upgrade_pct


OFFLINE_CAP_SECONDS = 8 * 3600
OFFLINE_EFFICIENCY = 0.6     # offline runs at 60% of online rate


def compute(state: GameState) -> dict:
    now = time.time()
    if state.last_saved <= 0:
        state.last_saved = now
        return _empty()
    elapsed = now - state.last_saved
    if elapsed < 60:
        return _empty()
    elapsed = min(elapsed, OFFLINE_CAP_SECONDS)
    # Mark the baseline consumed so the report can't be double-collected by
    # switching screens (the welcome modal is only re-shown on real loads).
    state.last_saved = now

    evo = aggregate_bonuses(state)
    away_mult = 1.0 + evo.get("away_pct", 0.0) + _upgrade_pct(state, "away_income")
    gps = total_gps(state) * away_mult * OFFLINE_EFFICIENCY
    gold_from_buildings = gps * elapsed

    # Kill-based gold: estimate kills at current zone rate.
    zone = e.zone_by_index(state.zone_index)
    pool = zone["enemies"]
    avg_gold = sum(cfg.ZONE_GOLD_BASE * (cfg.ZONE_GOLD_GROWTH ** state.zone_index)
                   * en.gold_mult for en in pool) / len(pool)
    density = evo.get("density_pct", 0.0) + _upgrade_pct(state, "enemy_density")
    base_interval = max(cfg.SPAWN_INTERVAL_MIN,
                        cfg.SPAWN_INTERVAL * (cfg.SPAWN_INTERVAL_MIN / cfg.SPAWN_INTERVAL)
                        ** min(1.0, state.zone_index / 8.0))
    interval = base_interval * (1.0 - min(0.8, density))
    kills = int((elapsed / max(cfg.SPAWN_INTERVAL_MIN, interval)) * OFFLINE_EFFICIENCY)
    gold_from_kills = kills * avg_gold * (1.0 + evo.get("gold_pct", 0.0))

    total_gold = gold_from_buildings + gold_from_kills
    if total_gold <= 0:
        return _empty()

    return {
        "seconds": int(elapsed),
        "gold": total_gold,
        "kills": kills,
        "applied": True,
    }


def apply(state: GameState, report: dict) -> None:
    if not report.get("applied"):
        return
    state.gold += report["gold"]
    state.lifetime_gold += report["gold"]
    state.monsters_killed += report["kills"]


def _empty() -> dict:
    return {"seconds": 0, "gold": 0, "kills": 0, "applied": False}


def format_duration(seconds: int) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"
