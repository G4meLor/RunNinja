# Unified hover-tooltip system — integration spec

A new module, `ui/tooltip.py` (`TooltipManager`), gives **every
interactive element** a hover tooltip.  Today only `Button` (its `hint`
field) and the skill-tree screen (`hover_node`) render tooltips, and each
does it ad-hoc.  `TooltipManager` replaces both with one reusable,
screen-agnostic manager that any screen can register hover regions with
and that renders a styled, cursor-anchored, screen-clamped, text-wrapping
tooltip card.

All rendering uses pygame primitives, cached fonts (via `theme`), and a
lazily-grown, reused scratch surface — zero per-frame allocations once
warm.

## The system

`TooltipManager` exposes:

| method | purpose |
|--------|---------|
| `register(region_id, rect, text)` | register (or re-register) a hover region |
| `clear()` | drop all regions (call at the top of each frame) |
| `update(mouse_pos, dt=0.0)` | find the hovered region and ease the tooltip in/out (with a small hover-in delay) |
| `draw(surf)` | render the tooltip card near the cursor, clamped to the screen |
| `hover_id` (property) | the currently-hovered region id, or `None` |
| `visible` (property) | True if a tooltip is currently shown |

`text` may be a plain string **or a zero-arg callable** returning the
current text.  The callable is evaluated lazily in `update` only when the
region is actually hovered, so it is cheap to register many live regions
(e.g. currency pills that show their current value without
re-registering every frame).

## Card style

The card is a small panel (`theme.draw_panel`) with:

* `fill = C.panel`, `border = C.panel_border_hi`, `border_w = 1`,
  `radius = 6` — matches the existing skill-tree hover card.
* The **first wrapped line is the title** (bold, `C.text`); the rest are
  **body** lines (regular, `C.text_dim`).  This mirrors the skill-tree
  tooltip's `name` / `desc` / `cost` / `branch` split without forcing
  callers to pass a structured object — just write a multi-line string.
* Long text is **word-wrapped** to `_MAX_WIDTH` (280 px); very long words
  are hard-broken by character so a giant number cannot overflow.
* The card is offset 16/16 from the cursor so it does not cover the
  pointer, and **clamped to the window** (flipping above the cursor when
  there is no room below, otherwise pinned to the edge).  It never runs
  off-screen.
* A soft **fade-in/out** (eased alpha) plus a small **hover-in delay**
  (`_HOVER_DELAY = 0.18s`) keep the tooltip from flashing on quick flicks
  across regions.

## Constructing and owning the manager

Each screen owns one `TooltipManager`, created in `__init__`:

```python
from ui.tooltip import TooltipManager

class GameScreen:
    def __init__(self, game) -> None:
        ...
        self.tooltips = TooltipManager()
```

A screen that wants to share hover state across sub-views (e.g. a
sub-renderer that draws its own list) can hang the manager on `game`
instead and pass it down — the manager is self-contained and has no
per-screen state beyond the registered regions.

## Per-frame driver

Every screen that uses tooltips runs the same three-step loop in its
`update`/`draw`.  Because layouts change per-frame (buttons move, list
items scroll, currencies update), regions are **re-registered every
frame**:

```python
def update(self, dt):
    ...
    self.tooltips.update(pygame.mouse.get_pos(), dt)

def draw(self, surf):
    ...
    # 1. Re-register hover regions for this frame.
    self.tooltips.clear()
    self.tooltips.register("gold", gold_rect,
        lambda: f"Gold\nDropped by monsters.\nYou have {format_number(state.gold)}.")
    self.tooltips.register("elixir", elixir_rect,
        "Elixir\nPermanent currency from ascension.")
    for b in self.nav_buttons:
        if b.hint:
            self.tooltips.register(f"nav:{b.label}", b.rect, b.hint)
    ...
    # 2. Draw the screen's own content (buttons, lists, ...).
    ...
    # 3. Draw the tooltip last so it sits on top.
    self.tooltips.draw(surf)
```

The `clear()` → re-`register()` pattern keeps the regions in sync with
the live layout at zero bookkeeping cost (a dict + an order list).

## What to register (per screen)

### `GameScreen` (`ui/screen_game.py`)

* **Currency pills** in `_draw_hud`: each `currency_pill(...)` returns
  its width; build a `pygame.Rect` from `(x, y, w, 28)` and register it
  with a callable tooltip describing the currency (e.g.
  `"Gold\nSoft currency dropped by monsters."`).
* **Zone bar**: register the `zb` rect with
  `"Zone progress\nDistance to the next zone."`.
* **Nav buttons**: each `Button` already has a `hint` (or can get one);
  register `f"nav:{label}"` → `b.rect` → `b.hint or label`.
* **Active-skill buttons**: register each with a tooltip describing the
  skill (cooldown, effect).
* **Energy button + bar**: register the energy button rect with a
  tooltip explaining auto-katana, and the energy bar with
  `"Energy\nPowers active skills; regenerates over time."`.

### `SkillTreeScreen` (`ui/screen_skilltree.py`)

Replace the ad-hoc `hover_node` card with the manager:

* Register each node: `self.tooltips.register(f"node:{node.id}", r,
  lambda n=node: self._node_tooltip(n))`.
* `_node_tooltip(node)` returns a multi-line string:
  `f"{node.name}\n{node.desc}\nCost: {node.cost} elixir\nBranch: {node.branch}"`
  (and a "Unlocked" line if `node.id in state.skill_tree`).
* The existing `if self.hover_node:` tooltip block in `draw` is removed;
  the manager renders it instead.  The `hover_node` field can either be
  kept (for click handling) or replaced by reading
  `self.tooltips.hover_id` and stripping the `node:` prefix.

### Other screens (upgrades, buildings, pets, quests, records, ascend)

* **`ScrollList` items**: in each screen that owns a `ScrollList`,
  register the per-item rect (the screen already iterates items to draw
  them, or can read `scroll_list._index_at(pos)`-equivalent rects).
  Register `f"list:{i}"` → item rect → item tooltip text.  The
  `ScrollList` itself can optionally grow a `hint` field on each item
  dict so screens do not have to recompute the text.
* **`Button` hints**: every `Button` with a `hint` should be registered.
  A future refactor can have `Button.draw` register itself with a shared
  manager; until then, screens register their own buttons.
* **Stat bars / currency displays**: register any stat or currency whose
  meaning is not obvious from its label.

## Replacing the `Button.hint` ad-hoc tooltip

`Button` currently renders its own tiny tooltip in `draw` when
`self.hint and self.hover`.  Two integration options:

1. **Leave it** — `Button`'s built-in hint is fine for short, single-line
   hints and does not require a manager.  Screens that want a richer
   tooltip (multi-line, live value) register the button with a
   `TooltipManager` instead and leave `Button.hint` empty.
2. **Unify** — pass the screen's `TooltipManager` into `Button` (e.g. a
   `tooltip_manager=` kwarg) and have `Button.draw` register itself when
   hovered.  This is the cleanest end state but requires touching
   `ui/widgets.py`; the spec leaves this as an optional follow-up so the
   new system can roll out without editing existing files.

Either way, the skill-tree screen's ad-hoc `hover_node` card should be
replaced by the manager (it is the most redundant case — the manager
renders the same card with the same style, plus wrapping and clamping).

## Full draw order (per screen)

1. Background / panels / HUD (unchanged).
2. Re-register hover regions (`clear()` then `register(...)`).
3. Draw the screen's own content (buttons, lists, bars, ...).
4. `self.tooltips.draw(surf)` — the tooltip card on top of everything.

`draw` must be called *after* the screen's own content so the tooltip
sits on top, and *after* `update` so the eased alpha reflects the current
frame.

## Tunables

The manager exposes these constants at the top of `ui/tooltip.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_HOVER_DELAY` | 0.18s | seconds the cursor must rest before the tooltip appears |
| `_FADE_SPEED` | 12.0 | alpha easing speed (higher = snappier) |
| `_PAD_X` / `_PAD_Y` | 10 / 8 | inner card padding |
| `_LINE_GAP` | 2 | pixels between wrapped lines |
| `_MAX_WIDTH` | 280 px | max card width before wrapping kicks in |
| `_OFFSET` | (16, 16) | cursor offset so the card does not cover the pointer |
| `_MARGIN` | 8 | keep this many pixels from the screen edge |

Tune by editing the constants; no other module needs to change.

## Why no per-frame allocations

* The card is rendered onto a **reused scratch surface**
  (`self._card_surf`) that is grown lazily to the largest size seen and
  then reused — never reallocated on a jitter in card height.
* Fonts come from `theme._font` (cached by size+bold), so the title and
  body fonts are shared across the whole UI.
* Wrapped lines for the current hover region are **cached** on the
  manager (`_cached_id` / `_cached_text` / `_cached_lines`) and only
  re-wrapped when the region or its text changes — not every frame.
* `register`/`clear` reuse the same dict and order list; the per-frame
  re-registration is just dict inserts, no allocation of new containers.

## Save compatibility

The tooltip system is purely visual and holds no persistent state —
nothing to save.  It is safe to construct on every screen entry and
discard on exit; the tooltip simply disappears if the screen is left
mid-hover.
