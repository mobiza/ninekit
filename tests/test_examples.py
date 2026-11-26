"""The shipped examples build and verify (the Gumdrop specs are pinned pixel for pixel by test_gumdrop_golden.py)."""
import time

import pytest

from conftest import ROOT
from ninekit.render import build
from ninekit.verify import verify, verify_manifest

BASICS = ROOT / "examples" / "basics" / "basics.yaml"
OTHERS = sorted(p for p in (ROOT / "examples").glob("*/*.yaml") if p.parent.name not in ("basics", "gumdrop"))


def test_basics_builds_fast_at_three_scales_and_verifies(tmp_path):
    t = time.time()
    res = build(BASICS, out=tmp_path)
    assert time.time() - t < 10
    assert res.manifest["scales"] == [1, 2, 3]
    assert not res.problems
    pieces = res.manifest["pieces"]
    assert {"panel", "pill", "badge", "scifi", "bar_track", "bar_fill", "tab", "shade_button", "stone"} <= set(pieces)
    assert pieces["badge"]["slice"] is None
    assert pieces["tab"]["stack"] == ["frame", "face"]
    assert pieces["shade_button"]["mode"] == "shade"
    assert pieces["stone"]["stretch"] == ["tile", "tile"]
    for p in pieces.values():
        for per_scale in p["outputs"].values():
            assert set(per_scale) == {"1", "2", "3"}
    rep = verify_manifest(res.manifest_path)
    assert rep.ok, [f.as_dict() for f in rep.files if f.status != "ok"]


def test_basics_verify_from_spec():
    rep = verify(BASICS)
    assert rep.ok and not rep.problems


@pytest.mark.parametrize("spec", OTHERS, ids=[p.parent.name for p in OTHERS])
def test_other_examples_build_and_verify(spec, tmp_path):
    res = build(spec, out=tmp_path)
    assert not res.problems, res.problems
    rep = verify_manifest(res.manifest_path)
    assert rep.ok, [f.as_dict() for f in rep.files if f.status != "ok"]


def test_recreate_matches_its_reference(tmp_path):
    """examples/recreate: the measured spec stays close to the Pillow-drawn reference (README.md lists the metrics)."""
    from ninekit.compare import compare

    here = ROOT / "examples" / "recreate"
    res = compare(here / "capsule.yaml", "capsule", here / "reference.png", out=tmp_path / "cmp.png", ref_scale=3)
    assert res["mean_abs"] < 1.5 and res["psnr"] > 40 and res["over_16_pct"] == 0
