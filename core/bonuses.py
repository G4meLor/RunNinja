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


# Register the built-in providers. Order does not matter — contributions
# are summed additively by key.
register_provider(_skill_tree_provider)
register_provider(_pets_provider)
register_provider(_pets_passive_provider)
register_provider(_dojo_provider)
register_provider(_heritage_provider)


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
