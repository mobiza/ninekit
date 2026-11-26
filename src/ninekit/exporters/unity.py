"""The `unity` export target (DESIGN 7): sprites a Unity project imports as 9-sliced UI sprites.

`-o DIR` is the project's ninekit folder (e.g. `Assets/UI/Ninekit`); several manifests share it:

    DIR/<name>/ninekit.json         the manifest (only the exported scale with --scale)
    DIR/<name>/<file>.png           its PNGs, at their manifest paths
    DIR/NinekitSprites.cs           generated: every piece of every manifest under DIR (asset paths, dp
                                    sizes, slices, content padding, overhang, stack order)
    DIR/NinekitTypes.cs             the descriptor types NinekitSprites.cs uses
    DIR/Editor/NinekitImporter.cs   the AssetPostprocessor that imports each listed PNG as a Sprite: FullRect
                                    mesh, spriteBorder from slice_px, pixelsPerUnit = 100 x scale (so
                                    SetNativeSize() gives the size in dp on a Canvas with a 100 reference
                                    PPU), no mipmaps, bilinear, clamp, uncompressed
    DIR/Runtime/...                 with --runtime: NineSliceStack (stacked frame/face Images, overhang,
                                    content rect, press scale of the face + content, `fixed` axes at
                                    their natural length) and the shade-ramp UI shader for `mode: shade`

A `fixed` axis imports as a plain sliced sprite (a bare Image stretches it); NineSliceStack keeps it at
its natural length, centred on the logical box.

The importer and the types are written on every export (without the importer the PNGs are plain
textures); `--runtime` adds the runtime. `<name>` is the manifest's name, so manifests sharing a
folder never collide; a re-export removes the PNGs its previous manifest listed and the new one does
not. One project has one ninekit folder (a second would compile the importer twice): exporting into
another folder of a project that already has one is an error naming it.
"""
from __future__ import annotations

import json as _json
import re
import shutil
from pathlib import Path

from ninekit import NinekitError, __version__
from ninekit.manifest import dumps, load_manifest, scale_key

ADAPTER = Path(__file__).resolve().parent.parent / "adapters" / "unity"
ALWAYS = ("NinekitTypes.cs", "Editor/NinekitImporter.cs")
RUNTIME = ("Runtime/NineSliceStack.cs", "Runtime/NinekitShadeRamp.cs", "Runtime/NinekitShadeRamp.shader")
MARKER = "ninekit-unity-adapter"          # in every adapter file's first lines: which copies are ours
_NAME_OK = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_RESERVED = {"editor", "runtime"}
_MEMBERS = {"Root", "All", "Find", "Manifest", "Pieces"}   # members of the generated classes
# manifest stretch -> NinekitStretch; `fixed` imports as a plain sliced sprite, NineSliceStack keeps its length
_STRETCH = {"stretch": "Stretch", "tile": "Tile", "fixed": "Fixed"}


def export(manifest_path, out_dir, scale=None, runtime=False) -> list[Path]:
    mpath = Path(manifest_path)
    if mpath.is_dir():
        mpath = mpath / "ninekit.json"
    manifest = load_manifest(mpath)
    name = str(manifest.get("name", ""))
    if not _NAME_OK.match(name) or name.lower() in _RESERVED:
        raise NinekitError(f"manifest name {name!r} cannot be a Unity folder name (letters, digits, _ . -; "
                           f"not Editor/Runtime): rename the spec's `name`")
    want = None if scale is None else scale_key(scale)
    if want is not None and float(want) not in {float(s) for s in manifest.get("scales", [])}:
        raise NinekitError(f"--scale {want}: the manifest has scales {manifest.get('scales')}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assets_root = _assets_root(out)
    _check_single_folder(out, assets_root)

    sub = out / name
    sub.mkdir(parents=True, exist_ok=True)
    exported = _filtered(manifest, want)
    written: list[Path] = []

    # PNGs (the previous export's leftovers first, so a removed piece does not linger as a Sprite)
    new_files = {e["file"] for _, _, _, e in _iter_entries(exported)}
    old_manifest = sub / "ninekit.json"
    if old_manifest.exists():
        try:
            old_files = {e["file"] for _, _, _, e in _iter_entries(load_manifest(old_manifest))}
        except NinekitError:
            old_files = set()
        for f in sorted(old_files - new_files):
            for stale in (sub / f, sub / (f + ".meta")):
                if stale.is_file():
                    stale.unlink()
    for f in sorted(new_files):
        src = mpath.parent / f
        dst = sub / f
        if not src.is_file():
            raise NinekitError(f"{mpath}: lists {f}, which is missing (run `ninekit build` again)")
        if src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        written.append(dst)
    (sub / "ninekit.json").write_text(dumps(exported), encoding="utf-8")
    written.append(sub / "ninekit.json")

    # the adapter: the importer and the types always, the runtime on request
    for rel in ALWAYS + (RUNTIME if runtime else ()):
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ADAPTER / rel, dst)
        written.append(dst)

    # the constants of every manifest in the folder (this one included)
    cs = out / "NinekitSprites.cs"
    cs.write_text(sprites_cs(out, assets_root), encoding="utf-8")
    written.append(cs)
    return written


# --- folders -----------------------------------------------------------------------------------------------------------

def _assets_root(out: Path) -> Path | None:
    """The Unity project's `Assets` folder [out] sits in (or is), or None when it is not in a project."""
    p = out.resolve()
    for q in (p, *p.parents):
        if q.name == "Assets":
            return q
    return None


def _unity_path(path: Path, assets_root: Path | None) -> str | None:
    """`Assets/...` for a path inside the project, else None."""
    if assets_root is None:
        return None
    rel = path.resolve().relative_to(assets_root)
    return "/".join(("Assets", *rel.parts))


def _check_single_folder(out: Path, assets_root: Path | None) -> None:
    if assets_root is None:
        return
    mine = (out / "Editor" / "NinekitImporter.cs").resolve()
    for p in assets_root.rglob("NinekitImporter.cs"):
        if p.resolve() == mine:
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            continue
        if MARKER in head:
            folder = p.parent.parent
            raise NinekitError(f"this Unity project already has a ninekit folder: {_unity_path(folder, assets_root)} "
                               f"(export there: one importer per project), or delete it first")


def _iter_entries(manifest: dict):
    for pname, p in manifest["pieces"].items():
        for o in p.get("stack") or sorted(p["outputs"]):
            for sk, entry in sorted(p["outputs"].get(o, {}).items(), key=lambda kv: float(kv[0])):
                yield pname, o, sk, entry


def _filtered(manifest: dict, want: str | None) -> dict:
    """The manifest as exported: every scale, or only [want] (pieces without a file at it are dropped)."""
    if want is None:
        return manifest
    out = {k: v for k, v in manifest.items() if k != "pieces"}
    out["scales"] = [int(float(want)) if float(want).is_integer() else float(want)]
    pieces = {}
    for pname, p in manifest["pieces"].items():
        outputs = {o: {sk: e for sk, e in per.items() if sk == want} for o, per in p["outputs"].items()}
        if not any(outputs.values()):
            continue
        pieces[pname] = {**p, "outputs": {o: per for o, per in outputs.items() if per}}
    out["pieces"] = pieces
    return out


# --- NinekitSprites.cs -------------------------------------------------------------------------------------------------

def _pascal(text: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
    s = "".join(p[:1].upper() + p[1:] for p in parts) or "_"
    return "_" + s if s[0].isdigit() else s


def _unique(names: list[str], taken: set[str]) -> list[str]:
    """C# identifiers for [names]: PascalCase, made unique against [taken] (and each other) with a suffix."""
    out, seen = [], set(taken)
    for n in names:
        ident = base = _pascal(n)
        i = 2
        while ident in seen:
            ident = f"{base}{i}"
            i += 1
        seen.add(ident)
        out.append(ident)
    return out


def _f(v) -> str:
    """A C# float literal."""
    v = float(v)
    if v.is_integer():
        return f"{int(v)}f"
    return f"{round(v, 4)!r}f"


def _s(text: str) -> str:
    return _json.dumps(text, ensure_ascii=False)


def _insets(v) -> str:
    """NinekitInsets from a manifest [l, t, r, b] (None -> Zero)."""
    if v is None:
        return "NinekitInsets.Zero"
    return f"new NinekitInsets({', '.join(_f(x) for x in v)})"


def _piece_cs(mname: str, pname: str, p: dict, root_expr: str, ind: str) -> str:
    stack = []
    for o in p.get("stack") or sorted(p["outputs"]):
        files = []
        for sk, e in sorted(p["outputs"].get(o, {}).items(), key=lambda kv: float(kv[0])):
            sp = e.get("slice_px")
            files.append(f"new NinekitFile({_f(sk)}, {root_expr} + {_s(mname + '/' + e['file'])}, "
                         f"new Vector2Int({int(e['size_px'][0])}, {int(e['size_px'][1])}), {_insets(sp)}, "
                         f"{'true' if sp is not None else 'false'})")
        if not files:
            continue
        sep = ",\n" + ind + "            "
        stack.append(f"new NinekitOutput({_s(o)}, new[] {{\n{ind}            {sep.join(files)} }})")
    stretch = p.get("stretch") or ["stretch", "stretch"]
    try:
        sx, sy = (f"NinekitStretch.{_STRETCH[s]}" for s in stretch)
    except KeyError as e:
        raise NinekitError(f"{mname}/{pname}: unknown stretch {e.args[0]!r} (known: {', '.join(_STRETCH)})") from None
    mode = "NinekitMode.Shade" if p.get("mode") == "shade" else "NinekitMode.Color"
    sep = ",\n" + ind + "        "
    return (f"new NinekitPiece({_s(mname)}, {_s(pname)},\n"
            f"{ind}    size: new Vector2({_f(p['size'][0])}, {_f(p['size'][1])}),\n"
            f"{ind}    slice: {_insets(p.get('slice'))}, sliced: {'true' if p.get('slice') is not None else 'false'},\n"
            f"{ind}    stretchX: {sx}, stretchY: {sy}, mode: {mode},\n"
            f"{ind}    content: {_insets(p.get('content'))}, hasContent: "
            f"{'true' if p.get('content') is not None else 'false'},\n"
            f"{ind}    overhang: {_insets(p.get('overhang'))},\n"
            f"{ind}    stack: new[] {{\n{ind}        {sep.join(stack)} }})")


def sprites_cs(out: Path, assets_root: Path | None) -> str:
    """NinekitSprites.cs for every `<out>/<name>/ninekit.json` (sorted by name)."""
    root = _unity_path(out, assets_root)
    manifests = []
    for mp in sorted(out.glob("*/ninekit.json")):
        try:
            manifests.append((mp.parent.name, load_manifest(mp)))
        except NinekitError as e:
            raise NinekitError(f"{mp}: {e} (every */ninekit.json in a ninekit folder is an export)") from None
    lines = [
        "// <auto-generated>",
        f"// ninekit {__version__}: `ninekit export --target unity` writes this file from every */ninekit.json",
        "// in this folder. Do not edit; export again.",
        "// </auto-generated>",
        "using System.Collections.Generic;",
        "using UnityEngine;",
        "",
        "namespace Ninekit",
        "{",
        "    /// <summary>Every exported ninekit piece: one nested class per manifest, one field per piece.</summary>",
        "    public static class NinekitSprites",
        "    {",
        "        /// <summary>The ninekit folder as an AssetDatabase path, with a trailing slash"
        + ("" if root else " (empty: the export folder was not inside a Unity project's Assets)") + ".</summary>",
        f"        public const string Root = {_s((root + '/') if root else '')};",
        "",
    ]
    class_names = _unique([m for m, _ in manifests], {"NinekitSprites", *_MEMBERS})
    for (mname, man), cname in zip(manifests, class_names):
        pnames = list(man["pieces"])
        fields = _unique(pnames, {cname, *_MEMBERS})
        ind = "            "
        lines += [
            f"        /// <summary>{mname}: {len(pnames)} pieces at scales "
            f"{', '.join(scale_key(s) for s in man.get('scales', []))}.</summary>",
            f"        public static class {cname}",
            "        {",
            f"            public const string Manifest = Root + {_s(mname + '/ninekit.json')};",
        ]
        for pname, field in zip(pnames, fields):
            p = man["pieces"][pname]
            lines.append(f"            public static readonly NinekitPiece {field} = "
                         f"{_piece_cs(mname, pname, p, 'Root', ind)};")
        lines += [
            f"            public static readonly NinekitPiece[] Pieces = {{ {', '.join(fields)} }};",
            "        }",
            "",
        ]
    all_items = ", ".join(f"{c}.Pieces" for c in class_names)
    lines += [
        "        static Dictionary<string, NinekitPiece> s_ById;",
        "",
        "        /// <summary>Every piece of every manifest.</summary>",
        "        public static IEnumerable<NinekitPiece> All",
        "        {",
        "            get",
        "            {",
        f"                foreach (var list in new NinekitPiece[][] {{ {all_items} }})",
        "                    foreach (var p in list) yield return p;",
        "            }",
        "        }",
        "",
        "        /// <summary>A piece by \"manifest/piece\" (e.g. \"basics/panel\"), or null.</summary>",
        "        public static NinekitPiece Find(string id)",
        "        {",
        "            if (s_ById == null)",
        "            {",
        "                var map = new Dictionary<string, NinekitPiece>();",
        "                foreach (var p in All) map[p.Id] = p;",
        "                s_ById = map;",
        "            }",
        "            return id != null && s_ById.TryGetValue(id, out var piece) ? piece : null;",
        "        }",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)
