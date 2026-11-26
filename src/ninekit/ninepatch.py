"""ninekit's own 9-slice resampler (preview, losslessness checks).

Each of the three regions per axis is resampled on its own (bilinear, clamped inside the region, like a
9-slice drawn as separate quads), in premultiplied alpha. The corners map 1:1 when the target is at least
the sum of the slices; otherwise they shrink proportionally. A `tile` middle repeats in whole tiles like the
runtimes (Godot TILE_FIT, CSS `border-image-repeat: round`): the count is round(length / tile), at least 1,
and each tile is scaled to fit the length exactly, so there is never a cut last tile.
"""
from __future__ import annotations

import numpy as np


def _axis(n_src: int, a: int, b: int, n_dst: int, mode: str, sliced: bool):
    """Per target texel: source indices (i0, i1) and the blend weight along one axis."""
    i0 = np.zeros(n_dst, dtype=np.int64)
    i1 = np.zeros(n_dst, dtype=np.int64)
    f = np.zeros(n_dst)
    if not sliced:
        segs = [(0, n_src, 0, n_dst, "stretch")]
    else:
        if n_dst >= a + b:
            A, B = a, b
        else:
            A = round(n_dst * a / (a + b)) if a + b else 0
            B = n_dst - A
        segs = [(0, a, 0, A, "stretch"), (a, n_src - b, A, n_dst - B, mode), (n_src - b, n_src, n_dst - B, n_dst,
                                                                              "stretch")]
    for sa, sb, da, db, m in segs:
        if db <= da:
            continue
        if sb <= sa:
            raise ValueError(f"empty source region [{sa}, {sb}) for {db - da} target texels")
        x = np.arange(da, db) + 0.5 - da
        n = sb - sa
        if m == "tile":
            length = db - da
            k = max(1, round(length / n))            # whole tiles, fitted to the length
            if k * n != length:
                x = x * (k * n / length)
            t = sa + np.mod(x, n) - 0.5
            lo = np.floor(t)
            fr = t - lo
            lo = lo.astype(np.int64)
            j0 = np.where(lo < sa, sb - 1, lo)          # wrap within the region
            j1 = np.where(lo + 1 >= sb, sa, lo + 1)
        else:
            t = sa + x * (n / (db - da)) - 0.5
            t = np.clip(t, sa, sb - 1)
            lo = np.floor(t)
            fr = t - lo
            j0 = lo.astype(np.int64)
            j1 = np.minimum(j0 + 1, sb - 1)
        i0[da:db], i1[da:db], f[da:db] = j0, j1, fr
    return i0, i1, f


def premultiply(img: np.ndarray) -> np.ndarray:
    a = img[..., 3:4].astype(np.float64) / 255.0
    return np.concatenate([img[..., :3].astype(np.float64) / 255.0 * a, a], axis=2)


def unpremultiply(p: np.ndarray) -> np.ndarray:
    a = p[..., 3:4]
    rgb = np.where(a > 1e-9, p[..., :3] / np.where(a > 1e-9, a, 1.0), 0.0)
    out = np.concatenate([rgb, a], axis=2)
    return (np.clip(out, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def nine_slice_premul(img: np.ndarray, slice_px, size, stretch=("stretch", "stretch")) -> np.ndarray:
    """[img] (h, w, 4 uint8) drawn as a 9-slice at [size] (W, H) px: premultiplied float RGBA (H, W, 4)."""
    h, w = img.shape[:2]
    W, H = int(size[0]), int(size[1])
    sliced = slice_px is not None
    l, t, r, b = slice_px if sliced else (0, 0, 0, 0)
    xi0, xi1, fx = _axis(w, l, r, W, stretch[0], sliced)
    yi0, yi1, fy = _axis(h, t, b, H, stretch[1], sliced)
    p = premultiply(img)
    fx = fx[None, :, None]
    fy = fy[:, None, None]
    # a + (b - a) * f: exactly a when a == b, so identical middle columns give identical results whatever
    # their count (this is what makes compaction provably lossless)
    r0, r1 = p[yi0], p[yi1]
    top = r0[:, xi0] + (r0[:, xi1] - r0[:, xi0]) * fx
    bot = r1[:, xi0] + (r1[:, xi1] - r1[:, xi0]) * fx
    return top + (bot - top) * fy


def nine_slice(img: np.ndarray, slice_px, size, stretch=("stretch", "stretch")) -> np.ndarray:
    """[img] drawn as a 9-slice at [size] (W, H) px, as straight-alpha uint8 RGBA."""
    return unpremultiply(nine_slice_premul(img, slice_px, size, stretch))
