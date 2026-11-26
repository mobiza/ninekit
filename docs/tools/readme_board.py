"""Layout helpers for docs/tools/make_readme_images.py: build the example specs once, then place their sprites on a
canvas and label them.

Every sprite comes from a fresh `ninekit build` and is drawn the way a runtime draws it (ninekit's own 9-slice
resampler; a pressed frame/face piece sinks its face by 0.92 toward the centre of its logical box). This module only
positions pieces and draws text, never UI art.

Fonts: macOS system fonts are used when present (Avenir Next, SF Pro Rounded, SF Mono, Avenir Next Condensed,
DIN Alternate, Iowan Old Style, Luminari from /System/Library/Fonts). Nothing is bundled or downloaded; on other
systems every role falls back to Pillow's built-in scalable font, so the script still runs (with plainer type).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:          # always draw with this checkout's ninekit
    sys.path.insert(0, str(ROOT / "src"))

from ninekit.draw import PRESS, draw_stack, stack_of  # noqa: E402
from ninekit.manifest import load_manifest  # noqa: E402
from ninekit.ninepatch import unpremultiply  # noqa: E402
from ninekit.render import build  # noqa: E402

S = 2                                          # image px per dp: every README image is drawn at 2x

_SYS = Path("/System/Library/Fonts")
_SUP = _SYS / "Supplemental"
# role -> (file, face index in a .ttc, variation name of a variable font)
FONTS = {
    "sans": (_SYS / "Avenir Next.ttc", 7, None),
    "sans-medium": (_SYS / "Avenir Next.ttc", 5, None),
    "sans-demi": (_SYS / "Avenir Next.ttc", 2, None),
    "sans-bold": (_SYS / "Avenir Next.ttc", 0, None),
    "sans-heavy": (_SYS / "Avenir Next.ttc", 8, None),
    "round": (_SYS / "SFNSRounded.ttf", 0, "Semibold"),
    "round-bold": (_SYS / "SFNSRounded.ttf", 0, "Bold"),
    "round-heavy": (_SYS / "SFNSRounded.ttf", 0, "Heavy"),
    "cond": (_SYS / "Avenir Next Condensed.ttc", 5, None),
    "cond-demi": (_SYS / "Avenir Next Condensed.ttc", 2, None),
    "cond-bold": (_SYS / "Avenir Next Condensed.ttc", 0, None),
    "din": (_SUP / "DIN Alternate Bold.ttf", 0, None),
    "mono": (_SYS / "SFNSMono.ttf", 0, "Medium"),
    "mono-bold": (_SYS / "SFNSMono.ttf", 0, "Bold"),
    "serif": (_SUP / "Iowan Old Style.ttc", 0, None),
    "serif-bold": (_SUP / "Iowan Old Style.ttc", 1, None),
    "serif-black": (_SUP / "Iowan Old Style.ttc", 4, None),
    "serif-italic": (_SUP / "Iowan Old Style.ttc", 2, None),
    "fantasy": (_SUP / "Luminari.ttf", 0, None),
}
_font_cache: dict = {}


def font(role: str, size_px: int) -> ImageFont.FreeTypeFont:
    key = (role, size_px)
    if key not in _font_cache:
        path, index, var = FONTS[role]
        try:
            f = ImageFont.truetype(str(path), size_px, index=index)
            if var:
                f.set_variation_by_name(var)
        except (OSError, ValueError):
            f = ImageFont.load_default(size=size_px)        # Pillow >= 10.1: a scalable fallback
        _font_cache[key] = f
    return _font_cache[key]


def hex_rgb(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in range(0, len(c), 2))


# --------------------------------------------------------------------------------------------- building the sets
SETS = {
    "gum": ROOT / "examples/gumdrop/buttons.yaml",
    "score": ROOT / "examples/gumdrop/scoreboard.yaml",
    "basics": ROOT / "examples/basics/basics.yaml",
    "neon": ROOT / "examples/neon/neon.yaml",
    "wood": ROOT / "examples/wood/wood.yaml",
    "quick": ROOT / "docs/tools/quick_piece.yaml",
    "capsule": ROOT / "examples/recreate/capsule.yaml",
}


class Kit:
    """Every example spec built once into a temporary folder; pieces are addressed as "set:piece"."""

    def __init__(self, sets: dict | None = None):
        self._tmp = tempfile.TemporaryDirectory(prefix="ninekit-readme-")
        self.sets = {}
        for key, spec in (sets or SETS).items():
            res = build(spec, out=Path(self._tmp.name) / key)
            self.sets[key] = (res.manifest_path, load_manifest(res.manifest_path))

    def add(self, key: str, spec, scales: list | None = None) -> None:
        """Builds one more spec (a path, or a dict written to a temporary YAML file) as set [key]."""
        if isinstance(spec, dict):
            import yaml
            path = Path(self._tmp.name) / f"{key}.yaml"
            path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
            spec = path
        res = build(spec, out=Path(self._tmp.name) / key, scales=scales)
        self.sets[key] = (res.manifest_path, load_manifest(res.manifest_path))

    def close(self) -> None:
        self._tmp.cleanup()

    def piece(self, ref: str) -> tuple[Path, dict, str]:
        key, name = ref.split(":", 1)
        mpath, m = self.sets[key]
        return mpath, m["pieces"][name], name

    def design_size(self, ref: str) -> tuple[float, float]:
        _, p, _ = self.piece(ref)
        return tuple(p.get("design_size") or p["size"])

    def draw(self, ref: str, w: float | None = None, h: float | None = None, pressed: bool = False,
             s: int = S, outputs: list | None = None) -> Image.Image:
        """The piece drawn as a runtime draws it at w x h dp (default: its design size), s px per dp."""
        mpath, p, name = self.piece(ref)
        dw, dh = p.get("design_size") or p["size"]
        size = (round((w or dw) * s), round((h or dh) * s))
        acc = draw_stack(mpath, p, stack_of(p, name, outputs), str(s), size, pressed)
        return Image.fromarray(unpremultiply(acc), "RGBA")

    def file(self, ref: str, output: str, s: int = S) -> Image.Image:
        """One output's PNG exactly as built."""
        mpath, p, _ = self.piece(ref)
        e = p["outputs"][output][str(s)]
        with Image.open(Path(mpath).parent / e["file"]) as im:
            return im.convert("RGBA")

    def slices(self, ref: str, s: int = S) -> list | None:
        _, p, _ = self.piece(ref)
        first = p["outputs"][next(iter(p["outputs"]))][str(s)]
        return first.get("slice_px")


# --------------------------------------------------------------------------------------------- the canvas
class Board:
    """An RGBA canvas measured in dp (S px per dp) to place sprites and labels on."""

    def __init__(self, kit: Kit, w: float, h: float, bg="#000000", s: int = S, dither: bool = False):
        self.kit, self.w, self.h, self.s = kit, w, h, s
        W, H = round(w * s), round(h * s)
        if isinstance(bg, Image.Image):
            self.img = bg.convert("RGBA").resize((W, H))
        elif isinstance(bg, (tuple, list)):          # (top, bottom): a vertical gradient
            top, bot = (np.array(hex_rgb(c), dtype=np.float64) for c in bg)
            t = np.linspace(0.0, 1.0, H)[:, None, None]
            rgb = np.broadcast_to(top + (bot - top) * t, (H, W, 3))
            if dither:          # a low-discrepancy (R2) pattern breaks up 8-bit banding in long, dark gradients
                yy, xx = np.indices((H, W))
                rgb = rgb + ((xx * 0.7548776662 + yy * 0.5698402910) % 1.0 - 0.5)[..., None] * 0.9
            rgb = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
            self.img = Image.fromarray(np.dstack([rgb, np.full((H, W), 255, np.uint8)]), "RGBA")
        else:
            self.img = Image.new("RGBA", (W, H), hex_rgb(bg) + (255,))
        self.draw = ImageDraw.Draw(self.img)

    # ----------------------------------------------------------------- sprites
    def piece(self, ref: str, x: float, y: float, w: float | None = None, h: float | None = None,
              pressed: bool = False, opacity: float = 1.0) -> tuple[float, float, float, float]:
        """Draws the piece at (x, y) dp, w x h dp; returns its content box (x0, y0, x1, y1) in dp."""
        im = self.kit.draw(ref, w, h, pressed, self.s)
        if opacity < 1.0:
            a = np.asarray(im).copy()
            a[..., 3] = (a[..., 3] * opacity + 0.5).astype(np.uint8)
            im = Image.fromarray(a, "RGBA")
        self.img.alpha_composite(im, (round(x * self.s), round(y * self.s)))
        return self.content_box(ref, x, y, w, h)

    def paste(self, im: Image.Image, x: float, y: float) -> None:
        self.img.alpha_composite(im.convert("RGBA"), (round(x * self.s), round(y * self.s)))

    def content_box(self, ref: str, x: float, y: float, w=None, h=None) -> tuple[float, float, float, float]:
        _, p, _ = self.kit.piece(ref)
        dw, dh = p.get("design_size") or p["size"]
        w, h = w or dw, h or dh
        c = p.get("content") or (0, 0, 0, 0)
        return x + c[0], y + c[1], x + w - c[2], y + h - c[3]

    def logical_centre(self, ref: str, x: float, y: float, w=None, h=None) -> tuple[float, float]:
        _, p, _ = self.kit.piece(ref)
        dw, dh = p.get("design_size") or p["size"]
        w, h = w or dw, h or dh
        o = p.get("overhang") or (0, 0, 0, 0)
        return x + (o[0] + w - o[2]) / 2, y + (o[1] + h - o[3]) / 2

    def label(self, ref: str, text: str, x: float, y: float, w=None, h=None, pressed: bool = False,
              size: float = 16, role: str = "sans-bold", dy: float = 0.0, **kw) -> None:
        """Text centred in the piece's content box; pressed, it sinks with the face (PRESS toward the centre)."""
        x0, y0, x1, y1 = self.content_box(ref, x, y, w, h)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + dy
        k = 1.0
        if pressed:
            lx, ly = self.logical_centre(ref, x, y, w, h)
            cx, cy, k = lx + (cx - lx) * PRESS, ly + (cy - ly) * PRESS, PRESS
            for key in ("stroke_w", "shadow_dy", "tracking"):
                if key in kw and kw[key]:
                    kw[key] = kw[key] * PRESS
        self.text(text, cx, cy, size * k, role=role, anchor="mc", **kw)

    # ----------------------------------------------------------------- text
    def text(self, text: str, x: float, y: float, size: float, fill="#FFFFFF", role: str = "sans",
             anchor: str = "lc", stroke=None, stroke_w: float = 0.0, shadow=None, shadow_dy: float = 0.0,
             tracking: float = 0.0, glow=None, glow_r: float = 3.0, glow_a: float = 0.8, opacity: float = 1.0) -> float:
        """Draws [text] with its anchor at (x, y) dp. Anchors: l/m/r horizontally; c = centred on the cap height,
        s = baseline, t = cap top. Returns the advance width in dp."""
        s = self.s
        f = font(role, max(1, round(size * s)))
        cap = -f.getbbox("H", anchor="ls")[1]
        width = self._advance(text, f, tracking * s)
        h_al, v_al = anchor[0], anchor[1]
        bx = x * s - {"l": 0, "m": width / 2, "r": width}[h_al]
        by = y * s + {"c": cap / 2, "s": 0, "t": cap}[v_al]
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        sw = round(stroke_w * s)

        def put(dx, dy, colour, with_stroke):
            self._draw_run(d, text, f, bx + dx, by + dy, tracking * s, colour,
                           stroke if with_stroke else None, sw if with_stroke else 0)

        if glow:
            g = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
            self._draw_run(ImageDraw.Draw(g), text, f, bx, by, tracking * s, glow, None, 0)
            g = g.filter(ImageFilter.GaussianBlur(glow_r * s))
            ga = np.asarray(g).astype(np.float64)
            ga[..., 3] = np.clip(ga[..., 3] * glow_a * 1.6, 0, 255)
            self.img.alpha_composite(Image.fromarray(ga.astype(np.uint8), "RGBA"))
        if shadow:
            put(0, shadow_dy * s, shadow, True)
        put(0, 0, fill, True)
        if opacity < 1.0:
            a = np.asarray(layer).copy()
            a[..., 3] = (a[..., 3] * opacity + 0.5).astype(np.uint8)
            layer = Image.fromarray(a, "RGBA")
        self.img.alpha_composite(layer)
        return width / s

    def measure(self, text: str, size: float, role: str = "sans", tracking: float = 0.0) -> float:
        f = font(role, max(1, round(size * self.s)))
        return self._advance(text, f, tracking * self.s) / self.s

    @staticmethod
    def _advance(text: str, f, tr: float) -> float:
        if not tr:
            return f.getlength(text)
        return sum(f.getlength(c) for c in text) + tr * (len(text) - 1)

    @staticmethod
    def _draw_run(d, text, f, x, y, tr, fill, stroke, sw):
        if not tr:
            d.text((x, y), text, font=f, fill=fill, anchor="ls", stroke_width=sw, stroke_fill=stroke)
            return
        for c in text:
            d.text((x, y), c, font=f, fill=fill, anchor="ls", stroke_width=sw, stroke_fill=stroke)
            x += f.getlength(c) + tr

    # ----------------------------------------------------------------- plain shapes for diagrams (not UI art)
    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width: float = 1.0, r: float = 0.0) -> None:
        s = self.s
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle([x0 * s, y0 * s, x1 * s - 1, y1 * s - 1], radius=r * s, fill=fill,
                                                outline=outline, width=max(1, round(width * s)) if outline else 0)
        self.img.alpha_composite(layer)

    def line(self, pts, fill, width: float = 1.0, dash: float = 0.0) -> None:
        s = self.s
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        pts = [(px * s, py * s) for px, py in pts]
        if not dash:
            d.line(pts, fill=fill, width=max(1, round(width * s)))
        else:
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                n = max(1, int(np.hypot(bx - ax, by - ay) / (dash * s)))
                for i in range(0, n, 2):
                    t0, t1 = i / n, min(1.0, (i + 1) / n)
                    d.line([(ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)],
                           fill=fill, width=max(1, round(width * s)))
        self.img.alpha_composite(layer)

    def hatch(self, x0, y0, x1, y1, fill, spacing: float = 4.0, width: float = 0.75) -> None:
        """Diagonal hatching clipped to a rectangle (marks a region in a diagram)."""
        s = self.s
        X0, Y0, X1, Y1 = (round(v * s) for v in (x0, y0, x1, y1))
        layer = Image.new("RGBA", (X1 - X0, Y1 - Y0), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        h = Y1 - Y0
        step = spacing * s
        k = -h
        while k < X1 - X0:
            d.line([(k, h), (k + h, 0)], fill=fill, width=max(1, round(width * s)))
            k += step
        self.img.alpha_composite(layer, (X0, Y0))

    def shadow(self, x0, y0, x1, y1, r: float, blur: float, colour=(0, 0, 0), alpha: float = 0.5, dy: float = 0.0):
        """A soft drop shadow under a rounded rectangle (behind a screen card)."""
        s = self.s
        m = Image.new("L", self.img.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([x0 * s, (y0 + dy) * s, x1 * s, (y1 + dy) * s], radius=r * s,
                                            fill=round(255 * alpha))
        m = m.filter(ImageFilter.GaussianBlur(blur * s))
        layer = Image.new("RGBA", self.img.size, tuple(colour) + (0,))
        layer.putalpha(m)
        self.img.alpha_composite(layer)

    def save(self, path: Path, budget_kb: int = 600) -> Path:
        return save_png(self.img, path, budget_kb)


def save_png(img: Image.Image, path: Path, budget_kb: int = 600) -> Path:
    """Saves an opaque PNG (optimize=True). Over [budget_kb], textured areas (noise, grain: a local contrast over
    6/255) are stored with 7 bits per channel, an error of at most 1/255 where nothing can show it; flat areas and
    gradients keep all 8 bits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = img.convert("RGB")
    img.save(path, optimize=True)
    if path.stat().st_size <= budget_kb * 1024:
        return path
    a = np.asarray(img).astype(np.int16)
    g = Image.fromarray(a.mean(axis=2).astype(np.uint8))
    hi = np.asarray(g.filter(ImageFilter.MaxFilter(5))).astype(np.int16)
    lo = np.asarray(g.filter(ImageFilter.MinFilter(5))).astype(np.int16)
    tex = (hi - lo) > 6
    a[tex] = np.minimum((a[tex] + 1) // 2 * 2, 254)
    Image.fromarray(a.astype(np.uint8), "RGB").save(path, optimize=True)
    return path
