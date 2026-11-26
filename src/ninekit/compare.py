"""`ninekit compare` (DESIGN 4): a built piece next to a reference crop, with a difference heatmap and metrics.

The piece's stacked outputs (the largest scale's files) are drawn as a 9-slice with ninekit's own resampler at
exactly the crop's pixel size (via the texture density when the reference has another one, see `ref_scale`),
both sides are composited on one background, and the image `reference | ninekit | |difference|` is written.
Metrics are on 8-bit RGB: mean and max absolute difference, PSNR, and the share of pixels whose largest channel
difference is over 16/255.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ninekit import NinekitError
from ninekit.canvas import hexc
from ninekit.draw import built_manifest, draw_stack, pick_scale, piece_of, stack_of
from ninekit.manifest import load_manifest

OVER = 16           # /255: a pixel "differs" when its largest channel difference is over this
HEAT_GAIN = 4       # the heatmap is |difference| x 4 (64/255 and more is white)
GAP = 4
HEAT_STOPS = [(0.0, (0, 0, 0)), (0.33, (170, 20, 20)), (0.66, (255, 190, 0)), (1.0, (255, 255, 255))]


def parse_crop(text: str) -> tuple[int, int, int, int]:
    """"x,y,w,h" (reference px) -> a tuple; w, h > 0."""
    try:
        vals = [int(round(float(v))) for v in text.replace(" ", "").split(",")]
    except ValueError:
        raise NinekitError(f"--crop {text!r}: expected x,y,w,h in px") from None
    if len(vals) != 4 or vals[2] <= 0 or vals[3] <= 0 or vals[0] < 0 or vals[1] < 0:
        raise NinekitError(f"--crop {text!r}: expected x,y,w,h in px with w, h > 0")
    return tuple(vals)


def _resize_premul(p: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """A premultiplied float RGBA image resampled (Lanczos) to [size] (W, H)."""
    W, H = size
    if p.shape[1] == W and p.shape[0] == H:
        return p
    chans = [np.asarray(Image.fromarray(p[..., c].astype(np.float32), "F").resize((W, H), Image.LANCZOS))
             for c in range(4)]
    out = np.stack(chans, axis=2).astype(np.float64)
    out[..., 3] = np.clip(out[..., 3], 0.0, 1.0)
    out[..., :3] = np.clip(out[..., :3], 0.0, out[..., 3:4])
    return out


def _heat(d: np.ndarray) -> np.ndarray:
    """|difference| (0..255, per pixel) -> RGB uint8 along HEAT_STOPS."""
    t = np.clip(d.astype(np.float64) * HEAT_GAIN / 255.0, 0.0, 1.0)
    ts = [s[0] for s in HEAT_STOPS]
    out = np.empty(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, ts, [s[1][c] for s in HEAT_STOPS])
    return (out + 0.5).astype(np.uint8)


def compare(target, piece_name: str, ref, out=None, crop=None, outputs=None, bg: str = "#3B4252", theme=None,
            ref_scale: float | None = None, zoom: int | None = None) -> dict:
    """Writes the comparison image and returns the metrics (see the module doc). [out] defaults to
    `<spec out>/compare_<piece>.png` for a SPEC, `compare_<piece>.png` next to a manifest (never the working
    folder)."""
    with built_manifest(target, theme, piece_name) as (mpath, default_dir):
        if out is None:
            out = Path(default_dir) / f"compare_{piece_name}.png"
        return _compare(mpath, piece_name, ref, out, crop, outputs, bg, ref_scale, zoom)


def _compare(mpath: Path, piece_name: str, ref, out, crop, outputs, bg, ref_scale, zoom) -> dict:
    piece = piece_of(load_manifest(mpath), piece_name)
    outputs = stack_of(piece, piece_name, outputs)
    scale_k = pick_scale(piece, outputs)
    smax = float(scale_k)
    rpath = Path(ref)
    try:
        with Image.open(rpath) as im:
            ref_img = im.convert("RGBA")
    except (OSError, ValueError) as e:
        raise NinekitError(f"cannot read reference {rpath}: {e}") from None
    if crop is None:
        crop = (0, 0, ref_img.width, ref_img.height)
    x, y, W, H = crop
    if x + W > ref_img.width or y + H > ref_img.height:
        raise NinekitError(f"--crop {x},{y},{W},{H} reaches outside the {ref_img.width}x{ref_img.height} reference")
    rs = smax if ref_scale is None else float(ref_scale)
    if rs <= 0:
        raise NinekitError("--ref-scale must be > 0")
    # texels of the largest scale covering the crop (corners stay 1:1 in texture px), then resampled to the crop
    RW, RH = max(1, round(W * smax / rs)), max(1, round(H * smax / rs))
    ours_p = _resize_premul(draw_stack(mpath, piece, outputs, scale_k, (RW, RH)), (W, H))
    bgc = np.asarray(hexc(bg), dtype=np.float64)
    ours = ours_p[..., :3] + bgc * (1.0 - ours_p[..., 3:4])
    refa = np.asarray(ref_img.crop((x, y, x + W, y + H)), dtype=np.float64) / 255.0
    refc = refa[..., :3] * refa[..., 3:4] + bgc * (1.0 - refa[..., 3:4])
    o8 = (np.clip(ours, 0, 1) * 255.0 + 0.5).astype(np.int16)
    r8 = (np.clip(refc, 0, 1) * 255.0 + 0.5).astype(np.int16)
    diff = np.abs(o8 - r8)
    mse = float((diff.astype(np.float64) ** 2).mean())
    per_px = diff.max(axis=2)
    metrics = {
        "mean_abs": round(float(diff.mean()), 3),
        "max_abs": int(diff.max()),
        "psnr": None if mse == 0 else round(10.0 * math.log10(255.0 ** 2 / mse), 2),
        "over_16_pct": round(100.0 * float((per_px > OVER).mean()), 3),
    }
    _write_sheet(Path(out), r8.astype(np.uint8), o8.astype(np.uint8), _heat(per_px), zoom)
    return {"piece": piece_name, "scale": scale_k, "outputs": outputs, "size": [W, H], "render_px": [RW, RH],
            "crop": [x, y, W, H], "ref": str(rpath), "ref_scale": rs, "out": str(Path(out)), **metrics}


def _write_sheet(out: Path, ref: np.ndarray, ours: np.ndarray, heat: np.ndarray, zoom: int | None) -> None:
    H, W = ref.shape[:2]
    if zoom is None:
        zoom = max(1, min(8, 480 // max(W, H)))
    if zoom < 1:
        raise NinekitError("--zoom must be >= 1")
    panels = [Image.fromarray(a, "RGB").resize((W * zoom, H * zoom), Image.NEAREST) for a in (ref, ours, heat)]
    pw, ph = panels[0].size
    head = 18
    sheet = Image.new("RGB", (3 * pw + 2 * GAP, ph + head), (236, 236, 236))
    draw = ImageDraw.Draw(sheet)
    from ninekit.preview import _font

    font = _font(12)
    for i, (panel, label) in enumerate(zip(panels, ("reference", "ninekit", f"|difference| x{HEAT_GAIN}"))):
        px = i * (pw + GAP)
        sheet.paste(panel, (px, head))
        draw.text((px + 2, 2), label, fill=(20, 20, 24), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)
