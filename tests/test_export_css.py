"""The `css` export target: files, the image-set / url() choice, layout model, press, tiles, shade, composites.

Units and rendering are measured in Chrome by demos/web/check.py (see ninekit/exporters/css.py); these tests pin
the CSS the exporter writes.
"""
import re

import pytest

from conftest import ROOT
from ninekit import NinekitError
from ninekit.cli import main as cli_main
from ninekit.exporters.css import (_Piece, export, ramp_filter_svg, shared_slice, slice_mismatches)
from ninekit.manifest import load_manifest
from ninekit.render import build

BASICS = ROOT / "examples" / "basics" / "basics.yaml"
BUTTONS = ROOT / "examples" / "gumdrop" / "buttons.yaml"


@pytest.fixture(scope="module")
def basics(tmp_path_factory):
    out = tmp_path_factory.mktemp("basics")
    res = build(BASICS, out=out)
    return res.manifest_path


@pytest.fixture(scope="module")
def buttons(tmp_path_factory):
    out = tmp_path_factory.mktemp("buttons")
    res = build(BUTTONS, out=out, only=["btn_mint", "btnc_berry"])
    return res.manifest_path


@pytest.fixture(scope="module")
def single(tmp_path_factory):
    """casual_button at one scale: the block's own slices, whole texels but not whole dp ([76, 92, 76, 92] at 3x)."""
    tmp = tmp_path_factory.mktemp("single")
    spec = tmp / "single.yaml"
    spec.write_text("ninekit: 1\nname: single\nscales: [3]\npieces:\n"
                    "  btn_mint: {block: casual_button, params: {style: mint}}\n")
    return build(spec, out=tmp / "out").manifest_path


def rules(css: str, selector: str) -> list[str]:
    """Bodies of every rule whose selector list contains [selector] exactly."""
    out = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{", "", css)      # rules inside media blocks count too
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sels = [s.strip() for s in m.group(1).split(",")]
        if selector in sels:
            out.append(m.group(2))
    return out


def decl(css: str, selector: str, prop: str) -> list[str]:
    """Values of [prop] in the rules of [selector], in order."""
    vals = []
    for body in rules(css, selector):
        for d in body.split(";"):
            if ":" in d:
                k, v = d.split(":", 1)
                if k.strip() == prop:
                    vals.append(v.strip())
    return vals


# ----------------------------------------------------------------------------------------------- files

def test_export_writes_pngs_css_and_gallery(basics, tmp_path):
    written = export(basics, tmp_path)
    m = load_manifest(basics)
    names = {p.name for p in written}
    assert {"ninekit.css", "index.html"} <= names
    for p in m["pieces"].values():
        for per in p["outputs"].values():
            for f in per.values():
                assert (tmp_path / f["file"]).is_file()
    css = (tmp_path / "ninekit.css").read_text()
    gallery = (tmp_path / "index.html").read_text()
    assert 'href="ninekit.css"' in gallery
    for name in m["pieces"]:
        assert f".nk-{name} {{" in css
        assert f'class="nk-{name}' in gallery


def test_scale_option_keeps_one_candidate(basics, tmp_path):
    export(basics, tmp_path, scale=2)
    assert sorted(p.name for p in tmp_path.glob("*.png")) == sorted(
        f["file"] for p in load_manifest(basics)["pieces"].values() for per in p["outputs"].values()
        for k, f in per.items() if k == "2")
    css = (tmp_path / "ninekit.css").read_text()
    assert "@1x.png" not in css and "@3x.png" not in css and "@media" not in css
    with pytest.raises(NinekitError):
        export(basics, tmp_path / "x", scale=5)


def test_cli_export_css(basics, tmp_path, capsys):
    assert cli_main(["export", str(basics), "--target", "css", "-o", str(tmp_path)]) == 0
    assert (tmp_path / "ninekit.css").is_file()
    assert "ninekit.css" in capsys.readouterr().out


# ----------------------------------------------------------------------------------------------- slicing

def test_every_file_slice_is_the_dp_slice_times_its_scale(basics, buttons):
    """The contract image-set() relies on: slice_px == slice (dp) x scale for every output and scale."""
    bad = {}
    for mpath in (basics, buttons):
        m = load_manifest(mpath)
        for name, p in m["pieces"].items():
            scales = sorted({k for per in p["outputs"].values() for k in per}, key=float)
            mism = slice_mismatches(p, scales)
            if mism:
                bad[name] = mism
    assert not bad, f"pieces whose files disagree with the dp slice: {sorted(bad)}"


def _piece(slice_dp, per_scale, stretch=("stretch", "stretch")):
    return {"size": [40, 30], "slice": slice_dp, "stretch": list(stretch), "content": None, "overhang": None,
            "mode": "color", "stack": ["main"],
            "outputs": {"main": {k: {"file": f"p@{k}x.png", "size_px": [40 * int(k), 30 * int(k)], "slice_px": sp}
                                 for k, sp in per_scale.items()}}}


def test_shared_slice_needs_whole_and_consistent_dp_slices():
    ok = _piece([10, 8, 10, 9], {"1": [10, 8, 10, 9], "2": [20, 16, 20, 18], "3": [30, 24, 30, 27]})
    assert shared_slice(ok, ["1", "2", "3"]) == [10, 8, 10, 9]
    # one file disagrees (compaction / rounding per scale) -> no shared cut
    off = _piece([10, 8, 10, 9], {"1": [10, 8, 10, 9], "2": [19, 16, 20, 18], "3": [30, 24, 30, 27]})
    assert shared_slice(off, ["1", "2", "3"]) is None
    assert slice_mismatches(off, ["1", "2", "3"]) == [("main", "2", [19, 16, 20, 18], [20.0, 16.0, 20.0, 18.0])]
    # fractional dp: Chrome rounds image-set slices to whole CSS px -> url() per scale instead
    frac = _piece([25.33, 30.67, 25.33, 30.67], {"3": [76, 92, 76, 92]})
    assert not slice_mismatches(frac, ["3"])
    assert shared_slice(frac, ["3"]) is None


def test_pieces_use_image_set_or_exact_url_per_scale(basics, tmp_path):
    export(basics, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    m = load_manifest(basics)
    for name, p in m["pieces"].items():
        if p["slice"] is None:
            continue
        pc = _Piece(name, p, None)
        sel = f".nk-{name}::before"
        o = pc.layers[0]
        sources = decl(css, sel, "border-image-source")
        slices = decl(css, sel, "border-image-slice")
        if pc.cut is not None:
            assert sources[-1] == ("image-set(" + ", ".join(
                f'url("{p["outputs"][o][k]["file"]}") {k}x' for k in ("1", "2", "3")) + ")")
            l, t, r, b = (int(v) for v in pc.cut)
            assert slices == [f"{t} {r} {b} {l} fill"]
            # a pressable piece's frame is counter-scaled while pressed: its widths follow --nk-u
            counter = pc.press and o != "face"
            want = " ".join(("0" if not v else f"calc(var(--nk-u, 1) * {v}px)" if counter else f"{v}px")
                            for v in (t, r, b, l))
            assert decl(css, sel, "border-image-width") == [want]
        else:
            # one url() per scale (base rule + resolution media queries), each with that file's own slice_px
            assert sources == [f'url("{p["outputs"][o][k]["file"]}")' for k in ("1", "2", "3")]
            for k, sl in zip(("1", "2", "3"), slices):
                l, t, r, b = p["outputs"][o][k]["slice_px"]
                assert sl == f"{t} {r} {b} {l} fill"
            assert "(min-resolution: 1.001dppx)" in css and "(min-resolution: 2.001dppx)" in css


def test_fractional_widths_are_exact(single, tmp_path):
    """slice_px / scale that does not terminate is written as calc(Npx / S): 25.3333px would be 75.9999 device px
    at a ratio of 3 and Chrome squeezes the 76-texel corner into 75."""
    export(single, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    assert decl(css, ".nk-btn_mint::after", "border-image-width") == [
        "calc(92px / 3) calc(76px / 3) calc(92px / 3) calc(76px / 3)"]
    assert decl(css, ".nk-btn_mint::after", "border-image-slice") == ["92 76 92 76 fill"]


def test_basics_take_image_set(basics):
    """With dp-consistent whole slices (DESIGN 2.4) every sliced basics piece shares one image-set()."""
    m = load_manifest(basics)
    for name, p in m["pieces"].items():
        if p["slice"] is not None:
            assert _Piece(name, p, None).cut is not None, name


def test_fixed_axis_keeps_natural_length_centred(basics, tmp_path):
    export(basics, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    m = load_manifest(basics)
    assert m["pieces"]["pill"]["stretch"] == ["stretch", "fixed"]
    # the pill is 30 dp tall: its layer is 30 px, centred on the box whatever height the box gets
    assert decl(css, ".nk-pill::before", "inset") == ["calc(50% - 15px) 0 auto 0"]
    assert decl(css, ".nk-pill::before", "height") == ["30px"]
    assert decl(css, ".nk-pill::before", "border-image-repeat") == ["stretch stretch"]
    assert decl(css, ".nk-pill", "min-width") and not decl(css, ".nk-pill", "min-height")
    assert decl(css, ".nk-bar_track::before", "height") == ["16px"]
    assert not decl(css, ".nk-panel::before", "height")


def test_fixed_axis_with_overhang_and_press():
    """y fixed, overhang below, frame/face: the frame's centred rect is counter-scaled too."""
    piece = {"size": [40, 34], "slice": [10, 16, 10, 17], "stretch": ["stretch", "fixed"], "content": None,
             "overhang": [0, 0, 0, 2], "mode": "color", "stack": ["frame", "face"],
             "outputs": {o: {"1": {"file": f"t_{o}.png", "size_px": [40, 34], "slice_px": [10, 16, 10, 17]}}
                         for o in ("frame", "face")}}
    css = _Piece("t", piece, None).css()
    # sprite 34 tall, logical 32: its top sits (34 + 0 - 2) / 2 = 16 above the box centre
    assert decl(css, ".nk-t::after", "inset") == ["calc(50% - 16px) 0 auto 0"]
    assert decl(css, ".nk-t::after", "height") == ["34px"]
    assert decl(css, ".nk-t::before", "inset") == [
        "calc(50% - var(--nk-u, 1) * 16px) calc((1 - var(--nk-u, 1)) * 50%) auto calc((1 - var(--nk-u, 1)) * 50%)"]
    assert decl(css, ".nk-t::before", "height") == ["calc(var(--nk-u, 1) * 34px)"]


def test_tile_axes_round_whole_tiles(basics, tmp_path):
    export(basics, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    assert decl(css, ".nk-stone::before", "border-image-repeat") == ["round round"]
    assert decl(css, ".nk-panel::before", "border-image-repeat") == ["stretch stretch"]


# ----------------------------------------------------------------------------------------------- layout model

def test_box_is_logical_rect_and_padding_is_content_minus_overhang(buttons, single, basics, tmp_path):
    export(buttons, tmp_path / "b")
    css = (tmp_path / "b" / "ninekit.css").read_text()
    # casual_button: canvas 128 x 62, overhang [0, 0, 0, 3], content [12, 8, 12, 17] (from the canvas)
    assert decl(css, ".nk-btn_mint", "padding") == ["8px 12px 14px"]
    # several scales: y is fixed, so the 62 px sprite is centred on the 59 px logical box, its top 29.5 px above the
    # box centre and its last 3 px below the box (the overhang); the frame is counter-scaled while pressed
    assert decl(css, ".nk-btn_mint::after", "inset") == ["calc(50% - 29.5px) 0 auto 0"]
    assert decl(css, ".nk-btn_mint::after", "height") == ["62px"]
    assert decl(css, ".nk-btn_mint::before", "inset") == [
        "calc(50% - var(--nk-u, 1) * 29.5px) calc((1 - var(--nk-u, 1)) * 50%) auto calc((1 - var(--nk-u, 1)) * 50%)"]
    # one scale: y stretches, the sprite is the box grown by the overhang
    export(single, tmp_path / "s")
    css1 = (tmp_path / "s" / "ninekit.css").read_text()
    assert decl(css1, ".nk-btn_mint::after", "inset") == ["0 0 -3px"]
    assert decl(css1, ".nk-btn_mint::before", "inset")[0].endswith("- var(--nk-u, 1) * 3px) calc((1 - var(--nk-u, 1)) * 50%)")
    # the label centre lands on the face panel's centre: 26.55 dp from the canvas top
    pc = _Piece("btn_mint", load_manifest(buttons)["pieces"]["btn_mint"], None)
    l, t, r, b = pc.padding()
    assert pc.logical == (128.0, pytest.approx(59.0))
    assert t + (pc.logical[1] - t - b) / 2 == pytest.approx(26.55, abs=0.1)
    # drawn whole: fixed logical size, background image-set
    assert decl(css, ".nk-btnc_berry", "width") == ["62px"] and decl(css, ".nk-btnc_berry", "height") == ["59px"]
    export(basics, tmp_path / "a")
    css = (tmp_path / "a" / "ninekit.css").read_text()
    assert decl(css, ".nk-panel", "padding") == ["8px 10px 11px"]      # content [10, 8, 10, 14] - overhang b 3
    assert decl(css, ".nk-panel::before", "inset") == ["0 0 -3px"]
    assert decl(css, ".nk-badge::before", "background-image")[-1] == (
        'image-set(url("badge@1x.png") 1x, url("badge@2x.png") 2x, url("badge@3x.png") 3x)')
    assert decl(css, ".nk-badge", "width") == ["28px"]
    for prop in ("appearance", "border", "background", "isolation"):
        assert decl(css, ".nk-pill", prop)


def test_frame_face_stack_and_output_classes(basics, tmp_path):
    export(basics, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    assert decl(css, ".nk-tab::before", "z-index") == ["-2"] and decl(css, ".nk-tab__frame", "z-index") == ["-2"]
    assert decl(css, ".nk-tab::after", "z-index") == ["-1"] and decl(css, ".nk-tab__face", "z-index") == ["-1"]
    assert "tab_frame@1x.png" in "".join(rules(css, ".nk-tab::before"))
    assert "tab_face@1x.png" in "".join(rules(css, ".nk-tab::after"))


def test_press_scales_face_and_content_frame_stays(buttons, tmp_path):
    export(buttons, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    for state in (".nk-btn_mint:active:not(:disabled)", ".nk-btn_mint.nk-pressed"):
        assert decl(css, state, "transform") == ["scale(var(--nk-press, 0.92))"]
        assert decl(css, state, "transform-origin") == ["50% 50%"]     # the logical box centre = the body
        assert decl(css, state, "will-change") == ["transform"]       # seamless (one composited layer)
        assert decl(css, state + "::before", "--nk-u") == ["calc(1 / var(--nk-press, 0.92))"]
        assert not decl(css, state + "::after", "--nk-u")
    # the frame's geometry follows --nk-u (counter-scaled), the face's does not
    assert "var(--nk-u, 1)" in decl(css, ".nk-btn_mint::before", "border-image-width")[0]
    assert "--nk-u" not in decl(css, ".nk-btn_mint::after", "border-image-width")[0]
    # round form: whole pieces press the same way; its composite `main` is a class, not stacked
    assert decl(css, ".nk-btnc_berry.nk-pressed", "transform") == ["scale(var(--nk-press, 0.92))"]
    assert decl(css, ".nk-btnc_berry__main", "background-image")[-1] == (
        'image-set(url("btnc_berry@1x.png") 1x, url("btnc_berry@2x.png") 2x, url("btnc_berry@3x.png") 3x)')
    assert not rules(css, ".nk-btnc_berry::before") or "btnc_berry@" not in "".join(rules(css, ".nk-btnc_berry::before"))


def test_single_output_pieces_have_no_press(basics, tmp_path):
    export(basics, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    assert ".nk-panel.nk-pressed" not in css and ".nk-tab.nk-pressed" in css


# ----------------------------------------------------------------------------------------------- shade

def test_shade_pieces_take_a_ramp_filter(basics, tmp_path):
    export(basics, tmp_path)
    css = (tmp_path / "ninekit.css").read_text()
    assert decl(css, ".nk-shade_button::before", "filter") == ["var(--nk-ramp, none)"]
    assert not decl(css, ".nk-panel::before", "filter")
    gallery = (tmp_path / "index.html").read_text()
    assert 'id="nk-ramp-gold"' in gallery and "--nk-ramp: url(#nk-ramp-gold)" in gallery


def test_ramp_filter_is_an_exact_gradient_map():
    svg = ramp_filter_svg("r", [[0, "#000000"], [0.5, "#FF8000"], [1, "#FFFFFF"]])
    assert 'color-interpolation-filters="sRGB"' in svg
    assert '<feFuncR type="table" tableValues="0 1 1"/>' in svg
    assert '<feFuncG type="table" tableValues="0 0.502 1"/>' in svg
    assert '<feFuncB type="table" tableValues="0 0 1"/>' in svg
    # stops off a small grid are sampled at 256 entries
    svg = ramp_filter_svg("r", [[0, "#000000"], [0.3333, "#FFFFFF"], [1, "#FFFFFF"]])
    assert len(re.search(r'feFuncR type="table" tableValues="([^"]*)"', svg).group(1).split()) == 256
