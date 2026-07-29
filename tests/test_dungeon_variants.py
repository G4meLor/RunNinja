"""Shadow Dungeon variants (Task 34 / cnt-shadow-dungeon-variants).

Story + Endless + Daily variants with a shared daily seed. The
daily-dungeon seed gives the shared daily challenge (the same for all
players on the same day). UI entry from the game screen.

The DungeonRunner takes a ``variant`` parameter ("story" | "endless" |
"daily") that affects the dungeon's difficulty/scaling:

  * Story: a fixed set of floors, a narrative progression, easier.
  * Endless: infinite floors, scaling difficulty.
  * Daily: a shared daily seed (deterministic per day), a fixed set of
    floors, a daily challenge.

The ``daily_dungeon_seed()`` function is deterministic per day (the
same for all players on the same day).
"""
import datetime

import pytest


# ---------------------------------------------------------------------------
# 1. The brief's specimen tests
# ---------------------------------------------------------------------------
def test_dungeon_variants(pygame_headless):
    """The brief's specimen test: DungeonRunner accepts a ``variant``
    parameter for each of the three variants."""
    from engine.runner import DungeonRunner
    from core.state import GameState
    for vtype in ("story", "endless", "daily"):
        state = GameState()
        state.dungeon_type = vtype
        dr = DungeonRunner(state, variant=vtype)
        assert dr is not None


def test_daily_seed_shared(pygame_headless):
    """The brief's specimen test: the daily seed is the same for all
    players on the same day (deterministic per day)."""
    from engine.runner import daily_dungeon_seed
    # The daily seed is the same for all players on the same day.
    s1 = daily_dungeon_seed()
    s2 = daily_dungeon_seed()
    assert s1 == s2


# ---------------------------------------------------------------------------
# 2. Daily seed is deterministic per day
# ---------------------------------------------------------------------------
def test_daily_seed_deterministic_per_day(pygame_headless):
    """The daily seed is deterministic: the same date produces the same
    seed. Two calls with the same date produce the same value; two
    different dates produce different values."""
    from engine.runner import daily_dungeon_seed
    today = datetime.date.today()
    # Same date -> same seed.
    assert daily_dungeon_seed(today) == daily_dungeon_seed(today)
    # Different dates -> different seeds (the seed encodes the date).
    d1 = daily_dungeon_seed(datetime.date(2026, 7, 28))
    d2 = daily_dungeon_seed(datetime.date(2026, 7, 29))
    assert d1 != d2, "daily seed did not change across days"


def test_daily_seed_is_int(pygame_headless):
    """The daily seed is an integer (it's stored in state.dungeon_seed,
    which is an int field)."""
    from engine.runner import daily_dungeon_seed
    seed = daily_dungeon_seed()
    assert isinstance(seed, int)


# ---------------------------------------------------------------------------
# 3. Variant support in DungeonRunner
# ---------------------------------------------------------------------------
def test_dungeon_runner_variant_attribute(pygame_headless):
    """DungeonRunner stores the variant on the instance (``dr.variant``).
    The variant is one of "story", "endless", "daily"."""
    from engine.runner import DungeonRunner
    from core.state import GameState
    for vtype in ("story", "endless", "daily"):
        state = GameState()
        dr = DungeonRunner(state, variant=vtype)
        assert dr.variant == vtype, (
            f"DungeonRunner(variant={vtype!r}).variant != {vtype!r}")


def test_dungeon_runner_default_variant_is_story(pygame_headless):
    """The default variant (when none is passed) is "story" (the
    narrative progression — the easiest, default dungeon)."""
    from engine.runner import DungeonRunner
    from core.state import GameState
    state = GameState()
    dr = DungeonRunner(state)
    assert dr.variant == "story"


def test_dungeon_enter_sets_dungeon_type_to_variant(pygame_headless):
    """Entering the dungeon sets state.dungeon_type to the runner's
    variant (not always "story" — the variant is the dungeon's type)."""
    from engine.runner import DungeonRunner
    from core.state import GameState
    for vtype in ("story", "endless", "daily"):
        state = GameState()
        state.medals = 100  # clear the entry gate
        dr = DungeonRunner(state, variant=vtype)
        dr.enter()
        assert state.dungeon_type == vtype, (
            f"enter() did not set dungeon_type to {vtype!r}")
        assert state.dungeon_active is True
        assert state.dungeon_floor == 1


def test_dungeon_enter_daily_sets_seed(pygame_headless):
    """Entering the Daily dungeon sets state.dungeon_seed to the daily
    seed (deterministic per day). The daily dungeon's seed is the shared
    daily challenge seed."""
    from engine.runner import DungeonRunner, daily_dungeon_seed
    from core.state import GameState
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state, variant="daily")
    dr.enter()
    assert state.dungeon_seed == daily_dungeon_seed(), (
        "enter() did not set dungeon_seed to the daily seed")


def test_dungeon_enter_non_daily_does_not_set_seed(pygame_headless):
    """Entering the Story or Endless dungeon does NOT set state.dungeon_seed
    to the daily seed (the daily seed is only for the Daily variant). The
    seed is left at 0 (the default) for Story/Endless."""
    from engine.runner import DungeonRunner, daily_dungeon_seed
    from core.state import GameState
    for vtype in ("story", "endless"):
        state = GameState()
        state.medals = 100
        dr = DungeonRunner(state, variant=vtype)
        dr.enter()
        # Story/Endless do NOT use the daily seed.
        assert state.dungeon_seed == 0, (
            f"enter(variant={vtype!r}) set dungeon_seed to the daily seed "
            "(only the Daily variant should set the seed)")


# ---------------------------------------------------------------------------
# 4. Story variant: fixed floors
# ---------------------------------------------------------------------------
def test_story_variant_has_fixed_floors(pygame_headless):
    """The Story variant has a fixed number of floors (a finite dungeon
    with a defined end). The ``STORY_FLOORS`` constant is the number of
    floors in the Story dungeon."""
    from engine.runner import DungeonRunner, STORY_FLOORS
    from core.state import GameState
    assert STORY_FLOORS > 0, "STORY_FLOORS must be > 0"
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state, variant="story")
    dr.enter()
    # The story variant has a fixed floor count (the dungeon ends after
    # STORY_FLOORS floors).
    assert dr.variant == "story"


def test_story_variant_completes(pygame_headless):
    """The Story variant completes (exits) after the fixed number of
    floors. The dungeon does NOT continue past STORY_FLOORS — when the
    boss on the last floor is killed, the dungeon exits (the player
    "cleared" the story dungeon)."""
    from engine.runner import DungeonRunner, STORY_FLOORS
    from core.state import GameState
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state, variant="story")
    dr.enter()
    # Simulate clearing each floor (kill the boss on each floor).
    for floor in range(1, STORY_FLOORS + 1):
        assert state.dungeon_active is True, (
            f"dungeon exited before floor {floor} (STORY_FLOORS={STORY_FLOORS})")
        dr.spawn_boss()
        boss = next(e for e in dr.world.enemies if e.is_boss)
        boss.alive = False
        boss.hp = 0
        dr._on_enemy_killed(boss, combo_m=1.0, gold_m=1.0, evo={})
    # After clearing all STORY_FLOORS floors, the dungeon is complete
    # (dungeon_active is False — the story dungeon ended).
    assert state.dungeon_active is False, (
        "the Story dungeon did not complete after STORY_FLOORS floors")


# ---------------------------------------------------------------------------
# 5. Endless variant: infinite floors
# ---------------------------------------------------------------------------
def test_endless_variant_infinite_floors(pygame_headless):
    """The Endless variant has infinite floors — the dungeon does NOT
    complete after any fixed number of floors. The player can descend
    indefinitely (the dungeon keeps going)."""
    from engine.runner import DungeonRunner, STORY_FLOORS
    from core.state import GameState
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state, variant="endless")
    dr.enter()
    # Simulate clearing many more floors than STORY_FLOORS — the endless
    # dungeon should still be active (it never completes).
    for floor in range(1, STORY_FLOORS + 5):
        dr.spawn_boss()
        boss = next(e for e in dr.world.enemies if e.is_boss)
        boss.alive = False
        boss.hp = 0
        dr._on_enemy_killed(boss, combo_m=1.0, gold_m=1.0, evo={})
        if not state.dungeon_active:
            break  # if it exited, we've proven the point (but it shouldn't)
    # The endless dungeon is still active (it never completes).
    assert state.dungeon_active is True, (
        "the Endless dungeon completed (it should be infinite)")
    # The floor is past STORY_FLOORS (the endless dungeon went further).
    assert state.dungeon_floor > STORY_FLOORS


# ---------------------------------------------------------------------------
# 6. Daily variant: uses the daily seed
# ---------------------------------------------------------------------------
def test_daily_variant_uses_daily_seed(pygame_headless):
    """The Daily variant uses the daily seed to deterministically pick
    the boss for each floor. The same daily seed produces the same
    sequence of bosses (the daily challenge is the same for all players
    on the same day)."""
    from engine.runner import DungeonRunner, daily_dungeon_seed
    from core.state import GameState
    # Two daily dungeons on the same day should spawn the same boss on
    # floor 1 (the seed determines the boss).
    state1 = GameState()
    state1.medals = 100
    dr1 = DungeonRunner(state1, variant="daily")
    dr1.enter()
    dr1.spawn_boss()
    boss1 = next(e for e in dr1.world.enemies if e.is_boss)

    state2 = GameState()
    state2.medals = 100
    dr2 = DungeonRunner(state2, variant="daily")
    dr2.enter()
    dr2.spawn_boss()
    boss2 = next(e for e in dr2.world.enemies if e.is_boss)

    # The same daily seed -> the same boss on the same floor.
    assert boss1.name == boss2.name, (
        "the Daily variant did not produce the same boss for the same "
        "daily seed (the daily challenge should be the same for all "
        "players on the same day)")


def test_daily_variant_has_fixed_floors(pygame_headless):
    """The Daily variant has a fixed number of floors (same as Story —
    a finite dungeon with a defined end, the daily challenge)."""
    from engine.runner import DungeonRunner, DAILY_FLOORS
    from core.state import GameState
    assert DAILY_FLOORS > 0, "DAILY_FLOORS must be > 0"
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state, variant="daily")
    dr.enter()
    assert dr.variant == "daily"


# ---------------------------------------------------------------------------
# 7. Dungeon boss pool in data/enemies.py
# ---------------------------------------------------------------------------
def test_dungeon_boss_pool_exists(pygame_headless):
    """The dungeon boss pool (``DUNGEON_BOSS_POOL``) exists in
    data/enemies.py with multiple bosses (the existing DUNGEON_BOSS +
    more). The pool is the source of bosses for the dungeon variants."""
    from data.enemies import DUNGEON_BOSS_POOL
    assert len(DUNGEON_BOSS_POOL) >= 2, (
        "DUNGEON_BOSS_POOL must have at least 2 bosses")


def test_dungeon_boss_pool_bosses_are_fire_element(pygame_headless):
    """The dungeon boss pool's bosses are fire-themed (the dungeon is
    fire-themed — the bosses use the Fire Godai element)."""
    from data.enemies import DUNGEON_BOSS_POOL
    for bdef in DUNGEON_BOSS_POOL:
        assert bdef.element == "fire", (
            f"dungeon boss {bdef.name} has element {bdef.element!r}, "
            "not 'fire'")


# ---------------------------------------------------------------------------
# 8. UI entry from the game screen
# ---------------------------------------------------------------------------
def test_game_screen_has_dungeon_button(pygame_headless):
    """The game screen has a dungeon entry button (a button that opens
    the dungeon / the dungeon variant selector)."""
    import main
    g = main.Game()
    screen = g.screens["game"]
    # The game screen has a dungeon button (an entry point).
    assert hasattr(screen, "btn_dungeon") or hasattr(screen, "dungeon_button"), (
        "the game screen has no dungeon entry button")
    # The button is a Button (has a rect + on_click).
    btn = getattr(screen, "btn_dungeon", None) or getattr(screen, "dungeon_button")
    assert hasattr(btn, "rect"), "the dungeon button is not a Button"
    assert hasattr(btn, "on_click"), "the dungeon button has no on_click"


def test_game_screen_has_variant_selector(pygame_headless):
    """The game screen has a variant selector (Story/Endless/Daily) —
    either as separate buttons or a selector that opens when the dungeon
    button is clicked. The three variants are selectable from the game
    screen."""
    import main
    g = main.Game()
    screen = g.screens["game"]
    # The game screen has variant buttons (Story/Endless/Daily) OR a
    # variant selector. The three variants are selectable.
    has_variants = (
        hasattr(screen, "dungeon_variant_buttons")
        or hasattr(screen, "btn_dungeon_story")
        or hasattr(screen, "_dungeon_variants")
        or hasattr(screen, "dungeon_variants")
    )
    assert has_variants, (
        "the game screen has no dungeon variant selector "
        "(Story/Endless/Daily)")


def test_dungeon_entry_from_game_screen_smoke(pygame_headless):
    """Smoke: clicking the dungeon entry button on the game screen
    opens the dungeon (the dungeon becomes active). The game screen's
    dungeon button calls the dungeon entry path."""
    import main
    from engine.runner import can_enter_dungeon
    g = main.Game()
    # Clear the entry gate (medals OR zone).
    g.state.medals = 100
    screen = g.screens["game"]
    # The dungeon button's on_click should open the dungeon (set
    # dungeon_active or open the variant selector). We verify by calling
    # the screen's dungeon entry method (if it has one) or by simulating
    # the variant selection.
    # The screen should have a method to enter the dungeon with a variant.
    assert hasattr(screen, "_enter_dungeon") or hasattr(screen, "enter_dungeon"), (
        "the game screen has no dungeon entry method "
        "(_enter_dungeon / enter_dungeon)")
    # Enter the story dungeon via the screen's method.
    enter_fn = getattr(screen, "_enter_dungeon", None) or getattr(screen, "enter_dungeon")
    enter_fn("story")
    assert g.state.dungeon_active is True, (
        "the game screen's _enter_dungeon did not activate the dungeon")
    assert g.state.dungeon_type == "story", (
        "the game screen's _enter_dungeon did not set dungeon_type")


# ---------------------------------------------------------------------------
# 9. State fields for dungeon variants
# ---------------------------------------------------------------------------
def test_state_has_dungeon_best_floor(pygame_headless):
    """The state has a ``dungeon_best_floor`` field (the best floor
    reached across all dungeon runs — a record-keeping field for the
    dungeon variants)."""
    from core.state import GameState
    s = GameState()
    assert hasattr(s, "dungeon_best_floor")
    assert s.dungeon_best_floor == 0  # default


def test_state_dungeon_seed_field(pygame_headless):
    """The state has a ``dungeon_seed`` field (the daily dungeon seed —
    the shared daily challenge seed). The field exists from Task 5."""
    from core.state import GameState
    s = GameState()
    assert hasattr(s, "dungeon_seed")
    assert s.dungeon_seed == 0  # default (set by daily enter)


# ---------------------------------------------------------------------------
# 10. Smoke: the dungeon variants tick without error
# ---------------------------------------------------------------------------
def test_dungeon_variants_tick_clean(pygame_headless):
    """Each variant's DungeonRunner.update ticks without error for 60
    frames after entering (the dungeon combat + spawn + skill tick all
    compose cleanly for each variant)."""
    from engine.runner import DungeonRunner
    from core.state import GameState
    for vtype in ("story", "endless", "daily"):
        state = GameState()
        state.medals = 100
        dr = DungeonRunner(state, variant=vtype)
        dr.enter()
        for _ in range(60):
            dr.update(1 / 60)
        # No exception = pass; the dungeon is still active (the variants
        # don't exit on a timeout — only on clearing the last floor).
        assert state.dungeon_active is True, (
            f"variant {vtype} exited during a 60-frame tick "
            "(it should still be active)")


def test_dungeon_variants_with_main_runner_smoke(pygame_headless):
    """The full smoke: a main Runner + a DungeonRunner (each variant)
    both tick without error when the dungeon is active. The road loop
    and the dungeon loop coexist for each variant."""
    from engine.runner import Runner, DungeonRunner
    from core.state import GameState
    for vtype in ("story", "endless", "daily"):
        state = GameState()
        state.medals = 100
        runner = Runner(state)
        dr = DungeonRunner(state, variant=vtype)
        dr.enter()
        for _ in range(60):
            runner.update(1 / 60)
            dr.update(1 / 60)
        # Both worlds advanced (the road's total_distance and the dungeon's
        # active state are both intact).
        assert runner.world.total_distance > 0
        assert state.dungeon_active is True
