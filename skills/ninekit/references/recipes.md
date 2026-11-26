# ninekit recipes

Working specs for common looks. Every block below that starts with `ninekit: 1` is built and verified by
`tests/test_docs_snippets.py`, so they stay correct. Copy one, rename the pieces, then change the numbers
and colours to match your reference (measure it first: see `workflow.md`).

The recipes use `scales: [1, 2, 3]` (the mobile default). Sizes are dp.
After a change, always:

```sh
ninekit build recipe.yaml && ninekit verify recipe.yaml && ninekit preview recipe.yaml
```

and open `out/<name>.preview.png` to look at it. A combined preview of these recipes is
`docs/images/recipes_preview.png`.

Contents:

1. [Casual glossy bevelled button (layers)](#1-casual-glossy-bevelled-button-layers)
2. [Casual button block (`casual_button`)](#2-casual-button-block-casual_button)
3. [Cream card with lip and shadow](#3-cream-card-with-lip-and-shadow)
4. [Pill and tab](#4-pill-and-tab)
5. [Round badge and count badge](#5-round-badge-and-count-badge)
6. [Progress bar: track and fill](#6-progress-bar-track-and-fill)
7. [Flat minimal panel and buttons](#7-flat-minimal-panel-and-buttons)
8. [Neon sci-fi chamfered panel with glow](#8-neon-sci-fi-chamfered-panel-with-glow)
9. [Wood and stone panels (tiled texture)](#9-wood-and-stone-panels-tiled-texture)
10. [Shade mode: one art, any colour](#10-shade-mode-one-art-any-colour)
11. [A theme that restyles a set](#11-a-theme-that-restyles-a-set)
12. [Gem and orb (angled and radial gradients)](#12-gem-and-orb-angled-and-radial-gradients)
13. [Torn parchment (roughen + mask)](#13-torn-parchment-roughen--mask)

---

## 1. Casual glossy bevelled button (layers)

**When:** casual / mobile game buttons: a dark outline, a metal bezel, a bevelled "pillow" face with a thick
lip and a soft sheen. Use this when you need to change the *shape* of the button; if the block's proportions
are fine, the `casual_button` block (recipe 2) is shorter. This is the block's default button (Gumdrop's
`mint`) written as layers, every band a var: `ninekit compare` puts the two side by side (`workflow.md`, step 6).

The layers go back to front, outside in: shadow → outline → depth band → outer ring → inner ring and its rim
light → well (frame output), then the face output: dark line → side walls → mitred top bevel (light) and
bottom bevel (the lip) → face panel → panel edge → sheen. Every number is a var, so a measured reference drops
straight in.

```yaml
ninekit: 1
name: casual
scales: [1, 2, 3]
out: out/

vars:
  R: 20                # outer corner radius
  SH: 3                # drop shadow below the body
  O: 0.8               # dark outline
  RING: 1.3            # outer bezel ring (mid steel)
  BZ: 2.4              # inner bezel ring (bright silver)
  DEPTH: 2             # the darker band at the bezel's bottom
  IN: O + RING + BZ    # inside the bezel: the well / the face block
  LINE: 0.6            # dark line between bezel and face
  LINE_B: 0.9          # ... at the bottom
  WALL: 3.6            # side walls
  GLOSS: 2.6           # top bevel
  LIP: 6.2             # bottom bevel (the lip)
  PR: 11               # face panel corner radius

colors:
  outline: "#262E3B"
  depth: "#505C6E"
  ring: [[0, "#7C8A9F"], [1, "#5D6A7F"]]
  bezel: [[0, "#EFF3F8"], [0.45, "#C3CCD8"], [1, "#99A6B7"]]
  bezel_light: [[0, "#FFFFFFE6"], [1, "#FFFFFF00"]]     # alpha stops fade it out
  well: [[0, "#03160E"], [1, "#062116"]]
  line: "#084530"
  wall: [[0, "#5DDCAB"], [1, "#1C966A"]]
  gloss: [[0, "#D3FFF0"], [1, "#C1FAE5"]]
  lip: [[0, "#17865D"], [1, "#106F4C"]]
  face: [[0, "#9DF4CF"], [0.55, "#47D4A0"], [1, "#23A676"]]
  face_edge: "#62E2B3"
  sheen: [[0, "#FFFFFF99"], [1, "#FFFFFF0F"]]

pieces:
  button:
    size: [128, 62]
    outputs: [frame, face]
    content: [12, 8, 12, 17]
    overhang: [0, 0, 0, 3]
    vars:
      B: h - SH                          # body bottom
      IB: B - IN - DEPTH                 # the bezel's inner bottom (the depth band sits under the rings)
      X0: IN + LINE                      # the face block
      Y0: IN + LINE
      X1: w - IN - LINE
      Y1: IB - LINE_B
      PX0: X0 + WALL                     # the face panel inside the bevels
      PY0: Y0 + GLOSS
      PX1: X1 - WALL
      PY1: Y1 - LIP
    layers:
      # frame: shadow, outline, depth band, outer ring, inner ring + its light rim, well
      - {name: shadow, output: frame, shape: {rect: [0, 2, w, "B + 2"], r: R},
         fill: "#1B2238", soft: 1.5, opacity: 0.3}
      - {name: outline, output: frame, shape: {rect: [0, 0, w, B], r: R}, fill: outline}
      - {name: depth, output: frame, shape: {rect: [O, O, "w - O", "B - O"], r: "R - O"}, fill: depth}
      - {name: outer ring, output: frame, shape: {rect: [O, O, "w - O", "B - O - DEPTH"], r: "R - O"},
         fill: {vgrad: ring, from: 0, to: B}}
      - {name: inner ring, output: frame,
         shape: &inner {rect: ["O + RING", "O + RING", "w - O - RING", "IB + BZ"], r: "R - O - RING"},
         fill: {vgrad: bezel, from: 0, to: B}}
      - {name: rim light, output: frame, shape: *inner, ring: 0.7,
         fill: {vgrad: bezel_light, from: "O + RING", to: "B * 0.6"}}
      - {name: well, output: frame, shape: {rect: [IN, IN, "w - IN", IB], r: "R - IN"},
         fill: {vgrad: well, from: IN, to: IB}}
      # face: dark line, side walls, mitred top/bottom bevels, the panel, its light edge, the sheen
      - {name: line, output: face, shape: {rect: [IN, IN, "w - IN", IB], r: "R - IN"}, fill: line}
      - {name: walls, output: face, shape: {rect: [X0, Y0, X1, Y1], r: "R - IN - LINE"},
         fill: {vgrad: wall, from: Y0, to: Y1}}
      - name: top bevel
        output: face
        shape: {polygon: [[X0, Y0], [X1, Y0], [PX1, PY0], [PX0, PY0]]}
        clip: {rect: [X0, Y0, X1, Y1], r: "R - IN - LINE"}
        fill: {vgrad: gloss, from: Y0, to: PY0}
      - name: bottom bevel
        output: face
        shape: {polygon: [[PX0, PY1], [PX1, PY1], [X1, Y1], [X0, Y1]]}
        clip: {rect: [X0, Y0, X1, Y1], r: "R - IN - LINE"}
        fill: {vgrad: lip, from: PY1, to: Y1}
      - {name: panel, output: face, shape: {rect: [PX0, PY0, PX1, PY1], r: PR},
         fill: {vgrad: face, from: PY0, to: PY1}}
      - {name: panel edge, output: face, shape: {rect: [PX0, PY0, PX1, PY1], r: PR}, ring: 0.8,
         clip: {rect: [0, "PY1 - 8", w, h]}, fill: face_edge}
      - {name: sheen, output: face, shape: {rect: ["PX0 + 5", "PY0 + 1.2", "PX1 - 5", "PY0 + 15.2"], r: 7},
         soft: 1, fill: {vgrad: sheen, from: "PY0 + 1.2", to: "PY0 + 15.2"}}
```

**Slices:** auto: [21, 23, 21, 25] dp at every scale. The mitre diagonals, the rounded corners and the sheen's
rounded ends all sit within the side slices, so the middle columns are identical and compaction cuts the texture
to 44 dp wide (2 dp of middle kept); vertically the gradients make a smooth middle that stretches.
The two outputs share one canvas and one set of slices: a runtime stacks `frame` then `face`, and on
press scales the face in over the dark well. Labels go in `content`; the shadow is `overhang`.
**Recolour:** change only `colors` (or make variants with `colors:` overrides).

## 2. Casual button block (`casual_button`)

**When:** you want that glossy steel-bezel button in a preset colour, or with a few measurements or colours
changed. One line per button.

```yaml
ninekit: 1
name: block_buttons
scales: [1, 2, 3]
out: out/

pieces:
  # the 9-slice button: frame + face, 128 x 62 dp
  btn_play:   {block: casual_button, params: {style: mint}}
  # a shorter button: every measurement is a param (dp)
  btn_small:  {block: casual_button, params: {style: sky, btn_w: 96, btn_h: 46, body_h: 44, radius: 14, wall: 3,
                                              lip: 4.4, gloss: 2, panel_radius: 7, sheen_height: 9, sheen_inset: 4,
                                              shadow_offset: 1.5, content: [10, 6, 10, 13]}}
  # the round form, drawn whole (icons go on top at runtime)
  btn_round:  {block: casual_button, params: {style: sun, circle: true}}
  # a custom colour set over a preset, in a lilac bezel: gradients are [top, bottom] pairs or [[t, colour], ...]
  btn_coral:
    block: casual_button
    params:
      style: berry
      colors:
        face: [[0, "#FFB59A"], [0.5, "#FF7F5C"], [1, "#E85E3F"]]
        gloss: ["#FFE0D3", "#FFD2C1"]
        wall: ["#FF8E6E", "#C9482C"]
        lip: ["#B5402A", "#97321F"]
        line: "#6B2214"
        face_edge: "#FF9B7E"
        bezel: {inner: [[0, "#F3ECFF"], [1, "#B7A3E0"]], outer: ["#8C76BF", "#664F99"], rim_light: "#FFFFFF"}
```

**Presets:** `berry mint sky sun grape coal cloud gray` (`gray` also greys the bezel and dims the sheen: use it
for disabled). **Outputs:** `layers: [frame, face]` (default) or add `full` for a composite `main`
(`pressed: true` sinks the face in the composite). **Bezel colours:** `colors: {bezel: {outline, depth, outer,
inner, rim_light}}`; the rings take gradients over the body height. **Sheen:** `sheen: 0` turns it off,
`sheen_height` / `sheen_inset` / `sheen_soft` shape it. All params and defaults: `spec.md` → *casual_button*.

**Slices:** the block sets them itself in whole texels per scale; with several scales they are put on the dp
grid, so every file shares one dp slice (`[28, 30, 28, 31]` dp for the default size) and y is `fixed`: a
button is used at its natural height (make a taller one with `btn_h` / `body_h`). The round form is drawn
whole. Do not give `size`, `slice`, `slice_px`, `outputs`, `compact` or `keep` on a block piece; `content` and
`overhang` may be overridden.

## 3. Cream card with lip and shadow

**When:** list rows, info cards, dialogs on a casual UI: a light face, a darker lip showing thickness, a
soft shadow, a light top edge.

```yaml
ninekit: 1
name: cards
scales: [1, 2, 3]
out: out/

vars:
  R: 14                # corner radius
  LIP: 4               # the darker band under the face (the card's thickness)
  SH: 3                # how far the shadow reaches below the card

colors:
  # light at the top, a calm middle, darker towards the lip
  face: [[0, "#FFFDF2"], [0.08, "#FFF8E0"], [0.35, "#FBF0D6"], [0.65, "#FBF0D6"], [1, "#F1E3C4"]]
  lip: [[0, "#C9B08A"], [1, "#9F8564"]]
  edge: "#7A6248"
  top_light: [[0, "#FFFFFFE6"], [1, "#FFFFFF00"]]

pieces:
  card:
    size: [64, 60]
    content: [12, 10, 12, 14]          # where labels / children go (dp from each edge)
    overhang: [0, 0, 0, 3]             # the shadow below the card is outside its logical box
    vars:
      B: h - SH                        # the card's bottom (the shadow lives under it)
    layers:
      - name: shadow
        shape: {rect: [1, 2, "w - 1", "B + 2"], r: R}
        fill: "#2B1D0E"
        soft: 2.5
        falloff: smooth
        opacity: 0.35
      - name: lip
        shape: {rect: [0, 0, w, B], r: R}
        fill: {vgrad: lip, from: "B - LIP - 6", to: B}
      - name: face                     # shares the lip's top and side edges: atop adds no alpha there
        shape: {rect: [0, 0, w, "B - LIP"], r: R}
        blend: atop
        fill: {vgrad: face, to: "B - LIP"}
      - name: top light
        shape: {rect: [0, 0, w, "B - LIP"], r: R}
        ring: 1.5
        blend: atop
        fill: {vgrad: top_light, from: 0, to: 12}
      - name: outline
        shape: {rect: [0, 0, w, B], r: R}
        ring: 1
        blend: atop
        fill: edge
        opacity: 0.6
    variants:
      card_me:                          # a highlighted row: the same art in another tint
        colors:
          face: [[0, "#F8FFEE"], [0.08, "#EEFAD8"], [0.35, "#E6F6CC"], [0.65, "#E6F6CC"], [1, "#D7EDB4"]]
          lip: [[0, "#A5BE7F"], [1, "#778C5C"]]
          edge: "#55693E"
```

**Slices:** auto: [15, 14, 15, 18] dp at every scale; x is compacted (32 dp wide), y is the smooth face
gradient, which stretches. The shadow and the lip live in the bottom slice; `overhang` tells the runtime
the shadow hangs below the card's logical box.

**Shared edges:** the lip is the card's silhouette; the face, the top light and the outline lie on the same
outer edge. Drawn `normal`, their anti-aliased fringes stack and the rounded corners come out ~0.6 px fatter
at 3x (`ninekit compare` of the two versions lights up exactly the corner arcs). `blend: atop` paints colour
only where the canvas already has alpha and never adds any, so the lip alone decides the silhouette. (The
other fix, an oversized drawing cut by a piece `mask:`, would also cut the drop shadow: recipe 13.)

## 4. Pill and tab

**When:** segmented controls, chips, tabs, capsule buttons. A pill is a rounded rect with `r: h / 2`.
`variants` give the selected/idle states from one definition.

```yaml
ninekit: 1
name: pills
scales: [1, 2, 3]
out: out/

colors:
  edge: "#0F2D5C"
  ring: [[0, "#2A63AE"], [1, "#183F7C"]]
  face: [[0, "#8ED2FF"], [0.15, "#5DB8F7"], [0.6, "#3A93E6"], [1, "#2468BC"]]
  gloss: [[0, "#FFFFFFB0"], [1, "#FFFFFF14"]]

pieces:
  # a capsule: radius h/2, so the ends are half circles and the middle stretches
  pill:
    size: [56, 30]
    content: [14, 4, 14, 6]
    layers:
      - shape: {rect: [0, 0, w, h], r: "h / 2"}
        fill: edge
      - name: lip
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 1.2"], r: "h / 2 - 1.2"}
        fill: {vgrad: ring, from: "h - 8", to: "h - 1.2"}
      - name: face
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 4"], r: "(h - 5.2) / 2"}
        fill: {vgrad: face, from: 1.2, to: "h - 4"}
      - name: gloss                       # spans the width, inset from the ends: no feature in the middle
        shape: {rect: [8, 3, "w - 8", "h / 2 - 0.5"], r: 5}
        fill: {vgrad: gloss, from: 3, to: "h / 2 - 0.5"}
    variants:
      pill_idle:                          # same shape, quieter colours
        colors:
          edge: "#3B2A16"
          ring: [[0, "#8E7350"], [1, "#6B5436"]]
          face: [[0, "#F4E3C1"], [0.6, "#E2C99C"], [1, "#CFB07E"]]
          gloss: [[0, "#FFFFFF80"], [1, "#FFFFFF00"]]

  # a top tab: rounded top corners, square-ish bottom; frame + face so the runtime can sink the face
  tab:
    size: [60, 34]
    outputs: [frame, face]
    content: [10, 4, 10, 7]
    layers:
      - output: frame
        shape: {rect: [0, 0, w, h], r: [11, 11, 3, 3]}
        fill: "#2C1F52"
      - output: frame
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 1.2"], r: [9.8, 9.8, 2, 2]}
        fill: {vgrad: [[0, "#5A3DA0"], [1, "#3A2672"]], from: "h - 8", to: "h - 1.2"}
      - output: face
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 5"], r: [9.8, 9.8, 2, 2]}
        fill: {vgrad: [[0, "#C7B0FF"], [0.15, "#AE8EFA"], [1, "#7652DC"]], from: 1.2, to: "h - 5"}
      - output: face                    # the rim light sits on the face's own edge: atop, no fringe build-up
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 5"], r: [9.8, 9.8, 2, 2]}
        ring: 1.2
        blend: atop
        fill: {vgrad: [[0, "#FFFFFFA0"], [1, "#FFFFFF00"]], from: 1.2, to: 10}
```

**Slices:** a pill's side slices are its end caps (`h / 2` each), so it cannot be narrower than it is tall.
It is rounded over its whole height, so no rows can stretch: auto slicing makes y **`fixed`** (manifest
`stretch: [stretch, fixed]`) and the runtimes draw it at its natural height, centred in a taller box. Design
pills at the height you use them. A gloss *centred* on the piece (an ellipse at `w / 2`) would make every
column different: keep highlights as shapes that span the width and end inside the caps, as here. The tab's
flat lower part stretches vertically. `r` takes one radius or `[tl, tr, br, bl]`.

## 5. Round badge and count badge

**When:** notification dots, medals, coins, round icons: drawn whole (`slice: none`), still rendered
natively at every scale. A count badge that grows sideways ("9" → "99+") is the same look as a sliced
capsule.

```yaml
ninekit: 1
name: badges
scales: [1, 2, 3]
out: out/

colors:
  rim: "#FFFFFF"
  red: [[0, "#FF7A6B"], [0.5, "#E5392B"], [1, "#B5211A"]]

pieces:
  # a notification dot, drawn whole: no slices, every scale rendered natively
  badge:
    size: [26, 28]
    slice: none
    layers:
      - name: shadow
        shape: {circle: [13, 14.5, 12]}
        fill: "#000000"
        soft: 2
        falloff: smooth
        opacity: 0.35
      - name: white rim
        shape: {circle: [13, 13, 12]}
        fill: rim
      - name: disc
        shape: {circle: [13, 13, 10.2]}
        fill: {vgrad: red, from: 2.8, to: 23.2}
      - name: inner bevel                  # depth: colour by distance inside the edge
        shape: {circle: [13, 13, 10.2]}
        fill: {depth: [[0, "#FFFFFF70"], [1.8, "#FFFFFF00"]]}
      - name: highlight
        shape: {ellipse: [13, 8, 6, 3]}
        fill: "#FFFFFF"
        soft: 1.2
        opacity: 0.45

  # a count badge ("99+") that grows sideways: the same look as a capsule, sliced
  badge_count:
    size: [40, 26]
    content: [8, 3, 8, 4]
    layers:
      - shape: {rect: [0, 0, w, h], r: "h / 2"}
        fill: rim
      - shape: {rect: [1.8, 1.8, "w - 1.8", "h - 1.8"], r: "h / 2 - 1.8"}
        fill: {vgrad: red, from: 1.8, to: "h - 1.8"}
      - shape: {rect: [1.8, 1.8, "w - 1.8", "h - 1.8"], r: "h / 2 - 1.8"}
        fill: {depth: [[0, "#FFFFFF60"], [1.6, "#FFFFFF00"]]}
      - shape: {rect: [6, 3.2, "w - 6", "h / 2"], r: 4}
        fill: {vgrad: [[0, "#FFFFFF80"], [1, "#FFFFFF00"]], from: 3.2, to: "h / 2"}
```

**Slices:** `badge` has none (`slice_px: null` in the manifest; engines draw it as a plain sprite). In a
piece drawn whole anything goes: centred ellipses, polygons, horizontal detail. The canvas is 2 dp taller
than the disc to hold the shadow. `badge_count` stretches in x only (y is `fixed`, like a pill).

## 6. Progress bar: track and fill

**When:** XP bars, loading bars, health bars. Two pieces: a recessed track and a fill the runtime
stretches to `progress x inner width` (the track's `content` is the inner rect).

```yaml
ninekit: 1
name: bars
scales: [1, 2, 3]
out: out/

pieces:
  # the recessed track; its content inset is where the runtime places the fill
  bar_track:
    size: [48, 18]
    content: [2, 2, 2, 2]
    layers:
      - name: rim
        shape: {rect: [0, 0, w, h], r: "h / 2"}
        fill: "#0B1B33"
      - name: floor + inner shadow          # depth paints by distance inside the edge
        shape: {rect: [1, 1, "w - 1", "h - 1"], r: "h / 2 - 1"}
        fill: {depth: [[0, "#040B16"], [3.5, "#1E3358"]]}
      - name: bottom light               # on the rim's outer edge: atop keeps the silhouette one fringe wide
        shape: {rect: [0, 0, w, h], r: "h / 2"}
        ring: 1
        clip: {rect: [0, "h / 2 + 2", w, h]}
        blend: atop
        fill: "#8FB2E8"
        opacity: 0.5

  # the fill: drawn at the track's inner height (18 - 2 - 2), stretched to progress x inner width
  bar_fill:
    size: [32, 14]
    layers:
      - shape: {rect: [0, 0, w, h], r: "h / 2"}
        fill: "#1D6B12"
      - shape: {rect: [1, 1, "w - 1", "h - 1"], r: "h / 2 - 1"}
        fill: {vgrad: [[0, "#C3F57A"], [0.45, "#76CF35"], [1, "#3F9A1B"]], from: 1, to: "h - 1"}
      - name: gloss
        shape: {rect: [4, 2.2, "w - 4", "h / 2"], r: 2}
        fill: "#FFFFFF"
        opacity: 0.4

  # a candy-striped fill: a repeating *shape* ("///" stripes), so x tiles with a declared `period`
  candy_fill:
    size: [48, 14]
    stretch: [tile, fixed]            # stripes repeat along x; the height is natural
    period: [8, 0]                    # the stripes repeat every 8 dp (tells the slicer what to look for)
    layers:
      - shape: {rect: [0, 0, w, h], r: "h / 2"}
        fill: "#2E7A14"
      - shape: &inner {rect: [1, 1, "w - 1", "h - 1"], r: "h / 2 - 1"}
        fill: {vgrad: [[0, "#9FE870"], [1, "#4FAE2C"]], from: 1, to: "h - 1"}
      - name: stripes                 # one parallelogram per period, from before the left edge past the right
        clip: *inner
        fill: "#FFFFFF"
        opacity: 0.35
        shape:
          union:
            - {polygon: [[-8, h], [-4, 0], [0, 0], [-4, h]]}
            - {polygon: [[0, h], [4, 0], [8, 0], [4, h]]}
            - {polygon: [[8, h], [12, 0], [16, 0], [12, h]]}
            - {polygon: [[16, h], [20, 0], [24, 0], [20, h]]}
            - {polygon: [[24, h], [28, 0], [32, 0], [28, h]]}
            - {polygon: [[32, h], [36, 0], [40, 0], [36, h]]}
            - {polygon: [[40, h], [44, 0], [48, 0], [44, h]]}
      - {name: gloss, shape: {rect: [4, 2, "w - 4", "h / 2"], r: 2}, fill: "#FFFFFF", opacity: 0.3}
```

**Slices:** `bar_track` and `bar_fill` stretch in x; y is `fixed` (rounded over the whole height), so draw
them at their design height. The fill's end caps are `h / 2` wide each, so below `h` dp of progress the
runtime must either hide the fill or let the engine shrink the caps (most 9-slice runtimes squash them
proportionally). `depth` is the cheapest inner shadow: it follows any shape's edge.

`candy_fill` repeats a *drawn shape*, not a noise: give such a piece `stretch: tile` on that axis and
`period:` (dp) so auto slicing finds a middle of whole stripes; draw the shape across the whole canvas, one
copy per period (`&inner` / `*inner` is a YAML anchor: the clip reuses the inner shape). Slanted stripes can
never be a smooth stretch region (they bend from row to row), which is why y is `fixed` here.

## 7. Flat minimal panel and buttons

**When:** apps, tools, flat/"material" game menus: one colour, a hairline border, an ambient shadow.
Flat art compacts to a tiny texture.

```yaml
ninekit: 1
name: flat
scales: [1, 2, 3]
out: out/

vars:
  R: 8

colors:
  surface: "#FFFFFF"
  border: "#E2E5EA"
  accent: "#3B6CF6"
  accent_hover: "#2F5BDB"

pieces:
  # a flat card: a soft ambient shadow, one surface colour, a hairline border
  surface:
    size: [40, 40]
    content: [12, 12, 12, 12]
    overhang: [4, 3, 4, 6]
    layers:
      - name: shadow
        shape: {rect: [4, 5, "w - 4", "h - 4"], r: R}
        fill: "#0F172A"
        soft: 6
        falloff: smooth
        opacity: 0.14
      - shape: {rect: [4, 3, "w - 4", "h - 6"], r: R}
        fill: surface
      - shape: {rect: [4, 3, "w - 4", "h - 6"], r: R}
        ring: 1
        blend: atop                       # the hairline on the surface's own edge
        fill: border

  # a flat button and its hover state: one colour, no depth
  button_flat:
    size: [40, 36]
    content: [14, 8, 14, 8]
    layers:
      - shape: {inset: 0, r: R}
        fill: accent
    variants:
      button_flat_hover: {colors: {accent: accent_hover}}

  # an outlined (ghost) button: a faint tint inside, a 1.5 dp ring. Both reach the outer edge, and atop
  # cannot help (the tint is too faint to carry the ring's alpha): draw them oversized, cut once with `mask`
  button_ghost:
    size: [40, 36]
    content: [14, 8, 14, 8]
    mask: {inset: 0, r: R}
    layers:
      - shape: {all: true}
        fill: accent
        opacity: 0.08
      - shape: {inset: 0, r: R}
        grow: 1                           # the band runs from 1 dp outside the mask to 1.5 dp inside it
        ring: 2.5
        fill: accent
```

**Slices:** auto + compaction keep 2 dp of middle: `button_flat` is 18 x 18 dp (8 + 2 + 8). The `overhang`
on `surface` tells the layout that 4/3/4/6 dp of the texture is shadow outside the card's rect. A ring
with nothing inside would verify with a warning (fully transparent stretch region); that is fine for
frames, but a faint tint is usually the better look.

## 8. Neon sci-fi chamfered panel with glow

**When:** sci-fi / cyber HUD panels: chamfered corners, a bright edge, an additive glow, scanlines.

```yaml
ninekit: 1
name: neon
scales: [1, 2, 3]
out: out/

vars:
  G: 6                 # glow room around the panel (the overhang)
  C: 10                # big chamfer (top-left, bottom-right)
  c: 4                 # small chamfer (top-right, bottom-left)

colors:
  cyan: "#39E6FF"
  body: [[0, "#16344F"], [0.3, "#0C2034"], [0.7, "#0C2034"], [1, "#071322"]]
  scan: [[0, "#39E6FF00"], [1, "#39E6FF1C"]]

pieces:
  panel_neon:
    size: [80, 64]
    stretch: [stretch, tile]          # the scanlines repeat vertically: y tiles, x stretches
    content: ["G + 8", "G + 8", "G + 8", "G + 8"]
    overhang: [G, G, G, G]            # the glow reaches G dp outside the panel's logical box
    layers:
      - name: body
        shape: {inset: G, chamfer: [C, c, C, c]}
        fill: {vgrad: body, from: G, to: "h - G"}
      - name: scanlines               # wood noise with no x period = straight horizontal lines
        shape: {inset: G, chamfer: [C, c, C, c]}
        grow: -1                      # 1 dp inside the edge, chamfers included (an exact offset)
        fill: {noise: {kind: wood, period: [0, 3], scale: 3, seed: 1, stops: scan}}
      - name: glow                    # exp falloff + add: a light glow both sides of the edge
        shape: {inset: G, chamfer: [C, c, C, c]}
        ring: 1
        soft: 4
        falloff: exp
        fill: cyan
        opacity: 0.55
        blend: add
      - name: edge
        shape: {inset: G, chamfer: [C, c, C, c]}
        ring: 1
        fill: cyan
      - name: corner ticks            # inside the corner slices: never in the stretched middle
        shape:
          union:
            - {polygon: [["G + 3", "G + C + 4"], ["G + C + 4", "G + 3"], ["G + C + 6", "G + 3"], ["G + 3", "G + C + 6"]]}
            - {polygon: [["w - G - 3", "h - G - C - 4"], ["w - G - C - 4", "h - G - 3"],
                         ["w - G - C - 6", "h - G - 3"], ["w - G - 3", "h - G - C - 6"]]}
        fill: cyan
        opacity: 0.85
```

**Slices:** [22, 23, 22, 23] dp. x stretches (identical columns, compacted); y tiles with the scanline
period (3 dp), so the y middle is a whole number of periods and repeats seamlessly. The body gradient has
a flat middle band for the same reason: a gradient running through a `tile` axis would break the
repeat. Chamfers are exact 45° cuts, `[tl, tr, br, bl]`; a corner uses its chamfer if > 0, else its
radius. To inset a chamfered shape by `d`, keep the shape and add `grow: -d` (an exact parallel offset):
insetting the rect with the same chamfer moves the cut by the wrong amount. The glow lives in the
`overhang`, so place the panel by its logical box and let the glow spill out.

## 9. Wood and stone panels (tiled texture)

**When:** fantasy / RPG / board-game panels with a material: wood grain, stone. Procedural `noise` is
tileable by construction; `image` fills take a seamless texture instead (`{image: tex.png, size: [32, 32]}`).

```yaml
ninekit: 1
name: textured
scales: [1, 2, 3]
out: out/

colors:
  frame: "#7A4D24"
  frame_dark: "#2E1A09"
  wood: [[0, "#5E3616"], [0.18, "#8A5A2E"], [0.6, "#9C6836"], [1, "#A87543"]]
  rock: [[0, "#5F5A52"], [0.5, "#878075"], [1, "#B3AB9C"]]

pieces:
  # a wood board: grain noise tiles both ways inside a frame
  wood_panel:
    size: [128, 96]
    stretch: [tile, tile]             # the grain varies along x and y: both axes tile
    content: [10, 10, 10, 10]
    layers:
      - name: outline
        shape: {rect: [0, 0, w, h], r: 10}
        fill: frame_dark
      - name: frame                   # flat on the sides: nothing may vary along a tile axis outside the texture
        shape: {inset: 1, r: 9}
        fill: frame
      - name: frame light (top)       # the clip keeps it inside the top slice
        shape: {inset: 1, r: 9}
        ring: 1
        clip: {rect: [0, 0, w, 8]}
        fill: "#C08A50"
      - name: frame shade (bottom)
        shape: {inset: 1, r: 9}
        ring: 1.5
        clip: {rect: [0, "h - 8", w, h]}
        fill: "#4A2A10"
      - name: boards
        shape: {inset: 6, r: 5}
        fill: {noise: {kind: wood, period: [96, 48], scale: 6, octaves: 2, seed: 11, stops: wood}}
      - name: inner shadow
        shape: {inset: 6, r: 5}
        fill: {depth: [[0, "#1A0C02B0"], [3, "#1A0C0200"]]}

  # a stone plate: value noise plus per-texel grain, one 24 dp period
  stone_panel:
    size: [72, 64]
    stretch: [tile, tile]
    content: [8, 8, 8, 8]
    layers:
      - shape: {rect: [0, 0, w, h], r: 9}
        fill: "#2E2925"
      - name: stone
        shape: {inset: 2, r: 7}
        fill: {noise: {kind: value, period: [24, 24], scale: 6, octaves: 5, seed: 7, stops: rock}}
      - name: grain
        shape: {inset: 2, r: 7}
        fill: {noise: {kind: grain, period: [24, 24], seed: 2, stops: [[0, "#00000030"], [1, "#FFFFFF20"]]}}
      - name: inner shade
        shape: {inset: 2, r: 7}
        fill: {depth: [[0, "#000000A0"], [2.5, "#00000000"]]}

  # vertical grain (axis: y): the same wood turned 90°; x period = across the grain, y period = along it
  plank:
    size: [96, 112]
    stretch: [tile, tile]
    content: [10, 10, 10, 10]
    layers:
      - shape: {rect: [0, 0, w, h], r: 6}
        fill: frame_dark
      - shape: &board {inset: 1.5, r: 4.5}
        fill: {noise: {kind: wood, axis: y, period: [48, 96], scale: 6, octaves: 2, warp: 0.8, seed: 4, stops: wood}}
      - shape: *board
        fill: {depth: [[0, "#1A0C02A0"], [3, "#1A0C0200"]]}
```

**Slices:** a noise/image paint that varies along an axis needs `stretch: tile` on that axis (else build
reports it and verify fails). Auto slicing finds a middle that is a whole number of periods; the piece
must be at least one period plus its borders on each tiled axis, and everything outside the texture
(frame sides) must be constant along the tiled axis — no `vgrad` on the frame when y tiles, unless it has
a flat middle band longer than a period. Tile axes are not compacted, so keep periods modest. `wood`
looks most like grain with x period ≈ 2 × y period and `scale` ≈ y period / 8; `warp` (default 1.5 rings)
sets how much the grain bends: 0.5–0.8 for calm planks, 0 for straight lines. `axis: y` turns the grain
vertical (`plank`); its period stays as written, so vertical grain needs an x period. A noise may also vary
along a `fixed` axis (a bar of natural height with a grain across it): only `stretch` axes forbid it.

## 10. Shade mode: one art, any colour

**When:** many colour versions of one piece (team colours, rarity tiers, user-picked themes) recoloured at
runtime: the art is written in shades 0..1 and the runtime maps each shade through a colour ramp
(gradient map). One texture, any tone.

```yaml
ninekit: 1
name: shaded
scales: [1, 2, 3]
out: out/

colors:                      # in a shade piece every colour is a number 0..1 (0 = darkest, 1 = lightest)
  outline: 0
  lip: [[0, 0.30], [1, 0.16]]
  face: [[0, 0.95], [0.3, 0.80], [0.7, 0.80], [1, 0.62]]
  light: 1

pieces:
  button_shade:
    mode: shade                # R = G = B = shade, A = coverage; the runtime maps shade -> colour ramp
    size: [56, 36]
    content: [12, 5, 12, 9]
    layers:
      - shape: {rect: [0, 0, w, h], r: 11}
        fill: outline
      - name: lip
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 1.2"], r: 9.8}
        fill: {vgrad: lip, from: "h - 9", to: "h - 1.2"}
      - name: face
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 5"], r: 9.8}
        fill: {vgrad: face, from: 1.2, to: "h - 5"}
      - name: top light
        shape: {rect: [1.2, 1.2, "w - 1.2", "h - 5"], r: 9.8}
        ring: 1.2
        clip: {rect: [0, 0, w, 9]}
        fill: light
        opacity: 0.8
      - name: gloss
        shape: {rect: [7, 3.5, "w - 7", 12], r: 4}
        fill: light
        opacity: 0.35
```

**Notes:** in shade mode `"#hex"` colours are errors and there are no alpha stops; fade with `opacity`
instead. Plan the ramp: give each material its own shade band (outline 0, lip 0.16–0.30, face
0.62–0.95, highlight 1) so a ramp can colour them independently. The manifest records `"mode": "shade"`;
every ninekit runtime maps it (Godot `ramp`, Unity `NinekitShadeRamp`, Flutter `NineRamp`, CSS `--nk-ramp`,
Phaser `opts.ramp`: see `engines.md`). Use plain colour
pieces with `variants` when there are only a few fixed colourways.

## 11. A theme that restyles a set

**When:** the same pieces in another concept (night mode, seasonal event, a second game). Write the set
once with role-named colours and vars, then put each concept in a theme file. A theme may only hold
`vars`, `colors` and `params` (plus `name`, `description`, `include`); it cannot change layers.

The set (`ui.yaml`):

```yaml
# file: ui.yaml
ninekit: 1
name: ui
scales: [1, 2, 3]
out: out/

vars:
  R: 12                      # corner radius: a theme may change it
  EDGE: 1.2

colors:                      # every colour the pieces use has a role name: themes swap these
  ink: "#3A2E22"
  panel_face: [[0, "#FFFBF0"], [0.3, "#F8EED8"], [0.7, "#F8EED8"], [1, "#EADBBE"]]
  panel_lip: [[0, "#C2AB86"], [1, "#9C8466"]]
  accent_edge: "#103565"
  accent_lip: [[0, "#2A63AE"], [1, "#183F7C"]]
  accent_face: [[0, "#8ED2FF"], [0.15, "#5DB8F7"], [0.6, "#3A93E6"], [1, "#2468BC"]]

params:
  "*": {style: mint}         # every block piece

pieces:
  panel:
    size: [56, 48]
    content: [10, 8, 10, 12]
    layers:
      - shape: {rect: [0, 0, w, "h - 1"], r: R}
        fill: ink
      - shape: {rect: [EDGE, EDGE, "w - EDGE", "h - 1 - EDGE"], r: "R - EDGE"}
        fill: {vgrad: panel_lip, from: "h - 12", to: "h - 1 - EDGE"}
      - shape: {rect: [EDGE, EDGE, "w - EDGE", "h - 6"], r: "R - EDGE"}
        fill: {vgrad: panel_face, from: EDGE, to: "h - 6"}
  pill:
    size: [48, 28]
    content: [12, 4, 12, 6]
    layers:
      - shape: {rect: [0, 0, w, h], r: "h / 2"}
        fill: accent_edge
      - shape: {rect: [EDGE, EDGE, "w - EDGE", "h - EDGE"], r: "h / 2 - EDGE"}
        fill: {vgrad: accent_lip, from: "h - 8", to: "h - EDGE"}
      - shape: {rect: [EDGE, EDGE, "w - EDGE", "h - 4"], r: "(h - 4 - EDGE) / 2"}
        fill: {vgrad: accent_face, from: EDGE, to: "h - 4"}
  play:
    block: casual_button
    params: {btn_w: 120}
```

The night concept (`night.yaml`):

```yaml
# file: night.yaml
# theme for: ui.yaml
# A theme holds only vars, colors and params; it restyles every piece of the set.
name: night
vars:
  R: 6                       # sharper corners
colors:
  ink: "#06080E"
  panel_face: [[0, "#3A4A6E"], [0.3, "#2B3756"], [0.7, "#2B3756"], [1, "#222C46"]]
  panel_lip: [[0, "#161D30"], [1, "#0D1220"]]
  accent_edge: "#2A0E3A"
  accent_lip: [[0, "#6A2C8E"], [1, "#4A1C66"]]
  accent_face: [[0, "#F0A6FF"], [0.15, "#D77BF2"], [0.6, "#B04FD8"], [1, "#8A33B4"]]
params:
  "*":                       # every block piece: the coal preset in a violet bezel
    style: coal
    colors:
      bezel: {outline: "#120A26", outer: ["#4B3A7A", "#36295C"], inner: [[0, "#B9A8E8"], [1, "#6E5AA6"]],
              rim_light: "#E4DBFF", depth: ["#2A1F4D", "#211839"]}
```

Check every concept, then build each into its own folder (the manifest keeps the set's `name`, so
folders keep them apart). `play` is a block piece: at three scales its slices go on the dp grid like the layered
pieces' (recipe 2):

```sh
ninekit verify ui.yaml && ninekit verify ui.yaml --theme night.yaml
ninekit preview ui.yaml --theme night.yaml -o out/night.preview.png
ninekit build ui.yaml -o out/day
ninekit build ui.yaml --theme night.yaml -o out/night
```

**Merging:** theme `vars`/`colors` override the spec's top level (piece and variant values still win);
theme `params` deep-merge, so `colors: {bezel: {...}}` changes only the keys it names. `"*"` params reach
every block piece; a piece name as the key targets one piece.

## 12. Gem and orb (angled and radial gradients)

**When:** icons drawn whole: gems, orbs, coins, currency and reward badges. `lgrad` (a linear gradient at an
angle) shades flat facets, `rgrad` (radial) shades round volumes. Both are horizontal features, so they
belong in pieces drawn whole (`slice: none`) or inside the fixed slices, never across a stretch region.

```yaml
ninekit: 1
name: gems
scales: [1, 2, 3]
out: out/

colors:
  ruby_dark: "#5E0A26"
  ruby: [[0, "#FF8FA8"], [0.5, "#E8335F"], [1, "#9B0F3A"]]
  ruby_side: [[0, "#C21E4C"], [1, "#6E0B2A"]]
  gold: [[0, "#FFF6C7"], [0.35, "#FFC93D"], [0.8, "#E0861A"], [1, "#9A4D0C"]]

pieces:
  # facets meet edge to edge: each is grown 0.3 dp so neighbours overlap (no seam), the outline overflows
  # the silhouette, and the piece's `mask` cuts the one outer edge at the end
  gem:
    size: [40, 40]
    slice: none
    mask: &gem {polygon: [[10, 7], [30, 7], [38, 15], [20, 37], [2, 15]]}
    layers:
      - {name: base, shape: {all: true}, fill: ruby_dark}
      - {name: table, shape: &table {polygon: [[10, 7], [30, 7], [26, 15], [14, 15]]}, grow: 0.3,
         fill: {lgrad: ruby, angle: 70}}
      - {name: crown left, shape: {polygon: [[10, 7], [14, 15], [2, 15]]}, grow: 0.3,
         fill: {lgrad: ruby, angle: 20}}
      - {name: crown right, shape: {polygon: [[30, 7], [38, 15], [26, 15]]}, grow: 0.3,
         fill: {lgrad: ruby_side, angle: 120}}
      - {name: pavilion left, shape: {polygon: [[2, 15], [14, 15], [20, 37]]}, grow: 0.3,
         fill: {lgrad: ruby_side, angle: 45}}
      - {name: pavilion middle, shape: &keel {polygon: [[14, 15], [26, 15], [20, 37]]}, grow: 0.3,
         fill: {lgrad: ruby, angle: 90}}
      - {name: pavilion right, shape: {polygon: [[26, 15], [38, 15], [20, 37]]}, grow: 0.3,
         fill: {lgrad: ruby_side, angle: 135}}
      - {name: facet lines, shape: {union: [*table, *keel]}, ring: 0.5, fill: "#FFFFFF", opacity: 0.35}
      - {name: sparkle, shape: {circle: [15, 11, 6]},
         fill: {rgrad: [[0, "#FFFFFFE0"], [1, "#FFFFFF00"]], center: [15, 11], radius: 6}}
      - {name: outline, shape: *gem, grow: 1, ring: 2.2, fill: "#3A0517"}

  # a golden orb: a radial gradient with an off-centre light, a rim light painted atop
  orb:
    size: [36, 36]
    slice: none
    layers:
      - {name: shadow, shape: {ellipse: [18, 32, 12, 3]}, fill: "#000000", soft: 2, falloff: smooth, opacity: 0.3}
      - {name: rim, shape: {circle: [18, 17, 15]}, fill: "#7A3A08"}
      - {name: sphere, shape: &sphere {circle: [18, 17, 13.8]}, fill: {rgrad: gold, center: [14, 12], radius: 19}}
      - {name: rim light, shape: *sphere, ring: 1.2, blend: atop,
         fill: {lgrad: [[0, "#FFFFFF00"], [1, "#FFF3C060"]], angle: 90}}
      - {name: glint, shape: {ellipse: [13, 10, 4.5, 2.6], angle: -30}, fill: "#FFFFFF", soft: 1, opacity: 0.8}
```

**Notes:** `lgrad: stops, angle: deg` spans the canvas (0° = left → right, 90° = top → bottom, like CSS);
`lgrad: stops, from: [x0, y0], to: [x1, y1]` spans two dp points. `rgrad: stops, center, radius, ratio` (an
ellipse when `ratio` ≠ 1). `&gem` / `*gem` are YAML anchors: the mask and the outline reuse one polygon. The
piece `mask` multiplies every output's alpha by its shape's coverage after all layers, so it also cuts
shadows and glows: the orb, which casts a shadow, keeps its edge clean with `atop` instead.

## 13. Torn parchment (roughen + mask)

**When:** fantasy maps, quest scrolls, notes, torn paper and chipped stone: `roughen` perturbs a shape's edge
with tileable noise. The edge varies along both axes, so both axes tile, with the roughen period.

```yaml
ninekit: 1
name: parchment
scales: [1, 2, 3]
out: out/

vars:
  ROUGH: 1.6                     # how far the edge wanders (dp, each way)

colors:
  paper: [[0, "#E9D5A6"], [0.5, "#F3E4BE"], [1, "#FBF2D8"]]

pieces:
  parchment:
    size: [120, 96]
    stretch: [tile, tile]        # paper grain and torn edge repeat every 24 dp
    content: [16, 16, 16, 16]
    # the silhouette: a torn rectangle, cut once after every layer
    mask: {shape: &sheet {inset: 4, r: 3}, roughen: &torn {amount: ROUGH, period: 24, scale: 3, seed: 5}}
    layers:
      - name: paper              # covers the whole canvas: the mask gives it its edge
        shape: {all: true}
        fill: {noise: {kind: value, period: [24, 24], scale: 8, octaves: 4, seed: 3, stops: paper}}
      - name: burnt edge         # the same torn edge, grown 1 dp past the mask, so the mask cuts it
        shape: *sheet
        roughen: *torn
        grow: 1
        fill: {depth: [[0, "#5A3A1C"], [2.2, "#8C6436A0"], [7, "#8C643600"]]}
```

**Slices:** [12, 12, 12, 12] dp; the tile regions are whole 24 dp periods. `roughen: {amount, period, scale, octaves,
seed}` counts as a periodic paint: fine on `tile` and `fixed` axes and on pieces drawn whole, a problem along a
`stretch` axis (`period: [24, 0]` would only roughen along x, for a torn strip that tiles in x and stretches in
y). **Overflow, then cut once:** every layer that reaches the silhouette is drawn past it (`{all: true}`,
`grow: 1`) and `mask` makes the one anti-aliased edge; a layer whose own edge sat exactly on the mask edge
would be cut twice there (a fringe too thin). `mask` may be a shape or `{shape, grow, soft, roughen}`.
