"""Pet detail + bonding panel for the Pets screen.

A side panel shown when the player selects a pet in the collection grid.
It surfaces everything worth knowing about a single pet at a glance:

  * a large sprite (cached ``pet_surface`` scaled up),
  * the pet's name, type, and buff description,
  * the current bond level (0..10) with a progress bar,
  * the bonus value contributed *at the current bond*,
  * a **Feed** button that spends gold to raise bond (cost scales with
    the bond level: ``bond ** 1.5 * 100`` gold), and
  * an **Equip / Unequip** button reflecting the current equip state.

The panel is self-contained: it owns a feed button and an equip button
(both ``ui.widgets.Button``), reads state through the ``game`` handle,
and persists changes via ``state.save()``.

All rendering uses pygame primitives + the cached theme fonts and the
cached ``assets.pet_surface``.  No per-frame allocations happen in
``draw`` once the panel has been constructed: the scaled sprite is
cached on the instance (keyed by ``(pid, size)``), and the only objects
created per call are the small ``pygame.Rect`` literals used to lay out
the panel — those are cheap and local to the draw function.

Integration (see ``docs/specs/pet_detail.md``):

    from ui.pet_detail import PetDetailPanel
    panel = PetDetailPanel(rect, game)
    panel.set_pet(pid)          # None hides the panel
    panel.handle(event)         # call before the grid so it can swallow
    panel.update(dt)
    panel.draw(surf)            # draws nothing if no pet is set

The panel is inactive until ``set_pet`` is called with a real pet id.
``handle`` returns ``True`` if it consumed the event (a button click or
a click inside the panel) so the screen can avoid also toggling equip on
the underlying grid card.
"""
from __future__ import annotations

import pygame

from theme import (
    C, font_xs, font_sm, font_md, font_lg, font_xl,
    draw_text, draw_text_center, draw_panel, draw_bar,
)
from ui.widgets import Button
from utils import format_number
from data import pets as pet_def


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
BOND_MAX = 10
# Feed cost curve: gold = bond ** 1.5 * 100.  Bond 0 -> 100, 1 -> 100,
# 2 -> ~283, 5 -> ~1118, 9 -> ~2700.  Raising the last level (9 -> 10)
# costs ~3000 gold.
FEED_COST_BASE = 100.0
FEED_COST_EXP = 1.5


def feed_cost(bond: int) -> int:
    """Gold required to raise bond from ``bond`` to ``bond + 1``.

    Bond is the *current* level; the cost of the next level scales as
    ``bond ** 1.5 * 100``.  At bond 0 the literal formula would yield 0
    (a free first feed), so we clamp the base to ``max(bond, 1)`` — the
    first feed costs 100 gold and the curve then follows the spec for
    bond >= 1.
    """
    if bond >= BOND_MAX:
        return 0
    base = bond if bond > 0 else 1
    return int(round(FEED_COST_BASE * (base ** FEED_COST_EXP)))


# ---------------------------------------------------------------------------
# Buff-key human descriptions (mirrors the engine's effect-key semantics
# so the panel can describe what each pet actually does).
# ---------------------------------------------------------------------------
_PCT_KEYS = {
    "gold_pct", "crit_dmg_pct", "speed_pct", "gps_pct",
    "upgrade_cost_pct", "building_cost_pct", "quest_reward_pct",
    "firefly_spawn", "energy_regen", "elixir_pct",
    "firefly_gold", "firefly_value",
}


def _buff_desc(pet: pet_def.PetDef) -> str:
    """A one-line description of what the pet's buff does per bond level."""
    key = pet.buff_key
    val = pet.buff_per_level
    # Most pet buffs are percentages; a couple are flat-ish multipliers
    # expressed as fractions.  We display them all as a signed percent
    # for readability, except the cost-reduction keys which read better
    # as "-X% cost".
    sign = "+" if val >= 0 else "-"
    pct = int(round(abs(val) * 100))
    if key in ("upgrade_cost_pct", "building_cost_pct"):
        return f"{sign}{pct}% upgrade cost per bond."
    if key == "firefly_value":
        return f"{sign}{pct}% firefly value per bond."
    if key == "firefly_gold":
        return f"{sign}{pct}% firefly gold per bond."
    if key == "firefly_spawn":
        return f"{sign}{pct}% firefly spawn rate per bond."
    if key == "energy_regen":
        return f"{sign}{pct}% energy regen per bond."
    if key == "elixir_pct":
        return f"{sign}{pct}% elixir gain per bond."
    if key == "gps_pct":
        return f"{sign}{pct}% building gold/sec per bond."
    if key == "gold_pct":
        return f"{sign}{pct}% gold from enemies per bond."
    if key == "crit_dmg_pct":
        return f"{sign}{pct}% crit damage per bond."
    if key == "speed_pct":
        return f"{sign}{pct}% move speed per bond."
    if key == "quest_reward_pct":
        return f"{sign}{pct}% quest rewards per bond."
    # Fallback: show the raw key + value.
    return f"{key} +{val:g} per bond."


def _bonus_value_text(pet: pet_def.PetDef, bond: int, stars: int = 0,
                     prestiges: int = 0) -> str:
    """The bonus value contributed at ``bond`` (+ stars + prestiges), for display."""
    val = pet_def.pet_bonus(pet, bond, stars, prestiges)
    key = pet.buff_key
    if key in _PCT_KEYS:
        sign = "+" if val >= 0 else "-"
        return f"{sign}{int(round(abs(val) * 100))}%"
    return f"+{val:g}"


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
class PetDetailPanel:
    """Right-side detail + bonding panel for a single pet.

    Construct once with a rect (the area the panel may occupy) and the
    game handle.  ``set_pet`` selects which pet to show (or ``None`` to
    hide the panel).  The panel owns its two buttons and refreshes their
    labels / enabled state each ``update``.
    """

    def __init__(self, rect: pygame.Rect, game) -> None:
        self.rect = pygame.Rect(rect)
        self.game = game
        self.pid: str | None = None
        # Scaled-sprite cache: (pid, size) -> Surface.  Reused across
        # frames so draw does not allocate.
        self._sprite_cache: dict[tuple[str, int], pygame.Surface] = {}
        # Buttons — laid out relative to the panel rect.
        bx = self.rect.x + 16
        bw = self.rect.w - 32
        by_feed = self.rect.y + 320
        by_equip = self.rect.y + 372
        self.btn_feed = Button(
            (bx, by_feed, bw, 44),
            "Feed",
            on_click=self._feed,
            color=(90, 60, 130),
        )
        self.btn_equip = Button(
            (bx, by_equip, bw, 44),
            "Equip",
            on_click=self._toggle_equip,
            color=C.btn,
        )
        self.buttons: list[Button] = [self.btn_feed, self.btn_equip]
        # Whether the panel currently consumes clicks inside its rect
        # (always True when a pet is set, so the grid underneath does
        # not also toggle equip).
        self._active = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_pet(self, pid: str | None) -> None:
        """Select which pet to display.  ``None`` hides the panel."""
        self.pid = pid
        self._active = pid is not None

    @property
    def active(self) -> bool:
        return self._active

    def handle(self, event: pygame.event.Event) -> bool:
        """Consume the event if it lands on the panel or its buttons.

        Returns True if the event was consumed so the caller can skip
        its own grid handling.  When no pet is set the panel is inert
        and returns False.
        """
        if not self._active or self.pid is None:
            return False
        # Let the buttons see the event first.
        consumed = False
        for b in self.buttons:
            if b.handle(event):
                consumed = True
        # Swallow any other click that lands inside the panel so the grid
        # underneath does not also toggle equip on the selected card.
        if (not consumed
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos)):
            return True
        return consumed

    def update(self, dt: float) -> None:
        if not self._active or self.pid is None:
            for b in self.buttons:
                b.update(dt)
            return
        state = self.game.state
        pet = pet_def.BY_ID.get(self.pid)
        if pet is None or self.pid not in state.pets:
            # Not owned — disable both buttons; keep labels short.
            self.btn_feed.enabled = False
            self.btn_feed.label = "Feed"
            self.btn_equip.enabled = False
            self.btn_equip.label = "Not owned"
            for b in self.buttons:
                b.update(dt)
            return
        bond = state.pet_bond(self.pid)
        equipped = self.pid in state.equipped_pets
        # Feed button: disabled at max bond, else enabled iff affordable.
        if bond >= BOND_MAX:
            self.btn_feed.enabled = False
            self.btn_feed.label = "Max bond"
        else:
            cost = feed_cost(bond)
            can_afford = state.gold >= cost
            self.btn_feed.enabled = can_afford
            self.btn_feed.label = f"Feed  ({format_number(cost)} g)"
        # Equip button: always enabled while owned (toggle label).
        self.btn_equip.enabled = True
        if equipped:
            self.btn_equip.label = "Unequip"
            self.btn_equip.color = (140, 60, 80)
        else:
            self.btn_equip.label = "Equip"
            self.btn_equip.color = C.btn
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf: pygame.Surface) -> None:
        if not self._active or self.pid is None:
            return
        state = self.game.state
        pet = pet_def.BY_ID.get(self.pid)
        if pet is None:
            return
        r = self.rect

        # Panel frame.
        draw_panel(surf, r, fill=C.panel, border=C.panel_border_hi,
                   border_w=2, radius=12)

        owned = self.pid in state.pets
        unlocked = pet_def.is_unlocked(pet, state)
        equipped = self.pid in state.equipped_pets

        # ---- Sprite (cached, scaled up from the 48px pet_surface) ----
        sprite = self._scaled_sprite(pet, 96)
        sx = r.centerx - sprite.get_width() // 2
        sy = r.y + 16
        surf.blit(sprite, (sx, sy))

        # ---- Name + type ----
        draw_text_center(surf, pet.name, (r.centerx, r.y + 128),
                         font_lg(bold=True), C.text)
        draw_text_center(surf, pet.ptype.capitalize(),
                         (r.centerx, r.y + 156), font_xs(), C.text_dim)

        # ---- Lock / not-owned banner ----
        if not unlocked:
            draw_text_center(surf, "Locked", (r.centerx, r.y + 180),
                             font_sm(bold=True), C.text_muted)
            draw_text_center(surf, pet.unlock, (r.centerx, r.y + 200),
                             font_xs(), C.text_muted)
            # Disable the buttons visually by drawing them dim.
            for b in self.buttons:
                b.draw(surf)
            return
        if not owned:
            draw_text_center(surf, "Not owned yet",
                             (r.centerx, r.y + 180),
                             font_sm(bold=True), C.text_muted)
            draw_text_center(surf, "Pull in the gacha to collect.",
                             (r.centerx, r.y + 200),
                             font_xs(), C.text_muted)
            for b in self.buttons:
                b.draw(surf)
            return

        # ---- Buff description ----
        draw_text_center(surf, _buff_desc(pet),
                         (r.centerx, r.y + 184), font_sm(), C.text)
        # Flavor desc (the data row's desc).
        draw_text_center(surf, pet.desc,
                         (r.centerx, r.y + 204), font_xs(), C.text_dim)

        # ---- Bond level + progress bar ----
        bond = state.pet_bond(self.pid)
        draw_text(surf, "Bond", (r.x + 16, r.y + 232),
                  font_sm(bold=True), C.text)
        draw_text(surf, f"{bond}/{BOND_MAX}",
                  (r.right - 64, r.y + 232),
                  font_sm(bold=True), C.text)
        bar = pygame.Rect(r.x + 16, r.y + 252, r.w - 32, 14)
        draw_bar(surf, bar, bond / BOND_MAX,
                 fill=C.soul, bg=C.mp_bg, border=C.panel_border)

        # ---- Bonus value at current bond (+ stars + prestiges) ----
        stars = state.pet_stars.get(self.pid, 0)
        prestiges = state.pet_prestiges.get(self.pid, 0)
        draw_text(surf, "Bonus", (r.x + 16, r.y + 276),
                  font_sm(), C.text_dim)
        draw_text(surf, _bonus_value_text(pet, bond, stars, prestiges),
                  (r.right - 96, r.y + 276),
                  font_sm(bold=True), C.soul)

        # ---- Equip state tag ----
        if equipped:
            draw_text(surf, "EQUIPPED", (r.x + 16, r.y + 296),
                      font_xs(bold=True), C.gold)
        else:
            draw_text(surf, "not equipped", (r.x + 16, r.y + 296),
                      font_xs(), C.text_muted)

        # ---- Buttons ----
        for b in self.buttons:
            b.draw(surf)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _scaled_sprite(self, pet: pet_def.PetDef, size: int) -> pygame.Surface:
        """Return a cached, scaled-up pet sprite.

        ``assets.pet_surface`` is already cached by ``(pid, size)``, so
        we just request the larger size directly — no per-frame
        allocation, no smoothscale needed.
        """
        key = (pet.id, size)
        cached = self._sprite_cache.get(key)
        if cached is not None:
            return cached
        from assets import pet_surface
        surf = pet_surface(pet.id, pet.hue, size)
        self._sprite_cache[key] = surf
        return surf

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------
    def _feed(self) -> None:
        if self.pid is None:
            return
        state = self.game.state
        if self.pid not in state.pets:
            return
        bond = state.pet_bond(self.pid)
        if bond >= BOND_MAX:
            return
        cost = feed_cost(bond)
        if state.gold < cost:
            return
        state.gold -= cost
        state.pets[self.pid] = min(BOND_MAX, bond + 1)
        state.save()
        from assets import play
        play("gacha", state.sound_on)

    def _toggle_equip(self) -> None:
        if self.pid is None:
            return
        state = self.game.state
        if self.pid not in state.pets:
            return
        if self.pid in state.equipped_pets:
            state.unequip_pet(self.pid)
        else:
            state.equip_pet(self.pid)
        state.save()
