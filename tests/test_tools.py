"""preview (DESIGN 6), `ninekit new`, export registry + the json target (DESIGN 7), measure forwarding, blocks."""
import json
import sys
import textwrap

import pytest

from conftest import load_rgba, piece_spec, write_spec
from ninekit import NinekitError, blocks, exporters
from ninekit.cli import main
from ninekit.preview import preview
from ninekit.render import build
from ninekit.verify import verify

LAYERS = [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": {"vgrad": [[0, "#ffcc00"], [1, "#cc6600"]]}}]


# --- preview ------------------------------------------------------------------------------------------------------------

def test_preview_sheet(tmp_path, capsys):
    spec = piece_spec(LAYERS, size=(40, 20), scales=[1, 2])
    spec["pieces"]["dot"] = {"size": [12, 12], "slice": "none",
                             "layers": [{"shape": {"circle": [6, 6, 5]}, "fill": "#ff0000"}]}
    spec["pieces"]["tab"] = {"size": [30, 16], "outputs": ["frame", "face"],
                             "layers": [{"shape": {"rect": [0, 0, "w", "h"], "r": 3}, "fill": "#000000",
                                         "output": "frame"},
                                        {"shape": {"rect": [1, 1, "w - 1", "h - 3"], "r": 2}, "fill": "#00ff00",
                                         "output": "face"}]}
    path = write_spec(tmp_path, spec)
    out = preview(path, tmp_path / "sheet.png")
    sheet = load_rgba(out)
    assert sheet.shape[0] > 100 and sheet.shape[1] > 200
    colours = {tuple(c) for c in sheet[..., :3].reshape(-1, 3)[::7]}
    assert (255, 0, 0) in colours and (0, 255, 0) in colours          # the badge and the stacked tab face
    # from a manifest, at a chosen scale, with a background
    res = build(path, out=tmp_path / "o")
    assert main(["preview", str(res.manifest_path), "--scale", "1", "--bg", "#102030"]) == 0
    assert (tmp_path / "o" / "t.preview.png").exists()
    assert "wrote" in capsys.readouterr().out
    with pytest.raises(NinekitError, match="scales"):
        preview(res.manifest_path, tmp_path / "x.png", scale=5)


def test_preview_shows_tiles_with_whole_repeats():
    from ninekit.preview import _sizes

    assert _sizes(40, 30, True, [5, 5, 5, 5], ["tile", "stretch"]) == [(40, 30), (70, 30), (70, 45)]
    assert _sizes(40, 30, True, [5, 5, 7, 5], ["tile", "tile"])[2] == (5 + 7 + 28 * 2, 10 + 20 * 2)
    # the design size first (a compacted texture is drawn at the size it was designed at), fixed axes stay
    assert _sizes(16, 30, True, [7, 5, 7, 5], ["stretch", "stretch"], (60, 40)) == [(60, 40), (90, 40), (120, 60)]
    assert _sizes(16, 30, True, [7, 14, 7, 15], ["stretch", "fixed"], (60, 30)) == [(60, 30), (90, 30), (120, 30)]


# --- new -----------------------------------------------------------------------------------------------------------------

def test_new_scaffold_builds_and_verifies(tmp_path, capsys):
    assert main(["new", str(tmp_path / "proj")]) == 0
    spec = tmp_path / "proj" / "ninekit.yaml"
    assert spec.exists() and "wrote" in capsys.readouterr().out
    res = build(spec)
    assert not res.problems and len(res.files) == 12
    assert verify(spec).ok
    assert main(["new", str(tmp_path / "proj")]) == 2          # refuses to overwrite
    assert "already exists" in capsys.readouterr().err


# --- export -----------------------------------------------------------------------------------------------------------------

def test_export_json(tmp_path, capsys):
    spec = piece_spec(LAYERS, size=(40, 20), scales=[1, 2], content=[3, 2, 3, 2])
    spec["pieces"]["dot"] = {"size": [12, 12], "slice": "none", "mode": "shade",
                             "layers": [{"shape": {"circle": [6, 6, 5]}, "fill": 0.5}]}
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    assert main(["export", str(res.manifest_path), "--target", "json", "-o", str(tmp_path / "e")]) == 0
    sprites = json.loads((tmp_path / "e" / "sprites.json").read_text())
    assert [(s["name"], s["scale"]) for s in sprites] == [("dot", 1), ("dot", 2), ("p", 1), ("p", 2)]
    p2 = sprites[3]
    assert set(p2) == {"name", "output", "scale", "file", "size_px", "slice_px", "slice_dp", "stretch", "content",
                       "overhang", "mode"}
    assert p2["slice_dp"] == [v / 2 for v in p2["slice_px"]] and p2["content"] == [3, 2, 3, 2]
    assert sprites[0]["slice_px"] is None and sprites[0]["slice_dp"] is None and sprites[0]["mode"] == "shade"
    assert (tmp_path / "e" / "p@2x.png").read_bytes() == (tmp_path / "o" / "p@2x.png").read_bytes()
    out = exporters.get_exporter("json")(res.manifest_path, tmp_path / "e2", scale=2)
    assert sorted(p.name for p in out) == ["dot@2x.png", "p@2x.png", "sprites.json"]


def test_export_registry_errors(tmp_path, monkeypatch):
    with pytest.raises(NinekitError, match="unknown export target"):
        exporters.get_exporter("blender")
    monkeypatch.setattr(exporters, "TARGETS", exporters.TARGETS + ("nosuch",))
    with pytest.raises(NinekitError, match="missing ninekit/exporters/nosuch.py"):
        exporters.get_exporter("nosuch")
    assert main(["export", str(tmp_path / "spec.yaml"), "--target", "json", "-o", str(tmp_path)]) == 2


# --- measure forwarding -------------------------------------------------------------------------------------------------

def test_measure_is_forwarded(monkeypatch):
    seen = {}
    fake = type(sys)("ninekit.measure")
    fake.main = lambda argv: seen.setdefault("argv", argv) and 7
    monkeypatch.setitem(sys.modules, "ninekit.measure", fake)
    assert main(["measure", "img.png", "--x", "3", "--json"]) == 7
    assert seen["argv"] == ["img.png", "--x", "3", "--json"]


def test_measure_missing_module_is_a_clear_error(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "ninekit.measure", None)
    assert main(["measure", "x.png"]) == 2
    assert "missing ninekit/measure.py" in capsys.readouterr().err


# --- blocks -------------------------------------------------------------------------------------------------------------

FAKE_BLOCK = textwrap.dedent('''
    from PIL import Image

    DEFAULTS = {"w": 10.0, "h": 10.0, "style": None, "layers": ["frame", "face"], "colors": None, "round": False}

    def render(params, scale):
        w, h = round(params["w"] * scale), round(params["h"] * scale)
        frame = Image.new("RGBA", (w, h), params["colors"]["frame"])
        face = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        face.paste(params["colors"]["face"], (scale, scale, w - scale, h - scale))
        outs = {"frame": frame, "face": face}
        if "full" in params["layers"]:
            full = frame.copy()
            full.alpha_composite(face)
            outs["main"] = full
        return {"outputs": outs, "slice_px": None if params.get("round") else [2 * scale] * 4,
                "size": [params["w"], params["h"]], "content": [1, 1, 1, 1], "overhang": None,
                "seen": params}
''')


@pytest.fixture
def fake_block(tmp_path, monkeypatch):
    (tmp_path / "fakeblock_mod.py").write_text(FAKE_BLOCK)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(blocks.REGISTRY, "fake", "fakeblock_mod:render")
    return tmp_path


def test_block_piece_outputs_params_and_files(fake_block):
    tmp_path = fake_block
    spec = {"ninekit": 1, "name": "b", "scales": [1, 2], "vars": {"W": 20},
            "pieces": {"btn": {"block": "fake", "params": {
                "w": "W + 4", "h": 10, "layers": ["frame", "face", "full"],
                "colors": {"frame": "#202020", "face": "#e0e0e0", "nested": {"gold": "#ffcc00"}}}}}}
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    files = sorted(f["file"] for f in res.files)
    assert files == ["btn@1x.png", "btn@2x.png", "btn_face@1x.png", "btn_face@2x.png", "btn_frame@1x.png",
                     "btn_frame@2x.png"]
    m = res.manifest["pieces"]["btn"]
    assert m["size"] == [24.0, 10.0] and m["slice"] == [2.0, 2.0, 2.0, 2.0] and m["content"] == [1, 1, 1, 1]
    assert m["stack"] == ["frame", "face", "main"]
    assert m["outputs"]["frame"]["2"]["slice_px"] == [4, 4, 4, 4]
    full = load_rgba(tmp_path / "o" / "btn@2x.png")
    assert tuple(full[5, 5]) == (0xE0, 0xE0, 0xE0, 255)
    assert verify(tmp_path / "o" / "ninekit.json").ok


def test_block_params_resolution(fake_block):
    from ninekit.expr import Scope
    from ninekit.render import resolve_params

    s = Scope({"W": 20, "mint": 3}, {"scale": 2})
    defaults = {"w": 1.0, "h": 1, "k": 0, "pad": [0, 0], "style": None, "colors": None, "circle": False,
                "layers": ["frame", "face"]}
    params = {"w": "W + 4", "h": 10, "style": "mint", "circle": True, "c": "#ff0000", "pad": ["W / 4", 2],
              "layers": ["mint", "face"], "colors": {"bezel": {"inner": "#ffcc00"}, "rgb": [1, 2, 3], "x": "W"},
              "k": "scale * 3", "extra": "W"}
    got = resolve_params(params, s, defaults)
    # numeric defaults evaluate; `style: mint` stays a name although a var `mint` exists; nested dicts and
    # keys without a numeric default pass verbatim
    assert got == {"w": 24, "h": 10, "style": "mint", "circle": True, "c": "#ff0000", "pad": [5, 2],
                   "layers": ["mint", "face"], "colors": {"bezel": {"inner": "#ffcc00"}, "rgb": [1, 2, 3], "x": "W"},
                   "k": 6, "extra": "W"}
    # a block without DEFAULTS gets numbers only
    assert resolve_params({"w": "W + 4", "h": 10}, s) == {"w": "W + 4", "h": 10}
    with pytest.raises(NinekitError, match="params.w"):
        resolve_params({"w": "#ff0000"}, s, defaults)


def test_block_round_form_and_forbidden_keys(fake_block):
    tmp_path = fake_block
    spec = {"ninekit": 1, "pieces": {"b": {"block": "fake", "params": {
        "w": 10, "h": 10, "round": True, "layers": ["frame", "face"], "colors": {"frame": "#000000", "face": "#ffffff"}},
        "content": [2, 2, 2, 2]}}}
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    m = res.manifest["pieces"]["b"]
    assert m["slice"] is None and m["content"] == [2, 2, 2, 2]
    spec["pieces"]["b"]["slice"] = [1, 1, 1, 1]
    with pytest.raises(NinekitError, match="cannot be set on a block piece"):
        build(write_spec(tmp_path, spec), out=tmp_path / "o")


def test_block_registry_errors(monkeypatch):
    with pytest.raises(NinekitError, match="unknown block 'nope'"):
        blocks.get_block("nope")
    monkeypatch.setitem(blocks.REGISTRY, "ghost", "ninekit.blocks.ghost:render")
    with pytest.raises(NinekitError, match="ninekit/blocks/ghost.py"):
        blocks.get_block("ghost")
    monkeypatch.setitem(blocks.REGISTRY, "nofn", "ninekit.blocks:missing_fn")
    with pytest.raises(NinekitError, match="no function missing_fn"):
        blocks.get_block("nofn")
