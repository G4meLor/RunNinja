"""Offline progress simulation for Tap Ninja.

When the player closes the game and returns, compute what their
buildings + kills would have earned.  Capped at 8h.  Away-income
multipliers apply.

Away Mastery (Task 18) boosts offline gold via the ``away_pct`` key, but
``compute`` caps the total offline earnings strictly below
active+boosted earnings (``active_per_sec * AWAY_CAP``) so a maxed Away
Mastery never makes idling better than playing actively.
"""
from __future__ import annotations

import math
import time

import config as cfg
from data import enemies as e
from core.state import GameState
from core.bonuses import aggregate_bonuses
from core.game_economy import total_gps, _upgrade_pct


OFFLINE_CAP_SECONDS = 8 * 3600
OFFLINE_EFFICIENCY = 0.6     # offline runs at 60% of online rate
# Away Mastery cap: offline earnings are capped at AWAY_CAP of
# active+boosted earnings, so a maxed Away Mastery (or any stacked
# away_pct source) keeps offline growth meaningful but strictly below
# what the player would earn playing actively with their current combo
# + gold multipliers. AWAY_CAP < 1.0 so the cap is always strict.
AWAY_CAP = 0.9


def compute(state: GameState) -> dict:
    now = time.time()
    if state.last_saved <= 0:
        state.last_saved = now
        return _empty()
    elapsed = now - state.last_saved
    if elapsed < 60:
        return _empty()
    elapsed = min(elapsed, OFFLINE_CAP_SECONDS)
    # Truncate to whole seconds once early: the report's ``seconds`` field
    # is ``int(elapsed)``, and the Away Mastery cap below is enforced
    # against the SAME truncated elapsed so ``gold / seconds`` cannot
    # drift above the cap (the uncapped gold was computed against the
    # full-precision elapsed; truncating here keeps the cap consistent
    # with the reported seconds).
    elapsed = float(int(elapsed))
    # Mark the baseline consumed so the report can't be double-collected by
    # switching screens (the welcome modal is only re-shown on real loads).
    state.last_saved = now

    evo = aggregate_bonuses(state)
    # Away Mastery cap (Task 18): cap the total offline earnings strictly
    # below active+boosted earnings. ``away_pct`` (from the Epic Research
    # Away Mastery node + the elixir skill tree's ``eco_away1`` node + the
    # ``away_income`` run upgrade) can stack high enough that the
    # uncapped offline gold would exceed what the player would earn
    # playing actively with their current combo + gold multipliers. The
    # cap enforces ``offline_per_sec <= active_per_sec * AWAY_CAP`` where
    # AWAY_CAP < 1.0, so offline stays meaningful (the boost is real) but
    # strictly below active -- idling is never better than playing.
    active = active_per_sec(state)
    cap = active * AWAY_CAP * elapsed

    away_mult = 1.0 + evo.get("away_pct", 0.0) + _upgrade_pct(state, "away_income")
    gps = total_gps(state) * away_mult * OFFLINE_EFFICIENCY
    gold_from_buildings = gps * elapsed

    # Kill-based gold: estimate kills at current zone rate. The zone
    # scales by the in-cycle zone (zone_index % 9) times the cycle
    # multiplier (CYCLE_GOLD_MULT ** cycle), mirroring World.zone_gold.
    zone = e.zone_by_index(state.zone_index)
    pool = zone["enemies"]
    cycle = state.zone_index // 9
    in_cycle = state.zone_index % 9
    avg_gold = sum(cfg.ZONE_GOLD_BASE * (cfg.ZONE_GOLD_GROWTH ** in_cycle)
                   * (cfg.CYCLE_GOLD_MULT ** cycle)
                   * en.gold_mult for en in pool) / len(pool)
    density = evo.get("density_pct", 0.0) + _upgrade_pct(state, "enemy_density")
    base_interval = max(cfg.SPAWN_INTERVAL_MIN,
                        cfg.SPAWN_INTERVAL * (cfg.SPAWN_INTERVAL_MIN / cfg.SPAWN_INTERVAL)
                        ** min(1.0, state.zone_index / 8.0))
    interval = base_interval * (1.0 - min(0.8, density))
    kills = int((elapsed / max(cfg.SPAWN_INTERVAL_MIN, interval)) * OFFLINE_EFFICIENCY)
    gold_from_kills = kills * avg_gold * (1.0 + evo.get("gold_pct", 0.0)
                                           + evo.get("coin_token_pct", 0.0))

    uncapped = gold_from_buildings + gold_from_kills
    if uncapped <= 0:
        return _empty()

    # Apply the Away Mastery cap. The cap is the active+boosted rate
    # times AWAY_CAP (< 1.0) times the elapsed time -- strictly below
    # what the player would earn playing actively. The cap is a guard
    # against runaway away_pct stacking; when active earnings are 0 (a
    # fresh state with no buildings / zone), fall back to the uncapped
    # value so Away Mastery still does *something* for a player who has
    # the node but no active income yet.
    if active > 0 and uncapped > cap:
        total_gold = cap
    else:
        total_gold = uncapped
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


def active_per_sec(state: GameState) -> float:
    """Active+boosted gold per second the player would earn playing now.

    The cap reference for the Away Mastery cap in ``compute``. This is the
    player's current active earnings rate: building gps + kill gold per
    second, both scaled by the player's current combo multiplier + gold
    multiplier (the "boosted" part of "active+boosted"). It mirrors the
    runner's per-tick gold award: ``total_gps(state)`` for buildings and
    an estimated kill rate (one kill per spawn interval) times
    ``avg_gold * combo_m * gold_m`` for kills.

    The combo + gold multipliers are the SAME ones the runner uses
    (``combo_mult`` from ``engine.runner`` + ``gold_mult`` from
    ``engine.runner``), computed here without importing the runner (to
    avoid a circular import). The combo multiplier is the asymptotic
    ``1 + (COMBO_MULT_CAP - 1) * (1 - exp(-c / tau))`` where
    ``tau = max(5.0, COMBO_TAU - combo_step_upgrade)`` -- INCLUDING the
    ``combo_step`` run upgrade (the same one the runner's
    ``combo_mult`` applies), so the cap accurately reflects the active
    rate with the player's current combo ramp. The gold multiplier is
    the flat ``1 + gold_pct + godai_fire + gold_drop +
    coin_token_pct``. The combo multiplier is capped at
    ``COMBO_MULT_CAP`` (3.0) by construction, so the active reference is
    bounded -- the cap is a real cap, not a moving target.
    """
    evo = aggregate_bonuses(state)
    # Building gps (the same value the runner awards each tick).
    gps = total_gps(state)
    # Kill gold per second: one kill per spawn interval at the current
    # zone + density, times avg_gold * combo_m * gold_m.
    zone = e.zone_by_index(state.zone_index)
    pool = zone["enemies"]
    cycle = state.zone_index // 9
    in_cycle = state.zone_index % 9
    avg_gold = sum(cfg.ZONE_GOLD_BASE * (cfg.ZONE_GOLD_GROWTH ** in_cycle)
                   * (cfg.CYCLE_GOLD_MULT ** cycle)
                   * en.gold_mult for en in pool) / len(pool)
    density = evo.get("density_pct", 0.0) + _upgrade_pct(state, "enemy_density")
    base_interval = max(cfg.SPAWN_INTERVAL_MIN,
                        cfg.SPAWN_INTERVAL * (cfg.SPAWN_INTERVAL_MIN / cfg.SPAWN_INTERVAL)
                        ** min(1.0, state.zone_index / 8.0))
    interval = base_interval * (1.0 - min(0.8, density))
    kills_per_sec = 1.0 / max(cfg.SPAWN_INTERVAL_MIN, interval)
    # Combo multiplier (mirrors engine.runner.Runner.combo_mult, capped
    # at COMBO_MULT_CAP by construction -- the asymptotic curve can never
    # exceed the cap). ``tau`` includes the ``combo_step`` run upgrade
    # (the same one the runner applies: ``COMBO_TAU - combo_step``,
    # floored at 5.0) so the cap accurately reflects the active rate with
    # the player's current combo ramp. The ``_upgrade_pct`` helper is the
    # same one ``core.game_economy`` exposes (and the runner's
    # ``_upgrade_val`` is just an alias for it).
    from engine.runner import COMBO_MULT_CAP
    c = state.combo
    # Task 22: include the combo_step_pct skill-tree bonus (the same one
    # the runner applies) so the offline cap mirrors the active combo
    # ramp. The bonus is permanent (skill-tree); the run upgrade resets.
    tau = max(5.0, cfg.COMBO_TAU - _upgrade_pct(state, "combo_step")
              - evo.get("combo_step_pct", 0.0) * cfg.COMBO_TAU)
    combo_m = 1.0 + (COMBO_MULT_CAP - 1.0) * (1.0 - math.exp(-c / tau))
    # Gold multiplier (mirrors engine.runner.Runner.gold_mult).
    gold_m = (1.0 + evo.get("gold_pct", 0.0) + evo.get("godai_fire", 0.0)
              + _upgrade_pct(state, "gold_drop")
              + evo.get("coin_token_pct", 0.0))
    gold_from_kills_per_sec = kills_per_sec * avg_gold * combo_m * gold_m
    return gps + gold_from_kills_per_sec


def format_duration(seconds: int) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"
