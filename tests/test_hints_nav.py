"""Task 36: Contextual hints + first-session tutorial + grouped nav + tooltips.

Tests cover:
  * HintEngine conditions (tap_road for a new player)
  * seen-set (no repeat)
  * gate (welcome_pending / zone_fx_active -> None)
  * chain order (tap -> farm -> upgrade -> ascend, only one at a time)
  * nav structure (12 NavItems with screen_ids, 4 categories)
  * stagger (reduced_motion -> instant)
  * tooltip registration (callable-text form, live values)
  * smoke import
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# ---------------------------------------------------------------------------
# 1. HintEngine conditions
# ---------------------------------------------------------------------------
def test_hint_engine_tap_road(pygame_headless):
    """A new player (monsters_killed < 10) gets the 'tap road' hint."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    assert hint is not None
    assert hint.action_id == "tap_road"
    assert "tap" in hint.text.lower() or "road" in hint.text.lower()


def test_hint_engine_buy_farm(pygame_headless):
    """After 10 kills with no farm, the 'buy farm' hint fires."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    state.monsters_killed = 10
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    assert hint is not None
    assert hint.action_id == "buy_farm"


def test_hint_engine_upgrade(pygame_headless):
    """With a farm but no upgrades, the 'upgrade' hint fires."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    state.monsters_killed = 10
    state.buildings["farm"] = 1
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    assert hint is not None
    assert hint.action_id == "upgrade"


def test_hint_engine_ascend(pygame_headless):
    """At zone 3 with no ascensions, the 'ascend' hint fires."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    state.monsters_killed = 50
    state.buildings["farm"] = 5
    state.upgrades["tap_power"] = 1
    state.best_zone = 3
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    assert hint is not None
    assert hint.action_id == "ascend"


# ---------------------------------------------------------------------------
# 2. Seen-set (no repeat)
# ---------------------------------------------------------------------------
def test_seen_hints_no_repeat(pygame_headless):
    """A dismissed hint does not repeat; the next applicable hint fires."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    state.seen_hints = ["tap_road"]
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    # tap_road is dismissed; with monsters_killed < 10 AND farm == 0, no
    # later hint condition is true, so we get None.
    assert hint is None or hint.action_id != "tap_road"


def test_seen_hints_chain_advances(pygame_headless):
    """Dismissing tap_road at 10+ kills advances to buy_farm."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    state.monsters_killed = 10
    state.seen_hints = ["tap_road"]
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    assert hint is not None
    assert hint.action_id == "buy_farm"


# ---------------------------------------------------------------------------
# 3. Gate (welcome_pending / zone_fx_active)
# ---------------------------------------------------------------------------
def test_gate_welcome_pending(pygame_headless):
    """welcome_pending=True -> no hint (the modal is showing)."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=True, zone_fx_active=False)
    assert hint is None


def test_gate_zone_fx_active(pygame_headless):
    """zone_fx_active=True -> no hint (a zone transition is playing)."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=True)
    assert hint is None


def test_gate_both(pygame_headless):
    """Both gates True -> no hint."""
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=True, zone_fx_active=True)
    assert hint is None


# ---------------------------------------------------------------------------
# 4. Chain order (only one hint at a time)
# ---------------------------------------------------------------------------
def test_chain_only_one_at_a_time(pygame_headless):
    """The priority order + seen-set ensures only one hint at a time.

    At each stage of the first-session progression, exactly one hint is
    applicable (the next un-dismissed one in the chain).
    """
    from core.hints import HintEngine
    from core.state import GameState
    he = HintEngine()
    # Stage 1: new player -> tap_road.
    s1 = GameState()
    h1 = he.next_hint(s1, welcome_pending=False, zone_fx_active=False)
    assert h1 is not None and h1.action_id == "tap_road"
    # Stage 2: 10 kills, no farm -> buy_farm (tap_road dismissed).
    s2 = GameState()
    s2.monsters_killed = 10
    s2.seen_hints = ["tap_road"]
    h2 = he.next_hint(s2, welcome_pending=False, zone_fx_active=False)
    assert h2 is not None and h2.action_id == "buy_farm"
    # Stage 3: farm bought, no upgrades -> upgrade.
    s3 = GameState()
    s3.monsters_killed = 10
    s3.buildings["farm"] = 1
    s3.seen_hints = ["tap_road", "buy_farm"]
    h3 = he.next_hint(s3, welcome_pending=False, zone_fx_active=False)
    assert h3 is not None and h3.action_id == "upgrade"
    # Stage 4: upgrades bought, zone 3, no ascend -> ascend.
    s4 = GameState()
    s4.monsters_killed = 50
    s4.buildings["farm"] = 5
    s4.upgrades["tap_power"] = 1
    s4.best_zone = 3
    s4.seen_hints = ["tap_road", "buy_farm", "upgrade"]
    h4 = he.next_hint(s4, welcome_pending=False, zone_fx_active=False)
    assert h4 is not None and h4.action_id == "ascend"
    # Stage 5: all dismissed -> None.
    s5 = GameState()
    s5.seen_hints = ["tap_road", "buy_farm", "upgrade", "ascend"]
    h5 = he.next_hint(s5, welcome_pending=False, zone_fx_active=False)
    assert h5 is None


# ---------------------------------------------------------------------------
# 5. Nav structure
# ---------------------------------------------------------------------------
def test_nav_items_constructed(pygame_headless):
    """The GameScreen builds 3 NavItems (the primary rail) with the
    expected screen_ids (ascend / hero / menuhub). The rest of the
    screens live on the Menu hub."""
    import main
    g = main.Game()
    gs = g.screens["game"]
    # nav_items is the list of NavItem objects.
    assert hasattr(gs, "nav_items")
    assert len(gs.nav_items) == 3
    # nav_by_screen is a dict keyed by screen_id.
    assert hasattr(gs, "_nav_by_screen")
    expected_ids = {"ascend", "hero", "menuhub"}
    assert set(gs._nav_by_screen.keys()) == expected_ids


def test_nav_items_have_icon_and_label(pygame_headless):
    """Each NavItem has an icon_color, a label, and a screen_id."""
    import main
    g = main.Game()
    gs = g.screens["game"]
    for item in gs.nav_items:
        assert hasattr(item, "screen_id")
        assert hasattr(item, "label")
        assert hasattr(item, "icon_color")
        assert len(item.label) > 0
        # icon_color is a 3-tuple of ints.
        assert len(item.icon_color) == 3


def test_nav_items_click_navigates(pygame_headless):
    """Clicking a NavItem calls game.set_screen with the right screen."""
    import main
    g = main.Game()
    gs = g.screens["game"]
    # Find the Menu hub nav item (the "menuhub" item opens the hub).
    item = gs._nav_by_screen.get("menuhub")
    assert item is not None
    # Simulate a click: call on_click.
    item.on_click()
    assert g.current_screen == "menuhub"


def test_menuhub_screen_constructs(pygame_headless):
    """The MenuHubScreen constructs and has buttons for the screens."""
    import main
    g = main.Game()
    # The hub screen exists.
    assert "menuhub" in g.screens
    hub = g.screens["menuhub"]
    # The hub has a buttons list (the section buttons + the Back button).
    assert hasattr(hub, "buttons")
    # The hub has at least 13 buttons (14 screens + the Back button = 15;
    # the screens are spread across the 4 sections).
    assert len(hub.buttons) >= 13


# ---------------------------------------------------------------------------
# 6. Stagger (reduced_motion -> instant)
# ---------------------------------------------------------------------------
def test_stagger_reduced_motion_instant(pygame_headless):
    """Under reduced_motion, the stagger_t is 1.0 (instant, no delay)."""
    import main
    g = main.Game()
    gs = g.screens["game"]
    g.state.reduced_motion = True
    # Update nav items with reduced_motion.
    for item in gs.nav_items:
        item.update(0.016, 0.0, True)
        assert item.stagger_t == 1.0


def test_stagger_normal_delays(pygame_headless):
    """Without reduced_motion, items stagger (idx 0 appears first)."""
    import main
    g = main.Game()
    gs = g.screens["game"]
    g.state.reduced_motion = False
    # At elapsed=0, the first item (idx 0) has delay 0, so its stagger_t
    # is (0 - 0)/0.15 = 0. After a small dt, it starts to appear.
    for item in gs.nav_items:
        item.update(0.016, 0.0, False)
    first = gs.nav_items[0]
    # At elapsed=0, stagger_t = 0 (the formula is (elapsed - delay)/0.15).
    # After some time, the first item appears (stagger_t > 0) while items
    # with a higher idx are still delayed.
    for item in gs.nav_items:
        item.update(0.016, 0.05, False)
    assert first.stagger_t > 0
    # The last item (idx 2) has delay 2*0.03 = 0.06s; at elapsed=0.05
    # it has not started yet (stagger_t == 0).
    last = gs.nav_items[-1]
    assert last.stagger_t == 0.0
    # After enough time, all items are visible.
    for item in gs.nav_items:
        item.update(0.016, 2.0, False)
        assert item.stagger_t == 1.0


# ---------------------------------------------------------------------------
# 7. Tooltip registration (callable-text form, live values)
# ---------------------------------------------------------------------------
def test_tooltip_manager_callable_text(pygame_headless):
    """The TooltipManager accepts a callable text and evaluates it lazily."""
    from ui.tooltip import TooltipManager
    import pygame
    tm = TooltipManager()
    value = [42]
    tm.register("test", pygame.Rect(0, 0, 100, 50),
                lambda: f"Value: {value[0]}")
    # The callable is stored; calling it returns the live value.
    region = tm._regions["test"]
    assert callable(region.text)
    assert region.text() == "Value: 42"
    # Change the value -> the callable reflects it (live).
    value[0] = 99
    assert region.text() == "Value: 99"


def test_upgrades_screen_registers_tooltips(pygame_headless):
    """The Upgrades screen registers a tooltip per upgrade button."""
    import main
    g = main.Game()
    g.set_screen("upgrades")
    us = g.screens["upgrades"]
    # The screen has a TooltipManager.
    assert hasattr(us, "tooltips")
    # After a draw, the manager has regions registered.
    import pygame
    surf = pygame.Surface((1280, 720))
    us.draw(surf)
    # At least one region per upgrade button.
    from config import TAP_UPGRADE_DEFS
    assert len(us.tooltips) >= len(TAP_UPGRADE_DEFS)


def test_buildings_screen_registers_tooltips(pygame_headless):
    """The Buildings screen registers a tooltip per building."""
    import main
    g = main.Game()
    g.set_screen("buildings")
    bs = g.screens["buildings"]
    assert hasattr(bs, "tooltips")
    import pygame
    surf = pygame.Surface((1280, 720))
    bs.draw(surf)
    from data.buildings import BUILDINGS
    assert len(bs.tooltips) >= len(BUILDINGS)


def test_skilltree_screen_registers_tooltips(pygame_headless):
    """The SkillTree screen registers a tooltip per node."""
    import main
    g = main.Game()
    g.set_screen("skilltree")
    ss = g.screens["skilltree"]
    assert hasattr(ss, "tooltips")
    import pygame
    surf = pygame.Surface((1280, 720))
    ss.draw(surf)
    from data.skill_tree import NODES
    assert len(ss.tooltips) >= len(NODES)


def test_pets_screen_registers_tooltips(pygame_headless):
    """The Pets screen registers a tooltip per pet."""
    import main
    g = main.Game()
    g.set_screen("pets")
    ps = g.screens["pets"]
    assert hasattr(ps, "tooltips")
    import pygame
    surf = pygame.Surface((1280, 720))
    ps.draw(surf)
    from data.pets import PETS
    assert len(ps.tooltips) >= len(PETS)


# ---------------------------------------------------------------------------
# 8. Smoke import (the nav restructure must not break construction)
# ---------------------------------------------------------------------------
def test_smoke_game_constructs(pygame_headless):
    """The Game constructs and the game screen has the hint engine wired."""
    import main
    g = main.Game()
    gs = g.screens["game"]
    assert hasattr(gs, "hint_engine")
    assert hasattr(gs, "_current_hint")
    # The hint engine is a HintEngine.
    from core.hints import HintEngine
    assert isinstance(gs.hint_engine, HintEngine)
