"""BonusProvider registry: aggregate_bonuses uses a registry of providers.

Each source registers a ``callable(state) -> dict[str, float]``;
``aggregate_bonuses`` merges all registered providers into the flat
``{effect_key: total_value}`` dict the engine reads. The flat-dict
contract is unchanged so every consumer (compute_ninja_stats, gold_mult,
total_gps, etc.) works unmodified.
"""
import pytest


def test_aggregate_bonuses_unchanged_contract(pygame_headless):
    """The flat-dict contract is preserved: off_root -> tap_pct 0.10."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.skill_tree = {"off_root"}  # +10% tap_pct
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0.0) == pytest.approx(0.10)


def test_skill_tree_provider_registered(pygame_headless):
    """The skill-tree provider is in the registry and contributes."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses, _PROVIDERS, _skill_tree_provider
    assert _skill_tree_provider in _PROVIDERS
    state = GameState()
    state.skill_tree = {"off_root", "off_crit1"}  # tap_pct 0.10 + crit_pct 0.02
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0.0) == pytest.approx(0.10)
    assert out.get("crit_pct", 0.0) == pytest.approx(0.02)


def test_pets_provider_registered(pygame_headless):
    """The pets provider is in the registry and contributes."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses, _PROVIDERS, _pets_provider
    assert _pets_provider in _PROVIDERS
    state = GameState()
    state.pets = {"frog": 5}
    state.equipped_pets = ["frog"]
    out = aggregate_bonuses(state)
    # frog: firefly_gold, 0.05 per bond level -> 0.05 * 5 = 0.25
    assert out.get("firefly_gold", 0.0) == pytest.approx(0.25)


def test_bonus_provider_registry_extensible(pygame_headless):
    """A custom provider can be registered and contributes to the dict."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses, register_provider

    def my_provider(state):
        return {"custom_key": 0.5}

    register_provider(my_provider)
    try:
        out = aggregate_bonuses(GameState())
        assert out.get("custom_key", 0.0) == pytest.approx(0.5)
    finally:
        # Don't leak the custom provider into other tests.
        from core.bonuses import _PROVIDERS
        if my_provider in _PROVIDERS:
            _PROVIDERS.remove(my_provider)


def test_register_provider_idempotent(pygame_headless):
    """Registering the same provider twice does not double-register."""
    from core.bonuses import register_provider, _PROVIDERS

    def my_provider(state):
        return {"idem_key": 1.0}

    register_provider(my_provider)
    n = len(_PROVIDERS)
    register_provider(my_provider)
    assert len(_PROVIDERS) == n
    _PROVIDERS.remove(my_provider)


def test_aggregate_bonuses_merges_all_providers(pygame_headless):
    """Two providers contributing the same key sum additively."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses, register_provider, _PROVIDERS

    def p1(state):
        return {"shared_key": 0.3}

    def p2(state):
        return {"shared_key": 0.4, "only_p2": 0.7}

    register_provider(p1)
    register_provider(p2)
    try:
        out = aggregate_bonuses(GameState())
        assert out.get("shared_key", 0.0) == pytest.approx(0.7)
        assert out.get("only_p2", 0.0) == pytest.approx(0.7)
    finally:
        _PROVIDERS.remove(p1)
        _PROVIDERS.remove(p2)


def test_aggregate_bonuses_empty_state(pygame_headless):
    """Empty state yields an empty (or zero-only) dict."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    out = aggregate_bonuses(GameState())
    # No skill tree, no equipped pets -> no contributions.
    # The dict may be empty or contain only zeros; either is fine as long
    # as no spurious keys appear.
    for k, v in out.items():
        assert v == 0.0, f"unexpected nonzero value for {k}: {v}"


def test_skill_tree_and_pets_provider_stack(pygame_headless):
    """Skill tree + pets both contributing the same key sum additively."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    # chicken: gold_pct 0.015 per bond level -> 0.015 * 3 = 0.045
    state = GameState()
    state.skill_tree = {"eco_root"}  # +10% gold_pct
    state.pets = {"chicken": 3}
    state.equipped_pets = ["chicken"]
    out = aggregate_bonuses(state)
    # Both the skill tree and the pet contribute gold_pct; they sum.
    assert out.get("gold_pct", 0.0) == pytest.approx(0.10 + 0.045)


def test_content_registry_zone_by_id(pygame_headless):
    """zone_by_id looks up by string id and raises KeyError for unknown."""
    from data.enemies import zone_by_id, ZONES
    z = zone_by_id("village")
    assert z["id"] == "village"
    assert z is ZONES[0]
    with pytest.raises(KeyError):
        zone_by_id("does_not_exist")


def test_zone_by_index_no_silent_clamp_for_negative(pygame_headless):
    """zone_by_index raises ValueError for negative indices (no silent clamp)."""
    from data.enemies import zone_by_index
    with pytest.raises(ValueError):
        zone_by_index(-1)


def test_zone_by_index_cycles_past_end(pygame_headless):
    """zone_by_index wraps modulo 9 past the last zone (infinite cycling).

    The 9 themed zones repeat forever at scaled stats; the wrap is
    intentional and documented. An index past the end maps to the
    in-cycle zone (``i % len(ZONES)``), not a clamp to the last zone.
    """
    from data.enemies import zone_by_index, ZONES
    n = len(ZONES)
    assert zone_by_index(n) is ZONES[0]      # cycle 1, in-cycle zone 0
    assert zone_by_index(n + 4) is ZONES[4]  # cycle 1, in-cycle zone 4
    assert zone_by_index(n + 100) is ZONES[100 % n]


def test_max_total_damage_mult_in_config(pygame_headless):
    """MAX_TOTAL_DAMAGE_MULT is defined in config with a sane value."""
    import config as cfg
    assert hasattr(cfg, "MAX_TOTAL_DAMAGE_MULT")
    assert cfg.MAX_TOTAL_DAMAGE_MULT > 0
    # It's a sanity cap — should be large but finite.
    assert cfg.MAX_TOTAL_DAMAGE_MULT == 1e9
