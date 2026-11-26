"""The `godot` export target (DESIGN 7): PNGs + `ninekit.json`, a `StyleBoxTexture` per output, the runtime.

* Every PNG the manifest lists (only `--scale S`'s when given) is copied under OUT with its manifest path, and
  `ninekit.json` is written next to them (filtered to the exported scale, so it never names a missing file).
* When the export includes scale 1, each output gets `<piece>[_<output>].tres` beside its @1x PNG: a Godot 4
  `StyleBoxTexture` with texture_margin_* = slice_px, axis_stretch from `stretch` (`tile` -> tile-fit, so a
  tiled middle always ends on a whole tile, like `ninekit preview`; `fixed` -> plain stretch: a StyleBox has
  no fixed mode, use the piece at its natural length on that axis), expand_margin_* = overhang and
  content_margin_* from content. The texture is referenced by a path relative to the .tres, so the folder
  can sit anywhere in the project.
* A re-export first removes the PNGs / `.tres` (and their `.import` files) that the previous `ninekit.json`
  in OUT listed and the new export does not; files that manifest does not account for are left alone.
* `runtime=True` copies the `addons/ninekit` runtime (NinekitManifest, NineSkin, NineButton, the shade ramp
  shader) into the Godot project that contains OUT: the nearest folder at or above OUT holding
  `project.godot` (or `godot_project` when the caller passes it). No project found is an error.

Units: content insets are measured from the piece's full art (its `size`, overhang included), as the
runtime's NineSkin lays them out; a StyleBox's content margins are measured from the control's rect (the art
minus the overhang), so content_margin = content - overhang (never below 0).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ninekit import NinekitError
from ninekit.manifest import dumps, iter_files, load_manifest, scale_key

SIDES = ("left", "top", "right", "bottom")
# StyleBoxTexture / NinePatchRect AxisStretchMode (DESIGN 7: `fixed` is written as plain stretch)
AXIS_STRETCH = {"stretch": 0, "fixed": 0, "tile": 2}
ADAPTER = Path(__file__).resolve().parents[1] / "adapters" / "godot" / "addons" / "ninekit"
_SKIP = {".uid", ".import", ".pyc"}


def find_godot_project(start) -> Path | None:
    """The nearest folder at or above [start] that holds `project.godot` (None when there is none)."""
    p = Path(start).resolve()
    for d in (p, *p.parents):
        if (d / "project.godot").is_file():
            return d
    return None


def _num(v) -> str:
    """A float the way Godot writes it (`15.0`, `1.4`)."""
    return repr(round(float(v), 4))


def stylebox_tres(texture_rel: str, slice_px, stretch, content, overhang) -> str:
    """The text of a StyleBoxTexture .tres for one @1x file."""
    lines = [
        '[gd_resource type="StyleBoxTexture" format=3]',
        "",
        f'[ext_resource type="Texture2D" path="{texture_rel}" id="1_tex"]',
        "",
        "[resource]",
    ]
    ov = [float(v) for v in (overhang or (0, 0, 0, 0))]
    if content is not None:
        for side, c, o in zip(SIDES, content, ov):
            lines.append(f"content_margin_{side} = {_num(max(0.0, float(c) - o))}")
    lines.append('texture = ExtResource("1_tex")')
    for side, v in zip(SIDES, slice_px or (0, 0, 0, 0)):
        lines.append(f"texture_margin_{side} = {_num(v)}")
    for side, o in zip(SIDES, ov):
        if o:
            lines.append(f"expand_margin_{side} = {_num(o)}")
    for axis, mode in zip(("horizontal", "vertical"), stretch):
        if mode not in AXIS_STRETCH:
            raise NinekitError(f"unknown stretch mode {mode!r}")
        if AXIS_STRETCH[mode]:
            lines.append(f"axis_stretch_{axis} = {AXIS_STRETCH[mode]}")
    return "\n".join(lines) + "\n"


def _filtered(manifest: dict, want: str | None) -> dict:
    """The manifest with only scale [want]'s files (all when None)."""
    if want is None:
        return manifest
    out = dict(manifest)
    out["scales"] = [s for s in manifest.get("scales", []) if scale_key(s) == want]
    pieces = {}
    for name, p in manifest["pieces"].items():
        q = dict(p)
        q["outputs"] = {o: {sk: e for sk, e in per.items() if sk == want} for o, per in p["outputs"].items()}
        pieces[name] = q
    out["pieces"] = pieces
    return out


def _owned(manifest: dict, want: str | None) -> set[str]:
    """Every file (relative to the export folder) an export of [manifest] writes, bar `ninekit.json`:
    the PNGs and the `.tres` beside each @1x PNG."""
    names: set[str] = set()
    for pname, o, sk, entry in iter_files(manifest):
        if want is not None and sk != want:
            continue
        names.add(entry["file"])
        if sk == "1":
            parent = Path(entry["file"]).parent
            names.add((parent / f"{pname}{'' if o == 'main' else '_' + o}.tres").as_posix())
    return names


def _remove_stale(out: Path, manifest: dict, want: str | None) -> None:
    """Deletes what a previous export (its `ninekit.json` in [out]) wrote and this one does not, with the
    `.import` files Godot made for them. Files the previous manifest does not account for are never touched."""
    old_path = out / "ninekit.json"
    if not old_path.is_file():
        return
    try:
        old = _owned(load_manifest(old_path), None)
    except (NinekitError, OSError, ValueError, KeyError):
        return
    for f in sorted(old - _owned(manifest, want)):
        for stale in (out / f, out / (f + ".import")):
            if stale.is_file():
                stale.unlink()


def copy_runtime(project_root: Path) -> list[Path]:
    """Copies the adapter into `<project_root>/addons/ninekit` (overwriting its files, keeping any others)."""
    if not ADAPTER.is_dir():
        raise NinekitError(f"the Godot runtime is missing from this ninekit install ({ADAPTER})")
    dst_root = Path(project_root) / "addons" / "ninekit"
    written = []
    for src in sorted(ADAPTER.rglob("*")):
        if not src.is_file() or src.suffix in _SKIP or src.name == ".DS_Store" or "__pycache__" in src.parts:
            continue
        dst = dst_root / src.relative_to(ADAPTER)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst)
    return written


def export(manifest_path, out_dir, scale=None, runtime=False, godot_project=None) -> list[Path]:
    mpath = Path(manifest_path)
    if mpath.is_dir():
        mpath = mpath / "ninekit.json"
    manifest = load_manifest(mpath)
    out = Path(out_dir)
    want = None if scale is None else scale_key(scale)
    if want is not None and want not in {scale_key(s) for s in manifest.get("scales", [])}:
        raise NinekitError(f"--scale {want}: the manifest has scales {manifest.get('scales')}")
    root = None
    if runtime:
        root = Path(godot_project) if godot_project is not None else find_godot_project(out)
        if root is None or not (root / "project.godot").is_file():
            raise NinekitError(f"--runtime: no project.godot at or above {out}; export into a folder of the "
                               f"Godot project (the runtime goes to <project>/addons/ninekit)")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "ninekit.json").resolve() != mpath.resolve():  # never delete the sources of an in-place export
        _remove_stale(out, manifest, want)
    written: list[Path] = []
    tres: dict[Path, str] = {}
    for pname, o, sk, entry in iter_files(manifest):
        if want is not None and sk != want:
            continue
        src = mpath.parent / entry["file"]
        dst = out / entry["file"]
        if not src.is_file():
            raise NinekitError(f"{pname}: {entry['file']} is missing next to the manifest")
        if src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            written.append(dst)
        if sk != "1":
            continue
        piece = manifest["pieces"][pname]
        path = dst.parent / f"{pname}{'' if o == 'main' else '_' + o}.tres"
        if path in tres:
            raise NinekitError(f"two outputs would write {path.name} ({pname}/{o} and another)")
        tres[path] = stylebox_tres(dst.name, entry["slice_px"], piece["stretch"], piece.get("content"),
                                   piece.get("overhang"))
    for path, text in tres.items():
        path.write_text(text, encoding="utf-8")
        written.append(path)
    mout = out / "ninekit.json"
    if mout.resolve() != mpath.resolve() or want is not None:
        mout.write_text(dumps(_filtered(manifest, want)), encoding="utf-8")
        written.append(mout)
    if root is not None:
        written += copy_runtime(root)
    return written

