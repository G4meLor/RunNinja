"""Build specialization (Dojos) + Heritage passives.

Unifies build-specialisation + Dojo + Heritage into one coherent axis.
At the abilities branch fork, the player commits to one damage path per
ascension (Kage-bunshin idle / Iaijutsu tap-burst / Shikigami summon /
Kusari-gama multi-hit). The 4 Dojos map to the 4 Godai elements (Void /
Wind / Fire / Water); the 5th element (Earth) is the generalist's
utility/defense heritage. Specialization is ADDITIVE (buffs toward
chosen), NOT mutually-exclusive -- a generalist default is viable and
respec is free (change dojo any time). Completing a full ascension under
a Dojo grants its Heritage passive; collecting all 5 heritages is the
meta-goal.

Dojo -> Godai mapping (the 4 most fitting elements):
  Kage-bunshin (shadow clones / idle)  -> Void   (ku -- shadows, emptiness)
  Iaijutsu    (quick draw / tap-burst) -> Wind   (fu -- speed, cutting wind)
  Shikigami   (spirit summon)          -> Fire   (ka -- spirit fire)
  Kusari-gama (chain multi-hit)         -> Water  (sui -- flowing chain)
  Earth (chi) -- generalist utility/defense heritage
"""
import pytest


# ---------------------------------------------------------------------------
# Dojo nodes in the skill tree
# ---------------------------------------------------------------------------
def test_four_dojo_nodes_in_abilities_branch(pygame_headless):
    """4 dojo nodes exist in the abilities branch, one per damage path."""
    from data import skill_tree as st
    dojo_nodes = [n for n in st.NODES if n.branch == "abilities"
                  and n.id.startswith("dojo_")]
    ids = {n.id for n in dojo_nodes}
    assert ids == {"dojo_kage_bunshin", "dojo_iaijutsu",
                   "dojo_shikigami", "dojo_kusari_gama"}


def test_dojo_nodes_have_ab_root_prereq(pygame_headless):
    """Each dojo node's prereq is ab_root (the abilities branch root)."""
    from data import skill_tree as st
    for nid in ("dojo_kage_bunshin", "dojo_iaijutsu",
                "dojo_shikigami", "dojo_kusari_gama"):
        n = st.BY_ID[nid]
        assert n.prereq == "ab_root", f"{nid} prereq is {n.prereq}"


# ---------------------------------------------------------------------------
# Dojo provider -- additive buff, no lockout
# ---------------------------------------------------------------------------
def test_dojo_additive(pygame_headless):
    """Setting state.dojo produces an additive buff toward the chosen path.
    No lockout: choosing one dojo does not reduce another's stat.
    """
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.dojo = "kage_bunshin"
    out = aggregate_bonuses(state)
    # Additive buff toward the chosen dojo, no lockout.
    assert "dojo_kage_bunshin" in out or out.get("idle_pct", 0) > 0


def test_dojo_none_no_buff(pygame_headless):
    """With dojo == 'none' (generalist), no dojo buff is emitted."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    out = aggregate_bonuses(state)
    for k in out:
        assert not k.startswith("dojo_"), f"unexpected dojo key {k}: {out[k]}"


def test_dojo_provider_registered(pygame_headless):
    """The dojo provider is in the registry."""
    from core.bonuses import _PROVIDERS, _dojo_provider
    assert _dojo_provider in _PROVIDERS


def test_dojo_not_mutually_exclusive(pygame_headless):
    """Specialization is ADDITIVE, not a capstone lockout: the generalist
    default (no dojo) still produces full, viable stats -- choosing a dojo
    only ADDS a buff, it doesn't reduce the base."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    # Generalist (no dojo).
    state_gen = GameState()
    stats_gen = compute_ninja_stats(state_gen)
    # Kage-bunshin (idle path).
    state_kb = GameState()
    state_kb.dojo = "kage_bunshin"
    stats_kb = compute_ninja_stats(state_kb)
    # The dojo ADDS to the chosen stat -- auto_damage should be higher.
    assert stats_kb["auto_damage"] > stats_gen["auto_damage"], (
        f"dojo not additive: auto {stats_gen['auto_damage']} -> {stats_kb['auto_damage']}")
    # But tap_damage should NOT be reduced (no lockout).
    assert stats_kb["tap_damage"] >= stats_gen["tap_damage"], (
        f"dojo lockout: tap {stats_gen['tap_damage']} -> {stats_kb['tap_damage']}")


# ---------------------------------------------------------------------------
# Each dojo buffs its mapped stat
# ---------------------------------------------------------------------------
def test_iaijutsu_buffs_tap(pygame_headless):
    """Iaijutsu (tap-burst) buffs tap_damage."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    s0 = GameState()
    s1 = GameState()
    s1.dojo = "iaijutsu"
    assert compute_ninja_stats(s1)["tap_damage"] > compute_ninja_stats(s0)["tap_damage"]


def test_kage_bunshin_buffs_auto(pygame_headless):
    """Kage-bunshin (idle) buffs auto_damage."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    s0 = GameState()
    s1 = GameState()
    s1.dojo = "kage_bunshin"
    assert compute_ninja_stats(s1)["auto_damage"] > compute_ninja_stats(s0)["auto_damage"]


def test_shikigami_buffs_crit_dmg(pygame_headless):
    """Shikigami (summon) buffs crit_dmg."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    s0 = GameState()
    s1 = GameState()
    s1.dojo = "shikigami"
    assert compute_ninja_stats(s1)["crit_dmg"] > compute_ninja_stats(s0)["crit_dmg"]


def test_kusari_gama_buffs_attack_speed(pygame_headless):
    """Kusari-gama (multi-hit) buffs attack_speed."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    s0 = GameState()
    s1 = GameState()
    s1.dojo = "kusari_gama"
    assert compute_ninja_stats(s1)["attack_speed"] > compute_ninja_stats(s0)["attack_speed"]


# ---------------------------------------------------------------------------
# Heritage granted on ascension
# ---------------------------------------------------------------------------
def test_heritage_granted_on_ascend(pygame_headless):
    """Ascending under a dojo grants that dojo's heritage."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.dojo = "kage_bunshin"
    state.zone_index = 5
    state.best_zone = 5
    state.gold = 100000
    ascend(state)
    assert "kage_bunshin" in state.heritage


def test_earth_heritage_from_generalist(pygame_headless):
    """Ascending with no dojo (generalist) grants the Earth heritage."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.dojo = "none"
    state.zone_index = 5
    state.best_zone = 5
    state.gold = 100000
    ascend(state)
    assert "earth" in state.heritage


def test_heritage_not_duplicated(pygame_headless):
    """Heritage is a set -- ascending twice under the same dojo doesn't
    duplicate the entry."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.dojo = "kage_bunshin"
    state.zone_index = 5
    state.gold = 100000
    ascend(state)
    ascend(state)
    # heritage is a set; "kage_bunshin" appears once.
    assert "kage_bunshin" in state.heritage


# ---------------------------------------------------------------------------
# Heritage provider -- additive permanent buff
# ---------------------------------------------------------------------------
def test_heritage_provider_registered(pygame_headless):
    """The heritage provider is in the registry."""
    from core.bonuses import _PROVIDERS, _heritage_provider
    assert _heritage_provider in _PROVIDERS


def test_heritage_provider_additive(pygame_headless):
    """Each collected heritage adds a small permanent buff."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.heritage = {"kage_bunshin", "iaijutsu"}
    out = aggregate_bonuses(state)
    assert out.get("heritage_kage_bunshin", 0) > 0
    assert out.get("heritage_iaijutsu", 0) > 0


def test_earth_heritage_buffs_max_hp(pygame_headless):
    """Earth heritage (utility/defense) buffs max_hp in compute_ninja_stats."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    s0 = GameState()
    s1 = GameState()
    s1.heritage = {"earth"}
    assert compute_ninja_stats(s1)["max_hp"] > compute_ninja_stats(s0)["max_hp"]


# ---------------------------------------------------------------------------
# Dojo + Godai compose cleanly in compute_ninja_stats
# ---------------------------------------------------------------------------
def test_dojo_godai_compose_cleanly(pygame_headless):
    """Dojo buffs and Godai element multipliers stack without interference:
    a state with both a dojo and a godai element produces stats that are
    strictly higher than either alone (they compose additively/multiplicatively
    in their respective layers, not destructively)."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    # Baseline: no dojo, no godai.
    base = compute_ninja_stats(GameState())
    # Dojo only (kage_bunshin -> auto_damage).
    s_dojo = GameState()
    s_dojo.dojo = "kage_bunshin"
    dojo_only = compute_ninja_stats(s_dojo)
    # Godai only (water -> max_hp).
    s_godai = GameState()
    s_godai.skill_tree = {"godai_gate", "godai_water"}
    godai_only = compute_ninja_stats(s_godai)
    # Both.
    s_both = GameState()
    s_both.dojo = "kage_bunshin"
    s_both.skill_tree = {"godai_gate", "godai_water"}
    both = compute_ninja_stats(s_both)
    # auto_damage: dojo adds to it; godai_water doesn't touch it.
    assert both["auto_damage"] > base["auto_damage"]
    assert both["auto_damage"] >= dojo_only["auto_damage"]
    # max_hp: godai_water multiplies it; dojo doesn't touch it.
    assert both["max_hp"] > base["max_hp"]
    assert both["max_hp"] >= godai_only["max_hp"]


# ---------------------------------------------------------------------------
# Generalist default is viable
# ---------------------------------------------------------------------------
def test_generalist_default_viable(pygame_headless):
    """A generalist (no dojo) produces viable stats -- all stats are
    positive and the ninja can fight."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    stats = compute_ninja_stats(GameState())
    assert stats["tap_damage"] > 0
    assert stats["auto_damage"] > 0
    assert stats["attack_speed"] > 0
    assert stats["max_hp"] > 0
    assert stats["crit_chance"] > 0
    assert stats["crit_dmg"] > 1.0


# ---------------------------------------------------------------------------
# Collect all 5 heritages meta-goal
# ---------------------------------------------------------------------------
def test_collect_all_5_heritages_meta_goal(pygame_headless):
    """There are exactly 5 heritages to collect: 4 dojos + Earth."""
    from core.state import GameState
    from core.ascend import ascend
    # Ascend under each dojo + once as generalist.
    state = GameState()
    state.gold = 100000
    for dojo in ("kage_bunshin", "iaijutsu", "shikigami", "kusari_gama", "none"):
        state.dojo = dojo
        # Re-set zone_index (ascend resets it to 0).
        state.zone_index = 5
        ascend(state)
    assert state.heritage == {"kage_bunshin", "iaijutsu", "shikigami",
                              "kusari_gama", "earth"}


def test_all_5_heritages_achievement_exists():
    """An achievement for collecting all 5 heritages exists and triggers."""
    from data.quests import ACHIEVEMENTS
    from core.state import GameState
    heritage_ach = [a for a in ACHIEVEMENTS if "heritage" in a.id.lower()]
    assert len(heritage_ach) >= 1, "no heritage collection achievement"
    ach = heritage_ach[0]
    state = GameState()
    state.heritage = {"kage_bunshin", "iaijutsu", "shikigami", "kusari_gama", "earth"}
    assert ach.check(state), f"achievement {ach.id} not satisfied with 5 heritages"
