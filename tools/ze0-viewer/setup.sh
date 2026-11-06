#!/usr/bin/env bash
# Regenerate or audit tools/ze0-viewer/tools_ze0 from the pinned osm2clarion.
#
# The harness imports the checked-in tools_ze0/ directly, so this script is the
# regeneration/audit path only (docs/format/ze0-tools.md). It:
#   1. clones the pin into vendor/osm2clarion (git-ignored) or reuses it,
#   2. copies upstream tools/ to vendor/tools_ze0.new,
#   3. applies ze0-tools.patch with `patch -p2`, so both the old-side
#      `a/tools/x.py` and the new-side `b/tools_ze0/x.py` reduce to `x.py` in
#      that staging directory,
#   4. compares the result with the checked-in tools_ze0/ and exits 1 on drift.
# `--update` replaces the checked-in copy after the rebuild.
#
# Usage:
#   ./setup.sh              clone/fetch the pin, rebuild, compare (no write)
#   ./setup.sh --update     rebuild and replace tools_ze0/ with the result
#   ./setup.sh --dry-run    print every command, change nothing
#   ./setup.sh --no-fetch   reuse the existing vendor clone, skip git fetch
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HERE/vendor/osm2clarion"
STAGE="$HERE/vendor/tools_ze0.new"
TARGET="$HERE/tools_ze0"
PATCH="$HERE/ze0-tools.patch"
PIN="07fbf78d049e7765db887818e77419ffc3dd499a"
REPO="https://github.com/albertbm/osm2clarion.git"

DRY_RUN=0
UPDATE=0
FETCH=1

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --update) UPDATE=1 ;;
    --no-fetch) FETCH=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "setup.sh: unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

case "$STAGE" in
  "$HERE"/vendor/*) ;;
  *) echo "setup.sh: refusing staging path: $STAGE" >&2; exit 1 ;;
esac

if [ ! -d "$DEST/.git" ]; then
  run mkdir -p "$HERE/vendor"
  run git clone "$REPO" "$DEST"
fi
if [ "$FETCH" -eq 1 ]; then
  run git -C "$DEST" fetch --quiet
fi
run git -C "$DEST" checkout --quiet "$PIN"
run git -C "$DEST" checkout --quiet -- .

if [ "$DRY_RUN" -eq 0 ]; then
  head="$(git -C "$DEST" rev-parse HEAD)"
  if [ "$head" != "$PIN" ]; then
    echo "setup.sh: pin mismatch: HEAD $head, expected $PIN" >&2
    exit 1
  fi
fi

run rm -rf "$STAGE"
run cp -a "$DEST/tools" "$STAGE"
run cp "$TARGET/PROVENANCE.md" "$STAGE/PROVENANCE.md"
run patch -d "$STAGE" -p2 --dry-run < "$PATCH"
run patch -d "$STAGE" -p2 < "$PATCH"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: would compare $STAGE with $TARGET"
  exit 0
fi

if diff -r --exclude=__pycache__ "$STAGE" "$TARGET"; then
  drift=0
  echo "tools_ze0 matches the pinned upstream plus ze0-tools.patch."
else
  drift=1
  echo "tools_ze0 DIFFERS from the rebuild (diff above)." >&2
fi

if [ "$UPDATE" -eq 1 ]; then
  rm -rf "$TARGET"
  cp -a "$STAGE" "$TARGET"
  echo "replaced $TARGET from the pin plus ze0-tools.patch."
elif [ "$drift" -eq 1 ]; then
  echo "re-run with --update to replace it, or add the change to the patch." >&2
  exit 1
else
  echo "left the checked-in copy untouched (--update replaces it)."
fi

echo "Run: cd tools/ze0-viewer && python3 harness.py selftest /path/to/tile.DAT"
