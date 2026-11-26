// Helpers for the demo's tests: real fonts, a view at a given pixel ratio, real image decoding and pixel
// readback (decoding and readback are real async work, so they run inside tester.runAsync).
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

/// Roboto from the Flutter SDK, so goldens show glyphs instead of the test font's boxes.
Future<void> loadFonts() async {
  final root = _flutterRoot();
  if (root == null) return;
  final loader = FontLoader('Roboto');
  for (final name in ['Regular', 'Medium', 'Bold', 'Black']) {
    final file = File('$root/bin/cache/artifacts/material_fonts/Roboto-$name.ttf');
    if (file.existsSync()) loader.addFont(Future.value(ByteData.sublistView(file.readAsBytesSync())));
  }
  await loader.load();
}

String? _flutterRoot() {
  final env = Platform.environment['FLUTTER_ROOT'];
  if (env != null && Directory(env).existsSync()) return env;
  var dir = File(Platform.resolvedExecutable).parent; // <root>/bin/cache/artifacts/engine/<platform>/
  while (dir.parent.path != dir.path) {
    if (File('${dir.path}/bin/flutter').existsSync()) return dir.path;
    dir = dir.parent;
  }
  return null;
}

/// A view of [logical] size at [dpr] physical pixels per logical pixel.
void setView(WidgetTester tester, double dpr, Size logical) {
  tester.view.devicePixelRatio = dpr;
  tester.view.physicalSize = logical * dpr;
  addTearDown(tester.view.reset);
}

/// Precaches with a context at the current pixel ratio (real async), then pumps [widget]: every image is
/// in the cache before the widgets ask for it, so the first frame is complete.
Future<void> pumpLoaded(WidgetTester tester, Widget widget, Future<void> Function(BuildContext) precache) async {
  await tester.pumpWidget(const SizedBox(key: ValueKey('precache-host')));
  final context = tester.element(find.byKey(const ValueKey('precache-host')));
  await tester.runAsync(() => precache(context));
  await tester.pumpWidget(widget);
  await tester.pump();
}

/// The repaint boundary at [finder] rendered at [dpr] (physical pixels).
Future<ui.Image> capture(WidgetTester tester, Finder finder, double dpr) async {
  final boundary = tester.renderObject<RenderRepaintBoundary>(finder);
  return (await tester.runAsync(() => boundary.toImage(pixelRatio: dpr)))!;
}

/// An image's pixels; premultiplied unless [straight].
class Pixels {
  Pixels(this.width, this.height, this.data);

  final int width;
  final int height;
  final Uint8List data;

  static Future<Pixels> of(WidgetTester tester, ui.Image image, {bool straight = false}) async {
    final bytes = await tester.runAsync(
      () => image.toByteData(format: straight ? ui.ImageByteFormat.rawStraightRgba : ui.ImageByteFormat.rawRgba),
    );
    return Pixels(image.width, image.height, bytes!.buffer.asUint8List());
  }

  /// A bundled asset file decoded as is (no resolution lookup).
  static Future<Pixels> asset(WidgetTester tester, String key, {bool straight = false}) async {
    final image = await tester.runAsync(() async {
      final data = await rootBundle.load(key);
      final codec = await ui.instantiateImageCodec(data.buffer.asUint8List());
      return (await codec.getNextFrame()).image;
    });
    return Pixels.of(tester, image!, straight: straight);
  }

  /// RGBA at (x, y).
  List<int> at(int x, int y) {
    final i = (y * width + x) * 4;
    return data.sublist(i, i + 4);
  }

  /// The largest channel difference between [w] x [h] texels at (x, y) here and at (ox, oy) in [other].
  int maxDiff(int x, int y, Pixels other, int ox, int oy, int w, int h) {
    var worst = 0;
    for (var j = 0; j < h; j++) {
      for (var i = 0; i < w; i++) {
        final a = at(x + i, y + j), b = other.at(ox + i, oy + j);
        for (var c = 0; c < 4; c++) {
          final d = (a[c] - b[c]).abs();
          if (d > worst) worst = d;
        }
      }
    }
    return worst;
  }
}
