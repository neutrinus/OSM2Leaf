# `tools_ze0` — the vendored ZE0 tile tools

Scope: what `tools/ze0-viewer/tools_ze0/` is, which copy the harness imports,
what `setup.sh` does today, and how the checked-in copy and the pinned upstream
clone are kept in step. Format knowledge lives in
[`map-tiles.md`](map-tiles.md); the workflow is
[`tools/README.md`](../../tools/README.md).

## What it is

`tools/ze0-viewer/tools_ze0/` is a **checked-in copy of the `tools/` Python
modules of the upstream project `albertbm/osm2clarion`** at commit
`07fbf78d049e7765db887818e77419ffc3dd499a`, with
[`tools/ze0-viewer/ze0-tools.patch`](../../tools/ze0-viewer/ze0-tools.patch)
applied. It contains code only — 46 Python modules plus `PROVENANCE.md` — and
no map data, no vendor image and no tile.

- Licence: GPL-3.0-or-later, the same as this repository. Upstream code is
  compatible and is linked/copied with attribution, not relicensed.
- Six modules carry the ZE0 delta (`git apply --stat ze0-tools.patch`):
  `bg_decode.py`, `clarion_bg.py`, `clarion_tile.py`, `inflate_tile.py`,
  `tile_grid.py`, `tile_scan.py` — 296 insertions, 40 deletions.
- `PROVENANCE.md` is ours, not upstream: it records the pin and the licence.
- `__pycache__/` is a local build artifact, git-ignored, never committed.

## Which copy the harness uses

`tools/ze0-viewer/harness.py` puts `tools/ze0-viewer/tools_ze0` at the front of
`sys.path` and imports `clarion_bg`, `clarion_rd`, `clarion_tile` and
`tile_scan` from it; its own `ze0_*` modules (`ze0_decode`, `ze0_tile_io`,
`ze0_roads`, …) stay in `tools/ze0-viewer/`. So:

> The harness always imports the **checked-in real directory**
> `tools/ze0-viewer/tools_ze0/`. A `vendor/` clone is never on `sys.path`.

A fresh checkout therefore runs `harness.py` with no network access and no
`setup.sh`. Tiles are passed on the command line and are not committed.

## What `setup.sh` does, and why it is not the regeneration path

[`setup.sh`](../../tools/ze0-viewer/setup.sh) clones the pin into
`tools/ze0-viewer/vendor/osm2clarion` (git-ignored, `.gitignore`
`/tools/ze0-viewer/vendor/`), checks the pin out, applies the patch with
`git apply -p1`, and only then creates `tools_ze0` as a symlink **if that path
does not exist**.

Two facts make the "regenerate by `setup.sh`" story in `PROVENANCE.md` wrong
(verified 2026-11-06, `EXP-2026-11-06-H6`):

1. **The symlink branch never runs.** In a checkout `tools_ze0` already exists
   as a real directory, so `[ ! -e "$HERE/tools_ze0" ]` is false. Even if it
   ran, it would point the harness at the clone's *unpatched* `tools/`.
2. **The patch does not apply to the clone.** Its new-side paths are
   `b/tools_ze0/<file>`; with `git apply -p1` the target becomes
   `tools_ze0/<file>` inside the clone, which does not exist, so the command
   exits with "No such file or directory" and `set -e` aborts the script. This
   was reproduced with an equivalent three-line synthetic patch (same
   `--- a/tools/x.py` / `+++ b/tools_ze0/x.py` shape): `git apply -p1` fails,
   while GNU patch 2.8 with `-p2` resolves both sides to the same file.

`PROVENANCE.md` should not be read as "run `setup.sh` and the harness picks up
the clone". The checked-in directory is authoritative; `setup.sh` is only
useful as the start of a manual regeneration (clone at the pin), and its patch
step needs fixing before it can be used as-is.

## Regenerating or auditing the checked-in copy

Audit without network access — the delta must be exactly the patch:

```bash
cd tools/ze0-viewer
git apply --stat ze0-tools.patch          # 6 files, +296/-40
git diff --no-index vendor/osm2clarion/tools tools_ze0   # after a clone
```

Regenerate (requires GitHub access; the sandbox reaches only
`files.viaaq.eu`, so this path was **not** run end-to-end here — the `-p2`
path handling was verified with a synthetic patch):

```bash
cd tools/ze0-viewer
git clone https://github.com/albertbm/osm2clarion.git vendor/osm2clarion
git -C vendor/osm2clarion checkout 07fbf78d049e7765db887818e77419ffc3dd499a
cp -a vendor/osm2clarion/tools tools_ze0.new
cd tools_ze0.new
patch -p2 --dry-run < ../ze0-tools.patch   # both a/tools/… and b/tools_ze0/… → ./
patch -p2 < ../ze0-tools.patch
cd .. && rm -rf tools_ze0 && mv tools_ze0.new tools_ze0
```

`patch -p2` is what makes the header shape work: `a/tools/x.py` and
`b/tools_ze0/x.py` both reduce to `x.py`, so the hunk lands on the copied file
instead of creating `tools/` or `tools_ze0/` subdirectories.

## Keeping the two copies in step

- The patch is the **only** sanctioned delta. Any edit to a file in
  `tools_ze0/` must land in `ze0-tools.patch` in the same change (or be
  listed as a new hunk), never as a silent in-place edit. `PROVENANCE.md` says
  the same; this document is the process of record.
- Never edit `vendor/osm2clarion` (git-ignored scratch); never commit it.
- Pin changes are a deliberate task: update `setup.sh`, the patch, and this
  document together, then re-run the tile checks.
- The pin matters: these exact modules produce the byte-identical round-trips
  for `B28R070R`, `B30R060R`, `B58R070R`, `B30R048R` and `LEV3456R`. A silent
  module change invalidates those results even if the self-tests still pass.

## Verifying the harness

```bash
cd tools/ze0-viewer
python3 harness.py selftest /path/to/B58R070R.DAT   # all commands on one tile
python3 harness.py verify   /path/to/B28R070R.DAT   # byte-identical rebuild
```

Expected: `verify` byte-identical for the five tiles above (AGENTS.md). A
factory tile is required; `tools/selftest.py` does not cover the viewer because
it must not depend on vendor data.

## What else lives in the tree

`tools_ze0/` also carries the upstream builders and header writers whose
docstrings document the container layout used elsewhere in `docs/format/`:
`make_drstr.py`, `make_drstr_card.py`, `make_mmain.py` (`MMAIN001.DAT` header,
`0x184` bounds, `0x1ac` level table — see
[`drstr.md`](drstr.md#mmain001dat--the-4-kib-database-header)),
`refer_header.py` (common header constants, `0x18c` code list, `0x1ac` level
table), `tile_header.py` and `sec4_write.py`. They are vendored code, so treat
their docstrings as upstream's reading, not as this repo's evidence: cite the
EXP or claim that verified the bytes.
