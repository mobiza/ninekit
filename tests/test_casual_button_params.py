"""casual_button params: presets, colour overrides, layers and validation."""
import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_block():
    # by path: the test depends on nothing else in ninekit
    name = "ninekit_casual_button_bypath"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "src" / "ninekit" / "blocks" / "casual_button.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


CB = _load_block()
S = 1   # small and quick: these tests compare renders with each other


def _arrays(res):
    return {k: np.asarray(v) for k, v in res["outputs"].items()}


def _same(a, b):
    return a.keys() == b.keys() and all(np.array_equal(a[k], b[k]) for k in a)


def test_presets():
    assert list(CB.PRESETS) == ["berry", "mint", "sky", "sun", "grape", "coal", "cloud", "gray"]
    for name, preset in CB.PRESETS.items():
        assert set(CB.REQUIRED_COLORS) <= set(preset) and "text_outline" in preset, name


def test_full_colour_set_without_style_equals_preset():
    for style in ("sun", "gray"):
        want = _arrays(CB.render({"style": style, "layers": ["frame", "face"]}, S))
        # as a YAML spec gives it: lists, not tuples; the defaults the preset leaves alone are given too
        colours = json.loads(json.dumps(CB.PRESETS[style]))
        colours.setdefault("sheen", CB.SHEEN)
        colours["bezel"] = {**json.loads(json.dumps(CB.BEZEL)), **colours.get("bezel", {})}
        assert _same(_arrays(CB.render({"colors": colours, "layers": ["frame", "face"]}, S)), want)


def test_single_colour_override():
    base = _arrays(CB.render({"style": "mint"}, S))
    face = _arrays(CB.render({"style": "mint", "colors": {"face_edge": "#ff0000"}}, S))
    assert np.array_equal(face["frame"], base["frame"]) and not np.array_equal(face["face"], base["face"])
    bezel = _arrays(CB.render({"style": "mint", "colors": {"bezel": {"inner": "#ffffff"}}}, S))
    assert np.array_equal(bezel["face"], base["face"]) and not np.array_equal(bezel["frame"], base["frame"])
    well = _arrays(CB.render({"style": "mint", "colors": {"well": "#000000"}}, S))
    assert np.array_equal(well["face"], base["face"]) and not np.array_equal(well["frame"], base["frame"])
    sheen = _arrays(CB.render({"style": "mint", "colors": {"sheen": "#ffe0f0"}}, S))
    assert np.array_equal(sheen["frame"], base["frame"]) and not np.array_equal(sheen["face"], base["face"])


def test_gradient_forms():
    flat = CB.render({"style": "mint", "colors": {"lip": "#17865d"}, "layers": ["face"]}, S)
    pair = CB.render({"style": "mint", "colors": {"lip": ["#17865d", "#17865d"]}, "layers": ["face"]}, S)
    stops = CB.render({"style": "mint", "colors": {"lip": [[0, "#17865d"], [1, [23, 134, 93]]]}, "layers": ["face"]}, S)
    assert _same(_arrays(flat), _arrays(pair)) and _same(_arrays(flat), _arrays(stops))
    # the bezel rings take gradients too; a flat one is one colour
    ring = CB.render({"style": "mint", "colors": {"bezel": {"outer": "#7c8a9f"}}, "layers": ["frame"]}, S)
    ring2 = CB.render({"style": "mint", "colors": {"bezel": {"outer": [[0, "#7c8a9f"], [1, "#7c8a9f"]]}},
                       "layers": ["frame"]}, S)
    assert _same(_arrays(ring), _arrays(ring2))


def test_sheen_and_lip():
    base = _arrays(CB.render({"style": "berry", "layers": ["frame", "face"]}, S))
    off = _arrays(CB.render({"style": "berry", "layers": ["frame", "face"], "sheen": 0}, S))
    assert np.array_equal(off["frame"], base["frame"]) and not np.array_equal(off["face"], base["face"])
    # the sheen only lightens the face's upper part
    diff = np.nonzero(np.abs(off["face"].astype(int) - base["face"].astype(int)).max(axis=(1, 2)))[0]
    assert diff.max() < 31
    lip = _arrays(CB.render({"style": "berry", "layers": ["face"], "lip": 3.0}, S))
    assert not np.array_equal(lip["face"], base["face"])
    # no sheen: its slice term is gone
    assert CB.render({"style": "berry", "layers": ["face"], "sheen": 0}, S)["slice_px"][0] < \
        CB.render({"style": "berry", "layers": ["face"]}, S)["slice_px"][0]


def test_layers_and_pressed():
    assert set(CB.render({"style": "berry", "layers": ["full"]}, S)["outputs"]) == {"main"}
    assert set(CB.render({"style": "berry", "layers": "face"}, S)["outputs"]) == {"face"}
    assert list(CB.render({"style": "berry", "layers": ["face", "full", "frame"]}, S)["outputs"]) == ["face", "main", "frame"]
    # pressed only changes the composite
    up = _arrays(CB.render({"style": "berry", "layers": ["frame", "face", "full"]}, S))
    down = _arrays(CB.render({"style": "berry", "layers": ["frame", "face", "full"], "pressed": True}, S))
    assert np.array_equal(up["frame"], down["frame"]) and np.array_equal(up["face"], down["face"])
    assert not np.array_equal(up["main"], down["main"])


def test_content_param():
    assert CB.render({"style": "berry", "content": None, "layers": ["face"]}, S)["content"] is None
    assert CB.render({"style": "berry", "content": [1, 2, 3, 4], "layers": ["face"]}, S)["content"] == [1, 2, 3, 4]


@pytest.mark.parametrize("params, words", [
    ({"style": "mint", "radus": 3}, "unknown params"),
    ({"style": "mauve"}, "unknown style"),
    ({"style": "mint", "colors": {"glos": "#fff000"}}, "unknown colours"),
    ({"style": "mint", "colors": {"bezel": {"gold": "#fff000"}}}, "unknown bezel colours"),
    ({"colors": {"face": "#ff0000"}}, "missing"),
    ({"style": "mint", "layers": ["frame", "frame"]}, "layers"),
    ({"style": "mint", "layers": ["shadow"]}, "layers"),
    ({"style": "mint", "colors": {"face_edge": "red"}}, "colour"),
    ({"style": "mint", "colors": {"wall": [[0, "#ff0000"]]}}, "gradient"),
    ({"style": "mint", "colors": {"bezel": {"rim_light": ["#ff0000", "#00ff00"]}}}, "colour"),
    ({"style": "mint", "ss": 0}, "ss"),
    ({"style": "mint", "sheen": 1.5}, "sheen"),
])
def test_bad_params(params, words):
    with pytest.raises(ValueError, match=words):
        CB.render(params, S)
