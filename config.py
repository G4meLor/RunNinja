"""Global tunable constants for the idle game.

Every balance number lives here so the game can be re-tuned without
hunting through the code.  Values are deliberately exposed as a single
``Config`` namespace so other modules can read ``cfg.FOO`` and we keep a
clean separation between *rules* and *mechanics*.
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
WINDOW_W = 1280
WINDOW_H = 720
FPS_CAP = 60
TITLE = "Endless Road — an idle adventure"

# Logical play-field used by the world engine.  The HUD reserves the top
# strip; the rest is the road.
HUD_H = 96
ROAD_TOP = HUD_H
ROAD_H = 360
ROAD_BOTTOM = ROAD_TOP + ROAD_H
SKY_TOP = 0
SKY_H = ROAD_TOP

# Sidebar / bottom panel for the active character summary.
PANEL_H = WINDOW_H - ROAD_BOTTOM


# ---------------------------------------------------------------------------
# Currency & progression curves
# ---------------------------------------------------------------------------
# Gold is the soft currency dropped by monsters.  Coins are the premium
# currency from ascension.  Souls are the ascension-specific currency.
GOLD_START = 0
COIN_START = 0
SOUL_START = 0

# Distance travelled per second at base move speed (pixels-ish, abstract).
BASE_SPEED = 90.0
# Each speed upgrade multiplies speed by this.
SPEED_UPGRADE_MULT = 1.06

# Monster HP / damage / gold curves.  We use a smooth exponential zone
# scaling so numbers stay readable for a long time.
ZONE_HP_BASE = 18.0
ZONE_HP_GROWTH = 1.18          # per zone level
ZONE_DMG_BASE = 4.0
ZONE_DMG_GROWTH = 1.14
ZONE_GOLD_BASE = 6.0
ZONE_GOLD_GROWTH = 1.16

# Infinite zone cycling: past zone 9 the 9 themed zones repeat at scaled
# stats. ``cycle = floor(zone_index / 9)``; the in-cycle zone
# (``zone_index % 9``) drives the base growth, and the cycle multiplier
# drives the long-run scaling so the endgame never stalls. The road
# continues forever with the same 9 themed zones + bosses; only the
# scaler changes (no new state field -- cycle is derived).
CYCLE_HP_MULT = 8.0
CYCLE_DMG_MULT = 7.0
CYCLE_GOLD_MULT = 9.0

# How often a monster spawns (seconds) at base.
SPAWN_INTERVAL = 1.1
SPAWN_INTERVAL_MIN = 0.45      # floor so the road never goes empty

# Distance (in "meters", abstract units) needed to advance a zone.
ZONE_DISTANCE = 600.0


# ---------------------------------------------------------------------------
# Gacha
# ---------------------------------------------------------------------------
GACHA_SINGLE_COST = 120        # coins
GACHA_MULTI_COST = 1080        # 10-pull, slight discount
GACHA_RATES = {
    "common": 0.60,
    "rare": 0.27,
    "epic": 0.10,
    "legendary": 0.025,
    "mythic": 0.005,
}
# Pity: guarantee a rare+ after N pulls without one, epic+ after M.
PITY_RARE = 20
PITY_EPIC = 60
PITY_LEGENDARY = 200

# Soft-pity ramp: after SOFT_PITY_START[rarity] pulls without that rarity,
# the rate climbs by SOFT_PITY_INCREMENT per pull. This shortens the
# PITY_LEGENDARY=200 grind — past 150 pulls the legendary rate ramps up
# sharply so a 200-pull dry streak is very unlikely.
SOFT_PITY_START = {  # per rarity: pulls without that rarity before the ramp
    "rare": 15,
    "epic": 50,
    "legendary": 150,
    "mythic": 190,
}
SOFT_PITY_INCREMENT = 0.02   # +2% per pull after the threshold

# Spark/pity-token shop: 1 token per pull, trade SPARK_SHOP_COST for any
# unlocked non-maxed pet. Pity tokens are cumulative across banners.
SPARK_SHOP_COST = 40

# Early-pity guarantee: in the first EARLY_PITY_WINDOW pulls of a new
# banner, guarantee at least one rare+ (one-time-per-banner).
EARLY_PITY_WINDOW = 10


# ---------------------------------------------------------------------------
# Gear (cnt-gear-loot)
# ---------------------------------------------------------------------------
# 4 gear slots, each with a passive affix pool. A dropped gear piece has one
# affix (random from the slot's pool) scaled by the rarity multiplier. The
# rarity distribution reuses ``GACHA_RATES`` (the same table the pet gacha
# uses) so the drop economy is consistent: a common drop is ~60% of kills,
# a mythic is ~0.5%. The gear provider in ``core/bonuses.py`` reads
# ``state.gear`` and emits the affix effects into the flat bonus dict, so
# gear stacks additively with the skill tree + pets + tokens + heritage
# contributions (same effect keys, additive by key).
#
# The stacking order is documented in ``MAX_TOTAL_DAMAGE_MULT`` above:
# gear is one of the additive sources in the ``evo`` layer; the total
# damage multiplier is clamped to ``MAX_TOTAL_DAMAGE_MULT`` (the sanity
# cap). Gear values are tuned so even a full set of mythic pieces stays
# well under the cap (a single mythic piece is at most +200% on a pct
# key, additive with the other sources, not multiplicative).
GEAR_SLOTS = ("blade", "mask", "talisman", "cloak")

# Affix pool per slot: ``(effect_key, base_value)``. The base value is the
# COMMON-rarity value; the actual dropped value is ``base * GEAR_RARITY_MULT[rarity]``.
# The effect keys are the same keys the engine already reads in
# ``aggregate_bonuses`` (``tap_pct``, ``atk_pct``, ``crit_pct``,
# ``crit_dmg_pct``, ``gold_pct``, ``speed_pct``, ``hp_pct``, ``def_pct``,
# ...), so gear stacks additively with the skill tree + pets + tokens +
# heritage contributions to the same keys.
#
# The 4 slots are themed by the 4 broad playstyles:
#   * **blade**  -- offense (tap + crit + crit dmg)
#   * **mask**   -- auto-attack + attack speed (the idle path)
#   * **talisman** -- economy (gold + drop + crit chance)
#   * **cloak**  -- defense + utility (hp + defense + energy)
GEAR_AFFIXES: dict[str, tuple[tuple[str, float], ...]] = {
    "blade": (
        ("tap_pct", 0.05),        # +5% tap damage (common)
        ("crit_dmg_pct", 0.10),   # +10% crit damage (common)
        ("crit_pct", 0.02),       # +2% crit chance (common)
    ),
    "mask": (
        ("atk_pct", 0.05),        # +5% auto-attack damage (common)
        ("speed_pct", 0.05),      # +5% attack speed (common)
        ("tap_pct", 0.03),        # +3% tap damage (common, hybrid)
    ),
    "talisman": (
        ("gold_pct", 0.08),       # +8% gold from enemies (common)
        ("crit_pct", 0.02),       # +2% crit chance (common)
        ("drop_pct", 0.05),       # +5% rare drop chance (common)
    ),
    "cloak": (
        ("hp_pct", 0.05),         # +5% max HP (common)
        ("def_pct", 0.05),        # +5% defense (common)
        ("energy_regen", 0.05),   # +5% energy regen (common, utility)
    ),
}

# Rarity multiplier on the base affix value. Reuses the GACHA_RATES rarity
# ladder (common/rare/epic/legendary/mythic): a common drop is the base
# value, a mythic drop is 8x the base. The multipliers are tuned so a
# single mythic piece is a significant but not game-breaking additive
# contribution (e.g. a mythic blade's tap_pct is 0.05 * 8 = +40%, which
# stacks additively with the skill tree + pets + tokens + heritage
# contributions to tap_pct, all under the MAX_TOTAL_DAMAGE_MULT cap).
GEAR_RARITY_MULT = {
    "common": 1.0,
    "rare": 2.0,
    "epic": 4.0,
    "legendary": 6.0,
    "mythic": 8.0,
}


# ---------------------------------------------------------------------------
# Upgrade economy
# ---------------------------------------------------------------------------
# Run upgrades (Tap Ninja — temporary, bought with gold, reset on ascension)
# ---------------------------------------------------------------------------
# (key, label, base cost, base effect per level, effect growth per level)
TAP_UPGRADE_DEFS = (
    ("tap_power", "Tap Power", 25, 2.0, 1.05),         # +flat tap damage
    ("tap_mult", "Tap Multiplier", 60, 0.05, 1.02),    # +% tap damage
    ("auto_attack", "Auto Attack", 40, 2.0, 1.05),     # +flat auto-attack damage
    ("crit_chance", "Crit Chance", 80, 0.01, 1.01),   # +crit% per level
    ("crit_dmg", "Crit Damage", 80, 0.05, 1.02),      # +crit dmg per level
    ("gold_drop", "Gold Drop", 50, 0.05, 1.03),       # +% enemy gold
    ("building_output", "Building Output", 100, 0.05, 1.02),  # +% building gps
    ("away_income", "Away Income", 120, 0.05, 1.02),   # +% offline gold
    ("enemy_density", "Enemy Density", 70, 0.04, 1.02),  # +% density (less spawn interval)
    ("combo_window", "Combo Window", 60, 0.5, 1.02),   # +seconds combo decay
    ("combo_step", "Combo Step", 100, 0.005, 1.01),    # +combo mult per combo
    ("vitality", "Vitality", 60, 20.0, 1.05),          # +max HP per level
    ("defense", "Defense", 80, 1.0, 1.04),             # +flat damage reduction
    # --- Task 22: run upgrade expansion (13 -> 20) ---
    # Tap-specialist: +crit chance for taps, +tap attack speed, +% tap dmg.
    ("tap_crit", "Tap Crit", 90, 0.01, 1.01),          # +crit chance for taps
    ("tap_speed", "Tap Speed", 90, 0.02, 1.02),        # +tap attack speed
    ("tap_mastery", "Tap Mastery", 100, 0.03, 1.02),   # +% tap damage capstone
    # Active-skill-adjacent: +skill damage, +skill cooldown reduction.
    ("skill_dmg", "Skill Power", 110, 0.05, 1.03),     # +skill damage multiplier
    ("skill_cd", "Skill Haste", 130, 0.02, 1.01),      # +skill cooldown reduction
    # Combo-decay-resistance: +extra combo grace, +slower combo decay.
    ("combo_grace", "Combo Grace", 70, 0.2, 1.02),     # +extra combo grace time
    ("combo_sustain", "Combo Sustain", 120, 0.01, 1.01),  # +combo decay resistance
    # --- Task 24: tap-vs-auto rebalance (gp-tap-auto-rebalance) ---
    # auto_mult mirrors tap_mult so auto-attack gets the same multiplicative
    # upgrade path tap has had since launch. Tuned (base=0.025, growth=1.02)
    # so at max upgrades the tap:auto ratio is ~3:1 (not the pre-rebalance
    # 58:1 / 94:1). The base is half of tap_mult's (0.05) so tap retains a
    # meaningful-but-bounded edge (the active-play bonus), while auto is the
    # backbone (auto_damage >= tap_damage at level 0).
    ("auto_mult", "Auto Multiplier", 60, 0.025, 1.02),  # +% auto-attack damage
)

# Quick-lookup maps for the engine.
UPGRADE_BASE_COST = {d[0]: d[2] for d in TAP_UPGRADE_DEFS}
UPGRADE_BASE_EFFECT = {d[0]: d[3] for d in TAP_UPGRADE_DEFS}
UPGRADE_EFFECT_GROWTH = {d[0]: d[4] for d in TAP_UPGRADE_DEFS}
UPGRADE_COST_GROWTH = 1.15
UPGRADE_MAX_LEVEL = 100

# Legacy alias (some modules may still read UPGRADE_DEFS).
UPGRADE_DEFS = TAP_UPGRADE_DEFS


# Combo curve: asymptotic approach to COMBO_MULT_CAP.
# combo_step upgrade reduces COMBO_TAU (faster ramp), not the step.
COMBO_TAU = 50.0      # combo count at which the multiplier is ~63% of cap


# ---------------------------------------------------------------------------
# Tap-vs-auto rebalance (Task 24 / gp-tap-auto-rebalance)
# ---------------------------------------------------------------------------
# Tap base scale: the tap base CONSTANT (10.0) is scaled down so auto is the
# backbone at level 0 (auto_damage >= tap_damage). The flat upgrade
# ``tap_power`` dominates both bases at high levels, so the constant mainly
# sets the early-game flavor: at level 0, tap = 10 * 0.2 = 2, auto = 8. The
# tap_mult / auto_mult run upgrades then bring tap up to ~3x auto at max.
TAP_BASE_SCALE = 0.2       # tap base constant scaled down ~5x (2.0 vs 10.0)

# Tap fatigue: anti-macro for active tapping. Above TAP_FATIGUE_THRESHOLD
# taps in the last TAP_FATIGUE_WINDOW seconds, each additional tap reduces
# the tap damage multiplier by TAP_FATIGUE_PER_TAP (5%), floored at
# TAP_FATIGUE_FLOOR (0.3x) so tapping never becomes useless. The window is
# 1 second (taps older than 1s drop out of the count). This caps the
# active-burst upside so a macro that fires 100 taps/s does not trivialize
# the game; the floor (0.3x) keeps tap meaningful even under heavy fatigue.
TAP_FATIGUE_PER_TAP = 0.05    # 5% per tap above threshold
TAP_FATIGUE_THRESHOLD = 5     # taps/window before fatigue kicks in
TAP_FATIGUE_FLOOR = 0.3       # floor (tapping never becomes useless)
TAP_FATIGUE_WINDOW = 1.0      # seconds; the rolling window for tap counting


# ---------------------------------------------------------------------------
# Damage multiplier sanity cap
# ---------------------------------------------------------------------------
# Sanity cap on the total damage multiplier (the product of all stacking
# sources). Without a cap, a bug or future content stack (gear + elements +
# tokens + heritage + epic research) could silently produce 1e12x damage
# and trivialize the game. This cap is the last line of defense.
#
# Stacking order (documented):
#   total_dmg = base
#              * tier_mult          (ascension tier stat_mult)
#              * combo_mult          (asymptotic, <= COMBO_MULT_CAP)
#              * evo                (skill tree + pets aggregate)
#              * godai_element       (Godai Elements branch)
#              * gear                (future: equipment set bonuses)
#              * tokens              (future: buff tokens)
#              * heritage            (future: heritage bonuses)
#              * epic_research       (future: epic research tree)
#   then clamped to MAX_TOTAL_DAMAGE_MULT.
MAX_TOTAL_DAMAGE_MULT = 1e9


# ---------------------------------------------------------------------------
# Ascension
# ---------------------------------------------------------------------------
# Each ascension tier multiplies all stats and resets zone progress but
# preserves characters & gacha progress.  Higher tiers cost souls.
#
# The 7 tier NAMES remain as labels for the ascend UI (the ladder shows the
# progression: Mortal -> Awakened -> ... -> Singularity). The flat
# ``stat_mult`` column they used to carry is DEPRECATED -- the live
# multiplier is ``1.6 ** tier`` (see ``engine.ninja._ascend_tier_mult`` and
# ``core.game_economy._tier_mult``). The column is kept here (set to 0.0)
# so any code that still indexes it does not crash; the UI reads the live
# value from the formula. The ``soul_cost`` and ``soul_reward_on_ascend``
# columns are still authoritative.
ASCEND_TIERS = (
    # (tier_name, stat_mult_deprecated, soul_cost, soul_reward_on_ascend, flavor)
    ("Mortal", 0.0, 0, 10, "The beginning of every hero."),
    ("Awakened", 0.0, 50, 40, "A spark of power ignites within."),
    ("Transcendent", 0.0, 250, 120, "Limits begin to dissolve."),
    ("Divine", 0.0, 1200, 350, "Walking the road of gods."),
    ("Eternal", 0.0, 6000, 1000, "Time itself bends to your will."),
    ("Cosmic", 0.0, 30000, 3000, "The road stretches across galaxies."),
    ("Singularity", 0.0, 150000, 12000, "All roads converge into one."),
)

# Elixir awarded on ascension.  Re-tuned for the persist-through-ascension
# economy: buildings now carry over (scaled by the tier multiplier in
# total_gps), so lifetime_gold grows faster on subsequent runs.  The
# diminish factor scales elixir-per-gold down on higher tiers so the
# post-ascension economy doesn't snowball.
#
#   elixir = lifetime_gold * ELIXIR_RATE * (1 - ELIXIR_DIMINISH * tier) * [bonuses]
#
# ELIXIR_RATE is tuned so a first ascension at ~10k lifetime gold gives
# ~50 elixir (matching the Awakened soul_reward tier).  ELIXIR_DIMINISH
# is 0.10 so the factor stays positive through all 7 tiers (tier 6 -> 0.40).
# Note: the tier multiplier is now ``1.6 ** tier`` (steeper than the old
# flat ladder at high tiers); the diminish factor is a flat per-tier
# scalar that does NOT track tier_mult, so the elixir economy is
# unaffected by the tier-formula change. The building-unlock regression
# test (tests/test_building_unlock.py) guards the first-3-ascensions
# balance.
ELIXIR_RATE = 0.005
ELIXIR_DIMINISH = 0.10


# ---------------------------------------------------------------------------
# Evolution tree
# ---------------------------------------------------------------------------
# Each node grants a passive bonus.  Branches let the player specialise.
# Format: id, name, branch, cost(souls), prereq, effect-key, effect-value, desc
EVOLUTION_NODES = (
    # --- Offense branch ---
    ("edge", "Razor Edge", "offense", 5, None, "atk_pct", 0.10,
     "+10% attack for all characters."),
    ("fury", "Inner Fury", "offense", 12, "edge", "atk_pct", 0.10,
     "+10% attack. Stacks with Razor Edge."),
    ("overdrive", "Overdrive", "offense", 30, "fury", "atk_pct", 0.15,
     "+15% attack. The road trembles."),
    ("executioner", "Executioner", "offense", 80, "overdrive", "crit_dmg_flat", 0.5,
     "+50% crit damage."),
    # --- Defense branch ---
    ("bulwark", "Bulwark", "defense", 5, None, "def_pct", 0.10,
     "+10% defense."),
    ("warden", "Warden's Will", "defense", 12, "bulwark", "hp_pct", 0.10,
     "+10% max HP."),
    ("phoenix", "Phoenix Heart", "defense", 30, "warden", "revive_pct", 0.25,
     "Revive once per zone at 25% HP."),
    ("eternal_guard", "Eternal Guard", "defense", 80, "phoenix", "def_pct", 0.20,
     "+20% defense."),
    # --- Fortune branch ---
    ("greed", "Golden Touch", "fortune", 5, None, "gold_pct", 0.15,
     "+15% gold from monsters."),
    ("magnet", "Loot Magnet", "fortune", 12, "greed", "drop_pct", 0.10,
     "+10% rare drop chance."),
    ("midas", "Midas Veins", "fortune", 30, "magnet", "gold_pct", 0.25,
     "+25% gold."),
    ("soul_harvest", "Soul Harvest", "fortune", 80, "midas", "soul_pct", 0.30,
     "+30% souls from ascension."),
    # --- Speed branch ---
    ("swift", "Swift Wind", "speed", 5, None, "speed_pct", 0.08,
     "+8% move speed."),
    ("momentum", "Momentum", "speed", 12, "swift", "speed_pct", 0.08,
     "+8% move speed."),
    ("warp", "Warp Step", "speed", 30, "momentum", "spawn_reduce", 0.10,
     "Monsters spawn 10% faster."),
    ("time_dilation", "Time Dilation", "speed", 80, "warp", "speed_pct", 0.15,
     "+15% move speed."),
)


# ---------------------------------------------------------------------------
# Number formatting helpers (used by UI)
# ---------------------------------------------------------------------------
# NOTE: ``format_number``, ``lerp``, ``clamp``, and the easing functions
# used to live here too, but they are now canonically defined in
# ``utils.py``.  We keep this section as a pointer so anyone grepping for
# them in config finds the right module.
# The canonical implementations: utils.format_number, utils.lerp,
# utils.clamp, utils.ease_out_cubic, utils.ease_in_out_cubic, utils.smoothstep.
