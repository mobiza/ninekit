import math

import numpy as np
import pytest

from ninekit import NinekitError
from ninekit.expr import evaluate
from ninekit.sdf import ALL_INSIDE, sdf_circle, sdf_ellipse, sdf_polygon, sdf_rrect, shape_sdf


def ev(v, what=""):
    return evaluate(v, {"w": 40.0, "h": 20.0})


def pts(*xy):
    a = np.array(xy, dtype=float)
    return a[:, 0], a[:, 1]


def reference_sdf_rrect(X, Y, x0, y0, x1, y1, r):
    # the reference rounded-rect sdf, written out: sdf_rrect must keep this exact float operation order
    tl, tr, br, bl = (r, r, r, r) if np.isscalar(r) else r
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hw, hh = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    right, below = X > cx, Y > cy
    rad = np.where(right, np.where(below, br, tr), np.where(below, bl, tl))
    qx = np.abs(X - cx) - (hw - rad)
    qy = np.abs(Y - cy) - (hh - rad)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return outside + inside - rad


def grid(w=40, h=20, s=3):
    ys, xs = np.mgrid[0:h * s, 0:w * s]
    return (xs + 0.5) / s, (ys + 0.5) / s


def test_rrect_matches_the_reference_exactly():
    X, Y = grid()
    for r in (3.0, (5.0, 1.0, 2.0, 0.5), 0):
        a = sdf_rrect(X, Y, 0.6, 1.2, 39.4, 18.7, r)
        b = reference_sdf_rrect(X, Y, 0.6, 1.2, 39.4, 18.7, r)
        assert np.array_equal(a, b)


def test_rect_distances():
    X, Y = pts((20, 10), (45, 10), (20, -3), (43, 24), (2, 10))
    d = sdf_rrect(X, Y, 0, 0, 40, 20, 0.0)
    assert d.tolist() == pytest.approx([-10, 5, 3, 5, -2])
    d = sdf_rrect(*pts((0, 0)), 0, 0, 40, 20, 4.0)
    assert d[0] == pytest.approx(math.hypot(4, 4) - 4)


def test_inset_equals_rect():
    X, Y = grid()
    a = shape_sdf({"inset": [1, 2, 3, 4], "r": 2}, X, Y, ev, 40.0, 20.0)
    b = sdf_rrect(X, Y, 1, 2, 37, 16, 2)
    assert np.array_equal(a, b)
    c = shape_sdf({"inset": 2}, X, Y, ev, 40.0, 20.0)
    assert np.array_equal(c, sdf_rrect(X, Y, 2, 2, 38, 18, 0.0))


def test_circle_and_ellipse():
    X, Y = pts((10, 10), (15, 10), (10, 2))
    assert sdf_circle(X, Y, 10, 10, 3).tolist() == pytest.approx([-3, 2, 5])
    e = sdf_ellipse(*pts((14, 10), (10, 12), (10, 10)), 10, 10, 4, 2)
    assert e.tolist() == pytest.approx([0, 0, -2])
    # rotated 90 degrees: the long axis turns vertical
    e = sdf_ellipse(*pts((10, 14), (12, 10)), 10, 10, 4, 2, 90)
    assert e.tolist() == pytest.approx([0, 0], abs=1e-9)


def test_polygon_exact_and_matches_rect():
    X, Y = grid(40, 20, 2)
    sq = sdf_polygon(X, Y, [(2, 3), (30, 3), (30, 17), (2, 17)])
    assert np.allclose(sq, sdf_rrect(X, Y, 2, 3, 30, 17, 0.0))
    # winding does not matter
    assert np.allclose(sq, sdf_polygon(X, Y, [(2, 17), (30, 17), (30, 3), (2, 3)]))
    # a right triangle: distances to its vertex and its hypotenuse
    tri = [(0, 0), (10, 0), (0, 10)]
    d = sdf_polygon(*pts((-3, -4), (10, 10), (1, 1)), tri)
    assert d.tolist() == pytest.approx([5, math.hypot(5, 5), -1])


def test_chamfer_is_exact_like_the_octagon_polygon():
    X, Y = grid(40, 20, 2)
    c = 4.0
    d = sdf_rrect(X, Y, 0, 0, 40, 20, 0.0, c)
    octagon = [(c, 0), (40 - c, 0), (40, c), (40, 20 - c), (40 - c, 20), (c, 20), (0, 20 - c), (0, c)]
    assert np.allclose(d, sdf_polygon(X, Y, octagon), atol=1e-9)
    # per corner: tl chamfered, tr rounded, br sharp, bl chamfered
    d2 = sdf_rrect(*pts((0, 0), (2, 2), (40, 0), (40, 20)), 0, 0, 40, 20, (0.0, 5.0, 0.0, 0.0), (3.0, 0.0, 0.0, 3.0))
    assert d2[0] == pytest.approx(3 / math.sqrt(2))       # outside the cut, along its normal
    assert d2[1] == pytest.approx(-(4 - 3) / math.sqrt(2))  # (2, 2): inside, 1/sqrt(2) past the cut x + y = 3
    assert d2[2] == pytest.approx(math.hypot(5, 5) - 5)    # rounded corner
    assert d2[3] == pytest.approx(0)                        # sharp corner


def test_chamfer_shape_and_lists_through_shape_sdf():
    X, Y = grid()
    a = shape_sdf({"rect": [0, 0, "w", "h"], "chamfer": [2, 0, 2, 0], "r": 1}, X, Y, ev, 40.0, 20.0)
    b = sdf_rrect(X, Y, 0, 0, 40.0, 20.0, 1, (2, 0, 2, 0))
    assert np.array_equal(a, b)


def test_booleans_and_all():
    X, Y = grid()
    a = {"circle": [10, 10, 6]}
    b = {"circle": [16, 10, 6]}
    da, db = (shape_sdf(s, X, Y, ev, 40.0, 20.0) for s in (a, b))
    assert np.array_equal(shape_sdf({"union": [a, b]}, X, Y, ev, 40.0, 20.0), np.minimum(da, db))
    assert np.array_equal(shape_sdf({"intersect": [a, b]}, X, Y, ev, 40.0, 20.0), np.maximum(da, db))
    assert np.array_equal(shape_sdf({"subtract": [a, b]}, X, Y, ev, 40.0, 20.0), np.maximum(da, -db))
    assert (shape_sdf({"all": True}, X, Y, ev, 40.0, 20.0) == ALL_INSIDE).all()


@pytest.mark.parametrize("shape, needle", [
    ({"rect": [0, 0, 1]}, "list of 4"),
    ({"circle": [0, 0, 1], "rect": [0, 0, 1, 1]}, "exactly one"),
    ({"circle": [0, 0, 1], "r": 2}, "does not take"),
    ({"polygon": [[0, 0], [1, 1]]}, "at least 3"),
    ({"subtract": [{"all": True}]}, "list of shapes"),
    ({"all": 1}, "all: true"),
    ({"ellipse": [0, 0, 0, 1]}, "positive"),
    ("circle", "mapping"),
])
def test_shape_errors(shape, needle):
    X, Y = grid(4, 4, 1)
    with pytest.raises(NinekitError, match=needle):
        shape_sdf(shape, X, Y, ev, 4.0, 4.0)
