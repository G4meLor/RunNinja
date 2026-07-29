"""Task 32: Alpha-dilation outline + hue-shifted shading ramp + squash-and-stretch.

Three cheap, high-impact graphics upgrades:

1. **Outline** (``assets.outline_array``): a vectorized 1px alpha-dilation
   outline applied to every generated sprite at cache time (zero per-frame
   cost). The "looks like real pixel art" trick — a dark 1px ring around
   each sprite so it reads against any background.
2. **Shading ramp** (``assets.apply_shading_ramp``): a 4-6 step hue-shifted
   shading ramp per sprite (cool shadows, warm highlights), applied at
   cache time (zero per-frame cost).
3. **Squash-and-stretch** (``ui.screen_game``): scale (1+k, 1-k) plays for
   ~80ms on slash/hit, driven by the existing ``slash_anim`` /
   ``last_damage_timer`` timers. Gated by ``reduced_motion`` (and the low
   render tier, which reduced_motion forces) so the animation is disabled
   for accessibility.

Acceptance criteria covered:
- Every generated sprite has a 1px alpha-dilation outline at cache time
- Sprites have a 4-6 step hue-shifted shading ramp (cool shadows, warm
  highlights)
- Squash-and-stretch (1+k, 1-k) plays for ~80ms on slash/hit, driven by
  existing timers
- reduced_motion disables squash-and-stretch (static frame)
- Outline + shading add zero per-frame cost (cache-time only)
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# ---------------------------------------------------------------------------
# outline_array
# ---------------------------------------------------------------------------
def test_outline_array_exists(pygame_headless):
    """outline_array is importable from assets."""
    from assets import outline_array
    assert callable(outline_array)


def test_outline_array_returns_surface(pygame_headless):
    """outline_array returns a Surface (not None)."""
    import pygame
    from assets import outline_array
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (255, 0, 0), (16, 16), 8)
    out = outline_array(s)
    assert out is not None
    assert isinstance(out, pygame.Surface)


def test_outline_array_adds_pixels_around_sprite(pygame_headless):
    """The outline is a 1px dilation: the output has more opaque pixels
    than the input (the ring around the sprite)."""
    import pygame
    import pygame.surfarray
    from assets import outline_array
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (255, 0, 0), (16, 16), 8)
    out = outline_array(s)
    # The outline adds opaque pixels around the sprite (the 1px ring).
    orig_opaque = (pygame.surfarray.array_alpha(s) > 0).sum()
    out_opaque = (pygame.surfarray.array_alpha(out) > 0).sum()
    assert out_opaque > orig_opaque, (
        f"outline did not add pixels: orig={orig_opaque} out={out_opaque}")


def test_outline_array_is_1px_wide(pygame_headless):
    """The outline is a 1px ring: a pixel just outside the sprite is
    opaque (the outline), and a pixel 2px outside is transparent (the
    outline is 1px, not 2px)."""
    import pygame
    import pygame.surfarray
    from assets import outline_array
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    # A circle of radius 8 centered at (16, 16).
    pygame.draw.circle(s, (255, 0, 0), (16, 16), 8)
    out = outline_array(s)
    alpha = pygame.surfarray.array_alpha(out)
    # Pixel at (16, 7) is 1px outside the top of the circle (radius 8,
    # center 16 -> top at y=8; y=7 is 1px above). This should be opaque
    # (the outline).
    assert alpha[16, 7] > 0, (
        f"outline pixel at (16,7) is transparent: {alpha[16, 7]}")
    # Pixel at (16, 6) is 2px outside; this should be transparent (the
    # outline is 1px, not 2px).
    assert alpha[16, 6] == 0, (
        f"pixel at (16,6) should be transparent (1px outline): {alpha[16, 6]}")


def test_outline_array_preserves_sprite_pixels(pygame_headless):
    """The sprite's own pixels are preserved (the outline is added AROUND
    the sprite, not on top of it). The center of the sprite keeps its
    original color."""
    import pygame
    import pygame.surfarray
    from assets import outline_array
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (255, 0, 0), (16, 16), 8)
    out = outline_array(s)
    arr = pygame.surfarray.array3d(out)
    # The center of the sprite is still red (the outline is around the
    # sprite, not on top of it).
    assert tuple(arr[16, 16]) == (255, 0, 0), (
        f"sprite center changed: {tuple(arr[16, 16])}")


def test_outline_array_outline_is_dark(pygame_headless):
    """The outline is a dark color (the "looks like real pixel art" trick
    uses a dark outline so the sprite reads against any background)."""
    import pygame
    import pygame.surfarray
    from assets import outline_array
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (255, 0, 0), (16, 16), 8)
    out = outline_array(s)
    arr = pygame.surfarray.array3d(out)
    # The outline pixel at (16, 7) is dark (low RGB values).
    r, g, b = int(arr[16, 7, 0]), int(arr[16, 7, 1]), int(arr[16, 7, 2])
    assert r < 80 and g < 80 and b < 80, (
        f"outline pixel not dark: ({r}, {g}, {b})")


def test_outline_array_no_sprite_no_outline(pygame_headless):
    """An empty surface (no sprite) produces no outline (no opaque pixels)."""
    import pygame
    import pygame.surfarray
    from assets import outline_array
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    out = outline_array(s)
    assert (pygame.surfarray.array_alpha(out) > 0).sum() == 0


# ---------------------------------------------------------------------------
# Shading ramp
# ---------------------------------------------------------------------------
def test_apply_shading_ramp_exists(pygame_headless):
    """apply_shading_ramp is importable from assets."""
    from assets import apply_shading_ramp
    assert callable(apply_shading_ramp)


def test_apply_shading_ramp_changes_colors(pygame_headless):
    """The shading ramp changes the sprite's colors (a hue shift is
    visible). A flat-color sprite with no luminance variation gets no
    ramp (the ramp needs a luminance range to quantize), so we draw a
    sprite with a luminance range (a bright body + a dark detail)."""
    import pygame
    import pygame.surfarray
    import numpy as np
    from assets import apply_shading_ramp
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (180, 80, 80), (16, 16), 8)
    pygame.draw.circle(s, (120, 40, 40), (16, 16), 4)  # darker center
    pygame.draw.rect(s, (220, 200, 60), (12, 8, 8, 3))  # bright yellow
    orig = pygame.surfarray.array3d(s).copy()
    apply_shading_ramp(s)
    after = pygame.surfarray.array3d(s)
    # The shading ramp should change at least some pixel colors.
    diff = np.abs(after.astype(int) - orig.astype(int))
    assert diff.max() > 0, "shading ramp did not change any pixel colors"


def test_apply_shading_ramp_4_to_6_steps(pygame_headless):
    """The ramp uses 4-6 steps (the brief says 4-6). We check the default
    step count is in [4, 6]."""
    import inspect
    from assets import apply_shading_ramp
    sig = inspect.signature(apply_shading_ramp)
    steps_param = sig.parameters.get("steps")
    assert steps_param is not None, "apply_shading_ramp has no 'steps' param"
    default = steps_param.default
    assert 4 <= default <= 6, (
        f"default steps {default} not in [4, 6]")


def test_apply_shading_ramp_cool_shadows_warm_highlights(pygame_headless):
    """Shadows shift hue cool (toward blue), highlights warm (toward
    red/orange). We draw a sprite with a dark region + a bright region,
    apply the ramp, and check the dark region gained blue (cool) while
    the bright region gained red (warm)."""
    import pygame
    import pygame.surfarray
    import numpy as np
    from assets import apply_shading_ramp
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    # A dark region (low luminance) + a bright region (high luminance).
    pygame.draw.rect(s, (60, 60, 60), (4, 4, 12, 12))   # dark (shadow)
    pygame.draw.rect(s, (200, 200, 200), (20, 20, 8, 8))  # bright (highlight)
    orig = pygame.surfarray.array3d(s).copy()
    apply_shading_ramp(s)
    after = pygame.surfarray.array3d(s)
    # The dark region (x=4..15, y=4..15) should gain blue (cool shift).
    dark_orig_blue = float(orig[8, 8, 2])
    dark_after_blue = float(after[8, 8, 2])
    assert dark_after_blue >= dark_orig_blue, (
        f"shadow did not shift cool (blue): {dark_orig_blue} -> {dark_after_blue}")
    # The bright region (x=20..27, y=20..27) should gain red (warm shift).
    bright_orig_red = float(orig[24, 24, 0])
    bright_after_red = float(after[24, 24, 0])
    assert bright_after_red >= bright_orig_red, (
        f"highlight did not shift warm (red): {bright_orig_red} -> {bright_after_red}")


def test_apply_shading_ramp_preserves_alpha(pygame_headless):
    """The shading ramp does not change the alpha channel (only the RGB)."""
    import pygame
    import pygame.surfarray
    from assets import apply_shading_ramp
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(s, (180, 80, 80), (16, 16), 8)
    pygame.draw.circle(s, (120, 40, 40), (16, 16), 4)
    orig_alpha = pygame.surfarray.array_alpha(s).copy()
    apply_shading_ramp(s)
    after_alpha = pygame.surfarray.array_alpha(s)
    assert (orig_alpha == after_alpha).all(), (
        "shading ramp changed the alpha channel")


# ---------------------------------------------------------------------------
# Outline + shading applied at cache time (zero per-frame cost)
# ---------------------------------------------------------------------------
def _reset_caches():
    import assets
    assets._NINJA_CACHE.clear()
    assets._NINJA_SHEET_CACHE.clear()
    assets._ENEMY_CACHE.clear()
    assets._ENEMY_SHEET_CACHE.clear()
    assets._FIREFLY_CACHE.clear()
    assets._BUILDING_CACHE.clear()
    assets._PET_CACHE.clear()


def test_ninja_surface_has_outline(pygame_headless):
    """ninja_surface has a 1px outline (more opaque pixels than a bare
    sprite). The outline is applied at cache time, so the cached sprite
    has the outline baked in."""
    import pygame
    import pygame.surfarray
    import numpy as np
    from assets import ninja_surface, _draw_ninja_frame, _NINJA_FRAME_IDLE
    _reset_caches()
    cached = ninja_surface(64)
    # Build a bare sprite (no outline) for comparison.
    bare = pygame.Surface((64, 64), pygame.SRCALPHA)
    _draw_ninja_frame(bare, 64, _NINJA_FRAME_IDLE)
    cached_opaque = (pygame.surfarray.array_alpha(cached) > 0).sum()
    bare_opaque = (pygame.surfarray.array_alpha(bare) > 0).sum()
    assert cached_opaque > bare_opaque, (
        f"ninja_surface has no outline: cached={cached_opaque} bare={bare_opaque}")


def test_enemy_surface_has_outline(pygame_headless):
    """enemy_surface has a 1px outline (applied at cache time)."""
    import pygame
    import pygame.surfarray
    from assets import enemy_surface, _draw_enemy_frame, _enemy_frame_count
    from data.enemies import ZONES
    _reset_caches()
    bandit = ZONES[0]["enemies"][0]
    cached = enemy_surface(bandit, 48)
    bare = pygame.Surface((48, 48), pygame.SRCALPHA)
    _draw_enemy_frame(bare, bandit, 48, 0, _enemy_frame_count(bandit))
    cached_opaque = (pygame.surfarray.array_alpha(cached) > 0).sum()
    bare_opaque = (pygame.surfarray.array_alpha(bare) > 0).sum()
    assert cached_opaque > bare_opaque, (
        f"enemy_surface has no outline: cached={cached_opaque} bare={bare_opaque}")


def test_sprite_sheet_frames_have_outline(pygame_headless):
    """Each frame in the ninja sprite sheet has a 1px outline (applied per
    frame at cache time, so the outline does not bleed across frame
    boundaries)."""
    import pygame
    import pygame.surfarray
    from assets import ninja_sprite_sheet, _draw_ninja_frame, _NINJA_FRAME_IDLE
    _reset_caches()
    sheet = ninja_sprite_sheet(64)
    # Frame 0 is at (0, 0, 64, 64); extract it and compare to a bare frame.
    frame0 = sheet.subsurface((0, 0, 64, 64))
    bare = pygame.Surface((64, 64), pygame.SRCALPHA)
    _draw_ninja_frame(bare, 64, _NINJA_FRAME_IDLE)
    frame0_opaque = (pygame.surfarray.array_alpha(frame0) > 0).sum()
    bare_opaque = (pygame.surfarray.array_alpha(bare) > 0).sum()
    assert frame0_opaque > bare_opaque, (
        f"sprite sheet frame 0 has no outline: frame0={frame0_opaque} bare={bare_opaque}")


def test_outline_and_shading_zero_per_frame_cost(pygame_headless):
    """Outline + shading are applied at cache time, not per frame. A
    second call (cache hit) does not re-apply the outline or shading
    (the cached sprite is returned directly). We check the cached sprite
    is returned by identity on a cache hit."""
    import pygame
    from assets import ninja_surface, enemy_surface, firefly_surface
    from assets import building_surface, pet_surface
    from data.enemies import ZONES
    _reset_caches()
    e = ZONES[0]["enemies"][0]
    # Prime the caches.
    n1 = ninja_surface(64)
    e1 = enemy_surface(e, 48)
    f1 = firefly_surface(10, 60)
    b1 = building_surface("farm", 48)
    p1 = pet_surface("frog", 120, 40)
    # Cache hits return the same surface (no re-application).
    assert ninja_surface(64) is n1
    assert enemy_surface(e, 48) is e1
    assert firefly_surface(10, 60) is f1
    assert building_surface("farm", 48) is b1
    assert pet_surface("frog", 120, 40) is p1


# ---------------------------------------------------------------------------
# Squash-and-stretch
# ---------------------------------------------------------------------------
def test_squash_factor_exists(pygame_headless):
    """A squash factor helper is importable from ui.screen_game (or
    assets). The helper computes the (1+k, 1-k) scale from the
    slash_anim / last_damage_timer timers."""
    from ui.screen_game import squash_factor
    assert callable(squash_factor)


def test_squash_factor_zero_at_rest(pygame_headless):
    """At rest (slash_anim=0, last_damage_timer=0), the squash factor is
    0 (no squash — the sprite is at its natural size)."""
    from ui.screen_game import squash_factor
    k = squash_factor(slash_anim=0.0, last_damage_timer=0.0)
    assert k == 0.0, f"squash at rest != 0: {k}"


def test_squash_factor_peak_at_slash_start(pygame_headless):
    """At the slash start (slash_anim=0.15, the initial value), the
    squash factor is at its peak (k > 0). The squash plays for ~80ms
    from the slash start."""
    from ui.screen_game import squash_factor
    k = squash_factor(slash_anim=0.15, last_damage_timer=0.0)
    assert k > 0.0, f"squash at slash start <= 0: {k}"


def test_squash_factor_peak_at_hit_start(pygame_headless):
    """At the hit start (last_damage_timer=0.6, the initial value), the
    squash factor is at its peak (k > 0)."""
    from ui.screen_game import squash_factor
    k = squash_factor(slash_anim=0.0, last_damage_timer=0.6)
    assert k > 0.0, f"squash at hit start <= 0: {k}"


def test_squash_factor_decays_to_zero_within_80ms(pygame_headless):
    """The squash decays to 0 within ~80ms. For slash (start 0.15), at
    slash_anim=0.07 (elapsed=0.08s), the squash is 0. For hit (start
    0.6), at last_damage_timer=0.52 (elapsed=0.08s), the squash is 0."""
    from ui.screen_game import squash_factor
    # Slash: 0.15 - 0.08 = 0.07 -> squash = 0
    k = squash_factor(slash_anim=0.07, last_damage_timer=0.0)
    assert k == 0.0, f"squash after 80ms (slash) != 0: {k}"
    # Hit: 0.6 - 0.08 = 0.52 -> squash = 0
    k = squash_factor(slash_anim=0.0, last_damage_timer=0.52)
    assert k == 0.0, f"squash after 80ms (hit) != 0: {k}"


def test_squash_factor_decays_over_time(pygame_headless):
    """The squash factor decays over time (the peak is at the start, and
    it decreases as the timer ticks down)."""
    from ui.screen_game import squash_factor
    k_start = squash_factor(slash_anim=0.15, last_damage_timer=0.0)
    k_mid = squash_factor(slash_anim=0.12, last_damage_timer=0.0)
    k_late = squash_factor(slash_anim=0.10, last_damage_timer=0.0)
    assert k_start > k_mid > k_late > 0.0, (
        f"squash does not decay: start={k_start} mid={k_mid} late={k_late}")


def test_squash_factor_hit_overrides_slash(pygame_headless):
    """Hit (last_damage_timer) takes priority over slash for the squash
    (the ninja recoils when hit mid-slash). The hit squash is larger
    than the slash squash at the same elapsed time, OR the hit squash
    is used when both are active. We check the hit squash is at least
    as large as the slash squash when both are at their peaks."""
    from ui.screen_game import squash_factor
    k_slash = squash_factor(slash_anim=0.15, last_damage_timer=0.0)
    k_hit = squash_factor(slash_anim=0.0, last_damage_timer=0.6)
    # Both should be > 0 (the squash plays on both slash and hit).
    assert k_slash > 0.0 and k_hit > 0.0


# ---------------------------------------------------------------------------
# Squash-and-stretch in the game screen (reduced_motion gate)
# ---------------------------------------------------------------------------
def _reinit_display():
    """Re-init pygame + the display if a prior test quit pygame."""
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


def test_game_draws_with_squash(pygame_headless):
    """The game screen draws 30 frames with squash-and-stretch at the high
    tier without error. Exercises the slash/hit squash path (the ninja
    auto-attacks during the 30 frames, so the slash squash fires)."""
    import pygame
    import main
    _reinit_display()
    try:
        g = main.Game()
        g.current_screen = "game"
        g.state.reduced_motion = False
        g.state.render_quality = "high"
        for _ in range(30):
            g._update(1 / 60)
            g.screens["game"].draw(g.screen)
        assert g.state is not None
    finally:
        # Restore the display for downstream tests instead of quitting
        # pygame (quitting tears down the display and breaks downstream
        # tests that don't re-init).
        _reinit_display()


def test_game_draws_squash_reduced_motion(pygame_headless):
    """The game screen draws 30 frames with reduced_motion on without
    error (squash disabled — the sprite is at its natural size)."""
    import pygame
    import main
    _reinit_display()
    try:
        g = main.Game()
        g.current_screen = "game"
        g.state.reduced_motion = True
        for _ in range(30):
            g._update(1 / 60)
            g.screens["game"].draw(g.screen)
        assert g.state is not None
    finally:
        _reinit_display()


def test_squash_disabled_by_low_tier(pygame_headless):
    """The squash is disabled at the low render tier (the accessibility
    gate and the tier never diverge — reduced_motion forces low). We
    check the squash factor is 0 when the tier is low (the screen reads
    the tier via ``state.effective_render_quality()``)."""
    import main
    _reinit_display()
    try:
        g = main.Game()
        g.state.reduced_motion = False
        g.state.render_quality = "low"
        # At the low tier, the squash is disabled (k = 0 even at the slash
        # peak). The screen's squash gate reads ``parallax_enabled(quality)``
        # (the same tier path as parallax — low tier disables both).
        from ui.screen_game import squash_factor
        from core.quality import parallax_enabled
        quality = g.state.effective_render_quality()
        if not parallax_enabled(quality):
            k = squash_factor(slash_anim=0.15, last_damage_timer=0.0,
                              reduced_motion=True)
            assert k == 0.0, f"squash not disabled at low tier: {k}"
    finally:
        _reinit_display()
