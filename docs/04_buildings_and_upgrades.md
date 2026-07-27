# 04 — Buildings & Run Upgrades

## Buildings (18 types, passive gold/sec)
Buildings are the idle-income backbone. Each has a level (count), a base
gold/sec, and a cost that scales geometrically per level.

| # | id | name | base_gps | base_cost | cost_growth | unlock_zone |
|---|----|------|---------|-----------|-------------|-------------|
| 1 | farm | Farm | 1 | 15 | 1.15 | 0 |
| 2 | sawmill | Sawmill | 5 | 100 | 1.16 | 0 |
| 3 | mine | Mine | 20 | 1.1k | 1.17 | 1 |
| 4 | tavern | Tavern | 80 | 12k | 1.18 | 2 |
| 5 | blacksmith | Blacksmith | 300 | 130k | 1.18 | 3 |
| 6 | barracks | Barracks | 1.0k | 1.4M | 1.19 | 4 |
| 7 | dojo | Dojo | 4.0k | 16M | 1.19 | 5 |
| 8 | shrine | Shrine | 15k | 180M | 1.20 | 6 |
| 9 | pagoda | Pagoda | 60k | 2.0B | 1.20 | 7 |
| 10 | castle | Castle | 250k | 22B | 1.21 | 8 |
| 11 | forge | Forge | 1.0M | 250B | 1.21 | 9 |
| 12 | treasury | Treasury | 4.0M | 2.8T | 1.22 | 10 |
| 13 | observatory | Observatory | 15M | 30T | 1.22 | 11 |
| 14 | dragon_vein | Dragon Vein | 60M | 330T | 1.23 | 12 |
| 15 | spirit_gate | Spirit Gate | 250M | 3.6Qa | 1.23 | 13 |
| 16 | celestial | Celestial Shrine | 1.0B | 40Qa | 1.24 | 14 |
| 17 | void_altar | Void Altar | 4.0B | 440Qa | 1.24 | 15 |
| 18 | infinity | Infinity Gate | 15B | 4.8Qi | 1.25 | 16 |

- `building_gps(level) = base_gps × level × (1 + global_building_mult)`.
- `building_cost(current_level) = base_cost × cost_growth ** current_level`.
- Total gold/sec = Σ building_gps(i) × (1 + upgrade_mults + skill_mults
  + pet_mults).
- "Buy 1 / Buy 10 / Buy Max" — buy Max computes how many levels the
  current gold affords (geometric series).
- Ascension perk (skill tree): start with N farms after ascending.

## Run upgrades (temporary, bought with gold)
Reset on ascension. Categories:

### Tap / damage
- **Tap Power**: +flat tap damage per level.
- **Tap Multiplier**: +% tap damage per level.
- **Auto Attack**: +flat auto-attack damage.
- **Crit Chance**: +crit% per level.
- **Crit Damage**: +crit dmg per level.

### Economy
- **Gold Drop**: +% enemy gold per level.
- **Building Output**: +% building gold/sec per level.
- **Away Income**: +% offline gold per level.
- **Coin Drop**: +% coin drop chance per level.

### Combat
- **Enemy Density**: -% spawn interval per level (more enemies).
- **Combo Window**: +seconds before combo decays.
- **Combo Step**: +combo multiplier per combo count.

### Costs scale geometrically; max level per upgrade (e.g. 100).

## Buy logic
- `upgrade_cost(current_level, base, growth) = base × growth ** level`.
- "Buy Max" for buildings: solve for max n such that
  `base_cost × cost_growth^level × (cost_growth^n - 1)/(cost_growth - 1)
  ≤ gold`.
