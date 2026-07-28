"""Task 26 -- Quest variety expansion (weekly + chapter) + Lore/Bestiary Codex.

Two low-cost content additions:

  * **Quest variety** -- a ``WEEKLY_POOL`` (refresh 7d, reward medals +
    amber) and ``CHAPTER_QUESTS`` (one-time, tied to zone progression)
    added alongside the existing daily pool. Only weekly + chapter -- NOT
    6+ new quest types.

  * **Lore/Bestiary Codex** -- a ``lore`` field on ``EnemyDef`` (pure
    data, no new mechanic) + a category-tab system on the bestiary screen
    so the codex is browsable by element / bosses-only / all.

Be aware of Task 17's Heritage/token changes in ``core/quests.py`` -- the
weekly/chapter logic is ADDITIVE and does NOT modify the existing
daily/achievement/token logic.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


# ---------------------------------------------------------------------------
# Specimen tests from the task brief
# ---------------------------------------------------------------------------
def test_weekly_quests_exist():
    """WEEKLY_POOL exists and has at least one quest."""
    from data.quests import WEEKLY_POOL
    assert len(WEEKLY_POOL) >= 1


def test_bestiary_has_lore():
    """Each enemy in ZONES has a lore entry (pure data, no mechanic)."""
    from data.enemies import ZONES
    for z in ZONES:
        for e in z["enemies"]:
            assert hasattr(e, "lore") or "lore" in getattr(e, "__dict__", {})


# ---------------------------------------------------------------------------
# Weekly quest definitions
# ---------------------------------------------------------------------------
def test_weekly_pool_is_small():
    """The weekly pool is 2-3 quests -- NOT 6+ (no quest-type sprawl)."""
    from data.quests import WEEKLY_POOL
    assert 1 <= len(WEEKLY_POOL) <= 5


def test_weekly_quests_have_fields():
    """Each weekly quest has id, name, desc, target, progress_key, rewards."""
    from data.quests import WEEKLY_POOL
    for wq in WEEKLY_POOL:
        assert wq.id
        assert wq.name
        assert wq.desc
        assert wq.target > 0
        assert wq.progress_key
        assert wq.reward_medals > 0
        assert wq.reward_amber > 0


# ---------------------------------------------------------------------------
# Chapter quest definitions
# ---------------------------------------------------------------------------
def test_chapter_quests_exist():
    """CHAPTER_QUESTS exists and has at least one quest."""
    from data.quests import CHAPTER_QUESTS
    assert len(CHAPTER_QUESTS) >= 1


def test_chapter_quests_small():
    """The chapter quest list is 2-3 quests -- NOT 6+."""
    from data.quests import CHAPTER_QUESTS
    assert 1 <= len(CHAPTER_QUESTS) <= 5


def test_chapter_quests_tied_to_zone_progression():
    """Chapter quests read zone-progression keys (best_zone / bosses_killed
    / monsters_killed / total_ascensions)."""
    from data.quests import CHAPTER_QUESTS
    valid_keys = {"best_zone", "bosses_killed", "monsters_killed",
                  "total_ascensions"}
    for cq in CHAPTER_QUESTS:
        assert cq.progress_key in valid_keys, (
            f"chapter quest {cq.id} uses non-zone key {cq.progress_key!r}")


# ---------------------------------------------------------------------------
# Weekly refresh + chapter progress (core/quests.py)
# ---------------------------------------------------------------------------
def test_maybe_refresh_weeklies_creates_quests():
    """maybe_refresh_weeklies populates state.weekly_quests and sets
    weekly_refresh to now + 7d."""
    import time
    from core.state import GameState
    from core.quests import maybe_refresh_weeklies, WEEKLY_REFRESH_SECONDS
    state = GameState()
    assert state.weekly_quests == []
    maybe_refresh_weeklies(state)
    assert len(state.weekly_quests) >= 1
    # weekly_refresh is set ~7d in the future.
    assert state.weekly_refresh > time.time()
    assert abs(state.weekly_refresh - time.time() - WEEKLY_REFRESH_SECONDS) < 5


def test_maybe_refresh_weeklies_does_not_overwrite_existing():
    """If weekly_refresh is in the future, the quests are NOT refreshed."""
    import time
    from core.state import GameState
    from core.quests import maybe_refresh_weeklies
    state = GameState()
    state.weekly_quests = [{"id": "w_kill_700", "target": 700,
                           "progress": 0.0, "baseline": 0.0}]
    state.weekly_refresh = time.time() + 100000  # far future
    maybe_refresh_weeklies(state)
    # Unchanged -- the existing quests survive.
    assert len(state.weekly_quests) == 1
    assert state.weekly_quests[0]["id"] == "w_kill_700"


def test_update_weekly_progress_completes():
    """A weekly quest completes when the cumulative counter reaches the
    target above the baseline; awards medals + amber."""
    from core.state import GameState
    from core.quests import maybe_refresh_weeklies, update_weekly_progress
    state = GameState()
    # Set a baseline of 0 and kill enough to satisfy the first weekly quest.
    state.monsters_killed = 0
    maybe_refresh_weeklies(state)
    # Find the quest with the lowest target for a quick completion.
    wq_state = state.weekly_quests[0]
    from data.quests import WEEKLY_POOL
    wq = next(w for w in WEEKLY_POOL if w.id == wq_state["id"])
    # Push the cumulative counter past the target above the baseline.
    if wq.progress_key == "monsters_killed":
        state.monsters_killed = wq_state["baseline"] + wq.target
    elif wq.progress_key == "lifetime_gold":
        state.lifetime_gold = wq_state["baseline"] + wq.target
    elif wq.progress_key == "bosses_killed":
        state.bosses_killed = wq_state["baseline"] + wq.target
    elif wq.progress_key == "total_ascensions":
        state.total_ascensions = wq_state["baseline"] + wq.target
    medals_before = state.medals
    amber_before = state.amber
    completed = update_weekly_progress(state)
    assert completed, "weekly quest should complete"
    assert state.medals > medals_before
    assert state.amber > amber_before


def test_update_chapter_progress_completes():
    """A chapter quest completes when the zone-progression counter reaches
    the target; awards medals + amber. Chapter quests are one-time (no
    refresh)."""
    from core.state import GameState
    from core.quests import update_chapter_progress
    from data.quests import CHAPTER_QUESTS
    state = GameState()
    state.best_zone = 9  # satisfies any zone-based chapter quest
    state.bosses_killed = 100  # satisfies any boss-based chapter quest
    medals_before = state.medals
    amber_before = state.amber
    completed = update_chapter_progress(state)
    assert completed, "at least one chapter quest should complete"
    assert state.medals > medals_before
    assert state.amber > amber_before
    # Chapter quests are one-time: a second call awards nothing new.
    medals_after = state.medals
    amber_after = state.amber
    completed2 = update_chapter_progress(state)
    assert state.medals == medals_after
    assert state.amber == amber_after


def test_chapter_quests_initialized_on_first_call():
    """If state.chapter_quests is empty, update_chapter_progress
    initializes it from CHAPTER_QUESTS."""
    from core.state import GameState
    from core.quests import update_chapter_progress
    from data.quests import CHAPTER_QUESTS
    state = GameState()
    assert state.chapter_quests == []
    update_chapter_progress(state)
    assert len(state.chapter_quests) == len(CHAPTER_QUESTS)


# ---------------------------------------------------------------------------
# Weekly/chapter quest state fields exist on GameState
# ---------------------------------------------------------------------------
def test_state_has_weekly_and_chapter_fields():
    """GameState has weekly_quests, weekly_refresh, chapter_quests fields."""
    from core.state import GameState
    s = GameState()
    assert hasattr(s, "weekly_quests")
    assert hasattr(s, "weekly_refresh")
    assert hasattr(s, "chapter_quests")
    assert s.weekly_quests == []
    assert s.weekly_refresh == 0.0
    assert s.chapter_quests == []


def test_v2_save_seeds_weekly_chapter_fields():
    """A v2 save migrated to v3 seeds weekly_quests, weekly_refresh,
    chapter_quests with defaults."""
    from core.state import GameState, _migrate
    v2_dict = {
        "save_version": 2, "gold": 100.0, "elixir": 1,
        "skill_tree": [], "achievements": [], "pets": {},
    }
    s = GameState.from_dict(_migrate(v2_dict))
    assert s.weekly_quests == []
    assert s.weekly_refresh == 0.0
    assert s.chapter_quests == []


# ---------------------------------------------------------------------------
# Bestiary lore + category tabs
# ---------------------------------------------------------------------------
def test_bestiary_bosses_have_lore():
    """Each boss in BOSSES has a lore entry."""
    from data.enemies import BOSSES
    for bid, bdef in BOSSES.items():
        assert hasattr(bdef, "lore") or "lore" in getattr(bdef, "__dict__", {}), (
            f"boss {bid} has no lore")


def test_bestiary_screen_has_category_tabs():
    """The bestiary screen has a category-tab system (source-level guard:
    the screen class must reference a tab / category attribute)."""
    import inspect
    from ui.screen_bestiary import BestiaryScreen
    src = inspect.getsource(BestiaryScreen)
    # The screen must have tab/category logic.
    assert "tab" in src.lower() or "category" in src.lower(), (
        "BestiaryScreen has no category-tab system")


def test_bestiary_screen_draws_lore():
    """The bestiary screen renders lore text (source-level guard: the draw
    method must reference the ``lore`` field)."""
    import inspect
    from ui.screen_bestiary import BestiaryScreen
    src = inspect.getsource(BestiaryScreen)
    assert "lore" in src, (
        "BestiaryScreen.draw does not reference the lore field")


# ---------------------------------------------------------------------------
# Quests screen shows weekly + chapter quests
# ---------------------------------------------------------------------------
def test_quests_screen_shows_weekly_and_chapter():
    """The quests screen displays weekly and chapter quests (source-level
    guard: the draw method must reference WEEKLY_POOL / CHAPTER_QUESTS or
    weekly_quests / chapter_quests)."""
    import inspect
    from ui.screen_quests import QuestsScreen
    src = inspect.getsource(QuestsScreen)
    assert "weekly" in src.lower() or "WEEKLY" in src, (
        "QuestsScreen does not display weekly quests")
    assert "chapter" in src.lower() or "CHAPTER" in src, (
        "QuestsScreen does not display chapter quests")


# ---------------------------------------------------------------------------
# Task 17 Heritage/token changes are preserved (regression guard)
# ---------------------------------------------------------------------------
def test_daily_quests_and_tokens_still_work():
    """Task 17's daily quest + token logic is preserved -- completing a
    daily quest still awards a token."""
    from core.state import GameState
    from core.quests import update_daily_progress
    state = GameState()
    state.daily_quests = [
        {"id": "q_kill_100", "target": 100, "progress": 0.0},
    ]
    state.kills_today = 100
    completed = update_daily_progress(state)
    assert completed
    assert sum(state.tokens.values()) > 0


def test_achievements_still_work():
    """Task 17's achievement logic is preserved."""
    from core.state import GameState
    from core.quests import check_achievements
    state = GameState()
    state.monsters_killed = 1
    newly = check_achievements(state)
    assert len(newly) >= 1
    assert "first_blood" in state.achievements
