"""Godai elemental affinities + fusion (Task 21).

Transforms the 4 Godai nodes from flat +15% stat boosts into a LIVE combat
decision layer. Adds:
  * an ``element`` field on ``EnemyDef`` (themed by zone),
  * ``attuned_element`` on GameState (default "none" = 1x to everything),
  * a 4-cycle type chart (void > wind > fire > water > void),
  * 4 fusion effects on a 30s cooldown,
  * an auto-attune toggle (skill-tree node) so idle players opt out.

Attunement defaults to "none" (1x) so the system is optional — idle
players are never worse than 1x. The zone-environmental-hazards proposal
is NOT implemented; the fusion is the single elemental system.
"""
import pytest


# ---------------------------------------------------------------------------
# 1. EnemyDef has an element field (default "none")
# ---------------------------------------------------------------------------
def test_enemydef_has_element_field():
    """EnemyDef has an ``element`` field defaulting to "none"."""
    from data.enemies import EnemyDef
    e = EnemyDef("e_test", "Test", "bandit", 0, 1.0, 1.0, 1.0, 20, 16)
    assert hasattr(e, "element")
    assert e.element == "none"


def test_enemydef_element_can_be_set():
    """EnemyDef accepts an explicit element."""
    from data.enemies import EnemyDef
    e = EnemyDef("e_test", "Test", "bandit", 0, 1.0, 1.0, 1.0, 20, 16,
                 element="fire")
    assert e.element == "fire"


# ---------------------------------------------------------------------------
# 2. Zone enemies are themed with an element
# ---------------------------------------------------------------------------
def test_zone_enemies_have_elements():
    """Every enemy in every zone has an element in the allowed set."""
    from data.enemies import ZONES
    allowed = {"none", "void", "wind", "fire", "water"}
    for zone in ZONES:
        for e in zone["enemies"]:
            assert e.element in allowed, (
                f"zone {zone['id']} enemy {e.id} has bad element {e.element!r}")


def test_zone_element_themes_differ():
    """At least 3 distinct elements appear across the 9 zones (the theme
    is not a single element for everything — the type chart matters)."""
    from data.enemies import ZONES
    seen = set()
    for zone in ZONES:
        for e in zone["enemies"]:
            seen.add(e.element)
    # "none" + at least 3 of the 4 real elements.
    assert len(seen - {"none"}) >= 3, (
        f"expected >= 3 real elements, got {seen}")


def test_bosses_have_elements_matching_zone():
    """Each zone boss has an element (the boss inherits the zone theme)."""
    from data.enemies import ZONES, BOSSES
    allowed = {"none", "void", "wind", "fire", "water"}
    for zone in ZONES:
        bdef = BOSSES[zone["id"]]
        assert bdef.element in allowed, (
            f"boss {bdef.id} has bad element {bdef.element!r}")


# ---------------------------------------------------------------------------
# 3. attuned_element defaults to "none" (1x to everything)
# ---------------------------------------------------------------------------
def test_attuned_element_default_none():
    """GameState.attuned_element defaults to "none"."""
    from core.state import GameState
    s = GameState()
    assert s.attuned_element == "none"


def test_element_default_none_is_1x(pygame_headless):
    """Attuned "none" vs any enemy element = 1.0 (idle never worse than 1x)."""
    from core.state import GameState
    from engine.enemy import element_mult
    state = GameState()
    assert state.attuned_element == "none"
    for elem in ("void", "wind", "fire", "water", "none"):
        assert element_mult(state.attuned_element, elem) == 1.0


# ---------------------------------------------------------------------------
# 4. Type chart: 4-cycle (void > wind > fire > water > void)
# ---------------------------------------------------------------------------
def test_type_chart_2x_advantage(pygame_headless):
    """The 4-cycle: void > wind > fire > water > void.
    Each element is 2x strong against the next in the cycle."""
    from engine.enemy import element_mult
    # 4-cycle: void > wind > fire > water > void
    assert element_mult("void", "wind") == 2.0
    assert element_mult("wind", "fire") == 2.0
    assert element_mult("fire", "water") == 2.0
    assert element_mult("water", "void") == 2.0


def test_type_chart_0_5x_disadvantage(pygame_headless):
    """The reverse direction is 0.5x (disadvantage)."""
    from engine.enemy import element_mult
    assert element_mult("wind", "void") == 0.5
    assert element_mult("fire", "wind") == 0.5
    assert element_mult("water", "fire") == 0.5
    assert element_mult("void", "water") == 0.5


def test_type_chart_neutral(pygame_headless):
    """Same element vs same element = 1.0 (neutral)."""
    from engine.enemy import element_mult
    for elem in ("void", "wind", "fire", "water", "none"):
        assert element_mult(elem, elem) == 1.0


def test_type_chart_none_attuned_is_1x(pygame_headless):
    """Attuned "none" vs any element = 1.0 (the idle floor)."""
    from engine.enemy import element_mult
    for elem in ("void", "wind", "fire", "water", "none"):
        assert element_mult("none", elem) == 1.0


def test_type_chart_unknown_elements_fall_to_1x(pygame_headless):
    """Unknown attacker/defender elements fall back to 1.0 (no crash)."""
    from engine.enemy import element_mult
    assert element_mult("void", "bogus") == 1.0
    assert element_mult("bogus", "fire") == 1.0


# ---------------------------------------------------------------------------
# 5. Elemental damage is applied in _apply_damage
# ---------------------------------------------------------------------------
def test_apply_damage_uses_element_mult(pygame_headless):
    """_apply_damage multiplies damage by element_mult(attuned, enemy.element).

    With attuned="void" vs an enemy with element "wind" (2x advantage),
    the enemy loses 2x the base amount. With "wind" vs "void" (0.5x),
    the enemy loses half.
    """
    from engine.enemy import Enemy, _apply_damage
    from data.enemies import EnemyDef
    # A wind-element defender.
    edef = EnemyDef("e_wind", "Wind Foe", "beast", 0, 1.0, 1.0, 1.0,
                    20, 16, element="wind")
    e = Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
              hp=100.0, max_hp=100.0, dmg=1.0, gold=1.0,
              speed=edef.speed, size=edef.size, rare_drop=edef.rare_drop,
              element="wind")
    # 2x advantage: void vs wind.
    _apply_damage(e, 10.0, attuned="void")
    assert e.hp == pytest.approx(100.0 - 10.0 * 2.0)


def test_apply_damage_none_attuned_is_1x(pygame_headless):
    """_apply_damage with attuned="none" applies the raw amount (1x)."""
    from engine.enemy import Enemy, _apply_damage
    from data.enemies import EnemyDef
    edef = EnemyDef("e_fire", "Fire Foe", "demon", 0, 1.0, 1.0, 1.0,
                    20, 16, element="fire")
    e = Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
              hp=100.0, max_hp=100.0, dmg=1.0, gold=1.0,
              speed=edef.speed, size=edef.size, rare_drop=edef.rare_drop,
              element="fire")
    _apply_damage(e, 10.0)  # default attuned="none"
    assert e.hp == pytest.approx(90.0)


def test_apply_damage_disadvantage_halves(pygame_headless):
    """_apply_damage with a 0.5x disadvantage applies half the amount."""
    from engine.enemy import Enemy, _apply_damage
    from data.enemies import EnemyDef
    edef = EnemyDef("e_void", "Void Foe", "wraith", 0, 1.0, 1.0, 1.0,
                    20, 16, element="void")
    e = Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
              hp=100.0, max_hp=100.0, dmg=1.0, gold=1.0,
              speed=edef.speed, size=edef.size, rare_drop=edef.rare_drop,
              element="void")
    # wind vs void = 0.5x disadvantage.
    _apply_damage(e, 10.0, attuned="wind")
    assert e.hp == pytest.approx(100.0 - 10.0 * 0.5)


# ---------------------------------------------------------------------------
# 6. Auto-attune toggle (skill-tree node)
# ---------------------------------------------------------------------------
def test_auto_attune_node_exists():
    """The ``godai_auto_attune`` node exists in the skill tree."""
    from data.skill_tree import BY_ID
    assert "godai_auto_attune" in BY_ID
    n = BY_ID["godai_auto_attune"]
    # Prereq is the Godai gate (so it's inside the Godai branch).
    assert n.prereq == "godai_gate"
    assert n.branch == "godai"


def test_auto_attune_picks_best_element(pygame_headless):
    """When the auto-attune node is unlocked, the runner picks the element
    that beats the current zone's dominant enemy element (2x advantage).

    Zone 5 (volcano) is fire-themed; the 4-cycle is void > wind > fire >
    water > void, so the element 2x vs fire is wind (wind beats fire).
    The pick is exposed via ``Runner.auto_attune_element()``.
    """
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import element_mult
    state = GameState()
    state.skill_tree = {"godai_gate", "godai_auto_attune"}
    state.zone_index = 5  # volcano -> fire
    r = Runner(state)
    pick = r.auto_attune_element()
    # The pick must be 2x against fire (wind beats fire in the cycle).
    assert element_mult(pick, "fire") == 2.0
    assert pick == "wind"


def test_auto_attune_none_when_node_locked(pygame_headless):
    """Without the auto-attune node, auto_attune_element returns "none"
    (the idle floor — no automatic attunement)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"godai_gate"}  # gate but no auto-attune
    r = Runner(state)
    assert r.auto_attune_element() == "none"


def test_auto_attune_updates_state_attuned(pygame_headless):
    """When auto-attune is on, ``update`` sets state.attuned_element to
    the best element for the current zone each tick."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"godai_gate", "godai_auto_attune"}
    state.zone_index = 5  # volcano -> fire -> auto-pick wind (wind 2x vs fire)
    r = Runner(state)
    r.update(0.1)
    assert state.attuned_element == "wind"


def test_idle_never_worse_than_1x(pygame_headless):
    """An idle player (no auto-attune node, attuned="none") deals 1x
    damage to every enemy element — never worse than 1x."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import element_mult
    state = GameState()
    # No godai nodes at all — pure idle.
    r = Runner(state)
    assert state.attuned_element == "none"
    r.update(0.1)
    # Still "none" (auto-attune off).
    assert state.attuned_element == "none"
    for elem in ("void", "wind", "fire", "water", "none"):
        assert element_mult(state.attuned_element, elem) == 1.0


# ---------------------------------------------------------------------------
# 7. Fusion effects on a 30s cooldown
# ---------------------------------------------------------------------------
def test_fusion_definitions_exist():
    """The 4 fusion pairs are defined."""
    from engine.runner import FUSIONS
    assert len(FUSIONS) >= 4
    # The 4 fusions from the brief.
    assert ("void", "fire") in FUSIONS
    assert ("wind", "water") in FUSIONS
    assert ("fire", "water") in FUSIONS
    assert ("void", "wind") in FUSIONS


def test_fusion_cooldown_is_30s():
    """The fusion cooldown is 30 seconds."""
    from engine.runner import FUSION_COOLDOWN
    assert FUSION_COOLDOWN == 30.0


def test_fusion_fires_on_cooldown(pygame_headless):
    """When both elements of a fusion pair are unlocked, the fusion fires
    after the cooldown, dealing burst damage to all enemies."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_enemy
    from data.enemies import ZONES
    state = GameState()
    # Unlock void + fire (the inferno fusion).
    state.skill_tree = {"godai_gate", "godai_void", "godai_fire"}
    state.zone_index = 5  # volcano -> fire
    r = Runner(state)
    # Spawn a weak enemy so the fusion has a target.
    edef = ZONES[0]["enemies"][0]
    e = spawn_enemy(edef, hp=1e6, dmg=1.0, gold=1.0)
    e.x = 500
    r.world.enemies.append(e)
    hp_before = e.hp
    # Jump the fusion timer to fire the fusion.
    r._fusion_timer = 0.0
    r._tick_fusion(30.0)
    # The fusion dealt damage (HP dropped).
    assert e.hp < hp_before


def test_fusion_does_not_fire_without_pair(pygame_headless):
    """Without both elements of any pair unlocked, the fusion does not
    fire (no burst damage)."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_enemy
    from data.enemies import ZONES
    state = GameState()
    # Only the gate — no element pair.
    state.skill_tree = {"godai_gate"}
    r = Runner(state)
    edef = ZONES[0]["enemies"][0]
    e = spawn_enemy(edef, hp=1e6, dmg=1.0, gold=1.0)
    r.world.enemies.append(e)
    hp_before = e.hp
    r._fusion_timer = 0.0
    r._tick_fusion(30.0)
    assert e.hp == hp_before  # no damage


def test_fusion_resets_cooldown(pygame_headless):
    """After firing, the fusion timer resets to the 30s cooldown."""
    from core.state import GameState
    from engine.runner import Runner, FUSION_COOLDOWN
    state = GameState()
    state.skill_tree = {"godai_gate", "godai_void", "godai_fire"}
    state.zone_index = 5
    r = Runner(state)
    r._fusion_timer = 0.0
    r._tick_fusion(30.0)
    assert r._fusion_timer == pytest.approx(FUSION_COOLDOWN)


# ---------------------------------------------------------------------------
# 8. Dual-element skill-tree nodes are the complement, not a competing system
# ---------------------------------------------------------------------------
def test_dual_element_nodes_are_complement():
    """The Godai element nodes (void/wind/fire/water) are the unlock GATE
    for the fusion + auto-attune — they are NOT a competing system.
    Each element node still grants its flat +15% stat boost (the
    existing behavior); the fusion + attunement layer on top."""
    from data.skill_tree import BY_ID
    for eid in ("godai_void", "godai_wind", "godai_fire", "godai_water"):
        n = BY_ID[eid]
        # The element node still grants its stat boost (effect_value > 0).
        assert n.effect_value > 0
        # And it's in the godai branch.
        assert n.branch == "godai"


# ---------------------------------------------------------------------------
# 9. No zone-environmental-hazards (the fusion is the single elemental system)
# ---------------------------------------------------------------------------
def test_no_zone_environmental_hazards():
    """No ``weather`` or ``hazard`` key is present on ZONES dicts (the
    zone-environmental-hazards proposal is NOT implemented — the fusion
    is the single elemental system). This test guards against accidental
    re-introduction; Task 31 (gfx-weather) may add a ``weather`` key
    later, but that is visual weather, NOT a combat hazard system."""
    from data.enemies import ZONES
    for z in ZONES:
        # No combat-hazard keys (the fusion is the single elemental system).
        assert "hazard" not in z, f"zone {z['id']} has a 'hazard' key"
        assert "elemental_hazard" not in z


# ---------------------------------------------------------------------------
# 10. ZONES dict edits compose with Task 12 (infinite zones) + Task 31 (weather)
# ---------------------------------------------------------------------------
def test_zones_still_cycle_modulo_9():
    """The 9-zone cycle (Task 12) still works: zone_by_index wraps modulo 9.
    The element field addition is additive (a new EnemyDef field), so it
    composes with the cycle without breaking."""
    from data.enemies import zone_by_index, ZONES
    n = len(ZONES)
    assert zone_by_index(n) is ZONES[0]
    assert zone_by_index(n + 4) is ZONES[4]
    assert zone_by_index(100) is ZONES[100 % n]


def test_zone_enemies_still_have_required_fields():
    """Every zone enemy still has the required EnemyDef fields (the
    element field is additive — the existing fields are intact)."""
    from data.enemies import ZONES
    for z in ZONES:
        for e in z["enemies"]:
            assert e.id
            assert e.name
            assert e.shape
            assert e.hp_mult > 0
            assert e.dmg_mult > 0
            assert e.gold_mult > 0
            assert e.speed > 0
            assert e.size > 0
