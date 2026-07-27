# 07 — Assets & UI (procedural, pygame primitives)

## Visual identity
A Japanese-ninja night-road theme: deep indigo sky, moon, paper-lantern
glows, silhouette hills (parallax), a stone road. The ninja is a small
procedural sprite. Enemies are silhouettes with colored accents. All
drawn with pygame primitives — **no external image files**.

## Palette
- Sky: deep indigo → violet gradient.
- Moon: pale cream circle with soft glow.
- Road: dark slate with dashed lane lines.
- Lanterns: warm orange/red glows along the road.
- Ninja: dark silhouette with a red headband accent.
- Gold: warm gold; Elixir: teal; Amber: amber; Medals: silver.
- Rarity: common (gray), rare (blue), epic (purple), legendary (gold),
  mythic (pink) — with shape symbols for color-blind safety.

## Procedural sprites (cached)
- **ninja_surface** — the hero; idle bob, slash animation on tap.
- **enemy_surface(shape, hue)** — slime, goblin, skeleton, beast, wraith,
  golem, demon, dragon, oni, etc.
- **building_surface(id)** — a small icon per building type (farm =
  hut, dojo = torii, castle = pagoda, etc.).
- **pet_surface(id)** — a small critter icon.
- **firefly_surface** — a glowing dot with a trail.
- **kunai/shuriken** — projectile sprites for active skills.
- **background(zone_index, hue)** — sky + parallax hills + road, cached
  per zone. Day/night tint overlay.

## Parallax (3 layers)
- Far: distant hills (scroll 0.3x).
- Mid: closer hills + lanterns (scroll 0.6x).
- Near: ground tufts (scroll 1.5x).
- Driven by `lane_scroll`, which advances with move speed.

## UI screens
1. **Menu** — title "Tap Ninja", Play/Settings, scrolling road bg.
2. **Game** — the road, ninja, enemies, HUD (currencies, zone, combo,
   energy bar), bottom panel (buildings + upgrade buttons), active-skill
   buttons, firefly layer.
3. **Buildings** — list of 18 buildings with level, gps, cost, Buy 1/10/Max.
4. **Upgrades** — run upgrades with level, cost, Buy.
5. **Skill tree** — the elixir tree (zoomable/scrollable), branches as
   columns, nodes with prereq lines, hover tooltips.
6. **Pets** — owned pets grid, equip up to 3, bond-level bars, pet
   gacha pull (Amber).
7. **Ascension** — tier ladder, elixir preview, confirm.
8. **Quests** — daily quests + achievements.
9. **Records** — lifetime stats dashboard.
10. **Settings** — sound, reduced motion, reset.

## HUD (top strip)
- Gold, Elixir, Amber, Medals pills.
- Zone name + progress bar.
- Combo counter (big, center, pulses on milestone).
- Energy bar (when unlocked).

## Bottom panel (game screen)
- Buildings quick-buy (top 3-4 buildings with Buy buttons).
- Active-skill buttons (cooldown overlays).
- "More" → buildings/upgrades screens.

## Juice
- Floating damage/gold numbers, crit popups (★).
- Screen shake + hit-stop on boss death / mythic pet pull.
- Death bursts, skill VFX (kunai trails, shuriken AOE ring, rope hook).
- Firefly catch sparkle.
- Combo milestone toasts.
- Ascension ceremony (dim, soul/elixir converge, tier reveal).
- All gated by "Reduced motion" setting.

## Sound (procedural, synthesized)
- tap, crit, kill, boss, coin, firefly, skill, ascend, gacha, evolve.
- Synthesized from NumPy waveforms; no audio files. Gated on sound_on.
