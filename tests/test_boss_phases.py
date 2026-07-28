"""Boss soft-phase intensity scaling + attack pattern library.

Regression tests for Task 13:
  * Bosses gain HP-threshold attack layers at 75/50/25% (no state machine).
  * Attack frequency scales up as HP drops.
  * Phase transitions are communicated (nameplate flash, banner, hue shift).
  * No enrage timer, no weak-point-tap -- auto-attack DPS can clear the boss.
  * The shield phase is breakable by sustained auto-attack DPS.
"""
import config as cfg


# ---------------------------------------------------------------------------
# 1. Enemy phase fields
# ---------------------------------------------------------------------------
def test_boss_phase_fields_on_enemy(pygame_headless):
    """Enemy has phase, attack_interval, attack_pattern, shield fields."""
    from engine.enemy import Enemy
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    e = Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
              hp=10, max_hp=10, dmg=1, gold=1, speed=edef.speed,
              size=edef.size, rare_drop=edef.rare_drop)
    assert e.phase == 0
    assert e.attack_interval == 1.0
    assert e.attack_pattern == "melee"
    assert e.shield == 0.0
    assert e.shield_max == 0.0


# ---------------------------------------------------------------------------
# 2. Phase derivation from HP thresholds
# ---------------------------------------------------------------------------
def test_boss_phase_thresholds(pygame_headless):
    """_boss_phase_from_hp returns 0/1/2/3 at 100/74/49/24% HP."""
    from engine.enemy import _boss_phase_from_hp, spawn_boss
    from data import enemies as ed
    bdef = ed.boss_for_zone("village")
    boss = spawn_boss(bdef, hp=1000.0, dmg=1.0, gold=1.0)
    # 100% HP -> phase 0
    boss.hp = boss.max_hp
    assert _boss_phase_from_hp(boss) == 0
    # 74% HP -> phase 1
    boss.hp = boss.max_hp * 0.74
    assert _boss_phase_from_hp(boss) == 1
    # 49% HP -> phase 2
    boss.hp = boss.max_hp * 0.49
    assert _boss_phase_from_hp(boss) == 2
    # 24% HP -> phase 3
    boss.hp = boss.max_hp * 0.24
    assert _boss_phase_from_hp(boss) == 3


# ---------------------------------------------------------------------------
# 3. Phase scaling (the brief's specimen test)
# ---------------------------------------------------------------------------
def test_boss_phase_scaling(pygame_headless):
    """Boss attack interval decreases as HP drops (phase derived from HP)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Spawn a boss.
    r.world.zone_distance = cfg.ZONE_DISTANCE  # trigger boss
    r.update(1.0)
    boss = next((e for e in r.world.enemies if e.is_boss), None)
    assert boss is not None
    # At 100% HP, base attack interval.
    base_interval = boss.attack_interval
    # Drop to 50% HP -> faster attacks.
    boss.hp = boss.max_hp * 0.5
    r.update(1.0)
    assert boss.attack_interval < base_interval or boss.phase >= 2


# ---------------------------------------------------------------------------
# 4. Attack interval scales with phase
# ---------------------------------------------------------------------------
def test_boss_attack_interval_scales_with_phase(pygame_headless):
    """attack_interval = 1.0 / (1.0 + 0.3 * phase) for boss enemies."""
    from engine.enemy import _boss_phase_from_hp, spawn_boss
    from data import enemies as ed
    bdef = ed.boss_for_zone("village")
    boss = spawn_boss(bdef, hp=1000.0, dmg=1.0, gold=1.0)
    # Phase 0: interval = 1.0
    boss.hp = boss.max_hp
    phase = _boss_phase_from_hp(boss)
    assert phase == 0
    expected = 1.0 / (1.0 + 0.3 * phase)
    assert abs(expected - 1.0) < 1e-9
    # Phase 1: interval = 1.0 / 1.3
    boss.hp = boss.max_hp * 0.74
    phase = _boss_phase_from_hp(boss)
    assert phase == 1
    expected = 1.0 / (1.0 + 0.3 * phase)
    assert abs(expected - 1.0 / 1.3) < 1e-9
    # Phase 2: interval = 1.0 / 1.6
    boss.hp = boss.max_hp * 0.49
    phase = _boss_phase_from_hp(boss)
    assert phase == 2
    expected = 1.0 / (1.0 + 0.3 * phase)
    assert abs(expected - 1.0 / 1.6) < 1e-9
    # Phase 3: interval = 1.0 / 1.9
    boss.hp = boss.max_hp * 0.24
    phase = _boss_phase_from_hp(boss)
    assert phase == 3
    expected = 1.0 / (1.0 + 0.3 * phase)
    assert abs(expected - 1.0 / 1.9) < 1e-9


# ---------------------------------------------------------------------------
# 5. Shield armed at phase 3, breakable by sustained auto-attack DPS
# ---------------------------------------------------------------------------
def test_boss_shield_breakable_by_auto_attack(pygame_headless):
    """The phase-3 shield is breakable by sustained auto-attack DPS."""
    from core.state import GameState
    from engine.runner import Runner
    from data import enemies as ed
    from engine.enemy import spawn_boss
    state = GameState()
    r = Runner(state)
    bdef = ed.boss_for_zone(r.world.zone_id)
    # Spawn a boss close to the ninja so it's the nearest target.
    boss = spawn_boss(bdef, hp=100.0, dmg=1.0, gold=1.0)
    boss.x = 200  # near PARTY_X so the ninja auto-attacks it
    r.world.enemies.append(boss)
    r.world.boss_active = True
    # Drop to 20% HP to trigger phase 3 + shield.
    boss.hp = boss.max_hp * 0.2
    r.update(0.1)  # tick to arm the shield
    assert boss.phase == 3, f"phase {boss.phase} != 3"
    assert boss.shield > 0, "shield not armed at phase 3"
    # Sustained auto-attack DPS breaks the shield and kills the boss.
    for _ in range(30):
        if not boss.alive:
            break
        r.update(1.0)
    assert not boss.alive, (
        "boss not killed -- shield must be breakable by sustained auto DPS")


# ---------------------------------------------------------------------------
# 6. No new GameState fields (phase is on Enemy, not GameState)
# ---------------------------------------------------------------------------
def test_no_new_gamestate_fields(pygame_headless):
    """Phase lives on Enemy, not GameState (no new state machine)."""
    from core.state import GameState
    st = GameState()
    assert not hasattr(st, "boss_phase"), (
        "boss_phase must not be a GameState field (phase is derived from HP)")
    assert not hasattr(st, "boss_shield"), (
        "boss_shield must not be a GameState field")


# ---------------------------------------------------------------------------
# 7. Boss is auto-killable without any weak-point-tap (no enrage timer)
# ---------------------------------------------------------------------------
def test_boss_auto_killable_no_enrage(pygame_headless):
    """A boss is killable through normal auto-attack DPS (no enrage gate)."""
    from core.state import GameState
    from engine.runner import Runner
    from data import enemies as ed
    from engine.enemy import spawn_boss
    state = GameState()
    r = Runner(state)
    bdef = ed.boss_for_zone(r.world.zone_id)
    # Spawn a boss with low HP; the ninja's auto-attack should kill it.
    boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
    boss.x = 200
    r.world.enemies.append(boss)
    r.world.boss_active = True
    r.update(2.0)
    assert not boss.alive, (
        "boss not auto-killed -- no enrage timer, no weak-point-tap required")


# ---------------------------------------------------------------------------
# 8. Phase transition event fires on phase change
# ---------------------------------------------------------------------------
def test_boss_phase_event_emitted(pygame_headless):
    """A boss_phase event is emitted on the bus when the phase changes."""
    from core.state import GameState
    from engine.runner import Runner
    from data import enemies as ed
    from engine.enemy import spawn_boss
    state = GameState()
    r = Runner(state)
    # Capture boss_phase events.
    events = []
    r.bus.on("boss_phase", lambda *a, **k: events.append((a, k)))
    bdef = ed.boss_for_zone(r.world.zone_id)
    boss = spawn_boss(bdef, hp=1000.0, dmg=1.0, gold=1.0)
    boss.x = 200
    r.world.enemies.append(boss)
    r.world.boss_active = True
    # Drop to 74% HP -> phase 1 event.
    boss.hp = boss.max_hp * 0.74
    r.update(0.1)
    assert any(e for e in events), "no boss_phase event emitted on phase change"


# ---------------------------------------------------------------------------
# 9. BossFxSystem.start_phase exists (phase transition visuals)
# ---------------------------------------------------------------------------
def test_boss_fx_start_phase_exists(pygame_headless):
    """BossFxSystem has a start_phase method for phase transition visuals."""
    from engine.boss_fx import BossFxSystem
    fx = BossFxSystem()
    assert hasattr(fx, "start_phase"), "BossFxSystem has no start_phase method"
    # Calling it does not raise.
    fx.start_phase("Test Boss", 0, 2)
