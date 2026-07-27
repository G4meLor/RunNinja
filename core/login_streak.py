"""Daily login streak system for Tap Ninja.

Tracks the number of consecutive real-world days the player has opened
the game and grants escalating Amber rewards.  The streak grows by one
each new calendar day the player returns; if a day is skipped the
streak resets to zero (the next login then starts a fresh streak at
day 1).

State fields (added to `GameState`):
    last_login_date : str | None   -- "YYYY-MM-DD" of the last awarded day
    login_streak   : int           -- current consecutive-day count

The module is stdlib-only (`datetime`) and side-effect-free aside from
mutating the `GameState` it is handed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from core.state import GameState


# ---------------------------------------------------------------------------
# Reward ladder.  Days not listed fall back to the previous tier's reward
# (so e.g. day 4..6 pay the day-3 reward) until the next milestone.  Day 30
# is the cap; later days keep paying 200.
# ---------------------------------------------------------------------------
STREAK_REWARDS: dict[int, int] = {
    1: 5,
    2: 8,
    3: 12,
    7: 30,
    14: 80,
    30: 200,
}


def _reward_for(streak: int) -> int:
    """Amber reward for a given streak length, using the highest applicable tier."""
    if streak <= 0:
        return 0
    reward = 0
    for day, amt in STREAK_REWARDS.items():
        if streak >= day:
            reward = amt
    return reward


def _today_str() -> str:
    return date.today().isoformat()           # "YYYY-MM-DD"


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def check_streak(state: GameState) -> tuple[int, int, bool]:
    """Inspect the streak for today and return (streak_count, reward, is_new_day).

    `is_new_day` is True when the player has not yet collected a login
    reward today.  In that case the streak is advanced (or reset if a day
    was skipped) and `reward` is the Amber to grant.  When the player has
    already collected today, `is_new_day` is False, `reward` is 0, and
    `streak_count` is the current streak (unchanged).

    This function does **not** mutate `state` — call `apply_streak` to
    record the collection once the reward has been handed out.
    """
    today = date.today()
    last = _parse_date(getattr(state, "last_login_date", None))

    if last is None:
        # First ever login: start a fresh streak at day 1.
        return 1, _reward_for(1), True

    if last == today:
        # Already collected today; no new reward, streak unchanged.
        streak = getattr(state, "login_streak", 0) or 0
        return streak, 0, False

    # A new calendar day.  Decide whether the streak continues or resets.
    if last == today - timedelta(days=1):
        streak = (getattr(state, "login_streak", 0) or 0) + 1
    else:
        # A day (or more) was skipped — start over at day 1.
        streak = 1
    return streak, _reward_for(streak), True


def apply_streak(state: GameState, reward: int) -> None:
    """Record that today's login reward has been collected.

    Updates `last_login_date` to today and bumps `login_streak` by one
    (capped at 30 for the reward ladder; the streak counter itself can
    keep climbing, but rewards plateau).  Grants the Amber reward to
    `state.amber` and `state.medals` is untouched (login rewards are
    Amber-only, matching the spec).
    """
    today = _today_str()
    # Re-derive the streak the same way check_streak does so this is safe
    # to call even if the caller didn't keep the returned streak around.
    last = _parse_date(getattr(state, "last_login_date", None))
    if last is None:
        new_streak = 1
    elif last == date.today():
        # Same-day re-apply: don't double-count.
        return
    elif last == date.today() - timedelta(days=1):
        new_streak = (getattr(state, "login_streak", 0) or 0) + 1
    else:
        new_streak = 1

    state.login_streak = new_streak
    state.last_login_date = today
    if reward > 0:
        state.amber += reward
