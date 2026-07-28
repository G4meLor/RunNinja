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
    """Equipped pets: bond level × buff_per_level per pet's buff_key.

    Star levels (1-12, from duplicate eggs) and prestige counts (from
    Spirit Embers) are second progression axes on top of bond: each
    adds a small multiplier on top of the bond-based bonus, so a
    maxed pet (bond 10 + 12 stars + N prestiges) still has something
    to chase. The multipliers fold into ``pet_bonus`` so every
    consumer of ``aggregate_bonuses`` reads them unmodified.
    """
    out: dict[str, float] = {}
    for pid in state.equipped_pets:
        bond = state.pet_bond(pid)
        if bond <= 0:
            continue
        p = pet_def.BY_ID.get(pid)
        if p is None:
            continue
        stars = state.pet_stars.get(pid, 0)
        prestiges = state.pet_prestiges.get(pid, 0)
        out[p.buff_key] = out.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond, stars, prestiges)
    return out


def _pets_passive_provider(state: GameState) -> dict[str, float]:
    """Owned-but-unequipped pets contribute a fraction of their bonus.

    The capstone fractions make the 12-pet collection meaningful instead
    of "equip the 3 best": a bond-10 pet on the bench still pulls its
    weight (50%), and a bond-5 pet contributes 25%. Below bond 5 the
    pet contributes nothing passively — no free lunch for a fresh pull.

    The fraction is applied to the same ``pet_bonus`` the equipped
    provider uses (including the star + prestige multipliers), so the
    depth axes deepen the passive contribution too. Equipped pets are
    skipped here — they get the full bonus from ``_pets_provider``.
    """
    out: dict[str, float] = {}
    for pid, bond in state.pets.items():
        if pid in state.equipped_pets:
            continue
        if bond < 5:
            continue
        p = pet_def.BY_ID.get(pid)
        if p is None:
            continue
        frac = 0.25 if bond < 10 else 0.5
        stars = state.pet_stars.get(pid, 0)
        prestiges = state.pet_prestiges.get(pid, 0)
        out[p.buff_key] = out.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond, stars, prestiges) * frac
    return out


# Build specialization (Dojos) -- the per-ascension damage-path commit.
# The 4 Dojos map to the 4 Godai elements (Kage-bunshin->Void,
# Iaijutsu->Wind, Shikigami->Fire, Kusari-gama->Water); Earth is the
# generalist's utility/defense heritage. Specialization is ADDITIVE
# (buffs toward the chosen path), NOT a mutually-exclusive capstone -- a
# generalist default (dojo == "none") is viable, and respec is free (the
# player can change dojo any time; the only cost is re-earning any
# heritage already collected, which is a no-op since heritage is a set).
#
# The provider emits an additive ``dojo_<id>`` bonus the engine folds
# into the appropriate stat in ``compute_ninja_stats``. The stacking
# order is documented in config.MAX_TOTAL_DAMAGE_MULT: the dojo buff is
# an additive pct on the base stat, layered BEFORE the Godai element
# multipliers (which are %-on-base in their respective stats), so the
# two compose cleanly without interference.
_DOJO_BUFF = 0.15  # +15% additive buff toward the chosen path's stat


def _dojo_provider(state: GameState) -> dict[str, float]:
    """Per-ascension dojo commit: an additive buff toward the chosen path.

    ``state.dojo`` is one of ``none``, ``kage_bunshin``, ``iaijutsu``,
    ``shikigami``, ``kusari_gama``. ``none`` (the generalist) emits no
    buff -- the generalist default is fully viable without a dojo. Each
    named dojo emits a ``dojo_<id>`` key the engine reads in
    ``compute_ninja_stats`` and folds into the path's stat (tap for
    iaijutsu, auto for kage_bunshin, crit_dmg for shikigami, attack_speed
    for kusari_gama). The buff is ADDITIVE (a flat pct on the base
    stat), NOT a mutually-exclusive capstone -- choosing a dojo never
    reduces another stat, so hybrids stay viable.
    """
    out: dict[str, float] = {}
    if state.dojo == "none":
        return out
    out[f"dojo_{state.dojo}"] = _DOJO_BUFF
    return out


# Heritage passives -- the "collect all 5" meta-goal. Each heritage is
# granted once (the first ascension under that dojo) and persists across
# all future ascensions as a small permanent buff. The 5 heritages are
# the 4 dojos + Earth (the generalist's utility/defense heritage). The
# provider emits a ``heritage_<id>`` key per collected heritage; the
# engine folds each into its mapped stat (the same stat the dojo buffs,
# except Earth which buffs max_hp -- the utility/defense flavor).
_HERITAGE_BUFF = 0.10  # +10% permanent buff per collected heritage


def _heritage_provider(state: GameState) -> dict[str, float]:
    """Permanent heritage passives, one per collected heritage.

    ``state.heritage`` is a set of dojo ids the player has ascended
    under at least once (plus ``"earth"`` for the generalist). Each
    heritage emits a ``heritage_<id>`` key the engine folds into its
    mapped stat in ``compute_ninja_stats``. The buffs are ADDITIVE on the
    existing stat keys, so they stack cleanly with the dojo + Godai
    layers without interference.
    """
    out: dict[str, float] = {}
    for h in state.heritage:
        out[f"heritage_{h}"] = _HERITAGE_BUFF
    return out


# Stacking tokens -- the permanent +1%-per-token floor (gp-permanent-scaling).
# ``state.tokens`` is a ``dict[str, int]`` mapping token kind
# (strike / crit / coin / elixir) to count. Tokens are sourced from daily
# quests + zone-boss milestones (NOT achievements -- see Heritage below)
# and survive ALL prestige layers (ascension resets gold/upgrades/zone/
# combo/energy but never tokens). Each token of a kind is +1% (0.01) to
# that kind's stat; the provider emits ``<kind>_token_pct`` per kind.
#
# The acquisition rate is capped (see ``core.quests.award_boss_token`` and
# ``update_daily_progress``) so the +1%-per-token complements rather than
# replaces the exponential zone scaling -- a player who kills 100 bosses
# does NOT get 100 tokens.


def _tokens_provider(state: GameState) -> dict[str, float]:
    """Permanent stacking tokens: +1% (0.01) per token of each kind.

    ``state.tokens`` maps token kind (``strike`` / ``crit`` / ``coin`` /
    ``elixir``) to count. Each token of a kind contributes +1% to that
    kind's ``<kind>_token_pct`` key. The keys are distinct from the
    skill-tree/pet ``tap_pct`` / ``crit_pct`` / ``gold_pct`` / ``atk_pct``
    keys so they stack additively without collision.
    """
    out: dict[str, float] = {}
    for kind, count in state.tokens.items():
        if count <= 0:
            continue
        out[f"{kind}_token_pct"] = out.get(f"{kind}_token_pct", 0.0) + count * 0.01
    return out


# Heritage passives (achievements) -- the 14 one-shot amber/medal-payout
# achievements converted to permanent cumulative multipliers
# (gp-permanent-scaling). Each unlocked achievement contributes +0.5%
# (0.005) to a single ``heritage_pct`` key the engine folds into the
# stat stack. This is a DIFFERENT heritage from the Dojo heritage
# (Task 15's ``_heritage_provider`` reads ``state.heritage``, the set of
# dojo ids, and emits ``heritage_<id>`` keys). The two read disjoint
# state (``state.achievements`` vs ``state.heritage``) and emit disjoint
# keys (``heritage_pct`` vs ``heritage_<id>``) so there is no
# double-counting.
_HERITAGE_ACHIEVEMENT_BUFF = 0.005  # +0.5% permanent multiplier per achievement


def _heritage_achievements_provider(state: GameState) -> dict[str, float]:
    """Permanent cumulative multiplier from unlocked achievements.

    Each unlocked achievement contributes +0.5% (0.005) to a single
    ``heritage_pct`` key. The provider reads ``len(state.achievements)``
    (NOT the Dojo ``state.heritage`` set -- that is a different heritage;
    see ``_heritage_provider`` above). The two heritages read disjoint
    state and emit disjoint keys, so they stack cleanly without
    double-counting.
    """
    n = len(state.achievements)
    if n <= 0:
        return {}
    return {"heritage_pct": n * _HERITAGE_ACHIEVEMENT_BUFF}


# Epic Research (Task 18) -- the permanent meta-tree bought with
# medals/amber. A SEPARATE node set from the elixir skill tree: it reuses
# the ``SkillNode`` structure but lives in ``state.epic_research`` (a
# separate set from ``state.skill_tree``) and is bought with the
# underused currencies medals + amber (NOT elixir). The provider reads
# ``state.epic_research`` and emits the node effects into the flat bonus
# dict using the same effect keys the engine already reads
# (``elixir_pct``, ``away_pct``, ``upgrade_cost_pct``, ...), so the
# contributions stack additively with the elixir skill tree + pets +
# tokens + heritage without collision. The keys are the same ones the
# engine reads; the Epic Research nodes are a separate *source* of the
# same keys, not a separate set of keys.
#
# Away Mastery (``away_pct``) is consumed by ``core.offline.compute``,
# which CAPS the total offline earnings strictly below active+boosted
# earnings (see ``core.offline``), so a maxed Away Mastery never makes
# idling better than playing actively.
def _epic_research_provider(state: GameState) -> dict[str, float]:
    """Epic Research nodes: each unlocked node contributes its effect_value.

    Reads ``state.epic_research`` (the set of unlocked Epic Research node
    ids). Each unlocked node contributes its ``effect_value`` to its
    ``effect_key`` in the flat bonus dict. The keys are the same effect
    keys the engine already reads (``elixir_pct``, ``away_pct``,
    ``upgrade_cost_pct``), so the contributions stack additively with the
    elixir skill tree's contributions to the same keys.
    """
    out: dict[str, float] = {}
    for n in st.EPIC_RESEARCH_NODES:
        if n.id in state.epic_research:
            out[n.effect_key] = out.get(n.effect_key, 0.0) + n.effect_value
    return out


# Gear (cnt-gear-loot) -- 4 equipment slots with passive affixes. Each
# slot holds at most one gear piece (``state.gear[slot] = {affix, value,
# rarity}``); the provider emits the affix effects into the flat bonus
# dict using the same effect keys the engine already reads (``tap_pct``,
# ``atk_pct``, ``crit_pct``, ``crit_dmg_pct``, ``gold_pct``, ``speed_pct``,
# ``hp_pct``, ``def_pct``, ``energy_regen``, ``drop_pct``), so the gear
# contributions stack additively with the skill tree + pets + tokens +
# heritage contributions to the same keys. The gear provider is the
# MODEL half of the gear split (Task 20); the Forge UI (enhance/reroll/
# salvage) is Task 33.
#
# The stacking order is documented in ``config.MAX_TOTAL_DAMAGE_MULT``:
# gear is one of the additive sources in the ``evo`` layer; the total
# damage multiplier is clamped to ``MAX_TOTAL_DAMAGE_MULT`` (the sanity
# cap). The gear values are tuned (see ``config.GEAR_RARITY_MULT``) so
# even a full set of mythic pieces stays well under the cap.
def _gear_provider(state: GameState) -> dict[str, float]:
    """Gear pieces: each slot's affix contributes its value to the key.

    ``state.gear`` maps slot -> ``{affix, value, rarity}``. Each piece's
    ``affix`` is the effect key (the same keys the engine reads in
    ``aggregate_bonuses``), and ``value`` is the rarity-scaled
    contribution. Two slots with the same affix sum additively (the
    provider emits a single dict; ``aggregate_bonuses`` merges it
    additively by key).
    """
    out: dict[str, float] = {}
    for slot, g in state.gear.items():
        affix = g.get("affix")
        value = g.get("value", 0.0)
        if affix is None or value <= 0:
            continue
        out[affix] = out.get(affix, 0.0) + value
    return out


# Register the built-in providers. Order does not matter — contributions
# are summed additively by key.
register_provider(_skill_tree_provider)
register_provider(_pets_provider)
register_provider(_pets_passive_provider)
register_provider(_dojo_provider)
register_provider(_heritage_provider)
register_provider(_tokens_provider)
register_provider(_heritage_achievements_provider)
register_provider(_epic_research_provider)
register_provider(_gear_provider)


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
