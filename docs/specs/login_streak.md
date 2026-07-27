# Daily Login Streak — integration spec

A daily login streak system that tracks the number of consecutive
real-world days the player has opened Tap Ninja and grants escalating
Amber rewards.  A streak counter is shown on the menu screen, and a
"Daily Login" reward modal appears on the first load of each new
calendar day.

## Files

| Path | Role |
|---|---|
| `core/login_streak.py` | New. `check_streak`, `apply_streak`, `STREAK_REWARDS`. |
| `core/state.py` | Existing. Add `last_login_date` + `login_streak` fields. |
| `main.py` | Existing. Call `check_streak` on load; show the reward modal. |
| `ui/screen_menu.py` | Existing. Render the streak counter. |
| `ui/welcome_modal.py` or a new `ui/login_modal.py` | Hosts the reward card. |

## State fields to add (`GameState`)

Add two flat, additive fields under the `# ---- Meta ----` block in
`core/state.py` (they load/save automatically via the existing
`from_dict` / `to_dict` path because the schema is additive):

```python
# ---- Daily login streak ----
last_login_date: str = ""     # "YYYY-MM-DD" of the last collected day
login_streak: int = 0         # current consecutive-day count
```

`from_dict` already copies any matching field via `hasattr`, and
`to_dict` uses `asdict`, so no other state.py changes are required.

## `core/login_streak.py` API

```python
STREAK_REWARDS: dict[int, int] = {1: 5, 2: 8, 3: 12, 7: 30, 14: 80, 30: 200}

def check_streak(state: GameState) -> tuple[int, int, bool]:
    """(streak_count, reward_amber, is_new_day). Does NOT mutate state."""
    ...

def apply_streak(state: GameState, reward: int) -> None:
    """Record today's collection: bumps streak, sets last_login_date, adds amber."""
    ...
```

### Reward ladder

Days not listed fall back to the previous tier's reward until the next
milestone; day 30 is the cap (later days keep paying 200):

| Day | Amber |
|---|---|
| 1 | 5 |
| 2 | 8 |
| 3 | 12 |
| 4–6 | 12 |
| 7 | 30 |
| 8–13 | 30 |
| 14 | 80 |
| 15–29 | 80 |
| 30+ | 200 |

### Streak progression

- `last_login_date` is `None`/empty → first ever login → streak = 1,
  reward = 5, `is_new_day = True`.
- `last_login_date == today` → already collected today →
  `is_new_day = False`, reward = 0, streak unchanged.
- `last_login_date == today - 1` → consecutive day → streak += 1,
  reward = `_reward_for(new_streak)`, `is_new_day = True`.
- `last_login_date < today - 1` (a day skipped) → streak resets to 1,
  reward = 5, `is_new_day = True`.

`check_streak` is pure (no mutation); `apply_streak` is idempotent
within a calendar day (a same-day second call is a no-op so the reward
cannot be double-claimed).

## `main.py` integration

### On load (`Game.__init__`, after `GameState.load()`)

```python
from core.login_streak import check_streak, apply_streak

self.state = GameState.load()
# ... existing first-time gold grant ...

# Daily login streak — detect a new calendar day and queue the modal.
self.login_streak, self.login_reward, self.login_is_new_day = check_streak(self.state)
if self.login_is_new_day:
    # The modal is shown on the menu screen (first thing the player sees).
    # Do NOT apply yet — wait for the player to dismiss the modal so the
    # reward animates in.  apply_streak is called from the modal's collect.
    self.pending_login_reward = self.login_reward
else:
    self.pending_login_reward = None
```

### Showing the modal

Two viable hosts:

1. **`MenuScreen` (recommended for "first load of each day").**  Add a
   `LoginModal` (mirroring `WelcomeModal`'s shape) to `MenuScreen`.  On
   `__init__`, if `game.pending_login_reward` is set, arm the modal with
   `(streak, reward)`.  The modal owns input while active, plays a
   count-up over ~1.2s, and on collect calls
   `apply_streak(self.game.state, reward)` then clears
   `game.pending_login_reward`.  A gold/amber particle burst at screen
   center and a toast ("Day N login: +X amber") finish the celebration.

2. **`GameScreen` (if the welcome-back modal already owns the first-load
   slot).**  Chain the login modal after `WelcomeModal` closes: in
   `_collect_welcome`, after `offline.apply`, check
   `self.game.pending_login_reward` and arm the login modal the same
   way.  This avoids two overlapping modals on a return visit.

Either way, `apply_streak` is called exactly once per new day, from
the modal's collect handler.

### Save safety

`apply_streak` writes `last_login_date` and `login_streak` to state,
which the existing 15s autosave (`Game._update`) and the quit save
(`Game.run`'s `self.state.save()`) will persist.  No extra save hook
is needed.

## `ui/screen_menu.py` integration — streak counter

Draw a small streak indicator on the menu, near the title:

```python
# In MenuScreen.draw, after the subtitle:
streak = getattr(self.game.state, "login_streak", 0)
if streak > 0:
    label = f"Login streak: {streak} day{'s' if streak != 1 else ''}"
    draw_text_center(surf, label,
                     (cfg.WINDOW_W // 2, title_y + 90),
                     font_sm(bold=True), C.gold)
```

The counter uses `C.gold` (the existing amber/coin accent) so it reads
as part of the reward theme.  It reflects the *current* streak, which
is updated by `apply_streak` when the modal is collected; on a fresh
load where the modal is still pending, the counter shows the previous
streak until the player collects.

## Behavior contract

- **First load of a new day**: `check_streak` returns `is_new_day=True`
  with the day's reward; the menu arms the login modal; the player
  collects → `apply_streak` bumps the streak, sets `last_login_date`,
  grants Amber, and the menu counter updates.
- **Same-day reload**: `check_streak` returns `is_new_day=False`,
  reward 0; no modal; the menu counter shows the already-counted
  streak.
- **Skipped day**: streak resets to 1, reward 5, modal shown.
- **No double-claim**: `apply_streak` is a no-op if
  `last_login_date == today`, so even if the modal is somehow
  triggered twice the reward is granted once.

## Constraints honored

- Stdlib only (`datetime`) in `core/login_streak.py`; no pygame, no
  third-party imports.
- No existing file is edited by the new module; only the two new
  fields are added to `GameState` (additive schema, loads cleanly on
  older saves).
- Reward values match the spec: 5 / 8 / 12 / 30 / 80 / 200 for days
  1 / 2 / 3 / 7 / 14 / 30.
