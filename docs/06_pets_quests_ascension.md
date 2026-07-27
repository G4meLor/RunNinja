# 06 — Pets, Quests, Ascension, Energy, Fireflies

## Pets
Collectible creatures providing passive buffs. Equipped (up to 3 active
at once). Each has a **bond level** (0–10) raised by feeding (gold or
amber). Higher bond → stronger buff.

### Pet list (12)
| id | name | type | buff_key | buff_per_level | unlock |
|----|------|------|----------|----------------|--------|
| frog | Frog | aquatic | firefly_gold | 0.05 | default |
| chicken | Chicken | bird | gold_pct | 0.015 | default |
| panda | Panda | critter | crit_dmg_pct | 0.03 | shuriken_vortex skill |
| otter | Otter | aquatic | speed_pct | 0.025 | default |
| penguin | Penguin | aquatic | firefly_value | 0.04 | default |
| squirrel | Squirrel | forest | gps_pct | 0.02 | rope_hook skill |
| turtle | Turtle | reptile | upgrade_cost_pct | 0.02 | default |
| hedgehog | Hedgehog | forest | building_cost_pct | 0.02 | default |
| cat | Cat | beast | quest_reward_pct | 0.03 | default |
| bunny | Bunny | beast | firefly_spawn | 0.03 | default |
| raccoon | Raccoon | forest | energy_regen | 0.02 | default |
| dragon | Dragon | mythical | elixir_pct | 0.04 | 5 ascensions |

- `pet_bonus(buff_key, bond)` = buff_per_level × bond.
- Equipped pets contribute to `aggregate_bonuses` alongside the skill tree.
- Pet gacha: spend Amber to roll a random pet (with pity). Duplicates
  raise bond.

## Quests
- **Daily quests**: 3 random quests from a pool, refresh every 24h
  (real time). Reward: Medals + small Amber.
  - Pool: "kill N enemies", "earn N gold", "reach combo N", "use N
    skills", "ascend once".
- **Achievements**: long-term milestones (first boss, zone 5, 100
  ascensions, collect all pets, etc.). Reward Amber + medals.
- Quest progress tracked on GameState; checked each tick.

## Ascension
- Requirement: reach a minimum zone (e.g. zone 5) this run.
- `elixir_gained = floor(lifetime_gold_this_run ** 0.5 × elixir_mult)`
  where `elixir_mult = 1 + sum(elixir_pct from skills/pets/gear)`.
- Resets: gold, buildings, run upgrades, zone, combo, energy.
- Keeps: elixir, skill tree, amber, medals, pets, achievements,
  total_distance, best_zone, total_ascensions, playtime.
- Ascension tier counter (cosmetic + small permanent bonus).

## Energy / Auto Katana
- Unlocked via the skill tree (an "unlock auto katana" node).
- While active: ninja auto-attacks at boosted speed; combo doesn't decay.
- Duration: `energy_timer` seconds (base 600s = 10 min, +skill seconds).
- Depletes while active; recharges by killing enemies
  (`energy_regen` rate + `energy_from_kill` per kill).
- Brief lockout after disabling.
- UI: an energy bar + activate button.

## Fireflies
- Special targets that spawn periodically (spawn rate upgradable).
- Catching one (tap or auto) → bonus gold (× firefly gold multiplier,
  boosted by combo + skills + pets).
- Spawn at screen edges; move erratically.
- High-combo + firefly + active-skill burst = the gold peak moment.
- Frog/Penguin/Bunny pets boost firefly mechanics.

## Zones
- 9+ zones, each with a monster pool + boss.
- Zone HP/dmg/gold scale exponentially per zone.
- Enemy density (spawn rate) upgradable.
- Boss at zone end; killing it advances to the next zone.
- Past the final zone: keep scaling by raw zone level (endless).
