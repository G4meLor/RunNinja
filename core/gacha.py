"""Pet gacha: spend Amber to roll a random pet (with pity).

Duplicates raise the pet's bond level.  Some pets are gated behind
skill-tree nodes or ascension counts.
"""
from __future__ import annotations

from dataclasses import dataclass

from data import pets as pet_def
from core.state import GameState
from utils import rng


PET_PULL_COST = 20          # amber per pull
PET_PULL_10_COST = 180      # 10-pull (10% discount)
PET_PITY = 10               # guaranteed a new pet after N pulls without one


@dataclass
class PetPullResult:
    pet_id: str
    name: str
    is_new: bool
    pity_used: bool = False


def _eligible_pets(state: GameState) -> list[pet_def.PetDef]:
    return [p for p in pet_def.PETS if pet_def.is_unlocked(p, state)]


def pull(state: GameState) -> PetPullResult:
    eligible = _eligible_pets(state)
    if not eligible:
        return PetPullResult("", "", False)
    # Pity: guarantee a pet the player doesn't own after PET_PITY pulls.
    unowned = [p for p in eligible if p.id not in state.pets]
    pity_used = False
    if unowned and state.pet_pulls > 0 and state.pet_pulls % PET_PITY == 0:
        chosen = rng().choice(unowned)
        pity_used = True
    else:
        # Weighted: unowned pets are more likely (so collection fills).
        weights = []
        for p in eligible:
            w = 3.0 if p.id not in state.pets else 1.0
            weights.append(w)
        chosen = rng().choices(eligible, weights=weights, k=1)[0]
    is_new = chosen.id not in state.pets
    if is_new:
        state.pets[chosen.id] = 1
    else:
        state.pets[chosen.id] = min(10, state.pet_bond(chosen.id) + 1)
    state.pet_pulls += 1
    return PetPullResult(chosen.id, chosen.name, is_new, pity_used)


def multi_pull(state: GameState, n: int = 10) -> list[PetPullResult]:
    return [pull(state) for _ in range(n)]


def can_afford(state: GameState) -> bool:
    return state.amber >= PET_PULL_COST


def can_afford_10(state: GameState) -> bool:
    return state.amber >= PET_PULL_10_COST


def pay(state: GameState) -> bool:
    if not can_afford(state):
        return False
    state.amber -= PET_PULL_COST
    return True


def pay_10(state: GameState) -> bool:
    if not can_afford_10(state):
        return False
    state.amber -= PET_PULL_10_COST
    return True
