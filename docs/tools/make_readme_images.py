"""Regenerates every image the README shows, from sprites ninekit itself renders.

    python3 docs/tools/make_readme_images.py                 # all images into docs/images/
    python3 docs/tools/make_readme_images.py hero stretch    # only some of them
    python3 docs/tools/make_readme_images.py --list

The example specs (examples/gumdrop, basics, neon, wood, recreate) and docs/tools/quick_piece.yaml are built fresh into
a temporary folder; this script only lays the sprites out, draws labels and diagram guides, and writes the PNG / GIF.
Run it from a checkout (it imports ninekit from src/). Needs numpy and Pillow >= 10.1, like ninekit itself.

Fonts are macOS system fonts (see readme_board.FONTS); on other systems Pillow's built-in font is used instead.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readme_board import ROOT, S, Board, Kit, font, save_png  # noqa: E402

from ninekit.blocks.casual_button import PRESETS  # noqa: E402
from ninekit.compare import compare  # noqa: E402

IMAGES = ROOT / "docs" / "images"


# =============================================================================================== Gumdrop
GUM_INK = "#3B2A78"


def gum_button(b: Board, style: str, label: str, x, y, w=172.0, pressed=False, size=21.0):
    ref = "gum:btn_" + style
    b.piece(ref, x, y, w, None, pressed)
    if style == "cloud":
        b.label(ref, label, x, y, w, None, pressed, size, "round-heavy", fill="#4A5468")
    else:
        fill = "#F1F2F4" if style == "gray" else "#FFFFFF"
        b.label(ref, label, x, y, w, None, pressed, size, "round-heavy", fill=fill,
                stroke=PRESETS[style]["text_outline"], stroke_w=2.2 if style != "gray" else 1.6,
                shadow=PRESETS[style]["text_outline"], shadow_dy=1.6)


def gum_round(b: Board, style: str, glyph: str, x, y, pressed=False, size=26.0):
    ref = "gum:btnc_" + style
    b.piece(ref, x, y, pressed=pressed)
    b.label(ref, glyph, x, y, pressed=pressed, size=size, role="round-heavy", dy=0.5,
            stroke=PRESETS[style]["text_outline"], stroke_w=2.2, shadow=PRESETS[style]["text_outline"], shadow_dy=1.6)


def gum_badge(b: Board, n: str, x, y):
    b.piece("basics:badge", x, y)
    b.text(n, x + 14, y + 14.2, 14, "#FFFFFF", "round-heavy", "mc", stroke="#7E1A12", stroke_w=1.2)


def gum_bar(b: Board, x, y, w, frac):
    b.piece("basics:bar_track", x, y, w)
    b.piece("basics:bar_fill", x + 2, y + 2, max(14.0, (w - 4) * frac))


def gum_scoreboard(b: Board, x, y, w, h, rows, tabs=("Friends", "World", "Team"), sel=1, size=17.0):
    """The violet panel: a tab strip with pills and a list of row cards."""
    b.piece("score:panel", x, y, w, h)
    b.piece("score:tab_strip", x + 14, y + 14, w - 28, 41)
    pw = (w - 28 - 8 - (len(tabs) - 1) * 2) / len(tabs)
    for i, label in enumerate(tabs):
        px = x + 18 + i * (pw + 2)
        ref = "score:pill_sel" if i == sel else "score:pill_idle"
        b.piece(ref, px, y + 18, pw, 32)
        if i == sel:
            b.label(ref, label, px, y + 18, pw, 32, size=15, role="round-heavy", fill="#FFFFFF", stroke="#7A1146",
                    stroke_w=1.4, shadow="#7A1146", shadow_dy=1.0)
        else:
            b.label(ref, label, px, y + 18, pw, 32, size=15, role="round-bold", fill="#3B2A78")
    ry = y + 67
    for i, (name, score, medal, me) in enumerate(rows):
        cy = ry + i * 64
        ref = "score:card_me" if me else "score:card"
        b.piece(ref, x + 14, cy, w - 28, 60)
        if medal:
            b.piece("score:" + medal, x + 26, cy + 9)
        else:
            b.text(str(i + 1), x + 43, cy + 27, size, "#2E7D5B" if me else "#5B48A0", "round-heavy", "mc")
        b.text(name, x + 72, cy + 27, size, "#1F5C43" if me else "#33265F", "round-bold", "lc")
        b.piece("score:metric", x + w - 110, cy + 15, 82, 26)
        b.text(score, x + w - 69, cy + 28, 14, GUM_INK, "round-bold", "mc")


def showcase_gumdrop(kit: Kit) -> Board:
    b = Board(kit, 760, 432, ("#F4F0FC", "#DCD2F2"))
    rows = (("Maple", "8 420", "medal_1", False), ("Juniper", "7 915", "medal_2", False),
            ("Clover", "7 310", "medal_3", False), ("You", "6 880", None, True), ("Basil", "6 205", None, False))
    gum_scoreboard(b, 20, 20, 340, 392, rows)

    X = 386
    b.text("Gumdrop", X, 38, 31, GUM_INK, "round-heavy", "lc")
    b.text("candy casual  ·  examples/gumdrop", X + 1, 62, 12.5, "#6A5AA0", "sans-demi", "lc")
    # XP bar with a level badge
    b.text("Level 12", X + 1, 86, 14, GUM_INK, "round-heavy", "lc")
    b.text("2 450 / 3 000 XP", 742, 86, 13, "#6A5AA0", "round-bold", "rc")
    gum_bar(b, X, 98, 356, 0.82)
    grid = (("berry", "Play"), ("mint", "Claim"), ("sky", "Invite"), ("sun", "Shop"), ("grape", "Events"),
            ("coal", "Settings"))
    for i, (style, label) in enumerate(grid):
        gum_button(b, style, label, X + (i % 2) * 184, 126 + (i // 2) * 68)
    # round buttons; the last is held down: its face and glyph sink toward the body's centre
    for i, (style, glyph) in enumerate((("berry", "+"), ("mint", "?"), ("sky", "i"), ("sun", "!"),
                                        ("grape", "×"))):
        gum_round(b, style, glyph, X + i * 74, 340, pressed=(i == 4))
    gum_badge(b, "3", X + 44, 334)
    return b


# =============================================================================================== Neon
CYAN, CYAN_HOT, CYAN_DIM, MAGENTA, NAVY = "#38E8FF", "#D9FCFF", "#5FB4CC", "#FF3BD4", "#04121F"


def neon_text(b: Board, s, x, y, size, fill=CYAN_HOT, role="cond-bold", anchor="lc", tracking=None, glow=CYAN, **kw):
    tr = size * 0.12 if tracking is None else tracking
    return b.text(s, x, y, size, fill, role, anchor, tracking=tr, glow=glow, glow_r=size * 0.22, glow_a=0.55, **kw)


def neon_bar(b: Board, x, y, w, frac):
    """The track (content inset 3 dp) and the segmented fill, whose glow overhangs 2 dp."""
    b.piece("neon:bar_track", x, y, w)
    inner = w - 6
    b.piece("neon:bar_fill", x + 1, y + 1, max(20.0, inner * frac) + 4)


def neon_button(b: Board, ref, label, x, y, w, pressed=False, size=17.0):
    b.piece(ref, x, y, w, None, pressed)
    if ref.endswith("primary"):
        b.label(ref, label, x, y, w, None, pressed, size, "cond-bold", fill=NAVY, tracking=size * 0.14)
    else:
        b.label(ref, label, x, y, w, None, pressed, size, "cond-bold", fill=CYAN_HOT, tracking=size * 0.14,
                glow=CYAN, glow_r=3.0, glow_a=0.45)


def neon_badge(b: Board, n, x, y):
    b.piece("neon:badge", x, y)
    b.text(n, x + 15, y + 15.2, 13, "#FFFFFF", "cond-bold", "mc")


def neon_window(b: Board, x, y, w, h, title, status="ONLINE"):
    b.piece("neon:window", x, y, w, h)
    neon_text(b, title, x + 24, y + 17.5, 13)
    if status:
        neon_text(b, status, x + w - 40, y + 17.5, 9.5, fill=CYAN_DIM, role="cond-demi", anchor="rc", glow=None)


def showcase_neon(kit: Kit) -> Board:
    b = Board(kit, 760, 432, ("#081321", "#03070E"), dither=True)
    # ---- the systems window
    X, Y, W, H = 14, 14, 448, 404
    neon_window(b, X, Y, W, H, "SHIP SYSTEMS")
    cx0, cx1 = X + 22, X + W - 22
    tw = (cx1 - cx0 - 8) / 3
    for i, label in enumerate(("SYSTEMS", "CREW", "CARGO")):
        ref = "neon:tab" if i == 0 else "neon:tab_idle"
        tx = cx0 - 5 + i * (tw + 4)
        b.piece(ref, tx, Y + 42, tw + 10)
        b.label(ref, label, tx, Y + 42, tw + 10, None, size=13.5, role="cond-bold",
                fill="#FFFFFF" if i == 0 else "#9CD7E8", tracking=1.6)
    stats = (("SHIELDS", "82%", 0.82), ("HULL INTEGRITY", "64%", 0.64), ("REACTOR OUTPUT", "97%", 0.97),
             ("FUEL", "41%", 0.41))
    for i, (label, val, frac) in enumerate(stats):
        ry = Y + 98 + i * 42
        neon_text(b, label, cx0, ry, 11.5, fill="#8FD8EA", role="cond-demi", glow=None, tracking=1.2)
        b.text(val, cx1, ry, 14, "#FFFFFF", "din", "rc")
        neon_bar(b, cx0, ry + 9, cx1 - cx0, frac)
    b.piece("neon:divider", cx0, Y + 268, cx1 - cx0)
    readouts = (("CREW", "12/14"), ("SPEED", "4.2 kt"), ("ETA", "03:41"))
    iw = (cx1 - cx0 - 16) / 3
    for i, (label, val) in enumerate(readouts):
        ix = cx0 + i * (iw + 8)
        b.piece("neon:inset", ix, Y + 290, iw, 92)
        neon_text(b, label, ix + 12, Y + 308, 10.5, fill=CYAN_DIM, role="cond-demi", glow=None, tracking=1.4)
        b.text(val, ix + 12, Y + 344, 26, "#FFFFFF", "din", "lc")
        b.piece("neon:divider", ix + 8, Y + 362, iw - 16, opacity=0.55)

    # ---- the right column
    RX, RW = 480, 266
    b.text("Neon", RX, 38, 31, CYAN_HOT, "cond-bold", "lc", tracking=1.5, glow=CYAN, glow_r=5, glow_a=0.6)
    b.text("sci-fi HUD  ·  examples/neon", RX + 1, 62, 12.5, "#6FA9C0", "sans-demi", "lc")
    b.piece("neon:inset", RX, 82, RW, 126)
    neon_text(b, "MISSION 07", RX + 14, 100, 11, fill=MAGENTA, role="cond-bold", glow=MAGENTA, tracking=1.6)
    for i, line in enumerate(("Escort the convoy through", "the Kessler belt and dock", "at Station Vega.")):
        b.text(line, RX + 14, 124 + i * 18, 14, "#E4F6FB", "sans-medium", "lc")
    b.text("REWARD", RX + 14, 190, 10.5, CYAN_DIM, "cond-demi", "lc", tracking=1.3)
    b.text("1 200 CR", RX + RW - 14, 190, 15, CYAN_HOT, "din", "rc", glow=CYAN, glow_r=2.5, glow_a=0.5)

    neon_button(b, "neon:btn_primary", "LAUNCH", RX - 6, 222, RW + 12, size=19)
    half = (RW - 10) / 2
    neon_button(b, "neon:btn_secondary", "SCAN", RX - 6, 284, half + 12, pressed=True)
    neon_button(b, "neon:btn_secondary", "COMMS", RX + half + 10 - 6, 284, half + 12)
    neon_badge(b, "3", RX + RW - 20, 278)
    b.piece("neon:divider", RX, 368, RW)
    neon_text(b, "SECTOR 7G", RX, 396, 11, fill=CYAN_DIM, role="cond-demi", glow=None, tracking=1.4)
    neon_text(b, "ALL SYSTEMS NOMINAL", RX + RW, 396, 11, fill="#7FF7C9", role="cond-demi", anchor="rc",
              glow="#3BFFB0", tracking=1.4)
    return b


# =============================================================================================== Wood
INK, CREAM = "#4A2C12", "#F6E7C5"


def wood_button(b: Board, ref, label, x, y, w, pressed=False, size=19.0):
    b.piece(ref, x, y, w, None, pressed)
    stroke = "#0B3A16" if "gem" in ref else "#1A1714"
    b.label(ref, label, x, y, w, None, pressed, size, "serif-black", fill="#FFF8E6", stroke=stroke, stroke_w=1.8,
            shadow=stroke, shadow_dy=1.6)


def wood_bar(b: Board, x, y, w, frac):
    """The iron track (pit inset 9 dp at the ends, 4 dp top/bottom) and the green fill in its pit."""
    b.piece("wood:bar_track", x, y, w)
    inner = w - 18
    b.piece("wood:bar_fill", x + 9, y + 4, max(10.0, inner * frac), 14)


def wood_quest(b: Board, x, y, w, h, title, body, reward, prog_label, done, total):
    b.piece("wood:card", x, y, w, h)
    b.text(title, x + 18, y + 24, 18, INK, "serif-black", "lc")
    for i, line in enumerate(body):
        b.text(line, x + 18, y + 48 + i * 18, 13, "#5A3A1E", "serif", "lc")
    b.text("Reward", x + 18, y + 48 + len(body) * 18 + 6, 12.5, "#8A5A2A", "serif-italic", "lc")
    b.text(reward, x + 70, y + 48 + len(body) * 18 + 6, 13, INK, "serif-bold", "lc")
    by = y + h - 38
    b.text(prog_label, x + 18, by - 1, 12, "#5A3A1E", "serif-bold", "lc")
    b.text(f"{done} / {total}", x + w - 18, by - 1, 12, "#5A3A1E", "serif-bold", "rc")
    wood_bar(b, x + 14, by + 8, w - 28, done / total)


def showcase_wood(kit: Kit) -> Board:
    b = Board(kit, 760, 432, ("#22302A", "#121A17"))
    # ---- the quest board
    X, Y, W, H = 14, 20, 452, 398
    b.piece("wood:panel", X, Y, W, H)
    pw = 196
    b.piece("wood:card", X + (W - pw) / 2, Y - 10, pw, 40)
    b.text("Quest Board", X + W / 2, Y + 9, 19, INK, "fantasy", "mc")
    cw = W - 56
    wood_quest(b, X + 28, Y + 46, cw, 164, "The Lost Lantern",
               ("Recover the keeper's lantern from the", "Whispering Mire before nightfall."),
               "120 gold  ·  40 XP", "Wisps gathered", 3, 5)
    b.piece("wood:seal", X + 28 + cw - 40, Y + 36)
    wood_quest(b, X + 28, Y + 220, cw, 146, "Wolves at the Mill",
               ("Drive the pack away from Ashford mill.",),
               "80 gold  ·  Fine Bow", "Pelts collected", 1, 3)

    # ---- the right column
    RX, RW = 488, 258
    b.text("Wood", RX, 38, 32, CREAM, "fantasy", "lc")
    b.text("fantasy  ·  examples/wood", RX + 1, 64, 12.5, "#B9A88A", "sans-demi", "lc")
    for i, (label, val, frac) in enumerate((("Health", "84 / 100", 0.84), ("Stamina", "52 / 80", 0.65),
                                            ("Experience", "Level 7", 0.38))):
        ry = 96 + i * 44
        b.text(label, RX, ry, 13.5, CREAM, "serif-bold", "lc")
        b.text(val, RX + RW, ry, 12.5, "#D9C7A2", "serif", "rc")
        wood_bar(b, RX, ry + 9, RW, frac)
    wood_button(b, "wood:btn_gem", "Accept Quest", RX, 238, RW, size=20)
    half = (RW - 10) / 2
    wood_button(b, "wood:btn_stone", "Map", RX, 308, half, pressed=True, size=17)
    wood_button(b, "wood:btn_stone", "Inventory", RX + half + 10, 308, half, size=17)
    b.text("Gold", RX, 394, 13, "#D9C7A2", "serif-italic", "lc")
    b.text("1 284", RX + RW, 394, 15, "#F2C766", "serif-black", "rc")
    return b


# =============================================================================================== hero
def card_gumdrop(kit: Kit) -> Board:
    b = Board(kit, 300, 290, ("#F4F0FC", "#DCD2F2"))
    b.text("Level 12", 18, 22, 14.5, GUM_INK, "round-heavy", "lc")
    b.text("2 450 / 3 000", 282, 22, 12.5, "#6A5AA0", "round-bold", "rc")
    gum_bar(b, 16, 32, 268, 0.78)
    gum_scoreboard(b, 16, 58, 268, 143, (("You", "6 880", "medal_1", True),), tabs=("World", "Friends"), sel=0)
    gum_button(b, "mint", "Play", 14, 212, 196, size=22)
    gum_round(b, "berry", "+", 222, 212)
    gum_badge(b, "3", 262, 205)
    return b


def card_neon(kit: Kit) -> Board:
    b = Board(kit, 300, 290, ("#0B1828", "#03070E"), dither=True)
    X, Y, W, H = 8, 8, 284, 274
    neon_window(b, X, Y, W, H, "STATUS")
    cx0, cx1 = X + 20, X + W - 20
    tw = (cx1 - cx0 - 8) / 3
    for i, label in enumerate(("SYS", "NAV", "COM")):
        ref = "neon:tab" if i == 0 else "neon:tab_idle"
        tx = cx0 - 5 + i * (tw + 4)
        b.piece(ref, tx, Y + 40, tw + 10)
        b.label(ref, label, tx, Y + 40, tw + 10, None, size=13, role="cond-bold",
                fill="#FFFFFF" if i == 0 else "#9CD7E8", tracking=1.6)
    for i, (label, val, frac) in enumerate((("SHIELDS", "82%", 0.82), ("FUEL", "41%", 0.41))):
        ry = Y + 94 + i * 42
        neon_text(b, label, cx0, ry, 11.5, fill="#8FD8EA", role="cond-demi", glow=None, tracking=1.2)
        b.text(val, cx1, ry, 14, "#FFFFFF", "din", "rc")
        neon_bar(b, cx0, ry + 9, cx1 - cx0, frac)
    neon_button(b, "neon:btn_primary", "LAUNCH", cx0 - 6, Y + 184, cx1 - cx0 + 12, size=19)
    neon_badge(b, "3", cx1 - 18, Y + 178)
    return b


def card_wood(kit: Kit) -> Board:
    b = Board(kit, 300, 290, ("#22302A", "#121A17"))
    b.piece("wood:panel", 8, 16, 284, 268)
    b.piece("wood:card", 80, 6, 140, 38)
    b.text("Quests", 150, 24.5, 17, INK, "fantasy", "mc")
    cx, cy, cw, ch = 26, 52, 248, 128
    b.piece("wood:card", cx, cy, cw, ch)
    b.text("The Lost Lantern", cx + 14, cy + 22, 16, INK, "serif-black", "lc")
    b.text("Reward", cx + 14, cy + 46, 12, "#8A5A2A", "serif-italic", "lc")
    b.text("120 gold", cx + 60, cy + 46, 12.5, INK, "serif-bold", "lc")
    b.text("Wisps gathered", cx + 14, cy + 74, 11.5, "#5A3A1E", "serif-bold", "lc")
    b.text("3 / 5", cx + cw - 14, cy + 74, 11.5, "#5A3A1E", "serif-bold", "rc")
    wood_bar(b, cx + 10, cy + 84, cw - 20, 0.6)
    b.piece("wood:seal", cx + cw - 38, cy - 8)
    wood_button(b, "wood:btn_gem", "Accept", 26, 192, 124, size=17)
    wood_button(b, "wood:btn_stone", "Later", 156, 192, 118, size=17)
    return b


def _rounded(img: Image.Image, r_px: float) -> Image.Image:
    """[img] with antialiased rounded corners (alpha)."""
    k = 4
    m = Image.new("L", (img.width * k, img.height * k), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, m.width - 1, m.height - 1], radius=r_px * k, fill=255)
    out = img.convert("RGBA")
    out.putalpha(m.resize(img.size, Image.LANCZOS))
    return out


def screen_card(b: Board, card: Board, x, y, k: float, r: float = 14.0) -> tuple:
    """Pastes [card] scaled by k (Lanczos from the 2x render: crisp) with rounded corners and a soft shadow."""
    W, H = round(card.w * k * S), round(card.h * k * S)
    img = card.img.convert("RGB").resize((W, H), Image.LANCZOS)
    w, h = W / S, H / S
    b.shadow(x, y, x + w, y + h, r, blur=9, alpha=0.55, dy=7)
    b.paste(_rounded(img, r * S), x, y)
    b.rect(x, y, x + w, y + h, outline=(255, 255, 255, 34), width=0.75, r=r)
    return w, h


def hero(kit: Kit) -> Board:
    b = Board(kit, 800, 380, ("#171C33", "#0B0E1B"), dither=True)
    b.text("ninekit", 400, 46, 50, "#FFFFFF", "sans-heavy", "mc", tracking=-0.5)
    b.text("Game UI sprites from YAML layers: measured, 9-sliced, exported to any engine.", 400, 84, 15.5,
           "#AEB7D8", "sans-medium", "mc")
    k, gap = 0.78, 22
    cw = 300 * k
    x0 = (800 - 3 * cw - 2 * gap) / 2
    cards = ((card_gumdrop, "Gumdrop", "candy casual"), (card_neon, "Neon", "sci-fi HUD"),
             (card_wood, "Wood", "fantasy"))
    for i, (fn, name, style) in enumerate(cards):
        x = x0 + i * (cw + gap)
        _, h = screen_card(b, fn(kit), x, 108, k)
        tw = b.measure(name + "  " + style, 12.5, "sans-bold")
        nw = b.measure(name + "  ", 12.5, "sans-bold")
        b.text(name, x + cw / 2 - tw / 2, 108 + h + 22, 12.5, "#E6EAF8", "sans-bold", "lc")
        b.text(style, x + cw / 2 - tw / 2 + nw, 108 + h + 22, 12.5, "#7F89AD", "sans-medium", "lc")
    return b


# =============================================================================================== quick piece
QUICK = ROOT / "docs" / "tools" / "quick_piece.yaml"
DOC_BG = ("#1A1F2E", "#121622")
DOC_INK, DOC_SOFT, DOC_FAINT, DOC_ACCENT = "#E8ECF8", "#A3ACC9", "#6C7594", "#FFB23E"


def quick_label(b: Board, text, x, y, w, h, size=17.0):
    b.label("quick:button", text, x, y, w, h, size=size, role="round-heavy", fill="#FFFFFF", stroke="#9A3A0E",
            stroke_w=1.6, shadow="#7A2E0E", shadow_dy=1.4)


def checker(b: Board, x0, y0, x1, y1, cell=6.0, c0="#2A3044", c1="#232838"):
    """A transparency checkerboard behind a texture (diagram background)."""
    b.rect(x0, y0, x1, y1, fill=c0)
    for j in range(int((y1 - y0) / cell) + 1):
        for i in range(int((x1 - x0) / cell) + 1):
            if (i + j) % 2:
                b.rect(x0 + i * cell, y0 + j * cell, min(x1, x0 + (i + 1) * cell), min(y1, y0 + (j + 1) * cell),
                       fill=c1)


def quick_piece(kit: Kit) -> Board:
    """The README's 20-line spec, built: its @2x texture as written, then drawn at three sizes."""
    b = Board(kit, 720, 156, DOC_BG)
    tex = kit.file("quick:button", "main")                      # the compacted @2x texture
    tw, th = tex.width / S, tex.height / S
    tx, ty = 42, 34
    checker(b, tx - 8, ty - 8, tx + tw + 8, ty + th + 8)
    b.paste(tex, tx, ty)
    b.text("button@2x.png", tx + tw / 2, 124, 11, DOC_SOFT, "mono", "mc")
    b.text(f"{tex.width} × {tex.height} px", tx + tw / 2, 140, 11, DOC_FAINT, "mono", "mc")
    arrow(b, 112, 62, 134)
    x = 152
    for label, w, h in (("OK", 96, 52), ("Continue", 176, 52), ("Start game", 224, 64)):
        y = 104 - h
        b.piece("quick:button", x, y, w, h)
        quick_label(b, label, x, y, w, h, 17 if h == 52 else 20)
        b.text(f"{w} × {h} dp", x + w / 2, 124, 11, DOC_SOFT, "mono", "mc")
        x += w + 20
    return b


# =============================================================================================== how it works
def code_card(b: Board, x, y, w, lines, size=12.0, lh=17.5, title=None):
    """A YAML excerpt with light syntax colouring."""
    h = 22 + len(lines) * lh + (22 if title else 0)
    b.rect(x, y, x + w, y + h, fill="#0E1220", outline="#2B3350", width=1, r=10)
    yy = y + 22
    if title:
        b.text(title, x + 14, y + 16, 10.5, DOC_FAINT, "mono", "lc")
        b.line([(x, y + 28), (x + w, y + 28)], "#2B3350", 1)
        yy += 18
    key_re = re.compile(r"^(\s*-?\s*)([A-Za-z_]+)(:)(.*)$")
    f = font("mono", round(size * S))
    cw = f.getlength("M") / S
    for i, line in enumerate(lines):
        ly = yy + i * lh
        m = key_re.match(line)
        if line.strip().startswith("#"):
            b.text(line, x + 14, ly, size, "#5E6A8C", "mono", "lc")
            continue
        if not m:
            b.text(line, x + 14, ly, size, "#C9D1EA", "mono", "lc")
            continue
        lead, key, colon, rest = m.groups()
        cx = x + 14
        b.text(lead, cx, ly, size, "#8792B4", "mono", "lc")
        cx += len(lead) * cw
        b.text(key, cx, ly, size, "#7FD1FF", "mono", "lc")
        cx += len(key) * cw
        b.text(colon, cx, ly, size, "#8792B4", "mono", "lc")
        cx += cw
        comment = ""
        if "#" in rest:
            rest, comment = rest.split("#", 1)
            comment = "#" + comment
        b.text(rest, cx, ly, size, "#F3D28B", "mono", "lc")
        if comment:
            b.text(comment, cx + len(rest) * cw, ly, size, "#5E6A8C", "mono", "lc")
    return h


def _top_items(inner: str) -> list:
    """The top-level `key: value` items of a flow mapping's inside (commas inside brackets are kept)."""
    items, depth, cur, quote = [], 0, "", None
    for c in inner:
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == "," and depth == 0:
            items.append(cur.strip())
            cur = ""
            continue
        cur += c
    return items + [cur.strip()] if cur.strip() else items


def spec_excerpt(path: Path, piece: str = "button") -> list:
    """The piece's lines of a spec, verbatim but for three cuts: one indent level less, no trailing comments, and
    each flow-style layer shortened to its first and last item around an ellipsis."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == f"{piece}:")
    ind = len(lines[start]) - len(lines[start].lstrip())
    out = []
    for ln in lines[start:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) < ind or (out and ln.strip() and len(ln) - len(ln.lstrip()) == ind):
            break
        ln = ln[ind:]
        m = re.match(r"^(\s*- \{)(.*)\}\s*$", ln)
        if m:
            items = _top_items(m.group(2))
            ln = m.group(1) + (f"{items[0]}, …, {items[-1]}" if len(items) > 2 else ", ".join(items)) + "}"
        elif "#" in ln and not ln.lstrip().startswith("#"):
            ln = ln.split("  #", 1)[0].rstrip()
        out.append(ln)
    return out


def step_title(b: Board, n: int, text: str, x, y):
    b.rect(x, y - 9, x + 18, y + 9, fill=DOC_ACCENT, r=9)
    b.text(str(n), x + 9, y + 0.5, 11, "#1A1F2E", "sans-heavy", "mc")
    b.text(text, x + 26, y, 14, DOC_INK, "sans-demi", "lc")


def arrow(b: Board, x0, y, x1, colour="#4C5577"):
    b.line([(x0, y), (x1 - 2, y)], colour, 1.6)
    b.line([(x1 - 8, y - 5), (x1, y), (x1 - 8, y + 5)], colour, 1.6)


def iso_plate(kit: Kit, ref: str, lean: float = 0.42, squash: float = 0.5, pad: float = 6.0) -> Image.Image:
    """One layer on a translucent sheet, leaned back (shear + squash) for an exploded view. Drawn from the @4x
    files and resampled in premultiplied alpha, then halved to this page's 2x."""
    s = 4
    im = kit.draw(ref, s=s)
    P = round(pad * s)
    sheet = Image.new("RGBA", (im.width + 2 * P, im.height + 2 * P), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).rounded_rectangle([0, 0, sheet.width - 1, sheet.height - 1], radius=7 * s,
                                            fill=(150, 170, 235, 26), outline=(170, 190, 255, 90), width=3)
    sheet.alpha_composite(im, (P, P))
    sw, sh = sheet.size
    k = lean
    ow, oh = round(sw + k * sh), round(squash * sh)
    data = (1.0, k / squash, -k * sh, 0.0, 1.0 / squash, 0.0)
    out = sheet.convert("RGBa").transform((ow, oh), Image.AFFINE, data, resample=Image.BICUBIC)
    return out.resize((ow * S // s, oh * S // s), Image.LANCZOS).convert("RGBA")


def how_it_works(kit: Kit) -> Board:
    import yaml

    spec = yaml.safe_load(QUICK.read_text(encoding="utf-8"))
    piece = spec["pieces"]["button"]
    layers = piece["layers"]
    alone = {**{k: v for k, v in spec.items() if k != "pieces"}, "pieces": {}}
    for i, layer in enumerate(layers):
        alone["pieces"][f"l{i}"] = {"size": piece["size"], "overhang": piece["overhang"], "slice": "none",
                                    "layers": [layer]}
    kit.add("layers", alone, scales=[4])
    kit.add("quick4", QUICK, scales=[4])

    b = Board(kit, 800, 452, DOC_BG)
    # ---- 1. the spec
    step_title(b, 1, "Describe it in YAML", 22, 30)
    code_card(b, 22, 50, 292, spec_excerpt(QUICK), size=10.4, lh=18, title=f"{QUICK.name}, excerpt")
    arrow(b, 320, 150, 340)

    # ---- 2. the layers, exploded (back = bottom of the stack)
    step_title(b, 2, "Layered back to front", 346, 30)
    names = [layer.get("name", f"layer {i}") for i, layer in enumerate(layers)]
    plates = [iso_plate(kit, f"layers:l{i}") for i in range(len(layers))]
    pw, ph = plates[0].width / S, plates[0].height / S
    x0, ybot, step = 350, 214, 35
    for i, im in enumerate(plates):
        y = ybot - i * step
        b.paste(im, x0, y)
        b.text(names[i], x0 + pw + 8, y + ph / 2 + 1, 11.5, DOC_SOFT, "mono", "lc")
    arrow(b, 556, 150, 576)

    # ---- 3. the built piece and its slices
    step_title(b, 3, "Sliced for you", 586, 30)
    sl = kit.slices("quick4:button", 4)                               # px at @4x
    sl_l, sl_t, sl_r, sl_b = (v / 4 for v in sl)
    W, H = 96, 52
    k = 2.0                                                            # drawn from the @4x files: 2x on this page
    px, py = 588, 70
    b.paste(kit.draw("quick4:button", W, H, s=4), px, py)
    x1, y1 = px + sl_l * k, py + sl_t * k
    x2, y2 = px + (W - sl_r) * k, py + (H - sl_b) * k
    X2, Y2 = px + W * k, py + H * k
    HATCH = (255, 255, 255, 120)
    b.hatch(x1, py, x2, Y2, HATCH)
    b.hatch(px, y1, x1, y2, HATCH)
    b.hatch(x2, y1, X2, y2, HATCH)
    for xx in (x1, x2):
        b.line([(xx, py - 6), (xx, Y2 + 6)], "#FFFFFF", 0.75, dash=2.5)
    for yy in (y1, y2):
        b.line([(px - 6, yy), (X2 + 6, yy)], "#FFFFFF", 0.75, dash=2.5)
    ly = Y2 + 26
    b.rect(px, ly - 6, px + 12, ly + 6, outline="#FFFFFF", width=0.75, r=2)
    b.text("fixed corners", px + 18, ly, 11.5, DOC_INK, "sans-demi", "lc")
    b.hatch(px + 110, ly - 6, px + 122, ly + 6, (255, 255, 255, 170), spacing=3.0)
    b.rect(px + 110, ly - 6, px + 122, ly + 6, outline="#FFFFFF", width=0.75, r=2)
    b.text("stretch", px + 128, ly, 11.5, DOC_INK, "sans-demi", "lc")
    b.text(f"slices {sl_l:g} · {sl_t:g} · {sl_r:g} · {sl_b:g} dp", px, ly + 24, 10.5, DOC_FAINT, "mono", "lc")
    tex = kit.file("quick:button", "main")
    b.text(f"@2x texture {tex.width}×{tex.height} px", px, ly + 42, 10.5, DOC_FAINT, "mono", "lc")

    # ---- 4. any size
    step_title(b, 4, "Any size, crisp at every scale", 22, 300)
    x = 26
    for label, w, h in (("OK", 96, 52), ("Continue", 172, 52), ("Start game", 232, 64)):
        y = 396 - h
        b.piece("quick:button", x, y, w, h)
        quick_label(b, label, x, y, w, h, 17 if h == 52 else 20)
        b.text(f"{w}×{h} dp", x + w / 2, 414, 10.5, DOC_FAINT, "mono", "mc")
        x += w + 16
    arrow(b, 578, 364, 598)

    # ---- 5. export
    step_title(b, 5, "Export", 610, 300)
    engines = ("Godot", "Unity", "Flutter", "CSS", "Phaser", "JSON")
    for i, e in enumerate(engines):
        cx, cy = 612 + (i % 2) * 86, 324 + (i // 2) * 34
        b.rect(cx, cy, cx + 78, cy + 26, fill="#232A3F", outline="#3A4466", width=1, r=13)
        b.text(e, cx + 39, cy + 13.5, 12, DOC_INK, "sans-demi", "mc")
    b.text("PNGs + ninekit.json", 612, 432, 10.5, DOC_FAINT, "mono", "lc")
    return b


# =============================================================================================== stretch.gif
def _ease(u: float) -> float:
    """0 -> 1 -> 0 over u in [0, 1], smooth at both ends (a raised cosine)."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * u)


STRETCH_LANES = (("gum:btn_sky", 134, "Gumdrop button", 30),        # (piece, lane centre x, caption, frames)
                 ("neon:window", 370, "Neon window", 30),
                 ("wood:panel", 600, "Wood panel", 34))


def _lane_size(ref: str, e: float, e2: float) -> tuple:
    if ref.startswith("gum"):
        return 116 + 104 * e, 62
    if ref.startswith("neon"):
        return 156 + 64 * e, 128 + 104 * e2
    return 148 + 56 * e, 116 + 112 * e2


def stretch_frames(kit: Kit, s: int = S) -> list:
    """RGB frames: three pieces resize one after another; the button is held down at its widest."""
    frames = []
    timeline = []
    for ref, _, _, n in STRETCH_LANES:
        for k in range(n):
            timeline.append((ref, k / n))
    for active, u in timeline:
        b = Board(kit, 720, 300, DOC_BG[0], s=s)
        for ref, cx, title, _n in STRETCH_LANES:
            _, p, _ = kit.piece(ref)
            ov = p.get("overhang") or (0, 0, 0, 0)
            uu = u if ref == active else 0.0
            e = _ease(uu)
            e2 = _ease(min(1.0, uu * 1.15)) if uu else 0.0
            w, h = _lane_size(ref, e, e2)
            pressed = ref == active and ref.startswith("gum") and 0.38 <= u <= 0.62
            x = cx - (w - ov[0] - ov[2]) / 2 - ov[0]           # the logical box stays centred in the lane
            y = 136 - (h - ov[1] - ov[3]) / 2 - ov[1]
            b.piece(ref, x, y, w, h, pressed)
            if ref.startswith("neon"):
                neon_text(b, "STATUS", x + 24, y + 17.5, 11)
            if ref.startswith("gum"):
                b.label(ref, "Play", x, y, w, h, pressed, 22, "round-heavy", fill="#FFFFFF",
                        stroke=PRESETS["sky"]["text_outline"], stroke_w=2.2, shadow=PRESETS["sky"]["text_outline"],
                        shadow_dy=1.6)
            lw, lh = w - ov[0] - ov[2], h - ov[1] - ov[3]
            b.text(title, cx, 272, 12.5, DOC_INK if ref == active else DOC_SOFT, "sans-demi", "mc")
            size = f"{lw:.0f} × {lh:.0f} dp"
            if pressed:
                tw = b.measure(size + "  pressed", 10.5, "mono")
                b.text(size, cx - tw / 2, 289, 10.5, DOC_SOFT, "mono", "lc")
                b.text("pressed", cx + tw / 2, 289, 10.5, DOC_ACCENT, "mono", "rc")
            else:
                b.text(size, cx, 289, 10.5, DOC_SOFT if ref == active else DOC_FAINT, "mono", "mc")
        frames.append(np.asarray(b.img.convert("RGB")))
    return frames


BAYER8 = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
                   [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
                   [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                   [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], dtype=np.float64)


def stretch_gif(kit: Kit, path: Path, s: int = 1, ms: int = 50, spread: float = 10.0) -> Path:
    """The frames on one shared 255-colour palette with ordered (Bayer) dithering: deterministic per pixel, so a
    pixel that does not change keeps its index; each frame stores only what changed (the rest transparent)."""
    frames = stretch_frames(kit, s)
    sample = np.concatenate(frames[:: max(1, len(frames) // 16)], axis=0)
    pal = Image.fromarray(sample).quantize(255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    H, W = frames[0].shape[:2]
    thr = (np.tile(BAYER8, (H // 8 + 1, W // 8 + 1))[:H, :W] + 0.5) / 64.0 - 0.5
    out, prev = [], None
    for fr in frames:
        d = np.clip(fr.astype(np.float64) + thr[..., None] * spread + 0.5, 0, 255).astype(np.uint8)
        idx = np.asarray(Image.fromarray(d).quantize(palette=pal, dither=Image.Dither.NONE)).copy()
        if prev is not None:
            masked = idx.copy()
            masked[(idx == prev)] = 255              # unchanged: transparent, the previous frame shows through
        else:
            masked = idx
        im = Image.fromarray(masked, "P")
        pal_bytes = pal.getpalette()[: 255 * 3] + [0, 0, 0]
        im.putpalette(pal_bytes)
        out.append(im)
        prev = idx
    path.parent.mkdir(parents=True, exist_ok=True)
    out[0].save(path, save_all=True, append_images=out[1:], duration=ms, loop=0, optimize=False, disposal=1,
                transparency=255)
    return path


# =============================================================================================== engines
# Each crop spans the screenshot's full width and starts and ends in a gap between rows of pieces, so nothing is
# cut; it is scaled to fit its tile and padded with the screenshot's own background colour.
ENGINE_SHOTS = (   # (file, crop box in its px, caption, detail)
    ("godot_demo.png", (0, 520, 430, 797), "Godot 4.7", "NineSkin, NineButton, StyleBoxTexture"),
    ("unity_demo.png", (0, 512, 1960, 1400), "Unity 6000.6", "NineSliceStack, sprite borders"),
    ("flutter_demo.png", (0, 40, 1260, 1040), "Flutter 3.47", "NineSliceBox · flutter test, DPR 3"),
    ("web_css_demo.png", (0, 122, 1760, 1156), "CSS", "border-image · headless Chrome, DPR 2"),
)


def engines(kit: Kit) -> Board:
    M, G, CAP = 16, 16, 30
    tw = (800 - 2 * M - G) / 2
    th = tw / 1.5
    TW, TH = round(tw * S), round(th * S)
    b = Board(kit, 800, M + 2 * (CAP + th) + G + M - 4, DOC_BG)
    for i, (fname, box, name, detail) in enumerate(ENGINE_SHOTS):
        x = M + (i % 2) * (tw + G)
        y = M + (i // 2) * (CAP + th + G)
        b.text(name, x + 2, y + 11, 14, DOC_INK, "sans-bold", "lc")
        b.text(detail, x + tw - 2, y + 11, 10.5, DOC_FAINT, "mono", "rc")
        with Image.open(IMAGES / fname) as im:
            shot = im.convert("RGB").crop(box)
        k = min(TW / shot.width, TH / shot.height)                  # contain: the whole crop is shown
        shot = shot.resize((round(shot.width * k), round(shot.height * k)), Image.LANCZOS)
        tile = Image.new("RGB", (TW, TH), shot.getpixel((2, 2)))
        tile.paste(shot, ((TW - shot.width) // 2, (TH - shot.height) // 2))
        b.shadow(x, y + CAP, x + tw, y + CAP + th, 10, blur=6, alpha=0.45, dy=4)
        b.paste(_rounded(tile, 10 * S), x, y + CAP)
        b.rect(x, y + CAP, x + tw, y + CAP + th, outline=(255, 255, 255, 30), width=0.75, r=10)
    return b


# =============================================================================================== recreate
def recreate(kit: Kit) -> Board:
    ex = ROOT / "examples" / "recreate"
    bg = "#3B4252"                                     # compare's default background: the metrics in its README
    with tempfile.TemporaryDirectory(prefix="ninekit-cmp-") as tmp:
        res = compare(ex / "capsule.yaml", "capsule", ex / "reference.png", out=Path(tmp) / "cmp.png", bg=bg,
                      ref_scale=3, zoom=1)
        with Image.open(Path(tmp) / "cmp.png") as im:
            sheet = im.convert("RGB")
    W, H = res["size"]
    head, gap = 18, 4                                  # compare's sheet layout (ninekit.compare._write_sheet)
    panels = [sheet.crop((i * (W + gap), head, i * (W + gap) + W, head + H)) for i in range(3)]
    z = 3                                              # nearest-neighbour: every pixel stays visible
    pw, ph = W * z / S, H * z / S
    gapx = (800 - 3 * pw) / 4
    b = Board(kit, 800, ph + 126, DOC_BG)
    titles = (("reference.png", "a Pillow drawing, 168×66 px"), ("ninekit", "capsule.yaml, from measurements"),
              ("|difference| ×4", "black = identical"))
    for i, (panel, (t1, t2)) in enumerate(zip(panels, titles)):
        x = gapx + i * (pw + gapx)
        b.text(t1, x, 22, 13.5, DOC_INK, "sans-bold", "lc")
        b.text(t2, x, 39, 10.5, DOC_FAINT, "mono", "lc")
        b.paste(panel.resize((W * z, H * z), Image.NEAREST), x, 54)
        b.rect(x, 54, x + pw, 54 + ph, outline=(255, 255, 255, 40), width=0.5)
    y = 54 + ph + 34
    stats = (f"mean |Δ| {res['mean_abs']:.2f} / 255", f"max {res['max_abs']} / 255", f"PSNR {res['psnr']:.1f} dB",
             f"{res['over_16_pct']:.2f} % of pixels over 16 / 255")
    line = "   ·   ".join(stats)
    b.text(line, 400, y, 12, DOC_SOFT, "mono", "mc")
    b.text("ninekit compare capsule.yaml capsule reference.png --ref-scale 3", 400, y + 22, 10.5, DOC_FAINT, "mono",
           "mc")
    return b


# =============================================================================================== contact sheets
def wood_sheet(kit: Kit, path: Path) -> Path:
    """The Wood contact sheet from its @2x files (the @3x sheet is over 1 MB); `ninekit preview` draws it."""
    from ninekit.cli import main as cli

    import contextlib
    import io

    with tempfile.TemporaryDirectory(prefix="ninekit-sheet-") as tmp, contextlib.redirect_stdout(io.StringIO()):
        sheet = Path(tmp) / "wood.png"
        cli(["preview", str(ROOT / "examples/wood/wood.yaml"), "--scale", "2", "-o", str(sheet)])
        with Image.open(sheet) as im:
            save_png(im, path)
    return path


# =============================================================================================== main
TARGETS = {
    "hero": ("hero.png", hero),
    "gumdrop": ("showcase_gumdrop.png", showcase_gumdrop),
    "neon": ("showcase_neon.png", showcase_neon),
    "wood": ("showcase_wood.png", showcase_wood),
    "stretch": ("stretch.gif", stretch_gif),
    "quick": ("quick_piece.png", quick_piece),
    "how": ("how_it_works.png", how_it_works),
    "engines": ("engines.png", engines),
    "recreate": ("recreate.png", recreate),
    "wood_sheet": ("wood_preview.png", wood_sheet),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("only", nargs="*", help="targets to draw (default: all)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("-o", "--out", type=Path, default=IMAGES)
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(f"{k:10s} {v[0]}" for k, v in TARGETS.items()))
        return 0
    names = a.only or list(TARGETS)
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        ap.error(f"unknown target(s) {', '.join(unknown)} (see --list)")
    readme = ROOT / "README.md"
    if readme.exists() and QUICK.read_text(encoding="utf-8").strip() not in readme.read_text(encoding="utf-8"):
        print(f"warning: README.md does not quote {QUICK.relative_to(ROOT)} verbatim (the quick-piece snippet)",
              file=sys.stderr)
    kit = Kit()
    try:
        for n in names:
            fname, fn = TARGETS[n]
            path = a.out / fname
            if fn.__code__.co_argcount >= 2:          # draws and writes the file itself
                fn(kit, path)
            else:
                res = fn(kit)
                if isinstance(res, Board):
                    res.save(path)
                else:
                    save_png(res, path)
            with Image.open(path) as im:
                print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}  "
                      f"{im.width}x{im.height}  {path.stat().st_size / 1024:.0f} KB")
    finally:
        kit.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
