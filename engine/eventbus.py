"""Runner-owned event bus replacing module-global FX callbacks.

Engine modules emit events; the runner subscribes the FX systems.
Module globals (``engine/enemy.on_enemy_dmg`` etc.) are kept as
deprecated aliases that forward to the bus for one release, so nothing
breaks during the transition.

The bus wraps every handler in ``try/except`` so a misbehaving FX system
can never break the simulation tick.
"""
from __future__ import annotations

from typing import Any, Callable


class EventBus:
    """A tiny pub/sub bus.

    ``on(name, handler)`` registers a handler for an event name.
    ``emit(name, *args, **kwargs)`` calls every handler registered for
    that name. Handler exceptions are swallowed — FX must never break the
    simulation.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, name: str, handler: Callable) -> None:
        """Register ``handler`` for ``name``. Idempotent per handler."""
        bucket = self._handlers.setdefault(name, [])
        if handler not in bucket:
            bucket.append(handler)

    def emit(self, name: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch ``name`` to all handlers. Exceptions are swallowed."""
        for h in self._handlers.get(name, ()):
            try:
                h(*args, **kwargs)
            except Exception:
                # FX must never break the simulation.
                pass
