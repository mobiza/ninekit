"""Spec loading (DESIGN 2): YAML, includes, theme merging, validation and variant expansion."""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

from ninekit import NinekitError
from ninekit.expr import RESERVED

SPEC_KEYS = {"ninekit", "name", "description", "scales", "grid", "out", "file", "include", "vars", "colors", "params",
             "pieces"}
THEME_KEYS = {"ninekit", "name", "description", "include", "vars", "colors", "params"}
PIECE_KEYS = {"size", "slice", "slice_px", "stretch", "content", "overhang", "layers", "variants", "vars", "colors",
              "outputs", "mode", "block", "params", "compact", "keep", "description", "mask", "period"}
LAYER_KEYS = {"shape", "fill", "grow", "ring", "clip", "soft", "falloff", "opacity", "offset", "blend", "output",
              "when", "name", "roughen"}
FILE_TOKENS = {"piece", "output", "scale"}
DEFAULT_FILE = "{piece}{output}{scale}.png"
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PIECE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
MAX_GRID = 4        # dp: scales whose common grid is coarser than this are refused (no usable dp grid)


class SpecError(NinekitError):
    pass


def as_fraction(v) -> Fraction:
    """A scale or grid value as an exact fraction (1.5 -> 3/2; "1/3" -> 1/3)."""
    if isinstance(v, str):
        return Fraction(v.strip())
    return Fraction(v).limit_denominator(1000)


def dp_grid(scales) -> Fraction:
    """The smallest dp step g with g x s a whole number of texels at every scale s (DESIGN 2.4).

    [1, 2, 3] -> 1, [3] -> 1/3, [2, 4] -> 1/2, [1.5, 3] -> 2/3. With s = p / q (reduced), g x s is whole for
    every s exactly when g is a multiple of lcm(q) / gcd(p).
    """
    fr = [as_fraction(s) for s in scales]
    num = 0
    den = 1
    for f in fr:
        num = math.gcd(num, f.numerator)
        den = den * f.denominator // math.gcd(den, f.denominator)
    return Fraction(den, num)


def _fmt_fraction(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def deep_merge(base: Any, over: Any) -> Any:
    """[over] merged onto [base]: dicts recursively (base key order kept, new keys appended), else replaced."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def load_yaml(path: Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError(f"cannot read {path}: {e.strerror}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SpecError(f"{path}: invalid YAML: {e}") from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SpecError(f"{path}: the top level must be a mapping")
    return data


def _load_with_includes(path: Path, stack: tuple[Path, ...] = ()) -> dict:
    path = Path(path).resolve()
    if path in stack:
        chain = " -> ".join(p.name for p in stack + (path,))
        raise SpecError(f"include cycle: {chain}")
    data = load_yaml(path)
    inc = data.get("include", [])
    if isinstance(inc, str):
        inc = [inc]
    if not isinstance(inc, list):
        raise SpecError(f"{path}: include must be a file or a list of files")
    merged: dict = {}
    for item in inc:
        merged = deep_merge(merged, _load_with_includes(path.parent / str(item), stack + (path,)))
    data = {k: v for k, v in data.items() if k != "include"}
    return deep_merge(merged, data)


@dataclass
class PieceDef:
    """One piece to render (a base piece or an expanded variant)."""
    name: str
    data: dict            # the piece fields (variant overrides merged, no `variants`)
    vars: dict            # flat scope: spec vars < piece vars (< variant vars)
    colors: dict          # spec colors < piece colors (< variant colors)
    params: dict          # block params (top-level params merged in)


@dataclass
class Spec:
    path: Path
    data: dict
    name: str
    scales: list
    out: Path
    file: str
    vars: dict
    colors: dict
    params: dict
    pieces: dict = field(default_factory=dict)
    grid_override: Fraction | None = None

    @property
    def base(self) -> Path:
        return self.path.parent

    @property
    def grid(self) -> Fraction:
        """The dp grid of the spec's own scales (or its `grid:`)."""
        return self.grid_for(self.scales)

    def grid_for(self, scales) -> Fraction:
        """The dp grid for rendering [scales] (the spec's scales plus any extra ones): sizes, auto slices,
        `keep` and noise/image periods snap to it, so every file is its dp value x its scale exactly."""
        g = dp_grid(list(self.scales) + [s for s in scales if s not in self.scales])
        if self.grid_override is not None:
            if (self.grid_override / g).denominator != 1:
                raise SpecError(f"{self.path.name}: grid {_fmt_fraction(self.grid_override)} dp is not a whole "
                                f"multiple of {_fmt_fraction(g)} dp, the smallest step that is whole texels at scales "
                                f"{', '.join(str(s) for s in scales)}")
            return self.grid_override
        if g > MAX_GRID:
            raise SpecError(f"{self.path.name}: scales {', '.join(str(s) for s in scales)} share no dp grid finer than "
                            f"{_fmt_fraction(g)} dp (the smallest step that is whole texels at every scale); use scales "
                            f"such as 1, 1.5, 2, 3, 4")
        return g

    def piece_defs(self, only: list[str] | None = None) -> list[PieceDef]:
        defs = expand_pieces(self)
        if only:
            known = {d.name for d in defs}
            missing = [n for n in only if n not in known]
            if missing:
                raise SpecError(f"--only: unknown piece(s) {', '.join(missing)} (known: {', '.join(sorted(known))})")
            defs = [d for d in defs if d.name in only]
        return defs


def _check_keys(where: str, data: dict, allowed: set) -> None:
    extra = [k for k in data if k not in allowed]
    if extra:
        raise SpecError(f"{where}: unknown key(s) {', '.join(map(str, extra))} (allowed: {', '.join(sorted(allowed))})")


def _check_vars(where: str, vars: Any) -> None:
    if not isinstance(vars, dict):
        raise SpecError(f"{where}: vars must be a mapping")
    for k, v in vars.items():
        if not isinstance(k, str) or not _NAME_RE.match(k):
            raise SpecError(f"{where}: var name {k!r} is not a valid name")
        if k in RESERVED:
            raise SpecError(f"{where}: var name {k!r} is reserved (built-in name or function)")
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            raise SpecError(f"{where}: var {k} must be a number or an expression, got {v!r}")


def _check_colors(where: str, colors: Any) -> None:
    if not isinstance(colors, dict):
        raise SpecError(f"{where}: colors must be a mapping")
    for k, v in colors.items():
        if not isinstance(k, str) or not _NAME_RE.match(k):
            raise SpecError(f"{where}: colour name {k!r} is not a valid name")
        if not isinstance(v, (str, int, float, list)) or isinstance(v, bool):
            raise SpecError(f"{where}: colour {k} must be a colour, a shade or a list of stops, got {v!r}")


def _check_file_template(tpl: str) -> None:
    for tok in re.findall(r"{([^{}]*)}", tpl):
        if tok not in FILE_TOKENS:
            raise SpecError(f"file template {tpl!r}: unknown token {{{tok}}} (allowed: {{piece}} {{output}} {{scale}})")
    if "{piece}" not in tpl:
        raise SpecError(f"file template {tpl!r} must contain {{piece}}")
    if not tpl.endswith(".png"):
        raise SpecError(f"file template {tpl!r} must end in .png")


def load_spec(path: str | Path, theme: str | Path | None = None) -> Spec:
    path = Path(path).resolve()
    data = _load_with_includes(path)
    if theme is not None:
        tpath = Path(theme).resolve()
        tdata = _load_with_includes(tpath)
        _check_keys(f"theme {tpath.name}", tdata, THEME_KEYS)
        data = deep_merge(data, {k: v for k, v in tdata.items() if k in ("vars", "colors", "params")})
    return parse_spec(data, path)


def parse_spec(data: dict, path: Path) -> Spec:
    where = path.name
    _check_keys(where, data, SPEC_KEYS)
    if data.get("ninekit") != 1:
        raise SpecError(f"{where}: missing or unsupported `ninekit: 1` header")
    name = data.get("name") or path.stem
    if not isinstance(name, str) or not _PIECE_RE.match(name):
        raise SpecError(f"{where}: name {name!r} must be a simple identifier")
    scales = data.get("scales", [1])
    if isinstance(scales, (int, float)):
        scales = [scales]
    if not isinstance(scales, list) or not scales:
        raise SpecError(f"{where}: scales must be a non-empty list of numbers")
    for s in scales:
        if isinstance(s, bool) or not isinstance(s, (int, float)) or s <= 0:
            raise SpecError(f"{where}: scale {s!r} must be a positive number")
    if len(set(scales)) != len(scales):
        raise SpecError(f"{where}: duplicate scales {scales}")
    scales = [int(s) if float(s).is_integer() else float(s) for s in scales]
    grid = data.get("grid")
    if grid is not None:
        try:
            if isinstance(grid, bool) or not isinstance(grid, (int, float, str)):
                raise ValueError
            grid = as_fraction(grid)
        except (ValueError, ZeroDivisionError):
            raise SpecError(f"{where}: grid must be a dp step such as 1, 0.5 or \"1/3\", got {data.get('grid')!r}") from None
        if grid <= 0:
            raise SpecError(f"{where}: grid must be > 0")
    file_tpl = data.get("file", DEFAULT_FILE)
    if not isinstance(file_tpl, str):
        raise SpecError(f"{where}: file must be a string template")
    _check_file_template(file_tpl)
    vars_ = data.get("vars") or {}
    _check_vars(where, vars_)
    colors = data.get("colors") or {}
    _check_colors(where, colors)
    params = data.get("params") or {}
    if not isinstance(params, dict) or not all(isinstance(v, dict) for v in params.values()):
        raise SpecError(f"{where}: params must map piece names (or \"*\") to mappings")
    pieces = data.get("pieces") or {}
    if not isinstance(pieces, dict) or not pieces:
        raise SpecError(f"{where}: pieces must be a non-empty mapping")
    for pname, p in pieces.items():
        _check_piece(f"{where}: piece {pname}", pname, p)
    out = data.get("out", "out/")
    spec = Spec(path=path, data=data, name=name, scales=scales, out=(path.parent / str(out)).resolve(),
                file=file_tpl, vars=vars_, colors=colors, params=params, pieces=pieces, grid_override=grid)
    spec.grid        # validates the grid (or the scales) early
    return spec


def _check_piece(where: str, name: Any, p: Any, variant: bool = False) -> None:
    if not isinstance(name, str) or not _PIECE_RE.match(name):
        raise SpecError(f"{where}: piece name {name!r} must use letters, digits, _ . -")
    if not isinstance(p, dict):
        raise SpecError(f"{where}: must be a mapping")
    _check_keys(where, p, PIECE_KEYS - ({"variants"} if variant else set()))
    if "vars" in p:
        _check_vars(where, p["vars"])
    if "colors" in p:
        _check_colors(where, p["colors"])
    if variant:
        return
    has_layers, has_block = "layers" in p, "block" in p
    if has_layers == has_block:
        raise SpecError(f"{where}: give either `layers` or `block` (exactly one)")
    if has_layers:
        if "params" in p:
            raise SpecError(f"{where}: `params` is for block pieces (`block: <name>`); a layered piece uses vars")
        if not isinstance(p["layers"], list) or not p["layers"]:
            raise SpecError(f"{where}: layers must be a non-empty list")
        if "size" not in p:
            raise SpecError(f"{where}: `size: [w, h]` is required for layer pieces")
        for i, layer in enumerate(p["layers"]):
            if not isinstance(layer, dict):
                raise SpecError(f"{where}: layer {i} must be a mapping")
            _check_keys(f"{where} layer {i}", layer, LAYER_KEYS)
            for req in ("shape", "fill"):
                if req not in layer:
                    raise SpecError(f"{where} layer {i}: `{req}` is required")
    n_slice = sum(k in p for k in ("slice", "slice_px"))
    if n_slice > 1:
        raise SpecError(f"{where}: give `slice` or `slice_px`, not both")
    variants = p.get("variants") or {}
    if not isinstance(variants, dict):
        raise SpecError(f"{where}: variants must be a mapping of name -> overrides")
    for vname, v in variants.items():
        _check_piece(f"{where} variant {vname}", vname, v or {}, variant=True)


def _piece_params(spec: Spec, name: str, data: dict) -> dict:
    params = dict(data.get("params") or {})
    for key in ("*", name):
        if key in spec.params:
            params = deep_merge(params, spec.params[key])
    return params


def expand_pieces(spec: Spec) -> list[PieceDef]:
    """Base pieces and their variants, in spec order (each variant right after its base)."""
    out: list[PieceDef] = []
    seen: set[str] = set()

    def add(name: str, data: dict) -> None:
        if name in seen:
            raise SpecError(f"{spec.path.name}: piece name {name!r} is used twice (a piece and a variant?)")
        seen.add(name)
        vars_ = {**spec.vars, **(data.get("vars") or {})}
        colors = {**spec.colors, **(data.get("colors") or {})}
        out.append(PieceDef(name=name, data=data, vars=vars_, colors=colors, params=_piece_params(spec, name, data)))

    for name, p in spec.pieces.items():
        base = {k: v for k, v in p.items() if k != "variants"}
        add(name, base)
        for vname, over in (p.get("variants") or {}).items():
            merged = deep_merge(base, over or {})
            if "layers" in merged and "params" in merged:
                raise SpecError(f"{spec.path.name}: piece {name} variant {vname}: `params` is for block pieces "
                                f"(`block: <name>`); a layered piece uses vars")
            # a variant's layers/size replace the base's wholesale (deep_merge does that for lists)
            add(vname, merged)
    return out
