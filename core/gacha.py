"""Pet gacha: spend Amber to roll a random pet (with pity + fairness).

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

**Gacha fairness bundle (Task 19):** the gacha is no longer a gamble.

  * **Soft-pity ramp**: after ``SOFT_PITY_START[rarity]`` pulls without
    that rarity, the rate climbs by ``SOFT_PITY_INCREMENT`` per pull.
    Shortens the ``PITY_LEGENDARY=200`` grind.

  * **Spark/pity-token shop**: 1 ``pity_tokens`` per pull. Trade
    ``SPARK_SHOP_COST`` (40) for any unlocked, non-maxed pet. Pity
    carries across banners (cumulative, not per-banner).

  * **Dupe-to-upgrade**: duplicates feed the ``pet_stars`` track (Task
    14). Maxed pets (bond 10 + star 12) are removed from the pool so the
    player never wastes a pull on a pet that can no longer progress.

  * **Early-pity guarantee**: in the first ``EARLY_PITY_WINDOW`` (10)
    pulls of a new banner, guarantee a rare+ (one-time-per-banner).
    Tracked via ``banner_pulls``.

Some pets are gated behind skill-tree nodes or ascension counts.
"""
from __future__ import annotations

from dataclasses import dataclass

import config as cfg
from data import pets as pet_def
from core.state import GameState
from utils import rng


PET_PULL_COST = 20          # amber per pull
PET_PULL_10_COST = 180      # 10-pull (10% discount)
PET_PITY = 10               # guaranteed a new pet after N pulls without one

# Pet depth (Task 14): nested pet prestige.
PET_BOND_MAX = 10

# Rarity tiers in draw order (common -> mythic). The pull rate table is
# keyed by these strings; ``pull`` rolls a rarity then picks a pet.
_RARITIES = ("common", "rare", "epic", "legendary", "mythic")


@dataclass
class PetPullResult:
    pet_id: str
    name: str
    is_new: bool
    pity_used: bool = False
    star_up: bool = False    # True if this duplicate incremented a star level
    rarity: str = "common"   # the rarity tier rolled (gp-gacha-fairness)


# ---------------------------------------------------------------------------
# Rarity derivation (mirrors engine/gacha_fx._rarity_of)
# ---------------------------------------------------------------------------
def _rarity_of(pet: pet_def.PetDef) -> str:
    """Map a pet to a rarity tier (mirrors engine/gacha_fx._rarity_of)."""
    if pet.ptype == "mythical":
        return "mythic"
    if pet.unlock.startswith("ascensions:"):
        return "legendary"
    if pet.unlock.startswith("skill:"):
        return "epic"
    if pet.buff_per_level >= 0.03:
        return "rare"
    return "common"


# ---------------------------------------------------------------------------
# Soft-pity ramp
# ---------------------------------------------------------------------------
def pull_rates(state: GameState) -> dict[str, float]:
    """The effective per-rarity pull rates after the soft-pity ramp.

    The base rates are ``cfg.GACHA_RATES``. After ``SOFT_PITY_START[rarity]``
    pulls without that rarity, the rate climbs by
    ``SOFT_PITY_INCREMENT`` per pull. The rates are renormalized to sum
    to 1.0 so the roll is a valid probability distribution.

    The pity counters live in ``state.pet_pity`` (a ``rarity -> pulls
    since last drop`` dict) and are DECOUPLED: a drop at rarity R resets
    the counter for R and all *lower* rarities (in the "at least this
    rarity" sense), but NOT for higher rarities. So a rare drop resets
    only the rare counter; an epic drop resets rare + epic; a legendary
    drop resets rare/epic/legendary; a mythic drop resets all. This lets
    the legendary counter accumulate across rare/epic drops so the
    legendary soft-pity ramp can actually fire after 150 pulls without a
    legendary -- the rare ramp no longer resets the ladder at ~20-30
    pulls and short-circuits the legendary grind.
    """
    base = dict(cfg.GACHA_RATES)
    pity = state.pet_pity
    out: dict[str, float] = {}
    for r in _RARITIES:
        rate = base.get(r, 0.0)
        start = cfg.SOFT_PITY_START.get(r)
        if start is not None:
            p = pity.get(r, 0)
            if p > start:
                # Ramp: +SOFT_PITY_INCREMENT per pull past the threshold.
                rate += (p - start) * cfg.SOFT_PITY_INCREMENT
        out[r] = max(0.0, rate)
    # Renormalize so the rates sum to 1.0 (a valid distribution).
    total = sum(out.values())
    if total > 0.0:
        out = {r: v / total for r, v in out.items()}
    return out


def _roll_rarity(state: GameState) -> str:
    """Roll a rarity tier using the soft-pity-ramped rates."""
    rates = pull_rates(state)
    weights = [rates.get(r, 0.0) for r in _RARITIES]
    return rng().choices(_RARITIES, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Maxed-pet removal (dupe-to-upgrade)
# ---------------------------------------------------------------------------
def _is_maxed(state: GameState, pid: str) -> bool:
    """A pet is maxed when bond is 10 AND stars are at PET_STAR_MAX."""
    bond = state.pet_bond(pid)
    stars = state.pet_stars.get(pid, 0)
    return bond >= PET_BOND_MAX and stars >= pet_def.PET_STAR_MAX


def _eligible_pets(state: GameState) -> list[pet_def.PetDef]:
    """Unlocked pets, with maxed pets (bond 10 + star 12) removed."""
    out = []
    for p in pet_def.PETS:
        if not pet_def.is_unlocked(p, state):
            continue
        # A maxed pet is removed from the pool — the player never wastes
        # a pull on a pet that can no longer progress.
        if p.id in state.pets and _is_maxed(state, p.id):
            continue
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------
def pull(state: GameState) -> PetPullResult:
    eligible = _eligible_pets(state)
    if not eligible:
        return PetPullResult("", "", False)
    # Pity: guarantee a pet the player doesn't own after PET_PITY pulls.
    unowned = [p for p in eligible if p.id not in state.pets]
    pity_used = False
    # Early-pity guarantee: in the first EARLY_PITY_WINDOW pulls of a new
    # banner, force at least one rare+ (one-time-per-banner). We track
    # this via banner_pulls: if we're in the first 10 pulls and no rare+
    # has been seen yet, force one. With the decoupled counters, "no
    # rare+ seen yet" means the rare counter equals banner_pulls (a
    # rare+ drop would have reset the rare counter). We check the rare
    # counter specifically (not all rare+ counters) because a rare drop
    # doesn't reset the epic/legendary/mythic counters.
    if (0 < state.banner_pulls < cfg.EARLY_PITY_WINDOW
            and state.pet_pity.get("rare", 0) == state.banner_pulls):
        # We're in the first 10 pulls and every pull so far was common.
        # Force a rare+ this pull (the guarantee).
        rare_plus_pool = [p for p in eligible if _rarity_of(p) != "common"]
        if rare_plus_pool:
            weights = []
            for p in rare_plus_pool:
                w = 3.0 if p.id not in state.pets else 1.0
                weights.append(w)
            chosen = rng().choices(rare_plus_pool, weights=weights, k=1)[0]
            rarity = _rarity_of(chosen)
            pity_used = True
        else:
            # No rare+ pet available (all locked or maxed) -- fall back
            # to the normal path.
            chosen = None
    else:
        chosen = None
    if chosen is None:
        if unowned and state.pet_pulls > 0 and state.pet_pulls % PET_PITY == 0:
            chosen = rng().choice(unowned)
            pity_used = True
            rarity = _rarity_of(chosen)
        else:
            # Roll a rarity tier (with the soft-pity ramp), then pick a pet
            # of that rarity. If no eligible pet of the rolled rarity exists,
            # fall back to a weighted pick across all eligible pets.
            rarity = _roll_rarity(state)
            pool = [p for p in eligible if _rarity_of(p) == rarity]
            if not pool:
                # Fall back: weighted across all eligible (unowned more likely).
                weights = []
                for p in eligible:
                    w = 3.0 if p.id not in state.pets else 1.0
                    weights.append(w)
                chosen = rng().choices(eligible, weights=weights, k=1)[0]
                rarity = _rarity_of(chosen)
            else:
                # Within the rarity tier, unowned pets are more likely.
                weights = []
                for p in pool:
                    w = 3.0 if p.id not in state.pets else 1.0
                    weights.append(w)
                chosen = rng().choices(pool, weights=weights, k=1)[0]
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
    # Advance the per-rarity pity counters.
    # The counters are DECOUPLED (not a single rare+ ladder): a drop at
    # rarity R resets the counter for R and all *lower* rarities (in the
    # "at least this rarity" sense), but NOT for higher rarities. So:
    #   rare drop    -> reset rare
    #   epic drop    -> reset rare + epic
    #   legendary drop -> reset rare + epic + legendary
    #   mythic drop  -> reset rare + epic + legendary + mythic
    # This lets the legendary counter accumulate across rare/epic drops
    # (which happen often) so the legendary soft-pity ramp can actually
    # fire after 150 pulls without a legendary -- the rare ramp no longer
    # resets the ladder at ~20-30 pulls and short-circuits the legendary
    # grind. A common pull increments all rare+ counters.
    _RARITY_ORDER = ("common", "rare", "epic", "legendary", "mythic")
    drop_idx = _RARITY_ORDER.index(rarity)
    pity = state.pet_pity
    for i, r in enumerate(_RARITY_ORDER):
        if r == "common":
            continue
        if i <= drop_idx:
            # This rarity or a lower one -- reset (the drop satisfies
            # "at least this rarity").
            pity[r] = 0
        else:
            # A higher rarity -- increment (no drop at this rarity).
            pity[r] = pity.get(r, 0) + 1
    state.pet_pulls += 1
    state.banner_pulls += 1
    # Spark/pity-token: 1 token per pull (cumulative across banners).
    state.pity_tokens += 1
    return PetPullResult(chosen.id, chosen.name, is_new, pity_used, star_up, rarity)


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
# Spark/pity-token shop
# ---------------------------------------------------------------------------
def spark_shop_trade(state: GameState, pid: str) -> bool:
    """Trade ``SPARK_SHOP_COST`` (40) pity tokens for a guaranteed pet.

    Requirements:
      * ``pid`` is unlocked (the unlock condition is met).
      * ``pid`` is not maxed (bond < 10 OR stars < PET_STAR_MAX).
        A maxed pet is removed from the pool — trading for one would
        waste the tokens.
      * ``state.pity_tokens >= SPARK_SHOP_COST``.

    On success: the pet is added (bond 1 if new, else a star-up), the
    tokens are spent, and the rarity pity ladder resets (the trade
    counts as a drop). Returns ``True`` on success, ``False`` otherwise.
    """
    if state.pity_tokens < cfg.SPARK_SHOP_COST:
        return False
    pet = pet_def.BY_ID.get(pid)
    if pet is None:
        return False
    if not pet_def.is_unlocked(pet, state):
        return False
    if _is_maxed(state, pid):
        return False
    # Spend the tokens.
    state.pity_tokens -= cfg.SPARK_SHOP_COST
    is_new = pid not in state.pets
    if is_new:
        state.pets[pid] = 1
    else:
        stars = state.pet_stars.get(pid, 0)
        if stars < pet_def.PET_STAR_MAX:
            state.pet_stars[pid] = stars + 1
    # Reset the rare+ pity ladder (the trade counts as a rare+ drop, so
    # it resets rare/epic/legendary/mythic per the decoupled-counter
    # rule -- the trade gives a guaranteed pet, which is at least rare
    # in the player's eyes, so the full ladder resets).
    pity = state.pet_pity
    for r in ("rare", "epic", "legendary", "mythic"):
        pity[r] = 0
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
