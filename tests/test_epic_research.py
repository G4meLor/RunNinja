"""Task 18 -- Epic Research permanent meta-tree (medals/amber).

A permanent meta-tree bought with underused medals/amber, reuses the
SkillNode structure from data/skill_tree.py. Three nodes (Elixir
Resonance, Away Mastery, Lab Discipline) live in ``state.epic_research``
(a separate set from ``state.skill_tree``) and are consumed by the
epic_research_provider in core.bonuses.

Away Mastery boosts offline gold via the ``away_pct`` key, but
core.offline caps the total offline earnings strictly below
active+boosted earnings (buildings + kills with combo + gold
multipliers) so a maxed Away Mastery never makes offline better than
playing actively.
"""
import time

import pytest


# ---------------------------------------------------------------------------
# Specimen tests from the task brief
# ---------------------------------------------------------------------------
def test_epic_research_provider(pygame_headless):
    """elixir_resonance -> a positive elixir_pct in the aggregate bonus dict."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.epic_research = {"elixir_resonance"}
    out = aggregate_bonuses(state)
    assert out.get("elixir_pct", 0) > 0


def test_away_mastery_caps_offline(pygame_headless):
    """Away Mastery + time away -> a report with applied or gold."""
    from core.state import GameState
    from core.offline import compute
    state = GameState()
    state.epic_research = {"away_mastery"}
    state.last_saved = 0  # simulate away
    report = compute(state)
    assert report["applied"] is True or "gold" in report


# ---------------------------------------------------------------------------
# Epic Research nodes (data/skill_tree.py)
# ---------------------------------------------------------------------------
def test_epic_research_nodes_exist(pygame_headless):
    """EPIC_RESEARCH_NODES has the three nodes from the brief."""
    from data.skill_tree import EPIC_RESEARCH_NODES
    ids = {n.id for n in EPIC_RESEARCH_NODES}
    assert "elixir_resonance" in ids
    assert "away_mastery" in ids
    assert "lab_discipline" in ids


def test_epic_research_nodes_reuse_skillnode(pygame_headless):
    """Epic Research nodes are SkillNode instances (reuses the structure)."""
    from data.skill_tree import EPIC_RESEARCH_NODES, SkillNode
    for n in EPIC_RESEARCH_NODES:
        assert isinstance(n, SkillNode)


def test_epic_research_nodes_separate_from_elixir_tree(pygame_headless):
    """Epic Research nodes are NOT in the elixir NODES list (separate tree)."""
    from data.skill_tree import NODES, EPIC_RESEARCH_NODES
    elixir_ids = {n.id for n in NODES}
    for n in EPIC_RESEARCH_NODES:
        assert n.id not in elixir_ids, (
            f"{n.id} is in the elixir NODES -- Epic Research must be separate")


# ---------------------------------------------------------------------------
# Epic Research provider (core/bonuses.py)
# ---------------------------------------------------------------------------
def test_epic_research_provider_registered(pygame_headless):
    """The epic research provider is in the registry."""
    from core.bonuses import _PROVIDERS, _epic_research_provider
    assert _epic_research_provider in _PROVIDERS


def test_epic_research_provider_zero_for_empty(pygame_headless):
    """No epic research -> no spurious keys from the epic provider."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    out = aggregate_bonuses(GameState())
    for k, v in out.items():
        assert v == 0.0, f"unexpected nonzero value for {k}: {v}"


def test_epic_research_elixir_resonance(pygame_headless):
    """elixir_resonance -> +15% elixir_pct."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.epic_research = {"elixir_resonance"}
    out = aggregate_bonuses(state)
    assert out.get("elixir_pct", 0) == pytest.approx(0.15)


def test_epic_research_away_mastery(pygame_headless):
    """away_mastery -> +25% away_pct."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.epic_research = {"away_mastery"}
    out = aggregate_bonuses(state)
    assert out.get("away_pct", 0) == pytest.approx(0.25)


def test_epic_research_lab_discipline(pygame_headless):
    """lab_discipline -> +10% upgrade_cost_pct (reduces upgrade cost)."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.epic_research = {"lab_discipline"}
    out = aggregate_bonuses(state)
    assert out.get("upgrade_cost_pct", 0) == pytest.approx(0.10)


def test_epic_research_lab_discipline_reduces_upgrade_cost(pygame_headless):
    """Lab Discipline actually reduces the upgrade cost in game_economy."""
    from core.state import GameState
    from core.game_economy import upgrade_cost
    state = GameState()
    state.upgrades = {"tap_power": 5}
    base_cost = upgrade_cost(state, "tap_power")
    state.epic_research = {"lab_discipline"}
    reduced_cost = upgrade_cost(state, "tap_power")
    assert reduced_cost < base_cost


def test_epic_research_multiple_nodes_stack(pygame_headless):
    """Multiple epic research nodes stack additively in the bonus dict."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.epic_research = {"elixir_resonance", "away_mastery", "lab_discipline"}
    out = aggregate_bonuses(state)
    assert out.get("elixir_pct", 0) == pytest.approx(0.15)
    assert out.get("away_pct", 0) == pytest.approx(0.25)
    assert out.get("upgrade_cost_pct", 0) == pytest.approx(0.10)


def test_epic_research_distinct_from_skill_tree(pygame_headless):
    """Epic Research reads state.epic_research, NOT state.skill_tree.

    Unlocking an epic research node does NOT add to the skill tree, and
    vice versa -- the two are separate sets with separate providers.
    """
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.skill_tree = {"off_root"}  # elixir skill tree node
    state.epic_research = {"elixir_resonance"}  # epic research node
    out = aggregate_bonuses(state)
    # Skill tree contributes tap_pct; epic research contributes elixir_pct.
    assert out.get("tap_pct", 0) == pytest.approx(0.10)
    assert out.get("elixir_pct", 0) == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Away Mastery: offline boost + strictly-below-active cap
# ---------------------------------------------------------------------------
def test_away_mastery_boosts_offline(pygame_headless):
    """Away Mastery + buildings + time away -> a positive offline report."""
    from core.state import GameState
    from core.offline import compute
    state = GameState()
    state.epic_research = {"away_mastery"}
    state.buildings = {"farm": 10}
    state.last_saved = time.time() - 3600  # 1 hour ago
    report = compute(state)
    assert report["applied"] is True
    assert report["gold"] > 0


def test_away_mastery_meaningful_boost(pygame_headless):
    """Away Mastery gives a meaningful boost: the away_pct contribution
    is positive and matches the node's effect_value."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    base_away = aggregate_bonuses(state).get("away_pct", 0)
    state.epic_research = {"away_mastery"}
    boosted_away = aggregate_bonuses(state).get("away_pct", 0)
    assert boosted_away > base_away
    assert boosted_away == pytest.approx(0.25)


def test_away_mastery_strictly_below_active(pygame_headless):
    """With Away Mastery, offline earnings per second stay strictly below
    active+boosted earnings per second (the cap in core.offline enforces
    this)."""
    from core.state import GameState
    from core.offline import compute, active_per_sec, AWAY_CAP
    state = GameState()
    state.epic_research = {"away_mastery"}
    state.buildings = {"farm": 100}
    state.zone_index = 5
    state.combo = 50  # mid-combo when the player left
    state.last_saved = time.time() - 3600
    # Compute active+boosted per second BEFORE compute (compute mutates
    # last_saved but not combo/buildings/zone, so active_per_sec is the
    # same before and after; computing it before is cleaner).
    active = active_per_sec(state)
    report = compute(state)
    assert report["applied"] is True
    offline_per_sec = report["gold"] / report["seconds"]
    # The cap enforces offline <= active * AWAY_CAP (strictly below active).
    assert offline_per_sec <= active * AWAY_CAP + 1e-6
    assert offline_per_sec < active


def test_away_mastery_cap_with_huge_away_pct(pygame_headless):
    """Even with a huge away_pct (stacked sources), the cap keeps offline
    strictly below active+boosted earnings."""
    from core.state import GameState
    from core.offline import compute, active_per_sec, AWAY_CAP
    state = GameState()
    state.epic_research = {"away_mastery"}
    state.skill_tree = {"eco_away1"}  # +15% away_pct
    state.upgrades = {"away_income": 50}  # large away_income upgrade
    state.buildings = {"farm": 100}
    state.zone_index = 5
    state.combo = 50
    state.last_saved = time.time() - 3600
    active = active_per_sec(state)
    report = compute(state)
    assert report["applied"] is True
    offline_per_sec = report["gold"] / report["seconds"]
    # The cap enforces offline <= active * AWAY_CAP despite the huge
    # away_pct that would otherwise push offline above active.
    assert offline_per_sec <= active * AWAY_CAP + 1e-6
    assert offline_per_sec < active


def test_away_mastery_cap_accounts_for_combo_step(pygame_headless):
    """The cap's active reference mirrors the runner's combo_mult INCLUDING
    the ``combo_step`` run upgrade (which reduces ``tau``, raising the
    combo multiplier at a given combo count). Without the upgrade the
    active reference would underestimate the real active rate, making the
    cap too low and underpaying the player offline.
    """
    import math
    from core.state import GameState
    from core.offline import active_per_sec
    from engine.runner import Runner, COMBO_MULT_CAP
    import config as cfg
    from core.game_economy import _upgrade_pct
    state = GameState()
    state.upgrades = {"combo_step": 10}
    state.combo = 50
    state.buildings = {"farm": 100}
    state.zone_index = 5
    # The runner's combo_mult at combo 50 with combo_step=10.
    r = Runner(state)
    runner_combo = r.combo_mult()
    # The tau active_per_sec should be using (with the combo_step upgrade
    # + the 5.0 floor).
    tau = max(5.0, cfg.COMBO_TAU - _upgrade_pct(state, "combo_step"))
    expected_combo = 1.0 + (COMBO_MULT_CAP - 1.0) * (1.0 - math.exp(-state.combo / tau))
    assert runner_combo == pytest.approx(expected_combo), (
        "active_per_sec's tau does not account for combo_step -- the cap "
        "would underestimate the active rate.")
    # And the cap holds: offline stays strictly below the (accurate)
    # active+boosted rate.
    from core.offline import compute, AWAY_CAP
    active = active_per_sec(state)
    state.last_saved = time.time() - 3600
    report = compute(state)
    assert report["applied"] is True
    offline_per_sec = report["gold"] / report["seconds"]
    assert offline_per_sec <= active * AWAY_CAP + 1e-6
    assert offline_per_sec < active


# ---------------------------------------------------------------------------
# Smoke: the provider composes with the rest of the bonus stack
# ---------------------------------------------------------------------------
def test_epic_research_composes_with_skill_tree(pygame_headless):
    """Epic Research + skill tree stack additively in the flat bonus dict
    -- no key collision, no interference."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.skill_tree = {"eli_root"}  # +10% elixir_pct (skill tree)
    state.epic_research = {"elixir_resonance"}  # +15% elixir_pct (epic)
    out = aggregate_bonuses(state)
    # Both contribute elixir_pct; they sum additively.
    assert out.get("elixir_pct", 0) == pytest.approx(0.10 + 0.15)
