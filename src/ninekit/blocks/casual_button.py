"""casual_button: a casual-game push button with a metal bezel and a bevelled, glossy "pillow" face, as a ninekit
block (DESIGN.md §2.3).

The button is drawn with Pillow masks at `ss` x supersampling and downsampled with Lanczos, layer by layer, from the
outside in:
  outline        a thin dark outline around the body
  bezel          an outer ring and an inner ring; the inner ring's first row is lighter along the top and upper sides
                 (the rim light, fading out downwards), and at the bottom a darker depth band sits under the outer ring
                 (the bezel's own side wall)
  line           a dark line in the button's tone just inside the bezel (thicker at the bottom: `line_bottom`)
  the face       a bevelled pillow: a light top bevel (`gloss`), side walls (`wall`) and a dark bottom bevel (`lip`),
                 mitred into each other at the corners, and the flat panel inside them (one long vertical gradient, a
                 light line along its bottom edge) under a soft sheen (a capsule of light fading downwards)
  well           a very dark socket filling the bezel, only seen when the face sinks in (pressed)
Every gradient runs vertically and every horizontal feature (the rounded corners, the bevel mitres, the sheen's rounded
ends) lives inside the side slices, so all middle columns are identical: the button stretches to any width without a
trace. Vertically a button has a natural height: with several scales the y axis is `fixed`; with one scale the block
leaves the two middle rows to stretch, so keep the sheen above them and the outermost colours (the bezel's outline, the
line) flat - their anti-aliased edge texels are stored with straight alpha, where a gradient's small steps turn into
colour jumps that `ninekit verify` reports. Labels are drawn by the runtime.

The defaults are the Gumdrop sample concept (examples/gumdrop/): a cool steel bezel, 20 dp corners, a 59 dp body with a
thick candy lip and a large soft sheen. Every measurement and colour is a param, so other looks are params too.

Params (dp unless noted):
  style          a PRESETS name (colours); optional when `colors` gives the full set
  colors         colour overrides, merged over the preset: line, wall, lip, gloss, face, well (gradients), face_edge,
                 shadow, sheen (solid), text_outline (carried for label tooling, not drawn), and
                 bezel: {outline, depth, outer, inner (gradients), rim_light (solid)} merged key by key over BEZEL.
                 A colour is "#rrggbb", "#rrggbbaa" or an [r, g, b(, a)] list; a gradient is one colour (flat),
                 a [top, bottom] pair, or [[t, colour], ...] stops (t 0..1 over the band, top to bottom; the bezel's
                 outline, outer, inner and depth run over the whole body height).
  circle         false: the 9-slice button (btn_w x btn_h); true: the round form, a btn_h square drawn whole
  layers         [frame, face] (default) -> outputs "frame" (drop shadow, bezel, dark well) and "face" (the face alone,
                 on the same canvas, so the two stack exactly); "full" -> output "main" (the composite)
  pressed        only for "full": the face sinks into the well (press_top / press_side / press_bottom)
  btn_w, btn_h   canvas (btn_h includes the drop shadow under the body)
  body_h         the body's height
  radius         the outer rings' corner radius
  press          the side slices' allowance for the pressed face (>= press_side)
  press_top, press_side, press_bottom   how far the pressed face sinks
  outline, outer_ring, inner_ring, depth   bezel bands (depth: the darker band at the bezel's bottom)
  rim_light      the inner ring's lighter first row
  rim_light_fade that row fades out by this share of the body height (unitless)
  line, line_bottom   the dark line inside the bezel (sides/top, bottom)
  wall           the side walls' width
  lip            the bottom bevel's height
  gloss          the top bevel's height
  panel_radius   the face panel's corner radius (rectangular form)
  face_edge_width   the panel's light bottom line
  sheen          the sheen's opacity at its top (unitless; 0 = no sheen); the colour is colors.sheen
  sheen_fade     its opacity at the bottom, as a share of the top's (unitless)
  sheen_height, sheen_inset, sheen_offset, sheen_soft   the sheen capsule: its height, its inset from the panel's
                 sides, its distance below the panel's top edge, and the blur of its edge
  shadow_offset, shadow_blur, shadow_opacity   the soft drop shadow under the body (opacity unitless)
  slice_margin   anti-aliasing allowance added to the side slices
  ss             supersampling factor (unitless)
  content        [l, t, r, b] label area measured from the canvas edges (centred on the face panel), or null
"""
from __future__ import annotations

import copy
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

DEFAULTS = {
    "style": None,
    "colors": None,
    "circle": False,
    "layers": ["frame", "face"],
    "pressed": False,
    "btn_w": 128.0,
    "btn_h": 62.0,              # body 59 tall, the soft drop shadow under it
    "body_h": 59.0,
    "radius": 20.0,             # the outer rings' corners
    "press": 2.0,               # the side slices' allowance for the pressed face (>= press_side)
    # pressed: the block inside the bezel (its bevels and face exactly as unpressed - same colours, same widths)
    # sinks straight in, a little deeper at the top than at the bottom (pushed in, it settles down into the well)
    "press_top": 2.2,
    "press_side": 1.6,
    "press_bottom": 1.0,
    "outline": 0.8,
    "outer_ring": 1.3,
    "inner_ring": 2.4,
    "depth": 2.0,               # the darker band at the bezel's bottom
    "rim_light": 0.7,
    "rim_light_fade": 0.6,
    "line": 0.6,
    "line_bottom": 0.9,
    "wall": 3.6,                # the side walls
    "lip": 6.2,                 # the bottom bevel: a thick candy lip
    "gloss": 2.6,               # the top bevel
    "panel_radius": 11.0,
    "face_edge_width": 0.8,
    "sheen": 0.6,
    "sheen_fade": 0.1,
    "sheen_height": 14.0,
    "sheen_inset": 5.0,
    "sheen_offset": 1.2,
    "sheen_soft": 1.2,
    "shadow_offset": 2.0,
    "shadow_blur": 1.3,
    "shadow_opacity": 0.3,
    "slice_margin": 1.5,
    "ss": 4,
    # the label area: the face panel spans 7.7..45.4 of the 62 dp (centre 26.55); the content area is 37 dp tall,
    # centred on it
    "content": [12.0, 8.0, 12.0, 17.0],
}

# a cool steel bezel: a dark slate outline, a mid-steel outer ring, a bright silver inner ring with a white rim light
BEZEL = {
    "outline": "#262e3b",
    "outer": [(0.0, "#7c8a9f"), (1.0, "#5d6a7f")],
    "inner": [(0.0, "#eff3f8"), (0.45, "#c3ccd8"), (1.0, "#99a6b7")],
    "rim_light": "#fbfdff",
    "depth": ("#5a6678", "#495465"),
}
SHADOW = "#1b2238"
SHEEN = "#ffffff"

PRESETS = {
    "berry": {
        "line": "#5e0c33",
        "wall": [(0.0, "#f06aa8"), (0.3, "#dd4b8f"), (0.75, "#c63679"), (1.0, "#b0296a")],
        "lip": ("#a7205e", "#84154a"),
        "gloss": ("#ffc5df", "#ffb1d3"),
        "face": [(0.0, "#ff90c2"), (0.25, "#f8679f"), (0.55, "#ee4f92"), (0.8, "#de3c84"), (1.0, "#c92d76")],
        "face_edge": "#f774b0",
        "text_outline": "#791042",
        "well": ("#21040e", "#2d0715"),
    },
    "mint": {
        "line": "#084530",
        "wall": [(0.0, "#5ddcab"), (0.3, "#3fc794"), (0.75, "#28ad7e"), (1.0, "#1c966a")],
        "lip": ("#17865d", "#106f4c"),
        "gloss": ("#d3fff0", "#c1fae5"),
        "face": [(0.0, "#9df4cf"), (0.25, "#6ee6b6"), (0.55, "#47d4a0"), (0.8, "#30bd89"), (1.0, "#23a676")],
        "face_edge": "#62e2b3",
        "text_outline": "#0c593d",
        "well": ("#03160e", "#062116"),
    },
    "sky": {
        "line": "#0b305d",
        "wall": [(0.0, "#5cb9f8"), (0.3, "#409fee"), (0.75, "#2b84d9"), (1.0, "#206fc4")],
        "lip": ("#1c61af", "#154e92"),
        "gloss": ("#d5efff", "#c3e7ff"),
        "face": [(0.0, "#9edbff"), (0.25, "#71c6fe"), (0.55, "#4daef9"), (0.8, "#3694ec"), (1.0, "#277cd6")],
        "face_edge": "#59b3f9",
        "text_outline": "#113f79",
        "well": ("#04101e", "#07172b"),
    },
    "sun": {
        "line": "#6c4109",
        "wall": [(0.0, "#fad35b"), (0.3, "#f3bb37"), (0.75, "#e7a01f"), (1.0, "#d98d17")],
        "lip": ("#ce8513", "#af6c0d"),
        "gloss": ("#fff5c8", "#ffefaf"),
        "face": [(0.0, "#ffe889"), (0.25, "#ffdb5f"), (0.55, "#fdc93b"), (0.8, "#f7b326"), (1.0, "#ef9f19")],
        "face_edge": "#ffd65b",
        "text_outline": "#7b4609",
        "well": ("#1e1102", "#2a1803"),
    },
    "grape": {
        "line": "#2d0d53",
        "wall": [(0.0, "#ad77f7"), (0.3, "#955aee"), (0.75, "#7d41dc"), (1.0, "#6a32c6")],
        "lip": ("#5e25ac", "#4b1b8e"),
        "gloss": ("#ebd8ff", "#e2c9ff"),
        "face": [(0.0, "#d2a5ff"), (0.25, "#bc85ff"), (0.55, "#a465f6"), (0.8, "#8c4de6"), (1.0, "#783bd3")],
        "face_edge": "#af7ef6",
        "text_outline": "#3c136f",
        "well": ("#11051e", "#19092b"),
    },
    "coal": {
        "line": "#0d0e12",
        "wall": [(0.0, "#565c6b"), (0.3, "#484d5b"), (0.75, "#3a3e4a"), (1.0, "#30333d")],
        "lip": ("#22252c", "#1a1c22"),
        "gloss": ("#898f9d", "#7b818f"),
        "face": [(0.0, "#5a606f"), (0.25, "#4f5463"), (0.55, "#444855"), (0.8, "#393c48"), (1.0, "#2f323c")],
        "face_edge": "#545a68",
        "text_outline": "#111217",
        "well": ("#050507", "#09090c"),
    },
    # a light face in the steel bezel (dark labels of its own)
    "cloud": {
        "line": "#717c8f",
        "wall": [(0.0, "#f2f5fa"), (0.3, "#e2e8f0"), (0.75, "#d1d9e4"), (1.0, "#c4cdda")],
        "lip": ("#b7c1d0", "#a2adbf"),
        "gloss": ("#fefeff", "#fafcfe"),
        "face": [(0.0, "#fefefe"), (0.25, "#f6f8fb"), (0.55, "#ecf0f6"), (0.8, "#e1e7f0"), (1.0, "#d6dde8")],
        "face_edge": "#edf1f6",
        "text_outline": "#576277",
        "well": ("#14171c", "#1c2027"),
    },
    # disabled: a flat grey face, a dull grey bezel and a faint sheen (a shiny bezel would still read as tappable)
    "gray": {
        "line": "#4d5056",
        "wall": [(0.0, "#b8bbc1"), (0.3, "#a9adb3"), (0.75, "#9a9ea5"), (1.0, "#8e9299")],
        "lip": ("#81858c", "#72767d"),
        "gloss": ("#dddee1", "#d5d7db"),
        "face": [(0.0, "#c8cbd0"), (0.25, "#bdc0c5"), (0.55, "#b2b5bb"), (0.8, "#a7aab0"), (1.0, "#9c9fa5")],
        "face_edge": "#b8bbc0",
        "text_outline": "#5b5e64",
        "well": ("#17181a", "#1f2023"),
        "sheen": "#ffffff59",
        "bezel": {"outline": "#575a60", "outer": ("#999ca2", "#8d9096"),
                  "inner": ("#c2c5c9", "#b3b6bb"), "rim_light": "#d3d5d8", "depth": ("#7b7e84", "#6e7176")},
    },
}

LAYERS = ("frame", "face", "full")
GRADIENT_KEYS = ("line", "wall", "lip", "gloss", "face", "well")
SOLID_KEYS = ("face_edge", "shadow", "sheen")
REQUIRED_COLORS = GRADIENT_KEYS + ("face_edge",)
COLOR_KEYS = GRADIENT_KEYS + SOLID_KEYS + ("text_outline", "bezel")
BEZEL_GRADIENTS = ("outline", "depth", "outer", "inner")
BEZEL_SOLIDS = ("rim_light",)
# Lanczos-3 downsampling reaches 3 texture px past an edge, the supersampled edge itself one more: the side slices
# keep at least this many texture px beyond the last rounded shape at any scale
RESAMPLE_PX = 4


# --- helpers (scale and supersampling passed in) ------------------------------------------------------------------

def hexc(h: str, a: int = 255) -> tuple:
    h = h.lstrip("#")
    if len(h) not in (6, 8):
        raise ValueError("casual_button: colour %r is not #rrggbb or #rrggbbaa" % ("#" + h))
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16) if len(h) == 8 else a)


def lerp(c0, c1, t):
    return tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(4))


def mask(size, box, radius, blur: float = 0.0) -> Image.Image:
    m = Image.new("L", size, 0)
    dr = ImageDraw.Draw(m)
    radius = max(1, radius)
    # Pillow <= 12.2 joined all four corners into a full ellipse of the box whenever the radius reached half of
    # BOTH sides; 12.3 clamps the diameter to the shorter side instead and draws a stadium for a non-square box.
    # The art (a round button's ring boxes are slightly wider than tall) is the ellipse: decide it here, so the
    # result does not depend on the Pillow version.
    x0, y0, x1, y1 = (round(v) for v in box)
    if 2 * radius >= x1 - x0 - 1 and x1 - x0 >= y1 - y0 - 1:
        dr.ellipse(box, fill=255)
    else:
        dr.rounded_rectangle(box, radius=radius, fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else m


def vstops(size, y0, y1, stops) -> Image.Image:
    """Full-size layer with a vertical multi-stop gradient between rows y0..y1 (clamped outside)."""
    w, h = size
    cs = [(t, hexc(c) if isinstance(c, str) else c) for t, c in stops]
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        t = min(1.0, max(0.0, (y - y0) / max(1, y1 - y0)))
        for i in range(len(cs) - 1):
            if cs[i][0] <= t <= cs[i + 1][0]:
                u = (t - cs[i][0]) / max(1e-6, cs[i + 1][0] - cs[i][0])
                col.putpixel((0, y), lerp(cs[i][1], cs[i + 1][1], u))
                break
        else:
            # stops that do not span 0..1 hold their end colours (rather than leaving such rows transparent)
            col.putpixel((0, y), cs[0][1] if t < cs[0][0] else cs[-1][1])
    return col.resize((w, h), Image.Resampling.NEAREST)


def put(dst: Image.Image, layer: Image.Image, m: Image.Image, opacity: float = 1.0) -> None:
    """Paints [layer] through the coverage mask [m]: the mask scales the layer's alpha only (no blending of its
    colour toward transparent black, which darkened every soft edge)."""
    if opacity < 1.0:
        m = m.point(lambda v: round(v * opacity))
    l = layer.copy()
    l.putalpha(ImageChops.multiply(l.getchannel("A"), m))
    dst.alpha_composite(l)


def downsample(img: Image.Image, ss: int) -> Image.Image:
    w, h = img.size
    return img.resize((w // ss, h // ss), Image.Resampling.LANCZOS)


# --- params ------------------------------------------------------------------------------------------------------

def _rgba(v, key: str) -> tuple:
    if isinstance(v, str):
        return hexc(v)
    if isinstance(v, (list, tuple)) and len(v) in (3, 4) and all(isinstance(x, int) for x in v):
        return tuple(v) + ((255,) if len(v) == 3 else ())
    raise ValueError("casual_button: colour %s=%r is not #rrggbb, #rrggbbaa or [r, g, b(, a)]" % (key, v))


def _is_colour(v) -> bool:
    return isinstance(v, str) or (isinstance(v, (list, tuple)) and len(v) in (3, 4)
                                  and all(isinstance(x, int) for x in v))


def _stops(v, key: str) -> list:
    """One colour (flat), a [top, bottom] pair or [[t, colour], ...] -> [(t, rgba), ...]."""
    if _is_colour(v):
        c = _rgba(v, key)
        return [(0, c), (1, c)]
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        if all(isinstance(e, (list, tuple)) and len(e) == 2 and isinstance(e[0], (int, float))
               and not isinstance(e[0], bool) and _is_colour(e[1]) for e in v):
            return [(e[0], _rgba(e[1], key)) for e in v]
        if len(v) == 2 and all(_is_colour(e) for e in v):
            return [(0, _rgba(v[0], key)), (1, _rgba(v[1], key))]
    raise ValueError("casual_button: gradient %s=%r is not a colour, a [top, bottom] pair or [[t, colour], ...]"
                     % (key, v))


def resolve(params: dict) -> tuple[dict, dict]:
    """(geometry params with defaults, normalised colours) from a block's params."""
    params = dict(params or {})
    unknown = sorted(set(params) - set(DEFAULTS))
    if unknown:
        raise ValueError("casual_button: unknown params %s (known: %s)" % (unknown, sorted(DEFAULTS)))
    p = copy.deepcopy(DEFAULTS)
    p.update(params)

    raw = {"bezel": dict(BEZEL), "shadow": SHADOW, "sheen": SHEEN}
    style = p["style"]
    if style is not None:
        if style not in PRESETS:
            raise ValueError("casual_button: unknown style %r (presets: %s)" % (style, sorted(PRESETS)))
        preset = PRESETS[style]
        raw.update({k: v for k, v in preset.items() if k != "bezel"})
        raw["bezel"].update(preset.get("bezel", {}))
    over = p["colors"] or {}
    if not isinstance(over, dict):
        raise ValueError("casual_button: colors must be a mapping")
    bad = sorted(set(over) - set(COLOR_KEYS))
    if bad:
        raise ValueError("casual_button: unknown colours %s (known: %s)" % (bad, list(COLOR_KEYS)))
    for k, v in over.items():
        if k == "bezel":
            bad = sorted(set(v) - set(BEZEL))
            if bad:
                raise ValueError("casual_button: unknown bezel colours %s (known: %s)" % (bad, list(BEZEL)))
            raw["bezel"].update(v)
        else:
            raw[k] = v
    missing = [k for k in REQUIRED_COLORS if k not in raw]
    if missing:
        raise ValueError("casual_button: colours %s missing: give a style or the full colour set" % missing)

    c = {k: _stops(raw[k], k) for k in GRADIENT_KEYS}
    c.update({k: _rgba(raw[k], k) for k in SOLID_KEYS})
    bz = raw["bezel"]
    c["bezel"] = {k: _stops(bz[k], "bezel." + k) for k in BEZEL_GRADIENTS}
    c["bezel"].update({k: _rgba(bz[k], "bezel." + k) for k in BEZEL_SOLIDS})

    layers = p["layers"]
    layers = [layers] if isinstance(layers, str) else list(layers)
    if not layers or any(l not in LAYERS for l in layers) or len(set(layers)) != len(layers):
        raise ValueError("casual_button: layers %r must be distinct names from %s" % (p["layers"], list(LAYERS)))
    p["layers"] = layers
    if not isinstance(p["ss"], int) or p["ss"] < 1:
        raise ValueError("casual_button: ss must be a positive integer")
    if not 0 <= p["sheen"] <= 1 or not 0 <= p["sheen_fade"] <= 1:
        raise ValueError("casual_button: sheen and sheen_fade must be within 0..1")
    return p, c


# --- drawing -----------------------------------------------------------------------------------------------------

def draw(p: dict, c: dict, scale, circle: bool, layer: str, pressed: bool) -> Image.Image:
    """One layer at [scale]: "frame" -> the drop shadow, the bezel and the very dark well filling everything inside
    it; "face" -> the face alone (its dark line, bevels, panel and sheen) on the same canvas, so the two stack exactly;
    "full" -> the composite ([pressed]: the face sunk into the well). A rectangle is btn_w x btn_h; [circle] is a btn_h
    square with a round body (the same rings, bevels and face around a round panel)."""
    ss = p["ss"]

    def px(v: float) -> int:
        return round(v * scale * ss)

    bz = c["bezel"]
    size = (round((p["btn_h"] if circle else p["btn_w"]) * scale) * ss, round(p["btn_h"] * scale) * ss)
    w = size[0]
    bh = px(p["body_h"])
    xo = (p["btn_h"] - p["body_h"]) / 2.0 if circle else 0.0      # a round body is body_h wide, centred
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    r = px(p["body_h"] / 2.0) if circle else px(p["radius"])
    face_only = layer == "face"
    if not face_only:
        # the soft drop shadow under the body
        so = p["shadow_offset"]
        sh = mask(size, (px(xo), px(so), w - 1 - px(xo), bh - 1 + px(so)), r, blur=px(p["shadow_blur"]))
        put(img, Image.new("RGBA", size, c["shadow"]), sh, p["shadow_opacity"])

    def box(top, side, bottom):
        return (px(xo + side), px(top), w - 1 - px(xo + side), bh - 1 - px(bottom))

    def ring(top, side, bottom, rad, layer_img):
        put(img, layer_img, mask(size, box(top, side, bottom), rad))

    o = p["outline"]
    inner_ring = p["inner_ring"]
    gt, gs, gb = o + p["outer_ring"], o + p["outer_ring"], o + p["depth"] + p["outer_ring"]
    if not face_only:
        put(img, vstops(size, 0, bh, bz["outline"]), mask(size, box(0, 0, 0), r))
        ring(o, o, o, r - px(o), vstops(size, 0, bh, bz["depth"]))
        ring(o, o, o + p["depth"], r - px(o), vstops(size, 0, bh, bz["outer"]))
        ring(gt, gs, gb, r - px(o + p["outer_ring"]), vstops(size, 0, bh, bz["inner"]))
        # the inner ring's lighter first row (top and upper sides), fading out downwards
        e = p["rim_light"]
        edge = mask(size, box(gt, gs, gb), r - px(gt))
        edge = Image.composite(Image.new("L", size, 0), edge, mask(size, box(gt + e, gs + e, gb + e), r - px(gt + e)))
        fade = vstops(size, px(gt), bh * p["rim_light_fade"],
                      [(0, (255, 255, 255, 255)), (1, (255, 255, 255, 0))]).getchannel("A")
        ge = Image.new("RGBA", size, bz["rim_light"])
        ga = Image.composite(fade, Image.new("L", size, 0), edge)
        if bz["rim_light"][3] < 255:     # a translucent rim light colour scales the row's alpha
            ga = ga.point(lambda v: round(v * bz["rim_light"][3] / 255))
        ge.putalpha(ga)
        img.alpha_composite(ge)
    wt0, ws0, wb0 = gt + inner_ring, gs + inner_ring, gb + inner_ring
    if layer == "frame":
        # the well the face sinks into: everything inside the bezel very dark in the button's tone
        ring(wt0, ws0, wb0, r - px(wt0), vstops(size, px(wt0), bh - px(wb0), c["well"]))
        return downsample(img, ss)
    # inside the bezel: pressed, it all sinks straight into the bezel, deeper at the top (the bezel stays)
    pt_, ps_, pb_ = (p["press_top"], p["press_side"], p["press_bottom"]) if pressed else (0.0, 0.0, 0.0)
    if pressed:
        # the well it sinks into: a very dark socket in the button's tone, the face's full size and shape, so
        # the ring the sunk face uncovers reads as a dark border (unpressed, the face covers it all: not drawn)
        ring(wt0, ws0, wb0, r - px(wt0), vstops(size, px(wt0), bh - px(wb0), c["well"]))
    lt, ls, lb = gt + inner_ring + pt_, gs + inner_ring + ps_, gb + inner_ring + pb_
    # the layers touching the bezel follow its rounding (concentric: the dark line stays thin at the corners);
    # only the innermost panel has corners of its own
    ring(lt, ls, lb, r - px(lt), vstops(size, px(lt), bh - px(lb), c["line"]))
    # the face: a bevelled pillow - a light TOP bevel (it catches the light: the "gloss"), SIDE walls, a dark BOTTOM
    # bevel (the lip), mitred into each other at the corners, and the flat panel inside them with its own long
    # gradient, a light line along its bottom edge and the sheen over its upper part
    wt, ws, wb = lt + p["line"], ls + p["line"], lb + p["line_bottom"]
    rw = max(2, r - px(wt))
    block = box(wt, ws, wb)
    block_mask = mask(size, block, rw)
    pt, ps, pb = wt + p["gloss"], ws + p["wall"], wb + p["lip"]
    panel_box = box(pt, ps, pb)
    if circle:
        rp = max(2, min(panel_box[2] - panel_box[0], panel_box[3] - panel_box[1]) // 2)
    else:
        rp = max(2, px(p["panel_radius"]))
    put(img, vstops(size, block[1], block[3], c["wall"]), block_mask)

    def bevel(points, layer_img):
        m = Image.new("L", size, 0)
        ImageDraw.Draw(m).polygon(points, fill=255)   # (supersampling anti-aliases it: no blur, no dark seams)
        put(img, layer_img, Image.composite(m, Image.new("L", size, 0), block_mask))

    if circle:
        # round: the ring between the body and the panel splits into quarters at the diagonals (top: the gloss,
        # bottom: the lip, sides: the walls), mitred through the panel's centre
        cx, cy = (panel_box[0] + panel_box[2]) / 2.0, (panel_box[1] + panel_box[3]) / 2.0
        bevel([(cx, cy), (block[0], block[1]), (block[2], block[1])],
              vstops(size, block[1], panel_box[1], c["gloss"]))
        bevel([(cx, cy), (block[2], block[3]), (block[0], block[3])],
              vstops(size, panel_box[3], block[3], c["lip"]))
    else:
        bevel([(block[0], block[1]), (block[2], block[1]), (panel_box[2], panel_box[1]), (panel_box[0], panel_box[1])],
              vstops(size, block[1], panel_box[1], c["gloss"]))
        bevel([(panel_box[0], panel_box[3]), (panel_box[2], panel_box[3]), (block[2], block[3]), (block[0], block[3])],
              vstops(size, panel_box[3], block[3], c["lip"]))
    pm = mask(size, panel_box, rp)
    put(img, vstops(size, panel_box[1], panel_box[3], c["face"]), pm)
    # the panel's light bottom edge
    be = Image.composite(Image.new("L", size, 0), pm,
                         mask(size, (panel_box[0], panel_box[1], panel_box[2], panel_box[3] - px(p["face_edge_width"])), rp))
    put(img, Image.new("RGBA", size, c["face_edge"]), be)
    if p["sheen"] > 0:
        # the sheen: a capsule of light across the panel's upper part, inset from its sides (its rounded ends stay in
        # the side slices), fading downwards and clipped to the panel
        top = pt + p["sheen_offset"]
        sbox = box(top, ps + p["sheen_inset"], p["body_h"] - top - p["sheen_height"])
        # (a round panel gets an ellipse: the radius covers the whole box)
        srad = (sbox[2] - sbox[0]) // 2 + 1 if circle else px(p["sheen_height"] / 2.0)
        sm = ImageChops.multiply(mask(size, sbox, srad, blur=px(p["sheen_soft"]) / 2.0), pm)
        col = c["sheen"]
        a0 = col[3] * p["sheen"]
        light = vstops(size, sbox[1], sbox[3], [(0, col[:3] + (round(a0),)),
                                                (1, col[:3] + (round(a0 * p["sheen_fade"]),))])
        put(img, light, sm)
    return downsample(img, ss)


def side_slice(p: dict, scale) -> int:
    """The left / right slice in texture px: every rounded shape must sit inside it - the face panel's corners and the
    sheen's rounded ends (pressed in by `press`) and the bezel's corners (the drop shadow's blur spreading them a
    little) - plus an anti-aliasing allowance that holds at any scale (at least RESAMPLE_PX texture px)."""
    panel_side = p["outline"] + p["outer_ring"] + p["inner_ring"] + p["line"] + p["wall"]   # the panel's left edge
    pressed_side = panel_side + max(p["press"], p["press_side"])
    panel = pressed_side + p["panel_radius"]
    bezel = p["radius"] + 1.5 * p["shadow_blur"]
    terms = [(panel + p["slice_margin"]) * scale, panel * scale + RESAMPLE_PX, bezel * scale + RESAMPLE_PX]
    if p["sheen"] > 0:
        sheen = pressed_side + p["sheen_inset"] + p["sheen_height"] / 2.0 + p["sheen_soft"]
        terms.append(sheen * scale + RESAMPLE_PX)
    return math.ceil(max(terms))


def _dp(v: float) -> float:
    return round(float(v), 6)


def render(params: dict, scale) -> dict:
    """The casual button at [scale] texture px per dp (DESIGN.md §2.3)."""
    p, c = resolve(params)
    circle = bool(p["circle"])
    outputs = {}
    for layer in p["layers"]:
        key = "main" if layer == "full" else layer
        outputs[key] = draw(p, c, scale, circle, layer, bool(p["pressed"]) and layer == "full")
    if circle:
        slice_px = None
    else:
        side = side_slice(p, scale)
        mid = round(p["btn_h"] * scale) // 2 - 1      # vertically: everything fixed but the two middle rows
        slice_px = [side, mid, side, mid]
    content = p["content"]
    return {
        "outputs": outputs,
        "slice_px": slice_px,
        "size": [_dp(p["btn_h"] if circle else p["btn_w"]), _dp(p["btn_h"])],
        "content": None if content is None else [_dp(v) for v in content],
        "overhang": [0.0, 0.0, 0.0, _dp(p["btn_h"] - p["body_h"])],     # the drop shadow below the body
    }
