"""verify (DESIGN 5)."""
import json

import numpy as np
from PIL import Image

from conftest import piece_spec, write_spec
from ninekit.manifest import load_manifest, write_manifest
from ninekit.render import build
from ninekit.verify import verify, verify_manifest

PILL = [{"shape": {"rect": [0, 0, "w", "h"], "r": "h / 2"}, "fill": {"vgrad": [[0, "#99ccff"], [1, "#2266aa"]]}}]
GLOSS_IN_THE_MIDDLE = {"shape": {"ellipse": ["w / 2", 4, 6, 2]}, "fill": "#ffffff", "opacity": 0.6}


def test_good_piece_passes(tmp_path):
    rep = verify(write_spec(tmp_path, piece_spec(PILL, size=(60, 20), scales=[1, 2, 3])))
    assert rep.ok, rep.as_dict()
    assert len(rep.files) == 3


def test_horizontal_feature_in_the_middle_fails_with_auto(tmp_path):
    rep = verify(write_spec(tmp_path, piece_spec(PILL + [GLOSS_IN_THE_MIDDLE], size=(60, 20), scales=[1, 2])))
    assert not rep.ok
    reasons = " ".join(r for rs in rep.problems.values() for r in rs)
    assert "cannot stretch horizontally" in reasons and "side slices" in reasons


def test_horizontal_feature_in_the_middle_fails_with_explicit_slices(tmp_path):
    spec = piece_spec(PILL + [GLOSS_IN_THE_MIDDLE], size=(60, 20), scales=[2], slice=[10, 9, 10, 9])
    rep = verify(write_spec(tmp_path, spec))
    assert not rep.ok
    (f,) = rep.files
    assert f.status == "fail"
    assert "x stretch region [20, 100) is not uniform" in f.reasons[0]
    assert "horizontal feature" in f.reasons[0]


def test_hard_line_in_stretched_rows_fails(tmp_path):
    spec = piece_spec([{"shape": {"all": True}, "fill": "#335577"},
                       {"shape": {"rect": [0, 9, "w", 10]}, "fill": "#ffffff"}], size=(20, 20), scales=[1],
                      slice=[4, 4, 4, 4])
    (f,) = verify(write_spec(tmp_path, spec)).files
    assert f.status == "fail" and "y stretch region [4, 16) is not smooth" in f.reasons[0]


def _manifest_with(tmp_path, img: np.ndarray, slice_px, stretch=("stretch", "stretch")):
    Image.fromarray(img, "RGBA").save(tmp_path / "x.png")
    m = {"ninekit": 1, "name": "t", "generator": "test", "scales": [1], "pieces": {"x": {
        "size": [img.shape[1], img.shape[0]], "slice": slice_px, "stretch": list(stretch), "content": None,
        "overhang": None, "mode": "color", "stack": ["main"],
        "outputs": {"main": {"1": {"file": "x.png", "size_px": [img.shape[1], img.shape[0]], "slice_px": slice_px}}}}}}
    write_manifest(tmp_path / "ninekit.json", m)
    return tmp_path / "ninekit.json"


def test_tile_seams_are_checked(tmp_path):
    period = np.array([10, 60, 140, 220, 90], np.uint8)
    img = np.zeros((4, 2 + 5 * 3 + 2, 4), np.uint8)
    img[..., 3] = 255
    img[:, 2:17, 0] = np.tile(period, 3)
    img[:, 17:, 0] = period[:2]                 # the line after the region repeats its first: seamless
    rep = verify_manifest(_manifest_with(tmp_path, img, [2, 0, 2, 0], ("tile", "stretch")))
    assert rep.ok, rep.as_dict()
    img[:, 17, 0] = 200                          # break the seam
    (f,) = verify_manifest(_manifest_with(tmp_path, img, [2, 0, 2, 0], ("tile", "stretch"))).files
    assert f.status == "fail" and "not seamless" in f.reasons[0]


def test_rule1_slices_inside_and_rule4_outputs_agree(tmp_path):
    img = np.full((10, 10, 4), 255, np.uint8)
    (f,) = verify_manifest(_manifest_with(tmp_path, img, [6, 1, 5, 1])).files
    assert f.status == "fail" and "does not fit" in f.reasons[0]
    (f,) = verify_manifest(_manifest_with(tmp_path, img, [5, 1, 5, 1])).files
    assert f.status == "fail" and "x stretch region is empty" in f.reasons[0]
    (f,) = verify_manifest(_manifest_with(tmp_path, img, [5, 1, 5, 1], ("fixed", "stretch"))).files
    assert f.status == "ok", f.reasons
    spec = piece_spec([{"shape": {"all": True}, "fill": "#ffffff", "output": "a"},
                       {"shape": {"all": True}, "fill": "#000000", "output": "b"}], size=(20, 10), outputs=["a", "b"])
    res = build(write_spec(tmp_path, spec), out=tmp_path / "o")
    m = load_manifest(res.manifest_path)
    m["pieces"]["p"]["outputs"]["b"]["1"]["slice_px"] = [1, 1, 1, 1]
    write_manifest(res.manifest_path, m)
    rep = verify_manifest(res.manifest_path)
    assert not rep.ok and any("outputs differ" in r for f in rep.files for r in f.reasons)


def test_size_mismatch_and_missing_file(tmp_path):
    img = np.full((10, 10, 4), 255, np.uint8)
    mp = _manifest_with(tmp_path, img, [2, 2, 2, 2])
    m = json.loads(mp.read_text())
    m["pieces"]["x"]["outputs"]["main"]["1"]["size_px"] = [11, 10]
    mp.write_text(json.dumps(m))
    assert "manifest says" in verify_manifest(mp).files[0].reasons[0]
    (tmp_path / "x.png").unlink()
    assert "cannot read" in verify_manifest(mp).files[0].reasons[0]


def test_warnings(tmp_path):
    img = np.zeros((10, 2100, 4), np.uint8)
    img[:, :2, 3] = 255
    (f,) = verify_manifest(_manifest_with(tmp_path, img, [2, 1, 2, 1])).files
    assert f.status == "ok"
    text = " ".join(f.warnings)
    assert "fully transparent" in text and "larger than 2048" in text
    spec = piece_spec(PILL, size=(60, 20), scales=[3], slice_px=[2, 30, 2, 29])
    (f,) = verify(write_spec(tmp_path, spec)).files
    assert any("thinner than 1 dp" in w for w in f.warnings)


def test_verify_json_cli(tmp_path, capsys):
    from ninekit.cli import main

    bad = write_spec(tmp_path, piece_spec(PILL + [GLOSS_IN_THE_MIDDLE], size=(60, 20), scales=[1], slice=[10, 9, 10, 9]))
    assert main(["verify", str(bad), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["files"][0]["status"] == "fail" and out["files"][0]["reasons"]
    good = write_spec(tmp_path, piece_spec(PILL, size=(60, 20), scales=[1]), "good.yaml")
    assert main(["verify", str(good)]) == 0
    assert "verify: 1 ok, 0 fail" in capsys.readouterr().out
