# Quest completion juice — integration spec

A new module, `ui/quest_fx.py` (`QuestFxSystem`), adds visible
**completion juice** to the daily-quest auto-claim: when a daily quest
completes (silently auto-claimed today by
`core/quests.update_daily_progress`), the quests screen fires a medal +
amber particle burst at the quest row, an expanding ring, a floating
"+N medals  +N amber" reward text, a top-of-panel toast banner, and a
per-quest "✓ Claimed" checkmark animation. It also exposes a
`countdown(state)` helper the screen uses to draw a "refreshes in
HH:MM" timer, and a `claim_all(...)` trigger for a new "Claim All"
button.

All rendering uses pygame primitives + cached theme fonts. Effect slots
live in fixed pools and rendered text surfaces are cached at spawn
time, so the per-frame hot path performs zero allocations once warm.

## The system

`QuestFxSystem` (in `ui/quest_fx.py`) exposes:

| method | purpose |
|--------|---------|
| `on_complete(x, y, medals, amber, quest_id="", name="")` | fire the juice for one completion: burst + ring + floating reward text + toast + per-quest pulse |
| `claim_all(x, y, medals, amber)` | fire the "Claim All" celebration: bigger burst + consolidated toast + ring |
| `update(dt)` | advance all active effects; retire expired ones |
| `draw(surf)` | draw rings, particles, floating text, and toasts onto the screen |
| `countdown(state)` | return `(h, m)` until the next daily refresh from `state.daily_refresh` |
| `pulse_t(quest_id)` | per-quest pulse progress (0..1); 0.0 when settled |
| `pulse_active(quest_id)` | True while the completion pulse is animating |
| `checkmark_anim(quest_id)` | return `(scale, alpha)` for the "✓ Claimed" checkmark |
| `has_pending()` | True while any completion pulse is animating (drives the "Claim All" button) |
| `reset()` | clear all pulses + per-quest pulse tracking (call on daily refresh) |

`sound_on` and `on_shake` are polish hooks the screen sets (see
"Sound + shake" below).

## Constructing and owning the system

`QuestsScreen` owns one instance, created in `__init__`:

```python
from ui.quest_fx import QuestFxSystem

class QuestsScreen:
    def __init__(self, game) -> None:
        ...
        self.fx = QuestFxSystem()
```

The system is self-contained and holds no persistent state — it is safe
to construct on every screen entry and discard on exit; effects simply
stop if the screen is left mid-animation.

## Wiring the trigger

`core/quests.update_daily_progress` already returns the list of
newly-completed quests (each a dict `{id, name, medals, amber}`) and
sets `dq_state["claimed"] = True` for each. The runner currently
consumes that list to push a plain `notify(...)` banner; the screen
needs the *same* completions to fire the row-local juice, so the
cleanest routing is for the screen to diff `state.daily_quests`'s
`claimed` flags against a `_seen_claims` set it owns.

### Option A (recommended): the screen diffs `claimed`

The screen keeps a `set[str]` of quest ids it has already seen claimed.
Each `update`, it walks `state.daily_quests`, and for any quest whose
`claimed` flag just flipped to `True` (and whose id is not in
`_seen_claims`), it calls `fx.on_complete(...)` with that row's centre
coordinates and the quest's rewards, then records the id in
`_seen_claims`. On daily refresh (`maybe_refresh_dailies` rebuilds
`state.daily_quests`), the screen clears `_seen_claims` and calls
`fx.reset()`.

```python
# QuestsScreen.__init__
self._seen_claims: set[str] = set()

# QuestsScreen.update, after the button updates:
state = self.game.state
# Detect a daily refresh (the quest list was rebuilt) and reset tracking.
ids = {dq["id"] for dq in state.daily_quests}
if not ids.issubset(self._seen_claims | {dq["id"] for dq in state.daily_quests if dq.get("claimed")}):
    # New quest set — clear stale tracking so the checkmarks re-settle.
    self._seen_claims = set()
    self.fx.reset()
for i, dq_state in enumerate(state.daily_quests):
    if dq_state.get("claimed") and dq_state["id"] not in self._seen_claims:
        dq = next(d for d in q.DAILY_POOL if d.id == dq_state["id"])
        if dq is None:
            continue
        # Row rect matches the draw layout (60, 170 + i*64, 560, 56).
        rx, ry = 60 + 280, 170 + i * 64 + 28
        self.fx.on_complete(rx, ry, dq.reward_medals, dq.reward_amber,
                            quest_id=dq.id, name=dq.name)
        self._seen_claims.add(dq_state["id"])
self.fx.update(dt)
```

The row centre is `(60 + 280, 170 + i*64 + 28)` because the screen
draws each row at `pygame.Rect(60, y, 560, 56)` with `y = 170 + i*64`.
Keep the two in sync if the layout changes.

### Option B: the runner stashes completions for the screen

If you prefer not to diff in the screen, have `engine/runner.py` stash
the completed list on the runner (e.g. `self.pending_quest_completions:
list[dict] = []`) instead of (or in addition to) calling `notify`, and
have the screen drain it each `update`:

```python
# engine/runner.py, replacing the existing for-loop in update():
completed = update_daily_progress(self.state)
self.pending_quest_completions.extend(completed)
# (the screen drains and fires fx; the runner keeps the notify too)

# QuestsScreen.update:
for c in self.game.runner.pending_quest_completions:
    i = next((i for i, d in enumerate(state.daily_quests)
              if d["id"] == c["id"]), None)
    if i is None:
        continue
    rx, ry = 60 + 280, 170 + i * 64 + 28
    self.fx.on_complete(rx, ry, c["medals"], c["amber"],
                        quest_id=c["id"], name=c["name"])
self.game.runner.pending_quest_completions.clear()
self.fx.update(dt)
```

Either route reaches the same fx; Option A keeps the runner unchanged.

## Drawing the countdown timer

`countdown(state)` returns `(h, m)` until `state.daily_refresh`
(epoch seconds, set by `core.quests.maybe_refresh_dailies` to
`now + DAILY_REFRESH_SECONDS`). The screen draws it next to the
"Daily quests refresh every 24h." subtitle, replacing the static text:

```python
# QuestsScreen.draw, replacing the "Daily quests refresh every 24h." line:
h, m = self.fx.countdown(state)
draw_text_center(surf, f"Daily quests  —  refreshes in {h:02d}:{m:02d}",
                 (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
```

`countdown` returns `(24, 0)` when no refresh is scheduled yet (a fresh
save before the first `maybe_refresh_dailies` call), so the timer never
reads negative or blank.

## Drawing the "✓ Claimed" checkmark animation

The screen currently draws a static "✓" when `claimed` is True. Replace
it with the animated checkmark, which scales in with a slight overshoot
and fades in over the first 40% of the pulse, then settles:

```python
# QuestsScreen.draw, inside the daily-quest row loop, replacing the
# `if claimed: draw_text(surf, "✓", ...)` block:
if claimed:
    scale, alpha = self.fx.checkmark_anim(dq.id)
    label = font_md(bold=True).render("✓", True, C.text_good)
    label.set_alpha(alpha)
    if scale != 1.0:
        sw = max(1, int(label.get_width() * scale))
        sh = max(1, int(label.get_height() * scale))
        label = pygame.transform.smoothscale(label, (sw, sh))
    surf.blit(label, label.get_rect(center=(r.right - 30, r.y + 28)))
```

The checkmark settles (scale 1.0, alpha 255) once the pulse finishes, so
claimed quests keep a stable "✓" after the animation.

## Adding the "Claim All" button

Add a `Button` to the screen that, when there is at least one
*unclaimed-but-complete* daily quest, claims all of them at once and
fires the consolidated celebration. Because `update_daily_progress`
already auto-claims, the button is most useful when the player wants to
re-trigger the celebration for already-claimed quests (e.g. they
switched to the screen mid-burst) — or, if the game later switches to
manual claim, the button does the actual claiming. The screen decides
visibility; the fx just plays.

```python
# QuestsScreen.__init__:
self.btn_claim_all = Button(
    (cfg.WINDOW_W - 200, 130, 160, 36), "Claim All",
    on_click=self._claim_all,
)
self.buttons = [self.btn_back, self.btn_claim_all]

# QuestsScreen._claim_all:
def _claim_all(self):
    state = self.game.state
    medals = amber = 0
    for dq_state in state.daily_quests:
        if dq_state.get("claimed"):
            dq = next(d for d in q.DAILY_POOL if d.id == dq_state["id"])
            if dq is None:
                continue
            medals += dq.reward_medals
            amber += dq.reward_amber
    if medals == 0 and amber == 0:
        return
    # Burst at the centre of the daily-quest column.
    self.fx.claim_all(cfg.WINDOW_W // 2, 170 + 2 * 64 + 28,
                      medals, amber)
```

The button's `enabled` flag can be wired to `self.fx.has_pending()` so
it only highlights while juice is actively playing (optional).

## Sound + shake

`QuestFxSystem` plays `assets.play("gacha", ...)` on each completion
and `assets.play("ascend", ...)` on `claim_all`, gated by
`self.sound_on`. It also calls `self.on_shake(amp, dur)` if set
(`on_complete` → 4.0/0.25, `claim_all` → 6.0/0.35). The screen wires
both once:

```python
# QuestsScreen.__init__, after self.fx = QuestFxSystem():
self.fx.sound_on = self.game.state.sound_on
self.fx.on_shake = self.game.shake
```

(`Game.shake(amp, dur)` already exists and respects
`state.reduced_motion`.) If the screen does not set these, the system
skips the sound and shake — no further changes are needed.

## Full draw order

1. Background gradient + title + currency pills (unchanged).
2. Countdown timer (new; replaces the static "refreshes every 24h.").
3. "Daily Quests" header.
4. Per-quest row: panel, name, desc, progress bar, count, and the
   animated "✓" checkmark (with `checkmark_anim` scale/alpha).
5. "Claim All" button (new).
6. Achievements (unchanged).
7. `self.fx.draw(surf)` — rings, particles, floating reward text, and
   toasts on top of the rows.
8. Buttons (the back button; the "Claim All" button is drawn in step 5
   or here — either works as long as it's above the fx toasts).

The fx draws *after* the rows so the burst, ring, and floating text
overlay the row; the toasts sit at `_TOAST_Y = 108` (just below the
currency pills) and stack downward.

## Tunables

The fx module exposes these constants at the top of `ui/quest_fx.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_BURST_LIFE` | 0.60s | particle lifetime |
| `_BURST_SPEED` | 150.0 | particle initial speed (px/s) |
| `_BURST_GRAVITY` | 220.0 | particle gravity (px/s^2) |
| `_BURST_COUNT` | 16 | particles per completion (split medal/amber) |
| `_PART_SIZE` | 3 | particle radius (px) |
| `_RING_DUR` | 0.55s | expanding ring duration |
| `_RING_MAX_R` | 54px | peak ring radius |
| `_FLOAT_DUR` | 0.90s | floating reward text lifetime |
| `_FLOAT_RISE` | 38px | pixels the text rises |
| `_PULSE_DUR` | 0.60s | "✓ Claimed" checkmark animation length |
| `_TOAST_LIFE` | 3.0s | toast banner lifetime |
| `_TOAST_Y` | 108 | toast banner top y |
| `_MAX_PARTICLES` | 80 | particle slot pool size |
| `_MAX_FLOATS` | 6 | floating text slot pool size |
| `_MAX_PULSES` | 6 | pulse slot pool size (one per daily quest + buffer) |
| `_MAX_TOASTS` | 3 | toast slot pool size |

Tune by editing the constants; no other module needs to change.

## Why no per-frame allocations

* Effect slots (`_Particle`, `_FloatText`, `_Pulse`, `_Toast`) are
  stored in fixed lists, recycled via `_next_free` (the first slot is
  reused if the pool is full).
* The floating reward text and the toast's text + bg surfaces are
  rendered **once at spawn time** (inside `on_complete` /
  `_spawn_toast`, which runs on a completion — not in the per-frame
  `update`/`draw`). `draw` only `set_alpha`s and `blit`s.
* The particle and ring scratch surfaces are stored on the system
  instance and grown lazily to fit the largest particle/ring, then
  reused — never re-allocated per frame after warm-up.
* `font_md(bold=True)` and `font_sm(bold=True)` are cached by
  `theme._font`, so no `SysFont` call happens per frame.
* The burst uses `utils.rng()` (the shared deterministic-per-run RNG)
  so the juice is stable for a given completion.

## Save compatibility

The fx system is purely visual and holds no persistent state — nothing
to save. `_seen_claims` lives on the screen and is rebuilt from
`state.daily_quests` on each screen entry, so it self-heals after a
load. A quest that was already claimed when the save was loaded will
not re-fire the juice (it is in `_seen_claims` from the first frame),
which is the desired behaviour — the juice plays for *new* completions
the player witnesses.
