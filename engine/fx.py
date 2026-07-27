"""FX layer: floating damage numbers + transient combat visuals.

Pure-state; the renderer reads it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config as cfg
from theme import C, font_sm, font_md
from utils import clamp


@dataclass
class FloatText:
    x: float
    y: float
    vy: float
    text: str
    color: tuple
    life: float
    max_life: float
    crit: bool = False

    def update(self, dt: float) -> None:
        self.y += self.vy * dt
        self.vy += 60 * dt
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0


class FXLayer:
    def __init__(self) -> None:
        self.texts: list[FloatText] = []

    def damage(self, x: float, y: float, amount: float, *, crit: bool = False) -> None:
        col = C.gold if crit else C.text
        text = f"{int(round(amount))}"
        if crit:
            text = "★" + text
        self.texts.append(FloatText(
            x=x + math.sin(len(self.texts)) * 6,
            y=y - 8,
            vy=-70 if not crit else -90,
            text=text, color=col,
            life=0.7 if not crit else 0.9,
            max_life=0.7 if not crit else 0.9,
            crit=crit,
        ))

    def update(self, dt: float) -> None:
        for t in self.texts:
            t.update(dt)
        self.texts = [t for t in self.texts if t.alive]

    def draw(self, surf) -> None:
        for t in self.texts:
            a = clamp(t.life / t.max_life, 0, 1)
            alpha = int(255 * a) if a > 0.6 else int(255 * (a / 0.6))
            f = font_md(bold=t.crit) if t.crit else font_sm()
            img = f.render(t.text, True, t.color)
            img.set_alpha(alpha)
            surf.blit(img, img.get_rect(center=(int(t.x), int(t.y))))
