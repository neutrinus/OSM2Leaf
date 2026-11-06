# tools_ze0: vendored ZE0 tools

This directory is a copy of the `tools/` folder of the upstream project
`albertbm/osm2clarion` at commit `07fbf78d049e7765db887818e77419ffc3dd499a`,
with `tools/ze0-viewer/ze0-tools.patch` applied. It was copied in as real files
(not a symlink) so the repo can run `harness.py` without a network clone.
`harness.py` inserts this directory at `sys.path[0]`; it always imports this
checked-in copy, never a `vendor/` clone.

- Upstream licence: GPL-3.0 (the repo is GPL-3.0 too; see `LICENSE`).
- Regenerate/audit: `tools/ze0-viewer/setup.sh` clones the pin into
  `tools/ze0-viewer/vendor/` (git-ignored), rebuilds this directory there and
  compares it with the checked-in files; `--update` replaces them. The patch is
  the only sanctioned delta — do not edit this copy in place without adding the
  change to `ze0-tools.patch`. See `docs/format/ze0-tools.md`.
- Contains code only. No map data, no vendor images.
