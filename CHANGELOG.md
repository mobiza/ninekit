# Changelog

All notable changes to ninekit are listed here. The project follows [Semantic Versioning](https://semver.org/).

## 0.1.0 — initial release

The first public release.

### Spec language

* YAML specs (`ninekit: 1`) of pieces drawn as stacks of vector layers, back to front, in dp.
* Signed-distance shapes: rounded and chamfered rects, circles, ellipses, polygons, `union` / `intersect` /
  `subtract`; layer keys `grow`, `ring`, `clip`, `offset`, `soft` with falloffs, `opacity`, `roughen`.
* Paints: colours, vertical gradients (`vgrad`), `depth` (by distance from the edge), `lgrad`, `rgrad`, tileable
  `noise` (value, grain, wood) and seamless images; blends `normal`, `add`, `multiply`, `screen`, `erase`, `atop`;
  a piece-level `mask`.
* Vars and expressions, named colours and gradients, variants, themes (`--theme`), includes, YAML anchors.
* Code blocks for art the layers cannot express: `casual_button`, a glossy bevelled push button with a metal
  bezel (eight presets, rectangular and round, every measurement and colour a param).

### Rendering and slicing

* Every scale (@1x, @2x, @3x, ...) rendered natively with one texel of anti-aliasing.
* Automatic 9-slice borders found from the pixels on a dp grid shared by every scale, lossless compaction of the
  identical middle, per-axis `stretch`, `tile` (whole repeats, `period:` for drawn patterns) or `fixed`.
* `frame` + `face` outputs for pressable pieces, `content` insets for labels, `overhang` for shadows and glows,
  `mode: shade` art recoloured at runtime.
* One engine-neutral manifest, `ninekit.json`.

### Command line

* `new`, `build`, `verify` (exit 1 on any failure), `preview` (contact sheets), `render` (any size, pressed),
  `compare` (side by side with a reference, heatmap, PSNR), `measure` (colour bands with sub-pixel edges, corner
  radius fit), `export`; `--json` output for agents.

### Engines

* Exporters and runtimes for Godot (4.7), Unity (6000.6), Flutter, CSS, Phaser (3.90) and plain JSON, each
  checked in the real engine by the projects under `demos/`.

### Examples, docs and agents

* Sample concepts Gumdrop (candy casual), Neon (sci-fi HUD) and Wood (fantasy), a tour of the language (basics)
  and a worked recreation of a reference (recreate).
* An agent skill (`skills/ninekit`) with references for the workflow, recipes, the spec and the engines; a Claude
  Code plugin and marketplace (`mobiza`); `AGENTS.md` for other coding agents.
* Golden pixel tests for the Gumdrop art and a test that builds and verifies every spec in the docs.
