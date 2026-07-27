# 05 — Skill Tree (Elixir, permanent)

A large, branching tree of 200+ nodes purchased with Elixir. Persists
across ascensions. Organized into branches; each node has a prerequisite
(parent) so the player unlocks in order.

## Branches
1. **Offense** — tap damage, auto-attack, crit chance, crit dmg.
2. **Economy** — gold drop, building output, away income, coin value.
3. **Elixir** — elixir gain %, elixir-from-bosses, ascension perks
   (start-with-farms, faster ascension).
4. **Energy** — energy timer, energy regen, energy from enemies.
5. **Firefly** — firefly spawn rate, gold drop, size, speed.
6. **Abilities** — unlock & upgrade active skills (Kunai Barrage,
   Shuriken Vortex, Rope Hook, Speed Step).
7. **Godai Elements** (advanced, unlocked by a gate node) — Void
   (elixir), Wind (GpS), Fire (coin gold), Water (hero power).

## Node shape
```
(id, name, branch, cost(elixir), prereq, effect_key, effect_value, desc)
```
`effect_key` is consumed by `aggregate_bonuses()` into a flat
`{key: total_value}` dict the engine reads.

## Effect keys (consumed by the engine)
- `tap_pct` — +% tap damage
- `atk_pct` — +% auto-attack damage
- `crit_pct` — +crit chance (absolute %)
- `crit_dmg_pct` — +crit damage multiplier
- `gold_pct` — +% gold from enemies
- `gps_pct` — +% building gold/sec
- `away_pct` — +% offline gold
- `coin_pct` — +% coin drop value
- `elixir_pct` — +% elixir gain
- `energy_timer` — +seconds of auto-katana duration
- `energy_regen` — +% energy regen rate
- `energy_from_kill` — +energy per kill
- `firefly_spawn` — +% firefly spawn rate
- `firefly_gold` — +% firefly gold
- `density_pct` — +% enemy density (reduces spawn interval)
- `combo_window` — +seconds combo decay window
- `combo_step` — +combo multiplier per combo
- `start_farms` — start ascension with N farms
- `ascend_cost_pct` — -% ascension requirement (QoL)
- `godai_void/wind/fire/water` — element multipliers

## Sample node layout (a representative subset — the full tree is ~200)
We'll generate the full tree programmatically: each branch has a root →
tier2 → tier3 → tier4 → tier5 chain, with costs scaling ~2.5x per tier
and effect values scaling ~1.5x per tier. Plus a few cross-branch gates.

## Unlock rules
- A node is unlockable if: prereq unlocked AND elixir ≥ cost AND not
  already unlocked.
- Some nodes are "gate" nodes that unlock a new branch (e.g. Godai).

## Aggregate
`aggregate_bonuses(unlocked_set) → {effect_key: sum(effect_value)}`.
Engine reads this each tick (cheap).
