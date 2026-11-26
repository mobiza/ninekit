---
name: ninekit
description: Generate production-quality game and app UI sprites with the ninekit CLI - 9-slice panels, cards, buttons (frame + pressable face), pills, tabs, badges, progress bars, frames, HUD pieces and icons drawn whole - from a reference screenshot or a style description, measured, verified and exported at @1x/@2x/@3x for Godot, Unity, Flutter, CSS/web, Phaser or plain JSON. Use it whenever a request is to create, recreate, restyle, re-theme, recolour or fix UI art, skins, 9-patch/nine-slice textures or HUD sprites, or to make a game's UI "look like this screenshot", in any engine. Do not hand-draw or hand-edit UI PNGs.
---

# ninekit: UI sprites from measured vectors

ninekit renders UI pieces described in a YAML spec (stacks of vector layers, or code blocks) into PNGs at
every scale plus one manifest, `ninekit.json`, with the 9-slice borders, stretch modes, content insets and
overhangs. Exporters turn the manifest into engine assets. The craft it encodes (from a production game's UI):
measure the reference, layer outside in, keep the stretched middle clean, and never ship without a
measured `verify` and a look at the pixels.

Use it for anything flat-to-glossy and geometric: panels, cards, buttons, pills, tabs, bars, badges,
frames, plates, chips, HUD capsules, medals, simple round icons. Do not use it for painted illustrations,
characters or detailed icons (ask for art for those; ninekit can frame them).

## Setup

```sh
ninekit --version                                   # installed?
pip install git+https://github.com/mobiza/ninekit  # if not (Python >= 3.10; numpy, pillow, pyyaml)
```

Inside a ninekit checkout without installing: `PYTHONPATH=src python3 -m ninekit ...`.

## Workflow

1. **Pin down the target.** Which engine, which pieces and states (normal / pressed / disabled /
   selected), the project's **design width** `D` in dp (logical units of its layout), and `scales`
   (`[1, 2, 3]` for mobile, `[1, 2]` for desktop/web). Look for an existing ninekit spec in the project
   first (`grep -rl "ninekit: 1"`) and extend it instead of starting over.
2. **Measure the reference, don't eyeball it.** `W` = the reference screenshot's width in px.
   ```sh
   ninekit measure ref.png --x 540 --from 900 --to 1080 --ref-width 1290 --design-width 430
   ninekit measure ref.png --y 990 --from 300 --to 640 --ref-width 1290 --design-width 430
   ```
   `--x` reads a column (vertical bands: outline, bezel, gloss, face, lip, shadow), `--y` a row (side
   bands: outline, walls). Each band has a dp thickness, sub-pixel edges (`edge_start`/`edge_end` in
   `--json`) and start/mid/end colours. Corner radii: `ninekit measure ref.png --corner tl --box
   x0,y0,x1,y1` (box around the body, without its shadow). Write every number into `vars`, every colour
   into `colors` under a role name. Details and a worked example: `references/workflow.md`.
3. **Write the spec.** Start from `ninekit new DIR` or the closest recipe in `references/recipes.md`.
   Layer **back to front, outside in**: shadow → outline → rings/bezel → walls/lip → face → gloss and
   highlights. Each band becomes a shape inset by the bands outside it.
4. **Build, verify, preview.**
   ```sh
   ninekit build ui.yaml && ninekit verify ui.yaml && ninekit preview ui.yaml
   ```
   `verify` exits 1 on any failure; `build` only warns. `preview` writes `out/<name>.preview.png`: each
   piece at its design size, 1.5× wider, 2× wider and 1.5× taller (pieces that fail get a red label). Themes: add `--theme t.yaml` to `verify`/`preview`/`compare`. `--json` on
   `build`, `verify`, `compare` and `measure` gives machine-readable results.
5. **LOOK at the sheet.** Open the preview PNG (read the image). Check the small, wide and tall
   versions on both backgrounds, then `ninekit preview ui.yaml --scale 1 -o /tmp/ui_1x.png` for @1x.
6. **Compare with the reference side by side** at the same size, then open the image:
   ```sh
   ninekit compare ui.yaml button ref.png --crop 300,900,340,180 --ref-scale 3 -o /tmp/cmp.png
   ```
   It draws `reference | ninekit | difference heatmap` and prints mean/max difference and PSNR
   (`--ref-scale` = reference px per dp = `W / D`; without `-o` it writes `out/compare_<piece>.png`).
   `ninekit render ui.yaml button --size 200x62 [--pressed] -o b.png` draws a piece at any size or pressed,
   as a runtime would. Fix the biggest difference, rebuild, re-verify, look again. Iterate until it matches.
7. **Export and check in the engine.**
   ```sh
   ninekit export out/ninekit.json --target godot -o path/to/project/ui --runtime
   ```
   Targets: `json godot unity flutter css phaser` (`references/engines.md`). Run the project and look at
   the pieces there at several sizes.

Report what you built with the preview image path, the verify summary and the exported files.

## Hard rules

* **Never hand-edit or hand-paint a PNG.** Every pixel comes from the spec; change the spec and rebuild.
* **Measure, then draw.** Thicknesses, radii and colours come from `ninekit measure` (or the project's
  existing numbers), converted with the design width: `dp = px × D / W`.
* **Gradients are vertical only** (`vgrad`; `depth` follows the edge). Anything that varies horizontally
  (a gloss end, a mitre, a centred highlight, a horizontal fade) must live inside the **side slices**:
  shapes that span the width and end within the corners, never a feature centred on the piece. Otherwise
  the piece cannot stretch (verify: "the identical columns around the centre are only ...").
* **One silhouette edge.** Layers drawn on the same outer edge stack their anti-aliased fringes and the
  piece looks heavier than the reference: paint the later ones `blend: atop`, or draw them past the edge
  (`{all: true}`, `grow: 1`) and give the piece `mask: <shape>` (cuts every output, shadows included).
  Inset a chamfered shape with `grow: -d`, not a smaller rect.
* **Let `slice: auto` and compaction slice it** (one dp slice for every scale, on the dp grid). Give
  explicit `slice_px` only to reproduce legacy art exactly; `slice: none` for pieces drawn whole (icons,
  round buttons, medals).
* **An axis that must not stretch is `fixed`** (`stretch: [stretch, fixed]`): runtimes draw it at its
  natural length, centred. Auto slicing makes y `fixed` by itself when no rows can stretch: pieces rounded
  over their whole height (pills, bars) and slanted lines or patterns through the middle (the y middle must
  be smooth: ≤ 8/255 per row and ≤ 3/255 bend over three rows). Design those at the size you use them.
* **Pressable things are `outputs: [frame, face]`.** `frame` = shadow, outline, bezel, dark well; `face` =
  everything that moves. The face covers the well until pressed; the runtime scales it in.
* **Labels go in `content` insets** (the runtime draws text); **shadows and glows go in `overhang`** (the
  art outside the logical box). Leave canvas room for them.
* **`scales: [1, 2, 3]` by default for mobile**, every scale rendered natively; check @1x.
* **Colour fields use role names** (`face`, `lip`, `accent`), states are `variants`, other concepts are
  themes (`--theme`) over the same pieces. **One art in many colours** → `mode: shade` (shades 0..1, the
  runtime maps a colour ramp).
* **Noise, image and `roughen` need `tile` (or `fixed`) on every axis they vary along**, and everything else
  in the side/top slices must be constant along that axis. A repeating *drawn* shape (stripes, notches) needs
  `stretch: tile` plus `period: [pw, ph]`. `lgrad`/`rgrad` vary along x: pieces drawn whole or the corners.
* **Done means:** `verify` passes, you looked at the preview, compared it with the reference
  (`ninekit compare`), and checked the export in the engine.

## Spec in one screen

```yaml
ninekit: 1
name: ui                      # manifest name
scales: [1, 2, 3]
out: out/
vars: {R: 12, LIP: 4}         # numbers or expressions: "R + 2", "round(42 * U * scale) / scale"
colors:
  ink: "#3A2E22"
  face: [[0, "#FFFBF0"], [0.35, "#F8EED8"], [0.65, "#F8EED8"], [1, "#EADBBE"]]   # a named gradient
pieces:
  panel:
    size: [56, 48]            # dp; layers may use w, h
    content: [10, 8, 10, 12]  # label insets (dp)
    overhang: [0, 0, 0, 2]    # art outside the logical box (dp)
    layers:                   # back to front
      - {shape: {rect: [1, 2, "w - 1", h], r: R}, fill: "#000000", soft: 2, falloff: smooth, opacity: 0.3}
      - {shape: {rect: [0, 0, w, "h - 2"], r: R}, fill: ink}
      - {shape: {rect: [1.2, 1.2, "w - 1.2", "h - 2 - LIP"], r: "R - 1.2"}, fill: {vgrad: face}}
    variants:
      panel_dark: {colors: {ink: "#0C1122", face: [[0, "#3A4A6E"], [0.35, "#2B3756"], [0.65, "#2B3756"], [1, "#222C46"]]}}
```

* Shapes: `rect [x0,y0,x1,y1]` / `inset d` (+ `r`, `chamfer`), `circle [cx,cy,r]`, `ellipse [cx,cy,a,b]`
  (+ `angle`), `polygon`, `union` / `intersect` / `subtract`, `{all: true}`.
* Paints: colour or name, `{vgrad: stops, from, to}`, `{depth: stops}` (by distance inside the edge:
  bevels, inner shadows), `{lgrad: stops, angle}`, `{rgrad: stops, center, radius}`,
  `{noise: {kind: value|grain|wood, period, axis, warp, ...}}`, `{image: file, size}`.
* Layer keys: `grow`, `ring` (band inside the edge), `clip`, `soft`, `falloff: linear|smooth|exp`,
  `opacity`, `offset`, `blend: normal|add|multiply|screen|erase|atop`, `roughen: {amount, period}`,
  `output`, `when`, `name`. Piece keys also: `mask`, `period`. Share shapes/layers with YAML anchors
  (`&body` … `*body`).
* `stretch`: `stretch` | `tile` | `fixed` per axis; `keep` (default 2 dp) is the middle compaction leaves;
  `grid: 1` keeps auto slices on whole dp with `scales: [3]`.
* Code blocks: `block: casual_button` + `params: {style: mint}` = a glossy bevelled push button with a steel
  bezel (presets `berry mint sky sun grape coal cloud gray`; every measurement and colour is a param).

Full reference: `references/spec.md`.

## Troubleshooting

| symptom | fix |
|---|---|
| `x: the identical columns around the centre are only ...` | Something varies along x in the middle: a centred ellipse/gloss, a polygon, noise. Make highlights span the width and end inside the corners; noise → `stretch: [tile, …]`; icons → `slice: none`; not meant to stretch → `stretch: [fixed, …]`. |
| `y stretch region ... is not smooth: rows A and B differ` | A horizontal edge or line crosses the middle rows (explicit slices). Move it into the top/bottom slice or use `slice: auto`. |
| Manifest says y is `fixed` but it should stretch | No smooth rows through the middle: rounded over the whole height, a line or a slanted/patterned detail through the centre. Give the piece a straight-sided, calm middle (patterns → `tile` + `period:`), or accept the fixed height. |
| `a noise/image paint varies along x ... set stretch x to tile` | Set `stretch` to `tile` on that axis. |
| `no tile period found on x/y; give period:` / no seamless repeat | A drawn repeating shape needs `period:`; else something outside the texture varies along the tiled axis (e.g. a `vgrad` on the frame), or the piece is shorter than one period plus borders. |
| Edges heavier / darker than the reference, fat rounded corners | Shared silhouette edges: `blend: atop` on the later layers, or overflow + `mask` (`ninekit compare` shows a bright arc on the corners). |
| `unknown key(s) ...` / `does not take ...` | A typo or a key on the wrong object; see `references/spec.md`. |
| `'w' is not available here` | `w`/`h` are not defined in `size` or block `params`; use vars. |
| `... cannot be set on a block piece` | Blocks decide `size`/slices/outputs; set the block's params instead. |
| warning `the stretch region is fully transparent` | Fine for a hollow frame; otherwise a fill is missing. |
| warning `slice(s) ... thinner than 1 dp` | Usually fine; check the corner looks right at @1x. |
| A thin line vanishes at @1x | It is thinner than 1 texel there: make it ≥ 1 dp or add it with `when: "scale >= 2"`. |
| `note: size ... not on the ... dp grid: snapped` | The size is not whole grid steps (1 dp for `[1, 2, 3]`); use grid multiples so `w`, `h` are what you wrote. |
| Piece cannot shrink below its design size | The slices cover most of it (a full-height gradient is a smooth middle; corners are big). Design the piece at the size it is used at. |
| Themed build looks wrong but `verify ui.yaml` passed | Verify the theme too: `ninekit verify ui.yaml --theme t.yaml`, `ninekit preview ui.yaml --theme t.yaml`. |
| Wrong size in the engine | Check the exporter's scale handling (`references/engines.md`) and that the engine uses the file's own `slice_px`. |

## References

* `references/workflow.md`: reference → sprite in detail, `measure` and `compare` worked example,
  verification checklist.
* `references/recipes.md`: working specs: casual bevelled button (layers and block), cream card (atop),
  pill and tab, badges, progress bars and candy stripes (`period:`), flat minimal (mask), neon chamfered
  panel with glow, wood/stone and vertical wood tiles, shade mode, themes, gem and orb (lgrad/rgrad), torn
  parchment (roughen + mask).
* `references/spec.md`: every key, shape, paint, expression, slicing rule, block param and CLI flag.
* `references/engines.md`: each export target, its runtime nodes/widgets/classes and units.
* `docs/DESIGN.md` in the ninekit repository: the design contract.
