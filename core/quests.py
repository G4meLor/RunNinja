"""Quest tracking: daily quests + achievements.

Daily quests refresh every 24h (real time) and reward Medals + Amber.
Achievements are checked each tick and reward Amber + medals.
"""
from __future__ import annotations

import time
import random

from data import quests as q
from core.state import GameState


DAILY_REFRESH_SECONDS = 24 * 3600


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
    """Update each daily quest's progress; return newly-completed quests."""
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
            completed.append({"id": dq.id, "name": dq.name,
                              "medals": dq.reward_medals, "amber": dq.reward_amber})
    return completed


def check_achievements(state: GameState) -> list:
    """Unlock newly-satisfied achievements; return the newly-unlocked list."""
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
