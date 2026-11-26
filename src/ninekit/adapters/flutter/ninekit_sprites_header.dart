// The data half of ninekit's Flutter export. `ninekit export --target flutter` copies these declarations to
// the top of `ninekit_sprites.dart` and appends one class of constants per manifest. They depend on Flutter's
// painting types only: plain `Image.asset(img.asset, centerSlice: img.centerSlice, fit: BoxFit.fill)` works
// without the runtime (`ninekit.dart`, written with `--runtime`).
import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

/// How a piece's middle fills an axis: `stretch`ed, `tile`d in whole repeats, or `fixed` (the axis keeps its
/// natural length; the ninekit runtime draws the art at that length, centred on the box).
enum NineStretch { stretch, tile, fixed }

/// `color`: finished art. `shade`: greys (R = G = B = shade, A = coverage) that a runtime maps through a colour
/// ramp (`NineRamp` in ninekit.dart).
enum NineMode { color, shade }

/// One file of an image: its scale (texture px per dp) and exact texture px.
@immutable
class NineVariant {
  const NineVariant({required this.scale, required this.width, required this.height, this.slice});

  final double scale;
  final int width;
  final int height;

  /// The 9-slice borders in this file's texture px (authoritative); null = drawn whole.
  final EdgeInsets? slice;

  /// The stretchable middle in this file's texture px (what `Canvas.drawImageNine` takes).
  Rect? get center =>
      slice == null ? null : Rect.fromLTRB(slice!.left, slice!.top, width - slice!.right, height - slice!.bottom);
}

/// One output image of a piece (e.g. `frame`, `face`, or `main`).
@immutable
class NineImage {
  const NineImage({
    required this.piece,
    required this.output,
    required this.asset,
    required this.size,
    required this.variants,
    this.centerSlice,
  });

  final String piece;
  final String output;

  /// The main asset key; Flutter picks the `<s>x/` variant for the device pixel ratio.
  final String asset;

  /// The canvas in logical px (dp), overhang included.
  final Size size;

  /// For `Image(centerSlice:)`: logical units (Flutter multiplies it by the chosen variant's scale), inside
  /// every variant's stretchable middle, so the corners stay 1:1 whichever variant is chosen. Null = drawn whole.
  final Rect? centerSlice;

  /// Every exported file, by ascending scale.
  final List<NineVariant> variants;

  /// The variant at [scale], or null.
  NineVariant? variantAt(double scale) {
    for (final v in variants) {
      if ((v.scale - scale).abs() < 1e-6) return v;
    }
    return null;
  }

  /// The asset key of the file Flutter uses at [scale] (`assets/ui/2.0x/card.png`).
  String assetAt(double scale) {
    if ((scale - 1).abs() < 1e-6) return asset;
    final cut = asset.lastIndexOf('/');
    final dir = scale == scale.roundToDouble() ? '${scale.toInt()}.0x' : '${scale}x';
    return '${asset.substring(0, cut + 1)}$dir/${asset.substring(cut + 1)}';
  }
}

/// A piece: its images bottom to top and its layout data (all in logical px).
@immutable
class NineSprite {
  const NineSprite({
    required this.name,
    required this.size,
    required this.layers,
    this.slice,
    this.stretchX = NineStretch.stretch,
    this.stretchY = NineStretch.stretch,
    this.content = EdgeInsets.zero,
    this.overhang = EdgeInsets.zero,
    this.mode = NineMode.color,
    this.composite,
  });

  final String name;

  /// The canvas (art) size, overhang included.
  final Size size;

  /// The 9-slice borders in dp (from the largest scale); null = drawn whole.
  final EdgeInsets? slice;
  final NineStretch stretchX;
  final NineStretch stretchY;

  /// Insets for children, measured from the canvas edges (overhang included), like the slices.
  final EdgeInsets content;

  /// How far the art reaches outside the body (the logical box a widget lays out); the canvas is the body
  /// inflated by this.
  final EdgeInsets overhang;
  final NineMode mode;

  /// The outputs to stack, bottom to top.
  final List<NineImage> layers;

  /// A `main` image next to named outputs: their ready-made composite (an alternative to stacking them).
  final NineImage? composite;

  /// The body (layout) rect's natural size: the canvas minus the overhang.
  Size get bodySize => Size(size.width - overhang.horizontal, size.height - overhang.vertical);

  /// The child padding inside the body: [content] minus [overhang], per side, at least 0.
  EdgeInsets get childPadding => EdgeInsets.fromLTRB(
    _nonNegative(content.left - overhang.left),
    _nonNegative(content.top - overhang.top),
    _nonNegative(content.right - overhang.right),
    _nonNegative(content.bottom - overhang.bottom),
  );

  /// The smallest body that keeps the slices unshrunk (zero for pieces drawn whole); on a `fixed` axis the
  /// natural body length.
  /// A `fixed` axis: the natural body length.
  Size get minBodySize => slice == null
      ? Size.zero
      : Size(
          stretchX == NineStretch.fixed ? bodySize.width : _nonNegative(slice!.horizontal - overhang.horizontal),
          stretchY == NineStretch.fixed ? bodySize.height : _nonNegative(slice!.vertical - overhang.vertical),
        );

  /// The image of [output] (`frame`, `face`, `main`), or null.
  NineImage? operator [](String output) {
    for (final l in layers) {
      if (l.output == output) return l;
    }
    return composite?.output == output ? composite : null;
  }
}

double _nonNegative(double v) => v < 0 ? 0 : v;
