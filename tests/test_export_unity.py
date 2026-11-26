"""The `unity` export target (DESIGN 7): files, NinekitSprites.cs, the importer, the folder rules.

The real proof is demos/unity (NinekitDemoCheck in the editor); these tests pin the exporter's output. When a
Unity editor is installed, the generated and adapter C# is also compiled against its assemblies.
"""
import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import write_spec
from ninekit import NinekitError
from ninekit.cli import main
from ninekit.exporters import get_exporter
from ninekit.exporters.unity import _pascal, _unique
from ninekit.render import build

RECT = {"shape": {"rect": [0, 0, "w", "h"], "r": 5}, "fill": {"vgrad": [[0, "#ffcc00"], [1, "#cc6600"]]}}
SPEC = {
    "ninekit": 1, "name": "demo", "scales": [1, 3],
    "pieces": {
        "card": {"size": [40, 24], "content": [4, 3, 4, 5], "overhang": [0, 0, 0, 2], "layers": [RECT]},
        "tab": {"size": [30, 20], "outputs": ["frame", "face"],
                "layers": [{**RECT, "output": "frame", "fill": "#222222"},
                           {"shape": {"rect": [1, 1, "w - 1", "h - 3"], "r": 4}, "fill": "#33aa33", "output": "face"}]},
        "dot": {"size": [12, 12], "slice": "none", "layers": [{"shape": {"circle": [6, 6, 5]}, "fill": "#ff0000"}]},
        "shady": {"size": [24, 16], "mode": "shade",
                  "layers": [{"shape": {"rect": [0, 0, "w", "h"], "r": 4}, "fill": {"vgrad": [[0, 0.9], [1, 0.3]]}}]},
    },
}


def _build(tmp_path, spec=SPEC, name="spec.yaml"):
    return build(write_spec(tmp_path, spec, name), out=tmp_path / ("out_" + spec["name"]))


def _project(tmp_path) -> Path:
    (tmp_path / "proj" / "Assets" / "UI").mkdir(parents=True, exist_ok=True)
    return tmp_path / "proj" / "Assets" / "UI" / "Ninekit"


def _files_cs(text: str) -> dict:
    """{asset path: (scale, size_px, slice_px [l, t, r, b] | None)} from NinekitSprites.cs."""
    out = {}
    for m in re.finditer(r'new NinekitFile\(([\d.]+)f, Root \+ "([^"]+)", new Vector2Int\((\d+), (\d+)\), '
                         r'(NinekitInsets\.Zero|new NinekitInsets\(([^)]*)\)), (true|false)\)', text):
        sl = None if m.group(7) == "false" else [int(float(v.strip().rstrip("f"))) for v in m.group(6).split(",")]
        out[m.group(2)] = (float(m.group(1)), [int(m.group(3)), int(m.group(4))], sl)
    return out


def test_export_unity_files(tmp_path, capsys):
    res = _build(tmp_path)
    dest = _project(tmp_path)
    assert main(["export", str(res.manifest_path), "--target", "unity", "-o", str(dest)]) == 0
    assert "wrote" in capsys.readouterr().out
    manifest = json.loads((dest / "demo" / "ninekit.json").read_text())
    assert manifest == json.loads(res.manifest_path.read_text())
    for p in manifest["pieces"].values():
        for per in p["outputs"].values():
            for e in per.values():
                assert (dest / "demo" / e["file"]).read_bytes() == (res.out_dir / e["file"]).read_bytes()
    for rel in ("NinekitSprites.cs", "NinekitTypes.cs", "Editor/NinekitImporter.cs"):
        assert (dest / rel).is_file()
    assert not (dest / "Runtime").exists()                  # the runtime only with --runtime
    get_exporter("unity")(res.manifest_path, dest, runtime=True)
    for rel in ("Runtime/NineSliceStack.cs", "Runtime/NinekitShadeRamp.cs", "Runtime/NinekitShadeRamp.shader"):
        assert (dest / rel).is_file()
        assert "ninekit-unity-adapter" in (dest / rel).read_text().splitlines()[0]
    stack = (dest / "Runtime" / "NineSliceStack.cs").read_text()
    # content is measured from the canvas edges: padding inside the logical rect = max(0, content - overhang)
    assert "l = Mathf.Max(0f, c.Left - o.Left); b = Mathf.Max(0f, c.Bottom - o.Bottom);" in stack
    assert "if (m_Content != null) m_Content.localScale = scale;" in stack      # the content sinks with the face


def test_export_unity_constants(tmp_path):
    res = _build(tmp_path)
    dest = _project(tmp_path)
    get_exporter("unity")(res.manifest_path, dest)
    cs = (dest / "NinekitSprites.cs").read_text()
    assert 'public const string Root = "Assets/UI/Ninekit/";' in cs
    assert "public static class Demo" in cs and 'Manifest = Root + "demo/ninekit.json"' in cs
    manifest = json.loads(res.manifest_path.read_text())
    files = _files_cs(cs)
    n = 0
    for pname, p in manifest["pieces"].items():
        field = _pascal(pname)
        block = cs[cs.index(f"NinekitPiece {field} = "):]
        block = block[:block.index(";\n")]
        assert f'new NinekitPiece("demo", "{pname}"' in block
        # stack order, bottom to top
        assert re.findall(r'new NinekitOutput\("(\w+)"', block) == p["stack"]
        for o, per in p["outputs"].items():
            for sk, e in per.items():
                scale, size_px, slice_px = files["demo/" + e["file"]]
                assert (scale, size_px, slice_px) == (float(sk), e["size_px"], e["slice_px"])
                n += 1
    assert n == len(files) == 2 * (1 + 2 + 1 + 1)
    card = cs[cs.index("NinekitPiece Card = "):]
    assert "content: new NinekitInsets(4f, 3f, 4f, 5f), hasContent: true" in card
    assert "overhang: new NinekitInsets(0f, 0f, 0f, 2f)" in card
    assert "mode: NinekitMode.Shade" in cs[cs.index("NinekitPiece Shady = "):]
    dot = cs[cs.index("NinekitPiece Dot = "):]
    assert "slice: NinekitInsets.Zero, sliced: false" in dot
    assert "Pieces = { Card, Dot, Shady, Tab }" in cs
    # the sprite border order Unity wants: (left, bottom, right, top) from the manifest's [l, t, r, b]
    types = (dest / "NinekitTypes.cs").read_text()
    assert "public Vector4 ToBorder() => new Vector4(Left, Bottom, Right, Top);" in types
    importer = (dest / "Editor" / "NinekitImporter.cs").read_text()
    assert re.search(r"new Vector4\(Convert\.ToSingle\(slice\[0\]\), Convert\.ToSingle\(slice\[3\]\),\s*"
                     r"Convert\.ToSingle\(slice\[2\]\), Convert\.ToSingle\(slice\[1\]\)\)", importer)
    for setting in ("SpriteMeshType.FullRect", "BasePixelsPerUnit * e.Scale", "TextureImporterCompression.Uncompressed",
                    "FilterMode.Bilinear", "TextureWrapMode.Clamp", "TextureImporterNPOTScale.None",
                    "ti.mipmapEnabled, false", "ti.alphaIsTransparency, true", "ti.sRGBTexture, !e.Shade",
                    "context.DependsOnSourceAsset(entry.Manifest)"):
        assert setting in importer, setting
    assert "public const float BasePixelsPerUnit = 100f;" in importer


def test_export_unity_scale(tmp_path):
    res = _build(tmp_path)
    dest = _project(tmp_path)
    get_exporter("unity")(res.manifest_path, dest, scale=3)
    exported = json.loads((dest / "demo" / "ninekit.json").read_text())
    assert exported["scales"] == [3]
    pngs = sorted(p.name for p in (dest / "demo").glob("*.png"))
    assert pngs and all(n.endswith("@3x.png") for n in pngs)
    for p in exported["pieces"].values():
        assert all(list(per) == ["3"] for per in p["outputs"].values())
    assert all(v[0] == 3.0 for v in _files_cs((dest / "NinekitSprites.cs").read_text()).values())
    # a later full export restores the other scale
    get_exporter("unity")(res.manifest_path, dest)
    assert len(list((dest / "demo").glob("*@1x.png"))) == 5
    with pytest.raises(NinekitError, match="scales"):
        get_exporter("unity")(res.manifest_path, dest, scale=2)


def test_export_unity_two_manifests_and_stale_files(tmp_path):
    res = _build(tmp_path)
    other = {**SPEC, "name": "other", "scales": [2], "pieces": {"card": SPEC["pieces"]["card"]}}
    res2 = _build(tmp_path, other, "other.yaml")
    dest = _project(tmp_path)
    get_exporter("unity")(res.manifest_path, dest)
    get_exporter("unity")(res2.manifest_path, dest)
    cs = (dest / "NinekitSprites.cs").read_text()
    assert "public static class Demo" in cs and "public static class Other" in cs
    assert "new NinekitPiece[][] { Demo.Pieces, Other.Pieces }" in cs
    assert (dest / "demo" / "card@1x.png").exists() and (dest / "other" / "card.png").exists()
    # re-export without `dot`: its PNGs (and Unity's .meta files) go, the rest stays
    (dest / "demo" / "dot@1x.png.meta").write_text("guid")
    spec = json.loads(json.dumps(SPEC))
    del spec["pieces"]["dot"]
    res3 = _build(tmp_path, spec, "spec2.yaml")
    get_exporter("unity")(res3.manifest_path, dest)
    assert not (dest / "demo" / "dot@1x.png").exists() and not (dest / "demo" / "dot@1x.png.meta").exists()
    assert (dest / "demo" / "card@1x.png").exists()
    assert "NinekitPiece Dot" not in (dest / "NinekitSprites.cs").read_text()


def test_export_unity_one_folder_per_project(tmp_path):
    res = _build(tmp_path)
    dest = _project(tmp_path)
    get_exporter("unity")(res.manifest_path, dest)
    with pytest.raises(NinekitError, match="already has a ninekit folder: Assets/UI/Ninekit"):
        get_exporter("unity")(res.manifest_path, tmp_path / "proj" / "Assets" / "Elsewhere")


def test_export_unity_outside_project_and_names(tmp_path):
    res = _build(tmp_path)
    dest = tmp_path / "loose"
    get_exporter("unity")(res.manifest_path, dest)
    cs = (dest / "NinekitSprites.cs").read_text()
    assert 'public const string Root = "";' in cs and 'Root + "demo/card@1x.png"' in cs
    bad = {**SPEC, "name": "Editor"}
    res2 = _build(tmp_path, bad, "bad.yaml")
    with pytest.raises(NinekitError, match="Unity folder name"):
        get_exporter("unity")(res2.manifest_path, dest)


def test_export_unity_fixed(tmp_path):
    """`fixed` (DESIGN 2.4): a plain sliced sprite for the importer, NinekitStretch.Fixed in the constants."""
    spec = json.loads(json.dumps(SPEC))
    spec["pieces"]["bar"] = {"size": [30, 12], "stretch": ["stretch", "fixed"],
                             "layers": [{"shape": {"rect": [0, 0, "w", "h"], "r": "h / 2"}, "fill": "#3366cc"}]}
    res = _build(tmp_path, spec)
    piece = json.loads(res.manifest_path.read_text())["pieces"]["bar"]
    assert piece["stretch"] == ["stretch", "fixed"] and piece["slice"] is not None
    dest = _project(tmp_path)
    get_exporter("unity")(res.manifest_path, dest, runtime=True)
    cs = (dest / "NinekitSprites.cs").read_text()
    bar = cs[cs.index("NinekitPiece Bar = "):]
    assert "stretchX: NinekitStretch.Stretch, stretchY: NinekitStretch.Fixed" in bar[:bar.index(";\n")]
    files = _files_cs(cs)
    assert files["demo/bar@3x.png"][2] == piece["outputs"]["main"]["3"]["slice_px"]     # sliced like any other
    assert "public enum NinekitStretch { Stretch, Tile, Fixed }" in (dest / "NinekitTypes.cs").read_text()
    stack = (dest / "Runtime" / "NineSliceStack.cs").read_text()
    assert "piece.StretchY == NinekitStretch.Fixed" in stack and "piece.StretchX == NinekitStretch.Fixed" in stack
    # an unknown stretch value is an error, not a silent stretch
    m = json.loads(res.manifest_path.read_text())
    m["pieces"]["bar"]["stretch"] = ["stretch", "wobble"]
    res.manifest_path.write_text(json.dumps(m))
    with pytest.raises(NinekitError, match="unknown stretch 'wobble'"):
        get_exporter("unity")(res.manifest_path, dest)


def test_identifiers():
    assert _pascal("btn_mint_light") == "BtnMintLight"
    assert _pascal("9lives") == "_9lives"
    assert _pascal("a-b.c") == "ABC"
    assert _unique(["a_b", "aB", "a-b", "root"], {"Root"}) == ["AB", "AB2", "AB3", "Root2"]


# --- compile the C# against an installed Unity (skipped without one) ------------------------------------------------

def _unity_contents():
    env = os.environ.get("NINEKIT_UNITY_EDITOR")      # e.g. /Applications/Unity/Hub/Editor/6000.6.10f1
    roots = [env] if env else sorted(glob.glob("/Applications/Unity/Hub/Editor/*"), reverse=True)
    for r in roots:
        c = Path(r) / "Unity.app" / "Contents"
        if (c / "Resources" / "Scripting" / "Managed" / "UnityEngine" / "UnityEditor.CoreModule.dll").exists():
            return c
    return None


UNITY = _unity_contents()


@pytest.mark.skipif(UNITY is None, reason="no Unity editor installed")
def test_export_unity_compiles(tmp_path):
    scripting = UNITY / "Resources" / "Scripting"
    dotnet = next(iter(glob.glob(str(scripting / "DotNetSdk" / "dotnet"))), None)
    csc = next(iter(sorted(glob.glob(str(scripting / "DotNetSdk" / "sdk" / "*" / "Roslyn" / "bincore" / "csc.dll")))), None)
    ui = sorted(glob.glob(str(UNITY / "Resources" / "PackageManager" / "ProjectTemplates" / "libcache" / "*"
                                     / "ScriptAssemblies" / "UnityEngine.UI.dll")))
    if not (dotnet and csc and ui) or shutil.which(dotnet) is None:
        pytest.skip("this Unity install has no csc / UnityEngine.UI.dll to compile with")
    res = _build(tmp_path)
    dest = _project(tmp_path)
    get_exporter("unity")(res.manifest_path, dest, runtime=True)
    managed = scripting / "Managed" / "UnityEngine"
    refs = [f"-r:{scripting / 'NetStandard' / 'ref' / '2.1.0' / 'netstandard.dll'}", f"-r:{ui[0]}"]
    refs += [f"-r:{p}" for p in sorted(managed.glob("UnityEngine*.dll"))]
    editor_refs = [f"-r:{managed / 'UnityEditor.CoreModule.dll'}", f"-r:{managed / 'UnityEditor.dll'}"]
    common = [dotnet, csc, "-nologo", "-noconfig", "-nostdlib", "-langversion:9", "-target:library", "-warnaserror+",
              "-nowarn:1701,1702"]
    sources = [str(dest / "NinekitTypes.cs"), str(dest / "NinekitSprites.cs"), *map(str, sorted((dest / "Runtime").glob("*.cs")))]
    for define, extra, files, out in (
            ([], [], sources, "rt.dll"),                                          # player build
            (["-define:UNITY_EDITOR"], editor_refs, sources, "rt_editor.dll"),    # editor build
    ):
        r = subprocess.run([*common, *define, *refs, *extra, f"-out:{tmp_path / out}", *files],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([*common, "-define:UNITY_EDITOR", *refs, *editor_refs, f"-r:{tmp_path / 'rt_editor.dll'}",
                        f"-out:{tmp_path / 'ed.dll'}", str(dest / "Editor" / "NinekitImporter.cs")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
