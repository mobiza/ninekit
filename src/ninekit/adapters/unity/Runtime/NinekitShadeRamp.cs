// ninekit-unity-adapter: written by `ninekit export --target unity --runtime`; edits are overwritten by the next export.
using UnityEngine;
using UnityEngine.UI;

namespace Ninekit
{
    /// <summary>
    /// Colours shade art (`mode: shade`: R = G = B = shade 0..1, A = coverage) through a colour ramp: shade 0
    /// takes the ramp's left end, 1 its right end. Put it next to a NineSliceStack (every layer gets the
    /// ramp) or next to an Image. One art, any tone: change Ramp and call Apply().
    /// </summary>
    [ExecuteAlways]
    [AddComponentMenu("UI/Ninekit/Shade Ramp")]
    public class NinekitShadeRamp : MonoBehaviour
    {
        public const string ShaderName = "Ninekit/UI Shade Ramp";
        const int Width = 256;

        [SerializeField] Gradient m_Ramp = new Gradient
        {
            colorKeys = new[] { new GradientColorKey(Color.black, 0f), new GradientColorKey(Color.white, 1f) },
            alphaKeys = new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(1f, 1f) },
        };
        [Tooltip("The ramp shader (kept as a reference so builds include it).")]
        [SerializeField] Shader m_Shader;

        Material m_Material;
        Texture2D m_Texture;

        public Gradient Ramp
        {
            get => m_Ramp;
            set { m_Ramp = value; Apply(); }
        }

        /// <summary>The material the layers draw with (created on first use).</summary>
        public Material RampMaterial
        {
            get
            {
                Ensure();
                return m_Material;
            }
        }

        /// <summary>Bakes the ramp and gives the material to the stack or Image on this object.</summary>
        public void Apply()
        {
            Ensure();
            if (m_Material == null) return;
            for (int i = 0; i < Width; i++)
                m_Texture.SetPixel(i, 0, m_Ramp.Evaluate(i / (Width - 1f)));
            m_Texture.Apply(false);
            Assign();
        }

        void Assign()
        {
            if (TryGetComponent(out NineSliceStack stack)) stack.RefreshMaterials();
            else if (TryGetComponent(out Graphic g)) g.material = isActiveAndEnabled ? m_Material : null;
        }

        void Ensure()
        {
            if (m_Shader == null) m_Shader = Shader.Find(ShaderName);
            if (m_Shader == null) return;
            if (m_Texture == null)
                m_Texture = new Texture2D(Width, 1, TextureFormat.RGBA32, false, false)
                {
                    wrapMode = TextureWrapMode.Clamp,
                    filterMode = FilterMode.Bilinear,
                    hideFlags = HideFlags.HideAndDontSave,
                    name = "ninekit ramp",
                };
            if (m_Material == null)
            {
                m_Material = new Material(m_Shader) { hideFlags = HideFlags.HideAndDontSave, name = "ninekit ramp" };
                m_Material.SetTexture("_RampTex", m_Texture);
            }
        }

        void OnEnable() => Apply();

        void OnDisable() => Assign();

        void OnDestroy()
        {
            if (m_Material != null) DestroyImmediate(m_Material);
            if (m_Texture != null) DestroyImmediate(m_Texture);
        }

        void Reset() => m_Shader = Shader.Find(ShaderName);

        void OnValidate()
        {
            if (isActiveAndEnabled && m_Texture != null) Apply();
        }
    }
}
