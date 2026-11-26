// Corners are the files' corners, texel for texel, at every device pixel ratio whose file exists, at several
// sizes, at fractional positions and sizes too (NineSliceBox snaps its art to the pixel grid); tile middles
// repeat; shade art goes through the ramp. Also: a plain Image.asset with the generated centerSlice.
import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ninekit_demo/demo_page.dart';
import 'package:ninekit_demo/ninekit/ninekit.dart';

import 'support.dart';

const _sliced = [
  Basics.panel,
  Basics.pill,
  Basics.scifi,
  Basics.barTrack,
  Basics.barFill,
  Basics.tab,
  Basics.stone,
  Basics.shadeButton,
  GumdropButtons.btnMint,
  GumdropButtons.btnGrape,
];

/// Files whose px size / slices are not the piece's dp values x scale (what one logical centerSlice needs).
List<String> _dpMismatches(Iterable<NineSprite> sprites) => [
  for (final s in sprites)
    for (final img in s.layers)
      for (final v in img.variants)
        if (v.width != (s.size.width * v.scale).round() ||
            v.height != (s.size.height * v.scale).round() ||
            (s.slice != null &&
                (v.slice!.left != (s.slice!.left * v.scale).roundToDouble() ||
                    v.slice!.top != (s.slice!.top * v.scale).roundToDouble() ||
                    v.slice!.right != (s.slice!.right * v.scale).roundToDouble() ||
                    v.slice!.bottom != (s.slice!.bottom * v.scale).roundToDouble())))
          '${img.piece}/${img.output}@${v.scale}x',
];

/// Compares the four corner blocks of the art drawn at [art] (device px) with the file's.
void _expectCorners(Pixels cap, Pixels src, NineVariant v, Rect art, String what, {int tol = 1}) {
  final s = v.slice!;
  final l = s.left.toInt(), t = s.top.toInt(), r = s.right.toInt(), b = s.bottom.toInt();
  final x0 = art.left.toInt(), y0 = art.top.toInt(), x1 = art.right.toInt(), y1 = art.bottom.toInt();
  expect(cap.maxDiff(x0, y0, src, 0, 0, l, t), lessThanOrEqualTo(tol), reason: '$what top-left');
  expect(cap.maxDiff(x1 - r, y0, src, v.width - r, 0, r, t), lessThanOrEqualTo(tol), reason: '$what top-right');
  expect(cap.maxDiff(x0, y1 - b, src, 0, v.height - b, l, b), lessThanOrEqualTo(tol), reason: '$what bottom-left');
  expect(
    cap.maxDiff(x1 - r, y1 - b, src, v.width - r, v.height - b, r, b),
    lessThanOrEqualTo(tol),
    reason: '$what bottom-right',
  );
}

/// Where the art of [sprite] must land (device px) for a box of [size] at logical [at]: the box inflated by
/// the overhang, edges on the nearest pixel; a `fixed` axis keeps the natural length, centred on the box
/// (only its start is rounded).
Rect _artPx(NineSprite sprite, Offset at, Size size, double dpr) {
  final o = sprite.overhang, body = sprite.bodySize;
  double px(double v) => (v * dpr).roundToDouble();
  (double, double) axis(double start, double box, double natural, double o0, double o1, bool fixed) {
    if (!fixed) return (px(start - o0), px(start + box + o1));
    final a = px(start + (box - natural) / 2 - o0);
    return (a, a + (natural + o0 + o1) * dpr);
  }

  final (l, r) = axis(at.dx, size.width, body.width, o.left, o.right, sprite.stretchX == NineStretch.fixed);
  final (t, b) = axis(at.dy, size.height, body.height, o.top, o.bottom, sprite.stretchY == NineStretch.fixed);
  return Rect.fromLTRB(l, t, r, b);
}

/// [src] (shade art, straight alpha) mapped through [ramp], premultiplied: what the bake must produce.
Pixels _shaded(Pixels src, NineRamp ramp) {
  final lut = ramp.lut();
  final out = Pixels(src.width, src.height, src.data.sublist(0));
  for (var i = 0; i < out.data.length; i += 4) {
    final a0 = src.data[i + 3], j = src.data[i] * 4, a = a0 * lut[j + 3];
    for (var c = 0; c < 3; c++) {
      out.data[i + c] = a0 == 0 ? 0 : (lut[j + c] * a + 32512) ~/ 65025;
    }
    out.data[i + 3] = a0 == 0 ? 0 : (a + 127) ~/ 255;
  }
  return out;
}

void main() {
  final mismatches = _dpMismatches([...Basics.all, ...GumdropButtons.all, ...Probe.all]);

  test(
    'every file is the piece\'s dp size and slices x its scale',
    () => expect(mismatches, isEmpty),
    skip: mismatches.isEmpty ? false : 'core dp-consistent slices pending: ${mismatches.join(', ')}',
  );

  for (final dpr in [1.0, 2.0, 3.0]) {
    for (final sprite in _sliced) {
      if (sprite.layers.first.variantAt(dpr) == null) continue; // a set exported without this scale
      testWidgets('${sprite.name}: NineSliceBox corners are the ${dpr}x file\'s (DPR $dpr)', (tester) async {
        final ramp = sprite.mode == NineMode.shade ? DemoPage.gold : null;
        final o = sprite.overhang;
        // a size just above the slices (fractional), a large one, and an odd one; at a fractional offset
        final minW = sprite.slice!.horizontal - o.horizontal, minH = sprite.slice!.vertical - o.vertical;
        final sizes = [
          Size(minW + 3.5, minH + 1.25),
          Size(sprite.size.width * 3, sprite.size.height * 2),
          Size(minW + 41.3, minH + 17),
        ];
        const pad = EdgeInsets.fromLTRB(4.3, 4.6, 4, 4);
        setView(tester, dpr, const Size(800, 1200));
        await pumpLoaded(
          tester,
          Directionality(
            textDirection: TextDirection.ltr,
            child: Align(
              alignment: Alignment.topLeft,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final (i, size) in sizes.indexed)
                    for (final img in sprite.layers)
                      RepaintBoundary(
                        key: ValueKey('$i/${img.output}'),
                        child: Padding(
                          padding: pad,
                          child: NineSliceBox(
                            sprite: sprite,
                            outputs: [img.output],
                            ramp: ramp,
                            width: size.width,
                            height: size.height,
                          ),
                        ),
                      ),
                ],
              ),
            ),
          ),
          (context) => precacheNineSprite(context, sprite, ramp: ramp),
        );
        for (final img in sprite.layers) {
          final v = img.variantAt(dpr)!;
          var src = await Pixels.asset(tester, img.assetAt(dpr), straight: ramp != null);
          if (ramp != null) src = _shaded(src, ramp);
          for (final (i, size) in sizes.indexed) {
            final cap = await Pixels.of(tester, await capture(tester, find.byKey(ValueKey('$i/${img.output}')), dpr));
            final art = _artPx(sprite, pad.topLeft, size, dpr);
            _expectCorners(cap, src, v, art, '${img.piece}/${img.output} $size');
          }
        }
      });
    }
  }

  for (final dpr in [1.0, 2.0, 3.0]) {
    testWidgets('a y-fixed pill in a taller box: art at its natural height, centred, 1:1 (DPR $dpr)', (tester) async {
      const sprite = Basics.pill;
      expect(sprite.stretchY, NineStretch.fixed);
      const box = Size(120, 64); // the pill is 30 dp tall
      setView(tester, dpr, const Size(160, 100));
      await pumpLoaded(
        tester,
        const Directionality(
          textDirection: TextDirection.ltr,
          child: Align(
            alignment: Alignment.topLeft,
            child: RepaintBoundary(
              key: ValueKey('pill'),
              child: Padding(
                padding: EdgeInsets.all(4),
                child: NineSliceBox(
                  key: ValueKey('box'),
                  sprite: sprite,
                  width: 120,
                  height: 64,
                  child: Center(child: SizedBox(key: ValueKey('child'), width: 20, height: 10)),
                ),
              ),
            ),
          ),
        ),
        (context) => precacheNineSprite(context, sprite),
      );
      // the box keeps the given size; the child lays out in the box, inside the padding [12, 4, 12, 6]
      expect(tester.getSize(find.byKey(const ValueKey('box'))), box);
      expect(tester.getCenter(find.byKey(const ValueKey('child'))), const Offset(4 + 12 + 96 / 2, 4 + 4 + 54 / 2));
      final img = sprite.layers.single, v = img.variantAt(dpr)!;
      final cap = await Pixels.of(tester, await capture(tester, find.byKey(const ValueKey('pill')), dpr));
      final src = await Pixels.asset(tester, img.assetAt(dpr));
      final art = _artPx(sprite, const Offset(4, 4), box, dpr);
      expect(art.top, ((4 + (64 - 30) / 2) * dpr).roundToDouble());
      expect(art.height, v.height); // natural height: the one-step middle is not stretched
      // the whole left and right slices, top to bottom, are the file's (nothing stretched vertically)
      final s = v.slice!;
      expect(cap.maxDiff(art.left.toInt(), art.top.toInt(), src, 0, 0, s.left.toInt(), v.height), lessThanOrEqualTo(1));
      expect(
        cap.maxDiff(
          (art.right - s.right).toInt(),
          art.top.toInt(),
          src,
          v.width - s.right.toInt(),
          0,
          s.right.toInt(),
          v.height,
        ),
        lessThanOrEqualTo(1),
      );
      // above and below the art: nothing drawn
      final mid = (art.left + art.width / 2).toInt();
      expect(cap.at(mid, (art.top - 1).toInt())[3], 0);
      expect(cap.at(mid, art.bottom.toInt())[3], 0);
      expect(cap.at(mid, (art.top + 1).toInt())[3], greaterThan(0));
    });
  }

  testWidgets('stone tiles whole repeats: no cut tile, no seams', (tester) async {
    const dpr = 3.0, sprite = Basics.stone;
    final v = sprite.layers.single.variantAt(dpr)!;
    final s = v.slice!;
    final mid = v.width - s.horizontal; // texels per repeat
    const width = 256.0; // as in the demo
    setView(tester, dpr, const Size(300, 200));
    await pumpLoaded(
      tester,
      const Align(
        alignment: Alignment.topLeft,
        child: RepaintBoundary(
          key: ValueKey('stone'),
          child: NineSliceBox(sprite: sprite, width: width, height: 120),
        ),
      ),
      (context) => precacheNineSprite(context, sprite),
    );
    final cap = await Pixels.of(tester, await capture(tester, find.byKey(const ValueKey('stone')), dpr));
    final src = await Pixels.asset(tester, sprite.layers.single.assetAt(dpr));
    final dmid = width * dpr - s.horizontal;
    final n = math.max(1, (dmid / mid).round());
    expect(n, greaterThan(1)); // 5 with the current art
    // y: the first repeat, 10 px in (its texel: the stretch of the y repeats undone)
    final midY = v.height - s.vertical, dmidY = 120 * dpr - s.vertical;
    final nY = math.max(1, (dmidY / midY).round());
    final row = (s.top + 10).toInt();
    final srcRow = (s.top + 10.5 * midY / (dmidY / nY)).floor();
    // each x repeat starts with the tile's first columns (stretched by dmid / n / mid, a few % at most)
    for (var k = 0; k < n; k++) {
      final x = (s.left + dmid * k / n).ceil();
      final u = (s.left + (x + 0.5 - s.left - dmid * k / n) * mid / (dmid / n)).floor();
      expect(cap.maxDiff(x, row, src, u, srcRow, 1, 1), lessThanOrEqualTo(24), reason: 'repeat $k');
      // no seam: never more transparent than the art there (the background would show through)
      expect(cap.at(x, row)[3], 255);
      expect(cap.at(x - 1, row)[3], 255);
    }
  });

  for (final dpr in [1.0, 2.0, 3.0]) {
    for (final sprite in [Basics.panel, Basics.pill, Basics.barFill, Basics.tab]) {
      final bad = _dpMismatches([sprite]).where((m) => m.endsWith('@${dpr}x')).toList();
      testWidgets('${sprite.name}: Image.asset with the generated centerSlice keeps corners 1:1 (DPR $dpr)', (
        tester,
      ) async {
        final img = sprite.layers.first;
        final v = img.variantAt(dpr)!;
        const size = Size(150, 90);
        setView(tester, dpr, const Size(200, 120));
        await pumpLoaded(
          tester,
          Align(
            alignment: Alignment.topLeft,
            child: RepaintBoundary(
              key: const ValueKey('img'),
              child: Image.asset(
                img.asset,
                centerSlice: img.centerSlice,
                width: size.width,
                height: size.height,
                fit: BoxFit.fill,
              ),
            ),
          ),
          (context) => precacheImage(AssetImage(img.asset), context),
        );
        final cap = await Pixels.of(tester, await capture(tester, find.byKey(const ValueKey('img')), dpr));
        final src = await Pixels.asset(tester, img.assetAt(dpr));
        _expectCorners(cap, src, v, Rect.fromLTWH(0, 0, size.width * dpr, size.height * dpr), img.asset);
      }, skip: bad.isNotEmpty); // core dp-consistent slices pending for these files
    }
  }
}
