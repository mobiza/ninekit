"""Safe arithmetic expressions for spec values (DESIGN 2.1).

Expressions are parsed with `ast` and walked against a whitelist; nothing is ever passed to `eval`.
Evaluation follows Python's own float semantics and operator order so legacy generator numbers
(e.g. `round(149 * K * scale) / scale`) reproduce bit for bit.
"""
from __future__ import annotations

import ast
import functools
import math
import operator
from typing import Any, Callable, Mapping

from ninekit import NinekitError


class ExprError(NinekitError):
    """An expression that cannot be parsed, is not allowed, or fails to evaluate."""


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _lerp(a, b, t):
    return a + (b - a) * t


def _round(x, n=None):
    # Python's round: banker's rounding, int result with one argument.
    return round(x) if n is None else round(x, int(n))


FUNCS: dict[str, Callable] = {
    "round": _round,
    "min": min,
    "max": max,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "clamp": _clamp,
    "lerp": _lerp,
}
CONSTS = {"pi": math.pi}
# Names provided by the renderer, never by vars.
BUILTIN_NAMES = ("scale", "w", "h", "w_px", "h_px")
RESERVED = set(FUNCS) | set(CONSTS) | set(BUILTIN_NAMES)

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: None,  # guarded, see _pow
}
_UNOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_CMPOPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def _pow(a, b):
    # Huge integer powers would hang the interpreter; go through floats past a small bound.
    if isinstance(a, int) and isinstance(b, int) and abs(b) <= 64 and abs(a) <= 1 << 32:
        return a ** b
    try:
        r = float(a) ** float(b)
    except (OverflowError, ZeroDivisionError) as e:
        raise ExprError(f"power {a} ** {b}: {e}") from None
    if isinstance(r, complex):
        raise ExprError(f"power {a} ** {b} is not a real number")
    return r


def _check(node: ast.AST, src: str) -> None:
    """Rejects every node kind outside the whitelist, with a message naming it."""
    if isinstance(node, ast.Expression):
        _check(node.body, src)
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise ExprError(f"{src!r}: operator {type(node.op).__name__} is not allowed")
        _check(node.left, src)
        _check(node.right, src)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNOPS:
            raise ExprError(f"{src!r}: operator {type(node.op).__name__} is not allowed")
        _check(node.operand, src)
    elif isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _CMPOPS:
                raise ExprError(f"{src!r}: comparison {type(op).__name__} is not allowed")
        _check(node.left, src)
        for c in node.comparators:
            _check(c, src)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExprError(f"{src!r}: only numbers are allowed as literals, not {node.value!r}")
    elif isinstance(node, ast.Name):
        if not isinstance(node.ctx, ast.Load):
            raise ExprError(f"{src!r}: assignment is not allowed")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExprError(f"{src!r}: only plain function calls are allowed ({', '.join(sorted(FUNCS))})")
        if node.func.id not in FUNCS:
            raise ExprError(f"{src!r}: unknown function {node.func.id!r} (allowed: {', '.join(sorted(FUNCS))})")
        if node.keywords:
            raise ExprError(f"{src!r}: keyword arguments are not allowed")
        for a in node.args:
            if isinstance(a, ast.Starred):
                raise ExprError(f"{src!r}: *args is not allowed")
            _check(a, src)
    elif isinstance(node, ast.Attribute):
        raise ExprError(f"{src!r}: attribute access (.{node.attr}) is not allowed")
    elif isinstance(node, ast.Subscript):
        raise ExprError(f"{src!r}: subscripts ([...]) are not allowed")
    else:
        raise ExprError(f"{src!r}: {type(node).__name__} is not allowed in an expression")


@functools.lru_cache(maxsize=8192)
def parse(src: str) -> ast.AST:
    """Parses and validates [src]; cached because specs evaluate the same strings per scale."""
    text = src.strip()
    if not text:
        raise ExprError("empty expression")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"{src!r}: syntax error ({e.msg})") from None
    _check(tree, src)
    return tree.body


def _eval(node: ast.AST, lookup: Callable[[str], Any], src: str):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return lookup(node.id)
    if isinstance(node, ast.BinOp):
        a = _eval(node.left, lookup, src)
        b = _eval(node.right, lookup, src)
        _need_number(a, src)
        _need_number(b, src)
        if isinstance(node.op, ast.Pow):
            return _pow(a, b)
        try:
            return _BINOPS[type(node.op)](a, b)
        except ZeroDivisionError:
            raise ExprError(f"{src!r}: division by zero") from None
        except OverflowError as e:
            raise ExprError(f"{src!r}: {e}") from None
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, lookup, src)
        _need_number(v, src)
        return _UNOPS[type(node.op)](v)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, lookup, src)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, lookup, src)
            if not _CMPOPS[type(op)](left, right):
                return 0
            left = right
        return 1
    if isinstance(node, ast.Call):
        args = [_eval(a, lookup, src) for a in node.args]
        for a in args:
            _need_number(a, src)
        try:
            return FUNCS[node.func.id](*args)
        except (TypeError, ValueError, OverflowError) as e:
            raise ExprError(f"{src!r}: {node.func.id}(): {e}") from None
    raise ExprError(f"{src!r}: cannot evaluate {type(node).__name__}")  # unreachable after _check


def _need_number(v, src):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ExprError(f"{src!r}: {v!r} is not a number")


def evaluate(value, lookup: Callable[[str], Any] | Mapping[str, Any] | None = None):
    """A number from a number or an expression string; [lookup] resolves names (callable or mapping)."""
    if isinstance(value, bool):
        raise ExprError(f"expected a number or an expression, got {value!r}")
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        raise ExprError(f"expected a number or an expression, got {value!r}")
    if lookup is None:
        lookup = {}
    if not callable(lookup):
        names = lookup

        def lookup(n, _names=names):
            if n in _names:
                return _names[n]
            if n in CONSTS:
                return CONSTS[n]
            raise ExprError(f"unknown name {n!r}")

    result = _eval(parse(value), lookup, value)
    _need_number(result, value)
    return result


def names_in(value) -> set[str]:
    """The names an expression refers to (empty for plain numbers)."""
    if not isinstance(value, str):
        return set()
    return {n.id for n in ast.walk(parse(value)) if isinstance(n, ast.Name)}


class Scope:
    """Lazy, memoised name resolution: built-ins (scale, w, h, ...) first, then vars, then constants.

    Vars are resolved on demand in one flat scope (spec < theme < piece < variant, innermost wins), so a
    var may use any other var; cycles are reported. Only successful results are memoised: a var that
    needs `w` fails while the piece size is evaluated and succeeds later, once `w` is set.
    """

    def __init__(self, vars: Mapping[str, Any] | None = None, builtins: Mapping[str, Any] | None = None,
                 where: str = ""):
        self.vars = dict(vars or {})
        self.builtins = dict(builtins or {})
        self.where = where
        self._memo: dict[str, Any] = {}
        self._stack: list[str] = []

    def set(self, name: str, value) -> None:
        self.builtins[name] = value

    def lookup(self, name: str):
        if name in self.builtins:
            return self.builtins[name]
        if name in self._memo:
            return self._memo[name]
        if name in self.vars:
            if name in self._stack:
                chain = " -> ".join(self._stack[self._stack.index(name):] + [name])
                raise ExprError(f"vars refer to each other in a cycle: {chain}")
            self._stack.append(name)
            try:
                v = evaluate(self.vars[name], self.lookup)
            except ExprError as e:
                if str(e).startswith("var "):
                    raise
                raise ExprError(f"var {name}: {e}") from None
            finally:
                self._stack.pop()
            self._memo[name] = v
            return v
        if name in CONSTS:
            return CONSTS[name]
        if name in BUILTIN_NAMES:
            raise ExprError(f"{name!r} is not available here (w/h exist inside layers and slices, "
                            f"w_px/h_px only inside slice_px)")
        raise ExprError(f"unknown name {name!r}")

    def eval(self, value, what: str = ""):
        """Evaluates [value]; errors name [what] (a field path) and the scope's piece."""
        try:
            return evaluate(value, self.lookup)
        except ExprError as e:
            prefix = " ".join(p for p in (self.where, what) if p)
            raise ExprError(f"{prefix}: {e}" if prefix else str(e)) from None

    def child(self, **builtins) -> "Scope":
        """A scope sharing vars and memo, with extra built-ins (memo stays valid: see class doc)."""
        s = Scope.__new__(Scope)
        s.vars = self.vars
        s.builtins = {**self.builtins, **builtins}
        s.where = self.where
        s._memo = self._memo
        s._stack = self._stack
        return s
