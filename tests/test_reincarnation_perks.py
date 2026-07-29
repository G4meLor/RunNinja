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


def test_start_zone_3_survives_reset_for_ascension(pygame_headless):
    """The perk's zone 3 start survives ``reset_for_ascension`` (the live
    game flow: the ascend screen calls ``reincarnate()`` then
    ``reset_for_ascension()``, which would otherwise reset
    ``world.zone_index`` to 0 and overwrite the perk via the next update
    tick's ``state.zone_index = world.zone_index`` sync).

    The fix: ``reset_for_ascension`` seeds ``world.zone_index`` from
    ``state.zone_index`` so the perk's value is respected. With the perk,
    the world starts at zone 2; without, at zone 0 (the ascension path).
    """
    from core.state import GameState
    from core.ascend import reincarnate
    from engine.runner import Runner
    # With the perk: reincarnate -> reset_for_ascension -> world.zone_index = 2.
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.soul_tree = {"start_zone_3"}
    r = Runner(state)
    reincarnate(state)
    r.reset_for_ascension()
    assert state.zone_index == 2  # the perk's value
    assert r.world.zone_index == 2  # the world respects the perk
    # Without the perk: reincarnate -> reset_for_ascension -> zone 0.
    state2 = GameState()
    state2.ascend_tier = 6
    state2.total_ascensions = 10
    r2 = Runner(state2)
    reincarnate(state2)
    r2.reset_for_ascension()
    assert state2.zone_index == 0
    assert r2.world.zone_index == 0


def test_start_zone_3_survives_update_tick_sync(pygame_headless):
    """The perk's zone 3 start survives a full ``update`` tick (the
    ``state.zone_index = world.zone_index`` sync in the runner's update
    loop would overwrite the perk if ``world.zone_index`` were 0). This
    is the end-to-end check: after reincarnate + reset_for_ascension +
    one update tick, the state is still at zone 2 with the perk.
    """
    from core.state import GameState
    from core.ascend import reincarnate
    from engine.runner import Runner
    state = GameState()
    state.ascend_tier = 6
    state.total_ascensions = 10
    state.soul_tree = {"start_zone_3"}
    r = Runner(state)
    reincarnate(state)
    r.reset_for_ascension()
    # Run one update tick -- the sync (state.zone_index = world.zone_index)
    # would overwrite the perk if world.zone_index were 0.
    r.update(1 / 60)
    assert state.zone_index == 2  # the perk survives the update sync


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


def test_extra_equip_slot_boss_drop_lands_in_spirit(pygame_headless):
    """With the perk, a boss drop can land in the 'spirit' slot (end-to-end).

    The runner's ``_drop_gear`` uses ``effective_gear_slots(state)`` so
    the 5th 'spirit' slot is in the drop pool when the perk is active.
    Over many boss kills with the perk, the 'spirit' slot should receive
    at least one drop (the slot is in the random pool).

    Re-initializes the display if a prior test quit pygame (the
    ``_drop_gear`` path calls ``death_fx.spawn`` which calls
    ``enemy_surface`` which calls ``convert_alpha`` -- needs the display).
    """
    import pygame
    from theme import reset_fonts
    if not pygame.display.get_init():
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        pygame.display.set_mode((1280, 720))
    reset_fonts()
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_boss
    from data import enemies as ed
    from core.bonuses import aggregate_bonuses
    from utils import seed
    seed(42)
    state = GameState()
    state.soul_tree = {"extra_equip_slot"}
    r = Runner(state)
    bdef = ed.boss_for_zone("village")
    spirit_drops = 0
    for _ in range(200):
        # Clear gear so each drop is fresh (the slot is random; we want
        # to see the 'spirit' slot appear at least once).
        state.gear = {}
        boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
        boss.alive = False
        boss.hp = 0
        r._on_enemy_killed(boss, r.combo_mult(), r.gold_mult(),
                           aggregate_bonuses(state))
        if "spirit" in state.gear:
            spirit_drops += 1
    assert spirit_drops > 0, (
        f"no drops landed in 'spirit' slot over 200 boss kills with the perk")


def test_extra_equip_slot_forge_buy_legendary_accepts_spirit(pygame_headless):
    """With the perk, ``forge_buy_legendary`` accepts the 'spirit' slot."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    import config as cfg
    state = GameState()
    state.soul_tree = {"extra_equip_slot"}
    state.amber = cfg.FORGE_LEGENDARY_AMBER
    assert forge_buy_legendary(state, "spirit")
    assert "spirit" in state.gear


def test_extra_equip_slot_forge_buy_legendary_rejects_spirit_without_perk(pygame_headless):
    """Without the perk, ``forge_buy_legendary`` rejects the 'spirit' slot."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    import config as cfg
    state = GameState()
    state.amber = cfg.FORGE_LEGENDARY_AMBER
    assert not forge_buy_legendary(state, "spirit")
    assert "spirit" not in state.gear


def test_extra_equip_slot_forge_ui_shows_5th_slot(pygame_headless):
    """The HeroScreen forge panel shows the 5th 'spirit' slot when the perk
    is active (the forge buttons iterate ``effective_gear_slots(state)``,
    so the 5th slot gets a row of buttons). The source-level guard: the
    ``_build_forge_buttons`` and ``_draw_forge_panel`` methods must
    iterate ``effective_gear_slots`` (NOT ``cfg.GEAR_SLOTS``) so the 5th
    slot appears when the perk is active."""
    import inspect
    from ui.screen_hero import HeroScreen
    src_build = inspect.getsource(HeroScreen._build_forge_buttons)
    assert "effective_gear_slots" in src_build, (
        "_build_forge_buttons does not iterate effective_gear_slots -- "
        "the 5th slot's forge buttons are never built")
    src_draw = inspect.getsource(HeroScreen._draw_forge_panel)
    assert "effective_gear_slots" in src_draw, (
        "_draw_forge_panel does not iterate effective_gear_slots -- "
        "the 5th slot's row is never drawn")


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
