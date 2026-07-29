"""Task 33: Gear Forge UI (enhance/reroll/salvage + amber sink).

The MANAGEMENT half of the gear split (the model is Task 20). Covers:

  * **Forge functions** in ``core/bonuses.py``:
    - ``forge_enhance(state, slot)``: gold sink, increases the gear's value
      (multiply by a factor, capped).
    - ``forge_reroll(state, slot)``: amber sink, rerolls the affix (random
      new affix from the slot's pool, same rarity).
    - ``forge_salvage(state, slot)``: returns amber (a fraction scaled by
      rarity), removes the piece.
    - ``forge_buy_legendary(state, slot)``: amber sink, the Amber-Shop --
      buys a guaranteed legendary gear piece in the slot.

  * **Forge UI** in ``ui/screen_hero.py``: a Forge panel with
    enhance/reroll/salvage buttons + an Amber-Shop for legendaries. No
    affix requires active play -- the Forge is a one-time management
    action like buying buildings.

  * **Amber-Shop**: legendaries are a complementary amber sink INSIDE this
    system (not a separate layer). The buy_legendary function lives in the
    same module as the other forge functions and uses the same gear data
    model.
"""
import pytest


# ---------------------------------------------------------------------------
# Specimen tests from the task brief
# ---------------------------------------------------------------------------
def test_forge_enhance(pygame_headless):
    """forge_enhance: gold sink, increases the gear's value."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 100000
    forge_enhance(state, "blade")
    # Enhance increases the value.
    assert state.gear["blade"]["value"] > 0.1
    assert state.gold < 100000


def test_forge_salvage(pygame_headless):
    """forge_salvage: returns amber, removes the piece."""
    from core.state import GameState
    from core.bonuses import forge_salvage
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    forge_salvage(state, "blade")
    assert "blade" not in state.gear
    assert state.amber > 0 or state.gold > 0  # salvage returns value


# ---------------------------------------------------------------------------
# forge_enhance
# ---------------------------------------------------------------------------
def test_forge_enhance_increases_value(pygame_headless):
    """Enhance multiplies the value by a factor (>1)."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 1_000_000
    old_val = state.gear["blade"]["value"]
    assert forge_enhance(state, "blade") is True
    assert state.gear["blade"]["value"] > old_val


def test_forge_enhance_sinks_gold(pygame_headless):
    """Enhance costs gold (state.gold decreases)."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 1_000_000
    before = state.gold
    forge_enhance(state, "blade")
    assert state.gold < before


def test_forge_enhance_empty_slot(pygame_headless):
    """Enhance on an empty slot is a no-op (returns False)."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    state = GameState()
    state.gold = 1_000_000
    assert forge_enhance(state, "blade") is False
    assert "blade" not in state.gear
    assert state.gold == 1_000_000  # no gold spent


def test_forge_enhance_cannot_afford(pygame_headless):
    """Enhance with insufficient gold is a no-op (returns False)."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 0
    assert forge_enhance(state, "blade") is False
    # The piece is unchanged.
    assert state.gear["blade"]["value"] == 0.1


def test_forge_enhance_capped(pygame_headless):
    """Enhance is capped at FORGE_ENHANCE_MAX_VALUE (no infinite growth)."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    import config as cfg
    state = GameState()
    # Start near the cap.
    state.gear = {"blade": {"affix": "tap_pct",
                            "value": cfg.FORGE_ENHANCE_MAX_VALUE - 0.01,
                            "rarity": "rare"}}
    state.gold = 1_000_000
    forge_enhance(state, "blade")
    # The value is capped (does not exceed the max).
    assert state.gear["blade"]["value"] <= cfg.FORGE_ENHANCE_MAX_VALUE


def test_forge_enhance_maxed_is_noop(pygame_headless):
    """Enhance on a piece already at the cap is a no-op (returns False)."""
    from core.state import GameState
    from core.bonuses import forge_enhance
    import config as cfg
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct",
                            "value": cfg.FORGE_ENHANCE_MAX_VALUE,
                            "rarity": "rare"}}
    state.gold = 1_000_000
    before_gold = state.gold
    assert forge_enhance(state, "blade") is False
    assert state.gold == before_gold  # no gold spent on a maxed piece


# ---------------------------------------------------------------------------
# forge_reroll
# ---------------------------------------------------------------------------
def test_forge_reroll_changes_affix(pygame_headless):
    """Reroll picks a (possibly different) affix from the slot's pool."""
    from core.state import GameState
    from core.bonuses import forge_reroll
    import config as cfg
    # Seed for determinism: with a 3-affix pool, re-rolling 50 times must
    # produce at least one affix change.
    from utils import seed
    seed(42)
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.amber = 10_000
    pool = [a[0] for a in cfg.GEAR_AFFIXES["blade"]]
    assert forge_reroll(state, "blade") is True
    # The new affix is still in the slot's pool.
    assert state.gear["blade"]["affix"] in pool
    # Over many rerolls, the affix should change at least once (the pool
    # has >1 affix, so a reroll that always kept the same affix would be
    # a bug).
    changed = False
    for _ in range(50):
        before = state.gear["blade"]["affix"]
        forge_reroll(state, "blade")
        if state.gear["blade"]["affix"] != before:
            changed = True
            break
    assert changed, "reroll never changed the affix (50 attempts)"


def test_forge_reroll_sinks_amber(pygame_headless):
    """Reroll costs amber (state.amber decreases)."""
    from core.state import GameState
    from core.bonuses import forge_reroll
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.amber = 1000
    before = state.amber
    forge_reroll(state, "blade")
    assert state.amber < before


def test_forge_reroll_keeps_rarity(pygame_headless):
    """Reroll keeps the rarity (only the affix changes)."""
    from core.state import GameState
    from core.bonuses import forge_reroll
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "epic"}}
    state.amber = 10_000
    forge_reroll(state, "blade")
    assert state.gear["blade"]["rarity"] == "epic"


def test_forge_reroll_empty_slot(pygame_headless):
    """Reroll on an empty slot is a no-op (returns False)."""
    from core.state import GameState
    from core.bonuses import forge_reroll
    state = GameState()
    state.amber = 10_000
    assert forge_reroll(state, "blade") is False
    assert state.amber == 10_000  # no amber spent


def test_forge_reroll_cannot_afford(pygame_headless):
    """Reroll with insufficient amber is a no-op (returns False)."""
    from core.state import GameState
    from core.bonuses import forge_reroll
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.amber = 0
    assert forge_reroll(state, "blade") is False
    assert state.gear["blade"]["affix"] == "tap_pct"  # unchanged


def test_forge_reroll_value_scales_with_rarity(pygame_headless):
    """After reroll, the value is base * GEAR_RARITY_MULT[rarity]."""
    from core.state import GameState
    from core.bonuses import forge_reroll
    import config as cfg
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "epic"}}
    state.amber = 10_000
    forge_reroll(state, "blade")
    g = state.gear["blade"]
    base = dict(cfg.GEAR_AFFIXES["blade"])[g["affix"]]
    assert g["value"] == pytest.approx(base * cfg.GEAR_RARITY_MULT["epic"])


# ---------------------------------------------------------------------------
# forge_salvage
# ---------------------------------------------------------------------------
def test_forge_salvage_returns_amber(pygame_headless):
    """Salvage returns amber (a fraction scaled by rarity)."""
    from core.state import GameState
    from core.bonuses import forge_salvage
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.amber = 0
    gained = forge_salvage(state, "blade")
    assert gained > 0
    assert state.amber == gained


def test_forge_salvage_removes_piece(pygame_headless):
    """Salvage removes the piece from state.gear."""
    from core.state import GameState
    from core.bonuses import forge_salvage
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"},
                  "mask": {"affix": "atk_pct", "value": 0.05, "rarity": "common"}}
    forge_salvage(state, "blade")
    assert "blade" not in state.gear
    # Other slots are untouched.
    assert "mask" in state.gear


def test_forge_salvage_empty_slot(pygame_headless):
    """Salvage on an empty slot is a no-op (returns 0)."""
    from core.state import GameState
    from core.bonuses import forge_salvage
    state = GameState()
    state.amber = 5
    assert forge_salvage(state, "blade") == 0
    assert state.amber == 5  # unchanged


def test_forge_salvage_scales_with_rarity(pygame_headless):
    """Salvage amber scales with the piece's rarity (mythic > common)."""
    from core.state import GameState
    from core.bonuses import forge_salvage
    state_a = GameState()
    state_a.gear = {"blade": {"affix": "tap_pct", "value": 0.05,
                              "rarity": "common"}}
    state_b = GameState()
    state_b.gear = {"blade": {"affix": "tap_pct", "value": 0.4,
                              "rarity": "mythic"}}
    a_common = forge_salvage(state_a, "blade")
    a_mythic = forge_salvage(state_b, "blade")
    assert a_mythic > a_common, (
        f"mythic salvage {a_mythic} should exceed common {a_common}")


# ---------------------------------------------------------------------------
# Amber-Shop: forge_buy_legendary
# ---------------------------------------------------------------------------
def test_forge_buy_legendary(pygame_headless):
    """The Amber-Shop buys a guaranteed legendary gear piece for amber."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    state = GameState()
    state.amber = 10_000
    assert forge_buy_legendary(state, "blade") is True
    g = state.gear.get("blade")
    assert g is not None
    assert g["rarity"] == "legendary"


def test_forge_buy_legendary_sinks_amber(pygame_headless):
    """Buying a legendary costs amber (state.amber decreases)."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    state = GameState()
    state.amber = 10_000
    before = state.amber
    forge_buy_legendary(state, "blade")
    assert state.amber < before


def test_forge_buy_legendary_cannot_afford(pygame_headless):
    """Buying a legendary with insufficient amber is a no-op."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    state = GameState()
    state.amber = 0
    assert forge_buy_legendary(state, "blade") is False
    assert "blade" not in state.gear
    assert state.amber == 0


def test_forge_buy_legendary_value(pygame_headless):
    """A bought legendary's value is base * GEAR_RARITY_MULT[legendary]."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    import config as cfg
    state = GameState()
    state.amber = 10_000
    forge_buy_legendary(state, "blade")
    g = state.gear["blade"]
    base = dict(cfg.GEAR_AFFIXES["blade"])[g["affix"]]
    assert g["value"] == pytest.approx(base * cfg.GEAR_RARITY_MULT["legendary"])


def test_forge_buy_legendary_affix_in_pool(pygame_headless):
    """A bought legendary's affix is drawn from the slot's pool."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    import config as cfg
    state = GameState()
    state.amber = 10_000
    forge_buy_legendary(state, "blade")
    pool = [a[0] for a in cfg.GEAR_AFFIXES["blade"]]
    assert state.gear["blade"]["affix"] in pool


def test_forge_buy_legendary_replaces_existing(pygame_headless):
    """Buying a legendary in an occupied slot replaces the old piece."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.05,
                            "rarity": "common"}}
    state.amber = 10_000
    forge_buy_legendary(state, "blade")
    # The piece is now a legendary (replaced the common).
    assert state.gear["blade"]["rarity"] == "legendary"


def test_forge_buy_legendary_invalid_slot(pygame_headless):
    """Buying a legendary in an invalid slot is a no-op."""
    from core.state import GameState
    from core.bonuses import forge_buy_legendary
    state = GameState()
    state.amber = 10_000
    assert forge_buy_legendary(state, "not_a_slot") is False
    assert state.amber == 10_000


# ---------------------------------------------------------------------------
# Forge functions live in core/bonuses.py (not a separate layer)
# ---------------------------------------------------------------------------
def test_forge_functions_in_bonuses_module(pygame_headless):
    """The forge functions live in core.bonuses (same module as the gear
    provider) -- the Amber-Shop is a complementary sink INSIDE this
    system, not a separate layer."""
    from core import bonuses
    for name in ("forge_enhance", "forge_reroll", "forge_salvage",
                 "forge_buy_legendary"):
        assert hasattr(bonuses, name), f"core.bonuses missing {name}"


# ---------------------------------------------------------------------------
# No affix requires active play (the Forge is a one-time management action)
# ---------------------------------------------------------------------------
def test_forge_no_active_play_required(pygame_headless):
    """The forge functions are pure state mutations -- no runner/combat
    required. A fresh GameState (no runner, no combat) can enhance, reroll,
    salvage, and buy a legendary directly."""
    from core.state import GameState
    from core.bonuses import (forge_enhance, forge_reroll, forge_salvage,
                              forge_buy_legendary)
    state = GameState()
    state.gold = 1_000_000
    state.amber = 10_000
    # Buy a legendary (no boss kill required).
    assert forge_buy_legendary(state, "blade")
    # Enhance it (no active play required).
    assert forge_enhance(state, "blade")
    # Reroll it (no active play required).
    assert forge_reroll(state, "blade")
    # Salvage it (returns amber).
    assert forge_salvage(state, "blade") > 0
    assert "blade" not in state.gear


# ---------------------------------------------------------------------------
# Config: forge cost constants
# ---------------------------------------------------------------------------
def test_forge_config_constants(pygame_headless):
    """The forge cost constants exist in config.py."""
    import config as cfg
    for name in ("FORGE_ENHANCE_GOLD", "FORGE_ENHANCE_FACTOR",
                "FORGE_ENHANCE_MAX_VALUE", "FORGE_REROLL_AMBER",
                "FORGE_SALVAGE_AMBER_BASE", "FORGE_LEGENDARY_AMBER"):
        assert hasattr(cfg, name), f"config missing {name}"
    assert cfg.FORGE_ENHANCE_FACTOR > 0
    assert cfg.FORGE_ENHANCE_MAX_VALUE > 0
    assert cfg.FORGE_ENHANCE_GOLD > 0
    assert cfg.FORGE_REROLL_AMBER > 0
    assert cfg.FORGE_SALVAGE_AMBER_BASE > 0
    assert cfg.FORGE_LEGENDARY_AMBER > 0


# ---------------------------------------------------------------------------
# Forge UI in ui/screen_hero.py
# ---------------------------------------------------------------------------
def test_hero_screen_has_forge_panel(pygame_headless):
    """The HeroScreen has a Forge panel (enhance/reroll/salvage + amber shop)."""
    import inspect
    from ui.screen_hero import HeroScreen
    src = inspect.getsource(HeroScreen)
    # The screen has a Forge panel (the toggle + the draw method).
    assert "forge" in src.lower()
    # The four forge actions are wired into the screen.
    for needle in ("enhance", "reroll", "salvage"):
        assert needle in src.lower(), f"HeroScreen missing {needle}"


def test_hero_screen_draws_with_forge_open(pygame_headless):
    """The HeroScreen draws without error with the Forge panel open."""
    import main
    g = main.Game()
    screen = g.screens["hero"]
    # Open the Forge panel.
    if hasattr(screen, "_forge_open"):
        screen._forge_open = True
    # Give the state some gear + currencies so the forge panel has content.
    g.state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    g.state.gold = 1_000_000
    g.state.amber = 1_000
    # Draw the screen (should not raise).
    g.screens["hero"].draw(g.screen)
    # Toggle the forge panel off and draw again.
    if hasattr(screen, "_forge_open"):
        screen._forge_open = False
    g.screens["hero"].draw(g.screen)


def test_hero_screen_forge_toggle_button(pygame_headless):
    """The HeroScreen has a Forge toggle button."""
    import main
    g = main.Game()
    screen = g.screens["hero"]
    # The screen has a Forge button (a Button in the buttons list whose
    # label mentions "Forge").
    labels = [getattr(b, "label", "") for b in screen.buttons]
    assert any("forge" in lbl.lower() for lbl in labels), (
        f"no Forge button in HeroScreen: {labels}")


def test_hero_screen_forge_buttons_for_each_slot(pygame_headless):
    """The HeroScreen has enhance/reroll/salvage buttons per gear slot."""
    import inspect
    from ui.screen_hero import HeroScreen
    src = inspect.getsource(HeroScreen)
    # The screen iterates over GEAR_SLOTS (all 4 slots have forge buttons).
    assert "GEAR_SLOTS" in src or "gear_slots" in src.lower(), (
        "HeroScreen does not iterate over GEAR_SLOTS")


# ---------------------------------------------------------------------------
# CRITICAL: forge buttons must actually respond to clicks. A fresh Button
# has pressed=False; if the buttons were rebuilt on every event, the
# MOUSEBUTTONDOWN (which sets pressed=True) and the MOUSEBUTTONUP (which
# checks pressed) would hit different Button objects and the click would
# never fire. This test simulates a real DOWN+UP pair on a forge button
# rect and asserts the state changed -- the exact gap that let the
# rebuild-on-every-event bug ship.
# ---------------------------------------------------------------------------
def test_forge_enhance_button_click_responds(pygame_headless):
    """Clicking the Enhance button in the open Forge panel sinks gold +
    increases the piece's value."""
    import pygame
    import main
    g = main.Game()
    screen = g.screens["hero"]
    state = g.state
    # Set up: a piece in the blade slot + enough gold to enhance.
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 1_000_000
    state.amber = 1_000
    # Open the Forge panel + rebuild the buttons for the current state.
    screen._forge_open = True
    screen._maybe_rebuild_forge_buttons()
    # Find the Enhance button for the blade slot (first slot, first button
    # in the row: the buttons are built in order Enhance, Reroll, Salvage,
    # Buy Legendary per slot, so index 0 is blade's Enhance).
    btn = screen._forge_btns[0]
    assert btn.label == "Enhance", f"first forge button is {btn.label!r}, expected 'Enhance'"
    assert btn.enabled, "Enhance button is disabled with sufficient gold + a non-maxed piece"
    rect = btn.rect
    center = rect.center
    # Simulate a real click: MOUSEBUTTONDOWN followed by MOUSEBUTTONUP at
    # the same point. The button must retain pressed=True across the two
    # events (the cache is what makes this work -- a fresh button would
    # have pressed=False on the UP event and the click would not fire).
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                              {"pos": center, "button": 1})
    up = pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {"pos": center, "button": 1})
    gold_before = state.gold
    value_before = state.gear["blade"]["value"]
    screen.handle(down)
    # The button is pressed after the DOWN event (same object, cached).
    assert btn.pressed is True, (
        "button.pressed is False after MOUSEBUTTONDOWN -- the button was "
        "rebuilt between events (the cache is broken)")
    screen.handle(up)
    # The click fired: gold sank + the piece's value increased.
    assert state.gold < gold_before, (
        f"gold unchanged after Enhance click: {gold_before} -> {state.gold} "
        "(the on_click did not fire)")
    assert state.gear["blade"]["value"] > value_before, (
        f"blade value unchanged after Enhance click: {value_before} -> "
        f"{state.gear['blade']['value']}")


def test_forge_reroll_button_click_responds(pygame_headless):
    """Clicking the Reroll button in the open Forge panel sinks amber."""
    import pygame
    import main
    from utils import seed
    seed(42)
    g = main.Game()
    screen = g.screens["hero"]
    state = g.state
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 1_000_000
    state.amber = 1_000
    screen._forge_open = True
    screen._maybe_rebuild_forge_buttons()
    # Reroll is the 2nd button in the blade row (index 1).
    btn = screen._forge_btns[1]
    assert btn.label == "Reroll", f"2nd forge button is {btn.label!r}"
    assert btn.enabled
    center = btn.rect.center
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                              {"pos": center, "button": 1})
    up = pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {"pos": center, "button": 1})
    amber_before = state.amber
    screen.handle(down)
    assert btn.pressed is True
    screen.handle(up)
    assert state.amber < amber_before, (
        f"amber unchanged after Reroll click: {amber_before} -> {state.amber}")


def test_forge_salvage_button_click_responds(pygame_headless):
    """Clicking the Salvage button in the open Forge panel returns amber +
    removes the piece."""
    import pygame
    import main
    g = main.Game()
    screen = g.screens["hero"]
    state = g.state
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 1_000_000
    state.amber = 1_000
    screen._forge_open = True
    screen._maybe_rebuild_forge_buttons()
    # Salvage is the 3rd button in the blade row (index 2).
    btn = screen._forge_btns[2]
    assert btn.label == "Salvage", f"3rd forge button is {btn.label!r}"
    assert btn.enabled
    center = btn.rect.center
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                              {"pos": center, "button": 1})
    up = pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {"pos": center, "button": 1})
    amber_before = state.amber
    screen.handle(down)
    assert btn.pressed is True
    screen.handle(up)
    assert "blade" not in state.gear, (
        f"blade still in gear after Salvage click: {state.gear}")
    assert state.amber > amber_before, (
        f"amber did not increase after Salvage: {amber_before} -> {state.amber}")


def test_forge_buy_legendary_button_click_responds(pygame_headless):
    """Clicking the Buy Legendary button in the open Forge panel sinks amber
    + adds a legendary piece."""
    import pygame
    import main
    from utils import seed
    seed(42)
    g = main.Game()
    screen = g.screens["hero"]
    state = g.state
    state.gear = {}
    state.gold = 1_000_000
    state.amber = 1_000
    screen._forge_open = True
    screen._maybe_rebuild_forge_buttons()
    # Buy Legendary is the 4th button in the blade row (index 3).
    btn = screen._forge_btns[3]
    assert btn.label == "Buy Legendary", f"4th forge button is {btn.label!r}"
    assert btn.enabled
    center = btn.rect.center
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                              {"pos": center, "button": 1})
    up = pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {"pos": center, "button": 1})
    amber_before = state.amber
    screen.handle(down)
    assert btn.pressed is True
    screen.handle(up)
    assert state.amber < amber_before, (
        f"amber unchanged after Buy Legendary click: {amber_before} -> {state.amber}")
    assert "blade" in state.gear, "blade slot empty after Buy Legendary"
    assert state.gear["blade"]["rarity"] == "legendary", (
        f"blade rarity is {state.gear['blade']['rarity']}, not 'legendary'")


def test_forge_buttons_cached_across_events(pygame_headless):
    """The forge buttons are cached on self._forge_btns (not rebuilt on
    every event) so the DOWN+UP pair hits the same Button object.

    This is the regression test for the rebuild-on-every-event bug: a
    fresh Button has pressed=False, so if handle() rebuilt the buttons on
    every call, the MOUSEBUTTONDOWN that sets pressed=True and the
    MOUSEBUTTONUP that checks pressed would hit different objects and the
    click would never fire.
    """
    import main
    g = main.Game()
    screen = g.screens["hero"]
    g.state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    g.state.gold = 1_000_000
    g.state.amber = 1_000
    screen._forge_open = True
    screen._maybe_rebuild_forge_buttons()
    btns_before = list(screen._forge_btns)
    # A second update call with the same state must NOT rebuild the
    # buttons (the snapshot is unchanged). This is what keeps the
    # DOWN+UP pair on the same object.
    screen._maybe_rebuild_forge_buttons()
    assert screen._forge_btns is not None
    # The cached list is the same objects (identity, not just equality).
    for a, b in zip(btns_before, screen._forge_btns):
        assert a is b, (
            "forge buttons were rebuilt with the same state -- the cache "
            "is broken and the DOWN+UP pair will not fire on_click")


def test_forge_buttons_rebuilt_when_state_changes(pygame_headless):
    """The forge buttons are rebuilt when the gear/currency state changes
    (so the enabled flags track the live state) -- but NOT on every event."""
    import main
    g = main.Game()
    screen = g.screens["hero"]
    g.state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    g.state.gold = 1_000_000
    g.state.amber = 1_000
    screen._forge_open = True
    screen._maybe_rebuild_forge_buttons()
    btns_before = list(screen._forge_btns)
    # Change the state (spend all the gold) -- the next rebuild must pick
    # up the new state (Enhance is now disabled).
    g.state.gold = 0
    screen._maybe_rebuild_forge_buttons()
    # The buttons were rebuilt (different objects).
    rebuilt = any(a is not b for a, b in zip(btns_before, screen._forge_btns))
    assert rebuilt, "forge buttons were not rebuilt after a state change"
    # The Enhance button is now disabled (no gold).
    enh = screen._forge_btns[0]
    assert enh.label == "Enhance"
    assert enh.enabled is False, (
        "Enhance button is still enabled after gold went to 0 -- the "
        "rebuild did not pick up the new state")
