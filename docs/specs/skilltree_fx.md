# Skill-tree unlock juice — integration spec

A new module, `ui/skilltree_fx.py` (`SkillTreeFxSystem`), adds **unlock
juice** to the elixir skill tree: when a node is unlocked it pulses with its
branch color, an expanding ring radiates from it, the connected prereq
edges glow briefly, and a floating "+effect" text rises from the node.
While the player hovers a **locked-but-unlockable** node, a glowing path is
drawn from the branch root down to that node through its prereq chain.

All rendering uses pygame primitives.  The fx system keeps fixed pools of
effect slots and reusable scratch surfaces, so the per-frame hot path
performs zero allocations once warm.

## The system

`SkillTreeFxSystem` exposes:

| method | purpose |
|--------|---------|
| `on_unlock(node_id, rect, branch_color, effect_text=None)` | fire the juice (pulse + ring + glowing prereq edges + floating text) |
| `update(dt)` | advance all active effects; retire expired ones |
| `draw(surf)` | draw the pulse rings, node-frame pulses, and floating text |
| `highlight_path(node_id, node_rects, unlocked)` | return a list of `(rect, alpha)` tracing the root→node path (see below) |
| `line_glow_alpha(node_id)` | alpha (0..255) for the incoming edge of `node_id` while glowing |
| `node_pulse_scale(node_id)` | scale factor (1.0 = none) for the node frame while pulsing |

`highlight_path` returns a system-owned list (reused across calls — the
caller must read it immediately, not retain it).  Each entry is a
`(pygame.Rect, int_alpha)` pair: the screen draws a glowing outline at
that rect with that alpha, so the path shimmers as a sin wave flows down
the chain.

## Constructing and owning the system

`SkillTreeScreen` owns one instance, created in `__init__`:

```python
from ui.skilltree_fx import SkillTreeFxSystem

class SkillTreeScreen:
    def __init__(self, game) -> None:
        ...
        self.fx = SkillTreeFxSystem()
```

(If you prefer, hang it on `game` instead and share it across screens —
the system is self-contained and has no per-screen state beyond the
active effects.)

## Wiring the trigger

In `SkillTreeScreen.handle`, after a successful unlock, fire the juice:

```python
elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
    if self.hover_node:
        state = self.game.state
        if skill_unlock.can_unlock(state, self.hover_node):
            ok = skill_unlock.unlock(state, self.hover_node)
            if ok:
                self.game.state.save()
                node = st.BY_ID[self.hover_node]
                rect = self.node_rects[self.hover_node]
                self.fx.on_unlock(
                    node.id, rect, st.branch_color(node.branch),
                    effect_text=self._effect_label(node),
                )
```

A helper for the floating label (optional — `on_unlock` synthesizes one
if `effect_text` is omitted):

```python
def _effect_label(self, node) -> str:
    if node.effect_key.startswith("unlock_"):
        return "Unlocked!"
    if "pct" in node.effect_key:
        return f"+{int(round(node.effect_value * 100))}%"
    if node.effect_key == "energy_timer":
        return f"+{int(node.effect_value)}s"
    return f"+{node.effect_value:g}"
```

## Wiring the update

In `SkillTreeScreen.update`, advance the fx:

```python
def update(self, dt):
    for b in self.buttons:
        b.update(dt)
    self.fx.update(dt)
```

## Wiring the draw

In `SkillTreeScreen.draw`, three integration points:

### 1. Glowing prereq edges

When drawing the line from a node's prereq, blend in the line-glow alpha.
Inside the per-node loop, where the prereq line is currently drawn:

```python
if node.prereq and node.prereq in self.node_rects:
    pr = self.node_rects[node.prereq]
    base_col = col if node.id in state.skill_tree else C.panel_border
    glow = self.fx.line_glow_alpha(node.id)
    if glow > 0:
        # Blend toward the branch color while the edge is glowing.
        base_col = _blend(base_col, col, glow / 255.0)
        pygame.draw.line(surf, base_col,
                         (pr.centerx, pr.bottom), (r.centerx, r.top),
                         2 + (2 if glow > 120 else 1))
    else:
        pygame.draw.line(surf, base_col,
                         (pr.centerx, pr.bottom), (r.centerx, r.top), 2)
```

`_blend` is a tiny module-level helper (or use `utils.lerp_color`):

```python
def _blend(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))
```

### 2. Node-frame pulse

When drawing a node that is pulsing, inflate its rect by the pulse scale:

```python
scale = self.fx.node_pulse_scale(node.id)
if scale != 1.0:
    dw = int(r.w * (scale - 1.0))
    dh = int(r.h * (scale - 1.0))
    r = r.inflate(dw, dh)
# then draw the node panel as usual with the (possibly inflated) r
```

### 3. Path highlight on hover

After the per-branch loop, if the hovered node is locked but unlockable,
draw the glowing path rects:

```python
if self.hover_node:
    node = st.BY_ID[self.hover_node]
    if node.id not in state.skill_tree and skill_unlock.can_unlock(state, node.id):
        path = self.fx.highlight_path(
            node.id, self.node_rects, state.skill_tree)
        col = st.branch_color(node.branch)
        for rect, alpha in path:
            # Soft glowing outline around each node on the path.
            glow_surf = pygame.Surface(
                (rect.w + 8, rect.h + 8), pygame.SRCALPHA)
            pygame.draw.rect(
                glow_surf, (*col, alpha),
                glow_surf.get_rect(), 2, border_radius=10)
            surf.blit(glow_surf, (rect.x - 4, rect.y - 4))
```

(The `glow_surf` allocation in the snippet is per-frame; a production
version should reuse a scratch surface.  The path is usually <6 nodes so
the cost is tiny, but a reusable surface on the screen object is cleaner.)

### 4. Draw the fx layer

Finally, after the screen has drawn its own content (so the fx render on
top), call:

```python
self.fx.draw(surf)
```

This draws the expanding rings, node-frame pulses, and floating "+effect"
texts.  The order matters: draw the fx *after* the node panels and edges
so the juice overlays them.

## Full draw order

1. Background gradient + title + currency pill (unchanged).
2. Per-branch: header, then for each node:
   a. draw the prereq line (with line-glow blend),
   b. draw the node panel (with pulse scale if active),
   c. draw the node text + cost.
3. Path highlight (if hovering a locked-but-unlockable node).
4. Hover tooltip (unchanged).
5. `self.fx.draw(surf)` — rings, frame pulses, floating text on top.
6. Buttons (unchanged).

## Tunables

The fx module exposes these constants at the top of `ui/skilltree_fx.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_PULSE_DUR` | 0.45s | node pulse + frame-pulse duration |
| `_RING_DUR` | 0.55s | expanding ring duration |
| `_RING_MAX_R` | 70px | peak ring radius |
| `_LINE_GLOW_DUR` | 0.40s | prereq edge glow duration |
| `_FLOAT_DUR` | 0.90s | floating text lifetime |
| `_FLOAT_RISE` | 38px | pixels the text rises |
| `_MAX_PULSES` | 8 | pulse slot pool size |
| `_MAX_FLOATS` | 8 | floating text slot pool size |
| `_MAX_LINE_GLOWS` | 24 | line-glow slot pool size |

Tune by editing the constants; no other module needs to change.

## Why no per-frame allocations

* Effect slots (`_Pulse`, `_FloatText`, `_LineGlow`) are stored in fixed
  lists, recycled via `_next_free` (oldest slot reused if pool is full).
* The expanding ring, node-frame outline, and (optionally) the text fade
  use reusable scratch surfaces stored on the system instance; they are
  grown lazily to fit the largest node and then reused.
* `highlight_path` returns a system-owned `_path_buf` list that is
  cleared and refilled each call — never re-allocated.
* `font_sm(bold=True)` is cached by `theme._font`, so the floating text
  does not create a new font object per frame.

## Save compatibility

The fx system is purely visual and holds no persistent state — nothing
to save.  It is safe to construct on every screen entry and discard on
exit; effects simply stop if the screen is left mid-animation.
