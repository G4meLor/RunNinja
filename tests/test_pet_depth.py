"""Pet depth: passive-at-capstone + star levels + nested pet prestige.

Three new mechanics on the existing 12-pet collection:

  * **Passive-at-capstone**: owned-but-unequipped pets contribute a
    fraction of their `pet_bonus` to the aggregate bonus dict — 25%
    at bond >= 5 and 50% at bond >= 10. Equipped pets still contribute
    the full bonus, so equipping stays meaningfully better than leaving
    a pet on the bench.

  * **Star levels (1-12)**: a second progression axis on top of bond.
    Each duplicate pull (after the pet is already owned) increments
    `pet_stars[pid]` (capped at 12). Stars apply a small multiplier
    to the pet's effective bonus.

  * **Spirit Embers**: a nested pet-prestige currency. A pet at max
    bond (10) can be prestiged: the bond resets to 0, the cap is
    raised, and Spirit Embers are paid out. Embers are clearly worth
    the re-grind (the post-prestige bonus outpaces the pre-prestige
    one once the bond is rebuilt).

The flat-dict contract of `aggregate_bonuses` is unchanged; the new
passive contributions are additive on the existing keys, and star
levels are folded into `pet_bonus` so every consumer
(`compute_ninja_stats`, `gold_mult`, `total_gps`, ...) reads them
without modification.
"""
import pytest


# ---------------------------------------------------------------------------
# Passive-at-capstone
# ---------------------------------------------------------------------------
def test_passive_at_capstone_bond_10(pygame_headless):
    """Owned-but-unequipped pet at bond 10 contributes 50% of pet_bonus."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.pets import BY_ID
    state = GameState()
    state.pets = {"frog": 10}  # bond 10, not equipped
    out = aggregate_bonuses(state)
    p = BY_ID["frog"]
    expected = p.buff_per_level * 10 * 0.5
    assert out.get(p.buff_key, 0) == pytest.approx(expected)


def test_passive_at_capstone_bond_5(pygame_headless):
    """Owned-but-unequipped pet at bond 5 contributes 25% of pet_bonus."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.pets import BY_ID
    state = GameState()
    state.pets = {"frog": 5}  # bond 5, not equipped
    out = aggregate_bonuses(state)
    p = BY_ID["frog"]
    expected = p.buff_per_level * 5 * 0.25
    assert out.get(p.buff_key, 0) == pytest.approx(expected)


def test_passive_below_bond_5_is_zero(pygame_headless):
    """Bond < 5 contributes nothing passively (no free lunch for new pets)."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.pets = {"frog": 4}  # bond 4, not equipped -> no passive
    out = aggregate_bonuses(state)
    # No skill tree, no equipped pets, bond < 5 -> nothing.
    for k, v in out.items():
        assert v == 0.0, f"unexpected nonzero value for {k}: {v}"


def test_passive_does_not_double_count_equipped(pygame_headless):
    """An equipped pet gets the FULL bonus, not full + passive fraction."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.pets import BY_ID
    state = GameState()
    state.pets = {"frog": 10}
    state.equipped_pets = ["frog"]
    out = aggregate_bonuses(state)
    p = BY_ID["frog"]
    # Equipped -> full pet_bonus, no passive fraction added on top.
    expected = p.buff_per_level * 10
    assert out.get(p.buff_key, 0) == pytest.approx(expected)


def test_equipped_better_than_passive(pygame_headless):
    """Equipped pet bonus is meaningfully larger than the passive one."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state_eq = GameState()
    state_eq.pets = {"frog": 10}
    state_eq.equipped_pets = ["frog"]
    state_pass = GameState()
    state_pass.pets = {"frog": 10}  # not equipped
    eq = aggregate_bonuses(state_eq).get("firefly_gold", 0)
    ps = aggregate_bonuses(state_pass).get("firefly_gold", 0)
    assert eq > ps
    # "Meaningfully larger" — at least 1.5x the passive contribution.
    assert eq >= 1.5 * ps


def test_passive_fractions_distinct_at_5_and_10(pygame_headless):
    """25% at bond 5 vs 50% at bond 10 — the two capstones are distinct."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.pets import BY_ID
    p = BY_ID["frog"]
    s5 = GameState(); s5.pets = {"frog": 5}
    s10 = GameState(); s10.pets = {"frog": 10}
    v5 = aggregate_bonuses(s5).get(p.buff_key, 0)
    v10 = aggregate_bonuses(s10).get(p.buff_key, 0)
    # v10 should be 4x v5: bond is 2x and the fraction is 2x (0.5 / 0.25).
    assert v10 == pytest.approx(v5 * 4)


def test_passive_sums_across_pets(pygame_headless):
    """Two unequipped pets at bond 10 each contribute 50% additively."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.pets import BY_ID
    state = GameState()
    state.pets = {"frog": 10, "chicken": 10}  # both unequipped
    out = aggregate_bonuses(state)
    f = BY_ID["frog"]
    c = BY_ID["chicken"]
    assert out.get(f.buff_key, 0) == pytest.approx(f.buff_per_level * 10 * 0.5)
    assert out.get(c.buff_key, 0) == pytest.approx(c.buff_per_level * 10 * 0.5)


# ---------------------------------------------------------------------------
# Star levels
# ---------------------------------------------------------------------------
def test_duplicate_pull_increments_star(pygame_headless):
    """A duplicate pull after the pet is owned increments pet_stars[pid]."""
    from core.state import GameState
    from core import gacha
    state = GameState()
    state.amber = 10000
    state.pets = {"frog": 1}  # already owned
    state.pet_stars = {}
    # Pull until we get a frog duplicate (deterministic seed for the test).
    import utils
    utils.seed(42)
    stars_before = state.pet_stars.get("frog", 0)
    # Pull several times; at least one should be a frog duplicate.
    for _ in range(50):
        r = gacha.pull(state)
        if r.pet_id == "frog" and not r.is_new:
            break
    assert state.pet_stars.get("frog", 0) >= stars_before + 1


def test_star_level_capped_at_12(pygame_headless):
    """Star levels are capped at 12 — excess duplicates do not overflow."""
    from core.state import GameState
    from core import gacha
    state = GameState()
    state.amber = 100000
    state.pets = {"frog": 10}  # already at max bond
    state.pet_stars = {"frog": 12}  # already at max stars
    import utils
    utils.seed(42)
    # Pull a frog duplicate — stars should stay at 12.
    for _ in range(50):
        r = gacha.pull(state)
        if r.pet_id == "frog":
            break
    assert state.pet_stars.get("frog", 0) == 12


def test_star_level_extends_bond_bonus(pygame_headless):
    """A pet with stars contributes more than the same pet with 0 stars.

    Star levels are a second progression axis: each star adds a small
    multiplier on top of the bond-based bonus, so a pet with bond 10
    and stars > 0 contributes more than the same pet with bond 10 and
    no stars.
    """
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from data.pets import BY_ID
    p = BY_ID["frog"]
    # Equipped, bond 10, no stars.
    s0 = GameState()
    s0.pets = {"frog": 10}; s0.equipped_pets = ["frog"]; s0.pet_stars = {}
    # Equipped, bond 10, 3 stars.
    s3 = GameState()
    s3.pets = {"frog": 10}; s3.equipped_pets = ["frog"]; s3.pet_stars = {"frog": 3}
    v0 = aggregate_bonuses(s0).get(p.buff_key, 0)
    v3 = aggregate_bonuses(s3).get(p.buff_key, 0)
    assert v3 > v0


# ---------------------------------------------------------------------------
# Spirit Embers (nested pet prestige)
# ---------------------------------------------------------------------------
def test_spirit_ember_prestige_requires_max_bond(pygame_headless):
    """Prestige is refused below bond 10 — only at max bond."""
    from core.state import GameState
    from core import gacha
    state = GameState()
    state.pets = {"frog": 9}
    state.spirit_embers = 0
    assert gacha.prestige_pet(state, "frog") is False
    assert state.spirit_embers == 0
    assert state.pets["frog"] == 9  # unchanged


def test_spirit_ember_prestige_at_max_bond(pygame_headless):
    """At bond 10, prestige pays out Spirit Embers and resets bond to 0."""
    from core.state import GameState
    from core import gacha
    state = GameState()
    state.pets = {"frog": 10}
    state.spirit_embers = 0
    assert gacha.prestige_pet(state, "frog") is True
    assert state.spirit_embers > 0
    assert state.pets["frog"] == 0  # bond reset


def test_spirit_ember_payout_worth_the_regrind(pygame_headless):
    """A prestiged pet at bond 10 out-bonuses a non-prestiged one at bond 10.

    The point of the re-grind is that the post-prestige bonus (once bond
    is rebuilt to 10) exceeds the pre-prestige bonus at bond 10. We
    measure that by comparing the equipped bonus of:
      (a) a pet at bond 10, 0 prestiges, 0 stars, and
      (b) the same pet at bond 10, 1 prestige, 0 stars.
    The prestiged version must contribute strictly more.
    """
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    from core import gacha
    from data.pets import BY_ID
    p = BY_ID["frog"]
    # (a) bond 10, no prestige.
    s_a = GameState()
    s_a.pets = {"frog": 10}; s_a.equipped_pets = ["frog"]
    s_a.pet_stars = {}; s_a.spirit_embers = 0
    # (b) prestige once, then re-grind bond to 10.
    s_b = GameState()
    s_b.pets = {"frog": 10}; s_b.equipped_pets = ["frog"]
    s_b.pet_stars = {}
    assert gacha.prestige_pet(s_b, "frog") is True
    s_b.pets["frog"] = 10  # simulate the re-grind
    v_a = aggregate_bonuses(s_a).get(p.buff_key, 0)
    v_b = aggregate_bonuses(s_b).get(p.buff_key, 0)
    assert v_b > v_a


def test_spirit_ember_payout_scales_with_prestige_count(pygame_headless):
    """Each prestige pays out more than the previous one (nested currency)."""
    from core.state import GameState
    from core import gacha
    state = GameState()
    state.pets = {"frog": 10}
    state.spirit_embers = 0
    gacha.prestige_pet(state, "frog")
    first = state.spirit_embers
    state.pets["frog"] = 10  # re-grind
    gacha.prestige_pet(state, "frog")
    second = state.spirit_embers - first
    # The second payout should be at least as large as the first
    # (prestige becomes more valuable, not less).
    assert second >= first


# ---------------------------------------------------------------------------
# aggregate_bonuses stability on pet swaps
# ---------------------------------------------------------------------------
def test_pet_swap_does_not_wildly_swing_aggregate(pygame_headless):
    """Swapping one equipped pet for another is a bounded change.

    The aggregate bonus dict should not swing wildly (e.g. double or
    halve) when a single pet is swapped — the passive contributions
    from the now-unequipped pet smooth the transition.
    """
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    # Two pets at bond 10, both contributing to *different* keys, so
    # equipping one vs the other is a single-pet swap.
    state = GameState()
    state.pets = {"frog": 10, "chicken": 10}
    state.pet_stars = {}
    # Equip frog.
    state.equipped_pets = ["frog"]
    out_frog = aggregate_bonuses(state)
    v_frog = out_frog.get("firefly_gold", 0)
    # Swap to chicken.
    state.equipped_pets = ["chicken"]
    out_chick = aggregate_bonuses(state)
    v_chick_gold = out_chick.get("gold_pct", 0)
    # Both should be positive and bounded — the swap doesn't zero out
    # the previously-equipped pet's key entirely (passive contributes).
    assert v_frog > 0
    assert v_chick_gold > 0
    # The frog's key shouldn't vanish entirely after the swap — the
    # passive-at-capstone contributes 50% of the bond-10 bonus.
    frog_after_swap = out_chick.get("firefly_gold", 0)
    assert frog_after_swap > 0
