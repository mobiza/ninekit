"""The `json` export target (DESIGN 7): the PNGs plus `sprites.json`, a flat list with one entry per file.

Each entry: {name, output, scale, file, size_px, slice_px, slice_dp, stretch, content, overhang, mode}.
Engines without an adapter can read it directly; there is no runtime to copy (`runtime` is ignored).
"""
from __future__ import annotations

import json as _json
import shutil
from pathlib import Path

from ninekit import NinekitError
from ninekit.manifest import iter_files, load_manifest, scale_key


def export(manifest_path, out_dir, scale=None, runtime=False) -> list[Path]:
    mpath = Path(manifest_path)
    if mpath.is_dir():
        mpath = mpath / "ninekit.json"
    manifest = load_manifest(mpath)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    want = None if scale is None else scale_key(scale)
    if want is not None and float(want) not in {float(s) for s in manifest.get("scales", [])}:
        raise NinekitError(f"--scale {want}: the manifest has scales {manifest.get('scales')}")
    written: list[Path] = []
    sprites = []
    for pname, o, sk, entry in iter_files(manifest):
        if want is not None and sk != want:
            continue
        piece = manifest["pieces"][pname]
        src = mpath.parent / entry["file"]
        dst = out / entry["file"]
        if src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            written.append(dst)
        s = float(sk)
        sp = entry["slice_px"]
        sprites.append({
            "name": pname,
            "output": o,
            "scale": int(s) if s.is_integer() else s,
            "file": entry["file"],
            "size_px": entry["size_px"],
            "slice_px": sp,
            "slice_dp": None if sp is None else [round(v / s, 4) for v in sp],
            "stretch": piece["stretch"],
            "content": piece.get("content"),
            "overhang": piece.get("overhang"),
            "mode": piece.get("mode", "color"),
        })
    sprites.sort(key=lambda e: (e["name"], e["output"], e["scale"]))
    path = out / "sprites.json"
    path.write_text(_json.dumps(sprites, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    written.append(path)
    return written
