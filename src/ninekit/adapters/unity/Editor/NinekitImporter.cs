// ninekit-unity-adapter: written by `ninekit export --target unity`; edits are overwritten by the next export.
// Imports every PNG a ninekit.json lists (the nearest one in its folder or above) as a 9-sliced UI Sprite.
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Ninekit
{
    /// <summary>
    /// For a PNG listed by a ninekit.json (schema 1): Sprite, single, FullRect mesh, spriteBorder from slice_px
    /// (x = left, y = bottom, z = right, w = top), pixelsPerUnit = BasePixelsPerUnit x scale, no mipmaps,
    /// bilinear, clamp, uncompressed, alpha is transparency, no NPOT scaling; shade art (mode: shade) is
    /// imported linear so a ramp shader reads the stored shade. The texture depends on the manifest: editing
    /// or re-exporting ninekit.json re-imports it.
    /// </summary>
    public sealed class NinekitImporter : AssetPostprocessor
    {
        /// <summary>Sprite px per Unity unit at scale 1. With a Canvas reference PPU of 100 (the default),
        /// Image.SetNativeSize() then gives a file's size in dp at every scale.</summary>
        public const float BasePixelsPerUnit = 100f;

        public const string ManifestName = "ninekit.json";

        /// <summary>Bump when the settings below change, so Unity re-imports the sprites.</summary>
        public override uint GetVersion() => 1;

        /// <summary>One PNG of a manifest.</summary>
        public sealed class Entry
        {
            public string Manifest;   // asset path of the ninekit.json
            public string File;       // asset path of the PNG
            public string Piece, Output;
            public float Scale;
            public Vector2Int SizePx;
            public Vector4 Border;    // sprite border order (l, b, r, t); zero when drawn whole
            public bool Sliced, Shade;
        }

        void OnPreprocessTexture()
        {
            if (!assetPath.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) return;
            var entry = Find(assetPath);
            if (entry == null) return;
            context.DependsOnSourceAsset(entry.Manifest);
            Apply((TextureImporter)assetImporter, entry);
        }

        // A manifest imported after its PNGs (or edited): re-import the PNGs whose settings differ.
        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            foreach (var path in imported)
            {
                if (!IsManifest(path)) continue;
                foreach (var e in Load(path).Values)
                {
                    var ti = AssetImporter.GetAtPath(e.File) as TextureImporter;
                    if (ti != null && !Matches(ti, e))
                        AssetDatabase.ImportAsset(e.File, ImportAssetOptions.ForceUpdate);
                }
            }
        }

        static bool IsManifest(string path) =>
            path.EndsWith("/" + ManifestName, StringComparison.Ordinal) || path == ManifestName;

        /// <summary>The entry of the PNG at [pngPath] in the nearest ninekit.json that lists it, or null.</summary>
        public static Entry Find(string pngPath)
        {
            pngPath = pngPath.Replace('\\', '/');
            for (var dir = Parent(pngPath); !string.IsNullOrEmpty(dir); dir = Parent(dir))
            {
                var manifest = dir + "/" + ManifestName;
                if (!System.IO.File.Exists(manifest)) continue;
                if (Load(manifest).TryGetValue(pngPath, out var e)) return e;
            }
            return null;
        }

        static string Parent(string path)
        {
            int i = path.LastIndexOf('/');
            return i <= 0 ? null : path.Substring(0, i);
        }

        /// <summary>Sets the importer to the entry's settings; true if anything changed.</summary>
        public static bool Apply(TextureImporter ti, Entry e) => Configure(ti, e, true);

        /// <summary>Whether the importer already has the entry's settings.</summary>
        public static bool Matches(TextureImporter ti, Entry e) => !Configure(ti, e, false);

        static bool Configure(TextureImporter ti, Entry e, bool write)
        {
            bool changed = false;
            void Set<T>(T current, T wanted, Action<T> set)
            {
                if (EqualityComparer<T>.Default.Equals(current, wanted)) return;
                changed = true;
                if (write) set(wanted);
            }
            int maxSize = Mathf.Clamp(Mathf.NextPowerOfTwo(Mathf.Max(e.SizePx.x, e.SizePx.y)), 2048, 16384);
            Set(ti.textureType, TextureImporterType.Sprite, v => ti.textureType = v);
            Set(ti.spriteImportMode, SpriteImportMode.Single, v => ti.spriteImportMode = v);
            Set(ti.spriteBorder, e.Border, v => ti.spriteBorder = v);
            Set(ti.spritePixelsPerUnit, BasePixelsPerUnit * e.Scale, v => ti.spritePixelsPerUnit = v);
            Set(ti.mipmapEnabled, false, v => ti.mipmapEnabled = v);
            Set(ti.filterMode, FilterMode.Bilinear, v => ti.filterMode = v);
            Set(ti.wrapMode, TextureWrapMode.Clamp, v => ti.wrapMode = v);
            Set(ti.alphaSource, TextureImporterAlphaSource.FromInput, v => ti.alphaSource = v);
            Set(ti.alphaIsTransparency, true, v => ti.alphaIsTransparency = v);
            Set(ti.npotScale, TextureImporterNPOTScale.None, v => ti.npotScale = v);
            Set(ti.sRGBTexture, !e.Shade, v => ti.sRGBTexture = v);
            Set(ti.isReadable, false, v => ti.isReadable = v);
            Set(ti.textureCompression, TextureImporterCompression.Uncompressed, v => ti.textureCompression = v);
            Set(ti.maxTextureSize, maxSize, v => ti.maxTextureSize = v);

            var s = new TextureImporterSettings();
            ti.ReadTextureSettings(s);
            bool settingsChanged = false;
            if (s.spriteMeshType != SpriteMeshType.FullRect) { s.spriteMeshType = SpriteMeshType.FullRect; settingsChanged = true; }
            if (s.spriteAlignment != (int)SpriteAlignment.Center) { s.spriteAlignment = (int)SpriteAlignment.Center; settingsChanged = true; }
            if (s.spriteGenerateFallbackPhysicsShape) { s.spriteGenerateFallbackPhysicsShape = false; settingsChanged = true; }
            if (settingsChanged)
            {
                changed = true;
                if (write) ti.SetTextureSettings(s);
            }
            return changed;
        }

        // --- manifest ----------------------------------------------------------------------------------------

        static readonly Dictionary<string, (DateTime time, long length, Dictionary<string, Entry> map)> s_Cache =
            new Dictionary<string, (DateTime, long, Dictionary<string, Entry>)>();

        /// <summary>Every PNG of the manifest at [manifestPath] by asset path (cached until the file changes).</summary>
        public static Dictionary<string, Entry> Load(string manifestPath)
        {
            var info = new FileInfo(manifestPath);
            if (!info.Exists) return new Dictionary<string, Entry>();
            lock (s_Cache)
            {
                if (s_Cache.TryGetValue(manifestPath, out var c) && c.time == info.LastWriteTimeUtc && c.length == info.Length)
                    return c.map;
            }
            var map = new Dictionary<string, Entry>();
            try
            {
                Parse(manifestPath, System.IO.File.ReadAllText(manifestPath, Encoding.UTF8), map);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"ninekit: cannot read {manifestPath}: {ex.Message}");
            }
            lock (s_Cache) s_Cache[manifestPath] = (info.LastWriteTimeUtc, info.Length, map);
            return map;
        }

        static void Parse(string manifestPath, string text, Dictionary<string, Entry> map)
        {
            var root = MiniJson.Parse(text) as Dictionary<string, object>;
            if (root == null || !(root.TryGetValue("ninekit", out var schema) && Convert.ToInt32(schema) == 1))
                throw new FormatException("not a ninekit manifest (schema 1)");
            var dir = Parent(manifestPath.Replace('\\', '/'));
            var pieces = (Dictionary<string, object>)root["pieces"];
            foreach (var piece in pieces)
            {
                var p = (Dictionary<string, object>)piece.Value;
                bool shade = p.TryGetValue("mode", out var mode) && (mode as string) == "shade";
                foreach (var output in (Dictionary<string, object>)p["outputs"])
                {
                    foreach (var scale in (Dictionary<string, object>)output.Value)
                    {
                        var f = (Dictionary<string, object>)scale.Value;
                        var size = (List<object>)f["size_px"];
                        var slice = f.TryGetValue("slice_px", out var sp) ? sp as List<object> : null;
                        var e = new Entry
                        {
                            Manifest = manifestPath,
                            File = dir + "/" + (string)f["file"],
                            Piece = piece.Key,
                            Output = output.Key,
                            Scale = float.Parse(scale.Key, CultureInfo.InvariantCulture),
                            SizePx = new Vector2Int(Convert.ToInt32(size[0]), Convert.ToInt32(size[1])),
                            Sliced = slice != null,
                            Shade = shade,
                        };
                        if (slice != null)   // manifest [l, t, r, b] -> sprite border (l, b, r, t)
                            e.Border = new Vector4(Convert.ToSingle(slice[0]), Convert.ToSingle(slice[3]),
                                Convert.ToSingle(slice[2]), Convert.ToSingle(slice[1]));
                        map[e.File] = e;
                    }
                }
            }
        }

        /// <summary>A small JSON reader: objects -> Dictionary, arrays -> List, numbers -> double.</summary>
        static class MiniJson
        {
            public static object Parse(string s)
            {
                int i = 0;
                var v = Value(s, ref i);
                Skip(s, ref i);
                if (i != s.Length) throw new FormatException($"unexpected text at {i}");
                return v;
            }

            static void Skip(string s, ref int i)
            {
                while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
            }

            static object Value(string s, ref int i)
            {
                Skip(s, ref i);
                if (i >= s.Length) throw new FormatException("unexpected end");
                char c = s[i];
                if (c == '{')
                {
                    var o = new Dictionary<string, object>();
                    i++; Skip(s, ref i);
                    if (s[i] == '}') { i++; return o; }
                    while (true)
                    {
                        Skip(s, ref i);
                        var key = Str(s, ref i);
                        Skip(s, ref i);
                        Expect(s, ref i, ':');
                        o[key] = Value(s, ref i);
                        Skip(s, ref i);
                        if (s[i] == ',') { i++; continue; }
                        Expect(s, ref i, '}');
                        return o;
                    }
                }
                if (c == '[')
                {
                    var a = new List<object>();
                    i++; Skip(s, ref i);
                    if (s[i] == ']') { i++; return a; }
                    while (true)
                    {
                        a.Add(Value(s, ref i));
                        Skip(s, ref i);
                        if (s[i] == ',') { i++; continue; }
                        Expect(s, ref i, ']');
                        return a;
                    }
                }
                if (c == '"') return Str(s, ref i);
                if (Word(s, ref i, "true")) return true;
                if (Word(s, ref i, "false")) return false;
                if (Word(s, ref i, "null")) return null;
                int start = i;
                while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
                if (i == start) throw new FormatException($"unexpected '{c}' at {i}");
                return double.Parse(s.Substring(start, i - start), NumberStyles.Float, CultureInfo.InvariantCulture);
            }

            static bool Word(string s, ref int i, string w)
            {
                if (string.CompareOrdinal(s, i, w, 0, w.Length) != 0) return false;
                i += w.Length;
                return true;
            }

            static void Expect(string s, ref int i, char c)
            {
                if (i >= s.Length || s[i] != c) throw new FormatException($"expected '{c}' at {i}");
                i++;
            }

            static string Str(string s, ref int i)
            {
                Expect(s, ref i, '"');
                var sb = new StringBuilder();
                while (i < s.Length && s[i] != '"')
                {
                    char c = s[i++];
                    if (c != '\\') { sb.Append(c); continue; }
                    char n = s[i++];
                    switch (n)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 't': sb.Append('\t'); break;
                        case 'r': sb.Append('\r'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'u': sb.Append((char)Convert.ToInt32(s.Substring(i, 4), 16)); i += 4; break;
                        default: sb.Append(n); break;
                    }
                }
                Expect(s, ref i, '"');
                return sb.ToString();
            }
        }
    }
}
#endif
