"""The `phaser` export target: files, `ninekit-phaser.json`, the generated ES module, and (with Node) the module's
layout driven against a stub scene. The real rendering is measured in Chrome by demos/web/check.py."""
import json
import math
import re
import shutil
import subprocess

import pytest

from conftest import ROOT
from ninekit import NinekitError
from ninekit.cli import main as cli_main
from ninekit.exporters.phaser import export, texture_key
from ninekit.manifest import load_manifest
from ninekit.render import build

BASICS = ROOT / "examples" / "basics" / "basics.yaml"
BUTTONS = ROOT / "examples" / "gumdrop" / "buttons.yaml"


@pytest.fixture(scope="module")
def basics(tmp_path_factory):
    return build(BASICS, out=tmp_path_factory.mktemp("basics")).manifest_path


@pytest.fixture(scope="module")
def buttons(tmp_path_factory):
    return build(BUTTONS, out=tmp_path_factory.mktemp("buttons"), only=["btn_mint", "btnc_berry"]).manifest_path


def embedded(js: str) -> dict:
    m = re.search(r"^const DATA = (\{.*?\n\});$", js, re.S | re.M)
    assert m, "no embedded DATA"
    return json.loads(m.group(1))


def test_export_writes_pngs_json_and_module(basics, tmp_path):
    written = {p.name for p in export(basics, tmp_path)}
    assert {"ninekit-phaser.json", "ninekit-phaser.js"} <= written
    m = load_manifest(basics)
    data = json.loads((tmp_path / "ninekit-phaser.json").read_text())
    assert data["name"] == "basics" and data["scales"] == [1, 2, 3]
    assert set(data["pieces"]) == set(m["pieces"])
    keys = set()
    for name, p in data["pieces"].items():
        mp = m["pieces"][name]
        assert p["stretch"] == mp["stretch"] and p["content"] == mp["content"] and p["overhang"] == mp["overhang"]
        for o, per in p["outputs"].items():
            for k, f in per.items():
                assert (tmp_path / f["file"]).is_file()
                assert f["size_px"] == mp["outputs"][o][k]["size_px"]
                assert f["slice_px"] == mp["outputs"][o][k]["slice_px"]       # texture px, authoritative
                assert f["key"] == texture_key("basics", name, o, k)
                keys.add(f["key"])
    assert len(keys) == sum(len(per) for p in data["pieces"].values() for per in p["outputs"].values())
    assert data["pieces"]["tab"]["layers"] == ["frame", "face"] and data["pieces"]["tab"]["press"] is True
    assert data["pieces"]["panel"]["press"] is False
    js = (tmp_path / "ninekit-phaser.js").read_text()
    assert embedded(js) == data
    for needle in ("export function preloadNinekit(scene, baseUrl, opts = {})",
                   "export function addNinekit(scene, x, y, name, width, height, opts = {})",
                   "scene.add.nineslice(", "import.meta.url"):
        assert needle in js
    assert "__NINEKIT_" not in js


def test_composite_main_is_not_stacked(buttons, tmp_path):
    export(buttons, tmp_path)
    data = json.loads((tmp_path / "ninekit-phaser.json").read_text())
    p = data["pieces"]["btnc_berry"]
    assert p["layers"] == ["frame", "face"] and p["composite"] == "main" and p["slice"] is None
    assert p["outputs"]["main"]["3"]["file"] == "btnc_berry@3x.png"


def test_scale_option(basics, tmp_path):
    export(basics, tmp_path, scale=3)
    data = json.loads((tmp_path / "ninekit-phaser.json").read_text())
    assert data["scales"] == [3]
    assert all(set(per) == {"3"} for p in data["pieces"].values() for per in p["outputs"].values())
    assert not list(tmp_path.glob("*@1x.png"))
    with pytest.raises(NinekitError):
        export(basics, tmp_path / "x", scale=4)


def test_cli_export_phaser(basics, tmp_path):
    assert cli_main(["export", str(basics), "--target", "phaser", "-o", str(tmp_path)]) == 0
    assert (tmp_path / "ninekit-phaser.js").is_file()


HARNESS = r"""
import * as nk from '%s';
const out = {};
function obj(kind, a) {
  return { kind, a, x: 0, y: 0, sx: 1, sy: 1, ox: 0.5, oy: 0.5, w: a.w, h: a.h, kids: [], visible: true,
    setOrigin(x, y) { this.ox = x; this.oy = y; return this; }, setPosition(x, y) { this.x = x; this.y = y; return this; },
    setScale(x, y = x) { this.sx = x; this.sy = y; return this; }, setSize(w, h) { this.w = w; this.h = h; return this; },
    add(c) { this.kids.push(...[c].flat()); return this; }, setVisible(v) { this.visible = v; return this; },
    setTileScale(x, y) { this.tsx = x; this.tsy = y; return this; }, setTilePosition() { return this; },
    on() { return this; }, setInteractive() { return this; } };
}
let have = false;
const loaded = [];
const scene = {
  textures: { exists: () => have, get: () => ({ has: () => false, add() {} }) },
  load: { image: (k, u) => loaded.push([k, u]) },
  add: {
    container: (x, y) => obj('container', {}).setPosition(x, y),
    nineslice: (x, y, key, frame, w, h, l, r, t, b) => obj('nineslice', { key, w, h, l, r, t, b }),
    image: (x, y, key, frame) => obj('image', { key, frame }),
    tileSprite: (x, y, w, h, key, frame) => obj('tile', { key, frame, w, h }),
  },
};
const pick = (o) => ({ kind: o.kind, a: o.a, x: o.x, y: o.y, sx: o.sx, sy: o.sy, ox: o.ox, oy: o.oy, w: o.w, h: o.h });
out.scale = nk.preloadNinekit(scene, 'ui', { scale: %s });
out.loaded = loaded;
have = true;
%s
console.log(JSON.stringify(out));
"""


def run_node(module, scale, body, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    h = tmp_path / "harness.mjs"
    h.write_text(HARNESS % (module.as_uri(), scale, body))
    r = subprocess.run([node, str(h)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_module_layout_basics(basics, tmp_path):
    export(basics, tmp_path / "out")
    data = json.loads((tmp_path / "out" / "ninekit-phaser.json").read_text())
    out = run_node(tmp_path / "out" / "ninekit-phaser.js", 2, r"""
      const panel = nk.addNinekit(scene, 10, 20, 'panel', 140, 80, { originX: 0, originY: 0 });
      out.panel = { c: pick(panel), layer: pick(panel.ninekit.layers.main) };
      const tab = nk.addNinekit(scene, 0, 0, 'tab', 120, 34);
      out.tab = { frame: pick(tab.ninekit.layers.frame), face: pick(tab.ninekit.layers.face) };
      tab.ninekit.setPressed(true);
      out.tabPressed = { frame: pick(tab.ninekit.layers.frame), face: pick(tab.ninekit.layers.face),
                         pivot: pick(tab.ninekit.pivot) };
      const pill = nk.addNinekit(scene, 0, 0, 'pill', 150, 50, { originX: 0, originY: 0 });
      out.pill = pick(pill.ninekit.layers.main);
      out.pillContent = pill.ninekit.contentRect();
      const badge = nk.addNinekit(scene, 0, 0, 'badge');
      out.badge = pick(badge.ninekit.layers.main);
      const stone = nk.addNinekit(scene, 0, 0, 'stone', 150, 100, { originX: 0, originY: 0, scale: 1 });
      out.stone = { group: pick(stone.ninekit.layers.main),
                    parts: stone.ninekit.layers.main.kids.map((p) => ({ ...pick(p), tsx: p.tsx, tsy: p.tsy })) };
    """, tmp_path)
    assert out["scale"] == 2
    files = [f for p in data["pieces"].values() for per in p["outputs"].values() for k, f in per.items() if k == "2"]
    assert sorted(out["loaded"]) == sorted([f["key"], "ui/" + f["file"]] for f in files)
    # panel: 140 x 80 dp logical + 3 dp overhang below -> a 280 x 166 texture-px NineSlice drawn at 1/2
    lay = out["panel"]["layer"]
    sp = data["pieces"]["panel"]["outputs"]["main"]["2"]["slice_px"]
    assert out["panel"]["c"]["x"] == 10 and out["panel"]["c"]["y"] == 20
    assert lay["kind"] == "nineslice" and [lay["a"][k] for k in "ltrb"] == sp
    assert (lay["w"], lay["h"], lay["sx"], lay["ox"], lay["oy"], lay["x"], lay["y"]) == (280, 166, 0.5, 0, 0, 0, 0)
    # tab (origin 0.5): frame and face share the rect; pressed, the face (and the content pivot) scale 0.92 about
    # the logical centre and the frame stays
    for o in ("frame", "face"):
        assert (out["tab"][o]["x"], out["tab"][o]["y"], out["tab"][o]["sx"]) == (-60, -17, 0.5)
    f = out["tabPressed"]["face"]
    assert f["x"] == pytest.approx(-60 * 0.92) and f["y"] == pytest.approx(-17 * 0.92) and f["sx"] == pytest.approx(0.46)
    assert out["tabPressed"]["frame"]["x"] == -60 and out["tabPressed"]["frame"]["sx"] == 0.5
    assert out["tabPressed"]["pivot"]["sx"] == pytest.approx(0.92)
    # y-fixed pill in a 150 x 50 box: the art keeps its 30 dp, centred (10 dp from the box top); the content
    # still lays out in the box (content [12, 4, 12, 6])
    assert data["pieces"]["pill"]["stretch"] == ["stretch", "fixed"]
    pl = out["pill"]
    assert (pl["x"], pl["y"], pl["w"], pl["h"], pl["sx"]) == (0, 10, 300, 60, 0.5)
    assert out["pillContent"]["y"] == 4 and out["pillContent"]["height"] == 40
    # drawn whole: an Image scaled to the sprite rect in dp
    assert out["badge"]["kind"] == "image" and out["badge"]["sx"] == pytest.approx(28 / 56)
    # tile: 9 parts; the middle repeats a whole number of times (150 x 100 dp at scale 1, region 48 x 24 px)
    parts = {(p["a"]["frame"]): p for p in out["stone"]["parts"]}
    assert out["stone"]["group"]["sx"] == 1 and len(parts) == 9
    l, t, r, b = data["pieces"]["stone"]["outputs"]["main"]["1"]["slice_px"]
    W, H = data["pieces"]["stone"]["outputs"]["main"]["1"]["size_px"]
    mw, mh, MW, MH = W - l - r, H - t - b, 150 - l - r, 100 - t - b
    c = parts["nk11"]
    assert c["kind"] == "tile" and (c["w"], c["h"]) == (MW, MH)
    jsround = lambda v: max(1, math.floor(v + 0.5))                      # Math.round (2.5 -> 3)
    assert c["tsx"] == pytest.approx(MW / (jsround(MW / mw) * mw))
    assert c["tsy"] == pytest.approx(MH / (jsround(MH / mh) * mh))
    assert parts["nk00"]["kind"] == "image" and (parts["nk00"]["x"], parts["nk00"]["y"]) == (0, 0)
    assert (parts["nk22"]["x"], parts["nk22"]["y"]) == (l + MW, t + MH)


def test_module_content_rect_from_canvas(buttons, tmp_path):
    export(buttons, tmp_path / "out")
    out = run_node(tmp_path / "out" / "ninekit-phaser.js", 3, r"""
      const b = nk.addNinekit(scene, 0, 0, 'btn_mint', 200, 59, { originX: 0, originY: 0 });
      out.rect = b.ninekit.contentRect();
      out.frame = pick(b.ninekit.layers.frame);
      const c = nk.addNinekit(scene, 0, 0, 'btnc_berry');
      out.round = { w: c.ninekit.width, h: c.ninekit.height, layers: Object.keys(c.ninekit.layers) };
      const comp = nk.addNinekit(scene, 0, 0, 'btnc_berry', undefined, undefined, { composite: true });
      out.composite = Object.keys(comp.ninekit.layers);
    """, tmp_path)
    r = out["rect"]
    # content [12, 8, 12, 17] measured from the 128 x 62 canvas (overhang 3 below the 59 dp body)
    assert (r["x"], r["y"]) == (12, pytest.approx(8))
    assert r["width"] == pytest.approx(176) and r["height"] == pytest.approx(37)
    assert r["centerY"] == pytest.approx(26.5, abs=0.01)                  # the face panel's centre
    assert out["frame"]["w"] == pytest.approx(600) and out["frame"]["h"] == pytest.approx(186)
    assert out["round"] == {"w": 62, "h": pytest.approx(59), "layers": ["frame", "face"]}
    assert out["composite"] == ["main"]
