"""casual_button at other scales: it renders natively at any scale, and the slices it reports hold - the columns
inside [l, w - r) are byte-identical (the stretch rule) and the rows inside [t, h - b) are smooth (DESIGN.md §5)."""
import importlib.util
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_block():
    # by path: the test depends on nothing else in ninekit
    name = "ninekit_casual_button_bypath"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "src" / "ninekit" / "blocks" / "casual_button.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


CB = _load_block()
SCALES = (1, 2, 4)


def _check_sliced(res, scale, label):
    l, t, r, b = res["slice_px"]
    w_dp, h_dp = res["size"]
    for key, img in res["outputs"].items():
        what = "%s/%s @%dx" % (label, key, scale)
        assert img.mode == "RGBA", what
        assert img.size == (round(w_dp * scale), round(h_dp * scale)), what
        a = np.asarray(img)
        h, w = a.shape[:2]
        assert 0 < l and 0 < r and l + r < w, "%s: slice %s in %d px" % (what, res["slice_px"], w)
        assert 0 < t and 0 < b and t + b < h, "%s: slice %s in %d px" % (what, res["slice_px"], h)
        mid = a[:, l:w - r]
        same = (mid == mid[:, :1]).all(axis=(0, 2))
        assert same.all(), "%s: columns %s differ from column %d" % (what, (np.nonzero(~same)[0] + l).tolist(), l)
        rows = a[t:h - b].astype(int)
        assert rows.shape[0] >= 1
        if rows.shape[0] > 1:
            step = np.abs(np.diff(rows, axis=0)).max()
            assert step <= 8, "%s: rows %d..%d change by %d per row" % (what, t, h - b, step)
        assert a[:, l].any(), "%s: transparent stretch column" % what


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("style", sorted(CB.PRESETS))
def test_rect_renders_and_stretches(style, scale):
    res = CB.render({"style": style, "layers": ["frame", "face", "full"]}, scale)
    assert set(res["outputs"]) == {"frame", "face", "main"}
    _check_sliced(res, scale, style)
    pressed = CB.render({"style": style, "layers": ["full"], "pressed": True}, scale)
    _check_sliced(pressed, scale, style + " pressed")
    assert pressed["slice_px"] == res["slice_px"]


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("style", ["mint", "gray", "cloud"])
def test_circle_renders_whole(style, scale):
    res = CB.render({"style": style, "circle": True, "layers": ["frame", "face", "full"]}, scale)
    assert res["slice_px"] is None
    assert res["size"] == [62.0, 62.0]
    for key, img in res["outputs"].items():
        assert img.mode == "RGBA" and img.size == (62 * scale, 62 * scale), key
        a = np.asarray(img)
        # round and centred: transparent corners, symmetric left to right (the mitred bevel triangles are filled by
        # Pillow's polygon rasteriser, which is not exactly mirror-symmetric: along the diagonals the face differs by
        # up to one supersampled texel of the bevel's contrast, 18/255 for mint's light top bevel at 4x)
        assert a[0, 0, 3] == 0 and a[0, -1, 3] == 0, key
        assert np.abs(a.astype(int) - a[:, ::-1]).max() <= (0 if key == "frame" else 24), key


def test_slice_follows_scale():
    # the side slice holds the panel corners, the sheen's rounded ends and the bezel corners plus an anti-aliasing
    # allowance that never drops under RESAMPLE_PX texture px; vertically everything but the two middle rows
    assert [CB.render({"style": "mint", "layers": ["face"]}, s)["slice_px"] for s in (1, 2, 3, 4)] == [
        [28, 30, 28, 30], [52, 61, 52, 61], [76, 92, 76, 92], [100, 123, 100, 123]]
    # without a sheen the panel and bezel corners decide
    no_sheen = {"style": "mint", "layers": ["face"], "sheen": 0}
    assert [CB.render(no_sheen, s)["slice_px"][0] for s in (1, 3)] == [26, 70]


# the side slices are derived from the geometry, not fixed: other measurements still stretch cleanly at every scale
GEOMETRIES = {
    "round_corners": {"radius": 22.0},
    "blurry_shadow": {"radius": 20.0, "shadow_blur": 2.0},
    "deep_press": {"press": 3.0, "press_side": 3.0},
    "thin_bezel": {"outline": 0.3, "outer_ring": 1.0, "inner_ring": 1.0, "wall": 3.0, "panel_radius": 2.0,
                   "radius": 8.0, "sheen_height": 6.0, "sheen_inset": 3.0},
    "flat_face": {"sheen": 0, "lip": 3.0, "gloss": 5.0, "panel_radius": 3.0, "radius": 12.0},
    "wide_sheen": {"sheen": 1.0, "sheen_fade": 1.0, "sheen_height": 16.0, "sheen_inset": 1.0, "sheen_soft": 2.5},
    "small": {"btn_w": 72.0, "btn_h": 40.0, "body_h": 38.0, "radius": 10.0, "wall": 3.0, "gloss": 2.0, "lip": 4.0,
              "panel_radius": 6.0, "sheen_height": 8.0, "sheen_inset": 3.0, "content": [8, 4, 8, 10]},
}


@pytest.mark.parametrize("scale", (1, 2, 3, 4))
@pytest.mark.parametrize("geo", sorted(GEOMETRIES))
def test_other_geometry_stretches(geo, scale):
    params = dict(GEOMETRIES[geo], style="sun")
    _check_sliced(CB.render(dict(params, layers=["frame", "face", "full"]), scale), scale, geo)
    _check_sliced(CB.render(dict(params, layers=["full"], pressed=True), scale), scale, geo + " pressed")
