"""Contextual hint engine — the first-session onboarding guide.

A pure function of state: each frame the UI calls
``next_hint(state, welcome_pending=..., zone_fx_active=...)`` and gets the
next best action to glow (or ``None``).  The engine evaluates a priority-
ordered list of conditions and returns the first whose condition is true and
whose ``action_id`` is not in ``state.seen_hints``.

The chain (the first-session tutorial):

1. ``tap_road``   — the player hasn't killed 10 monsters yet → "tap the road".
2. ``buy_farm``    — the player killed 10+ but hasn't bought a farm → "buy a farm".
3. ``upgrade``     — the player has a farm but no run upgrades → "buy an upgrade".
4. ``ascend``      — the player reached zone 3+ but hasn't ascended → "ascend".

The seen-set (``state.seen_hints``) prevents repeats: once a hint is
dismissed (the player follows the action or clicks the glow), its
``action_id`` is appended to ``seen_hints`` so the engine skips it on the
next call.  The engine itself just checks membership; the dismissal is
wired by the UI.

Hard gates: if ``welcome_pending`` (the offline-progress welcome-back modal
is showing) or ``zone_fx_active`` (a zone-transition cinematic is playing),
the engine returns ``None`` — no hint during a modal or a transition.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hint:
    """A single contextual hint.

    ``action_id`` is the stable id stored in ``state.seen_hints``.
    ``condition`` is a callable ``(state) -> bool``.  ``text`` is the
    human-readable prompt.  ``target`` is a UI-facing key that tells the
    GameScreen where to draw the glow (e.g. ``"road"`` or
    ``"nav:buildings"``).
    """
    action_id: str
    condition: callable
    text: str
    target: str


class HintEngine:
    """Priority-ordered hint evaluator.

    The engine is stateless (it reads ``state.seen_hints`` but does not
    mutate it); the UI owns the dismissal (appending to ``seen_hints``).
    Constructed once by the GameScreen and called per frame.
    """

    def __init__(self) -> None:
        self.hints: list[Hint] = [
            Hint("tap_road",
                 lambda s: s.monsters_killed < 10,
                 "Tap the road to attack!",
                 "road"),
            Hint("buy_farm",
                 lambda s: s.monsters_killed >= 10
                           and s.building_level("farm") == 0,
                 "Buy a farm in Buildings.",
                 "nav:menuhub"),
            Hint("upgrade",
                 lambda s: s.building_level("farm") >= 1
                           and len(s.upgrades) == 0,
                 "Buy an upgrade.",
                 "nav:menuhub"),
            Hint("ascend",
                 lambda s: s.best_zone >= 3 and s.ascend_tier == 0,
                 "Ascend for permanent power.",
                 "nav:ascend"),
        ]

    def next_hint(self, state, *, welcome_pending: bool,
                  zone_fx_active: bool) -> Hint | None:
        """Return the first applicable hint, or ``None``.

        Gated on ``not welcome_pending and not zone_fx_active`` (no hint
        during the welcome-back modal or a zone-transition cinematic).
        Skips any hint whose ``action_id`` is in ``state.seen_hints``.
        """
        if welcome_pending or zone_fx_active:
            return None
        for h in self.hints:
            if h.action_id in state.seen_hints:
                continue
            try:
                if h.condition(state):
                    return h
            except Exception:
                continue
        return None
