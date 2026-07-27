# 03 — Combat, Tapping, Combo

## Scene
A ninja stands on the left of a scrolling road. Enemies spawn from the
right and walk left. The ninja auto-attacks the nearest enemy on a
cooldown (attack speed). The player can also **tap** (click) to deal
extra damage instantly — active play is rewarded.

## Tapping
- Click anywhere on the road → the ninja slashes the nearest alive enemy
  for `tap_damage`.
- `tap_damage` = base_tap × (1 + tap_upgrade_levels × tap_upgrade_growth)
  × crit_mult × combo_mult × skill_mults × pet_mults.
- Crit: roll crit_chance; if crit, damage × crit_dmg.
- Tap is the active-play lever; auto-attack is the idle baseline.

## Auto-attack (idle)
- The ninja auto-attacks the nearest enemy every `1/attack_speed` seconds.
- `attack_damage` = base_atk × upgrades × skills × pets × combo.
- When Auto Katana (energy) is active, attack_speed is boosted and the
  ninja attacks even while the player isn't tapping.

## Combo system
- Each kill increments `combo`.
- Combo decays after `combo_window` seconds (default 2.5s) without a kill.
- `combo_mult` = 1 + combo × combo_step (default 0.01, cap at combo_cap).
  - e.g. combo 50 → ×1.5, combo 100 → ×2.0, combo 200 → ×3.0 (cap).
- Combo resets on ascension and on party-wipe-respawn.
- **Combo is the core active-play reward** — keeping it alive (tapping,
  auto-katana) is the skill.

## Enemy
- HP scales by zone: `hp = zone_hp_base × zone_hp_growth ** zone_index
  × monster_hp_mult`.
- Damage to the ninja (if they reach the ninja): `dmg = zone_dmg_base ×
  zone_dmg_growth ** zone_index × monster_dmg_mult`.
- Gold drop: `gold = zone_gold_base × zone_gold_growth ** zone_index ×
  monster_gold_mult × combo_mult × gold_mults`.
- Enemy density (spawn rate) upgradable.
- Bosses: appear at zone end, higher HP/dmg/gold, guaranteed rare drop.

## Death
- On enemy death: drop gold, maybe coins/amber, advance combo, maybe
  trigger firefly spawn, FX (death burst, floating gold number).
- On ninja "death" (HP 0): combo resets, ninja respawns after a short
  delay at partial HP (the road never truly ends). Revive_pct evolution
  can improve this.

## Crit
- `crit_chance` upgradable (skill tree, run upgrades, pets).
- `crit_dmg` (multiplier, e.g. 1.5 = +50%) upgradable.
- Crit hits show a gold ★ floating number + sharper SFX.

## Active skills (burst windows)
- **Kunai Barrage** — throw N kunai, each dealing tap_damage × mult.
- **Shuriken Vortex** — AOE damage to all on-screen enemies for a duration.
- **Rope Hook** — pull/instant-kill weak enemies, spawns a bonus.
- **Speed Step** — boost attack/move speed for a duration.
- Each has an independent cooldown; the player sequences them for burst.
- Unlocked via the elixir skill tree.
