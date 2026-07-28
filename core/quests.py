"""Quest tracking: daily quests + achievements.

Daily quests refresh every 24h (real time) and reward Medals + Amber.
Achievements are checked each tick and reward Amber + medals.

Token awards (gp-permanent-scaling): stacking tokens (Strike / Crit /
Coin / Elixir) are permanent +1%-per-token multipliers sourced from
daily quests + zone-boss milestones -- NOT achievements (the Heritage
passives read ``state.achievements``; tokens read ``state.tokens`` --
distinct sources, no double-counting). The acquisition rate is capped
so the +1%-per-token complements rather than replaces the exponential
zone scaling.
"""
from __future__ import annotations

import time
import random

from data import quests as q
from core.state import GameState


DAILY_REFRESH_SECONDS = 24 * 3600
# Weekly refresh (Task 26 / cnt-quest-codex): 7 days. Weekly quests read
# CUMULATIVE counters (monsters_killed, lifetime_gold, bosses_killed,
# total_ascensions) -- NOT the daily-reset counters -- so the progress
# is measured as the delta from a baseline captured at refresh time.
WEEKLY_REFRESH_SECONDS = 7 * 24 * 3600

# Stacking tokens (gp-permanent-scaling). The four kinds map to the four
# combat/economy stats: Strike -> tap damage, Crit -> crit chance, Coin ->
# gold, Elixir -> elixir gain. Tokens are permanent (survive ALL prestige
# layers) and each is +1% (0.01) to its stat via ``_tokens_provider``.
TOKEN_KINDS = ("strike", "crit", "coin", "elixir")

# Per-quest token award weights (strike/crit/coin/elixir). Daily quests
# tend to award the kind that matches their flavor (kill quests -> strike,
# gold quests -> coin, combo/skill quests -> crit, ascend quests ->
# elixir). Boss milestones cycle through all four kinds so a boss-kill
# streak awards a mix.
_QUEST_TOKEN_KIND = {
    "q_kill_100": "strike",
    "q_kill_500": "strike",
    "q_gold_1k": "coin",
    "q_gold_100k": "coin",
    "q_combo_50": "crit",
    "q_combo_100": "crit",
    "q_skills_5": "crit",
    "q_ascend": "elixir",
    "q_firefly_20": "elixir",
}

# Boss milestone cap: award a token every Nth boss kill. The cap ensures
# the +1%-per-token complements rather than replaces the exponential
# zone scaling -- 100 boss kills yields ~100/BOSS_TOKEN_EVERY tokens, not
# 100. ``boss_number`` is 0-indexed (the first boss is boss 0); a token
# is awarded when ``boss_number % BOSS_TOKEN_EVERY == 0``.
BOSS_TOKEN_EVERY = 5


def _award_token(state: GameState, kind: str, amount: int = 1) -> None:
    """Award ``amount`` tokens of ``kind`` to ``state.tokens``.

    Tokens are permanent -- this is the ONLY mutation path for
    ``state.tokens`` (the ascension reset in ``core.ascend.ascend`` never
    touches tokens). The kind must be one of ``TOKEN_KINDS``; unknown
    kinds are ignored (forward-compatible: a future kind that hasn't been
    wired into the provider yet is still stored, so the player doesn't
    lose the token when the provider catches up).
    """
    if amount <= 0:
        return
    if kind not in TOKEN_KINDS:
        return
    state.tokens[kind] = state.tokens.get(kind, 0) + amount


def award_boss_token(state: GameState, boss_number: int) -> None:
    """Award a token for a zone-boss kill at a capped milestone rate.

    ``boss_number`` is the 0-indexed boss count (the first boss is 0).
    A token is awarded every ``BOSS_TOKEN_EVERY`` kills (1/5/10/15/...),
    cycling through ``TOKEN_KINDS`` so a boss-kill streak awards a mix
    of strike/crit/coin/elixir tokens. The cap ensures the +1%-per-token
    complements rather than replaces the exponential zone scaling: 100
    boss kills yields ~20 tokens, not 100.
    """
    if boss_number < 0:
        return
    if boss_number % BOSS_TOKEN_EVERY != 0:
        return
    kind = TOKEN_KINDS[boss_number // BOSS_TOKEN_EVERY % len(TOKEN_KINDS)]
    _award_token(state, kind)


def _award_daily_quest_token(state: GameState, quest_id: str) -> None:
    """Award a token for completing a daily quest.

    Each daily-quest completion awards one token of the kind that matches
    the quest's flavor (kill -> strike, gold -> coin, combo/skill -> crit,
    ascend/firefly -> elixir). Unknown quest ids award a random kind
    (forward-compatible: a new quest not yet in the map still awards a
    token). The award is ONE token per completion (the cap) -- the daily
    refresh + the 24h cooldown are the natural rate limit.
    """
    kind = _QUEST_TOKEN_KIND.get(quest_id)
    if kind is None:
        kind = random.choice(TOKEN_KINDS)
    _award_token(state, kind)


def maybe_refresh_dailies(state: GameState) -> None:
    """Refresh the daily quest set if 24h have passed."""
    now = time.time()
    if state.daily_refresh <= 0 or now >= state.daily_refresh:
        # Pick 3 random quests from the pool.
        pool = list(q.DAILY_POOL)
        random.shuffle(pool)
        chosen = pool[:3]
        state.daily_quests = [
            {"id": dq.id, "target": dq.target, "progress": 0.0}
            for dq in chosen
        ]
        state.daily_refresh = now + DAILY_REFRESH_SECONDS
        # Reset daily counters.
        state.gold_earned_today = 0.0
        state.best_combo_today = 0
        state.skills_used_today = 0
        state.ascensions_today = 0
        state.fireflies_today = 0
        state.kills_today = 0


def daily_progress(state: GameState, key: str) -> float:
    """Current progress value for a daily quest keyed by progress_key."""
    if key == "kills_today":
        return state.kills_today
    if key == "monsters_killed":   # legacy key — falls back to today's kills
        return state.kills_today
    if key == "gold_earned_today":
        return state.gold_earned_today
    if key == "best_combo_today":
        return state.best_combo_today
    if key == "skills_used_today":
        return state.skills_used_today
    if key == "ascensions_today":
        return state.ascensions_today
    if key == "fireflies_today":
        return state.fireflies_today
    return 0.0


def update_daily_progress(state: GameState) -> list[dict]:
    """Update each daily quest's progress; return newly-completed quests.

    Each newly-completed daily quest awards Medals + Amber AND a stacking
    token (gp-permanent-scaling). Tokens come from daily quests + zone-boss
    milestones -- NOT achievements (the Heritage passives read
    ``state.achievements``; tokens read ``state.tokens`` -- distinct
    sources, no double-counting). The token kind matches the quest's
    flavor (kill -> strike, gold -> coin, combo/skill -> crit, ascend ->
    elixir); the award is ONE token per completion (the cap).
    """
    completed = []
    for dq_state in state.daily_quests:
        dq = next((d for d in q.DAILY_POOL if d.id == dq_state["id"]), None)
        if dq is None:
            continue
        progress = daily_progress(state, dq.progress_key)
        dq_state["progress"] = min(dq.target, progress)
        if dq_state["progress"] >= dq.target and not dq_state.get("claimed"):
            dq_state["claimed"] = True
            state.medals += dq.reward_medals
            state.amber += dq.reward_amber
            _award_daily_quest_token(state, dq.id)
            completed.append({"id": dq.id, "name": dq.name,
                              "medals": dq.reward_medals, "amber": dq.reward_amber})
    return completed


def check_achievements(state: GameState) -> list:
    """Unlock newly-satisfied achievements; return the newly-unlocked list.

    Achievements award Amber + Medals (the one-shot payout) and are
    converted to permanent cumulative multipliers by the Heritage
    passives provider (``_heritage_achievements_provider`` in
    ``core.bonuses``, which reads ``len(state.achievements)``).
    Achievements do NOT award tokens -- tokens come from daily quests +
    zone-boss milestones only (distinct sources, no double-counting).
    """
    newly = []
    for a in q.ACHIEVEMENTS:
        if a.id in state.achievements:
            continue
        try:
            if a.check(state):
                state.achievements.add(a.id)
                state.amber += a.reward_amber
                state.medals += a.reward_medals
                newly.append(a)
        except Exception:
            continue
    return newly


# ---------------------------------------------------------------------------
# Weekly quests (Task 26 / cnt-quest-codex)
# ---------------------------------------------------------------------------
# Weekly quests read CUMULATIVE counters (monsters_killed, lifetime_gold,
# bosses_killed, total_ascensions) -- NOT the daily-reset counters. The
# progress is the delta from a ``baseline`` captured at refresh time, so
# the quest tracks "this week's" progress, not the lifetime total. The
# refresh is 7d; the reward is a bigger Medals + Amber payout than a
# daily quest. The quest shape (``DailyQuest``) is reused so the UI + core
# logic share one quest shape; the only difference is the longer refresh
# + the cumulative progress key.
#
# This block is ADDITIVE -- it does NOT touch the daily / achievement /
# token logic above (Task 17's Heritage/token changes are preserved).

def _weekly_progress(state: GameState, key: str, baseline: float) -> float:
    """Current progress for a weekly quest: the delta from the baseline.

    Weekly quests read CUMULATIVE counters (not the daily-reset ones).
    The ``baseline`` is the counter value at refresh time, so the progress
    is "this week's" gain, not the lifetime total.
    """
    if key == "monsters_killed":
        return max(0.0, state.monsters_killed - baseline)
    if key == "lifetime_gold":
        return max(0.0, state.lifetime_gold - baseline)
    if key == "bosses_killed":
        return max(0.0, state.bosses_killed - baseline)
    if key == "total_ascensions":
        return max(0.0, state.total_ascensions - baseline)
    return 0.0


def maybe_refresh_weeklies(state: GameState) -> None:
    """Refresh the weekly quest set if 7d have passed (or no set exists).

    Picks 2 random quests from ``WEEKLY_POOL`` and captures the current
    cumulative-counter value as each quest's ``baseline`` so the progress
    tracks this week's gain. Does NOT touch the daily / achievement /
    token logic (Task 17's changes are preserved).
    """
    now = time.time()
    if state.weekly_refresh > 0 and now < state.weekly_refresh:
        return  # not yet time to refresh
    pool = list(q.WEEKLY_POOL)
    random.shuffle(pool)
    chosen = pool[:2]
    state.weekly_quests = [
        {"id": wq.id, "target": wq.target, "progress": 0.0,
         "baseline": _weekly_baseline(state, wq.progress_key)}
        for wq in chosen
    ]
    state.weekly_refresh = now + WEEKLY_REFRESH_SECONDS


def _weekly_baseline(state: GameState, key: str) -> float:
    """The current cumulative-counter value for a weekly quest key.

    Captured at refresh time so the weekly progress tracks the delta from
    this baseline (``progress = current - baseline``).
    """
    if key == "monsters_killed":
        return float(state.monsters_killed)
    if key == "lifetime_gold":
        return float(state.lifetime_gold)
    if key == "bosses_killed":
        return float(state.bosses_killed)
    if key == "total_ascensions":
        return float(state.total_ascensions)
    return 0.0


def update_weekly_progress(state: GameState) -> list[dict]:
    """Update each weekly quest's progress; return newly-completed quests.

    Each newly-completed weekly quest awards Medals + Amber (a bigger
    payout than a daily quest). Weekly quests do NOT award tokens (tokens
    come from daily quests + zone-boss milestones only -- distinct
    sources, no double-counting with the Heritage passives).
    """
    completed = []
    for wq_state in state.weekly_quests:
        wq = next((w for w in q.WEEKLY_POOL if w.id == wq_state["id"]), None)
        if wq is None:
            continue
        baseline = wq_state.get("baseline", 0.0)
        progress = _weekly_progress(state, wq.progress_key, baseline)
        wq_state["progress"] = min(wq.target, progress)
        if (wq_state["progress"] >= wq.target
                and not wq_state.get("claimed")):
            wq_state["claimed"] = True
            state.medals += wq.reward_medals
            state.amber += wq.reward_amber
            completed.append({"id": wq.id, "name": wq.name,
                              "medals": wq.reward_medals,
                              "amber": wq.reward_amber})
    return completed


# ---------------------------------------------------------------------------
# Chapter quests (Task 26 / cnt-quest-codex)
# ---------------------------------------------------------------------------
# Chapter quests are one-time milestones tied to zone progression. Unlike
# daily/weekly quests, they do NOT refresh -- once claimed, they stay
# claimed. The ``progress_key`` reads a cumulative state counter
# (best_zone / bosses_killed / monsters_killed / total_ascensions); the
# quest completes the first time the counter reaches the target. The
# reward is a one-time Medals + Amber payout.
#
# ``state.chapter_quests`` is initialized lazily on the first
# ``update_chapter_progress`` call (so a new player starts with the full
# chapter list, not an empty one). This block is ADDITIVE -- it does NOT
# touch the daily / achievement / token logic above.

def _chapter_progress(state: GameState, key: str) -> float:
    """Current progress for a chapter quest (a cumulative counter)."""
    if key == "best_zone":
        return float(state.best_zone)
    if key == "bosses_killed":
        return float(state.bosses_killed)
    if key == "monsters_killed":
        return float(state.monsters_killed)
    if key == "total_ascensions":
        return float(state.total_ascensions)
    return 0.0


def _init_chapter_quests(state: GameState) -> None:
    """Initialize ``state.chapter_quests`` from ``CHAPTER_QUESTS`` if empty.

    Idempotent: if the list is already populated, this is a no-op.
    """
    if state.chapter_quests:
        return
    state.chapter_quests = [
        {"id": cq.id, "target": cq.target, "progress": 0.0,
         "claimed": False}
        for cq in q.CHAPTER_QUESTS
    ]


def update_chapter_progress(state: GameState) -> list[dict]:
    """Update each chapter quest's progress; return newly-completed quests.

    Chapter quests are one-time: once claimed, they stay claimed (no
    refresh). The progress reads a cumulative state counter
    (``best_zone`` / ``bosses_killed`` / ``monsters_killed`` /
    ``total_ascensions``); the quest completes the first time the counter
    reaches the target. The reward is a one-time Medals + Amber payout.
    Chapter quests do NOT award tokens (tokens come from daily quests +
    zone-boss milestones only).
    """
    _init_chapter_quests(state)
    completed = []
    for cq_state in state.chapter_quests:
        cq = next((c for c in q.CHAPTER_QUESTS if c.id == cq_state["id"]),
                   None)
        if cq is None:
            continue
        if cq_state.get("claimed"):
            continue
        progress = _chapter_progress(state, cq.progress_key)
        cq_state["progress"] = min(cq.target, progress)
        if cq_state["progress"] >= cq.target:
            cq_state["claimed"] = True
            state.medals += cq.reward_medals
            state.amber += cq.reward_amber
            completed.append({"id": cq.id, "name": cq.name,
                              "medals": cq.reward_medals,
                              "amber": cq.reward_amber})
    return completed
