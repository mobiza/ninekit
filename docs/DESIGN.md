# ninekit — design (v1 contract)

ninekit is an **engine-agnostic sprite generator** for game and app UI. A YAML spec describes UI pieces
(panels, buttons, pills, badges, cards, bars, frames, icons drawn whole) as stacks of vector layers;
`ninekit build` renders every piece at every requested scale into PNG sprites plus one engine-neutral
manifest (`ninekit.json`) carrying the 9-slice borders, stretch modes and content insets. Exporters turn
that manifest into what each engine wants (Godot, Unity, Flutter, CSS/web, Phaser, plain JSON).

It was extracted from the UI pipeline of a production mobile game and keeps that pipeline's rules:

* everything is drawn in code from measured numbers, never painted by hand;
* signed-distance shapes with one texel of anti-aliasing, layered back to front;
* gradients run vertically and every horizontal feature sits inside the fixed slices, so the stretched
  middle columns are identical and a piece stretches to any width without a trace;
* textures are tiny: the fixed slices plus a few identical middle columns;
* nothing ships without a measured check (`ninekit verify`) and a look (`ninekit preview`).

This document is the contract between the modules. If code and this document disagree, fix one of them
deliberately — never silently.

---

## 1. Units

* **dp (design px)** — the logical unit every spec number is in. A piece is `size: [w, h]` dp.
* **scale** — texture px per dp. A spec renders at one or more scales (`scales: [1, 2, 3]`). Every scale
  is rendered natively from the vector description (never resampled from another scale).
* Texel centres: texel (i, j) of a canvas at scale s covers dp point `((i + 0.5) / s, (j + 0.5) / s)`.
* **dp grid** `g`: the smallest dp step that is a whole number of texels at every scale of the spec
  (`g x s` whole for every s; computed with exact fractions): `[1, 2, 3]` -> 1 dp, `[3]` -> 1/3 dp,
  `[2, 4]` -> 1/2 dp, `[1.5, 3]` -> 2/3 dp, `[1, 1.5, 2, 3, 4]` -> 2 dp. A spec may set `grid:` to a coarser
  whole multiple (e.g. `grid: 1` with `scales: [3]` for whole-dp, web-friendly slices); scales whose grid
  would be coarser than 4 dp are refused. Sizes, auto slices, `keep` and noise/image periods snap to it, so
  every file of a piece is its dp numbers x its scale exactly (one dp slice is exact at every scale).
* Canvas size: the size snapped to the nearest grid point, `n = round(w / g)` steps (Python's `round`),
  i.e. `n x g x s` px at scale s. With one scale the grid is one texel and this is the plain
  `round(w * s)`. Build reports a size the grid moved by more than half a texel of the largest scale (more
  than rounding to that scale's texels alone would). Inside layers, `w` and `h` are that canvas measured back
  in dp (`w_px / s`, `h_px / s`), the same at every scale, so shapes written against `w`, `h` always reach
  the canvas edges.

## 2. Spec format (YAML, `ninekit: 1`)

```yaml
ninekit: 1
name: gumdrop                # manifest name
description: ...             # optional free text (also allowed in themes and pieces)
scales: [3]                  # texture px per dp, one file per scale
grid: 1                      # optional: a coarser dp grid than the scales need (here whole dp at 3x)
out: out/                    # output folder, relative to the spec file
file: "{piece}{output}{scale}.png"   # file name template, see below
include: [theme.yaml]        # optional; merged first (this file wins)
vars:                        # numbers / expressions (see 2.1 for how names resolve)
  U: 393 / 1179              # dp per reference px (design width / screenshot width)
  R: 42 * U                  # a corner radius measured as 42 px
colors:                      # names -> "#rrggbb" / "#rrggbbaa", another name, or a list of stops
  lilac: "#F4EFFD"
  face: [[0, "#FFFFFF"], [1, "#E5DDF7"]]     # a named gradient: {vgrad: face}
params:                      # optional block params by piece name ("*" = every block piece)
  "*": {style: mint}
pieces:
  card:
    size: ["(2 * round((R + 1.5) * scale) + 6) / scale", 70]
    slice: auto              # auto | none (or null) | [l, t, r, b] dp ; or slice_px: [...] (see 2.4)
    stretch: [stretch, stretch]   # x, y: stretch | tile | fixed; one value = both axes (`stretch: tile`)
    content: [8, 6, 8, 10]   # optional dp insets for children/labels
    overhang: [0, 0, 0, 1]   # optional dp the art reaches outside the logical rect (shadows)
    compact: true            # auto slices only: remove identical middle lines (2.4)
    keep: 2                  # dp of identical middle kept by compaction (on the grid)
    period: [0, 0]           # optional dp repeat of a tiled *shape* per axis (2.4; 0 = none)
    mask: <shape>            # optional final silhouette: every output's alpha x this shape's coverage (2.2)
    layers: [...]            # see 2.2
    variants:                # optional: extra pieces sharing everything but overrides
      card_me: {colors: {lilac: "#EBFCF3"}}
```

`ninekit build spec.yaml --theme other.yaml` merges a theme file (vars/colors/params only) over the spec:
the same pieces in another concept.

Merging (includes, themes, variants) is a deep merge: mappings merge key by key, anything else (lists,
numbers, strings) is replaced. A variant is its base piece with the variant's keys merged over it (so a
variant may also replace `size` or `layers`). Unknown keys anywhere are errors (typos never pass silently).

### 2.1 Values and expressions

* Any numeric field accepts a number or an expression string.
* Expressions: `+ - * / // % **`, unary minus/plus, parentheses, numbers, names, comparisons
  `< <= > >= == !=` (they give 1 or 0, for `when`), the constant `pi`, and the functions
  `round min max abs floor ceil sqrt sin cos clamp(x, lo, hi) lerp(a, b, t)` (`sin`/`cos` in radians;
  `round(x, n)` rounds to n decimals).
  Names: `vars` (spec, theme, piece, variant — innermost wins), `scale` (current scale), `w`, `h`
  (the piece size in dp, inside layers and slices), `w_px`, `h_px` (inside `slice_px` only).
  Evaluated with a whitelist AST walker — never `eval`; attribute access, subscripts, strings, keyword
  arguments and any other call are rejected with a message naming them.
* Vars resolve lazily in one flat scope per piece (spec < theme < piece < variant, innermost wins): a var
  may use any other var (earlier or later) and sees the overrides (a variant changing `R` changes every var
  derived from `R`); cycles are errors. Vars hold numbers or expressions only; a var that uses `w`/`h` works
  inside layers but not in `size`. Var names may not shadow the built-in names or functions.
* Colour fields accept `"#rrggbb"`, `"#rrggbbaa"` or a name from `colors` (names may point at other
  names). A `colors` entry may also be a list of `[t, colour]` stops: a named gradient, usable wherever
  stops are expected (`vgrad: face`, `depth: bevel`, noise `stops: rock`) — themes and variants swap
  gradients like colours. In `mode: shade` pieces a colour field is a number 0..1 (a shade) instead, and
  `colors` entries are shades.
* `round` is Python's `round` (banker's rounding), so numbers ported from Python generators reproduce
  exactly. Expressions keep Python's float semantics and operator order, so `round(42 * U * scale) / scale`
  is bit-identical to the same expression in Python.

### 2.2 Layers

Layers paint back to front onto a float RGBA canvas (straight alpha, source-over by default).

```yaml
- shape: <shape>          # required (use {all: true} for the whole canvas)
  fill: <paint>           # required
  grow: 0                 # dp; shifts the edge outwards (sdf - grow)
  ring: 0                 # dp; keep only the band of this width just inside the edge
  clip: <shape>           # multiply the coverage by this shape's coverage (canvas coords, not offset)
  soft: 0                 # dp blur width of the edge (0 = one texel of anti-aliasing)
  falloff: linear         # linear | smooth | exp   (shape of the soft edge)
  opacity: 1
  offset: [0, 0]          # dp; moves the shape (not the paint)
  blend: normal           # normal | add | multiply | screen | erase | atop
  roughen: {amount: 0.8, period: 12, seed: 0}   # optional: perturbs the edge with tileable noise
  output: main            # which output image this layer belongs to (see 2.5)
  when: 1                 # expression; the layer is skipped when it evaluates to 0
  name: face              # optional label, used in error messages
```

Coverage = `cover(sdf, soft)`: `clip(0.5 - d / width, 0, 1)` with `width = max(soft, 1 / scale)` for
`linear` (one texel of anti-aliasing when `soft` is 0); `smooth` applies smoothstep to that; `exp` uses
`exp(-max(d, 0) * 3 / width)` outside and 1 inside (glows; on a `ring` it glows to both sides of the band).

Order per layer: shape (moved by `offset`) → `roughen` → `grow` → `ring` → coverage (`soft`, `falloff`) ×
`clip` coverage → × `opacity` → × the paint's alpha → composite with `blend`. Blends on the straight-alpha
canvas: `normal` is source-over (a fixed float operation order); `add` is Porter-Duff plus (premultiplied sums, alpha
clamped at 1); `multiply` / `screen` are the W3C separable blends with source-over compositing; `erase`
is destination-out (the layer's coverage removes alpha, colours stay); `atop` is source-atop (it paints only
where the canvas already has alpha and never changes the alpha).

**Shared edges.** Layers that share the same outer edge stack their anti-aliased fringes (the silhouette
grows ~0.6 px fatter at 3x). Two ways to keep one edge: paint the later layers `blend: atop` (they cannot add
alpha), or draw every layer that reaches the silhouette oversized (`{all: true}`, `grow`) and give the piece
`mask: <shape>`: after all layers, every output's alpha is multiplied by that shape's coverage (one texel of
anti-aliasing; `mask: {shape, grow, soft, roughen}` for more). Not on block pieces.

`roughen: {amount, period, scale, octaves, seed}` adds tileable value noise (−amount..amount dp) to the
shape's sdf: torn paper, chipped stone. `period` is a dp number or `[pw, ph]` (0 = no variation along that
axis; snapped to the grid like a noise period). It counts as a periodic paint: fine on pieces drawn whole,
on `tile` axes (the region becomes whole periods) and `fixed` axes; along a `stretch` axis it is a problem.

**Shapes** (all coordinates dp; expressions may use `w`, `h`):

| shape | meaning |
|---|---|
| `{rect: [x0, y0, x1, y1], r: R}` | rounded rect; `r` one radius or `[tl, tr, br, bl]`; optional `chamfer: c` or `[tl, tr, br, bl]` (45° cut corners, exact sdf; a corner uses chamfer if > 0, else radius). Corners are chosen per quadrant, so a corner should not exceed half the shorter side (chamfers are clamped to it) |
| `{inset: d \| [l, t, r, b], r: R, chamfer: c}` | rounded rect inset from the canvas edges |
| `{circle: [cx, cy, r]}` | circle |
| `{ellipse: [cx, cy, a, b], angle: deg}` | ellipse (an approximate sdf, exact on the axes) |
| `{polygon: [[x, y], ...]}` | exact polygon sdf |
| `{union: [s, ...]}`, `{intersect: [s, ...]}`, `{subtract: [a, b, ...]}` | min / max / max(a, -min(b, ...)) |
| `{all: true}` | everything (sdf = -inf; a large negative number in practice) |

**Paints:**

| paint | meaning |
|---|---|
| `"#hex"`, name, number (shade mode) | solid |
| `{vgrad: [[t, c], ...], from: y0, to: y1}` | vertical gradient over dp rows `from..to` (default `0..h`), clamped outside; linear interpolation per channel |
| `{lgrad: [[t, c], ...], angle: deg}` or `{lgrad: ..., from: [x0, y0], to: [x1, y1]}` | linear gradient at an angle (degrees; 0 = left → right, 90 = top → bottom), spanning the canvas (its corners project onto 0 and 1, like CSS), or between two dp points (clamped outside) |
| `{rgrad: [[t, c], ...], center: [cx, cy], radius: r, ratio: k}` | radial gradient: t = distance / `radius` from `center` (default the canvas centre, half the shorter side), `ratio` = vertical / horizontal radius (an ellipse) |
| `{depth: [[d, c], ...]}` | colour by distance *inside* the layer's edge (`-sdf` after `grow`, before `ring`, dp): bevels, cushions, inner glows |
| `{noise: {kind: value \| grain \| wood, period: [pw, ph], scale: s, octaves: n, seed: k, stops: [[t, c], ...], warp: a, axis: x \| y}}` | procedural, tileable with the given dp period; the axis it varies along must be `tile` (it repeats) or `fixed` (natural length), never `stretch` |
| `{image: path, tile: true, size: [dw, dh]}` | an external (seamless) texture, path relative to the spec, drawn at `size` dp per tile (default: one image px per dp); `tile: false` draws it once at the origin |

Stops with alpha (`#rrggbbaa`) interpolate premultiplied (no dark fringe fading to transparent); a paint's
alpha multiplies the layer's coverage. Without alpha stops the interpolation is straight per channel.

Noise details: a period is snapped to the dp grid (`round(p / g)` steps, at least one; with one scale that
is `round(p * scale)` texels), so the texture repeats exactly and the period is the same dp at every scale;
a period of `0` means no variation along that axis (e.g. `wood` with `period: [0, 12]` stretches
in x). `scale` is the feature size in dp (default a quarter of the longest period); the lattice wraps at a
whole number of cells per period, so the pattern is the same at every scale. `value`: smooth fBm value
noise (`octaves`, default 3). `grain`: one random value per cell, no smoothing (cell default: one texel).
`wood`: horizontal grain lines (needs a y period) bent by low-frequency noise; `warp` is how far the rings
bend, in rings (default 1.5; 0 = straight rings; `wood` only). `axis` is the grain direction: `x` (default)
as described; `y` is the x pattern turned 90° (computed with the periods swapped and transposed, so it tiles
with the `period` as written: vertical wood needs an x period). `seed` default 0, `stops` default black →
white (0 → 1 in shade mode). Images tile by resampling a 3×3 mosaic, so the filter wraps; a tiled image's
`size` snaps to the grid like a noise period (`tile: false` images are drawn at `round(size * scale)`).


`lgrad` / `rgrad` are for pieces drawn whole and for art inside the fixed slices: across a stretch region they
break the identical-middle-columns (or the smooth-rows) rule, and auto slicing / `verify` catch it like any
other horizontal feature. Anything horizontal belongs inside the side slices.

### 2.3 Blocks (code recipes)

A piece may use `block: <name>` + `params: {...}` instead of `layers`. A block is a Python function for
art that the layer language cannot express (yet). Registry: `ninekit/blocks/__init__.py` maps a name to
`"module:function"` and imports lazily.

```python
def render(params: dict, scale: int) -> dict:
    """Returns {
        "outputs": {"main" | "<name>": PIL.Image (RGBA, texture px at this scale)},
        "slice_px": [l, t, r, b] | None,     # None = not sliced (drawn whole)
        "size": [w_dp, h_dp],
        "content": [l, t, r, b] | None,      # dp
        "overhang": [l, t, r, b] | None,     # dp
    }"""
```

`params` values are resolved against the block module's `DEFAULTS` mapping: a string is evaluated as an
expression (`"R + 2"`, with the piece's vars and `scale`) only for a key whose default is a number, or element
by element for a key whose default is a list of numbers; an invalid expression there is an error. Everything
else is passed exactly as written: names such as `style: mint` (even when a var `mint` exists), colour
strings, booleans, lists of names (`layers: [frame, face]`) and nested mappings like
`colors: {bezel: {inner: "#..."}}` (never evaluated, flattened or renamed). A block without `DEFAULTS` gets
numbers only (strings stay strings). Top-level `params` (spec, includes, theme) merge over a piece's own:
`"*"` first, then the piece's name; they reach block pieces only, while `params` on a layered piece (or its
variant) is an error. A block piece takes `size`, `slice_px`, `content` and `overhang` from the block's result:
no auto slicing and no compaction (`slice_px: None` = drawn whole); `size`, `slice`, `slice_px`, `layers`,
`outputs`, `compact` and `keep` are errors on a block piece, while `stretch`, `mode`, `content` and
`overhang` may be set (the last two override the block's). With one scale the block's `slice_px` is used
as is (single-scale legacy art reproduces exactly). With several scales its per-scale slices are put on the dp
grid (2.4) so every file shares one dp slice: per side the largest `slice_px / scale` over the scales, rounded up to the grid, then
`slice_px = that x scale` in every file. The middle then lies inside each scale's own middle, so the block's
stretch rule still holds. An axis left with less than one grid step in the middle (or requested `fixed`)
becomes `fixed` with exactly one grid step in the middle: `casual_button` at `[1, 2, 3]` is x 28 dp and
y fixed (30 / 31 dp), a button used at its natural height. Skipped (kept as the block made them): `tile`
axes, blocks drawn whole, and canvases that are not whole grid steps at every scale (verify then warns).
A block may return `main` alongside named outputs (e.g. a composite `main` next to `frame` / `face`); each
becomes a file. First block: `casual_button` — a casual push button with a metal bezel and a bevelled, glossy
pillow face (frame + face layers, rectangular and circle forms), every measurement and colour a parameter; its
defaults and presets are the Gumdrop sample concept (`examples/gumdrop/`).

### 2.4 Slicing

Every file of a piece shares one dp size and one dp slice: `size_px == size x s` and
`slice_px == slice x s` at every scale s, exactly. Flutter's single `centerSlice` (logical px) and CSS's
`image-set()` with one `border-image-slice` rely on it. Auto slicing therefore looks at all scales of a piece
at once and works in grid steps (`g`, see 1); `build --scales` still decides over the spec's scales, so it
writes the same files a full build writes.

* `slice: [l, t, r, b]` — dp; per scale `round(v * scale)` texture px. A value that is not on the grid is
  kept as written (never moved) and reported as a warning: its files cannot share one dp slice.
* `slice_px: [exprs]` — evaluated per scale with `w_px, h_px, scale` (exact reproduction of legacy art);
  untouched by the grid.
* `slice: none` (or `null`) — drawn whole (icons, round buttons, medals); still multi-scale.
* `slice: auto` (default) — computed from the rendered pixels of every scale (all outputs of the piece
  together). Per scale the run of lines below is found and rounded inwards to whole grid steps; each side's
  slice is the largest over the scales (in dp), so the middle lies inside every scale's run:
  * x (`stretch`): the run of byte-identical columns around the centre column (for an even width both centre
    columns are tried, the longer run wins). Shorter than 3 columns at any scale, or no whole grid step in
    common, is a problem: the piece cannot stretch horizontally (a mirror-symmetric feature centred on the
    piece always gives 2 equal centre columns, which is not a stretchable middle). Its files get an empty x
    middle, so `verify` fails the manifest too. A piece that is not meant to stretch horizontally says
    `stretch: [fixed, ...]`.
  * y (`stretch`): the longest *smooth* run of rows around the centre row: adjacent rows differ by ≤ 8/255
    and every three consecutive rows bend by ≤ 3/255 (|row i − 2 row i+1 + row i+2|, every channel incl.
    alpha); identical rows are smooth too. The bend rule catches low-contrast slanted lines and patterns
    (a 22 %-opacity "///" passes 8/255 per row but bends 6–13/255 where it crosses a texel); a gradient bends
    only at its stops (measured ≤ 6/255, at the ends of gradients, so their last row moves into the slice). A short identical run never wins over a longer smooth
    one: the identical rows around the centre are used instead only when the smooth run is at most 1 dp
    longer on each side (the anti-aliased start of rounded corners, so flat pieces still compact). When the
    smooth runs of the scales share less than one whole grid step (a pill or bar fully rounded vertically, a
    sharp line through the centre), the axis becomes `fixed`.
  * `fixed` (requested in `stretch`, or y as above): the axis keeps its natural length. Its slices leave
    exactly one grid step in the middle (centred); nothing is checked or compacted there. Runtimes must not
    stretch a fixed axis (draw the piece at its natural length on it).
  * `tile`: with P the period of the piece's periodic paints and `roughen`s, and of the piece's `period:`
    hint (lcm of their texel periods; one grid step if none), which must be the same dp at every scale
    (periods snap to the grid), the region `[l, l + k·P)` starts on a grid step and holds the most whole
    periods such that at every scale line x matches line x + P (within 2/255) across it (ties: the most
    centred); the line after it repeats its first (seamless). When the repeating thing is a *shape* (a
    segmented bar), give the piece `period: [pw, ph]` (dp, 0 = none; only on `tile` axes); without any period
    the tile is just a run of identical lines and `build` warns. No region → the problem "no tile period found
    on x/y; give `period:`" (and an empty middle, which `verify` reports the same way).
  * Problems found while slicing (no stretchable middle, a periodic paint or `roughen` varying along a
    `stretch` axis (on a `fixed` axis it is fine), a size that differs per scale) are reported by `build` and fail `verify SPEC`. An auto-sliced piece needs
    one dp size: a `size` written with `scale` that snaps to different grid points per scale is a problem
    (use dp, or `slice_px` for exact legacy art).
* `compact: true` (default when `slice: auto`): identical middle columns (and identical middle rows) are
  removed losslessly down to `keep` dp (default 2, rounded up to the grid), the same dp at every scale, and
  `size` / `slice` are updated. Only `stretch` axes whose whole middle is byte-identical at every scale are
  compacted (never explicit slices, `tile` or `fixed` axes, smooth y runs, or pieces with problems).
  Lossless means: drawn as a 9-slice at any size, the compacted and the uncompacted texture give identical
  pixels (tested with ninekit's resampler).
* Warnings (reported by `build`, listed by `verify SPEC`, never failures): a size the grid moved, explicit
  `slice` values off the grid.

Block pieces are not auto-sliced or compacted (the block draws them and reports its slices); with several
scales their slices are unified on the grid as described in 2.3, with the same `fixed` rule.

### 2.5 Outputs and modes

* `outputs: [frame, face]` declares several images per piece on the same canvas (they stack exactly);
  each layer goes to `layer.output` (default the first output). Single-output pieces use `main`.
* File template tokens: `{piece}`, `{output}` (`""` for `main`, else `_<name>`), `{scale}` (`""` when the
  spec declares a single scale, else `@<s>x` with `s` like `2` or `1.5`; `build --scales` does not change
  names). Default `"{piece}{output}{scale}.png"`; the template may contain folders. Two files with one
  name are an error.
* `mode: shade` — the art is written in shades, not colours: R = G = B = shade (0..1), A = coverage.
  Runtimes map the shade through a colour ramp (one art, any tone). Manifest records `"mode": "shade"`.

## 3. Manifest (`ninekit.json`, schema 1)

Written next to the PNGs. Engine adapters and exporters read only this file.

```json
{
  "ninekit": 1,
  "name": "gumdrop_scoreboard",
  "generator": "ninekit 0.1.0",
  "scales": [1, 2, 3],
  "pieces": {
    "card": {
      "size": [36.0, 60.0],
      "slice": [17.0, 15.0, 17.0, 21.0],
      "stretch": ["stretch", "stretch"],
      "content": [14, 10, 14, 16],
      "overhang": [0, 0, 0, 3],
      "mode": "color",
      "slicing": "auto",
      "stack": ["main"],
      "outputs": {
        "main": {
          "1": {"file": "card@1x.png", "size_px": [36, 60],   "slice_px": [17, 15, 17, 21]},
          "3": {"file": "card@3x.png", "size_px": [108, 180], "slice_px": [51, 45, 51, 63]}
        }
      }
    }
  }
}
```

* `slice` / `slice_px` are `null` for pieces drawn whole. `slice_px` is authoritative for a file.
* Piece-level `size` and `slice` (dp, 2 decimals) are the largest scale's `size_px` / `slice_px` divided by
  that scale (a block piece's `size` is the block's own). For layered pieces every file is exactly these dp
  values x its scale (2.4); `verify` fails an auto-sliced piece whose files are not, and warns for the others
  (explicit off-grid `slice`, `slice_px`, blocks).
* `stretch` per axis: `stretch` (the middle is stretched), `tile` (the middle repeats in whole tiles) or
  `fixed` (the axis keeps its natural length; its middle is one grid step and must not be stretched: a
  runtime without a "fixed" mode draws the piece at its natural length on that axis).
* `design_size`: the piece's size as designed (dp): the spec's size on the grid before compaction (a block's
  own size). It is the natural size to show the piece at; `size` is the (compacted) texture's.
* `slicing`: where the slices came from: `auto`, `slice` (explicit dp), `slice_px`, `none` (drawn whole) or
  `block`. Readers that do not know the key ignore it.
* `content` / `overhang` are `null` when the spec (or block) gives none.
* **Box model (every runtime follows it).** All insets — `slice`, `content`, `overhang` — are measured
  from the edges of the *canvas* (the full texture). The **logical box** a user sizes and lays out is the
  canvas minus `overhang` (the art may reach outside it: shadows, glows). Children/labels are padded inside
  the logical box by `max(0, content − overhang)` per side. Example: `casual_button` is 128×62 dp with
  overhang `[0, 0, 0, 3]` and content `[12, 8, 12, 17]` → logical box 128×59, child padding
  `[12, 8, 12, 14]`, label centre on the face panel's centre 26.5 dp below the canvas top.
* **Press (frame/face pieces).** The face output and the content scale together toward the centre of the
  logical box (0.92 by default) and spring back; the frame stays.
* **Tiles.** `stretch: tile` repeats whole tiles (the count is fitted to the length: Godot TILE_FIT, CSS
  `round`), never a cut last tile.
* `stack` lists the outputs bottom to top, as a runtime layers them (the `outputs` mapping is key-sorted,
  so it cannot carry the order). When `main` sits next to named outputs it is their composite, an
  alternative to stacking them (previews skip it).
* Scale keys are strings: `"3"`, `"1.5"`.
* Paths are relative to the manifest. Keys are sorted, two-space indent, trailing newline (stable diffs).

## 4. CLI

```
ninekit build   SPEC [--theme T] [-o OUT] [--only a,b] [--scales 1,2,3] [--json]
ninekit verify  SPEC|MANIFEST [--theme T] [--json]   # exit 1 on any failure
ninekit preview SPEC|MANIFEST [--theme T] [-o sheet.png] [--bg "#hex"] [--scale S]
ninekit compare SPEC|MANIFEST PIECE REF.png [--crop x,y,w,h] [--outputs frame,face] [--bg "#hex"]
                [--ref-scale S] [--theme T] [--zoom N] [-o compare.png] [--json]
ninekit render  SPEC|MANIFEST PIECE --size WxH [--outputs a,b] [--scale S] [--pressed] [--theme T]
                -o file.png [--json]
ninekit export  MANIFEST --target json|godot|unity|flutter|css|phaser -o DIR [--scale S] [--runtime]
ninekit measure IMAGE (--x X | --y Y) [--from A --to B] [--ref-width W --design-width D]
                [--avg N] [--tol T] [--min-band P] [--json]
ninekit new     DIR                              # scaffold a starter spec
```

`--json` prints machine-readable results (for agents). Every command prints what it wrote. A MANIFEST
argument may also be the folder holding `ninekit.json`; `--theme` applies to a SPEC only (an error with a
manifest).

`compare` draws the piece's stacked outputs (default: its `stack` without a composite `main`) from the
largest scale's files as a 9-slice with ninekit's resampler at exactly the crop's pixel size (default crop:
the whole reference): it renders `crop x scale / ref-scale` texels (corners 1:1 in texture px) and resamples
that to the crop when the reference has another density (`--ref-scale`, reference px per dp; default the
largest scale). Both sides are composited on `--bg` (default `#3B4252`) and written side by side as
`reference | ninekit | |difference| heatmap` (difference x4: black → red → yellow → white). It prints mean
and max absolute difference (8-bit RGB), PSNR (dB; `null`/inf when identical) and the % of pixels whose
largest channel difference is over 16/255. Without `-o` it writes `<spec out>/compare_<piece>.png` (for a
manifest: `compare_<piece>.png` next to it), never into the working folder.

`render` draws a piece at any dp size (`--size WxH`) as a transparent PNG, the way a runtime draws it: the
stacked outputs (default its `stack` without a composite `main`) from one scale's files (`--scale`, default
the largest; px = dp x scale) as 9-slices with ninekit's resampler (tile axes in whole fitted tiles).
`--pressed` scales the `face` output by 0.92 toward the centre of the logical box (canvas minus overhang)
while the frame stays (frame/face pieces only). Stretching a `fixed` axis is allowed but noted. For mockups
and for agents checking a size.

`measure` samples one line of a reference image and lists its bands: `--avg N` averages N px across the
line, `--tol T` is the largest adjacent difference inside a band (0..255, default 10), `--min-band P` merges
bands thinner than P px (default 1); with `--ref-width W --design-width D` positions are also given in dp
(`dp = ref px x D / W`).

Exit codes: 0 success, 1 `verify` failures, 2 errors (bad spec, missing file, unknown target...; printed
as `error: ...`, or `{"ok": false, "error": ...}` with `--json`). `build` writes the files even when a
piece has slicing problems: it reports them as warnings (`"problems"` in JSON, `"ok": false`) and leaves
the gate to `verify`. `build` also reports warnings (`note:` lines; `"warnings"` in JSON) that never fail anything:
sizes the grid moved, explicit slices off the grid. `verify SPEC` and `preview SPEC` build into a temporary
folder first (a fresh render, never stale files); `preview` writes `<out>/<name>.preview.png` by default. `build --only` updates the
existing manifest's other pieces in place. `export` takes the manifest or its folder.

## 5. verify

Per file (every output × scale):

1. `slice_px` inside the image; `l + r ≤ w`, `t + b ≤ h`.
2. x stretch region `[l, w − r)`: `stretch` → all columns byte-identical; `tile` → seamless (the column
   after the region's last equals its first within 2/255; with no column after it, the column before the
   region equals its last; with neither, the wrap may not step more than the region's own detail). An
   empty region on a `stretch` / `tile` axis fails (the piece cannot stretch that way).
3. y stretch region `[t, h − b)`: `stretch` → rows identical or smooth (≤ 8/255 adjacent, and every three
   consecutive rows bend by ≤ 3/255, see 2.4); `tile` → seamless; empty → fail as in 2 (an empty `tile`
   region says that no tile period was found and points at `period:`).
   A `fixed` axis is not checked (2 and 3): it is drawn at its natural length.
4. Outputs of one piece share size and slices.
5. Warnings (not failures): fully transparent stretch region, slices thinner than 1 dp (`0 < slice_px <
   scale`), texture > 2048 px.
6. dp consistency: `size_px == size x scale` and `slice_px == slice x scale` (within the manifest's 2-decimal
   rounding). A failure for `slicing: auto` pieces, a warning for the others (explicit `slice`, `slice_px`,
   blocks, manifests without `slicing`).

Result per file: `ok | fail` with reasons; JSON mode lists them (`{"ok", "files": [{piece, output, scale,
file, status, reasons, warnings}], "problems": {piece: [...]}, "warnings": {piece: [...]}, "summary"}`).
Verifying a SPEC (optionally `--theme`) adds the spec-level problems (failures) and warnings found while
rendering (2.4).

## 6. preview

One contact sheet per spec/manifest: every piece 9-slice-rendered (ninekit's own resampler, bilinear like
the GPU) first at its DESIGN size (`design_size`: the spec's size, not the compacted texture), then 1.5×
wider and 2× wider + 1.5× taller, outputs stacked as the runtime stacks them, on a checkerboard and on
`--bg`, labelled with the design size and, when it differs, the texture's size. A `fixed` axis (or one without a middle) keeps
its natural length. Pieces that fail `verify` (or the spec's problems) or carry warnings get a red label and
their first reasons (`FAIL: ...`, `warning: ...`). It is what an agent looks at to judge the art.

The resampler (`ninekit/ninepatch.py`) draws each of the three regions per axis on its own, bilinear and
clamped inside the region (like a 9-slice drawn as separate quads), in premultiplied alpha; corners map
1:1 when the target is at least the sum of the slices, else shrink proportionally; a `tile` middle is drawn
like the runtimes (Godot TILE_FIT, CSS `round`): round(length / tile) whole tiles (at least one), each scaled
to fit the length exactly, never a cut last tile. The preview picks tile lengths that are whole repeats, so
the tiles show at their own size. Pieces drawn whole are shown at their
own size only. `--scale` picks which scale's files to show (default the largest).

## 7. Exporters (`ninekit/exporters/<target>.py`)

Each exporter: `export(manifest_path, out_dir, scale=None, runtime=False) -> list[Path]`. It copies the
PNGs it needs and writes the engine glue. `--runtime` also copies the engine adapter from
`ninekit/adapters/<engine>/` (package data).

A `fixed` axis (3) has no engine mode of its own: an exporter writes it as the engine's plain stretch mode
(never tile) and the piece is meant to be used at its natural length on that axis (its middle is one grid
step, so drawn at that length it is 1:1). The ninekit runtimes (Godot `NineSkin`/`NineButton`, Unity
`NineSliceStack`, Flutter `NineSliceBox`/`NineSliceButton`, the CSS pseudo-element layer, Phaser
`addNinekit`) enforce it: on a fixed axis the art is drawn at its natural length, centred on the logical box,
whatever length the box gets (the content still lays out in the box). Plain engine primitives (a Godot
StyleBox, a Unity sliced Image without the runtime, a bare Flutter `centerSlice`) just stretch.

| target | output |
|---|---|
| `json` | PNGs + `sprites.json`: a flat list (top-level JSON array, sorted by name, output, scale) of `{name, output, scale, file, size_px, slice_px, slice_dp, stretch, content, overhang, mode}` (`mode` so a reader knows shade art); no runtime |
| `godot` | PNGs + `ninekit.json`; one `StyleBoxTexture` `.tres` per output for the @1x file (texture_margin_* = slice_px, axis_stretch from stretch (tile → TILE_FIT), `expand_margin_*` = overhang, `content_margin_*` = max(0, content − overhang)); with `--runtime` the `addons/ninekit` runtime is copied to the Godot project root (`--godot-project DIR`, default: the nearest folder above `-o` holding `project.godot`): `NinekitManifest` (load/cache, `pick_scale`), `NineSkin` (Container; one NinePatchRect per stacked output at node scale 1/scale; overhang, content, TILE_FIT, LTR-locked art inside RTL parents, shade ramp), `NineButton` (BaseButton: frame/face press 0.92 toward the body centre, label, disabled tint), `ninekit_ramp.gdshader`. Verified in Godot 4.7 (`demos/godot`). |
| `unity` | `-o DIR` is the project's single ninekit root (e.g. `Assets/UI/Ninekit`); each manifest lands in `DIR/<manifest name>/` (PNGs + `ninekit.json`), so several sprite sets share one root without name clashes; stale PNGs/metas of a re-export are removed. Always written: `Editor/NinekitImporter.cs` (AssetPostprocessor reading the sibling `ninekit.json`: textureType Sprite, single, FullRect mesh, spriteBorder (x = left, y = bottom, z = right, w = top) from slice_px, pixelsPerUnit = 100 × scale, no mipmaps, bilinear, clamp, uncompressed; re-imports when the manifest changes), `NinekitTypes.cs`, and `NinekitSprites.cs` (constants for every manifest under DIR). `--runtime` adds `Runtime/`: `NineSliceStack` (stacked outputs, overhang, content rect, press scale of the face + content, `FitWholeTiles()` for seamless Tiled images) and a shade-ramp component + UI shader. A second ninekit root in the same project is refused (the importer would compile twice). Verified in Unity 6000.6 (`demos/unity`). |
| `flutter` | Resolution-aware layout under `-o` (`card.png` = 1.0x, `2.0x/card.png`, `3.0x/card.png`; without scale 1 no main file is written and the pubspec snippet lists every main path, which Flutter accepts). The app root is the nearest folder above `-o` with `pubspec.yaml`; asset keys are relative to it and Dart goes to `<app>/lib/ninekit/`: `ninekit_sprites.dart` (one section per manifest: asset path, logical size, centerSlice, content padding, overhang, stack). `--runtime` copies `ninekit.dart`: `NineSliceBox` (draws with the chosen variant's own `slice_px`, snapped to physical pixels), `NineSliceButton` (face + child press 0.92), `NineRamp` (shade → colours via a cached 256-entry LUT image), `precacheNineSprite`. `centerSlice` is in logical (1.0x) pixels — measured. Verified with `flutter test` at DPR 1/2/3 (`demos/flutter`). |
| `css` | PNGs + `ninekit.css` + `index.html` gallery. The element's box is the logical box with `padding` = max(0, content − overhang); the sprite is drawn on `::before` (second output on `::after`) at `inset: −overhang` with `border-image … fill`, `border-image-repeat` from stretch (`tile` → `round`), border widths written as `calc(<slice_px>px / <scale>)` (Chrome truncates decimal lengths). `image-set()` across scales only when every dp slice is a whole CSS px and `slice_px == slice × scale` in every file (Chrome rounds `border-image-slice` to whole CSS px of the chosen image); otherwise one `url()` per scale behind resolution media queries with that file's own `slice_px`. Whole pieces use `background-image`. `:active` scales the element 0.92 with the frame counter-scaled (face + content sink together). Shade pieces via an SVG `feComponentTransfer` ramp. Verified in headless Chrome at DPR 1/2/3 (`demos/web`). |
| `phaser` | PNGs + `ninekit-phaser.json` + ES module `ninekit-phaser.js`: `preloadNinekit(scene, baseUrl, {scale})`, `addNinekit(scene, x, y, name, w, h, opts)` → a Container stacking the outputs as `nineslice` objects (texture-px slices, displayed at 1/scale so sizes are dp); `tile` pieces are built from 9 parts with TileSprites (Phaser's NineSlice cannot tile); `contentRect()`, `setPressed()` (face + content 0.92); shade ramps via a CPU LUT. Verified with Phaser 3.90 in headless Chrome. |

Every target's units must be checked in the real engine (see `demos/`), not assumed.

## 8. Repository layout

```
pyproject.toml            package `ninekit` (src layout), deps numpy, pillow, pyyaml; entry point `ninekit`
src/ninekit/
  __init__.py __main__.py cli.py
  expr.py spec.py canvas.py sdf.py paint.py render.py slicing.py manifest.py
  verify.py ninepatch.py preview.py draw.py compare.py measure.py scaffold.py
  blocks/__init__.py blocks/casual_button.py
  exporters/__init__.py json.py godot.py unity.py flutter.py css.py phaser.py
  adapters/godot/... adapters/unity/... adapters/flutter/... (package data)
examples/<name>/*.yaml    example specs (basics, gumdrop, recreate, neon, wood); their out/ is git-ignored
demos/<engine>/           small projects proving each export in the real engine
skills/ninekit/SKILL.md   the agent skill (+ references/)
.claude-plugin/plugin.json  Claude Code plugin manifest (exposes skills/)
AGENTS.md                 pointer for any coding agent
tests/                    pytest; fixtures under tests/fixtures/
docs/                     this file, images for the README
```

Development: `PYTHONPATH=src python3 -m pytest -q` and `PYTHONPATH=src python3 -m ninekit ...` work
without installing; `pip install -e .` gives the `ninekit` command.
