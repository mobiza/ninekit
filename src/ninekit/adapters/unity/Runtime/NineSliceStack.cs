// ninekit-unity-adapter: written by `ninekit export --target unity --runtime`; edits are overwritten by the next export.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace Ninekit
{
    /// <summary>
    /// Draws a ninekit piece in a uGUI rect: one Image per layer (frame, face...), bottom to top, sliced (or
    /// tiled) as the manifest says. This rect is the piece's logical body; the layers reach out by the
    /// piece's overhang (drop shadows hang outside). On a `fixed` axis the art keeps its natural length,
    /// centred on the body, whatever length the rect gets (the content still lays out in the rect). Labels and icons go under Content (the piece's content
    /// area, above the layers). Pressed, the top layer (the face) and Content scale together by PressScale
    /// towards the body's centre, uncovering what the frame draws under the face.
    /// In the editor the sprites come from the piece id (NinekitSprites); at runtime in a build, set them
    /// with SetSprites, or keep the ones the editor serialized.
    /// </summary>
    [ExecuteAlways]
    [RequireComponent(typeof(RectTransform))]
    [AddComponentMenu("UI/Ninekit/Nine Slice Stack")]
    public class NineSliceStack : UIBehaviour, IPointerDownHandler, IPointerUpHandler
    {
        [Tooltip("\"manifest/piece\", e.g. \"basics/tab\" (an Id from NinekitSprites).")]
        [SerializeField] string m_Piece = "";
        [Tooltip("Which scale's files to use: that scale, else the next larger one; 0 = the largest exported.")]
        [SerializeField] float m_Scale;
        [Tooltip("The layer sprites, bottom to top (filled from the piece in the editor).")]
        [SerializeField] Sprite[] m_Sprites = new Sprite[0];
        [Tooltip("Extend the layers by the piece's overhang, so this rect is the logical body.")]
        [SerializeField] bool m_ApplyOverhang = true;
        [Tooltip("The top layer's scale while pressed (ninekit's default: 0.92).")]
        [SerializeField, Range(0.5f, 1f)] float m_PressScale = 0.92f;
        [SerializeField, Min(0f)] float m_PressTime = 0.07f;
        [SerializeField, Min(0f)] float m_ReleaseTime = 0.22f;
        [Tooltip("React to pointer presses (the layers are raycast targets).")]
        [SerializeField] bool m_Interactable = true;
        [SerializeField] Color m_Color = Color.white;
        [Tooltip("Optional material for every layer (a NinekitShadeRamp on this object overrides it).")]
        [SerializeField] Material m_Material;
        [SerializeField, HideInInspector] List<Image> m_Layers = new List<Image>();
        [SerializeField, HideInInspector] RectTransform m_Content;

        bool m_Pressed;
        float m_From = 1f, m_To = 1f, m_Elapsed, m_Duration;
        bool m_Overshoot;
        bool m_RebuildQueued;

        /// <summary>"manifest/piece"; setting it rebuilds (and in the editor loads the piece's sprites).</summary>
        public string Piece
        {
            get => m_Piece;
            set { m_Piece = value ?? ""; Rebuild(); }
        }

        /// <summary>Which scale's files to use (0 = the largest).</summary>
        public float Scale
        {
            get => m_Scale;
            set { m_Scale = value; Rebuild(); }
        }

        public float PressScale { get => m_PressScale; set => m_PressScale = value; }
        public bool Interactable { get => m_Interactable; set { m_Interactable = value; Rebuild(); } }
        public Color Color { get => m_Color; set { m_Color = value; Rebuild(); } }
        public Material Material { get => m_Material; set { m_Material = value; RefreshMaterials(); } }

        /// <summary>The piece's descriptor, or null when the id is unknown.</summary>
        public NinekitPiece Descriptor => NinekitSprites.Find(m_Piece);

        /// <summary>The layer Images, bottom to top.</summary>
        public IReadOnlyList<Image> Layers => m_Layers;

        /// <summary>The content area, drawn above the layers: this rect padded by max(0, content - overhang) per
        /// side (content is measured from the canvas edges); the whole rect when the piece has no content.
        /// Put labels and icons here: pressed, it sinks with the face.</summary>
        public RectTransform Content
        {
            get
            {
                EnsureContent();
                return m_Content;
            }
        }

        /// <summary>Sets the layer sprites (bottom to top) directly, e.g. at runtime in a build.</summary>
        public void SetSprites(params Sprite[] sprites)
        {
            m_Sprites = sprites ?? new Sprite[0];
            Build();
        }

        /// <summary>Pressed state; animated (PressTime down, ReleaseTime up with a little overshoot).</summary>
        public bool Pressed
        {
            get => m_Pressed;
            set => SetPressed(value, false);
        }

        public void SetPressed(bool pressed, bool instant)
        {
            m_Pressed = pressed;
            float target = pressed ? m_PressScale : 1f;
            if (instant)
            {
                m_From = m_To = target;
                m_Elapsed = m_Duration = 0f;
                SetTopScale(target);
                return;
            }
            m_From = CurrentTopScale;
            m_To = target;
            m_Elapsed = 0f;
            m_Duration = pressed ? m_PressTime : m_ReleaseTime;
            m_Overshoot = !pressed;
            if (m_Duration <= 0f) SetTopScale(target);
        }

        public void OnPointerDown(PointerEventData e)
        {
            if (m_Interactable && e.button == PointerEventData.InputButton.Left) Pressed = true;
        }

        public void OnPointerUp(PointerEventData e)
        {
            if (e.button == PointerEventData.InputButton.Left) Pressed = false;
        }

        /// <summary>Re-reads the piece (and in the editor its sprites) and rebuilds the layers.</summary>
        public void Rebuild()
        {
#if UNITY_EDITOR
            var piece = Descriptor;
            if (piece != null) LoadSprites(piece);
#endif
            Build();
        }

        /// <summary>The size nearest [size] (canvas units = dp) at which a tiled sprite's middle holds whole tiles.
        /// Image.Type.Tiled cuts the last tile, so a seamless tile meets the end border at a random phase
        /// otherwise (a visible seam).</summary>
        public static Vector2 FitWholeTiles(Sprite sprite, Vector2 size, float referencePixelsPerUnit = 100f)
        {
            if (sprite == null) return size;
            var b = sprite.border;                                  // l, b, r, t texture px
            float k = referencePixelsPerUnit / sprite.pixelsPerUnit; // dp per texture px
            return new Vector2(Fit(size.x, (b.x + b.z) * k, (sprite.rect.width - b.x - b.z) * k),
                               Fit(size.y, (b.y + b.w) * k, (sprite.rect.height - b.y - b.w) * k));

            static float Fit(float s, float ends, float tile) =>
                tile <= 0f ? s : ends + Mathf.Max(1f, Mathf.Round((s - ends) / tile)) * tile;
        }

        /// <summary>Moves [child] under Content and stretches it over the content area (it sinks with the face).</summary>
        public void FitToContent(RectTransform child)
        {
            child.SetParent(Content, false);
            child.anchorMin = Vector2.zero;
            child.anchorMax = Vector2.one;
            child.offsetMin = Vector2.zero;
            child.offsetMax = Vector2.zero;
        }

        NinekitInsets Overhang
        {
            get
            {
                var piece = m_ApplyOverhang ? Descriptor : null;
                return piece != null ? piece.Overhang : NinekitInsets.Zero;
            }
        }

        float CurrentTopScale => m_Layers.Count > 0 && m_Layers[m_Layers.Count - 1] != null
            ? m_Layers[m_Layers.Count - 1].rectTransform.localScale.x : 1f;

        // The face and the content scale together; both pivots sit on the body's centre.
        void SetTopScale(float s)
        {
            var scale = new Vector3(s, s, 1f);
            if (m_Layers.Count > 0 && m_Layers[m_Layers.Count - 1] != null)
                m_Layers[m_Layers.Count - 1].rectTransform.localScale = scale;
            if (m_Content != null) m_Content.localScale = scale;
        }

        void EnsureContent()
        {
            if (m_Content != null) return;
            var go = new GameObject("content", typeof(RectTransform));
            go.layer = gameObject.layer;
            go.transform.SetParent(transform, false);
            m_Content = (RectTransform)go.transform;
        }

        void Build()
        {
            var piece = Descriptor;
            var layers = piece?.Layers;
            m_Layers.RemoveAll(i => i == null);
            // one child Image per sprite, reused by position
            while (m_Layers.Count < m_Sprites.Length)
            {
                var go = new GameObject("layer", typeof(RectTransform), typeof(Image));
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                m_Layers.Add(go.GetComponent<Image>());
            }
            while (m_Layers.Count > m_Sprites.Length)
            {
                var img = m_Layers[m_Layers.Count - 1];
                m_Layers.RemoveAt(m_Layers.Count - 1);
                if (Application.isPlaying) Destroy(img.gameObject);
                else DestroyImmediate(img.gameObject);
            }
            for (int i = 0; i < m_Layers.Count; i++)
            {
                var img = m_Layers[i];
                var sprite = m_Sprites[i];
                img.transform.SetSiblingIndex(i);
                img.gameObject.name = layers != null && i < layers.Length ? layers[i].Name : "layer " + i;
                img.sprite = sprite;
                bool sliced = sprite != null && sprite.border != Vector4.zero;
                img.type = !sliced ? Image.Type.Simple : piece != null && piece.Tiled ? Image.Type.Tiled : Image.Type.Sliced;
                img.fillCenter = true;
                img.preserveAspect = false;
                img.color = m_Color;
                img.raycastTarget = m_Interactable;
            }
            EnsureContent();
            m_Content.SetSiblingIndex(m_Layers.Count);   // above the layers
            RefreshMaterials();
            Layout();
            SetTopScale(m_Pressed ? m_PressScale : 1f);
        }

        /// <summary>Applies the layer material: a NinekitShadeRamp's on this object if enabled, else Material.</summary>
        public void RefreshMaterials()
        {
            var ramp = GetComponent<NinekitShadeRamp>();
            var mat = ramp != null && ramp.isActiveAndEnabled ? ramp.RampMaterial : m_Material;
            foreach (var img in m_Layers)
                if (img != null) img.material = mat;
        }

        void Layout()
        {
            var o = Overhang;
            var size = ((RectTransform)transform).rect.size;
            var piece = Descriptor;
            // the art's span in this rect's frame (origin bottom-left): the body plus the overhang, or on a fixed
            // axis the art's natural length with its body part centred on the body
            float x0 = -o.Left, x1 = size.x + o.Right, y0 = -o.Bottom, y1 = size.y + o.Top;
            var natural = NaturalSize(piece);
            if (piece != null && piece.StretchX == NinekitStretch.Fixed && natural.x > 0f)
            {
                x0 = (size.x - (natural.x - o.Left - o.Right)) * 0.5f - o.Left;
                x1 = x0 + natural.x;
            }
            if (piece != null && piece.StretchY == NinekitStretch.Fixed && natural.y > 0f)
            {
                y0 = (size.y - (natural.y - o.Bottom - o.Top)) * 0.5f - o.Bottom;
                y1 = y0 + natural.y;
            }
            // the pivot sits on the body's centre, so the pressed face shrinks towards it
            var pivot = new Vector2(x1 > x0 ? (size.x * 0.5f - x0) / (x1 - x0) : 0.5f,
                                    y1 > y0 ? (size.y * 0.5f - y0) / (y1 - y0) : 0.5f);
            foreach (var img in m_Layers)
            {
                if (img == null) continue;
                var rt = img.rectTransform;
                rt.anchorMin = Vector2.zero;
                rt.anchorMax = Vector2.one;
                rt.pivot = pivot;   // before the offsets: they are kept, the pivot moves inside the rect
                rt.offsetMin = new Vector2(x0, y0);
                rt.offsetMax = new Vector2(x1 - size.x, y1 - size.y);
            }
            if (m_Content == null) return;
            // content insets are measured from the canvas edges (overhang included), like slices: inside this
            // rect (the canvas minus the overhang) the padding is max(0, content - overhang) per side. Its pivot
            // sits on the same body centre (outside 0..1 is fine), so face and content scale as one.
            float l = 0f, b = 0f, r = 0f, t = 0f;
            if (piece != null && piece.HasContent)
            {
                var c = piece.Content;
                l = Mathf.Max(0f, c.Left - o.Left); b = Mathf.Max(0f, c.Bottom - o.Bottom);
                r = Mathf.Max(0f, c.Right - o.Right); t = Mathf.Max(0f, c.Top - o.Top);
            }
            float cw = size.x - l - r, ch = size.y - b - t;
            m_Content.anchorMin = Vector2.zero;
            m_Content.anchorMax = Vector2.one;
            m_Content.pivot = new Vector2(cw != 0f ? (size.x * 0.5f - l) / cw : 0.5f, ch != 0f ? (size.y * 0.5f - b) / ch : 0.5f);
            m_Content.offsetMin = new Vector2(l, b);
            m_Content.offsetMax = new Vector2(-r, -t);
        }

        // The drawn file's canvas size in dp (every scale shares it), or the piece's size; zero when unknown.
        Vector2 NaturalSize(NinekitPiece piece)
        {
            if (piece == null) return Vector2.zero;
            var layers = piece.Layers;
            var file = layers.Length > 0 ? layers[0].File(m_Scale) : null;
            return file != null ? file.Size : piece.Size;
        }

        protected override void OnEnable()
        {
            base.OnEnable();
            Rebuild();
        }

        protected override void OnRectTransformDimensionsChange()
        {
            base.OnRectTransformDimensionsChange();
            if (isActiveAndEnabled) Layout();
        }

        void Update()
        {
            if (m_RebuildQueued)
            {
                m_RebuildQueued = false;
                Rebuild();
            }
            if (m_Elapsed >= m_Duration) return;
            m_Elapsed += Time.unscaledDeltaTime;
            float t = Mathf.Clamp01(m_Elapsed / m_Duration);
            float k = m_Overshoot ? EaseOutBack(t) : 1f - (1f - t) * (1f - t);
            SetTopScale(Mathf.LerpUnclamped(m_From, m_To, k));
        }

        static float EaseOutBack(float t)
        {
            const float c1 = 1.70158f, c3 = c1 + 1f;
            float u = t - 1f;
            return 1f + c3 * u * u * u + c1 * u * u;
        }

#if UNITY_EDITOR
        void LoadSprites(NinekitPiece piece)
        {
            var layers = piece.Layers;
            var sprites = new Sprite[layers.Length];
            for (int i = 0; i < layers.Length; i++)
            {
                var file = layers[i].File(m_Scale);
                sprites[i] = file != null ? AssetDatabase.LoadAssetAtPath<Sprite>(file.Path) : null;
            }
            bool same = sprites.Length == m_Sprites.Length;
            for (int i = 0; same && i < sprites.Length; i++) same = sprites[i] == m_Sprites[i];
            if (same) return;
            m_Sprites = sprites;
            if (!Application.isPlaying) EditorUtility.SetDirty(this);
        }

        protected override void OnValidate()
        {
            base.OnValidate();
            m_RebuildQueued = true;   // no hierarchy changes inside OnValidate
            if (!Application.isPlaying) EditorApplication.QueuePlayerLoopUpdate();
        }
#endif
    }
}
