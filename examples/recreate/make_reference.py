"""Draws reference.png, the stand-in "screenshot" this example recreates with ninekit: a small HUD capsule (the
background of a resource counter) painted with plain Pillow, the way an artist's export might look. It shares no code
with ninekit: rounded rectangles filled with vertical gradients at 4x supersampling, a blurred drop shadow, Lanczos
downsampling. 168 x 66 px, meant as a 3x asset (56 x 22 dp).

    python3 examples/recreate/make_reference.py      # rewrites examples/recreate/reference.png
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 4                          # supersampling
W, H = 168, 66                  # px
BODY = 60                       # the capsule's height; the soft shadow uses the rest


def gradient(top, bottom, y0, y1):
    """A full-canvas layer (supersampled) with a vertical gradient from row y0 to y1 (px), clamped outside."""
    col = Image.new("RGBA", (1, H * SS))
    for y in range(H * SS):
        t = min(1.0, max(0.0, (y / SS - y0) / (y1 - y0)))
        col.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return col.resize((W * SS, H * SS), Image.Resampling.NEAREST)


def capsule(x0, y0, x1, y1, r=None, blur=0.0):
    """A coverage mask: a rounded rectangle (px; r defaults to a full capsule)."""
    m = Image.new("L", (W * SS, H * SS), 0)
    r = (y1 - y0) / 2 if r is None else r
    ImageDraw.Draw(m).rounded_rectangle([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1], radius=r * SS, fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur * SS)) if blur else m


def paint(img, layer, mask, opacity=1.0):
    a = ImageChops.multiply(layer.getchannel("A"), mask)
    if opacity < 1:
        a = a.point(lambda v: round(v * opacity))
    layer = layer.copy()
    layer.putalpha(a)
    img.alpha_composite(layer)


def main(out: Path) -> None:
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    solid = lambda c: Image.new("RGBA", img.size, c)
    # a soft shadow 3 px below the body
    paint(img, solid((10, 28, 38, 255)), capsule(2, 3, W - 2, BODY + 3, blur=1.6), 0.45)
    # the rim: a dark teal capsule
    paint(img, solid((14, 59, 72, 255)), capsule(0, 0, W, BODY))
    # the lip: 7 px of darker teal showing under the face
    paint(img, gradient((25, 104, 124, 255), (17, 78, 95, 255), BODY - 16, BODY - 3), capsule(3, 3, W - 3, BODY - 3))
    # the face: a light-to-deep teal gradient
    paint(img, gradient((104, 214, 226, 255), (36, 146, 172, 255), 3, BODY - 10), capsule(3, 3, W - 3, BODY - 10))
    # a highlight band across the face's upper part, fading downwards, its ends inset from the caps
    paint(img, gradient((255, 255, 255, 170), (255, 255, 255, 20), 7, 24), capsule(14, 7, W - 14, 24, r=8.5))
    img = img.resize((W, H), Image.Resampling.LANCZOS)
    img.save(out, optimize=True)
    print(f"wrote {out}  {W}x{H} px")


if __name__ == "__main__":
    main(Path(__file__).resolve().parent / "reference.png")
