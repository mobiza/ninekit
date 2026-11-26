"""ninekit measure: read a reference screenshot and report what it is made of.

Two modes:

  ninekit measure IMAGE (--x X | --y Y) [--from A --to B] [--avg N] [--tol T] [--min-band PX] [--min-alpha A]
  ninekit measure IMAGE --corner tl|tr|bl|br [--box x0,y0,x1,y1]

Line mode segments the line into bands. A band is a run whose colour is constant or changes smoothly (adjacent
samples differ by at most `tol` in the worst RGBA channel, 0..255); a bigger jump starts a new band. Pixels with
alpha below `min_alpha` count as fully transparent (their RGB is ignored). Anti-aliased / soft edge pixels (a
blend of the two neighbouring bands, or an alpha ramp of up to 3 px next to transparency) are absorbed into the
band they belong to and reported as sub-pixel edge positions; bands thinner than `min_band` merge into the more
similar neighbour.

Positions are reference px along the line: `start` inclusive, `end` exclusive. dp = ref px * D / W when
--ref-width W --design-width D are given, otherwise dp = ref px.

JSON schema (--x / --y): a list, one object per band, top->bottom or left->right:
  start, end            int, px   integer pixel range [start, end) of the band, soft/AA edge pixels included
  thickness_px          int       end - start
  thickness_dp          float     thickness_px * dp scale
  start_dp, end_dp      float     start / end in dp
  edge_start, edge_end  float, px sub-pixel edge positions: where the band's material really begins / ends
                                  (from alpha coverage on silhouette edges, from colour interpolation on inner
                                  edges); equal to start / end when the edge is pixel aligned
  edge_start_dp, edge_end_dp  float  the same in dp
  kind                  "flat" | "gradient"
  soft_start, soft_end  int, px   edge pixels at each end excluded from the colours below
  start_color, mid_color, end_color  "#rrggbb"   of the solid core (soft pixels excluded)
  start_alpha, mid_alpha, end_alpha  int 0..255

JSON schema (--corner): one object
  corner                "tl" | "tr" | "bl" | "br"
  box                   [x0, y0, x1, y1]  px, x1/y1 exclusive
  radius_px, radius_dp  float     corner radius of the rounded rectangle
  edge_x_px, edge_x_dp  float     distance from the box's vertical side to the shape's straight vertical edge
  edge_y_px, edge_y_dp  float     distance from the box's horizontal side to the shape's straight horizontal edge
The corner fit uses alpha coverage: missing area in the corner = (1 - pi/4) * r^2.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from PIL import Image

DEFAULT_TOL = 10.0
DEFAULT_MIN_BAND = 1
DEFAULT_MIN_ALPHA = 8.0
FLAT_TOL = 3.0  # a band whose samples all stay within this of its mean is "flat"
TRANSPARENT_ALPHA = 12.0  # a band whose alpha stays below this counts as transparent (for soft edges)
MAX_SOFT_PX = 3  # longest alpha ramp absorbed as a soft edge

Color = tuple  # (r, g, b, a), ints 0..255


@dataclass
class Band:
    start: int
    end: int  # exclusive
    start_color: Color
    mid_color: Color
    end_color: Color
    flat: bool
    soft_start: int = 0  # leading edge px (alpha ramp / anti-aliased), included in start..end
    soft_end: int = 0  # trailing edge px likewise
    edge_start: Optional[float] = None  # sub-pixel position of the band's real start edge
    edge_end: Optional[float] = None

    def __post_init__(self):
        if self.edge_start is None:
            self.edge_start = float(self.start)
        if self.edge_end is None:
            self.edge_end = float(self.end)

    @property
    def thickness(self) -> int:
        return self.end - self.start

    @property
    def kind(self) -> str:
        return "flat" if self.flat else "gradient"

    def to_dict(self, dp_scale: float = 1.0) -> dict:
        d = {
            "start": self.start,
            "end": self.end,
            "thickness_px": self.thickness,
            "thickness_dp": round(self.thickness * dp_scale, 4),
            "start_dp": round(self.start * dp_scale, 4),
            "end_dp": round(self.end * dp_scale, 4),
            "edge_start": round(self.edge_start, 4),
            "edge_end": round(self.edge_end, 4),
            "edge_start_dp": round(self.edge_start * dp_scale, 4),
            "edge_end_dp": round(self.edge_end * dp_scale, 4),
            "kind": self.kind,
            "soft_start": self.soft_start,
            "soft_end": self.soft_end,
        }
        for name in ("start", "mid", "end"):
            c = getattr(self, name + "_color")
            d[name + "_color"] = hex_color(c)
            d[name + "_alpha"] = int(c[3])
        return d


def hex_color(c: Sequence[int]) -> str:
    return "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))


def _color_str(c: Sequence[int]) -> str:
    s = hex_color(c)
    return s if c[3] == 255 else f"{s}/a{int(c[3])}"


def _to_rgba(image) -> np.ndarray:
    """PIL image, path or ndarray -> float array (H, W, 4)."""
    if isinstance(image, (str, bytes)) or hasattr(image, "__fspath__"):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGBA"), dtype=np.float64)
    a = np.asarray(image, dtype=np.float64)
    if a.ndim == 2:
        a = np.stack([a, a, a, np.full_like(a, 255)], axis=-1)
    elif a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255.0)], axis=-1)
    return a


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    """Worst-channel difference; colour is ignored where both pixels are fully transparent."""
    if a[3] == 0 and b[3] == 0:
        return 0.0
    return float(np.abs(a - b).max())


def _rgb_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a[:3] - b[:3]).max())


def _sample_line(arr: np.ndarray, axis: str, pos: int, start, end, avg: int) -> tuple[np.ndarray, int]:
    h, w = arr.shape[:2]
    if axis not in ("x", "y"):
        raise ValueError("axis must be 'x' or 'y'")
    across, along = (w, h) if axis == "x" else (h, w)
    if not 0 <= pos < across:
        raise ValueError(f"--{axis} {pos} outside the image (0..{across - 1})")
    s = 0 if start is None else int(start)
    e = along if end is None else int(end)
    s, e = max(0, s), min(along, e)
    if e <= s:
        raise ValueError("empty range")
    avg = max(1, int(avg))
    lo = min(max(0, pos - avg // 2), across - avg) if avg <= across else 0
    hi = min(across, lo + avg)
    if axis == "x":
        block = arr[s:e, lo:hi, :]  # (n, avg, 4)
    else:
        block = arr[lo:hi, s:e, :].transpose(1, 0, 2)
    # alpha-weighted mean so transparent pixels do not drag the colour
    al = block[..., 3:4]
    tot = al.sum(axis=1)
    rgb = np.where(tot > 0, (block[..., :3] * al).sum(axis=1) / np.maximum(tot, 1e-9), block[:, 0, :3])
    a = block[..., 3].mean(axis=1, keepdims=True)
    return np.concatenate([rgb, a], axis=1), s


def _segment(px: np.ndarray, tol: float) -> list[list[int]]:
    cuts = [0]
    for i in range(1, len(px)):
        if _dist(px[i - 1], px[i]) > tol:
            cuts.append(i)
    cuts.append(len(px))
    return [[cuts[i], cuts[i + 1]] for i in range(len(cuts) - 1)]


def _ramp_ok(px: np.ndarray, ramp: list[int], q: int, tol: float) -> bool:
    """ramp: pixel indices ordered from the transparent side to the opaque pixel q."""
    if px[q][3] - px[ramp[0]][3] <= tol:
        return False
    nxt = q
    for i in reversed(ramp):
        if px[i][3] > px[nxt][3] or _rgb_dist(px[i], px[nxt]) > tol:
            return False
        nxt = i
    return True


def _absorb_soft(px: np.ndarray, segs: list[list[int]], tol: float, soft: set) -> bool:
    """Absorb alpha ramps (up to MAX_SOFT_PX px) beside a transparent band into the opaque band they fade into."""
    n = len(segs)
    transparent = [bool(px[s:e, 3].max() <= TRANSPARENT_ALPHA) for s, e in segs]
    for i in range(n):
        if not transparent[i]:
            continue
        for d in (1, -1):
            cands, total, j = [], 0, i + d
            while 0 <= j < n and not transparent[j] and total + segs[j][1] - segs[j][0] <= MAX_SOFT_PX:
                cands.append(j)
                total += segs[j][1] - segs[j][0]
                j += d
            for k in range(len(cands), 0, -1):
                o = i + d * (k + 1)
                if not 0 <= o < n or transparent[o]:
                    continue
                ramp = []
                for c in cands[:k]:
                    r = list(range(segs[c][0], segs[c][1]))
                    ramp += r if d == 1 else r[::-1]
                q = segs[o][0] if d == 1 else segs[o][1] - 1
                if not _ramp_ok(px, ramp, q, tol):
                    continue
                soft.update(ramp)
                if d == 1:
                    segs[o][0] = segs[cands[0]][0]
                else:
                    segs[o][1] = segs[cands[0]][1]
                for c in sorted(cands[:k], reverse=True):
                    del segs[c]
                return True
    return False


def _absorb_antialias(px: np.ndarray, segs: list[list[int]], tol: float, aa: dict) -> bool:
    """Absorb one 1-px band that is a blend of its neighbours into the nearer neighbour.

    Records aa[pixel] = sub-pixel position of the edge between the two neighbours (left one first)."""
    for i in range(1, len(segs) - 1):
        s, e = segs[i]
        if e - s != 1:
            continue
        a, c, b = px[segs[i - 1][1] - 1], px[s], px[segs[i + 1][0]]
        ab = b - a
        n2 = float(ab @ ab)
        if _dist(a, b) <= tol or n2 == 0:
            continue
        t = float((c - a) @ ab) / n2
        resid = _dist(c, a + t * ab)
        if -0.1 <= t <= 1.1 and resid <= tol:
            aa[s] = s + 1 - min(max(t, 0.0), 1.0)  # the right band covers share t of the pixel
            if t < 0.5:
                segs[i - 1][1] = e
            else:
                segs[i + 1][0] = s
            del segs[i]
            return True
    return False


def _merge_short(px: np.ndarray, segs: list[list[int]], min_band: int, tol: float) -> bool:
    cand = [i for i, (s, e) in enumerate(segs) if e - s < min_band]
    if not cand or len(segs) < 2:
        return False
    i = min(cand, key=lambda k: segs[k][1] - segs[k][0])
    s, e = segs[i]
    mean = px[s:e].mean(axis=0)
    dl = _dist(mean, px[segs[i - 1][1] - 1]) if i > 0 else float("inf")
    dr = _dist(mean, px[segs[i + 1][0]]) if i < len(segs) - 1 else float("inf")
    if 0 < i < len(segs) - 1 and _dist(px[segs[i - 1][1] - 1], px[segs[i + 1][0]]) <= tol:
        # a blip between two similar bands: fuse all three
        segs[i - 1][1] = segs[i + 1][1]
        del segs[i + 1]
    elif dl <= dr:
        segs[i - 1][1] = e
    else:
        segs[i + 1][0] = s
    del segs[i]
    return True


def _rgba(c: np.ndarray) -> Color:
    return tuple(int(v) for v in np.clip(np.rint(c), 0, 255))


def _boundary(px, L, R, soft, aa, sl, sr) -> float:
    """Sub-pixel position of the boundary between bands L=[s,e) and R. sl/sr: L's trailing / R's leading edge px."""
    if sl and all(i in soft for i in range(L[1] - sl, L[1])):
        q = px[L[1] - sl - 1][3]
        c = float(px[L[1] - sl:L[1], 3].sum()) / max(q, 1.0)
        return L[1] - sl + min(c, sl)
    if sr and all(i in soft for i in range(R[0], R[0] + sr)):
        q = px[R[0] + sr][3]
        c = float(px[R[0]:R[0] + sr, 3].sum()) / max(q, 1.0)
        return R[0] + sr - min(c, sr)
    if L[1] - 1 in aa:
        return aa[L[1] - 1]
    if R[0] in aa:
        return aa[R[0]]
    return float(L[1])


def measure_line(image, axis: str, pos: int, start: Optional[int] = None, end: Optional[int] = None,
                 avg: int = 1, tol: float = DEFAULT_TOL, min_band: int = DEFAULT_MIN_BAND,
                 min_alpha: float = DEFAULT_MIN_ALPHA) -> list[Band]:
    """Segment the line at column `pos` (axis 'x', read top to bottom) or row `pos` (axis 'y', left to right)."""
    px, offset = _sample_line(_to_rgba(image), axis, int(pos), start, end, avg)
    px[px[:, 3] < min_alpha] = 0.0
    segs = _segment(px, tol)
    soft: set = set()
    aa: dict = {}
    while _absorb_soft(px, segs, tol, soft):
        pass
    while _absorb_antialias(px, segs, tol, aa):
        pass
    while _merge_short(px, segs, min_band, tol):
        pass
    edge = soft | set(aa)
    lead, trail = [], []
    for s, e in segs:
        ss = 0
        while s + ss < e - 1 and s + ss in edge:
            ss += 1
        se = 0
        while e - 1 - se > s + ss and e - 1 - se in edge:
            se += 1
        lead.append(ss)
        trail.append(se)
    bounds = [float(segs[0][0])]
    for i in range(len(segs) - 1):
        bounds.append(_boundary(px, segs[i], segs[i + 1], soft, aa, trail[i], lead[i + 1]))
    bounds.append(float(segs[-1][1]))
    bands = []
    for i, (s, e) in enumerate(segs):
        run = px[s + lead[i]:e - trail[i]]
        mean = run.mean(axis=0)
        flat = max(_dist(p, mean) for p in run) <= FLAT_TOL
        bands.append(Band(offset + s, offset + e, _rgba(run[0]), _rgba(run[len(run) // 2]), _rgba(run[-1]), flat,
                          lead[i], trail[i], offset + bounds[i], offset + bounds[i + 1]))
    return bands


def fit_corner(image, corner: str, box: Optional[Sequence[int]] = None, min_alpha: float = DEFAULT_MIN_ALPHA) -> dict:
    """Radius of a rounded-rect corner from alpha coverage, plus the straight-edge offsets (px).

    box = (x0, y0, x1, y1), x1/y1 exclusive, must contain the whole shape's width/height (default: image).
    The window is the corner's half of the box; missing area = (1 - pi/4) r^2."""
    if corner not in ("tl", "tr", "bl", "br"):
        raise ValueError("corner must be tl, tr, bl or br")
    arr = _to_rgba(image)
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = (0, 0, w, h) if box is None else (int(v) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise ValueError("box too small")
    alpha = arr[y0:y1, x0:x1, 3].copy()
    alpha[alpha < min_alpha] = 0.0
    cov = alpha / 255.0
    if corner in ("tr", "br"):
        cov = cov[:, ::-1]
    if corner in ("bl", "br"):
        cov = cov[::-1, :]
    bh, bw = cov.shape
    hw, hh = math.ceil(bw / 2), math.ceil(bh / 2)
    rows = range(max(0, bh // 2 - 1), min(bh, bh // 2 + 2))
    cols = range(max(0, bw // 2 - 1), min(bw, bw // 2 + 2))
    dx = hw - float(np.mean([cov[r, :hw].sum() for r in rows]))
    dy = hh - float(np.mean([cov[:hh, c].sum() for c in cols]))
    missing = (hw - dx) * (hh - dy) - float(cov[:hh, :hw].sum())
    r = math.sqrt(max(missing, 0.0) / (1.0 - math.pi / 4.0))
    return {"corner": corner, "box": [x0, y0, x1, y1], "radius_px": r, "edge_x_px": dx, "edge_y_px": dy}


def _format_table(bands: list[Band], scale: float, axis: str, show_dp: bool) -> str:
    unit = "x" if axis == "y" else "y"
    head = ["#", f"{unit}0", f"{unit}1", "px"] + (["dp"] if show_dp else []) + ["edge0", "edge1", "kind", "soft",
                                                                                "start", "mid", "end"]
    rows = [head]
    for i, b in enumerate(bands):
        row = [str(i), str(b.start), str(b.end), str(b.thickness)]
        if show_dp:
            row.append(f"{b.thickness * scale:.2f}")
        row += [f"{b.edge_start:.2f}", f"{b.edge_end:.2f}", b.kind, f"{b.soft_start}/{b.soft_end}",
                _color_str(b.start_color), _color_str(b.mid_color), _color_str(b.end_color)]
        rows.append(row)
    widths = [max(len(r[c]) for r in rows) for c in range(len(head))]
    numeric = 6 + (1 if show_dp else 0)
    return "\n".join("  ".join(v.rjust(w) if c < numeric else v.ljust(w)
                               for c, (v, w) in enumerate(zip(r, widths))).rstrip() for r in rows)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ninekit measure", description=__doc__.split("\n\n")[0],
                                epilog="JSON schema" + __doc__.split("JSON schema", 1)[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image")
    p.add_argument("--x", type=int, help="sample the vertical line at this column (top to bottom)")
    p.add_argument("--y", type=int, help="sample the horizontal line at this row (left to right)")
    p.add_argument("--corner", choices=["tl", "tr", "bl", "br"], help="fit a rounded-rect corner radius")
    p.add_argument("--box", help="corner mode: x0,y0,x1,y1 (px, x1/y1 exclusive) around the shape; default whole image")
    p.add_argument("--from", dest="start", type=int, help="first position along the line (ref px)")
    p.add_argument("--to", dest="end", type=int, help="end position along the line, exclusive (ref px)")
    p.add_argument("--ref-width", type=float, help="reference image width W (for dp conversion)")
    p.add_argument("--design-width", type=float, help="design width D: dp = ref px * D / W")
    p.add_argument("--avg", type=int, default=1, help="average N px across the line")
    p.add_argument("--tol", type=float, default=DEFAULT_TOL, help="max adjacent difference inside a band (0..255)")
    p.add_argument("--min-band", type=int, default=DEFAULT_MIN_BAND, help="merge bands thinner than this (px)")
    p.add_argument("--min-alpha", type=float, default=DEFAULT_MIN_ALPHA,
                   help="pixels with alpha below this count as transparent (default 8)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if (a.ref_width is None) != (a.design_width is None):
        p.error("--ref-width and --design-width go together")
    if (a.x is not None) + (a.y is not None) + (a.corner is not None) != 1:
        p.error("give exactly one of --x, --y, --corner")
    scale = 1.0
    if a.ref_width:
        if a.ref_width <= 0:
            p.error("--ref-width must be positive")
        scale = a.design_width / a.ref_width
    try:
        if a.corner:
            box = [int(v) for v in a.box.split(",")] if a.box else None
            if box is not None and len(box) != 4:
                p.error("--box needs x0,y0,x1,y1")
            res = fit_corner(a.image, a.corner, box, a.min_alpha)
            for k in ("radius", "edge_x", "edge_y"):
                res[k + "_dp"] = res[k + "_px"] * scale
            res = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}
            if a.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"corner {res['corner']}  box {res['box']}")
                for k, label in (("radius", "radius"), ("edge_x", "edge x"), ("edge_y", "edge y")):
                    print(f"  {label:7s} {res[k + '_px']:8.3f} px  {res[k + '_dp']:8.3f} dp")
            return 0
        axis, pos = ("x", a.x) if a.x is not None else ("y", a.y)
        bands = measure_line(a.image, axis, pos, a.start, a.end, a.avg, a.tol, a.min_band, a.min_alpha)
    except (ValueError, OSError) as ex:
        print(f"ninekit measure: {ex}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps([b.to_dict(scale) for b in bands], indent=2))
    else:
        print(_format_table(bands, scale, axis, a.ref_width is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
