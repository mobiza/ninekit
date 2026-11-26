extends Node
## Measures the demo in the engine and saves a screenshot (a windowed run; headless has no pixels):
##   Godot --path demos/godot res://tests/check.tscn -- --shot=/absolute/path.png
## Prints one line per check ("ok ..." / "FAIL ...") and quits with 0 only when every check passed.
##
## Checks: every NinePatchRect covers its NineSkin's rect grown by the overhang (pressed layers: scaled
## towards the pivot); y-fixed pieces keep their natural height centred in taller boxes; the @1x StyleBoxTexture and the @3x NineSkin draw the same rect and place their
## label alike; the held button's face and label are at the press scale, the frame is not; the disabled
## button is tinted; RTL skins sit exactly like their LTR twins; shade ramps colour the art; in the
## screenshot the stretched middle columns are seamless and the corners are identical at every size; a
## synthetic click presses the idle button (face at the press scale), releases it (back to 1, `pressed`
## emitted) and leaves the disabled one alone.

const EPS := 0.02
## Largest channel difference (0..1) allowed between pixels that must match.
const PIXEL_TOL := 3.0 / 255.0
## Rows left out of the pixel checks: bar_track has the fill drawn over its corners and middle.
const PIXEL_SKIP := ["bar_track"]

var _fails := 0
var _checks := 0
var _demo: Control
var _img: Image
var _k := 1.0


func _ready() -> void:
	_demo = (load("res://demo.tscn") as PackedScene).instantiate() as Control
	add_child(_demo)
	for i in 10:
		await get_tree().process_frame
	await get_tree().create_timer(0.6).timeout
	await RenderingServer.frame_post_draw
	_img = get_viewport().get_texture().get_image()
	var vis := get_viewport().get_visible_rect().size
	_k = float(_img.get_width()) / vis.x
	print("viewport %s, image %dx%d, %.3f image px per unit" % [vis, _img.get_width(), _img.get_height(), _k])
	_check_geometry()
	_check_stylebox()
	_check_fixed()
	_check_manifest()
	_check_buttons()
	_check_rtl()
	_check_shade()
	_check_pixels()
	var shot := _arg("shot")
	if not shot.is_empty():
		var err := _img.save_png(shot)
		_expect(err == OK, "screenshot saved to %s" % shot)
	await _check_click()
	print("%d checks, %d failed" % [_checks, _fails])
	get_tree().quit(1 if _fails > 0 else 0)


func _arg(key: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + key + "="):
			return a.substr(key.length() + 3)
	return ""


func _expect(ok: bool, what: String) -> void:
	_checks += 1
	if not ok:
		_fails += 1
	print(("ok   " if ok else "FAIL ") + what)


func _near(a: Rect2, b: Rect2) -> bool:
	return a.position.distance_to(b.position) < EPS and a.size.distance_to(b.size) < EPS


static func _r(r: Rect2) -> String:
	return "(%.2f, %.2f  %.2f x %.2f)" % [r.position.x, r.position.y, r.size.x, r.size.y]


## Every NineSkin under [param n], internal ones (inside NineButtons) included.
func _skins(n: Node, out: Array[NineSkin] = []) -> Array[NineSkin]:
	if n is NineSkin:
		out.append(n)
	for c in n.get_children(true):
		_skins(c, out)
	return out


## The rect [param np] draws, in global (viewport) units.
static func _drawn(np: NinePatchRect) -> Rect2:
	return Rect2(np.global_position, np.size * np.get_global_transform().get_scale())


## Where [param skin]'s [param output] must be drawn: its rect grown by the overhang, pressed outputs scaled
## by press_scale towards the pivot.
static func _expected(skin: NineSkin, output: String) -> Rect2:
	var art := skin.art_rect()
	art.position += skin.global_position
	if not skin.is_press_output(output) or skin.press_scale == 1.0:
		return art
	var s := skin.press_scale
	var pivot := skin.global_position + skin.size * skin.press_pivot
	return Rect2(pivot + (art.position - pivot) * s, art.size * s)


func _check_geometry() -> void:
	var n := 0
	var bad := PackedStringArray()
	for skin in _skins(_demo):
		for o in skin.get_drawn_outputs():
			var np := skin.get_layer(o)
			n += 1
			if not _near(_drawn(np), _expected(skin, o)):
				bad.append("%s/%s drawn %s, expected %s" % [skin.piece, o, _r(_drawn(np)), _r(_expected(skin, o))])
	_expect(bad.is_empty() and n > 0, "%d NinePatchRects cover their NineSkin rect + overhang %s" % [n, ", ".join(bad)])
	var demo := _demo as Object
	for piece: String in demo.get("rows"):
		var parts := PackedStringArray()
		for skin: NineSkin in demo.get("rows")[piece]:
			var np := skin.get_layer(skin.get_drawn_outputs()[0])
			var gs := np.get_global_transform().get_scale().x
			parts.append("%.0fx%.0f art %.2fx%.2f corners L%.2f T%.2f" % [skin.size.x, skin.size.y,
				_drawn(np).size.x, _drawn(np).size.y, np.patch_margin_left * gs, np.patch_margin_top * gs])
		print("     %s @%sx: %s" % [piece, (demo.get("rows")[piece][0] as NineSkin).get_scale_key(), " | ".join(parts)])


func _probe(name: String) -> Variant:
	return (_demo.get("probes") as Dictionary)[name]


func _check_stylebox() -> void:
	var panel := _probe("sb_panel") as PanelContainer
	var skin := _probe("skin_panel") as NineSkin
	var sb := panel.get_theme_stylebox("panel") as StyleBoxTexture
	var w1 := int((skin.get_manifest().file_entry("panel", "main", "1")["size_px"] as Array)[0])
	_expect(sb != null and sb.texture != null and sb.texture.get_width() == w1,
		"panel.tres is a StyleBoxTexture on panel@1x.png (%d px wide)" % w1)
	var sb_rect := panel.get_global_rect().grow_individual(sb.expand_margin_left, sb.expand_margin_top,
		sb.expand_margin_right, sb.expand_margin_bottom)
	var np_rect := _drawn(skin.get_layer("main"))
	# (side by side: compared relative to their own nodes)
	sb_rect.position -= panel.global_position
	np_rect.position -= skin.global_position
	_expect(_near(sb_rect, np_rect) and panel.size == skin.size,
		"@1x StyleBox draws %s, @3x NineSkin draws %s relative to their %s nodes" % [_r(sb_rect), _r(np_rect), panel.size])
	var a := (_probe("sb_label") as Control).get_global_rect()
	var b := (_probe("skin_label") as Control).get_global_rect()
	_expect(a.size.distance_to(b.size) < EPS and (a.position - panel.global_position).distance_to(b.position - skin.global_position) < EPS,
		"content: StyleBox label %s, NineSkin label %s (relative to their nodes)" % [_r(a), _r(b)])


## y-fixed pieces (pill, bar_track: no stretch-safe middle rows) keep their natural height, centred on a
## taller box; the label still lays out in the box.
func _check_fixed() -> void:
	var skins: Array = (_demo.get("rows")["pill"] as Array) + (_demo.get("rows")["bar_track"] as Array)
	skins += [_probe("pill_ltr"), _probe("pill_rtl")]
	var parts := PackedStringArray()
	var ok := true
	for skin: NineSkin in skins:
		var m := skin.get_manifest()
		var ov := m.overhang(skin.piece)
		var nat := skin.natural_size()
		var d := _drawn(skin.get_layer("main"))
		var logical_mid := d.position.y + ov.y + nat.y * 0.5
		var box_mid := skin.global_position.y + skin.size.y * 0.5
		ok = ok and m.fixed_axes(skin.piece)[1] and absf(d.size.y - (nat.y + ov.y + ov.w)) < EPS \
			and absf(logical_mid - box_mid) < EPS and absf(d.size.x - skin.size.x) < EPS
		if skin.get_child_count() > 0 and skin.get_child(0) is Label:
			var lab := (skin.get_child(0) as Control).get_global_rect()
			var box := skin.get_global_rect()
			ok = ok and box.encloses(lab)
		parts.append("%s box %.0fx%.0f -> art %.2fx%.2f at dy %.2f" % [skin.piece, skin.size.x, skin.size.y,
			d.size.x, d.size.y, d.position.y - skin.global_position.y])
	_expect(ok, "y-fixed keeps its natural height, centred: " + ", ".join(parts))


func _check_manifest() -> void:
	var m := NinekitManifest.load_from("res://ui/basics")
	var picks := PackedStringArray()
	for want: float in [0.0, 1.0, 1.5, 2.0, 5.0]:
		picks.append(m.pick_scale("panel", want))
	_expect(picks == PackedStringArray(["3", "1", "2", "2", "3"]) and m == NinekitManifest.load_from("res://ui/basics/ninekit.json"),
		"pick_scale(panel, 0 / 1 / 1.5 / 2 / 5) -> %s; manifests cached" % ", ".join(picks))
	_expect(m.drawn_outputs("tab") == PackedStringArray(["frame", "face"])
		and NinekitManifest.load_from("res://ui/buttons").drawn_outputs("btnc_sky") == PackedStringArray(["frame", "face"]),
		"drawn outputs: tab frame + face; btnc_sky's composite main left out")


func _check_buttons() -> void:
	var held := _probe("btn_pressed") as NineButton
	var skin := held.get_skin()
	var face_s := skin.get_layer("face").get_global_transform().get_scale().x
	var frame_s := skin.get_layer("frame").get_global_transform().get_scale().x
	var box := held.get_label().get_parent() as Control
	_expect(absf(skin.press_scale - 0.92) < 1e-4 and absf(face_s - 0.92 / 3.0) < 1e-4 and absf(frame_s - 1.0 / 3.0) < 1e-4
		and absf(box.scale.x - 0.92) < 1e-4,
		"held button: press %.3f, face node scale %.4f, frame %.4f, label box %.3f" % [skin.press_scale, face_s, frame_s, box.scale.x])
	var pivot := skin.global_position + skin.size * 0.5
	var face := _drawn(skin.get_layer("face"))
	var frame := _drawn(skin.get_layer("frame"))
	_expect(face.get_center().distance_to(pivot + (frame.get_center() - pivot) * 0.92) < EPS and face.size.x < frame.size.x,
		"held face %s sunk inside frame %s towards the body centre %s" % [_r(face), _r(frame), pivot])
	var idle := _probe("btn_idle") as NineButton
	_expect(idle.get_skin().press_scale == 1.0, "idle button at press scale 1")
	var off := _probe("btn_disabled") as NineButton
	_expect(off.get_skin().modulate == off.disabled_modulate, "disabled button tinted %s" % off.get_skin().modulate)
	var layers := skin.get_children(true).filter(func(c: Node) -> bool: return c is NinePatchRect)
	_expect(layers.size() == 2 and layers[0] == skin.get_layer("frame") and layers[1] == skin.get_layer("face"),
		"frame drawn under face")
	var lbl := held.get_label()
	var content := skin.content_rect()
	content.position += skin.global_position
	_expect(absf(lbl.get_global_rect().get_center().y - (pivot + (content.get_center() - pivot) * 0.92).y) < 0.6,
		"label centred on the (pressed) content rect: label centre %s, content centre %s" % [lbl.get_global_rect().get_center(), content.get_center()])
	for name in ["btn_idle", "btn_wide", "btn_round", "btn_icon"]:
		var b := _probe(name) as NineButton
		print("     %s %s: %s, min %s" % [name, b.piece, _r(b.get_global_rect()), b.get_combined_minimum_size()])
	# Gumdrop's 9-slice buttons are y-fixed (built at 1, 2, 3): the art keeps its 62 dp (59 dp body + 3 dp shadow)
	# centred on the box, also on the wide button's taller box; the label sits on the face, 26.5 dp below the
	# canvas top (content [12, 8, 12, 17] -> 8 .. 45)
	for name in ["btn_idle", "btn_wide"]:
		var b := _probe(name) as NineButton
		var sk := b.get_skin()
		var fr := _drawn(sk.get_layer("frame"))
		var body_mid := fr.position.y + sk.natural_size().y * 0.5
		var label_dy := b.get_label().get_global_rect().get_center().y - fr.position.y
		_expect(sk.get_manifest().fixed_axes(sk.piece)[1] and absf(fr.size.y - 62.0) < EPS
			and absf(body_mid - b.get_global_rect().get_center().y) < EPS and absf(label_dy - 26.5) < 0.6,
			"%s (y-fixed) box %.0fx%.0f: art %.2fx%.2f at dy %.2f, label centre %.2f dp below the canvas top" % [name,
			b.size.x, b.size.y, fr.size.x, fr.size.y, fr.position.y - b.global_position.y, label_dy])


func _check_rtl() -> void:
	for piece in ["pill", "tab"]:
		var ltr := _probe(piece + "_ltr") as NineSkin
		var rtl := _probe(piece + "_rtl") as NineSkin
		var parts := PackedStringArray()
		var ok := rtl.is_layout_rtl() and not ltr.is_layout_rtl()
		for o in rtl.get_drawn_outputs():
			var dl := _drawn(ltr.get_layer(o))
			var dr := _drawn(rtl.get_layer(o))
			var off_l := dl.position - ltr.global_position
			var off_r := dr.position - rtl.global_position
			ok = ok and off_l.distance_to(off_r) < EPS and dl.size.distance_to(dr.size) < EPS
			parts.append("%s offset %s / %s" % [o, off_l, off_r])
		var lab_l: Control = ltr.get_child(0)
		var lab_r: Control = rtl.get_child(0)
		ok = ok and (lab_l.global_position - ltr.global_position).distance_to(lab_r.global_position - rtl.global_position) < EPS
		_expect(ok, "%s in RTL at %s draws like LTR: %s" % [piece, _r(rtl.get_global_rect()), ", ".join(parts)])


func _check_shade() -> void:
	for name in ["shade_blue", "shade_red"]:
		var skin := _probe(name) as NineSkin
		var np := skin.get_layer("main")
		var c := _pixel(skin.global_position + Vector2(skin.size.x * 0.5, 5.0))
		var mat_ok := np.material is ShaderMaterial and (np.material as ShaderMaterial).get_shader_parameter("ramp") is GradientTexture1D
		var hue_ok := (c.b > c.r + 0.2) if name == "shade_blue" else (c.r > c.b + 0.2)
		_expect(mat_ok and hue_ok, "%s: ramp material, face pixel %s" % [name, c.to_html(false)])


func _pixel(p: Vector2) -> Color:
	return _img.get_pixelv(Vector2i((p * _k).floor()))


## The largest channel difference between two image blocks of [param size] units at [param a] and [param b].
func _block_diff(a: Vector2, b: Vector2, size: Vector2) -> float:
	var n := Vector2i((size * _k).floor())
	var pa := Vector2i((a * _k).round())
	var pb := Vector2i((b * _k).round())
	var m := 0.0
	for y in n.y:
		for x in n.x:
			var ca := _img.get_pixel(pa.x + x, pa.y + y)
			var cb := _img.get_pixel(pb.x + x, pb.y + y)
			m = maxf(m, maxf(maxf(absf(ca.r - cb.r), absf(ca.g - cb.g)), maxf(absf(ca.b - cb.b), absf(ca.a - cb.a))))
	return m


## The largest difference of any pixel in the row segment [x0, x1) at y from the segment's first pixel.
func _row_spread(y: float, x0: float, x1: float) -> float:
	var iy := int(floor(y * _k))
	var ix0 := int(ceil(x0 * _k))
	var ix1 := int(floor(x1 * _k))
	var first := _img.get_pixel(ix0, iy)
	var m := 0.0
	for x in range(ix0, ix1):
		var c := _img.get_pixel(x, iy)
		m = maxf(m, maxf(maxf(absf(c.r - first.r), absf(c.g - first.g)), absf(c.b - first.b)))
	return m


func _check_pixels() -> void:
	var rows: Dictionary = _demo.get("rows")
	for piece: String in rows:
		var skins: Array = rows[piece]
		var first := skins[0] as NineSkin
		var m := first.get_manifest()
		var sk := first.get_scale_key()
		var o := first.get_drawn_outputs()[0]
		var sl := Vector4(m.slice_px(piece, o, sk)) / float(sk) * first.art_scale
		if m.is_whole(piece) or PIXEL_SKIP.has(piece):
			# (drawn whole: the art scales as one image, nothing to compare across sizes)
			continue
		var ct := m.content(piece) * first.art_scale if m.has_content(piece) else sl
		# the corners outside the content rect (labels never reach there)
		var tl := Vector2(minf(sl.x, ct.x), sl.y)
		var br := Vector2(minf(sl.z, ct.z), sl.w)
		var worst_corner := 0.0
		var worst_seam := 0.0
		var stretch_x: bool = (m.piece_data(piece).get("stretch", ["stretch"]) as Array)[0] == "stretch"
		for skin: NineSkin in skins:
			var a := skin.art_rect()
			a.position += skin.global_position
			var a0 := first.art_rect()
			a0.position += first.global_position
			worst_corner = maxf(worst_corner, _block_diff(a0.position, a.position, tl))
			worst_corner = maxf(worst_corner, _block_diff(a0.end - br, a.end - br, br))
			if stretch_x:
				# the stretched middle columns, 1.5 units clear of the corners, along the top and the bottom slice
				var x0 := a.position.x + sl.x + 1.5
				var x1 := a.end.x - sl.z - 1.5
				for y: float in [a.position.y + sl.y * 0.5, a.end.y - sl.w * 0.5]:
					worst_seam = maxf(worst_seam, _row_spread(y, x0, x1))
		_expect(worst_corner <= PIXEL_TOL, "%s: corners identical at %d sizes (max diff %.4f)" % [piece, skins.size(), worst_corner])
		if stretch_x:
			_expect(worst_seam <= PIXEL_TOL, "%s: stretched middle seamless (max column spread %.4f)" % [piece, worst_seam])


## Mouse down or up on [param b]'s centre, through Input (after a motion to the spot).
func _click(b: Control, down: bool) -> void:
	var at := b.get_global_rect().get_center()
	var mv := InputEventMouseMotion.new()
	mv.position = at
	mv.global_position = at
	mv.button_mask = MOUSE_BUTTON_MASK_LEFT if not down else 0
	var ev := InputEventMouseButton.new()
	ev.button_index = MOUSE_BUTTON_LEFT
	ev.button_mask = MOUSE_BUTTON_MASK_LEFT if down else 0
	ev.pressed = down
	ev.position = at
	ev.global_position = at
	Input.parse_input_event(mv)
	Input.parse_input_event(ev)


## Waits at least 3 frames and [param seconds] of wall time (a loaded machine has long frames), then until
## [param skin]'s press scale stops moving.
func _settle(skin: NineSkin, seconds: float) -> void:
	var t0 := Time.get_ticks_msec()
	var last := -1.0
	var frames := 0
	while frames < 3 or Time.get_ticks_msec() - t0 < seconds * 1000.0 or skin.press_scale != last:
		last = skin.press_scale
		frames += 1
		await get_tree().process_frame
		if Time.get_ticks_msec() - t0 > 3000:
			return


## One press-and-release on [param b]: [press scale while held, after release, `pressed` emissions].
func _press_cycle(b: NineButton) -> Array:
	var fired := [0]
	var count := func() -> void: fired[0] += 1
	b.pressed.connect(count)
	_click(b, true)
	await _settle(b.get_skin(), 0.4)
	var held := b.get_skin().press_scale
	var face := b.get_skin().get_layer("face").get_global_transform().get_scale().x
	_click(b, false)
	await _settle(b.get_skin(), 0.6)
	b.pressed.disconnect(count)
	return [held, face, b.get_skin().press_scale, fired[0]]


func _check_click() -> void:
	var r: Array = await _press_cycle(_probe("btn_idle") as NineButton)
	_expect(absf(r[0] - 0.92) < 1e-3 and absf(r[1] - 0.92 / 3.0) < 1e-3 and absf(r[2] - 1.0) < 1e-3 and r[3] == 1,
		"click: held %.3f (face node %.4f), released %.3f, pressed emitted %d" % r)
	var d: Array = await _press_cycle(_probe("btn_disabled") as NineButton)
	_expect(d[0] == 1.0 and d[2] == 1.0 and d[3] == 0, "click on the disabled button: %.3f, no pressed signal" % d[0])
