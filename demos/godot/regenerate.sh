#!/bin/sh
# Rebuilds the demo's art and runtime with ninekit (run from anywhere):
#   ui/basics/   examples/basics/basics.yaml at scales 1, 2, 3 (PNGs, ninekit.json, @1x StyleBoxTexture .tres)
#   ui/buttons/  examples/gumdrop/buttons.yaml at scales 1, 2, 3
#   addons/ninekit/  the runtime (--runtime: copied into the Godot project that contains ui/)
# then imports the project when GODOT points at a Godot 4.7 binary (or open the project in the editor).
# ui/ and addons/ninekit/ are produced here only (git-ignored). A re-export overwrites in place and drops
# the files of pieces that are gone (the exporter compares with the previous ninekit.json).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
PY=${PYTHON:-python3}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

"$PY" -m ninekit build "$ROOT/examples/basics/basics.yaml" -o "$TMP/basics" > /dev/null
"$PY" -m ninekit build "$ROOT/examples/gumdrop/buttons.yaml" -o "$TMP/buttons" > /dev/null
"$PY" -m ninekit export "$TMP/basics" --target godot -o "$HERE/ui/basics" --runtime
"$PY" -m ninekit export "$TMP/buttons" --target godot -o "$HERE/ui/buttons"

if [ -n "${GODOT:-}" ]; then
  "$GODOT" --headless --path "$HERE" --import
else
  echo "set GODOT=/path/to/Godot to import, or open the project in the editor"
fi
