#!/usr/bin/env bash
# Rebuilds the web demo's sprites through ninekit's own exporters:
#   examples/basics/basics.yaml  at scales 1, 2, 3  -> generated/{css,phaser}/basics/
#   examples/gumdrop/buttons.yaml at scales 1, 2, 3 -> generated/{css,phaser}/buttons/
# Then serve this folder and open css.html / phaser.html (`python3 -m http.server` works, but its listen backlog of 5
# can reset some of the many parallel sprite requests: reload, or use any other static server). check.py serves,
# screenshots and measures both pages in headless Chrome.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
nk() { PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m ninekit "$@"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
nk build "$ROOT/examples/basics/basics.yaml" --scales 1,2,3 -o "$TMP/basics" >/dev/null
nk build "$ROOT/examples/gumdrop/buttons.yaml" -o "$TMP/buttons" >/dev/null
nk verify "$TMP/basics" >/dev/null
nk verify "$TMP/buttons" >/dev/null

rm -rf "$HERE/generated"
for target in css phaser; do
  for set in basics buttons; do
    nk export "$TMP/$set" --target "$target" -o "$HERE/generated/$target/$set" >/dev/null
    echo "exported $set -> generated/$target/$set ($(ls "$HERE/generated/$target/$set" | wc -l | tr -d ' ') files)"
  done
done
