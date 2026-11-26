"""The `css` export target (DESIGN 7): the PNGs, `ninekit.css` and an `index.html` gallery of every class.

Layout model (one piece = one block or inline-block element):

* The element's own box is the piece's *logical* rect: the sprite canvas minus `overhang` (the art that reaches
  outside, e.g. a drop shadow); `box-sizing: border-box`, so `width` / `height` are the logical size. `content`
  insets are measured from the canvas edges (like the slices), so `padding` = max(0, content - overhang) per side.
* The sprite is drawn behind the content on pseudo-elements: the stack's first output on `::before`, the second on
  `::after` (z-index -n .. -1 inside the element's own stacking context, `isolation: isolate`), each positioned with
  `inset` = -overhang. A piece with more than two stacked outputs needs one child per extra output:
  `<span class="nk-<piece>__<output>"></span>` (every output also has this class; it positions like the pseudos).
* A `fixed` axis (DESIGN 2.4 / 7): the layers keep the sprite's natural length on it, centred on the logical box
  whatever length the box gets (`top: calc(50% - ...)`, `height`); the content still lays out in the box, and the
  box gets no min size on that axis.
* 9-slice pieces use `border-image` with `fill`, border widths = the slices in dp (CSS px); pieces drawn whole
  (`slice: null`) use `background-image` sized to the sprite rect. The class also resets `appearance`, `border` and
  `background` (a native `<button>` look would cover the sprite).

Units (measured in Chrome 158 at device pixel ratio 1, 2 and 3; see demos/web/check.py):
* with `image-set()`, the chosen candidate's natural size is its pixel size / its resolution, and
  `border-image-slice` numbers are in those CSS px, not in the file's pixels (slice 10 cuts 20 px of the 2x file);
* Chrome rounds `border-image-slice` to whole units of that natural size (10.3333 -> 10, 10.5 and 10.6667 -> 11 CSS
  px for a 3x candidate; whole file px for a plain `url()`).
So one `image-set()` with one `border-image-slice` (= the piece's dp `slice`, `border-image-width` the same in px)
is exact when every file's `slice_px` equals `slice` x its scale and `slice` is whole CSS px. Otherwise (fractional
dp slices, e.g. 25.33 / 30.67 dp at scale 3, or files whose slices disagree with the dp value) the piece
gets one plain `url()` per scale, chosen by `resolution` media queries (the same pick as image-set: the smallest
scale >= the device pixel ratio, else the largest), with that file's own `slice_px` (whole image px) and
`border-image-width` = `slice_px / scale`.

`border-image-repeat`: `stretch` -> `stretch`; `tile` -> `round`: whole tiles only (the tile region holds whole
periods, so whole repeats meet each other and the end slices seamlessly; `repeat` would centre the tiles and cut
both ends at an arbitrary phase).

Frame/face pieces (a stacked output named `face`): `:active` (or the class `nk-pressed`) scales the face and the
content together by `--nk-press` (default 0.92) toward the centre of the logical box (the body): the element gets
`transform: scale(...)` plus `will-change: transform`, and the other layers (the frame) are counter-scaled by
geometry (`--nk-u` = 1 / press in their `inset` and `border-image-width`), so they stay put. `will-change` matters:
without a composited layer Chrome paints a scaled border-image piece by piece and hairline seams show between the
nine pieces; with it the layer is scaled as a whole (measured at DPR 2 and 3).

Shade-mode pieces: the layers carry `filter: var(--nk-ramp, none)`. Point `--nk-ramp` at an SVG `<filter>` whose
`feComponentTransfer` maps R, G and B through the ramp's channels (R = G = B = shade, so this is an exact gradient
map); `ramp_filter_svg()` writes one, and index.html shows two. Without a ramp the greys show.
"""
from __future__ import annotations

import html
import json as _json
import shutil
from pathlib import Path
from urllib.parse import quote

from ninekit import NinekitError, __version__
from ninekit.manifest import load_manifest, scale_key

PRESS = 0.92
PREFIX = "nk-"
# example ramps for shade pieces in the gallery (stops: [t, "#rrggbb"], t = the shade 0..1)
EXAMPLE_RAMPS = {
    "gold": [[0, "#4A2306"], [0.45, "#C8761E"], [1, "#FFF1B8"]],
    "mint": [[0, "#0B3B33"], [0.5, "#21A88C"], [1, "#E6FFF6"]],
}


# ----------------------------------------------------------------------------------------------- helpers

def _num(v: float) -> str:
    """A CSS number: integers without a point, else up to 4 decimals."""
    v = float(v)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _px(v: float) -> str:
    s = _num(v)
    return "0" if s in ("0", "-0") else s + "px"


def css_ident(name: str) -> str:
    """[name] escaped for a CSS class selector (piece names use letters, digits, `_ . -`)."""
    out = []
    for ch in name:
        if ch.isalnum() and ch.isascii() or ch in "_-":
            out.append(ch)
        else:
            out.append("\\" + ch)
    return "".join(out)


def class_name(piece: str, output: str | None = None) -> str:
    """The HTML class of a piece (`nk-<piece>`) or of one of its outputs (`nk-<piece>__<output>`)."""
    return PREFIX + piece + ("" if output is None else "__" + output)


def _url(file: str) -> str:
    return 'url("' + quote(file, safe="/@._-~") + '")'


def _tlbr(v4) -> list:
    """[l, t, r, b] -> [t, r, b, l] (CSS order)."""
    l, t, r, b = v4
    return [t, r, b, l]


def stacked_layers(piece: dict) -> tuple[list, str | None]:
    """(outputs drawn stacked bottom->top, the composite output or None). `main` next to named outputs is their
    composite (DESIGN 3): an alternative to stacking them, so it is not stacked."""
    stack = list(piece.get("stack") or sorted(piece["outputs"]))
    if len(stack) > 1 and "main" in stack:
        return [o for o in stack if o != "main"], "main"
    return stack, None


def piece_scales(piece: dict, want: str | None) -> list[str]:
    """The scale keys every output of [piece] has (restricted to [want]), ascending."""
    keys = None
    for per in piece["outputs"].values():
        ks = set(per)
        keys = ks if keys is None else keys & ks
    keys = sorted(keys or [], key=float)
    if want is not None:
        keys = [k for k in keys if k == want]
    return keys


def slice_mismatches(piece: dict, scales: list[str]) -> list[tuple]:
    """(output, scale, slice_px, dp slice x scale) for every file whose `slice_px` is not the piece's dp `slice` x
    its scale (rounded; the manifest keeps dp to 2 decimals)."""
    dp = piece.get("slice")
    out = []
    if dp is None:
        return out
    for o, per in piece["outputs"].items():
        for k in scales:
            sp = per[k].get("slice_px")
            want = [v * float(k) for v in dp]
            if sp is None or any(abs(a - b) > 0.05 for a, b in zip(sp, want)):
                out.append((o, k, sp, [round(v, 2) for v in want]))
    return out


def shared_slice(piece: dict, scales: list[str]) -> list | None:
    """The piece's dp `slice` when one `image-set()` + `border-image-slice` is exact for every file at [scales]:
    each file's `slice_px` = slice x scale, and the slice is whole CSS px (Chrome rounds to whole px); else None."""
    dp = piece.get("slice")
    if dp is None or slice_mismatches(piece, scales):
        return None
    if any(abs(v - round(v)) > 1e-6 for v in dp):
        return None
    return [float(round(v)) for v in dp]


def _media(lower: str) -> str:
    """The media query that selects scales above [lower] (the same pick as image-set: the smallest scale at or
    above the device pixel ratio, else the largest)."""
    r = _num(float(lower) + 0.001)
    return f"@media (-webkit-min-device-pixel-ratio: {r}), (min-resolution: {r}dppx)"


def _ramp_at(stops, t: float) -> tuple:
    pts = sorted(((float(a), _rgb(c)) for a, c in stops), key=lambda p: p[0])
    if t <= pts[0][0]:
        return pts[0][1]
    for (a0, c0), (a1, c1) in zip(pts, pts[1:]):
        if t <= a1:
            u = 0.0 if a1 == a0 else (t - a0) / (a1 - a0)
            return tuple(x0 + (x1 - x0) * u for x0, x1 in zip(c0, c1))
    return pts[-1][1]


def _rgb(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def ramp_filter_svg(fid: str, stops) -> str:
    """An SVG `<filter>` mapping a shade piece's greys through [stops] ([[t, "#rrggbb"], ...], t = shade 0..1):
    feComponentTransfer tables, linear between equally spaced entries - exact when every stop sits on that grid
    (the smallest grid of <= 256 entries that holds them), else sampled at 256 entries."""
    ts = [float(t) for t, _ in stops]
    n = 256
    for k in range(1, 256):
        if all(abs(t * k - round(t * k)) < 1e-9 for t in ts):
            n = k + 1
            break
    samples = [_ramp_at(stops, i / (n - 1)) for i in range(n)]
    funcs = "".join(
        f'<feFunc{ch} type="table" tableValues="{" ".join(_num(round(s[j], 4)) for s in samples)}"/>'
        for j, ch in enumerate("RGB"))
    return (f'<filter id="{html.escape(fid)}" color-interpolation-filters="sRGB">'
            f'<feComponentTransfer>{funcs}</feComponentTransfer></filter>')


# ----------------------------------------------------------------------------------------------- per piece

class _Piece:
    """What the CSS of one piece needs, worked out once (also used by the gallery and the tests)."""

    def __init__(self, name: str, piece: dict, want: str | None):
        self.name = name
        self.piece = piece
        self.sel = "." + css_ident(class_name(name))
        self.layers, self.composite = stacked_layers(piece)
        self.scales = piece_scales(piece, want)
        if not self.scales:
            raise NinekitError(f"piece {name}: no files at scale {want}")
        self.whole = piece.get("slice") is None
        self.oh = [float(v) for v in (piece.get("overhang") or [0, 0, 0, 0])]
        self.content = piece.get("content")
        self.shade = piece.get("mode") == "shade"
        self.stretch = list(piece.get("stretch") or ["stretch", "stretch"])
        self.fixed = [m == "fixed" and not self.whole for m in self.stretch]
        self.cut = None if self.whole else shared_slice(piece, self.scales)
        self.mismatches = slice_mismatches(piece, self.scales)
        self.press = "face" in self.layers and len(self.layers) > 1
        top = self.scales[-1]
        w_px, h_px = piece["outputs"][self.layers[0]][top]["size_px"]
        s = float(top)
        self.sprite = (w_px / s, h_px / s)
        self.logical = (max(0.0, self.sprite[0] - self.oh[0] - self.oh[2]),
                        max(0.0, self.sprite[1] - self.oh[1] - self.oh[3]))

    def padding(self) -> list:
        """[l, t, r, b] padding: content insets (from the canvas edges) minus the overhang, at least 0."""
        if self.content is None:
            return [0.0] * 4
        return [max(0.0, float(c) - o) for c, o in zip(self.content, self.oh)]

    def slices_dp(self) -> list:
        """Per side the largest slice in dp over the scales (the widths the corners need)."""
        if self.cut is not None:
            return self.cut
        out = [0.0] * 4
        for o in self.layers:
            for k in self.scales:
                sp = self.piece["outputs"][o][k]["slice_px"]
                out = [max(a, v / float(k)) for a, v in zip(out, sp)]
        return [round(v, 4) for v in out]

    def min_size(self) -> tuple:
        """The smallest logical box at which the corners draw unshrunk (9-slice pieces)."""
        sl = self.slices_dp()
        return (max(0.0, sl[0] + sl[2] - self.oh[0] - self.oh[2]), max(0.0, sl[1] + sl[3] - self.oh[1] - self.oh[3]))

    def targets(self, output: str) -> list[str]:
        """Selectors drawing [output]: its pseudo-element (first two stacked outputs) and its own class."""
        sels = []
        if output in self.layers:
            i = self.layers.index(output)
            if i < 2:
                sels.append(self.sel + ("::before" if i == 0 else "::after"))
        sels.append("." + css_ident(class_name(self.name, output)))
        return sels

    def all_outputs(self) -> list[str]:
        return self.layers + ([self.composite] if self.composite else [])

    def _state(self, targets: list[str]) -> list[str]:
        """[targets] (pseudo-elements or output classes of this piece) in the pressed states."""
        out = []
        for state in (":active:not(:disabled)", ".nk-pressed"):
            for t in targets:
                out.append(self.sel + state + (t[len(self.sel):] if t.startswith(self.sel + "::") else " > " + t))
        return out

    # --- css
    def css(self) -> str:
        p, oh = self.piece, self.oh
        j = lambda v: _json.dumps(v, separators=(",", ":"))
        how = ("drawn whole" if self.whole else "image-set, dp slice" if self.cut is not None
               else "one url() per scale (media queries)")
        lines = [f"/* {self.name}: sprite {_num(self.sprite[0])} x {_num(self.sprite[1])} dp, "
                 f"logical box {_num(self.logical[0])} x {_num(self.logical[1])} dp; "
                 f"slice {j(p.get('slice'))}; stretch {j(self.stretch)}; content {j(self.content)}; "
                 f"overhang {j(p.get('overhang'))}; mode {p.get('mode', 'color')}; stack {j(self.layers)}"
                 + (f" (+ composite {self.composite})" if self.composite else "") + f"; {how} */"]
        box = ["position: relative", "isolation: isolate", "box-sizing: border-box",
               "-webkit-appearance: none", "appearance: none", "border: 0", "background: none",
               "padding: " + _box4(_tlbr(self.padding()))]
        if self.whole:
            box += [f"width: {_px(self.logical[0])}", f"height: {_px(self.logical[1])}"]
        else:
            mw, mh = self.min_size()
            if not self.fixed[0]:
                box.append(f"min-width: {_px(mw)}")
            if not self.fixed[1]:
                box.append(f"min-height: {_px(mh)}")
        lines.append(_rule([self.sel], box))
        media: dict[str, list[str]] = {}
        n = len(self.layers)
        for o in self.all_outputs():
            sels = self.targets(o)
            z = (self.layers.index(o) - n) if o in self.layers else -1
            u = self.press and o in self.layers and o != "face"     # counter-scaled while the element is pressed
            decl = ['content: ""', "position: absolute"] + self._place(u) + [
                    "box-sizing: border-box", "pointer-events: none", f"z-index: {z}"]
            per = p["outputs"][o]
            if self.whole:
                decl += ["background-position: center", "background-size: 100% 100%",
                         "background-repeat: no-repeat",
                         "background-image: " + _image_set(per, self.scales, webkit=True),
                         "background-image: " + _image_set(per, self.scales)]
            elif self.cut is not None:
                decl += ["border-image-source: " + _image_set(per, self.scales, webkit=True),
                         "border-image-source: " + _image_set(per, self.scales),
                         "border-image-slice: " + " ".join(_num(v) for v in _tlbr(self.cut)) + " fill",
                         "border-image-width: " + _widths(_tlbr(self.cut), u),
                         "border-image-repeat: " + self._repeat()]
            else:
                decl += self._url_decl(per, self.scales[0], u) + ["border-image-repeat: " + self._repeat()]
                for lower, sk in zip(self.scales, self.scales[1:]):
                    media.setdefault(lower, []).append(_rule(sels, self._url_decl(per, sk, u), indent="  "))
            if self.shade:
                decl.append("filter: var(--nk-ramp, none)")
            lines.append(_rule(sels, decl))
        for lower in self.scales[:-1]:
            if lower in media:
                lines.append(_media(lower) + " {\n" + "\n".join(media[lower]) + "\n}")
        if self.press:
            lines.append(_rule([self.sel + ":active:not(:disabled)", self.sel + ".nk-pressed"], [
                f"transform: scale(var(--nk-press, {_num(PRESS)}))", "transform-origin: 50% 50%",
                "will-change: transform"]))
            others = [t for o in self.layers if o != "face" for t in self.targets(o)]
            if others:
                lines.append(_rule(self._state(others), [f"--nk-u: calc(1 / var(--nk-press, {_num(PRESS)}))"]))
        return "\n".join(lines) + "\n"

    def _place(self, counter: bool) -> list[str]:
        """Where a layer sits: the logical box plus the overhang (`inset` = -overhang); on a `fixed` axis the
        sprite keeps its natural length, centred on the logical box whatever length the box gets (DESIGN 7).
        [counter]: that rect scaled by --nk-u about the box centre (a frame that stays put while its element is
        scaled by 1 / u)."""
        oh = self.oh
        if not any(self.fixed):
            return ["inset: " + _inset(_tlbr(oh), counter)]
        t, r, b, l = (_side(v, counter) for v in _tlbr(oh))
        extra = []
        for axis in (0, 1):
            if not self.fixed[axis]:
                continue
            size = self.sprite[axis]
            o0, o1 = (oh[0], oh[2]) if axis == 0 else (oh[1], oh[3])
            off = (size + o0 - o1) / 2.0           # box centre -> sprite start
            start = f"calc(50% - {U} * {_px(off)})" if counter else f"calc(50% - {_px(off)})"
            length = f"calc({U} * {_px(size)})" if counter else _px(size)
            if axis == 0:
                l, r = start, "auto"
                extra.append(f"width: {length}")
            else:
                t, b = start, "auto"
                extra.append(f"height: {length}")
        return [f"inset: {t} {r} {b} {l}"] + extra

    def _repeat(self) -> str:
        return " ".join("round" if m == "tile" else "stretch" for m in self.stretch)

    def _url_decl(self, per: dict, sk: str, u: bool = False) -> list[str]:
        f = per[sk]
        s = float(sk)
        sp = f["slice_px"]
        return ["border-image-source: " + _url(f["file"]),
                "border-image-slice: " + " ".join(_num(v) for v in _tlbr(sp)) + " fill",
                "border-image-width: " + _widths([_Frac(v, s) for v in _tlbr(sp)], u)]


def _box4(v4) -> str:
    """A CSS 1-4 value shorthand of [t, r, b, l] lengths."""
    t, r, b, l = (_px(v) for v in v4)
    if t == r == b == l:
        return t
    if t == b and r == l:
        return f"{t} {r}"
    if r == l:
        return f"{t} {r} {b}"
    return f"{t} {r} {b} {l}"


U = "var(--nk-u, 1)"


def _side(oh: float, counter: bool) -> str:
    """One `inset` side of a layer: -overhang; [counter]: scaled by --nk-u about the box centre
    (side = (1 - u) * 50% - u * overhang), so a frame stays put while its element is scaled by 1 / u."""
    if not counter:
        return _px(-oh)
    return f"calc((1 - {U}) * 50%" + (f" - {U} * {_px(oh)})" if oh else ")")


def _inset(oh_trbl, counter: bool) -> str:
    if not counter:
        return _box4([-v for v in oh_trbl])
    return " ".join(_side(v, True) for v in oh_trbl)


class _Frac:
    """A length of [px] texels at [scale] in CSS px, written exactly: `14.5px`, or `calc(55px / 3)` when the
    decimal would not terminate (Chrome truncates layout lengths: 18.3333px is 54.9999 device px at a ratio of 3,
    which squeezes a 55-texel corner into 54 device px)."""

    def __init__(self, px: float, scale: float):
        self.px, self.scale = float(px), float(scale)

    def __bool__(self):
        return self.px != 0

    def css(self) -> str:
        v = self.px / self.scale
        if abs(round(v, 4) * self.scale - self.px) < 1e-9:
            return _px(v)
        return f"calc({_px(self.px)} / {_num(self.scale)})"


def _len(v) -> str:
    return v.css() if isinstance(v, _Frac) else _px(v)


def _widths(trbl, counter: bool) -> str:
    """`border-image-width` in px; [counter]: each times --nk-u."""
    if not counter:
        return " ".join(_len(v) for v in trbl)
    out = []
    for v in trbl:
        if not v:
            out.append("0")
        else:
            inner = _len(v)
            inner = inner[5:-1] if inner.startswith("calc(") else inner
            out.append(f"calc({U} * {inner})")
    return " ".join(out)


def _image_set(per: dict, scales: list[str], webkit: bool = False) -> str:
    fn = "-webkit-image-set" if webkit else "image-set"
    return fn + "(" + ", ".join(f"{_url(per[k]['file'])} {_num(float(k))}x" for k in scales) + ")"


def _rule(selectors: list[str], decls: list[str], indent: str = "") -> str:
    sel = (",\n" + indent).join(selectors)
    body = "".join(f"{indent}  {d};\n" for d in decls)
    return f"{indent}{sel} {{\n{body}{indent}}}"


# ----------------------------------------------------------------------------------------------- export

def _header(manifest: dict, scales: list[str]) -> str:
    return f"""/* ninekit.css - generated by ninekit {__version__} from manifest "{manifest.get('name')}" (scales {', '.join(scales)}).
 * Do not edit: re-export with `ninekit export ninekit.json --target css -o DIR`.
 *
 * One piece = one block / inline-block element: <div class="nk-panel">text</div>. Its box is the piece's logical
 * rect (the sprite minus its overhang); padding = content insets (measured from the canvas) minus the overhang; set
 * width / height as you like (min sizes keep the corners 1:1). The sprite is drawn on ::before / ::after behind the
 * content (inset = -overhang). More than two stacked outputs: add <span class="nk-PIECE__OUTPUT"></span> children
 * for the third and later ones. A composite `main` next to named outputs:
 * <div class="nk-PIECE nk-bare"><span class="nk-PIECE__main"></span></div>.
 * Units: dp = CSS px. With image-set(), border-image-slice numbers are CSS px of the chosen candidate (its pixels
 * / its resolution) and Chrome rounds them to whole CSS px (measured at DPR 1, 2, 3): pieces whose dp slices are
 * whole and match every file use image-set(); the others use one url() per scale under resolution media queries,
 * with that file's exact slice_px.
 * Pressed (pieces with a `face`): :active or .nk-pressed scales the element - face and content - by
 * var(--nk-press, 0.92) about the box centre (will-change: transform keeps the nine pieces seamless); the frame
 * is counter-scaled (--nk-u) and stays put.
 * Shade pieces: set --nk-ramp: url(#your-filter) (an SVG feComponentTransfer gradient map; see index.html).
 */
"""


def export(manifest_path, out_dir, scale=None, runtime=False) -> list[Path]:
    """PNGs + `ninekit.css` + `index.html` in [out_dir] (`runtime` is ignored: plain CSS needs none)."""
    mpath = Path(manifest_path)
    if mpath.is_dir():
        mpath = mpath / "ninekit.json"
    manifest = load_manifest(mpath)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    want = None if scale is None else scale_key(scale)
    if want is not None and float(want) not in {float(s) for s in manifest.get("scales", [])}:
        raise NinekitError(f"--scale {want}: the manifest has scales {manifest.get('scales')}")
    pieces = [_Piece(name, p, want) for name, p in manifest["pieces"].items()]
    written: list[Path] = []
    copied = set()
    for pc in pieces:
        for o in pc.all_outputs():
            for k in pc.scales:
                f = pc.piece["outputs"][o][k]["file"]
                if f in copied:
                    continue
                copied.add(f)
                src, dst = mpath.parent / f, out / f
                if not src.is_file():
                    raise NinekitError(f"{src}: missing (listed in {mpath.name})")
                if src.resolve() != dst.resolve():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
                    written.append(dst)
    scales = sorted({k for pc in pieces for k in pc.scales}, key=float)
    css = _header(manifest, scales) + "\n" + "\n".join(pc.css() for pc in pieces)
    css += "\n/* a composite `main` shown alone: hide the stacked pseudo-elements */\n"
    css += _rule([".nk-bare.nk-bare::before", ".nk-bare.nk-bare::after"], ["content: none"]) + "\n"
    path = out / "ninekit.css"
    path.write_text(css, encoding="utf-8")
    written.append(path)
    gallery = out / "index.html"
    gallery.write_text(_gallery(manifest, pieces), encoding="utf-8")
    written.append(gallery)
    return written


# ----------------------------------------------------------------------------------------------- gallery

def _gallery_sizes(pc: _Piece) -> list[tuple]:
    if pc.whole:
        return [pc.logical]
    mw, mh = pc.min_size()
    w0, h0 = max(pc.logical[0], mw), max(pc.logical[1], mh)
    return [(w0, h0), (round(w0 * 1.6), h0), (round(w0 * 3), round(h0 * 1.5))]


def _gallery(manifest: dict, pieces: list[_Piece]) -> str:
    esc = html.escape
    ramps = "".join(ramp_filter_svg(f"nk-ramp-{k}", v) for k, v in EXAMPLE_RAMPS.items())
    cards = []
    for pc in pieces:
        p = pc.piece
        files = ", ".join(p["outputs"][o][k]["file"] for o in pc.all_outputs() for k in pc.scales)
        demos = []
        variants = [("", "")]
        if pc.shade:
            variants += [(f"--nk-ramp: url(#nk-ramp-{k});", f"ramp {k}") for k in EXAMPLE_RAMPS]
        for style_extra, tag in variants:
            for (w, h) in _gallery_sizes(pc):
                inner = '<div class="g-content"></div>'
                demos.append(f'<figure><div class="{esc(class_name(pc.name))}" style="width:{_px(w)};height:{_px(h)};'
                             f'{style_extra}">{inner}</div><figcaption>{_num(w)} x {_num(h)}'
                             f'{(" " + tag) if tag else ""}</figcaption></figure>')
        if pc.press:
            w, h = _gallery_sizes(pc)[0]
            demos.append(f'<figure><div class="{esc(class_name(pc.name))} nk-pressed" '
                         f'style="width:{_px(w)};height:{_px(h)}"><div class="g-content"></div></div>'
                         f'<figcaption>.nk-pressed</figcaption></figure>')
        if pc.composite:
            w, h = _gallery_sizes(pc)[0]
            demos.append(f'<figure><div class="{esc(class_name(pc.name))} nk-bare" style="width:{_px(w)};height:{_px(h)}">'
                         f'<span class="{esc(class_name(pc.name, pc.composite))}"></span></div>'
                         f'<figcaption>composite {esc(pc.composite)}</figcaption></figure>')
        extra = []
        for o in pc.layers[2:]:
            extra.append(f'&lt;span class="{esc(class_name(pc.name, o))}"&gt;&lt;/span&gt;')
        markup = (f'&lt;div class="{esc(class_name(pc.name))}"&gt;' + "".join(extra) + "…&lt;/div&gt;")
        if len(pc.layers) > 2:   # the gallery's own boxes need the extra children too
            kids = "".join(f'<span class="{esc(class_name(pc.name, o))}"></span>' for o in pc.layers[2:])
            demos = [d.replace('<div class="g-content">', kids + '<div class="g-content">') for d in demos]
        j = lambda v: _json.dumps(v, separators=(",", ":"))
        info = (f"sprite {_num(pc.sprite[0])}×{_num(pc.sprite[1])} dp · logical {_num(pc.logical[0])}×"
                f"{_num(pc.logical[1])} · slice {j(p.get('slice'))} · stretch {j(pc.stretch)} · content "
                f"{j(pc.content)} · overhang {j(p.get('overhang'))} · mode {p.get('mode', 'color')} · "
                f"stack {j(pc.layers)}" + ("" if pc.whole else
                                           " · " + ("image-set, common cut " + j(pc.cut) if pc.cut else
                                                    "one url() per scale")))
        cards.append(f'<section><h2>.{esc(class_name(pc.name))}</h2><p class="info">{esc(info)}</p>'
                     f'<p class="info"><code>{markup}</code></p><p class="info files">{esc(files)}</p>'
                     f'<div class="row checker">{"".join(demos)}</div>'
                     f'<div class="row dark">{"".join(demos)}</div></section>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ninekit {esc(str(manifest.get('name')))}</title>
<link rel="stylesheet" href="ninekit.css">
<style>
  body {{ margin: 0; padding: 16px; font: 13px/1.4 system-ui, sans-serif; background: #f4f1ea; color: #222; }}
  h1 {{ font-size: 18px; margin: 0 0 12px; }}
  h2 {{ font: 600 14px/1.2 ui-monospace, monospace; margin: 0 0 4px; }}
  section {{ margin: 0 0 18px; }}
  .info {{ margin: 0 0 4px; color: #555; font-size: 12px; }}
  .files {{ color: #888; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 18px; align-items: flex-start; padding: 14px; }}
  .checker {{ background: repeating-conic-gradient(#ddd 0 25%, #fff 0 50%) 0 0 / 16px 16px; }}
  .dark {{ background: #3B4252; color: #ddd; }}
  figure {{ margin: 0; }}
  figcaption {{ font-size: 11px; opacity: .7; margin-top: 6px; }}
  .g-content {{ width: 100%; height: 100%; min-height: 4px; outline: 1px dashed rgba(255, 0, 128, .55); }}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">{ramps}</svg>
<h1>ninekit · {esc(str(manifest.get('name')))} · {len(pieces)} pieces</h1>
<p class="info">Each piece at its natural logical size, ~1.6× wide, ~3× wide and taller; the dashed box is the
content area (content insets are measured from the canvas; padding = content - overhang). Shade pieces also show two example ramps
(<code>style="--nk-ramp: url(#nk-ramp-gold)"</code>).</p>
{"".join(cards)}
</body>
</html>
"""
