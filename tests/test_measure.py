import importlib.util
import sys
import json
import pathlib

import pytest
from PIL import Image

try:
    from ninekit import measure as M
except ImportError:  # package __init__ not there yet: import by path
    _p = pathlib.Path(__file__).resolve().parents[1] / "src" / "ninekit" / "measure.py"
    _spec = importlib.util.spec_from_file_location("ninekit_measure", _p)
    M = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = M
    _spec.loader.exec_module(M)


def column(rows, w=4):
    """Image w wide whose row i is rows[i] (an RGBA tuple)."""
    img = Image.new("RGBA", (w, len(rows)))
    for y, c in enumerate(rows):
        for x in range(w):
            img.putpixel((x, y), c)
    return img


BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
GREEN = (60, 160, 40, 255)


def test_outline_gradient_flat():
    rows = [BLACK] * 2
    rows += [(200, 220 - 10 * i, 60, 255) for i in range(6)]  # smooth 6 px gradient
    rows += [GREEN] * 10
    bands = M.measure_line(column(rows), "x", 1)
    assert [(b.start, b.end) for b in bands] == [(0, 2), (2, 8), (8, 18)]
    assert [b.thickness for b in bands] == [2, 6, 10]
    assert [b.flat for b in bands] == [True, False, True]
    assert M.hex_color(bands[0].start_color) == "#000000"
    assert M.hex_color(bands[1].start_color) == "#c8dc3c"
    assert M.hex_color(bands[1].end_color) == "#c8aa3c"
    assert M.hex_color(bands[2].mid_color) == "#3ca028"


def test_antialiased_edge_absorbed():
    rows = [BLACK] * 3 + [(128, 128, 128, 255)] + [WHITE] * 3
    bands = M.measure_line(column(rows), "x", 0)
    assert len(bands) == 2
    assert bands[0].end in (3, 4) and bands[0].end == bands[1].start


def test_real_thin_line_kept():
    rows = [WHITE] * 3 + [(200, 40, 40, 255)] + [WHITE] * 3
    bands = M.measure_line(column(rows), "x", 0)
    assert [b.thickness for b in bands] == [3, 1, 3]


def test_min_band_merges():
    rows = [WHITE] * 3 + [(200, 40, 40, 255)] + [WHITE] * 3
    bands = M.measure_line(column(rows), "x", 0, min_band=2)
    assert len(bands) == 1 and bands[0].thickness == 7


def test_semi_transparent():
    rows = [GREEN] * 3 + [(60, 160, 40, 128)] * 4
    bands = M.measure_line(column(rows), "x", 0)
    assert [b.thickness for b in bands] == [3, 4]
    assert bands[1].start_color[3] == 128
    d = bands[1].to_dict()
    assert d["start_alpha"] == 128 and d["start_color"] == "#3ca028"


def test_horizontal_range_and_offset():
    img = Image.new("RGBA", (10, 3), WHITE)
    for x in range(5, 10):
        for y in range(3):
            img.putpixel((x, y), BLACK)
    bands = M.measure_line(img, "y", 1, start=2, end=9)
    assert [(b.start, b.end) for b in bands] == [(2, 5), (5, 9)]


def test_avg_reduces_noise():
    img = Image.new("RGBA", (4, 6))
    for y in range(6):
        for x in range(4):
            v = 100 + (30 if x % 2 else -30)  # column noise of +-30
            img.putpixel((x, y), (v, v, v, 255))
    assert len(M.measure_line(img, "x", 1, avg=1, tol=10)) == 1  # constant per column anyway
    for y in range(3):
        for x in range(4):
            img.putpixel((x, y), (255, 255, 255, 255) if x % 2 else (0, 0, 0, 255))
    # raw column 1 is white for 3 rows then 130: one jump; averaging 2 cols gives 127 then 100: no jump
    assert len(M.measure_line(img, "x", 1, avg=1, tol=10)) == 2
    assert len(M.measure_line(img, "x", 1, avg=2, tol=40)) == 1


def test_out_of_range():
    with pytest.raises(ValueError):
        M.measure_line(column([WHITE] * 3), "x", 9)


def test_cli_json_and_dp(tmp_path, capsys):
    f = tmp_path / "t.png"
    column([BLACK] * 4 + [WHITE] * 8).save(f)
    rc = M.main([str(f), "--x", "1", "--ref-width", "100", "--design-width", "50", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert [d["thickness_px"] for d in data] == [4, 8]
    assert [d["thickness_dp"] for d in data] == [2.0, 4.0]
    assert data[0]["start_color"] == "#000000" and data[1]["kind"] == "flat"


def test_cli_table(tmp_path, capsys):
    f = tmp_path / "t.png"
    column([BLACK] * 4 + [WHITE] * 8).save(f)
    assert M.main([str(f), "--x", "1", "--ref-width", "100", "--design-width", "50"]) == 0
    out = capsys.readouterr().out
    assert "#000000" in out and "2.00" in out and "flat" in out
    assert M.main([str(f), "--x", "99"]) == 2


REAL = pathlib.Path(__file__).resolve().parent / "fixtures" / "gumdrop" / "buttons" / "btn_mint_face@3x.png"


def test_real_asset():
    img = Image.open(REAL)
    bands = M.measure_line(img, "x", img.width // 2)
    assert 1 <= len(bands) <= 20
    assert bands[0].start == 0 and bands[-1].end == img.height
    assert all(a.end == b.start for a, b in zip(bands, bands[1:]))


DARK = (50, 80, 20)


def test_two_px_alpha_ramp_into_transparency():
    rows = [(0, 0, 0, 0)] * 4 + [DARK + (70,), DARK + (170,)] + [DARK + (255,)] * 6
    bands = M.measure_line(column(rows), "x", 0)
    assert [(b.start, b.end) for b in bands] == [(0, 4), (4, 12)]
    assert bands[1].soft_start == 2 and bands[1].soft_end == 0
    assert bands[1].start_color == DARK + (255,)  # colours come from the solid core
    assert bands[1].flat
    assert bands[1].to_dict()["soft_start"] == 2


def test_one_px_aa_edge_at_end():
    rows = [GREEN] * 5 + [GREEN[:3] + (100,)] + [(0, 0, 0, 0)] * 4
    bands = M.measure_line(column(rows), "x", 0)
    assert [(b.start, b.end) for b in bands] == [(0, 6), (6, 10)]
    assert bands[0].soft_end == 1 and bands[0].soft_start == 0
    assert bands[0].thickness == 6


def test_three_px_ramp():
    rows = [(0, 0, 0, 0)] * 2 + [DARK + (40,), DARK + (100,), DARK + (180,)] + [DARK + (255,)] * 5
    bands = M.measure_line(column(rows), "x", 0)
    assert len(bands) == 2 and bands[1].soft_start == 3


def test_real_outline_next_to_soft_edge_kept():
    outline = (20, 10, 5, 255)
    rows = [(0, 0, 0, 0)] * 3 + [(20, 10, 5, 90)] + [outline] + [GREEN] * 6
    bands = M.measure_line(column(rows), "x", 0)
    # the soft pixel is its own edge, not a band; the opaque 1 px outline stays a band
    assert [(b.start, b.end) for b in bands] == [(0, 3), (3, 5), (5, 11)]
    assert bands[1].soft_start == 1 and bands[1].start_color == outline
    assert bands[2].soft_start == 0


def test_opaque_outline_next_to_transparency_not_soft():
    rows = [(0, 0, 0, 0)] * 3 + [(20, 10, 5, 255)] + [GREEN] * 6
    bands = M.measure_line(column(rows), "x", 0)
    assert [b.thickness for b in bands] == [3, 1, 6]
    assert all(b.soft_start == 0 and b.soft_end == 0 for b in bands)


# ---- min_alpha, sub-pixel edges, corner fit ----

import numpy as np


def test_min_alpha_kills_stray_pixels():
    rows = [(0, 0, 0, 0)] * 3 + [(200, 30, 90, 5)] + [(0, 0, 0, 0)] * 2 + [(10, 250, 10, 3)] + [GREEN] * 5
    bands = M.measure_line(column(rows), "x", 0)
    assert [(b.start, b.end) for b in bands] == [(0, 7), (7, 12)] or len(bands) == 2
    assert bands[0].start_color[3] == 0
    # with min_alpha 0 the strays are bands again
    assert len(M.measure_line(column(rows), "x", 0, min_alpha=0)) > 2


def test_subpixel_silhouette_edge_from_alpha():
    # material starts 0.4 px into row 4: row 4 has coverage 0.6
    rows = [(0, 0, 0, 0)] * 4 + [GREEN[:3] + (round(0.6 * 255),)] + [GREEN] * 6
    bands = M.measure_line(column(rows), "x", 0)
    assert len(bands) == 2
    assert bands[1].edge_start == pytest.approx(4.4, abs=0.02)
    assert bands[0].edge_end == pytest.approx(4.4, abs=0.02)
    assert bands[1].soft_start == 1


def test_subpixel_silhouette_edge_two_px_ramp_end():
    # material ends 1.25 px into the ramp: coverage 1, 0.25 ... (alpha 255, 64)
    rows = [GREEN] * 5 + [GREEN[:3] + (255,)] * 0 + [GREEN[:3] + (170,), GREEN[:3] + (40,)] + [(0, 0, 0, 0)] * 4
    bands = M.measure_line(column(rows), "x", 0)
    assert bands[0].soft_end == 2
    assert bands[0].edge_end == pytest.approx(5 + (170 + 40) / 255, abs=0.02)


def test_subpixel_inner_edge_from_colour_interpolation():
    a, b = (200, 40, 40), (40, 40, 200)
    mid = tuple(round(0.7 * x + 0.3 * y) for x, y in zip(a, b))  # 30 % of the pixel is band B
    rows = [a + (255,)] * 4 + [mid + (255,)] + [b + (255,)] * 4
    bands = M.measure_line(column(rows), "x", 0)
    assert len(bands) == 2
    assert bands[0].edge_end == pytest.approx(4.7, abs=0.03) == pytest.approx(bands[1].edge_start, abs=1e-9)
    assert bands[0].flat and bands[1].flat
    d = bands[0].to_dict(0.5)
    assert d["edge_end"] == pytest.approx(4.7, abs=0.03) and d["edge_end_dp"] == pytest.approx(2.35, abs=0.02)


def rounded_rect_alpha(w, h, x0, y0, x1, y1, r, ss=64):
    """Exact-ish coverage of a rounded rect [x0,x1]x[y0,y1] (px, fractional) by ss x ss supersampling."""
    ys = (np.arange(h * ss) + 0.5) / ss
    xs = (np.arange(w * ss) + 0.5) / ss
    X, Y = np.meshgrid(xs, ys)
    cx = np.clip(X, x0 + r, x1 - r)
    cy = np.clip(Y, y0 + r, y1 - r)
    inside = ((X - cx) ** 2 + (Y - cy) ** 2 <= r * r) & (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    cov = inside.reshape(h, ss, w, ss).mean(axis=(1, 3))
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = (120, 200, 60)
    img[..., 3] = np.rint(cov * 255)
    return Image.fromarray(img, "RGBA")


@pytest.mark.parametrize("corner", ["tl", "tr", "bl", "br"])
@pytest.mark.parametrize("r", [4.0, 9.3, 16.0, 20.0])
def test_corner_fit_radius(corner, r):
    img = rounded_rect_alpha(80, 50, 3.3, 2.6, 76.4, 46.9, r)
    res = M.fit_corner(img, corner)
    assert res["radius_px"] == pytest.approx(r, abs=0.05)
    dx = 3.3 if corner in ("tl", "bl") else 80 - 76.4
    dy = 2.6 if corner in ("tl", "tr") else 50 - 46.9
    assert res["edge_x_px"] == pytest.approx(dx, abs=0.05)
    assert res["edge_y_px"] == pytest.approx(dy, abs=0.05)


def test_corner_cli_dp_and_box(tmp_path, capsys):
    img = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    img.paste(rounded_rect_alpha(80, 50, 3.0, 3.0, 77.0, 47.0, 12.0), (20, 10))
    f = tmp_path / "c.png"
    img.save(f)
    rc = M.main([str(f), "--corner", "tl", "--box", "20,10,100,60", "--ref-width", "120",
                 "--design-width", "60", "--json"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["radius_px"] == pytest.approx(12.0, abs=0.05)
    assert d["radius_dp"] == pytest.approx(6.0, abs=0.03)
    assert d["box"] == [20, 10, 100, 60]


def test_cli_requires_one_mode(tmp_path):
    f = tmp_path / "t.png"
    column([BLACK] * 4).save(f)
    with pytest.raises(SystemExit):
        M.main([str(f)])
    with pytest.raises(SystemExit):
        M.main([str(f), "--x", "1", "--corner", "tl"])


def test_json_schema_documented():
    for key in ("edge_start", "edge_end", "thickness_dp", "soft_start", "radius_px", "edge_x_px"):
        assert key in M.__doc__
    d = M.measure_line(column([BLACK] * 3 + [WHITE] * 3), "x", 0)[0].to_dict()
    for key in ("start", "end", "thickness_px", "thickness_dp", "start_dp", "end_dp", "edge_start", "edge_end",
                "edge_start_dp", "edge_end_dp", "kind", "soft_start", "soft_end", "start_color", "mid_color",
                "end_color", "start_alpha", "mid_alpha", "end_alpha"):
        assert key in d and key in M.__doc__
