"""Paints (DESIGN 2.2): solid, vgrad, depth, noise and image fills.

A paint returns (colour, alpha): colour is one RGB or an (h, w, 3) array, alpha is None (opaque), a number
or an (h, w) array that multiplies the layer's coverage. In `mode: shade` every colour is a number 0..1 and
R = G = B = that shade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from ninekit import NinekitError
from ninekit.canvas import hex_alpha, hexc

NOISE_KINDS = ("value", "grain", "wood")
PAINT_KINDS = ("vgrad", "lgrad", "rgrad", "depth", "noise", "image")
WOOD_WARP = 1.5     # default ring bending of `wood`, in rings


@dataclass
class PaintCtx:
    """What a paint needs from the piece being rendered."""
    ev: Callable[[Any, str], float]     # evaluates a number / expression, (value, what)
    colors: dict
    mode: str                            # "color" | "shade"
    scale: float
    base: Path                           # the spec's folder (image paths)
    X: np.ndarray
    Y: np.ndarray
    w: float
    h: float
    images: dict = field(default_factory=dict)
    periods: list = field(default_factory=list)   # (px_x, px_y) of every periodic paint used
    grid: Fraction | None = None                  # the dp grid: periods snap to it (None: whole texels only)

    def grid_px(self, v: float) -> int:
        """A dp length snapped to the grid (at least one step), in texels at this scale."""
        if self.grid is None:
            return max(1, round(v * self.scale))
        g = self.grid
        steps = max(1, round(v * g.denominator / g.numerator))
        return int(steps * g * Fraction(self.scale).limit_denominator(1000))


def resolve_colour(value, ctx: PaintCtx, what: str = "colour", _depth: int = 0):
    """(rgb (3,), alpha or None) of a colour field: "#hex", a colour name, or a shade number in shade mode."""
    if _depth > 16:
        raise NinekitError(f"{what}: colour names refer to each other in a cycle")
    if isinstance(value, str) and value in ctx.colors:
        target = ctx.colors[value]
        if isinstance(target, list):
            raise NinekitError(f"{what}: {value!r} is a gradient (a list of stops), not a single colour")
        return resolve_colour(target, ctx, f"{what} ({value})", _depth + 1)
    if ctx.mode == "shade":
        if isinstance(value, str) and value.startswith("#"):
            raise NinekitError(f"{what}: {value!r} is a colour, but this piece is mode: shade (use a number 0..1)")
        v = float(ctx.ev(value, what))
        if not 0.0 <= v <= 1.0:
            raise NinekitError(f"{what}: shade {v} is outside 0..1")
        return np.array([v, v, v], dtype=np.float64), None
    if isinstance(value, str) and value.startswith("#"):
        try:
            return hexc(value), hex_alpha(value)
        except NinekitError as e:
            raise NinekitError(f"{what}: {e}") from None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raise NinekitError(f"{what}: {value!r} is a shade number; colours are \"#rrggbb\" (or set mode: shade)")
    raise NinekitError(f"{what}: unknown colour {value!r} (use \"#rrggbb\", \"#rrggbbaa\" or a name from colors)")


def resolve_stops(value, ctx: PaintCtx, what: str):
    """(ts, cols (n, 3), alphas (n,) or None) from [[t, colour], ...] or the name of such a list in colors."""
    if isinstance(value, str):
        if value not in ctx.colors or not isinstance(ctx.colors[value], list):
            raise NinekitError(f"{what}: {value!r} is not a gradient in colors (a list of [t, colour] stops)")
        what = f"{what} ({value})"
        value = ctx.colors[value]
    if not isinstance(value, list) or not value:
        raise NinekitError(f"{what}: stops must be a non-empty list of [t, colour]")
    ts, cols, alphas = [], [], []
    for i, s in enumerate(value):
        if not isinstance(s, list) or len(s) != 2:
            raise NinekitError(f"{what}[{i}]: a stop is [t, colour]")
        ts.append(ctx.ev(s[0], f"{what}[{i}].t"))
        rgb, a = resolve_colour(s[1], ctx, f"{what}[{i}].colour")
        cols.append(rgb)
        alphas.append(a)
    if any(b < a for a, b in zip(ts, ts[1:])):
        raise NinekitError(f"{what}: stop positions must not decrease ({ts})")
    al = None if all(a is None for a in alphas) else np.array([1.0 if a is None else a for a in alphas])
    return np.array(ts), np.stack(cols), al


def interp_stops(t: np.ndarray, ts, cols, alphas):
    """Colour (and alpha) along stops; with alpha stops the colours interpolate premultiplied."""
    out = np.empty(t.shape + (3,))
    if alphas is None:
        for ch in range(3):
            out[..., ch] = np.interp(t, ts, cols[:, ch])
        return out, None
    a = np.interp(t, ts, alphas)
    safe = np.where(a > 1e-9, a, 1.0)
    for ch in range(3):
        out[..., ch] = np.interp(t, ts, cols[:, ch] * alphas) / safe
    return out, a


def vgrad(Y: np.ndarray, y0: float, y1: float, ts, cols, alphas=None):
    """vgrad: vertical gradient over dp rows [y0, y1], clamped outside, linear per channel."""
    t = np.clip((Y - y0) / max(1e-6, y1 - y0), 0.0, 1.0)
    return interp_stops(t, ts, cols, alphas)


def paint(fill, ctx: PaintCtx, depth: Callable[[], np.ndarray], what: str = "fill"):
    """(colour, alpha) of a fill; [depth]() returns the layer's sdf (dp) for depth paints."""
    if not isinstance(fill, dict):
        return resolve_colour(fill, ctx, what)
    kinds = [k for k in PAINT_KINDS if k in fill]
    if len(kinds) != 1:
        raise NinekitError(f"{what}: needs exactly one of {', '.join(PAINT_KINDS)} (or a plain colour)")
    kind = kinds[0]
    if kind == "vgrad":
        _keys(fill, {"vgrad", "from", "to"}, what)
        ts, cols, al = resolve_stops(fill["vgrad"], ctx, f"{what}.vgrad")
        y0 = ctx.ev(fill.get("from", 0), f"{what}.from")
        y1 = ctx.ev(fill["to"], f"{what}.to") if "to" in fill else ctx.h
        return vgrad(ctx.Y, y0, y1, ts, cols, al)
    if kind == "lgrad":
        _keys(fill, {"lgrad", "angle", "from", "to"}, what)
        ts, cols, al = resolve_stops(fill["lgrad"], ctx, f"{what}.lgrad")
        return interp_stops(_lgrad_t(fill, ctx, what), ts, cols, al)
    if kind == "rgrad":
        _keys(fill, {"rgrad", "center", "radius", "ratio"}, what)
        ts, cols, al = resolve_stops(fill["rgrad"], ctx, f"{what}.rgrad")
        return interp_stops(_rgrad_t(fill, ctx, what), ts, cols, al)
    if kind == "depth":
        _keys(fill, {"depth"}, what)
        ts, cols, al = resolve_stops(fill["depth"], ctx, f"{what}.depth")
        return interp_stops(-depth(), ts, cols, al)
    if kind == "noise":
        _keys(fill, {"noise"}, what)
        return _noise(fill["noise"], ctx, f"{what}.noise")
    _keys(fill, {"image", "tile", "size"}, what)
    return _image(fill, ctx, what)


def _point(v, ctx: PaintCtx, what: str) -> tuple[float, float]:
    if not isinstance(v, list) or len(v) != 2:
        raise NinekitError(f"{what}: a point is [x, y] dp")
    return ctx.ev(v[0], f"{what}[0]"), ctx.ev(v[1], f"{what}[1]")


def _lgrad_t(fill: dict, ctx: PaintCtx, what: str) -> np.ndarray:
    """Position 0..1 along a linear gradient: from `from` to `to` (dp points), or at `angle` degrees (0 = left to
    right, 90 = top to bottom) spanning the canvas (its corners project onto 0 and 1, like CSS)."""
    if "from" in fill or "to" in fill:
        if "angle" in fill or "from" not in fill or "to" not in fill:
            raise NinekitError(f"{what}: lgrad takes `angle`, or both `from` and `to` points")
        x0, y0 = _point(fill["from"], ctx, f"{what}.from")
        x1, y1 = _point(fill["to"], ctx, f"{what}.to")
        dx, dy = x1 - x0, y1 - y0
        n2 = dx * dx + dy * dy
        if n2 <= 0:
            raise NinekitError(f"{what}: lgrad `from` and `to` are the same point")
        return np.clip(((ctx.X - x0) * dx + (ctx.Y - y0) * dy) / n2, 0.0, 1.0)
    a = math.radians(ctx.ev(fill.get("angle", 0), f"{what}.angle"))
    dx, dy = math.cos(a), math.sin(a)
    corners = [0.0, ctx.w * dx, ctx.h * dy, ctx.w * dx + ctx.h * dy]
    lo, hi = min(corners), max(corners)
    return np.clip((ctx.X * dx + ctx.Y * dy - lo) / max(1e-9, hi - lo), 0.0, 1.0)


def _rgrad_t(fill: dict, ctx: PaintCtx, what: str) -> np.ndarray:
    """Position 0..1 from `center` (default the canvas centre) out to `radius` (default half the shorter side);
    `ratio` = vertical / horizontal radius (an ellipse)."""
    cx, cy = _point(fill["center"], ctx, f"{what}.center") if "center" in fill else (ctx.w / 2.0, ctx.h / 2.0)
    r = ctx.ev(fill.get("radius", min(ctx.w, ctx.h) / 2.0), f"{what}.radius")
    k = ctx.ev(fill.get("ratio", 1), f"{what}.ratio")
    if r <= 0 or k <= 0:
        raise NinekitError(f"{what}: rgrad radius and ratio must be > 0")
    return np.clip(np.hypot(ctx.X - cx, (ctx.Y - cy) / k) / r, 0.0, 1.0)


def _keys(d: dict, allowed: set, what: str) -> None:
    extra = set(d) - allowed
    if extra:
        raise NinekitError(f"{what}: unknown key(s) {', '.join(sorted(map(str, extra)))}")


# --- noise -------------------------------------------------------------------------------------------------------------

def _period_px(v: float, ctx: PaintCtx) -> int:
    """A dp period snapped to the grid, in texels (0 = no variation along the axis)."""
    if v <= 0:
        return 0
    return ctx.grid_px(v)


def _lattice_axis(n_px: int, cells: int, smooth: bool):
    """Per texel of one period: lattice indices (i0, i1) and the blend weight, wrapping at [cells]."""
    u = (np.arange(n_px) + 0.5) / n_px * cells
    i0 = np.floor(u).astype(np.int64)
    f = u - i0
    if smooth:
        f = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)   # quintic fade: C2 across cells
    else:
        f = np.zeros_like(f)
    return i0 % cells, (i0 + 1) % cells, f


def _octave(px, py, cx, cy, lattice, smooth):
    ix0, ix1, fx = _lattice_axis(px, cx, smooth)
    iy0, iy1, fy = _lattice_axis(py, cy, smooth)
    a = lattice[np.ix_(iy0, ix0)]
    b = lattice[np.ix_(iy0, ix1)]
    c = lattice[np.ix_(iy1, ix0)]
    d = lattice[np.ix_(iy1, ix1)]
    fx, fy = fx[None, :], fy[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _fbm(px, py, cx, cy, octaves, rng, smooth=True):
    total = np.zeros((py, px))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        kx, ky = (cx << o) if cx > 1 else 1, (cy << o) if cy > 1 else 1
        lattice = rng.random((ky, kx))
        total += amp * _octave(px, py, kx, ky, lattice, smooth)
        norm += amp
        amp *= 0.5
    return total / norm


def noise_tile(spec: dict, ctx: PaintCtx, what: str) -> np.ndarray:
    """One period of the noise in texels, values 0..1, shape (Py, Px) (an axis without variation has 1 texel)."""
    _keys(spec, {"kind", "period", "scale", "octaves", "seed", "stops", "warp", "axis"}, what)
    kind = spec.get("kind", "value")
    if kind not in NOISE_KINDS:
        raise NinekitError(f"{what}: kind must be one of {', '.join(NOISE_KINDS)}")
    if "warp" in spec and kind != "wood":
        raise NinekitError(f"{what}: warp applies to kind: wood only")
    axis = spec.get("axis", "x")
    if axis not in ("x", "y"):
        raise NinekitError(f"{what}: axis must be x or y (the grain direction)")
    per = spec.get("period")
    if not isinstance(per, list) or len(per) != 2:
        raise NinekitError(f"{what}: period: [pw, ph] (dp; 0 = no variation along that axis) is required")
    pw, ph = (ctx.ev(v, f"{what}.period[{i}]") for i, v in enumerate(per))
    if pw <= 0 and ph <= 0:
        raise NinekitError(f"{what}: at least one period must be > 0")
    if axis == "y":
        # the x pattern turned 90 degrees: computed with the periods swapped, then transposed
        pw, ph = ph, pw
    Px, Py = _period_px(pw, ctx), _period_px(ph, ctx)
    ctx.periods.append((Py, Px) if axis == "y" else (Px, Py))
    tile = _noise_tile(spec, kind, axis, pw, ph, Px, Py, ctx, what)
    return np.ascontiguousarray(tile.T) if axis == "y" else tile


def _noise_tile(spec, kind, axis, pw, ph, Px, Py, ctx: PaintCtx, what: str) -> np.ndarray:
    nx, ny = max(Px, 1), max(Py, 1)
    octaves = int(ctx.ev(spec.get("octaves", 1 if kind == "grain" else 3), f"{what}.octaves"))
    if not 1 <= octaves <= 8:
        raise NinekitError(f"{what}: octaves must be 1..8")
    seed = int(ctx.ev(spec.get("seed", 0), f"{what}.seed"))
    rng = np.random.default_rng(seed)
    longest = max(pw, ph)
    if kind == "grain":
        # a random value per cell (default one texel), no smoothing: speckle / film grain
        cell = ctx.ev(spec["scale"], f"{what}.scale") if "scale" in spec else 1.0 / ctx.scale
        cell_px = max(1, round(cell * ctx.scale))
        cx = max(1, round(nx / cell_px)) if Px else 1
        cy = max(1, round(ny / cell_px)) if Py else 1
        return _fbm(nx, ny, cx, cy, octaves, rng, smooth=False)
    feature = ctx.ev(spec.get("scale", longest / 4.0), f"{what}.scale")
    if feature <= 0:
        raise NinekitError(f"{what}: scale (feature size, dp) must be > 0")
    cx = max(1, round(pw / feature)) if Px else 1
    cy = max(1, round(ph / feature)) if Py else 1
    if kind == "value":
        return _fbm(nx, ny, cx, cy, octaves, rng)
    # wood: horizontal grain lines (rings along y) bent by low-frequency noise
    if not Py:
        if axis == "y":
            raise NinekitError(f"{what}: wood with axis: y needs an x period (its grain lines run along y)")
        raise NinekitError(f"{what}: wood needs a y period (its grain lines run along x)")
    rings = max(1, round(ph / feature))
    amp = ctx.ev(spec.get("warp", WOOD_WARP), f"{what}.warp")
    if amp < 0:
        raise NinekitError(f"{what}: warp (how far the rings bend, in rings) must be >= 0")
    bend = _fbm(nx, ny, max(1, cx // 2) if Px else 1, max(1, rings // 2), octaves, rng)
    phase = (np.arange(ny)[:, None] + 0.5) / ny * rings + amp * bend
    return 0.5 + 0.5 * np.sin(2.0 * math.pi * phase)


def roughen_field(spec, ctx: PaintCtx, what: str) -> np.ndarray:
    """A layer's `roughen: {amount, period, scale, octaves, seed}`: an edge offset (dp, -amount..amount) per texel
    from tileable value noise with the given dp period (a number or [pw, ph]; 0 = no variation along that axis).
    The period counts as a periodic paint (tile axes repeat with it; a stretch axis it varies along is a problem)."""
    if not isinstance(spec, dict):
        raise NinekitError(f"{what}: roughen must be a mapping (amount, period, scale, octaves, seed)")
    _keys(spec, {"amount", "period", "scale", "octaves", "seed"}, what)
    if "amount" not in spec or "period" not in spec:
        raise NinekitError(f"{what}: roughen needs `amount` (dp) and `period` (dp, or [pw, ph])")
    amount = ctx.ev(spec["amount"], f"{what}.amount")
    if amount < 0:
        raise NinekitError(f"{what}.amount must be >= 0")
    per = spec["period"]
    per = per if isinstance(per, list) else [per, per]
    nspec = {"kind": "value", "period": per, **{k: spec[k] for k in ("scale", "octaves", "seed") if k in spec}}
    tile = noise_tile(nspec, ctx, what)
    h_px, w_px = ctx.X.shape
    ty, tx = tile.shape
    return amount * (2.0 * tile[np.ix_(np.arange(h_px) % ty, np.arange(w_px) % tx)] - 1.0)


def _noise(spec, ctx: PaintCtx, what: str):
    if not isinstance(spec, dict):
        raise NinekitError(f"{what}: must be a mapping (kind, period, scale, octaves, seed, stops)")
    tile = noise_tile(spec, ctx, what)
    default = [[0, 0], [1, 1]] if ctx.mode == "shade" else [[0, "#000000"], [1, "#ffffff"]]
    ts, cols, al = resolve_stops(spec.get("stops", default), ctx, f"{what}.stops")
    h_px, w_px = ctx.X.shape
    ty, tx = tile.shape
    field_ = tile[np.ix_(np.arange(h_px) % ty, np.arange(w_px) % tx)]
    return interp_stops(field_, ts, cols, al)


# --- image ------------------------------------------------------------------------------------------------------------

def _image(fill: dict, ctx: PaintCtx, what: str):
    path = (ctx.base / str(fill["image"])).resolve()
    if path not in ctx.images:
        try:
            with Image.open(path) as im:
                ctx.images[path] = im.convert("RGBA")
        except (OSError, ValueError) as e:
            raise NinekitError(f"{what}: cannot read image {path}: {e}") from None
    src = ctx.images[path]
    if "size" in fill:
        sz = fill["size"]
        if not isinstance(sz, list) or len(sz) != 2:
            raise NinekitError(f"{what}.size: [dw, dh] dp per tile")
        dw, dh = (ctx.ev(v, f"{what}.size[{i}]") for i, v in enumerate(sz))
    else:
        dw, dh = src.size  # one image px per dp
    tile = fill.get("tile", True)
    if tile:        # a tile is a period: snapped to the grid like noise periods
        tw, th = ctx.grid_px(dw), ctx.grid_px(dh)
    else:
        tw, th = max(1, round(dw * ctx.scale)), max(1, round(dh * ctx.scale))
    if tile:
        # resample a 3x3 mosaic and keep the centre, so the filter wraps and the tile stays seamless
        big = Image.new("RGBA", (src.width * 3, src.height * 3))
        for i in range(3):
            for j in range(3):
                big.paste(src, (i * src.width, j * src.height))
        big = big.resize((tw * 3, th * 3), Image.LANCZOS)
        arr = np.asarray(big.crop((tw, th, tw * 2, th * 2)), dtype=np.float64) / 255.0
        ctx.periods.append((tw, th))
        h_px, w_px = ctx.X.shape
        arr = arr[np.ix_(np.arange(h_px) % th, np.arange(w_px) % tw)]
    else:
        arr0 = np.asarray(src.resize((tw, th), Image.LANCZOS), dtype=np.float64) / 255.0
        h_px, w_px = ctx.X.shape
        arr = np.zeros((h_px, w_px, 4))
        arr[:min(th, h_px), :min(tw, w_px)] = arr0[:h_px, :w_px]
    if ctx.mode == "shade":
        lum = arr[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
        return np.repeat(lum[..., None], 3, axis=2), arr[..., 3]
    return arr[..., :3], arr[..., 3]
