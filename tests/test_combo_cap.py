"""Combo multiplier cap: asymptotic curve structurally capped at COMBO_MULT_CAP.

Regression test for the bug where `COMBO_MULT_CAP=3.0` was defined but never
applied — the old linear `1 + c*step` reached ~270x at combo 200 with maxed
combo_step, a 90x balance break. The fix replaces the linear formula with an
asymptotic `1 + COMBO_MULT_CAP*(1 - exp(-c/COMBO_TAU))` so the cap is
structurally enforced and the curve is smooth.
"""
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
