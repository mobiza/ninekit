// ninekit shade art (mode: shade; R = G = B = shade 0..1, A = coverage) coloured through a ramp:
// shade 0 takes the ramp's first colour, 1 its last; the ramp's alpha multiplies the coverage.
// NineSkin sets `ramp` to a GradientTexture1D of its Gradient.
shader_type canvas_item;

uniform sampler2D ramp : filter_linear, repeat_disable;

// (in fragment() COLOR already holds the texture colour times the modulate; the node's modulate alone
// comes through this varying)
varying vec4 tint;

void vertex() {
	tint = COLOR;
}

void fragment() {
	vec4 t = texture(TEXTURE, UV);
	float w = float(textureSize(ramp, 0).x);
	// texel centres: shade 0 -> the first texel, 1 -> the last
	float u = (clamp(t.r, 0.0, 1.0) * (w - 1.0) + 0.5) / w;
	vec4 c = texture(ramp, vec2(u, 0.5));
	COLOR = vec4(c.rgb, t.a * c.a) * tint;
}
