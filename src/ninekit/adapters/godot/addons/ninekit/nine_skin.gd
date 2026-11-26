@tool
class_name NineSkin
extends Container
## Draws one ninekit piece behind its children: one [NinePatchRect] per drawn output (the piece's
## [code]stack[/code], bottom to top) using a hi-res file at node scale [code]1 / scale[/code], so the corners
## keep their dp size whatever the texture's px per dp. Children are laid out in the piece's content rect.
##
## [codeblock]
## var card := NineSkin.new()
## card.piece = "panel"                   # from NinekitManifest.default_path ("res://ui")
## card.custom_minimum_size = Vector2(200, 80)
## card.add_child(Label.new())            # fills the content rect
## [/codeblock]
##
## - Box model (DESIGN 3): the node's rect is the piece's logical box, the art (canvas) minus
##   [code]overhang[/code], which lets the art reach outside it (a drop shadow). [code]content[/code] is
##   measured from the canvas edges: children are padded inside the node's rect by
##   [code]max(0, content - overhang)[/code] per side; a child that needs more room is centred on that rect
##   at its own minimum size. Without content insets the children fill the node's rect.
## - The minimum size keeps the 9-slice corners whole (art drawn whole, or a fixed axis: its natural size)
##   and fits the children; [member art_scale] scales the art itself when a piece must be drawn smaller.
## - [code]stretch: tile[/code] repeats the middle in whole tiles ([member tile_fit]).
## - [code]stretch: fixed[/code]: on that axis the art keeps its natural length, centred on the node's
##   rect whatever length the node gets (the children still lay out in the rect).
## - [code]mode: shade[/code] art is coloured through [member ramp] ([code]ninekit_ramp.gdshader[/code]).
## - The art is laid out left to right even under an RTL parent: the 9-slice is not mirrored, and a scaled
##   child would be mirrored against its unscaled size and slide off. Children keep their LTR spots too.
## - [member press_scale] below 1 scales the pressed outputs and the children towards [member press_pivot]
##   (what [NineButton] animates).

const _RAMP_SHADER := preload("ninekit_ramp.gdshader")

## The piece to draw.
@export var piece: String = "":
	set(v):
		piece = v
		_queue_rebuild()
## The manifest's folder (or its ninekit.json); empty: [member NinekitManifest.default_path].
@export_dir var manifest_path: String = "":
	set(v):
		manifest_path = v
		_queue_rebuild()
## Texture px per dp of the file to draw: the smallest scale at or above it; 0 takes the largest.
@export_range(0.0, 8.0, 0.25) var texture_scale: float = 0.0:
	set(v):
		texture_scale = v
		_queue_rebuild()
## The art drawn this many times its dp size (corners, overhang and content insets too); 1 = as designed.
@export_range(0.05, 8.0, 0.01) var art_scale: float = 1.0:
	set(v):
		art_scale = maxf(0.001, v)
		update_minimum_size()
		queue_sort()
## The outputs to draw, bottom to top; empty: the piece's stack (a composite [code]main[/code] next to
## named outputs is left out).
@export var outputs: PackedStringArray = PackedStringArray():
	set(v):
		outputs = v
		_queue_rebuild()
## The colours of a shade piece: shade 0 takes the first colour, 1 the last. Null shows the plain greys.
@export var ramp: Gradient:
	set(v):
		ramp = v
		_queue_rebuild()
## A tiled axis repeats whole tiles, slightly stretched to fit, so the tiles meet the end slice seamlessly;
## false repeats them at their own size and cuts the last one.
@export var tile_fit: bool = true:
	set(v):
		tile_fit = v
		_queue_rebuild()

@export_group("Press")
## How far the pressed outputs and the children are scaled (1 = released).
@export_range(0.5, 1.0, 0.001) var press_scale: float = 1.0:
	set(v):
		press_scale = v
		_apply_press()
## The point they scale towards, as a share of the node's rect (the piece's body).
@export var press_pivot: Vector2 = Vector2(0.5, 0.5):
	set(v):
		press_pivot = v
		_apply_press()
## The outputs that scale when pressed; empty: [code]face[/code] when the piece has one, else every output
## above the bottom one, else the only one.
@export var press_outputs: PackedStringArray = PackedStringArray():
	set(v):
		press_outputs = v
		_queue_rebuild()

var _manifest: NinekitManifest = null
var _dirty := true
var _layers: Array[NinePatchRect] = []
var _layer_outputs := PackedStringArray()
var _pressing: Array[bool] = []
var _scale_key := ""
var _file_scale := 1.0
var _whole := false
var _art_dp := Vector2.ZERO
var _slice_dp := Vector4.ZERO
var _overhang := Vector4.ZERO
var _content := Vector4.ZERO
var _has_content := false
var _fixed: Array[bool] = [false, false]
var _shade := false
var _canvas := Rect2()


func _notification(what: int) -> void:
	match what:
		NOTIFICATION_ENTER_TREE:
			if _dirty:
				_rebuild()
		NOTIFICATION_SORT_CHILDREN:
			_layout()
		NOTIFICATION_LAYOUT_DIRECTION_CHANGED:
			queue_sort()


## Applies every property change now (they are otherwise applied together, deferred).
func refresh() -> void:
	_rebuild()


## The manifest in use (null when none could be read or the piece is not in it).
func get_manifest() -> NinekitManifest:
	return _manifest


## The scale key of the files drawn ([code]"3"[/code]), empty when nothing is drawn.
func get_scale_key() -> String:
	return _scale_key


## The NinePatchRect drawing [param output] (null when it is not drawn).
func get_layer(output: String) -> NinePatchRect:
	var i := _layer_outputs.find(output)
	return _layers[i] if i >= 0 else null


## The drawn outputs, bottom to top.
func get_drawn_outputs() -> PackedStringArray:
	return _layer_outputs.duplicate()


## Whether [param output] is drawn and scales with [member press_scale].
func is_press_output(output: String) -> bool:
	var i := _layer_outputs.find(output)
	return i >= 0 and _pressing[i]


## The piece's natural node size in dp (its art minus the overhang, times [member art_scale]).
func natural_size() -> Vector2:
	var ov := _overhang * art_scale
	return _art_dp * art_scale - Vector2(ov.x + ov.z, ov.y + ov.w)


## Where the art is drawn, in this node's coordinates: its rect grown by the overhang; on a fixed axis the
## art's natural length, its logical part centred on the rect.
func art_rect() -> Rect2:
	var ov := _overhang * art_scale
	var r := Rect2(-ov.x, -ov.y, size.x + ov.x + ov.z, size.y + ov.y + ov.w)
	var nat := _art_dp * art_scale
	if _fixed[0]:
		r.size.x = nat.x
		r.position.x = (size.x - (nat.x - ov.x - ov.z)) * 0.5 - ov.x
	if _fixed[1]:
		r.size.y = nat.y
		r.position.y = (size.y - (nat.y - ov.y - ov.w)) * 0.5 - ov.y
	return r


## The children's rect: the node's rect padded by max(0, content - overhang) per side (the whole rect
## without content insets).
func content_rect() -> Rect2:
	if not _has_content:
		return Rect2(Vector2.ZERO, size)
	var p := _padding()
	var r := Rect2(Vector2(p.x, p.y), size - Vector2(p.x + p.z, p.y + p.w))
	r.size = r.size.max(Vector2.ZERO)
	return r


## The children's padding inside the node's rect (left, top, right, bottom): max(0, content - overhang).
func _padding() -> Vector4:
	var c := (_content - _overhang) * art_scale
	return Vector4(maxf(0.0, c.x), maxf(0.0, c.y), maxf(0.0, c.z), maxf(0.0, c.w))


func _queue_rebuild() -> void:
	if _dirty:
		return
	_dirty = true
	if is_inside_tree():
		_rebuild.call_deferred()


func _rebuild() -> void:
	_dirty = false
	_manifest = null
	var drawn := PackedStringArray()
	if not piece.is_empty():
		_manifest = NinekitManifest.load_from(manifest_path)
		if _manifest != null and not _manifest.has_piece(piece):
			push_error("ninekit: %s has no piece \"%s\"" % [_manifest.path, piece])
			_manifest = null
	if _manifest != null:
		drawn = outputs if not outputs.is_empty() else _manifest.drawn_outputs(piece)
		_scale_key = _manifest.pick_scale(piece, texture_scale, drawn[0] if not drawn.is_empty() else "")
		if _scale_key.is_empty():
			drawn = PackedStringArray()
	if drawn.is_empty():
		_scale_key = ""
		_file_scale = 1.0
		_whole = false
		_art_dp = Vector2.ZERO
		_slice_dp = Vector4.ZERO
		_overhang = Vector4.ZERO
		_content = Vector4.ZERO
		_has_content = false
		_fixed = [false, false]
		_shade = false
	else:
		_file_scale = maxf(0.0001, float(_scale_key))
		_whole = _manifest.is_whole(piece)
		_art_dp = _manifest.art_size(piece, drawn[0], _scale_key)
		_slice_dp = Vector4(_manifest.slice_px(piece, drawn[0], _scale_key)) / _file_scale
		_overhang = _manifest.overhang(piece)
		_content = _manifest.content(piece)
		_has_content = _manifest.has_content(piece)
		_fixed = _manifest.fixed_axes(piece)
		_shade = _manifest.is_shade(piece)
	while _layers.size() > drawn.size():
		var old: NinePatchRect = _layers.pop_back()
		remove_child(old)
		old.queue_free()
	while _layers.size() < drawn.size():
		var np := NinePatchRect.new()
		np.mouse_filter = Control.MOUSE_FILTER_IGNORE
		np.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
		np.layout_direction = Control.LAYOUT_DIRECTION_LTR
		add_child(np, false, Node.INTERNAL_MODE_FRONT)
		_layers.append(np)
	_layer_outputs = drawn
	var press_set := _press_set(drawn)
	_pressing.clear()
	var modes: Array[int] = [0, 0]
	if not drawn.is_empty():
		modes = _manifest.axis_modes(piece, tile_fit)
	var mat: ShaderMaterial = _ramp_material() if _shade and ramp != null else null
	for i in drawn.size():
		var np := _layers[i]
		var o := drawn[i]
		np.name = "ninekit_" + o
		var sp := _manifest.slice_px(piece, o, _scale_key)
		np.texture = _manifest.texture(piece, o, _scale_key)
		np.patch_margin_left = sp.x
		np.patch_margin_top = sp.y
		np.patch_margin_right = sp.z
		np.patch_margin_bottom = sp.w
		np.axis_stretch_horizontal = modes[0] as NinePatchRect.AxisStretchMode
		np.axis_stretch_vertical = modes[1] as NinePatchRect.AxisStretchMode
		np.material = mat
		_pressing.append(press_set.has(o))
	update_minimum_size()
	queue_sort()


func _press_set(drawn: PackedStringArray) -> PackedStringArray:
	if not press_outputs.is_empty():
		return press_outputs
	if drawn.has("face"):
		return PackedStringArray(["face"])
	if drawn.size() > 1:
		return drawn.slice(1)
	return drawn


func _ramp_material() -> ShaderMaterial:
	var tex := GradientTexture1D.new()
	tex.gradient = ramp
	tex.width = 256
	var m := ShaderMaterial.new()
	m.shader = _RAMP_SHADER
	m.set_shader_parameter("ramp", tex)
	return m


func _layout() -> void:
	_canvas = art_rect()
	var k := art_scale / _file_scale
	for np in _layers:
		np.size = _canvas.size / k
	var inner := content_rect()
	for c in get_children():
		var ctl := c as Control
		if ctl == null or not ctl.visible or ctl.top_level:
			continue
		var r := inner
		var need := ctl.get_combined_minimum_size()
		if need.x > r.size.x:
			r.position.x -= (need.x - r.size.x) * 0.5
			r.size.x = need.x
		if need.y > r.size.y:
			r.position.y -= (need.y - r.size.y) * 0.5
			r.size.y = need.y
		fit_child_in_rect(ctl, r)
	_apply_press()


func _apply_press() -> void:
	var s := press_scale
	var pivot := size * press_pivot
	var k := art_scale / _file_scale
	for i in _layers.size():
		var np := _layers[i]
		if _pressing[i] and s != 1.0:
			# the layer's art maps x -> pivot + s * (canvas origin + k * x - pivot)
			np.position = pivot * (1.0 - s) + _canvas.position * s
			np.scale = Vector2.ONE * (k * s)
		else:
			np.position = _canvas.position
			np.scale = Vector2.ONE * k
	for c in get_children():
		var ctl := c as Control
		if ctl == null or not ctl.visible or ctl.top_level:
			continue
		if s != 1.0:
			ctl.pivot_offset = pivot - ctl.position
		ctl.scale = Vector2.ONE * s


func _get_minimum_size() -> Vector2:
	var a := art_scale
	var ov := _overhang * a
	var ovs := Vector2(ov.x + ov.z, ov.y + ov.w)
	var m := Vector2.ZERO
	if not _layers.is_empty():
		var art := _art_dp if _whole else Vector2(_slice_dp.x + _slice_dp.z, _slice_dp.y + _slice_dp.w)
		for i in 2:
			if _fixed[i]:
				art[i] = _art_dp[i]
		m = (art * a - ovs).max(Vector2.ZERO)
	var pad := Vector2.ZERO
	if _has_content:
		var p := _padding()
		pad = Vector2(p.x + p.z, p.y + p.w)
	for c in get_children():
		var ctl := c as Control
		if ctl != null and ctl.visible and not ctl.top_level:
			m = m.max(ctl.get_combined_minimum_size() + pad)
	return m
