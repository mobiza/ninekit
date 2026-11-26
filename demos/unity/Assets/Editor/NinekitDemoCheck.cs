// Proves ninekit's Unity export in the real editor (run by ../regenerate.sh or by hand):
//   Unity -batchmode -quit -projectPath demos/unity -executeMethod NinekitDemoCheck.Run -logFile -
// (a) every sprite a ninekit.json lists is imported as the manifest says (border, PPU, FullRect mesh, size,
//     filtering) and NinekitSprites.cs agrees; Image.SetNativeSize() gives the size in dp;
// (b) a Canvas with sliced pieces at several sizes, the same piece from @1x and @3x side by side, Gumdrop's
//     frame + face buttons (released and pressed), tiled and shade-ramp pieces;
// (c) renders it to a RenderTexture (2 px per dp) and writes docs/images/unity_demo.png;
// (d) prints PASS / FAIL and exits with 0 / 1.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Ninekit;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

public static class NinekitDemoCheck
{
    const string NinekitFolder = "Assets/UI/Ninekit";
    const int PxPerDp = 2;
    const float CanvasW = 980, CanvasH = 712;
    static readonly Color32 Bg = new Color32(0x3B, 0x42, 0x52, 0xFF);

    static readonly List<string> s_Failures = new List<string>();
    static int s_Checks;
    static Font s_Font;
    static RectTransform s_Root;

    static void Check(bool ok, string what)
    {
        s_Checks++;
        if (!ok) s_Failures.Add(what);
    }

    static void Log(string msg) => Debug.Log("[ninekit] " + msg);

    [MenuItem("Tools/Ninekit/Run Demo Check")]
    public static void Run()
    {
        int code = 1;
        try
        {
            s_Failures.Clear();
            s_Checks = 0;
            s_LabelChecks = 0;
            CheckImports();
            var shot = Arg("-ninekitShot") ??
                       Path.GetFullPath(Path.Combine(Application.dataPath, "../../../docs/images/unity_demo.png"));
            BuildAndRender(shot);
            foreach (var f in s_Failures) Log("FAIL " + f);
            Log(s_Failures.Count == 0
                ? $"PASS: {s_Checks} checks"
                : $"FAIL: {s_Failures.Count} of {s_Checks} checks failed");
            code = s_Failures.Count == 0 ? 0 : 1;
        }
        catch (Exception e)
        {
            Log("FAIL: exception " + e);
        }
        if (Application.isBatchMode) EditorApplication.Exit(code);
    }

    static string Arg(string name)
    {
        var args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    // --- (a) import settings -------------------------------------------------------------------------------

    static void CheckImports()
    {
        var manifests = Directory.GetFiles(NinekitFolder, NinekitImporter.ManifestName, SearchOption.AllDirectories)
            .Select(p => p.Replace('\\', '/')).OrderBy(p => p).ToList();
        Check(manifests.Count == 2, $"expected 2 manifests under {NinekitFolder}, found {manifests.Count}");
        int files = 0;
        foreach (var m in manifests)
        {
            foreach (var e in NinekitImporter.Load(m).Values)
            {
                files++;
                var ti = AssetImporter.GetAtPath(e.File) as TextureImporter;
                var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(e.File);
                if (ti == null || sprite == null)
                {
                    Check(false, $"{e.File}: not imported as a Sprite");
                    continue;
                }
                var s = new TextureImporterSettings();
                ti.ReadTextureSettings(s);
                var tex = sprite.texture;
                Check(ti.textureType == TextureImporterType.Sprite && ti.spriteImportMode == SpriteImportMode.Single,
                    $"{e.File}: type {ti.textureType} / {ti.spriteImportMode}");
                Check(sprite.border == e.Border, $"{e.File}: border {sprite.border} != manifest {e.Border}");
                Check(Mathf.Abs(sprite.pixelsPerUnit - 100f * e.Scale) < 1e-4f,
                    $"{e.File}: PPU {sprite.pixelsPerUnit} != {100f * e.Scale}");
                Check(s.spriteMeshType == SpriteMeshType.FullRect, $"{e.File}: mesh {s.spriteMeshType}");
                Check(tex.width == e.SizePx.x && tex.height == e.SizePx.y && sprite.rect.size == (Vector2)e.SizePx,
                    $"{e.File}: texture {tex.width}x{tex.height} != {e.SizePx}");
                Check(tex.mipmapCount == 1 && tex.filterMode == FilterMode.Bilinear && tex.wrapMode == TextureWrapMode.Clamp,
                    $"{e.File}: mips {tex.mipmapCount}, {tex.filterMode}, {tex.wrapMode}");
                Check(ti.textureCompression == TextureImporterCompression.Uncompressed && !GraphicsFormatUtilityIsCompressed(tex),
                    $"{e.File}: compressed ({tex.format})");
                Check(ti.sRGBTexture == !e.Shade, $"{e.File}: sRGB {ti.sRGBTexture} for mode {(e.Shade ? "shade" : "color")}");
                if (e.Piece == "panel" || e.Piece == "btn_mint" && e.Output == "face" || e.Piece == "badge" && e.Scale == 3)
                    Log($"{e.File}: {e.SizePx.x}x{e.SizePx.y} px, border (l,b,r,t) {sprite.border}, PPU {sprite.pixelsPerUnit}, " +
                        $"mesh {s.spriteMeshType}, native {e.SizePx.x / e.Scale:0.##}x{e.SizePx.y / e.Scale:0.##} dp");
            }
        }
        Log($"{files} files in {manifests.Count} manifests checked against their importer settings");
        CheckManifestEdit();

        // NinekitSprites.cs agrees with the imported sprites
        int listed = 0;
        foreach (var piece in NinekitSprites.All)
            foreach (var o in piece.Stack)
                foreach (var f in o.Files)
                {
                    listed++;
                    var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(f.Path);
                    Check(sprite != null, $"NinekitSprites {piece.Id}/{o.Name}@{f.Scale}: no sprite at {f.Path}");
                    if (sprite == null) continue;
                    Check(sprite.border == (f.Sliced ? f.SlicePx.ToBorder() : Vector4.zero),
                        $"NinekitSprites {f.Path}: border {sprite.border} != {f.SlicePx}");
                    Check(sprite.rect.size == (Vector2)f.SizePx, $"NinekitSprites {f.Path}: size {sprite.rect.size}");
                }
        Check(listed == files, $"NinekitSprites lists {listed} files, the manifests {files}");
    }

    // Editing a ninekit.json re-imports its sprites: change one file's slice_px, refresh, then put it back.
    static void CheckManifestEdit()
    {
        const string manifest = NinekitFolder + "/basics/ninekit.json";
        const string png = NinekitFolder + "/basics/bar_fill@1x.png";
        var original = File.ReadAllText(manifest);
        var rx = new System.Text.RegularExpressions.Regex(
            "(\"file\": \"bar_fill@1x\\.png\",\\s*\"size_px\": \\[[^\\]]*\\],\\s*\"slice_px\": \\[)([^\\]]*)(\\])");
        if (!rx.IsMatch(original))
        {
            Check(false, $"{manifest}: no slice_px for bar_fill@1x.png to edit");
            return;
        }
        var before = AssetDatabase.LoadAssetAtPath<Sprite>(png).border;
        try
        {
            File.WriteAllText(manifest, rx.Replace(original, "${1}4, 3, 5, 2${3}", 1));
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var edited = AssetDatabase.LoadAssetAtPath<Sprite>(png).border;
            Log($"edited {manifest}: bar_fill@1x slice_px [6, 5, 6, 6] -> [4, 3, 5, 2]: border {before} -> {edited}");
            Check(edited == new Vector4(4, 2, 5, 3), $"after editing the manifest, {png} border is {edited}, not (4, 2, 5, 3)");
        }
        finally
        {
            File.WriteAllText(manifest, original);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        }
        var restored = AssetDatabase.LoadAssetAtPath<Sprite>(png).border;
        Check(restored == before, $"after restoring the manifest, {png} border is {restored}, not {before}");
    }

    static bool GraphicsFormatUtilityIsCompressed(Texture2D t) =>
        UnityEngine.Experimental.Rendering.GraphicsFormatUtility.IsCompressedFormat(t.graphicsFormat);

    // --- (b) canvas ----------------------------------------------------------------------------------------

    sealed class Probe
    {
        public string Name;
        public Rect CellDp;           // where to look for the art (top-left origin, dp)
        public Vector2 ExpectSizeDp;  // the art's expected size
    }

    static void BuildAndRender(string shotPath)
    {
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        s_Font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        int pw = (int)CanvasW * PxPerDp, ph = (int)CanvasH * PxPerDp;
        var rt = new RenderTexture(pw, ph, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Default) { antiAliasing = 1 };
        rt.Create();
        var cam = new GameObject("Camera").AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Bg;
        cam.orthographic = true;
        cam.orthographicSize = CanvasH / 2f;   // world units = dp: 2 px per dp
        cam.transform.position = new Vector3(0, 0, -100);
        cam.nearClipPlane = 1;
        cam.farClipPlane = 1000;
        cam.targetTexture = rt;

        // a world-space canvas, 1 unit = 1 dp, centred on the camera
        var canvasGo = new GameObject("Canvas", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
        var canvas = canvasGo.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;
        canvas.worldCamera = cam;
        canvasGo.GetComponent<CanvasScaler>().dynamicPixelsPerUnit = PxPerDp;
        s_Root = (RectTransform)canvasGo.transform;
        s_Root.sizeDelta = new Vector2(CanvasW, CanvasH);
        s_Root.position = Vector3.zero;
        Check(Mathf.Approximately(canvas.referencePixelsPerUnit, 100f), $"canvas reference PPU {canvas.referencePixelsPerUnit}");

        CheckNativeSizes();

        var probes = new List<Probe>();
        var stacks = new List<(NineSliceStack stack, string what)>();
        float y = 10;

        // row 1: sliced pieces at three sizes (@2x files: 1:1 at 2 px per dp)
        Label("sliced at three sizes (@2x files, 1 dp = 2 px)", 14, y);
        y += 20;
        float x = 14;
        foreach (var size in new[] { new Vector2(60, 52), new Vector2(140, 84), new Vector2(230, 112) })
        {
            Img("basics/panel", "main", 2, x, y, size);
            x += size.x + 16;
        }
        x += 14;
        foreach (var size in new[] { new Vector2(52, 50), new Vector2(110, 76), new Vector2(200, 112) })
        {
            Img("basics/scifi", "main", 2, x, y, size);
            x += size.x + 14;
        }
        y += 112 + 18;

        // row 2: pill (y-fixed: plain Images at its natural height), tab (frame + face stack), bars
        x = 14;
        float pillH = NinekitSprites.Basics.Pill.Size.y;
        foreach (var w in new[] { 60f, 120f, 200f })
        {
            Img("basics/pill", "main", 2, x, y, new Vector2(w, pillH));
            x += w + 14;
        }
        x += 10;
        foreach (var size in new[] { new Vector2(40, 34), new Vector2(90, 40), new Vector2(160, 48) })
        {
            stacks.Add((Stack("basics/tab", 2, x, y, size, false), "tab"));
            x += size.x + 14;
        }
        // a y-fixed bar track in a taller box: NineSliceStack keeps its natural height, centred
        var fixedStacks = new List<(NineSliceStack stack, Rect boxDp)>();
        var trackBox = new Rect(x + 4, y + 4, 150, 40);
        Box(trackBox);
        fixedStacks.Add((Stack("basics/bar_track", 2, trackBox.x, trackBox.y, trackBox.size, false), trackBox));
        y += 48 + 14;
        x = 14;
        foreach (var w in new[] { 60f, 150f, 260f })
        {
            Img("basics/bar_track", "main", 2, x, y, new Vector2(w, 16));
            Img("basics/bar_fill", "main", 2, x + 2, y + 2, new Vector2(Mathf.Max(14, (w - 4) * 0.6f), 12));
            x += w + 14;
        }
        y += 16 + 22;

        // row 3: tiled stone, shade art through two ramps, the badge drawn whole
        Label("tiled (stone), shade ramps (one shade art, two ramps), drawn whole (badge); y-fixed pieces in taller boxes (outlined)", 14, y);
        y += 20;
        x = 14;
        var stone = AssetDatabase.LoadAssetAtPath<Sprite>(NinekitSprites.Basics.Stone.Output("main").File(2).Path);
        foreach (var want in new[] { new Vector2(72, 64), new Vector2(170, 100) })
        {
            var size = NineSliceStack.FitWholeTiles(stone, want);   // Tiled cuts the last tile: whole tiles only
            Img("basics/stone", "main", 2, x, y, size, Image.Type.Tiled);
            x += size.x + 16;
        }
        var blueRamp = Ramp(("#0B2246", 0f), ("#1C4E9C", 0.25f), ("#3A93E6", 0.7f), ("#DDF2FF", 1f));
        var orangeRamp = Ramp(("#3D1704", 0f), ("#9C420C", 0.25f), ("#F08A24", 0.7f), ("#FFF2C4", 1f));
        var shadeProbes = new List<(Vector2 centre, bool blue)>();
        foreach (var (size, ramp, blue) in new[] { (new Vector2(70, 34), blueRamp, true), (new Vector2(130, 44), blueRamp, true),
                                                   (new Vector2(70, 34), orangeRamp, false), (new Vector2(130, 44), orangeRamp, false) })
        {
            var s = Stack("basics/shade_button", 2, x, y, size, false);
            var r = s.gameObject.AddComponent<NinekitShadeRamp>();
            r.Ramp = ramp;
            shadeProbes.Add((new Vector2(x + size.x / 2, y + size.y * 0.3f), blue));
            x += size.x + 14;
        }
        Img("basics/badge", "main", 2, x + 6, y, new Vector2(28, 30), Image.Type.Simple);
        var pillBox = new Rect(x + 52, y, 150, 60);
        Box(pillBox);
        var pillStack = Stack("basics/pill", 2, pillBox.x, pillBox.y, pillBox.size, false);
        AddLabel(pillStack, "fixed y");
        fixedStacks.Add((pillStack, pillBox));
        y += 88 + 22;

        // row 4: the same rect from @1x and @3x files
        Label("@1x | @3x, same rect: equal size", 14, y);
        y += 20;
        x = 14;
        foreach (var (id, size) in new[] { ("basics/panel", new Vector2(120, 80)), ("basics/pill", new Vector2(100, 30)),
                                           ("basics/scifi", new Vector2(100, 80)), ("basics/tab", new Vector2(80, 40)) })
        {
            foreach (var scale in new[] { 1f, 3f })
            {
                if (id == "basics/tab")
                {
                    Img(id, "frame", scale, x, y, size);
                    Img(id, "face", scale, x, y, size);
                }
                else Img(id, "main", scale, x, y, size);
                probes.Add(new Probe { Name = $"{id}@{scale}x", CellDp = new Rect(x - 4, y - 4, size.x + 8, size.y + 8), ExpectSizeDp = size });
                x += size.x + 8;
            }
            x += 10;
        }
        y += 80 + 22;

        // row 5: Gumdrop's buttons: frame + face stacked; pressed faces sink towards the body centre
        Label("gumdrop buttons @3x: frame + face (NineSliceStack), released | y-fixed in an 80 dp box | pressed 0.92 (face + label sink together); round ones drawn whole", 14, y);
        y += 20;
        x = 14;
        foreach (var (id, size, pressed) in new[] {
                     ("gumdrop_buttons/btn_mint", new Vector2(128, 59), false),
                     ("gumdrop_buttons/btn_sun", new Vector2(200, 59), false),
                     ("gumdrop_buttons/btn_sky", new Vector2(150, 80), false),     // y-fixed: in a taller (outlined) box
                     ("gumdrop_buttons/btn_berry", new Vector2(150, 59), true) })
        {
            if (size.y > 59) Box(new Rect(x, y, size.x, size.y));
            var s = Stack(id, 3, x, y, size, pressed);
            stacks.Add((s, id));
            AddLabel(s, pressed ? "PRESSED" : "PLAY");
            x += size.x + 16;
        }
        y += 80 + 16;
        x = 14;
        foreach (var (id, pressed) in new[] { ("gumdrop_buttons/btnc_sky", false), ("gumdrop_buttons/btnc_sky", true),
                                              ("gumdrop_buttons/btnc_berry", false), ("gumdrop_buttons/btn_grape", false),
                                              ("gumdrop_buttons/btn_coal", false), ("gumdrop_buttons/btn_cloud", false) })
        {
            var size = id.Contains("btnc") ? new Vector2(62, 59) : new Vector2(110, 59);
            var s = Stack(id, 3, x, y, size, pressed);
            stacks.Add((s, id));
            if (id.Contains("btnc")) AddLabel(s, "i");
            x += size.x + 16;
        }
        Img("gumdrop_buttons/btnc_berry", "main", 3, x, y, new Vector2(62, 62), Image.Type.Simple);
        x += 62 + 6;
        Label("<- btnc_berry main (composite)", x, y + 24);

        CheckStacks(stacks);
        CheckFixed(fixedStacks);

        // render
        Canvas.ForceUpdateCanvases();
        cam.Render();
        var grab = new Texture2D(pw, ph, TextureFormat.RGBA32, false, false);
        var prev = RenderTexture.active;
        RenderTexture.active = rt;
        grab.ReadPixels(new Rect(0, 0, pw, ph), 0, 0);
        grab.Apply();
        RenderTexture.active = prev;
        var px = grab.GetPixels32();
        Check(px.Any(c => !Same(c, Bg, 0)), "the render is empty (only the background)");

        // (b) measured: @1x and @3x cover the same pixels; corners map 1:1; ramps colour the shade art
        for (int i = 0; i + 1 < probes.Count; i += 2)
        {
            var a = Bounds(px, pw, ph, probes[i].CellDp);
            var b = Bounds(px, pw, ph, probes[i + 1].CellDp);
            var want = probes[i].ExpectSizeDp * PxPerDp;
            Log($"{probes[i].Name}: {a.width}x{a.height} px, {probes[i + 1].Name}: {b.width}x{b.height} px (rect {want.x}x{want.y} px)");
            // within 1 dp: @1x anti-aliases over a whole dp, @3x over a third
            Check(Mathf.Abs(a.width - b.width) <= PxPerDp && Mathf.Abs(a.height - b.height) <= PxPerDp,
                $"{probes[i].Name} {a.size} vs {probes[i + 1].Name} {b.size}: not the same size");
            Check(a.width <= want.x + 1 && a.height <= want.y + 1, $"{probes[i].Name}: drawn {a.size} outside its rect {want}");
            // corners of the same dp size: the two renders match pixel for pixel up to resolution (a wrong PPU
            // would draw one scale's corners 3x larger)
            float diff = MeanDiff(px, pw, ph, probes[i].CellDp, probes[i + 1].CellDp);
            Log($"{probes[i].Name} vs @3x: mean difference {diff:0.00}/255");
            Check(diff < 6f, $"{probes[i].Name} vs {probes[i + 1].Name}: mean difference {diff:0.00}/255");
        }
        CheckCorners(px, pw, ph);
        foreach (var (fs, box) in fixedStacks)
        {
            var inner = new Rect(box.x + 2, box.y + 2, box.width - 4, box.height - 4);   // inside the outline
            var drawn = Bounds(px, pw, ph, inner);
            float natural = fs.Descriptor.Size.y * PxPerDp;
            float offCentre = drawn.center.y - (box.y + box.height / 2) * PxPerDp;
            Log($"{fs.Piece} (y-fixed) in a {box.width}x{box.height} dp box: drawn {drawn.height} px tall " +
                $"(natural {natural} px), centre {offCentre:0.#} px off the box centre");
            Check(Mathf.Abs(drawn.height - natural) <= 2 && Mathf.Abs(offCentre) <= 1,
                $"{fs.Piece}: drawn {drawn.height} px tall, {offCentre} px off centre (natural {natural} px)");
        }
        foreach (var (centre, blue) in shadeProbes)
        {
            var c = At(px, pw, ph, centre);
            Check(blue ? c.b > c.r + 40 : c.r > c.b + 40, $"shade ramp at {centre}: {c} is not {(blue ? "blue" : "orange")}");
        }

        // (c) the screenshot
        Directory.CreateDirectory(Path.GetDirectoryName(shotPath));
        File.WriteAllBytes(shotPath, grab.EncodeToPNG());
        Log($"wrote {shotPath} ({pw}x{ph})");
        cam.targetTexture = null;
        rt.Release();
    }

    // Image.SetNativeSize() of every sprite: its size in dp (size_px / scale).
    static void CheckNativeSizes()
    {
        var go = new GameObject("native", typeof(RectTransform), typeof(Image));
        go.transform.SetParent(s_Root, false);
        var img = go.GetComponent<Image>();
        int n = 0;
        foreach (var piece in NinekitSprites.All)
            foreach (var o in piece.Stack)
                foreach (var f in o.Files)
                {
                    img.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(f.Path);
                    if (img.sprite == null) continue;
                    img.SetNativeSize();
                    var got = ((RectTransform)go.transform).sizeDelta;
                    Check((got - f.Size).magnitude < 1e-3f, $"SetNativeSize {f.Path}: {got} != {f.Size} dp");
                    n++;
                }
        Log($"SetNativeSize gives size_px / scale dp for {n} sprites (e.g. basics/panel@3x -> {NinekitSprites.Basics.Panel.Output("main").File(3).Size})");
        UnityEngine.Object.DestroyImmediate(go);
    }

    // Frame and face share their rect when released; pressed, the face is the rect scaled by 0.92 around the body centre.
    static void CheckStacks(List<(NineSliceStack stack, string what)> stacks)
    {
        foreach (var (s, what) in stacks)
        {
            var piece = s.Descriptor;
            Check(piece != null && s.Layers.Count == piece.Layers.Length && s.Layers.All(l => l.sprite != null),
                $"{what}: stack has {s.Layers.Count} layers / missing sprites");
            if (piece == null || s.Layers.Count < 2) continue;
            var body = (RectTransform)s.transform;
            var frame = Corners(s.Layers[0].rectTransform);
            var face = Corners(s.Layers[s.Layers.Count - 1].rectTransform);
            var o = piece.Overhang;
            var b = Corners(body);
            // the art: the body plus the overhang; on a fixed axis its natural length, body part centred on the body
            var natural = piece.Layers[0].File(s.Scale).Size;
            float ax0 = b.xMin - o.Left, ax1 = b.xMax + o.Right, ay0 = b.yMin - o.Bottom, ay1 = b.yMax + o.Top;
            if (piece.StretchX == NinekitStretch.Fixed)
            {
                ax0 = b.xMin + (b.width - (natural.x - o.Left - o.Right)) / 2 - o.Left;
                ax1 = ax0 + natural.x;
            }
            if (piece.StretchY == NinekitStretch.Fixed)
            {
                ay0 = b.yMin + (b.height - (natural.y - o.Bottom - o.Top)) / 2 - o.Bottom;
                ay1 = ay0 + natural.y;
            }
            var art = Rect.MinMaxRect(ax0, ay0, ax1, ay1);
            Check(Near(frame, art), $"{what}: frame {frame} != the art rect {art} (stretch {piece.StretchX}/{piece.StretchY})");
            if (piece.StretchY == NinekitStretch.Fixed && b.height > natural.y - o.Bottom - o.Top + 1e-3f)
                Log($"{what} (y-fixed) in a {b.width:0.##}x{b.height:0.##} dp box: frame {frame.width:0.##}x{frame.height:0.##} dp, " +
                    $"centred (dy {(frame.yMin + o.Bottom + frame.yMax - o.Top) / 2 - b.center.y:0.###})");
            float k = s.Pressed ? s.PressScale : 1f;
            var c = b.center;
            var want = Rect.MinMaxRect(c.x + (art.xMin - c.x) * k, c.y + (art.yMin - c.y) * k,
                                       c.x + (art.xMax - c.x) * k, c.y + (art.yMax - c.y) * k);
            Check(Near(face, want), $"{what}: face {face} != {want} (pressed {s.Pressed})");
            // the label sits on the content area and sinks with the face: same scale, same centre
            var label = s.Content.GetComponentInChildren<Text>();
            if (label == null) continue;
            // content is measured from the canvas edges: padding inside the body = max(0, content - overhang)
            var c0 = piece.HasContent ? piece.Content : NinekitInsets.Zero;
            var pad = new NinekitInsets(Mathf.Max(0, c0.Left - o.Left), Mathf.Max(0, c0.Top - o.Top),
                                        Mathf.Max(0, c0.Right - o.Right), Mathf.Max(0, c0.Bottom - o.Bottom));
            var content = Rect.MinMaxRect(b.xMin + pad.Left, b.yMin + pad.Bottom, b.xMax - pad.Right, b.yMax - pad.Top);
            var wantLabel = Rect.MinMaxRect(c.x + (content.xMin - c.x) * k, c.y + (content.yMin - c.y) * k,
                                            c.x + (content.xMax - c.x) * k, c.y + (content.yMax - c.y) * k);
            var got = Corners(label.rectTransform);
            Check(Near(got, wantLabel), $"{what}: label {got} != content scaled with the face {wantLabel} (pressed {s.Pressed})");
            s_LabelChecks++;
            if (what == "gumdrop_buttons/btn_mint")   // the supervisor's worked example, measured
            {
                var cr = Corners(s.Content);
                var measured = new NinekitInsets(cr.xMin - b.xMin, b.yMax - cr.yMax, b.xMax - cr.xMax, cr.yMin - b.yMin);
                float centreBelowTop = art.yMax - got.center.y;
                Log($"{what}: body {b.width:0.##}x{b.height:0.##} dp (canvas {art.width:0.##}x{art.height:0.##}), " +
                    $"content padding (l,t,r,b) {measured.Left:0.##}, {measured.Top:0.##}, {measured.Right:0.##}, {measured.Bottom:0.##}, " +
                    $"label centre {centreBelowTop:0.##} dp below the canvas top");
                Check(Mathf.Abs(b.height - 59f) < 1e-3f && Mathf.Abs(art.height - 62f) < 1e-3f, $"{what}: body {b.size}, canvas {art.size}");
                Check(Mathf.Abs(measured.Left - 12f) < 1e-3f && Mathf.Abs(measured.Top - 8f) < 1e-3f &&
                      Mathf.Abs(measured.Right - 12f) < 1e-3f && Mathf.Abs(measured.Bottom - 14f) < 1e-3f,
                    $"{what}: content padding {measured}, not (12, 8, 12, 14)");
                Check(Mathf.Abs(centreBelowTop - 26.5f) < 1e-3f, $"{what}: label centre {centreBelowTop} dp below the top, not 26.5");
            }
            if (s.Pressed)
                Log($"{what} pressed: face {face.width:0.##}x{face.height:0.##} dp, label {got.width:0.##}x{got.height:0.##} dp " +
                    $"(content {content.width:0.##}x{content.height:0.##} x {k})");
        }
        Check(s_LabelChecks >= 4, $"only {s_LabelChecks} labels checked");
    }

    static int s_LabelChecks;

    // A fixed axis keeps the art's natural length, centred on the box; the content still lays out in the box.
    static void CheckFixed(List<(NineSliceStack stack, Rect boxDp)> fixedStacks)
    {
        foreach (var (s, _) in fixedStacks)
        {
            var piece = s.Descriptor;
            var box = Corners((RectTransform)s.transform);
            var art = Corners(s.Layers[0].rectTransform);
            var natural = piece.Layers[0].File(s.Scale).Size;
            var o = piece.Overhang;
            Check(piece.StretchY == NinekitStretch.Fixed, $"{piece.Id}: stretch y is {piece.StretchY}, not Fixed");
            Check(Mathf.Abs(art.height - natural.y) < 1e-3f, $"{piece.Id}: art {art.height} dp tall in a {box.height} dp box, natural {natural.y}");
            Check(Mathf.Abs(art.width - (box.width + o.Left + o.Right)) < 1e-3f, $"{piece.Id}: art {art.width} dp wide, box {box.width}");
            Check(Mathf.Abs(art.center.y - box.center.y) < 1e-3f, $"{piece.Id}: art centre {art.center.y}, box centre {box.center.y}");
            var c0 = piece.HasContent ? piece.Content : NinekitInsets.Zero;
            var content = Corners(s.Content);
            var want = Rect.MinMaxRect(box.xMin + Mathf.Max(0, c0.Left - o.Left), box.yMin + Mathf.Max(0, c0.Bottom - o.Bottom),
                                       box.xMax - Mathf.Max(0, c0.Right - o.Right), box.yMax - Mathf.Max(0, c0.Top - o.Top));
            Check(Near(content, want), $"{piece.Id}: content {content} != the box padded {want}");
            Log($"{piece.Id} (stretch {piece.StretchX}/{piece.StretchY}) in a {box.width:0.##}x{box.height:0.##} dp box: " +
                $"art {art.width:0.##}x{art.height:0.##} dp, centred (dy {art.center.y - box.center.y:0.###}), " +
                $"content {content.width:0.##}x{content.height:0.##} dp");
        }
        Check(fixedStacks.Count >= 2, "no y-fixed stacks checked");
    }

    static void Box(Rect dp)
    {
        var c = new Color(1, 1, 1, 0.45f);
        foreach (var r in new[] { new Rect(dp.x, dp.y, dp.width, 1), new Rect(dp.x, dp.yMax - 1, dp.width, 1),
                                  new Rect(dp.x, dp.y, 1, dp.height), new Rect(dp.xMax - 1, dp.y, 1, dp.height) })
            Place("box", r.x, r.y, r.size).gameObject.AddComponent<Image>().color = c;
    }

    // The @2x panel's corner slices land 1:1 on screen pixels: identical to the PNG over the background.
    static void CheckCorners(Color32[] px, int pw, int ph)
    {
        var f = NinekitSprites.Basics.Panel.Output("main").File(2);
        var png = new Texture2D(2, 2, TextureFormat.RGBA32, false, false);
        png.LoadImage(File.ReadAllBytes(f.Path));
        var src = png.GetPixels32();
        // the 140 x 84 panel of row 1 sits at (14 + 60 + 16, 30) dp
        int x0 = (14 + 60 + 16) * PxPerDp, yTop = 30 * PxPerDp;
        int w = 140 * PxPerDp, h = 84 * PxPerDp;
        int l = (int)f.SlicePx.Left, t = (int)f.SlicePx.Top, r = (int)f.SlicePx.Right, b = (int)f.SlicePx.Bottom;
        int worst = 0;
        void Compare(int sx0, int sy0, int dx0, int dy0, int cw, int chh)
        {
            for (int j = 0; j < chh; j++)
                for (int i = 0; i < cw; i++)
                {
                    var s = src[(png.height - 1 - (sy0 + j)) * png.width + sx0 + i];     // PNG rows from the top
                    var d = px[(ph - 1 - (dy0 + j)) * pw + dx0 + i];
                    var want = Over(s, Bg);
                    worst = Mathf.Max(worst, Mathf.Abs(want.r - d.r), Mathf.Abs(want.g - d.g), Mathf.Abs(want.b - d.b));
                }
        }
        Compare(0, 0, x0, yTop, l, t);                                            // top-left
        Compare(png.width - r, png.height - b, x0 + w - r, yTop + h - b, r, b);    // bottom-right
        Log($"panel@2x corners vs the PNG on screen: max difference {worst}/255 ({l}x{t} and {r}x{b} px)");
        Check(worst <= 2, $"panel@2x corners differ from the PNG by {worst}/255");
    }

    // --- helpers -------------------------------------------------------------------------------------------

    static RectTransform Place(string name, float x, float y, Vector2 size)
    {
        var go = new GameObject(name, typeof(RectTransform));
        var rt = (RectTransform)go.transform;
        rt.SetParent(s_Root, false);
        rt.anchorMin = rt.anchorMax = new Vector2(0, 1);
        rt.pivot = new Vector2(0, 1);
        rt.anchoredPosition = new Vector2(x, -y);
        rt.sizeDelta = size;
        return rt;
    }

    static Image Img(string id, string output, float scale, float x, float y, Vector2 size, Image.Type type = Image.Type.Sliced)
    {
        var file = NinekitSprites.Find(id).Output(output).File(scale);
        var img = Place($"{id}/{output}@{scale}", x, y, size).gameObject.AddComponent<Image>();
        img.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(file.Path);
        img.type = type;
        return img;
    }

    static NineSliceStack Stack(string id, float scale, float x, float y, Vector2 size, bool pressed)
    {
        var s = Place(id, x, y, size).gameObject.AddComponent<NineSliceStack>();
        s.Scale = scale;
        s.Piece = id;
        s.SetPressed(pressed, true);
        return s;
    }

    static void AddLabel(NineSliceStack s, string text)
    {
        var t = new GameObject("label", typeof(RectTransform)).AddComponent<Text>();
        t.transform.SetParent(s.transform, false);
        s.FitToContent(t.rectTransform);
        t.font = s_Font;
        t.fontSize = 20;
        t.fontStyle = FontStyle.Bold;
        t.alignment = TextAnchor.MiddleCenter;
        t.color = new Color32(0xF8, 0xF0, 0xCA, 0xFF);
        t.raycastTarget = false;
        t.text = text;
        t.gameObject.AddComponent<Outline>().effectColor = new Color(0, 0, 0, 0.6f);
    }

    static void Label(string text, float x, float y)
    {
        var t = Place("label", x, y, new Vector2(CanvasW - x - 10, 18)).gameObject.AddComponent<Text>();
        t.font = s_Font;
        t.fontSize = 13;
        t.color = new Color32(0xE5, 0xE9, 0xF0, 0xFF);
        t.text = text;
    }

    static Gradient Ramp(params (string hex, float t)[] keys)
    {
        var g = new Gradient
        {
            colorKeys = keys.Select(k => new GradientColorKey(ColorUtility.TryParseHtmlString(k.hex, out var c) ? c : Color.magenta, k.t)).ToArray(),
            alphaKeys = new[] { new GradientAlphaKey(1, 0), new GradientAlphaKey(1, 1) },
        };
        return g;
    }

    static Rect Corners(RectTransform rt)
    {
        var w = new Vector3[4];
        rt.GetWorldCorners(w);
        return Rect.MinMaxRect(w[0].x, w[0].y, w[2].x, w[2].y);
    }

    static bool Near(Rect a, Rect b) =>
        Mathf.Abs(a.xMin - b.xMin) < 1e-3f && Mathf.Abs(a.yMin - b.yMin) < 1e-3f &&
        Mathf.Abs(a.xMax - b.xMax) < 1e-3f && Mathf.Abs(a.yMax - b.yMax) < 1e-3f;

    static bool Same(Color32 a, Color32 b, int tol) =>
        Mathf.Abs(a.r - b.r) <= tol && Mathf.Abs(a.g - b.g) <= tol && Mathf.Abs(a.b - b.b) <= tol;

    static Color32 Over(Color32 s, Color32 bg)
    {
        float a = s.a / 255f;
        return new Color32((byte)Mathf.RoundToInt(s.r * a + bg.r * (1 - a)), (byte)Mathf.RoundToInt(s.g * a + bg.g * (1 - a)),
                           (byte)Mathf.RoundToInt(s.b * a + bg.b * (1 - a)), 255);
    }

    static Color32 At(Color32[] px, int pw, int ph, Vector2 dp)
    {
        int x = Mathf.FloorToInt(dp.x * PxPerDp), y = Mathf.FloorToInt(dp.y * PxPerDp);
        return px[(ph - 1 - y) * pw + x];
    }

    // Mean RGB difference of two equally sized cells (dp, top-left origin).
    static float MeanDiff(Color32[] px, int pw, int ph, Rect a, Rect b)
    {
        int ax = Mathf.RoundToInt(a.xMin * PxPerDp), ay = Mathf.RoundToInt(a.yMin * PxPerDp);
        int bx = Mathf.RoundToInt(b.xMin * PxPerDp), by = Mathf.RoundToInt(b.yMin * PxPerDp);
        int w = Mathf.RoundToInt(a.width * PxPerDp), h = Mathf.RoundToInt(a.height * PxPerDp);
        double sum = 0;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                var p = px[(ph - 1 - (ay + y)) * pw + ax + x];
                var q = px[(ph - 1 - (by + y)) * pw + bx + x];
                sum += Mathf.Abs(p.r - q.r) + Mathf.Abs(p.g - q.g) + Mathf.Abs(p.b - q.b);
            }
        return (float)(sum / (3.0 * w * h));
    }

    // The pixel bounds (top-left origin) of everything that is not background inside [cellDp].
    static Rect Bounds(Color32[] px, int pw, int ph, Rect cellDp)
    {
        int x0 = Mathf.FloorToInt(cellDp.xMin * PxPerDp), x1 = Mathf.CeilToInt(cellDp.xMax * PxPerDp);
        int y0 = Mathf.FloorToInt(cellDp.yMin * PxPerDp), y1 = Mathf.CeilToInt(cellDp.yMax * PxPerDp);
        int minX = int.MaxValue, minY = int.MaxValue, maxX = -1, maxY = -1;
        for (int y = y0; y < y1; y++)
            for (int x = x0; x < x1; x++)
            {
                if (Same(px[(ph - 1 - y) * pw + x], Bg, 6)) continue;
                minX = Mathf.Min(minX, x); maxX = Mathf.Max(maxX, x);
                minY = Mathf.Min(minY, y); maxY = Mathf.Max(maxY, y);
            }
        return maxX < 0 ? Rect.zero : Rect.MinMaxRect(minX, minY, maxX + 1, maxY + 1);
    }
}
