import 'package:flutter/material.dart';

import 'ninekit/ninekit.dart';

/// Every exported piece at several sizes: basics and Gumdrop's buttons (both at scales 1, 2, 3).
/// Each box has a ValueKey with its name; the tests compare their sizes and pixels across pixel ratios.
class DemoPage extends StatelessWidget {
  const DemoPage({super.key});

  static const Color background = Color(0xFF3B4252);
  static const Size size = Size(420, 608);

  static const NineRamp blue = NineRamp([
    (0.0, Color(0xFF0B2350)),
    (0.3, Color(0xFF1B4C98)),
    (0.7, Color(0xFF3F97EA)),
    (1.0, Color(0xFFD6F0FF)),
  ]);
  static const NineRamp green = NineRamp([
    (0.0, Color(0xFF123A0A)),
    (0.3, Color(0xFF2B7A16)),
    (0.7, Color(0xFF66C536)),
    (1.0, Color(0xFFE4FFCC)),
  ]);
  static const NineRamp gold = NineRamp([
    (0.0, Color(0xFF462805)),
    (0.3, Color(0xFF975C10)),
    (0.7, Color(0xFFEFB13A)),
    (1.0, Color(0xFFFFF3C6)),
  ]);
  static const List<NineRamp> ramps = [blue, green, gold];

  /// Loads every image (and ramp bake) the page draws for [context]'s pixel ratio.
  static Future<void> precache(BuildContext context) => Future.wait([
    for (final s in Basics.all)
      if (s.mode == NineMode.color) precacheNineSprite(context, s),
    for (final r in ramps) precacheNineSprite(context, Basics.shadeButton, ramp: r),
    for (final s in [GumdropButtons.btnMint, GumdropButtons.btnSun, GumdropButtons.btnSky, GumdropButtons.btncBerry])
      precacheNineSprite(context, s),
    precacheNineSprite(context, GumdropButtons.btncSky, composite: true),
  ]);

  static const TextStyle _heading = TextStyle(color: Color(0xFFECEFF4), fontSize: 15, fontWeight: FontWeight.w700);
  static const TextStyle _ink = TextStyle(color: Color(0xFF3A2E22), fontSize: 14, fontWeight: FontWeight.w600);
  static const TextStyle _light = TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w700);
  static const TextStyle _button = TextStyle(
    color: Colors.white,
    fontSize: 20,
    fontWeight: FontWeight.w800,
    shadows: [Shadow(color: Color(0x99000000), offset: Offset(0, 1.5), blurRadius: 1.5)],
  );

  static Widget _row(double height, List<Widget> children, {double gap = 12}) => SizedBox(
    height: height,
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < children.length; i++) ...[if (i > 0) SizedBox(width: gap), children[i]],
      ],
    ),
  );

  static Widget _label(String text, TextStyle style) => Center(child: Text(text, style: style));

  @override
  Widget build(BuildContext context) {
    void tap() {}
    return RepaintBoundary(
      key: const ValueKey('demo'),
      child: ColoredBox(
        color: background,
        child: SizedBox.fromSize(
          size: size,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 20, child: Text('basics · scales 1, 2, 3', style: _heading)),
                const SizedBox(height: 8),
                _row(68, [
                  const NineSliceBox(key: ValueKey('panel_s'), sprite: Basics.panel, width: 40, height: 40),
                  NineSliceBox(
                    key: const ValueKey('panel_m'),
                    sprite: Basics.panel,
                    width: 120,
                    height: 64,
                    child: _label('Panel', _ink),
                  ),
                  NineSliceBox(
                    key: const ValueKey('panel_l'),
                    sprite: Basics.panel,
                    width: 204,
                    height: 64,
                    child: _label('content padding', _ink),
                  ),
                ]),
                const SizedBox(height: 12),
                _row(36, [
                  const NineSliceBox(
                    key: ValueKey('pill_fit'),
                    sprite: Basics.pill,
                    child: Text('OK', style: _light),
                  ),
                  NineSliceBox(
                    key: const ValueKey('pill_m'),
                    sprite: Basics.pill,
                    width: 120,
                    height: 30,
                    child: _label('Play', _light),
                  ),
                  NineSliceBox(
                    key: const ValueKey('pill_l'),
                    sprite: Basics.pill,
                    width: 180,
                    height: 36, // y is fixed: the 30 dp art is centred in the 36 dp box
                    child: _label('Continue', _light),
                  ),
                ]),
                const SizedBox(height: 12),
                _row(36, [
                  NineSliceBox(
                    key: const ValueKey('tab_s'),
                    sprite: Basics.tab,
                    width: 56,
                    height: 34,
                    child: _label('A', _light),
                  ),
                  NineSliceBox(
                    key: const ValueKey('tab_m'),
                    sprite: Basics.tab,
                    width: 96,
                    height: 34,
                    child: _label('Tab', _light),
                  ),
                  const NineSliceBox(key: ValueKey('badge'), sprite: Basics.badge),
                  const Padding(
                    padding: EdgeInsets.only(top: 9),
                    child: NineSliceBox(
                      key: ValueKey('bar_track'),
                      sprite: Basics.barTrack,
                      width: 168,
                      height: 16,
                      child: Padding(
                        padding: EdgeInsets.all(2),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: NineSliceBox(
                            key: ValueKey('bar_fill'),
                            sprite: Basics.barFill,
                            width: 112,
                            height: 12,
                          ),
                        ),
                      ),
                    ),
                  ),
                ]),
                const SizedBox(height: 12),
                _row(120, [
                  const NineSliceBox(key: ValueKey('scifi'), sprite: Basics.scifi, width: 120, height: 84),
                  const NineSliceBox(key: ValueKey('stone'), sprite: Basics.stone, width: 256, height: 120),
                ]),
                const SizedBox(height: 12),
                _row(40, [
                  for (final (name, ramp) in [('blue', blue), ('green', green), ('gold', gold)])
                    NineSliceBox(
                      key: ValueKey('shade_$name'),
                      sprite: Basics.shadeButton,
                      ramp: ramp,
                      width: 120,
                      height: 40,
                      child: Padding(padding: const EdgeInsets.only(bottom: 4), child: _label(name, _light)),
                    ),
                ], gap: 14),
                const SizedBox(height: 16),
                const SizedBox(height: 20, child: Text('gumdrop buttons · scales 1, 2, 3', style: _heading)),
                const SizedBox(height: 8),
                _row(72, [
                  NineSliceButton(
                    key: const ValueKey('btn_mint'),
                    sprite: GumdropButtons.btnMint,
                    width: 180,
                    onPressed: tap,
                    child: _label('Play', _button),
                  ),
                  NineSliceButton(
                    key: const ValueKey('btn_sun'),
                    sprite: GumdropButtons.btnSun,
                    width: 196,
                    onPressed: tap,
                    child: _label('Shop', _button),
                  ),
                ]),
                const SizedBox(height: 12),
                _row(72, [
                  NineSliceButton(
                    key: const ValueKey('btn_sky'),
                    sprite: GumdropButtons.btnSky,
                    width: 180,
                    onPressed: tap,
                    child: _label('Press me', _button),
                  ),
                  NineSliceButton(
                    key: const ValueKey('btnc_berry'),
                    sprite: GumdropButtons.btncBerry,
                    onPressed: tap,
                    child: _label('×', _button.copyWith(fontSize: 30)),
                  ),
                  const NineSliceBox(key: ValueKey('btnc_sky'), sprite: GumdropButtons.btncSky, composite: true),
                ]),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
