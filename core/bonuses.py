"""Aggregate all permanent + equipped bonuses into a flat dict.

This is the single function the engine calls to get the combined effect
of the elixir skill tree, equipped pets, and ascension tier.  Returns
``{effect_key: total_value}``.
"""
from __future__ import annotations

from core.state import GameState
from data import skill_tree as st
from data import pets as pet_def


def aggregate_bonuses(state: GameState) -> dict[str, float]:
    out: dict[str, float] = {}
    # Skill tree nodes.
    for n in st.NODES:
        if n.id in state.skill_tree:
            out[n.effect_key] = out.get(n.effect_key, 0.0) + n.effect_value
    # Equipped pets (bond × buff_per_level).
    for pid in state.equipped_pets:
        bond = state.pet_bond(pid)
        if bond <= 0:
            continue
        p = pet_def.BY_ID.get(pid)
        if p is None:
            continue
        out[p.buff_key] = out.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond)
    return out
