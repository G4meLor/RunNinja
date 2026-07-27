# 02 — Core Loop & Currencies

## The loop
```
tap/auto-attack enemies → gold
   ↓
buy buildings (passive gold/sec) + run upgrades (damage, crit, density)
   ↓
push to higher zones → tougher enemies, more gold
   ↓
ascend → reset gold/buildings/upgrades → gain Elixir
   ↓
spend Elixir on permanent skill tree (200+ nodes)
   ↓
equip pets for the current goal
   ↓
repeat stronger (multipliers compound)
```

## Currencies (4)

### Gold (soft, run-scoped)
- Earned: killing enemies (tap damage), building income (gold/sec),
  firefly bonuses, quest rewards.
- Spent: buildings, run upgrades, pet bonding.
- Resets on ascension (buildings & run upgrades lost).
- Format: compact (k, M, B, ... → scientific notation at extreme scale).

### Elixir (prestige, permanent)
- Earned: on ascension, = f(total gold earned this run) × elixir
  multipliers (skill tree, pets, gear).
- Formula (our design): `elixir = floor( (lifetime_gold_this_run) ** 0.5
  × elixir_mult )` where `elixir_mult = 1 + sum(skill bonuses) + pet
  bonuses + gear bonuses`. Square-root curve → diminishing returns,
  encouraging frequent ascension.
- Spent: permanent skill tree nodes (200+).
- Persists across ascensions.

### Amber (premium, permanent)
- Earned: daily quests, achievements, rare events.
- Spent: pet gacha/pulls, cosmetics, convenience items (Kimono/Katana/
  Kabuto/Geta of Legends — flat/mult bonuses).
- Persists. Slow to accumulate.

### Medals (event, permanent)
- Earned: daily challenges, weekly challenges, events.
- Spent: medal shop exchanges (minor permanent boosts).
- Persists.

## Number scale
- Gold grows to scientific notation (1.2e30). Use compact formatting
  (k/M/B/T/Qa/.../aa) up to ~1e300, then scientific.
- All multipliers are multiplicative unless noted (additive %).

## Save model
- Single JSON file, autosave every 15s + on exit.
- Forward-compatible (additive schema; missing fields default).
- Offline progress computed on load (gold/kills/elixir-at-current-rate,
  capped at 8h).

## What resets on ascension
- gold → 0 (plus a small starter based on tier)
- buildings → 0 (except ascension-perk "start with N farms")
- run upgrades → 0
- zone_index → 0
- combo → 0
- energy → full

## What persists on ascension
- elixir, skill tree unlocks
- amber, medals
- pets (owned + bond levels)
- achievements
- total_distance, best_zone, total_ascensions, playtime
