# Exporting to an engine

`ninekit build` writes PNGs plus the engine-neutral manifest `ninekit.json`. `ninekit export` turns that
manifest into what one engine wants:

```sh
ninekit export out/ninekit.json --target <json|godot|unity|flutter|css|phaser> -o <dir> [--scale S] [--runtime]
```

* The manifest argument may be `ninekit.json` or its folder. A YAML spec is refused: build first.
* `--scale S` exports only that scale's files (and a manifest filtered to it).
* `--runtime` also copies the engine's runtime (Godot, Unity, Flutter). CSS needs none; the Phaser module
  *is* the runtime.
* Re-exporting into the same folder overwrites in place and removes the files of pieces that are gone
  (Godot, Unity), so export each sprite set into its own folder.
* Demos: `demos/<engine>/` are small projects proving each target in the real engine. Their assets are
  generated, not committed: run `demos/<engine>/regenerate.sh` first (it builds `examples/basics` and
  `examples/gumdrop/buttons` and exports them with the real exporter).

Contents: [shared rules](#shared-rules) · [json](#json) · [godot](#godot) · [unity](#unity) ·
[flutter](#flutter) · [css](#css) · [phaser](#phaser)

## Shared rules

**Units.** Every runtime works in dp (design px): Godot node units, Unity canvas units (reference PPU 100),
Flutter logical px, CSS px, Phaser world units. A file of scale `s` has `s` texture px per dp, and every
file of a layered piece is exactly its dp size and dp slices × `s` (the dp grid). Runtimes draw the
hi-res file at `1 / s` so corners keep their dp size and map 1:1 to texels when the device pixel ratio
equals `s`. Plain engine primitives that use the @1x file (a Godot StyleBox) look soft on 2x/3x screens.

**Box model** (all runtimes). `slice`, `content` and `overhang` are measured from the edges of the full
texture (the canvas). The **logical box** you size and lay out is the canvas minus `overhang`; the art
(shadows, glows) reaches outside it. Children/labels are padded inside the logical box by
`max(0, content − overhang)` per side. Example: `casual_button` is 128×62 dp with overhang `[0, 0, 0, 3]`
and content `[12, 8, 12, 17]` → logical box 128×59, child padding `[12, 8, 12, 14]`.

**Press** (pieces with `frame` + `face` outputs). The face output and the content scale together by 0.92
toward the centre of the logical box and spring back; the frame stays.

**Tiles.** A `tile` axis repeats whole tiles only, each slightly stretched to fit the length (Godot
TILE_FIT, CSS `round`, Unity `FitWholeTiles()`, the Flutter and Phaser runtimes do it themselves). A cut
last tile would meet the end slice at an arbitrary phase.

**`fixed` axes.** A `fixed` axis (requested with `stretch: [.., fixed]`, or chosen by auto slicing when a
piece has no stretchable rows, e.g. a capsule fully rounded vertically) has no engine mode of its own:
exporters write it as the engine's plain stretch mode (never tile), and its middle is one grid step. The
ninekit runtimes (Godot `NineSkin`/`NineButton`, Unity `NineSliceStack`, Flutter
`NineSliceBox`/`NineSliceButton`, the CSS pseudo-element layers, Phaser `addNinekit`) draw the art at its
natural length on that axis, centred on the logical box, whatever length the box gets; the content still
lays out in the box. Plain primitives (a Godot StyleBox, a Unity sliced `Image` without the runtime, a bare
Flutter `centerSlice`) just stretch it: use such pieces at their natural length on that axis.

**Shade pieces** (`mode: shade`) are greys mapped through a colour ramp at runtime: Godot `ramp`
(Gradient + `ninekit_ramp.gdshader`), Unity `NinekitShadeRamp`, Flutter `NineRamp`, CSS an SVG
`feComponentTransfer` filter in `--nk-ramp`, Phaser `opts.ramp`.

## json

For engines without an adapter, or your own tooling.

```sh
ninekit export out/ninekit.json --target json -o export/json
```

Writes the PNGs (at their manifest paths) and `sprites.json`: a top-level array sorted by name, output and
scale, one entry per file:

```json
{"name": "panel", "output": "main", "scale": 3, "file": "panel@3x.png", "size_px": [84, 144],
 "slice_px": [39, 30, 39, 39], "slice_dp": [13, 10, 13, 13], "stretch": ["stretch", "stretch"],
 "content": [10, 8, 10, 12], "overhang": null, "mode": "color"}
```

`slice_px` is `[l, t, r, b]` texels (`null` for pieces drawn whole), `slice_dp` the same divided by the
scale. `mode` tells a reader the art is shade art. Draw the file at `1 / scale` with its own `slice_px`; apply
the box model and the `fixed` rule above yourself. No runtime (`--runtime` is ignored).

## godot

Godot 4 (verified in Godot 4.7, `demos/godot`).

```sh
ninekit export out/ninekit.json --target godot -o path/to/project/ui --runtime
```

* `-o` (here `res://ui`) gets the PNGs at their manifest paths and `ninekit.json` (filtered to the exported
  scales). Godot imports the PNGs on the next editor focus or `godot --headless --path <project> --import`.
* When the export includes scale 1, every output also gets `<piece>[_<output>].tres` next to its @1x PNG: a
  `StyleBoxTexture` with `texture_margin_*` = `slice_px`, `axis_stretch_*` from `stretch` (`tile` →
  TILE_FIT, `fixed` → stretch), `expand_margin_*` = overhang and `content_margin_*` =
  `max(0, content − overhang)`.
* `--runtime` copies `addons/ninekit/` into the Godot project that contains `-o` (the nearest folder above it
  with `project.godot`; override with `--godot-project DIR`): `NinekitManifest` (load/cache a manifest,
  `pick_scale`), `NineSkin` (a `Container`), `NineButton` (a `BaseButton`) and `ninekit_ramp.gdshader`.
  They are global classes (`class_name`); there is no editor plugin to enable.

**StyleBox (no runtime).** Quick theming of existing controls; uses the @1x file (soft on hi-dpi screens),
stretches a `fixed` axis:

```gdscript
$Panel.add_theme_stylebox_override("panel", load("res://ui/panel.tres"))
```

**NineSkin / NineButton (runtime).** Hi-res files at node scale `1 / scale`, one `NinePatchRect` per stacked
output, the box model (the node's rect is the logical box, overhang drawn outside it, children laid out in
the content rect), TILE_FIT tiles, `fixed` axes kept at their natural length and centred, LTR-locked art
inside RTL parents, shade ramps, press.

```gdscript
# NinekitManifest.default_path is "res://ui"; set manifest_path for another folder.
var card := NineSkin.new()
card.piece = "panel"
card.custom_minimum_size = Vector2(220, 90)        # dp = node units
var title := Label.new()
title.text = "Daily reward"
card.add_child(title)                              # laid out in the piece's content rect
add_child(card)

var play := NineButton.new()
play.manifest_path = "res://ui/buttons"
play.piece = "btn_mint"                            # a frame + face piece
play.text = "Play"
play.custom_minimum_size.x = 180
play.pressed.connect(_on_play)                     # press: face + label scale to 0.92 and spring back
add_child(play)

var gem := NineSkin.new()
gem.piece = "button_shade"                         # mode: shade
var ramp := Gradient.new()                         # shade 0 -> first colour, 1 -> last
ramp.set_color(0, Color("#4A2306"))
ramp.set_color(1, Color("#FFF1B8"))
gem.ramp = ramp
add_child(gem)
```

Useful members: `NineSkin.texture_scale` (which scale's files: the smallest at or above it, 0 = largest),
`art_scale` (draw the art smaller/larger than designed), `outputs`, `tile_fit`, `press_scale`,
`content_rect()`, `natural_size()`; `NineButton.label_settings`, `icon`, `disabled_modulate`,
`press_time`/`release_time`. The minimum size keeps the 9-slice corners whole and fits the children.

Units: make the project's viewport width the design width (stretch mode `canvas_items`), so node units are
dp. Regenerate the demo: `demos/godot/regenerate.sh` (`GODOT=/path/to/Godot` also imports it).

## unity

Unity 6 uGUI (verified in Unity 6000.6, `demos/unity`).

```sh
ninekit export out/ninekit.json --target unity -o MyGame/Assets/UI/Ninekit --runtime
```

* `-o` is the project's **single** ninekit root (a second root in one project is refused: the importer would
  compile twice). Each manifest lands in `<root>/<manifest name>/` (PNGs + `ninekit.json`), so several
  sprite sets share the root; a re-export removes the PNGs its previous manifest listed.
* Always written: `Editor/NinekitImporter.cs`, an `AssetPostprocessor` that imports every listed PNG as a
  Sprite (single, FullRect mesh, `spriteBorder` from `slice_px` as (left, bottom, right, top),
  **pixelsPerUnit = 100 × scale**, no mipmaps, bilinear, clamp, uncompressed; re-imports when the manifest
  changes); `NinekitTypes.cs`; `NinekitSprites.cs` (generated descriptors for every manifest under the root:
  `NinekitSprites.Find("basics/panel")` or `NinekitSprites.Basics.Panel`: size, slices, content, overhang,
  stretch, stack, every file).
* `--runtime` adds `Runtime/`: `NineSliceStack` (stacked layers, overhang, content rect, press, `fixed` axes)
  and `NinekitShadeRamp` + its UI shader.

Units: PPU = 100 × scale means `Image.SetNativeSize()` gives the size in dp on a Canvas whose Canvas Scaler
has Reference Pixels Per Unit 100 (the default). Use *Scale With Screen Size* with the design resolution
(e.g. 430 × 932) so canvas units are dp.

**Plain sliced Image (no runtime).** Works for single-output pieces; a `fixed` axis stretches; for `tile`
pieces set `Image.Type.Tiled` and size the rect with `NineSliceStack.FitWholeTiles(...)` (part of the
runtime) or whole tiles yourself.

```csharp
var img = gameObject.AddComponent<Image>();
img.sprite = panelSprite;              // the imported Assets/UI/Ninekit/basics/panel@3x.png
img.type = Image.Type.Sliced;
img.SetNativeSize();                   // dp size, then resize the RectTransform freely
```

**NineSliceStack (runtime).** Add *UI → Ninekit → Nine Slice Stack* to a RectTransform and set *Piece* to
`"manifest/piece"` (the editor loads the sprites from `NinekitSprites` and serializes them; in a build call
`SetSprites` if you change them). The rect is the logical box; layers reach out by the overhang; labels go
under `Content`, which sinks with the face.

```csharp
using Ninekit;
using UnityEngine;

public class PlayButton : MonoBehaviour
{
    [SerializeField] NineSliceStack stack;     // Piece = "gumdrop_buttons/btn_mint" set in the inspector
    [SerializeField] RectTransform label;      // a Text / TMP label

    void Start()
    {
        stack.FitToContent(label);             // label under Content, stretched over the content area
        stack.PressScale = 0.92f;              // pointer down/up press the face + content (Interactable)
    }
}
```

Shade pieces: add `NinekitShadeRamp` next to the stack (or an Image), set its `Ramp` gradient, call `Apply()`.
Regenerate the demo: `demos/unity/regenerate.sh` (`--check` runs the editor check in batch mode;
`UNITY=/path/to/Unity` picks the editor).

## flutter

Flutter (verified with `flutter test` at device pixel ratio 1, 2 and 3, `demos/flutter`).

```sh
ninekit export out/ninekit.json --target flutter -o my_app/assets/ui --runtime
```

* PNGs go in Flutter's resolution-aware layout under `-o` without the `@sx` suffix: scale 1 is the main
  asset (`assets/ui/panel.png`), others go to `2.0x/`, `3.0x/`, `1.5x/`. A spec without scale 1 gets no
  main file (a 3x file there would claim to be 1x); the pubspec snippet then lists each main path, which
  Flutter accepts.
* The app root is the nearest folder above `-o` with a `pubspec.yaml`; asset keys are relative to it. The
  exporter prints the `flutter: assets:` lines to add to `pubspec.yaml`.
* Dart goes to `<app>/lib/ninekit/`: `ninekit_sprites.dart` (one `abstract final class` per manifest, e.g.
  `basics` → `Basics`, with a `NineSprite` const per piece (`Basics.panel`) and a `NineImage` per output
  (`Basics.panelMain`, `Basics.tabFrame`): asset key, logical size, `centerSlice`, content padding,
  overhang, stack, every variant's exact px). Each export rewrites only its own manifest's section.
* `--runtime` adds `ninekit.dart` (re-exports the sprites file): `NineSliceBox`, `NineSliceButton`,
  `NineRamp`, `precacheNineSprite`.

**Units:** `centerSlice` is in **logical (1.0x) pixels**: Flutter's `paintImage` multiplies it by the chosen
variant's scale (measured in `demos/flutter/test/center_slice_test.dart`). It is exact because every file
is its dp slice × scale. Plain `Image.asset` works without the runtime (a `fixed` axis stretches):

```dart
Image.asset(Basics.panelMain.asset,
    centerSlice: Basics.panelMain.centerSlice, fit: BoxFit.fill, width: 240, height: 90);
```

**Runtime widgets.** `NineSliceBox` draws a piece's outputs behind its child with the chosen file's own
`slice_px`, snapped to physical pixels; the box is the logical box, the child is padded by the content
insets, `fixed` axes keep their natural length, tiles are whole. `NineSliceButton` presses the `face`
output and the child to 0.92 with a spring; `onPressed: null` disables it.

```dart
import 'ninekit/ninekit.dart';

NineSliceBox(sprite: Basics.panel, width: 240, child: const Text('Daily reward'));

NineSliceButton(
  sprite: GumdropButtons.btnMint,
  width: 180,
  onPressed: () => startGame(),
  child: const Text('Play'),
);

NineSliceBox(                                   // mode: shade
  sprite: Basics.shadeButton,
  ramp: NineRamp.even([Color(0xFF4A2306), Color(0xFFC8761E), Color(0xFFFFF1B8)]),
  width: 120,
  height: 40,
);
```

`precacheNineSprite(context, sprite)` warms the images (and shade bakes) before first paint. Regenerate the
demo: `demos/flutter/regenerate.sh`, then `flutter test`.

## css

Plain CSS for the web (verified in headless Chrome at DPR 1, 2 and 3, `demos/web`).

```sh
ninekit export out/ninekit.json --target css -o web/ui
```

Writes the PNGs, `ninekit.css` (one class per piece, `nk-<piece>`, plus `nk-<piece>__<output>` per output)
and `index.html`, a gallery of every class. Usage:

```html
<link rel="stylesheet" href="ui/ninekit.css">
<div class="nk-panel" style="width: 240px">Daily reward</div>
<button class="nk-btn_mint" style="width: 180px">Play</button>
```

* The element's box is the logical box (`box-sizing: border-box`), with `padding = max(0, content −
  overhang)`. The sprite is drawn on `::before` (a second output on `::after`; more outputs need a child
  `<span class="nk-<piece>__<output>"></span>` each) at `inset: −overhang`, with `border-image … fill`,
  `border-image-repeat` from stretch (`tile` → `round`), border widths `calc(<slice_px>px / <scale>)`.
* Frame/face pieces: `:active` (or the class `nk-pressed`) scales the face and the content by `--nk-press`
  (0.92) while the frame is counter-scaled.
* `fixed` axis: the layers keep the sprite's natural length on it, centred on the box.
* Pieces drawn whole use `background-image`.
* Shade pieces carry `filter: var(--nk-ramp, none)`: point `--nk-ramp` at an SVG `feComponentTransfer`
  filter (the gallery shows two).

**Units:** `image-set()` across scales is used only when every dp slice is a whole CSS px and every file's
`slice_px` is its slice × scale: Chrome rounds `border-image-slice` to whole CSS px of the chosen image.
Otherwise (fractional dp slices, e.g. a single-scale `casual_button`: 25.33 / 30.67 dp at 3x) each file
gets its own `url()` behind `resolution` media queries with that file's own `slice_px`. For web-only sets,
`grid: 1` in the spec keeps auto slices on whole dp even with `scales: [3]`. Regenerate the demo: `demos/web/regenerate.sh`, then serve the folder and open
`css.html` (`demos/web/check.py` screenshots and measures it).

## phaser

Phaser 3.60+ (verified with Phaser 3.90 in headless Chrome, `demos/web`).

```sh
ninekit export out/ninekit.json --target phaser -o public/ui
```

Writes the PNGs, `ninekit-phaser.json` and `ninekit-phaser.js`, an ES module with the data embedded (no
extra fetch):

```js
import { preloadNinekit, addNinekit } from './ui/ninekit-phaser.js';

class Menu extends Phaser.Scene {
  preload() { preloadNinekit(this); }            // one scale for every texture: pickScale(devicePixelRatio)
  create() {
    const panel = addNinekit(this, 200, 150, 'panel', 240, 90);          // x, y = centre of the logical box
    panel.ninekit.addContent(this.add.text(0, 0, 'Daily reward'));
    const play = addNinekit(this, 200, 260, 'btn_mint', 180, 59, { button: true });
    play.ninekit.contentRect();                   // where labels go (container-local)
    addNinekit(this, 200, 340, 'button_shade', 120, 40,
               { ramp: [[0, '#4A2306'], [0.45, '#C8761E'], [1, '#FFF1B8']] });
  }
}
```

* Units: dp = world units. Textures load at one scale (`preloadNinekit(scene, baseUrl, { scale })`, default
  the smallest scale ≥ `devicePixelRatio`) and are drawn at `1 / scale` as `nineslice` objects with
  texture-px slices.
* `addNinekit` returns a Container: one child per stacked output (`nineslice`, an Image for pieces drawn
  whole, Images + TileSprites for `tile` axes, since Phaser's NineSlice cannot tile), then a `content`
  container for labels. `container.ninekit` has `resize(w, h)`, `setPressed(on)` (face + content 0.92),
  `contentRect()`, `addContent(...)`, `layers`. `opts.button: true` wires pointer down/up/out to the press;
  `opts.ramp` recolours shade art through a cached CPU LUT.
* `fixed` axes keep the art's natural length, centred on the logical box.

Regenerate the demo: `demos/web/regenerate.sh`, then serve the folder and open `phaser.html`.
