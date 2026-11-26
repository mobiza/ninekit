"""The `ninekit` command line (DESIGN 4)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ninekit import NinekitError, __version__


def _rel(p: Path) -> str:
    """A path relative to the working folder when it is inside it, else absolute."""
    try:
        r = os.path.relpath(p)
    except ValueError:
        return str(p)
    return str(p) if r.startswith("..") else r


def _plain(o):
    """json.dumps fallback: numpy scalars as plain Python numbers (never "int64 is not JSON serializable")."""
    item = getattr(o, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _dumps(data) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=_plain)


def _scales(text: str | None):
    if not text:
        return None
    out = []
    for part in text.split(","):
        part = part.strip()
        if part:
            v = float(part)
            out.append(int(v) if v.is_integer() else v)
    return out


def cmd_build(args) -> int:
    from ninekit.render import build

    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    res = build(args.spec, theme=args.theme, out=args.out, only=only, scales=_scales(args.scales))
    if args.json:
        print(_dumps({
            "ok": not res.problems,
            "manifest": str(res.manifest_path),
            "out": str(res.out_dir),
            "files": [{**f, "path": str(res.out_dir / f["file"])} for f in res.files],
            "problems": res.problems,
            "warnings": res.warnings,
        }))
        return 0
    for f in res.files:
        sp = f["slice_px"]
        print(f"wrote {_rel(res.out_dir / f['file'])}  {f['size_px'][0]}x{f['size_px'][1]}  "
              f"slice_px {sp if sp is not None else 'none'}")
    print(f"wrote {_rel(res.manifest_path)}  ({len(res.manifest['pieces'])} pieces)")
    for piece, reasons in res.problems.items():
        for r in reasons:
            print(f"warning: {piece}: {r}", file=sys.stderr)
    for piece, notes in res.warnings.items():
        for n in notes:
            print(f"note: {piece}: {n}", file=sys.stderr)
    return 0


def cmd_verify(args) -> int:
    from ninekit.verify import verify

    report = verify(args.target, theme=args.theme)
    if args.json:
        print(_dumps(report.as_dict()))
        return 0 if report.ok else 1
    for f in report.files:
        tag = "ok  " if f.status == "ok" else "FAIL"
        print(f"{tag} {f.file}")
        for r in f.reasons:
            print(f"     - {r}")
        for wmsg in f.warnings:
            print(f"     warning: {wmsg}")
    for piece, reasons in report.problems.items():
        for r in reasons:
            print(f"FAIL {piece}: {r}")
    for piece, notes in report.warnings.items():
        for n in notes:
            print(f"warning: {piece}: {n}")
    print(report.summary())
    return 0 if report.ok else 1


def cmd_preview(args) -> int:
    from ninekit.preview import preview

    path = preview(args.target, args.out, bg=args.bg, scale=_scales(args.scale)[0] if args.scale else None,
                   theme=args.theme)
    print(f"wrote {_rel(path)}")
    return 0


def cmd_compare(args) -> int:
    from ninekit.compare import compare, parse_crop

    res = compare(args.target, args.piece, args.ref, args.out, crop=parse_crop(args.crop) if args.crop else None,
                  outputs=[o.strip() for o in args.outputs.split(",") if o.strip()] if args.outputs else None,
                  bg=args.bg, theme=args.theme, ref_scale=float(args.ref_scale) if args.ref_scale else None,
                  zoom=args.zoom)
    if args.json:
        print(_dumps({"ok": True, **res}))
        return 0
    psnr = "inf" if res["psnr"] is None else f"{res['psnr']:.2f} dB"
    print(f"wrote {_rel(Path(res['out']))}: reference | {res['piece']} @{res['scale']}x | |difference| heatmap")
    print(f"compare {res['piece']} at {res['size'][0]}x{res['size'][1]} px (rendered {res['render_px'][0]}x"
          f"{res['render_px'][1]} texels, {_rel(Path(res['ref']))} crop {res['crop']}): mean abs diff "
          f"{res['mean_abs']:.2f}/255, max {res['max_abs']}/255, PSNR {psnr}, "
          f"{res['over_16_pct']:.2f}% of pixels over 16/255")
    return 0


def cmd_render(args) -> int:
    from ninekit.draw import parse_size, render_piece_at

    res = render_piece_at(args.target, args.piece, parse_size(args.size), args.out,
                          outputs=[o.strip() for o in args.outputs.split(",") if o.strip()] if args.outputs else None,
                          scale=_scales(args.scale)[0] if args.scale else None, pressed=args.pressed,
                          theme=args.theme)
    if args.json:
        print(_dumps({"ok": True, **res}))
        return 0
    print(f"wrote {_rel(Path(res['out']))}  {res['piece']} {res['size'][0]:g} x {res['size'][1]:g} dp @{res['scale']}x "
          f"= {res['size_px'][0]}x{res['size_px'][1]} px" + ("  pressed" if res["pressed"] else ""))
    for n in res["notes"]:
        print(f"note: {n}", file=sys.stderr)
    return 0


def cmd_export(args) -> int:
    from ninekit.exporters import get_exporter

    target = Path(args.manifest)
    if target.suffix.lower() in (".yaml", ".yml"):
        raise NinekitError("export takes a manifest (ninekit.json); run `ninekit build SPEC` first")
    fn = get_exporter(args.target)
    scale = _scales(args.scale)[0] if args.scale else None
    kwargs = {}
    if args.godot_project:
        if args.target != "godot":
            raise NinekitError("--godot-project only applies to --target godot")
        kwargs["godot_project"] = Path(args.godot_project)
    written = fn(target, Path(args.out), scale=scale, runtime=args.runtime, **kwargs)
    for p in written:
        print(f"wrote {_rel(Path(p))}")
    return 0


def cmd_new(args) -> int:
    from ninekit.scaffold import scaffold

    for p in scaffold(args.dir):
        print(f"wrote {_rel(p)}")
    return 0


def cmd_measure(argv: list[str]) -> int:
    import importlib

    try:
        measure = importlib.import_module("ninekit.measure")
    except ModuleNotFoundError as e:
        if e.name == "ninekit.measure":
            print("error: `ninekit measure` is not available in this build (missing ninekit/measure.py)",
                  file=sys.stderr)
            return 2
        raise
    return int(measure.main(list(argv)) or 0)


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ninekit", description="Engine-agnostic 9-slice sprite generator for game/app UI.")
    p.add_argument("--version", action="version", version=f"ninekit {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    b = sub.add_parser("build", help="render a spec's pieces to PNGs + ninekit.json")
    b.add_argument("spec")
    b.add_argument("--theme", help="a theme file (vars/colors/params) merged over the spec")
    b.add_argument("-o", "--out", help="output folder (default: the spec's `out`)")
    b.add_argument("--only", help="comma-separated piece names")
    b.add_argument("--scales", help="comma-separated scales, e.g. 1,2,3 (default: the spec's)")
    b.add_argument("--json", action="store_true", help="machine-readable output")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("verify", help="measured checks of a spec (fresh build) or a manifest; exit 1 on failure")
    v.add_argument("target", metavar="SPEC|MANIFEST")
    v.add_argument("--theme", help="a theme file merged over the spec (SPEC only)")
    v.add_argument("--json", action="store_true", help="machine-readable output")
    v.set_defaults(func=cmd_verify)

    pv = sub.add_parser("preview", help="contact sheet of every piece at several sizes")
    pv.add_argument("target", metavar="SPEC|MANIFEST")
    pv.add_argument("--theme", help="a theme file merged over the spec (SPEC only)")
    pv.add_argument("-o", "--out", help="sheet path (default: <out>/<name>.preview.png)")
    pv.add_argument("--bg", default="#3B4252", help="background colour of the second row (default #3B4252)")
    pv.add_argument("--scale", help="which scale's files to show (default: the largest)")
    pv.set_defaults(func=cmd_preview)

    c = sub.add_parser("compare", help="a built piece next to a reference crop, with a difference heatmap and metrics")
    c.add_argument("target", metavar="SPEC|MANIFEST")
    c.add_argument("piece")
    c.add_argument("ref", metavar="REF.png", help="the reference image")
    c.add_argument("--crop", metavar="x,y,w,h", help="the piece's box in the reference, px (default: the whole image)")
    c.add_argument("--outputs", metavar="a,b", help="outputs to stack, bottom first (default: the piece's stack)")
    c.add_argument("--bg", default="#3B4252", help="background both sides are composited on (default #3B4252)")
    c.add_argument("--ref-scale", metavar="S", help="reference px per dp (default: the largest scale, i.e. the "
                                                    "reference is at the density of the files compared)")
    c.add_argument("--theme", help="a theme file merged over the spec (SPEC only)")
    c.add_argument("--zoom", type=int, help="nearest-neighbour zoom of the written image (default: auto)")
    c.add_argument("-o", "--out", help="side-by-side image (default: <spec out>/compare_<piece>.png, or next to "
                                       "the manifest)")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser("render", help="draw a piece at any dp size (9-slice, transparent PNG) for mockups")
    r.add_argument("target", metavar="SPEC|MANIFEST")
    r.add_argument("piece")
    r.add_argument("--size", required=True, metavar="WxH", help="the size in dp, e.g. 240x56")
    r.add_argument("--outputs", metavar="a,b", help="outputs to stack, bottom first (default: the piece's stack)")
    r.add_argument("--scale", help="which scale's files to draw (default: the largest); px = dp x scale")
    r.add_argument("--pressed", action="store_true", help="draw the pressed state (the face scaled 0.92)")
    r.add_argument("--theme", help="a theme file merged over the spec (SPEC only)")
    r.add_argument("-o", "--out", required=True, help="the PNG to write")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.set_defaults(func=cmd_render)

    e = sub.add_parser("export", help="turn a manifest into an engine's assets")
    e.add_argument("manifest", metavar="MANIFEST")
    e.add_argument("--target", required=True, help="json | godot | unity | flutter | css | phaser")
    e.add_argument("-o", "--out", required=True, help="output folder")
    e.add_argument("--scale", help="only this scale")
    e.add_argument("--runtime", action="store_true", help="also copy the engine adapter")
    e.add_argument("--godot-project", metavar="DIR",
                   help="godot only: the Godot project root for --runtime (default: the nearest folder "
                        "above -o holding project.godot)")
    e.set_defaults(func=cmd_export)

    sub.add_parser("measure", help="measure an image's runs/edges (see `ninekit measure --help`)", add_help=False)

    n = sub.add_parser("new", help="scaffold a starter spec in DIR")
    n.add_argument("dir")
    n.set_defaults(func=cmd_new)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "measure":
        return cmd_measure(argv[1:])
    parser = make_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args) or 0)
    except NinekitError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        else:
            print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
