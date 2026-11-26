extends Control
## ninekit's Godot demo: the art in ui/ and the runtime in addons/ninekit/ are written by
## `ninekit export --target godot` (see regenerate.sh). Every row is one piece at several sizes:
##   panel, pill, scifi, tab (frame + face), bar_track + bar_fill, stone (tiled) through NineSkin @3x;
##   shade_button through the ramp shader in two colours and badge (drawn whole) at three art scales;
##   panel through the exported @1x StyleBoxTexture next to the same panel through NineSkin @3x;
##   Gumdrop's buttons (frame + face) as NineButtons: idle, held pressed, disabled, wide and round;
##   a pill and a tab inside an RTL container next to their LTR twins.
## tests/check.tscn measures this scene and saves a screenshot.

const BASICS := "res://ui/basics"
const BUTTONS := "res://ui/buttons"
const INK := Color("#3A2E22")
const CREAM := Color("#FFF6DA")

## Nodes the check measures, by name; rows[piece] = the NineSkins of one row, small to large.
var probes: Dictionary = {}
var rows: Dictionary = {}


func _ready() -> void:
	var bg := ColorRect.new()
	bg.color = Color("#2B3240")
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right"]:
		margin.add_theme_constant_override("margin_" + side, 12)
	margin.add_theme_constant_override("margin_top", 10)
	add_child(margin)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	margin.add_child(col)

	col.add_child(_label("ninekit -> Godot: NineSkin @3x, StyleBox @1x, NineButton", 13, CREAM))
	_size_row(col, "panel", [Vector2(60, 48), Vector2(110, 64), Vector2(200, 84)], INK)
	_size_row(col, "pill", [Vector2(56, 30), Vector2(100, 36), Vector2(160, 44)], CREAM)
	_size_row(col, "scifi", [Vector2(70, 48), Vector2(110, 64), Vector2(180, 80)], Color("#39E6FF"))
	_size_row(col, "tab", [Vector2(60, 34), Vector2(100, 40), Vector2(150, 48)], CREAM)
	_bar_row(col)
	_size_row(col, "stone", [Vector2(90, 64), Vector2(130, 80), Vector2(180, 96)], Color.TRANSPARENT)
	_shade_row(col)
	_stylebox_row(col)
	_button_rows(col)
	_rtl_row(col)


func _skin(piece: String, sz: Vector2, where: String = BASICS) -> NineSkin:
	var s := NineSkin.new()
	s.manifest_path = where
	s.piece = piece
	s.custom_minimum_size = sz
	s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return s


func _label(text: String, font_size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var ls := LabelSettings.new()
	ls.font_size = font_size
	ls.font_color = color
	l.label_settings = ls
	return l


func _row(parent: Control) -> HBoxContainer:
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 8)
	parent.add_child(r)
	return r


## One piece at several sizes, each labelled with its size (no label when [param ink] is transparent).
func _size_row(parent: Control, piece: String, sizes: Array, ink: Color) -> void:
	var r := _row(parent)
	var skins: Array[NineSkin] = []
	for sz: Vector2 in sizes:
		var s := _skin(piece, sz)
		if ink.a > 0.0:
			s.add_child(_label("%dx%d" % [sz.x, sz.y], 11, ink))
		r.add_child(s)
		skins.append(s)
	rows[piece] = skins


## Progress bars: bar_fill drawn over bar_track at three sizes and fill levels.
func _bar_row(parent: Control) -> void:
	var r := _row(parent)
	var skins: Array[NineSkin] = []
	for spec: Array in [[Vector2(100, 16), 0.35], [Vector2(130, 20), 0.6], [Vector2(160, 24), 0.85]]:
		var sz: Vector2 = spec[0]
		var track := _skin("bar_track", sz)
		var holder := Control.new()
		holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
		track.add_child(holder)
		var fill := _skin("bar_fill", Vector2.ZERO)
		fill.position = Vector2(2, 2)
		fill.size = Vector2((sz.x - 4.0) * float(spec[1]), sz.y - 4.0)
		holder.add_child(fill)
		r.add_child(track)
		skins.append(track)
	rows["bar_track"] = skins


## shade_button in two ramps, and the badge (drawn whole) at art_scale 1, 1.5, 2.
func _shade_row(parent: Control) -> void:
	var r := _row(parent)
	var blue := _skin("shade_button", Vector2(100, 36))
	blue.ramp = _ramp([Color("#0B1F45"), Color("#1E5FB8"), Color("#4FA6F5"), Color("#C9ECFF")])
	blue.add_child(_label("blue ramp", 12, Color.WHITE))
	r.add_child(blue)
	var red := _skin("shade_button", Vector2(100, 36))
	red.ramp = _ramp([Color("#3D0A0A"), Color("#A8261C"), Color("#EE6A4A"), Color("#FFD9C4")])
	red.add_child(_label("red ramp", 12, Color.WHITE))
	r.add_child(red)
	probes["shade_blue"] = blue
	probes["shade_red"] = red
	var badges: Array[NineSkin] = []
	for k: float in [1.0, 1.5, 2.0]:
		var b := _skin("badge", Vector2.ZERO)
		b.art_scale = k
		r.add_child(b)
		badges.append(b)
	rows["badge"] = badges


func _ramp(colors: Array) -> Gradient:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.3, 0.7, 1.0])
	g.colors = PackedColorArray(colors)
	return g


## The same panel through the exported @1x StyleBoxTexture (a PanelContainer) and through NineSkin @3x.
func _stylebox_row(parent: Control) -> void:
	var r := _row(parent)
	var sb_panel := PanelContainer.new()
	sb_panel.add_theme_stylebox_override("panel", load(BASICS + "/panel.tres") as StyleBox)
	sb_panel.custom_minimum_size = Vector2(190, 70)
	sb_panel.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var sb_label := _label("@1x StyleBox", 13, INK)
	sb_panel.add_child(sb_label)
	r.add_child(sb_panel)
	var skin := _skin("panel", Vector2(190, 70))
	var skin_label := _label("@3x NineSkin", 13, INK)
	skin.add_child(skin_label)
	r.add_child(skin)
	probes["sb_panel"] = sb_panel
	probes["sb_label"] = sb_label
	probes["skin_panel"] = skin
	probes["skin_label"] = skin_label


func _button(piece: String, text: String, width: float, outline: Color) -> NineButton:
	var b := NineButton.new()
	b.manifest_path = BUTTONS
	b.piece = piece
	b.text = text
	var ls := LabelSettings.new()
	ls.font_size = 20
	ls.font_color = Color.WHITE
	ls.outline_size = 5
	ls.outline_color = outline
	ls.shadow_color = outline
	ls.shadow_size = 5
	ls.shadow_offset = Vector2(0, 2)
	b.label_settings = ls
	b.custom_minimum_size.x = width
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return b


## Gumdrop's buttons: idle, held pressed (toggle_mode + button_pressed), disabled, a wide one, round ones.
func _button_rows(parent: Control) -> void:
	var r := _row(parent)
	var play := _button("btn_mint", "Play", 126, Color("#0c593d"))
	r.add_child(play)
	var held := _button("btn_sun", "Pressed", 126, Color("#7b4609"))
	held.toggle_mode = true
	held.button_pressed = true
	r.add_child(held)
	var off := _button("btn_berry", "Disabled", 126, Color("#791042"))
	off.disabled = true
	r.add_child(off)
	probes["btn_idle"] = play
	probes["btn_pressed"] = held
	probes["btn_disabled"] = off
	var r2 := _row(parent)
	var wide := _button("btn_sky", "Continue", 250, Color("#113f79"))
	# (taller than the art's 59 dp body: a y-fixed button keeps its natural height, centred on the box)
	wide.custom_minimum_size.y = 70
	r2.add_child(wide)
	var plus := _button("btnc_grape", "+", 0, Color("#3c136f"))
	r2.add_child(plus)
	var star := _button("btnc_sky", "", 0, Color("#113f79"))
	star.icon = load(BASICS + "/badge@3x.png") as Texture2D
	star.icon_size = Vector2(28, 30)
	r2.add_child(star)
	probes["btn_wide"] = wide
	probes["btn_round"] = plus
	probes["btn_icon"] = star


## A pill and a tab in an LTR row and the same in an RTL row: the art must stay on its node.
func _rtl_row(parent: Control) -> void:
	var r := _row(parent)
	for rtl: bool in [false, true]:
		var box := HBoxContainer.new()
		box.add_theme_constant_override("separation", 6)
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.layout_direction = Control.LAYOUT_DIRECTION_RTL if rtl else Control.LAYOUT_DIRECTION_LTR
		var tag := "RTL" if rtl else "LTR"
		var pill := _skin("pill", Vector2(110, 36))
		pill.add_child(_label("pill " + tag, 12, CREAM))
		box.add_child(pill)
		var tab := _skin("tab", Vector2(80, 36))
		tab.add_child(_label(tag, 12, CREAM))
		box.add_child(tab)
		r.add_child(box)
		probes["pill_" + tag.to_lower()] = pill
		probes["tab_" + tag.to_lower()] = tab
