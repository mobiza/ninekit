// ninekit's Flutter runtime, written by `ninekit export --target flutter --runtime` next to the generated
// `ninekit_sprites.dart` (which it re-exports). Widgets: NineSliceBox (a piece's outputs stacked behind a
// child), NineSliceButton (frame + face, the face sinks on press) and NineRamp (colours for `mode: shade` art).
import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/physics.dart';
import 'package:flutter/widgets.dart';

import 'ninekit_sprites.dart';

export 'ninekit_sprites.dart';

// --- painting ---------------------------------------------------------------------------------------------

/// Draws [image], a file at [scale] texture px per dp, 9-sliced into [dst] (logical px). [slice] is in the
/// file's texture px (null = drawn whole, scaled to [dst]).
///
/// The canvas is scaled by 1 / [scale], so corners map 1:1 to texels: pixel-exact when the device pixel
/// ratio equals [scale] and [dst] lies on whole physical pixels. A target smaller than the slices shrinks
/// them proportionally; a `tile` middle repeats a whole number of times, never a cut tile (like Godot's
/// TILE_FIT or CSS `round`): each repeat is stretched slightly to fit. A `fixed` axis is drawn like `stretch`:
/// the caller gives it its natural length ([NineSlicePainter.artRect]), so its one-step middle stays 1:1.
void paintNineImage(
  Canvas canvas,
  Rect dst,
  ui.Image image,
  double scale,
  EdgeInsets? slice, {
  NineStretch stretchX = NineStretch.stretch,
  NineStretch stretchY = NineStretch.stretch,
  Paint? paint,
}) {
  if (dst.isEmpty) return;
  final p = paint ?? (Paint()..filterQuality = FilterQuality.medium);
  final iw = image.width.toDouble(), ih = image.height.toDouble();
  final w = dst.width * scale, h = dst.height * scale;
  canvas.save();
  canvas.translate(dst.left, dst.top);
  canvas.scale(1 / scale);
  if (slice == null) {
    canvas.drawImageRect(image, Rect.fromLTWH(0, 0, iw, ih), Rect.fromLTWH(0, 0, w, h), p);
  } else if (stretchX != NineStretch.tile &&
      stretchY != NineStretch.tile &&
      w >= slice.horizontal &&
      h >= slice.vertical) {
    final center = Rect.fromLTRB(slice.left, slice.top, iw - slice.right, ih - slice.bottom);
    canvas.drawImageNine(image, center, Rect.fromLTWH(0, 0, w, h), p);
  } else {
    // separate quads: no anti-aliasing, or the shared edges of neighbouring quads (repeats end at
    // fractional px) would each be half covered and let the background show through as seams
    final q = Paint()
      ..filterQuality = p.filterQuality
      ..color = p.color
      ..colorFilter = p.colorFilter
      ..blendMode = p.blendMode
      ..isAntiAlias = false;
    final xs = _segments(iw, slice.left, slice.right, w, stretchX == NineStretch.tile);
    final ys = _segments(ih, slice.top, slice.bottom, h, stretchY == NineStretch.tile);
    for (final y in ys) {
      for (final x in xs) {
        canvas.drawImageRect(image, Rect.fromLTRB(x.s0, y.s0, x.s1, y.s1), Rect.fromLTRB(x.d0, y.d0, x.d1, y.d1), q);
      }
    }
  }
  canvas.restore();
}

/// One run along an axis: source texels [s0, s1) drawn to [d0, d1) (both in texture px).
class _Seg {
  const _Seg(this.s0, this.s1, this.d0, this.d1);
  final double s0, s1, d0, d1;
}

List<_Seg> _segments(double size, double a, double b, double dst, bool tile) {
  final fixed = a + b;
  if (dst <= fixed) {
    final k = fixed > 0 ? dst / fixed : 0.0;
    return [if (a > 0) _Seg(0, a, 0, a * k), if (b > 0) _Seg(size - b, size, a * k, dst)];
  }
  final mid = size - fixed, dmid = dst - fixed;
  final out = <_Seg>[if (a > 0) _Seg(0, a, 0, a)];
  if (mid > 0) {
    final n = tile ? math.max(1, (dmid / mid).round()) : 1;
    for (var i = 0; i < n; i++) {
      out.add(_Seg(a, size - b, a + dmid * i / n, a + dmid * (i + 1) / n));
    }
  }
  if (b > 0) out.add(_Seg(size - b, size, dst - b, dst));
  return out;
}

/// The texture-px slices of [img] as a file of [image] at [scale]: the exported variant's own slices, or,
/// for a file the export does not know (e.g. left over), the logical centerSlice scaled to it.
EdgeInsets? _sliceOf(NineImage image, double scale, ui.Image img) {
  final v = image.variantAt(scale);
  if (v != null && v.width == img.width && v.height == img.height) return v.slice;
  final c = image.centerSlice;
  if (c == null) return null;
  return EdgeInsets.fromLTRB(
    (c.left * scale).roundToDouble(),
    (c.top * scale).roundToDouble(),
    img.width - (c.right * scale).roundToDouble(),
    img.height - (c.bottom * scale).roundToDouble(),
  );
}

// --- shade ramps ------------------------------------------------------------------------------------------

/// A colour ramp for `mode: shade` art: shade t (0..1, the art's red channel) -> colour; the art's alpha
/// multiplies the colour's.
///
/// Applied by baking: the chosen variant is read back once, mapped through a 256-entry table and uploaded as
/// a new image, cached per (asset, scale, ramp). That is exact for any number of stops and identical on Skia,
/// Impeller, web and in `flutter test` goldens. A `ColorFilter.matrix` is linear (two stops at most), a
/// `ShaderMask` maps by position rather than by value, and a fragment shader would have to redo the 9-slice
/// geometry itself (post-processing a layer with a shader is Impeller-only).
@immutable
class NineRamp {
  const NineRamp(this.stops);

  /// [colors] spread evenly from shade 0 to shade 1.
  NineRamp.even(List<Color> colors)
    : stops = [for (var i = 0; i < colors.length; i++) (colors.length == 1 ? 0.0 : i / (colors.length - 1), colors[i])];

  /// (t, colour) pairs, ascending t in 0..1.
  final List<(double, Color)> stops;

  /// The colour at shade [t] (linear per channel between stops, clamped outside).
  Color at(double t) {
    if (stops.isEmpty) return const Color(0x00000000);
    if (t <= stops.first.$1) return stops.first.$2;
    for (var i = 1; i < stops.length; i++) {
      final (t1, c1) = stops[i];
      if (t <= t1) {
        final (t0, c0) = stops[i - 1];
        return Color.lerp(c0, c1, t1 > t0 ? (t - t0) / (t1 - t0) : 1)!;
      }
    }
    return stops.last.$2;
  }

  /// 256 straight RGBA entries, index = shade byte.
  Uint8List lut() {
    final out = Uint8List(256 * 4);
    for (var i = 0; i < 256; i++) {
      final c = at(i / 255);
      out[i * 4] = (c.r * 255).round();
      out[i * 4 + 1] = (c.g * 255).round();
      out[i * 4 + 2] = (c.b * 255).round();
      out[i * 4 + 3] = (c.a * 255).round();
    }
    return out;
  }

  @override
  bool operator ==(Object other) => other is NineRamp && listEquals(other.stops, stops);

  @override
  int get hashCode => Object.hashAll(stops);
}

/// [src] (shade art) mapped through [ramp]: a new image of the same size.
Future<ui.Image> bakeShadeRamp(ui.Image src, NineRamp ramp) async {
  final data = await src.toByteData(format: ui.ImageByteFormat.rawStraightRgba);
  final px = data!.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  final lut = ramp.lut();
  final out = Uint8List(px.length);
  for (var i = 0; i < px.length; i += 4) {
    final a0 = px[i + 3];
    if (a0 == 0) continue;
    final j = px[i] * 4;
    final a = a0 * lut[j + 3]; // alpha x 255
    // decodeImageFromPixels takes premultiplied rgba8888
    out[i] = (lut[j] * a + 32512) ~/ 65025;
    out[i + 1] = (lut[j + 1] * a + 32512) ~/ 65025;
    out[i + 2] = (lut[j + 2] * a + 32512) ~/ 65025;
    out[i + 3] = (a + 127) ~/ 255;
  }
  final done = Completer<ui.Image>();
  ui.decodeImageFromPixels(out, src.width, src.height, ui.PixelFormat.rgba8888, done.complete);
  return done.future;
}

class _Baked {
  _Baked(this.future) {
    future.then((img) => image = img, onError: (Object _) {});
  }
  final Future<ui.Image> future;
  ui.Image? image;
}

/// Baked ramps, most recently used last. Evicted images are not disposed: a widget may still be painting them.
final LinkedHashMap<(String, double, NineRamp), _Baked> _bakes = LinkedHashMap();
const int _maxBakes = 128;

_Baked _bake(String asset, double scale, ui.Image src, NineRamp ramp) {
  final key = (asset, scale, ramp);
  final hit = _bakes.remove(key);
  if (hit != null) return _bakes[key] = hit;
  final copy = src.clone();
  final baked = _Baked(bakeShadeRamp(copy, ramp).whenComplete(copy.dispose));
  _bakes[key] = baked;
  if (_bakes.length > _maxBakes) _bakes.remove(_bakes.keys.first);
  return baked;
}

// --- loading ----------------------------------------------------------------------------------------------

/// Loads [sprite]'s images for [context]'s device pixel ratio into the image cache (and bakes [ramp]), so a
/// NineSliceBox built afterwards paints on its first frame.
Future<void> precacheNineSprite(
  BuildContext context,
  NineSprite sprite, {
  NineRamp? ramp,
  bool composite = false,
  AssetBundle? bundle,
  String? package,
}) {
  final config = createLocalImageConfiguration(context);
  final images = composite && sprite.composite != null ? [sprite.composite!] : sprite.layers;
  return Future.wait([
    for (final img in images) _load(img, AssetImage(img.asset, bundle: bundle, package: package), config, ramp),
  ]);
}

Future<void> _load(NineImage img, ImageProvider provider, ImageConfiguration config, NineRamp? ramp) async {
  final got = Completer<ImageInfo>();
  final stream = provider.resolve(config);
  final listener = ImageStreamListener(
    (info, _) => got.isCompleted ? info.dispose() : got.complete(info),
    onError: (Object e, StackTrace? s) => got.isCompleted ? null : got.completeError(e, s),
  );
  stream.addListener(listener);
  try {
    final info = await got.future;
    if (ramp != null) await _bake(img.asset, info.scale, info.image, ramp).future;
    info.dispose();
  } finally {
    stream.removeListener(listener);
  }
}

/// One image of a box: its stream, the resolved file and, for a ramp, the baked copy.
class _Layer {
  _Layer(this.image, this.stream, this.ramp, this.onChange) {
    _listener = ImageStreamListener(_onImage, onError: _onError);
    stream.addListener(_listener);
  }

  final NineImage image;
  final ImageStream stream;
  final NineRamp? ramp;
  final VoidCallback onChange;
  late final ImageStreamListener _listener;
  ImageInfo? info;
  ui.Image? _shaded;
  bool _disposed = false;

  /// What to draw: the file, or its ramp bake once ready.
  ui.Image? get drawable => ramp == null ? info?.image : _shaded;

  void _onImage(ImageInfo next, bool sync) {
    info?.dispose();
    info = next;
    _shaded = null;
    if (ramp != null) {
      final baked = _bake(image.asset, next.scale, next.image, ramp!);
      _shaded = baked.image;
      if (_shaded == null) {
        baked.future.then((img) {
          if (!_disposed && identical(info, next)) {
            _shaded = img;
            onChange();
          }
        }, onError: (Object _) {});
      }
    }
    onChange();
  }

  void _onError(Object error, StackTrace? stack) {
    FlutterError.reportError(
      FlutterErrorDetails(
        exception: error,
        stack: stack,
        library: 'ninekit',
        context: ErrorDescription('loading ${image.asset}'),
      ),
    );
  }

  void dispose() {
    _disposed = true;
    stream.removeListener(_listener);
    info?.dispose();
    info = null;
  }
}

// --- NineSliceBox -----------------------------------------------------------------------------------------

/// Draws a piece's outputs, stacked bottom to top, behind [child].
///
/// The box's own rect is the piece's body (the canvas minus [NineSprite.overhang]); the art reaches the
/// overhang outside it (painted, not laid out). [child] is padded by [NineSprite.childPadding] (the content
/// insets, which are measured from the canvas edges, minus the overhang). Size: [width] / [height] when
/// given, else the child plus its padding (at least the slices), else the piece's natural body size; a
/// piece drawn whole keeps its natural size. On a `fixed` axis the art keeps its natural length, centred on
/// the box, whatever length the box gets (the child still lays out in the box).
///
/// Each image comes from Flutter's resolution-aware lookup and is drawn with the chosen file's own slices,
/// so the logical size is the same at every device pixel ratio and corners stay 1:1 with the texels.
class NineSliceBox extends StatefulWidget {
  const NineSliceBox({
    super.key,
    required this.sprite,
    this.width,
    this.height,
    this.child,
    this.outputs,
    this.composite = false,
    this.ramp,
    this.filterQuality = FilterQuality.medium,
    this.bundle,
    this.package,
  });

  final NineSprite sprite;
  final double? width;
  final double? height;
  final Widget? child;

  /// The outputs to draw, bottom to top (default: [NineSprite.layers]).
  final List<String>? outputs;

  /// Draw the piece's ready-made composite (`main` next to named outputs) instead of its layers.
  final bool composite;

  /// The colours for `mode: shade` art (ignored when null).
  final NineRamp? ramp;
  final FilterQuality filterQuality;
  final AssetBundle? bundle;
  final String? package;

  /// The images this box draws, bottom to top.
  List<NineImage> get images {
    if (composite && sprite.composite != null) return [sprite.composite!];
    final outs = outputs;
    if (outs == null) return sprite.layers;
    return [
      for (final o in outs) sprite[o] ?? (throw ArgumentError.value(o, 'outputs', '${sprite.name} has no such output')),
    ];
  }

  @override
  State<NineSliceBox> createState() => NineSliceBoxState();
}

class NineSliceBoxState extends State<NineSliceBox> {
  List<_Layer> _layers = const [];

  /// The resolved file per image (null until loaded): `debugLabel` is its asset key, `scale` its scale.
  @visibleForTesting
  List<ImageInfo?> get debugInfos => [for (final l in _layers) l.info];

  /// Whether every image (and ramp bake) is ready to paint.
  bool get isReady => _layers.every((l) => l.drawable != null);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _resolve();
  }

  @override
  void didUpdateWidget(NineSliceBox oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(oldWidget.images, widget.images) ||
        oldWidget.ramp != widget.ramp ||
        oldWidget.bundle != widget.bundle ||
        oldWidget.package != widget.package) {
      _resolve();
    }
  }

  void _resolve() {
    final config = createLocalImageConfiguration(context);
    final images = widget.images;
    final next = <_Layer>[];
    final keep = <_Layer>{};
    for (var i = 0; i < images.length; i++) {
      final provider = AssetImage(images[i].asset, bundle: widget.bundle, package: widget.package);
      final stream = provider.resolve(config);
      final old = i < _layers.length ? _layers[i] : null;
      if (old != null && old.image == images[i] && old.ramp == widget.ramp && old.stream.key == stream.key) {
        next.add(old);
        keep.add(old);
      } else {
        next.add(_Layer(images[i], stream, widget.ramp, _changed));
      }
    }
    for (final l in _layers) {
      if (!keep.contains(l)) l.dispose();
    }
    _layers = next;
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    for (final l in _layers) {
      l.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.sprite;
    final painter = NineSlicePainter(
      sprite: s,
      frames: [
        for (final l in _layers)
          if (l.drawable != null && l.info != null) (l.image, l.drawable!, l.info!.scale),
      ],
      filterQuality: widget.filterQuality,
      devicePixelRatio: MediaQuery.maybeDevicePixelRatioOf(context) ?? 1.0,
    );
    final child = widget.child;
    // a piece drawn whole keeps its own size; a sliced one may follow its child
    final ownSize = child == null || s.slice == null;
    final width = widget.width ?? (ownSize ? s.bodySize.width : null);
    final height = widget.height ?? (ownSize ? s.bodySize.height : null);
    Widget? content = child == null ? null : Padding(padding: s.childPadding, child: child);
    if (content != null && (width == null || height == null)) {
      // sized by the child: a child smaller than the slices' minimum sits in the middle
      content = Align(widthFactor: width == null ? 1 : null, heightFactor: height == null ? 1 : null, child: content);
    }
    final box = SizedBox(
      width: width,
      height: height,
      child: CustomPaint(painter: painter, child: content),
    );
    if (width != null && height != null) return box;
    final min = s.minBodySize;
    return ConstrainedBox(
      constraints: BoxConstraints(minWidth: width == null ? min.width : 0, minHeight: height == null ? min.height : 0),
      child: box,
    );
  }
}

/// Paints resolved images of [sprite] into the body rect inflated by the overhang.
///
/// With a [devicePixelRatio], that rect is snapped to whole physical pixels (the layout keeps its logical
/// size): a box at a fractional position or of a fractional size still gets corners on the pixel grid.
class NineSlicePainter extends CustomPainter {
  NineSlicePainter({
    required this.sprite,
    required this.frames,
    this.filterQuality = FilterQuality.medium,
    this.devicePixelRatio,
  });

  final NineSprite sprite;

  /// (image, its file, the file's scale), bottom to top.
  final List<(NineImage, ui.Image, double)> frames;
  final FilterQuality filterQuality;

  /// Physical pixels per logical pixel; null = no snapping.
  final double? devicePixelRatio;

  @override
  void paint(Canvas canvas, Size size) {
    final dst = artRect(sprite, size, canvas: canvas, devicePixelRatio: devicePixelRatio);
    final paint = Paint()..filterQuality = filterQuality;
    for (final (image, img, scale) in frames) {
      paintNineImage(
        canvas,
        dst,
        img,
        scale,
        _sliceOf(image, scale, img),
        stretchX: sprite.stretchX,
        stretchY: sprite.stretchY,
        paint: paint,
      );
    }
  }

  /// Where [sprite]'s art goes for a body of [size]: the body inflated by the overhang; on a `fixed` axis the
  /// art keeps its natural length, centred on the body. With a [canvas] and [devicePixelRatio], the edges
  /// move to the nearest physical pixel (a fixed axis keeps its length: only its start moves). Snapping uses
  /// the canvas's own transform (offsets inside this layer; layers sit at whole logical pixels in practice)
  /// and is skipped under rotation or skew.
  static Rect artRect(NineSprite sprite, Size size, {Canvas? canvas, double? devicePixelRatio}) {
    final o = sprite.overhang, body = sprite.bodySize;
    final fx = sprite.stretchX == NineStretch.fixed, fy = sprite.stretchY == NineStretch.fixed;
    final bx = fx ? (size.width - body.width) / 2 : 0.0, by = fy ? (size.height - body.height) / 2 : 0.0;
    var r = Rect.fromLTRB(
      bx - o.left,
      by - o.top,
      (fx ? bx + body.width : size.width) + o.right,
      (fy ? by + body.height : size.height) + o.bottom,
    );
    if (canvas == null || devicePixelRatio == null) return r;
    final m = canvas.getTransform();
    if (m[1] != 0 || m[4] != 0 || m[0] == 0 || m[5] == 0) return r;
    final sx = m[0] * devicePixelRatio, sy = m[5] * devicePixelRatio;
    final tx = m[12] * devicePixelRatio, ty = m[13] * devicePixelRatio;
    double x(double v) => ((v * sx + tx).roundToDouble() - tx) / sx;
    double y(double v) => ((v * sy + ty).roundToDouble() - ty) / sy;
    final left = x(r.left), top = y(r.top);
    r = Rect.fromLTRB(left, top, fx ? left + r.width : x(r.right), fy ? top + r.height : y(r.bottom));
    return r;
  }

  @override
  bool shouldRepaint(NineSlicePainter old) =>
      old.sprite != sprite ||
      old.filterQuality != filterQuality ||
      old.devicePixelRatio != devicePixelRatio ||
      !listEquals(old.frames, frames);
}

// --- NineSliceButton --------------------------------------------------------------------------------------

/// A button from a frame/face piece: the face output (and [child]) sit over the other outputs and, on press,
/// scale toward the body's centre to [pressedScale], then spring back on release.
///
/// Its height defaults to the piece's own body height (its width follows [width] or the child). Without a
/// [face] output among several, or for a one-image piece, the whole piece presses.
class NineSliceButton extends StatefulWidget {
  const NineSliceButton({
    super.key,
    required this.sprite,
    required this.onPressed,
    this.width,
    this.height,
    this.child,
    this.face = 'face',
    this.pressedScale = 0.92,
    this.ramp,
    this.bundle,
    this.package,
  });

  final NineSprite sprite;

  /// Null disables the button (no press).
  final VoidCallback? onPressed;
  final double? width;
  final double? height;
  final Widget? child;

  /// The output that sinks.
  final String face;
  final double pressedScale;
  final NineRamp? ramp;
  final AssetBundle? bundle;
  final String? package;

  @override
  State<NineSliceButton> createState() => NineSliceButtonState();
}

class NineSliceButtonState extends State<NineSliceButton> with SingleTickerProviderStateMixin {
  /// 0 = up, 1 = fully pressed; the release spring overshoots a little past 0.
  late final AnimationController _press = AnimationController.unbounded(vsync: this);
  static final SpringDescription _spring = SpringDescription.withDampingRatio(mass: 1, stiffness: 600, ratio: 0.5);
  static const Duration _downTime = Duration(milliseconds: 70);
  int _gesture = 0;

  /// The face's current scale (1 = up).
  double get faceScale => 1 - (1 - widget.pressedScale) * _press.value;

  bool get _enabled => widget.onPressed != null;

  void _down() {
    _gesture++;
    _press.animateTo(1, duration: _downTime, curve: Curves.easeOut);
  }

  void _up() {
    final g = _gesture;
    void spring() {
      if (mounted && g == _gesture) _press.animateWith(SpringSimulation(_spring, _press.value, 0, 0));
    }

    if (_press.isAnimating && _press.value < 1) {
      // a quick tap still reaches the bottom before springing back
      final left = _downTime * (1 - _press.value).clamp(0.0, 1.0);
      _press.animateTo(1, duration: left, curve: Curves.easeOut).whenCompleteOrCancel(spring);
    } else {
      spring();
    }
  }

  @override
  void dispose() {
    _press.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.sprite;
    final sinks = s.layers.length > 1 && s.layers.any((l) => l.output == widget.face);
    final back = sinks
        ? [
            for (final l in s.layers)
              if (l.output != widget.face) l.output,
          ]
        : const <String>[];
    final front = sinks ? [widget.face] : [for (final l in s.layers) l.output];
    final face = AnimatedBuilder(
      animation: _press,
      builder: (context, child) => Transform.scale(scale: faceScale, child: child),
      child: NineSliceBox(
        sprite: s,
        outputs: front,
        width: widget.width,
        height: widget.height ?? s.bodySize.height,
        ramp: widget.ramp,
        bundle: widget.bundle,
        package: widget.package,
        child: widget.child,
      ),
    );
    return Semantics(
      button: true,
      enabled: _enabled,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: _enabled ? (_) => _down() : null,
        onTapUp: _enabled ? (_) => _up() : null,
        onTapCancel: _enabled ? _up : null,
        onTap: widget.onPressed,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            if (back.isNotEmpty)
              Positioned.fill(
                child: NineSliceBox(
                  sprite: s,
                  outputs: back,
                  ramp: widget.ramp,
                  bundle: widget.bundle,
                  package: widget.package,
                ),
              ),
            face,
          ],
        ),
      ),
    );
  }
}
