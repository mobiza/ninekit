"""The godot export target (DESIGN 7): PNGs + ninekit.json, a StyleBoxTexture .tres per @1x output, the runtime."""
import json

import pytest

from conftest import ROOT
from ninekit import NinekitError, exporters
from ninekit.cli import main
from ninekit.exporters.godot import find_godot_project, stylebox_tres
from ninekit.render import build

BASICS = ROOT / "examples" / "basics" / "basics.yaml"
RUNTIME = {"nine_skin.gd", "nine_button.gd", "ninekit_manifest.gd", "ninekit_ramp.gdshader"}


def tres_props(path) -> dict:
    """The [resource] properties of a .tres as {key: text value}, plus the ext_resource path."""
    props, section = {}, None
    for line in path.read_text().splitlines():
        if line.startswith("[ext_resource"):
            props["ext_path"] = line.split('path="')[1].split('"')[0]
        elif line.startswith("["):
            section = line
        elif section == "[resource]" and " = " in line:
            k, v = line.split(" = ", 1)
            props[k] = v
    return props


@pytest.fixture(scope="module")
def basics(tmp_path_factory):
    return build(BASICS, out=tmp_path_factory.mktemp("basics"))


def test_godot_export_files_and_styleboxes(basics, tmp_path):
    out = tmp_path / "ui"
    written = exporters.get_exporter("godot")(basics.manifest_path, out)
    m = basics.manifest
    files = {e["file"] for p in m["pieces"].values() for per in p["outputs"].values() for e in per.values()}
    assert {p.name for p in out.glob("*.png")} == files
    assert json.loads((out / "ninekit.json").read_text()) == m
    tres = {p.name for p in out.glob("*.tres")}
    assert tres == {"panel.tres", "pill.tres", "badge.tres", "scifi.tres", "bar_track.tres", "bar_fill.tres",
                    "tab_frame.tres", "tab_face.tres", "shade_button.tres", "stone.tres"}
    assert set(written) == {out / f for f in files} | {out / t for t in tres} | {out / "ninekit.json"}

    panel = tres_props(out / "panel.tres")
    assert (out / "panel.tres").read_text().startswith('[gd_resource type="StyleBoxTexture" format=3]')
    assert panel["ext_path"] == "panel@1x.png" and panel["texture"] == 'ExtResource("1_tex")'
    sp = m["pieces"]["panel"]["outputs"]["main"]["1"]["slice_px"]
    assert [float(panel[f"texture_margin_{s}"]) for s in ("left", "top", "right", "bottom")] == sp
    # overhang [0, 0, 0, 3] -> expand margins; content [10, 8, 10, 14] is measured from the art's edges,
    # a StyleBox's content margins from the control's rect (the art minus the overhang)
    assert panel["expand_margin_bottom"] == "3.0" and "expand_margin_top" not in panel
    assert [float(panel[f"content_margin_{s}"]) for s in ("left", "top", "right", "bottom")] == [10, 8, 10, 11]
    assert "axis_stretch_horizontal" not in panel  # stretch is Godot's default

    stone = tres_props(out / "stone.tres")
    assert stone["axis_stretch_horizontal"] == "2" and stone["axis_stretch_vertical"] == "2"  # tile -> tile-fit
    assert "content_margin_left" not in stone  # no content: Godot's default (the texture margins)

    # pill is y-fixed (fully rounded vertically): a StyleBox has no fixed mode, it is written as plain stretch
    assert m["pieces"]["pill"]["stretch"] == ["stretch", "fixed"]
    pill = tres_props(out / "pill.tres")
    assert "axis_stretch_vertical" not in pill and "axis_stretch_horizontal" not in pill

    badge = tres_props(out / "badge.tres")  # drawn whole: no slices
    assert all(float(badge[f"texture_margin_{s}"]) == 0 for s in ("left", "top", "right", "bottom"))

    face = tres_props(out / "tab_face.tres")
    assert face["ext_path"] == "tab_face@1x.png"
    assert float(face["texture_margin_top"]) == m["pieces"]["tab"]["outputs"]["face"]["1"]["slice_px"][1]


def test_godot_export_one_scale(basics, tmp_path):
    out = tmp_path / "ui"
    exporters.get_exporter("godot")(basics.manifest_path, out, scale=3)
    assert all(p.name.endswith("@3x.png") for p in out.glob("*.png"))
    assert not list(out.glob("*.tres"))  # StyleBoxes are @1x only
    m = json.loads((out / "ninekit.json").read_text())
    assert m["scales"] == [3]
    for p in m["pieces"].values():
        for per in p["outputs"].values():
            assert list(per) == ["3"] and (out / per["3"]["file"]).is_file()
    with pytest.raises(NinekitError, match="--scale 4"):
        exporters.get_exporter("godot")(basics.manifest_path, out, scale=4)


def test_godot_runtime_goes_to_the_project(basics, tmp_path, capsys):
    proj = tmp_path / "game"
    proj.mkdir()
    (proj / "project.godot").write_text("config_version=5\n")
    out = proj / "art" / "ui"
    assert find_godot_project(out) == proj
    assert main(["export", str(basics.manifest_path), "--target", "godot", "-o", str(out), "--runtime"]) == 0
    printed = capsys.readouterr().out
    addon = proj / "addons" / "ninekit"
    assert {p.name for p in addon.iterdir()} == RUNTIME
    assert "addons/ninekit/nine_skin.gd" in printed and "panel.tres" in printed
    for gd in addon.glob("*.gd"):
        text = gd.read_text()
        assert text.startswith("@tool\nclass_name ") and "\t" in text  # GDScript, tab-indented
    # outside any Godot project the runtime has nowhere to go
    with pytest.raises(NinekitError, match="no project.godot"):
        exporters.get_exporter("godot")(basics.manifest_path, tmp_path / "loose", runtime=True)
    # unless the caller names the project
    other = tmp_path / "other"
    other.mkdir()
    (other / "project.godot").write_text("")
    exporters.get_exporter("godot")(basics.manifest_path, tmp_path / "loose", runtime=True, godot_project=other)
    assert {p.name for p in (other / "addons" / "ninekit").iterdir()} == RUNTIME


def test_godot_export_block_pieces_without_scale_1(tmp_path):
    spec = tmp_path / "b.yaml"
    spec.write_text("ninekit: 1\nname: b\nscales: [3]\npieces:\n"
                    "  btn_mint: {block: casual_button, params: {style: mint}}\n"
                    "  btnc_sky: {block: casual_button, params: {style: sky, circle: true, layers: [frame, face, full]}}\n")
    res = build(spec, out=tmp_path / "b")
    out = tmp_path / "ui"
    exporters.get_exporter("godot")(res.manifest_path, out)
    assert {p.name for p in out.glob("*.png")} == {"btn_mint_frame.png", "btn_mint_face.png", "btnc_sky_frame.png",
                                                    "btnc_sky_face.png", "btnc_sky.png"}
    assert not list(out.glob("*.tres"))


def test_godot_export_gumdrop_buttons(tmp_path):
    res = build(ROOT / "examples" / "gumdrop" / "buttons.yaml", out=tmp_path / "b", only=["btn_mint", "btnc_sky"])
    out = tmp_path / "ui"
    exporters.get_exporter("godot")(res.manifest_path, out)
    assert {p.name for p in out.glob("*.tres")} == {"btn_mint_frame.tres", "btn_mint_face.tres", "btnc_sky_frame.tres",
                                                     "btnc_sky_face.tres", "btnc_sky.tres"}
    text = (out / "btn_mint_frame.tres").read_text()
    assert 'path="btn_mint_frame@1x.png"' in text and "texture_margin_left = 28.0\n" in text
    assert "content_margin_bottom = 14.0\n" in text and "expand_margin_bottom = 3.0\n" in text


def test_stylebox_tres_units():
    text = stylebox_tres("a.png", [76, 92, 76, 92], ["stretch", "tile"], [12, 7.33, 12, 16.67], [0, 0, 0, 2.5])
    assert 'path="a.png"' in text
    assert "content_margin_top = 7.33\n" in text and "content_margin_bottom = 14.17\n" in text
    assert "expand_margin_bottom = 2.5\n" in text and "axis_stretch_vertical = 2\n" in text
    assert "axis_stretch_horizontal" not in text
    # an overhang wider than the content inset never gives a negative margin (Godot reads < 0 as "unset")
    assert "content_margin_bottom = 0.0\n" in stylebox_tres("a.png", None, ["stretch"] * 2, [0, 0, 0, 1], [0, 0, 0, 3])
    assert "axis_stretch" not in stylebox_tres("a.png", [1, 1, 1, 1], ["fixed", "fixed"], None, None)
    with pytest.raises(NinekitError, match="stretch mode"):
        stylebox_tres("a.png", None, ["wrap", "stretch"], None, None)


def test_godot_export_name_clash(tmp_path):
    src = tmp_path / "m"
    src.mkdir()
    pieces = {}
    for name, out in (("tab", "frame"), ("tab_frame", "main")):
        f = f"{name}_{out}.png"
        (src / f).write_bytes(b"")
        pieces[name] = {"size": [4, 4], "slice": None, "stretch": ["stretch", "stretch"], "content": None,
                        "overhang": None, "mode": "color", "stack": [out],
                        "outputs": {out: {"1": {"file": f, "size_px": [4, 4], "slice_px": None}}}}
    (src / "ninekit.json").write_text(json.dumps({"ninekit": 1, "name": "x", "scales": [1], "pieces": pieces}))
    with pytest.raises(NinekitError, match="tab_frame.tres"):
        exporters.get_exporter("godot")(src, tmp_path / "ui")


def test_cli_godot_project_option(basics, tmp_path):
    proj = tmp_path / "game"
    proj.mkdir()
    (proj / "project.godot").write_text("")
    out = tmp_path / "elsewhere" / "ui"
    rc = main(["export", str(basics.manifest_path), "--target", "godot", "-o", str(out),
               "--runtime", "--godot-project", str(proj)])
    assert rc == 0
    assert {p.name for p in (proj / "addons" / "ninekit").glob("*") if p.is_file()} >= RUNTIME


def test_cli_godot_project_rejected_for_other_targets(basics, tmp_path, capsys):
    rc = main(["export", str(basics.manifest_path), "--target", "json", "-o", str(tmp_path / "o"),
               "--godot-project", str(tmp_path)])
    assert rc == 2
    assert "--godot-project" in capsys.readouterr().err


def test_godot_reexport_removes_stale_files_only(basics, tmp_path):
    src = tmp_path / "src"
    build(BASICS, out=src)
    m = json.loads((src / "ninekit.json").read_text())
    gone = sorted(m["pieces"])[0]
    gone_files = {e["file"] for per in m["pieces"][gone]["outputs"].values() for e in per.values()}
    out = tmp_path / "ui"
    exporters.get_exporter("godot")(src / "ninekit.json", out)
    (out / (next(iter(gone_files)) + ".import")).write_text("x")
    (out / "mine.png").write_text("keep")
    (out / "mine.tres").write_text("keep")
    assert any(p.suffix == ".tres" and p.name.startswith(gone) for p in out.iterdir())
    del m["pieces"][gone]
    (src / "ninekit.json").write_text(json.dumps(m))
    exporters.get_exporter("godot")(src / "ninekit.json", out)
    left = {p.name for p in out.iterdir()}
    assert not gone_files & left
    assert not any(n.startswith(gone) and n.endswith((".tres", ".import")) for n in left)
    assert {"mine.png", "mine.tres"} <= left
    assert len([n for n in left if n.endswith(".png")]) > 1
