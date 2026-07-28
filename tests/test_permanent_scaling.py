"""Task 17 -- Permanent scaling floor: stacking tokens + Heritage passives.

Two permanent-scaling systems on top of the existing BonusProvider
registry (Task 3):

  * **Stacking tokens** -- permanent ``+1%``-per-token multipliers
    (Strike / Crit / Coin / Elixir) sourced from daily quests + zone-boss
    milestones. They live in ``state.tokens`` (a ``dict[str, int]``
    seeded by the v3 migration) and survive ALL prestige layers
    (ascension resets gold/upgrades/zone/combo/energy but never tokens;
    reincarnation is the only deeper reset and even there tokens persist
    as the permanent floor). The provider emits ``<kind>_token_pct`` per
    token kind.

  * **Heritage passives (achievements)** -- the 14 one-shot
    amber/medal-payout achievements are converted to permanent cumulative
    multipliers. The provider reads ``len(state.achievements)`` (NOT the
    Dojo ``heritage`` set -- that is a different heritage, see Task 15)
    and emits a single ``heritage_pct`` key.

The two providers read disjoint state (``state.tokens`` vs
``state.achievements``) so there is no double-counting. Tokens come from
daily quests + zone-boss milestones (NOT achievements); Heritage comes
from achievements (NOT daily quests / bosses). The acquisition rate is
capped so the ``+1%``-per-token complements rather than replaces the
exponential zone scaling.
"""
import pytest


# ---------------------------------------------------------------------------
# Specimen tests from the task brief
# ---------------------------------------------------------------------------
def test_tokens_permanent(pygame_headless):
    """5 strike tokens -> +5% tap via the ``strike_token_pct`` key."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.tokens = {"strike": 5}  # 5 strike tokens = +5% tap
    out = aggregate_bonuses(state)
    assert out.get("strike_token_pct", 0) == pytest.approx(0.05)


def test_heritage_from_achievements(pygame_headless):
    """2 achievements -> a positive ``heritage_pct`` cumulative multiplier."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.achievements = {"first_blood", "slayer"}  # 2 achievements
    out = aggregate_bonuses(state)
    # Each achievement contributes a small permanent multiplier.
    assert out.get("heritage_pct", 0) > 0


# ---------------------------------------------------------------------------
# Tokens provider
# ---------------------------------------------------------------------------
def test_tokens_provider_registered(pygame_headless):
    """The tokens provider is in the registry."""
    from core.bonuses import _PROVIDERS, _tokens_provider
    assert _tokens_provider in _PROVIDERS


def test_tokens_provider_zero_for_empty(pygame_headless):
    """No tokens -> no ``*_token_pct`` keys."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    out = aggregate_bonuses(GameState())
    for k, v in out.items():
        assert not k.endswith("_token_pct"), f"unexpected token key {k}: {v}"


def test_tokens_provider_one_pct_each(pygame_headless):
    """Each token of each kind is +1% (0.01) -- additive across kinds."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.tokens = {"strike": 3, "crit": 2, "coin": 4, "elixir": 1}
    out = aggregate_bonuses(state)
    assert out.get("strike_token_pct", 0) == pytest.approx(0.03)
    assert out.get("crit_token_pct", 0) == pytest.approx(0.02)
    assert out.get("coin_token_pct", 0) == pytest.approx(0.04)
    assert out.get("elixir_token_pct", 0) == pytest.approx(0.01)


def test_tokens_survive_ascension(pygame_headless):
    """Tokens persist through ascension (the prestige loop resets gold,
    upgrades, zone, combo, energy -- never tokens)."""
    from core.state import GameState
    from core.ascend import ascend
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.tokens = {"strike": 5}
    state.zone_index = 9  # ascend requires zone_index >= 5
    state.gold = 1e6
    state.lifetime_gold = 1e6
    gained = ascend(state)
    assert gained > 0
    # Tokens untouched by the ascension reset.
    assert state.tokens == {"strike": 5}
    out = aggregate_bonuses(state)
    assert out.get("strike_token_pct", 0) == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Heritage achievements provider
# ---------------------------------------------------------------------------
def test_heritage_achievements_provider_registered(pygame_headless):
    """The heritage-achievements provider is in the registry."""
    from core.bonuses import _PROVIDERS, _heritage_achievements_provider
    assert _heritage_achievements_provider in _PROVIDERS


def test_heritage_achievements_zero_for_empty(pygame_headless):
    """No achievements -> heritage_pct == 0 (no spurious key)."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    out = aggregate_bonuses(GameState())
    assert out.get("heritage_pct", 0) == 0.0


def test_heritage_achievements_cumulative(pygame_headless):
    """Each achievement adds +0.5% (0.005) -- cumulative across all 14+."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.quests import ACHIEVEMENTS
    state = GameState()
    state.achievements = {a.id for a in ACHIEVEMENTS}
    out = aggregate_bonuses(state)
    assert out.get("heritage_pct", 0) == pytest.approx(
        len(ACHIEVEMENTS) * 0.005)


def test_heritage_achievements_distinct_from_dojo_heritage(pygame_headless):
    """The Dojo heritage set (Task 15) and the achievements heritage
    (this task) read disjoint state -- no double-counting. The Dojo
    heritage emits ``heritage_<id>`` keys; the achievements heritage
    emits a single ``heritage_pct`` key."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.heritage = {"kage_bunshin", "earth"}  # Dojo heritage (Task 15)
    state.achievements = {"first_blood", "slayer"}  # this task's heritage
    out = aggregate_bonuses(state)
    # Dojo heritage -> per-id keys.
    assert out.get("heritage_kage_bunshin", 0) > 0
    assert out.get("heritage_earth", 0) > 0
    # Achievements heritage -> the single ``heritage_pct`` key.
    assert out.get("heritage_pct", 0) > 0
    # The two do not share keys: the Dojo heritage never emits
    # ``heritage_pct`` and the achievements heritage never emits
    # ``heritage_<id>``.
    assert out.get("heritage_pct", 0) == pytest.approx(2 * 0.005)


# ---------------------------------------------------------------------------
# Token awards from daily quests + zone-boss milestones (NOT achievements)
# ---------------------------------------------------------------------------
def test_token_award_on_daily_quest_complete(pygame_headless):
    """Completing a daily quest awards a token (capped rate). Tokens come
    from daily quests + zone-boss milestones -- NOT achievements."""
    from core.state import GameState
    from core.quests import update_daily_progress, TOKEN_KINDS
    state = GameState()
    state.daily_quests = [
        {"id": "q_kill_100", "target": 100, "progress": 0.0},
    ]
    state.kills_today = 100  # satisfies q_kill_100
    completed = update_daily_progress(state)
    assert completed, "daily quest should complete"
    # A token was awarded (some kind in the token set).
    assert sum(state.tokens.values()) > 0
    assert any(k in TOKEN_KINDS for k in state.tokens)


def test_token_award_on_zone_boss_milestone(pygame_headless):
    """Each zone-boss kill awards a token at a capped milestone rate
    (every Nth boss). Tokens come from bosses -- NOT achievements."""
    from core.state import GameState
    from core.quests import award_boss_token
    state = GameState()
    # The first few bosses may or may not award a token (the cap); but
    # after enough bosses, at least one token has been awarded.
    total = 0
    for i in range(50):
        award_boss_token(state, boss_number=i)
        total = sum(state.tokens.values())
        if total > 0:
            break
    assert total > 0, "no token awarded after 50 boss kills"


def test_token_award_capped_rate(pygame_headless):
    """The acquisition rate is capped: not every boss kill awards a token.
    A cap ensures the +1%-per-token complements rather than replaces the
    exponential zone scaling -- so 100 boss kills must NOT yield 100
    tokens."""
    from core.state import GameState
    from core.quests import award_boss_token
    state = GameState()
    for i in range(100):
        award_boss_token(state, boss_number=i)
    total = sum(state.tokens.values())
    assert total < 100, f"cap not enforced: {total} tokens from 100 bosses"


def test_no_token_award_from_achievements(pygame_headless):
    """Achievements do NOT award tokens (Heritage reads
    ``state.achievements``; tokens come from daily quests + bosses only
    -- distinct sources, no double-counting)."""
    from core.state import GameState
    from core.quests import check_achievements
    state = GameState()
    state.monsters_killed = 1  # satisfies first_blood
    state.bosses_killed = 1    # satisfies slayer
    state.best_zone = 5         # satisfies zone_5
    newly = check_achievements(state)
    assert len(newly) >= 1
    # Achievements never add tokens.
    assert sum(state.tokens.values()) == 0


# ---------------------------------------------------------------------------
# Hidden / secret achievements with cryptic in-game hints
# ---------------------------------------------------------------------------
def test_hidden_achievements_exist(pygame_headless):
    """A few achievements are hidden/secret (the desc is a cryptic hint
    until unlocked -- not wiki-dependent)."""
    from data.quests import ACHIEVEMENTS
    hidden = [a for a in ACHIEVEMENTS if getattr(a, "hidden", False)]
    assert len(hidden) >= 2, "expected at least 2 hidden/secret achievements"


def test_hidden_achievements_have_cryptic_hints(pygame_headless):
    """Hidden achievements have a ``hint`` field -- a cryptic in-game
    hint (not the full desc, not wiki-dependent)."""
    from data.quests import ACHIEVEMENTS
    hidden = [a for a in ACHIEVEMENTS if getattr(a, "hidden", False)]
    for a in hidden:
        hint = getattr(a, "hint", None)
        assert hint, f"hidden achievement {a.id} has no cryptic hint"
        # The hint is not the full desc (it is a cryptic teaser).
        assert hint != a.desc, (
            f"hidden achievement {a.id} hint == desc (not cryptic)")


def test_hidden_achievements_still_check(pygame_headless):
    """Hidden achievements still unlock when their check fires -- the
    ``hidden`` flag only controls the in-game display, not the unlock."""
    from data.quests import ACHIEVEMENTS
    from core.state import GameState
    hidden = [a for a in ACHIEVEMENTS if getattr(a, "hidden", False)]
    for a in hidden:
        # The check is callable and does not raise.
        s = GameState()
        try:
            a.check(s)
        except Exception as e:
            pytest.fail(f"hidden achievement {a.id} check raised: {e}")


# ---------------------------------------------------------------------------
# Smoke: the providers compose with the rest of the bonus stack
# ---------------------------------------------------------------------------
def test_tokens_and_heritage_compose_with_skill_tree(pygame_headless):
    """Tokens + Heritage stack additively with the skill tree in the flat
    bonus dict -- no key collision, no interference."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.skill_tree = {"off_root"}  # +10% tap_pct
    state.tokens = {"strike": 5}     # +5% strike_token_pct
    state.achievements = {"first_blood", "slayer"}  # heritage_pct
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0) == pytest.approx(0.10)
    assert out.get("strike_token_pct", 0) == pytest.approx(0.05)
    assert out.get("heritage_pct", 0) > 0
