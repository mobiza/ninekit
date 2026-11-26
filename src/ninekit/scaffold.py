"""`ninekit new DIR`: a starter spec that builds and verifies as is."""
from __future__ import annotations

from pathlib import Path

from ninekit import NinekitError

STARTER = """\
# A starter ninekit spec. Build, check and look:
#   ninekit build ninekit.yaml && ninekit verify ninekit.yaml && ninekit preview ninekit.yaml
# The full contract is ninekit's docs/DESIGN.md.
ninekit: 1
name: starter
scales: [1, 2, 3]          # texture px per dp; every scale is rendered natively
out: out/

vars:
  R: 10                    # corner radius (dp)

colors:
  outline: "#2B2140"
  face: [[0, "#FFF7E8"], [1, "#EAD8B8"]]     # a named gradient (vertical stops)
  lip: [[0, "#B49A74"], [1, "#8C7457"]]
  button_face: [[0, "#FFD86B"], [0.5, "#F6B93B"], [1, "#E58E26"]]
  button_lip: [[0, "#B8661E"], [1, "#8A4512"]]

pieces:
  # a panel: soft shadow, a lip under the face, a thin outline; slices are found automatically
  panel:
    size: [56, 48]
    content: [10, 8, 10, 12]
    layers:
      - shape: {rect: [3, 4, "w - 3", "h - 2"], r: R}
        fill: "#000000"
        soft: 2.5
        falloff: smooth
        opacity: 0.3
      - shape: {rect: [2, 0, "w - 2", "h - 3"], r: R}
        fill: {vgrad: lip, from: "h - 12", to: "h - 3"}
      - shape: {rect: [2, 0, "w - 2", "h - 7"], r: R}
        fill: {vgrad: face, to: "h - 7"}
      - shape: {rect: [2, 0, "w - 2", "h - 3"], r: R}
        ring: 1
        fill: outline

  # a button in two images on one canvas: the frame and the face (the runtime can press the face)
  button:
    size: [64, 36]
    outputs: [frame, face]
    content: [12, 4, 12, 8]
    layers:
      - output: frame
        shape: {rect: [0, 0, w, h], r: 12}
        fill: outline
      - output: frame
        shape: {rect: [1.5, 1.5, "w - 1.5", "h - 1.5"], r: 10.5}
        fill: {vgrad: button_lip, from: "h - 10", to: "h - 1.5"}
      - output: face
        shape: {rect: [1.5, 1.5, "w - 1.5", "h - 6"], r: 10.5}
        fill: {vgrad: button_face, from: 1.5, to: "h - 6"}
      - output: face
        shape: {rect: [5, 3.5, "w - 5", 13], r: 6}
        fill: {vgrad: [[0, "#FFFFFFA0"], [1, "#FFFFFF10"]], from: 3.5, to: 13}

  # an icon drawn whole (no 9-slice)
  badge:
    size: [24, 24]
    slice: none
    layers:
      - shape: {circle: [12, 12, 11]}
        fill: outline
      - shape: {circle: [12, 12, 9.5]}
        fill: {vgrad: button_face, from: 2.5, to: 21.5}
      - shape: {ellipse: [12, 8, 5, 2.5]}
        fill: "#FFFFFF"
        soft: 1
        opacity: 0.45
"""


def scaffold(directory) -> list[Path]:
    """Writes DIR/ninekit.yaml (refuses to overwrite) and returns the files written."""
    d = Path(directory)
    target = d / "ninekit.yaml"
    if target.exists():
        raise NinekitError(f"{target} already exists; not overwriting it")
    d.mkdir(parents=True, exist_ok=True)
    target.write_text(STARTER, encoding="utf-8")
    return [target]
