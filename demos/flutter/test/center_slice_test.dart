// Settles the units of Flutter's `centerSlice` with a resolution-aware asset, by counting texels.
//
// The probe is 12 x 12 dp with 4 dp red corners (a white 1 dp dot at (1, 1) inside each), green edges and a
// blue middle; probe.png is 12 x 12 px (1x), 3.0x/probe.png 36 x 36 px. Drawn 40 x 40 dp with
// centerSlice Rect.fromLTRB(4, 4, 8, 8):
//  * logical units (Flutter scales the rect by the chosen file's scale): corners are 4 dp at every ratio,
//    i.e. 12 physical px at DPR 3 (the 3x file's 12 px corner, 1:1);
//  * if it were the chosen file's px, the 3x file's corner would be 4 px = 4 physical px at DPR 3.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ninekit_demo/ninekit/ninekit.dart';

import 'support.dart';

const _red = [0xFF, 0x20, 0x20, 0xFF];
const _green = [0x20, 0xC0, 0x40, 0xFF];
const _blue = [0x20, 0x40, 0xFF, 0xFF];
const _white = [0xFF, 0xFF, 0xFF, 0xFF];

bool _near(List<int> a, List<int> b, [int tol = 2]) =>
    List.generate(4, (i) => (a[i] - b[i]).abs() <= tol).every((ok) => ok);

void main() {
  test('the exporter wrote the probe centerSlice in logical px', () {
    expect(Probe.probeMain.centerSlice, const Rect.fromLTRB(4, 4, 8, 8));
    expect(Probe.probeMain.variants.map((v) => (v.scale, v.width, v.slice)), [
      (1.0, 12, const EdgeInsets.all(4)),
      (3.0, 36, const EdgeInsets.all(12)),
    ]);
  });

  for (final dpr in [1.0, 2.0, 3.0]) {
    testWidgets('Image.asset centerSlice is in logical px (DPR $dpr)', (tester) async {
      const probe = Probe.probeMain;
      setView(tester, dpr, const Size(48, 48));
      await pumpLoaded(
        tester,
        Align(
          alignment: Alignment.topLeft,
          child: RepaintBoundary(
            key: const ValueKey('probe'),
            child: Image.asset(probe.asset, centerSlice: probe.centerSlice, width: 40, height: 40, fit: BoxFit.fill),
          ),
        ),
        (context) => precacheImage(const AssetImage('assets/ui/probe/probe.png'), context),
      );

      // the file Flutter chose: 1x at DPR 1 and 2 (its low-ratio rule prefers the nearest lower file at 2
      // when only 1x and 3x exist), 3x at DPR 3
      final key = (await tester.runAsync(
        () => const AssetImage(
          'assets/ui/probe/probe.png',
        ).obtainKey(createLocalImageConfiguration(tester.element(find.byKey(const ValueKey('probe'))))),
      ))!;
      final fileScale = dpr == 3 ? 3.0 : 1.0;
      expect(key.name, probe.assetAt(fileScale));
      expect(key.scale, fileScale);

      final px = await Pixels.of(tester, await capture(tester, find.byKey(const ValueKey('probe')), dpr));
      expect(px.width, (40 * dpr).round());

      // a row through the corner below the dot (dp y = 3.5): red for 4 dp, then green, red again at the end
      final y = (3.5 * dpr).floor();
      var red = 0;
      while (_near(px.at(red, y), _red)) {
        red++;
      }
      expect(red, (4 * dpr).round(), reason: 'corner width in physical px at DPR $dpr');
      expect(_near(px.at((20 * dpr).round(), y), _green), isTrue);
      expect(_near(px.at((20 * dpr).round(), (20 * dpr).round()), _blue), isTrue);

      if (dpr == fileScale) {
        // file px == physical px: the corners are the file's corners, texel for texel
        final src = await Pixels.asset(tester, key.name);
        final c = (4 * dpr).round(), w = px.width;
        expect(px.maxDiff(0, 0, src, 0, 0, c, c), lessThanOrEqualTo(1));
        expect(px.maxDiff(w - c, 0, src, src.width - c, 0, c, c), lessThanOrEqualTo(1));
        expect(px.maxDiff(0, w - c, src, 0, src.height - c, c, c), lessThanOrEqualTo(1));
        expect(px.maxDiff(w - c, w - c, src, src.width - c, src.height - c, c, c), lessThanOrEqualTo(1));
        // the dot keeps its 1 dp: white at dp (1.5, 1.5), red at dp (2.5, 2.5)
        expect(px.at((1.5 * dpr).floor(), (1.5 * dpr).floor()), _white);
        expect(px.at((2.5 * dpr).floor(), (2.5 * dpr).floor()), _red);
      }
    });
  }

  testWidgets('a centerSlice in the 3x file\'s px is wrong: the corners come out 3x too big', (tester) async {
    // the counter-hypothesis, run: Rect.fromLTRB(12, 12, 24, 24) is the 3x file's middle in its own px
    const probe = Probe.probeMain;
    setView(tester, 3, const Size(96, 96));
    await pumpLoaded(
      tester,
      Align(
        alignment: Alignment.topLeft,
        child: RepaintBoundary(
          key: const ValueKey('probe'),
          child: Image.asset(
            probe.asset,
            centerSlice: const Rect.fromLTRB(12, 12, 24, 24),
            width: 80,
            height: 80,
            fit: BoxFit.fill,
          ),
        ),
      ),
      (context) => precacheImage(const AssetImage('assets/ui/probe/probe.png'), context),
    );
    final px = await Pixels.of(tester, await capture(tester, find.byKey(const ValueKey('probe')), 3));
    // Flutter reads 12 as 12 dp = 36 file px: the whole file becomes "corner" and the middle is empty, so
    // the probe's 12 px corner is not 12 physical px any more
    var red = 0;
    while (_near(px.at(red, 10), _red)) {
      red++;
    }
    expect(red, isNot(12));
  });
}
