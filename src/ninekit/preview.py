"""`ninekit preview` (DESIGN 6): one contact sheet of every piece, 9-slice-rendered at several sizes.

Per piece: its own size, ~1.6x wide, ~3x wide and 1.6x taller (whole pieces only at their own size), each
on a checkerboard and on --bg, outputs stacked bottom to top as a runtime stacks them, labelled with the
name and sizes. A `tile` axis is shown with a whole number of repeats (like a runtime's tile-fit): a partial
last tile meets the end slice at an arbitrary phase; a `fixed` axis (or one with no middle) keeps its natural
length. Pieces that fail `verify` or carry warnings get a red label and their first reasons. It is what an
agent (or a person) looks at to judge the art.
"""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ninekit import NinekitError
from ninekit.canvas import hexc
from ninekit.manifest import load_manifest, scale_key
from ninekit.ninepatch import nine_slice_premul

PAD = 10          # around each cell's image
GAP = 12          # between cells
MARGIN = 20
MAX_W = 2000      # shelf width of the sheet
SHEET_BG = (236, 236, 236)
CHECK = (255, 255, 255), (206, 206, 210)
CHECK_PX = 8


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1: bitmap font only
        return ImageFont.load_default()


def _checker(w: int, h: int) -> np.ndarray:
    ys, xs = np.mgrid[0:h, 0:w]
    on = ((xs // CHECK_PX) + (ys // CHECK_PX)) % 2 == 0
    out = np.empty((h, w, 3))
    out[on] = np.array(CHECK[0]) / 255.0
    out[~on] = np.array(CHECK[1]) / 255.0
    return out


def _cell(layers: list, slice_px, stretch, size, bg) -> np.ndarray:
    """The stacked outputs at [size] over a background ([bg] RGB or None = checkerboard), uint8 RGB."""
    W, H = size
    cw, ch = W + 2 * PAD, H + 2 * PAD
    base = _checker(cw, ch) if bg is None else np.broadcast_to(bg, (ch, cw, 3)).copy()
    for img in layers:
        p = nine_slice_premul(img, slice_px, (W, H), stretch)
        region = base[PAD:PAD + H, PAD:PAD + W]
        base[PAD:PAD + H, PAD:PAD + W] = p[..., :3] + region * (1.0 - p[..., 3:4])
    return (np.clip(base, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def _snap(n: int, lo: int, hi: int, total: int, mode: str) -> int:
    """A target length whose tiled middle is a whole number of repeats (as a runtime's tile-fit would draw)."""
    if mode != "tile":
        return n
    region = total - lo - hi
    if region <= 0:
        return n
    k = max(1, round((n - lo - hi) / region))
    return lo + hi + k * region


def _sizes(w: int, h: int, sliced: bool, slice_px, stretch, design=None) -> list:
    """Cell sizes (px): the DESIGN size first (the spec's size, not the compacted texture [w] x [h]), then 1.5x
    wider and 2x wider + 1.5x taller. A fixed axis (or one without a middle) keeps its natural length; a tile axis
    shows whole repeats."""
    if not sliced:
        return [(w, h)]
    l, t, r, b = slice_px
    grow_x = stretch[0] != "fixed" and l + r < w
    grow_y = stretch[1] != "fixed" and t + b < h
    dw, dh = design or (w, h)
    dw, dh = (max(w, dw) if grow_x else w), (max(h, dh) if grow_y else h)
    sizes = [(dw, dh)]
    if grow_x:
        sizes.append((round(dw * 1.5), dh))
    if grow_x or grow_y:
        sizes.append((round(dw * 2) if grow_x else dw, round(dh * 1.5) if grow_y else dh))
    return [(_snap(W, l, r, w, stretch[0]), _snap(H, t, b, h, stretch[1])) for W, H in sizes]


FAIL_RGB = (196, 24, 24)
REASON_W = 110      # characters per reason line
REASON_LINES = 3


def _status(mpath: Path, problems: dict | None, warnings: dict | None) -> dict:
    """piece -> {"fail": [...], "warn": [...]}: verify of the manifest plus the spec-level problems/warnings."""
    from ninekit.verify import verify_manifest

    report = verify_manifest(mpath)
    report.problems = dict(problems or {})
    report.warnings = dict(warnings or {})
    return report.piece_status()


def _reason_lines(st: dict) -> list:
    """The first failures / warnings of a piece, word-wrapped to REASON_LINES lines."""
    items = [("FAIL", r) for r in st["fail"]] + [("warning", w) for w in st["warn"]]
    out: list = []
    shown = 0
    partial = False
    for tag, r in items:
        wrapped = textwrap.wrap(f"{tag}: {r}", REASON_W, subsequent_indent="  ")
        room = REASON_LINES - len(out)
        out += wrapped[:room]
        if len(wrapped) <= room:
            shown += 1
        else:
            partial = True
        if len(out) >= REASON_LINES:
            break
    others = len(items) - shown - (1 if partial else 0)
    if partial or others:
        tail = " ..." + (f" (+{others} more)" if others else "")
        out[-1] = out[-1][:REASON_W - len(tail)].rstrip() + tail
    return out


def render_sheet(manifest_path, out_path, bg: str = "#3B4252", scale=None, problems: dict | None = None,
                 warnings: dict | None = None) -> Path:
    mpath = Path(manifest_path)
    if mpath.is_dir():
        mpath = mpath / "ninekit.json"
    manifest = load_manifest(mpath)
    status = _status(mpath, problems, warnings)
    bg_rgb = hexc(bg)
    scales = [scale_key(s) for s in manifest.get("scales", [])]
    want = scale_key(scale) if scale is not None else max(scales, key=float)
    if want not in scales:
        raise NinekitError(f"--scale {want}: the manifest has scales {manifest.get('scales')}")
    font = _font(15)
    small = _font(12)
    blocks = []
    for pname, piece in manifest["pieces"].items():
        order = piece.get("stack") or list(piece["outputs"])
        if "main" in order and len(order) > 1:
            order = [o for o in order if o != "main"]   # "main" next to named outputs is their composite
        entries = [piece["outputs"][o][want] for o in order if want in piece["outputs"].get(o, {})]
        if not entries:
            continue
        layers = []
        for e in entries:
            with Image.open(mpath.parent / e["file"]) as im:
                layers.append(np.asarray(im.convert("RGBA")))
        sp = entries[0]["slice_px"]
        h, w = layers[0].shape[:2]
        stretch = piece.get("stretch", ["stretch", "stretch"])
        if isinstance(stretch, str):
            stretch = [stretch, stretch]
        size_dp = piece.get("size")
        design_dp = piece.get("design_size") or size_dp
        s = float(want)
        design_px = (round(design_dp[0] * s), round(design_dp[1] * s))
        cells = []
        for size in _sizes(w, h, sp is not None, sp, stretch, design_px):
            cells.append((size, _cell(layers, sp, stretch, size, None), _cell(layers, sp, stretch, size, bg_rgb)))
        label = f"{pname}   {design_dp[0]:g} x {design_dp[1]:g} dp   @{want}x {design_px[0]}x{design_px[1]} px"
        if [round(v, 2) for v in design_dp] != [round(v, 2) for v in size_dp]:
            label += f"   (texture {size_dp[0]:g} x {size_dp[1]:g} dp, {w}x{h} px)"
        sub = "slice_px " + (str(sp) if sp is not None else "none (drawn whole)")
        if len(order) > 1:
            sub += "   outputs " + " + ".join(order)
        if piece.get("mode") == "shade":
            sub += "   mode shade"
        if stretch != ["stretch", "stretch"]:
            sub += f"   stretch {stretch[0]}/{stretch[1]}"
        st = status.get(pname)
        reasons = _reason_lines(st) if st else []
        bw = sum(c[1].shape[1] for c in cells) + GAP * (len(cells) - 1)
        tw = max([_text_w(font, label), _text_w(small, sub)] + [_text_w(small, r) for r in reasons])
        top = 40 + 15 * len(reasons)
        bh = top + max(c[1].shape[0] for c in cells) * 2 + GAP
        blocks.append({"label": label, "sub": sub, "cells": cells, "w": max(bw, tw), "h": bh, "top": top,
                       "reasons": reasons, "bad": bool(st)})
    if not blocks:
        raise NinekitError("nothing to preview")
    # shelf packing
    x, y, shelf_h, placed, sheet_w = MARGIN, MARGIN, 0, [], 0
    for b in blocks:
        if x > MARGIN and x + b["w"] > MAX_W:
            x, y, shelf_h = MARGIN, y + shelf_h + 2 * GAP, 0
        placed.append((x, y, b))
        x += b["w"] + 3 * GAP
        shelf_h = max(shelf_h, b["h"])
        sheet_w = max(sheet_w, x)
    sheet_h = y + shelf_h + MARGIN
    sheet = Image.new("RGB", (sheet_w - 3 * GAP + MARGIN, sheet_h), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    for x, y, b in placed:
        draw.text((x, y), b["label"], fill=FAIL_RGB if b["bad"] else (20, 20, 24), font=font)
        draw.text((x, y + 19), b["sub"], fill=(90, 90, 98), font=small)
        for i, line in enumerate(b["reasons"]):
            draw.text((x, y + 37 + 15 * i), line, fill=FAIL_RGB, font=small)
        cx = x
        row_h = max(c[1].shape[0] for c in b["cells"])
        top = b["top"]
        for size, on_check, on_bg in b["cells"]:
            sheet.paste(Image.fromarray(on_check, "RGB"), (cx, y + top))
            sheet.paste(Image.fromarray(on_bg, "RGB"), (cx, y + top + row_h + GAP))
            cx += on_check.shape[1] + GAP
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)
    return out


def _text_w(font, text: str) -> int:
    try:
        return int(font.getlength(text)) + 4
    except AttributeError:
        return len(text) * 7


def preview(target, out_path=None, bg: str = "#3B4252", scale=None, theme=None) -> Path:
    """A sheet for a spec (built into a temporary folder) or a manifest; returns the sheet's path."""
    p = Path(target)
    if p.suffix.lower() in (".yaml", ".yml"):
        from ninekit.render import build
        from ninekit.spec import load_spec

        spec = load_spec(p, theme)
        out = Path(out_path) if out_path else spec.out / f"{spec.name}.preview.png"
        with tempfile.TemporaryDirectory(prefix="ninekit-preview-") as tmp:
            res = build(p, theme=theme, out=tmp)
            return render_sheet(Path(tmp) / "ninekit.json", out, bg, scale, res.problems, res.warnings)
    if theme is not None:
        raise NinekitError("--theme applies to a SPEC; this is a manifest")
    mpath = p / "ninekit.json" if p.is_dir() else p
    if out_path is None:
        out_path = mpath.parent / f"{load_manifest(mpath)['name']}.preview.png"
    return render_sheet(mpath, out_path, bg, scale)
