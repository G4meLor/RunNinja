"""Aggregate all permanent + equipped bonuses into a flat dict.

BonusProvider registry: each source registers a
``callable(state) -> dict[str, float]``; ``aggregate_bonuses`` merges all
registered providers into the flat ``{effect_key: total_value}`` dict the
engine reads. The flat-dict contract is unchanged so every consumer
(``compute_ninja_stats``, ``gold_mult``, ``total_gps``, etc.) works
unmodified.

To add a new bonus source (gear, elements, tokens, heritage, ...), define
a ``callable(state) -> dict[str, float]`` and call ``register_provider``
with it — no edit to ``aggregate_bonuses`` or the Runner required.
"""
from __future__ import annotations

from typing import Callable

from core.state import GameState
from data import skill_tree as st
from data import pets as pet_def


# A provider returns the partial bonus dict for one source.
# ``aggregate_bonuses`` merges all providers additively by key.
Provider = Callable[[GameState], dict[str, float]]

_PROVIDERS: list[Provider] = []


def register_provider(p: Provider) -> None:
    """Register a bonus provider. Idempotent: a second add is a no-op."""
    if p not in _PROVIDERS:
        _PROVIDERS.append(p)


def _skill_tree_provider(state: GameState) -> dict[str, float]:
    """Skill tree nodes: each unlocked node contributes its effect_value."""
    out: dict[str, float] = {}
    for n in st.NODES:
        if n.id in state.skill_tree:
            out[n.effect_key] = out.get(n.effect_key, 0.0) + n.effect_value
    return out


def _pets_provider(state: GameState) -> dict[str, float]:
    """Equipped pets: bond level × buff_per_level per pet's buff_key."""
    out: dict[str, float] = {}
    for pid in state.equipped_pets:
        bond = state.pet_bond(pid)
        if bond <= 0:
            continue
        p = pet_def.BY_ID.get(pid)
        if p is None:
            continue
        out[p.buff_key] = out.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond)
    return out


# Register the built-in providers. Order does not matter — contributions
# are summed additively by key.
register_provider(_skill_tree_provider)
register_provider(_pets_provider)


def aggregate_bonuses(state: GameState) -> dict[str, float]:
    """Merge all registered providers into the flat bonus dict.

    The flat ``{effect_key: total_value}`` contract is unchanged: every
    consumer (compute_ninja_stats, gold_mult, total_gps, ...) reads the
    same keys it always did.
    """
    out: dict[str, float] = {}
    for p in _PROVIDERS:
        for k, v in p(state).items():
            out[k] = out.get(k, 0.0) + v
    return out
