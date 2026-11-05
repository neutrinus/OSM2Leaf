#!/usr/bin/env bash
# Fetch the pinned osm2clarion tools and apply the ZE0 patch.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HERE/vendor/osm2clarion"
PIN="07fbf78d049e7765db887818e77419ffc3dd499a"

if [ ! -d "$DEST/.git" ]; then
  mkdir -p "$HERE/vendor"
  git clone https://github.com/albertbm/osm2clarion.git "$DEST"
fi

git -C "$DEST" fetch --quiet
git -C "$DEST" checkout --quiet "$PIN"
git -C "$DEST" checkout --quiet -- .

git -C "$DEST" apply -p1 "$HERE/ze0-tools.patch"

if [ ! -e "$HERE/tools_ze0" ]; then
  ln -s vendor/osm2clarion/tools "$HERE/tools_ze0"
fi

echo "ZE0 viewer tools ready."
echo "Run: cd tools/ze0-viewer && python3 harness.py selftest /path/to/tile.DAT"
