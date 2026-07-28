"""EventBus: a Runner-owned bus replacing module-global FX callbacks.

Engine modules emit events; the runner subscribes the FX systems.
Module globals (engine/enemy.on_enemy_dmg etc.) are kept as deprecated
aliases that forward to the bus for one release.
"""
import pytest

import config as cfg


def test_eventbus_dispatch(pygame_headless):
    """on() + emit() dispatches args and kwargs to the handler."""
    from engine.eventbus import EventBus
    bus = EventBus()
    received = []
    bus.on("enemy_dmg", lambda *a, **k: received.append(("enemy_dmg", a, k)))
    bus.emit("enemy_dmg", 100, 200, 5.0, is_crit=True, is_boss=False)
    assert received and received[0][0] == "enemy_dmg"
    assert received[0][1] == (100, 200, 5.0)
    assert received[0][2] == {"is_crit": True, "is_boss": False}


def test_eventbus_multiple_handlers(pygame_headless):
    """Multiple handlers for the same event all fire."""
    from engine.eventbus import EventBus
    bus = EventBus()
    calls = []
    bus.on("enemy_dmg", lambda *a, **k: calls.append("first"))
    bus.on("enemy_dmg", lambda *a, **k: calls.append("second"))
    bus.emit("enemy_dmg", 1)
    assert calls == ["first", "second"]


def test_eventbus_handler_exception_does_not_propagate(pygame_headless):
    """A handler raising must not break the bus or other handlers."""
    from engine.eventbus import EventBus

    def bad_handler(*a, **k):
        raise RuntimeError("boom")

    bus = EventBus()
    log = []
    bus.on("enemy_dmg", lambda *a, **k: log.append("before"))
    bus.on("enemy_dmg", bad_handler)
    bus.on("enemy_dmg", lambda *a, **k: log.append("after"))
    # Must not raise.
    bus.emit("enemy_dmg", 1, 2)
    # The good handlers before and after the bad one both fired.
    assert "before" in log
    assert "after" in log


def test_eventbus_unknown_event_noop(pygame_headless):
    """Emitting an event with no subscribers is a no-op."""
    from engine.eventbus import EventBus
    bus = EventBus()
    # Must not raise.
    bus.emit("never_subscribed", 1, 2, three=3)


def test_eventbus_no_handlers_silent(pygame_headless):
    """An event with no handlers does nothing, no error."""
    from engine.eventbus import EventBus
    bus = EventBus()
    bus.emit("nobody_listens")
    # No assertion needed — reaching here without error is the test.


def test_eventbus_on_returns_none(pygame_headless):
    """on() has no return value (subscribers register for side effects)."""
    from engine.eventbus import EventBus
    bus = EventBus()
    ret = bus.on("x", lambda *a, **k: None)
    assert ret is None


def test_eventbus_emit_no_args(pygame_headless):
    """emit() with no args/kwargs works."""
    from engine.eventbus import EventBus
    bus = EventBus()
    log = []
    bus.on("ping", lambda *a, **k: log.append((a, k)))
    bus.emit("ping")
    assert log == [((), {})]


def test_deprecated_module_globals_forward_to_bus(pygame_headless):
    """The deprecated module globals (on_enemy_dmg etc.) forward to the bus.

    The Runner wires them to ``lambda *a, **k: self.bus.emit(...)``, so a
    caller that still uses the old global keeps working — the event lands
    on the bus.
    """
    from engine.eventbus import EventBus
    from engine import enemy as _e

    bus = EventBus()
    _e.set_event_bus(bus)
    received = []
    bus.on("enemy_dmg", lambda *a, **k: received.append(("enemy_dmg", a, k)))

    # Simulate the Runner wiring the deprecated alias.
    _e.on_enemy_dmg = lambda *a, **k: bus.emit("enemy_dmg", *a, **k)

    # A caller using the old global directly.
    _e.on_enemy_dmg(10, 20, 5.0, is_crit=True, is_boss=False)
    assert received and received[0][0] == "enemy_dmg"
    assert received[0][1] == (10, 20, 5.0)
    assert received[0][2] == {"is_crit": True, "is_boss": False}

    # Cleanup so other tests aren't affected.
    _e.on_enemy_dmg = None
    _e.set_event_bus(None)


def test_enemy_module_emits_via_bus(pygame_headless):
    """_apply_damage emits 'enemy_dmg' on the bus when wired."""
    from engine.eventbus import EventBus
    from engine import enemy as _e
    from data import enemies as ed

    bus = EventBus()
    _e.set_event_bus(bus)
    received = []
    bus.on("enemy_dmg", lambda *a, **k: received.append((a, k)))

    edef = ed.zone_by_index(0)["enemies"][0]
    e = _e.spawn_enemy(edef, hp=100.0, dmg=5.0, gold=3.0)
    _e._apply_damage(e, 10.0, is_crit=True)
    assert received, "expected an enemy_dmg event"
    assert received[0][0] == (e.x, e.y, 10.0)
    assert received[0][1] == {"is_crit": True, "is_boss": False}

    _e.set_event_bus(None)


def test_world_emits_boss_and_firefly_spawn(pygame_headless):
    """World._enter_boss and _spawn_firefly emit on the bus when wired."""
    from engine.eventbus import EventBus
    from engine.world import World

    bus = EventBus()
    events = []
    bus.on("boss_spawn", lambda *a, **k: events.append(("boss_spawn", a, k)))
    bus.on("firefly_spawn", lambda *a, **k: events.append(("firefly_spawn", a, k)))

    w = World()
    w.set_event_bus(bus)
    # Force a boss spawn by crossing the zone distance threshold.
    w.zone_distance = cfg.ZONE_DISTANCE
    w.update(0.01, paused=False)
    assert any(ev[0] == "boss_spawn" for ev in events), "expected a boss_spawn event"

    # Force a firefly spawn by running the firefly timer past the interval.
    w.firefly_timer = 1000.0
    w.update(0.01, paused=False)
    assert any(ev[0] == "firefly_spawn" for ev in events), "expected a firefly_spawn event"
