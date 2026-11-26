#!/usr/bin/env bash
# Rebuilds the demo's sprites with ninekit and exports them into Assets/UI/Ninekit (git-ignored: this script
# recreates all of it, importer and runtime included, from a clean checkout):
#   examples/basics/basics.yaml  at scales 1, 2, 3
#   examples/gumdrop/buttons.yaml at scales 1, 2, 3
# With --check it then runs the editor check (Assets/Editor/NinekitDemoCheck.cs) in batch mode, which writes
# docs/images/unity_demo.png and exits 0 (PASS) or 1 (FAIL). UNITY=/path/to/Unity overrides the editor.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DEST="$HERE/Assets/UI/Ninekit"
PY="${PYTHON:-python3}"
ninekit() { PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" -m ninekit "$@"; }

BUILD="$(mktemp -d "${TMPDIR:-/tmp}/ninekit-unity.XXXXXX")"
trap 'rm -rf "$BUILD"' EXIT

ninekit build "$ROOT/examples/basics/basics.yaml" -o "$BUILD/basics" --scales 1,2,3 > /dev/null
ninekit build "$ROOT/examples/gumdrop/buttons.yaml" -o "$BUILD/buttons" > /dev/null
ninekit verify "$BUILD/basics/ninekit.json" > /dev/null
ninekit verify "$BUILD/buttons/ninekit.json" > /dev/null
rm -rf "$DEST" "$DEST.meta"      # nothing stale survives (Unity re-imports the folder from scratch)
ninekit export "$BUILD/basics/ninekit.json" --target unity -o "$DEST" --runtime > /dev/null
ninekit export "$BUILD/buttons/ninekit.json" --target unity -o "$DEST" --runtime > /dev/null
echo "exported basics + gumdrop_buttons into ${DEST#"$ROOT/"}"

if [[ "${1:-}" == "--check" ]]; then
  UNITY="${UNITY:-/Applications/Unity/Hub/Editor/6000.6.10f1/Unity.app/Contents/MacOS/Unity}"
  LOG="$HERE/Logs/ninekit_check.log"
  mkdir -p "$HERE/Logs"
  status=0
  "$UNITY" -batchmode -quit -projectPath "$HERE" -executeMethod NinekitDemoCheck.Run -logFile "$LOG" || status=$?
  grep -E '^\[ninekit\]' "$LOG" || true
  echo "unity exit code $status (log: ${LOG#"$ROOT/"})"
  exit "$status"
fi
