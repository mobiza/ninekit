"""The dp grid (DESIGN 2.4): one dp size and one dp slice for every file of a piece, fixed axes, verify's dp and
empty-region rules, block params, `compare`."""
import copy
import json
from fractions import Fraction

import numpy as np
import pytest
from PIL import Image

from conftest import ROOT, load_rgba, piece_spec, render_one, write_spec
from ninekit import NinekitError
from ninekit.cli import main
from ninekit.manifest import load_manifest, write_manifest
from ninekit.ninepatch import nine_slice_premul, unpremultiply
from ninekit.render import build
from ninekit.scaffold import scaffold
from ninekit.slicing import plan_slices
from ninekit.spec import SpecError, dp_grid, load_spec
from ninekit.verify import verify, verify_manifest

BASICS = ROOT / "examples" / "basics" / "basics.yaml"
PILL = [{"shape": {"rect": [0, 0, "w", "h"], "r": "h / 2"}, "fill": {"vgrad": [[0, "#99ccff"], [1, "#2266aa"]]}}]
PANEL = [  # a slow gradient face: a few identical rows at 3x, none at 1x (the old y rule split here)
    {"shape": {"rect": [0, 0, "w", "h"], "r": 8}, "fill": "#2b2140"},
    {"shape": {"rect": [1, 1, "w - 1", "h - 1"], "r": 7}, "fill": {"vgrad": [[0, "#fff7e8"], [1, "#ead8b8"]]}},
]
FLAT = [{"shape": {"rect": [0, 0, "w", "h"], "r": 5}, "fill": "#224466"},
        {"shape": {"rect": [1.5, 1.5, "w - 1.5", "h - 1.5"], "r": 3.5}, "fill": "#88aacc"}]


def dp_mismatches(manifest: dict) -> list:
    bad = []
    for name, p in manifest["pieces"].items():
        for o, per in p["outputs"].items():
            for sk, e in per.items():
                s = float(sk)
                if e["size_px"] != [round(v * s) for v in p["size"]]:
                    bad.append((name, o, sk, "size", e["size_px"], p["size"]))
                if p["slice"] is not None and e["slice_px"] != [round(v * s) for v in p["slice"]]:
                    bad.append((name, o, sk, "slice", e["slice_px"], p["slice"]))
                if p["slice"] is not None and any(abs(v * s - round(v * s)) > 0.02 for v in p["slice"]):
                    bad.append((name, o, sk, "not on the grid", p["slice"]))
    return bad


# --- the grid -------------------------------------------------------------------------------------------------------------

def test_dp_grid_is_the_smallest_step_whole_at_every_scale():
    assert dp_grid([1, 2, 3]) == 1
    assert dp_grid([3]) == Fraction(1, 3)
    assert dp_grid([2, 4]) == Fraction(1, 2)
    assert dp_grid([1.5, 3]) == Fraction(2, 3)
    assert dp_grid([1, 1.5, 2, 3, 4]) == 2


def test_grid_key_coarser_multiple_only(tmp_path):
    spec = piece_spec(FLAT, size=(31.4, 20.2), scales=[3])
    assert load_spec(write_spec(tmp_path, spec)).grid == Fraction(1, 3)
    spec["grid"] = 1                                      # web-friendly whole dp at 3x only
    s = load_spec(write_spec(tmp_path, spec))
    assert s.grid == 1
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    p = res.manifest["pieces"]["p"]
    e = p["outputs"]["main"]["3"]
    assert all(float(v).is_integer() for v in p["slice"]) and all(float(v).is_integer() for v in p["size"])
    assert e["slice_px"] == [int(v * 3) for v in p["slice"]]
    assert res.warnings["p"] and "snapped to 31 x 20 dp" in res.warnings["p"][0]
    spec["grid"] = "1/3"
    assert load_spec(write_spec(tmp_path, spec)).grid == Fraction(1, 3)
    for bad in (0.5, 0, "x"):
        spec["grid"] = bad
        with pytest.raises(SpecError, match="grid"):
            load_spec(write_spec(tmp_path, spec))
    spec.pop("grid")
    spec["scales"] = [1, 1.33]
    with pytest.raises(SpecError, match="share no dp grid"):
        load_spec(write_spec(tmp_path, spec))


# --- one dp slice and size per piece --------------------------------------------------------------------------------------

def test_basics_and_the_scaffold_are_dp_consistent(tmp_path):
    scaffold(tmp_path / "new")
    for spec in (BASICS, tmp_path / "new" / "ninekit.yaml"):
        res = build(spec, out=tmp_path / spec.stem)
        assert not res.problems and not res.warnings
        assert not dp_mismatches(res.manifest), dp_mismatches(res.manifest)
        assert verify_manifest(res.manifest_path).ok


def test_slow_gradient_y_takes_the_long_smooth_run_at_every_scale(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(PANEL, size=(40, 48), scales=[1, 2, 3])), out=tmp_path / "o")
    p = res.manifest["pieces"]["p"]
    assert not dp_mismatches(res.manifest)
    l, t, r, b = p["slice"]
    assert p["size"][1] - t - b >= 30                    # the smooth face, not 3 identical rows at 3x
    assert p["stretch"] == ["stretch", "stretch"]
    assert verify_manifest(res.manifest_path).ok


def test_flat_y_keeps_its_identical_rows_and_compacts_in_dp(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(FLAT, size=(40, 30), scales=[1, 2, 3])), out=tmp_path / "o")
    p = res.manifest["pieces"]["p"]
    assert not dp_mismatches(res.manifest)
    l, t, r, b = p["slice"]
    assert p["size"] == [l + 2 + r, t + 2 + b]           # keep: 2 dp of identical middle on both axes
    assert verify_manifest(res.manifest_path).ok


def test_scales_subset_writes_the_same_files(tmp_path):
    path = write_spec(tmp_path, piece_spec(PANEL, size=(40, 48), scales=[1, 2, 3]))
    build(path, out=tmp_path / "all")
    build(path, out=tmp_path / "two", scales=[2])
    assert np.array_equal(load_rgba(tmp_path / "all" / "p@2x.png"), load_rgba(tmp_path / "two" / "p@2x.png"))


def test_scale_dependent_size_is_a_problem(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(FLAT, size=("10 + scale * 3", 20), scales=[1, 2, 3])),
                out=tmp_path / "o")
    assert any("size differs per scale" in p for p in res.problems["p"])
    rep = verify_manifest(res.manifest_path)
    assert not rep.ok and any("do not share one dp" in r for f in rep.files for r in f.reasons)


def test_off_grid_explicit_slice_is_warned_not_moved(tmp_path):
    spec = piece_spec(FLAT, size=(40, 30), scales=[1, 2, 3], slice=[6.5, 6, 6.5, 6])
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    assert not res.problems and "not on the 1 dp grid" in res.warnings["p"][0]
    p = res.manifest["pieces"]["p"]
    assert p["outputs"]["main"]["2"]["slice_px"] == [13, 12, 13, 12]      # 6.5 x 2, exactly as written
    assert p["outputs"]["main"]["1"]["slice_px"] == [6, 6, 6, 6]          # round(6.5) per scale, not moved
    rep = verify(write_spec(tmp_path, spec))
    assert rep.ok and rep.warnings["p"]                                   # a warning, not a failure
    assert any("do not share one dp" in w for f in rep.files for w in f.warnings)


def test_noise_periods_snap_to_the_grid(tmp_path):
    noise = {"noise": {"kind": "value", "period": [7.5, 0], "seed": 2, "stops": [[0, "#303030"], [1, "#d0d0d0"]]}}
    layers = [{"shape": {"rect": [0, 0, "w", "h"], "r": 3}, "fill": "#101010"},
              {"shape": {"inset": 1.5, "r": 2}, "fill": noise}]
    res = build(write_spec(tmp_path, piece_spec(layers, size=(60, 20), scales=[1, 2, 3], stretch=["tile", "stretch"])),
                out=tmp_path / "o")
    assert not res.problems
    p = res.manifest["pieces"]["p"]
    assert not dp_mismatches(res.manifest)
    l, t, r, b = p["slice"]
    assert (p["size"][0] - l - r) % 8 == 0              # round(7.5) = 8 dp on the 1 dp grid, at every scale
    assert verify_manifest(res.manifest_path).ok


# --- fixed axes -------------------------------------------------------------------------------------------------------------

def test_full_pill_is_fixed_in_y_with_one_grid_step(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(PILL, size=(60, 20), scales=[1, 2, 3])), out=tmp_path / "o")
    p = res.manifest["pieces"]["p"]
    assert p["stretch"] == ["stretch", "fixed"] and not res.problems
    for sk, e in p["outputs"]["main"].items():
        h = e["size_px"][1]
        assert h - e["slice_px"][1] - e["slice_px"][3] == int(sk)       # exactly one 1 dp step in the middle
    assert verify_manifest(res.manifest_path).ok


def test_explicit_fixed_axis(tmp_path):
    vpill = [{"shape": {"rect": [0, 0, "w", "h"], "r": "w / 2"}, "fill": "#aa3366"}]
    res = build(write_spec(tmp_path, piece_spec(vpill, size=(20, 40), scales=[1, 3], stretch=["fixed", "stretch"])),
                out=tmp_path / "o")
    p = res.manifest["pieces"]["p"]
    assert p["stretch"] == ["fixed", "stretch"] and not res.problems
    assert p["size"][0] - p["slice"][0] - p["slice"][2] == 1
    assert verify_manifest(res.manifest_path).ok
    res = build(write_spec(tmp_path, piece_spec(vpill, size=(20, 40), scales=[2], stretch="fixed")), out=tmp_path / "f")
    assert res.manifest["pieces"]["p"]["stretch"] == ["fixed", "fixed"]
    with pytest.raises(NinekitError, match="stretch | tile | fixed"):
        build(write_spec(tmp_path, piece_spec(vpill, size=(20, 40), stretch=["fixed", "bend"])), out=tmp_path / "x")


def test_plan_slices_works_in_grid_steps():
    img1 = np.zeros((10, 20, 4), np.int16)
    img1[..., 3] = 255
    img1[:, :4, 0] = 50                                   # a 4 dp feature on the left
    img3 = np.repeat(np.repeat(img1, 3, axis=0), 3, axis=1)
    img3[:, 12, 0] = 50                                   # at 3x it reaches 1/3 dp further
    cuts, problems = plan_slices({1: img1, 3: img3}, (20, 10), {1: 1, 3: 3}, ["stretch", "stretch"], {1: (0, 0), 3: (0, 0)})
    assert not problems and cuts[0].lo == 5               # 13 texels at 3x = 4.33 dp -> ceil to 5 dp
    assert cuts[1].mode == "stretch" and cuts[1].identical


# --- verify ----------------------------------------------------------------------------------------------------------------

def test_verify_manifest_fails_a_piece_that_cannot_stretch(tmp_path):
    gloss = PILL[:0] + [{"shape": {"rect": [0, 0, "w", "h"], "r": 6}, "fill": "#336699"},
                        {"shape": {"ellipse": ["w / 2", 5, 6, 2]}, "fill": "#ffffff", "opacity": 0.6}]
    res = build(write_spec(tmp_path, piece_spec(gloss, size=(60, 20), scales=[1, 2])), out=tmp_path / "o")
    assert res.problems
    rep = verify_manifest(res.manifest_path)            # the manifest alone fails too (no spec problems here)
    assert not rep.ok
    assert all(f.status == "fail" and "x stretch region is empty" in f.reasons[0] for f in rep.files)


def test_verify_fails_auto_files_that_leave_the_dp_grid_and_warns_others(tmp_path):
    res = build(write_spec(tmp_path, piece_spec(FLAT, size=(40, 30), scales=[1, 2])), out=tmp_path / "o")
    m = load_manifest(res.manifest_path)
    m["pieces"]["p"]["outputs"]["main"]["2"]["slice_px"][0] += 1
    write_manifest(res.manifest_path, m)
    rep = verify_manifest(res.manifest_path)
    (f,) = [f for f in rep.files if f.scale == "2"]
    assert f.status == "fail" and any("do not share one dp" in r for r in f.reasons)
    m["pieces"]["p"]["slicing"] = "slice_px"
    write_manifest(res.manifest_path, m)
    (f,) = [f for f in verify_manifest(res.manifest_path).files if f.scale == "2"]
    assert f.status == "ok" and any("do not share one dp" in w for w in f.warnings)


def test_verify_and_preview_take_a_theme(tmp_path, capsys):
    spec = piece_spec(copy.deepcopy(FLAT), size=(40, 30), scales=[1, 2])
    spec["colors"] = {"accent": "#224466"}
    spec["pieces"]["p"]["layers"][0]["fill"] = "accent"
    path = write_spec(tmp_path, spec)
    theme = tmp_path / "theme.yaml"
    theme.write_text("ninekit: 1\ncolors: {accent: \"#aa2200\"}\n")
    assert main(["verify", str(path), "--theme", str(theme)]) == 0
    assert main(["preview", str(path), "--theme", str(theme), "-o", str(tmp_path / "sheet.png")]) == 0
    sheet = load_rgba(tmp_path / "sheet.png")
    assert ((sheet[..., 0] == 0xAA) & (sheet[..., 1] == 0x22) & (sheet[..., 2] == 0)).any()
    res = build(path, out=tmp_path / "o")
    capsys.readouterr()
    assert main(["verify", str(res.manifest_path), "--theme", str(theme)]) == 2
    assert "applies to a SPEC" in capsys.readouterr().err
    assert main(["verify", str(tmp_path / "o")]) == 0                     # a folder holding ninekit.json


def test_preview_marks_failing_pieces(tmp_path):
    gloss = [{"shape": {"rect": [0, 0, "w", "h"], "r": 6}, "fill": "#336699"},
             {"shape": {"ellipse": ["w / 2", 5, 6, 2]}, "fill": "#ffffff", "opacity": 0.6}]
    from ninekit.preview import FAIL_RGB, preview

    out = preview(write_spec(tmp_path, piece_spec(gloss, size=(60, 20), scales=[1, 2])), tmp_path / "s.png")
    sheet = load_rgba(out)[..., :3]
    assert (np.abs(sheet.astype(int) - np.array(FAIL_RGB)).max(axis=2) < 40).sum() > 50
    good = preview(write_spec(tmp_path, piece_spec(FLAT, size=(40, 30), scales=[1, 2]), "good.yaml"), tmp_path / "g.png")
    assert not (np.abs(load_rgba(good)[..., :3].astype(int) - np.array(FAIL_RGB)).max(axis=2) < 40).any()


# --- spec rules -------------------------------------------------------------------------------------------------------------

def test_params_on_a_layered_piece_is_an_error(tmp_path):
    spec = piece_spec(FLAT, size=(40, 30), params={"style": "mint"})
    with pytest.raises(SpecError, match="`params` is for block pieces"):
        load_spec(write_spec(tmp_path, spec))
    spec = piece_spec(FLAT, size=(40, 30))
    spec["pieces"]["p"]["variants"] = {"q": {"params": {"x": 1}}}
    with pytest.raises(SpecError, match="variant q: `params` is for block pieces"):
        load_spec(write_spec(tmp_path, spec)).piece_defs()
    spec = piece_spec(FLAT, size=(40, 30))
    spec["params"] = {"*": {"style": "mint"}}                            # top-level params serve block pieces only
    assert load_spec(write_spec(tmp_path, spec)).piece_defs()


def test_casual_button_style_name_is_not_a_var(tmp_path):
    base = {"ninekit": 1, "name": "b", "scales": [1], "pieces": {"b": {"block": "casual_button",
                                                                       "params": {"style": "mint"}}}}
    ref = build(write_spec(tmp_path, base, "ref.yaml"), out=tmp_path / "ref")
    spec = {**base, "vars": {"mint": 3, "W": 100},
            "pieces": {"b": {"block": "casual_button", "params": {"style": "mint", "btn_w": "W + 28"}}}}
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    assert res.manifest["pieces"]["b"]["size"] == ref.manifest["pieces"]["b"]["size"] == [128.0, 62.0]
    for f in ("b_frame.png", "b_face.png"):
        assert np.array_equal(load_rgba(tmp_path / "o" / f), load_rgba(tmp_path / "ref" / f))
    assert res.manifest["pieces"]["b"]["slicing"] == "block"


def test_wood_warp(tmp_path):
    def wood(**extra):
        fill = {"noise": {"kind": "wood", "period": [20, 12], "seed": 4, **extra}}
        return render_one(tmp_path, piece_spec([{"shape": {"all": True}, "fill": fill}], size=(20, 12), scales=[2],
                                               slice="none")).outputs["main"]
    assert np.array_equal(wood(), wood(warp=1.5))          # the default is the old bending
    straight = wood(warp=0)
    assert (straight == straight[:, :1]).all()             # no bending: every row is one colour
    assert not np.array_equal(wood(warp=3), wood())
    with pytest.raises(NinekitError, match="warp applies to kind: wood"):
        render_one(tmp_path, piece_spec([{"shape": {"all": True}, "fill": {"noise": {
            "kind": "value", "period": [8, 8], "warp": 1}}}], size=(8, 8), slice="none"))


# --- compare ----------------------------------------------------------------------------------------------------------------

def _reference(tmp_path, res, piece, size):
    """The piece's stack drawn at [size] with ninekit's resampler: a perfect reference."""
    p = res.manifest["pieces"][piece]
    acc = np.zeros((size[1], size[0], 4))
    for o in p["stack"]:
        e = p["outputs"][o]["3"]
        img = load_rgba(res.out_dir / e["file"])
        q = nine_slice_premul(img, e["slice_px"], size, p["stretch"])
        acc = q + acc * (1.0 - q[..., 3:4])
    canvas = Image.new("RGBA", (size[0] + 30, size[1] + 20), (0, 0, 0, 0))
    canvas.paste(Image.fromarray(unpremultiply(acc), "RGBA"), (10, 5))
    path = tmp_path / "ref.png"
    canvas.save(path)
    return path


def test_compare_identical_and_different(tmp_path, capsys):
    path = write_spec(tmp_path, piece_spec(PANEL, size=(40, 48), scales=[1, 3], outputs=["main"]))
    res = build(path, out=tmp_path / "o")
    ref = _reference(tmp_path, res, "p", (210, 144))
    out = tmp_path / "cmp.png"
    assert main(["compare", str(res.manifest_path), "p", str(ref), "--crop", "10,5,210,144", "-o", str(out),
                 "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] and data["size"] == [210, 144] and data["scale"] == "3"
    assert data["mean_abs"] < 0.05 and data["max_abs"] <= 1 and data["over_16_pct"] == 0
    with Image.open(out) as im:
        assert im.width >= 3 * 210 and im.height > 144
    # a spec works too (built fresh); a wrong colour shows in the metrics
    img = load_rgba(ref).copy()
    img[40:60, 50:120, :3] = [255, 0, 0]
    Image.fromarray(img, "RGBA").save(ref)
    assert main(["compare", str(path), "p", str(ref), "--crop", "10,5,210,144", "-o", str(out)]) == 0
    text = capsys.readouterr().out
    assert "PSNR" in text and "% of pixels over 16/255" in text and "wrote" in text
    assert main(["compare", str(path), "p", str(ref), "--crop", "10,5,210,144", "-o", str(out), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["over_16_pct"] > 3 and data["psnr"] < 40


def test_compare_ref_scale_and_errors(tmp_path, capsys):
    path = write_spec(tmp_path, piece_spec(FLAT, size=(40, 30), scales=[1, 3]))
    res = build(path, out=tmp_path / "o")
    ref = _reference(tmp_path, res, "p", (150, 90))       # 50 x 30 dp at 3 px per dp
    small = tmp_path / "small.png"
    with Image.open(ref) as im:
        im.crop((10, 5, 160, 95)).resize((50, 30), Image.LANCZOS).save(small)   # the same at 1 px per dp
    assert main(["compare", str(res.manifest_path), "p", str(small), "--ref-scale", "1", "-o",
                 str(tmp_path / "c.png"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["size"] == [50, 30] and data["render_px"] == [150, 90] and data["mean_abs"] < 2
    assert main(["compare", str(res.manifest_path), "nope", str(small), "-o", str(tmp_path / "c.png")]) == 2
    assert "unknown piece 'nope'" in capsys.readouterr().err
    assert main(["compare", str(res.manifest_path), "p", str(small), "--crop", "0,0,60,30", "-o",
                 str(tmp_path / "c.png")]) == 2
    assert "reaches outside" in capsys.readouterr().err
    assert main(["compare", str(res.manifest_path), "p", str(small), "--outputs", "face", "-o",
                 str(tmp_path / "c.png")]) == 2
    assert "no output(s) face" in capsys.readouterr().err


# --- plain numbers in every output path, dp-consistent blocks ---------------------------------------------------------------

def test_build_json_and_print_with_a_tile_y_axis(tmp_path, capsys):
    """Regression: a `tile` y axis leaked numpy ints into slice_px (`--json` crashed, the plain output printed
    `np.int64(23)`)."""
    noise = {"noise": {"kind": "value", "period": [0, 6], "seed": 3, "stops": [[0, "#203040"], [1, "#5080a0"]]}}
    layers = [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": "#101820"},
              {"shape": {"inset": 1.5, "r": 3}, "fill": noise}]
    path = write_spec(tmp_path, piece_spec(layers, size=(40, 40), scales=[1, 2, 3], stretch=["stretch", "tile"]))
    assert main(["build", str(path), "-o", str(tmp_path / "o"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] and all(type(v) is int for f in data["files"] for v in f["slice_px"])
    assert main(["build", str(path), "-o", str(tmp_path / "o")]) == 0
    assert "np." not in capsys.readouterr().out
    assert main(["verify", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    res = build(path, out=tmp_path / "o2")
    for r in res.rendered["p"].values():
        assert all(type(v) is int for v in r.slice_px)
    assert res.manifest["pieces"]["p"]["stretch"] == ["stretch", "tile"] and not dp_mismatches(res.manifest)


def test_multiscale_block_pieces_share_one_dp_slice(tmp_path):
    pieces = {"btn": {"block": "casual_button", "params": {"style": "mint"}},
              "pressed": {"block": "casual_button", "params": {"style": "berry", "layers": "full", "pressed": True}},
              "round": {"block": "casual_button", "params": {"style": "sky", "circle": True}}}
    spec = {"ninekit": 1, "name": "b", "scales": [1, 2, 3], "pieces": pieces}
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    m = res.manifest["pieces"]
    assert not dp_mismatches(res.manifest)
    for name in ("btn", "pressed"):
        # x: the largest slice over the scales (28 px at 1x = 28 dp), y: no grid step left -> fixed, one step
        assert m[name]["slice"] == [28.0, 30.0, 28.0, 31.0] and m[name]["stretch"] == ["stretch", "fixed"]
        assert m[name]["outputs"][m[name]["stack"][0]]["3"]["slice_px"] == [84, 90, 84, 93]
    assert m["round"]["slice"] is None
    rep = verify_manifest(res.manifest_path)
    assert rep.ok and not any(f.warnings for f in rep.files), [f.as_dict() for f in rep.files if f.warnings]
    # one scale: the block's own slices, untouched (single-scale legacy art reproduces exactly)
    res3 = build(write_spec(tmp_path, {**spec, "scales": [3]}, "one.yaml"), out=tmp_path / "o3")
    p3 = res3.manifest["pieces"]["btn"]
    assert p3["outputs"]["frame"]["3"]["slice_px"] == [76, 92, 76, 92] and p3["stretch"] == ["stretch", "stretch"]
    rep3 = verify_manifest(res3.manifest_path)
    assert rep3.ok, [f.as_dict() for f in rep3.files if f.status != "ok"]
