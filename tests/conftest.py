"""Shared helpers for ninekit's tests (`PYTHONPATH=src python3 -m pytest -q`)."""
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def write_spec(tmp_path: Path, spec: dict | str, name: str = "spec.yaml") -> Path:
    """Writes a spec (a dict, or YAML text) and returns its path."""
    p = tmp_path / name
    p.write_text(spec if isinstance(spec, str) else yaml.safe_dump(spec, sort_keys=False))
    return p


def piece_spec(layers, size=(20, 10), scales=(1,), **piece) -> dict:
    """A one-piece spec named `p`."""
    return {"ninekit": 1, "name": "t", "scales": list(scales),
            "pieces": {"p": {"size": list(size), "layers": layers, **piece}}}


def render_one(tmp_path, spec: dict, scale=None, piece="p"):
    """The Rendered result of one piece at one scale (no files written)."""
    from ninekit.render import render_piece
    from ninekit.spec import load_spec

    s = load_spec(write_spec(tmp_path, spec))
    pdef = next(d for d in s.piece_defs() if d.name == piece)
    return render_piece(s, pdef, scale if scale is not None else s.scales[0])


def load_rgba(path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"))


@pytest.fixture
def root() -> Path:
    return ROOT
