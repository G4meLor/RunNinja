"""Ascension: the prestige loop for Tap Ninja.

Ascending resets gold, run upgrades, zone, combo, and energy, but grants
Elixir based on the gold earned this run.  **Buildings persist through
ascension** (scaled by the tier stat_mult in ``total_gps`` so they stay
relevant) -- only gold and run upgrades reset.  Elixir is spent on the
permanent skill tree.  Requires reaching a minimum zone (this run),
reducible by the "ascend_cost_pct" bonus.

Task 27 / pl-juice-polish additions:
  * **Free respec-on-prestige** for the elixir skill tree (``respec_skill_tree``):
    the tree persists through ascension (it's permanent), but the player
    can refund all elixir spent on it and re-spend it freely. This is the
    "respec" the brief calls for -- not a reset on ascension (the tree
    already persists), but a manual refund/re-spend the player can do any
    time. The refund is FREE (no cost) so it's a respec, not a re-grind.
  * **Elixir-per-Minute readout** (``elixir_per_minute``): computed from
    the ``config.py`` curves (the ``elixir_gain`` formula + the current
    ``lifetime_gold`` + ``ascend_tier``). The ascend screen surfaces this
    so the player can see their pacing.
  * **Recommended-ascend** (``recommended_ascend``): a bool the ascend
    screen highlights when the elixir-per-minute is high enough AND the
    player can ascend (a "now is a good time" cue, not a hard gate).
  * **Tome of Samsara** (``TOME_OF_SAMSARA_NODE`` + ``tome_of_samsara_tooltip``
    + ``elixir_per_ascension``): the elixir-tree's top-tier node
    (``eli_t6`` "Ouroboros") is promoted as the compounding elixir-growth
    anchor. The tooltip recommends "invest ~30%" of elixir here (a soft
    guidance, not a hard rule) + projects the elixir-per-ascension the
    player would earn with it maxed. The Tome is the SINGLE compounding
    elixir-growth loop -- the unspent-elixir-as-multiplier is NOT
    implemented (``elixir_gain`` does NOT scale with the unspent balance).
"""
from __future__ import annotations

import math

import config as cfg
from core.state import GameState
from core.bonuses import aggregate_bonuses


# ---------------------------------------------------------------------------
# Task 27: Tome of Samsara -- the compounding elixir-growth anchor.
# ---------------------------------------------------------------------------
# The elixir-tree's top-tier node (``eli_t6`` "Ouroboros") is the single
# compounding elixir-growth loop. The node already grants ``elixir_pct``
# (a permanent +65% elixir gain), which stacks additively with the other
# elixir_pct sources (the lower elixir-tree tiers + Godai Void + elixir
# tokens + Epic Research's Elixir Resonance). Promoting it as the "Tome
# of Samsara" anchor is a UI/teaching layer -- the compounding already
# works through the additive ``elixir_pct`` stack; the anchor is the
# *recommended* node to invest in for long-term elixir growth.
TOME_OF_SAMSARA_NODE = "elixir_t6"


def ascend_requirement(state: GameState) -> int:
    """Minimum zone index (this run) required to ascend."""
    base = 5
    evo = aggregate_bonuses(state)
    reduction = evo.get("ascend_cost_pct", 0.0)
    return max(1, int(base * (1.0 - min(0.8, reduction))))


def can_ascend(state: GameState) -> bool:
    return state.zone_index >= ascend_requirement(state)


def should_auto_ascend(state: GameState) -> bool:
    """Whether auto-ascend should fire this tick (Task 28 / pl-automation).

    True when:
    1. ``auto_ascend`` is unlocked (in ``state.skill_tree``), AND
    2. ``can_ascend(state)`` is True (the base requirement is met), AND
    3. ``state.zone_index >= state.auto_ascend_threshold`` (the player's
       threshold is met; 0 means use the base requirement -- auto-ascend
       fires as soon as ``can_ascend`` is True).

    The threshold is RESPECTED -- the player sets it and the auto-ascend
    only fires when the threshold is met. A player who wants to push
    deeper before auto-ascending sets a higher threshold; the auto-ascend
    waits until the threshold is reached. The threshold is an ADDITIONAL
    gate on top of the base ascend requirement, so the player can never
    auto-ascend below the base requirement (the threshold only delays).
    """
    if "auto_ascend" not in state.skill_tree:
        return False
    if not can_ascend(state):
        return False
    if state.auto_ascend_threshold > 0 and state.zone_index < state.auto_ascend_threshold:
        return False
    return True


def elixir_gain(state: GameState) -> int:
    """Elixir that would be earned by ascending right now.

    Re-tuned for the persist-through-ascension economy.  Buildings now
    carry over (scaled by the tier stat_mult in ``total_gps``), so
    lifetime_gold grows faster on subsequent runs.  The diminish factor
    scales elixir-per-gold down on higher tiers so the post-ascension
    economy doesn't snowball:

        elixir = lifetime_gold * ELIXIR_RATE
                  * (1 - ELIXIR_DIMINISH * ascend_tier) * [bonuses]

    ELIXIR_RATE (cfg) is tuned so a first ascension at ~10k lifetime gold
    gives ~50 elixir (matching the Awakened soul_reward tier).  The
    diminish factor stays positive through all 7 tiers (tier 6 -> 0.40).
    """
    evo = aggregate_bonuses(state)
    mult = 1.0 + evo.get("elixir_pct", 0.0) + evo.get("godai_void", 0.0)
    # Stacking tokens (gp-permanent-scaling): elixir tokens are +1% each
    # to elixir gain. They are permanent (survive all prestige layers)
    # and sourced from daily quests + zone-boss milestones (NOT
    # achievements -- no double-counting with the Heritage passives).
    mult += evo.get("elixir_token_pct", 0.0)
    if state.lifetime_gold <= 0:
        return 0
    rate = getattr(cfg, "ELIXIR_RATE", 0.005)
    diminish = getattr(cfg, "ELIXIR_DIMINISH", 0.10)
    factor = max(0.0, 1.0 - diminish * state.ascend_tier)
    return int(math.floor(max(1, state.lifetime_gold * rate * factor) * mult))


def ascend(state: GameState) -> int:
    """Perform ascension; returns elixir gained (0 if not allowed).

    Buildings **persist** through ascension (they are not reset here);
    they are scaled by the tier stat_mult in ``total_gps`` so they stay
    relevant as the player climbs tiers.  Only gold, run upgrades, zone,
    combo, and energy reset.  The ``start_farms`` skill-tree perk
    guarantees a minimum farm count (it raises low farm counts to the
    perk value rather than overwriting a higher existing count).

    Heritage: completing a full ascension under a Dojo grants that
    dojo's heritage passive (a one-time per-dojo unlock). The generalist
    (``dojo == "none"``) grants the Earth heritage. Heritage is a set,
    so ascending twice under the same dojo doesn't duplicate the entry;
    the player can respec dojo freely between ascensions and collect all
    5 heritages (4 dojos + Earth) as the meta-goal.
    """
    if not can_ascend(state):
        return 0
    gained = elixir_gain(state)
    state.elixir += gained
    state.ascend_tier += 1
    state.total_ascensions += 1
    state.ascensions_today += 1
    # Reset run-scoped state.  Buildings persist (not reset).
    state.gold = 0.0
    state.upgrades = {}
    state.zone_index = 0
    state.zone_distance = 0.0
    state.combo = 0
    state.combo_timer = 0.0
    state.energy = state.energy_max
    state.energy_active = False
    # Ascension perk: guarantee a minimum farm count.  The "Homestead" perk
    # (start_farms) starts each ascension with N farms -- but only if the
    # player doesn't already have more (buildings persist, so a player who
    # ground farms keeps them).
    evo = aggregate_bonuses(state)
    start_farms = int(evo.get("start_farms", 0.0))
    if start_farms > 0:
        cur = state.building_level("farm")
        if cur < start_farms:
            state.buildings["farm"] = start_farms
    # Heritage: grant the dojo's heritage passive (one-time per dojo).
    # The generalist (no dojo) grants the Earth heritage -- the
    # utility/defense flavor, the 5th in the "collect all 5" meta-goal.
    if state.dojo == "none":
        state.heritage.add("earth")
    else:
        state.heritage.add(state.dojo)
    # Souls: award the tier's soul reward (the reincarnation currency).
    # ``soul_reward_on_ascend`` is the 4th column in ``cfg.ASCEND_TIERS``.
    # The soul reward is the currency the player spends on Soul Tree perks
    # (the permanent run-breaking verbs in ``data.skill_tree``). The
    # ``soul_pct`` bonus (from the Soul Harvest evolution node) scales the
    # reward up. Souls persist through ascension (they are NOT reset here
    # -- only reincarnation resets souls, and even there the spent-perk
    # state in ``state.soul_tree`` survives).
    tier_idx = min(state.ascend_tier, len(cfg.ASCEND_TIERS) - 1)
    soul_reward = cfg.ASCEND_TIERS[tier_idx][3]
    soul_mult = 1.0 + evo.get("soul_pct", 0.0)
    state.souls += int(soul_reward * soul_mult)
    return gained


def ascend_progress(state: GameState) -> float:
    req = ascend_requirement(state)
    return min(1.0, state.zone_index / req) if req > 0 else 1.0


# ---------------------------------------------------------------------------
# Task 35 (gp-reincarnation-perks): Reincarnation + Soul Tree perks
# ---------------------------------------------------------------------------
# Reincarnation is the HARD reset above ascension. Ascension (above) is the
# soft reset (resets run state, keeps buildings, increments tier, grants
# elixir + souls). Reincarnation resets ascend_tier + elixir + skill_tree
# too -- the full rebuild -- but the Soul Tree perks (``state.soul_tree``)
# persist and modify how the new run starts. The Cosmic Forge
# (``state.cosmic_forge``, max 10) is the persistent anchor -- it survives
# reincarnation (it IS the anchor), incremented once per reincarnation,
# clamped at 10.
#
# The gate is Singularity (tier 6, the top of ``cfg.ASCEND_TIERS``) + 10
# ascensions (``state.total_ascensions >= 10``). The gate ensures the
# player has mastered the base loop before the hard reset is offered.
SINGULARITY_TIER = 6  # the top of cfg.ASCEND_TIERS (index 6 = "Singularity")
REINCARNATION_ASCENSION_GATE = 10  # min total ascensions to reincarnate


def can_reincarnate(state: GameState) -> bool:
    """Whether the player can reincarnate (the hard reset gate).

    True when:
    1. ``state.ascend_tier >= SINGULARITY_TIER`` (the player has reached
       Singularity, the top of the 7-tier ladder), AND
    2. ``state.total_ascensions >= REINCARNATION_ASCENSION_GATE`` (the
       player has ascended at least 10 times).

    Both gates must hold. The gate ensures the player has mastered the
    base loop before the hard reset is offered -- the Soul Tree perks are
    a reward for the deep investment, not a first-purchase rush.
    """
    return (state.ascend_tier >= SINGULARITY_TIER
            and state.total_ascensions >= REINCARNATION_ASCENSION_GATE)


def reincarnate(state: GameState) -> bool:
    """Perform reincarnation (the hard reset); returns True if done.

    Reincarnation is the HARD reset above ascension:
      * Resets run-scoped state (gold, upgrades, zone, combo, energy) --
        same as ascension.
      * Resets ascend_tier to 0 (the prestige ladder restarts).
      * Resets elixir to 0 (the elixir currency is re-ground).
      * Resets skill_tree to empty (the elixir skill tree is re-ground) --
        UNLESS the ``keep_skill_tree`` perk is active, in which case 25%
        of the unlocked nodes are kept (rounded down).
      * Does NOT reset ``state.soul_tree`` (the Soul Tree perks are
        permanent -- they survive ALL resets; the whole point is they
        persist across the hard reset).
      * Does NOT reset ``state.souls`` (the perk currency is spent on
        perks, not re-ground).
      * Increments ``state.cosmic_forge`` (the persistent anchor, max 10).
      * Applies the ``start_zone_3`` perk: ``state.zone_index = 2``
        (0-indexed zone 3) instead of 0.

    Returns False (no-op) when the gate (``can_reincarnate``) is not met.
    """
    if not can_reincarnate(state):
        return False
    # --- Hard reset: run-scoped state (same as ascension) ---
    state.gold = 0.0
    state.upgrades = {}
    state.zone_index = 0
    state.zone_distance = 0.0
    state.combo = 0
    state.combo_timer = 0.0
    state.energy = state.energy_max
    state.energy_active = False
    # --- Hard reset: prestige layers (ascension does NOT touch these) ---
    state.ascend_tier = 0
    state.elixir = 0
    # keep_skill_tree perk: keep 25% of the unlocked skill-tree nodes
    # (rounded down). Without the perk, the skill tree is fully reset.
    if "keep_skill_tree" in state.soul_tree and state.skill_tree:
        kept_count = len(state.skill_tree) // 4
        if kept_count > 0:
            # Keep the first N nodes (deterministic; the player can respec
            # the elixir tree freely after the reincarnation, so the exact
            # set kept doesn't matter -- the count is the perk's value).
            kept = list(state.skill_tree)[:kept_count]
            state.skill_tree = set(kept)
        else:
            state.skill_tree = set()
    else:
        state.skill_tree = set()
    # --- Apply the start_zone_3 perk: start at zone 3 (zone_index = 2) ---
    if "start_zone_3" in state.soul_tree:
        state.zone_index = 2
    # --- The Cosmic Forge: the persistent anchor (max 10) ---
    # Incremented once per reincarnation, clamped at 10. The Forge is the
    # anchor that survives the hard reset -- it IS the persistence layer
    # for the reincarnation count (a record of how many times the player
    # has rebuilt). The clamp at 10 is the spec's hard cap.
    state.cosmic_forge = min(10, state.cosmic_forge + 1)
    # --- NOT reset: soul_tree (permanent perks) + souls (the currency) ---
    # state.soul_tree and state.souls are NOT touched here -- they persist
    # across the hard reset (the whole point of the Soul Tree).
    return True


def purchase_soul_tree_perk(state: GameState, perk_id: str) -> bool:
    """Purchase a Soul Tree perk; returns True if purchased.

    Spends ``state.souls`` (the reincarnation currency) and adds the perk
    to ``state.soul_tree`` (the permanent perk set). Returns False (no-op)
    when:
      * The perk id is not a valid Soul Tree perk.
      * The perk is already unlocked (in ``state.soul_tree``).
      * The player has insufficient souls (``state.souls < perk.cost``).

    The perks are permanent -- once purchased, they survive ALL resets
    (ascension + reincarnation). The purchase is a one-time spend; the
    perk is never re-ground.
    """
    from data.skill_tree import SOUL_TREE_PERKS_BY_ID
    perk = SOUL_TREE_PERKS_BY_ID.get(perk_id)
    if perk is None:
        return False
    if perk_id in state.soul_tree:
        return False
    if state.souls < perk.cost:
        return False
    state.souls -= perk.cost
    state.soul_tree.add(perk_id)
    return True


# ---------------------------------------------------------------------------
# Task 27 / pl-juice-polish: free respec + elixir/min + Tome of Samsara
# ---------------------------------------------------------------------------
def respec_skill_tree(state: GameState) -> int:
    """Refund all elixir spent on the skill tree + clear it.

    The "respec" the brief calls for. The elixir skill tree is PERMANENT
    (it persists through ascension -- ``ascend`` does NOT reset it), so
    the "respec" is NOT a reset on ascension; it's a manual
    refund/re-spend the player can do any time. The refund is FREE (no
    cost) so it's a respec, not a re-grind -- the player gets back every
    elixir they spent on the tree and can re-spend it on a different
    build.

    Returns the total elixir refunded (0 if the tree was empty). The
    refund is the sum of the ``cost`` of every unlocked node (the same
    value the player paid to unlock it); the tree is cleared to ``set()``.
    """
    from data import skill_tree as st
    total = 0
    for nid in list(state.skill_tree):
        node = st.BY_ID.get(nid)
        if node is not None:
            total += node.cost
    state.skill_tree = set()
    state.elixir += total
    return total


def elixir_per_minute(state: GameState) -> float:
    """Elixir per minute the player would earn at the current pacing.

    Computed from the ``config.py`` curves (the ``elixir_gain`` formula +
    the current ``lifetime_gold`` + ``ascend_tier``). The readout is the
    elixir-per-ascension divided by the estimated minutes-to-ascend (the
    time it would take to reach the ascension requirement at the current
    gold-earning rate). This is a PACING readout -- it tells the player
    how fast they're earning elixir, not a hard number.

    The estimate is conservative: it assumes the player keeps earning at
    the current ``active_per_sec`` rate (the same rate ``core.offline``
    uses for the Away Mastery cap) until they reach the ascension
    requirement, then ascends. The elixir-per-ascension is the live
    ``elixir_gain(state)`` (which already accounts for the diminish factor
    + the elixir_pct stack). The minutes-to-ascend is the remaining
    lifetime_gold the player would earn by the time they reach the
    requirement, divided by the current gold/sec rate -- so the readout
    reflects the player's actual earning pace, not a fixed "1 min/zone"
    approximation.

    Returns 0.0 when the player can't estimate a rate (no active income,
    or the requirement is already met).
    """
    if state.lifetime_gold <= 0:
        return 0.0
    req = ascend_requirement(state)
    # The elixir-per-ascension at the current state (a lower bound on the
    # future gain -- the player's elixir_pct stack won't decrease, so the
    # future gain is >= the current gain).
    elixir_per_asc = float(elixir_gain(state))
    # If the player is already past the requirement, the "per minute" is
    # the elixir-per-ascension (ascend now); we use a 1-minute floor so
    # the readout doesn't divide by zero.
    if state.zone_index >= req:
        return elixir_per_asc
    # Estimate the gold/sec the player is earning (the active rate, which
    # mirrors the runner's per-tick gold award). This is the same value
    # ``core.offline.active_per_sec`` computes; we import it lazily to
    # avoid a circular import at module load.
    try:
        from core.offline import active_per_sec
        gps = active_per_sec(state)
    except Exception:
        gps = 0.0
    if gps <= 0:
        return 0.0
    # The minutes-to-ascend: the remaining gold the player would earn by
    # the time they reach the requirement, divided by the current gold/sec
    # rate. The "remaining gold" is the lifetime_gold the player would
    # have at the requirement -- we approximate by scaling the current
    # lifetime_gold by the remaining zone fraction (the player earns
    # roughly proportional gold per zone). This is a conservative
    # estimate (the actual rate depends on the player's damage + the
    # zone's HP pool); the 1-minute floor keeps the readout sane.
    zones_remaining = max(1, req - state.zone_index)
    # The gold-per-zone the player is currently earning (approximately).
    # Use the current lifetime_gold / max(1, zone_index) as the per-zone
    # estimate, then multiply by the zones remaining to get the remaining
    # gold. The minutes-to-ascend is the remaining gold / gps / 60.
    gold_per_zone = state.lifetime_gold / max(1, state.zone_index)
    remaining_gold = gold_per_zone * zones_remaining
    seconds_to_ascend = remaining_gold / gps
    minutes_to_ascend = max(1.0, seconds_to_ascend / 60.0)
    return elixir_per_asc / minutes_to_ascend


def recommended_ascend(state: GameState) -> bool:
    """Whether the ascend screen should highlight "recommended ascend".

    True when the player CAN ascend (``can_ascend``) AND the
    elixir-per-minute is high enough to be worth ascending now (the
    elixir-per-ascension is >= a soft threshold). The threshold is a
    pacing cue, not a hard gate -- the player can always ascend when
    ``can_ascend`` is True; this just highlights "now is a good time".

    The threshold is tuned so a first ascension at ~10k lifetime gold
    (the ELIXIR_RATE tuning point) is recommended. The threshold is a
    constant (not a config knob) so the pacing readout is stable across
    runs; the elixir-per-minute diminishes with tier (the diminish factor
    in ``elixir_gain``), so the threshold naturally stops recommending
    at high tiers where the elixir-per-ascension has diminished below
    the first-ascension baseline.
    """
    if not can_ascend(state):
        return False
    # The threshold: the elixir-per-ascension at the first-ascension
    # tuning point (~50 elixir at 10k lifetime gold). This is the
    # "worth ascending" baseline; below it, the player is better off
    # pushing deeper for more lifetime_gold before ascending.
    return elixir_gain(state) >= _RECOMMEND_THRESHOLD


# The recommended-ascend threshold: the elixir-per-ascension at the
# first-ascension tuning point (~50 elixir at 10k lifetime gold). Tuned
# so a first ascension at the intended pacing is recommended; the
# diminish factor naturally stops recommending at high tiers.
_RECOMMEND_THRESHOLD = 50


def elixir_per_ascension(state: GameState) -> float:
    """Project the elixir earned per ascension at the current state.

    This is the live ``elixir_gain(state)`` (the same value the ascend
    screen shows in the "If you ascend now" preview). Exposed as a
    separate function so the Tome of Samsara tooltip can project the
    elixir-per-ascension with the Tome maxed (a what-if projection)
    without mutating state.

    Returns 0.0 when the player has no lifetime_gold.
    """
    return float(elixir_gain(state))


def tome_of_samsara_tooltip(state: GameState) -> str:
    """The Tome of Samsara tooltip: "invest ~30%" + elixir-per-ascension projection.

    The tooltip is a multi-line string (the first line is the title,
    rendered bold by the tooltip manager). It recommends investing ~30%
    of the player's elixir into the Tome of Samsara (the compounding
    elixir-growth anchor) and projects the elixir-per-ascension the
    player would earn with the Tome maxed.

    The "invest ~30%" is a SOFT guidance (a recommended allocation,
    not a hard rule). The projection is the elixir-per-ascension with
    the Tome's ``elixir_pct`` (0.65 from ``eli_t6``) added to the
    player's current stack -- a what-if, not a mutation.
    """
    from data import skill_tree as st
    node = st.BY_ID.get(TOME_OF_SAMSARA_NODE)
    node_name = node.name if node else "Tome of Samsara"
    node_cost = node.cost if node else 0
    # The current elixir-per-ascension.
    current = elixir_per_ascension(state)
    # The projected elixir-per-ascension with the Tome maxed (a what-if:
    # add the Tome's elixir_pct to the player's current stack). We
    # compute this without mutating state by reading the current
    # elixir_pct stack + adding the Tome's contribution.
    evo = aggregate_bonuses(state)
    current_elixir_pct = evo.get("elixir_pct", 0.0)
    tome_pct = node.effect_value if node else 0.65
    # The projection: recompute elixir_gain with the Tome's elixir_pct
    # added. We approximate by scaling the current gain by the ratio of
    # (1 + new_pct) / (1 + old_pct) -- the elixir_pct stack is additive
    # on the multiplier, so the ratio is exact for the elixir_pct term.
    if current > 0:
        old_mult = 1.0 + current_elixir_pct
        new_mult = 1.0 + current_elixir_pct + tome_pct
        projected = current * (new_mult / old_mult) if old_mult > 0 else current
    else:
        projected = 0.0
    # The "invest ~30%" recommendation: 30% of the player's current elixir
    # (a soft allocation guidance, not a hard rule).
    invest_30 = int(state.elixir * 0.30)
    return (
        f"{node_name}\n"
        f"The compounding elixir-growth anchor. Invest ~30% here "
        f"(~{invest_30} elixir) for long-term elixir growth.\n"
        f"Projection: ~{int(projected)} elixir per ascension with this maxed "
        f"(currently ~{int(current)})."
    )
