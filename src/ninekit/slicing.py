"""Automatic 9-slice borders and lossless compaction on the dp grid (DESIGN 2.4).

All functions work on uint8 RGBA arrays (h, w, 4); a piece's outputs are judged together, so every output
of a piece gets the same slices. Auto slicing looks at every scale of a piece at once and works in *grid
steps* (the dp grid g of the spec: the smallest dp step that is whole texels at every scale), so every file
of a piece gets the same dp slices and the same dp size: `slice_px == slice_dp x scale` exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np

SMOOTH_TOL = 8      # /255: adjacent rows of a "smooth" stretch region (gradients)
BEND_TOL = 3        # /255: |second difference| of three rows inside a smooth region (a gradient bends only a little;
                    # a low-contrast slanted line or pattern bends sharply where it crosses a texel)
SEAM_TOL = 2        # /255: tile seams
# A mirror-symmetric feature centred on the piece always yields 2 equal centre columns (1 for an odd width);
# a real stretchable middle needs more than that.
MIN_RUN_X = 3
# y: the identical rows around the centre win over the longer smooth run only when the smooth run adds at most
# this much (dp, per side): the anti-aliased start of rounded corners, not a gradient (DESIGN 2.4).
IDENTICAL_SLACK_DP = 1
X_HINT = ("keep horizontal features (gradients, highlights, noise) inside the side slices, set slice: none, use "
          "stretch: tile with a periodic paint, or stretch: [fixed, ...] if it is not meant to stretch")


def _stack(arrays: list[np.ndarray]) -> np.ndarray:
    return np.concatenate([a.astype(np.int16) for a in arrays], axis=2)


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Maximal runs [a, b) of True in a 1-D bool array."""
    out, start = [], None
    for i, f in enumerate(flags.tolist()):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(flags)))
    return out


def _run_around(same: np.ndarray, n: int) -> tuple[int, int]:
    """The run [a, b) of lines (n of them) joined by same[i] (line i ~ line i + 1) containing the centre.

    For an even count the two centre lines are both tried and the longer run wins.
    """
    best = None
    for c in sorted({(n - 1) // 2, n // 2}):
        a = c
        while a > 0 and same[a - 1]:
            a -= 1
        b = c + 1
        while b < n and same[b - 1]:
            b += 1
        if best is None or b - a > best[1] - best[0]:
            best = (a, b)
    return best


def _lines(arr: np.ndarray, axis: str) -> np.ndarray:
    """Lines along the axis as a (n, k) int array: columns for "x", rows for "y"."""
    if axis == "x":
        return arr.transpose(1, 0, 2).reshape(arr.shape[1], -1)
    return arr.reshape(arr.shape[0], -1)


def _steps(lines: np.ndarray) -> np.ndarray:
    """Largest channel difference between line i and line i + 1 (n - 1 values)."""
    if lines.shape[0] < 2:
        return np.zeros(0, dtype=np.int64)
    return np.abs(lines[1:] - lines[:-1]).max(axis=1)


def _bends(lines: np.ndarray) -> np.ndarray:
    """|line i - 2 line i+1 + line i+2| (largest channel), n - 2 values: bend[j] belongs to the middle line j + 1."""
    if lines.shape[0] < 3:
        return np.zeros(0, dtype=np.int64)
    return np.abs(lines[2:] - 2 * lines[1:-1] + lines[:-2]).max(axis=1)


def smooth_run_around(lines: np.ndarray) -> tuple[int, int]:
    """The longest run [a, b) of rows around the centre that is smooth: adjacent rows differ by <= SMOOTH_TOL and
    every three consecutive rows inside it bend by <= BEND_TOL (identical rows are smooth too)."""
    n = lines.shape[0]
    if n < 2:
        return 0, n
    pair = _steps(lines) <= SMOOTH_TOL            # pair[i]: rows i, i + 1
    tri = _bends(lines) <= BEND_TOL               # tri[j]: rows j, j + 1, j + 2
    best = None
    for c in sorted({(n - 1) // 2, n // 2}):
        for left_first in (True, False):
            a, b = c, c + 1
            for _ in range(2):
                for side in ((0, 1) if left_first else (1, 0)):
                    if side == 0:
                        while a > 0 and pair[a - 1] and (b - a < 2 or tri[a - 1]):
                            a -= 1
                    else:
                        while b < n and pair[b - 1] and (b - a < 2 or tri[b - 2]):
                            b += 1
            if best is None or b - a > best[1] - best[0]:
                best = (a, b)
    return best


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def tile_run(stacked: np.ndarray, axis: str, period: int) -> tuple[int, int] | None:
    """The tile region [l, l + k * period) whose line after it repeats its first (seamless), or None
    (one image on its own; auto slicing uses the grid-aware search in plan_slices).

    Lines x and x + period must match within SEAM_TOL across the whole region; the longest such run wins
    (ties: closest to the centre).
    """
    lines = _lines(stacked, axis)
    n = lines.shape[0]
    p = max(1, int(period))
    if n <= p:
        return None
    ok = np.abs(lines[p:] - lines[:-p]).max(axis=1) <= SEAM_TOL      # ok[x]: line x ~ line x + p
    runs = _runs(ok)
    if not runs:
        return None
    centre = (n - 1) / 2.0
    a, b = max(runs, key=lambda r: (r[1] - r[0], -abs((r[0] + r[1]) / 2.0 - centre)))
    k = (b - 1 - a) // p + 1
    return a, a + k * p


# --- the dp-grid planner ----------------------------------------------------------------------------------------------

@dataclass
class AxisCut:
    """One axis of a piece's slices, in grid steps: [lo] steps before the middle, [hi] after it."""
    lo: int
    hi: int
    mode: str               # stretch | tile | fixed (the manifest's value for this axis)
    identical: bool         # the middle lines are byte-identical at every scale (compactable)

    def __post_init__(self):
        # plain Python numbers: numpy integers would leak into slice_px, the manifest and --json output
        self.lo, self.hi, self.identical = int(self.lo), int(self.hi), bool(self.identical)


def _fixed_cut(n: int) -> AxisCut:
    """Exactly one grid step in the middle, centred (a fixed axis is drawn at its natural length)."""
    lo = (n - 1) // 2
    return AxisCut(lo, n - 1 - lo, "fixed", False)


def _empty_cut(n: int, mode: str) -> AxisCut:
    """No middle at all: the axis cannot stretch, and verify fails on the empty stretch region."""
    lo = n // 2
    return AxisCut(lo, n - lo, mode, False)


def _label(s) -> str:
    f = float(s)
    return f"@{int(f) if f.is_integer() else f'{f:g}'}x"


def _middle_identical(lines_by_scale: dict, gs: dict, lo: int, n: int, hi: int) -> bool:
    for s, lines in lines_by_scale.items():
        a, b = lo * gs[s], (n - hi) * gs[s]
        if b - a > 1 and np.any(_steps(lines[a:b])):
            return False
    return True


def _dp_run(lines_by_scale: dict, gs: dict, tol, short: list | None = None):
    """(lo, hi) grid steps outside the run of lines around the centre joined within [tol] (or the smooth rule,
    tol "smooth"), over every scale: per scale the run is rounded inwards to whole grid steps and the largest lo /
    hi win."""
    lo = hi = 0
    for s, lines in lines_by_scale.items():
        m = lines.shape[0]
        if tol == "smooth":
            a, b = smooth_run_around(lines)
        else:
            a, b = _run_around(_steps(lines) <= tol, m) if m > 1 else (0, 1)
        if short is not None and b - a < MIN_RUN_X:
            short.append(f"{b - a} px at {_label(s)}")
        lo = max(lo, _ceil_div(a, gs[s]))
        hi = max(hi, _ceil_div(m - b, gs[s]))
    return lo, hi


def _stretch_axis(axis: str, lines_by_scale: dict, n: int, gs: dict, grid, problems: list) -> AxisCut:
    """x: the identical columns around the centre. y: the longest smooth run of rows around the centre row
    (identical rows are smooth too); its identical core wins instead only when the smooth run is at most
    IDENTICAL_SLACK_DP longer on each side. Per scale a run becomes whole grid steps (rounded inwards) and the
    dp slices are the largest over the scales. Less than one grid step in common: x fails, y is fixed."""
    grid_txt = str(grid.numerator) if grid.denominator == 1 else f"{grid.numerator}/{grid.denominator}"
    if axis == "x":
        short: list = []
        lo, hi = _dp_run(lines_by_scale, gs, 0, short)
        if short:
            problems.append(f"x: the identical columns around the centre are only {', '.join(short)} wide (at least "
                            f"{MIN_RUN_X} needed), so the piece cannot stretch horizontally; {X_HINT}")
            return _empty_cut(n, "stretch")
        if n - lo - hi < 1:
            problems.append(f"x: the identical columns around the centre share no whole {grid_txt} dp grid step at "
                            f"every scale, so the piece cannot stretch horizontally; {X_HINT}")
            return _empty_cut(n, "stretch")
        return AxisCut(lo, hi, "stretch", True)
    lo, hi = _dp_run(lines_by_scale, gs, "smooth")
    if n - lo - hi < 1:
        return _fixed_cut(n)
    ilo, ihi = _dp_run(lines_by_scale, gs, 0)
    slack = _ceil_div(IDENTICAL_SLACK_DP * grid.denominator, grid.numerator)
    if n - ilo - ihi >= 1 and ilo - lo <= slack and ihi - hi <= slack:
        return AxisCut(ilo, ihi, "stretch", True)
    return AxisCut(lo, hi, "stretch", _middle_identical(lines_by_scale, gs, lo, n, hi))


def _tile_axis(axis: str, lines_by_scale: dict, n: int, gs: dict, periods: dict, problems: list) -> AxisCut:
    """The region of whole periods (the same dp period at every scale) where line x matches line x + period
    (within SEAM_TOL) at every scale; most periods wins, ties: centred. No region -> the axis fails."""
    p_steps = None
    runs = {}
    for s, lines in lines_by_scale.items():
        p = int(periods.get(s) or 0) or gs[s]
        if p % gs[s] or (p_steps is not None and p // gs[s] != p_steps):
            got = ", ".join(f"{(int(periods.get(t) or 0) or gs[t]) / float(t):g} dp at {_label(t)}"
                            for t in lines_by_scale)
            problems.append(f"{axis}: the periodic paints repeat every {got}: not one whole number of grid steps, so "
                            f"the tile region cannot be the same at every scale")
            return _empty_cut(n, "tile")
        p_steps = p // gs[s]
        m = lines.shape[0]
        ok = (np.abs(lines[p:] - lines[:-p]).max(axis=1) <= SEAM_TOL) if m > p else np.zeros(0, dtype=bool)
        # run_end[x]: the first index >= x whose line does not repeat one period later
        run_end = np.arange(len(ok) + 1)
        nxt = len(ok)
        for i in range(len(ok) - 1, -1, -1):
            if not ok[i]:
                nxt = i
            run_end[i] = nxt
        runs[s] = (run_end, p, len(ok))
    best = None
    for start in range(n):
        k = None
        for s, (run_end, p, m) in runs.items():
            x0 = start * gs[s]
            length = run_end[x0] - x0 if x0 < m else 0
            ks = (length - 1) // p + 1 if length >= 1 else 0
            k = ks if k is None else min(k, ks)
            if k == 0:
                break
        if k:
            key = (k, -abs(2 * start + k * p_steps - n), -start)
            if best is None or key > best[0]:
                best = (key, start, k)
    if best is None:
        problems.append(f"{axis}: no tile period found on {axis} (stretch {axis} is tile, but nothing repeats every "
                        f"{p_steps} grid step(s) at every scale); give the piece `period: [pw, ph]` (dp) when a shape "
                        f"repeats, check the noise/image period, or use stretch / fixed")
        return _empty_cut(n, "tile")
    _, start, k = best
    return AxisCut(start, n - start - k * p_steps, "tile", False)


def plan_slices(stacks: dict, steps: tuple[int, int], gs: dict, stretch, periods: dict, grid=None):
    """The dp slices of a piece from its renders at every scale.

    stacks: scale -> stacked int16 (h, w, c) of all outputs; steps: (nw, nh) the canvas in grid steps (the same
    at every scale); gs: scale -> texels per grid step; stretch: the requested [x, y] modes; periods: scale ->
    (px_x, px_y) of the periodic paints (0 = none); grid: the dp grid (for messages and the y slack).
    Returns ([AxisCut x, AxisCut y], problems).
    """
    problems: list[str] = []
    cuts = []
    grid = Fraction(1) if grid is None else Fraction(grid)
    for i, axis in enumerate(("x", "y")):
        n = steps[i]
        lines = {s: _lines(st, axis) for s, st in stacks.items()}
        mode = stretch[i]
        if mode == "fixed":
            cuts.append(_fixed_cut(n))
        elif mode == "tile":
            cuts.append(_tile_axis(axis, lines, n, gs, {s: periods[s][i] for s in stacks}, problems))
        else:
            cuts.append(_stretch_axis(axis, lines, n, gs, grid, problems))
    return cuts, problems


def cut_scale(arrays: list[np.ndarray], cuts, steps: tuple[int, int], g_px: int, keep_steps: int | None):
    """One scale's slice_px from the plan, and the arrays compacted to [keep_steps] grid steps of identical
    middle (None = no compaction): (arrays, slice_px)."""
    cx, cy = cuts
    slice_px = [int(v) * int(g_px) for v in (cx.lo, cy.lo, cx.hi, cy.hi)]
    if keep_steps is None:
        return arrays, slice_px
    return compact(arrays, slice_px, keep_steps * g_px,
                   cx.identical and cx.mode == "stretch" and steps[0] - cx.lo - cx.hi > keep_steps,
                   cy.identical and cy.mode == "stretch" and steps[1] - cy.lo - cy.hi > keep_steps)


def auto_slice(arrays: list[np.ndarray], stretch: tuple[str, str], periods: tuple[int, int]):
    """One image set on its own (one texel = one grid step): (slice_px [l, t, r, b], compact_x, compact_y,
    problems). The build uses plan_slices over every scale."""
    h, w = arrays[0].shape[:2]
    cuts, problems = plan_slices({1: _stack(arrays)}, (w, h), {1: 1}, list(stretch), {1: tuple(periods)})
    cx, cy = cuts
    return [cx.lo, cy.lo, cx.hi, cy.hi], cx.identical, cy.identical, problems


def compact(arrays: list[np.ndarray], slice_px: list[int], keep: int, cx: bool, cy: bool):
    """Removes identical middle columns / rows down to [keep] texels: (arrays, slice_px), lossless."""
    l, t, r, b = slice_px
    h, w = arrays[0].shape[:2]
    keep = max(1, int(keep))
    if cx and w - l - r > keep:
        cols = np.r_[0:l + keep, w - r:w]
        arrays = [a[:, cols] for a in arrays]
    if cy and h - t - b > keep:
        rows = np.r_[0:t + keep, h - b:h]
        arrays = [a[rows] for a in arrays]
    return [np.ascontiguousarray(a) for a in arrays], [l, t, r, b]
