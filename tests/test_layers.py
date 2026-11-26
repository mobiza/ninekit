"""Layers, paints, blends, outputs, modes and multi-scale rendering (DESIGN 2.2, 2.5, 1)."""
import numpy as np
import pytest
from PIL import Image

from conftest import load_rgba, piece_spec, render_one, write_spec
from ninekit import NinekitError
from ninekit.canvas import Canvas
from ninekit.paint import PaintCtx, noise_tile
from ninekit.render import build, coverage

ALL = {"all": True}


def whole(layers, size=(8, 8), scale=1, **piece):
    return piece_spec(layers, size=size, scales=[scale], slice="none", **piece)


def px(tmp_path, layers, size=(8, 8), scale=1, **piece):
    return render_one(tmp_path, whole(layers, size, scale, **piece)).outputs["main"]


# --- paints -------------------------------------------------------------------------------------------------------------

def test_solid_hex_and_alpha_and_names(tmp_path):
    assert tuple(px(tmp_path, [{"shape": ALL, "fill": "#123456"}])[0, 0]) == (0x12, 0x34, 0x56, 255)
    assert tuple(px(tmp_path, [{"shape": ALL, "fill": "#12345680"}])[0, 0]) == (0x12, 0x34, 0x56, 128)
    spec = whole([{"shape": ALL, "fill": "accent"}])
    spec["colors"] = {"accent": "base", "base": "#ff8000"}
    assert tuple(render_one(tmp_path, spec).outputs["main"][0, 0]) == (255, 128, 0, 255)
    with pytest.raises(NinekitError, match="unknown colour"):
        px(tmp_path, [{"shape": ALL, "fill": "nope"}])
    with pytest.raises(NinekitError, match="shade number"):
        px(tmp_path, [{"shape": ALL, "fill": 0.5}])


def test_vgrad_is_linear_per_channel_and_from_to(tmp_path):
    img = px(tmp_path, [{"shape": ALL, "fill": {"vgrad": [[0, "#000000"], [1, "#ffffff"]], "from": 2, "to": 6}}],
             size=(2, 8))
    col = img[:, 0, 0].tolist()
    # texel centres 0.5 .. 7.5 dp: clamped above 2 and below 6, linear between
    expect = [round(min(max((y + 0.5 - 2) / 4, 0), 1) * 255) for y in range(8)]
    assert col == expect
    # default span is the whole canvas, named gradients come from colors
    spec = whole([{"shape": ALL, "fill": {"vgrad": "g"}}], size=(1, 4))
    spec["colors"] = {"g": [[0, "#000000"], [1, "#ffffff"]]}
    assert render_one(tmp_path, spec).outputs["main"][:, 0, 0].tolist() == [32, 96, 159, 223]


def test_vgrad_alpha_stops_interpolate_premultiplied(tmp_path):
    img = px(tmp_path, [{"shape": ALL, "fill": {"vgrad": [[0, "#ff000000"], [1, "#ff0000ff"]]}}], size=(1, 4))
    assert img[:, 0, 0].tolist() == [255] * 4          # no darkening toward the transparent end
    assert img[:, 0, 3].tolist() == [32, 96, 159, 223]


def test_depth_paints_by_distance_inside(tmp_path):
    img = px(tmp_path, [{"shape": {"rect": [0, 0, 10, 10]}, "fill": {"depth": [[0, "#000000"], [4, "#ffffff"]]}}],
             size=(10, 10))
    row = img[5, :, 0].tolist()
    # depth at texel centres: 0.5, 1.5, ... from the left edge
    assert row[:5] == [round(min(d / 4, 1) * 255) for d in (0.5, 1.5, 2.5, 3.5, 4.5)]
    assert row == row[::-1]


def _ctx(scale=2):
    X, Y = np.zeros((1, 1)), np.zeros((1, 1))
    return PaintCtx(ev=lambda v, w="": v if not isinstance(v, str) else float(v), colors={}, mode="color",
                    scale=scale, base=None, X=X, Y=Y, w=1, h=1)


@pytest.mark.parametrize("kind", ["value", "grain", "wood"])
def test_noise_tiles_with_the_period(kind):
    ctx = _ctx(2)
    tile = noise_tile({"kind": kind, "period": [12, 8], "scale": 3, "seed": 5}, ctx, "n")
    assert tile.shape == (16, 24)
    assert ctx.periods == [(24, 16)]
    assert tile.min() >= 0 and tile.max() <= 1 and tile.std() > 0.01
    # deterministic
    assert np.array_equal(tile, noise_tile({"kind": kind, "period": [12, 8], "scale": 3, "seed": 5}, _ctx(2), "n"))
    # value noise is smooth across the wrap: the step over the seam is like any other step
    if kind == "value":
        steps = np.abs(np.diff(np.concatenate([tile, tile[:, :1]], axis=1), axis=1))
        assert steps[:, -1].max() <= steps[:, :-1].max() + 1e-9


def test_noise_axis_without_period_is_constant_and_wood_needs_y():
    t = noise_tile({"kind": "value", "period": [0, 10], "seed": 1}, _ctx(1), "n")
    assert t.shape == (10, 1)
    with pytest.raises(NinekitError, match="y period"):
        noise_tile({"kind": "wood", "period": [10, 0]}, _ctx(1), "n")
    with pytest.raises(NinekitError, match="kind"):
        noise_tile({"kind": "plasma", "period": [10, 10]}, _ctx(1), "n")


def test_noise_paint_is_periodic_in_the_texture(tmp_path):
    fill = {"noise": {"kind": "value", "period": [6, 5], "seed": 3, "stops": [[0, "#000000"], [1, "#ffffff"]]}}
    img = px(tmp_path, [{"shape": ALL, "fill": fill}], size=(20, 16), scale=2)
    assert np.array_equal(img[:, :-12], img[:, 12:])      # 6 dp * 2 = 12 px
    assert np.array_equal(img[:-10], img[10:])            # 5 dp * 2 = 10 px


def test_image_tile_paint(tmp_path):
    rng = np.random.default_rng(0)
    Image.fromarray(rng.integers(0, 255, (5, 7, 4), dtype=np.uint8), "RGBA").save(tmp_path / "tex.png")
    img = px(tmp_path, [{"shape": ALL, "fill": {"image": "tex.png", "size": [3, 2]}}], size=(16, 12), scale=2)
    assert np.array_equal(img[:, :-6], img[:, 6:]) and np.array_equal(img[:-4], img[4:])
    once = px(tmp_path, [{"shape": ALL, "fill": {"image": "tex.png", "size": [3, 2], "tile": False}}],
              size=(16, 12), scale=2)
    assert once[:4, :6, 3].any() and not once[4:, :, 3].any() and not once[:, 6:, 3].any()
    with pytest.raises(NinekitError, match="cannot read image"):
        px(tmp_path, [{"shape": ALL, "fill": {"image": "missing.png"}}])


# --- edge, coverage and layer options ---------------------------------------------------------------------------------

def test_coverage_linear_is_the_one_texel_ramp():
    d = np.linspace(-2, 2, 41)
    for scale, soft in ((3, 0.0), (3, 1.1), (1, 0.45)):
        width = max(soft, 1.0 / scale)
        assert np.array_equal(coverage(d, soft, "linear", scale), np.clip(0.5 - d / width, 0.0, 1.0))
    sm = coverage(d, 2.0, "smooth", 1)
    lin = coverage(d, 2.0, "linear", 1)
    assert np.allclose(sm, lin * lin * (3 - 2 * lin))
    ex = coverage(d, 2.0, "exp", 1)
    assert (ex[d <= 0] == 1).all() and np.all(np.diff(ex[d > 0]) < 0) and ex[-1] == pytest.approx(np.exp(-3))


def test_grow_ring_soft_offset_opacity(tmp_path):
    base = {"shape": {"rect": [4, 4, 12, 12]}, "fill": "#ffffff"}
    a = px(tmp_path, [base], size=(16, 16))[..., 3]
    assert a[8, 3] == 0 and a[8, 4] == 255
    g = px(tmp_path, [{**base, "grow": 1}], size=(16, 16))[..., 3]
    assert g[8, 3] == 255 and g[8, 2] == 0
    r = px(tmp_path, [{**base, "ring": 1}], size=(16, 16))[..., 3]
    assert r[8, 4] == 255 and r[8, 5] == 0 and r[4, 8] == 255 and r[8, 8] == 0
    s = px(tmp_path, [{**base, "soft": 4}], size=(16, 16))[..., 3]
    assert 0 < s[8, 3] < 255 and 0 < s[8, 4] < 255
    o = px(tmp_path, [{**base, "offset": [2, -1]}], size=(16, 16))[..., 3]
    assert np.array_equal(o[:-1, 2:][3:14], a[1:, :-2][3:14])
    h = px(tmp_path, [{**base, "opacity": 0.5}], size=(16, 16))[..., 3]
    assert h[8, 8] == 128


def test_offset_moves_the_shape_not_the_paint(tmp_path):
    fill = {"vgrad": [[0, "#000000"], [1, "#ffffff"]]}
    a = px(tmp_path, [{"shape": {"rect": [0, 0, 4, 8]}, "fill": fill}], size=(8, 8))
    b = px(tmp_path, [{"shape": {"rect": [0, 0, 4, 8]}, "fill": fill, "offset": [4, 0]}], size=(8, 8))
    assert np.array_equal(a[:, :4], b[:, 4:])


def test_clip_multiplies_coverage(tmp_path):
    img = px(tmp_path, [{"shape": ALL, "fill": "#ffffff", "clip": {"rect": [0, 0, 8, 3]}}], size=(8, 8))
    assert img[:3, :, 3].min() == 255 and img[3:, :, 3].max() == 0


def test_when_skips_layers(tmp_path):
    spec = piece_spec([{"shape": ALL, "fill": "#ff0000"},
                       {"shape": ALL, "fill": "#0000ff", "when": "scale >= 2"}], size=(4, 4), scales=[1, 2],
                      slice="none")
    assert tuple(render_one(tmp_path, spec, 1).outputs["main"][0, 0]) == (255, 0, 0, 255)
    assert tuple(render_one(tmp_path, spec, 2).outputs["main"][0, 0]) == (0, 0, 255, 255)


# --- blends --------------------------------------------------------------------------------------------------------------

def reference_put(rgb, a, colour, alpha):
    # straight-alpha source-over, written out: Canvas.put (normal) must keep this exact float operation order
    alpha = np.clip(alpha, 0.0, 1.0)
    col = colour if isinstance(colour, np.ndarray) and colour.ndim == 3 else np.broadcast_to(colour, rgb.shape)
    out_a = alpha + a * (1.0 - alpha)
    safe = np.where(out_a > 1e-6, out_a, 1.0)
    rgb = (col * alpha[..., None] + rgb * (a * (1.0 - alpha))[..., None]) / safe[..., None]
    return rgb, out_a


def test_normal_blend_matches_the_reference_put():
    rng = np.random.default_rng(1)
    c = Canvas(5, 4, 3)
    rgb, a = c.rgb.copy(), c.a.copy()
    for _ in range(4):
        col = rng.random((4, 5, 3)) if rng.random() < 0.5 else rng.random(3)
        al = rng.random((4, 5)) * 1.2 - 0.1
        c.put(col, al)
        rgb, a = reference_put(rgb, a, col, al)
        assert np.array_equal(c.rgb, rgb) and np.array_equal(c.a, a)


def _two(tmp_path, top, blend, bottom="#4080c0"):
    return px(tmp_path, [{"shape": ALL, "fill": bottom}, {"shape": ALL, "fill": top, "blend": blend}], size=(2, 2))[0, 0]


def test_blend_modes(tmp_path):
    assert tuple(_two(tmp_path, "#404040", "add")) == (0x80, 0xC0, 0xFF, 255)
    assert tuple(_two(tmp_path, "#ffffff", "multiply")) == (0x40, 0x80, 0xC0, 255)
    assert tuple(_two(tmp_path, "#808080", "multiply")) == (0x20, 0x40, 0x60, 255)
    assert tuple(_two(tmp_path, "#000000", "screen")) == (0x40, 0x80, 0xC0, 255)
    assert tuple(_two(tmp_path, "#ffffff", "screen")) == (255, 255, 255, 255)
    erased = _two(tmp_path, "#00000080", "erase")
    assert erased[3] == 127 and tuple(erased[:3]) == (0x40, 0x80, 0xC0)
    # add on an empty canvas is plain paint; its alpha sums and clamps
    img = px(tmp_path, [{"shape": ALL, "fill": "#ff000080", "blend": "add"},
                        {"shape": ALL, "fill": "#0000ffc0", "blend": "add"}], size=(2, 2))[0, 0]
    assert img[3] == 255 and img[0] > 0 and img[2] > 0
    with pytest.raises(NinekitError, match="blend"):
        _two(tmp_path, "#000000", "overlay")


# --- outputs, modes, file names, scales ----------------------------------------------------------------------------------

def test_multiple_outputs_stack_on_one_canvas(tmp_path):
    spec = piece_spec([{"shape": {"rect": [0, 0, "w", "h"], "r": 3}, "fill": "#202020", "output": "frame"},
                       {"shape": {"rect": [1, 1, "w - 1", "h - 2"], "r": 2}, "fill": "#e0e0e0", "output": "face"}],
                      size=(20, 12), scales=[1, 2], outputs=["frame", "face"])
    res = build(write_spec(tmp_path, spec), out=tmp_path / "out")
    names = sorted(f["file"] for f in res.files)
    assert names == ["p_face@1x.png", "p_face@2x.png", "p_frame@1x.png", "p_frame@2x.png"]
    m = res.manifest["pieces"]["p"]
    assert m["stack"] == ["frame", "face"]
    for s in ("1", "2"):
        assert m["outputs"]["frame"][s]["size_px"] == m["outputs"]["face"][s]["size_px"]
        assert m["outputs"]["frame"][s]["slice_px"] == m["outputs"]["face"][s]["slice_px"]
    face = load_rgba(tmp_path / "out" / "p_face@2x.png")
    assert face[0, :, 3].max() == 0          # the face leaves the frame's top edge alone
    bad = piece_spec([{"shape": ALL, "fill": "#fff", "output": "nope"}], outputs=["frame"])
    with pytest.raises(NinekitError, match="not one of the piece's outputs"):
        render_one(tmp_path, bad)


def test_shade_mode(tmp_path):
    spec = whole([{"shape": ALL, "fill": 0.25}, {"shape": {"rect": [0, 0, 8, 4]}, "fill": {"vgrad": [[0, 1], [1, 0.5]]}}],
                 mode="shade")
    r = render_one(tmp_path, spec)
    img = r.outputs["main"]
    assert r.mode == "shade"
    assert (img[..., 0] == img[..., 1]).all() and (img[..., 1] == img[..., 2]).all()
    assert img[7, 0, 0] == round(0.25 * 255)
    spec["colors"] = {"dark": 0.1}
    spec["pieces"]["p"]["layers"][0]["fill"] = "dark"
    assert render_one(tmp_path, spec).outputs["main"][7, 0, 0] == round(0.1 * 255)
    spec["pieces"]["p"]["layers"][0]["fill"] = "#ffffff"
    with pytest.raises(NinekitError, match="mode: shade"):
        render_one(tmp_path, spec)
    res = build(write_spec(tmp_path, whole([{"shape": ALL, "fill": 1}], mode="shade")), out=tmp_path / "o")
    assert res.manifest["pieces"]["p"]["mode"] == "shade"


def test_file_template_tokens(tmp_path):
    layers = [{"shape": ALL, "fill": "#ffffff"}]
    one = build(write_spec(tmp_path, piece_spec(layers, scales=[3], slice="none")), out=tmp_path / "a")
    assert [f["file"] for f in one.files] == ["p.png"]
    many = build(write_spec(tmp_path, piece_spec(layers, scales=[1, 1.5, 2], slice="none")), out=tmp_path / "b")
    assert [f["file"] for f in many.files] == ["p@1x.png", "p@1.5x.png", "p@2x.png"]
    spec = piece_spec(layers, scales=[1, 2], slice="none", outputs=["frame", "face"])
    spec["file"] = "ui/{scale}/{piece}{output}.png"
    res = build(write_spec(tmp_path, spec), out=tmp_path / "c")
    assert sorted(f["file"] for f in res.files) == ["ui/@1x/p_face.png", "ui/@1x/p_frame.png", "ui/@2x/p_face.png",
                                                    "ui/@2x/p_frame.png"]
    assert (tmp_path / "c" / "ui" / "@2x" / "p_face.png").exists()
    # --scales keeps the spec's naming (stable file names)
    sub = build(write_spec(tmp_path, piece_spec(layers, scales=[1, 2], slice="none")), out=tmp_path / "d", scales=[2])
    assert [f["file"] for f in sub.files] == ["p@2x.png"]


def test_every_scale_is_rendered_natively(tmp_path):
    spec = piece_spec([{"shape": {"circle": [8, 8, 6]}, "fill": "#ffffff"}], size=(16, 16), scales=[1, 3],
                      slice="none")
    a1 = render_one(tmp_path, spec, 1).outputs["main"][..., 3].astype(float) / 255
    a3 = render_one(tmp_path, spec, 3).outputs["main"][..., 3].astype(float) / 255
    assert a1.shape == (16, 16) and a3.shape == (48, 48)
    # one texel of anti-aliasing at each scale: the 3x edge is three times sharper, not a 3x upscale of 1x
    ys, xs = np.mgrid[0:48, 0:48]
    d = np.hypot((xs + 0.5) / 3 - 8, (ys + 0.5) / 3 - 8) - 6
    assert np.allclose(a3, np.clip(0.5 - d * 3, 0, 1), atol=0.5 / 255 + 1e-9)
    partial3 = ((a3 > 0) & (a3 < 1)).sum()
    partial1 = ((a1 > 0) & (a1 < 1)).sum()
    assert partial3 < partial1 * 3 * 1.5   # an upscale would have ~9x the partial texels


def test_size_snaps_to_the_grid_and_w_follows(tmp_path):
    spec = piece_spec([{"shape": {"rect": [0, 0, "w", "h"]}, "fill": "#ffffff"}], size=[10.5, 4], scales=[1, 3],
                      slice="none")
    r1 = render_one(tmp_path, spec, 1)
    assert r1.outputs["main"].shape[:2] == (4, 10)     # the 1 dp grid of [1, 3]: round(10.5) = 10 (banker's)
    assert r1.outputs["main"][..., 3].min() == 255     # w = 10 dp: the rect fills the canvas
    r3 = render_one(tmp_path, spec, 3)
    assert r3.outputs["main"].shape[:2] == (12, 30)    # the same 10 dp at 3x (not round(31.5) = 32 texels)
    assert any("snapped to 10 x 4 dp" in w for w in r3.warnings)
    # one scale: the grid is one texel, the old per-scale rounding, and nothing is reported
    r = render_one(tmp_path, {**spec, "scales": [3]}, 3)
    assert r.outputs["main"].shape[:2] == (12, 32) and not r.warnings
