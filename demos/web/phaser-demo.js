// ninekit Phaser demo: the same pieces as css.html, through the generated `ninekit-phaser.js` modules.
// World units = CSS px = dp. The canvas backing store is devicePixelRatio x larger (camera zoom = dpr, canvas zoom
// = 1/dpr) and each module loads the texture scale matching the ratio, so texels land 1:1 on device pixels.
import * as basics from './generated/phaser/basics/ninekit-phaser.js';
import * as buttons from './generated/phaser/buttons/ninekit-phaser.js';

const W = 880, H = 1360;
const DPR = window.devicePixelRatio || 1;
const GOLD = [[0, '#4A2306'], [0.5, '#C8761E'], [1, '#FFF1B8']];
const MINT = [[0, '#0B3B33'], [0.5, '#21A88C'], [1, '#E6FFF6']];
const INK = '#2b2620';
const probes = {};

function text(scene, s, style = {}) {
  // RTL: Phaser 3.90's `rtl: true` puts each line at canvas.width (device px) inside a context already scaled by
  // `resolution`, so with resolution > 1 the text lands off its canvas. Instead the string is wrapped in Unicode
  // isolates (RLI ... PDI): canvas fillText runs the bidi algorithm with a right-to-left base direction.
  const { rtl, ...rest } = style;
  return scene.add.text(0, 0, rtl ? `⁧${s}⁩` : s, {
    fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', fontSize: '13px', color: INK,
    resolution: DPR, ...rest,
  });
}

/** A piece with its logical rect's top-left at (x, y); `label` is centred in its content rect. */
function piece(scene, mod, name, x, y, w, h, opts = {}) {
  const c = mod.addNinekit(scene, x, y, name, w, h, { originX: 0, originY: 0, ...opts });
  const nk = c.ninekit;
  if (opts.label) {
    const r = nk.contentRect();
    const t = text(scene, opts.label, {
      fontSize: opts.fontSize || '21px', fontStyle: opts.fontStyle || 'bold', color: opts.color || '#ffffff',
      align: 'center', rtl: !!opts.rtl,
    }).setOrigin(0.5, 0.5).setPosition(r.centerX, r.centerY);
    if (opts.shadow !== false) t.setShadow(0, opts.shadowY ?? 2, 'rgba(40,20,0,0.45)', 0, false, true);
    nk.addContent(t);
  }
  if (opts.lines) {           // a panel: a bold title and a wrapped body, top-aligned in the content rect
    const r = nk.contentRect();
    const ax = opts.rtl ? r.x + r.width : r.x;
    const title = text(scene, opts.lines[0], { fontStyle: 'bold', rtl: !!opts.rtl })
      .setOrigin(opts.rtl ? 1 : 0, 0).setPosition(ax, r.y + 3);  // ~ CSS half-leading
    const body = text(scene, opts.lines[1], {
      fontSize: '12px', color: '#4a3b2a', rtl: !!opts.rtl, align: opts.rtl ? 'right' : 'left',
      wordWrap: { width: r.width, useAdvancedWrap: true },
    }).setOrigin(opts.rtl ? 1 : 0, 0).setPosition(ax, r.y + 21);
    nk.addContent(title, body);
  }
  if (opts.pressed) nk.setPressed(true);
  if (opts.probe) probes[opts.probe] = { piece: name, x, y, w: nk.width, h: nk.height, pressed: !!opts.pressed };
  return c;
}

function bar(scene, x, y, w, h, frac, rtl = false) {
  piece(scene, basics, 'bar_track', x, y, w, h);
  const fw = Math.max(12, (w - 4) * frac), fh = h - 4;
  piece(scene, basics, 'bar_fill', rtl ? x + w - 2 - fw : x + 2, y + 2, fw, fh);
}

function heading(scene, s, y) {
  text(scene, s.toUpperCase(), { fontStyle: 'bold', color: '#7a6c58', letterSpacing: 1 }).setPosition(16, y);
}

class Demo extends Phaser.Scene {
  preload() {
    basics.preloadNinekit(this);            // the scale matching devicePixelRatio (1, 2 or 3)
    buttons.preloadNinekit(this);           // only scale 3 exists
  }

  create() {
    const cam = this.cameras.main;
    cam.setOrigin(0, 0).setZoom(DPR);

    text(this, 'ninekit · Phaser (NineSlice at 1/scale)', { fontSize: '18px', fontStyle: 'bold' }).setPosition(16, 12);
    const info = text(this, '', { fontFamily: 'ui-monospace, monospace', fontSize: '11px', color: '#8a7d6a' })
      .setPosition(16, 38);

    // --- probes (same places as css.html)
    heading(this, 'Measured probes', 70);
    this.add.rectangle(16, 86, 828, 236, 0xffffff).setOrigin(0, 0);    // = css.html's strip (860 - 2 x 16)
    piece(this, basics, 'scifi', 32, 108, 120, 72, { probe: 'scifi' });
    piece(this, basics, 'pill', 172, 108, 150, 30, { probe: 'pill', label: 'pill', fontSize: '13px', shadowY: 1 });
    piece(this, basics, 'panel', 342, 108, 140, 80, { probe: 'panel', lines: ['Panel', 'overhang 3 below'] });
    piece(this, basics, 'tab', 502, 108, 110, 40, { probe: 'tab', label: 'Tab', fontSize: '13px', shadow: false });
    piece(this, basics, 'stone', 632, 108, 150, 100, { probe: 'stone' });
    piece(this, basics, 'badge', 802, 108, undefined, undefined, { probe: 'badge' });
    piece(this, buttons, 'btn_mint', 32, 226, 200, 59, { probe: 'btn', label: 'Play' });
    piece(this, buttons, 'btn_mint', 252, 226, 200, 59, { probe: 'btn_pressed', label: 'Play', pressed: true });
    piece(this, buttons, 'btnc_berry', 472, 226, undefined, undefined, { probe: 'btnc' });
    piece(this, buttons, 'btnc_berry', 558, 226, undefined, undefined, { probe: 'btnc_pressed', pressed: true });
    piece(this, basics, 'shade_button', 644, 226, 90, 40, { probe: 'shade', ramp: GOLD });
    // y-fixed (DESIGN 7): the art keeps its 30 dp, centred on the 50 dp box; the label lays out in the box
    this.add.rectangle(740.5, 222.5, 103, 57).setOrigin(0, 0).setStrokeStyle(1, 0xd8cfc0);   // the box, 3 px out
    piece(this, basics, 'pill', 744, 226, 96, 50,
      { probe: 'pill_tall', label: 'tall box', fontSize: '13px', shadowY: 1 });
    text(this, 'btn_mint 200×59 · pressed · btnc_berry · btnc_berry pressed · shade_button + gold ramp · y-fixed pill in a 50 px box',
      { fontFamily: 'ui-monospace, monospace', fontSize: '10px', color: '#9a8f80' }).setPosition(32, 298);

    // --- basics at three sizes
    heading(this, 'Basics at three sizes', 334);
    let y = 356;
    piece(this, basics, 'panel', 16, y, 120, 70, { lines: ['Inbox', '3 new'] });
    piece(this, basics, 'panel', 152, y, 200, 90, { lines: ['Daily quest', 'Collect 12 gumdrops before the timer runs out.'] });
    piece(this, basics, 'panel', 368, y, 300, 120,
      { lines: ['Notes', 'Content rect = canvas minus content insets; the shadow below is overhang.'] });
    y = 496;
    piece(this, basics, 'pill', 16, y, 32, 30, { label: '1', fontSize: '13px', shadowY: 1 });
    piece(this, basics, 'pill', 64, y, 90, 30, { label: 'Shop', fontSize: '13px', shadowY: 1 });
    piece(this, basics, 'pill', 170, y, 170, 40, { label: 'Daily reward', fontSize: '13px', shadowY: 1 });
    piece(this, basics, 'scifi', 356, y, 110, 60);
    piece(this, basics, 'scifi', 482, y, 200, 80);
    y = 594;
    bar(this, 16, y, 120, 16, 0.3);
    bar(this, 152, y, 200, 16, 0.6);
    bar(this, 368, y, 300, 20, 1);
    y = 628;
    piece(this, basics, 'tab', 16, y, 70, 34, { label: 'Tab', fontSize: '13px', shadow: false });
    piece(this, basics, 'tab', 102, y, 120, 34, { label: 'Items', fontSize: '13px', shadow: false });
    piece(this, basics, 'tab', 238, y, 170, 44, { label: 'Settings', fontSize: '13px', shadow: false });
    piece(this, basics, 'tab', 424, y, 120, 34, { label: 'Pressed', fontSize: '13px', shadow: false, pressed: true });
    piece(this, basics, 'badge', 560, y);
    piece(this, basics, 'stone', 604, y, 72, 64);
    piece(this, basics, 'stone', 692, y, 130, 64);
    y = 708;
    piece(this, basics, 'stone', 16, y, 200, 100);
    this.add.rectangle(232, y, 632, 100, 0x3b4252).setOrigin(0, 0);
    piece(this, basics, 'shade_button', 248, y + 16, 44, 32);
    piece(this, basics, 'shade_button', 308, y + 16, 80, 32, { ramp: GOLD });
    piece(this, basics, 'shade_button', 404, y + 16, 140, 48, { ramp: MINT });
    piece(this, basics, 'shade_button', 560, y + 16, 140, 48, { ramp: GOLD });

    // --- gumdrop buttons
    heading(this, 'Gumdrop buttons (casual_button block, scales 1, 2, 3)', 834);
    y = 856;
    piece(this, buttons, 'btn_mint', 16, y, 120, 59, { label: 'Play' });
    piece(this, buttons, 'btn_mint', 152, y, 180, 59, { label: 'Play' });
    piece(this, buttons, 'btn_sun', 348, y, 180, 59, { label: 'Pressed', pressed: true });
    piece(this, buttons, 'btn_sky', 544, y, 280, 59, { label: 'Continue' });
    y = 940;
    piece(this, buttons, 'btn_grape', 16, y, 200, 80, { label: 'Taller' });
    piece(this, buttons, 'btnc_berry', 232, y);
    piece(this, buttons, 'btnc_mint', 314, y);
    piece(this, buttons, 'btnc_mint', 396, y, undefined, undefined, { pressed: true });
    piece(this, buttons, 'btnc_sky', 478, y, undefined, undefined, { composite: true });

    // --- RTL: laid out right to left, labels shaped RTL; the art is not mirrored
    heading(this, 'RTL row (right to left, Arabic labels; the art is not mirrored)', 1046);
    y = 1068;
    piece(this, basics, 'panel', W - 16 - 250, y, 250, 96,
      { rtl: true, lines: ['المهمة اليومية', 'اجمع ١٢ قطعة حلوى قبل انتهاء الوقت.'] });
    piece(this, buttons, 'btn_mint', W - 16 - 250 - 16 - 170, y, 170, 59, { label: 'العب', rtl: true });
    piece(this, basics, 'pill', W - 16 - 250 - 16 - 170 - 16 - 100, y, 100, 30,
      { label: 'المستوى ٣', rtl: true, fontSize: '13px', shadowY: 1 });
    bar(this, W - 16 - 250 - 16 - 170 - 16 - 100 - 16 - 180, y, 180, 16, 0.4, true);
    piece(this, basics, 'tab', W - 16 - 110, y + 112, 110, 34, { label: 'الإعدادات', rtl: true, fontSize: '13px', shadow: false });

    info.setText(`devicePixelRatio ${DPR} · textures basics @${basics.pickScale(DPR)}x, buttons @${buttons.pickScale(DPR)}x · ` +
      `canvas ${this.scale.width}×${this.scale.height} px`);
    document.getElementById('nk-probes').textContent = JSON.stringify({ page: 'phaser', dpr: DPR, probes });
    let frames = 0;
    // ready after the first drawn frame (software WebGL at a ratio of 3 takes seconds per frame)
    this.game.events.on('postrender', () => { if (++frames === 1) window.nkReady = true; });
  }
}

try {
  new Phaser.Game({
    type: Phaser.WEBGL,
    parent: 'game',
    width: W * DPR,
    height: H * DPR,
    backgroundColor: '#f2ede4',
    scale: { mode: Phaser.Scale.NONE, zoom: 1 / DPR },
    render: { antialias: true },
    banner: false,
    scene: Demo,
  });
} catch (e) {
  window.nkError = String(e);
  throw e;
}
window.addEventListener('error', (e) => { window.nkError = String(e.message || e); });
