# Endless Road — an idle adventure

A self-contained **pygame** idle game. Walk an endless road, auto-fight
monsters, summon heroes via gacha, upgrade them, evolve a skill tree,
and ascend for permanent power. **No external assets** — every sprite,
background, and effect is drawn from pygame primitives.

## Run

```bash
python3 main.py
```

Requires Python 3.11+ and `pygame` (`pip install pygame`). Audio is
optional (mixer is initialized best-effort; the game is silent if
unavailable; NumPy is used for procedural SFX but the game runs without it).

## Controls

| Key | Action |
|-----|--------|
| `0` | Main menu |
| `1` | Road (game) |
| `2` | Buildings |
| `3` | Upgrades |
| `4` | Skill tree |
| `5` | Pets |
| `6` | Ascension |
| `7` | Quests |
| `8` | Records |
| `9` | Settings |
| `H` | Hero loadout |
| `B` | Bestiary |
| `G` | Godai elements |
| `C` | Cosmetics |
| `P` / `Esc` | Pause |
| `F1` | FPS overlay |

Mouse: click the road to tap/attack, click nav buttons, list items,
upgrade buttons, and the welcome/offline-progress modal.

## Systems

- **Road** — a scrolling, day/night world with 9 zones, parallax
  hills + near-ground tufts, each zone with its own monster pool and a
  boss. The party auto-attacks the nearest monster; skills proc on
  cooldown.
- **Road events** — chests (bonus gold/coins/souls), shrines (temp
  attack buff), and elite monsters (tough + guaranteed rare drop)
  appear periodically to break up the grind.
- **Gacha** — 31 heroes across 5 rarities (common → mythic). Single &amp;
  10-pull, with a tiered pity system (rare+ at 20, epic+ at 60,
  legendary+ at 200). Pull reveal is rarity-tiered for drama.
- **Upgrades** — 6 stats per hero (atk/def/hp/spd/crit/cdmg) with
  geometric cost scaling. Stars auto-promote from duplicate pulls.
- **Evolution tree** — 4 branches (offense/defense/fortune/speed),
  16 nodes, global bonuses unlocked with souls.
- **Ascension** — 7 prestige tiers (Mortal → Singularity). Resets the
  road but keeps heroes, evolutions, and pity; grants a permanent stat
  multiplier + souls. Requires reaching zone 3 in the current run.
- **Offline progress** — closing the game earns gold/kills/coins at
  the current zone's rate (capped at 8h, shown in a welcome modal).
- **Achievements** — 14 milestones with rewards.
- **Records** — a dashboard of lifetime stats (distance, kills, bosses,
  pulls, ascensions, playtime, collection %, achievement progress).
- **Juice** — floating damage numbers, crit popups, screen shake,
  hit-stop on boss death, monster death bursts, skill VFX (beams/AOE/
  heals/auras), zone transition wipes, kill-streak milestones.
  All gated by a "Reduced motion" setting.
- **Sound** — procedurally synthesized SFX (no audio files) for hits,
  crits, kills, boss deaths, pulls, rare drops, ascension, evolution.
  Gated by the "Sound" setting.

## Save

Progress autosaves every 15s and on exit to
`~/.endless_road/save.json`. The save is forward-compatible (additive
schema); corrupt saves are backed up to `.bak`.

## Architecture

```
config.py        balance constants + number formatting
theme.py         palette, fonts, drawing helpers
utils.py         RNG, timers, easing
assets.py        procedural sprites, backgrounds, particles

data/            characters (roster+skills), monsters (zones+bosses),
                 evolution_tree

core/            state (save/load), gacha, upgrade, evolution, ascend,
                 inventory, offline, achievements

engine/          world (zones/spawn), combat (tick), loot, runner,
                 fx (floating text + skill VFX)

ui/              widgets + screens (menu, game, gacha, evolution,
                 ascend, inventory, settings)

main.py          Game controller + main loop
```

The simulation (`engine/`) is pure state and never draws; the UI
(`ui/`) reads it. The `Runner` ties the world + combat together and
owns the FX layer. Combat forwards damage/skill events to the FX
layer via module-level callbacks the runner wires up.
