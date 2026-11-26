"""The engine-neutral manifest `ninekit.json`, schema 1 (DESIGN 3).

Piece-level `size` / `slice` (dp) come from the largest scale; per-file `size_px` / `slice_px` are
authoritative. Keys are sorted, two-space indent, trailing newline (stable diffs).
"""
from __future__ import annotations

import json
from pathlib import Path

from ninekit import NinekitError, __version__

SCHEMA = 1


def scale_key(s) -> str:
    """"3" for 3 / 3.0, "1.5" for 1.5: the manifest's scale keys and the @<s>x file token."""
    f = float(s)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _clean(v):
    """A number for content / overhang: an int when whole, else rounded to 4 places."""
    f = float(v)
    return int(f) if f.is_integer() else round(f, 4)


def _dp(v) -> float:
    return round(float(v), 2)


def manifest_entry(per_scale: dict, file_map: dict) -> dict:
    """The manifest entry of one piece from its Rendered results per scale and {(output, scale): file}."""
    smax = max(per_scale, key=float)
    top = per_scale[smax]
    outputs: dict = {}
    for s, r in per_scale.items():
        for o, arr in r.outputs.items():
            outputs.setdefault(o, {})[scale_key(s)] = {
                "file": file_map[(o, s)],
                "size_px": [int(arr.shape[1]), int(arr.shape[0])],
                "slice_px": None if r.slice_px is None else [int(v) for v in r.slice_px],
            }
    design = getattr(top, "design_size", None) or top.size
    return {
        "size": [_dp(top.size[0]), _dp(top.size[1])],
        "design_size": [_dp(design[0]), _dp(design[1])],
        "slice": None if top.slice_px is None else [_dp(v / float(smax)) for v in top.slice_px],
        "stretch": list(top.stretch),
        "content": None if top.content is None else [_clean(v) for v in top.content],
        "overhang": None if top.overhang is None else [_clean(v) for v in top.overhang],
        "mode": top.mode,
        "slicing": getattr(top, "slicing", None),
        "stack": list(top.outputs),
        "outputs": outputs,
    }


def new_manifest(name: str, scales: list, pieces: dict) -> dict:
    return {
        "ninekit": SCHEMA,
        "name": name,
        "generator": f"ninekit {__version__}",
        "scales": sorted(scales, key=float),
        "pieces": pieces,
    }


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_manifest(path: Path, manifest: dict) -> None:
    Path(path).write_text(dumps(manifest), encoding="utf-8")


def load_manifest(path) -> dict:
    p = Path(path)
    if p.is_dir():
        p = p / "ninekit.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError as e:
        raise NinekitError(f"cannot read manifest {p}: {e.strerror}") from None
    except json.JSONDecodeError as e:
        raise NinekitError(f"{p}: not valid JSON ({e})") from None
    if not isinstance(data, dict) or data.get("ninekit") != SCHEMA or not isinstance(data.get("pieces"), dict):
        raise NinekitError(f"{p}: not a ninekit manifest (schema {SCHEMA})")
    return data


def merge_manifest(existing_path: Path, fresh: dict) -> dict:
    """[fresh]'s pieces over an existing manifest of the same name (for `build --only`)."""
    try:
        old = load_manifest(existing_path)
    except NinekitError:
        return fresh
    if old.get("name") != fresh["name"]:
        return fresh
    pieces = {**old["pieces"], **fresh["pieces"]}
    scales = sorted({*map(float, old.get("scales", [])), *map(float, fresh["scales"])})
    out = dict(fresh)
    out["pieces"] = pieces
    out["scales"] = [int(s) if s.is_integer() else s for s in scales]
    return out


def iter_files(manifest: dict):
    """(piece, output, scale_key, file entry) for every file, in manifest order."""
    for pname, p in manifest["pieces"].items():
        for o in p.get("stack") or list(p["outputs"]):
            for sk, entry in p["outputs"].get(o, {}).items():
                yield pname, o, sk, entry
