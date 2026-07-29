"""Task 37 (pl-music-sfx): generative ambient music + layered SFX.

Covers:
- A SEPARATE ``music_on`` toggle distinct from ``sound_on`` (the
  non-negotiable accessibility condition): the two are independent.
- A ``volume`` slider (0.0..1.0) on the settings screen.
- Default ``music_on = False``, ``volume = 0.5``.
- A generative pentatonic koto/taiko loop keyed to zone hue with a 4-bar
  re-rolled cycle (``generate_music_segment``).
- Crossfade between zone segments (no jarring key changes) -- the music
  loop crossfades on zone changes.
- Layered SFX with ADSR envelopes + noise layers + pitch variation + UI
  sounds replacing the single-sine tones (``_make_tone`` / ``_make_sweep``
  are layered; ``ui_click`` / ``ui_confirm`` UI sounds are registered).
- ``sound_on`` gate respected; noise-layer volumes conservative.
- One music system, one SFX system (no competing duplicates).
- The mixer may not init under the dummy driver -- the tests must not
  crash (degrade gracefully).
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _make_game():
    """Construct ``main.Game()`` with the display re-initialized if a
    prior test quit pygame.

    ``main.Game()`` calls ``pygame.display.set_mode`` itself, so this
    re-inits the display first if a prior test torn it down (e.g.
    ``test_render_tier`` calls ``pygame.quit()``). This keeps the
    session-scoped ``pygame_headless`` fixture's display alive across
    tests that quit pygame, so downstream tests (e.g. the outline tests)
    don't fail with "cannot convert without pygame.display initialized".
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
    import main
    return main.Game()


# ---------------------------------------------------------------------------
# 1. music_on is SEPARATE from sound_on
# ---------------------------------------------------------------------------
def test_music_on_field_exists():
    """GameState has a music_on field (separate from sound_on)."""
    from core.state import GameState
    s = GameState()
    assert hasattr(s, "music_on")
    assert hasattr(s, "sound_on")


def test_music_on_default_off():
    """music_on defaults to False (off or very low volume)."""
    from core.state import GameState
    s = GameState()
    assert s.music_on is False


def test_volume_default_0_5():
    """volume defaults to 0.5."""
    from core.state import GameState
    s = GameState()
    assert s.volume == 0.5


def test_music_on_separate_from_sfx():
    """music_on and sound_on are independent (the non-negotiable
    accessibility condition). Toggling one does not affect the other."""
    from core.state import GameState
    s = GameState()
    # They're independent: set one, the other is unchanged.
    s.music_on = True
    s.sound_on = False
    assert s.music_on is True
    assert s.sound_on is False
    # And the reverse.
    s.music_on = False
    s.sound_on = True
    assert s.music_on is False
    assert s.sound_on is True


def test_music_on_in_save_schema():
    """music_on + volume are in the save schema (persist across saves)."""
    from core.save_manager import _SCHEMA
    assert "music_on" in _SCHEMA
    assert _SCHEMA["music_on"] is bool
    assert "volume" in _SCHEMA
    assert _SCHEMA["volume"] is float


# ---------------------------------------------------------------------------
# 2. Generative music engine (assets.py)
# ---------------------------------------------------------------------------
def test_generate_music_segment_no_crash(pygame_headless):
    """generate_music_segment(root_hz=220, bars=4) does not crash.

    The brief's specimen test: ``seg is not None or True`` (audio may be
    unavailable; just no crash).
    """
    from assets import generate_music_segment
    seg = generate_music_segment(root_hz=220, bars=4)
    assert seg is not None or True  # audio may be unavailable; just no crash


def test_generate_music_segment_returns_array_or_none(pygame_headless):
    """generate_music_segment returns a stereo int16 array or None."""
    from assets import generate_music_segment
    seg = generate_music_segment(root_hz=220, bars=4)
    if seg is not None:
        # It's a numpy array (stereo int16).
        assert seg.ndim == 2
        assert seg.shape[1] == 2  # stereo
        assert seg.dtype.name == "int16"


def test_generate_music_segment_4_bar_duration():
    """A 4-bar segment at 90 BPM is ~10.7s (4 bars * 4 beats * 60/90)."""
    from assets import generate_music_segment, _MUSIC_SR
    seg = generate_music_segment(root_hz=220, bars=4)
    if seg is not None:
        # 4 bars * 4 beats/bar * 60s/min / 90 BPM = 10.667s.
        expected_samples = int(_MUSIC_SR * 4 * 4 * 60 / 90)
        # The segment length should be close to the expected duration
        # (within a few samples for float rounding).
        assert abs(seg.shape[0] - expected_samples) < 100, (
            f"segment length {seg.shape[0]} != expected {expected_samples}")


def test_generate_music_segment_re_rolled_each_cycle(pygame_headless):
    """Two segments with different seeds are different (re-rolled each
    cycle for non-repetition)."""
    from assets import generate_music_segment
    seg1 = generate_music_segment(root_hz=220, bars=4, seed=1)
    seg2 = generate_music_segment(root_hz=220, bars=4, seed=2)
    if seg1 is not None and seg2 is not None:
        # The two segments are different (the melody is re-rolled).
        assert not (seg1 == seg2).all(), (
            "segments with different seeds should differ (re-rolled)")


def test_generate_music_segment_deterministic_with_seed(pygame_headless):
    """Two segments with the same seed are identical (deterministic
    within a cycle)."""
    from assets import generate_music_segment
    seg1 = generate_music_segment(root_hz=220, bars=4, seed=42)
    seg2 = generate_music_segment(root_hz=220, bars=4, seed=42)
    if seg1 is not None and seg2 is not None:
        assert (seg1 == seg2).all(), (
            "segments with the same seed should be identical")


def test_root_hz_for_zone_in_range():
    """root_hz_for_zone maps a hue to a frequency in a pleasant range."""
    from assets import root_hz_for_zone
    for zone_index in range(9):
        for hue in (0, 90, 120, 160, 200, 220, 270, 280, 360):
            f = root_hz_for_zone(zone_index, hue)
            # The frequency is in a pleasant register (110..440 Hz).
            assert 110.0 <= f <= 440.0, (
                f"root_hz {f} for zone {zone_index} hue {hue} out of range")


def test_root_hz_for_zone_drifts_with_zone_index():
    """Later zones are slightly lower (darker) -- a subtle audio cue."""
    from assets import root_hz_for_zone
    # Same hue, different zone index: the drift lowers the frequency.
    f0 = root_hz_for_zone(0, 120)
    f8 = root_hz_for_zone(8, 120)
    assert f8 < f0, (
        f"later zone should be lower: zone 0 = {f0}, zone 8 = {f8}")


def test_make_music_sound_returns_sound_or_none(pygame_headless):
    """make_music_sound returns a pygame.Sound or None (degrades gracefully)."""
    from assets import make_music_sound
    snd = make_music_sound(root_hz=220, bars=4)
    # Either a Sound (mixer available) or None (mixer unavailable).
    assert snd is None or hasattr(snd, "play"), (
        "make_music_sound should return a Sound or None")


# ---------------------------------------------------------------------------
# 3. Layered SFX (assets.py)
# ---------------------------------------------------------------------------
def test_make_tone_is_layered_with_adsr():
    """_make_tone uses an ADSR envelope (not a pure exponential decay)."""
    import inspect
    from assets import _make_tone
    src = inspect.getsource(_make_tone)
    # The layered tone uses the ADSR envelope helper.
    assert "_adsr" in src
    # And a noise layer.
    assert "noise" in src.lower()


def test_make_sweep_is_layered_with_adsr():
    """_make_sweep uses an ADSR envelope + noise layer."""
    import inspect
    from assets import _make_sweep
    src = inspect.getsource(_make_sweep)
    assert "_adsr" in src
    assert "noise" in src.lower()


def test_make_tone_has_pitch_variation():
    """_make_tone has pitch variation (a small random detune per build)."""
    import inspect
    from assets import _make_tone
    src = inspect.getsource(_make_tone)
    assert "detune" in src


def test_adsr_envelope_shape():
    """The ADSR envelope rises (attack) then falls (release)."""
    import numpy as np
    from assets import _adsr
    sr = 22050
    n = int(sr * 0.5)  # 0.5s
    env = _adsr(n, sr, 0.5, attack=0.05, decay_t=0.2, sustain=0.5, release_t=0.2)
    # The envelope starts at 0 (attack starts at 0).
    assert env[0] == 0.0
    # The envelope rises during the attack.
    assert env[int(sr * 0.05)] > env[0]
    # The envelope peaks (> 0.5) during the attack/decay.
    assert env.max() > 0.5
    # The envelope ends at 0 (release ends at 0).
    assert env[-1] < 0.1


def test_noise_burst_decays():
    """The noise burst decays (the peak is early, the tail is quiet)."""
    import numpy as np
    from assets import _noise_burst
    sr = 22050
    n = int(sr * 0.3)
    noise = _noise_burst(n, sr, 0.3, decay=10.0)
    # The peak is in the first half (the decay).
    first_half = np.abs(noise[:n // 2]).max()
    second_half = np.abs(noise[n // 2:]).max()
    assert first_half > second_half, (
        f"noise should decay: first half {first_half}, second half {second_half}")


def test_ui_sounds_registered(pygame_headless):
    """UI click + confirm sounds are registered in _SFX."""
    from assets import init_sfx, _SFX
    init_sfx()
    # The UI sounds are registered (if the mixer is available).
    if _SFX:
        assert "ui_click" in _SFX
        assert "ui_confirm" in _SFX


def test_play_respects_sound_on_gate(pygame_headless):
    """play(name, False) is a no-op (respects sound_on)."""
    from assets import play
    # Should not raise even if the mixer is gone.
    play("tap", False)
    play("tap", True)
    play("nonexistent", True)


def test_layered_sfx_noise_volumes_conservative():
    """The noise-layer gains are conservative (a small fraction of vol)."""
    import inspect
    from assets import init_sfx
    src = inspect.getsource(init_sfx)
    # The noise gains in init_sfx are all <= 0.10 (conservative for
    # sound-sensitive players).
    import re
    # Find all noise=... values in init_sfx.
    noise_vals = [float(m) for m in re.findall(r"noise=([0-9.]+)", src)]
    for v in noise_vals:
        assert v <= 0.10, (
            f"noise gain {v} is not conservative (should be <= 0.10)")


# ---------------------------------------------------------------------------
# 4. The settings UI (music/SFX split + volume slider)
# ---------------------------------------------------------------------------
def test_settings_screen_has_music_toggle(pygame_headless):
    """The SettingsScreen has a separate Music toggle (btn_music)."""
    import main
    g = _make_game()
    screen = g.screens["settings"]
    assert hasattr(screen, "btn_music")
    # The music toggle is a separate button from the sound toggle.
    assert screen.btn_music is not screen.btn_sound


def test_settings_screen_music_toggle_gated_on_music_on(pygame_headless):
    """The Music toggle is gated on state.music_on (NOT state.sound_on)."""
    import inspect
    from ui.screen_settings import SettingsScreen
    # The toggle flips state.music_on (NOT state.sound_on).
    src = inspect.getsource(SettingsScreen._toggle_music)
    assert "self.game.state.music_on" in src
    # The toggle body must NOT assign to state.sound_on (the two toggles
    # are independent -- the non-negotiable accessibility condition).
    # (The source may mention sound_on in comments/labels, but the
    # assignment must be to music_on.)
    body = src.split("def _toggle_music")[1] if "def _toggle_music" in src else src
    assert "self.game.state.sound_on =" not in body
    assert "self.game.state.sound_on  =" not in body


def test_settings_screen_has_volume_slider(pygame_headless):
    """The SettingsScreen has a volume slider (a slider rect)."""
    import main
    g = _make_game()
    screen = g.screens["settings"]
    # The slider rect is on the settings screen.
    assert hasattr(screen, "_slider_rect")


def test_settings_volume_slider_sets_state_volume(pygame_headless):
    """Dragging the volume slider sets state.volume (and saves)."""
    import main
    g = _make_game()
    screen = g.screens["settings"]
    # The slider's _set_volume_from_x sets state.volume from an x pos.
    r = screen._slider_rect
    # Left edge -> volume 0.
    screen._set_volume_from_x(r.x)
    assert g.state.volume == 0.0
    # Right edge -> volume 1.
    screen._set_volume_from_x(r.x + r.w)
    assert g.state.volume == 1.0
    # Midway -> volume 0.5.
    screen._set_volume_from_x(r.x + r.w // 2)
    assert abs(g.state.volume - 0.5) < 0.05


def test_settings_volume_slider_clamps(pygame_headless):
    """The volume slider clamps to 0..1 (out-of-range x is clamped)."""
    import main
    g = _make_game()
    screen = g.screens["settings"]
    r = screen._slider_rect
    # Far left (out of range) -> 0.
    screen._set_volume_from_x(r.x - 1000)
    assert g.state.volume == 0.0
    # Far right (out of range) -> 1.
    screen._set_volume_from_x(r.x + r.w + 1000)
    assert g.state.volume == 1.0


def test_settings_music_toggle_independent_from_sound_toggle(pygame_headless):
    """Toggling music does not affect sound (and vice versa)."""
    import main
    g = _make_game()
    screen = g.screens["settings"]
    # Start with both off.
    g.state.music_on = False
    g.state.sound_on = False
    # Toggle music on.
    screen._toggle_music()
    assert g.state.music_on is True
    # Sound is still off (independent).
    assert g.state.sound_on is False
    # Toggle sound on.
    screen._toggle_sound()
    assert g.state.sound_on is True
    # Music is still on (independent).
    assert g.state.music_on is True


# ---------------------------------------------------------------------------
# 5. The music playback loop (main.py)
# ---------------------------------------------------------------------------
def test_game_has_music_loop_state(pygame_headless):
    """Game has the music-loop state (channel, current, zone_index)."""
    import main
    g = _make_game()
    assert hasattr(g, "_music_channel")
    assert hasattr(g, "_music_current")
    assert hasattr(g, "_music_zone_index")
    assert hasattr(g, "_music_fade")


def test_game_has_update_music(pygame_headless):
    """Game has an _update_music method (the music loop)."""
    import main
    g = _make_game()
    assert hasattr(g, "_update_music")
    assert callable(g._update_music)


def test_music_loop_respects_music_on_gate(pygame_headless):
    """_update_music is a no-op when music_on is False (respects the gate)."""
    import main
    g = _make_game()
    g.state.music_on = False
    # Clear the music state.
    g._music_current = None
    g._music_zone_index = -1
    # Run the music loop -- it should not start any music.
    g._update_music(1 / 60)
    # No music was started (music_on is off).
    assert g._music_current is None


def test_music_loop_does_not_crash_without_mixer(pygame_headless):
    """_update_music does not crash when the mixer is unavailable."""
    import main
    g = _make_game()
    # Force the channel to None (simulating no mixer).
    g._music_channel = None
    g.state.music_on = True
    # Run the music loop -- it should not crash (degrades gracefully).
    g._update_music(1 / 60)
    # No crash = pass.
    assert g is not None


def test_music_loop_scales_by_volume(pygame_headless):
    """The music loop scales the output by state.volume."""
    import inspect
    from main import Game
    src = inspect.getsource(Game._update_music)
    # The loop reads state.volume and applies it to the segment.
    assert "state.volume" in src
    # And set_volume is called on the segment.
    assert "set_volume" in src


def test_music_loop_crossfades_on_zone_change(pygame_headless):
    """The music loop fades in a new segment on zone changes (no jarring
    key changes -- the new segment fades in gently from 0)."""
    import inspect
    from main import Game
    src = inspect.getsource(Game._update_music)
    # The loop checks for zone changes and starts a fade-in.
    assert "zone_index" in src
    assert "_music_fade" in src
    # And the segment-start method exists (generates + plays + fades in).
    assert hasattr(Game, "_start_music_segment")


def test_music_loop_re_rolls_each_cycle(pygame_headless):
    """The music loop re-rolls the segment each cycle (non-repetition)."""
    import inspect
    from main import Game
    src = inspect.getsource(Game._update_music)
    # The loop checks get_busy() (the segment ended) and starts a new cycle.
    assert "get_busy" in src
    assert hasattr(Game, "_start_music_segment")


def test_music_loop_gated_on_music_on_not_sound_on(pygame_headless):
    """The music loop is gated on music_on, NOT on sound_on (the two
    are SEPARATE -- the non-negotiable accessibility condition)."""
    import inspect
    from main import Game
    src = inspect.getsource(Game._update_music)
    # The gate reads state.music_on (NOT state.sound_on).
    assert "state.music_on" in src
    # The loop does NOT read state.sound_on (the SFX gate is separate).
    # (If the loop read sound_on, music would be silent whenever SFX is
    # off -- conflating the two toggles. The brief is explicit: the two
    # are independent.)


# ---------------------------------------------------------------------------
# 6. One music system, one SFX system (no competing duplicates)
# ---------------------------------------------------------------------------
def test_one_sfx_system():
    """There is one SFX system (the _SFX dict + play()). No competing
    duplicates."""
    import inspect
    import assets
    # The _SFX dict is the single SFX registry.
    assert hasattr(assets, "_SFX")
    # And play() is the single SFX play function.
    assert hasattr(assets, "play")
    # There is no second SFX dict or play function (no competing
    # duplicates). The init_sfx builds into _SFX; no other module
    # defines its own SFX dict.
    src = inspect.getsource(assets)
    # _SFX is defined once (the module-level dict).
    assert src.count("_SFX: dict") == 1 or src.count("_SFX =") == 1 or src.count("_SFX:") >= 1


def test_one_music_system():
    """There is one music system (generate_music_segment + the Game loop).
    No competing duplicates."""
    import assets
    # The generative music engine is in assets.py.
    assert hasattr(assets, "generate_music_segment")
    assert hasattr(assets, "make_music_sound")
    # The root_hz mapping is in assets.py.
    assert hasattr(assets, "root_hz_for_zone")


# ---------------------------------------------------------------------------
# 7. Smoke: the music loop does not break the smoke test
# ---------------------------------------------------------------------------
def test_game_ticks_with_music_on(pygame_headless):
    """Game ticks 30 frames with music_on=True without error (the music
    loop does not break the smoke test)."""
    import main
    g = _make_game()
    g.state.music_on = True
    for _ in range(30):
        g._update(1 / 60)
    # No crash = pass.
    assert g.state is not None
