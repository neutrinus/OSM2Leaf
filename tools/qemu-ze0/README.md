# `tools/qemu-ze0` — pinned QEMU for the `ze0` SH-4 machine

Out-of-tree home of the emulator work from
[`docs/research/full-system-emulation.md`](../../docs/research/full-system-emulation.md)
(TODO M8). The machine itself is **patches**, never a vendored QEMU tree: this
directory holds `build.sh`, this README and `patches/*.patch` (M8.A2+) — no
QEMU source.

## Pin

| Item | Value |
| --- | --- |
| Version | **QEMU 8.2.7** (8.2 LTS line, ≥ 8.2 as required by M8) |
| Tarball | <https://download.qemu.org/qemu-8.2.7.tar.xz> |
| SHA-256 | `1f0604f296ab9acb4854c054764a1ba408643fc299bd54a6500cccfaaca65b55` |
| Size | `132676368` bytes (~127 MiB) |
| Git mirror | <https://gitlab.com/qemu-project/qemu.git>, tag `v8.2.7` |
| Target | `sh4-softmmu` only |

`build.sh` refuses to continue if the downloaded file has another size or
SHA-256. Change the pin only together with this table and an EXP entry.

## Usage

The source and build trees stay **outside the repository**, by default in
`$HOME/.cache/qemu-ze0` (`$XDG_CACHE_HOME/qemu-ze0` when set):

```bash
# full run: download, verify, extract, patch, configure, build, check -M ze0
tools/qemu-ze0/build.sh

# the same build in a chosen cache, e.g. on a scratch disk
tools/qemu-ze0/build.sh --srcdir /scratch/qemu-ze0 --jobs 8

# see every command without fetching, writing or building anything
tools/qemu-ze0/build.sh --dry-run

# after adding/changing patches/*.patch: discard the trees and rebuild
tools/qemu-ze0/build.sh --force

# only check that an existing binary lists the machine
tools/qemu-ze0/build.sh --verify-only --qemu /scratch/qemu-ze0/build/qemu-system-sh4

# offline test of this script (no network, no QEMU source needed)
tools/qemu-ze0/build.sh --selftest
```

What a run does, in order:

1. refuses to run as root and refuses an `--srcdir` inside the repository;
2. reuses `SRCDIR/qemu-8.2.7.tar.xz` or downloads it, then checks size and
   SHA-256;
3. extracts to `SRCDIR/qemu-8.2.7` (or clones tag `v8.2.7` with `--from-git`);
4. applies every `patches/*.patch` in sorted order with `patch -p1`
   (`--no-patch` or a missing `patches/` skips this);
5. configures an out-of-tree `SRCDIR/build` with
   `--target-list=sh4-softmmu --disable-werror --disable-docs`;
6. runs `make -j<N>`;
7. requires `qemu-system-sh4 -M help` to print a `ze0` line and fails with
   the machine list otherwise.

Exit codes: `0` ok, `1` failure (including "no `ze0` machine in this build"),
`2` usage error, `3` network needed.

## Offline / no-network

QEMU is not vendored, so the first build needs network. `--dry-run` and
`--selftest` never fetch anything. When the download fails the script prints a
`NETWORK NEEDED` block with the tarball and git URLs and exits `3`; nothing is
built or written outside the cache. To build offline, copy
`qemu-8.2.7.tar.xz` into the cache (or pass `--srcdir` pointing at an already
prepared tree) and re-run.

Disk and time: the extracted tree is ~0.8 GiB, the build tree ~0.9 GiB and
the tarball 127 MiB (1.8 GiB total on this host); a `sh4-softmmu`-only build
took 2m33s on 12 cores.

## Patches

`patches/` is the only machine-code location: M8.A1 defines the layout,
M8.A2…A7 add the files (`0001-hw-sh4-ze0-machine.patch` etc.). Every
`*.patch` in the directory is applied in sorted order with `patch -p1` from
the extracted tree root; `--no-patch` skips the loop and a missing directory
is a no-op, so the script works before the first patch exists. Each patch
must stay free of vendor bytes and cite the firmware VA it models, per
`AGENTS.md`. `build.sh --force` re-extracts and re-applies them, so a patch
edit never leaves a half-patched tree behind; a failed hunk stops the run with
exit 1 and deletes the half-patched cache tree (the verified tarball is
kept), so the next run extracts cleanly.

## Current state (M8.A1, 2026-11-06)

- The script, its plan, the refusals and the `-M ze0` check are verified
  offline by `--selftest` (42 checks).
- A stock 8.2.7 build with this configure line was run once during M8.A1; it
  produces `qemu-system-sh4` but **no `ze0` machine**, so `--verify-only`
  fails by design until M8.A2 adds the patch. See
  [`EXP-2026-11-06-M8.A1-build-env.md`](../../docs/experiments/EXP-2026-11-06-M8.A1-build-env.md).
- `tools/selftest.py` discovers only `tools/*.py`, so this shell script's
  `--selftest` is not part of that registry; run it directly.

## Handy invocations after a successful build

```bash
# the machine the probe wants (M8.A2+)
QEMU=~/.cache/qemu-ze0/build/qemu-system-sh4
"$QEMU" -M help | grep ze0
"$QEMU" -M ze0 -cpu sh7785 -m 512M -nographic

# stock QEMU for comparison: the probe already works with -M none
python3 tools/ce_qemu_probe.py --qemu "$QEMU" IMAGE
```
