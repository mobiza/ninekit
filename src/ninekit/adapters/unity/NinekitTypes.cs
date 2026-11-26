// ninekit-unity-adapter: written by `ninekit export --target unity`; edits are overwritten by the next export.
// The descriptor types of NinekitSprites.cs (generated from ninekit.json, schema 1).
using UnityEngine;

namespace Ninekit
{
    /// <summary>colour art, or shade art (R = G = B = shade, mapped through a colour ramp at runtime).</summary>
    public enum NinekitMode { Color, Shade }

    /// <summary>How an axis' middle fills a larger rect. Fixed: the axis keeps its natural length (its middle is
    /// one grid step); a plain sliced Image would stretch it, NineSliceStack draws it at that length, centred.</summary>
    public enum NinekitStretch { Stretch, Tile, Fixed }

    /// <summary>Insets by edge name (dp or texture px, as the field holding it says).</summary>
    public readonly struct NinekitInsets
    {
        public readonly float Left, Top, Right, Bottom;

        public NinekitInsets(float left, float top, float right, float bottom)
        {
            Left = left; Top = top; Right = right; Bottom = bottom;
        }

        public static readonly NinekitInsets Zero = new NinekitInsets(0, 0, 0, 0);

        public bool IsZero => Left == 0 && Top == 0 && Right == 0 && Bottom == 0;

        /// <summary>Sprite.border order: (left, bottom, right, top).</summary>
        public Vector4 ToBorder() => new Vector4(Left, Bottom, Right, Top);

        public RectOffset ToRectOffset() =>
            new RectOffset(Mathf.RoundToInt(Left), Mathf.RoundToInt(Right), Mathf.RoundToInt(Top), Mathf.RoundToInt(Bottom));

        public override string ToString() => $"(l {Left}, t {Top}, r {Right}, b {Bottom})";
    }

    /// <summary>One PNG: one output of a piece at one scale.</summary>
    public sealed class NinekitFile
    {
        /// <summary>Texture px per dp.</summary>
        public readonly float Scale;
        /// <summary>AssetDatabase path (Assets/...), for AssetDatabase.LoadAssetAtPath&lt;Sprite&gt;.</summary>
        public readonly string Path;
        public readonly Vector2Int SizePx;
        /// <summary>Texture px; Zero when the piece is drawn whole.</summary>
        public readonly NinekitInsets SlicePx;
        public readonly bool Sliced;

        public NinekitFile(float scale, string path, Vector2Int sizePx, NinekitInsets slicePx, bool sliced)
        {
            Scale = scale; Path = path; SizePx = sizePx; SlicePx = slicePx; Sliced = sliced;
        }

        /// <summary>The file's size in dp: what Image.SetNativeSize() gives (pixelsPerUnit 100 x scale).</summary>
        public Vector2 Size => new Vector2(SizePx.x / Scale, SizePx.y / Scale);
    }

    /// <summary>One image of a piece (main, frame, face...) at every exported scale.</summary>
    public sealed class NinekitOutput
    {
        public readonly string Name;
        /// <summary>Ascending scale.</summary>
        public readonly NinekitFile[] Files;

        public NinekitOutput(string name, NinekitFile[] files)
        {
            Name = name; Files = files;
        }

        /// <summary>The file at [scale]; else the smallest above it; else the largest. 0 = the largest.</summary>
        public NinekitFile File(float scale = 0)
        {
            if (Files.Length == 0) return null;
            if (scale > 0)
                foreach (var f in Files)
                    if (f.Scale >= scale - 1e-4f) return f;
            return Files[Files.Length - 1];
        }
    }

    /// <summary>A ninekit piece: sizes in dp, outputs bottom to top.</summary>
    public sealed class NinekitPiece
    {
        /// <summary>"manifest/piece".</summary>
        public readonly string Id;
        public readonly string Manifest, Name;
        /// <summary>dp, from the largest scale (other scales may differ by rounding / compaction).</summary>
        public readonly Vector2 Size;
        public readonly NinekitInsets Slice;
        public readonly bool Sliced;
        public readonly NinekitStretch StretchX, StretchY;
        public readonly NinekitMode Mode;
        /// <summary>dp insets for labels / children; see HasContent.</summary>
        public readonly NinekitInsets Content;
        public readonly bool HasContent;
        /// <summary>dp the art reaches outside the logical rect (shadows); Zero when none.</summary>
        public readonly NinekitInsets Overhang;
        /// <summary>Outputs bottom to top as the manifest lists them (may end with the composite "main").</summary>
        public readonly NinekitOutput[] Stack;

        public NinekitPiece(string manifest, string name, Vector2 size, NinekitInsets slice, bool sliced,
            NinekitStretch stretchX, NinekitStretch stretchY, NinekitMode mode,
            NinekitInsets content, bool hasContent, NinekitInsets overhang, NinekitOutput[] stack)
        {
            Manifest = manifest; Name = name; Id = manifest + "/" + name;
            Size = size; Slice = slice; Sliced = sliced; StretchX = stretchX; StretchY = stretchY; Mode = mode;
            Content = content; HasContent = hasContent; Overhang = overhang; Stack = stack;
        }

        /// <summary>The images a runtime stacks, bottom to top: Stack without the composite "main" when it
        /// sits next to named outputs (it is their alternative, not a layer).</summary>
        public NinekitOutput[] Layers
        {
            get
            {
                if (Stack.Length < 2) return Stack;
                var list = new System.Collections.Generic.List<NinekitOutput>();
                foreach (var o in Stack)
                    if (o.Name != "main") list.Add(o);
                return list.Count > 0 ? list.ToArray() : Stack;
            }
        }

        /// <summary>The output named [name], or null.</summary>
        public NinekitOutput Output(string name)
        {
            foreach (var o in Stack)
                if (o.Name == name) return o;
            return null;
        }

        /// <summary>Whether the runtime should tile (any tile axis: a stretch axis has identical middle lines,
        /// so tiling it looks the same as stretching it).</summary>
        public bool Tiled => StretchX == NinekitStretch.Tile || StretchY == NinekitStretch.Tile;

        public override string ToString() => Id;
    }
}
