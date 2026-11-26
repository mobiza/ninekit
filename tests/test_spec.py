import pytest
import yaml

from conftest import piece_spec, render_one, write_spec
from ninekit.render import build
from ninekit.spec import SpecError, deep_merge, load_spec


def _base_layers():
    return [{"shape": {"rect": [0, 0, "w", "h"], "r": "R"}, "fill": "main"}]


def test_deep_merge_dicts_recursively_lists_replaced():
    a = {"vars": {"A": 1, "B": 2}, "l": [1, 2], "x": {"y": {"z": 1}}}
    b = {"vars": {"B": 3, "C": 4}, "l": [9], "x": {"y": {"w": 2}}}
    m = deep_merge(a, b)
    assert m == {"vars": {"A": 1, "B": 3, "C": 4}, "l": [9], "x": {"y": {"z": 1, "w": 2}}}
    assert list(m["vars"]) == ["A", "B", "C"]
    assert a["vars"]["B"] == 2  # inputs untouched


def test_include_is_merged_first_and_this_file_wins(tmp_path):
    (tmp_path / "base.yaml").write_text(yaml.safe_dump({"vars": {"R": 2, "W": 20}, "colors": {"main": "#ff0000"}}))
    (tmp_path / "theme.yaml").write_text(yaml.safe_dump({"include": "base.yaml", "colors": {"main": "#00ff00"}}))
    spec = piece_spec(_base_layers(), size=["W", 10])
    spec["include"] = ["theme.yaml"]
    spec["vars"] = {"R": 3}
    s = load_spec(write_spec(tmp_path, spec))
    assert s.vars == {"R": 3, "W": 20}
    assert s.colors == {"main": "#00ff00"}
    r = render_one(tmp_path, spec)
    assert r.outputs["main"].shape[1] <= 20  # W from the include (auto-compacted)
    assert tuple(r.outputs["main"][5, r.outputs["main"].shape[1] // 2]) == (0, 255, 0, 255)


def test_include_cycle_is_an_error(tmp_path):
    (tmp_path / "a.yaml").write_text("include: b.yaml\n")
    (tmp_path / "b.yaml").write_text("include: a.yaml\n")
    spec = piece_spec(_base_layers())
    spec["include"] = "a.yaml"
    with pytest.raises(SpecError, match="include cycle"):
        load_spec(write_spec(tmp_path, spec))


def test_theme_merges_vars_colors_params_only(tmp_path):
    spec = piece_spec(_base_layers())
    spec["vars"] = {"R": 2}
    spec["colors"] = {"main": "#ff0000"}
    p = write_spec(tmp_path, spec)
    theme = tmp_path / "night.yaml"
    theme.write_text(yaml.safe_dump({"vars": {"R": 4}, "colors": {"main": "#0000ff"}}))
    s = load_spec(p, theme)
    assert s.vars["R"] == 4 and s.colors["main"] == "#0000ff"
    res = build(p, theme=theme, out=tmp_path / "out")
    assert res.manifest["pieces"]["p"]["outputs"]["main"]["1"]["file"] == "p.png"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"pieces": {"x": {}}}))
    with pytest.raises(SpecError, match="unknown key"):
        load_spec(p, bad)


def test_variants_share_everything_but_overrides(tmp_path):
    spec = piece_spec(_base_layers(), size=[12, 8])
    spec["vars"] = {"R": 2}
    spec["colors"] = {"main": "#ff0000"}
    spec["pieces"]["p"]["variants"] = {"p_blue": {"colors": {"main": "#0000ff"}},
                                       "p_wide": {"size": [30, 8], "vars": {"R": 4}}}
    s = load_spec(write_spec(tmp_path, spec))
    defs = s.piece_defs()
    assert [d.name for d in defs] == ["p", "p_blue", "p_wide"]
    assert defs[1].colors["main"] == "#0000ff" and defs[1].data["size"] == [12, 8]
    assert defs[2].vars["R"] == 4 and defs[2].data["size"] == [30, 8]
    assert "variants" not in defs[0].data
    blue = render_one(tmp_path, spec, piece="p_blue").outputs["main"]
    assert tuple(blue[blue.shape[0] // 2, blue.shape[1] // 2]) == (0, 0, 255, 255)


def test_variant_name_collision(tmp_path):
    spec = piece_spec(_base_layers())
    spec["vars"] = {"R": 1}
    spec["colors"] = {"main": "#ff0000"}
    spec["pieces"]["q"] = dict(spec["pieces"]["p"])
    spec["pieces"]["p"]["variants"] = {"q": {}}
    with pytest.raises(SpecError, match="used twice"):
        load_spec(write_spec(tmp_path, spec)).piece_defs()


@pytest.mark.parametrize("mutate, needle", [
    (lambda s: s.pop("ninekit"), "ninekit: 1"),
    (lambda s: s.update(bogus=1), "unknown key"),
    (lambda s: s["pieces"]["p"]["layers"][0].update(fil="#fff"), "unknown key"),
    (lambda s: s["pieces"]["p"]["layers"][0].pop("fill"), "`fill` is required"),
    (lambda s: s["pieces"]["p"].pop("size"), "size"),
    (lambda s: s.update(vars={"scale": 2}), "reserved"),
    (lambda s: s.update(vars={"round": 2}), "reserved"),
    (lambda s: s.update(vars={"L": [1, 2]}), "number or an expression"),
    (lambda s: s.update(file="{piece}{bad}.png"), "unknown token"),
    (lambda s: s.update(scales=[0]), "positive"),
    (lambda s: s["pieces"]["p"].update(slice=[1, 1, 1, 1], slice_px=[1, 1, 1, 1]), "not both"),
    (lambda s: s["pieces"]["p"].update(block="casual_button"), "exactly one"),
])
def test_validation_errors(tmp_path, mutate, needle):
    spec = piece_spec([{"shape": {"all": True}, "fill": "#ffffff"}])
    mutate(spec)
    with pytest.raises(SpecError, match=needle):
        load_spec(write_spec(tmp_path, spec))


def test_only_filters_pieces(tmp_path):
    spec = piece_spec([{"shape": {"all": True}, "fill": "#ffffff"}])
    spec["pieces"]["q"] = dict(spec["pieces"]["p"])
    s = load_spec(write_spec(tmp_path, spec))
    assert [d.name for d in s.piece_defs(["q"])] == ["q"]
    with pytest.raises(SpecError, match="unknown piece"):
        s.piece_defs(["zzz"])


def test_top_level_params_merge_into_block_pieces(tmp_path):
    spec = {"ninekit": 1, "pieces": {"b": {"block": "x", "params": {"a": 1, "b": 2}}},
            "params": {"*": {"b": 3, "c": 4}, "b": {"c": 5}}}
    s = load_spec(write_spec(tmp_path, spec))
    assert s.piece_defs()[0].params == {"a": 1, "b": 3, "c": 5}
