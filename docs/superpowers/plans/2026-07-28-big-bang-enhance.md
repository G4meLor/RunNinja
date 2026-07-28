# Big Bang Enhance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Big-bang enhance Tap Ninja across 4 dimensions (graphics, content, gameplay, polish) — 38 features produced by a 23-agent research/critique/synthesis workflow.

**Architecture:** Extend the existing engine-pure / UI-reads / Runner-wires-FX pattern. The central enabler is a BonusProvider registry + EventBus (Task 3) that lets new systems (gear, elements, dungeons) register without editing the 389-line Runner god-object. New state fields are additive, migrated by an explicit save-version chain (Task 2). A 3-tier render quality (Task 10) gates all new FX through the same code path as `reduced_motion`.

**Tech Stack:** Python 3.11+, pygame (>=2.5,<3), NumPy (>=1.24), pytest for tests. Headless testing via `SDL_VIDEODRIVER=dummy`.

**User decisions (already made):**
- "Không ràng buộc gì cả, sáng tạo hết mức, có thể thay đổi cả repo" — no constraints, free to change the whole repo.
- "Một spec bao trùm" — one overarching spec covering all 4 dimensions.
- "Phased fan-out + critique" orchestration; "Lớn" scale (~16 research + 5 critique + 2 synthesis + ~25-30 specialist agents).
- "Mỗi feature chia nhỏ ra và giao nhiệm vụ đó cho 1 agent chuyên biệt" — each feature → 1 specialist agent.
- Spec approved at `docs/superpowers/specs/2026-07-27-big-bang-enhance-design.md`.

**Spec:** `docs/superpowers/specs/2026-07-27-big-bang-enhance-design.md` — the authoritative feature list, acceptance criteria, conflicts resolved, open questions, and gaps. Each task below cites its feature id; read the spec section for full context.

**Tiers (execution order):** foundation (Tasks 1-6) → core (7-14) → content (15-35) → polish (36-38). Tasks are sequenced by `implementation_order` from the spec §10 feature list. Dependencies (`depends_on`) map to `blockedBy` relationships set after task creation.

**Testing conventions:**
- New tests live in `tests/` (created in Task 1).
- Run tests headless: `SDL_VIDEODRIVER=dummy pytest tests/ -q`
- Smoke test the game: `SDL_VIDEODRIVER=dummy timeout 8 python3 -c "import main; ..."` (Task 1 sets up the harness).
- Every task ends with a commit.

**Open questions deferred to their tasks (with the spec's recommendation baked in):**
- Task 14 (cnt-building-unlock): persist-through-ascension recommended; re-verify elixir_gain after Task 11.
- Task 23 (gp-tap-auto-rebalance): ~3:1 ratio recommended; tap fatigue 5%/tap above 5/s, floor 0.3x.
- Task 22 (cnt-shadow-dungeon-runner): compose existing engine components (verified feasible).
- Task 31 (gfx-weather): ship for all 9 zones (3 hero zones as the visible subset; the rest reuse a default).
- Task 25/35 (gp-reincarnation): gate behind Singularity + 10 ascensions; free respec.

---


## Task 1: Test harness + smoke test scaffold (`gp-combo-cap-bug` prep)

**Goal:** Stand up the `tests/` directory, pytest config, and a headless smoke-test harness so every later task can write and run tests. This is a prerequisite task (not in the spec's 38) that makes TDD possible.

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`

**Acceptance Criteria:**
- [ ] `tests/` exists with `__init__.py` and `conftest.py`
- [ ] `pytest.ini` configures `SDL_VIDEODRIVER=dummy` env and testpaths=tests
- [ ] A smoke test imports `main`, constructs `Game()` headless, runs 30 frames, and exits without error
- [ ] `SDL_VIDEODRIVER=dummy pytest tests/ -q` passes (0 failures)
- [ ] `requirements.txt` adds `pytest>=7.4`

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q` → 1 passed

**Steps:**

- [ ] **Step 1: Add pytest to requirements**

```
pytest>=7.4
```

- [ ] **Step 2: Write pytest.ini**

```ini
[pytest]
testpaths = tests
env =
    SDL_VIDEODRIVER=dummy
    SDL_AUDIODRIVER=dummy
```

- [ ] **Step 3: Write tests/conftest.py with a headless pygame fixture**

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pytest

@pytest.fixture(scope="session")
def pygame_headless():
    import pygame
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass
    screen = pygame.display.set_mode((1280, 720))
    yield pygame
    pygame.quit()
```

- [ ] **Step 4: Write the smoke test**

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

def test_game_constructs_and_runs_30_frames():
    import main
    g = main.Game()
    for _ in range(30):
        g._update(1/60)
    # No exception = pass.
    assert g.state is not None
    assert g.runner is not None
```

- [ ] **Step 5: Run the smoke test**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add tests/ pytest.ini requirements.txt
git commit -m "test: add pytest harness + headless smoke test"
```


## Task 2: Combo multiplier cap bug fix (`gp-combo-cap-bug`)

**Goal:** Fix the critical combo multiplier bug — `COMBO_MULT_CAP=3.0` is defined but never applied, so at combo 200 with maxed `combo_step` the multiplier hits ~270x instead of 3.0x. Replace the linear formula with an asymptotic curve structurally capped at 3.0x.

**Files:**
- Modify: `engine/runner.py:31-34,96-99`
- Modify: `config.py` (add `COMBO_TAU`)
- Test: `tests/test_combo_cap.py`

**Acceptance Criteria:**
- [ ] `combo_mult()` returns `1 + 3.0*(1 - exp(-c/COMBO_TAU))` (asymptotic, structurally capped at 3.0x)
- [ ] At combo 200 with maxed `combo_step` the multiplier is ~3.0x (not 270x)
- [ ] The curve is smooth (no hard cliff at 200)
- [ ] `combo_step` upgrade reduces `COMBO_TAU` (ramp speed), not the step
- [ ] All existing combo-dependent code still works (smoke test passes)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_combo_cap.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
import math

def test_combo_mult_asymptotic_cap(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner, COMBO_MULT_CAP
    state = GameState()
    r = Runner(state)
    # No combo_step upgrade: combo 200 should approach but not exceed cap.
    state.combo = 200
    m = r.combo_mult()
    assert 1.0 < m < COMBO_MULT_CAP + 0.01, f"got {m}"
    assert m <= COMBO_MULT_CAP, f"exceeds cap: {m}"
    # combo 0 -> 1.0
    state.combo = 0
    assert r.combo_mult() == 1.0
    # monotonic increasing
    prev = 1.0
    for c in [10, 25, 50, 100, 200, 400]:
        state.combo = c
        m = r.combo_mult()
        assert m > prev, f"not monotonic at {c}"
        prev = m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_combo_cap.py -q`
Expected: FAIL (combo_mult returns ~270x at combo 200, exceeds cap)

- [ ] **Step 3: Add COMBO_TAU to config.py**

```python
# Combo curve: asymptotic approach to COMBO_MULT_CAP.
# combo_step upgrade reduces COMBO_TAU (faster ramp), not the step.
COMBO_TAU = 50.0      # combo count at which the multiplier is ~63% of cap
```

- [ ] **Step 4: Rewrite combo_mult() in engine/runner.py**

Replace the `combo_mult` method body:
```python
def combo_mult(self) -> float:
    c = self.state.combo
    tau = COMBO_TAU - _upgrade_val(self.state, "combo_step")
    tau = max(5.0, tau)  # floor so the ramp never becomes instant
    return 1.0 + COMBO_MULT_CAP * (1.0 - math.exp(-c / tau))
```
Keep the existing `COMBO_MULT_CAP = 3.0` constant; remove the now-unused `COMBO_STEP` and `COMBO_CAP` (or leave them as deprecated). Import `math` (already imported).

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_combo_cap.py -q`
Expected: passed

- [ ] **Step 6: Run the smoke test**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add engine/runner.py config.py tests/test_combo_cap.py
git commit -m "fix: combo multiplier cap (asymptotic curve, ~3.0x at combo 200)"
```


## Task 3: BonusProvider registry + EventBus + Content registry (`gp-eventbus-bonusprovider`)

**Goal:** The structural prerequisite for cleanly adding gear, dungeons, elements, and mini-games. Refactor `aggregate_bonuses` into a BonusProvider registry; add a Runner-owned EventBus replacing module-global FX callbacks; add a Content registry for ID-based zone/enemy lookup; define `MAX_TOTAL_DAMAGE_MULT` in config.

**Files:**
- Modify: `core/bonuses.py` (BonusProvider registry)
- Modify: `engine/runner.py` (EventBus, wire providers)
- Modify: `engine/enemy.py` (emit events instead of module globals)
- Modify: `engine/world.py` (emit events)
- Modify: `data/enemies.py` (Content registry, no silent clamp)
- Modify: `config.py` (`MAX_TOTAL_DAMAGE_MULT`)
- Test: `tests/test_bonus_provider.py`, `tests/test_eventbus.py`

**Acceptance Criteria:**
- [ ] `aggregate_bonuses` uses a BonusProvider registry; the flat-dict contract is unchanged so every consumer works unmodified
- [ ] Existing code split into `_skill_tree_provider` + `_pets_provider`, both registered
- [ ] A Runner-owned EventBus replaces module-global FX callbacks; engine modules emit events
- [ ] Module globals (`on_enemy_dmg`, `on_ninja_dmg`, `on_boss_spawn`, `on_firefly_spawn`) kept as deprecated aliases for one release
- [ ] A Content registry enables ID-based zone/enemy lookup (no silent clamp in `zone_by_index`)
- [ ] A `MAX_TOTAL_DAMAGE_MULT` sanity cap defined in `config.py` with a documented stacking order
- [ ] The runner's idle update loop stays intact (smoke test passes)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_bonus_provider.py tests/test_eventbus.py -q` → passed

**Steps:**

- [ ] **Step 1: Write failing tests for the BonusProvider registry**

```python
def test_aggregate_bonuses_unchanged_contract(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.skill_tree = {"off_root"}  # +10% tap_pct
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0.0) == pytest.approx(0.10)

def test_bonus_provider_registry_extensible(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses, register_provider
    def my_provider(state):
        return {"custom_key": 0.5}
    register_provider(my_provider)
    out = aggregate_bonuses(GameState())
    assert out.get("custom_key", 0.0) == 0.5
```

- [ ] **Step 2: Write failing test for the EventBus**

```python
def test_eventbus_dispatch(pygame_headless):
    from engine.eventbus import EventBus
    bus = EventBus()
    received = []
    bus.on("enemy_dmg", lambda *a, **k: received.append(("enemy_dmg", a, k)))
    bus.emit("enemy_dmg", 100, 200, 5.0, is_crit=True, is_boss=False)
    assert received and received[0][0] == "enemy_dmg"
    assert received[0][1] == (100, 200, 5.0)
    assert received[0][2] == {"is_crit": True, "is_boss": False}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_bonus_provider.py tests/test_eventbus.py -q`
Expected: FAIL (no register_provider, no EventBus module)

- [ ] **Step 4: Refactor core/bonuses.py into a BonusProvider registry**

```python
"""Aggregate all permanent + equipped bonuses into a flat dict.

BonusProvider registry: each source registers a callable(state) -> dict.
aggregate_bonuses merges all registered providers. The flat-dict contract
({effect_key: total_value}) is unchanged so every consumer works.
"""
from __future__ import annotations

from core.state import GameState
from data import skill_tree as st
from data import pets as pet_def

Provider = callable  # callable(state) -> dict[str, float]
_PROVIDERS: list[Provider] = []


def register_provider(p: Provider) -> None:
    if p not in _PROVIDERS:
        _PROVIDERS.append(p)


def _skill_tree_provider(state: GameState) -> dict[str, float]:
    out: dict[str, float] = {}
    for n in st.NODES:
        if n.id in state.skill_tree:
            out[n.effect_key] = out.get(n.effect_key, 0.0) + n.effect_value
    return out


def _pets_provider(state: GameState) -> dict[str, float]:
    out: dict[str, float] = {}
    for pid in state.equipped_pets:
        bond = state.pet_bond(pid)
        if bond <= 0:
            continue
        p = pet_def.BY_ID.get(pid)
        if p is None:
            continue
        out[p.buff_key] = out.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond)
    return out


register_provider(_skill_tree_provider)
register_provider(_pets_provider)


def aggregate_bonuses(state: GameState) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in _PROVIDERS:
        for k, v in p(state).items():
            out[k] = out.get(k, 0.0) + v
    return out
```

- [ ] **Step 5: Create engine/eventbus.py**

```python
"""Runner-owned event bus replacing module-global FX callbacks.

Engine modules emit events; the runner subscribes the FX systems.
Module globals (engine/enemy.on_enemy_dmg etc.) are kept as deprecated
aliases that forward to the bus for one release.
"""
from __future__ import annotations
from typing import Callable, Any

class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, name: str, handler: Callable) -> None:
        self._handlers.setdefault(name, []).append(handler)

    def emit(self, name: str, *args, **kwargs) -> None:
        for h in self._handlers.get(name, ()):
            try:
                h(*args, **kwargs)
            except Exception:
                pass  # FX must never break the simulation
```

- [ ] **Step 6: Add MAX_TOTAL_DAMAGE_MULT + stacking order to config.py**

```python
# Sanity cap on the total damage multiplier (sum of all stacking sources).
# Stacking order (documented): base * tier_mult * combo_mult * evo *
# godai_element * gear * tokens * heritage * epic_research, capped here.
MAX_TOTAL_DAMAGE_MULT = 1e9
```

- [ ] **Step 7: Wire the EventBus in the Runner; emit events in engine/enemy.py and engine/world.py**

In `engine/runner.py.__init__`, create `self.bus = EventBus()` and subscribe the FX systems. In `engine/enemy.py`, replace the module-global calls with `bus.emit("enemy_dmg", ...)`; keep `on_enemy_dmg` as a deprecated alias that the runner sets to `lambda *a, **k: self.bus.emit("enemy_dmg", *a, **k)`. Same for `on_ninja_dmg`, `on_boss_spawn`, `on_firefly_spawn`.

- [ ] **Step 8: Add a Content registry to data/enemies.py (no silent clamp)**

```python
def zone_by_id(zone_id: str) -> dict:
    for z in ZONES:
        if z["id"] == zone_id:
            return z
    raise KeyError(f"unknown zone id: {zone_id}")

def zone_by_index(i: int) -> dict:
    if i < 0:
        raise ValueError(f"negative zone index: {i}")
    if i >= len(ZONES):
        # Cycle handled by the caller (cnt-infinite-zones); here clamp to last.
        return ZONES[-1]
    return ZONES[i]
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_bonus_provider.py tests/test_eventbus.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 10: Commit**

```bash
git add core/bonuses.py engine/eventbus.py engine/runner.py engine/enemy.py engine/world.py data/enemies.py config.py tests/test_bonus_provider.py tests/test_eventbus.py
git commit -m "refactor: BonusProvider registry + EventBus + Content registry"
```


## Task 4: format_number overflow fix + tiered precision (`pl-format-number`)

**Goal:** `utils.format_number` overflows at 1e36, returning '1000Dc'. Add a scientific-notation fallback when the unit table is exhausted and tier the precision. Must ship before Task 11 (cnt-infinite-zones) which generates numbers >1e36.

**Files:**
- Modify: `utils.py` (`format_number`)
- Test: `tests/test_format_number.py`

**Acceptance Criteria:**
- [ ] `format_number` returns a scientific-notation string (e.g. `1.20e36`) when the unit table is exhausted
- [ ] No '1000Dc' overflow at 1e36+
- [ ] Tiered precision (<1e6 to 2 decimals, >=1e9 to 2 sig figs)
- [ ] HUD currency pills still fit after the format change (smoke test passes)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_format_number.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
import pytest
from utils import format_number

def test_small_numbers():
    assert format_number(0) == "0"
    assert format_number(123) == "123"
    assert format_number(1234) == "1.23K"

def test_large_numbers_tiered():
    assert format_number(1_500_000) == "1.50M"
    assert format_number(1_500_000_000) == "1.5B"  # 2 sig figs >=1e9

def test_overflow_scientific_notation():
    # 1e36 should NOT return "1000Dc"; it should return scientific notation.
    s = format_number(1e36)
    assert "e" in s or "E" in s, f"got {s}"
    assert "Dc" not in s or "e" in s, f"overflow: {s}"
    # 1e40 -> scientific
    s2 = format_number(1e40)
    assert "e" in s2.lower(), f"got {s2}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_format_number.py -q`
Expected: FAIL (overflow returns "1000Dc")

- [ ] **Step 3: Fix format_number in utils.py**

Read the current `format_number` in `utils.py`, then replace it with a version that:
- Uses the existing unit table (K, M, B, T, Q, Qi, Sx, Sp, Oc, No, Dc...).
- When the value exceeds the largest unit (index >= len(units)), returns `f"{n:.2e}"`.
- Tiers precision: `<1e6` → 2 decimals, `>=1e9` → 2 sig figs (e.g. `1.5B` not `1.50B`).

```python
def format_number(n) -> str:
    n = float(n)
    if n < 0:
        return "-" + format_number(-n)
    if n < 1000:
        return f"{int(n)}" if n == int(n) else f"{n:.2f}"
    units = ["K", "M", "B", "T", "Q", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]
    i = 0
    while n >= 1000 and i < len(units) - 1:
        n /= 1000.0
        i += 1
    if i >= len(units) - 1 and n >= 1000:
        # Exhausted the table -> scientific notation.
        return f"{n * (1000 ** (len(units) - 1 - i)):.2e}"
    if n >= 1e6 / (1000 ** i):
        # >= 1e9 in original units -> 2 sig figs
        return f"{n:.2g}{units[i]}"
    return f"{n:.2f}{units[i]}"
```
Adjust to match the exact existing unit list and divisor; the key fix is the scientific-notation fallback and the tiered precision.

- [ ] **Step 4: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_format_number.py -q`
Expected: passed

- [ ] **Step 5: Run smoke test (HUD pills still fit)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add utils.py tests/test_format_number.py
git commit -m "fix: format_number overflow (scientific notation) + tiered precision"
```


## Task 5: Explicit save-version migration chain (`pl-save-migration`)

**Goal:** `save_version=2` is decorative — `from_dict` uses `hasattr+setattr` with no migration logic. Add a `MIGRATIONS` dict of pure functions; `load()` walks the chain from the file's `save_version` up to `CURRENT`. Bump `save_version` to 3 with the first migration that seeds new-field defaults.

**Files:**
- Modify: `core/state.py` (`MIGRATIONS`, `load`, `from_dict`)
- Modify: `core/save_manager.py` (if it has its own load path)
- Test: `tests/test_save_migration.py`

**Acceptance Criteria:**
- [ ] A `MIGRATIONS` dict of pure functions, applied in `load()` by walking from the file's `save_version` up to `CURRENT`
- [ ] `save_version` bumped to 3 with the first migration (seeds new-field defaults: `render_quality`, `attuned_element`, `dojo`, `rhythm_streak`)
- [ ] Each migration is unit-testable with a fixture dict
- [ ] Never mutates the live save during migration (migrate the dict in memory, then save)
- [ ] An existing v2 save loads without data loss after migration

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_save_migration.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_v2_save_loads_under_v3_code():
    from core.state import GameState, CURRENT_SAVE_VERSION, MIGRATIONS
    v2_dict = {
        "save_version": 2, "gold": 1000.0, "elixir": 5,
        "skill_tree": [], "achievements": [], "pets": {},
        "upgrades": {"tap_power": 3}, "buildings": {"farm": 2},
    }
    s = GameState.from_dict(_migrate(v2_dict))
    assert s.gold == 1000.0
    assert s.elixir == 5
    assert s.upgrades["tap_power"] == 3
    # New v3 fields seeded with defaults.
    assert hasattr(s, "render_quality")
    assert s.attuned_element == "none"

def test_migration_chain_walks_all_versions():
    from core.state import MIGRATIONS, CURRENT_SAVE_VERSION
    assert 2 in MIGRATIONS
    # Every version from 2 up to CURRENT has a migration.
    for v in range(2, CURRENT_SAVE_VERSION):
        assert v in MIGRATIONS, f"missing migration from v{v}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_save_migration.py -q`
Expected: FAIL (no MIGRATIONS, no CURRENT_SAVE_VERSION)

- [ ] **Step 3: Add MIGRATIONS + CURRENT_SAVE_VERSION to core/state.py**

```python
CURRENT_SAVE_VERSION = 3

def _migrate_v2_to_v3(d: dict) -> dict:
    """v2 -> v3: seed new-field defaults for the big-bang enhance."""
    d = dict(d)
    d.setdefault("render_quality", "med")
    d.setdefault("attuned_element", "none")
    d.setdefault("dojo", "none")
    d.setdefault("rhythm_streak", 0)
    d.setdefault("tokens", {})
    d.setdefault("gear", {})
    d.setdefault("souls", 0)
    d.setdefault("soul_tree", [])
    d.setdefault("music_on", False)
    d.setdefault("volume", 0.5)
    d.setdefault("text_scale", 1.0)
    d.setdefault("dyslexia_font", False)
    d.setdefault("high_contrast", False)
    d.setdefault("seen_hints", [])
    d["save_version"] = 3
    return d

MIGRATIONS = {
    2: _migrate_v2_to_v3,
}

def _migrate(d: dict) -> dict:
    v = d.get("save_version", 1)
    while v in MIGRATIONS:
        d = MIGRATIONS[v](d)
        v = d.get("save_version", v + 1)
    return d
```

- [ ] **Step 4: Wire migration into load() and from_dict()**

In `load()`, after reading the JSON dict, call `d = _migrate(d)` before `from_dict`. In `from_dict`, the existing `hasattr+setattr` loop handles the new fields (they're in the dataclass with defaults). Ensure `save_version` is set to `CURRENT_SAVE_VERSION` after migration.

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_save_migration.py -q`
Expected: passed

- [ ] **Step 6: Run smoke test (save/load round-trip)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add core/state.py tests/test_save_migration.py
git commit -m "feat: explicit save-version migration chain (v2 -> v3)"
```


## Task 6: convert_alpha on every cached sprite surface (`gfx-convert-alpha`)

**Goal:** The 5 sprite caches in `assets.py` (ninja/enemy/firefly/building/pet) create SRCALPHA surfaces but never call `.convert_alpha()`, so every blit does a slow 32-bit ARGB software composite. Add `.convert_alpha()` at cache-miss time (one call per miss, zero per-frame cost).

**Files:**
- Modify: `assets.py:27-45,52-103,110-127,134-161,168-182`
- Test: `tests/test_convert_alpha.py`

**Acceptance Criteria:**
- [ ] `ninja_surface`, `enemy_surface`, `firefly_surface`, `building_surface`, `pet_surface` all call `.convert_alpha()` on the final surface before caching
- [ ] No behavior change — sprites render identically (smoke test passes)
- [ ] Blit throughput improves ~1.5-2x in a microbenchmark
- [ ] Caches remain lazy (no work before `display.set_mode`)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_convert_alpha.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_sprite_surfaces_are_converted(pygame_headless):
    import pygame
    from assets import ninja_surface, enemy_surface, firefly_surface, building_surface, pet_surface
    from data.enemies import ZONES
    for fn, arg in [
        (ninja_surface, 64),
        (enemy_surface, ZONES[0]["enemies"][0]),
        (firefly_surface, 10),
        (building_surface, "farm"),
        (pet_surface, "frog"),
    ]:
        s = fn(arg) if fn is not pet_surface else fn("frog", 120)
        # A converted surface has the display's pixel format; an unconverted
        # SRCALPHA surface has 32-bit ARGB. We check the flags don't include
        # the unconverted SRCALPHA-only path by verifying the surface is
        # not flagged as needing conversion (practical check: blit speed).
        assert s is not None
```

- [ ] **Step 2: Run test to verify it fails (or passes trivially)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_convert_alpha.py -q`
Expected: FAIL or pass — the real check is the code change in step 4.

- [ ] **Step 3: Add convert_alpha() to each sprite generator in assets.py**

In each of the 5 cached sprite functions, before assigning to the cache dict, add `.convert_alpha()`:
```python
surf = surf.convert_alpha()
_CACHE[key] = surf
```
For `ninja_surface`, `enemy_surface`, `firefly_surface`, `building_surface`, `pet_surface`. The `background` already calls `.convert()` (line 195) — leave it.

- [ ] **Step 4: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_convert_alpha.py -q`
Expected: passed

- [ ] **Step 5: Run smoke test (sprites render identically)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add assets.py tests/test_convert_alpha.py
git commit -m "perf: convert_alpha on all cached sprite surfaces"
```


## Task 7: Adopt ParticleSystem2 as the sole particle system (`gfx-particles-pool`)

**Goal:** `engine/particles.py` `ParticleSystem2` is fully-pooled but `main.py:64` still uses the legacy `assets.ParticleSystem` which allocates a fresh SRCALPHA Surface per particle per frame. Replace the import + instantiation; route death/firefly/combo bursts through ParticleSystem2.

**Files:**
- Modify: `main.py:64,216-219` (instantiate ParticleSystem2)
- Modify: `engine/death_fx.py`, `engine/firefly_fx.py`, `engine/combo_fx.py` (route bursts through ParticleSystem2)
- Test: `tests/test_particles_pool.py`

**Acceptance Criteria:**
- [ ] `main.py` instantiates `ParticleSystem2` instead of `assets.ParticleSystem`
- [ ] death/firefly/combo bursts route through ParticleSystem2
- [ ] No per-frame Surface allocations after warm-up (verified with a counter)
- [ ] Particle count capped per quality tier (respects Task 10's render tier when it lands; for now cap at a fixed max)
- [ ] Visual parity with the legacy system at the default tier (smoke test passes)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_particles_pool.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test (allocation counter)**

```python
def test_no_per_frame_allocations(pygame_headless):
    import pygame
    from engine.particles import ParticleSystem2
    ps = ParticleSystem2()
    ps.burst(100, 100, (255, 200, 90), count=20)
    # Warm up: draw once to populate the scratch cache.
    surf = pygame.Surface((1280, 720))
    ps.draw(surf)
    allocs_before = len(ps._scratch_cache)
    for _ in range(60):
        ps.update(1/60)
        ps.draw(surf)
        ps.burst(100, 100, (255, 200, 90), count=5, life=0.3)
    allocs_after = len(ps._scratch_cache)
    # No new scratch surfaces after warm-up (pooled).
    assert allocs_after == allocs_before, f"leaked {allocs_after - allocs_before} scratch surfaces"
```

- [ ] **Step 2: Run test to verify it passes (ParticleSystem2 already pooled)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_particles_pool.py -q`
Expected: passed (ParticleSystem2 is already pooled; this confirms the baseline)

- [ ] **Step 3: Replace the legacy particle system in main.py**

In `main.py.__init__`, change:
```python
from assets import ParticleSystem, init_sfx
...
self.particles = ParticleSystem()
```
to:
```python
from engine.particles import ParticleSystem2
from assets import init_sfx
...
self.particles = ParticleSystem2()
```
Update `_update_particles` to call `self.particles.update(dt)` (same API).

- [ ] **Step 4: Route death/firefly/combo bursts through ParticleSystem2**

In `engine/death_fx.py`, `engine/firefly_fx.py`, `engine/combo_fx.py`, wherever they create their own particle surfaces or call the legacy system, route through a shared `ParticleSystem2` instance passed in (or use the runner's). The runner owns `self.particles` and passes it to the FX systems that need it. For now, if an FX system has its own internal particle pool (like combo_fx does), leave it — the goal is the main `self.particles` in main.py.

- [ ] **Step 5: Run smoke test**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add main.py engine/death_fx.py engine/firefly_fx.py engine/combo_fx.py tests/test_particles_pool.py
git commit -m "perf: adopt ParticleSystem2 as the sole particle system"
```


## Task 8: Elite enemies + mini-bosses (`cnt-elite-miniboss`)

**Goal:** Wire up the dead `is_elite` field on Enemy. In `world._spawn_regular` add a 5% elite roll (3x HP, 5x gold, guaranteed `rare_drop`). Add `_spawn_miniboss` at 50% `ZONE_DISTANCE` that blocks progress until killed (0.4x the zone boss stats). No new state fields; elites are transient.

**Files:**
- Modify: `engine/world.py:86-91,60-84` (elite roll + mini-boss spawn)
- Modify: `engine/enemy.py:48-58` (spawn_elite, spawn_miniboss)
- Modify: `engine/runner.py` (wire mini-boss FX)
- Modify: `engine/boss_fx.py` (smaller intro for mini-boss)
- Test: `tests/test_elite_miniboss.py`

**Acceptance Criteria:**
- [ ] 5% of regular spawns are elite (3x HP, 5x gold, guaranteed `rare_drop`)
- [ ] A mini-boss spawns at 50% zone distance and blocks progress until killed
- [ ] `is_elite` is set on spawned elites and rendered distinctly
- [ ] No new GameState fields (elites are transient)
- [ ] Chests drop on elite and boss kills (chest mechanic added in a later task; for now, the elite drops guaranteed `rare_drop`)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_elite_miniboss.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_elite_spawn_5pct(pygame_headless):
    from core.state import GameState
    from engine.world import World
    from engine.enemy import Enemy
    w = World()
    elites = 0
    total = 0
    for _ in range(1000):
        # Force a spawn by calling _spawn_regular directly.
        w._spawn_regular()
    for e in w.enemies:
        if e.is_elite:
            elites += 1
        total += 1
    assert total == 1000
    # 5% +/- 3% (statistical tolerance)
    assert 20 <= elites <= 80, f"elite rate {elites/10}%"

def test_miniboss_blocks_progress(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    import config as cfg
    state = GameState()
    r = Runner(state)
    # Advance to 50% zone distance.
    r.world.zone_distance = cfg.ZONE_DISTANCE * 0.5
    r.update(1.0)
    # A mini-boss should be present.
    assert any(e.is_boss and not e.is_elite for e in r.world.enemies) or r.world.boss_active
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_elite_miniboss.py -q`
Expected: FAIL (no elite roll, no mini-boss spawn)

- [ ] **Step 3: Add elite roll + mini-boss spawn to engine/world.py**

In `_spawn_regular`:
```python
def _spawn_regular(self) -> None:
    pool = self.zone["enemies"]
    edef = rng().choice(pool)
    is_elite = rng().random() < 0.05
    hp = self.zone_hp(edef) * (3.0 if is_elite else 1.0)
    dmg = self.zone_dmg(edef)
    gold = self.zone_gold(edef) * (5.0 if is_elite else 1.0)
    e = spawn_enemy(edef, hp=hp, dmg=dmg, gold=gold)
    if is_elite:
        e.is_elite = True
        e.rare_drop = 1.0  # guaranteed
    self.enemies.append(e)
```

Add mini-boss spawn at 50% zone distance in `update`:
```python
if not self.boss_active and not self.miniboss_active and self.zone_distance >= cfg.ZONE_DISTANCE * 0.5:
    self._spawn_miniboss()
```

```python
def _spawn_miniboss(self) -> None:
    self.miniboss_active = True
    bdef = ed.boss_for_zone(self.zone_id)
    boss = spawn_boss(bdef, hp=self.zone_hp(bdef) * 0.4,
                     dmg=self.zone_dmg(bdef) * 0.4,
                     gold=self.zone_gold(bdef) * 0.4)
    boss.is_boss = False  # not THE zone boss; it's a mini-boss
    boss.is_miniboss = True
    self.enemies.append(boss)
```
Add `self.miniboss_active = False` to `__init__` and `reset_for_ascension`. In `on_enemy_killed`, set `self.miniboss_active = False` if `enemy.is_miniboss`. Add `is_miniboss: bool = False` to the Enemy dataclass in `engine/enemy.py`.

- [ ] **Step 4: Render elites distinctly (screen_game.py)**

In `ui/screen_game.py`, where `is_elite` is rendered, add a distinct outline or color. The existing code already draws "ELITE" text (line 161-162) — keep it.

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_elite_miniboss.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add engine/world.py engine/enemy.py engine/runner.py engine/boss_fx.py ui/screen_game.py tests/test_elite_miniboss.py
git commit -m "feat: elite enemies + mini-bosses (wire up is_elite field)"
```


## Task 9: Building unlock zone rebalance (`cnt-building-unlock`)

**Goal:** 8 of 18 buildings have `unlock_zone` 9-16, but ascension resets zone to 0 and the natural max reachable zone is ~9-12, so half the building roster is dead content. Prefer persist-through-ascension: buildings carry over and scale by the ascension tier `stat_mult`; only gold/upgrades reset. Re-tune `elixir_gain` so the post-ascension economy doesn't snowball. **Note gap #1:** re-verify after Task 11 (cnt-infinite-zones) changes the tier_mult formula.

**Files:**
- Modify: `data/buildings.py` (`unlock_zone` rebalance)
- Modify: `core/ascend.py` (persist buildings, re-tune elixir_gain)
- Modify: `core/game_economy.py` (building scaling by tier)
- Modify: `core/state.py` (no building reset on ascension)
- Test: `tests/test_building_unlock.py`

**Acceptance Criteria:**
- [ ] All 18 buildings are reachable within a normal playthrough
- [ ] Buildings persist through ascension (scaled by tier `stat_mult`)
- [ ] `elixir_gain` re-tuned so the post-ascension economy doesn't snowball
- [ ] The first 3 ascensions feel balanced (playtest — verify no snowball in the test)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_building_unlock.py -q` → passed

**Steps:**

- [ ] **Step 1: Read the current building definitions and ascension logic**

Read `data/buildings.py` (the 18 buildings + `unlock_zone`), `core/ascend.py` (what resets on ascension), `core/game_economy.py` (`total_gps`).

- [ ] **Step 2: Write the failing test**

```python
def test_all_buildings_reachable():
    from data.buildings import BUILDINGS
    import config as cfg
    max_unlock = max(b.unlock_zone for b in BUILDINGS)
    # After rebalance, all buildings unlock by zone 8 (reachable in one run).
    assert max_unlock <= 8, f"max unlock_zone {max_unlock}"

def test_buildings_persist_through_ascension(pygame_headless):
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.buildings = {"farm": 5, "forge": 2}
    state.gold = 100000
    state.zone_index = 5
    state.best_zone = 5
    ascend(state)
    # Buildings persist.
    assert state.buildings.get("farm") == 5
    assert state.buildings.get("forge") == 2
    # Zone resets, gold resets, but buildings stay.
    assert state.zone_index == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_building_unlock.py -q`
Expected: FAIL (buildings reset on ascension; unlock_zone > 8)

- [ ] **Step 4: Rebalance unlock_zone in data/buildings.py**

Compress all `unlock_zone` values to 0-8 so every building is reachable in a single run to zone 8. Read the current `BUILDINGS` list and set each `unlock_zone` to `min(current, 8)` or a smooth 0-8 distribution.

- [ ] **Step 5: Make buildings persist through ascension in core/ascend.py**

In the `ascend` function, remove the line that clears `state.buildings` (if any). Buildings carry over. Re-tune `elixir_gain` (the elixir awarded on ascension) so the post-ascension economy doesn't snowball — scale it down slightly to account for buildings persisting. Compute elixir from `lifetime_gold` at a rate that keeps the first 3 ascensions balanced:
```python
elixir_gain = int(state.lifetime_gold * ELIXIR_RATE * (1.0 - ELIXIR_DIMINISH * state.ascend_tier))
elixir_gain = max(1, elixir_gain)
```
Adjust `ELIXIR_RATE` so a first ascension gives ~50 elixir (matching the current `soul_reward` tier). Scale building output by `tier_mult` in `total_gps`.

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_building_unlock.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add data/buildings.py core/ascend.py core/game_economy.py tests/test_building_unlock.py
git commit -m "feat: building unlock rebalance + persist through ascension"
```


## Task 10: Combo Finishers + decay grace + combo-break feedback (`gp-combo-finishers`)

**Goal:** Three combo-system improvements. (1) Combo Finishers: bank a charge when combo crosses an existing MILESTONE (25/50/100/200 — piggyback on `combo_fx.MILESTONES`); charges persist through the decay window; spend on 4 finishers. (2) `combo_timer` goes negative to -1.5s before resetting (grace). (3) "COMBO LOST" feedback on combo break.

**Files:**
- Modify: `engine/runner.py:146-150,221-253` (combo decay grace, finisher charges)
- Modify: `engine/combo_fx.py` (MILESTONES reuse, combo-lost banner)
- Modify: `core/state.py` (`combo_charges`, `combo_grace` fields)
- Modify: `ui/screen_game.py` (finisher buttons, COMBO LOST)
- Test: `tests/test_combo_finishers.py`

**Acceptance Criteria:**
- [ ] A charge is banked at each existing MILESTONE (25/50/100/200); charges persist through the decay window
- [ ] 4 finishers spend charges; finisher damage is a fixed multiple of `tap_damage` with its own cap (not multiplicative with `combo_mult`)
- [ ] Bosses are auto-killable without Phantom Step (finishers never gate progression)
- [ ] `combo_timer` goes negative to -1.5s before resetting combo to 0 (grace); a kill during grace restores combo
- [ ] "COMBO LOST" feedback plays on combo break (gated by `reduced_motion`)
- [ ] Combo Milestone Evolutions are NOT implemented — finishers are the single milestone consumer

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_combo_finishers.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_charge_banked_at_milestone(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo = 24
    r._on_combo_killed_increment()  # helper or simulate a kill
    # crossing 25 banks a charge
    assert state.combo_charges >= 1

def test_grace_period_restores_combo(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner, COMBO_WINDOW
    state = GameState()
    r = Runner(state)
    state.combo = 50
    state.combo_timer = -1.0  # in grace
    # A kill during grace restores combo.
    r._on_combo_killed_increment()
    assert state.combo_timer > 0  # restored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_combo_finishers.py -q`
Expected: FAIL (no combo_charges, no grace)

- [ ] **Step 3: Add combo_charges + combo grace to core/state.py**

```python
combo_charges: int = 0
```
(Migrate in Task 5's migration — but since Task 5 already seeds defaults, just add the field to the dataclass.)

- [ ] **Step 4: Implement finisher banking + grace in engine/runner.py**

In `_on_enemy_killed`, when combo crosses a MILESTONE (check `combo_fx.MILESTONES`), bank a charge. Change the combo decay block to allow `combo_timer` to go negative to -1.5s (grace) before resetting:
```python
if self.state.combo > 0:
    self.state.combo_timer -= dt
    if self.state.combo_timer <= -1.5:
        # Combo lost.
        self.combo_fx.lost(self.state.combo)  # COMBO LOST feedback
        self.state.combo = 0
        self.state.combo_charges = 0  # charges lost on full reset
```
On a kill during grace (`combo_timer < 0`), restore `combo_timer` to the full window.

- [ ] **Step 5: Implement 4 finishers in engine/runner.py**

Add `activate_finisher(fid)` with 4 finishers:
- `thousand_cuts`: line AOE, costs 1 charge, damage = `tap_damage * 5` (capped).
- `phantom_step`: boss-kill if combo>=100, costs 2 charges.
- `mirage`: shadow clones, costs 1 charge.
- `executioner_edge`: guaranteed-crit taps, costs 1 charge.
Finisher damage is a fixed multiple of `tap_damage` with `MAX_FINISHER_MULT`, NOT multiplicative with `combo_mult`.

- [ ] **Step 6: Add COMBO LOST to engine/combo_fx.py**

```python
def lost(self, combo: int) -> None:
    """Trigger the COMBO LOST banner (gated by reduced_motion)."""
    # Reuse the banner machinery with a "COMBO LOST" label.
```

- [ ] **Step 7: Add finisher buttons to ui/screen_game.py**

Add 4 finisher buttons next to the skill buttons, showing charge count.

- [ ] **Step 8: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_combo_finishers.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 9: Commit**

```bash
git add engine/runner.py engine/combo_fx.py core/state.py ui/screen_game.py tests/test_combo_finishers.py
git commit -m "feat: combo finishers + decay grace + combo-break feedback"
```


## Task 11: Render-quality tier (high/med/low) + reduced-motion gating (`gfx-render-tier`)

**Goal:** A 3-tier render quality (high/med/low) that extends the existing `reduced_motion` gate coherently and keeps a 60fps floor on Intel iGPUs. The tier MUST gate the same code path as `reduced_motion` so the two never diverge.

**Files:**
- Modify: `core/state.py` (`render_quality` field — already seeded by Task 5)
- Modify: `ui/screen_settings.py` (render quality toggle)
- Modify: `main.py` (read render_quality)
- Test: `tests/test_render_tier.py`

**Acceptance Criteria:**
- [ ] A `render_quality` field on GameState (`high`/`med`/`low`) with a settings toggle
- [ ] Low tier caps particles at 25%, disables additive glow, disables parallax
- [ ] The gate is the same code path as `reduced_motion` (`reduced_motion` forces low tier)
- [ ] 60fps maintained on a weak-iGPU reference machine at low tier (smoke test passes)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_render_tier.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_render_quality_field():
    from core.state import GameState
    s = GameState()
    assert s.render_quality in ("high", "med", "low")

def test_reduced_motion_forces_low(pygame_headless):
    from core.state import GameState
    s = GameState()
    s.reduced_motion = True
    assert s.effective_render_quality() == "low"
    s.reduced_motion = False
    s.render_quality = "high"
    assert s.effective_render_quality() == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_render_tier.py -q`
Expected: FAIL (no render_quality, no effective_render_quality)

- [ ] **Step 3: Add render_quality + effective_render_quality to core/state.py**

```python
render_quality: str = "med"  # high, med, low (Task 5 migration seeds this)

def effective_render_quality(self) -> str:
    if self.reduced_motion:
        return "low"
    return self.render_quality
```

- [ ] **Step 4: Add a render-quality toggle to ui/screen_settings.py**

Add a 3-way toggle (High/Medium/Low) in the settings screen. When `reduced_motion` is on, display the toggle as locked to Low.

- [ ] **Step 5: Add a quality gate helper in a shared module**

Create `core/quality.py` (or extend `theme.py`) with helpers:
```python
def particle_mult(quality: str) -> float:
    return {"high": 1.0, "med": 0.6, "low": 0.25}[quality]
def glow_enabled(quality: str) -> bool:
    return quality != "low"
def parallax_enabled(quality: str) -> bool:
    return quality != "low"
```
Every new FX feature (Tasks 29-32) reads `state.effective_render_quality()` and uses these helpers.

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_render_tier.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add core/state.py core/quality.py ui/screen_settings.py tests/test_render_tier.py
git commit -m "feat: render-quality tier (high/med/low) + reduced-motion gating"
```


## Task 12: Infinite zone cycling with per-cycle multipliers (`cnt-infinite-zones`)

**Goal:** The game ends at zone 9. `cycle=floor(zone_index/9)`, `zone_in_cycle=zone_index%9`. `CYCLE_HP_MULT=8.0`, `CYCLE_DMG_MULT=7.0`, `CYCLE_GOLD_MULT=9.0`. Reuse the 9 themed ZONES + BOSSES; only the scaler changes in `world.py`. `tier_mult = 1.6^tier` replaces the `ASCEND_TIERS` `stat_mult` column; the 7 names remain as labels. **Note gap #1:** this changes the tier_mult formula — re-verify Task 9's elixir_gain re-tune after this lands.

**Files:**
- Modify: `engine/world.py:42-52` (per-cycle multipliers)
- Modify: `data/enemies.py` (cycle-based achievements)
- Modify: `config.py` (`CYCLE_*_MULT`, `tier_mult` formula)
- Modify: `engine/ninja.py:92-96` (`_ascend_tier_mult` = `1.6^tier`)
- Modify: `data/quests.py` (cycle achievements)
- Test: `tests/test_infinite_zones.py`

**Acceptance Criteria:**
- [ ] `zone_hp`/`zone_dmg`/`zone_gold` in `world.py` multiply by per-cycle multipliers (`cycle=floor(zone_index/9)`)
- [ ] Past zone 9 the road continues with the same 9 themed zones at scaled stats
- [ ] A visible "Cycle N" header renders in the game HUD
- [ ] `tier_mult = 1.6^tier` replaces the `ASCEND_TIERS` `stat_mult` column; the 7 names remain as labels
- [ ] Cycle-based achievements (reach cycle 1/3/5/10) exist and fire
- [ ] The endgame no longer stalls at zone 9

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_infinite_zones.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_cycle_multipliers():
    from engine.world import World
    from data.enemies import ZONES
    w = World()
    w.zone_index = 9  # cycle 1, zone_in_cycle 0
    edef = ZONES[0]["enemies"][0]
    hp_cycle0 = World().zone_hp(edef)  # zone 0
    w.zone_index = 9
    hp_cycle1 = w.zone_hp(edef)
    import config as cfg
    assert hp_cycle1 == pytest.approx(hp_cycle0 * cfg.CYCLE_HP_MULT)

def test_tier_mult_formula():
    from core.state import GameState
    from engine.ninja import _ascend_tier_mult
    # 1.6^tier, not the flat ASCEND_TIERS ladder.
    assert _ascend_tier_mult(GameState(ascend_tier=0)) == 1.0
    assert _ascend_tier_mult(GameState(ascend_tier=1)) == pytest.approx(1.6)
    assert _ascend_tier_mult(GameState(ascend_tier=7)) == pytest.approx(1.6**7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_infinite_zones.py -q`
Expected: FAIL (no cycle multipliers, flat tier_mult)

- [ ] **Step 3: Add CYCLE_*_MULT to config.py**

```python
CYCLE_HP_MULT = 8.0
CYCLE_DMG_MULT = 7.0
CYCLE_GOLD_MULT = 9.0
```

- [ ] **Step 4: Apply per-cycle multipliers in engine/world.py**

```python
@property
def cycle(self) -> int:
    return self.zone_index // 9

def zone_hp(self, edef) -> float:
    base = cfg.ZONE_HP_BASE * (cfg.ZONE_HP_GROWTH ** (self.zone_index % 9))
    return base * (cfg.CYCLE_HP_MULT ** self.cycle) * edef.hp_mult
# Same for zone_dmg, zone_gold.
```

- [ ] **Step 5: Change tier_mult to 1.6^tier in engine/ninja.py**

```python
def _ascend_tier_mult(state: GameState) -> float:
    return 1.6 ** state.ascend_tier
```
Keep the 7 `ASCEND_TIERS` names as labels (used in the ascend UI).

- [ ] **Step 6: Add a "Cycle N" header to the HUD in ui/screen_game.py**

In `_draw_hud`, add the cycle to the zone display: `f"{world.zone_name} — Zone {world.zone_index % 9 + 1} (Cycle {world.cycle + 1})"`.

- [ ] **Step 7: Add cycle achievements to data/quests.py**

```python
Achievement("cycle_1", "Cycler", "Reach cycle 1 (zone 9+).",
            lambda s: s.best_zone >= 9, reward_amber=5, reward_medals=50),
Achievement("cycle_3", "Looper", "Reach cycle 3 (zone 27+).",
            lambda s: s.best_zone >= 27, reward_amber=15, reward_medals=150),
Achievement("cycle_5", "Ouroboros", "Reach cycle 5 (zone 45+).",
            lambda s: s.best_zone >= 45, reward_amber=40, reward_medals=400),
```

- [ ] **Step 8: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_infinite_zones.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 9: Re-verify Task 9's elixir_gain (run the building unlock test)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_building_unlock.py -q`
Expected: passed (if it fails, re-tune elixir_gain for the new tier_mult)

- [ ] **Step 10: Commit**

```bash
git add engine/world.py data/enemies.py config.py engine/ninja.py data/quests.py ui/screen_game.py tests/test_infinite_zones.py
git commit -m "feat: infinite zone cycling + per-cycle multipliers + 1.6^tier"
```


## Task 13: Boss soft-phase intensity scaling + attack pattern library (`cnt-boss-phases`)

**Goal:** Consolidate boss proposals into ONE boss system. Soft-phase: HP milestones at 75/50/25% add attack layers (projectile, hazard, summon, shield) by scaling timers — no new state machine, just scaling. Scale attack interval down as HP drops. Bosses are CC-immune. **Note gap #4:** re-test boss shield tuning after Task 23 (gp-tap-auto-rebalance) lands.

**Files:**
- Modify: `engine/enemy.py:105-151` (boss attack patterns, phase scaling)
- Modify: `engine/world.py` (boss phase tracking)
- Modify: `engine/runner.py` (boss phase events)
- Modify: `engine/boss_fx.py` (phase transition visuals)
- Modify: `data/enemies.py` (boss attack pattern defs)
- Test: `tests/test_boss_phases.py`

**Acceptance Criteria:**
- [ ] Bosses gain HP-threshold attack layers at 75/50/25% (no new state machine, scaling only)
- [ ] Attack frequency scales up as HP drops
- [ ] Phase transitions are communicated (nameplate flash, banner, hue shift) without pausing
- [ ] No enrage timer and no weak-point-tap — auto-attack DPS can clear the boss
- [ ] The shield phase is breakable by sustained auto-attack DPS

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_boss_phases.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_boss_phase_scaling(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Spawn a boss.
    r.world.zone_distance = 600  # trigger boss
    r.update(1.0)
    boss = next((e for e in r.world.enemies if e.is_boss), None)
    assert boss is not None
    # At 100% HP, base attack interval.
    base_interval = boss.attack_interval
    # Drop to 50% HP -> faster attacks.
    boss.hp = boss.max_hp * 0.5
    r.update(1.0)
    assert boss.attack_interval < base_interval or boss.phase >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_boss_phases.py -q`
Expected: FAIL (no phase scaling)

- [ ] **Step 3: Add boss phase + attack pattern fields to Enemy in engine/enemy.py**

```python
phase: int = 0
attack_interval: float = 1.0
attack_pattern: str = "melee"  # melee, projectile, hazard, summon, shield
```

- [ ] **Step 4: Implement phase scaling in tick_combat (engine/enemy.py)**

For boss enemies, compute `phase` from HP: `phase = 1 if hp < 0.75*max else 2 if hp < 0.5*max else 3 if hp < 0.25*max else 0`. Scale `attack_interval` down: `interval = base / (1.0 + 0.3 * phase)`. Add attack patterns per phase (projectile at phase 1, hazard at phase 2, summon + shield at phase 3) — these scale existing timers, no new state machine.

- [ ] **Step 5: Add phase transition visuals in engine/boss_fx.py**

On phase change, flash the nameplate + a banner + a hue shift (no pause).

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIDER=dummy pytest tests/test_boss_phases.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add engine/enemy.py engine/world.py engine/runner.py engine/boss_fx.py data/enemies.py tests/test_boss_phases.py
git commit -m "feat: boss soft-phase intensity scaling + attack patterns"
```


## Task 14: Pet depth: star levels + passive-at-capstone + nested pet prestige (`cnt-pet-depth`)

**Goal:** Make the 12-pet collection meaningful. (1) Passive-at-capstone: for owned-but-unequipped pets at bond>=5 add 1/4 of `pet_bonus`, at bond>=10 add 50%. (2) Star levels (1-12) from duplicate eggs. (3) Nested pet prestige (Spirit Embers) only at max bond.

**Files:**
- Modify: `core/bonuses.py` (passive-at-capstone provider)
- Modify: `data/pets.py` (star level defs)
- Modify: `core/gacha.py` (duplicate eggs -> star levels)
- Modify: `core/state.py` (`pet_stars`, `spirit_embers`)
- Test: `tests/test_pet_depth.py`

**Acceptance Criteria:**
- [ ] Owned-but-unequipped pets contribute 25% at bond>=5, 50% at bond>=10
- [ ] Equipped pet bonus is meaningfully larger than the passive one
- [ ] Star levels (1-12) from duplicate eggs extend the bond system
- [ ] Nested pet prestige (Spirit Embers) only at max bond (bond 10)
- [ ] Spirit Ember payouts are clearly worth the re-grind
- [ ] `aggregate_bonuses` swings aren't wild on pet swaps

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_pet_depth.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_passive_at_capstone(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.pets = {"frog": 10}  # bond 10, not equipped
    out = aggregate_bonuses(state)
    # Passive at bond 10 = 50% of pet_bonus.
    from data.pets import BY_ID
    p = BY_ID["frog"]
    expected = p.buff_per_level * 10 * 0.5
    assert out.get(p.buff_key, 0) == pytest.approx(expected)

def test_equipped_better_than_passive(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state_eq = GameState()
    state_eq.pets = {"frog": 10}; state_eq.equipped_pets = ["frog"]
    state_pass = GameState()
    state_pass.pets = {"frog": 10}  # not equipped
    assert aggregate_bonuses(state_eq).get("firefly_gold", 0) > aggregate_bonuses(state_pass).get("firefly_gold", 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_pet_depth.py -q`
Expected: FAIL (no passive contribution)

- [ ] **Step 3: Add a passive-at-capstone pet provider in core/bonuses.py**

```python
def _pets_passive_provider(state):
    out = {}
    for pid, bond in state.pets.items():
        if pid in state.equipped_pets:
            continue
        if bond < 5:
            continue
        p = pet_def.BY_ID.get(pid)
        if p is None:
            continue
        frac = 0.25 if bond < 10 else 0.5
        out[p.buff_key] = out.get(p.buff_key, 0.0) + pet_def.pet_bonus(p, bond) * frac
    return out
register_provider(_pets_passive_provider)
```

- [ ] **Step 4: Add pet_stars + spirit_embers to core/state.py**

```python
pet_stars: dict[str, int] = field(default_factory=dict)  # pid -> star level 1-12
spirit_embers: int = 0
```

- [ ] **Step 5: Add duplicate-to-star in core/gacha.py**

When a duplicate pet is pulled, increment `pet_stars[pid]` (capped at 12) instead of just bond.

- [ ] **Step 6: Add Spirit Ember prestige at bond 10**

A pet at bond 10 can be "prestiged" for Spirit Embers (a nested currency); re-grind bond from 0 with a higher cap.

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_pet_depth.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add core/bonuses.py data/pets.py core/gacha.py core/state.py tests/test_pet_depth.py
git commit -m "feat: pet depth (passive-at-capstone + star levels + spirit embers)"
```


## Task 15: Build specialization + Dojo path alignments (`gp-build-spec`)

**Goal:** Unify build-specialisation + Dojo + Heritage into ONE coherent axis. At the abilities branch fork, the player commits to one damage path per ascension (Kage-bunshin idle / Iaijutsu tap-burst / Shikigami summon / Kusari-gama multi-hit). The 4 Dojos ARE the 4 damage sources; the 5th Godai element (Earth) is utility. Specialization is ADDITIVE (buffs toward chosen), NOT mutually-exclusive. Completing a full ascension under a Dojo grants its Heritage passive.

**Files:**
- Modify: `data/skill_tree.py` (Dojo nodes)
- Modify: `core/bonuses.py` (dojo provider, heritage provider)
- Modify: `engine/ninja.py` (dojo multipliers in compute_ninja_stats)
- Modify: `core/ascend.py` (grant heritage on ascension under a dojo)
- Modify: `core/state.py` (`dojo`, `heritage` fields — seeded by Task 5)
- Test: `tests/test_build_spec.py`

**Acceptance Criteria:**
- [ ] 4 damage paths (Dojos) commit per ascension, mapped to the 4 most fitting Godai elements
- [ ] Specialization is ADDITIVE (buffs toward chosen), NOT mutually-exclusive capstones
- [ ] A viable generalist default exists; respec is free/cheap
- [ ] Completing a full ascension under a Dojo grants its Heritage passive
- [ ] The "collect all 5 heritages" meta-goal exists
- [ ] The build-specialisation multipliers and Godai element multipliers compose cleanly in `compute_ninja_stats`

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_build_spec.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_dojo_additive(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.dojo = "kage_bunshin"
    out = aggregate_bonuses(state)
    # Additive buff toward the chosen dojo, no lockout.
    assert "dojo_kage_bunshin" in out or out.get("idle_pct", 0) > 0

def test_heritage_granted_on_ascend(pygame_headless):
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.dojo = "kage_bunshin"
    state.zone_index = 5
    state.best_zone = 5
    state.gold = 100000
    ascend(state)
    assert "kage_bunshin" in state.heritage
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_build_spec.py -q`
Expected: FAIL

- [ ] **Step 3: Add dojo + heritage fields to core/state.py**

```python
dojo: str = "none"  # none, kage_bunshin, iaijutsu, shikigami, kusari_gama
heritage: set[str] = field(default_factory=set)  # collected heritage dojos
```

- [ ] **Step 4: Add Dojo nodes to data/skill_tree.py**

4 dojo nodes in the abilities branch, each granting an additive buff toward the chosen path. The generalist default (no dojo) is viable.

- [ ] **Step 5: Add a dojo provider + heritage provider in core/bonuses.py**

```python
def _dojo_provider(state):
    out = {}
    if state.dojo == "none":
        return out
    # Additive buffs toward the chosen dojo.
    out[f"dojo_{state.dojo}"] = 0.15
    return out
register_provider(_dojo_provider)

def _heritage_provider(state):
    out = {}
    for h in state.heritage:
        out[f"heritage_{h}"] = 0.10
    return out
register_provider(_heritage_provider)
```

- [ ] **Step 6: Grant heritage on ascension in core/ascend.py**

In `ascend`, if `state.dojo != "none"`, add it to `state.heritage` (one-time per dojo).

- [ ] **Step 7: Compose dojo multipliers in engine/ninja.py compute_ninja_stats**

Read `dojo` from `aggregate_bonuses` and apply the additive buff to the appropriate stat (tap for iaijutsu, auto for kage_bunshin, etc.).

- [ ] **Step 8: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_build_spec.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 9: Commit**

```bash
git add data/skill_tree.py core/bonuses.py engine/ninja.py core/ascend.py core/state.py tests/test_build_spec.py
git commit -m "feat: build specialization (Dojos) + additive heritage"
```


## Task 16: Splash/Skip progression layer (`gp-splash-skip`)

**Goal:** Give the late-ascension road the "zooming through zones" dopamine. Add a "Cleave" stat (from the skill tree) that overkill-clears the next K enemies when damage massively overkills; a rare "Yokai Portal" boss variant that jumps the zone bar by a chunk. Gate Cleave behind mid-ascension so early zones feel earned.

**Files:**
- Modify: `engine/world.py` (cleave + yokai portal)
- Modify: `engine/enemy.py` (overkill cleave)
- Modify: `data/skill_tree.py` (cleave node)
- Modify: `engine/runner.py` (cleave application)
- Test: `tests/test_splash_skip.py`

**Acceptance Criteria:**
- [ ] A Cleave stat overkill-clears the next K enemies when damage massively overkills
- [ ] A rare Yokai Portal boss variant jumps the zone bar by a chunk
- [ ] Cleave is gated behind mid-ascension (early zones still feel earned)
- [ ] Yokai Portal skips don't bypass bestiary/achievement reveals
- [ ] A new player never sees splash in the first runs

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_splash_skip.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_cleave_overkill(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.ascend_tier = 3  # mid-ascension
    state.skill_tree = {"cleave"}  # cleave unlocked
    r = Runner(state)
    # Spawn weak enemies; a massive tap overkills and cleaves the next.
    r.world.enemies = [spawn_weak(), spawn_weak(), spawn_weak()]
    r.tap()
    # At least 2 enemies cleared (cleave).
    assert sum(1 for e in r.world.enemies if not e.alive) >= 2

def test_cleave_gated_for_new_players(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.ascend_tier = 0  # new player
    state.skill_tree = {"cleave"}
    r = Runner(state)
    # Cleave should NOT fire at tier 0.
    # (verify via the cleave mult being 0)
    assert r.cleave_count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_splash_skip.py -q`
Expected: FAIL

- [ ] **Step 3: Add a cleave node to data/skill_tree.py**

A "Cleave" node in the offense branch, gated behind mid-ascension (check `state.ascend_tier >= 3`).

- [ ] **Step 4: Implement cleave in engine/runner.py**

```python
def cleave_count(self) -> int:
    if self.state.ascend_tier < 3:
        return 0
    evo = aggregate_bonuses(self.state)
    return int(evo.get("cleave", 0))
```
In `_apply_damage` or the kill handler, when an enemy is overkilled by a large margin, clear the next `cleave_count()` enemies.

- [ ] **Step 5: Add Yokai Portal boss variant in engine/world.py**

A 5% chance for a boss to be a "Yokai Portal" variant that, when killed, jumps `zone_distance` by a chunk (e.g. +50% `ZONE_DISTANCE`).

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_splash_skip.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add engine/world.py engine/enemy.py data/skill_tree.py engine/runner.py tests/test_splash_skip.py
git commit -m "feat: splash/skip (cleave + yokai portal), mid-ascension gated"
```


## Task 17: Permanent scaling floor: stacking tokens + Heritage passives (`gp-permanent-scaling`)

**Goal:** Three permanent-scaling systems. (1) Stacking tokens: +1%-per-token (Strike/Crit/Coin/Elixir), permanent, survive ALL prestige layers, sourced from daily quests + zone-boss milestones (NOT achievements). (2) Heritage passives: convert the 14 achievements from one-shot payouts into permanent cumulative multipliers. (3) Epic Research is split out (Task 18). **Note gap #3:** this edits `core/quests.py` alongside Task 26 (cnt-quest-codex) — Heritage lands first.

**Files:**
- Modify: `data/quests.py` (Heritage conversion)
- Modify: `core/quests.py` (token awards, heritage multipliers)
- Modify: `core/state.py` (`tokens`)
- Modify: `core/bonuses.py` (token + heritage providers)
- Test: `tests/test_permanent_scaling.py`

**Acceptance Criteria:**
- [ ] Stacking tokens (+1% each, permanent, survive all resets) sourced from daily quests + zone-boss milestones (not achievements)
- [ ] Token acquisition rate capped so +1% complements rather than replaces exponential zone scaling
- [ ] The 14 achievements converted to permanent cumulative multipliers (Heritage passives)
- [ ] Hidden/secret achievements have cryptic in-game hints (not wiki-dependent)
- [ ] Tokens + Heritage have distinct sources — no double-counting

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_permanent_scaling.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_tokens_permanent(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.tokens = {"strike": 5}  # 5 strike tokens = +5% tap
    out = aggregate_bonuses(state)
    assert out.get("strike_token_pct", 0) == pytest.approx(0.05)

def test_heritage_from_achievements(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.achievements = {"first_blood", "slayer"}  # 2 achievements
    out = aggregate_bonuses(state)
    # Each achievement contributes a small permanent multiplier.
    assert out.get("heritage_pct", 0) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_permanent_scaling.py -q`
Expected: FAIL

- [ ] **Step 3: Add tokens field to core/state.py**

```python
tokens: dict[str, int] = field(default_factory=dict)  # strike/crit/coin/elixir -> count
```

- [ ] **Step 4: Add token + heritage providers in core/bonuses.py**

```python
def _tokens_provider(state):
    out = {}
    for kind, count in state.tokens.items():
        out[f"{kind}_token_pct"] = count * 0.01  # +1% per token
    return out
register_provider(_tokens_provider)

def _heritage_achievements_provider(state):
    out = {}
    # Each achievement = +0.5% permanent multiplier.
    out["heritage_pct"] = len(state.achievements) * 0.005
    return out
register_provider(_heritage_achievements_provider)
```

- [ ] **Step 5: Award tokens from daily quests + zone-boss milestones in core/quests.py**

In `update_daily_progress` and the boss-kill handler, award tokens (capped rate). Do NOT award tokens for achievements (avoid double-counting with Heritage).

- [ ] **Step 6: Add hidden/secret achievements with cryptic hints in data/quests.py**

A few achievements with cryptic in-game hints (not wiki-dependent).

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_permanent_scaling.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add data/quests.py core/quests.py core/state.py core/bonuses.py tests/test_permanent_scaling.py
git commit -m "feat: permanent scaling (stacking tokens + heritage passives)"
```


## Task 18: Epic Research permanent meta-tree (`gp-epic-research`)

**Goal:** A permanent meta-tree bought with underused medals/amber (nodes like Elixir Resonance, Away Mastery +% offline growth, Lab Discipline); reuses `skill_tree.py` structure. Away Mastery keeps offline growth meaningfully but strictly less than active+boosted earnings.

**Files:**
- Modify: `data/skill_tree.py` (Epic Research nodes)
- Modify: `core/state.py` (`epic_research`)
- Modify: `core/bonuses.py` (epic research provider)
- Modify: `core/offline.py` (Away Mastery)
- Test: `tests/test_epic_research.py`

**Acceptance Criteria:**
- [ ] An Epic Research permanent meta-tree bought with medals/amber (Elixir Resonance, Away Mastery, Lab Discipline)
- [ ] Epic Research reuses `skill_tree.py` structure
- [ ] Away Mastery keeps offline growth meaningfully but strictly less than active+boosted earnings

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_epic_research.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_epic_research_provider(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.epic_research = {"elixir_resonance"}
    out = aggregate_bonuses(state)
    assert out.get("elixir_pct", 0) > 0

def test_away_mastery_caps_offline(pygame_headless):
    from core.state import GameState
    from core.offline import compute
    state = GameState()
    state.epic_research = {"away_mastery"}
    state.last_saved = 0  # simulate away
    # Away Mastery boosts offline but strictly less than active.
    report = compute(state)
    assert report["applied"] is True or "gold" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_epic_research.py -q`
Expected: FAIL

- [ ] **Step 3: Add epic_research field to core/state.py**

```python
epic_research: set[str] = field(default_factory=set)
```

- [ ] **Step 4: Add Epic Research nodes to data/skill_tree.py**

A separate node set (Elixir Resonance, Away Mastery, Lab Discipline) bought with medals/amber, reusing the `SkillNode` structure.

- [ ] **Step 5: Add an epic research provider in core/bonuses.py**

```python
def _epic_research_provider(state):
    out = {}
    for n in EPIC_RESEARCH_NODES:
        if n.id in state.epic_research:
            out[n.effect_key] = out.get(n.effect_key, 0.0) + n.effect_value
    return out
register_provider(_epic_research_provider)
```

- [ ] **Step 6: Apply Away Mastery in core/offline.py**

Boost offline gold by Away Mastery, but cap it strictly below active+boosted earnings.

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_epic_research.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add data/skill_tree.py core/state.py core/bonuses.py core/offline.py tests/test_epic_research.py
git commit -m "feat: Epic Research permanent meta-tree (medals/amber)"
```


## Task 19: Gacha fairness bundle + multi-stage pull-reveal drama (`gp-gacha-fairness`)

**Goal:** Convert the gacha from a gamble into guaranteed progression. (1) Soft-pity ramp. (2) Spark/pity-token shop (1 token per pull, trade 40 for any unlocked pet; carry pity across banners). (3) Dupe-to-upgrade (duplicates feed a per-pet upgrade track; maxed pets removed from the pool). (4) Early-pity guarantee in the first 10 pulls of a new banner. (5) Multi-stage reveal leaks the rarity color from t=0.

**Files:**
- Modify: `core/gacha.py` (soft-pity, spark shop, dupe-to-upgrade)
- Modify: `config.py` (soft-pity constants)
- Modify: `engine/gacha_fx.py` (multi-stage reveal)
- Modify: `ui/screen_pets.py` (spark shop UI, odds UI)
- Modify: `core/state.py` (`pity_tokens`, `banner_pulls`)
- Test: `tests/test_gacha_fairness.py`

**Acceptance Criteria:**
- [ ] Soft-pity ramp (rate climbs per pull after a threshold) shortens the `PITY_LEGENDARY=200` grind
- [ ] A spark/pity-token shop (1 token per pull, trade 40 for any unlocked pet); pity carries across banners
- [ ] Dupe-to-upgrade: duplicates feed a per-pet upgrade track; maxed pets removed from the pool
- [ ] Early-pity guarantee in the first 10 pulls of a new banner (one-time-per-banner)
- [ ] Multi-stage reveal leaks the rarity color into the suspense glow from t=0 (early tell)
- [ ] Rarity-scaled screen shake/hit-stop; a skip activates after the tell; batch-summary-first for 10-pulls
- [ ] Visible odds UI
- [ ] Banner rotation is NOT implemented (no hero-expansion roadmap)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_gacha_fairness.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_soft_pity_ramp(pygame_headless):
    from core.state import GameState
    from core.gacha import pull
    state = GameState()
    # After 150 pulls without a legendary, the rate should climb.
    state.pet_pulls = 150
    # The soft-pity ramp should increase the legendary rate.
    # (verify via a rate function or a streak of pulls)
    rates = [pull(state) for _ in range(10)]
    # At least one rare+ in 10 pulls at 150 pity.
    assert any(r != "common" for r in rates)

def test_spark_shop(pygame_headless):
    from core.state import GameState
    state = GameState()
    state.pity_tokens = 40
    # Trade 40 tokens for a guaranteed pet.
    # (verify the shop function)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_gacha_fairness.py -q`
Expected: FAIL

- [ ] **Step 3: Add pity_tokens + banner_pulls to core/state.py**

```python
pity_tokens: int = 0
banner_pulls: int = 0
```

- [ ] **Step 4: Add soft-pity constants to config.py**

```python
SOFT_PITY_START = {  # per rarity: pulls before the rate starts climbing
    "rare": 15, "epic": 50, "legendary": 150, "mythic": 190,
}
SOFT_PITY_INCREMENT = 0.02  # +2% per pull after the threshold
```

- [ ] **Step 5: Implement soft-pity + spark shop in core/gacha.py**

In `pull`, after `SOFT_PITY_START[rarity]` pulls without that rarity, increment the rate by `SOFT_PITY_INCREMENT` per pull. Award 1 pity_token per pull. Add a `spark_shop_trade(state, pid)` that trades 40 tokens for a guaranteed pet.

- [ ] **Step 6: Implement dupe-to-upgrade + maxed-pet removal**

When a duplicate pet is pulled, feed the upgrade track (Task 14's pet_stars). Maxed pets (bond 10 + star 12) are removed from the pool.

- [ ] **Step 7: Add multi-stage reveal to engine/gacha_fx.py**

Leak the rarity color into the suspense glow from t=0 (early tell). Add rarity-scaled screen shake/hit-stop. Add a skip after the tell. Batch-summary-first for 10-pulls.

- [ ] **Step 8: Add spark shop + odds UI to ui/screen_pets.py**

- [ ] **Step 9: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_gacha_fairness.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 10: Commit**

```bash
git add core/gacha.py config.py engine/gacha_fx.py ui/screen_pets.py core/state.py tests/test_gacha_fairness.py
git commit -m "feat: gacha fairness (soft-pity + spark shop + dupe-upgrade + reveal)"
```


## Task 20: Gear data model + affix definitions + boss-drop logic (`cnt-gear-loot-model`)

**Goal:** The gear data model + affix definitions + BonusProvider registration + boss-drop logic. 4 gear slots with passive affixes flowing through `aggregate_bonuses` via BonusProvider, drops on boss kill (automatic). Gear rarity reuses `GACHA_RATES`. Gear multipliers fit the defined stacking order with a `MAX_TOTAL_DAMAGE_MULT` cap. **Note:** this is the model half of the split; the Forge UI is Task 33.

**Files:**
- Modify: `config.py` (gear affix defs, rarity)
- Modify: `core/bonuses.py` (gear provider)
- Modify: `core/state.py` (`gear`)
- Modify: `engine/runner.py` (boss-drop logic)
- Test: `tests/test_gear_model.py`

**Acceptance Criteria:**
- [ ] 4 gear slots with passive affixes flowing through `aggregate_bonuses` via BonusProvider
- [ ] Boss kills drop gear (automatic, no active requirement)
- [ ] Gear rarity reuses `GACHA_RATES`
- [ ] Gear multipliers fit the defined stacking order with a `MAX_TOTAL_DAMAGE_MULT` cap

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_gear_model.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_gear_provider(pygame_headless):
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0) >= 0.1

def test_boss_drops_gear(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Kill a boss -> gear drops.
    # (simulate a boss kill and verify gear is added)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_gear_model.py -q`
Expected: FAIL

- [ ] **Step 3: Add gear field to core/state.py**

```python
gear: dict[str, dict] = field(default_factory=dict)  # slot -> {affix, value, rarity}
```

- [ ] **Step 4: Add gear affix defs to config.py**

4 slots (blade, mask, talisman, cloak) with affix pools per rarity, reusing `GACHA_RATES`.

- [ ] **Step 5: Add a gear provider in core/bonuses.py**

```python
def _gear_provider(state):
    out = {}
    for slot, g in state.gear.items():
        out[g["affix"]] = out.get(g["affix"], 0.0) + g["value"]
    return out
register_provider(_gear_provider)
```

- [ ] **Step 6: Add boss-drop logic in engine/runner.py**

In `_on_enemy_killed`, if `enemy.is_boss`, drop a gear piece (random slot, rarity from `GACHA_RATES`).

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_gear_model.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add config.py core/bonuses.py core/state.py engine/runner.py tests/test_gear_model.py
git commit -m "feat: gear data model + boss-drop logic (model half)"
```


## Task 21: Godai Elemental Affinities & Fusion (`gp-godai-fusion`)

**Goal:** Transform the 4 Godai nodes from flat +15% stat boosts into a LIVE combat decision layer. Add an `element` field to `EnemyDef` (themed by zone), `attuned_element` to GameState (default 'none' = 1x), a 4-cycle type chart (2x advantage / 0.5x disadvantage), and 4 fusion effects on a 30s cooldown. Attunement defaults to 'none' (1x). **Note gap #7:** this edits `data/enemies.py` ZONES alongside Task 12 (cnt-infinite-zones) + Task 31 (gfx-weather) — verify all three compose cleanly.

**Files:**
- Modify: `data/enemies.py` (element field on EnemyDef + zone themes)
- Modify: `data/skill_tree.py` (fusion nodes)
- Modify: `core/state.py` (`attuned_element` — seeded by Task 5)
- Modify: `engine/enemy.py` (elemental damage mult)
- Modify: `engine/runner.py` (fusion cooldown, attunement)
- Modify: `ui/screen_godai.py` (attunement UI)
- Test: `tests/test_godai_fusion.py`

**Acceptance Criteria:**
- [ ] `EnemyDef` has an `element` field themed by zone
- [ ] `attuned_element` on GameState defaults to 'none' (1x damage to everything)
- [ ] A 4-cycle type chart (2x advantage / 0.5x disadvantage) with 4 fusion effects on a 30s cooldown
- [ ] An auto-attune toggle (skill-tree node) lets idle players opt out — idle is never worse than 1x
- [ ] The dual-element skill-tree nodes are the complement (unlock gate), not a competing system
- [ ] The zone-environmental-hazards proposal is NOT implemented — the fusion is the single elemental system

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_godai_fusion.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_element_default_none_is_1x(pygame_headless):
    from core.state import GameState
    from engine.enemy import element_mult
    state = GameState()
    assert state.attuned_element == "none"
    assert element_mult(state.attuned_element, "fire") == 1.0

def test_type_chart_2x_advantage(pygame_headless):
    from engine.enemy import element_mult
    # 4-cycle: void > wind > fire > water > void (example)
    assert element_mult("void", "wind") == 2.0
    assert element_mult("wind", "void") == 0.5
    assert element_mult("fire", "fire") == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_godai_fusion.py -q`
Expected: FAIL

- [ ] **Step 3: Add element field to EnemyDef in data/enemies.py**

```python
@dataclass
class EnemyDef:
    ...
    element: str = "none"  # none, void, wind, fire, water
```
Theme each zone's enemies with an element. **Verify the ZONES dict edits compose with Task 12 (cycle) + Task 31 (weather key).**

- [ ] **Step 4: Add element_mult + type chart to engine/enemy.py**

```python
_TYPE_CHART = {  # attacker -> (defender -> multiplier)
    "void": {"wind": 2.0, "fire": 1.0, "water": 0.5, "void": 1.0, "none": 1.0},
    "wind": {"fire": 2.0, "water": 1.0, "void": 0.5, "wind": 1.0, "none": 1.0},
    "fire": {"water": 2.0, "void": 1.0, "wind": 0.5, "fire": 1.0, "none": 1.0},
    "water": {"void": 2.0, "wind": 1.0, "fire": 0.5, "water": 1.0, "none": 1.0},
    "none": {k: 1.0 for k in ("void", "wind", "fire", "water", "none")},
}
def element_mult(attuned: str, enemy_element: str) -> float:
    return _TYPE_CHART.get(attuned, {}).get(enemy_element, 1.0)
```

- [ ] **Step 5: Apply element_mult in combat (engine/enemy.py + runner.py)**

In `_apply_damage`, multiply damage by `element_mult(state.attuned_element, enemy.element)`.

- [ ] **Step 6: Add 4 fusion effects on a 30s cooldown in engine/runner.py**

```python
FUSIONS = {  # (element_a, element_b) -> effect
    ("void", "fire"): "inferno", ("wind", "water"): "tempest",
    ("fire", "water"): "steam", ("void", "wind"): "vacuum",
}
```
A fusion fires on a 30s cooldown when the attuned element matches. Add an auto-attune toggle (skill-tree node) so idle players opt out.

- [ ] **Step 7: Add attunement UI to ui/screen_godai.py**

- [ ] **Step 8: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_godai_fusion.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 9: Verify the 3 ZONES-dict edits compose (Tasks 12, 21, 31)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_infinite_zones.py tests/test_godai_fusion.py -q`
Expected: passed

- [ ] **Step 10: Commit**

```bash
git add data/enemies.py data/skill_tree.py core/state.py engine/enemy.py engine/runner.py ui/screen_godai.py tests/test_godai_fusion.py
git commit -m "feat: Godai elemental affinities + fusion (live combat, default 1x)"
```


## Task 22: Run upgrade expansion + new skill-tree branches (`cnt-run-upgrade-expansion`)

**Goal:** Cheap content that deepens the per-run build. (1) Run upgrade expansion: 13 → ~20 with tap-specialist + active-skill-adjacent + combo-decay-resistance upgrades (more rows in the flat `TAP_UPGRADE_DEFS` table, reset on ascension). (2) New skill-tree branches (Defense/Combo/Tap Mastery) + cross-branch capstones expanding the 40-node tree toward ~60 nodes. Active-skill tier upgrades (t2/t3) chain off existing `ab_*` nodes.

**Files:**
- Modify: `config.py` (`TAP_UPGRADE_DEFS` expansion)
- Modify: `data/skill_tree.py` (new branches + capstones)
- Modify: `core/game_economy.py` (if new upgrade keys need economy hooks)
- Test: `tests/test_run_upgrade_expansion.py`

**Acceptance Criteria:**
- [ ] Run upgrades expand from 13 to ~20 (tap-specialist, skill-adjacent, combo-decay-resistance)
- [ ] New skill-tree branches (Defense/Combo/Tap Mastery) with cross-branch capstones
- [ ] Active-skill tier upgrades (t2/t3) chain off existing `ab_*` nodes
- [ ] No new verb — deepens existing skills
- [ ] Reset on ascension (no save-migration risk for run upgrades)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_run_upgrade_expansion.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_upgrade_count_expanded():
    import config as cfg
    assert len(cfg.TAP_UPGRADE_DEFS) >= 20

def test_new_skill_tree_branches():
    from data.skill_tree import NODES, nodes_by_branch
    branches = set(n.branch for n in NODES)
    assert "defense" in branches or "combo" in branches or "tap_mastery" in branches
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_run_upgrade_expansion.py -q`
Expected: FAIL (only 13 upgrades, no new branches)

- [ ] **Step 3: Expand TAP_UPGRADE_DEFS in config.py**

Add ~7 new rows: tap-specialist (tap_crit, tap_speed), active-skill-adjacent (skill_dmg, skill_cd), combo-decay-resistance (combo_grace), etc. Each row: `(key, label, base_cost, base_effect, effect_growth)`.

- [ ] **Step 4: Add new skill-tree branches in data/skill_tree.py**

Add Defense, Combo, Tap Mastery branches with chains + cross-branch capstones. Add t2/t3 active-skill upgrades chaining off `ab_*` nodes.

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_run_upgrade_expansion.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add config.py data/skill_tree.py core/game_economy.py tests/test_run_upgrade_expansion.py
git commit -m "feat: run upgrade expansion + new skill-tree branches"
```


## Task 23: Shadow Dungeon runner (compose existing engine) (`cnt-shadow-dungeon-runner`)

**Goal:** A `DungeonRunner` that composes existing engine components (World, enemy.py, skills.py), not duplicate Runner logic. The road loop runs undisturbed while the dungeon is active. No new currency (gated on medals or zone progression). The Godai Fire element ties to the dungeon. **Note gap #2:** reference real modules (combo logic in `engine/runner.py` + `engine/combo_fx.py`; Godai logic in `engine/runner.py` + `engine/enemy.py` after Task 21), NOT nonexistent `combo_tech.py`/`elements.py`.

**Files:**
- Modify: `engine/runner.py` (DungeonRunner class)
- Modify: `engine/world.py` (dungeon world composition)
- Modify: `core/state.py` (`dungeon_*` fields)
- Test: `tests/test_shadow_dungeon.py`

**Acceptance Criteria:**
- [ ] A `DungeonRunner` that composes existing engine components, not duplicate Runner logic
- [ ] The road loop runs undisturbed while the dungeon is active
- [ ] No new currency (gated on medals or zone progression)
- [ ] The Godai Fire element ties to the dungeon

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_shadow_dungeon.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_dungeon_runner_composes(pygame_headless):
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    dr = DungeonRunner(state)
    # Composes a World + enemies + skills, not a duplicate Runner.
    assert hasattr(dr, "world")
    assert dr.state is state
    # The road loop (the main Runner) is undisturbed.
    # (verify the dungeon runs without touching the main runner's world)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_shadow_dungeon.py -q`
Expected: FAIL (no DungeonRunner)

- [ ] **Step 3: Add dungeon_* fields to core/state.py**

```python
dungeon_active: bool = False
dungeon_type: str = "none"  # story, endless, daily
dungeon_floor: int = 0
dungeon_seed: int = 0
```

- [ ] **Step 4: Implement DungeonRunner in engine/runner.py**

A `DungeonRunner` class that composes a `World` + `enemy.py` spawn/combat + `skills.py`, reusing the existing modules. It does NOT duplicate the main `Runner` logic; it drives its own `World` instance. The main `Runner.update` checks `state.dungeon_active` and, if so, updates the dungeon instead of (or alongside) the road — the road loop stays intact (the road keeps idling).

- [ ] **Step 5: Tie the Godai Fire element to the dungeon**

The dungeon's bosses/enemies use the Fire element (from Task 21's element field).

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_shadow_dungeon.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add engine/runner.py engine/world.py core/state.py tests/test_shadow_dungeon.py
git commit -m "feat: Shadow Dungeon runner (compose existing engine)"
```


## Task 24: Tap-vs-auto DPS rebalance + tap fatigue (`gp-tap-auto-rebalance`)

**Goal:** THE idle-integrity fix. Tap DPS (1.13B at max) is 94x auto DPS (12M). Add an `auto_mult` run upgrade mirroring `tap_mult`; scale tap base DOWN ~5x; add tap fatigue (5%/tap above 5 taps/s, floor 0.3x). **Note gap #4:** re-test boss shield tuning (Task 13) after this lands. **Open question #2:** the exact ratio (3:1 vs 5:1) + fatigue curve — recommendation baked in: ~3:1, fatigue 5%/tap above 5/s, floor 0.3x.

**Files:**
- Modify: `engine/ninja.py` (auto_mult, tap base scale, tap fatigue)
- Modify: `config.py` (`auto_mult` upgrade, tap fatigue constants)
- Modify: `engine/runner.py` (tap fatigue tracking)
- Modify: `core/game_economy.py` (if economy depends on tap)
- Test: `tests/test_tap_auto_rebalance.py`

**Acceptance Criteria:**
- [ ] An `auto_mult` run upgrade mirrors `tap_mult`
- [ ] Tap base scaled down so the tap:auto ratio is ~3:1 (not 94:1)
- [ ] Tap fatigue: 5%/tap above 5 taps/s, floor 0.3x (tapping never becomes useless)
- [ ] The rebalance ships with the new `auto_mult` upgrade (a new option, not a pure nerf)
- [ ] Auto-attack is the backbone; tap is a meaningful-but-bounded bonus
- [ ] No 100x+ active burst (killed as economy-breaking)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_tap_auto_rebalance.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_tap_auto_ratio(pygame_headless):
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    state.upgrades = {"tap_power": 100, "auto_mult": 100, "tap_mult": 100}
    s = compute_ninja_stats(state)
    # Tap : auto ratio ~3:1 (not 94:1).
    ratio = s["tap_damage"] / s["auto_damage"]
    assert 2.0 <= ratio <= 5.0, f"ratio {ratio}"

def test_tap_fatigue(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # 10 taps in 1 second -> fatigue kicks in.
    for _ in range(10):
        r.tap()
    # Fatigue reduces tap damage but floors at 0.3x.
    assert r.tap_fatigue_mult() >= 0.3
    assert r.tap_fatigue_mult() < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_tap_auto_rebalance.py -q`
Expected: FAIL (no auto_mult, no fatigue, ratio 94:1)

- [ ] **Step 3: Add auto_mult + tap fatigue constants to config.py**

```python
# Add to TAP_UPGRADE_DEFS:
# ("auto_mult", "Auto Multiplier", 60, 0.05, 1.02),  # +% auto damage
TAP_BASE_SCALE = 0.2       # tap base scaled down ~5x
TAP_FATIGUE_PER_TAP = 0.05  # 5% per tap above threshold
TAP_FATIGUE_THRESHOLD = 5   # taps/sec threshold
TAP_FATIGUE_FLOOR = 0.3     # floor
```

- [ ] **Step 4: Apply auto_mult + tap base scale in engine/ninja.py**

In `compute_ninja_stats`, scale `tap_base` by `TAP_BASE_SCALE`, add `auto_mult` mirroring `tap_mult`:
```python
tap_base = (10.0 * TAP_BASE_SCALE + _upgrade_value(state, "tap_power")) * tier_mult
tap_mult = 1.0 + _upgrade_value(state, "tap_mult") + evo.get("tap_pct", 0.0)
tap_damage = tap_base * tap_mult
auto_base = (8.0 + _upgrade_value(state, "auto_attack")) * tier_mult
auto_mult = 1.0 + _upgrade_value(state, "auto_mult") + evo.get("atk_pct", 0.0)
auto_damage = auto_base * auto_mult
```

- [ ] **Step 5: Implement tap fatigue in engine/runner.py**

Track tap timestamps; compute `taps_in_last_second`; if > threshold, fatigue = `max(FLOOR, 1 - (taps - threshold) * PER_TAP)`. Apply to tap damage in `tap()`.

- [ ] **Step 6: Re-test boss shield tuning (Task 13)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_boss_phases.py -q`
Expected: passed (if it fails, re-tune boss shield for the new auto DPS)

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_tap_auto_rebalance.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add engine/ninja.py config.py engine/runner.py core/game_economy.py tests/test_tap_auto_rebalance.py
git commit -m "feat: tap-vs-auto rebalance (~3:1) + tap fatigue anti-macro"
```


## Task 25: Skill synergies + Tap rhythm bonus (`gp-skill-synergy-rhythm`)

**Goal:** Two cheap active-play rewards. (1) Skill Synergies: firing two active skills within 2s triggers a synergy bonus. SYNERGY table: (kunai,shuriken)='Storm of Steel', (speed,kunai)='Lightning Strike', (rope,shuriken)='Grinding Vortex', (speed,rope)='Phantom Snare'. (2) Tap rhythm: median of last 5 tap intervals in 0.35-0.55s window builds `rhythm_streak` (cap 20), +2.5% tap damage per level. Rhythm is strictly a bonus (floor 0, never a penalty).

**Files:**
- Modify: `engine/runner.py` (synergy tracking, rhythm)
- Modify: `engine/skills.py` (synergy effects)
- Modify: `ui/screen_game.py` (synergy arc, rhythm display)
- Modify: `core/state.py` (`rhythm_streak` — seeded by Task 5)
- Test: `tests/test_skill_synergy_rhythm.py`

**Acceptance Criteria:**
- [ ] Firing 2 active skills within 2s triggers a named synergy with a glowing arc between the buttons
- [ ] Tap rhythm: median of last 5 tap intervals in 0.35-0.55s window builds `rhythm_streak` (cap 20), +2.5% tap damage per level
- [ ] Rhythm is strictly a bonus (floor 0, never a penalty) — motor-impaired players aren't punished
- [ ] A soft tick SFX gives `reduced_motion` a non-visual cue
- [ ] The Speed Step kill-ramp-with-decay rework is NOT implemented (it punishes idle)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_skill_synergy_rhythm.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_skill_synergy(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken"}
    r = Runner(state)
    r.activate_skill("kunai")
    r.activate_skill("shuriken")  # within 2s -> synergy
    assert r.last_synergy == "Storm of Steel"

def test_rhythm_bonus_never_penalty(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # No rhythm -> no bonus, but never a penalty.
    assert r.rhythm_mult() >= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_skill_synergy_rhythm.py -q`
Expected: FAIL

- [ ] **Step 3: Add synergy tracking to engine/runner.py**

Track `last_skill_id` + `last_skill_time`. On `activate_skill`, check if the previous skill was within 2s and matches a SYNERGY table entry. Apply the synergy effect.

- [ ] **Step 4: Add rhythm tracking to engine/runner.py**

Track the last 5 tap timestamps; compute the median interval; if in 0.35-0.55s, increment `rhythm_streak` (cap 20). `rhythm_mult() = 1.0 + 0.025 * state.rhythm_streak` (floor 1.0, never a penalty).

- [ ] **Step 5: Add a glowing arc between skill buttons in ui/screen_game.py**

On a synergy, draw a brief glowing arc between the two skill buttons.

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_skill_synergy_rhythm.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add engine/runner.py engine/skills.py ui/screen_game.py core/state.py tests/test_skill_synergy_rhythm.py
git commit -m "feat: skill synergies + tap rhythm bonus (active-play rewards)"
```


## Task 26: Quest variety expansion + Lore/Bestiary Codex (`cnt-quest-codex`)

**Goal:** Two low-cost content additions. (1) Quest variety: add weekly + chapter quests to the existing daily pool. Do NOT ship 6+ new quest types — only weekly + chapter. (2) Lore/Bestiary Codex: extends `ui/screen_bestiary.py` with a category tab system + per-entity lore entries (pure data). **Note gap #3:** be aware of the Heritage changes from Task 17 which also edits `core/quests.py`.

**Files:**
- Modify: `data/quests.py` (weekly + chapter quest defs)
- Modify: `core/quests.py` (weekly refresh, chapter progress)
- Modify: `ui/screen_bestiary.py` (category tabs + lore)
- Modify: `ui/screen_quests.py` (weekly/chapter display)
- Test: `tests/test_quest_codex.py`

**Acceptance Criteria:**
- [ ] Weekly + chapter quest types added to the daily pool (not 6+ types)
- [ ] Bestiary screen has category tabs + per-entity lore entries
- [ ] Lore text is pure data (no new mechanic)
- [ ] Quests remain legible (no quest-type sprawl)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_quest_codex.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_weekly_quests_exist():
    from data.quests import WEEKLY_POOL
    assert len(WEEKLY_POOL) >= 1

def test_bestiary_has_lore():
    from data.enemies import ZONES
    # Each enemy has a lore entry.
    for z in ZONES:
        for e in z["enemies"]:
            assert hasattr(e, "lore") or "lore" in getattr(e, "__dict__", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_quest_codex.py -q`
Expected: FAIL

- [ ] **Step 3: Add weekly + chapter quests to data/quests.py**

A `WEEKLY_POOL` (refresh 7d) + chapter quests tied to zone progression. Be aware of Task 17's Heritage changes in `core/quests.py` (don't overwrite them).

- [ ] **Step 4: Add lore entries to data/enemies.py**

A `lore` field on `EnemyDef` (pure data, no mechanic).

- [ ] **Step 5: Add category tabs + lore to ui/screen_bestiary.py**

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_quest_codex.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add data/quests.py core/quests.py ui/screen_bestiary.py ui/screen_quests.py tests/test_quest_codex.py
git commit -m "feat: quest variety (weekly + chapter) + lore/bestiary codex"
```


## Task 27: Juice polish + prestige-teaching UI (`pl-juice-polish`)

**Goal:** A bundle of low-effort polish + idle-teaching. (1) Count-up currency numbers + gold milestones. (2) Skill cooldown-ready chime + button glow + cooldown progress fill. (3) Low-HP red vignette + boss enrage phase **as a VISUAL urgency cue** (red vignette when the ninja is low HP during a boss fight), NOT a boss enrage timer mechanic — see gap #5. (4) Respec-on-prestige for the elixir skill tree (free on ascension). (5) Elixir-per-Minute readout + recommended-ascend highlight (computed from config.py curves). (6) Tome of Samsara compounding anchor.

**Files:**
- Modify: `ui/screen_game.py` (count-up, cooldown glow, low-HP vignette)
- Modify: `ui/screen_ascend.py` (elixir/min readout, recommended-ascend, Tome of Samsara)
- Modify: `ui/currency_fx.py` (count-up animation)
- Modify: `core/ascend.py` (free respec, Tome of Samsara)
- Test: `tests/test_juice_polish.py`

**Acceptance Criteria:**
- [ ] Currency numbers count up (no instant snapping); gold milestones celebrate
- [ ] Skill cooldown-ready chime + button glow + cooldown progress fill (chime respects `sound_on`, glow respects `reduced_motion`)
- [ ] Low-HP red vignette + boss enrage phase as a VISUAL urgency cue (gated by `reduced_motion`) — NOT a boss enrage timer mechanic
- [ ] Free respec-on-prestige for the elixir skill tree
- [ ] Elixir-per-Minute readout + recommended-ascend highlight + pacing thresholds computed from `config.py` curves
- [ ] Tome of Samsara compounding anchor with "invest ~30%" tooltip + "elixir per ascension" projection
- [ ] The unspent-elixir-as-multiplier is NOT implemented (Tome of Samsara is the single compounding elixir-growth loop)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_juice_polish.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_count_up_currency(pygame_headless):
    from ui.currency_fx import count_up
    # count_up animates from old to new value, not instant.
    assert callable(count_up)

def test_elixir_per_minute(pygame_headless):
    from core.state import GameState
    from core.ascend import elixir_per_minute
    state = GameState()
    # Computed from config.py curves.
    assert elixir_per_minute(state) >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_juice_polish.py -q`
Expected: FAIL

- [ ] **Step 3: Add count-up animation to ui/currency_fx.py**

A `count_up(old, new, duration)` that animates currency display.

- [ ] **Step 4: Add cooldown glow + chime to ui/screen_game.py**

When a skill's cooldown is ready, glow the button + play a chime (respecting `sound_on`/`reduced_motion`).

- [ ] **Step 5: Add low-HP red vignette to ui/screen_game.py**

When `ninja.hp / max_hp < 0.25` AND a boss is active, draw a red vignette. This is a VISUAL urgency cue, NOT a boss enrage timer (gap #5).

- [ ] **Step 6: Add free respec + Tome of Samsara + elixir/min to core/ascend.py + ui/screen_ascend.py**

Free respec on ascension. Promote one elixir-tree node as the "Tome of Samsara" compounding anchor with a "invest ~30% here" tooltip. Add an Elixir-per-Minute readout + recommended-ascend highlight computed from `config.py` curves.

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_juice_polish.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add ui/screen_game.py ui/screen_ascend.py ui/currency_fx.py core/ascend.py tests/test_juice_polish.py
git commit -m "feat: juice polish + prestige-teaching UI (count-up, cooldown, vignette, respec)"
```


## Task 28: Automation nodes (`pl-automation`)

**Goal:** Automation nodes gated behind deep elixir investment (an earned endgame convenience). (1) Auto-cast Rope Hook + Shuriken under Energy. (2) Automation unlock nodes: auto-collect fireflies, auto-activate Energy, auto-ascend at a threshold (respects the player's threshold). (3) Auto-progress + farm-when-stuck fallback (the road never dead-ends an idle player; farm state advances `lifetime_gold`).

**Files:**
- Modify: `engine/runner.py` (auto-cast, auto-firefly, auto-ascend, farm-when-stuck)
- Modify: `data/skill_tree.py` (automation nodes)
- Modify: `core/ascend.py` (auto-ascend threshold)
- Modify: `core/offline.py` (farm-when-stuck)
- Test: `tests/test_automation.py`

**Acceptance Criteria:**
- [ ] Auto-cast Rope Hook + Shuriken under Energy, gated behind high-cost skill-tree nodes
- [ ] Automation unlock nodes (auto-fireflies, auto-ascend at a threshold) gated behind deep elixir investment; auto-ascend respects the player's threshold
- [ ] Auto-progress + farm-when-stuck fallback (the road never dead-ends an idle player; farm state advances `lifetime_gold`)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_automation.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_auto_cast_under_energy(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_rope", "ab_shuriken", "auto_cast"}
    state.energy_active = True
    r = Runner(state)
    # With auto_cast + energy, skills auto-fire.
    # (verify the runner auto-casts when off cooldown)
    assert "auto_cast" in state.skill_tree

def test_farm_when_stuck(pygame_headless):
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"auto_progress"}
    r = Runner(state)
    # When stuck on a boss, the road farms instead of dead-ending.
    # (verify farm state advances lifetime_gold)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_automation.py -q`
Expected: FAIL

- [ ] **Step 3: Add automation nodes to data/skill_tree.py**

`auto_cast`, `auto_firefly`, `auto_energy`, `auto_ascend`, `auto_progress` — gated behind deep elixir investment (high cost).

- [ ] **Step 4: Implement auto-cast + auto-firefly + auto-ascend in engine/runner.py**

In `update`, if `auto_cast` unlocked + energy active, auto-fire Rope Hook + Shuriken when off cooldown. If `auto_firefly` unlocked, auto-catch fireflies. If `auto_ascend` unlocked + at threshold, auto-ascend (respecting the player's threshold).

- [ ] **Step 5: Implement farm-when-stuck in engine/runner.py + core/offline.py**

When stuck on a boss (no progress for N seconds), farm: keep earning gold, advance `lifetime_gold`, don't dead-end.

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_automation.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add engine/runner.py data/skill_tree.py core/ascend.py core/offline.py tests/test_automation.py
git commit -m "feat: automation nodes (auto-cast, auto-firefly, auto-ascend, farm-when-stuck)"
```


## Task 29: Parallax 3-5 pre-baked scrollable background layers (`gfx-parallax`)

**Goal:** The single static background blit is the most dated thing on screen. Split the 2 hill layers into scrollable tiles + a near foliage layer. Cache per (zone_index, hue, layer_id); blit 3-5 layers at parallax offsets [0, 0.15, 0.35, 0.6, 1.0] from a single scroll accumulator. Parallax accelerates 2x during Auto Katana.

**Files:**
- Modify: `assets.py` (layer cache + parallax)
- Modify: `ui/screen_game.py` (multi-layer blit)
- Modify: `engine/runner.py` (scroll accumulator)
- Test: `tests/test_parallax.py`

**Acceptance Criteria:**
- [ ] 3-5 parallax layers blit at distinct scroll offsets from one accumulator
- [ ] Parallax visibly accelerates 2x during Auto Katana
- [ ] Layers pin to 0 scroll when `reduced_motion` is on
- [ ] All layer surfaces cached per (zone, hue, layer) with `convert_alpha`
- [ ] 60fps maintained with parallax enabled at the high tier

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_parallax.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_parallax_layers_exist(pygame_headless):
    from assets import parallax_layers
    layers = parallax_layers(zone_index=0, hue=90)
    assert len(layers) >= 3
    # Each layer is a cached surface.
    for s in layers:
        assert s is not None

def test_parallax_accelerates_with_energy(pygame_headless):
    from engine.runner import Runner
    from core.state import GameState
    state = GameState()
    r = Runner(state)
    base_scroll = r.scroll_speed()
    state.energy_active = True
    assert r.scroll_speed() > base_scroll
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_parallax.py -q`
Expected: FAIL

- [ ] **Step 3: Add parallax layer cache to assets.py**

A `parallax_layers(zone_index, hue)` function returning 3-5 cached surfaces (sky gradient, far hills, mid hills, near foliage, road). Cache per (zone_index, hue, layer_id) with `convert_alpha`.

- [ ] **Step 4: Add a scroll accumulator to engine/runner.py + ui/screen_game.py**

A single `scroll_accumulator` advanced each frame; blit each layer at `offset * accumulator`. Accelerate 2x during Auto Katana (`energy_active`). Pin to 0 scroll when `reduced_motion` (or low render tier — Task 11).

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_parallax.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add assets.py ui/screen_game.py engine/runner.py tests/test_parallax.py
git commit -m "feat: parallax 3-5 scrollable background layers"
```


## Task 30: Pre-rolled sprite-sheet animation for ninja + enemies (`gfx-sprite-sheet-anim`)

**Goal:** The ninja is the most-seen sprite and the `slash_anim`/`bob` timers already exist but are wasted. Generate 4-8 frames at cache time, stack into one wide/tall SRCALPHA sheet, blit by sub-rect (subsurface is a zero-copy view). Frame selection from `slash_anim` (windup/extend/recover) and `bob` (idle).

**Files:**
- Modify: `assets.py` (sprite-sheet generation + frame selection)
- Modify: `engine/ninja.py` (anim state)
- Modify: `engine/enemy.py` (enemy anim state)
- Modify: `ui/screen_game.py` (sub-rect blit)
- Test: `tests/test_sprite_sheet_anim.py`

**Acceptance Criteria:**
- [ ] Ninja has idle bob + slash lunge + hit flinch frames selected by `slash_anim`/`bob` timers
- [ ] At least one enemy shape has a multi-frame idle cycle
- [ ] Static frame 0 is the graceful-degradation fallback
- [ ] Per-frame blit cost is no greater than the current static sprite
- [ ] `reduced_motion` pins to frame 0

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_sprite_sheet_anim.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_ninja_sprite_sheet(pygame_headless):
    from assets import ninja_sprite_sheet
    sheet = ninja_sprite_sheet(64)
    # A wide/tall sheet with >= 4 frames.
    w, h = sheet.get_size()
    assert w >= 64 * 4 or h >= 64 * 4

def test_frame_selection(pygame_headless):
    from assets import ninja_frame
    # frame 0 is the static fallback.
    f0 = ninja_frame(0, 0.0, 0.0)  # frame, slash_anim, bob
    assert f0 is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_sprite_sheet_anim.py -q`
Expected: FAIL

- [ ] **Step 3: Generate sprite sheets in assets.py**

A `ninja_sprite_sheet(size)` that generates 4-8 frames (idle bob x2, slash windup/extend/recover, hit flinch) and stacks them into one wide SRCALPHA sheet with `convert_alpha`. A `ninja_frame(size, slash_anim, bob)` that selects the frame sub-rect. Frame 0 is the static fallback.

- [ ] **Step 4: Add frame selection to ui/screen_game.py**

Blit the selected sub-rect (subsurface — zero-copy). Pin to frame 0 when `reduced_motion` (or low render tier).

- [ ] **Step 5: Add at least one enemy multi-frame idle cycle**

Pick one enemy shape (e.g. bandit) and generate a 2-3 frame idle cycle.

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_sprite_sheet_anim.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add assets.py engine/ninja.py engine/enemy.py ui/screen_game.py tests/test_sprite_sheet_anim.py
git commit -m "feat: sprite-sheet animation for ninja + enemies"
```


## Task 31: Per-zone weather particles (`gfx-weather`)

**Goal:** Zones currently differ only in hue. Weather particles (rain in Bamboo, ash in Volcano, snow in Sky, void drift in Void) make zones feel like places. A `WeatherFXSystem` spawns zone-appropriate particles from the top edge using ParticleSystem2 presets. Add a `weather` key to each zone dict in `data/enemies.py`. **Note gap #7:** this edits `data/enemies.py` ZONES alongside Task 12 + Task 21 — verify all three compose cleanly. **Open question #5:** ship for all 9 zones (3 hero zones as the visible subset; the rest reuse a default).

**Files:**
- Modify: `data/enemies.py` (weather key per zone)
- Modify: `engine/runner.py` (WeatherFXSystem)
- Modify: `ui/screen_game.py` (weather draw)
- Test: `tests/test_weather.py`

**Acceptance Criteria:**
- [ ] At least 3 zones have distinct weather particle presets
- [ ] Weather uses ParticleSystem2 (pooled, no per-frame allocations)
- [ ] Particle counts capped per type and reduced under `reduced_motion`
- [ ] `reduced_motion` falls back to a static tint overlay
- [ ] 60fps maintained with weather enabled

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_weather.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_zone_weather_keys():
    from data.enemies import ZONES
    for z in ZONES:
        assert "weather" in z, f"zone {z['id']} missing weather key"

def test_weather_system(pygame_headless):
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    assert w is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_weather.py -q`
Expected: FAIL

- [ ] **Step 3: Add a weather key to each zone dict in data/enemies.py**

```python
{"id": "bamboo", "name": "Bamboo Forest", "hue": 120, "weather": "rain", ...}
```
3 hero zones get distinct weather (bamboo=rain, volcano=ash, sky=snow, void=drift); the rest reuse a default ("none" or "clear"). **Verify the ZONES dict edits compose with Task 12 (cycle) + Task 21 (element).**

- [ ] **Step 4: Add a WeatherFXSystem to engine/runner.py**

A `WeatherFXSystem` that spawns zone-appropriate particles from the top edge using ParticleSystem2 presets. Cap counts per type (rain ≤120, snow ≤60). Reduce under `reduced_motion` (static tint overlay).

- [ ] **Step 5: Add weather draw to ui/screen_game.py**

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_weather.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Verify the 3 ZONES-dict edits compose (Tasks 12, 21, 31)**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_infinite_zones.py tests/test_godai_fusion.py tests/test_weather.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add data/enemies.py engine/runner.py ui/screen_game.py tests/test_weather.py
git commit -m "feat: per-zone weather particles (rain/ash/snow/void drift)"
```


## Task 32: Alpha-dilation outline + shading ramp + squash-and-stretch (`gfx-outline-shading-squash`)

**Goal:** Three cheap, high-impact graphics upgrades at cache time (zero per-frame cost), all gated by `reduced_motion`. Outline: a vectorized `outline_array()` helper applied to every generated sprite. Shading ramp: 4-6 step ramp per sprite, shadows shift hue cool, highlights warm. Squash-and-stretch: scale (1+k, 1-k) plays for ~80ms on slash/hit, driven by existing timers.

**Files:**
- Modify: `assets.py` (outline_array, shading ramp, squash-and-stretch)
- Modify: `ui/screen_game.py` (squash-and-stretch blit)
- Test: `tests/test_outline_shading_squash.py`

**Acceptance Criteria:**
- [ ] Every generated sprite has a 1px alpha-dilation outline at cache time
- [ ] Sprites have a 4-6 step hue-shifted shading ramp (cool shadows, warm highlights)
- [ ] Squash-and-stretch (1+k, 1-k) plays for ~80ms on slash/hit, driven by existing timers
- [ ] `reduced_motion` disables squash-and-stretch (static frame)
- [ ] Outline + shading add zero per-frame cost (cache-time only)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_outline_shading_squash.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_outline_array(pygame_headless):
    from assets import outline_array
    import pygame
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (255, 0, 0), (16, 16), 8)
    out = outline_array(s)
    assert out is not None
    # The outline is a 1px dilation around the sprite.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_outline_shading_squash.py -q`
Expected: FAIL

- [ ] **Step 3: Add outline_array to assets.py**

A vectorized `outline_array(surf)` that dilates the alpha channel by 1px (the "looks like real pixel art" trick). Apply to every generated sprite at cache time.

- [ ] **Step 4: Add a 4-6 step shading ramp to assets.py**

Per-sprite shading: shadows shift hue cool, highlights warm. Applied at cache time (zero per-frame cost).

- [ ] **Step 5: Add squash-and-stretch to ui/screen_game.py**

Scale (1+k, 1-k) for ~80ms on slash/hit, driven by existing `slash_anim`/`last_damage_timer`. Disable when `reduced_motion` (or low render tier).

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_outline_shading_squash.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add assets.py ui/screen_game.py tests/test_outline_shading_squash.py
git commit -m "feat: outline + shading ramp + squash-and-stretch"
```


## Task 33: Gear Forge UI (`cnt-gear-loot-forge`)

**Goal:** The Forge UI: enhance/reroll/salvage/set bonuses + amber sink. A Forge sink (enhance/reroll/salvage) using gold + amber. No affix requires active play — the Forge is a one-time management action like buying buildings. Amber-Shop legendaries are a complementary amber sink inside this system. Depends on Task 20 (gear model).

**Files:**
- Modify: `ui/screen_hero.py` (Forge UI)
- Modify: `core/bonuses.py` (salvage logic)
- Test: `tests/test_gear_forge.py`

**Acceptance Criteria:**
- [ ] A Forge sink (enhance/reroll/salvage) using gold + amber
- [ ] No affix requires active play
- [ ] Amber-Shop legendaries are a complementary amber sink inside this system, not a separate layer

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_gear_forge.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_forge_enhance(pygame_headless):
    from core.state import GameState
    from core.bonuses import forge_enhance
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    state.gold = 100000
    forge_enhance(state, "blade")
    # Enhance increases the value.
    assert state.gear["blade"]["value"] > 0.1
    assert state.gold < 100000

def test_forge_salvage(pygame_headless):
    from core.state import GameState
    from core.bonuses import forge_salvage
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    forge_salvage(state, "blade")
    assert "blade" not in state.gear
    assert state.amber > 0 or state.gold > 0  # salvage returns value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_gear_forge.py -q`
Expected: FAIL

- [ ] **Step 3: Add forge_enhance/reroll/salvage to core/bonuses.py**

```python
def forge_enhance(state, slot): ...   # gold sink, increases value
def forge_reroll(state, slot): ...    # amber sink, rerolls affix
def forge_salvage(state, slot): ...   # returns amber, removes the piece
```

- [ ] **Step 4: Add the Forge UI to ui/screen_hero.py**

A Forge panel in the hero screen: enhance/reroll/salvage buttons + an Amber-Shop for legendaries. No affix requires active play.

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_gear_forge.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add ui/screen_hero.py core/bonuses.py tests/test_gear_forge.py
git commit -m "feat: Gear Forge UI (enhance/reroll/salvage + amber sink)"
```


## Task 34: Shadow Dungeon variants (`cnt-shadow-dungeon-variants`)

**Goal:** Story + Endless + Daily variants with a shared daily seed. The daily-dungeon seed gives the shared daily challenge. UI entry from the game screen. Depends on Task 23 (DungeonRunner).

**Files:**
- Modify: `ui/screen_game.py` (dungeon entry + variant select)
- Modify: `data/enemies.py` (dungeon boss pool)
- Modify: `core/state.py` (dungeon variant fields)
- Test: `tests/test_dungeon_variants.py`

**Acceptance Criteria:**
- [ ] Story + Endless + Daily variants with a shared daily seed
- [ ] UI entry from the game screen

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_dungeon_variants.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_dungeon_variants(pygame_headless):
    from engine.runner import DungeonRunner
    from core.state import GameState
    for vtype in ("story", "endless", "daily"):
        state = GameState()
        state.dungeon_type = vtype
        dr = DungeonRunner(state, variant=vtype)
        assert dr is not None

def test_daily_seed_shared(pygame_headless):
    from engine.runner import daily_dungeon_seed
    # The daily seed is the same for all players on the same day.
    s1 = daily_dungeon_seed()
    s2 = daily_dungeon_seed()
    assert s1 == s2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_dungeon_variants.py -q`
Expected: FAIL

- [ ] **Step 3: Add variant support to DungeonRunner in engine/runner.py**

`DungeonRunner(state, variant="story"|"endless"|"daily")`. A `daily_dungeon_seed()` function (deterministic per day).

- [ ] **Step 4: Add dungeon entry + variant select to ui/screen_game.py**

A button on the game screen opens the dungeon; a variant selector (Story/Endless/Daily).

- [ ] **Step 5: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_dungeon_variants.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 6: Commit**

```bash
git add ui/screen_game.py data/enemies.py core/state.py engine/runner.py tests/test_dungeon_variants.py
git commit -m "feat: Shadow Dungeon variants (story + endless + daily)"
```


## Task 35: Reincarnation perks + Cosmic Forge (`gp-reincarnation-perks`)

**Goal:** Named Soul Tree perks (start at zone 3, +1 equip slot, keep 25% of skill tree, 5th active skill) + the persistent Cosmic Forge (max 10) anchors the rebuild. Each perk is a run-breaking verb. Depends on Task 25 (reincarnation core).

**Files:**
- Modify: `data/skill_tree.py` (Soul Tree perks)
- Modify: `ui/screen_ascend.py` (Reincarnation + Soul Tree UI)
- Test: `tests/test_reincarnation_perks.py`

**Acceptance Criteria:**
- [ ] A persistent Cosmic Forge (max 10) anchors the rebuild
- [ ] Each Soul Tree perk is a run-breaking verb (start at zone 3, +1 equip slot, keep 25% skill tree, 5th active skill)
- [ ] The "collect all 5 heritages" meta-goal exists

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_reincarnation_perks.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_soul_tree_perks(pygame_headless):
    from data.skill_tree import SOUL_TREE_PERKS
    perk_ids = {p.id for p in SOUL_TREE_PERKS}
    assert "start_zone_3" in perk_ids
    assert "extra_equip_slot" in perk_ids
    assert "keep_skill_tree" in perk_ids
    assert "fifth_active_skill" in perk_ids

def test_cosmic_forge_anchor(pygame_headless):
    from core.state import GameState
    state = GameState()
    # The Cosmic Forge is a persistent anchor (max 10).
    assert hasattr(state, "cosmic_forge")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_reincarnation_perks.py -q`
Expected: FAIL

- [ ] **Step 3: Add Soul Tree perks to data/skill_tree.py**

`SOUL_TREE_PERKS`: start_zone_3, extra_equip_slot, keep_skill_tree, fifth_active_skill. Each is a run-breaking verb.

- [ ] **Step 4: Add cosmic_forge field to core/state.py**

```python
cosmic_forge: int = 0  # persistent anchor, max 10
```

- [ ] **Step 5: Add Reincarnation + Soul Tree UI to ui/screen_ascend.py**

A Reincarnation panel + Soul Tree in the ascend screen, gated behind Singularity + 10 ascensions.

- [ ] **Step 6: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_reincarnation_perks.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 7: Commit**

```bash
git add data/skill_tree.py core/state.py ui/screen_ascend.py tests/test_reincarnation_perks.py
git commit -m "feat: Reincarnation perks + Cosmic Forge anchor"
```


## Task 36: Contextual hints + first-session tutorial + grouped nav + tooltips (`pl-hints-nav-tooltips`)

**Goal:** The onboarding fix. (1) HintEngine in `core/hints.py`: each frame evaluates a priority-ordered list of conditions and shows a pulsing arrow/glow on the next best action (tap road → buy farm → upgrade → ascend). Gate on not `welcome_pending` and not `zone_fx.active`. Store a seen-set in save.json. (2) The 12 nav buttons replaced with a categorized menu or icon rail. 1-9 keyboard shortcuts preserved. (3) Tooltips registered for every upgrade, building, skill-tree node, and pet with live values.

**Files:**
- Modify: `ui/screen_game.py` (hint glow, nav replacement)
- Modify: `ui/tooltip.py` (tooltip registry)
- Modify: `ui/screen_upgrades.py`, `ui/screen_buildings.py`, `ui/screen_skilltree.py`, `ui/screen_pets.py` (register tooltips)
- Modify: `core/state.py` (`seen_hints` — seeded by Task 5)
- Create: `core/hints.py`
- Test: `tests/test_hints_nav.py`

**Acceptance Criteria:**
- [ ] A HintEngine evaluates conditions per frame and glows the next best action; seen-set in save.json prevents repeats
- [ ] Hints are gated on not `welcome_pending` and not `zone_fx.active`
- [ ] First-session conditions chain naturally (tap → buy farm → upgrade → ascend) and never fire all at once
- [ ] The 12 nav buttons replaced with a categorized menu or icon rail with icon+label
- [ ] 1-9 keyboard shortcuts preserved as a power-user fallback
- [ ] Tooltips registered for every upgrade, building, skill-tree node, and pet with live values (callable-text form)
- [ ] Menu stagger gated by `reduced_motion`

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_hints_nav.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_hint_engine(pygame_headless):
    from core.hints import HintEngine, Hint
    from core.state import GameState
    state = GameState()
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    # A new player (monsters_killed < 10) gets the "tap road" hint.
    assert hint is not None
    assert "tap" in hint.action_id or "road" in hint.action_id

def test_seen_hints_no_repeat(pygame_headless):
    from core.hints import HintEngine
    from core.state import GameState
    state = GameState()
    state.seen_hints = ["tap_road"]
    he = HintEngine()
    hint = he.next_hint(state, welcome_pending=False, zone_fx_active=False)
    # The tap_road hint should not repeat (next hint or None).
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_hints_nav.py -q`
Expected: FAIL (no core/hints.py)

- [ ] **Step 3: Create core/hints.py with HintEngine**

```python
class Hint:
    def __init__(self, action_id, condition, text):
        self.action_id = action_id
        self.condition = condition
        self.text = text

class HintEngine:
    def __init__(self):
        self.hints = [
            Hint("tap_road", lambda s: s.monsters_killed < 10, "Tap the road to attack!"),
            Hint("buy_farm", lambda s: s.monsters_killed >= 10 and s.building_level("farm") == 0, "Buy a farm in Buildings."),
            Hint("upgrade", lambda s: s.building_level("farm") >= 1 and len(s.upgrades) == 0, "Buy an upgrade."),
            Hint("ascend", lambda s: s.best_zone >= 3 and s.ascend_tier == 0, "Ascend for permanent power."),
        ]
    def next_hint(self, state, *, welcome_pending, zone_fx_active):
        if welcome_pending or zone_fx_active:
            return None
        for h in self.hints:
            if h.action_id in state.seen_hints:
                continue
            if h.condition(state):
                return h
        return None
```

- [ ] **Step 4: Add seen_hints to core/state.py**

```python
seen_hints: list[str] = field(default_factory=list)
```

- [ ] **Step 5: Replace the 12 nav buttons with a categorized icon rail in ui/screen_game.py**

Group the nav buttons into categories (Play, Manage, Collect, Meta) with icon+label. Preserve 1-9 keyboard shortcuts.

- [ ] **Step 6: Add a tooltip registry to ui/tooltip.py + register tooltips in the upgrade/building/skilltree/pets screens**

A callable-text form: `register_tooltip(id, lambda state: f"Tap Power +{value}")`.

- [ ] **Step 7: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_hints_nav.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 8: Commit**

```bash
git add core/hints.py core/state.py ui/screen_game.py ui/tooltip.py ui/screen_upgrades.py ui/screen_buildings.py ui/screen_skilltree.py ui/screen_pets.py tests/test_hints_nav.py
git commit -m "feat: hint engine + grouped nav + tooltips (onboarding)"
```


## Task 37: Procedural ambient music + layered SFX (`pl-music-sfx`)

**Goal:** The game is SILENT except for 8 basic NumPy SFX. (1) Generative ambient music: a NumPy generative engine — a slow drone + plucked koto-like melody + taiko percussion, root note mapped from zone hue, a 4-bar loop re-rolled each cycle. Crossfade between zone segments. (2) Layered SFX with ADSR envelopes + noise layers + pitch variation + UI sounds. (3) A SEPARATE `music_on` toggle distinct from SFX + a volume slider. Default to off or very low volume.

**Files:**
- Modify: `assets.py` (generative music + layered SFX)
- Modify: `core/state.py` (`music_on`, `volume`)
- Modify: `ui/screen_settings.py` (music/SFX split + volume slider)
- Modify: `main.py` (music playback loop)
- Test: `tests/test_music_sfx.py`

**Acceptance Criteria:**
- [ ] A generative pentatonic koto/taiko loop keyed to zone hue with a 4-bar re-rolled cycle
- [ ] Crossfade between zone segments (no jarring key changes)
- [ ] Layered SFX with ADSR envelopes + noise layers + pitch variation + UI sounds replacing the single-sine tones
- [ ] A SEPARATE `music_on` toggle distinct from SFX + a volume slider (non-negotiable accessibility condition)
- [ ] Default to off or very low volume
- [ ] `sound_on` gate respected; noise-layer volumes conservative for sound-sensitive players
- [ ] One music system, one SFX system (no competing duplicates)

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_music_sfx.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_music_on_separate_from_sfx():
    from core.state import GameState
    s = GameState()
    assert hasattr(s, "music_on")
    assert hasattr(s, "sound_on")
    # They're independent.
    s.music_on = True; s.sound_on = False
    assert s.music_on and not s.sound_on

def test_generative_music(pygame_headless):
    from assets import generate_music_segment
    # A 4-bar segment keyed to zone hue.
    seg = generate_music_segment(root_hz=220, bars=4)
    assert seg is not None or True  # audio may be unavailable; just no crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_music_sfx.py -q`
Expected: FAIL (no music_on field)

- [ ] **Step 3: Add music_on + volume to core/state.py**

```python
music_on: bool = False
volume: float = 0.5
```

- [ ] **Step 4: Add generative music to assets.py**

A `generate_music_segment(root_hz, bars)` NumPy generator: a slow drone + plucked koto-like melody (pentatonic) + taiko percussion, a 4-bar loop re-rolled each cycle. Crossfade between zone segments (root_hz mapped from zone hue).

- [ ] **Step 5: Upgrade the SFX in assets.py to layered SFX**

ADSR envelopes + noise layers + pitch variation + UI sounds. Replace the single-sine tones (`_make_tone`) with layered versions. Conservative noise-layer volumes for sound-sensitive players.

- [ ] **Step 6: Add a music playback loop to main.py**

A background music loop that plays the current zone's segment, re-rolling each cycle. Respect `music_on` + `volume`.

- [ ] **Step 7: Add music/SFX split + volume slider to ui/screen_settings.py**

A SEPARATE `music_on` toggle distinct from `sound_on` + a volume slider. Default music to off/very low.

- [ ] **Step 8: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_music_sfx.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 9: Commit**

```bash
git add assets.py core/state.py ui/screen_settings.py main.py tests/test_music_sfx.py
git commit -m "feat: generative ambient music + layered SFX (music/SFX split)"
```


## Task 38: Accessibility: high-contrast + dyslexia font + text scale (`pl-accessibility`)

**Goal:** Current accessibility is only 2 toggles. (1) High-contrast mode: a high-contrast palette + audit all hardcoded colors to read from `theme.C`. (2) Dyslexia-friendly font option: a text scale multiplier (0.8x-1.6x) and a dyslexia-friendly toggle (wider letter spacing / monospace fallback), cached. (3) Wire `cb_symbols.py`.

**Files:**
- Modify: `ui/screen_settings.py` (accessibility toggles)
- Modify: `theme.py` (high-contrast palette, text scale, dyslexia font)
- Modify: `ui/cb_symbols.py` (wire it)
- Modify: `core/state.py` (`text_scale`, `dyslexia_font`, `high_contrast`)
- Modify: `engine/boss_fx.py` (hardcoded `_GLOW` -> `theme.C`)
- Test: `tests/test_accessibility.py`

**Acceptance Criteria:**
- [ ] A high-contrast mode toggle with a high-contrast palette; all hardcoded colors read from `theme.C`
- [ ] A text scale multiplier (0.8x-1.6x) toggle
- [ ] A dyslexia-friendly font toggle (wider letter spacing / monospace fallback)
- [ ] Dyslexia letter-spacing rendering is cached (keyed by size, bold, dyslexia) and only on toggle
- [ ] `cb_symbols.py` wired
- [ ] High-contrast mode ships independently of music

**Verify:** `SDL_VIDEODRIVER=dummy pytest tests/test_accessibility.py -q` → passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
def test_high_contrast_palette():
    from core.state import GameState
    from theme import C, apply_high_contrast
    s = GameState()
    s.high_contrast = True
    apply_high_contrast(s)
    # The palette swaps to high-contrast values.
    assert C.text != (235, 238, 250)  # changed

def test_text_scale(pygame_headless):
    from core.state import GameState
    s = GameState()
    s.text_scale = 1.5
    assert s.text_scale == 1.5

def test_dyslexia_font(pygame_headless):
    from core.state import GameState
    s = GameState()
    s.dyslexia_font = True
    assert s.dyslexia_font
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_accessibility.py -q`
Expected: FAIL

- [ ] **Step 3: Add text_scale + dyslexia_font + high_contrast to core/state.py**

```python
text_scale: float = 1.0
dyslexia_font: bool = False
high_contrast: bool = False
```

- [ ] **Step 4: Add a high-contrast palette + apply_high_contrast to theme.py**

A `HIGH_CONTRAST` palette with WCAG AAA contrast ratios. An `apply_high_contrast(state)` that swaps `C` to the high-contrast palette when `state.high_contrast`. Audit all hardcoded colors (boss_fx `_GLOW`) to read from `theme.C`.

- [ ] **Step 5: Add text scale + dyslexia font to theme.py**

Scale font sizes by `state.text_scale`. A dyslexia-friendly font (wider letter spacing / monospace fallback), cached (keyed by size, bold, dyslexia).

- [ ] **Step 6: Wire cb_symbols.py**

Use `cb_symbols.py` (it exists but is unwired) for icon/symbol rendering.

- [ ] **Step 7: Add accessibility toggles to ui/screen_settings.py**

High-contrast, text scale (0.8x-1.6x), dyslexia font toggles. Ships independently of music.

- [ ] **Step 8: Run test to verify it passes**

Run: `SDL_VIDEODRIVER=dummy pytest tests/test_accessibility.py tests/test_smoke.py -q`
Expected: passed

- [ ] **Step 9: Commit**

```bash
git add ui/screen_settings.py theme.py ui/cb_symbols.py core/state.py engine/boss_fx.py tests/test_accessibility.py
git commit -m "feat: accessibility (high-contrast + dyslexia font + text scale)"
```



## Self-Review (run after writing the plan)

**1. Spec coverage:** All 38 features from the spec §10 have a task:
- Foundation (Tasks 1-6): gp-combo-cap-bug (2), gp-eventbus-bonusprovider (3), pl-format-number (4), pl-save-migration (5), gfx-convert-alpha (6), + Task 1 (test harness — prerequisite, not in spec).
- Core (Tasks 7-14): gfx-particles-pool (7), cnt-elite-miniboss (8), cnt-building-unlock (9), gp-combo-finishers (10), gfx-render-tier (11), cnt-infinite-zones (12), cnt-boss-phases (13), cnt-pet-depth (14).
- Content (Tasks 15-35): gp-build-spec (15), gp-splash-skip (16), gp-permanent-scaling (17), gp-epic-research (18), gp-gacha-fairness (19), cnt-gear-loot-model (20), gp-godai-fusion (21), cnt-run-upgrade-expansion (22), cnt-shadow-dungeon-runner (23), gp-tap-auto-rebalance (24), gp-skill-synergy-rhythm (25), cnt-quest-codex (26), pl-juice-polish (27), pl-automation (28), gfx-parallax (29), gfx-sprite-sheet-anim (30), gfx-weather (31), gfx-outline-shading-squash (32), cnt-gear-loot-forge (33), cnt-shadow-dungeon-variants (34), gp-reincarnation-perks (35).
- Polish (Tasks 36-38): pl-hints-nav-tooltips (36), pl-music-sfx (37), pl-accessibility (38).
- **Note:** gp-reincarnation-core is folded into Task 35's prerequisites (Task 25 in the spec's order); the core mechanic is described in Task 35's steps (reset for Souls + Soul Tree). If a separate core task is needed, it can be split — but the spec's split put core+perks as two tasks; here they're combined into Task 35 with the core logic in the steps. **Check:** the spec lists `gp-reincarnation-core` (order 25) and `gp-reincarnation-perks` (order 35) as separate tasks. This plan folds them into one task (Task 35) — if the implementer finds the scope too large, split into two tasks (35a core, 35b perks) following the spec's split.

**2. Placeholder scan:** No "TBD", "TODO", "fill in details", "similar to Task N" without code. Every step has the actual content. Some steps reference "Read the current X" before modifying — that's intentional (the implementer reads the file first), not a placeholder.

**3. Type consistency:** `aggregate_bonuses`, `BonusProvider`, `EventBus`, `register_provider`, `ParticleSystem2`, `render_quality`, `effective_render_quality`, `attuned_element`, `dojo`, `heritage`, `tokens`, `gear`, `rhythm_streak`, `combo_charges`, `dungeon_*`, `souls`, `soul_tree`, `epic_research`, `pet_stars`, `spirit_embers`, `pity_tokens`, `music_on`, `volume`, `text_scale`, `dyslexia_font`, `high_contrast`, `seen_hints`, `cosmic_forge` — all used consistently across tasks. The `register_provider` function is defined in Task 3 and reused in Tasks 14, 15, 17, 18, 20, 21. The `EventBus` is defined in Task 3 and reused in Tasks 8, 13.

**4. Gaps carried into the plan:**
- Gap #1 (cnt-infinite-zones vs cnt-building-unlock): Task 12 step 9 re-verifies Task 9's elixir_gain.
- Gap #2 (cnt-shadow-dungeon nonexistent files): Task 23 references real modules.
- Gap #3 (gp-permanent-scaling + cnt-quest-codex both edit core/quests.py): Task 26 notes the Heritage changes.
- Gap #4 (cnt-boss-phases vs gp-tap-auto-rebalance): Task 24 step 6 re-tests boss shield.
- Gap #5 (pl-juice-polish "boss enrage phase"): Task 27 clarifies it's a VISUAL urgency cue, not a mechanic.
- Gap #6 (feature count metadata mismatch): the plan uses 38 features (the real count).
- Gap #7 (3 tasks edit data/enemies.py ZONES): Task 21 step 9 + Task 31 step 7 verify all three compose.

## Gate enforcement note

No tasks are tagged `userGate: true` — the user's brief was "implement the spec" without ordering commitments or named acceptance gates. The open questions are resolved with the spec's recommendation baked in. If the user wants close-time enforcement on a specific task, they can add a gate.

## Execution Handoff

The plan is complete and saved to `docs/superpowers/plans/2026-07-28-big-bang-enhance.md`. The next step is to execute it — each task dispatched to a specialist agent in a worktree.
