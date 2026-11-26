@tool
class_name NineButton
extends BaseButton
## A button drawn by a ninekit piece, typically a [code]frame[/code] + [code]face[/code] pair: an internal
## [NineSkin] fills the button and a [Label] (with an optional icon before it) sits centred on the piece's
## content rect. Pressed, the face output, the label and the icon scale to [member press_scale] towards
## [member press_pivot] (the body's centre) and spring back on release; disabled, the art and the label are
## tinted by [member disabled_modulate]. Input, signals, [member BaseButton.toggle_mode],
## [member BaseButton.button_group], shortcuts and focus are [BaseButton]'s.
##
## [codeblock]
## var b := NineButton.new()
## b.piece = "btn_mint"                   # from NinekitManifest.default_path ("res://ui")
## b.text = "Play"
## b.custom_minimum_size.x = 180
## b.pressed.connect(_on_play)
## [/codeblock]
## The minimum size is the skin's: whole 9-slice corners and room for the label in the content rect. For a
## smaller button than the art allows, lower [member art_scale].

## The piece to draw.
@export var piece: String = "":
	set(v):
		piece = v
		_skin.piece = v
## The manifest's folder (or its ninekit.json); empty: [member NinekitManifest.default_path].
@export_dir var manifest_path: String = "":
	set(v):
		manifest_path = v
		_skin.manifest_path = v
## Texture px per dp of the files to draw; 0 takes the largest ([member NineSkin.texture_scale]).
@export_range(0.0, 8.0, 0.25) var texture_scale: float = 0.0:
	set(v):
		texture_scale = v
		_skin.texture_scale = v
## The art drawn this many times its dp size ([member NineSkin.art_scale]).
@export_range(0.05, 8.0, 0.01) var art_scale: float = 1.0:
	set(v):
		art_scale = v
		_skin.art_scale = v
## The colours of a shade piece ([member NineSkin.ramp]).
@export var ramp: Gradient:
	set(v):
		ramp = v
		_skin.ramp = v
## The label's text (no label when empty).
@export_multiline var text: String = "":
	set(v):
		text = v
		_label.text = v
		_label.visible = not v.is_empty()
## The label's font, size, colour, outline and shadow (null: the theme's).
@export var label_settings: LabelSettings:
	set(v):
		label_settings = v
		_label.label_settings = v
## An icon before the label.
@export var icon: Texture2D:
	set(v):
		icon = v
		_icon.texture = v
		_icon.visible = v != null
## The icon's size in dp; zero: the texture's own size.
@export var icon_size: Vector2 = Vector2.ZERO:
	set(v):
		icon_size = v
		_icon.expand_mode = TextureRect.EXPAND_KEEP_SIZE if v == Vector2.ZERO else TextureRect.EXPAND_IGNORE_SIZE
		_icon.custom_minimum_size = v

@export_group("Press")
## The pressed scale of the face, the label and the icon.
@export_range(0.5, 1.0, 0.001) var press_scale: float = 0.92
## The point they scale towards, as a share of the button's rect (the piece's body).
@export var press_pivot: Vector2 = Vector2(0.5, 0.5):
	set(v):
		press_pivot = v
		_skin.press_pivot = v
## The outputs that scale when pressed; empty: [code]face[/code], else every output above the bottom one.
@export var press_outputs: PackedStringArray = PackedStringArray():
	set(v):
		press_outputs = v
		_skin.press_outputs = v
## Seconds of the press (an ease-out) and of the release (an ease-out with a little overshoot).
@export var press_time: float = 0.07
@export var release_time: float = 0.22
## The tint of the art and the label while disabled.
@export var disabled_modulate: Color = Color(0.6, 0.6, 0.6, 1.0)

var _skin: NineSkin
var _box: HBoxContainer
var _icon: TextureRect
var _label: Label
var _down := false
var _disabled_look := false
var _synced := false
var _tween: Tween


func _init() -> void:
	_skin = NineSkin.new()
	_skin.name = "skin"
	_skin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_skin, false, Node.INTERNAL_MODE_FRONT)
	_skin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_skin.minimum_size_changed.connect(update_minimum_size)
	_box = HBoxContainer.new()
	_box.name = "content"
	_box.alignment = BoxContainer.ALIGNMENT_CENTER
	_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_skin.add_child(_box)
	_icon = TextureRect.new()
	_icon.name = "icon"
	_icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_icon.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_icon.visible = false
	_box.add_child(_icon)
	_label = Label.new()
	_label.name = "label"
	_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_label.visible = false
	_box.add_child(_label)


func _notification(what: int) -> void:
	if what == NOTIFICATION_READY:
		_sync_state()


func _draw() -> void:
	# (BaseButton redraws on every state change: hover, press, toggle, disable)
	_sync_state.call_deferred()


## The internal skin (the art and the content box).
func get_skin() -> NineSkin:
	return _skin


func get_label() -> Label:
	return _label


func get_icon_rect() -> TextureRect:
	return _icon


func _get_minimum_size() -> Vector2:
	return _skin.get_combined_minimum_size()


func _sync_state() -> void:
	if not is_inside_tree():
		return
	var mode := get_draw_mode()
	var dis := mode == DRAW_DISABLED
	if dis != _disabled_look or not _synced:
		_disabled_look = dis
		_skin.modulate = disabled_modulate if dis else Color.WHITE
	var down := mode == DRAW_PRESSED or mode == DRAW_HOVER_PRESSED
	if down == _down and _synced:
		return
	_down = down
	if _tween != null and _tween.is_valid():
		_tween.kill()
	var target := press_scale if down else 1.0
	if not _synced or Engine.is_editor_hint():
		_skin.press_scale = target
	elif down:
		_tween = create_tween()
		_tween.tween_property(_skin, "press_scale", target, press_time) \
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	else:
		_tween = create_tween()
		_tween.tween_property(_skin, "press_scale", target, release_time) \
			.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_synced = true
