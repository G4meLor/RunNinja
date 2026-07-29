"""Task 35 -- Reincarnation perks + Cosmic Forge anchor.

Named Soul Tree perks (start at zone 3, +1 equip slot, keep 25% of skill
tree, 5th active skill) + the persistent Cosmic Forge (max 10) anchors the
rebuild. Each perk is a run-breaking verb -- it changes how a new run
starts after reincarnation. The Cosmic Forge is a PERSISTENT anchor (max
10) -- it survives reincarnation (it IS the anchor). The "collect all 5
heritages" meta-goal already exists (Task 15); this test verifies it.

Reincarnation is the HARD reset (resets ascend_tier + elixir + skill_tree)
gated behind Singularity (tier 6) + 10 ascensions. The Soul Tree perks
(``state.soul_tree``) are permanent -- they survive ALL resets. Souls are
the reincarnation currency, awarded on ascension
(``soul_reward_on_ascend`` in ``config.ASCEND_TIERS``).
"""
import pytest


# ---------------------------------------------------------------------------
# Specimen tests from the task brief
# ---------------------------------------------------------------------------
def test_soul_tree_perks(pygame_headless):
    from data.skill_tree import SOUL_TREE_PERKS
    perk_ids = {p.id for p in SOUL_TREE_PERKS}
    assert "start_zone_3" in perk_ids
    assert "extra_equip_slot" in perk_ids
    assert "keep_skill_tree" in perk_ids
    assert "fifth_active_skill" in perk_ids


def test_cosmic_forge_anchor(pygame_headless):
    from core.state import GameState
    state = GameState()
    # The Cosmic Forge is a persistent anchor (max 10).
    assert hasattr(state, "cosmic_forge")


# ---------------------------------------------------------------------------
# Soul Tree perks (data/skill_tree.py)
# ---------------------------------------------------------------------------
def test_soul_tree_perks_are_soul_tree_perk(pygame_headless):
    """Each Soul Tree perk is a SoulTreePerk dataclass instance."""
    from data.skill_tree import SOUL_TREE_PERKS, SoulTreePerk
    for p in SOUL_TREE_PERKS:
        assert isinstance(p, SoulTreePerk)


def test_soul_tree_perks_have_costs(pygame_headless):
    """Each perk has a positive soul cost."""
    from data.skill_tree import SOUL_TREE_PERKS
    for p in SOUL_TREE_PERKS:
        assert p.cost > 0, f"perk {p.id} has non-positive cost {p.cost}"


def test_soul_tree_perks_by_id(pygame_headless):
    """SOUL_TREE_PERKS_BY_ID maps each perk id to the perk object."""
    from data.skill_tree import SOUL_TREE_PERKS_BY_ID
    for pid in ("start_zone_3", "extra_equip_slot", "keep_skill_tree",
                "fifth_active_skill"):
        assert pid in SOUL_TREE_PERKS_BY_ID, f"missing perk {pid}"


def test_soul_tree_perks_exactly_four(pygame_headless):
    """Exactly 4 Soul Tree perks (the 4 run-breaking verbs)."""
    from data.skill_tree import SOUL_TREE_PERKS
    assert len(SOUL_TREE_PERKS) == 4


# ---------------------------------------------------------------------------
# Cosmic Forge (persistent anchor, max 10)
# ---------------------------------------------------------------------------
def test_cosmic_forge_default_zero(pygame_headless):
    from core.state import GameState
    state = GameState()
    assert state.cosmic_forge == 0


def test_cosmic_forge_persists_in_save(pygame_headless):
    """Cosmic Forge survives a save/load round-trip."""
    from core.state import GameState
    state = GameState()
    state.cosmic_forge = 5
    d = state.to_dict()
    assert d["cosmic_forge"] == 5
    state2 = GameState.from_dict(d)
    assert state2.cosmic_forge == 5


# ---------------------------------------------------------------------------
# Reincarnation gate + function (core/ascend.py)
# ---------------------------------------------------------------------------
def test_reincarnation_gate(pygame_headless):
    """Reincarnation is gated behind Singularity (tier 6) + 10 ascensions."""
    from core.state import GameState
    from core.ascend import can_reincarnate
    state = GameState()
    # Not gated: need Singularity (tier 6) + 10 ascensions.
    assert not can_reincarnate(state)
    state.ascend_tier = 6
    assert not can_reincarnate(state)  # still need 10 ascensions
    state.total_ascensions = 10
    assert can_reincarnate(state)


def test_reincarnation_gate_partial_tier(pygame_headless):
    """Below Singularity (tier < 6) the gate is not met even with 10+ ascensions."""
    from core.state import GameState
    from core.ascend import can_reincarnate
    state = GameState()
    state.ascend_tier = 5  # Cosmic, not Singularity
    state.total_ascensions = 20
    assert not can_reincarnate(state)


def test_reincarnate_resets_ascend_tier(pygame_headless):
    """Reincarnation is a HARD reset: ascend_tier goes back to 0."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.elixir = 1000
    state.skill_tree = {"off_root"}
    assert reincarnate(state)
    assert state.ascend_tier == 0
    assert state.elixir == 0
    assert state.skill_tree == set()


def test_reincarnate_resets_run_state(pygame_headless):
    """Reincarnation resets run-scoped state (gold, zone, combo, energy)."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.gold = 50000
    state.zone_index = 10
    state.combo = 50
    state.energy = 100
    state.energy_active = True
    state.upgrades = {"tap_power": 5}
    reincarnate(state)
    assert state.gold == 0
    assert state.zone_index == 0
    assert state.combo == 0
    assert state.energy_active == False
    assert state.upgrades == {}


def test_reincarnate_increments_cosmic_forge(pygame_headless):
    """Each reincarnation increments the Cosmic Forge (the persistent anchor)."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    forge = state.cosmic_forge
    reincarnate(state)
    assert state.cosmic_forge == forge + 1


def test_cosmic_forge_clamps_at_10(pygame_headless):
    """The Cosmic Forge is capped at 10 (the persistent anchor max)."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.cosmic_forge = 10
    reincarnate(state)
    assert state.cosmic_forge == 10  # clamped, not 11


def test_reincarnate_preserves_soul_tree(pygame_headless):
    """Soul Tree perks are permanent -- they survive reincarnation."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.soul_tree = {"start_zone_3", "extra_equip_slot"}
    state.souls = 500
    reincarnate(state)
    assert state.soul_tree == {"start_zone_3", "extra_equip_slot"}
    assert state.souls == 500


def test_reincarnate_returns_false_when_gated(pygame_headless):
    """Reincarnation returns False (no-op) when the gate is not met."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 3
    state.total_ascensions = 5
    assert not reincarnate(state)
    # State is unchanged.
    assert state.ascend_tier == 3


# ---------------------------------------------------------------------------
# Perk: start_zone_3
# ---------------------------------------------------------------------------
def test_start_zone_3_perk(pygame_headless):
    """With the perk, reincarnation starts at zone 3 (zone_index = 2)."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.soul_tree = {"start_zone_3"}
    reincarnate(state)
    assert state.zone_index == 2  # 0-indexed zone 3


def test_no_start_zone_3_perk(pygame_headless):
    """Without the perk, reincarnation starts at zone 1 (zone_index = 0)."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    reincarnate(state)
    assert state.zone_index == 0


# ---------------------------------------------------------------------------
# Perk: keep_skill_tree
# ---------------------------------------------------------------------------
def test_keep_skill_tree_perk(pygame_headless):
    """With the perk, 25% of skill-tree nodes are kept on reincarnation."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.soul_tree = {"keep_skill_tree"}
    # 8 nodes -> keep 2 (25% rounded down).
    state.skill_tree = {"off_root", "eco_root", "eli_root", "eng_root",
                        "fly_root", "ab_root", "def_root", "combo_root"}
    reincarnate(state)
    assert len(state.skill_tree) == 2  # 8 // 4 = 2


def test_keep_skill_tree_rounds_down(pygame_headless):
    """25% of 3 nodes = 0.75, rounded down = 0 (no nodes kept)."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.soul_tree = {"keep_skill_tree"}
    state.skill_tree = {"off_root", "eco_root", "eli_root"}
    reincarnate(state)
    assert len(state.skill_tree) == 0  # 3 // 4 = 0


def test_keep_skill_tree_not_active_resets_all(pygame_headless):
    """Without the perk, the skill tree is fully reset on reincarnation."""
    from core.state import GameState
    from core.ascend import reincarnate
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.skill_tree = {"off_root", "eco_root", "eli_root"}
    reincarnate(state)
    assert state.skill_tree == set()


# ---------------------------------------------------------------------------
# Perk: extra_equip_slot
# ---------------------------------------------------------------------------
def test_extra_equip_slot_perk(pygame_headless):
    """With the perk, effective_gear_slots returns 5 slots; without, 4."""
    from core.state import GameState
    from core.bonuses import effective_gear_slots
    state = GameState()
    assert len(effective_gear_slots(state)) == 4
    state.soul_tree = {"extra_equip_slot"}
    assert len(effective_gear_slots(state)) == 5


def test_extra_equip_slot_adds_spirit(pygame_headless):
    """The 5th slot is 'spirit' (a new slot, not a duplicate)."""
    from core.state import GameState
    from core.bonuses import effective_gear_slots
    state = GameState()
    state.soul_tree = {"extra_equip_slot"}
    slots = effective_gear_slots(state)
    assert "spirit" in slots
    # The base 4 slots are still there.
    for s in ("blade", "mask", "talisman", "cloak"):
        assert s in slots


def test_extra_equip_slot_affix_pool(pygame_headless):
    """The 'spirit' slot has an affix pool in GEAR_AFFIXES."""
    import config as cfg
    assert "spirit" in cfg.GEAR_AFFIXES
    pool = cfg.GEAR_AFFIXES["spirit"]
    assert len(pool) > 0


# ---------------------------------------------------------------------------
# Perk: fifth_active_skill
# ---------------------------------------------------------------------------
def test_fifth_active_skill_def(pygame_headless):
    """The 5th skill 'shadow_step' is in SKILL_DEFS."""
    from engine.skills import SKILL_DEFS
    assert "shadow_step" in SKILL_DEFS
    d = SKILL_DEFS["shadow_step"]
    assert d["cooldown"] > 0
    assert "name" in d


def test_fifth_active_skill_in_runner(pygame_headless):
    """With the perk, the runner's skill set includes shadow_step."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.soul_tree = {"fifth_active_skill"}
    state.skill_tree = {"ab_root"}  # need at least one skill unlocked
    r = Runner(state)
    assert "shadow_step" in r.skills


def test_fifth_active_skill_not_in_runner_without_perk(pygame_headless):
    """Without the perk, shadow_step is NOT in the runner's skill set."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root"}
    r = Runner(state)
    assert "shadow_step" not in r.skills


# ---------------------------------------------------------------------------
# Heritage meta-goal (collect all 5)
# ---------------------------------------------------------------------------
def test_heritage_meta_goal_exists(pygame_headless):
    """The 'collect all 5 heritages' meta-goal: 4 dojos + Earth."""
    from core.state import GameState
    state = GameState()
    assert isinstance(state.heritage, set)
    # The 5 heritage keys: 4 dojos + Earth.
    all_heritages = {"kage_bunshin", "iaijutsu", "shikigami",
                     "kusari_gama", "earth"}
    for h in all_heritages:
        state.heritage.add(h)
    assert state.heritage == all_heritages
    assert len(state.heritage) == 5


def test_heritage_granted_on_ascend_dojo(pygame_headless):
    """Ascending under a dojo grants that dojo's heritage (Task 15)."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.dojo = "kage_bunshin"
    state.zone_index = 5
    state.best_zone = 5
    state.gold = 100000
    state.lifetime_gold = 100000
    ascend(state)
    assert "kage_bunshin" in state.heritage


def test_heritage_granted_on_ascend_earth(pygame_headless):
    """Ascending with no dojo grants the Earth heritage (Task 15)."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.dojo = "none"
    state.zone_index = 5
    state.best_zone = 5
    state.gold = 100000
    state.lifetime_gold = 100000
    ascend(state)
    assert "earth" in state.heritage


# ---------------------------------------------------------------------------
# Souls awarded on ascension
# ---------------------------------------------------------------------------
def test_souls_awarded_on_ascend(pygame_headless):
    """Ascending awards souls (the reincarnation currency)."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.zone_index = 5
    state.best_zone = 5
    state.gold = 100000
    state.lifetime_gold = 100000
    souls_before = state.souls
    ascend(state)
    assert state.souls > souls_before


# ---------------------------------------------------------------------------
# Soul Tree perk purchase
# ---------------------------------------------------------------------------
def test_purchase_soul_tree_perk(pygame_headless):
    """Purchasing a Soul Tree perk spends souls + adds to soul_tree."""
    from core.state import GameState
    from core.ascend import purchase_soul_tree_perk
    from data.skill_tree import SOUL_TREE_PERKS_BY_ID
    state = GameState()
    state.souls = 500
    perk = SOUL_TREE_PERKS_BY_ID["start_zone_3"]
    assert purchase_soul_tree_perk(state, "start_zone_3")
    assert "start_zone_3" in state.soul_tree
    assert state.souls == 500 - perk.cost


def test_purchase_soul_tree_perk_insufficient_souls(pygame_headless):
    """Purchasing a perk with insufficient souls fails (no-op)."""
    from core.state import GameState
    from core.ascend import purchase_soul_tree_perk
    state = GameState()
    state.souls = 10
    assert not purchase_soul_tree_perk(state, "start_zone_3")
    assert "start_zone_3" not in state.soul_tree
    assert state.souls == 10  # unchanged


def test_purchase_soul_tree_perk_already_unlocked(pygame_headless):
    """Purchasing an already-unlocked perk is a no-op."""
    from core.state import GameState
    from core.ascend import purchase_soul_tree_perk
    state = GameState()
    state.souls = 500
    state.soul_tree = {"start_zone_3"}
    assert not purchase_soul_tree_perk(state, "start_zone_3")
    assert state.souls == 500  # unchanged
