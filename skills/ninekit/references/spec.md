# ninekit spec reference

The YAML spec language as implemented in `src/ninekit/` (ninekit 0.1.0). `docs/DESIGN.md` is the design
contract; this file follows the code. Contents:

1. [Units and the dp grid](#1-units-and-the-dp-grid)
2. [Spec file](#2-spec-file)
3. [Merging: include, theme, variants](#3-merging-include-theme-variants)
4. [Pieces](#4-pieces)
5. [Values and expressions](#5-values-and-expressions)
6. [Colours, gradients, shades](#6-colours-gradients-shades)
7. [Layers](#7-layers)
8. [Shapes](#8-shapes)
9. [Paints](#9-paints)
10. [Outputs, file names, modes](#10-outputs-file-names-modes)
11. [Slicing and compaction](#11-slicing-and-compaction)
12. [Blocks and `casual_button`](#12-blocks-and-casual_button)
13. [Manifest `ninekit.json`](#13-manifest-ninekitjson)
14. [CLI](#14-cli)
15. [verify rules](#15-verify-rules)

A minimal complete spec:

```yaml
ninekit: 1
name: minimal
scales: [1, 2, 3]
pieces:
  panel:
    size: [48, 40]
    content: [8, 8, 8, 8]
    layers:
      - shape: {rect: [0, 0, w, h], r: 10}
        fill: "#2B2140"
      - shape: {inset: 1.5, r: 8.5}
        fill: {vgrad: [[0, "#FFF7E8"], [1, "#EAD8B8"]]}
```

---

## 1. Units and the dp grid

* **dp** (design px): every number in a spec. A piece is `size: [w, h]` dp.
* **scale**: texture px per dp. Each scale in `scales` is rendered natively from the vectors (never
  resampled from another scale). Scales may be fractional (`1.5`).
* **dp grid** `g`: the smallest dp step that is a whole number of texels at every scale of the spec:
  `[1, 2, 3]` → 1 dp, `[3]` → 1/3 dp, `[2, 4]` → 1/2 dp, `[1.5, 3]` → 2/3 dp, `[1, 1.5, 2, 3, 4]` → 2 dp.
  Scales whose grid would be coarser than 4 dp are refused. `grid:` (section 2) may make it coarser.
* Sizes, auto slices, `keep` and noise/image periods **snap to the grid**, so every file of a layered piece
  is exactly its dp numbers × its scale: `size_px == size × s` and `slice_px == slice × s`. One dp slice is
  exact at every scale (Flutter's single `centerSlice` and CSS `image-set()` rely on it).
* Canvas: `n = round(w / g)` grid steps, i.e. `n × g × s` texels at scale `s` (with one scale, plain
  `round(w × s)`). `build` notes a size the grid moved by more than half a texel of the largest scale.
  Inside layers, `w` and `h` are the snapped canvas in dp, the same at every scale, so shapes written
  against `w`, `h` reach the edges exactly.
* Texel `(i, j)` samples the dp point `((i + 0.5) / s, (j + 0.5) / s)`. Edges get one texel of
  anti-aliasing at every scale, so a 1 dp line is 1 texel at @1x and 3 texels at @3x; lines thinner than
  `1 / scale` dp fade out at that scale.

## 2. Spec file

Top-level keys (anything else is an error):

| key | default | meaning |
|---|---|---|
| `ninekit` | required | must be `1` |
| `name` | file stem | manifest name; letters, digits, `_ . -` |
| `description` | | free text, ignored |
| `scales` | `[1]` | list of positive numbers (a single number is accepted); duplicates are errors |
| `grid` | the scales' grid | a coarser dp grid, a whole multiple of the scales' own: `1`, `0.5`, `"1/3"`; e.g. `grid: 1` with `scales: [3]` keeps auto slices on whole dp (web-friendly) |
| `out` | `out/` | output folder, relative to the spec file |
| `file` | `"{piece}{output}{scale}.png"` | file name template (section 10) |
| `include` | | a file or list of files merged first (this file wins) |
| `vars` | | name → number or expression (section 5) |
| `colors` | | name → colour, name, shade number, or list of stops (section 6) |
| `params` | | block params by piece name, `"*"` = every block piece (section 12) |
| `pieces` | required | name → piece (non-empty) |

Names (`vars`, `colors`) are identifiers (`[A-Za-z_][A-Za-z0-9_]*`). Piece names may also use digits
first, `.` and `-`.

**YAML anchors** share shapes and layers inside one file: name a node with `&name` and reuse it with
`*name`; a mapping can be extended with the merge key `<<:`.

```yaml
layers:
  - {name: body, shape: &body {rect: [0, 0, w, h], r: 8}, fill: face}
  - {name: rim light, shape: *body, ring: 1, blend: atop, fill: light}
  - &glow {shape: *body, ring: 1, soft: 4, falloff: exp, blend: add, fill: light}
  - {<<: *glow, opacity: 0.5}              # the same layer with one key changed
```

Anchors are plain YAML (resolved when the file is read): they do not cross `include`d files, and an anchor
must be defined before it is used.

## 3. Merging: include, theme, variants

All merging is a **deep merge**: mappings merge key by key, anything else (lists, numbers, strings) is
replaced wholesale.

* **include**: each included file (and its own includes, cycles are errors) is merged first, then the
  including file over it.
* **theme**: `--theme THEME` (on `build`, `verify`, `preview`, `compare`, with a SPEC) merges the theme's
  `vars`, `colors` and `params` over the spec's top level. A theme file may contain only `ninekit`, `name`,
  `description`, `include`, `vars`, `colors`, `params` (anything else is an error; its `name` is not used:
  the manifest keeps the spec's name). Piece-level and variant-level `vars`/`colors` still win over it.
* **variants**: `variants: {name: overrides}` under a piece makes extra pieces: the base piece with the
  overrides deep-merged (any piece key except `variants`). A variant listing `layers` or `size` replaces
  them. Variants are built right after their base; names must be unique across pieces and variants.

Scope order for vars and colours: spec (+ includes) < theme < piece < variant, innermost wins.

## 4. Pieces

| key | for | meaning |
|---|---|---|
| `size` | layers (required) | `[w, h]` dp, snapped to the grid; may use vars and `scale`, not `w`/`h` |
| `layers` | | non-empty list of layers (section 7); exactly one of `layers` / `block` |
| `block` | | a block name (section 12); exactly one of `layers` / `block` |
| `params` | block | block parameters (section 12); an error on a layered piece |
| `slice` | layers | `auto` (default), `none` (or `null`), or `[l, t, r, b]` dp (section 11) |
| `slice_px` | layers | `[l, t, r, b]` texel expressions per scale; exclusive with `slice` |
| `stretch` | all | `[x, y]`, each `stretch`, `tile` or `fixed`; one value applies to both. Default `[stretch, stretch]` |
| `content` | all | `[l, t, r, b]` dp insets for labels/children, from the canvas edges (may use `w`, `h`) |
| `overhang` | all | `[l, t, r, b]` dp of the art outside the logical box: shadows, glows |
| `outputs` | layers | list of output images on one canvas, e.g. `[frame, face]` (default `[main]`) |
| `mode` | all | `color` (default) or `shade` (section 10) |
| `compact` | layers | `true` (default): remove identical middle lines when `slice: auto` |
| `keep` | layers | dp of identical middle kept by compaction (default `2`, rounded up to the grid) |
| `mask` | layers | the final silhouette: after all layers, every output's alpha × this shape's coverage; a shape or `{shape, grow, soft, roughen}` (section 7) |
| `period` | layers | `[pw, ph]` dp: the repeat of a tiled *shape* on a `tile` axis (0 = none; section 11) |
| `vars`, `colors` | all | piece-level overrides |
| `variants` | | name → overrides (section 3) |
| `description` | | free text, ignored |

`stretch` modes: `stretch` (the middle stretches), `tile` (the middle repeats in whole tiles), `fixed` (the
axis keeps its natural length; use it for a piece that is not meant to stretch that way, e.g.
`stretch: [stretch, fixed]` for a bar of one height). `content` and `overhang` do not change pixels; they
travel in the manifest so runtimes can lay out labels and place pieces by their logical box (section 13).

## 5. Values and expressions

Every numeric field takes a number or an expression string (quote it when it contains spaces or starts
with `-`: `"w - 2"`).

* Operators: `+ - * / // % **`, unary `-`/`+`, parentheses, comparisons `< <= > >= == !=` (give `1` or
  `0`; chains like `0 < x < 1` work).
* Constant: `pi`.
* Functions: `round(x)` / `round(x, n)` (Python's banker's rounding), `min`, `max`, `abs`, `floor`,
  `ceil`, `sqrt`, `sin`, `cos` (radians), `clamp(x, lo, hi)`, `lerp(a, b, t)`.
* Rejected with an error naming them: attribute access, subscripts, strings, keyword arguments, `*args`,
  any other function.
* Python float semantics and operator order (so legacy numbers reproduce bit for bit).

Names available per field:

| field | names |
|---|---|
| `size`, numeric block `params` | vars, `scale` |
| layer fields (shape, paint, `grow`, `ring`, `soft`, `opacity`, `offset`, `when`), `slice` (dp), `content`, `overhang`, `keep` | vars, `scale`, `w`, `h` |
| `slice_px` | vars, `scale`, `w`, `h`, `w_px`, `h_px` |

Vars resolve lazily in one flat scope per piece: a var may use any other var, earlier or later; a variant
changing `R` changes every var derived from `R`; cycles are errors. A var that uses `w`/`h` works inside
layers but not in `size`. Var names may not be `scale w h w_px h_px pi` or a function name. A `size` that
uses `scale` and snaps to different dp per scale cannot be auto-sliced (a problem): write sizes in dp.

## 6. Colours, gradients, shades

* A colour field takes `"#rrggbb"`, `"#rrggbbaa"` (quote it: `#` starts a YAML comment) or a name from
  `colors`. Names may point at other names (cycles are errors).
* A `colors` entry may be a list of `[t, colour]` stops: a **named gradient**, usable wherever stops are
  expected (`vgrad: face`, `depth: bevel`, noise `stops: rock`). Themes and variants swap gradients like
  colours. Stop positions must not decrease.
* Stops without alpha interpolate per channel (straight, bit for bit). If any stop has alpha,
  colours interpolate premultiplied: fading to `#rrggbb00` has no dark fringe.
* A paint's alpha multiplies the layer's coverage.
* **Shade mode** (`mode: shade`): every colour field is a number `0..1` (or a name whose value is one);
  `#hex` is an error; `colors` entries are shades or lists of `[t, shade]`. There are no alpha stops: fade
  with `opacity`.

## 7. Layers

Layers paint back to front onto a float RGBA canvas (straight alpha).

| key | default | meaning |
|---|---|---|
| `shape` | required | section 8 |
| `fill` | required | section 9 |
| `name` | | a label; shown in error messages |
| `grow` | `0` | dp; moves the edge outwards (negative shrinks) |
| `ring` | `0` | dp; keep only a band this wide just inside the edge (>= 0) |
| `clip` | | a shape; coverage is multiplied by its coverage (canvas coords, ignores `offset`, 1-texel AA) |
| `soft` | `0` | dp blur width of the edge (0 = one texel of anti-aliasing) |
| `falloff` | `linear` | `linear`, `smooth` (smoothstep) or `exp` (glow) |
| `opacity` | `1` | `0..1` |
| `offset` | `[0, 0]` | dp; moves the shape, not the paint or the clip |
| `blend` | `normal` | `normal`, `add`, `multiply`, `screen`, `erase`, `atop` |
| `roughen` | | `{amount, period, scale, octaves, seed}`: perturbs the edge with tileable noise (below) |
| `output` | first output | which output image the layer paints (section 10) |
| `when` | `1` | expression; the layer is skipped when it is `0` |

Order: shape (moved by `offset`) → `roughen` → `grow` → `ring` → coverage (`soft`, `falloff`) × `clip`
coverage → × `opacity` → × paint alpha → composite with `blend`. After the last layer, the piece's `mask`
(if any) multiplies every output's alpha.

Coverage of signed distance `d` (negative inside), `width = max(soft, 1 / scale)`:

* `linear`: `clamp(0.5 - d / width, 0, 1)` (one texel of anti-aliasing when `soft` is 0).
* `smooth`: smoothstep of the linear value (soft shadows).
* `exp`: 1 inside, `exp(-d * 3 / width)` outside: a glow. On a `ring` it glows to both sides of the band.

Blends (straight-alpha canvas): `normal` = source-over (a fixed float operation order); `add` = Porter-Duff plus
(premultiplied sums, clamped): light, glows; `multiply` / `screen` = W3C separable blends with
source-over; `erase` = destination-out (the layer's coverage removes alpha; colours stay): cut holes;
`atop` = source-atop: paints only where the canvas already has alpha and never changes the alpha.

**Shared edges.** Layers drawn on the same outer edge stack their anti-aliased fringes: the silhouette
comes out ~0.6 px fatter at 3x (visible on rounded corners and diagonals). Keep one edge:

* paint every later layer on that edge `blend: atop` (it recolours, the first layer keeps the alpha); right
  for pieces with a drop shadow or glow, and when the first layer is opaque at the edge; or
* **overflow, then cut once:** draw every layer that reaches the silhouette past it (`{all: true}`,
  `grow: 1`) and give the piece `mask: <shape>` (one texel of anti-aliasing; `{shape, grow, soft, roughen}`
  for more). The mask cuts *every* output, shadows and glows included, and is not allowed on block pieces.

Inner layers (inset from the silhouette, over an opaque layer) do not need either.

**roughen** adds tileable value noise of −`amount`..`amount` dp to the shape's distance: torn paper,
chipped stone, rough edges. `period` is a dp number or `[pw, ph]` (0 = no variation along that axis), snapped
to the grid; `scale`, `octaves`, `seed` as for noise. It counts as a periodic paint: fine on pieces drawn
whole and on `tile` and `fixed` axes; varying along a `stretch` axis is a problem. Give the layers and the
`mask` the same `roughen` (a YAML anchor) so their edges line up.

Useful patterns:

* **outline**: the full shape in the outline colour, then the next shape inset by the outline width; or
  one layer with `ring: width` on top.
* **highlight only at the top**: a `ring` with a `vgrad` that fades to alpha 0, or a `clip` rect over the
  top slice.
* **soft drop shadow**: the body shape offset down, black, `soft: 1.5..3`, `falloff: smooth`,
  `opacity: 0.3..0.5`, drawn first; give the piece `overhang`.
* **glow**: `ring: 1`, `soft: 3..5`, `falloff: exp`, `blend: add`.
* **detail only where it fits**: `when: "scale >= 2"` skips a hairline at @1x.
* **cut a hole**: a later layer with `blend: erase`.
* **one silhouette edge**: `blend: atop` on layers that share the outer edge, or `mask` (above).
* **inset a chamfered (or any) shape by `d`**: the same shape with `grow: -d`, an exact parallel offset.
  Insetting a chamfered rect and keeping its `chamfer` moves the 45° cut by the wrong amount.

## 8. Shapes

All coordinates are dp and may be expressions using `w`, `h`.

| shape | modifiers | meaning |
|---|---|---|
| `{rect: [x0, y0, x1, y1]}` | `r`, `chamfer` | rectangle; `r` one radius or `[tl, tr, br, bl]` |
| `{inset: d}` / `{inset: [l, t, r, b]}` | `r`, `chamfer` | rectangle inset from the canvas edges |
| `{circle: [cx, cy, r]}` | | circle |
| `{ellipse: [cx, cy, a, b]}` | `angle` (degrees) | ellipse, radii `a`, `b` > 0 (approximate sdf, exact on the axes) |
| `{polygon: [[x, y], ...]}` | | simple polygon, >= 3 points, any winding (exact sdf) |
| `{union: [s, ...]}` | | min of the shapes' sdfs (>= 1 shape) |
| `{intersect: [s, ...]}` | | max (>= 1 shape) |
| `{subtract: [a, b, ...]}` | | `a` minus the union of the rest (>= 2 shapes) |
| `{all: true}` | | the whole canvas |

* `chamfer: c` or `[tl, tr, br, bl]`: exact 45° cut corners. A corner uses its chamfer if > 0, else its
  radius. Chamfers are clamped to half the shorter side.
* Corners are chosen per quadrant, so a radius should not exceed half the
  shorter side; `r: "h / 2"` makes a capsule.
* Other modifiers are errors (`r` on a circle, `angle` on a rect).

## 9. Paints

| paint | meaning |
|---|---|
| `"#hex"`, a colour name, a number (shade mode) | solid |
| `{vgrad: stops, from: y0, to: y1}` | vertical gradient over dp rows `y0..y1` (default `0..h`), clamped outside |
| `{lgrad: stops, angle: deg}` | linear gradient at an angle (0° = left → right, 90° = top → bottom), spanning the canvas (its corners project onto 0 and 1, like CSS) |
| `{lgrad: stops, from: [x0, y0], to: [x1, y1]}` | linear gradient between two dp points, clamped outside |
| `{rgrad: stops, center: [cx, cy], radius: r, ratio: k}` | radial gradient: `t` = distance / `radius` from `center` (defaults: the canvas centre, half the shorter side); `ratio` = vertical / horizontal radius (an ellipse) |
| `{depth: stops}` | colour by distance **inside** the layer's edge in dp (after `grow`, before `ring`): bevels, cushions, inner shadows. `t = 0` is the edge; negative `t` is outside |
| `{noise: {...}}` | procedural, tileable texture (below) |
| `{image: path, tile: true, size: [dw, dh]}` | an external texture (below) |

`stops` is a list `[[t, colour], ...]` or the name of a named gradient. Only `vgrad` and `depth` keep a
stretched middle clean: `lgrad` and `rgrad` vary along x, so they belong in pieces drawn whole (gems, orbs,
coins) or inside the fixed slices; across a stretch region auto slicing and `verify` catch them like any
horizontal feature.

**noise** keys:

| key | default | meaning |
|---|---|---|
| `kind` | `value` | `value` (smooth fBm), `grain` (one random value per cell, no smoothing), `wood` (grain lines along x, bent by noise) |
| `period` | required | `[pw, ph]` dp, snapped to the dp grid (at least one step); `0` = no variation along that axis (`wood` needs `ph` > 0) |
| `scale` | longest period / 4 (`grain`: one texel) | feature size in dp (`grain`: cell size) |
| `octaves` | 3 (`grain`: 1) | 1..8 |
| `seed` | 0 | integer |
| `stops` | black → white (`0 → 1` in shade mode) | the colour ramp the noise value 0..1 maps through |
| `warp` | 1.5 | `wood` only: how far the rings bend, in rings (`0` = straight rings) |
| `axis` | `x` | the grain direction: `y` turns the pattern 90° (vertical wood); the `period` stays as written, so vertical grain needs an x period |

The lattice wraps at a whole number of cells per period, so the noise repeats exactly and looks the same
at every scale. `wood` with `period: [0, p]` (or `warp: 0`) gives straight horizontal lines (scanlines,
stripes); lower `warp` (0.5–1) for long, calm grain.

**image** keys: `image` path relative to the spec file; `size: [dw, dh]` dp per tile (default one image px
per dp; a tiled image's size snaps to the grid); `tile: true` (default) repeats it seamlessly (resampled
through a 3x3 mosaic so the filter wraps); `tile: false` draws it once at the origin at
`round(size × scale)`. In shade mode the image's luminance is the shade. The image must itself be
seamless.

A noise, tiled image or `roughen` that varies along an axis needs that axis to be `tile` (it repeats) or
`fixed` (drawn at its natural length); along a `stretch` axis build reports a problem and verify fails.

## 10. Outputs, file names, modes

* `outputs: [frame, face]`: several images on the same canvas (they stack exactly, share size and
  slices). Each layer goes to its `output` (default: the first). Names: lowercase letters, digits, `_`.
  Single-output pieces use `main`. The manifest's `stack` lists outputs bottom to top.
* A pressable piece is `frame` (shadow, bezel, the dark well) + `face` (everything that moves); runtimes
  scale the face and the content by 0.92 toward the logical box's centre when pressed, and the face covers
  the well when not pressed.
* `file` template tokens: `{piece}`, `{output}` (`""` for `main`, else `_<name>`), `{scale}` (`""` when
  the spec declares one scale, else `@<s>x`, e.g. `@2x`, `@1.5x`). Must contain `{piece}`, end in `.png`,
  may contain folders. `build --scales` does not change names. Two files with one name are an error.
* `mode: shade`: R = G = B = shade, A = coverage; the manifest records `"mode": "shade"` and runtimes map
  the shade through a colour ramp.

## 11. Slicing and compaction

Every file of a layered piece shares one dp size and one dp slice. Auto slicing looks at **all scales of a
piece at once** and works in whole grid steps; `build --scales` still decides over the spec's scales.

* `slice: auto` (default), judged on all outputs of the piece together. Per scale the run of lines below
  is found and rounded inwards to whole grid steps; each side's slice is the largest over the scales (dp):
  * **x** (`stretch`): the run of byte-identical columns around the centre column (both centre columns
    are tried for an even width). Shorter than 3 columns at any scale, or no whole grid step in common, is
    a **problem**: the piece cannot stretch horizontally; build warns, its files get an empty middle and
    verify fails. A piece not meant to stretch horizontally says `stretch: [fixed, ...]`.
  * **y** (`stretch`): the longest *smooth* run of rows around the centre: adjacent rows differ by <= 8/255
    per channel **and** every three consecutive rows bend by <= 3/255 (`|row i − 2·row i+1 + row i+2|`,
    alpha included); identical rows are smooth too. The bend rule rejects low-contrast slanted lines and
    patterns (a faint "///" changes little per row but bends where it crosses a texel); a gradient bends only
    at its stops, so the rows at a gradient's ends move into the slices. The identical rows around the centre
    win instead only when the smooth run is at most 1 dp longer on each side (the anti-aliased start of
    rounded corners), so flat pieces still compact. When the scales' smooth runs share less than one grid
    step (a pill or bar rounded over its whole height, a sharp line or a slanted pattern through the centre)
    the axis becomes **`fixed`**.
  * **`fixed`** (requested, or y as above): the axis keeps its natural length; its slices leave exactly one
    grid step in the middle (centred). Nothing is checked or compacted there. Runtimes draw the piece at its
    natural length on that axis.
  * **`tile`**: with P the period of the piece's periodic paints and `roughen`s and of its `period:` hint
    (lcm; one grid step if none; the same dp at every scale since periods snap to the grid), the region starts
    on a grid step and holds the most whole periods such that line `x` matches line `x + P` (within 2/255) at
    every scale (ties: most centred). When the repeating thing is a **drawn shape** (stripes, notches,
    segments), give the piece `period: [pw, ph]` (dp, 0 = none; only on `tile` axes) and draw one copy per
    period across the whole canvas; without any period `build` warns and the tile is just a run of identical
    lines. No region is the problem "no tile period found on x/y; give `period:`".
* `slice: none` (or `null`): drawn whole (icons, round buttons, medals); `slice_px` is `null`.
* `slice: [l, t, r, b]`: dp; `round(v × scale)` texels per scale. A value off the grid is kept as written
  and noted (its files cannot share one dp slice). Never compacted.
* `slice_px: [exprs]`: texels per scale, may use `w_px`, `h_px`; must be whole numbers; untouched by the
  grid. Use it only to reproduce legacy art exactly.
* **Compaction** (`compact: true`, only with `slice: auto` and no problems): identical middle columns and
  rows are removed losslessly down to `keep` dp (default 2, rounded up to the grid), the same dp at every
  scale; `size` and `slice` are updated. Only `stretch` axes whose whole middle is byte-identical at every
  scale are compacted (never `tile`/`fixed` axes, smooth y runs, explicit slices). Lossless: drawn as a
  9-slice at any size, compacted and uncompacted give identical pixels.
* **Problems** (fail `verify SPEC`): no stretchable middle on x, a periodic paint or `roughen` varying along
  a `stretch` axis (on a `fixed` axis it is fine), no seamless tile region, a size that differs per scale.
  **Warnings** (`note:` lines, never failures): a size the grid moved, explicit `slice` values off the grid,
  a `tile` axis with no declared period.

Block pieces are not auto-sliced or compacted: the block reports its slices. With one scale they are used as
is; with several they are put on the dp grid (per side the largest `slice_px / scale`, rounded up to the
grid), so every file shares one dp slice, and an axis left without a whole grid step of middle becomes
`fixed` (`casual_button` at `[1, 2, 3]`: x stretches, y is fixed at its natural height).

## 12. Blocks and `casual_button`

A piece with `block: <name>` is drawn by Python code with `params`. The block decides `size`, slices and
outputs: `size`, `slice`, `slice_px`, `layers`, `outputs`, `compact`, `keep` are errors on a block piece;
`stretch`, `mode`, `content`, `overhang` may be set (the last two override the block's).

Params resolution follows the block's `DEFAULTS`: a string is evaluated as an expression (spec vars and
`scale`) only for a key whose default is a number (or element by element for a list of numbers); an
invalid expression there is an error. Everything else passes exactly as written: `style: mint` (even if a
var `mint` exists), colour strings, booleans, `layers: [frame, face]`, nested mappings. Spec `colors` names
are **not** resolved inside params. Spec/theme `params` merge over a piece's own: `"*"` first, then the
piece's name; they reach block pieces only.

### `casual_button`

A casual push button with a metal bezel and a bevelled, glossy pillow face: outline → bezel (outer ring, inner
ring with a rim light, a darker depth band at the bottom) → dark line → face (light top bevel, side walls, a thick
lip, the panel and a soft sheen); the frame output also holds the drop shadow and the dark well the pressed face
sinks into. The defaults and presets are the Gumdrop sample concept (`examples/gumdrop/buttons.yaml`).

| param | default | meaning |
|---|---|---|
| `style` | none | preset: `berry mint sky sun grape coal cloud gray` (`gray` = disabled: grey bezel, faint sheen); optional if `colors` gives all |
| `colors` | | overrides over the preset: `line wall lip gloss face well` (gradients), `face_edge shadow sheen` (solid), `text_outline` (carried for labels, not drawn), `bezel: {outline, depth, outer, inner (gradients over the body height), rim_light (solid)}` |
| `circle` | `false` | `true`: the round form, a `btn_h` square drawn whole |
| `layers` | `[frame, face]` | any of `frame`, `face`, `full` (`full` → output `main`, the composite) |
| `pressed` | `false` | `full` only: the face sunk into the well |
| `btn_w`, `btn_h` | 128, 62 | canvas dp (`btn_h` includes the drop shadow) |
| `body_h` | 59 | the body's height |
| `radius` | 20 | outer corner radius |
| `press` | 2 | side slice allowance for the pressed face |
| `press_top`, `press_side`, `press_bottom` | 2.2, 1.6, 1 | how far the pressed face sinks |
| `outline`, `outer_ring`, `inner_ring`, `depth` | 0.8, 1.3, 2.4, 2 | bezel bands (depth: the darker band at the bezel's bottom) |
| `rim_light`, `rim_light_fade` | 0.7, 0.6 | the inner ring's light first row and its fade (share of body height) |
| `line`, `line_bottom` | 0.6, 0.9 | dark line inside the bezel (sides/top, bottom) |
| `wall` | 3.6 | side walls |
| `lip` | 6.2 | the bottom bevel's height |
| `gloss` | 2.6 | the top bevel's height |
| `panel_radius` | 11 | face panel corner radius |
| `face_edge_width` | 0.8 | the panel's light bottom line |
| `sheen`, `sheen_fade` | 0.6, 0.1 | the sheen's opacity at its top (0 = none) and at its bottom (share of the top's) |
| `sheen_height`, `sheen_inset`, `sheen_offset`, `sheen_soft` | 14, 5, 1.2, 1.2 | the sheen capsule: height, inset from the panel's sides, distance below the panel's top, edge blur |
| `shadow_offset`, `shadow_blur`, `shadow_opacity` | 2, 1.3, 0.3 | drop shadow |
| `slice_margin` | 1.5 | anti-aliasing allowance in the side slices |
| `ss` | 4 | supersampling factor (integer) |
| `content` | `[12, 8, 12, 17]` | label area (centred on the face panel), or `null` |

A colour is `"#rrggbb"`, `"#rrggbbaa"` or `[r, g, b(, a)]`; a gradient is one colour (flat), a
`[top, bottom]` pair or `[[t, colour], ...]`. The block returns `overhang: [0, 0, 0, btn_h - body_h]`; the
rectangle is sliced `[side, mid, side, mid]` (side from the panel, sheen and bezel geometry, `mid` leaves two
middle rows) in whole texels per scale. With several scales the slices are put on the dp grid and y becomes
`fixed` (the default button: `[28, 30, 28, 31]` dp at `[1, 2, 3]`); with one scale they stay as the block made them
(e.g. `[76, 92, 76, 92]` px = 25.33 / 30.67 dp at 3x), and the two middle rows stretch: keep the sheen above them
and the bezel outline and the line flat colours.

## 13. Manifest `ninekit.json`

Written next to the PNGs (schema 1, keys sorted, two-space indent). Per piece:

| key | meaning |
|---|---|
| `size`, `slice` | dp (2 decimals) from the largest scale's file (the compacted texture); `slice` is `null` for pieces drawn whole |
| `design_size` | the size as designed (dp, on the grid, before compaction; a block's own size): the natural size to show the piece at |
| `stretch` | per axis `stretch`, `tile` or `fixed` |
| `slicing` | where the slices came from: `auto`, `slice`, `slice_px`, `none` or `block` |
| `mode` | `color` or `shade` |
| `content`, `overhang` | dp from the canvas edges, or `null` |
| `stack` | outputs bottom to top (when `main` sits next to named outputs it is their composite) |
| `outputs` | `{output: {"<scale>": {file, size_px, slice_px}}}`; scale keys are strings (`"3"`, `"1.5"`) |

* Per-file `slice_px` is authoritative. For layered pieces every file is exactly the piece's dp `size` and
  `slice` × its scale; verify fails an auto-sliced piece whose files are not.
* **Box model:** all insets are measured from the canvas (texture) edges. The **logical box** is the canvas
  minus `overhang`; children are padded inside it by `max(0, content − overhang)`. E.g. `casual_button`:
  128×62 dp, overhang `[0, 0, 0, 3]`, content `[12, 8, 12, 17]` → logical box 128×59, child
  padding `[12, 8, 12, 14]`.
* **Press:** the face output and the content scale together toward the logical box's centre (0.92), the
  frame stays. **Tiles:** whole tiles only (fitted to the length). **Fixed:** drawn at the natural length,
  centred. See `engines.md`.
* Paths are relative to the manifest. Exporters read only this file.

## 14. CLI

```
ninekit build   SPEC [--theme T] [-o OUT] [--only a,b] [--scales 1,2,3] [--json]
ninekit verify  SPEC|MANIFEST [--theme T] [--json]
ninekit preview SPEC|MANIFEST [--theme T] [-o sheet.png] [--bg "#hex"] [--scale S]
ninekit compare SPEC|MANIFEST PIECE REF.png [--crop x,y,w,h] [--outputs frame,face] [--bg "#hex"]
                [--ref-scale S] [--theme T] [--zoom N] [-o compare.png] [--json]
ninekit render  SPEC|MANIFEST PIECE --size WxH [--outputs a,b] [--scale S] [--pressed] [--theme T]
                -o file.png [--json]
ninekit export  MANIFEST --target json|godot|unity|flutter|css|phaser -o DIR [--scale S] [--runtime]
                [--godot-project DIR]
ninekit measure IMAGE (--x X | --y Y) [--from A] [--to B] [--ref-width W --design-width D]
                [--avg N] [--tol T] [--min-band N] [--min-alpha A] [--json]
ninekit measure IMAGE --corner tl|tr|bl|br [--box x0,y0,x1,y1] [--ref-width W --design-width D] [--json]
ninekit new     DIR
```

A MANIFEST argument may also be its folder. `--theme` applies to a SPEC only (an error with a manifest).

* `build`: writes PNGs + `ninekit.json` to the spec's `out` (or `-o`). Slicing problems print as `warning:`
  lines and notes as `note:` lines (JSON: `"ok": false`, `"problems"`, `"warnings"`); files are still
  written and the exit code is 0: the gate is `verify`. `--only` re-renders some pieces and updates the
  existing manifest in place. `--scales` overrides the spec's scales without renaming files (slices are
  still decided over the spec's scales).
* `verify SPEC`: builds into a temporary folder and checks every file plus the spec-level problems and
  notes; exit 1 on any failure. `verify MANIFEST` checks the files (section 15).
* `preview`: a contact sheet: every piece first at its **design size** (`design_size`, not the compacted
  texture), then 1.5× wider, then 2× wider and 1.5× taller (tile axes in whole repeats, a `fixed` axis at its
  natural length), on a checkerboard and on `--bg` (default `#3B4252`), labelled with the design size and,
  when it differs, the texture's. Pieces that fail verify or carry warnings get a red label and their first
  reasons. Default path `<out>/<name>.preview.png` (spec) or next to the manifest. `--scale` picks which
  scale's files to show (default the largest).
* `compare`: draws the piece's stacked outputs (default: its `stack` without a composite `main`) from the
  largest scale's files as a 9-slice at exactly the crop's pixel size (`--crop x,y,w,h`, default the whole
  reference) and writes `reference | ninekit | |difference| heatmap` (×4: black → red → yellow → white),
  both composited on `--bg`. `--ref-scale` = reference px per dp (default the largest scale; for a screenshot
  `W / D`). Prints mean and max absolute difference (8-bit RGB), PSNR and the % of pixels differing by more
  than 16/255. Without `-o` it writes `<spec out>/compare_<piece>.png` (for a manifest: next to it), never
  into the working folder. Exit 0 (it measures, it does not judge).
* `render`: draws a piece at any dp size (`--size 240x56`) as a transparent PNG, the way a runtime draws it:
  the stacked outputs from one scale's files (`--scale`, default the largest; px = dp × scale) as 9-slices
  with tile axes in whole fitted tiles. `--pressed` scales the `face` output by 0.92 toward the logical box's
  centre (frame/face pieces). Stretching a `fixed` axis is allowed but noted. For mockups, for checking a
  piece at the size a layout uses, and for comparing the pressed state.
* `export`: see `engines.md`. It refuses a YAML spec (build first).
* `measure` (line mode): samples one line of an image and prints colour bands (see `workflow.md`). `--x X`
  reads the vertical line at column X (top to bottom), `--y Y` the row Y (left to right). `--ref-width W
  --design-width D` adds dp columns (`dp = px × D / W`). `--avg N` averages N px across the line (noisy
  screenshots); `--tol` (default 10/255) is the largest step inside a band; `--min-band` merges thinner
  bands; `--min-alpha` (default 8) treats pixels below that alpha as transparent. Anti-aliased and soft edge
  pixels are absorbed into their band and reported as **sub-pixel edges**. `--json` gives one object per
  band:

  | key | meaning |
  |---|---|
  | `start`, `end`, `thickness_px` | integer px range `[start, end)` incl. edge pixels |
  | `start_dp`, `end_dp`, `thickness_dp` | the same in dp |
  | `edge_start`, `edge_end` (+ `_dp`) | sub-pixel positions where the band's material really begins / ends (from alpha coverage on silhouette edges, colour interpolation on inner edges); equal to `start`/`end` when pixel aligned |
  | `kind` | `flat` or `gradient` |
  | `soft_start`, `soft_end` | edge px at each end left out of the colours |
  | `start_color`, `mid_color`, `end_color` / `..._alpha` | `#rrggbb` and alpha 0..255 of the solid core |

* `measure --corner tl|tr|bl|br` fits a rounded-rect corner radius from alpha coverage (missing area =
  (1 − π/4)·r²) in the corner's half of `--box x0,y0,x1,y1` (px, end exclusive; default the whole image:
  give a box that excludes shadows). `--json`: `corner`, `box`, `radius_px`, `radius_dp`, `edge_x_px`,
  `edge_x_dp`, `edge_y_px`, `edge_y_dp` (the distances from the box's sides to the shape's straight edges).
* `new DIR`: writes `DIR/ninekit.yaml`, a starter spec (panel, frame + face button, round badge) that
  builds and verifies; refuses to overwrite.
* `--json` (build, verify, compare, render, measure) prints machine-readable results. Exit codes: 0 ok, 1 verify
  failure, 2 error (`error: ...` on stderr, or `{"ok": false, "error": ...}` with `--json`).
* Without installing: `PYTHONPATH=src python3 -m ninekit ...` from a ninekit checkout.

## 15. verify rules

Per file (every output × scale):

1. `slice_px` fits: `l + r <= w`, `t + b <= h`.
2. x stretch region `[l, w - r)`: `stretch` → all columns byte-identical; `tile` → seamless (the column
   after the region equals its first within 2/255). An empty region on a `stretch`/`tile` axis fails.
3. y stretch region `[t, h - b)`: `stretch` → rows identical or smooth (<= 8/255 between neighbours and
   <= 3/255 bend over three rows); `tile` → seamless; empty → fail (for `tile`: no tile period found, give
   `period:`). A `fixed` axis is not checked.
4. Outputs of one piece share size and slices.
5. Warnings only: fully transparent stretch region (fine for hollow frames), slices thinner than 1 dp,
   textures larger than 2048 px.
6. dp consistency: `size_px == size × scale` and `slice_px == slice × scale`: a failure for
   `slicing: auto` pieces, a warning for the others (explicit `slice`, `slice_px`, blocks).

`verify SPEC` (optionally `--theme`) also reports the spec-level problems (failures) and notes (warnings)
found while rendering (section 11).
