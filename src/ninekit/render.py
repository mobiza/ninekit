"""Rendering pieces (layers or blocks) at every scale, and `ninekit build` (DESIGN 2, 3).

Every scale is rendered natively from the vector description: the canvas is round(w * s) x round(h * s)
texels and the shapes are evaluated at that scale's texel centres.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

from ninekit import NinekitError
from ninekit.canvas import BLENDS, Canvas, texel_grid
from ninekit.expr import ExprError, Scope
from ninekit.manifest import manifest_entry, merge_manifest, new_manifest, scale_key, write_manifest
from ninekit.paint import PaintCtx, paint, roughen_field
from ninekit.sdf import shape_sdf
from ninekit.slicing import cut_scale, plan_slices
from ninekit.spec import PieceDef, Spec, SpecError, load_spec

FALLOFFS = ("linear", "smooth", "exp")
STRETCH_MODES = ("stretch", "tile", "fixed")
MODES = ("color", "shade")
BLOCK_FORBIDDEN = ("size", "slice", "slice_px", "layers", "outputs", "compact", "keep", "mask", "period")
MASK_KEYS = {"shape", "grow", "soft", "roughen"}
DEFAULT_KEEP = 2        # dp of identical middle kept by compaction
_OUTPUT_OK = set("abcdefghijklmnopqrstuvwxyz0123456789_")


@dataclass
class Rendered:
    """One piece at one scale, ready to write."""
    name: str
    scale: float
    outputs: dict                      # output name -> uint8 (h, w, 4), in stacking order (bottom first)
    slice_px: list | None
    size: tuple                        # dp (the texture size / scale, or a block's own size)
    stretch: list
    content: list | None
    overhang: list | None
    mode: str
    problems: list = field(default_factory=list)   # piece-level failures found while rendering (verify fails)
    block: str | None = None
    warnings: list = field(default_factory=list)   # piece-level notes (snapped sizes, off-grid slices)
    slicing: str = "auto"              # auto | slice | slice_px | none | block: where the slices came from
    design_size: tuple | None = None   # dp: the size as designed (before compaction); None = `size`


def coverage(d: np.ndarray, soft: float, falloff: str, scale: float) -> np.ndarray:
    """Coverage of an sdf: a one-texel linear ramp (`linear`), smoothstep of it, or an exponential glow outside."""
    width = max(soft, 1.0 / scale)
    if falloff == "exp":
        return np.where(d <= 0, 1.0, np.exp(-np.maximum(d, 0) * 3.0 / width))
    c = np.clip(0.5 - d / width, 0.0, 1.0)
    if falloff == "smooth":
        c = c * c * (3.0 - 2.0 * c)
    return c


def _list4(v, ev, what):
    if v is None:
        return None
    if not isinstance(v, list) or len(v) != 4:
        raise NinekitError(f"{what}: must be [l, t, r, b]")
    return [ev(x, f"{what}[{i}]") for i, x in enumerate(v)]


def _stretch(data: dict, where: str) -> list:
    st = data.get("stretch", ["stretch", "stretch"])
    if isinstance(st, str):
        st = [st, st]
    if not isinstance(st, list) or len(st) != 2 or any(s not in STRETCH_MODES for s in st):
        raise NinekitError(f"{where}: stretch must be [x, y] (or one value for both) with each stretch | tile | fixed")
    return list(st)


def _mode(data: dict, where: str) -> str:
    mode = data.get("mode", "color")
    if mode not in MODES:
        raise NinekitError(f"{where}: mode must be color or shade")
    return mode


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def resolve_params(params: dict, scope: Scope, defaults: dict | None = None) -> dict:
    """Block params (DESIGN 2.3). A string is evaluated as an expression only for a key whose default in the
    block's DEFAULTS is a number (or a list of numbers, element by element); everything else is passed exactly
    as written: names such as `style: mint` (even when a var `mint` exists), colour strings, booleans and
    nested mappings like `colors:` (never evaluated). A block without DEFAULTS gets numbers only."""
    out = {}
    for k, v in params.items():
        d = (defaults or {}).get(k)
        if isinstance(v, str) and _is_number(d):
            out[k] = _param_number(v, scope, k)
        elif isinstance(v, list) and isinstance(d, (list, tuple)) and d and all(_is_number(x) for x in d):
            out[k] = [_param_number(x, scope, f"{k}[{i}]") if isinstance(x, str) else copy.deepcopy(x)
                      for i, x in enumerate(v)]
        else:
            out[k] = copy.deepcopy(v)
    return out


def _param_number(v: str, scope: Scope, what: str):
    try:
        return scope.eval(v, f"params.{what}")
    except ExprError as e:
        raise NinekitError(f"params.{what}: {v!r} is not a number or an expression ({e})") from None


@dataclass
class _Raw:
    """One scale of a layered piece before slicing: the full canvas of every output."""
    scale: float
    arrays: dict
    steps: tuple            # canvas size in grid steps (w, h)
    stretch: list
    mode: str
    content: list | None
    overhang: list | None
    periods: tuple          # texels per axis of the periodic paints (0 = none)
    lscope: Scope
    problems: list
    warnings: list


def render_piece(spec: Spec, pdef: PieceDef, scale) -> Rendered:
    """One piece at one scale. Slices are decided over all of the spec's scales (plus [scale]), so the result is
    the same file a full build writes."""
    scales = list(spec.scales) + ([scale] if scale not in spec.scales else [])
    return render_piece_scales(spec, pdef, scales)[scale]


def render_piece_scales(spec: Spec, pdef: PieceDef, scales) -> dict:
    """{scale: Rendered} of one piece at every scale in [scales]; auto slices and compaction are decided over all
    of them together on the dp grid (DESIGN 2.4)."""
    data = pdef.data
    if "block" in data:
        out = {}
        for s in scales:
            where = f"piece {pdef.name} @{scale_key(s)}x"
            out[s] = _render_block(spec, pdef, s, Scope(pdef.vars, {"scale": s}, where=where), where)
        if len(scales) > 1:
            _unify_block_slices(out, spec.grid_for(scales))
        return out
    grid = spec.grid_for(scales)
    smax = max(scales, key=float)
    raws = {s: _render_raw(spec, pdef, s, grid, smax) for s in scales}
    problems: list[str] = []
    warnings: list[str] = []
    for s, r in raws.items():
        problems += [f"@{scale_key(s)}x {p}" for p in r.problems]
        warnings += [w for w in r.warnings if w not in warnings]
    slicing, per_scale, stretch, more_problems, more_warnings = _slice_piece(pdef, raws, grid, smax)
    problems += more_problems
    warnings += [w for w in more_warnings if w not in warnings]
    out = {}
    for s, r in raws.items():
        arrays, slice_px = per_scale[s]
        first = next(iter(arrays.values()))
        out[s] = Rendered(name=pdef.name, scale=s, outputs=arrays, slice_px=slice_px,
                          size=(first.shape[1] / s, first.shape[0] / s), stretch=list(stretch), content=r.content,
                          overhang=r.overhang, mode=r.mode, problems=list(problems), warnings=list(warnings),
                          slicing=slicing, design_size=(float(r.steps[0] * grid), float(r.steps[1] * grid)))
    return out


def _fmt(v: float) -> str:
    return f"{round(float(v), 4):g}"


def _grid_txt(g: Fraction) -> str:
    return str(g.numerator) if g.denominator == 1 else f"{g.numerator}/{g.denominator}"


def _render_raw(spec: Spec, pdef: PieceDef, scale, grid: Fraction, smax) -> _Raw:
    data = pdef.data
    where = f"piece {pdef.name} @{scale_key(scale)}x"
    scope = Scope(pdef.vars, {"scale": scale}, where=where)
    ev = scope.eval
    size = data["size"]
    if not isinstance(size, list) or len(size) != 2:
        raise NinekitError(f"{where}: size must be [w, h] dp")
    sw, sh = ev(size[0], "size[0]"), ev(size[1], "size[1]")
    # the canvas snaps to the dp grid: a whole number of grid steps, so it is whole texels at every scale
    nw, nh = (round(v * grid.denominator / grid.numerator) for v in (sw, sh))
    if nw < 1 or nh < 1:
        raise NinekitError(f"{where}: size {_fmt(sw)} x {_fmt(sh)} dp is less than one {_grid_txt(grid)} dp grid step")
    fs = Fraction(scale).limit_denominator(1000)
    w_px, h_px = int(nw * grid * fs), int(nh * grid * fs)
    warnings = []
    if max(abs(sw - float(nw * grid)), abs(sh - float(nh * grid))) * float(smax) > 0.5 + 1e-9:
        warnings.append(f"size {_fmt(sw)} x {_fmt(sh)} dp is not on the {_grid_txt(grid)} dp grid (whole texels at "
                        f"every scale): snapped to {_fmt(nw * grid)} x {_fmt(nh * grid)} dp")
    w, h = w_px / scale, h_px / scale
    lscope = scope.child(w=w, h=h)
    lev = lscope.eval
    outputs = data.get("outputs", ["main"])
    if (not isinstance(outputs, list) or not outputs or len(set(outputs)) != len(outputs)
            or not all(isinstance(o, str) and o and set(o) <= _OUTPUT_OK for o in outputs)):
        raise NinekitError(f"{where}: outputs must be a list of distinct lowercase names, e.g. [frame, face]")
    mode = _mode(data, where)
    stretch = _stretch(data, where)
    tgrid = texel_grid(w_px, h_px, scale)
    canvases = {o: Canvas(w_px, h_px, scale, tgrid) for o in outputs}
    X0, Y0 = tgrid
    ctx = PaintCtx(ev=lev, colors=pdef.colors, mode=mode, scale=scale, base=spec.base, X=X0, Y=Y0, w=w, h=h,
                   grid=grid)
    for i, layer in enumerate(data["layers"]):
        lw = f"layer {i}" + (f" ({layer['name']})" if "name" in layer else "")
        _draw_layer(layer, lw, canvases, outputs, ctx, lev, scale, w, h)
    if "mask" in data:
        cover = _mask_coverage(data["mask"], ctx, lev, scale, w, h)
        for c in canvases.values():
            c.a = c.a * cover
    arrays = {o: canvases[o].to_uint8() for o in outputs}
    content = _list4(data.get("content"), lev, "content")
    overhang = _list4(data.get("overhang"), lev, "overhang")
    periods = _axis_periods(ctx.periods)
    problems = []
    sl = data.get("slice", "auto")
    for axis, p, st in (("x", periods[0], stretch[0]), ("y", periods[1], stretch[1])):
        if p and st == "stretch" and sl is not None and sl != "none":
            problems.append(f"{axis}: a noise/image paint or roughen varies along {axis} (period {p} px) but stretch "
                            f"is {st}; set stretch {axis} to tile (repeat) or fixed (natural length)")
    periods = _period_hint(data, ctx, lev, stretch, periods, where)
    for axis, p, st in (("x", periods[0], stretch[0]), ("y", periods[1], stretch[1])):
        if st == "tile" and not p and sl == "auto" and "slice_px" not in data:
            warnings.append(f"{axis} is tile but nothing declares a period on {axis} (no noise/image/roughen period "
                            f"and no `period:`): the tile is any run of identical lines; give `period: [pw, ph]` (dp) "
                            f"when a shape repeats")
    return _Raw(scale=scale, arrays=arrays, steps=(nw, nh), stretch=stretch, mode=mode, content=content,
                overhang=overhang, periods=periods, lscope=lscope, problems=problems, warnings=warnings)


def _mask_coverage(mask, ctx: PaintCtx, ev, scale, w, h) -> np.ndarray:
    """Coverage of the piece-level `mask` (the final silhouette): a shape, or {shape, grow, soft, roughen}."""
    if isinstance(mask, dict) and "shape" in mask:
        extra = set(mask) - MASK_KEYS
        if extra:
            raise NinekitError(f"mask: unknown key(s) {', '.join(sorted(map(str, extra)))} (allowed: "
                               f"{', '.join(sorted(MASK_KEYS))})")
        shape, opts = mask["shape"], mask
    else:
        shape, opts = mask, {}
    d = shape_sdf(shape, ctx.X, ctx.Y, ev, w, h, "mask")
    if "roughen" in opts:
        d = d + roughen_field(opts["roughen"], ctx, "mask.roughen")
    grow = ev(opts.get("grow", 0), "mask.grow")
    if grow != 0:
        d = d - grow
    soft = ev(opts.get("soft", 0), "mask.soft")
    if soft < 0:
        raise NinekitError("mask.soft must be >= 0")
    return coverage(d, soft, "linear", scale)


def _period_hint(data: dict, ctx: PaintCtx, ev, stretch, periods, where: str) -> tuple:
    """The piece's `period: [pw, ph]` (dp, 0 = none): the repeat of a tiled *shape*, combined (lcm) with the
    periodic paints' periods. Only for tile axes."""
    if "period" not in data:
        return periods
    per = data["period"]
    if not isinstance(per, list) or len(per) != 2:
        raise NinekitError(f"{where}: period must be [pw, ph] dp (0 = none on that axis)")
    out = list(periods)
    for i, (axis, v) in enumerate(zip("xy", per)):
        dp = ev(v, f"period[{i}]")
        if dp < 0:
            raise NinekitError(f"{where}: period[{i}] must be >= 0")
        if dp == 0:
            continue
        if stretch[i] != "tile":
            raise NinekitError(f"{where}: period {axis} is {dp} dp but stretch {axis} is {stretch[i]}; `period` is "
                               f"the repeat of a tile axis")
        px = ctx.grid_px(dp)
        out[i] = px if not out[i] else math.lcm(out[i], px)
    return tuple(out)


def _draw_layer(layer: dict, lw: str, canvases: dict, outputs: list, ctx: PaintCtx, ev, scale, w, h) -> None:
    if "when" in layer and ev(layer["when"], f"{lw}.when") == 0:
        return
    out = layer.get("output", outputs[0])
    if out not in canvases:
        raise NinekitError(f"{lw}: output {out!r} is not one of the piece's outputs {outputs}")
    canvas = canvases[out]
    X, Y = ctx.X, ctx.Y
    if "offset" in layer:
        off = layer["offset"]
        if not isinstance(off, list) or len(off) != 2:
            raise NinekitError(f"{lw}.offset: [dx, dy] dp")
        dx, dy = ev(off[0], f"{lw}.offset[0]"), ev(off[1], f"{lw}.offset[1]")
        if dx != 0:
            X = X - dx
        if dy != 0:
            Y = Y - dy
    d = shape_sdf(layer["shape"], X, Y, ev, w, h, f"{lw}.shape")
    if "roughen" in layer:
        d = d + roughen_field(layer["roughen"], ctx, f"{lw}.roughen")
    grow = ev(layer.get("grow", 0), f"{lw}.grow")
    if grow != 0:
        d = d - grow
    edge = d
    ring = ev(layer.get("ring", 0), f"{lw}.ring")
    if ring < 0:
        raise NinekitError(f"{lw}.ring must be >= 0")
    if ring > 0:
        d = np.maximum(d, -d - ring)
    soft = ev(layer.get("soft", 0), f"{lw}.soft")
    if soft < 0:
        raise NinekitError(f"{lw}.soft must be >= 0")
    falloff = layer.get("falloff", "linear")
    if falloff not in FALLOFFS:
        raise NinekitError(f"{lw}.falloff must be one of {', '.join(FALLOFFS)}")
    alpha = coverage(d, soft, falloff, scale)
    if "clip" in layer:
        alpha = alpha * coverage(shape_sdf(layer["clip"], ctx.X, ctx.Y, ev, w, h, f"{lw}.clip"), 0.0, "linear", scale)
    opacity = ev(layer.get("opacity", 1), f"{lw}.opacity")
    if not 0 <= opacity <= 1:
        raise NinekitError(f"{lw}.opacity must be 0..1")
    blend = layer.get("blend", "normal")
    if blend not in BLENDS:
        raise NinekitError(f"{lw}.blend must be one of {', '.join(BLENDS)}")
    colour, pa = paint(layer["fill"], ctx, lambda: edge, f"{lw}.fill")
    if opacity != 1:
        alpha = opacity * alpha
    if pa is not None:
        alpha = alpha * pa
    canvas.put(colour, alpha, blend)


def _axis_periods(periods: list) -> tuple[int, int]:
    """The period (px) per axis that every periodic paint repeats with (lcm), 0 = none."""
    px = py = 0
    for x, y in periods:
        if x:
            px = x if not px else math.lcm(px, x)
        if y:
            py = y if not py else math.lcm(py, y)
    return px, py


def _int_px(v, what):
    if abs(v - round(v)) > 1e-9:
        raise NinekitError(f"{what}: {v} is not a whole number of texels")
    return int(round(v))


def _slice_piece(pdef: PieceDef, raws: dict, grid: Fraction, smax):
    """(slicing, {scale: (arrays, slice_px)}, stretch, problems, warnings) of a layered piece."""
    data = pdef.data
    scales = list(raws)
    first = raws[scales[0]]
    stretch = list(first.stretch)
    names = list(first.arrays)
    plain = {s: (r.arrays, None) for s, r in raws.items()}
    if "slice_px" in data:
        sp = data["slice_px"]
        out = {}
        for s, r in raws.items():
            where = f"piece {pdef.name} @{scale_key(s)}x"
            if not isinstance(sp, list) or len(sp) != 4:
                raise NinekitError(f"{where}: slice_px must be [l, t, r, b]")
            h_px, w_px = next(iter(r.arrays.values())).shape[:2]
            sev = r.lscope.child(w_px=w_px, h_px=h_px).eval
            out[s] = (r.arrays, [_int_px(sev(v, f"slice_px[{i}]"), f"{where} slice_px[{i}]") for i, v in enumerate(sp)])
        return "slice_px", out, stretch, [], []
    sl = data.get("slice", "auto")
    if sl is None or sl == "none":
        return "none", plain, stretch, [], []
    if isinstance(sl, list):
        out, warnings = {}, []
        for s, r in raws.items():
            where = f"piece {pdef.name} @{scale_key(s)}x"
            if len(sl) != 4:
                raise NinekitError(f"{where}: slice must be [l, t, r, b] dp, auto or none")
            vals = [r.lscope.eval(v, f"slice[{i}]") for i, v in enumerate(sl)]
            off = [_fmt(v) for v in vals if abs(v * grid.denominator / grid.numerator
                                                - round(v * grid.denominator / grid.numerator)) > 1e-6]
            if off:
                msg = (f"slice {', '.join(off)} dp not on the {_grid_txt(grid)} dp grid: the files round it per scale, "
                       f"so their slices are not the same dp (use multiples of {_grid_txt(grid)} dp)")
                if msg not in warnings:
                    warnings.append(msg)
            out[s] = (r.arrays, [round(v * s) for v in vals])
        return "slice", out, stretch, [], warnings
    if sl != "auto":
        raise NinekitError(f"piece {pdef.name}: slice must be [l, t, r, b] dp, auto or none")
    gs = {s: int(grid * Fraction(s).limit_denominator(1000)) for s in scales}
    stacks = {s: _stack_outputs(r.arrays, names) for s, r in raws.items()}
    periods = {s: r.periods for s, r in raws.items()}
    problems: list[str] = []
    steps = {s: r.steps for s, r in raws.items()}
    if len(set(steps.values())) > 1:
        sizes = ", ".join(f"{_fmt(w * grid)} x {_fmt(h * grid)} dp at @{scale_key(s)}x" for s, (w, h) in steps.items())
        problems.append(f"size differs per scale ({sizes}): auto slices need one dp size; write size in dp without "
                        f"`scale`, or use slice_px for exact legacy art")
        plans = {}
        for s in scales:
            cuts, p = plan_slices({s: stacks[s]}, steps[s], {s: gs[s]}, stretch, {s: periods[s]}, grid)
            plans[s] = cuts
            problems += [f"@{scale_key(s)}x {x}" for x in p if f"@{scale_key(s)}x {x}" not in problems]
    else:
        cuts, p = plan_slices(stacks, steps[scales[0]], gs, stretch, periods, grid)
        plans = {s: cuts for s in scales}
        problems += p
    keep_steps = None
    if data.get("compact", True) and not problems and not any(r.problems for r in raws.values()):
        keep = raws[smax].lscope.eval(data.get("keep", DEFAULT_KEEP), "keep")
        if keep <= 0:
            raise NinekitError(f"piece {pdef.name}: keep must be > 0 dp")
        keep_steps = max(1, math.ceil(keep * grid.denominator / grid.numerator - 1e-9))
    out = {}
    for s, r in raws.items():
        arrs, slice_px = cut_scale([r.arrays[n] for n in names], plans[s], steps[s], gs[s], keep_steps)
        out[s] = (dict(zip(names, arrs)), slice_px)
    final = [plans[smax][0].mode, plans[smax][1].mode]
    return "auto", out, final, problems, []


def _stack_outputs(arrays: dict, names: list) -> np.ndarray:
    return np.concatenate([arrays[n].astype(np.int16) for n in names], axis=2)


def _unify_block_slices(per_scale: dict, grid: Fraction) -> None:
    """A block's per-scale slice_px on the dp grid (DESIGN 2.3): per side the largest slice over the scales (dp),
    rounded up to the grid, then slice_px = that dp x scale in every file. The middle then lies inside every
    scale's own middle, so the block's stretch rule still holds. An axis left with less than one grid step in the
    middle (or requested `fixed`) becomes `fixed` with exactly one grid step in the middle. `tile` axes, blocks
    drawn whole and canvases that are not whole grid steps at every scale are left as the block made them."""
    rs = list(per_scale.values())
    if any(r.slice_px is None for r in rs):
        return
    gs = {s: grid * Fraction(s).limit_denominator(1000) for s in per_scale}
    if any(g.denominator != 1 for g in gs.values()):
        return
    gs = {s: int(g) for s, g in gs.items()}
    steps = set()
    for s, r in per_scale.items():
        h, w = next(iter(r.outputs.values())).shape[:2]
        if w % gs[s] or h % gs[s]:
            return
        steps.add((w // gs[s], h // gs[s]))
    if len(steps) != 1:
        return
    (nw, nh), = steps
    stretch = list(rs[0].stretch)
    cuts = {}
    for axis, (a, b), n in ((0, (0, 2), nw), (1, (1, 3), nh)):
        mode = stretch[axis]
        if mode == "tile":
            continue
        lo = max(-(-r.slice_px[a] // gs[s]) for s, r in per_scale.items())
        hi = max(-(-r.slice_px[b] // gs[s]) for s, r in per_scale.items())
        if mode == "fixed" or n - lo - hi < 1:
            lo = (n - 1) // 2
            hi, mode = n - 1 - lo, "fixed"
        cuts[axis] = (a, b, int(lo), int(hi))
        stretch[axis] = mode
    for s, r in per_scale.items():
        sp = list(r.slice_px)
        for a, b, lo, hi in cuts.values():
            sp[a], sp[b] = lo * gs[s], hi * gs[s]
        r.slice_px = sp
        r.stretch = list(stretch)


def _render_block(spec: Spec, pdef: PieceDef, scale, scope: Scope, where: str) -> Rendered:
    from ninekit.blocks import block_defaults, get_block

    data = pdef.data
    bad = [k for k in BLOCK_FORBIDDEN if k in data]
    if bad:
        raise NinekitError(f"{where}: {', '.join(bad)} cannot be set on a block piece (the block decides them)")
    fn = get_block(data["block"])
    params = resolve_params(pdef.params, scope, block_defaults(data["block"]))
    try:
        res = fn(params, scale)
    except NinekitError:
        raise
    except Exception as e:  # a block's own validation errors are user errors here
        raise NinekitError(f"{where}: block {data['block']}: {e}") from e
    if not isinstance(res, dict) or "outputs" not in res or not res["outputs"]:
        raise NinekitError(f"{where}: block {data['block']} returned no outputs")
    arrays = {}
    for name, img in res["outputs"].items():
        if isinstance(img, Image.Image):
            arr = np.asarray(img.convert("RGBA"), dtype=np.uint8)
        else:
            arr = np.asarray(img, dtype=np.uint8)
        arrays[name] = np.ascontiguousarray(arr)
    shapes = {a.shape for a in arrays.values()}
    if len(shapes) != 1:
        raise NinekitError(f"{where}: block outputs differ in size {sorted(shapes)}")
    first = next(iter(arrays.values()))
    size = res.get("size") or [first.shape[1] / scale, first.shape[0] / scale]
    ev = scope.child(w=size[0], h=size[1]).eval
    content = _list4(data["content"], ev, "content") if "content" in data else res.get("content")
    overhang = _list4(data["overhang"], ev, "overhang") if "overhang" in data else res.get("overhang")
    sp = res.get("slice_px")
    return Rendered(name=pdef.name, scale=scale, outputs=arrays, slice_px=None if sp is None else [int(v) for v in sp],
                    size=(float(size[0]), float(size[1])), stretch=_stretch(data, where), content=content,
                    overhang=overhang, mode=_mode(data, where), block=data["block"], slicing="block",
                    design_size=(float(size[0]), float(size[1])))


# --- build -------------------------------------------------------------------------------------------------------------

@dataclass
class BuildResult:
    out_dir: Path
    manifest_path: Path
    manifest: dict
    files: list                       # {piece, output, scale, file, size_px, slice_px}
    problems: dict                    # piece -> [reasons] (verify fails on these)
    rendered: dict                    # piece -> {scale: Rendered}
    warnings: dict = field(default_factory=dict)   # piece -> [notes] (snapped sizes, off-grid slices)


def file_name(template: str, piece: str, output: str, scale, single_scale: bool) -> str:
    return template.format(piece=piece, output="" if output == "main" else f"_{output}",
                           scale="" if single_scale else f"@{scale_key(scale)}x")


def build_spec(spec: Spec, out_dir: Path | None = None, only: list | None = None, scales: list | None = None,
               write: bool = True) -> BuildResult:
    out_dir = Path(out_dir).resolve() if out_dir is not None else spec.out
    scales = list(scales) if scales else list(spec.scales)
    # slices are decided over the spec's scales too, so `--scales` writes the same files a full build writes
    all_scales = list(spec.scales) + [s for s in scales if s not in spec.scales]
    single = len(spec.scales) == 1
    defs = spec.piece_defs(only)
    files, problems, warnings, rendered, entries, taken = [], {}, {}, {}, {}, {}
    for pdef in defs:
        every = render_piece_scales(spec, pdef, all_scales)
        per_scale = {s: every[s] for s in scales}
        first = per_scale[scales[0]]
        if first.problems:
            problems[pdef.name] = list(first.problems)
        if first.warnings:
            warnings[pdef.name] = list(first.warnings)
        rendered[pdef.name] = per_scale
        file_map = {}
        for s, r in per_scale.items():
            for o, arr in r.outputs.items():
                fname = file_name(spec.file, pdef.name, o, s, single)
                if fname in taken:
                    raise SpecError(f"file name {fname!r} is produced twice ({taken[fname]} and {pdef.name}/{o}); "
                                    f"check the file template")
                taken[fname] = f"{pdef.name}/{o}"
                file_map[(o, s)] = fname
                if write:
                    path = out_dir / fname
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(arr, "RGBA").save(path, optimize=True)
                files.append({"piece": pdef.name, "output": o, "scale": s, "file": fname,
                              "size_px": [int(arr.shape[1]), int(arr.shape[0])], "slice_px": r.slice_px})
        entries[pdef.name] = manifest_entry(per_scale, file_map)
    manifest = new_manifest(spec.name, scales, entries)
    mpath = out_dir / "ninekit.json"
    if only and mpath.exists():
        manifest = merge_manifest(mpath, manifest)
    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(mpath, manifest)
    return BuildResult(out_dir=out_dir, manifest_path=mpath, manifest=manifest, files=files, problems=problems,
                       rendered=rendered, warnings=warnings)


def build(spec_path, theme=None, out=None, only=None, scales=None, write: bool = True) -> BuildResult:
    return build_spec(load_spec(spec_path, theme), out, only, scales, write)
