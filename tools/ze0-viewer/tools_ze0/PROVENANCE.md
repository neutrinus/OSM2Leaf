# tools_ze0: vendored ZE0 tools

This directory is a copy of the `tools/` folder of the upstream project
`albertbm/osm2clarion` at commit `07fbf78d049e7765db887818e77419ffc3dd499a`,
with `tools/ze0-viewer/ze0-tools.patch` applied. It was copied in as real files
(not a symlink) so the repo can run `harness.py mutate` without a network clone.

- Upstream licence: GPL-3.0 (the repo is GPL-3.0 too; see `LICENSE`).
- Regenerate: `tools/ze0-viewer/setup.sh` creates the symlink for a local clone
  under `tools/ze0-viewer/vendor/` (git-ignored). Do not edit this copy in place
  without noting the change in `ze0-tools.patch` or here.
- Contains code only. No map data, no vendor images.
