"""Draws the Gumdrop showcase (docs/images/gumdrop_preview.png): the scoreboard and button sets laid out as a small
mock screen. Every sprite is a fresh `ninekit build` of the two specs, drawn the way a runtime draws it (ninekit's
9-slice resampler, pressed faces scaled 0.92 toward the body); the script only places the pieces and the labels.

    PYTHONPATH=src python3 examples/gumdrop/showcase.py [OUT.png]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ninekit.blocks.casual_button import PRESETS
from ninekit.draw import PRESS, draw_stack, stack_of
from ninekit.manifest import load_manifest
from ninekit.ninepatch import unpremultiply
from ninekit.render import build

HERE = Path(__file__).resolve().parent
S = 2                           # texture px per dp of the image (the specs' @2x files)
W, H = 760, 432                 # the image in dp


class Board:
    def __init__(self, sets: dict):
        self.sets = sets            # name -> (manifest path, manifest)
        bg = np.linspace(0, 1, H * S)[:, None, None]
        top, bot = np.array([0xF3, 0xEF, 0xFB]), np.array([0xD9, 0xCF, 0xF1])
        rgb = (top + (bot - top) * bg).repeat(W * S, axis=1)
        self.img = Image.fromarray(np.dstack([rgb, np.full(rgb.shape[:2], 255)]).astype(np.uint8), "RGBA")
        self.draw = ImageDraw.Draw(self.img)

    def piece(self, name: str, x: float, y: float, w: float | None = None, h: float | None = None,
              pressed: bool = False) -> None:
        for mpath, m in self.sets.values():
            if name in m["pieces"]:
                break
        else:
            raise KeyError(name)
        p = m["pieces"][name]
        dw, dh = p.get("design_size") or p["size"]
        size = (round((w or dw) * S), round((h or dh) * S))
        acc = draw_stack(mpath, p, stack_of(p, name), str(S), size, pressed)
        self.img.alpha_composite(Image.fromarray(unpremultiply(acc), "RGBA"), (round(x * S), round(y * S)))

    def text(self, s: str, cx: float, cy: float, size: float, fill: str, stroke: str | None = None,
             width: float = 2.0, anchor: str = "mm") -> None:
        font = ImageFont.load_default(size=round(size * S))
        self.draw.text((cx * S, cy * S), s, font=font, fill=fill, anchor=anchor,
                       stroke_width=round(width * S) if stroke else 0, stroke_fill=stroke)

    def button(self, style: str, label: str, x: float, y: float, w: float = 172, pressed: bool = False) -> None:
        self.piece("btn_" + style, x, y, w, 62, pressed)
        # the label sits on the face centre (content [12, 8, 12, 17] of the 62 dp canvas: 26.5 dp down); pressed, it
        # scales with the face toward the logical box's centre (62 - 3 dp of shadow)
        cy, k = 26.5, 1.0
        if pressed:
            cy, k = 29.5 + (26.5 - 29.5) * PRESS, PRESS
        if style == "cloud":
            self.text(label, x + w / 2, y + cy, 21 * k, "#4A5468")
        elif style == "gray":
            self.text(label, x + w / 2, y + cy, 21 * k, "#F1F2F4", PRESETS["gray"]["text_outline"], 1.6 * k)
        else:
            self.text(label, x + w / 2, y + cy, 21 * k, "#FFFFFF", PRESETS[style]["text_outline"], 2.0 * k)


def main(out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="gumdrop-") as tmp:
        sets = {}
        for spec in ("buttons", "scoreboard"):
            res = build(HERE / f"{spec}.yaml", out=Path(tmp) / spec)
            sets[spec] = (res.manifest_path, load_manifest(res.manifest_path))
        b = Board(sets)

        # --- the scoreboard: a panel holding a tab strip with three pills and five rows
        b.piece("panel", 20, 20, 340, 398)
        b.piece("tab_strip", 34, 34, 312, 41)
        for i, (label, piece) in enumerate((("Friends", "pill_idle"), ("World", "pill_sel"), ("Team", "pill_idle"))):
            x = 38 + i * 102
            b.piece(piece, x, 38, 100, 32)
            sel = piece == "pill_sel"
            b.text(label, x + 50, 38 + 13.5, 15, "#FFFFFF" if sel else "#3B2A78", "#7A1146" if sel else None, 1.4)
        rows = (("Maple", "8 420", "medal_1"), ("Juniper", "7 915", "medal_2"), ("Clover", "7 310", "medal_3"),
                ("You", "6 880", None), ("Basil", "6 205", None))
        for i, (name, score, medal) in enumerate(rows):
            y = 87 + i * 64
            me = name == "You"
            b.piece("card_me" if me else "card", 34, y, 312, 60)
            if medal:
                b.piece(medal, 46, y + 9)
            else:
                b.text(str(i + 1), 63, y + 27, 17, "#2E7D5B" if me else "#5B48A0")
            b.text(name, 92, y + 27, 17, "#1F5C43" if me else "#33265F", anchor="lm")
            b.piece("metric", 250, y + 15, 82, 26)
            b.text(score, 291, y + 27.5, 14, "#3B2A78")

        # --- the buttons: every preset, round ones, a pressed one
        b.text("Gumdrop", 384, 30, 30, "#3B2A78", anchor="lm")
        b.text("ninekit sample concept", 386, 54, 13, "#6A5AA0", anchor="lm")
        grid = (("berry", "Play"), ("mint", "Claim"), ("sky", "Invite"), ("sun", "Shop"),
                ("grape", "Events"), ("coal", "Settings"), ("cloud", "Sign in"), ("gray", "Locked"))
        for i, (style, label) in enumerate(grid):
            b.button(style, label, 384 + (i % 2) * 182, 72 + (i // 2) * 68)
        # round ones (drawn whole); the last is held down: its face and glyph sink toward the body's centre
        for i, (style, glyph) in enumerate((("berry", "+"), ("mint", "?"), ("sky", "i"), ("sun", "!"), ("grape", "x"))):
            x, pressed = 384 + i * 72, i == 4
            b.piece("btnc_" + style, x, 348, pressed=pressed)
            cy, k = (29.5 + (27.5 - 29.5) * PRESS, PRESS) if pressed else (27.5, 1.0)
            b.text(glyph, x + 31, 348 + cy, 26 * k, "#FFFFFF", PRESETS[style]["text_outline"], 2.0 * k)
        out.parent.mkdir(parents=True, exist_ok=True)
        b.img.convert("RGB").save(out, optimize=True)
        print(f"wrote {out}  {b.img.width}x{b.img.height} px")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "docs" / "images" / "gumdrop_preview.png")
