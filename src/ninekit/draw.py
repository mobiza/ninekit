"""Drawing a built piece the way a runtime draws it (DESIGN 4: `ninekit render`, `compare`, `preview`).

The piece's stacked outputs are drawn as 9-slices with ninekit's resampler (ninepatch.py) at any size; with
`pressed` the `face` output scales by PRESS toward the centre of the logical box (the canvas minus overhang)
while the frame stays, as the runtimes do.
"""
from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

from ninekit import NinekitError
from ninekit.manifest import load_manifest, scale_key
from ninekit.ninepatch import nine_slice_premul, unpremultiply

PRESS = 0.92


@contextmanager
def built_manifest(target, theme=None, only: str | None = None):
    """Yields (manifest path, default output folder) for a SPEC (built into a temporary folder; the folder is the
    spec's `out`) or a manifest / its folder (the manifest's folder)."""
    t = Path(target)
    if t.suffix.lower() in (".yaml", ".yml"):
        from ninekit.render import build
        from ninekit.spec import load_spec

        spec = load_spec(t, theme)
        names = {d.name for d in spec.piece_defs()}
        with tempfile.TemporaryDirectory(prefix="ninekit-draw-") as tmp:
            res = build(t, theme=theme, out=tmp, only=[only] if only in names else None)
            yield res.manifest_path, spec.out
        return
    if theme is not None:
        raise NinekitError("--theme applies to a SPEC; this is a manifest")
    mpath = t / "ninekit.json" if t.is_dir() else t
    yield mpath, mpath.parent


def piece_of(manifest: dict, name: str) -> dict:
    pieces = manifest["pieces"]
    if name not in pieces:
        raise NinekitError(f"unknown piece {name!r} (known: {', '.join(sorted(pieces))})")
    return pieces[name]


def stack_of(piece: dict, name: str, outputs: list | None = None) -> list:
    """The outputs to stack, bottom first: [outputs], or the piece's stack without a composite `main`."""
    stack = piece.get("stack") or list(piece["outputs"])
    if outputs is None:
        outputs = [o for o in stack if o != "main"] if len(stack) > 1 and "main" in stack else list(stack)
    missing = [o for o in outputs if o not in piece["outputs"]]
    if missing:
        raise NinekitError(f"piece {name}: no output(s) {', '.join(missing)} (it has {', '.join(stack)})")
    return list(outputs)


def pick_scale(piece: dict, outputs: list, scale=None) -> str:
    keys = sorted({k for o in outputs for k in piece["outputs"][o]}, key=float)
    if scale is None:
        return keys[-1]
    want = scale_key(scale)
    if want not in keys:
        raise NinekitError(f"--scale {want}: the piece has scales {', '.join(keys)}")
    return want


def stretch_of(piece: dict) -> list:
    st = piece.get("stretch") or ["stretch", "stretch"]
    return [st, st] if isinstance(st, str) else list(st)


def draw_stack(mpath: Path, piece: dict, outputs: list, scale_k: str, size: tuple[int, int],
               pressed: bool = False) -> np.ndarray:
    """The stacked outputs drawn as 9-slices at [size] (W, H) texels of scale [scale_k]: premultiplied float RGBA.
    With [pressed] the `face` output scales by PRESS toward the centre of the logical box."""
    W, H = size
    stretch = stretch_of(piece)
    acc = np.zeros((H, W, 4))
    s = float(scale_k)
    for o in outputs:
        e = piece["outputs"][o][scale_k]
        with Image.open(Path(mpath).parent / e["file"]) as im:
            img = np.asarray(im.convert("RGBA"))
        sp = e.get("slice_px")
        if sp is not None:
            l, t, r, b = sp
            h, w = img.shape[:2]
            if (l + r >= w and W > w) or (t + b >= h and H > h):
                raise NinekitError(f"{e['file']}: slice_px {sp} leaves no middle to stretch to {W}x{H}; "
                                   f"`ninekit verify` the piece first")
        p = nine_slice_premul(img, sp, (W, H), stretch)
        if pressed and o == "face":
            ov = [float(v) * s for v in (piece.get("overhang") or (0, 0, 0, 0))]
            cx, cy = (ov[0] + W - ov[2]) / 2.0, (ov[1] + H - ov[3]) / 2.0
            p = scale_about(p, cx, cy, PRESS)
        acc = p + acc * (1.0 - p[..., 3:4])
    return acc


def scale_about(p: np.ndarray, cx: float, cy: float, k: float) -> np.ndarray:
    """A premultiplied image scaled by [k] about (cx, cy) (texel coordinates), bilinear, transparent outside."""
    H, W = p.shape[:2]
    pad = np.zeros((H + 2, W + 2, 4))
    pad[1:-1, 1:-1] = p
    xs = cx + (np.arange(W) + 0.5 - cx) / k - 0.5 + 1.0
    ys = cy + (np.arange(H) + 0.5 - cy) / k - 0.5 + 1.0
    xs = np.clip(xs, 0.0, W + 1.0)
    ys = np.clip(ys, 0.0, H + 1.0)
    x0 = np.minimum(np.floor(xs).astype(np.int64), W)
    y0 = np.minimum(np.floor(ys).astype(np.int64), H)
    fx = (xs - x0)[None, :, None]
    fy = (ys - y0)[:, None, None]
    r0, r1 = pad[y0], pad[y0 + 1]
    top = r0[:, x0] + (r0[:, x0 + 1] - r0[:, x0]) * fx
    bot = r1[:, x0] + (r1[:, x0 + 1] - r1[:, x0]) * fx
    return top + (bot - top) * fy


def parse_size(text: str) -> tuple[float, float]:
    """"WxH" (dp) -> (w, h), both > 0."""
    try:
        w, h = (float(v) for v in text.lower().replace(" ", "").split("x"))
    except ValueError:
        raise NinekitError(f"--size {text!r}: expected WxH in dp, e.g. 200x56") from None
    if w <= 0 or h <= 0:
        raise NinekitError(f"--size {text!r}: width and height must be > 0")
    return w, h


def render_piece_at(target, piece_name: str, size_dp: tuple[float, float], out, outputs=None, scale=None,
                    pressed: bool = False, theme=None) -> dict:
    """`ninekit render`: the piece drawn at [size_dp] (dp) with transparency, written to [out] (PNG)."""
    with built_manifest(target, theme, piece_name) as (mpath, _):
        manifest = load_manifest(mpath)
        piece = piece_of(manifest, piece_name)
        outs = stack_of(piece, piece_name, outputs)
        if pressed and "face" not in outs:
            raise NinekitError(f"--pressed: piece {piece_name} has no `face` output among {', '.join(outs)} (the press "
                               f"scales the face of a frame/face piece)")
        sk = pick_scale(piece, outs, scale)
        s = float(sk)
        W, H = max(1, round(size_dp[0] * s)), max(1, round(size_dp[1] * s))
        notes = []
        e0 = piece["outputs"][outs[0]][sk]
        w0, h0 = e0["size_px"]
        for axis, mode, want, have in (("x", stretch_of(piece)[0], W, w0), ("y", stretch_of(piece)[1], H, h0)):
            if mode == "fixed" and want != have and e0.get("slice_px") is not None:
                notes.append(f"{axis} is fixed (meant to be used at its natural length, {have / s:g} dp): stretched "
                             f"to {want / s:g} dp anyway")
        img = unpremultiply(draw_stack(mpath, piece, outs, sk, (W, H), pressed))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img, "RGBA").save(out, optimize=True)
    return {"piece": piece_name, "size": [size_dp[0], size_dp[1]], "scale": sk, "size_px": [W, H],
            "outputs": outs, "pressed": pressed, "out": str(out), "notes": notes}
