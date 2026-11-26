"""Signed distance fields of the spec's shapes (DESIGN 2.2), in dp, negative inside.

`sdf_rrect`, `sdf_circle` and `sdf_ellipse` keep a fixed float operation order on explicit X, Y grids, so art made
with them reproduces bit for bit from one release to the next.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

from ninekit import NinekitError

SHAPE_KINDS = ("rect", "inset", "circle", "ellipse", "polygon", "union", "intersect", "subtract", "all")
_SHAPE_MODIFIERS = {
    "rect": {"r", "chamfer"},
    "inset": {"r", "chamfer"},
    "circle": set(),
    "ellipse": {"angle"},
    "polygon": set(),
    "union": set(),
    "intersect": set(),
    "subtract": set(),
    "all": set(),
}
# A finite stand-in for -inf: keeps every coverage formula free of inf - inf = nan.
ALL_INSIDE = -1e9


def sdf_rrect(X, Y, x0, y0, x1, y1, r, chamfer=None) -> np.ndarray:
    """Rounded rect; [r] one radius or (tl, tr, br, bl); [chamfer] likewise (45° cuts, used where > 0)."""
    tl, tr, br, bl = (r, r, r, r) if np.isscalar(r) else r
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hw, hh = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    right, below = X > cx, Y > cy
    if chamfer is not None:
        ctl, ctr, cbr, cbl = (chamfer,) * 4 if np.isscalar(chamfer) else chamfer
        # a chamfered corner has no radius; corner sizes are per quadrant like the radii
        tl, tr, br, bl = [0.0 if c > 0 else rad for c, rad in zip((ctl, ctr, cbr, cbl), (tl, tr, br, bl))]
    rad = np.where(right, np.where(below, br, tr), np.where(below, bl, tl))
    qx = np.abs(X - cx) - (hw - rad)
    qy = np.abs(Y - cy) - (hh - rad)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    d = outside + inside - rad
    if chamfer is None or max(ctl, ctr, cbr, cbl) <= 0:
        return d
    lim = max(0.0, min(hw, hh))
    ch = np.where(right, np.where(below, min(cbr, lim), min(ctr, lim)), np.where(below, min(cbl, lim), min(ctl, lim)))
    return np.where(ch > 0, _chamfer_quadrant(np.abs(X - cx), np.abs(Y - cy), hw, hh, ch), d)


def _chamfer_quadrant(px, py, hw, hh, c) -> np.ndarray:
    """Exact sdf of {x <= hw, y <= hh, x + y <= hw + hh - c} in a corner's mirrored frame (px, py >= 0)."""
    s2 = math.sqrt(2.0)
    sx, sy = px - hw, py - hh
    sd = (px + py - (hw + hh - c)) / s2
    inside = np.maximum(np.maximum(sx, sy), sd)
    d_side = np.hypot(sx, np.maximum(py - (hh - c), 0.0))            # the vertical edge up to the cut
    d_top = np.hypot(np.maximum(px - (hw - c), 0.0), sy)             # the horizontal edge up to the cut
    # the cut segment from (hw, hh - c) to (hw - c, hh)
    wx, wy = px - hw, py - (hh - c)
    cc = np.where(c > 0, c, 1.0)
    t = np.clip((wx * -cc + wy * cc) / (2.0 * cc * cc), 0.0, 1.0)
    d_cut = np.hypot(wx + cc * t, wy - cc * t)
    outside = np.minimum(np.minimum(d_side, d_top), d_cut)
    return np.where(inside > 0, outside, inside)


def sdf_circle(X, Y, cx, cy, r) -> np.ndarray:
    return np.hypot(X - cx, Y - cy) - r


def sdf_ellipse(X, Y, cx, cy, a, b, angle_deg=0.0) -> np.ndarray:
    """An approximate ellipse sdf (exact on the axes, good enough for one texel of AA and soft edges)."""
    t = np.radians(angle_deg)
    dx, dy = X - cx, Y - cy
    u = dx * np.cos(t) + dy * np.sin(t)
    v = -dx * np.sin(t) + dy * np.cos(t)
    return (np.hypot(u / a, v / b) - 1.0) * min(a, b)


def sdf_polygon(X, Y, pts) -> np.ndarray:
    """Exact signed distance to a simple polygon (any winding), even-odd inside test."""
    pts = [(float(x), float(y)) for x, y in pts]
    if len(pts) < 3:
        raise NinekitError("polygon needs at least 3 points")
    vx, vy = pts[0]
    d2 = (X - vx) ** 2 + (Y - vy) ** 2
    sign = np.ones_like(X)
    n = len(pts)
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[i - 1]
        ex, ey = xj - xi, yj - yi
        wx, wy = X - xi, Y - yi
        ee = ex * ex + ey * ey
        t = np.clip((wx * ex + wy * ey) / ee, 0.0, 1.0) if ee > 0 else np.zeros_like(X)
        bx, by = wx - ex * t, wy - ey * t
        d2 = np.minimum(d2, bx * bx + by * by)
        c1 = Y >= yi
        c2 = Y < yj
        c3 = ex * wy > ey * wx
        flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
        sign = np.where(flip, -sign, sign)
    return sign * np.sqrt(d2)


def shape_sdf(shape, X, Y, ev: Callable, w: float, h: float, where: str = "shape") -> np.ndarray:
    """The sdf of a spec shape dict. [ev](value, what) evaluates numbers; [w], [h] are the canvas dp size."""
    if not isinstance(shape, dict):
        raise NinekitError(f"{where}: a shape must be a mapping like {{rect: [...]}} or {{circle: [...]}}")
    kinds = [k for k in shape if k in SHAPE_KINDS]
    if len(kinds) != 1:
        raise NinekitError(f"{where}: needs exactly one of {', '.join(SHAPE_KINDS)}, got {list(shape)}")
    kind = kinds[0]
    extra = set(shape) - {kind} - _SHAPE_MODIFIERS[kind]
    if extra:
        raise NinekitError(f"{where}: {kind} does not take {', '.join(sorted(extra))}")
    arg = shape[kind]
    here = f"{where}.{kind}"

    def nums(v, n, what):
        if not isinstance(v, list) or len(v) != n:
            raise NinekitError(f"{here}: {what} must be a list of {n} numbers")
        return [ev(x, f"{here}[{i}]") for i, x in enumerate(v)]

    def corners(key):
        if key not in shape:
            return None
        v = shape[key]
        if isinstance(v, list):
            return tuple(nums(v, 4, f"{key} [tl, tr, br, bl]"))
        return ev(v, f"{here}.{key}")

    if kind == "all":
        if arg is not True:
            raise NinekitError(f"{here}: use {{all: true}}")
        return np.full(X.shape, ALL_INSIDE)
    if kind in ("rect", "inset"):
        if kind == "rect":
            x0, y0, x1, y1 = nums(arg, 4, "[x0, y0, x1, y1]")
        else:
            if isinstance(arg, list):
                l, t, r_, b = nums(arg, 4, "[l, t, r, b]")
            else:
                l = t = r_ = b = ev(arg, here)
            x0, y0, x1, y1 = l, t, w - r_, h - b
        r = corners("r")
        return sdf_rrect(X, Y, x0, y0, x1, y1, 0.0 if r is None else r, corners("chamfer"))
    if kind == "circle":
        cx, cy, r = nums(arg, 3, "[cx, cy, r]")
        return sdf_circle(X, Y, cx, cy, r)
    if kind == "ellipse":
        cx, cy, a, b = nums(arg, 4, "[cx, cy, a, b]")
        if a <= 0 or b <= 0:
            raise NinekitError(f"{here}: radii must be positive")
        angle = ev(shape["angle"], f"{here}.angle") if "angle" in shape else 0.0
        return sdf_ellipse(X, Y, cx, cy, a, b, angle)
    if kind == "polygon":
        if not isinstance(arg, list) or len(arg) < 3:
            raise NinekitError(f"{here}: needs a list of at least 3 [x, y] points")
        pts = [nums(p, 2, f"point {i}") for i, p in enumerate(arg)]
        return sdf_polygon(X, Y, pts)
    # booleans
    if not isinstance(arg, list) or len(arg) < (2 if kind == "subtract" else 1):
        raise NinekitError(f"{here}: needs a list of shapes")
    ds = [shape_sdf(s, X, Y, ev, w, h, f"{here}[{i}]") for i, s in enumerate(arg)]
    if kind == "union":
        return _reduce(np.minimum, ds)
    if kind == "intersect":
        return _reduce(np.maximum, ds)
    return np.maximum(ds[0], -_reduce(np.minimum, ds[1:]))


def _reduce(fn, ds):
    out = ds[0]
    for d in ds[1:]:
        out = fn(out, d)
    return out
