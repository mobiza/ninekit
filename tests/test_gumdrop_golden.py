"""Golden test: examples/gumdrop/{buttons,scoreboard}.yaml rebuild exactly to tests/fixtures/gumdrop/.

Every file of every scale must have the same RGBA pixels as its fixture, the set of files must be the same, and the
manifest (ninekit.json) must be equal apart from `generator` (the version string). A failure means the renderer, the
casual_button block or the specs changed what they draw. When the Gumdrop art is changed on purpose, look at the
new `ninekit preview` sheets first, then rewrite the fixtures with

    NINEKIT_UPDATE_GOLDEN=1 PYTHONPATH=src python3 -m pytest -q tests/test_gumdrop_golden.py
"""
import json
import os
import shutil

import numpy as np
import pytest

from conftest import ROOT, load_rgba
from ninekit.render import build
from ninekit.verify import verify_manifest

SPECS = ("buttons", "scoreboard")
FIXTURES = ROOT / "tests" / "fixtures" / "gumdrop"
UPDATE = os.environ.get("NINEKIT_UPDATE_GOLDEN") == "1"


@pytest.fixture(scope="module", params=SPECS)
def built(request, tmp_path_factory):
    name = request.param
    res = build(ROOT / "examples" / "gumdrop" / f"{name}.yaml", out=tmp_path_factory.mktemp(name))
    if UPDATE:
        shutil.rmtree(FIXTURES / name, ignore_errors=True)
        shutil.copytree(res.out_dir, FIXTURES / name)
    return name, res


def _manifest(path):
    m = json.loads(path.read_text())
    m.pop("generator", None)
    return m


def test_same_files(built):
    name, res = built
    ours = sorted(p.name for p in res.out_dir.iterdir())
    golden = sorted(p.name for p in (FIXTURES / name).iterdir())
    assert ours == golden


def test_pixels_equal(built):
    name, res = built
    pngs = sorted(p.name for p in (FIXTURES / name).glob("*.png"))
    assert pngs
    bad = []
    for f in pngs:
        a, b = load_rgba(res.out_dir / f), load_rgba(FIXTURES / name / f)
        if a.shape != b.shape:
            bad.append(f"{f}: size {a.shape[1]}x{a.shape[0]}, golden {b.shape[1]}x{b.shape[0]}")
        elif not np.array_equal(a, b):
            d = np.abs(a.astype(int) - b.astype(int))
            bad.append(f"{f}: max abs diff {d.max()}, {int((d.max(axis=2) > 0).sum())} px differ")
    assert not bad, "\n".join(bad)


def test_manifest_equal(built):
    name, res = built
    assert _manifest(res.manifest_path) == _manifest(FIXTURES / name / "ninekit.json")


def test_clean_build_and_verify(built):
    name, res = built
    assert not res.problems and not res.warnings, (res.problems, res.warnings)
    rep = verify_manifest(res.manifest_path)
    assert rep.ok, [f.as_dict() for f in rep.files if f.status != "ok"]
    assert not any(f.warnings for f in rep.files), [f.as_dict() for f in rep.files if f.warnings]


def test_buttons_metadata():
    m = _manifest(FIXTURES / "buttons" / "ninekit.json")
    assert m["name"] == "gumdrop_buttons" and m["scales"] == [1, 2, 3]
    styles = ("berry", "mint", "sky", "sun", "grape", "coal", "cloud", "gray")
    assert set(m["pieces"]) == {f"btn_{s}" for s in styles} | {f"btnc_{s}" for s in styles}
    rect, rnd = m["pieces"]["btn_berry"], m["pieces"]["btnc_sky"]
    assert rect["design_size"] == [128.0, 62.0] and rnd["size"] == [62.0, 62.0] and rnd["slice"] is None
    assert rect["content"] == [12.0, 8.0, 12.0, 17.0] and rect["overhang"] == [0.0, 0.0, 0.0, 3.0]
    assert rect["stack"] == ["frame", "face"] and rnd["stack"] == ["frame", "face", "main"]
    # several scales: one dp slice on the grid for every file (DESIGN 2.3), y fixed (a button has a natural height)
    assert rect["stretch"] == ["stretch", "fixed"]
    for per in rect["outputs"].values():
        for k, e in per.items():
            assert e["slice_px"] == [round(v * int(k)) for v in rect["slice"]]
