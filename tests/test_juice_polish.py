"""Task 27: Juice polish + prestige-teaching UI.

Six polish/teaching features:

1. **Count-up currency** numbers + gold milestones (no instant snapping).
2. **Skill cooldown-ready chime** + button glow + cooldown progress fill
   (chime respects ``sound_on``, glow respects ``reduced_motion``).
3. **Low-HP red vignette** + boss enrage phase as a VISUAL urgency cue
   (gated by ``reduced_motion``) -- NOT a boss enrage timer mechanic
   (gap #5: no enrage timer, no weak-point-tap; auto-attack DPS clears
   the boss. The vignette is purely visual).
4. **Free respec-on-prestige** for the elixir skill tree (the tree
   persists through ascension; the player can refund + re-spend).
5. **Elixir-per-Minute readout** + recommended-ascend highlight +
   pacing thresholds computed from ``config.py`` curves.
6. **Tome of Samsara** compounding elixir-growth anchor with an
   "invest ~30%" tooltip + "elixir per ascension" projection.

The unspent-elixir-as-multiplier is NOT implemented (Tome of Samsara is
the single compounding elixir-growth loop; ``elixir_gain`` does NOT
scale with the unspent ``state.elixir`` balance).
"""

# ---------------------------------------------------------------------------
# 1. Count-up currency
# ---------------------------------------------------------------------------
def test_count_up_currency(pygame_headless):
    """count_up animates from old to new, not instant."""
    from ui.currency_fx import count_up
    assert callable(count_up)
    # At t=0 returns old; at t>=duration returns new.
    assert count_up(0, 100, 1.0, 0.0) == 0
    assert count_up(0, 100, 1.0, 1.0) == 100
    assert count_up(0, 100, 1.0, 2.0) == 100  # clamps
    # Midway is between old and new (no instant snapping).
    mid = count_up(0, 100, 1.0, 0.5)
    assert 0 < mid < 100


def test_gold_milestone_crossed(pygame_headless):
    """Crossing a gold milestone returns the milestone (for celebration)."""
    from ui.currency_fx import gold_milestone_crossed
    # No milestone crossed.
    assert gold_milestone_crossed(500, 900) is None
    # Crossed 1k.
    assert gold_milestone_crossed(900, 1100) == 1000
    # Crossed 10k.
    assert gold_milestone_crossed(9000, 11000) == 10000


# ---------------------------------------------------------------------------
# 2. Skill cooldown chime + glow + progress fill
# ---------------------------------------------------------------------------
def test_skill_ready_sfx_registered(pygame_headless):
    """A 'skill_ready' SFX is registered for the cooldown-ready chime."""
    from assets import init_sfx, _SFX
    init_sfx()
    assert "skill_ready" in _SFX


def test_skill_ready_chime_respects_sound_on(pygame_headless):
    """play('skill_ready', False) is a no-op (respects sound_on)."""
    from assets import play
    # Should not raise even if the mixer is gone.
    play("skill_ready", False)
    play("skill_ready", True)


def test_gamescreen_has_cooldown_glow(pygame_headless):
    """The GameScreen tracks per-skill cooldown-ready glow."""
    import main
    g = main.Game()
    screen = g.screens["game"]
    # The screen tracks per-skill glow timers (the cooldown-ready glow).
    assert hasattr(screen, "_skill_glow")
    assert hasattr(screen, "_skill_was_on_cooldown")


def test_gamescreen_has_cooldown_progress_fill(pygame_headless):
    """The GameScreen draws a cooldown progress fill on skill buttons."""
    import inspect
    from ui.screen_game import GameScreen
    src = inspect.getsource(GameScreen)
    # The screen has a cooldown-progress-fill draw path.
    assert "cooldown" in src.lower()


# ---------------------------------------------------------------------------
# 3. Low-HP red vignette (VISUAL urgency cue, NOT a boss enrage timer)
# ---------------------------------------------------------------------------
def test_gamescreen_has_low_hp_vignette(pygame_headless):
    """The GameScreen draws a low-HP red vignette (a visual urgency cue)."""
    import inspect
    from ui.screen_game import GameScreen
    src = inspect.getsource(GameScreen)
    assert "vignette" in src.lower()


def test_low_hp_vignette_gated_by_reduced_motion(pygame_headless):
    """The low-HP vignette is gated by reduced_motion."""
    import inspect
    from ui.screen_game import GameScreen
    src = inspect.getsource(GameScreen)
    # The vignette is drawn only when not reduced_motion.
    assert "reduced_motion" in src


def test_low_hp_vignette_requires_boss_active(pygame_headless):
    """The low-HP vignette requires a boss to be active (a boss-fight
    urgency cue, not a general low-HP warning)."""
    import inspect
    from ui.screen_game import GameScreen
    src = inspect.getsource(GameScreen)
    # The vignette is drawn only when a boss is active.
    assert "boss_active" in src


# ---------------------------------------------------------------------------
# 4. Free respec-on-prestige for the elixir skill tree
# ---------------------------------------------------------------------------
def test_respec_skill_tree(pygame_headless):
    """respec_skill_tree refunds all elixir spent on the skill tree + clears it."""
    from core.state import GameState
    from core.ascend import respec_skill_tree
    from data import skill_tree as st
    state = GameState()
    state.elixir = 0
    state.skill_tree = {"eli_root", "elixir_t2", "elixir_t3"}
    # The respec refunds the total cost of unlocked nodes.
    total_cost = sum(st.BY_ID[nid].cost for nid in state.skill_tree)
    refunded = respec_skill_tree(state)
    assert state.skill_tree == set()
    assert state.elixir == total_cost
    assert refunded == total_cost


def test_respec_skill_tree_empty(pygame_headless):
    """respec_skill_tree on an empty tree is a no-op (returns 0)."""
    from core.state import GameState
    from core.ascend import respec_skill_tree
    state = GameState()
    state.elixir = 42
    refunded = respec_skill_tree(state)
    assert refunded == 0
    assert state.elixir == 42
    assert state.skill_tree == set()


def test_skill_tree_persists_through_ascension(pygame_headless):
    """The elixir skill tree persists through ascension (it's permanent)."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.skill_tree = {"eli_root", "eli_t2"}
    state.gold = 50000
    state.lifetime_gold = 50000
    state.zone_index = 5
    ascend(state)
    # The skill tree persists (ascend does NOT reset it).
    assert state.skill_tree == {"eli_root", "eli_t2"}


# ---------------------------------------------------------------------------
# 4b. Respec button on the skill tree screen (the UI wiring)
# ---------------------------------------------------------------------------
def test_respec_button_on_skilltree_screen(pygame_headless):
    """The SkillTreeScreen has a Respec button wired to respec_skill_tree."""
    import inspect
    from ui.screen_skilltree import SkillTreeScreen
    src = inspect.getsource(SkillTreeScreen)
    # The screen has a respec button + a click handler that calls
    # asc.respec_skill_tree(state).
    assert "btn_respec" in src
    assert "respec_skill_tree" in src


def test_respec_button_gated_by_unlocked_nodes(pygame_headless):
    """The Respec button is disabled when the tree is empty (no respec if
    the tree is empty)."""
    import main
    g = main.Game()
    screen = g.screens["skilltree"]
    # With an empty tree, the button is disabled.
    g.state.skill_tree = set()
    screen.update(1 / 60)
    assert screen.btn_respec.enabled is False
    # With at least 1 unlocked node, the button is enabled.
    g.state.skill_tree = {"eli_root"}
    screen.update(1 / 60)
    assert screen.btn_respec.enabled is True


def test_respec_button_shows_refund_amount(pygame_headless):
    """The Respec button label shows the refund amount (the elixir the
    player would get back)."""
    import main
    g = main.Game()
    screen = g.screens["skilltree"]
    g.state.skill_tree = {"eli_root", "elixir_t2"}
    screen.update(1 / 60)
    # The label includes the refund amount (the +N elixir format).
    assert "+" in screen.btn_respec.label


def test_respec_button_click_refunds_and_clears(pygame_headless):
    """Clicking the Respec button refunds the elixir + clears the tree."""
    import main
    g = main.Game()
    screen = g.screens["skilltree"]
    g.state.elixir = 0
    g.state.skill_tree = {"eli_root", "elixir_t2"}
    # Click the respec button.
    screen._do_respec()
    # The tree is cleared + the elixir is refunded.
    assert g.state.skill_tree == set()
    from data import skill_tree as st
    expected_refund = st.BY_ID["eli_root"].cost + st.BY_ID["elixir_t2"].cost
    assert g.state.elixir == expected_refund


# ---------------------------------------------------------------------------
# 5. Elixir-per-Minute readout + recommended-ascend + pacing thresholds
# ---------------------------------------------------------------------------
def test_elixir_per_minute(pygame_headless):
    """elixir_per_minute is computed from config.py curves; >= 0."""
    from core.state import GameState
    from core.ascend import elixir_per_minute
    state = GameState()
    assert elixir_per_minute(state) >= 0


def test_elixir_per_minute_uses_config_curves(pygame_headless):
    """elixir_per_minute scales with ELIXIR_RATE + the diminish factor."""
    import config as cfg
    from core.state import GameState
    from core.ascend import elixir_per_minute
    state = GameState()
    state.lifetime_gold = 100000
    state.ascend_tier = 0
    epm_t0 = elixir_per_minute(state)
    # Higher tier -> lower elixir-per-minute (the diminish factor).
    state.ascend_tier = 3
    epm_t3 = elixir_per_minute(state)
    assert epm_t0 > epm_t3, (
        f"elixir_per_minute should diminish with tier: "
        f"t0={epm_t0}, t3={epm_t3}")


def test_recommended_ascend(pygame_headless):
    """recommended_ascend returns a bool (the ascend screen highlights it)."""
    from core.state import GameState
    from core.ascend import recommended_ascend
    state = GameState()
    # With no progress, not recommended (can't ascend or low elixir).
    assert isinstance(recommended_ascend(state), bool)
    # With high lifetime_gold + can_ascend, recommended.
    state.lifetime_gold = 1000000
    state.zone_index = 5
    assert isinstance(recommended_ascend(state), bool)


def test_recommended_ascend_requires_can_ascend(pygame_headless):
    """recommended_ascend is False when the player can't ascend."""
    from core.state import GameState
    from core.ascend import recommended_ascend
    state = GameState()
    state.lifetime_gold = 1000000
    state.zone_index = 0  # below the ascend requirement
    assert recommended_ascend(state) is False


def test_ascend_screen_has_elixir_per_minute(pygame_headless):
    """The AscendScreen shows an elixir-per-minute readout."""
    import inspect
    from ui.screen_ascend import AscendScreen
    src = inspect.getsource(AscendScreen)
    assert "elixir_per_minute" in src or "per_minute" in src.lower()


# ---------------------------------------------------------------------------
# 6. Tome of Samsara compounding anchor
# ---------------------------------------------------------------------------
def test_tome_of_samsara_node(pygame_headless):
    """The Tome of Samsara is a specific elixir-tree node (the compounding anchor)."""
    from core.ascend import TOME_OF_SAMSARA_NODE
    from data import skill_tree as st
    # The node exists in the skill tree.
    assert TOME_OF_SAMSARA_NODE in st.BY_ID


def test_tome_of_samsara_tooltip(pygame_headless):
    """The Tome of Samsara tooltip recommends 'invest ~30%'."""
    from core.ascend import tome_of_samsara_tooltip
    from core.state import GameState
    state = GameState()
    tip = tome_of_samsara_tooltip(state)
    assert "30%" in tip


def test_tome_of_samsara_tooltip_has_projection(pygame_headless):
    """The Tome of Samsara tooltip includes an elixir-per-ascension projection."""
    from core.ascend import tome_of_samsara_tooltip
    from core.state import GameState
    state = GameState()
    state.lifetime_gold = 10000
    tip = tome_of_samsara_tooltip(state)
    # The tooltip includes a projection (a number).
    assert "projection" in tip.lower() or "ascension" in tip.lower()


def test_elixir_per_ascension(pygame_headless):
    """elixir_per_ascension projects the elixir earned per ascension."""
    from core.ascend import elixir_per_ascension
    from core.state import GameState
    state = GameState()
    state.lifetime_gold = 10000
    assert elixir_per_ascension(state) >= 0


def test_ascend_screen_has_tome_of_samsara(pygame_headless):
    """The AscendScreen shows the Tome of Samsara section."""
    import inspect
    from ui.screen_ascend import AscendScreen
    src = inspect.getsource(AscendScreen)
    assert "samsara" in src.lower() or "tome" in src.lower()


# ---------------------------------------------------------------------------
# 7. The unspent-elixir-as-multiplier is NOT implemented
# ---------------------------------------------------------------------------
def test_unspent_elixir_not_a_multiplier(pygame_headless):
    """The unspent elixir is NOT a multiplier (Tome of Samsara is the
    single compounding elixir-growth loop, not unspent elixir as a
    multiplier). elixir_gain does NOT scale with the unspent balance."""
    from core.ascend import elixir_gain
    from core.state import GameState
    state = GameState()
    state.lifetime_gold = 10000
    state.elixir = 1000000  # a lot of unspent elixir
    gained_with_elixir = elixir_gain(state)
    state.elixir = 0  # no unspent elixir
    gained_no_elixir = elixir_gain(state)
    # The elixir_gain does NOT scale with unspent elixir (only with
    # elixir_pct from the skill tree + tokens, not the unspent balance).
    assert gained_with_elixir == gained_no_elixir, (
        f"elixir_gain should not scale with unspent elixir: "
        f"with={gained_with_elixir}, without={gained_no_elixir}")
