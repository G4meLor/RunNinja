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
implementation. Tám phần:

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

## 10. Open Items (to be filled by Phase A–C output)

> Phần này sẽ được thay bằng spec content đầy đủ sau khi Workflow Phase A–C
> hoàn thành:
>
> - **Features detail** — danh sách ~25-30 feature với files/acceptance/
>   dependencies (từ Phase C).
> - **Architecture overview** — cập nhật từ `engine/` thuần state + `ui/`
>   đọc state + Runner wire FX callbacks, mở rộng cho các hệ thống mới.
> - **Data flow** — cách state mới (equipment, dungeons, elements) luân
>   chuyển qua engine/UI.
> - **Testing strategy** — smoke test (`python3 main.py` khởi động không
>   crash), unit test cho math curves, FX regression.
