# `tools/qemu-ze0` — pinned QEMU for the `ze0` SH-4 machine

Out-of-tree home of the emulator work from
[`docs/research/full-system-emulation.md`](../../docs/research/full-system-emulation.md)
(TODO M8). The machine itself is **patches**, never a vendored QEMU tree: this
directory holds `build.sh`, this README and `patches/*.patch` (M8.A2+) — no
QEMU source.

## Pin

| Item | Value |
| --- | --- |
| Version | **QEMU 8.2.10** (last 8.2 release, 2025-03-26; the 8.2 line is EOL) |
| Tarball | <https://download.qemu.org/qemu-8.2.10.tar.xz> |
| SHA-256 | `37b4a643da8ed6015eef35f5d7f06e7259d9c95359965a0a98e9667c621ab2bb` |
| Size | `132685948` bytes (~127 MiB) |
| Git mirror | <https://gitlab.com/qemu-project/qemu.git>, tag `v8.2.10` |
| Target | `sh4-softmmu` only |

The previous pin, **8.2.7**, stays in the `QEMU_PINS` table and still builds;
see the EXP for the measured equivalence.

`build.sh` refuses to continue if the downloaded file has another size or
SHA-256, and refuses a full build of a version that is not in `QEMU_PINS`
(an unverified tarball is never compiled). Change the pin only together with
this table and an EXP entry.

### Why a pin, and where it stops

The machine is five out-of-tree patches on `hw/sh4`, an API QEMU moves.
Measured on 11.1.3 (2026-11-17): four of five patches reject, and not from
line drift — `exec/address-spaces.h` is gone, `DeviceClass.reset` became
`legacy_reset`, `SHIX` was deleted. `hw/sh4/{Kconfig,meson.build}` are
byte-identical 8.2.7→8.2.10, so the whole series applies unchanged there.

`--check-version V` answers "would this release accept our patches?" in
minutes without building anything:

```bash
tools/qemu-ze0/build.sh --check-version 11.1.3
# check: 0002-sh4-ze0-boot-stubs.patch                  APPLIES
# check: m8a4-0003-hw-sh4-sh7750-use-sh4-ccn.patch      FAILED
# build.sh: check: QEMU 11.1.3: 3 applied, 2 failed, 1 unpinned-tarball
```

A pinned version is hash-verified; an unpinned one is downloaded and its
SHA-256/size printed so it can be added to `QEMU_PINS`. The port itself is
TODO **M8.A9**, with the per-hunk recipe in
[`docs/research/qemu-ze0-port-delta.md`](../../docs/research/qemu-ze0-port-delta.md).

### Exit codes

`--check-version` exits with the verdict, so a caller reads the answer from
the exit code instead of parsing the log. The verdict line is printed last;
nothing follows it.

| Exit | Meaning |
| --- | --- |
| `0` | every patch applies (`all applied, 0 failed`) |
| `4` | at least one patch does not apply — a porting delta, the probe's normal answer for a release that moved (M8.A9) |
| `2` | usage error (bad argument, bad `--version`, unpinned version outside `--check-version`) |
| `3` | missing input or download fault: no cached tarball and no network, a truncated or SHA-256-mismatched cached tarball, or `tar`/`patch`/`sha256sum`/`curl`/`wget` absent |
| `1` | the full build failed, or `-M help` did not list `ze0` |

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

# probe another QEMU release: apply the patches, build nothing
tools/qemu-ze0/build.sh --check-version 11.1.3

# offline test of this script (no network, no QEMU source needed)
tools/qemu-ze0/build.sh --selftest
```

What a run does, in order:

1. refuses to run as root and refuses an `--srcdir` inside the repository;
2. reuses `SRCDIR/qemu-<version>.tar.xz` or downloads it, then checks size and
   SHA-256 against `QEMU_PINS`;
3. extracts to `SRCDIR/qemu-<version>` (or clones tag `v<version>` with
   `--from-git`);
4. applies every `patches/*.patch` in sorted order with `patch -p1`
   (`--no-patch` or a missing `patches/` skips this);
5. configures an out-of-tree `SRCDIR/build` with
   `--target-list=sh4-softmmu --disable-werror --disable-docs`;
6. runs `make -j<N>`;
7. requires `qemu-system-sh4 -M help` to print a `ze0` line and fails with
   the machine list otherwise.

Exit codes: `0` ok, `1` failure (including "no `ze0` machine in this build"),
`2` usage error, `3` network needed or a missing tool/input, `4`
`--check-version` found a patch that does not apply.

## Offline / no-network

QEMU is not vendored, so the first build needs network. `--dry-run` and
`--selftest` never fetch anything. When the download fails the script prints a
`NETWORK NEEDED` block with the tarball and git URLs and exits `3`; nothing is
built or written outside the cache. To build offline, copy
`qemu-8.2.10.tar.xz` into the cache (or pass `--srcdir` pointing at an already
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

## Current state (M8.A1 → M5.43, 2026-11-06 → 2026-11-18)

- The script, its plan, the refusals and the `-M ze0` check are verified
  offline by `--selftest` (69 checks, including the pin table, the
  `--check-version` plan and its four exit-code cases: a green all-apply run
  exiting `0`, an injected stale patch exiting `4`, and a truncated tarball
  and a PATH without `patch` each exiting `3` — all offline).
- A stock 8.2.7 build with this configure line was run once during M8.A1; it
  produces `qemu-system-sh4` but **no `ze0` machine**, so `--verify-only`
  fails by design until M8.A2 adds the patch. See
  [`EXP-2026-11-06-M8.A1-build-env.md`](../../docs/experiments/EXP-2026-11-06-M8.A1-build-env.md).
- **M8.A2 (2026-11-17):** `build.sh --force --jobs 8` on a host with the
  QEMU deps applies all five patches, builds QEMU 8.2.7 and prints
  `OK: ze0  Nissan Leaf ZE0 navigation unit (SH-4A, research skeleton)`;
  `-M ze0` boots `archive/head256.img` for 10 s with 0 CPU exceptions. See
  [`EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md`](../../docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md).
- **M8.A10 (2026-11-17):** pin bumped 8.2.7 → 8.2.10. `hw/sh4`,
  `configs/devices/sh4-softmmu` and `include/hw/sh4` are byte-identical
  between the two releases (`diff -r` empty), all five patches apply
  unchanged, and the built binary boots `archive/head256.img` with the same
  stable result as 8.2.7 (0 exceptions, one `write 0x38`). See
  [`EXP-2026-11-17-M8.A10-bump-8210.md`](../../docs/experiments/EXP-2026-11-17-M8.A10-bump-8210.md).
- **M8.A6 (2026-11-19):** `ze0-0002` maps the kernel debug SCIF
  (`sh_serial`, SCIF mode) at `0xffe46000` on serial port 0; `run.sh
  --serial` (default `log` = `WORK/serial.log`; `stdio`, `none` or any QEMU
  chardev) carries it. The retail EU2011 banner does not go there — only
  the AER exception dump does. See
  [`EXP-2026-11-19-M8.A6-debug-serial.md`](../../docs/experiments/EXP-2026-11-19-M8.A6-debug-serial.md).
- **M8.B1 (2026-11-20):** `ze0-0003` adds the INTC/INT2 model
  (`0xff802000`, `0xff804000`) and TMU ch0–2 at `0xffd80000`; the EU2011
  kernel's TMU0 interrupt (INTEVT `0x400`) is delivered to its ISR and
  acknowledged. See
  [`EXP-2026-11-20-M8.B1-intc-model.md`](../../docs/experiments/EXP-2026-11-20-M8.B1-intc-model.md).
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
