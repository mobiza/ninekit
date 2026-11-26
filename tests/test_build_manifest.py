"""build + the manifest (DESIGN 3, 4)."""
import json

import pytest

from conftest import piece_spec, write_spec
from ninekit.cli import main
from ninekit.manifest import load_manifest
from ninekit.render import build

LAYERS = [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": {"vgrad": [[0, "#ffffff"], [1, "#888888"]]}}]


def test_manifest_shape_and_format(tmp_path):
    spec = piece_spec(LAYERS, size=(30, 16), scales=[1, 3], content=[4, 2, 4, 3], overhang=[0, 0, 0, 1.5])
    spec["name"] = "demo"
    spec["pieces"]["icon"] = {"size": [10, 10], "slice": "none", "layers": LAYERS}
    res = build(write_spec(tmp_path, spec), out=tmp_path / "out")
    text = (tmp_path / "out" / "ninekit.json").read_text()
    data = json.loads(text)
    # sorted keys, two-space indent, trailing newline
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"
    assert text.endswith("}\n") and "\n  \"generator\"" in text
    assert data["ninekit"] == 1 and data["name"] == "demo" and data["scales"] == [1, 3]
    assert data["generator"].startswith("ninekit ")
    p = data["pieces"]["p"]
    assert set(p) == {"size", "design_size", "slice", "stretch", "content", "overhang", "mode", "slicing", "stack",
                      "outputs"}
    assert p["design_size"] == [30, 16] and p["size"][0] < 30          # compacted texture vs the designed size
    assert p["stretch"] == ["stretch", "stretch"] and p["mode"] == "color" and p["stack"] == ["main"]
    assert p["slicing"] == "auto" and data["pieces"]["icon"]["slicing"] == "none"
    assert p["content"] == [4, 2, 4, 3] and p["overhang"] == [0, 0, 0, 1.5]
    e1, e3 = p["outputs"]["main"]["1"], p["outputs"]["main"]["3"]
    assert e1["file"] == "p@1x.png" and e3["file"] == "p@3x.png"
    assert set(e1) == {"file", "size_px", "slice_px"}
    assert p["size"] == [round(e3["size_px"][0] / 3, 2), round(e3["size_px"][1] / 3, 2)]
    assert p["slice"] == [round(v / 3, 2) for v in e3["slice_px"]]
    icon = data["pieces"]["icon"]
    assert icon["slice"] is None and icon["outputs"]["main"]["3"]["slice_px"] is None
    assert icon["content"] is None and icon["overhang"] is None
    assert icon["outputs"]["main"]["3"]["size_px"] == [30, 30]
    assert res.manifest == data


def test_only_updates_the_existing_manifest(tmp_path):
    spec = piece_spec(LAYERS, size=(30, 16))
    spec["pieces"]["q"] = {"size": [20, 10], "layers": LAYERS}
    path = write_spec(tmp_path, spec)
    build(path, out=tmp_path / "out")
    spec["pieces"]["q"]["size"] = [24, 12]
    write_spec(tmp_path, spec)
    build(path, out=tmp_path / "out", only=["q"])
    m = load_manifest(tmp_path / "out")
    assert set(m["pieces"]) == {"p", "q"}
    assert m["pieces"]["q"]["outputs"]["main"]["1"]["size_px"][1] == 12


def test_build_default_out_is_relative_to_the_spec(tmp_path):
    spec = piece_spec(LAYERS, size=(30, 16))
    spec["out"] = "art/"
    build(write_spec(tmp_path, spec))
    assert (tmp_path / "art" / "p.png").exists() and (tmp_path / "art" / "ninekit.json").exists()


def test_build_cli_human_and_json(tmp_path, capsys):
    path = write_spec(tmp_path, piece_spec(LAYERS, size=(30, 16), scales=[1, 2]))
    assert main(["build", str(path), "-o", str(tmp_path / "o")]) == 0
    out = capsys.readouterr().out
    assert "wrote" in out and "p@2x.png" in out and "ninekit.json" in out
    assert main(["build", str(path), "-o", str(tmp_path / "o"), "--json", "--scales", "2"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True and data["manifest"].endswith("ninekit.json")
    assert [f["file"] for f in data["files"]] == ["p@2x.png"]
    assert data["files"][0]["size_px"] and data["files"][0]["slice_px"]


def test_build_cli_errors_are_clean(tmp_path, capsys):
    path = write_spec(tmp_path, piece_spec([{"shape": {"rect": [0, 0, "W", 1]}, "fill": "#ffffff"}]))
    assert main(["build", str(path), "-o", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "unknown name 'W'" in err and "layer 0" in err
    assert main(["build", str(path), "-o", str(tmp_path / "o"), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_build_json_reports_problems(tmp_path, capsys):
    grad = [{"shape": {"all": True}, "fill": "#000000"},
            {"shape": {"ellipse": ["w / 2", 5, 3, 2]}, "fill": "#ffffff"}]
    path = write_spec(tmp_path, piece_spec(grad, size=(30, 10)))
    assert main(["build", str(path), "-o", str(tmp_path / "o"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False and "cannot stretch horizontally" in data["problems"]["p"][0]


@pytest.mark.parametrize("args", [["--help"], ["build", "--help"], ["verify", "--help"], ["export", "--help"]])
def test_help(args, capsys):
    with pytest.raises(SystemExit) as e:
        main(args)
    assert e.value.code == 0
    assert "usage: ninekit" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 2
    assert "build" in capsys.readouterr().out
