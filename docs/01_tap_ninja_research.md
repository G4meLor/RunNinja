# Tap Ninja — Research Summary (Phase 1)

Source: Tap Ninja wiki (Fandom), Steam Community guides, Reddit r/TapNinja.
Synthesized from multiple searches via Gemini.

## Game identity
Tap Ninja is an **incremental idle / clicker RPG**. You play a ninja
standing on a road; enemies run across the screen and you tap (or
auto-attack) them for gold. The core loop is: **kill enemies → earn
gold → buy buildings & upgrades → ascend for Elixir → spend Elixir on
permanent skills → repeat stronger.**

## Currencies (4)
1. **Gold** — primary soft currency. Earned by killing enemies + building
   income. Spent on buildings & run upgrades. Resets on ascension.
2. **Elixir** — prestige currency. Earned on ascension, tied to coin/gold
   value of enemies killed. Spent on the permanent skill tree (200+ nodes).
   *No simple static formula* — it's dynamic, tied to coin generation ×
   elixir-multiplier upgrades/pets/gear. Diminishing returns → ascend
   frequently when elixir/min stops climbing.
3. **Amber** — premium/rare currency. Used for special purchases
   (pets, cosmetics, convenience). High-rank Amber items (Kimono, Katana,
   Kabuto, Geta of Legends) give flat/multiplicative bonuses.
4. **Medals** — earned from daily challenges & events. Shop exchanges.

## Combat & tapping
- **Tapping**: click the ninja to slash enemies crossing the screen.
- **Auto Katana**: an unlockable (via ascension) that auto-attacks for a
  set duration. Powered by the **Energy** system.
- **Combo multiplier**: consecutive kills build a combo → increases gold
  drops. Keeping the combo alive is the core active-play skill.
- **Active skills**: Kunai Barrage, Shuriken Vortex, Rope Hook, Speed Step,
  etc. Each has its own cooldown; players sequence them for burst windows.
- **Crit chance & crit multiplier**: core damage stats, upgradable.

## Energy system
- Unlockable via ascension upgrades. Powers the Auto Katana.
- Starts at ~10 min duration, extendable via Elixir upgrades.
- Depletes while active; recharges by killing enemies manually.
- Brief lockout after disabling before you can gain energy from kills.

## Buildings (18 types)
- Primary source of passive Gold/sec.
- Unlocked progressively: **Farm** (first), Sawmill, Mines, Tavern,
  Blacksmith, Barracks, Dojo, ... (18 total).
- Costs scale up per purchase; no static tier table (dynamic).
- "Buy All" / "Buy Next" buttons for efficient bulk buying.
- Ascension perk: start with 3 Farms after ascending.

## Upgrades (run-scoped)
- Temporary, bought with Gold during a run.
- Boost building production, tapping damage, crit chance, enemy density.
- Reset on ascension.

## Skill Tree (Elixir — permanent, 200+ nodes)
Categories:
- **Ability skills**: Rope Hook (unlocks pets/Squirrel), Shuriken Vortex,
  Speed Step — each with cooldown/multiplier upgrades.
- **Economic**: Coin Value, Gold/sec %, Away Income (offline), Building/
  Upgrade Cost reduction.
- **Enemy & drops**: Coin Drop, Enemy Density, Gem Drop Chance/Value.
- **Energy**: Energy Regen, Energy Timer, Energy From Enemies.
- **Firefly**: Firefly Spawn Rate, Gold Drop, Size, Speed.
- **Combat**: Crit Chance, Crit Multiplier, Challenge Gold.
- **Godai Elements** (advanced sub-tree): Void (elixir), Wind (GpS),
  Fire (coin gold), Water (hero power).

## Pets (equip multiple; provide passive buffs)
- **Frog** — firefly collection/elixir synergy (active meta).
- **Chicken** — flat gold/elixir income (~7.5%).
- **Panda** — crit, coin/elixir value, chest rarity (endgame).
- **Otter** — running speed (~25%), encounter rate (offline meta).
- **Penguin** — firefly value (offline meta).
- **Squirrel** — conquest/construction, wood/iron production (unlocked
  after Rope Hook).
- **Turtle** — upgrade discount.
- **Hedgehog** — building cost reduction.
- **Cat** — quest rewards/medals.
- **Bunny** — speed/firefly.
- **Raccoon** — construction.
- Common combos: Frog+Panda+Chicken (active elixir); Otter+Penguin+Dog
  (offline); Turtle+Hedgehog+Parrot (economy).

## Zones / stages
- Distinct zones/maps. Advancing → harder enemies, more gold.
- Enemy density upgradable via skill tree.

## Quests & achievements
- **Daily quests** — refresh daily, reward Medals/Amber.
- **Achievements** — long-term milestones.
- **Weekly challenges**.

## Ascension (prestige)
- Resets buildings, gold, run upgrades.
- Grants Elixir based on coin value of enemies killed (dynamic, ×
  multipliers from skills/pets/gear).
- Keeps: Elixir, skill tree, pets, achievements.
- Strategy: ascend frequently when elixir/min plateaus.

## Offline / away income
- "Away Income" skill boosts gold earned while closed.
- Offline elixir also possible (Otter/Penguin/Dog combo).

## Fireflies
- Special targets appearing periodically.
- High-multiplier events → wait for fireflies → burst skills → big gold.
- Spawn at screen edges; shurikens clear them fast.

## Meta-progression (late game)
- **Artifacts/Relics** — powerful global modifiers.
- **Research/Laboratory** — end-game scaling tiers, rare resources.

## Design principles to carry over
1. **Active vs idle balance** — active play (combo, skills) is rewarded but
   idle (buildings, auto-katana, offline) is viable.
2. **Frequent prestige** — ascend often; diminishing returns on long runs.
3. **Many compounding multipliers** — gold × crit × combo × pets × skills ×
   gear; numbers grow to scientific notation.
4. **Pet collection meta** — equipping the right pets for the goal is a
   core strategic layer.
5. **Burst windows** — active skills + fireflies + combo = satisfying peaks.
6. **Energy as a session gate** — limits active automation, encourages
   natural play cycles.
