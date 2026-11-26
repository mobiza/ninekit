// The demo page at device pixel ratios 1, 2 and 3: the same logical layout, the expected file per ratio,
// the press animation, and one golden per ratio (`flutter test --update-goldens` rewrites them).
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ninekit_demo/demo_page.dart';
import 'package:ninekit_demo/main.dart';
import 'package:ninekit_demo/ninekit/ninekit.dart';

import 'support.dart';

const _ratios = [1.0, 2.0, 3.0];

Future<void> _pumpDemo(WidgetTester tester, double dpr) async {
  setView(tester, dpr, DemoPage.size);
  await pumpLoaded(tester, const DemoApp(), DemoPage.precache);
}

/// Holds [key]'s button down until its press animation has finished.
Future<TestGesture> _holdDown(WidgetTester tester, Key key) async {
  final gesture = await tester.startGesture(tester.getCenter(find.byKey(key)));
  await tester.pump(const Duration(milliseconds: 150)); // the scroll view delays tap-down by kPressTimeout
  await tester.pump(const Duration(milliseconds: 150));
  return gesture;
}

Map<String, Rect> _boxes(WidgetTester tester) => {
  for (final e in find.byWidgetPredicate((w) => w.key is ValueKey<String>).evaluate())
    (e.widget.key! as ValueKey<String>).value: tester.getRect(find.byWidget(e.widget)),
};

void main() {
  setUpAll(loadFonts);

  testWidgets('same logical layout at DPR 1, 2, 3; each ratio gets its file', (tester) async {
    final layouts = <double, Map<String, Rect>>{};
    for (final dpr in _ratios) {
      await _pumpDemo(tester, dpr);
      final states = tester.stateList<NineSliceBoxState>(find.byType(NineSliceBox)).toList();
      expect(states.length, greaterThan(20));
      for (final s in states) {
        expect(s.isReady, isTrue, reason: '${s.widget.sprite.name} not loaded at DPR $dpr');
        for (final (i, info) in s.debugInfos.indexed) {
          final image = s.widget.images[i];
          // basics and gumdrop have 1x, 2x, 3x: the file of this ratio
          final scale = dpr;
          expect(info!.scale, scale, reason: image.asset);
          expect(info.debugLabel, image.assetAt(scale));
          expect(
            (info.image.width, info.image.height),
            (image.variantAt(scale)!.width, image.variantAt(scale)!.height),
          );
        }
      }
      layouts[dpr] = _boxes(tester);
    }
    expect(layouts[2], layouts[1]);
    expect(layouts[3], layouts[1]);

    final b = layouts[1]!;
    expect(b['demo']!.size, DemoPage.size);
    expect(b['panel_m']!.size, const Size(120, 64));
    expect(b['badge']!.size, Basics.badge.size);
    // child-sized pill: the label plus its padding [12, 4, 12, 6]; y is fixed, so at least its natural 30 dp
    final ok = tester.getRect(find.text('OK'));
    expect(Basics.pill.minBodySize.height, 30);
    expect(b['pill_fit']!.width, closeTo(ok.width + 24, 1e-9));
    expect(b['pill_fit']!.height, closeTo(ok.height + 10 < 30 ? 30 : ok.height + 10, 1e-9));
    // a y-fixed pill in a taller box keeps the box's size (its art is drawn 30 dp tall, centred)
    expect(b['pill_l']!.size, const Size(180, 36));
    // gumdrop buttons: canvas 128 x 62 minus the 3 dp shadow overhang = a 59 dp tall logical box
    expect(b['btn_mint']!.size.width, 180);
    expect(b['btn_mint']!.size.height, closeTo(59, 1e-9));
    expect(b['btnc_berry']!.size.width, 62);
    expect(b['btnc_berry']!.size.height, closeTo(59, 1e-9));
  });

  testWidgets('a label sits on the face: content insets are measured from the canvas', (tester) async {
    await _pumpDemo(tester, 3);
    final sprite = GumdropButtons.btnMint;
    // content [12, 8, 12, 17] from the canvas, overhang [0, 0, 0, 3] -> padding [12, 8, 12, 14]
    expect(sprite.childPadding.top, closeTo(8, 1e-9));
    expect(sprite.childPadding.bottom, closeTo(14, 1e-9));
    final box = tester.getRect(find.byKey(const ValueKey('btn_mint')));
    final label = tester.getRect(
      find.descendant(of: find.byKey(const ValueKey('btn_mint')), matching: find.text('Play')),
    );
    expect(label.center.dy - box.top, closeTo(26.5, 0.01));
    expect(label.center.dx - box.left, closeTo(90, 0.01));
  });

  testWidgets('press: face and label sink to 0.92 around the body centre, then spring back', (tester) async {
    await _pumpDemo(tester, 2);
    const key = ValueKey('btn_sky');
    final body = tester.getRect(find.byKey(key));
    final state = tester.state<NineSliceButtonState>(find.byKey(key));
    final face = find.descendant(of: find.byKey(key), matching: find.byType(NineSliceBox)).last;
    final frame = find.descendant(of: find.byKey(key), matching: find.byType(NineSliceBox)).first;
    expect(tester.widget<NineSliceBox>(frame).outputs, ['frame']);
    expect(tester.widget<NineSliceBox>(face).outputs, ['face']);

    final labelUp = tester.getRect(find.text('Press me'));
    final gesture = await _holdDown(tester, key);
    expect(state.faceScale, closeTo(0.92, 1e-9));
    final pressed = tester.getRect(face);
    expect(pressed.center.dx, closeTo(body.center.dx, 1e-6));
    expect(pressed.center.dy, closeTo(body.center.dy, 1e-6));
    expect(pressed.width, closeTo(body.width * 0.92, 1e-6));
    expect(pressed.height, closeTo(body.height * 0.92, 1e-6));
    // the label scales with the face, toward the same centre
    final label = tester.getRect(find.text('Press me'));
    expect(label.height, closeTo(labelUp.height * 0.92, 1e-6));
    expect(label.center.dy, closeTo(body.center.dy + (labelUp.center.dy - body.center.dy) * 0.92, 1e-6));
    expect(tester.getRect(frame), body); // the frame stays

    await gesture.up();
    var peak = 0.0;
    for (var i = 0; i < 40; i++) {
      await tester.pump(const Duration(milliseconds: 16));
      if (state.faceScale > peak) peak = state.faceScale;
    }
    expect(peak, greaterThan(1.0)); // the spring overshoots a little
    await tester.pumpAndSettle();
    expect(state.faceScale, closeTo(1.0, 1e-3));
  });

  for (final dpr in _ratios) {
    testWidgets('golden at DPR $dpr (btn_sky held down)', (tester) async {
      await _pumpDemo(tester, dpr);
      final gesture = await _holdDown(tester, const ValueKey('btn_sky'));
      expect(tester.state<NineSliceButtonState>(find.byKey(const ValueKey('btn_sky'))).faceScale, 0.92);
      final image = await capture(tester, find.byKey(const ValueKey('demo')), dpr);
      expect((image.width, image.height), ((DemoPage.size.width * dpr).round(), (DemoPage.size.height * dpr).round()));
      await expectLater(image, matchesGoldenFile('goldens/demo_dpr${dpr.toInt()}.png'));
      await gesture.up();
      await tester.pumpAndSettle();
    });
  }
}
