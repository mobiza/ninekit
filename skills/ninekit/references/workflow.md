# From a reference to a verified sprite set

The loop: **measure → write layers → build → verify → preview → look → compare → iterate → export →
check in the engine.** Numbers come from measuring the reference, never from eyeballing it, and nothing
ships without both a passing `verify` and a look at the pixels.

## 1. Collect the reference

* Use the original screenshot at full resolution (PNG, not a resized or JPEG-compressed copy).
* Note what device or canvas it came from: you need its width in px (`W`).
* One reference image can hold many pieces; measure each piece separately.
* If the request is a style description instead of a screenshot, start from the closest recipe in
  `recipes.md` and skip to step 4; you still compare the result against the description (and against any
  existing UI in the project) by looking at the preview.

## 2. Choose the design width

ninekit works in **dp**: the logical units of *your* game's layout (Godot viewport units, Unity reference
resolution / canvas units, Flutter logical px, CSS px, iOS pt). The design width `D` is the width of the
screen in those units. Measured reference px convert to dp with `dp = px × D / W`.

| reference | W (px) | typical D |
|---|---|---|
| iPhone 15/16 Pro Max screenshot | 1290 | 430 pt |
| iPhone 15/16 / 15/16 Pro screenshot | 1179 | 393 pt |
| iPhone 13/14 screenshot | 1170 | 390 pt |
| iPad (10th gen) screenshot | 1640 | 820 pt |
| Android phone screenshot | 1080 | screenshot px ÷ density, usually 360–412 dp |
| the project's own layout | its viewport | the project's design width (e.g. 390 or 430) |

When the reference comes from another app, use **your** project's design width for `D` and the
reference's screen width for `W`, so the pieces come out at the size your layout will use them. If the
reference is a mockup with the phone drawn inside a bigger image, `W` is the width of the phone screen in
that image, not the image width.

Pick `scales` to cover the device pixel ratios you ship: `[1, 2, 3]` for mobile, `[1, 2]` for desktop and
web. Each scale is rendered natively.

## 3. Measure with `ninekit measure`

`measure` reads one line of the image and splits it into **bands**: runs whose colour is constant or
changes smoothly. Anti-aliased transitions and soft alpha ramps are absorbed into the band they belong to,
and the band's real edges are reported **to a fraction of a pixel** (`edge0`/`edge1` in the table,
`edge_start`/`edge_end` and `edge_start_dp`/`edge_end_dp` in `--json`): from the alpha coverage on a
silhouette, from colour interpolation between two bands inside. Use those, not the whole-pixel
`start`/`end`, for thicknesses: `edge_end − edge_start` is the band as drawn.

* `--x X` reads the **column** X top to bottom: the vertical structure (outline, bezel, gloss, face, lip,
  shadow). Pick a column through the plain middle of the piece, away from labels and icons.
* `--y Y` reads the **row** Y left to right: the side structure (outline, walls). Use `--to` to stop at
  the middle.
* `--from` / `--to` limit the line to the piece (reference px, end exclusive).
* `--ref-width W --design-width D` adds a `dp` column. `--json` gives `start_dp`, `end_dp`,
  `thickness_dp` and colours per band.
* Noisy or JPEG-ish reference: `--avg 3` averages 3 px across the line; `--tol 16` tolerates bigger steps
  inside a band. `--min-alpha A` (default 8) counts fainter pixels as transparent (stray shadow haze).
* **Corner radius:** `ninekit measure ref.png --corner tl --box x0,y0,x1,y1` fits the radius from the alpha
  coverage of that corner (the area a rounded corner misses is (1 − π/4)·r²). Give a `--box` tight around
  the piece's body, without its shadow; `--json` returns `radius_px`/`radius_dp` and `edge_x_*`/`edge_y_*`,
  the distances from the box's sides to the straight edges (non-zero when the box is loose). Fit two
  opposite corners: a different bottom radius usually means a shadow or lip is inside the box.

### Worked example: Gumdrop's mint button

`tests/fixtures/gumdrop/buttons/btn_mint_face@3x.png` and `btn_mint_frame@3x.png` are the frame and face of
Gumdrop's mint button at 3x (the sample concept in `examples/gumdrop/`): 384 x 186 px for a 128 x 62 dp button.
Here the "reference" is the sprite itself, so `W = 384`, `D = 128` (for a phone screenshot it would be e.g.
`--ref-width 1290 --design-width 430`). From the repository root:

```sh
ninekit measure tests/fixtures/gumdrop/buttons/btn_mint_face@3x.png --x 192 --ref-width 384 --design-width 128
```

```
 #   y0   y1   px     dp   edge0   edge1  kind      soft  start         mid           end
 0    0   13   13   4.33    0.00   13.00  flat      0/0   #000000/a0    #000000/a0    #000000/a0
 1   13   14    1   0.33   13.00   14.00  flat      0/0   #0b4733/a128  #0b4733/a128  #0b4733/a128
 2   14   15    1   0.33   14.00   15.26  flat      0/0   #00422b       #00422b       #00422b
 3   15   17    2   0.67   15.26   17.00  flat      1/0   #dbfff9       #dbfff9       #dbfff9
 4   17   23    6   2.00   17.00   23.00  gradient  0/0   #ccfbeb       #c7fce9       #c0fae4
 5   23   27    4   1.33   23.00   26.51  gradient  0/1   #a1f4d1       #a0f4d0       #a8f5d4
 6   27  134  107  35.67   26.51  133.73  gradient  0/1   #bff7df       #4dd6a3       #22a776
 7  134  136    2   0.67  133.73  136.29  flat      0/0   #64e4b5       #65e6b6       #65e6b6
 8  136  155   19   6.33  136.29  154.70  gradient  1/1   #127f57       #137a54       #11734e
 9  155  158    3   1.00  154.70  157.50  gradient  0/1   #08432e/a251  #094b34       #094b34
10  158  186   28   9.33  157.50  186.00  flat      0/0   #000000/a0    #000000/a0    #000000/a0
```

```sh
ninekit measure tests/fixtures/gumdrop/buttons/btn_mint_face@3x.png --y 93 --to 100 --ref-width 384 --design-width 128
```

```
#  x0   x1  px     dp  edge0   edge1  kind      soft  start       mid         end
0   0   13  13   4.33   0.00   13.50  flat      0/0   #000000/a0  #000000/a0  #000000/a0
1  13   15   2   0.67  13.50   15.29  flat      1/0   #074530     #074530     #074530
2  15   26  11   3.67  15.29   26.00  gradient  1/0   #34be8c     #32b887     #33b988
3  26  100  74  24.67  26.00  100.00  flat      0/0   #3fcc98     #40cd99     #40cd99
```

```sh
ninekit measure tests/fixtures/gumdrop/buttons/btn_mint_frame@3x.png --x 192 --ref-width 384 --design-width 128
```

```
 #   y0   y1   px     dp   edge0   edge1  kind      soft  start        mid          end
 0    0    2    2   0.67    0.00    2.50  gradient  0/0   #28303d      #202734      #202734
 1    2    6    4   1.33    2.50    6.26  gradient  1/0   #8290a6      #7b899d      #75849a
 2    6    8    2   0.67    6.26    8.00  flat      1/0   #ffffff      #ffffff      #ffffff
 3    8   12    4   1.33    8.00   12.00  gradient  0/0   #f1f5f9      #e9eef4      #e5eaef
 4   12   13    1   0.33   12.00   13.49  flat      0/0   #f9fdff      #f9fdff      #f9fdff
 5   13   15    2   0.67   13.49   15.00  flat      1/0   #000600      #000600      #000600
 6   15  156  141  47.00   15.00  156.00  gradient  0/0   #071a12      #041c12      #092319
 7  156  158    2   0.67  156.00  157.51  flat      0/1   #001609      #001609      #001609
 8  158  159    1   0.33  157.51  159.00  flat      0/0   #adb8ca      #adb8ca      #adb8ca
 9  159  165    6   2.00  159.00  164.72  flat      0/1   #9eabba      #a0acbc      #a2aebf
10  165  169    4   1.33  164.72  168.52  flat      0/1   #5c697e      #5f6c81      #616e83
11  169  174    5   1.67  168.52  174.48  flat      0/0   #485364      #4a5566      #4c5768
12  174  177    3   1.00  174.48  176.93  flat      1/1   #242c39      #242c39      #242c39
13  177  186    9   3.00  176.93  186.00  gradient  1/0   #1c2038/a63  #1c2239/a44  #1b2436/a28
```

The corner of the same button:

```sh
ninekit measure tests/fixtures/gumdrop/buttons/btn_mint_frame@3x.png --corner tl --ref-width 384 --design-width 128
```

```
corner tl  box [0, 0, 384, 186]
  radius    60.035 px    20.012 dp
  edge x     0.000 px     0.000 dp
  edge y     0.000 px     0.000 dp
```

a 20 dp radius (`casual_button`'s `radius: 20`). Sub-pixel edges matter for thin bands: the face's dark
line is band 1 (one half-covered pixel, alpha 128, so its material starts at 13.5) plus band 2, whose
material ends at 15.26, not 15: 15.26 − 13.5 = 1.76 px = 0.59 dp, the block's `line: 0.6`. Whole pixels
would have said 2 px = 0.67 dp (`--json` prints `edge_start`, `edge_end` for every band).

## 4. Turn bands into layers

Read the bands **outside in** and draw them **back to front**: each band becomes a shape inset by the sum
of the bands outside it, filled with the band's colour, and the next band (one step further in) covers
its inside. A band that is a line or light on top of others (a highlight, an edge line) becomes a `ring`.
The outermost band is the silhouette: anything else drawn on that same edge (a rim light, a lip that
starts at the top, a hairline) gets `blend: atop`, or the layers overflow it and the piece gets a `mask`
(`spec.md` → *Shared edges*); otherwise the edge comes out thicker than the reference. To inset a chamfered
shape, reuse it with `grow: -d`.

| measured band (dp) | what it is | layer |
|---|---|---|
| frame 0: 0.67 / frame 12: 1.00 | dark outline (top / bottom) | `rect [0, 0, w, B]`, the outline colour |
| frame 1: 1.33 / frame 10: 1.33 | outer steel ring (top / bottom) | inset by the outline (`O`) |
| frame 2 + 3 + 4: 0.67 + 1.33 + 0.33 | inner silver ring with a white rim light on top | inset by `O + RING`; the light row as a fading `ring` |
| frame 11: 1.67 | darker depth band at the bezel's bottom | the rings' bottom moved up by `DEPTH` |
| frame 6: 47.00 | the well: very dark, only visible when pressed | inset by the bezel |
| frame 13: 3.00, alpha 63 → 28 | soft drop shadow below the body | an offset, `soft` shape drawn first; `overhang` bottom 3 |
| face 1 + 2: 0.67 | dark line inside the bezel (0.6 dp + its anti-aliased edge) | inset by the bezel |
| face 3 + 4: 2.67, very light | top bevel ("gloss") | mitred polygon, `vgrad` over the band |
| face y-row 2: 3.67 | side walls | the face block's own fill |
| face 5 + 6: 37.00, `#a1f4d1` → `#4dd6a3` → `#22a776` | the face panel, a sheen over its upper part | `vgrad` over the band; the sheen a capsule with an alpha `vgrad` |
| face 7: 0.67, lighter | the panel's light bottom line | a `ring` clipped to the bottom |
| face 8: 6.33 | the lip (bottom bevel) | mitred polygon, dark `vgrad` |
| face 9: 1.00 | dark bottom line (0.9 dp + AA) | part of the dark line shape (`line_bottom`) |

Rules for reading numbers:

* A band's `thickness_dp` includes anti-aliased pixels: thin lines measure up to 1 reference px thicker
  than they are drawn. Round to a clean value that reproduces the band at the reference's own scale
  (here 0.67 → 0.6 dp line, 1.00 → 0.9 dp bottom line).
* `gradient` bands give `start`, `mid` and `end` colours: use them as `[0, start], [0.5, mid], [1, end]`
  stops over the band's `start_dp..end_dp` (`vgrad: {from, to}`). Add stops if the mid colour is off the
  straight line between start and end.
* Colours that differ only by alpha (`/a254`) are edge pixels of the same colour.
* Horizontal rows tell you what lives in the side slices (walls, bevel mitres). A flat band reaching the
  centre (`--y` band 3 here) is the stretchable middle.

These numbers are `casual_button`'s defaults (`outline 0.8, outer_ring 1.3, inner_ring 2.4, depth 2,
line 0.6, line_bottom 0.9, gloss 2.6, wall 3.6, lip 6.2, face_edge_width 0.8`, `btn_h - body_h = 3`),
which is why `{block: casual_button, params: {style: mint}}` reproduces this button byte for byte. For a
different reference, either set those params from your measurements or write the layers (recipe 1 in
`recipes.md` is this structure in the layer language, every band a var).

Write the measurements as `vars` (`O: 0.6`, `GLOSS: 4.7`, ...) and derive positions from them (`IN: O +
BZ`), and give every colour a role name in `colors`. Then a re-measure is a one-line change and a theme
can restyle the set.

## 5. Build, verify, preview, look

```sh
ninekit build ui.yaml            # PNGs + out/ninekit.json; slicing problems print as warnings
ninekit verify ui.yaml           # fresh build in a temp folder; exit 1 on any failure
ninekit preview ui.yaml          # out/<name>.preview.png
```

Open the preview PNG and look at it (an agent: read the image file). Each piece is drawn first at its
design size, then 1.5× wider, then 2× wider and 1.5× taller, on a checkerboard and on a dark background;
pieces that fail verify have a red label with the reason. For a theme add `--theme t.yaml` to `verify` and
`preview`. Check:

* the wide and tall versions look like the small one: nothing smeared, no seams, no doubled highlight;
* corners are round and clean, outlines even all around, the silhouette no heavier than the reference's
  (shared edges, above);
* shadows and glows stop inside the canvas (else grow `overhang` and the canvas);
* `@1x` too: `ninekit preview ui.yaml --scale 1 -o /tmp/ui_1x.png`: hairlines thinner than 1 dp fade at
  1x; thicken them or add them only at higher scales with `when: "scale >= 2"`.

## 6. Compare with the reference, side by side

Looking at the preview alone is not enough: put the rendered piece next to the reference at the same
size. `ninekit compare` draws the piece's stacked outputs as a 9-slice (ninekit's own resampler) at exactly
the size of a box in the reference and writes `reference | ninekit | |difference| heatmap`:

```sh
ninekit compare ui.yaml button ref.png --crop 300,900,340,180 --ref-scale 3 -o /tmp/cmp.png
```

* `--crop x,y,w,h`: the piece's box in the reference (ref px), including the shadow it casts; default the
  whole image.
* `--ref-scale`: reference px per dp, i.e. `W / D` (1290 / 430 = 3); default the spec's largest scale.
* `--outputs frame,face`: which outputs to stack (default the piece's stack); `--theme`, `--bg`, `--zoom`,
  `--json` as elsewhere. It also takes a built manifest instead of the spec.
* It prints mean and max absolute difference (8-bit RGB), PSNR and the share of pixels off by more than
  16/255. The heatmap is ×4: black → red → yellow → white. Without `-o` the image goes to
  `<out>/compare_<piece>.png`.

**`ninekit render`** draws a piece at any dp size the way a runtime draws it: use it when the reference
shows the piece at a size other than its design size, to check the pressed state, or to make mockups:

```sh
ninekit render ui.yaml button --size 200x62 -o /tmp/button_200.png
ninekit render ui.yaml button --size 200x62 --pressed -o /tmp/button_pressed.png
```

A rendered PNG can itself be the reference of a `compare` (e.g. the pressed button against a screenshot of
the pressed state, with `--ref-scale`).

Worked example, from the repository root, with this spec saved as `mint.yaml`:

```yaml
# file: mint.yaml
ninekit: 1
name: mint
scales: [1, 2, 3]
pieces:
  btn: {block: casual_button, params: {style: mint}}
```

```sh
ninekit compare mint.yaml btn tests/fixtures/gumdrop/buttons/btn_mint_face@3x.png --outputs face -o face.png
```

prints `mean abs diff 0.00/255, max 0/255, PSNR inf, 0.00% of pixels over 16/255`: the block reproduces
the face exactly. The layered button of recipe 1 (the same bands as layers) against the same reference gives
a mean of 1.30/255, max 56/255 and PSNR 39.35 dB (1.00% of pixels over 16/255), and its heatmap lights up
exactly where the two differ: the anti-aliasing of the panel's corners and of the sheen's edge, and the
lower mitres. Fix the biggest difference first (a band at the wrong height shows as a bright
line, a wrong colour as a lit area), rebuild, verify, compare again. Labels and icons in the reference
show in the diff: they are not part of the sprite (crop around them or ignore them).

Iterate: change the vars/colours, rebuild, re-verify, re-preview, re-compare (and re-render the sizes and
states the reference shows). Never touch the PNGs.

## 7. Export and check in the engine

```sh
ninekit export out/ninekit.json --target godot -o path/to/project/ui --runtime
```

See `engines.md` for each target. Then run the project and look at the pieces in the engine at a few
sizes, on the device scale you ship (and at least one other). An exporter's units are only right once
seen in the engine.

## Verification checklist

- [ ] `ninekit verify SPEC` exits 0: no failed files, no spec problems; any warnings understood
      (a fully transparent middle is fine for a hollow frame).
- [ ] Themed sets: `ninekit verify SPEC --theme T` passes and you looked at `ninekit preview SPEC --theme T`.
- [ ] Looked at the preview sheet: all three sizes, checkerboard and dark background.
- [ ] Looked at `--scale 1` (and every other shipped scale): no vanished hairlines, no blurry edges.
- [ ] `ninekit compare` against the reference at the same size: the heatmap is dark apart from labels and
      icons.
- [ ] Stretched wide and tall: the middle is clean (only vertical gradients, highlights inside the side
      slices); an axis that must not stretch is `fixed` in the manifest.
- [ ] `content` puts labels where the reference has them; `overhang` covers every shadow and glow.
- [ ] Frame/face pieces: `ninekit render ... --pressed` looks right (the face sinks into the well).
- [ ] The silhouette is one edge: layers on the outer edge are `atop`, or the piece has a `mask`.
- [ ] Colours are role names, states are `variants`, concepts are themes; no hand-edited PNG anywhere.
- [ ] Exported for the project's engine and checked in the engine.
