"""The `phaser` export target (DESIGN 7): the PNGs, `ninekit-phaser.json` and the ES module `ninekit-phaser.js`.

`ninekit-phaser.json`: the manifest reduced to what a Phaser runtime needs - per piece `size` (dp, the sprite
canvas), `slice`, `stretch`, `content`, `overhang`, `mode`, `layers` (outputs stacked bottom -> top; a composite
`main` next to named outputs is left out of them and named in `composite`), `press` (a frame/face piece) and per
output and scale `{file, key, size_px, slice_px}` (`key` = the texture key the module loads it under).

`ninekit-phaser.js` embeds that data (no extra fetch) and exports `preloadNinekit(scene, baseUrl, {scale})` (queues
every output as a texture at one scale; baseUrl defaults to the module's own folder) and
`addNinekit(scene, x, y, name, width, height, opts)` (a Container of `scene.add.nineslice` objects with texture-px
slices drawn at 1/scale, so width / height are dp - the logical size, overhang outside it; Images for pieces drawn
whole; Images + TileSprites for `tile` axes, whole tiles only; a `content` container for labels whose rect is
`contentRect()`, insets measured from the canvas; `setPressed` scales the face and the content by 0.92 toward the
logical centre). Its source is `ninekit/adapters/web/phaser_runtime.js` (package data); `runtime` is ignored because the
module already is the runtime.
"""
from __future__ import annotations

import json as _json
import shutil
from importlib import resources
from pathlib import Path

from ninekit import NinekitError, __version__
from ninekit.exporters.css import piece_scales, stacked_layers
from ninekit.manifest import load_manifest, scale_key

RUNTIME = "adapters/web/phaser_runtime.js"


def texture_key(manifest_name: str, piece: str, output: str, scale: str) -> str:
    return f"ninekit:{manifest_name}/{piece}/{output}@{scale}"


def _r(v: float) -> float:
    f = round(float(v), 4)
    return int(f) if f.is_integer() else f


def phaser_data(manifest: dict, want: str | None = None) -> dict:
    """The data of `ninekit-phaser.json` for [manifest] (restricted to scale [want])."""
    name = manifest.get("name")
    pieces = {}
    all_scales: set = set()
    for pname, p in manifest["pieces"].items():
        layers, composite = stacked_layers(p)
        scales = piece_scales(p, want)
        if not scales:
            raise NinekitError(f"piece {pname}: no files at scale {want}")
        all_scales.update(scales)
        outs = {}
        for o in layers + ([composite] if composite else []):
            outs[o] = {k: {"file": p["outputs"][o][k]["file"],
                           "key": texture_key(name, pname, o, k),
                           "size_px": p["outputs"][o][k]["size_px"],
                           "slice_px": p["outputs"][o][k]["slice_px"]} for k in scales}
        top = scales[-1]
        w_px, h_px = outs[layers[0]][top]["size_px"]
        s = float(top)
        pieces[pname] = {
            "size": [_r(w_px / s), _r(h_px / s)],
            "slice": p.get("slice"),
            "stretch": list(p.get("stretch") or ["stretch", "stretch"]),
            "content": p.get("content"),
            "overhang": p.get("overhang"),
            "mode": p.get("mode", "color"),
            "layers": layers,
            "composite": composite,
            "press": "face" in layers and len(layers) > 1,
            "outputs": outs,
        }
    scales = sorted(all_scales, key=float)
    return {
        "ninekit": 1,
        "name": name,
        "generator": f"ninekit {__version__}",
        "scales": [int(float(k)) if float(k).is_integer() else float(k) for k in scales],
        "pieces": pieces,
    }


def runtime_source() -> str:
    return resources.files("ninekit").joinpath(RUNTIME).read_text(encoding="utf-8")


def module_source(data: dict) -> str:
    """`ninekit-phaser.js`: the runtime with [data] embedded."""
    src = runtime_source()
    blob = _json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)
    return (src.replace("__NINEKIT_VERSION__", __version__)
               .replace("__NINEKIT_NAME__", str(data.get("name")).replace('"', "'"))
               .replace("__NINEKIT_DATA__", blob))


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
    data = phaser_data(manifest, want)
    written: list[Path] = []
    copied = set()
    for p in data["pieces"].values():
        for per in p["outputs"].values():
            for f in per.values():
                if f["file"] in copied:
                    continue
                copied.add(f["file"])
                src, dst = mpath.parent / f["file"], out / f["file"]
                if not src.is_file():
                    raise NinekitError(f"{src}: missing (listed in {mpath.name})")
                if src.resolve() != dst.resolve():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
                    written.append(dst)
    jpath = out / "ninekit-phaser.json"
    jpath.write_text(_json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    written.append(jpath)
    mod = out / "ninekit-phaser.js"
    mod.write_text(module_source(data), encoding="utf-8")
    written.append(mod)
    return written
