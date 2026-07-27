# Big Bang Enhance — Multi-Agent Orchestration Design

**Date:** 2026-07-27
**Status:** Design approved (orchestration); spec content to be produced by Phase A–C
**Owner:** tmchien

## 1. Goal

"Big bang enhance" Tap Ninja — một idle adventure game bằng pygame — trên
**cả 4 chiều**:

1. **Graphics & visual richness** — nâng cấp từ primitives đơn giản → pixel
   art procedural phong phú (sprite đa khung hoạt hình, parallax nhiều lớp,
   day/night/weather, zone atmosphere, UI polish).
2. **Content breadth** — zones/enemies/bosses/heroes/pets/skills/quests mở
   rộng: boss phases & attack patterns, hero roster phong phú, enemy
   variety, quest variety.
3. **Gameplay depth & systems** — combo techniques, elemental affinities
   (godai), equipment/gear, dungeon/boss-rush mode, mini-games, prestige
   layers mới.
4. **Polish & balance** — economy curves, progression pacing, FX juice
   (shake/particles/hit-stop), procedural SFX richness, onboarding,
   accessibility, UX flow.

## 2. Constraints

- **Không ràng buộc** theo yêu cầu của user: được tự do sáng tạo, có thể
  thay đổi toàn bộ repo (tech stack, assets, architecture, save schema).
- Quy mô **lớn** — tận dụng tối đa đa dạng ý tưởng của nhiều game tham chiếu
  và lối suy nghĩ phóng khoáng.
- Một **spec bao trùm** cả 4 chiều (không chia từng chiều thành chu kỳ riêng).

## 3. Orchestration Architecture

Phased fan-out + critique + synthesis, rồi per-feature specialist
implementation. Năm phase (A–E):

```
Phase A: RESEARCH & IDEATION        ~16 agents, fan-out, song song
Phase B: CRITIQUE                   ~5 agents, adversarial panel
Phase C: SYNTHESIS                  ~2 agents, gộp + sequencing
Phase D: SPEC FINALIZATION          main loop (viết + self-review + user review)
Phase E: IMPLEMENTATION             writing-plans → ~25-30 specialist agents (worktrees)
```

Phase A–C chạy trong **một Workflow** (deterministic fan-out). Phase D tôi
(main loop) tự viết spec từ output. Phase E tách ra ngoài Workflow qua
`writing-plans` skill + specialist dispatch (mỗi feature trong worktree
riêng).

## 4. Phase A — Research & Ideation (~16 agents, `parallel()`)

16 agent chia 3 nhóm, chạy song song. Mỗi agent trả về structured findings
theo schema thống nhất.

### Nhóm 1 — Reference game research (8 agents)

Mỗi agent nghiên cứu 1 game tham chiếu và rút ra những gì Tap Ninja có thể
học hỏi (mechanics, progression curves, visual style, juice):

1. **Tap Titans / Tap Titans 2** — tap combat, hero roster, skill tree,
   prestige layers.
2. **Tap Ninja (game gốc)** — so sánh trực tiếp, tìm khoảng trống.
3. **Vampire Survivors** — enemy waves, build variety, auto-combat juice,
   boss patterns.
4. **Clicker Heroes / Clicker Heroes 2** — idle scaling, zone progression,
   hero unlocks.
5. **Idle Slayer / Idle Apocalypse** — idle economy, prestige depth,
   multi-currency.
6. **Egg Inc / Realm Grinder** — idle pacing, achievement-driven
   progression, automation.
7. **Gacha design** (Genshin / Fire Emblem Heroes / Arknights) — pity
   systems, rarity tiers, pull drama, character design.
8. **Pixel-art idle games** (retro idle / Saturnalia-style) — procedural
   pixel art techniques, palette, animation.

### Nhóm 2 — Dimension design research (5 agents)

9. **Graphics & visual richness** — nâng primitives → pixel art: sprite
   sheets đa khung, parallax nhiều lớp, day/night/weather, zone atmosphere,
   UI polish, tất cả procedural (pygame + NumPy).
10. **Content breadth** — zones/enemies/bosses/heroes/pets/skills/quests
    mở rộng: boss phases & attack patterns, hero roster, enemy variety,
    quest variety.
11. **Gameplay depth & systems** — combo techniques, elemental affinities
    (godai), equipment/gear, dungeon/boss-rush mode, mini-games, prestige
    layers mới.
12. **Polish & balance** — economy curves, progression pacing, FX juice
    (shake/particles/hit-stop), procedural SFX richness, onboarding,
    accessibility, UX flow.
13. **Idle game math & curves** — exponential scaling, prestige
    multipliers, breakpoint analysis, số lớn (K/M/B/T formatting), balancing
    auto vs tap.

### Nhóm 3 — Technical feasibility (3 agents)

14. **Pygame performance** — sprite caching, surface conversion, particle
    pooling, draw batching, frame budget 60fps với nhiều entities.
15. **Procedural asset generation** — procedural sprite/skeleton animation,
    pixel-art generation algorithms, procedural SFX synthesis nâng cao.
16. **Architecture & save compatibility** — cách mở rộng engine/ui/core
    mà không phá save cũ, FX callback pattern, data-driven definitions.

### Schema trả về (mỗi agent)

```json
{
  "agent": "<id>",
  "dimension": "graphics|content|gameplay|polish|technical",
  "ideas": [
    {"name": "...", "description": "...", "applicability": "...",
     "effort": "low|med|high", "risk": "low|med|high"}
  ],
  "mechanics": [
    {"name": "...", "how_it_works": "...", "adaptation": "..."}
  ],
  "techniques": [{"name": "...", "how": "..."}],
  "risks": ["..."],
  "top_3_recommendations": ["..."]
}
```

## 5. Phase B — Critique (5 adversarial agents, `parallel()`)

5 agent phản biện chạy song song, **mỗi agent nhận toàn bộ research** từ
Phase A và đánh giá từ một **lens riêng** để tránh trùng lặp:

1. **Lens: Fun & engagement** — ý tưởng nào thực sự vui hay chỉ phức tạp
   thêm? Combo/skill/mini-game nào giữ người chơi ở lại? Loại feature
   creep không phục vụ core loop.
2. **Lens: Idle integrity** — giữ tinh thần idle (auto-progress, away
   income, prestige)? Ý tưởng nào phá vỡ idle feel (quá active, quá
   grindy)? Tap vẫn có nghĩa khi auto mạnh.
3. **Lens: Scope & feasibility** — ý tưởng nào quá tham vọng cho pygame
   procedural? MVP vs nice-to-have? Effort/risk, loại ý tưởng không đáng.
4. **Lens: Coherence & economy** — các ý tưởng có mâu thuẫn nhau không
   (combo cap vs milestone)? Economy curves cân bằng? Prestige layers lồng
   nhau hợp lý?
5. **Lens: Onboarding & accessibility** — người mới hiểu được không?
   Reduced motion / sound settings đủ? Tutorial/onboarding? Cognitive load
   với nhiều hệ thống mới?

### Output mỗi critique agent

```json
{
  "lens": "<id>",
  "survivors": [
    {"idea_ref": "<agent>:<idea-name>", "why_kept": "...", "adjusted": "..."}
  ],
  "killed": [{"idea_ref": "...", "reason": "..."}],
  "conflicts": [{"a": "...", "b": "...", "resolution": "..."}],
  "must_haves": ["..."],
  "nice_to_haves": ["..."],
  "verdict_summary": "..."
}
```

**Nguyên tắc:** Critique agents **chỉ lọc và phản biện**, không sinh ý tưởng
mới — tránh bias "tự đề xuất". Mỗi ý tưởng bị kill phải có lý do cụ thể.

## 6. Phase C — Synthesis (2 agents, `pipeline()`)

### Agent C1 — Feature synthesis

Nhận toàn bộ survivors từ 5 critique agents, gộp thành **feature list nhất
quán**, phân loại theo 4 chiều, giải quyết mọi conflict đã ghi nhận. Mỗi
feature = một đơn vị implement độc lập có interface rõ.

```json
{
  "features": [{
    "id": "<kebab-id>",
    "dimension": "graphics|content|gameplay|polish",
    "name": "...",
    "description": "...",
    "files": ["..."],
    "acceptance_criteria": ["..."],
    "depends_on": ["<feature-id>"],
    "effort": "low|med|high",
    "priority": "P1|P2|P3"
  }],
  "feature_count": 28,
  "dimension_counts": {"graphics": 7, "content": 8, "gameplay": 9, "polish": 4},
  "conflicts_resolved": ["..."],
  "open_questions": ["..."]
}
```
> Số `feature_count` và `dimension_counts` chỉ là ví dụ minh họa schema —
> giá trị thực do Phase C quyết định.
```

### Agent C2 — Integration & sequencing review

Nhận feature list từ C1, kiểm tra:

- **Dependencies** đúng chưa (feature A cần feature B trước).
- **Sequencing** hợp lý cho implementation (foundation trước, dependent
  sau).
- **Scope** — mỗi feature đủ nhỏ cho 1 specialist agent trong 1 worktree
  không? Quá lớn → chia nhỏ.
- **Completeness** — gap nào giữa các feature (output của A cần cho B nhưng
  chưa ai định nghĩa)?

```json
{
  "sequenced_features": [{"...": "with implementation_order"}],
  "split_suggestions": [{"feature_id": "...", "into": ["...", "..."]}],
  "gaps": ["..."],
  "final_feature_count": 26
}
```
> `final_feature_count` chỉ là ví dụ — giá trị thực do Phase C quyết định.

**Mục tiêu Phase C:** ~25-30 feature sequenced, mỗi feature độc lập, có
files/acceptance/dependencies rõ — sẵn sàng cho Phase E.

## 7. Phase D — Spec Finalization (main loop)

1. **Viết design doc** — nội dung thực sự (features, architecture, data
   flow, testing) được điền từ output Phase C vào file này (thay phần
   placeholder này bằng spec content đầy đủ).
2. **Self-review inline** — quét placeholder ("TBD"/"TODO"), mâu thuẫn nội
   bộ, ambiguity, scope. Fix ngay trong file.
3. **Commit** design doc vào git.
4. **User review gate** — dừng lại, nhờ user review spec file. User yêu cầu
   thay đổi → sửa + re-review. User approve → sang Phase E.

## 8. Phase E — Implementation (writing-plans + ~25-30 specialist agents)

1. **Invoke `writing-plans` skill** — chuyển feature list sequenced thành
   implementation plan chi tiết: mỗi feature = 1 task có steps cụ thể +
   verify commands + modelTier (mechanical/standard/frontier) theo
   model-routing.
2. **Dispatch mỗi feature → 1 specialist agent** qua
   `subagent-driven-development` / `dispatching-parallel-agents`:
   - Mỗi agent chạy trong **worktree riêng** (`isolation: "worktree"`) để
     không xung đột file khi implement song song.
   - Agent nhận: feature spec, files cần sửa, acceptance criteria, verify
     command.
   - Agent implement → chạy verify (test/lint/run smoke) → báo cáo kết quả.
3. **Dependency-aware dispatch** — feature có `depends_on` chỉ dispatch
   sau khi prerequisite hoàn thành. Foundation features (sprite cache,
   data-driven defs) trước, dependent features (animated sprites, boss
   patterns) sau.
4. **Verification** — mỗi agent tự verify trong worktree; main loop review
   kết quả, chạy integration test toàn repo sau khi merge.
5. **Code review** cuối — `requesting-code-review` skill cho whole-plan
   review ở session level.

## 9. Summary

| Phase | Ai làm | Output | Scale |
|-------|--------|--------|-------|
| A Research | 16 agents (Workflow) | structured findings | large |
| B Critique | 5 agents (Workflow) | survivors/killed/conflicts | large |
| C Synthesis | 2 agents (Workflow) | sequenced feature list ~25-30 | medium |
| D Spec | main loop | design doc + self-review + user approval | — |
| E Implement | ~25-30 specialist agents (worktrees) | implemented + verified features | large |

**Tổng agent ước tính:** ~48-53 agent across all phases. Phase A–C trong 1
Workflow (~23 agent). Phase E tách ra ngoài Workflow qua specialist
dispatch.

## 10. Phase A–C Output — Feature List (38 features)

Phase A (16 research agents) → B (5 critique agents) → C (2 synthesis
agents) đã hoàn thành. Output: **38 feature** sequenced, chia theo 4 chiều
và 4 implementation tier (foundation → core → content → polish).

**Dimension counts:** graphics 7 · content 11 · gameplay 13 · polish 7
**Effort:** low 10 · med 22 · high 6
**Priority:** P1 9 · P2 23 · P3 6

### Conflicts resolved (16)

- **Meta-prestige:** kept ONE Reincarnation/Soul Tree; killed
  Transcendence/Ultra Ascension/Transmigration as duplicates.
- **Gear:** kept ONE Gear Loot System; Amber-Shop legendaries are a sink
  inside it; killed the TT2 relic-sets version.
- **Boss:** ONE boss system (cnt-boss-phases) — soft-phase + attack
  patterns, no enrage timer, no weak-point-tap.
- **Hero roster:** killed ALL hero rosters — they fragment the
  single-ninja identity; Dojos (gp-build-spec) give replayable paths.
- **Elemental:** kept Godai Fusion (live combat, default 1x, optional);
  killed passive zone-hazards + the 0.5x disadvantage chart.
- **Dungeon:** kept Shadow Dungeon as the SINGLE challenge mode; killed
  Survival Dungeon + Keys/Challenge Levels (5th currency — sprawl).
- **Active-play:** kept Rhythm + tap fatigue; killed Speed Step
  kill-ramp-with-decay (punishes idle) + 100x active burst.
- **Build specialization:** ADDITIVE (buffs toward chosen), not
  mutually-exclusive capstones; Dojos ARE the 4 damage sources; 5th Godai
  element (Earth) is utility flavor.
- **Music + SFX:** ONE generative music system + ONE layered SFX system;
  the 8 single-tone SFX are the #1 audio tell of a prototype.
- **Apocalypse event + Shadow Dungeon:** BOTH kept as distinct cadences.
- **Combo milestone consumers:** kept Combo Finishers; killed Combo
  Milestone Evolutions — one combo-milestone consumer only.
- **Infinite zones:** kept per-cycle multiplier (reuses 9 zones); killed
  the procedural generator duplicate.
- **Elixir compounding:** kept Tome of Samsara (gain-side); killed
  unspent-elixir-as-multiplier (holding-side) to avoid double compounding.
- **Pet passive-at-capstone:** reduced to 50% at bond 10 (not 100%) so
  equipping still matters.
- **Currency sprawl:** consolidated ~12 proposed currencies to 6-7 with
  distinct persistence scopes; killed Keys/Challenge Stars/Sacred
  Relics/Karma.

### Open questions (8 — to resolve during implementation)

1. Building unlock rebalance: persist-through-ascension vs compress
   unlock_zone to 0-8 — needs playtest of the first 3 ascensions.
2. Tap-vs-auto target ratio (3:1 vs 5:1) + tap-fatigue curve need
   playtesting against the new auto_mult upgrade.
3. Whether Shadow Dungeon's DungeonRunner composes existing engine
   components cleanly or needs a second World type.
4. Run-upgrade milestone multiplier thresholds (2x/4x/8x at 25/50/100)
   need balance verification against the segmented cost curve.
5. Whether to ship weather (gfx-weather) for all 9 zones or stage 3
   hero zones first.
6. Soul Tree perk set (gp-reincarnation) + Soul economy tuning — verify
   the hard reset isn't punishing.
7. Whether Godai fusion attunement defaults to 'none' (1x) and the
   auto-attune toggle is sufficient for idle players.
8. Stacking-token acquisition rate cap (gp-permanent-scaling) — tokens
   must complement, not replace, the exponential zone scaling.

### Gaps flagged by sequencing (7 — coordination notes for implementers)

1. **cnt-infinite-zones vs cnt-building-unlock:** cnt-infinite-zones
   (order 11) changes tier_mult to 1.6^tier, but cnt-building-unlock
   (order 8) re-tunes elixir_gain first. Resolution: re-verify the
   elixir_gain re-tune after cnt-infinite-zones ships, OR split the
   tier_mult change into a foundation feature that lands before order 8.
2. **cnt-shadow-dungeon references nonexistent files** (combo_tech.py,
   elements.py). The dungeon must compose the actual existing modules
   (combo logic in engine/runner.py + combo_fx.py; Godai logic in
   runner.py + enemy.py after gp-godai-fusion).
3. **gp-permanent-scaling + cnt-quest-codex both edit core/quests.py.**
   Heritage conversion (order 16) lands before quest-codex (order 26);
   the quest-codex implementer must be aware of the Heritage changes.
4. **cnt-boss-phases (12) vs gp-tap-auto-rebalance (23):** boss shield
   phase is "breakable by sustained auto-attack DPS" — re-test boss
   shield tuning after the rebalance lands.
5. **pl-juice-polish "boss enrage phase"** must be a VISUAL urgency cue
   (red vignette when ninja is low HP during a boss fight), NOT a boss
   enrage timer mechanic — to avoid contradicting cnt-boss-phases.
6. **Feature count metadata mismatch:** synthesis metadata says 28 but
   the features array has 33; after 5 splits the final count is 38. Use
   38 in the plan.
7. **gp-godai-fusion + cnt-infinite-zones + gfx-weather all edit
   data/enemies.py ZONES** (additive: new dict keys / EnemyDef field /
   weather key). No cross-dependencies listed; a single agent should
   verify all three zone-dict modifications compose cleanly.

### Feature list (ordered by implementation_order)

Each feature: `id` · dimension · effort · priority · depends_on · name.
Full details (files, acceptance criteria) follow in §11.

**Tier: foundation (order 1-5)** — P1, low effort, no deps. Land first.

1. `gp-combo-cap-bug` · gameplay · low · P1 · [] · Combo multiplier cap bug fix (asymptotic curve)
2. `pl-save-migration` · polish · low · P1 · [] · Explicit save-version migration chain
3. `gp-eventbus-bonusprovider` · gameplay · low · P1 · [] · BonusProvider registry + EventBus + Content registry
4. `pl-format-number` · polish · low · P1 · [] · format_number overflow fix + tiered precision
5. `gfx-convert-alpha` · graphics · low · P1 · [] · convert_alpha on every cached sprite surface

**Tier: core (order 6-13)** — P1/P2, low-med effort, deps on foundation.

6. `gfx-particles-pool` · graphics · low · P1 · [gfx-convert-alpha] · Adopt ParticleSystem2 as the sole particle system
7. `cnt-elite-miniboss` · content · low · P1 · [gp-combo-cap-bug] · Elite enemies + mini-bosses (wire up the dead is_elite field)
8. `cnt-building-unlock` · content · low · P1 · [gp-combo-cap-bug, pl-save-migration] · Building unlock zone rebalance (fix 8 inaccessible buildings)
9. `gp-combo-finishers` · gameplay · med · P2 · [gp-combo-cap-bug] · Combo Finishers + decay grace period + combo-break feedback
10. `gfx-render-tier` · graphics · med · P2 · [gfx-convert-alpha, gfx-particles-pool] · Render-quality tier (high/med/low) + reduced-motion gating
11. `cnt-infinite-zones` · content · low · P1 · [cnt-building-unlock, pl-format-number] · Infinite zone cycling with per-cycle multipliers + compounding tier multiplier
12. `cnt-boss-phases` · content · med · P2 · [cnt-elite-miniboss, gp-eventbus-bonusprovider] · Boss soft-phase intensity scaling + attack pattern library
13. `cnt-pet-depth` · content · med · P2 · [gp-eventbus-bonusprovider, pl-save-migration] · Pet depth: star levels + passive-at-capstone + nested pet prestige

**Tier: content (order 14-35)** — P2/P3, med-high effort, deps on core.

14. `gp-build-spec` · gameplay · med · P2 · [gp-eventbus-bonusprovider, cnt-infinite-zones, pl-save-migration] · Build specialization + Dojo path alignments (additive)
15. `gp-splash-skip` · gameplay · med · P2 · [cnt-infinite-zones, gp-combo-cap-bug] · Splash/Skip progression layer (Cleave + Yokai Portal)
16. `gp-permanent-scaling` · gameplay · med · P2 · [gp-eventbus-bonusprovider, pl-save-migration, cnt-infinite-zones] · Permanent scaling floor: stacking tokens + Heritage passives
17. `gp-epic-research` · gameplay · med · P2 · [gp-permanent-scaling] · Epic Research permanent meta-tree (split from gp-permanent-scaling)
18. `gp-gacha-fairness` · gameplay · med · P2 · [cnt-pet-depth, pl-save-migration] · Gacha fairness bundle + multi-stage pull-reveal drama
19. `cnt-gear-loot-model` · content · high · P3 · [gp-eventbus-bonusprovider, pl-save-migration, cnt-boss-phases] · Gear data model + affix definitions + boss-drop logic (split from cnt-gear-loot)
20. `gp-godai-fusion` · gameplay · med · P2 · [gp-build-spec, gp-eventbus-bonusprovider] · Godai Elemental Affinities & Fusion (live combat, optional, default 1x)
21. `cnt-run-upgrade-expansion` · content · med · P2 · [gp-build-spec, gp-combo-finishers] · Run upgrade expansion + new skill-tree branches
22. `cnt-shadow-dungeon-runner` · content · high · P3 · [cnt-boss-phases, gp-combo-finishers, gp-eventbus-bonusprovider] · DungeonRunner composing existing engine components (split from cnt-shadow-dungeon)
23. `gp-tap-auto-rebalance` · gameplay · med · P2 · [gp-combo-cap-bug, cnt-run-upgrade-expansion] · Tap-vs-auto DPS rebalance (~3:1) + tap fatigue anti-macro
24. `gp-skill-synergy-rhythm` · gameplay · low · P2 · [gp-combo-cap-bug] · Skill synergies + Tap rhythm bonus (active-play rewards, never a penalty)
25. `gp-reincarnation-core` · gameplay · high · P3 · [cnt-infinite-zones, gp-eventbus-bonusprovider, pl-save-migration] · Reincarnation meta-prestige core: reset for Souls + Soul Tree (split from gp-reincarnation)
26. `cnt-quest-codex` · content · med · P2 · [pl-save-migration] · Quest variety expansion + Lore/Bestiary Codex
27. `pl-juice-polish` · polish · med · P2 · [gp-combo-cap-bug, pl-save-migration, gp-eventbus-bonusprovider, cnt-infinite-zones] · Juice polish + prestige-teaching UI (split from pl-juice-automation)
28. `pl-automation` · polish · med · P2 · [gp-combo-cap-bug, pl-save-migration, gp-eventbus-bonusprovider, cnt-infinite-zones] · Automation nodes: auto-cast, auto-fireflies, auto-ascend, farm-when-stuck (split from pl-juice-automation)
29. `gfx-parallax` · graphics · med · P2 · [gfx-convert-alpha, gfx-render-tier] · Parallax 3-5 pre-baked scrollable background layers
30. `gfx-sprite-sheet-anim` · graphics · med · P2 · [gfx-convert-alpha, gfx-render-tier] · Pre-rolled sprite-sheet animation for ninja + enemies
31. `gfx-weather` · graphics · med · P2 · [gfx-particles-pool, gfx-render-tier] · Per-zone weather particles (rain/snow/ash/void drift)
32. `gfx-outline-shading-squash` · graphics · med · P2 · [gfx-convert-alpha, gfx-sprite-sheet-anim] · Alpha-dilation outline + hue-shifted shading ramp + squash-and-stretch
33. `cnt-gear-loot-forge` · content · high · P3 · [cnt-gear-loot-model] · Forge UI: enhance/reroll/salvage/set bonuses + amber sink (split from cnt-gear-loot)
34. `cnt-shadow-dungeon-variants` · content · high · P3 · [cnt-shadow-dungeon-runner] · Story + Endless + Daily variants, shared daily seed, UI entry (split from cnt-shadow-dungeon)
35. `gp-reincarnation-perks` · gameplay · high · P3 · [gp-reincarnation-core] · Named Soul Tree perks + Cosmic Forge anchor + UI (split from gp-reincarnation)

**Tier: polish (order 36-38)** — P2, med effort, deps on save-migration.

36. `pl-hints-nav-tooltips` · polish · med · P2 · [pl-save-migration] · Contextual hint system + first-session tutorial + grouped nav + full tooltips
37. `pl-music-sfx` · polish · med · P2 · [pl-save-migration] · Procedural ambient music + layered SFX (with music/SFX split)
38. `pl-accessibility` · polish · med · P2 · [pl-save-migration] · Accessibility: high-contrast mode + dyslexia font + text scale

## 11. Feature Details (files + acceptance criteria)

> Files are listed relative to repo root (e.g. `engine/runner.py`). For
> split sub-features, the parent's files are the superset; the split
> narrows the scope.

### Graphics (7)

#### gfx-convert-alpha (order 5, P1, low)
The 5 sprite caches in `assets.py` (ninja/enemy/firefly/building/pet)
create SRCALPHA surfaces but never call `.convert_alpha()`, so every blit
does a slow 32-bit ARGB software composite. Add `.convert_alpha()` at
cache-miss time (one call per miss, zero per-frame cost). The background
already calls `.convert()` at line 195.
- **Files:** `assets.py`
- **Acceptance:**
  - All 5 sprite surfaces call `.convert_alpha()` before caching
  - No behavior change — sprites render identically
  - Blit throughput improves ~1.5-2x in a microbenchmark
  - Caches remain lazy (no work before `display.set_mode`)

#### gfx-particles-pool (order 6, P1, low)
`engine/particles.py` `ParticleSystem2` is fully-pooled (zero per-frame
allocations) but `main.py:64` still uses the legacy `assets.ParticleSystem`
which allocates a fresh SRCALPHA Surface per particle per frame (~100-300
allocs/sec at combat peak). Replace the import + instantiation; route
death/firefly/combo bursts through ParticleSystem2. API-compatible.
- **Files:** `main.py`, `engine/particles.py`, `engine/death_fx.py`,
  `engine/firefly_fx.py`, `engine/combo_fx.py`
- **Acceptance:**
  - `main.py` instantiates `ParticleSystem2` instead of
    `assets.ParticleSystem`
  - death/firefly/combo bursts route through ParticleSystem2
  - No per-frame Surface allocations after warm-up (verified with a counter)
  - Particle count capped per quality tier
  - Visual parity with the legacy system at the default tier

#### gfx-render-tier (order 10, P2, med)
A 3-tier render quality (high/med/low) that extends the existing
`reduced_motion` gate coherently and keeps a 60fps floor on Intel iGPUs.
Low tier: cap particle counts at 25%, disable additive glow, skip
per-frame scratch fills, disable parallax. The tier MUST gate the same
code path as `reduced_motion` so the two never diverge.
- **Files:** `core/state.py`, `ui/screen_settings.py`, `main.py`
- **Acceptance:**
  - A `render_quality` field on GameState (high/med/low) with a settings
    toggle
  - Low tier caps particles at 25%, disables additive glow, disables
    parallax
  - The gate is the same code path as `reduced_motion` (reduced_motion
    forces low tier)
  - 60fps maintained on a weak-iGPU reference machine at low tier

#### gfx-parallax (order 29, P2, med)
The single static background blit is the most dated thing on screen. Split
the 2 hill layers into scrollable tiles + a near foliage layer. Cache per
(zone_index, hue, layer_id); blit 3-5 layers at parallax offsets
[0, 0.15, 0.35, 0.6, 1.0] from a single scroll accumulator. The existing
`lane_scroll` (1.0x) is preserved as the road layer. Parallax accelerates
2x during Auto Katana.
- **Files:** `assets.py`, `ui/screen_game.py`, `engine/runner.py`
- **Acceptance:**
  - 3-5 parallax layers blit at distinct scroll offsets from one
    accumulator
  - Parallax visibly accelerates 2x during Auto Katana
  - Layers pin to 0 scroll when `reduced_motion` is on
  - All layer surfaces cached per (zone, hue, layer) with `convert_alpha`
  - 60fps maintained with parallax enabled at the high tier

#### gfx-sprite-sheet-anim (order 30, P2, med)
The ninja is the most-seen sprite and the `slash_anim`/`bob` timers
already exist in engine state but are wasted (the screen only uses a 1px
vertical bob). Generate 4-8 frames at cache time, stack into one wide/tall
SRCALPHA sheet, blit by sub-rect (subsurface is a zero-copy view). Frame
selection from `slash_anim` (windup/extend/recover) and `bob` (idle).
- **Files:** `assets.py`, `engine/ninja.py`, `engine/enemy.py`,
  `ui/screen_game.py`
- **Acceptance:**
  - Ninja has idle bob + slash lunge + hit flinch frames selected by
    `slash_anim`/`bob` timers
  - At least one enemy shape has a multi-frame idle cycle
  - Static frame 0 is the graceful-degradation fallback
  - Per-frame blit cost is no greater than the current static sprite
  - `reduced_motion` pins to frame 0

#### gfx-outline-shading-squash (order 32, P2, med)
Three cheap, high-impact graphics upgrades at cache time (zero per-frame
cost), all gated by `reduced_motion`. Outline: a vectorized
`outline_array()` helper applied to every generated sprite (the single
most effective "looks like real pixel art" trick). Shading ramp: 4-6 step
ramp per sprite, shadows shift hue cool, highlights warm.
Squash-and-stretch: scale (1+k, 1-k) plays for ~80ms on slash/hit, driven
by existing timers.
- **Files:** `assets.py`, `ui/screen_game.py`
- **Acceptance:**
  - Every generated sprite has a 1px alpha-dilation outline at cache time
  - Sprites have a 4-6 step hue-shifted shading ramp (cool shadows, warm
    highlights)
  - Squash-and-stretch (1+k, 1-k) plays for ~80ms on slash/hit, driven by
    existing timers
  - `reduced_motion` disables squash-and-stretch (static frame)
  - Outline + shading add zero per-frame cost (cache-time only)

#### gfx-weather (order 31, P2, med)
Zones currently differ only in hue. Weather particles (rain in Bamboo, ash
in Volcano, snow in Sky, void drift in Void) make zones feel like places.
A `WeatherFXSystem` spawns zone-appropriate particles from the top edge
using ParticleSystem2 presets. Add a `weather` key to each zone dict in
`data/enemies.py`. Cap counts per weather type (rain ≤120, snow ≤60).
- **Files:** `data/enemies.py`, `engine/runner.py`, `ui/screen_game.py`
- **Acceptance:**
  - At least 3 zones have distinct weather particle presets
  - Weather uses ParticleSystem2 (pooled, no per-frame allocations)
  - Particle counts capped per type and reduced under `reduced_motion`
  - `reduced_motion` falls back to a static tint overlay
  - 60fps maintained with weather enabled

### Content (11)

#### cnt-elite-miniboss (order 7, P1, low)
The Enemy dataclass already has an `is_elite` field that is drawn but
never spawned — this wires up existing dead code. In `world._spawn_regular`
add a 5% elite roll (3x HP, 5x gold, guaranteed `rare_drop`). Add
`_spawn_miniboss` at 50% `ZONE_DISTANCE` that blocks progress until killed
(0.4x the zone boss stats). No new state fields; elites are transient.
- **Files:** `engine/world.py`, `engine/enemy.py`, `engine/runner.py`,
  `engine/boss_fx.py`
- **Acceptance:**
  - 5% of regular spawns are elite (3x HP, 5x gold, guaranteed `rare_drop`)
  - A mini-boss spawns at 50% zone distance and blocks progress until killed
  - `is_elite` is set on spawned elites and rendered distinctly
  - No new GameState fields (elites are transient)
  - Chests drop on elite and boss kills

#### cnt-building-unlock (order 8, P1, low)
Verified: 8 of 18 buildings (forge through infinity) have `unlock_zone`
9-16, but ascension resets zone to 0 and the natural max reachable zone is
~9-12, so half the building roster is dead content. Prefer the
persist-through-ascension option: buildings carry over and scale by the
ascension tier `stat_mult`; only gold/upgrades reset. MUST re-tune the
elixir_gain so the post-ascension economy doesn't snowball. **Note gap #1
in §10:** re-verify after cnt-infinite-zones changes the tier_mult formula.
- **Files:** `data/buildings.py`, `core/ascend.py`,
  `core/game_economy.py`, `core/state.py`
- **Acceptance:**
  - All 18 buildings are reachable within a normal playthrough
  - Buildings persist through ascension (scaled by tier `stat_mult`) OR
    `unlock_zone` compressed to 0-8
  - `elixir_gain` re-tuned so the post-ascension economy doesn't snowball
  - The first 3 ascensions feel balanced (playtest)

#### cnt-infinite-zones (order 11, P1, low)
The single biggest structural problem: the game ends at zone 9 (Cosmic
Void boss HP ~1624, one-shot by maxed run upgrades).
`cycle=floor(zone_index/9)`, `zone_in_cycle=zone_index%9`.
`CYCLE_HP_MULT=8.0`, `CYCLE_DMG_MULT=7.0`, `CYCLE_GOLD_MULT=9.0`. Reuse
the 9 themed ZONES + BOSSES; only the scaler changes in `world.py` (no new
state field — cycle is derived). Surface a visible "Cycle N" header.
`tier_mult = 1.6^tier` replaces the `ASCEND_TIERS` `stat_mult` column; the
7 names remain as labels.
- **Files:** `engine/world.py`, `data/enemies.py`, `config.py`,
  `engine/ninja.py`, `data/quests.py`
- **Acceptance:**
  - `zone_hp`/`zone_dmg`/`zone_gold` in `world.py` multiply by per-cycle
    multipliers (cycle=floor(zone_index/9))
  - Past zone 9 the road continues with the same 9 themed zones at scaled
    stats
  - A visible "Cycle N" header renders in the game HUD
  - `tier_mult = 1.6^tier` replaces the `ASCEND_TIERS` `stat_mult` column;
    the 7 names remain as labels
  - Cycle-based achievements (reach cycle 1/3/5/10) exist and fire
  - The endgame no longer stalls at zone 9

#### cnt-boss-phases (order 12, P2, med)
Consolidates the boss proposals into ONE boss system. Bosses are currently
stat-buffed enemies with no behavior. Soft-phase: HP milestones at
75/50/25% add attack layers (projectile, hazard, summon, shield) by scaling
timers — no new state machine, just scaling. Scale attack interval down as
HP drops. Bosses are CC-immune. **Note gap #4 in §10:** re-test boss shield
tuning after gp-tap-auto-rebalance lands.
- **Files:** `engine/enemy.py`, `engine/world.py`, `engine/runner.py`,
  `engine/boss_fx.py`, `data/enemies.py`
- **Acceptance:**
  - Bosses gain HP-threshold attack layers at 75/50/25% (no new state
    machine, scaling only)
  - Attack frequency scales up as HP drops
  - Phase transitions are communicated (nameplate flash, banner, hue shift)
    without pausing
  - No enrage timer and no weak-point-tap — auto-attack DPS can clear the
    boss
  - The shield phase is breakable by sustained auto-attack DPS

#### cnt-pet-depth (order 13, P2, med)
Makes the existing 12-pet collection meaningful instead of "equip the 3
best". (1) Passive-at-capstone: for owned-but-unequipped pets at bond>=5
add 1/4 of `pet_bonus`, at bond>=10 add 50% (NOT 100%). (2) Star levels
(1-12) from duplicate eggs as a second progression axis. (3) Nested pet
prestige (Spirit Embers) only at max bond (bond 10).
- **Files:** `core/bonuses.py`, `data/pets.py`, `core/gacha.py`,
  `core/state.py`
- **Acceptance:**
  - Owned-but-unequipped pets contribute 25% at bond>=5, 50% at bond>=10
  - Equipped pet bonus is meaningfully larger than the passive one
  - Star levels (1-12) from duplicate eggs extend the bond system
  - Nested pet prestige (Spirit Embers) only at max bond (bond 10)
  - Spirit Ember payouts are clearly worth the re-grind
  - `aggregate_bonuses` swings aren't wild on pet swaps

#### cnt-gear-loot-model (order 19, P3, high) — split from cnt-gear-loot
The gear data model + affix definitions + BonusProvider registration +
boss-drop logic. 4 gear slots with passive affixes flowing through
`aggregate_bonuses` via BonusProvider, drops on boss kill (automatic).
Gear rarity reuses `GACHA_RATES`. Gear multipliers fit the defined stacking
order with a `MAX_TOTAL_DAMAGE_MULT` sanity cap.
- **Files:** `config.py`, `core/bonuses.py`, `core/state.py`,
  `engine/runner.py`
- **Acceptance:**
  - 4 gear slots with passive affixes flowing through `aggregate_bonuses`
    via BonusProvider
  - Boss kills drop gear (automatic, no active requirement)
  - Gear rarity reuses `GACHA_RATES`
  - Gear multipliers fit the defined stacking order with a
    `MAX_TOTAL_DAMAGE_MULT` cap

#### cnt-gear-loot-forge (order 33, P3, high) — split from cnt-gear-loot
The Forge UI: enhance/reroll/salvage/set bonuses + amber sink. A Forge sink
(enhance/reroll/salvage) using gold + amber. No affix requires active play —
the Forge is a one-time management action like buying buildings.
Amber-Shop legendaries are a complementary amber sink inside this system.
- **Files:** `ui/screen_hero.py`, `core/bonuses.py` (salvage logic)
- **Acceptance:**
  - A Forge sink (enhance/reroll/salvage) using gold + amber
  - No affix requires active play
  - Amber-Shop legendaries are a complementary amber sink inside this
    system, not a separate layer

#### cnt-shadow-dungeon-runner (order 22, P3, high) — split from cnt-shadow-dungeon
A `DungeonRunner` that composes existing engine components (World,
enemy.py, skills.py), not duplicate Runner logic. The road loop runs
undisturbed while the dungeon is active. No new currency (gated on medals
or zone progression). The Godai Fire element ties to the dungeon. **Note
gap #2 in §10:** reference real modules (combo logic in runner.py +
combo_fx.py; Godai logic in runner.py + enemy.py after gp-godai-fusion),
not nonexistent combo_tech.py/elements.py.
- **Files:** `engine/runner.py`, `engine/world.py`, `core/state.py`
- **Acceptance:**
  - A `DungeonRunner` that composes existing engine components, not
    duplicate Runner logic
  - The road loop runs undisturbed while the dungeon is active
  - No new currency (gated on medals or zone progression)
  - The Godai Fire element ties to the dungeon

#### cnt-shadow-dungeon-variants (order 34, P3, high) — split from cnt-shadow-dungeon
Story + Endless + Daily variants with a shared daily seed. The daily-dungeon
seed gives the shared daily challenge. UI entry from the game screen.
- **Files:** `ui/screen_game.py`, `data/enemies.py`, `core/state.py`
- **Acceptance:**
  - Story + Endless + Daily variants with a shared daily seed
  - UI entry from the game screen

#### cnt-quest-codex (order 26, P2, med)
Two low-cost content additions. (1) Quest variety: add weekly + chapter
quests to the existing daily pool (weekly gives a return reason; chapter
ties to zone progression). Do NOT ship 6+ new quest types at once — only
weekly + chapter. (2) Lore/Bestiary Codex: extends the existing
`ui/screen_bestiary.py` with a category tab system + unlock-state map +
per-entity lore entries (pure data, no new mechanic). **Note gap #3 in
§10:** be aware of the Heritage changes from gp-permanent-scaling (order
16) which also edits core/quests.py.
- **Files:** `data/quests.py`, `core/quests.py`, `ui/screen_bestiary.py`,
  `ui/screen_quests.py`
- **Acceptance:**
  - Weekly + chapter quest types added to the daily pool (not 6+ types)
  - Bestiary screen has category tabs + per-entity lore entries
  - Lore text is pure data (no new mechanic)
  - Quests remain legible (no quest-type sprawl)

#### cnt-run-upgrade-expansion (order 21, P2, med)
Cheap content that deepens the per-run build. (1) Run upgrade expansion:
13 → ~20 with tap-specialist + active-skill-adjacent + combo-decay-resistance
upgrades (more rows in the existing flat `TAP_UPGRADE_DEFS` table, reset on
ascension so no save-migration risk). (2) New skill-tree branches
(Defense/Combo/Tap Mastery) + cross-branch capstones expanding the 40-node
tree toward ~60 nodes. Active-skill tier upgrades (t2/t3) chain off existing
`ab_*` nodes.
- **Files:** `config.py`, `data/skill_tree.py`, `core/game_economy.py`
- **Acceptance:**
  - Run upgrades expand from 13 to ~20 (tap-specialist, skill-adjacent,
    combo-decay-resistance)
  - New skill-tree branches (Defense/Combo/Tap Mastery) with cross-branch
    capstones
  - Active-skill tier upgrades (t2/t3) chain off existing `ab_*` nodes
  - No new verb — deepens existing skills
  - Reset on ascension (no save-migration risk for run upgrades)

### Gameplay (13)

#### gp-combo-cap-bug (order 1, P1, low)
CRITICAL: `COMBO_MULT_CAP=3.0` is defined at `engine/runner.py:34` but
never applied in `combo_mult()` (lines 96-99). At combo 200 with maxed
`combo_step` the multiplier hits 270x instead of 3.0x — a 90x balance break.
Replace the linear `1+c*step` with the asymptotic `1 + 3.0*(1 - exp(-c/50))`
so the cap is structurally enforced and the curve is smooth.
- **Files:** `engine/runner.py`, `config.py`
- **Acceptance:**
  - `combo_mult()` returns `1 + 3.0*(1 - exp(-c/50))` (asymptotic,
    structurally capped at 3.0x)
  - At combo 200 with maxed `combo_step` the multiplier is ~3.0x (not 270x)
  - The curve is smooth (no hard cliff at 200)
  - `combo_step` upgrade reduces `COMBO_TAU` (ramp speed), not the step
  - All existing combo-dependent code still works

#### gp-eventbus-bonusprovider (order 3, P1, low)
The structural prerequisites for cleanly adding equipment, dungeons,
elements, and mini-games without editing the 389-line Runner god-object.
(1) BonusProvider registry: refactor `aggregate_bonuses` into a
BonusProvider protocol; each source registers a `callable(state) ->
dict[str, float]`; `aggregate_bonuses` merges all providers. (2) A
Runner-owned EventBus replaces module-global FX callbacks; engine modules
emit events. (3) A Content registry enables ID-based zone/enemy lookup.
- **Files:** `core/bonuses.py`, `engine/runner.py`, `engine/enemy.py`,
  `engine/world.py`, `data/enemies.py`, `config.py`
- **Acceptance:**
  - `aggregate_bonuses` uses a BonusProvider registry; the flat-dict
    contract is unchanged so every consumer works unmodified
  - Existing code split into `_skill_tree_provider` + `_pets_provider`,
    both registered
  - A Runner-owned EventBus replaces module-global FX callbacks; engine
    modules emit events
  - Module globals kept as deprecated aliases for one release
  - A Content registry enables ID-based zone/enemy lookup (no silent
    clamp in `zone_by_index`)
  - A `MAX_TOTAL_DAMAGE_MULT` sanity cap defined in `config.py` with a
    documented stacking order
  - The runner's idle update loop stays intact

#### gp-combo-finishers (order 9, P2, med)
Three combo-system improvements. (1) Combo Finishers: bank a charge when
combo crosses an existing MILESTONE (25/50/100/200 — piggyback on
`combo_fx.MILESTONES`, do NOT invent new thresholds); charges persist
through the decay window; spend on 4 finishers (Thousand Cuts line AOE,
Phantom Step boss-kill if combo>=100, Mirage shadow clones, Executioner's
Edge guaranteed-crit taps). Finisher damage is a fixed multiple of
`tap_damage` with its own cap. (2) `combo_timer` goes negative to -1.5s
before resetting (grace); a kill during grace restores combo. (3) "COMBO
LOST" feedback on combo break.
- **Files:** `engine/runner.py`, `engine/combo_fx.py`, `core/state.py`,
  `ui/screen_game.py`
- **Acceptance:**
  - A charge is banked at each existing MILESTONE (25/50/100/200);
    charges persist through the decay window
  - 4 finishers spend charges; finisher damage is a fixed multiple of
    `tap_damage` with its own cap (not multiplicative with `combo_mult`)
  - Bosses are auto-killable without Phantom Step (finishers never gate
    progression)
  - `combo_timer` goes negative to -1.5s before resetting combo to 0
    (grace); a kill during grace restores combo
  - "COMBO LOST" feedback plays on combo break (gated by `reduced_motion`)
  - Combo Milestone Evolutions are NOT implemented — finishers are the
    single milestone consumer

#### gp-build-spec (order 14, P2, med)
Unifies the build-specialisation + Dojo + Heritage proposals into ONE
coherent axis. At the abilities branch fork, the player commits to one
damage path per ascension (Kage-bunshin idle / Iaijutsu tap-burst /
Shikigami summon / Kusari-gama multi-hit). The 4 Dojos ARE the 4 damage
sources; the 5th Godai element (Earth) is utility/defense flavor.
Specialization is ADDITIVE (buffs toward chosen), NOT mutually-exclusive
capstones. Completing a full ascension under a Dojo grants its Heritage
passive.
- **Files:** `data/skill_tree.py`, `core/bonuses.py`, `engine/ninja.py`,
  `core/ascend.py`, `core/state.py`
- **Acceptance:**
  - 4 damage paths (Dojos) commit per ascension, mapped to the 4 most
    fitting Godai elements
  - Specialization is ADDITIVE (buffs toward chosen), NOT
    mutually-exclusive capstones that lock out hybrids
  - A viable generalist default exists; respec is free/cheap
  - Completing a full ascension under a Dojo grants its Heritage passive
  - The "collect all 5 heritages" meta-goal exists
  - The Godai attunement (fusion) is a separate cyclable layer, not the
    build commitment
  - The build-specialisation multipliers and Godai element multipliers
    compose cleanly in `compute_ninja_stats` with a defined stacking order

#### gp-splash-skip (order 15, P2, med)
Pairs with infinite cycling: gives the late-ascension road the "zooming
through zones" dopamine. Add a "Cleave" stat (from the skill tree) that
overkill-clears the next K enemies when damage massively overkills; a rare
"Yokai Portal" boss variant that jumps the zone bar by a chunk. MUST gate
the Cleave stat behind mid-ascension so early zones still feel earned.
- **Files:** `engine/world.py`, `engine/enemy.py`, `data/skill_tree.py`,
  `engine/runner.py`
- **Acceptance:**
  - A Cleave stat overkill-clears the next K enemies when damage massively
    overkills
  - A rare Yokai Portal boss variant jumps the zone bar by a chunk
  - Cleave is gated behind mid-ascension (early zones still feel earned)
  - Yokai Portal skips don't bypass bestiary/achievement reveals
  - A new player never sees splash in the first runs

#### gp-permanent-scaling (order 16, P2, med)
Three permanent-scaling systems that reuse existing infrastructure. (1)
Stacking tokens: permanent +1%-per-token (Strike/Crit/Coin/Elixir), never
spent, survive ALL prestige layers — sourced from daily quests + zone-boss
milestones (NOT achievements, to avoid double-counting with Heritage). (2)
Heritage passives: convert the 14 achievements from one-shot amber/medal
payouts into permanent cumulative multipliers; add hidden/secret
achievements with cryptic in-game hints. (3) Epic Research is split out
(see gp-epic-research).
- **Files:** `data/quests.py`, `core/quests.py`, `core/state.py`,
  `core/bonuses.py`
- **Acceptance:**
  - Stacking tokens (+1% each, permanent, survive all resets) sourced from
    daily quests + zone-boss milestones (not achievements)
  - Token acquisition rate capped so +1% complements rather than replaces
    exponential zone scaling
  - The 14 achievements converted to permanent cumulative multipliers
    (Heritage passives)
  - Hidden/secret achievements have cryptic in-game hints (not
    wiki-dependent)
  - Tokens + Heritage have distinct sources — no double-counting

#### gp-epic-research (order 17, P2, med) — split from gp-permanent-scaling
A permanent meta-tree bought with underused medals/amber (nodes like Elixir
Resonance, Away Mastery +% offline growth, Lab Discipline); reuses
`skill_tree.py` structure; gives premium currencies a high-value home and
makes every prestige strictly stronger. Away Mastery keeps offline growth
meaningfully but strictly less than active+boosted earnings.
- **Files:** `data/skill_tree.py`, `core/state.py`, `core/bonuses.py`,
  `core/offline.py`
- **Acceptance:**
  - An Epic Research permanent meta-tree bought with medals/amber (Elixir
    Resonance, Away Mastery, Lab Discipline)
  - Epic Research reuses `skill_tree.py` structure
  - Away Mastery keeps offline growth meaningfully but strictly less than
    active+boosted earnings

#### gp-gacha-fairness (order 18, P2, med)
Converts the gacha from a gamble into guaranteed progression. (1) Soft-pity
ramp: keep base rates, add a per-rarity `soft_pity_start` +
`increment_per_pull`. (2) Spark/pity-token shop: 1 token per pull, trade 40
for any unlocked pet; carry pity across banners. (3) Dupe-to-upgrade:
duplicates feed a per-pet upgrade track; maxed pets removed from the pool.
(4) Early-pity guarantee in the first 10 pulls of a new banner. (5)
Multi-stage reveal leaks the rarity color into the suspense glow from t=0.
- **Files:** `core/gacha.py`, `config.py`, `engine/gacha_fx.py`,
  `ui/screen_pets.py`, `core/state.py`
- **Acceptance:**
  - Soft-pity ramp (rate climbs per pull after a threshold) shortens the
    `PITY_LEGENDARY=200` grind
  - A spark/pity-token shop (1 token per pull, trade 40 for any unlocked
    pet); pity carries across banners
  - Dupe-to-upgrade: duplicates feed a per-pet upgrade track; maxed pets
    removed from the pool
  - Early-pity guarantee in the first 10 pulls of a new banner
    (one-time-per-banner)
  - Multi-stage reveal leaks the rarity color into the suspense glow from
    t=0 (early tell)
  - Rarity-scaled screen shake/hit-stop; a skip activates after the tell;
    batch-summary-first for 10-pulls
  - Visible odds UI
  - Banner rotation is NOT implemented without a hero-expansion roadmap

#### gp-godai-fusion (order 20, P2, med)
Transforms the 4 Godai nodes from flat +15% stat boosts into a LIVE combat
decision layer. Add an `element` field to `EnemyDef` (themed by zone),
`attuned_element` to GameState (default 'none' = 1x damage to everything),
a 4-cycle type chart (2x advantage / 0.5x disadvantage), and 4 fusion
effects (Void+Fire Inferno, Wind+Water Tempest, etc.) on a 30s cooldown.
Attunement defaults to 'none' (1x) so the system is optional. **Note gap
#7 in §10:** this edits `data/enemies.py` ZONES alongside
cnt-infinite-zones + gfx-weather — verify all three compose cleanly.
- **Files:** `data/enemies.py`, `data/skill_tree.py`, `core/state.py`,
  `engine/enemy.py`, `engine/runner.py`, `ui/screen_godai.py`
- **Acceptance:**
  - `EnemyDef` has an `element` field themed by zone
  - `attuned_element` on GameState defaults to 'none' (1x damage to
    everything)
  - A 4-cycle type chart (2x advantage / 0.5x disadvantage) with 4 fusion
    effects on a 30s cooldown
  - An auto-attune toggle (skill-tree node) lets idle players opt out —
    idle is never worse than 1x
  - The dual-element skill-tree nodes are the complement (unlock gate),
    not a competing system
  - The zone-environmental-hazards proposal is NOT implemented — the
    fusion is the single elemental system

#### gp-tap-auto-rebalance (order 23, P2, med)
THE idle-integrity fix. Tap DPS (1.13B at max) is 94x auto DPS (12M)
because tap benefits from `tap_mult` while auto gets only `atk_pct`. Add
an `auto_mult` run upgrade mirroring `tap_mult`; scale tap base DOWN ~5x
(tap fires 5/s vs auto 1.5/s); add tap fatigue (5%/tap above 5 taps/s,
floor 0.3x) to keep manual play rewarding but macro-proof. **Note open
question #2 in §10:** the exact ratio (3:1 vs 5:1) + fatigue curve need
playtesting.
- **Files:** `engine/ninja.py`, `config.py`, `engine/runner.py`,
  `core/game_economy.py`
- **Acceptance:**
  - An `auto_mult` run upgrade mirrors `tap_mult`
  - Tap base scaled down so the tap:auto ratio is ~3:1 (not 94:1)
  - Tap fatigue: 5%/tap above 5 taps/s, floor 0.3x (tapping never becomes
    useless)
  - The rebalance ships with the new `auto_mult` upgrade (a new option,
    not a pure nerf)
  - Auto-attack is the backbone; tap is a meaningful-but-bounded bonus
  - No 100x+ active burst (killed as economy-breaking)

#### gp-skill-synergy-rhythm (order 24, P2, low)
Two cheap active-play rewards. (1) Skill Synergies: firing two active
skills within 2s triggers a synergy bonus (a sequencing puzzle on the 4
active skills). SYNERGY table: (kunai,shuriken)='Storm of Steel',
(speed,kunai)='Lightning Strike', (rope,shuriken)='Grinding Vortex',
(speed,rope)='Phantom Snare'. (2) Tap rhythm: median of last 5 tap
intervals in 0.35-0.55s window builds `rhythm_streak` (cap 20), +2.5% tap
damage per level. Rhythm is strictly a bonus (floor 0, never a penalty).
- **Files:** `engine/runner.py`, `engine/skills.py`, `ui/screen_game.py`,
  `core/state.py`
- **Acceptance:**
  - Firing 2 active skills within 2s triggers a named synergy with a
    glowing arc between the buttons
  - Tap rhythm: median of last 5 tap intervals in 0.35-0.55s window builds
    `rhythm_streak` (cap 20), +2.5% tap damage per level
  - Rhythm is strictly a bonus (floor 0, never a penalty) —
    motor-impaired players aren't punished
  - A soft tick SFX gives `reduced_motion` a non-visual cue
  - The Speed Step kill-ramp-with-decay rework is NOT implemented (it
    punishes idle)

#### gp-reincarnation-core (order 25, P3, high) — split from gp-reincarnation
The SINGLE meta-prestige design. A meta-prestige layer above the 7
ascension tiers: reset elixir/skill-tree/ascension for Souls + a permanent
Soul Tree with NAMED, concrete perks. Gate behind Singularity + 10
ascensions so it appears only after the base loop is mastered. Soul Tree
nodes are truly permanent (survive all resets). Free respec so the hard
reset isn't punishing.
- **Files:** `core/ascend.py`, `core/state.py`, `config.py`
- **Acceptance:**
  - A meta-prestige layer gated behind Singularity + 10 ascensions
  - Reset elixir/skill-tree/ascension for Souls + a permanent Soul Tree
  - Soul Tree nodes survive ALL resets (truly permanent)
  - Free respec so the hard reset isn't punishing
  - Transcendence, Ultra Ascension, and Transmigration are NOT implemented
    (killed as duplicates)

#### gp-reincarnation-perks (order 35, P3, high) — split from gp-reincarnation
Named Soul Tree perks (start at zone 3, +1 equip slot, keep 25% of skill
tree, 5th active skill) + the persistent Cosmic Forge (max 10) anchors the
rebuild so the hard reset doesn't feel punishing. Each perk is a
run-breaking verb. UI in the ascend screen.
- **Files:** `data/skill_tree.py`, `ui/screen_ascend.py`
- **Acceptance:**
  - A persistent Cosmic Forge (max 10) anchors the rebuild
  - Each Soul Tree perk is a run-breaking verb (start at zone 3, +1 equip
    slot, keep 25% skill tree, 5th active skill)
  - The "collect all 5 heritages" meta-goal exists

### Polish (7)

#### pl-format-number (order 4, P1, low)
`utils.format_number` overflows at 1e36, returning '1000Dc' instead of
rolling to the next unit — a visible bug once players reach cycle 6+ where
boss HP exceeds 1e36. Add a scientific-notation fallback when the unit
table is exhausted: if `u >= len(units): return f'{n:.2e}'`. Tier the
precision (<1e6 to 2 decimals, >=1e9 to 2 sig figs). MUST ship before
cnt-infinite-zones.
- **Files:** `utils.py`
- **Acceptance:**
  - `format_number` returns a scientific-notation string (e.g. 1.20e36)
    when the unit table is exhausted
  - No '1000Dc' overflow at 1e36+
  - Tiered precision (<1e6 to 2 decimals, >=1e9 to 2 sig figs)
  - HUD currency pills still fit after the format change

#### pl-save-migration (order 2, P1, low)
`save_version=2` is decorative — `from_dict` uses `hasattr+setattr` with
no migration logic, so the "forward-compatible additive schema" claim is a
time bomb. Add a `MIGRATIONS` dict of pure functions (from_version ->
migration). `load()` walks the chain from the file's `save_version` up to
`CURRENT`. Bump `save_version` to 3 with the first migration (seeds
new-field defaults).
- **Files:** `core/state.py`, `core/save_manager.py`
- **Acceptance:**
  - A `MIGRATIONS` dict of pure functions, applied in `load()` by walking
    from the file's `save_version` up to `CURRENT`
  - `save_version` bumped to 3 with the first migration (seeds new-field
    defaults)
  - Each migration is unit-testable with a fixture dict
  - Never mutates the live save during migration (migrate the dict in
    memory, then save)
  - An existing v2 save loads without data loss after migration

#### pl-juice-polish (order 27, P2, med) — split from pl-juice-automation
A bundle of low-effort polish + idle-teaching. (1) Count-up currency
numbers + gold milestone celebrations. (2) Skill cooldown-ready chime +
button glow + cooldown progress fill. (3) Low-HP red vignette + boss
enrage phase **as a VISUAL urgency cue** (red vignette when the ninja is
low HP during a boss fight), NOT a boss enrage timer mechanic — see gap #5
in §10. (4) Respec-on-prestige for the elixir skill tree (free on
ascension). (5) Elixir-per-Minute live readout + recommended-ascend
highlight + pacing-threshold surfacing in the ascend screen (computed from
config.py curves). (6) Tome of Samsara compounding elixir-growth anchor
(promote one elixir-tree node with a "invest ~30% here" tooltip + "elixir
per ascension" projection).
- **Files:** `ui/screen_game.py`, `ui/screen_ascend.py`,
  `ui/currency_fx.py`, `core/ascend.py`
- **Acceptance:**
  - Currency numbers count up (no instant snapping); gold milestones
    celebrate
  - Skill cooldown-ready chime + button glow + cooldown progress fill
    (chime respects `sound_on`, glow respects `reduced_motion`)
  - Low-HP red vignette + boss enrage phase as a VISUAL urgency cue (gated
    by `reduced_motion`) — NOT a boss enrage timer mechanic
  - Free respec-on-prestige for the elixir skill tree
  - Elixir-per-Minute readout + recommended-ascend highlight + pacing
    thresholds computed from `config.py` curves
  - Tome of Samsara compounding anchor with "invest ~30%" tooltip +
    "elixir per ascension" projection
  - The unspent-elixir-as-multiplier is NOT implemented (Tome of Samsara
    is the single compounding elixir-growth loop)

#### pl-automation (order 28, P2, med) — split from pl-juice-automation
Automation nodes gated behind deep elixir investment (an earned endgame
convenience). (1) Auto-cast Rope Hook + Shuriken under Energy. (2)
Automation unlock nodes: auto-collect fireflies, auto-activate Energy,
auto-ascend at a threshold (respects the player's threshold). (3)
Auto-progress + farm-when-stuck fallback (softens the hard boss wall; the
road never dead-ends an idle player; farm state advances `lifetime_gold`).
- **Files:** `engine/runner.py`, `data/skill_tree.py`, `core/ascend.py`,
  `core/offline.py`
- **Acceptance:**
  - Auto-cast Rope Hook + Shuriken under Energy, gated behind high-cost
    skill-tree nodes
  - Automation unlock nodes (auto-fireflies, auto-ascend at a threshold)
    gated behind deep elixir investment; auto-ascend respects the player's
    threshold
  - Auto-progress + farm-when-stuck fallback (the road never dead-ends an
    idle player; farm state advances `lifetime_gold`)

#### pl-hints-nav-tooltips (order 36, P2, med)
The onboarding fix. (1) HintEngine in `core/hints.py`: each frame evaluates
a priority-ordered list of conditions and shows a pulsing arrow/glow on the
next best action (tap road → buy farm → upgrade → ascend). Gate on not
`welcome_pending` and not `zone_fx.active`. Store a seen-set in save.json
so hints never repeat. (2) The 12 nav buttons replaced with a categorized
menu or icon rail with icon+label. 1-9 keyboard shortcuts preserved as a
power-user fallback. (3) Tooltips registered for every upgrade, building,
skill-tree node, and pet with live values (callable-text form).
- **Files:** `ui/screen_game.py`, `ui/tooltip.py`, `ui/screen_upgrades.py`,
  `ui/screen_buildings.py`, `ui/screen_skilltree.py`, `ui/screen_pets.py`,
  `core/state.py`
- **Acceptance:**
  - A HintEngine evaluates conditions per frame and glows the next best
    action; seen-set in save.json prevents repeats
  - Hints are gated on not `welcome_pending` and not `zone_fx.active`
  - First-session conditions chain naturally (tap → buy farm → upgrade →
    ascend) and never fire all at once
  - The 12 nav buttons replaced with a categorized menu or icon rail with
    icon+label
  - 1-9 keyboard shortcuts preserved as a power-user fallback
  - Tooltips registered for every upgrade, building, skill-tree node, and
    pet with live values (callable-text form)
  - Menu stagger gated by `reduced_motion`

#### pl-music-sfx (order 37, P2, med)
The game is SILENT except for 8 basic NumPy SFX (every tap is the same
330Hz sine) — the single biggest perceived polish gap. (1) Generative
ambient music: a NumPy generative engine — a slow drone + plucked
koto-like melody + taiko percussion, root note mapped from zone hue, a
4-bar loop re-rolled each cycle for non-repetition. Crossfade between zone
segments. (2) Layered SFX with ADSR envelopes + noise layers + pitch
variation + UI sounds replacing the single-sine tones. (3) A SEPARATE
`music_on` toggle distinct from SFX + a volume slider (non-negotiable
accessibility condition). Default to off or very low volume.
- **Files:** `assets.py`, `core/state.py`, `ui/screen_settings.py`,
  `main.py`
- **Acceptance:**
  - A generative pentatonic koto/taiko loop keyed to zone hue with a
    4-bar re-rolled cycle
  - Crossfade between zone segments (no jarring key changes)
  - Layered SFX with ADSR envelopes + noise layers + pitch variation + UI
    sounds replacing the single-sine tones
  - A SEPARATE `music_on` toggle distinct from SFX + a volume slider
    (non-negotiable accessibility condition)
  - Default to off or very low volume
  - `sound_on` gate respected; noise-layer volumes conservative for
    sound-sensitive players
  - One music system, one SFX system (no competing duplicates)

#### pl-accessibility (order 38, P2, med)
Current accessibility is only 2 toggles (`sound_on` + `reduced_motion`).
The text contrast ratio is borderline WCAG AA (~4.5:1). `cb_symbols.py`
exists but is unwired. (1) High-contrast mode: a high-contrast palette +
audit all hardcoded colors (boss_fx `_GLOW`) to read from `theme.C` so the
swap is consistent. (2) Dyslexia-friendly font option: a text scale
multiplier (0.8x-1.6x) and a dyslexia-friendly toggle (wider letter
spacing / monospace fallback), cached (keyed by size, bold, dyslexia). (3)
Wire `cb_symbols.py`.
- **Files:** `ui/screen_settings.py`, `theme.py`, `ui/cb_symbols.py`,
  `core/state.py`, `engine/boss_fx.py`
- **Acceptance:**
  - A high-contrast mode toggle with a high-contrast palette; all
    hardcoded colors read from `theme.C`
  - A text scale multiplier (0.8x-1.6x) toggle
  - A dyslexia-friendly font toggle (wider letter spacing / monospace
    fallback)
  - Dyslexia letter-spacing rendering is cached (keyed by size, bold,
    dyslexia) and only on toggle
  - `cb_symbols.py` wired
  - High-contrast mode ships independently of music

## 12. Architecture & Data Flow

### BonusProvider registry (gp-eventbus-bonusprovider)

The central architectural change. `aggregate_bonuses(state)` is refactored
from a monolithic function into a **BonusProvider registry**:

```
BonusProvider = callable(state) -> dict[str, float]
providers = [_skill_tree_provider, _pets_provider, _gear_provider, ...]
aggregate_bonuses(state) = merge(p(state) for p in providers)
```

The flat-dict contract (`{effect_key: total_value}`) is unchanged so every
consumer (`compute_ninja_stats`, `gold_mult`, `total_gps`, etc.) works
unmodified. New systems (gear, elements, dungeons) register a provider
instead of editing the runner.

### EventBus (gp-eventbus-bonusprovider)

The module-global FX callbacks (`on_enemy_dmg`, `on_ninja_dmg`,
`on_boss_spawn`, `on_firefly_spawn`) become a Runner-owned EventBus. Engine
modules emit events (`emit("enemy_dmg", x, y, amount, is_crit)`) instead
of calling module globals. Module globals kept as deprecated aliases for one
release. This decouples the engine from the FX layer cleanly.

### State extensions

New GameState fields (all additive, migrated by pl-save-migration):
- `render_quality` (gfx-render-tier), `attuned_element` (gp-godai-fusion)
- `gear` dict (cnt-gear-loot), `tokens` dict (gp-permanent-scaling)
- `dungeon_*` fields (cnt-shadow-dungeon), `souls`, `soul_tree` (gp-reincarnation)
- `dojo` (gp-build-spec), `rhythm_streak` (gp-skill-synergy-rhythm)
- `music_on`, `volume`, `text_scale`, `dyslexia_font`, `high_contrast`
- `seen_hints` set (pl-hints-nav-tooltips)

### Data flow

```
data/ (dataclass defs) → engine/ (pure sim, emits events) → EventBus
                        ↓                                  ↓
                  core/bonuses (BonusProvider registry)   engine/*_fx (FX systems)
                        ↓                                  ↓
                  core/state (single source of truth) ← ui/ (reads state, draws)
```

The simulation (`engine/`) stays pure state and never draws. The UI
(`ui/`) reads it. New systems follow this: data defs in `data/`, logic in
`engine/`/`core/`, FX in `engine/*_fx.py`, UI in `ui/screen_*.py`.

## 13. Testing Strategy

- **Smoke test:** `python3 main.py` khởi động không crash, tất cả 14 screen
  chuyển đổi được, autosave 15s chạy.
- **Unit tests (math curves):** `combo_mult` asymptotic cap, `format_number`
  overflow, `zone_hp/dmg/gold` per-cycle multipliers, `tier_mult = 1.6^tier`,
  tap-fatigue curve, gacha soft-pity.
- **Save migration tests:** v2 save loads under v3 code without data loss;
  each migration is unit-testable with a fixture dict.
- **FX regression:** every FX system draws without error under
  `reduced_motion` (low tier) and high tier; particle count caps respected.
- **Balance playtests:** first 3 ascensions (cnt-building-unlock), tap:auto
  ratio (gp-tap-auto-rebalance), boss shield tuning (cnt-boss-phases after
  rebalance), Soul Tree reset (gp-reincarnation).
- **Integration:** after all features merge, run the full game for 5 minutes
  across 3 ascensions + 1 dungeon run; verify no crashes, 60fps at low tier,
  save/load round-trips.
