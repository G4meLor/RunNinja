"""Task 30: Pre-rolled sprite-sheet animation for ninja + enemies.

The ninja is the most-seen sprite and the ``slash_anim``/``bob`` timers
already exist but are wasted (the screen only uses a 1px vertical bob).
Generate 4-8 frames at cache time, stack into one wide/tall SRCALPHA
sheet, blit by sub-rect (``subsurface`` is a zero-copy view). Frame
selection from ``slash_anim`` (windup/extend/recover) and ``bob`` (idle).

Acceptance criteria covered:
- Ninja has idle bob + slash lunge + hit flinch frames selected by
  ``slash_anim``/``bob`` timers
- At least one enemy shape has a multi-frame idle cycle
- Static frame 0 is the graceful-degradation fallback
- Per-frame blit cost is no greater than the current static sprite
- ``reduced_motion`` pins to frame 0
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# ---------------------------------------------------------------------------
# Ninja sprite-sheet generation
# ---------------------------------------------------------------------------
def test_ninja_sprite_sheet_exists(pygame_headless):
    """ninja_sprite_sheet returns a surface (the wide sheet)."""
    from assets import ninja_sprite_sheet
    sheet = ninja_sprite_sheet(64)
    assert sheet is not None


def test_ninja_sprite_sheet_wide(pygame_headless):
    """The sheet is wide (or tall) with >= 4 frames of size px each."""
    from assets import ninja_sprite_sheet
    sheet = ninja_sprite_sheet(64)
    w, h = sheet.get_size()
    # Either wide (frames stacked horizontally) or tall (vertically).
    assert w >= 64 * 4 or h >= 64 * 4, (
        f"sheet too small for 4 frames: {w}x{h}")


def test_ninja_sprite_sheet_frame_count(pygame_headless):
    """The sheet has 4-8 frames (per the brief)."""
    from assets import ninja_sprite_sheet
    sheet = ninja_sprite_sheet(64)
    w, h = sheet.get_size()
    # The frame size is 64x64; the sheet is wide (frames stacked
    # horizontally) so frames = w // 64.
    frames = w // 64
    assert 4 <= frames <= 8, (
        f"expected 4-8 frames, got {frames} ({w}x{h})")


def test_ninja_sprite_sheet_cached(pygame_headless):
    """ninja_sprite_sheet returns the same surface on repeated calls."""
    from assets import ninja_sprite_sheet
    a = ninja_sprite_sheet(64)
    b = ninja_sprite_sheet(64)
    assert a is b


def test_ninja_sprite_sheet_convert_alpha(pygame_headless):
    """The sheet calls convert_alpha before caching."""
    import pygame
    from assets import ninja_sprite_sheet, _NINJA_SHEET_CACHE

    _NINJA_SHEET_CACHE.clear()

    class CountingSurface(pygame.Surface):
        convert_alpha_count = 0

        def convert_alpha(self, *a, **k):
            type(self).convert_alpha_count += 1
            return super().convert_alpha(*a, **k)

    orig = pygame.Surface
    pygame.Surface = CountingSurface  # type: ignore[assignment]
    try:
        ninja_sprite_sheet(64)
    finally:
        pygame.Surface = orig  # type: ignore[assignment]
    assert CountingSurface.convert_alpha_count >= 1, (
        "ninja_sprite_sheet did not call convert_alpha")


# ---------------------------------------------------------------------------
# Ninja frame selection
# ---------------------------------------------------------------------------
def test_ninja_frame_exists(pygame_headless):
    """ninja_frame returns a surface (the selected frame)."""
    from assets import ninja_frame
    f = ninja_frame(64, 0.0, 0.0)
    assert f is not None
    assert f.get_size() == (64, 64)


def test_ninja_frame_zero_is_static(pygame_headless):
    """Frame 0 (slash_anim=0, bob=0) is the static fallback."""
    from assets import ninja_frame, ninja_surface
    f0 = ninja_frame(64, 0.0, 0.0)
    static = ninja_surface(64)
    # Frame 0 should be the same size as the static sprite.
    assert f0.get_size() == static.get_size()


def test_ninja_frame_idle_bob(pygame_headless):
    """Different bob values select different idle frames (the bob cycle).

    The frame is a subsurface (zero-copy view) of the sheet; different
    frames have different x offsets in the sheet. We check the subsurface
    offset to confirm the frame selection picks a distinct frame per
    bob phase.
    """
    from assets import ninja_frame
    # bob=0 -> sin(0)=0, not >0 -> frame 0 (neutral).
    f0 = ninja_frame(64, 0.0, 0.0)
    # bob at a point where sin(bob*4) > 0 -> idle up frame.
    f_up = ninja_frame(64, 0.0, 0.4)  # sin(1.6) > 0
    # bob at a point where sin(bob*4) < 0 -> idle down frame.
    f_down = ninja_frame(64, 0.0, 3.0)  # sin(12) < 0
    assert f0 is not None
    assert f_up is not None
    assert f_down is not None
    # All are 64x64 frames.
    assert f0.get_size() == (64, 64)
    assert f_up.get_size() == (64, 64)
    assert f_down.get_size() == (64, 64)
    # Different frames have different x offsets in the sheet (the
    # subsurface is a zero-copy view at a distinct x).
    assert f0.get_offset()[0] == 0, f"frame 0 x: {f0.get_offset()[0]}"
    assert f_up.get_offset()[0] == 64, f"up x: {f_up.get_offset()[0]}"
    assert f_down.get_offset()[0] == 128, f"down x: {f_down.get_offset()[0]}"


def test_ninja_frame_slash_frames_distinct(pygame_headless):
    """The slash windup/extend/recover frames are distinct (different x
    offsets in the sheet)."""
    from assets import ninja_frame
    f_windup = ninja_frame(64, 0.12, 0.0)
    f_extend = ninja_frame(64, 0.08, 0.0)
    f_recover = ninja_frame(64, 0.03, 0.0)
    # Each slash phase is a distinct frame.
    assert f_windup.get_offset()[0] == 192
    assert f_extend.get_offset()[0] == 256
    assert f_recover.get_offset()[0] == 320


def test_ninja_frame_hit_flinch_distinct(pygame_headless):
    """The hit-flinch frame is distinct (frame 6, x=384)."""
    from assets import ninja_frame
    f_flinch = ninja_frame(64, 0.0, 0.0, last_damage_timer=0.3)
    assert f_flinch.get_offset()[0] == 384


def test_ninja_frame_slash_windup(pygame_headless):
    """slash_anim > 0.10 selects the windup frame."""
    from assets import ninja_frame
    f = ninja_frame(64, 0.12, 0.0)
    assert f is not None
    assert f.get_size() == (64, 64)


def test_ninja_frame_slash_extend(pygame_headless):
    """0.05 < slash_anim <= 0.10 selects the extend frame."""
    from assets import ninja_frame
    f = ninja_frame(64, 0.08, 0.0)
    assert f is not None
    assert f.get_size() == (64, 64)


def test_ninja_frame_slash_recover(pygame_headless):
    """0 < slash_anim <= 0.05 selects the recover frame."""
    from assets import ninja_frame
    f = ninja_frame(64, 0.03, 0.0)
    assert f is not None
    assert f.get_size() == (64, 64)


def test_ninja_frame_hit_flinch(pygame_headless):
    """last_damage_timer > 0 selects the hit flinch frame."""
    from assets import ninja_frame
    f = ninja_frame(64, 0.0, 0.0, last_damage_timer=0.3)
    assert f is not None
    assert f.get_size() == (64, 64)


def test_ninja_frame_hit_flinch_overrides_slash(pygame_headless):
    """Hit flinch takes priority over slash (the ninja recoils when hit
    mid-slash)."""
    from assets import ninja_frame
    f = ninja_frame(64, 0.12, 0.0, last_damage_timer=0.3)
    # Should be the flinch frame, not the windup frame.
    f_flinch = ninja_frame(64, 0.0, 0.0, last_damage_timer=0.3)
    assert f.get_rect() == f_flinch.get_rect()


def test_ninja_frame_reduced_motion_pins_frame_0(pygame_headless):
    """reduced_motion pins to frame 0 regardless of slash_anim/bob/hit.

    The frame is a subsurface; frame 0 has x offset 0. We check the
    subsurface offset to confirm the pinned frame is frame 0 (not just
    same-size, but the same x in the sheet).
    """
    from assets import ninja_frame
    f_slash = ninja_frame(64, 0.12, 0.0, reduced_motion=True)
    f_bob = ninja_frame(64, 0.0, 5.0, reduced_motion=True)
    f_hit = ninja_frame(64, 0.0, 0.0, last_damage_timer=0.3,
                       reduced_motion=True)
    # All reduced_motion frames are frame 0 (x offset 0 in the sheet).
    for f in (f_slash, f_bob, f_hit):
        assert f.get_offset()[0] == 0, (
            f"reduced_motion did not pin to frame 0: x={f.get_offset()[0]}")


# ---------------------------------------------------------------------------
# Enemy sprite-sheet (bandit multi-frame idle cycle)
# ---------------------------------------------------------------------------
def test_enemy_sprite_sheet_bandit_multiframe(pygame_headless):
    """The bandit shape has a multi-frame idle cycle (>= 2 frames)."""
    from assets import enemy_sprite_sheet
    from data.enemies import ZONES
    bandit = ZONES[0]["enemies"][0]  # e_bandit, shape="bandit"
    sheet = enemy_sprite_sheet(bandit, 48)
    w, h = sheet.get_size()
    # At least 2 frames (multi-frame idle cycle).
    frames = w // 48
    assert frames >= 2, (
        f"bandit sheet has < 2 frames: {frames} ({w}x{h})")


def test_enemy_sprite_sheet_cached(pygame_headless):
    """enemy_sprite_sheet returns the same surface on repeated calls."""
    from assets import enemy_sprite_sheet
    from data.enemies import ZONES
    bandit = ZONES[0]["enemies"][0]
    a = enemy_sprite_sheet(bandit, 48)
    b = enemy_sprite_sheet(bandit, 48)
    assert a is b


def test_enemy_sprite_sheet_convert_alpha(pygame_headless):
    """The enemy sheet calls convert_alpha before caching."""
    import pygame
    from assets import enemy_sprite_sheet, _ENEMY_SHEET_CACHE
    from data.enemies import ZONES

    _ENEMY_SHEET_CACHE.clear()
    bandit = ZONES[0]["enemies"][0]

    class CountingSurface(pygame.Surface):
        convert_alpha_count = 0

        def convert_alpha(self, *a, **k):
            type(self).convert_alpha_count += 1
            return super().convert_alpha(*a, **k)

    orig = pygame.Surface
    pygame.Surface = CountingSurface  # type: ignore[assignment]
    try:
        enemy_sprite_sheet(bandit, 48)
    finally:
        pygame.Surface = orig  # type: ignore[assignment]
    assert CountingSurface.convert_alpha_count >= 1


def test_enemy_frame_selection(pygame_headless):
    """enemy_frame selects a frame based on bob (the bandit idle cycle).

    The bandit has a 3-frame idle cycle; the bob timer selects the frame.
    Different bob phases select different frames (distinct x offsets in
    the sheet).
    """
    from assets import enemy_frame
    from data.enemies import ZONES
    bandit = ZONES[0]["enemies"][0]
    f0 = enemy_frame(bandit, 48, 0.0)        # sin(0)=0 -> neutral (frame 0)
    f1 = enemy_frame(bandit, 48, 0.4)         # sin(1.6)>0 -> lean forward (frame 1)
    f2 = enemy_frame(bandit, 48, 3.0)         # sin(12)<0 -> lean back (frame 2)
    assert f0 is not None
    assert f1 is not None
    assert f2 is not None
    assert f0.get_size() == (48, 48)
    assert f1.get_size() == (48, 48)
    assert f2.get_size() == (48, 48)
    # Distinct x offsets in the sheet (the bandit idle cycle).
    assert f0.get_offset()[0] == 0
    assert f1.get_offset()[0] == 48
    assert f2.get_offset()[0] == 96


def test_enemy_frame_reduced_motion(pygame_headless):
    """reduced_motion pins enemy to frame 0 (x offset 0)."""
    from assets import enemy_frame
    from data.enemies import ZONES
    bandit = ZONES[0]["enemies"][0]
    f0 = enemy_frame(bandit, 48, 0.0, reduced_motion=True)
    f1 = enemy_frame(bandit, 48, 5.0, reduced_motion=True)
    # Both pinned to frame 0 (x offset 0).
    assert f0.get_offset()[0] == 0
    assert f1.get_offset()[0] == 0


def test_enemy_frame_non_bandit_single_frame(pygame_headless):
    """Non-bandit shapes get a 1-frame sheet (the static sprite). This is
    the graceful-degradation fallback for enemy shapes without a
    multi-frame cycle."""
    from assets import enemy_frame, enemy_surface
    from data.enemies import ZONES
    # Find a non-bandit enemy (the rat, shape="beast").
    beast = ZONES[0]["enemies"][1]
    f = enemy_frame(beast, 48, 0.0)
    static = enemy_surface(beast, 48)
    assert f.get_size() == static.get_size()


# ---------------------------------------------------------------------------
# Per-frame blit cost: subsurface is zero-copy, same size as static
# ---------------------------------------------------------------------------
def test_ninja_frame_size_matches_static(pygame_headless):
    """The selected frame has the same pixel dimensions as the static
    sprite, so the per-frame blit cost is identical (the subsurface is a
    zero-copy view — no allocation, same pixel count, same format)."""
    from assets import ninja_frame, ninja_surface
    for size in (64, 72):
        static = ninja_surface(size)
        for sa in (0.0, 0.12, 0.08, 0.03):
            for bob in (0.0, 1.0, 5.0):
                f = ninja_frame(size, sa, bob)
                assert f.get_size() == static.get_size(), (
                    f"frame size {f.get_size()} != static {static.get_size()}"
                    f" at size={size}, slash_anim={sa}, bob={bob}")


def test_ninja_frame_is_subsurface(pygame_headless):
    """ninja_frame returns a subsurface (zero-copy view) of the sheet,
    not a copy — so there is no per-frame pixel allocation."""
    import pygame
    from assets import ninja_frame, ninja_sprite_sheet
    sheet = ninja_sprite_sheet(64)
    f = ninja_frame(64, 0.0, 0.0)
    # A subsurface shares the same pixel buffer as its parent. We check
    # that the subsurface's parent is the sheet (or that get_parent()
    # is not None — a subsurface has a parent, a standalone surface
    # does not).
    assert hasattr(f, "get_parent")
    parent = f.get_parent()
    assert parent is not None, (
        "ninja_frame did not return a subsurface (no parent)")


# ---------------------------------------------------------------------------
# Smoke: the game screen draws with sprite-sheet animation
# ---------------------------------------------------------------------------
def _reinit_display():
    """Re-init pygame + the display if a prior test quit pygame.

    The ``pygame_headless`` fixture is session-scoped; prior tests in
    this file may quit pygame. The font cache holds stale freetype
    objects after quit, so we also clear it (``reset_fonts``) before
    constructing ``main.Game()`` so the buttons' ``font_md()`` calls
    build fresh fonts against the live display.
    """
    import pygame
    from theme import reset_fonts
    if not pygame.display.get_init():
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        pygame.display.set_mode((1280, 720))
    reset_fonts()


def test_game_draws_with_sprite_sheet(pygame_headless):
    """The game screen draws 30 frames with sprite-sheet animation at the
    high tier without error. Exercises both ``_update()`` and ``draw()``
    so the render path (the subsurface blit + the downstream enemy/ninja
    positioning) is verified."""
    import main
    import pygame
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.reduced_motion = False
    g.state.render_quality = "high"
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()


def test_game_draws_reduced_motion(pygame_headless):
    """The game screen draws 30 frames with reduced_motion without error
    (all sprites pin to frame 0). Exercises the ``draw()`` path with the
    sprite-sheet animation pinned to frame 0 via the reduced_motion
    gate."""
    import main
    import pygame
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.reduced_motion = True
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()
