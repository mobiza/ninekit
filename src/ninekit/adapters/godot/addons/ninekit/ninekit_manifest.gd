@tool
class_name NinekitManifest
extends RefCounted
## A ninekit manifest ([code]ninekit.json[/code], schema 1) read from a res:// folder, with the lookups the
## runtime needs: pieces, the outputs they draw and the file to use at a requested scale.
##
## [codeblock]
## var m := NinekitManifest.load_from("res://ui")
## var tex := m.texture("panel", "main", m.pick_scale("panel"))
## [/codeblock]
## Manifests are cached per path ([method load_from] returns the same object); call [method clear_cache]
## after exporting new art while the game runs (e.g. in the editor).
##
## Units: sizes and insets are dp (design px, the node units); a file of scale [code]s[/code] has
## [code]s[/code] texture px per dp. Insets are [Vector4] (left, top, right, bottom). [code]content[/code] is
## measured from the edges of the piece's whole art ([method art_size], overhang included);
## [code]overhang[/code] is how far the art reaches outside the node's rect.

## The folder (or [code]ninekit.json[/code] path) used when a node names no manifest.
static var default_path: String = "res://ui"

static var _cache: Dictionary = {}

## The [code]ninekit.json[/code] this was read from.
var path: String = ""
## The folder of [member path]; file names in the manifest are relative to it.
var dir: String = ""
## The parsed manifest.
var data: Dictionary = {}

var _textures: Dictionary = {}


## The manifest in folder [param where] (or the [code]ninekit.json[/code] at [param where]); empty means
## [member default_path]. Null (with an error) when it cannot be read.
static func load_from(where: String = "") -> NinekitManifest:
	var json_path := where if not where.is_empty() else default_path
	if not json_path.ends_with(".json"):
		json_path = json_path.path_join("ninekit.json")
	if _cache.has(json_path):
		return _cache[json_path]
	var m := NinekitManifest.new()
	if not m._read(json_path):
		return null
	_cache[json_path] = m
	return m


## Forgets every loaded manifest (the next [method load_from] reads the file again).
static func clear_cache() -> void:
	_cache.clear()


func _read(json_path: String) -> bool:
	var parsed: Variant = null
	if ResourceLoader.exists(json_path):
		var res := load(json_path)
		if res is JSON:
			parsed = (res as JSON).data
	if parsed == null and FileAccess.file_exists(json_path):
		parsed = JSON.parse_string(FileAccess.get_file_as_string(json_path))
	if not (parsed is Dictionary) or int((parsed as Dictionary).get("ninekit", 0)) != 1:
		push_error("ninekit: %s is missing or not a ninekit manifest (schema 1)" % json_path)
		return false
	data = parsed
	path = json_path
	dir = json_path.get_base_dir()
	return true


## The manifest's name.
func manifest_name() -> String:
	return str(data.get("name", ""))


func has_piece(piece: String) -> bool:
	return (data.get("pieces", {}) as Dictionary).has(piece)


## Every piece name, sorted.
func piece_names() -> PackedStringArray:
	var names := PackedStringArray((data.get("pieces", {}) as Dictionary).keys())
	names.sort()
	return names


## The manifest entry of [param piece] ({} when there is none).
func piece_data(piece: String) -> Dictionary:
	return (data.get("pieces", {}) as Dictionary).get(piece, {})


## The outputs a runtime draws, bottom to top: the piece's [code]stack[/code], without [code]main[/code]
## when it sits next to named outputs (it is then their composite, an alternative to stacking them).
func drawn_outputs(piece: String) -> PackedStringArray:
	var p := piece_data(piece)
	var stack := PackedStringArray(p.get("stack", (p.get("outputs", {}) as Dictionary).keys()))
	if stack.size() > 1 and stack.has("main"):
		stack.remove_at(stack.find("main"))
	return stack


## The scale keys ([code]"1"[/code], [code]"3"[/code], [code]"1.5"[/code]) [param output] of [param piece]
## has files for, smallest first ([param output] empty: the first drawn output).
func scale_keys(piece: String, output: String = "") -> PackedStringArray:
	var o := output if not output.is_empty() else _first_output(piece)
	var per: Dictionary = (piece_data(piece).get("outputs", {}) as Dictionary).get(o, {})
	var keys: Array = per.keys()
	keys.sort_custom(func(a: Variant, b: Variant) -> bool: return float(a) < float(b))
	return PackedStringArray(keys)


## The scale key of the file to draw for [param requested] texture px per dp: the smallest scale at or above
## it, else the largest; [param requested] <= 0 picks the largest. Empty when the piece has no files.
func pick_scale(piece: String, requested: float = 0.0, output: String = "") -> String:
	var keys := scale_keys(piece, output)
	if keys.is_empty():
		return ""
	if requested > 0.0:
		for k in keys:
			if float(k) >= requested - 0.0001:
				return k
	return keys[keys.size() - 1]


## The file entry {file, size_px, slice_px} of one output at one scale ({} when there is none).
func file_entry(piece: String, output: String, scale_key: String) -> Dictionary:
	var per: Dictionary = (piece_data(piece).get("outputs", {}) as Dictionary).get(output, {})
	return per.get(scale_key, {})


## The texture of one output at one scale (null with an error when it is missing).
func texture(piece: String, output: String, scale_key: String) -> Texture2D:
	var e := file_entry(piece, output, scale_key)
	if e.is_empty():
		push_error("ninekit: %s has no %s/%s@%s" % [path, piece, output, scale_key])
		return null
	var file := dir.path_join(str(e["file"]))
	if not _textures.has(file):
		_textures[file] = load(file) as Texture2D
	return _textures[file]


## The 9-slice margins (left, top, right, bottom) of one file in texture px; zero for art drawn whole.
func slice_px(piece: String, output: String, scale_key: String) -> Vector4i:
	var s: Variant = file_entry(piece, output, scale_key).get("slice_px")
	if s is Array and (s as Array).size() == 4:
		return Vector4i(int(s[0]), int(s[1]), int(s[2]), int(s[3]))
	return Vector4i.ZERO


## Whether the piece is drawn whole (no 9-slice).
func is_whole(piece: String) -> bool:
	return piece_data(piece).get("slice") == null


## A file's size in dp (its size_px over its scale): the whole art, overhang included.
func art_size(piece: String, output: String, scale_key: String) -> Vector2:
	var e := file_entry(piece, output, scale_key)
	var sz: Array = e.get("size_px", [0, 0])
	var s := maxf(0.0001, float(scale_key))
	return Vector2(float(sz[0]), float(sz[1])) / s


## The piece's natural node size in dp at [param scale_key]: its art minus the overhang.
func natural_size(piece: String, scale_key: String = "") -> Vector2:
	var sk := scale_key if not scale_key.is_empty() else pick_scale(piece)
	var ov := overhang(piece)
	return art_size(piece, _first_output(piece), sk) - Vector2(ov.x + ov.z, ov.y + ov.w)


## The content insets in dp, measured from the art's edges (zero when the piece gives none).
func content(piece: String) -> Vector4:
	return _vec4(piece_data(piece).get("content"))


func has_content(piece: String) -> bool:
	return piece_data(piece).get("content") is Array


## How far (dp) the art reaches outside the node's rect (a drop shadow).
func overhang(piece: String) -> Vector4:
	return _vec4(piece_data(piece).get("overhang"))


## Whether the art is in shades (R = G = B = shade, A = coverage) for a colour ramp.
func is_shade(piece: String) -> bool:
	return str(piece_data(piece).get("mode", "color")) == "shade"


## The NinePatchRect axis stretch mode per axis: [code]stretch[/code] and [code]fixed[/code] -> STRETCH,
## [code]tile[/code] -> TILE_FIT (whole tiles, so the tiled middle meets the end slice on a tile boundary)
## or TILE.
func axis_modes(piece: String, tile_fit: bool = true) -> Array[int]:
	var st: Array = piece_data(piece).get("stretch", ["stretch", "stretch"])
	var tile := NinePatchRect.AXIS_STRETCH_MODE_TILE_FIT if tile_fit else NinePatchRect.AXIS_STRETCH_MODE_TILE
	var out: Array[int] = []
	for i in 2:
		out.append(tile if str(st[i]) == "tile" else NinePatchRect.AXIS_STRETCH_MODE_STRETCH)
	return out


## Per axis (x, y), whether the piece's stretch is [code]fixed[/code]: no stretch-safe middle, the art is
## drawn at its natural length on that axis.
func fixed_axes(piece: String) -> Array[bool]:
	var st: Array = piece_data(piece).get("stretch", ["stretch", "stretch"])
	var out: Array[bool] = [str(st[0]) == "fixed", str(st[1]) == "fixed"]
	return out


func _first_output(piece: String) -> String:
	var outs := drawn_outputs(piece)
	return outs[0] if not outs.is_empty() else "main"


static func _vec4(v: Variant) -> Vector4:
	if v is Array and (v as Array).size() == 4:
		return Vector4(float(v[0]), float(v[1]), float(v[2]), float(v[3]))
	return Vector4.ZERO
