"""The float RGBA canvas layers paint onto (straight alpha), and colour parsing.

`Canvas.put` with blend "normal" is straight-alpha source-over with a fixed float operation order, so art
reproduces bit for bit from one release to the next.
"""
from __future__ import annotations

import numpy as np

from ninekit import NinekitError

BLENDS = ("normal", "add", "multiply", "screen", "erase", "atop")


def hexc(h: str) -> np.ndarray:
    """RGB (0..1 float64) of "#rrggbb" / "#rrggbbaa" (the alpha is read by hex_alpha)."""
    s = h.lstrip("#")
    if len(s) not in (6, 8) or any(ch not in "0123456789abcdefABCDEF" for ch in s):
        raise NinekitError(f"bad colour {h!r} (use #rrggbb or #rrggbbaa)")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) / 255.0


def hex_alpha(h: str) -> float | None:
    """The alpha of "#rrggbbaa" (0..1), or None for "#rrggbb"."""
    s = h.lstrip("#")
    return int(s[6:8], 16) / 255.0 if len(s) == 8 else None


class Canvas:
    """An RGBA float canvas of w_px x h_px texels at [scale]; X, Y are texel centres in dp."""

    def __init__(self, w_px: int, h_px: int, scale: float, grid: tuple[np.ndarray, np.ndarray] | None = None):
        self.w_px, self.h_px = int(w_px), int(h_px)
        self.scale = scale
        self.w, self.h = self.w_px / scale, self.h_px / scale
        if grid is None:
            grid = texel_grid(self.w_px, self.h_px, scale)
        self.X, self.Y = grid
        self.rgb = np.zeros((self.h_px, self.w_px, 3))
        self.a = np.zeros((self.h_px, self.w_px))

    def put(self, colour, alpha, blend: str = "normal") -> None:
        """Paints [colour] (an (h, w, 3) array or one RGB) with coverage [alpha] using [blend]."""
        alpha = np.clip(alpha, 0.0, 1.0)
        if np.ndim(alpha) == 0:
            alpha = np.broadcast_to(alpha, self.a.shape)
        col = colour if isinstance(colour, np.ndarray) and colour.ndim == 3 else np.broadcast_to(colour, self.rgb.shape)
        if blend == "normal":
            # source-over on straight alpha (keep this exact float operation order).
            out_a = alpha + self.a * (1.0 - alpha)
            safe = np.where(out_a > 1e-6, out_a, 1.0)
            self.rgb = (col * alpha[..., None] + self.rgb * (self.a * (1.0 - alpha))[..., None]) / safe[..., None]
            self.a = out_a
            return
        if blend == "erase":
            # destination-out: the source's coverage removes the destination; colours stay.
            self.a = self.a * (1.0 - alpha)
            return
        if blend == "atop":
            # source-atop: paints only where the canvas already has alpha and never changes the alpha, so a layer
            # that shares the canvas's outer edge does not thicken its anti-aliased fringe.
            self.rgb = self.rgb * (1.0 - alpha[..., None]) + col * alpha[..., None]
            return
        sa = alpha[..., None]
        ba = self.a[..., None]
        if blend == "add":
            # Porter-Duff plus (plus-lighter): premultiplied sums, clamped.
            out_a = np.minimum(self.a + alpha, 1.0)
            prem = col * sa + self.rgb * ba
            safe = np.where(out_a > 1e-6, out_a, 1.0)[..., None]
            self.rgb = np.minimum(prem / safe, 1.0)
            self.a = out_a
            return
        if blend == "multiply":
            mixed = self.rgb * col
        elif blend == "screen":
            mixed = self.rgb + col - self.rgb * col
        else:
            raise NinekitError(f"unknown blend {blend!r} (allowed: {', '.join(BLENDS)})")
        # W3C separable blending with source-over compositing.
        out_a = alpha + self.a * (1.0 - alpha)
        prem = col * sa * (1.0 - ba) + self.rgb * ba * (1.0 - sa) + sa * ba * mixed
        safe = np.where(out_a > 1e-6, out_a, 1.0)[..., None]
        self.rgb = prem / safe
        self.a = out_a

    def to_uint8(self) -> np.ndarray:
        img = np.dstack([self.rgb, self.a])
        return (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def texel_grid(w_px: int, h_px: int, scale: float) -> tuple[np.ndarray, np.ndarray]:
    """Texel centres in dp: texel (i, j) covers ((i + 0.5) / scale, (j + 0.5) / scale) (the texel-centre grid)."""
    ys, xs = np.mgrid[0:h_px, 0:w_px]
    return (xs + 0.5) / scale, (ys + 0.5) / scale
