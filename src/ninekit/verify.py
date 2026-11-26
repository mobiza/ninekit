"""`ninekit verify` (DESIGN 5): measured checks of every file of a manifest (or a freshly built spec)."""
from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from ninekit import NinekitError
from ninekit.manifest import load_manifest
from ninekit.slicing import BEND_TOL, SEAM_TOL, SMOOTH_TOL

MAX_TEXTURE = 2048


@dataclass
class FileResult:
    piece: str
    output: str
    scale: str
    file: str
    status: str = "ok"
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.status = "fail"
        self.reasons.append(reason)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerifyReport:
    files: list
    problems: dict          # piece -> spec-level reasons (from a spec build)
    warnings: dict = field(default_factory=dict)    # piece -> spec-level notes (snapped sizes, off-grid slices)

    @property
    def ok(self) -> bool:
        return all(f.status == "ok" for f in self.files) and not self.problems

    def as_dict(self) -> dict:
        return {"ok": self.ok, "files": [f.as_dict() for f in self.files], "problems": self.problems,
                "warnings": self.warnings, "summary": self.summary()}

    def summary(self) -> str:
        n_ok = sum(f.status == "ok" for f in self.files)
        n_fail = len(self.files) - n_ok
        n_warn = sum(bool(f.warnings) for f in self.files)
        s = f"verify: {n_ok} ok, {n_fail} fail, {n_warn} with warnings"
        if self.problems:
            s += f", {len(self.problems)} piece(s) with spec problems"
        if self.warnings:
            s += f", {len(self.warnings)} piece(s) with spec warnings"
        return s

    def piece_status(self) -> dict:
        """piece -> {"fail": [reasons], "warn": [warnings]} for every piece with either (preview labels)."""
        out: dict = {}
        for f in self.files:
            e = out.setdefault(f.piece, {"fail": [], "warn": []})
            e["fail"] += [r for r in f.reasons if r not in e["fail"]]
            e["warn"] += [w for w in f.warnings if w not in e["warn"]]
        for piece, reasons in self.problems.items():
            e = out.setdefault(piece, {"fail": [], "warn": []})
            e["fail"] = list(reasons) + [r for r in e["fail"] if r not in reasons]
        for piece, notes in self.warnings.items():
            e = out.setdefault(piece, {"fail": [], "warn": []})
            e["warn"] = list(notes) + [w for w in e["warn"] if w not in notes]
        return {k: v for k, v in out.items() if v["fail"] or v["warn"]}


def _lines(arr: np.ndarray, axis: str) -> np.ndarray:
    a = arr.astype(np.int16)
    return a.transpose(1, 0, 2) if axis == "x" else a


def _check_stretch(arr: np.ndarray, axis: str, lo: int, hi: int, mode: str, res: FileResult) -> None:
    """Rules 2 and 3: the stretch region [lo, hi) along [axis] (x = columns, y = rows). A `fixed` axis is drawn
    at its natural length, so its middle is not checked."""
    if mode == "fixed":
        return
    lines = _lines(arr, axis)          # (n, other, 4)
    n = lines.shape[0]
    name, other = ("column", "rows") if axis == "x" else ("row", "columns")
    if hi - lo < 1 and mode == "tile":
        res.fail(f"{axis} tile region is empty (slice_px leaves no middle {name}s): no tile period was found on {axis}; "
                 f"give the piece `period: [pw, ph]` (dp) when a shape repeats, or check the noise/image period")
        return
    if hi - lo < 1:
        how = "horizontally" if axis == "x" else "vertically"
        res.fail(f"{axis} stretch region is empty (slice_px leaves no middle {name}s): the piece cannot stretch "
                 f"{how} although stretch {axis} is {mode}; give it a middle, or set stretch {axis} to fixed if it is "
                 f"meant to keep its natural length")
        return
    region = lines[lo:hi]
    if mode == "tile":
        if hi < n:
            seam = np.abs(lines[hi] - lines[lo]).max()
            where = f"{name} {hi} (after the region) vs {name} {lo} (its first)"
        elif lo > 0:
            seam = np.abs(lines[lo - 1] - lines[hi - 1]).max()
            where = f"{name} {lo - 1} (before the region) vs {name} {hi - 1} (its last)"
        else:
            inner = np.abs(np.diff(region, axis=0)).max() if hi - lo > 1 else 0
            seam = max(0, int(np.abs(region[-1] - region[0]).max()) - int(inner))
            where = f"wrap from {name} {hi - 1} to {name} {lo} beyond the texture's own detail"
        if seam > SEAM_TOL:
            res.fail(f"{axis} tile region [{lo}, {hi}) is not seamless: {where} differ by {int(seam)}/255 "
                     f"(allowed {SEAM_TOL}); make the region a whole number of periods")
        return
    if axis == "x":
        d = np.abs(region - region[0:1]).max(axis=(1, 2))
        bad = np.nonzero(d)[0]
        if bad.size:
            c = int(bad[0]) + lo
            rows = np.nonzero(np.abs(lines[c] - lines[lo]).max(axis=1))[0]
            res.fail(f"x stretch region [{lo}, {hi}) is not uniform: column {c} differs from column {lo} by up to "
                     f"{int(d.max())}/255 ({other} {int(rows.min())}..{int(rows.max())}); a horizontal feature sits in "
                     f"the stretched middle: move it into the side slices or use vertical gradients only")
        return
    if hi - lo < 2:
        return
    step = np.abs(np.diff(region, axis=0)).max(axis=(1, 2))
    bad = np.nonzero(step > SMOOTH_TOL)[0]
    if bad.size:
        r = int(bad[0]) + lo
        res.fail(f"y stretch region [{lo}, {hi}) is not smooth: rows {r} and {r + 1} differ by {int(step.max())}/255 "
                 f"(allowed {SMOOTH_TOL}); keep edges and lines out of the stretched rows")
        return
    if hi - lo < 3:
        return
    bend = np.abs(region[2:] - 2 * region[1:-1] + region[:-2]).max(axis=(1, 2))
    bad = np.nonzero(bend > BEND_TOL)[0]
    if bad.size:
        r = int(bad[0]) + lo + 1
        res.fail(f"y stretch region [{lo}, {hi}) is not smooth: rows {r - 1}..{r + 1} bend by {int(bend.max())}/255 "
                 f"(second difference, allowed {BEND_TOL}): a low-contrast slanted line or pattern crosses the "
                 f"stretched rows; move it into the top/bottom slices, or set stretch y to fixed")


def verify_manifest(path) -> VerifyReport:
    mpath = Path(path)
    if mpath.is_dir():
        mpath = mpath / "ninekit.json"
    manifest = load_manifest(mpath)
    results: list[FileResult] = []
    for pname, piece in manifest["pieces"].items():
        stretch = piece.get("stretch", ["stretch", "stretch"])
        if isinstance(stretch, str):
            stretch = [stretch, stretch]
        order = piece.get("stack") or list(piece["outputs"])
        by_scale: dict = {}
        for o in order:
            for sk, entry in piece["outputs"].get(o, {}).items():
                res = FileResult(pname, o, sk, entry["file"])
                results.append(res)
                by_scale.setdefault(sk, []).append((res, entry))
                _verify_file(mpath.parent, entry, stretch, float(sk), res)
                _check_dp(piece, entry, float(sk), res)
        # rule 4: outputs of one piece share size and slices
        for sk, items in by_scale.items():
            base = items[0][1]
            for res, entry in items[1:]:
                if entry["size_px"] != base["size_px"] or entry["slice_px"] != base["slice_px"]:
                    res.fail(f"outputs differ at @{sk}x: {entry['size_px']} / {entry['slice_px']} vs "
                             f"{base['size_px']} / {base['slice_px']} ({items[0][0].output})")
    return VerifyReport(files=results, problems={})


def _verify_file(root: Path, entry: dict, stretch, scale: float, res: FileResult) -> None:
    path = root / entry["file"]
    try:
        with Image.open(path) as im:
            arr = np.asarray(im.convert("RGBA"))
    except (OSError, ValueError) as e:
        res.fail(f"cannot read {entry['file']}: {e}")
        return
    h, w = arr.shape[:2]
    if [w, h] != list(entry["size_px"]):
        res.fail(f"image is {w}x{h} px, the manifest says {entry['size_px'][0]}x{entry['size_px'][1]}")
        return
    if max(w, h) > MAX_TEXTURE:
        res.warnings.append(f"texture {w}x{h} px is larger than {MAX_TEXTURE} px")
    sp = entry.get("slice_px")
    if sp is None:
        return
    l, t, r, b = sp
    # rule 1 (an empty middle, l + r == w, fails below unless the axis is fixed)
    if min(sp) < 0 or l + r > w or t + b > h:
        res.fail(f"slice_px {sp} does not fit the {w}x{h} image (needs l + r <= w and t + b <= h)")
        return
    _check_stretch(arr, "x", l, w - r, stretch[0], res)
    _check_stretch(arr, "y", t, h - b, stretch[1], res)
    # rule 5 warnings
    if h - b > t and w - r > l and not arr[t:h - b, l:w - r, 3].any():
        res.warnings.append("the stretch region is fully transparent")
    thin = [v for v in sp if 0 < v < scale]
    if thin:
        res.warnings.append(f"slice(s) {thin} px are thinner than 1 dp at @{res.scale}x")


def _check_dp(piece: dict, entry: dict, scale: float, res: FileResult) -> None:
    """Rule 6: a file's px are the piece's dp x its scale (one dp slice is exact in every file). Auto-sliced pieces
    fail; slice / slice_px / block pieces (the author chose the px) are warned."""
    tol = 0.006 * scale + 1e-6            # the manifest keeps dp to 2 decimals
    bad = []
    size = piece.get("size")
    if size is not None and any(abs(px - dp * scale) > tol for px, dp in zip(entry["size_px"], size)):
        bad.append(f"size_px {entry['size_px']} != size {size} dp x {res.scale}")
    sl, sp = piece.get("slice"), entry.get("slice_px")
    if sl is not None and sp is not None and any(abs(px - dp * scale) > tol for px, dp in zip(sp, sl)):
        bad.append(f"slice_px {sp} != slice {sl} dp x {res.scale}")
    if not bad:
        return
    msg = "; ".join(bad) + ": the files of this piece do not share one dp size/slice"
    if piece.get("slicing") == "auto":
        res.fail(msg + " (auto slices are on the dp grid at every scale; rebuild with this ninekit)")
    else:
        res.warnings.append(msg + " (one dp slice is not exact at every scale, e.g. for Flutter's centerSlice "
                                  "or CSS image-set)")


def verify_spec(spec_path, theme=None) -> VerifyReport:
    """Builds the spec into a temporary folder and verifies it, plus the spec-level problems found while
    rendering (auto slicing that found no stretchable middle, periodic paints on stretch axes)."""
    from ninekit.render import build

    with tempfile.TemporaryDirectory(prefix="ninekit-verify-") as tmp:
        result = build(spec_path, theme=theme, out=tmp)
        report = verify_manifest(Path(tmp) / "ninekit.json")
    report.problems = result.problems
    report.warnings = result.warnings
    return report


def verify(target, theme=None) -> VerifyReport:
    """A SPEC (built fresh, optionally with a theme), a manifest, or a folder holding ninekit.json."""
    p = Path(target)
    if p.suffix.lower() in (".yaml", ".yml"):
        return verify_spec(p, theme)
    if theme is not None:
        raise NinekitError("--theme applies to a SPEC; this is a manifest")
    return verify_manifest(p)
