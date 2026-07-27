"""Skill-tree unlock logic (elixir)."""
from __future__ import annotations

from core.state import GameState
from data import skill_tree as st


def can_unlock(state: GameState, node_id: str) -> bool:
    return st.can_unlock(node_id, state.skill_tree, state.elixir)


def unlock(state: GameState, node_id: str) -> bool:
    if not can_unlock(state, node_id):
        return False
    n = st.BY_ID[node_id]
    state.elixir -= n.cost
    state.skill_tree.add(node_id)
    return True
