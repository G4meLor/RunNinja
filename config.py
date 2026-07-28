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
# Ascension
# ---------------------------------------------------------------------------
# Each ascension tier multiplies all stats and resets zone progress but
# preserves characters & gacha progress.  Higher tiers cost souls.
ASCEND_TIERS = (
    # (tier_name, stat_mult, soul_cost, soul_reward_on_ascend, flavor)
    ("Mortal", 1.00, 0, 10, "The beginning of every hero."),
    ("Awakened", 1.25, 50, 40, "A spark of power ignites within."),
    ("Transcendent", 1.60, 250, 120, "Limits begin to dissolve."),
    ("Divine", 2.10, 1200, 350, "Walking the road of gods."),
    ("Eternal", 3.00, 6000, 1000, "Time itself bends to your will."),
    ("Cosmic", 4.50, 30000, 3000, "The road stretches across galaxies."),
    ("Singularity", 7.00, 150000, 12000, "All roads converge into one."),
)


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
