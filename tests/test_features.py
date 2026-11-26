"""`ninekit render`, tile-fit resampling, compare's default output, atop / mask, the bend rule, `period:`, noise
`axis`, lgrad / rgrad / roughen, noise on fixed axes (DESIGN 2.2, 2.4, 4, 5)."""
import copy
import json

import numpy as np
import pytest
from PIL import Image

from conftest import load_rgba, piece_spec, render_one, write_spec
from ninekit import NinekitError
from ninekit.cli import main
from ninekit.ninepatch import nine_slice
from ninekit.paint import PaintCtx, noise_tile
from ninekit.render import build
from ninekit.verify import verify_manifest

TAB = {"size": [40, 24], "outputs": ["frame", "face"], "overhang": [0, 0, 0, 2],
       "layers": [{"output": "frame", "shape": {"rect": [0, 0, "w", "h - 2"], "r": 6}, "fill": "#202040"},
                  {"output": "face", "shape": {"rect": [2, 2, "w - 2", "h - 5"], "r": 4},
                   "fill": {"vgrad": [[0, "#c0a0ff"], [1, "#7050d0"]]}}]}
FLAT = [{"shape": {"rect": [0, 0, "w", "h"], "r": 5}, "fill": "#224466"},
        {"shape": {"rect": [1.5, 1.5, "w - 1.5", "h - 1.5"], "r": 3.5}, "fill": "#88aacc"}]


def _spec(tmp_path, pieces, scales=(1, 2, 3), name="spec.yaml"):
    return write_spec(tmp_path, {"ninekit": 1, "name": "t", "scales": list(scales), "pieces": pieces}, name)


# --- 1. render ------------------------------------------------------------------------------------------------------------

def test_render_draws_any_dp_size_with_transparency(tmp_path, capsys):
    path = _spec(tmp_path, {"tab": copy.deepcopy(TAB)})
    out = tmp_path / "r.png"
    assert main(["render", str(path), "tab", "--size", "120x24", "-o", str(out), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["size_px"] == [360, 72] and data["scale"] == "3" and data["outputs"] == ["frame", "face"]
    img = load_rgba(out)
    assert img.shape == (72, 360, 4) and img[0, 0, 3] == 0 and img[36, 180, 3] == 255      # transparent corners
    assert main(["render", str(path), "tab", "--size", "120x24", "--scale", "1", "--pressed", "-o",
                 str(tmp_path / "p.png")]) == 0
    pressed = load_rgba(tmp_path / "p.png")
    plain = load_rgba(tmp_path / "r.png")
    assert pressed.shape == (24, 120, 4)
    assert main(["render", str(path), "tab", "--size", "120x24", "--scale", "1", "-o", str(tmp_path / "n.png")]) == 0
    normal = load_rgba(tmp_path / "n.png")
    assert not np.array_equal(pressed, normal)                     # the face sank 0.92 toward the body's centre
    assert np.array_equal(pressed[:, :2], normal[:, :2])           # the frame stays
    assert plain.shape != normal.shape


def test_render_errors_and_fixed_note(tmp_path, capsys):
    pill = [{"shape": {"rect": [0, 0, "w", "h"], "r": "h / 2"}, "fill": {"vgrad": [[0, "#99ccff"], [1, "#2266aa"]]}}]
    path = _spec(tmp_path, {"pill": {"size": [60, 20], "layers": pill}})
    assert main(["render", str(path), "pill", "--size", "90x30", "-o", str(tmp_path / "x.png")]) == 0
    assert "y is fixed" in capsys.readouterr().err
    assert main(["render", str(path), "pill", "--size", "90x20", "--pressed", "-o", str(tmp_path / "x.png")]) == 2
    assert "no `face` output" in capsys.readouterr().err
    assert main(["render", str(path), "pill", "--size", "90", "-o", str(tmp_path / "x.png")]) == 2
    assert "WxH" in capsys.readouterr().err
    assert main(["render", str(path), "pill", "--size", "90x20", "--scale", "4", "-o", str(tmp_path / "x.png")]) == 2


# --- 2. tile fit ----------------------------------------------------------------------------------------------------------

def test_ninepatch_tiles_whole_tiles_fitted_to_the_length():
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (4, 2 + 5 + 2, 4), dtype=np.uint8)
    img[..., 3] = 255
    exact = nine_slice(img, [2, 0, 2, 0], (2 + 15 + 2, 4), ("tile", "stretch"))
    assert np.array_equal(exact[:, 2:7], img[:, 2:7]) and np.array_equal(exact[:, 12:17], img[:, 2:7])
    fit = nine_slice(img, [2, 0, 2, 0], (2 + 12 + 2, 4), ("tile", "stretch"))      # round(12 / 5) = 2 tiles of 6
    assert np.abs(fit[:, 2:8].astype(int) - fit[:, 8:14]).max() <= 1               # whole, identical tiles
    one = nine_slice(img, [2, 0, 2, 0], (2 + 3 + 2, 4), ("tile", "stretch"))        # at least one tile
    assert one.shape == (4, 7, 4)


# --- 3. compare's default output ------------------------------------------------------------------------------------------

def test_compare_without_out_never_writes_into_the_working_folder(tmp_path, monkeypatch, capsys):
    path = _spec(tmp_path, {"p": {"size": [40, 30], "layers": copy.deepcopy(FLAT)}}, scales=[1])
    ref = tmp_path / "ref.png"
    Image.new("RGBA", (40, 30), (40, 70, 100, 255)).save(ref)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert main(["compare", str(path), "p", str(ref)]) == 0
    assert (tmp_path / "out" / "compare_p.png").is_file() and not list(cwd.iterdir())
    res = build(path, out=tmp_path / "built")
    capsys.readouterr()
    assert main(["compare", str(res.manifest_path), "p", str(ref), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["out"] == str(tmp_path / "built" / "compare_p.png")
    assert not list(cwd.iterdir())


# --- 4. atop and mask -----------------------------------------------------------------------------------------------------

SHAPE = {"rect": [1, 1, "w - 1", "h - 1"], "r": 6}


def _alpha(tmp_path, layers, **piece):
    return render_one(tmp_path, piece_spec(layers, size=(40, 24), scales=[3], slice="none", **piece)
                      ).outputs["main"][..., 3]


def test_shared_edges_thicken_without_atop_or_mask(tmp_path):
    single = _alpha(tmp_path, [{"shape": SHAPE, "fill": "#335577"}])
    stacked = _alpha(tmp_path, [{"shape": SHAPE, "fill": "#335577"},
                                {"shape": SHAPE, "ring": 1, "fill": "#ffffff"}])
    assert (stacked >= single).all() and (stacked > single).sum() > 50          # the fringe accumulates


def test_atop_keeps_the_single_shape_fringe(tmp_path):
    single = _alpha(tmp_path, [{"shape": SHAPE, "fill": "#335577"}])
    stacked = _alpha(tmp_path, [{"shape": SHAPE, "fill": "#335577"},
                                {"shape": SHAPE, "ring": 1, "fill": "#ffffff", "blend": "atop"}])
    assert np.array_equal(stacked, single)
    img = render_one(tmp_path, piece_spec([{"shape": SHAPE, "fill": "#000000"},
                                           {"shape": {"all": True}, "fill": "#ff0000", "blend": "atop"}],
                                          size=(40, 24), scales=[3], slice="none")).outputs["main"]
    assert (img[img[..., 3] > 0][:, 0] == 255).all() and np.array_equal(img[..., 3], single)


def test_mask_cuts_one_silhouette(tmp_path):
    single = _alpha(tmp_path, [{"shape": SHAPE, "fill": "#335577"}])
    # body and ring drawn oversized (past the silhouette), the mask makes the only anti-aliased edge
    stacked = _alpha(tmp_path, [{"shape": {"all": True}, "fill": "#335577"},
                                {"shape": SHAPE, "grow": 0.5, "ring": 1.5, "fill": "#ffffff"},
                                {"shape": {"rect": [0, 0, "w", 2]}, "fill": "#ff0000", "opacity": 0.5}],
                     mask=SHAPE)
    assert np.array_equal(stacked, single)
    soft = _alpha(tmp_path, [{"shape": {"all": True}, "fill": "#335577"}], mask={"shape": SHAPE, "soft": 2})
    assert not np.array_equal(soft, single) and soft[36, 60] == 255
    with pytest.raises(NinekitError, match="mask: unknown key"):
        _alpha(tmp_path, [{"shape": {"all": True}, "fill": "#000000"}], mask={"shape": SHAPE, "blur": 1})
    with pytest.raises(NinekitError, match="cannot be set on a block piece"):
        build(_spec(tmp_path, {"b": {"block": "casual_button", "params": {"style": "mint"}, "mask": SHAPE}}, [1]),
              out=tmp_path / "o")


# --- 5. the bend rule -----------------------------------------------------------------------------------------------------

HATCH_FACE = [{"shape": {"rect": [0, 0, "w", "h"], "r": 6}, "fill": "#0a2040"},
              {"shape": {"rect": [1, 1, "w - 1", "h - 1"], "r": 5},
               "fill": {"vgrad": [[0, "#7cf5ff"], [1, "#0b84b5"]]}},
              {"name": "hatch", "shape": {"union": [          # neon's "///": slope 9/40, 22 % opacity
                  {"polygon": [["w - 25", "h - 8"], ["w - 22", "h - 8"], ["w - 13", 8], ["w - 16", 8]]},
                  {"polygon": [["w - 20", "h - 8"], ["w - 17", "h - 8"], ["w - 8", 8], ["w - 11", 8]]}]},
               "fill": "#0a2040", "opacity": 0.22}]


def test_bend_rule_catches_a_faint_slanted_detail(tmp_path):
    spec = piece_spec(HATCH_FACE, size=(120, 56), scales=[1, 2, 3])
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    assert res.manifest["pieces"]["p"]["stretch"] == ["stretch", "fixed"]        # auto: not stretched vertically
    # explicit slices on a calmer face: every pair of rows passes 8/255, the bend at the hatch does not
    dim = copy.deepcopy(HATCH_FACE)
    dim[1]["fill"] = {"vgrad": [[0, "#40a0c0"], [1, "#205070"]]}
    explicit = piece_spec(dim, size=(120, 56), scales=[3], slice=[30, 12, 30, 12])
    rep = verify_manifest(build(write_spec(tmp_path, explicit, "e.yaml"), out=tmp_path / "e").manifest_path)
    (f,) = rep.files
    assert f.status == "fail" and "bend by" in f.reasons[0] and "second difference" in f.reasons[0]
    plain = piece_spec(dim[:2], size=(120, 56), scales=[3], slice=[30, 12, 30, 12])
    assert verify_manifest(build(write_spec(tmp_path, plain, "g.yaml"), out=tmp_path / "g").manifest_path).ok


# --- 6. period hint -------------------------------------------------------------------------------------------------------

SEGMENTS = [{"shape": {"rect": [0, 0, "w", "h"], "r": 3}, "fill": "#103010"},
            {"shape": {"union": [{"rect": [f"{2 + 6 * i}", 2, f"{6 + 6 * i}", "h - 2"]} for i in range(10)]},
             "fill": "#60e060"}]


def test_period_hint_tiles_a_repeating_shape(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(SEGMENTS, size=(62, 10), scales=[1, 2, 3], stretch=["tile", "fixed"],
                                                period=[6, 0])), out=tmp_path / "o")
    assert not res.problems
    p = res.manifest["pieces"]["p"]
    l, t, r, b = p["slice"]
    assert (p["size"][0] - l - r) % 6 == 0 and p["size"][0] - l - r >= 6
    assert verify_manifest(res.manifest_path).ok


SLANTED = [{"shape": {"rect": [0, 0, "w", "h"], "r": 3}, "fill": "#103010"},
           {"shape": {"union": [{"polygon": [[f"{2 + 6 * i}", "h - 2"], [f"{5 + 6 * i}", "h - 2"], [f"{7 + 6 * i}", 2],
                                             [f"{4 + 6 * i}", 2]]} for i in range(10)]}, "fill": "#60e060"}]


def test_missing_tile_period_is_said_plainly(tmp_path):
    # flat segments without `period:`: any identical columns tile, so build says no period is declared
    res = build(write_spec(tmp_path, piece_spec(SEGMENTS, size=(62, 10), scales=[1, 2], stretch=["tile", "fixed"])),
                out=tmp_path / "w")
    assert any("nothing declares a period on x" in w for w in res.warnings["p"])
    # slanted segments: nothing repeats one grid step later, so no tile region is found
    res = build(write_spec(tmp_path, piece_spec(SLANTED, size=(62, 10), scales=[1, 2], stretch=["tile", "fixed"])),
                out=tmp_path / "o")
    assert any("no tile period found on x" in p and "`period:" in p for p in res.problems["p"])
    rep = verify_manifest(res.manifest_path)
    assert all("x tile region is empty" in f.reasons[0] and "period" in f.reasons[0] for f in rep.files)
    with pytest.raises(NinekitError, match="period x is 6 dp but stretch x is stretch"):
        build(write_spec(tmp_path, piece_spec(SEGMENTS, size=(62, 10), period=[6, 0])), out=tmp_path / "x")


# --- 7. noise axis --------------------------------------------------------------------------------------------------------

def _ctx(scale=2):
    X, Y = np.zeros((1, 1)), np.zeros((1, 1))
    return PaintCtx(ev=lambda v, w="": v if not isinstance(v, str) else float(v), colors={}, mode="color",
                    scale=scale, base=None, X=X, Y=Y, w=1, h=1)


@pytest.mark.parametrize("kind", ["wood", "grain", "value"])
def test_noise_axis_y_is_the_x_pattern_turned(kind):
    cx, cy = _ctx(), _ctx()
    along_x = noise_tile({"kind": kind, "period": [20, 12], "scale": 3, "seed": 4}, cx, "n")
    along_y = noise_tile({"kind": kind, "period": [12, 20], "scale": 3, "seed": 4, "axis": "y"}, cy, "n")
    assert np.array_equal(along_y, along_x.T)
    assert cx.periods == [(40, 24)] and cy.periods == [(24, 40)]
    wood = noise_tile({"kind": "wood", "period": [12, 0], "axis": "y", "seed": 1}, _ctx(), "n")
    assert wood.shape == (1, 24)                     # vertical grain lines: varies along x only
    with pytest.raises(NinekitError, match="axis: y needs an x period"):
        noise_tile({"kind": "wood", "period": [0, 12], "axis": "y"}, _ctx(), "n")
    with pytest.raises(NinekitError, match="axis must be x or y"):
        noise_tile({"kind": "value", "period": [8, 8], "axis": "z"}, _ctx(), "n")


# --- 8. lgrad, rgrad, roughen ---------------------------------------------------------------------------------------------

def _img(tmp_path, fill, size=(20, 10), scale=1, **piece):
    return render_one(tmp_path, piece_spec([{"shape": {"all": True}, "fill": fill}], size=size, scales=[scale],
                                           slice="none", **piece)).outputs["main"]


def test_lgrad_and_rgrad(tmp_path):
    stops = [[0, "#000000"], [1, "#ffffff"]]
    img = _img(tmp_path, {"lgrad": stops})                                  # angle 0: left to right over the canvas
    assert img[0, 0, 0] < 10 and img[0, -1, 0] > 245 and (img[:, 5, 0] == img[0, 5, 0]).all()
    down = _img(tmp_path, {"lgrad": stops, "angle": 90})
    assert down[0, 0, 0] < 20 and down[-1, 0, 0] > 235 and (down[3] == down[3, 0]).all()
    pts = _img(tmp_path, {"lgrad": stops, "from": [5, 0], "to": [15, 0]})
    assert (pts[:, :5, 0] == 0).all() and (pts[:, 15:, 0] == 255).all()
    diag = _img(tmp_path, {"lgrad": stops, "angle": 45}, size=(10, 10))
    assert diag[0, 0, 0] < diag[5, 5, 0] < diag[9, 9, 0] and abs(int(diag[0, 9, 0]) - int(diag[9, 0, 0])) <= 1
    rad = _img(tmp_path, {"rgrad": stops, "center": [10, 5], "radius": 5}, size=(20, 10))
    assert rad[5, 10, 0] < 40 and rad[5, 0, 0] == 255 and rad[5, 7, 0] == rad[5, 12, 0]
    ell = _img(tmp_path, {"rgrad": stops, "center": [10, 10], "radius": 8, "ratio": 0.5}, size=(20, 20))
    assert ell[10, 14, 0] < ell[14, 10, 0]                                  # half the radius vertically
    with pytest.raises(NinekitError, match="angle`, or both"):
        _img(tmp_path, {"lgrad": stops, "angle": 0, "from": [0, 0], "to": [1, 0]})
    with pytest.raises(NinekitError, match="radius and ratio must be > 0"):
        _img(tmp_path, {"rgrad": stops, "radius": 0})


def test_lgrad_across_a_stretch_axis_is_caught(tmp_path):
    layers = [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": {"lgrad": [[0, "#203040"], [1, "#80a0c0"]]}}]
    res = build(write_spec(tmp_path, piece_spec(layers, size=(40, 20), scales=[1, 2])), out=tmp_path / "o")
    assert any("cannot stretch horizontally" in p for p in res.problems["p"])
    assert not verify_manifest(res.manifest_path).ok


def test_roughen(tmp_path):
    plain = [{"shape": {"inset": 2, "r": 3}, "fill": "#d8c090"}]
    torn = [{**plain[0], "roughen": {"amount": 1.2, "period": 12, "seed": 3}}]
    a = render_one(tmp_path, piece_spec(plain, size=(48, 36), scales=[2], slice="none")).outputs["main"]
    b = render_one(tmp_path, piece_spec(torn, size=(48, 36), scales=[2], slice="none")).outputs["main"]
    assert not np.array_equal(a[..., 3], b[..., 3]) and abs(int(a[..., 3].sum()) - int(b[..., 3].sum())) < a.size
    # on tile axes the edge noise repeats with its period: the tile region is whole periods
    res = build(write_spec(tmp_path, piece_spec([{"shape": {"rect": [-2, 3, "w + 2", "h - 3"]}, "fill": "#d8c090",
                                                  "roughen": {"amount": 1, "period": [12, 0], "seed": 2}}],
                                                size=(60, 20), scales=[1, 2], stretch=["tile", "fixed"])),
                out=tmp_path / "o")
    assert not res.problems
    p = res.manifest["pieces"]["p"]
    assert (p["size"][0] - p["slice"][0] - p["slice"][2]) % 12 == 0 and verify_manifest(res.manifest_path).ok
    # on a stretch axis it is a problem
    res = build(write_spec(tmp_path, piece_spec(torn, size=(48, 36), scales=[1]), "s.yaml"), out=tmp_path / "s")
    assert any("roughen varies along x" in p for p in res.problems["p"])
    with pytest.raises(NinekitError, match="roughen needs `amount`"):
        render_one(tmp_path, piece_spec([{**plain[0], "roughen": {"period": 4}}], size=(10, 10), slice="none"))


# --- 9. noise on a fixed axis ---------------------------------------------------------------------------------------------

def test_noise_may_vary_along_a_fixed_axis(tmp_path):
    noise = {"noise": {"kind": "wood", "period": [0, 10], "seed": 5, "stops": [[0, "#5a3417"], [1, "#c08850"]]}}
    layers = [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": "#1c0d04"},
              {"shape": {"inset": 1.5, "r": 3}, "fill": noise}]
    res = build(write_spec(tmp_path, piece_spec(layers, size=(60, 20), scales=[1, 2, 3], stretch=["stretch", "fixed"])),
                out=tmp_path / "o")
    assert not res.problems and res.manifest["pieces"]["p"]["stretch"] == ["stretch", "fixed"]
    assert verify_manifest(res.manifest_path).ok
    res = build(write_spec(tmp_path, piece_spec(layers, size=(60, 20), scales=[1]), "s.yaml"), out=tmp_path / "s")
    assert any("set stretch y to tile (repeat) or fixed" in p for p in res.problems["p"])
