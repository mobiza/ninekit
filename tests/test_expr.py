import math
import time

import pytest

from ninekit.expr import ExprError, Scope, evaluate, names_in


def test_numbers_pass_through():
    assert evaluate(3) == 3
    assert evaluate(2.5) == 2.5
    assert evaluate("4") == 4


def test_arithmetic_matches_python_float_order():
    K = 430 / 923
    env = {"K": K, "scale": 3}
    assert evaluate("round(149 * K * scale) / scale", env) == round(149 * K * 3) / 3
    assert evaluate("(22 * K + 1.33) * scale", env) == (22 * K + 1.33) * 3
    assert evaluate("1 - 2 - 3") == -4
    assert evaluate("2 ** 3 ** 2") == 2 ** 3 ** 2
    assert evaluate("-2 ** 2") == -4
    assert evaluate("7 // 2") == 3 and evaluate("-7 // 2") == -4
    assert evaluate("7 % 3") == 1
    assert evaluate("+(1 + 2) * 3") == 9


def test_round_is_bankers():
    assert evaluate("round(2.5)") == 2
    assert evaluate("round(3.5)") == 4
    assert evaluate("round(-0.5)") == 0
    assert isinstance(evaluate("round(2.6)"), int)
    assert evaluate("round(0.125, 2)") == round(0.125, 2)


def test_functions():
    assert evaluate("min(3, 1, 2)") == 1
    assert evaluate("max(3, 1, 2)") == 3
    assert evaluate("abs(-2)") == 2
    assert evaluate("floor(2.7)") == 2
    assert evaluate("ceil(2.1)") == 3
    assert evaluate("sqrt(16)") == 4
    assert evaluate("sin(pi / 2)") == pytest.approx(1.0)
    assert evaluate("cos(0)") == 1.0
    assert evaluate("clamp(5, 0, 3)") == 3 and evaluate("clamp(-1, 0, 3)") == 0 and evaluate("clamp(2, 0, 3)") == 2
    assert evaluate("lerp(10, 20, 0.25)") == 12.5


def test_comparisons_give_one_or_zero():
    assert evaluate("scale >= 2", {"scale": 3}) == 1
    assert evaluate("scale >= 2", {"scale": 1}) == 0
    assert evaluate("1 < 2 < 3") == 1
    assert evaluate("1 < 3 < 2") == 0


@pytest.mark.parametrize("src, needle", [
    ("x.real", "attribute"),
    ("(1).bit_length()", "plain function"),
    ("a[0]", "subscript"),
    ("eval('1')", "unknown function"),
    ("__import__('os')", "unknown function"),
    ("open(1)", "unknown function"),
    ("'abc'", "only numbers"),
    ("lambda: 1", "Lambda"),
    ("round(x=1)", "keyword"),
    ("[1, 2]", "List"),
    ("1 if 1 else 2", "IfExp"),
    ("x := 3", "syntax"),
    ("1 and 2", "BoolOp"),
    ("~1", "Invert"),
    ("True", "only numbers"),
    ("min(*[1])", "args"),
])
def test_rejects_everything_outside_the_whitelist(src, needle):
    with pytest.raises(ExprError) as e:
        evaluate(src, {"x": 1, "a": 1})
    assert needle.lower() in str(e.value).lower()


def test_errors_are_clear():
    with pytest.raises(ExprError, match="unknown name 'nope'"):
        evaluate("nope + 1")
    with pytest.raises(ExprError, match="division by zero"):
        evaluate("1 / 0")
    with pytest.raises(ExprError, match="syntax"):
        evaluate("1 +")
    with pytest.raises(ExprError, match="sqrt"):
        evaluate("sqrt(-1)")


def test_huge_powers_do_not_hang():
    t = time.time()
    with pytest.raises(ExprError):
        evaluate("10 ** 10 ** 10")
    assert time.time() - t < 1.0


def test_names_in():
    assert names_in("a + b * round(c)") == {"a", "b", "c", "round"}
    assert names_in(3) == set()


def test_scope_lazy_vars_forward_refs_and_innermost_wins():
    s = Scope({"B": "A * 2", "A": 3}, {"scale": 2})
    assert s.eval("B + scale") == 8
    # piece vars override spec vars in one flat scope: dependants see the override
    s2 = Scope({**{"R": 10, "M": "R + 2"}, **{"R": 20}}, {"scale": 1})
    assert s2.eval("M") == 22


def test_scope_cycle_is_reported():
    s = Scope({"A": "B + 1", "B": "A + 1"}, {"scale": 1}, where="piece p")
    with pytest.raises(ExprError, match="cycle"):
        s.eval("A")


def test_w_and_h_only_inside_layers():
    s = Scope({"FB": "h - 3"}, {"scale": 2})
    with pytest.raises(ExprError, match="'h' is not available here"):
        s.eval("FB")
    inner = s.child(w=10.0, h=8.0)
    assert inner.eval("FB") == 5.0
    assert inner.eval("w * h") == 80.0
    with pytest.raises(ExprError, match="w_px"):
        inner.eval("w_px")
    assert inner.child(w_px=20, h_px=16).eval("w_px + h_px") == 36


def test_scope_error_names_the_place():
    s = Scope({}, {"scale": 1}, where="piece card @1x")
    with pytest.raises(ExprError, match=r"piece card @1x size\[0\]: unknown name 'X'"):
        s.eval("X", "size[0]")


def test_math_constant_pi():
    assert evaluate("pi") == math.pi
