"""Pet gacha: spend Amber to roll a random pet (with pity).

Duplicates raise the pet's bond level (capped at 10). Once the pet is
at max bond, **further duplicates increment its star level** (1-12,
capped at ``PET_STAR_MAX``) — a second progression axis on top of bond.

**Spirit Embers (nested pet prestige):** a pet at max bond (10) can be
prestiged via ``prestige_pet``. The bond resets to 0, Spirit Embers are
paid out (scaling with the prestige count), and a permanent multiplier
is folded into the pet's bonus via ``pet_bonus(pet, bond, stars,
prestiges)``. The re-grind is clearly worth it: each prestige adds
``PET_PRESTIGE_BONUS_PER`` of the pet's base bonus, so the post-prestige
bonus (once bond is rebuilt to 10) outpaces the pre-prestige bonus at
bond 10.

Some pets are gated behind skill-tree nodes or ascension counts.
"""
from __future__ import annotations

from dataclasses import dataclass

from data import pets as pet_def
from core.state import GameState
from utils import rng


PET_PULL_COST = 20          # amber per pull
PET_PULL_10_COST = 180      # 10-pull (10% discount)
PET_PITY = 10               # guaranteed a new pet after N pulls without one

# Pet depth (Task 14): nested pet prestige.
PET_BOND_MAX = 10


@dataclass
class PetPullResult:
    pet_id: str
    name: str
    is_new: bool
    pity_used: bool = False
    star_up: bool = False    # True if this duplicate incremented a star level


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
    star_up = False
    if is_new:
        state.pets[chosen.id] = 1
    else:
        # Duplicate: bond is raised by *feeding* (gold/amber) in the
        # pet-detail panel; duplicates from the gacha increment the
        # star level — the second progression axis on top of bond.
        # Capped at PET_STAR_MAX (12); above the cap the duplicate is
        # a no-op (but still counts toward pity / pull count).
        stars = state.pet_stars.get(chosen.id, 0)
        if stars < pet_def.PET_STAR_MAX:
            state.pet_stars[chosen.id] = stars + 1
            star_up = True
    state.pet_pulls += 1
    return PetPullResult(chosen.id, chosen.name, is_new, pity_used, star_up)


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


# ---------------------------------------------------------------------------
# Spirit Embers — nested pet prestige
# ---------------------------------------------------------------------------
def prestige_pet(state: GameState, pid: str) -> bool:
    """Prestige a max-bond pet for Spirit Embers.

    Requirements:
      * ``pid`` is owned and at bond 10 (max bond).
      * The prestige resets bond to 0 and pays out Spirit Embers
        (scaling with the pet's prestige count — each re-grind is
        worth more than the last).
      * The pet's prestige count is incremented; ``pet_bonus`` folds
        the count into a permanent multiplier so the post-prestige
        bonus (once bond is rebuilt to 10) outpaces the pre-prestige
        bonus at bond 10.

    Returns ``True`` if the prestige happened, ``False`` if the
    requirements weren't met (not owned, or bond < 10).
    """
    if pid not in state.pets:
        return False
    if state.pet_bond(pid) < PET_BOND_MAX:
        return False
    n = state.pet_prestiges.get(pid, 0) + 1
    payout = pet_def.PET_PRESTIGE_PAYOUT_BASE + (n - 1) * pet_def.PET_PRESTIGE_PAYOUT_STEP
    state.spirit_embers += payout
    state.pets[pid] = 0  # bond reset — re-grind from 0
    state.pet_prestiges[pid] = n
    return True
