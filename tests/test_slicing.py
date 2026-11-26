"""Slicing (DESIGN 2.4): auto + lossless compaction, explicit slice / slice_px / none, tile regions, ninepatch."""
import numpy as np
import pytest

from conftest import piece_spec, render_one, write_spec
from ninekit import NinekitError
from ninekit.ninepatch import nine_slice
from ninekit.render import build
from ninekit.slicing import auto_slice, compact, tile_run

PANEL = [
    {"shape": {"rect": [1, 2, "w - 1", "h"], "r": 6}, "fill": "#000000", "soft": 2, "opacity": 0.3},
    {"shape": {"rect": [0, 0, "w", "h - 2"], "r": 6}, "fill": {"vgrad": [[0, "#ffeecc"], [1, "#aa8855"]]}},
    {"shape": {"rect": [0, 0, "w", "h - 2"], "r": 6}, "ring": 1, "fill": "#332211"},
]
FLAT = [  # flat colours: identical rows too, so y compacts as well
    {"shape": {"rect": [0, 0, "w", "h"], "r": 5}, "fill": "#224466"},
    {"shape": {"rect": [1.5, 1.5, "w - 1.5", "h - 1.5"], "r": 3.5}, "fill": "#88aacc"},
]


@pytest.mark.parametrize("layers", [PANEL, FLAT])
@pytest.mark.parametrize("scale", [1, 2, 3])
def test_auto_slice_compaction_is_lossless(tmp_path, layers, scale):
    full = render_one(tmp_path, piece_spec(layers, size=(40, 30), scales=[scale], compact=False))
    packed = render_one(tmp_path, piece_spec(layers, size=(40, 30), scales=[scale]))
    assert full.slice_px[0] == packed.slice_px[0] and full.slice_px[2] == packed.slice_px[2]
    w_full = full.outputs["main"].shape[1]
    w_packed = packed.outputs["main"].shape[1]
    l, t, r, b = packed.slice_px
    assert w_packed == l + 2 * scale + r < w_full                 # keep: 2 dp of identical middle
    if layers is FLAT:
        assert packed.outputs["main"].shape[0] == t + 2 * scale + b < full.outputs["main"].shape[0]
    h_full = full.outputs["main"].shape[0]
    for W, H in ((w_full, h_full), (w_full * 2, h_full), (w_full * 3 + 7, h_full * 2 + 3), (l + r + 1, h_full)):
        a = nine_slice(full.outputs["main"], full.slice_px, (W, H))
        c = nine_slice(packed.outputs["main"], packed.slice_px, (W, H))
        assert np.array_equal(a, c), (W, H)
    # the compacted texture at its own size is the original's 9-slice down to that size
    assert packed.size == (w_packed / scale, packed.outputs["main"].shape[0] / scale)


def test_auto_slice_finds_the_round_ends():
    img = np.zeros((10, 30, 4), np.uint8)
    img[:, 8:22] = 200          # middle columns identical
    img[:, :8] = np.arange(8)[None, :, None]
    img[:, 22:] = np.arange(8)[None, :, None] + 50
    img[4:6] = 0                # rows differ: two identical rows only -> smooth fallback
    sl, cx, cy, problems = auto_slice([img], ("stretch", "stretch"), (0, 0))
    assert sl[0] == 8 and sl[2] == 8 and cx and not problems


def test_auto_slice_fails_without_identical_middle_columns():
    img = np.zeros((6, 20, 4), np.uint8)
    img[..., 0] = np.arange(20)[None, :] * 10    # a horizontal gradient
    img[..., 3] = 255
    _, _, _, problems = auto_slice([img], ("stretch", "stretch"), (0, 0))
    assert problems and "cannot stretch horizontally" in problems[0]


def test_auto_y_prefers_identical_rows_then_smooth():
    img = np.zeros((20, 10, 4), np.uint8)
    img[..., 3] = 255
    img[:, :, 0] = (np.arange(20) * 3)[:, None]       # a smooth vertical gradient (3/255 per row)
    sl, _, cy, _ = auto_slice([img], ("stretch", "stretch"), (0, 0))
    assert not cy and sl[1] == 0 and sl[3] == 0       # the whole height is one smooth run, not compactable
    img[8:14, :, 0] = 77                              # 6 identical rows around the centre
    sl, _, cy, _ = auto_slice([img], ("stretch", "stretch"), (0, 0))
    assert cy and (sl[1], 20 - sl[3]) == (8, 14)


def test_outputs_are_sliced_together():
    a = np.zeros((6, 20, 4), np.uint8)
    b = a.copy()
    b[:, 3] = 9      # only the second output has a feature at column 3; the run must avoid it
    sl, _, _, _ = auto_slice([a, b], ("stretch", "stretch"), (0, 0))
    assert sl[0] >= 4
    (pa, pb), sl2 = compact([a, b], sl, 6, True, False)
    assert pa.shape == pb.shape


def test_explicit_slice_slice_px_and_none(tmp_path):
    layers = [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": "#ffffff"}]
    r = render_one(tmp_path, piece_spec(layers, size=(30, 20), scales=[3], slice=[5, 4.5, 5, "h / 4"]))
    assert r.slice_px == [15, round(4.5 * 3), 15, 15]
    assert r.outputs["main"].shape[:2] == (60, 90)          # never compacted
    r = render_one(tmp_path, piece_spec(layers, size=(30, 20), scales=[2],
                                        slice_px=["round(4.2 * scale)", 8, "w_px // 4", "h_px - 31"]))
    assert r.slice_px == [8, 8, 15, 9]
    r = render_one(tmp_path, piece_spec(layers, size=(30, 20), scales=[2], slice="none"))
    assert r.slice_px is None
    with pytest.raises(NinekitError, match="whole number"):
        render_one(tmp_path, piece_spec(layers, size=(30, 20), scales=[2], slice_px=[1.5, 1, 1, 1]))
    with pytest.raises(NinekitError, match="slice must be"):
        render_one(tmp_path, piece_spec(layers, size=(30, 20), scales=[2], slice="sometimes"))


def test_keep_sets_the_compacted_middle_in_dp_on_the_grid(tmp_path):
    for scales, keep, want in (([2], 1.5, {2: 3}), ([2], 0.2, {2: 1}), ([1, 2], 1.5, {1: 2, 2: 4}),
                               ([3], 1, {3: 3})):
        for s, px in want.items():
            r = render_one(tmp_path, piece_spec(FLAT, size=(40, 30), scales=scales, keep=keep), s)
            l, t, r_, b = r.slice_px
            assert r.outputs["main"].shape[1] == l + px + r_, (scales, keep, s)


def test_tile_region_is_whole_periods_and_seamless(tmp_path):
    noise = {"noise": {"kind": "value", "period": [8, 6], "seed": 2, "stops": [[0, "#303030"], [1, "#d0d0d0"]]}}
    layers = [{"shape": {"rect": [0, 0, "w", "h"], "r": 3}, "fill": "#101010"},
              {"shape": {"inset": 1.5, "r": 2}, "fill": noise}]
    for scale in (1, 2, 3):
        r = render_one(tmp_path, piece_spec(layers, size=(40, 30), scales=[scale], stretch=["tile", "tile"]))
        assert not r.problems
        img = r.outputs["main"]
        l, t, rr, b = r.slice_px
        h, w = img.shape[:2]
        assert (w - l - rr) % (8 * scale) == 0 and (h - t - b) % (6 * scale) == 0
        assert np.abs(img[:, w - rr].astype(int) - img[:, l].astype(int)).max() <= 2
        assert np.abs(img[h - b].astype(int) - img[t].astype(int)).max() <= 2


def test_tile_run_none_when_no_repeat():
    img = np.random.default_rng(0).integers(0, 255, (5, 30, 4)).astype(np.int16)
    assert tile_run(img, "x", 7) is None


def test_periodic_paint_on_a_stretch_axis_is_a_problem(tmp_path):
    noise = {"noise": {"kind": "value", "period": [8, 0], "seed": 2}}
    r = render_one(tmp_path, piece_spec([{"shape": {"all": True}, "fill": noise}], size=(40, 10), scales=[1]))
    assert any("set stretch x to tile" in p for p in r.problems)


def test_ninepatch_identity_corners_and_tile():
    rng = np.random.default_rng(3)
    img = rng.integers(0, 255, (12, 16, 4), dtype=np.uint8)
    img[..., 3] = 255
    assert np.array_equal(nine_slice(img, [4, 3, 5, 2], (16, 12)), img)
    big = nine_slice(img, [4, 3, 5, 2], (40, 30))
    assert np.array_equal(big[:3, :4], img[:3, :4]) and np.array_equal(big[-2:, -5:], img[-2:, -5:])
    tiled = nine_slice(img, [4, 3, 5, 2], (4 + 5 + 7 * 3, 12), ("tile", "stretch"))
    assert np.array_equal(tiled[:, 4:11], img[:, 4:11]) and np.array_equal(tiled[:, 11:18], img[:, 4:11])
    small = nine_slice(img, [4, 3, 5, 2], (6, 4))
    assert small.shape == (4, 6, 4)
    whole = nine_slice(img, None, (32, 24))
    assert whole.shape == (24, 32, 4)


def test_build_writes_compacted_sizes_to_the_manifest(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(FLAT, size=(40, 30), scales=[1, 2])), out=tmp_path / "o")
    p = res.manifest["pieces"]["p"]
    for sk, s in (("1", 1), ("2", 2)):
        e = p["outputs"]["main"][sk]
        l, t, r, b = e["slice_px"]
        assert e["size_px"] == [l + 2 * s + r, t + 2 * s + b]
        # one dp size and one dp slice for every file
        assert e["size_px"] == [round(v * s) for v in p["size"]] and e["slice_px"] == [round(v * s) for v in p["slice"]]
    e2 = p["outputs"]["main"]["2"]
    assert p["size"] == [round(e2["size_px"][0] / 2, 2), round(e2["size_px"][1] / 2, 2)]
    assert p["slice"] == [round(v / 2, 2) for v in e2["slice_px"]]
