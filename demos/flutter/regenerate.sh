#!/usr/bin/env bash
# Rebuilds the demo's sprites with ninekit and exports them into this Flutter app:
#   assets/ui/basics/  examples/basics/basics.yaml at scales 1, 2, 3 (main file = 1x, 2.0x/, 3.0x/)
#   assets/ui/gumdrop/ examples/gumdrop/buttons.yaml at scales 1, 2, 3 (main file = 1x, 2.0x/, 3.0x/)
#   assets/ui/probe/   probe/probe.yaml at scales 1, 3 (the centerSlice unit test)
#   lib/ninekit/ninekit_sprites.dart (one section per manifest) + lib/ninekit/ninekit.dart (--runtime)
# Then: flutter test   (add --update-goldens after an intended visual change)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
nk() { PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m ninekit "$@"; }

nk build "$root/examples/basics/basics.yaml" -o "$tmp/basics" --scales 1,2,3 >/dev/null
nk build "$root/examples/gumdrop/buttons.yaml" -o "$tmp/gumdrop" >/dev/null
nk build "$here/probe/probe.yaml" -o "$tmp/probe" >/dev/null

rm -rf "$here/assets/ui" "$here/lib/ninekit"
# each export prints the pubspec lines its assets need; pubspec.yaml must carry all of them
{
  nk export "$tmp/basics" --target flutter -o "$here/assets/ui/basics" --runtime
  nk export "$tmp/gumdrop" --target flutter -o "$here/assets/ui/gumdrop"
  nk export "$tmp/probe" --target flutter -o "$here/assets/ui/probe"
} | grep -v '^wrote ' > "$tmp/snippets.txt"
missing=0
while read -r entry; do
  grep -qxF "    $entry" "$here/pubspec.yaml" || { echo "pubspec.yaml lacks: $entry" >&2; missing=1; }
done < <(grep '^    - ' "$tmp/snippets.txt" | sed 's/^ *//')
[ "$missing" = 0 ] || { echo "add the lines above to pubspec.yaml (flutter: assets:)" >&2; exit 1; }
echo "exported into $here/assets/ui and $here/lib/ninekit ($(grep -c '^    - ' "$tmp/snippets.txt") pubspec entries, all present)"
