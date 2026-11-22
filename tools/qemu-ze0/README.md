# `tools/qemu-ze0` — pinned QEMU for the `ze0` SH-4 machine

Out-of-tree home of the emulator work from
[`docs/research/full-system-emulation.md`](../../docs/research/full-system-emulation.md)
(TODO M8). The machine itself is **patches**, never a vendored QEMU tree: this
directory holds `build.sh`, this README and `patches/*.patch` (M8.A2+) — no
QEMU source.

## Pin

| Item | Value |
| --- | --- |
| Version | **QEMU 11.1.3** (the only supported version since M8.A11, 2026-11-21) |
| Tarball | <https://download.qemu.org/qemu-11.1.3.tar.xz> |
| SHA-256 | `5a8289c7940dc77d3873c81a6c29ba3afe1446fc9d36e77fa1658cdbecb84b22` |
| Size | `141819712` bytes (~135 MiB) |
| Git mirror | <https://gitlab.com/qemu-project/qemu.git>, tag `v11.1.3` |
| Target | `sh4-softmmu` only |

`build.sh` refuses to continue if the downloaded file has another size or
SHA-256, and refuses a full build of a version that is not in `QEMU_PINS`
(an unverified tarball is never compiled). Change the pin only together with
this table and an EXP entry.

### One version, one series

The machine is thirteen out-of-tree patches on `hw/sh4`, `hw/sd` and
`target/sh4` in [`patches/`](patches/), written against QEMU 11.1.3.

Until 2026-11-21 the series existed twice: for QEMU 8.2.7/8.2.10 (the
original, default) and as a port to 11.1.3 (M8.A9). Both gave the same boot
up to F3 (C-6873), every patch had to be written, built and booted twice,
and 8.2 is end-of-life, so the 8.2 series was removed (M8.A11,
[`EXP-2026-11-21-M8.A11-qemu-single-version.md`](../../docs/experiments/EXP-2026-11-21-M8.A11-qemu-single-version.md)).
It is in git history up to the merge of M8.C1b; `build.sh --version 8.2.10`
now answers "no verified tarball pin". The dated notes below that name 8.2
describe the builds of their day. What changed between the two API
generations, patch by patch, is in
[`patches/PORT-11.1.md`](patches/PORT-11.1.md); each patch keeps the
explanatory header it was first written with.

`--check-version V` answers "would this release accept our patches?" in
minutes without building anything:

```bash
tools/qemu-ze0/build.sh --check-version 11.1.3
# check: 0002-sh4-ze0-boot-stubs.patch                  APPLIES
# ...
# build.sh: check: QEMU 11.1.3: 13 applied, 0 failed, 0 unpinned-tarball
```

A pinned version is hash-verified; an unpinned one is downloaded and its
SHA-256/size printed so it can be added to `QEMU_PINS`.

Two things differ on an 11.x host, both handled by the scripts:

- `configure` installs the Python package `qemu.qmp` into its build venv
  (from PyPI unless already installed) and, without a system `libfdt`, would
  clone the `dtc` subproject from gitlab; `build.sh` passes `--disable-fdt`
  for `>= 11.0` (no sh4 board uses a device tree).
- "Invalid read/write at addr …" (an access to unmapped memory) moved from
  `-d guest_errors` to `-d invalid_mem`. `run.sh` and `ce_qemu_probe.py` add
  `invalid_mem` when the binary knows it; without it an 11.x log shows an
  empty unmodelled-access list.

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
`qemu-11.1.3.tar.xz` into the cache (or pass `--srcdir` pointing at an already
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
- **M8.B3 (2026-11-20):** no RTC model is needed: EU2011 `OEMGetRealTime`
  is a software clock seeded from `nk.exe` data (2009-07-10 07:10:00) plus
  `CurMSec`. `tools/ze0_rtc.py` drives Get/Set from a shim and reads the
  date words. See
  [`EXP-2026-11-20-M8.B3-rtc-time.md`](../../docs/experiments/EXP-2026-11-20-M8.B3-rtc-time.md).
- **M8.A3 (2026-11-20):** `ze0-0004` gives `-M ze0` a built-in CE loader:
  `-M ze0 -kernel SD-IMAGE` (options `kernel-off=`, default `0x3e00200`,
  and `app-off=`, default `0x200200`, 0 = none) copies physfirst..physlast
  of each image and starts at the `nk.exe` entry (`0x8800ebd0`, EU2011), so
  no `-device loader` lines are needed. `run.sh --image` uses it on ze0 and
  sizes the `-M none` cuts from the ROMHDR (C-1283 fixed).
  `tools/ze0_ceload.py plan` prints the same load plan. See
  [`EXP-2026-11-20-M8.A3-builtin-loader.md`](../../docs/experiments/EXP-2026-11-20-M8.A3-builtin-loader.md).
- **M8.B2 (2026-11-20):** `ze0-0005` sets the TMU input clock to
  Pφ = 42 MHz, the rate the EU2011 OAL assumes (2 625 000 Hz at Pφ/16), so
  `CurMSec` follows real time (ratio 1.000; 60 MHz ran 1.43× fast).
  `-M ze0,tmu=off` leaves the TMU unmapped. For repeatable traces, add
  `-icount shift=0,sleep=off`. `tools/ze0_tmu.py` samples `CurMSec`. See
  [`EXP-2026-11-20-M8.B2-ze0-tmu.md`](../../docs/experiments/EXP-2026-11-20-M8.B2-ze0-tmu.md).
- **M8.B5 (2026-11-20), milestone F1:** `ze0-0006` makes an odd-PC fetch
  raise the SH-4 address error (the Windows CE API trap; QEMU raised an
  illegal instruction and the kernel halted), and maps the OAL's second
  128 MiB DRAM at phys `0x10000000` (`ext-ram=off` = old catch-all). The
  EU2011 kernel then starts `filesys.exe` and `device.exe`. Read the
  kernel's debug text with `tools/ze0_dbgmsg.py run -- <qemu argv>`. See
  [`EXP-2026-11-20-M8.B5-ze0-f1-filesys.md`](../../docs/experiments/EXP-2026-11-20-M8.B5-ze0-f1-filesys.md).
- **M8.B6 (2026-11-20):** `ze0-0007` adds `-M ze0,dbgmsg=VA`: QEMU copies
  the UTF-16 string at `r4` to serial port 0 whenever the guest runs the
  instruction at VA (no guest byte changed). The EU2011 kernel has no gate
  that routes its debug text to a UART (C-6240), so this is how a boot gets
  a plain log. `run.sh` passes `dbgmsg=0x880404f4` (EU2011) by default on
  `-M ze0 --image` (`--dbgmsg off` for older builds) and has `--icount`;
  use `--log /dev/null` for long boots (the `-d int` log reached 11 GB in
  150 s). See
  [`EXP-2026-11-20-M8.B6-debuglog-uart.md`](../../docs/experiments/EXP-2026-11-20-M8.B6-debuglog-uart.md).
- **M8.C10 (2026-11-20):** `ze0-0008` adds the SD host: two SDHI/TMIO-style
  ports at `0xffe4c000`/`0xffe4d000` (and area-7 aliases) on QEMU's SD bus,
  their interrupts (INTEVT `0xae0`/`0xb00`, INT2 bit 29), and `sh_serial`
  stubs on SCIF channels 0–5/7 (a kernel-mode TEND spin in `serial_scif.dll`
  stopped the boot). Options `sdhi=off`, `sdhi-trace=on`, `scif-stubs=off`.
  `run.sh --sd CARD.qcow2` puts a card on port 0; QEMU's `sd-card` needs a
  power-of-two size, so use a qcow2 overlay over the 7.5 GB card image. The
  launcher's SD check passes; the card driver's first DMA transfer fails
  until the HPB DMAC exists (M8.C1). `tools/ze0_sdhost.py` decodes the
  trace. See
  [`EXP-2026-11-20-M8.C10-sd-host.md`](../../docs/experiments/EXP-2026-11-20-M8.C10-sd-host.md).
- **M8.C1b (2026-11-21):** `ze0-0009` adds the HPB-DMAC (`0xffc08000`,
  area-7 alias `0x1fc08000`; channels 8/9 = SD ports 0/1, interrupts INTEVT
  `0xc60`/`0xc80`, INT2 bit 19), so SD data transfers complete; a card
  password by "trust on first use" (the unit refuses a card with no CMD42
  password, and the real one must not be in the repository); three fixes of
  QEMU's card model (CMD6 status, CMD42 length checks) and an area-7 alias
  for the debug SCIF. With it the boot unlocks the card, reads the opening
  image and mounts both partitions (`Store Mgr Ready! [DSK1:]`): **F3**.
  (Written for both series of the day; M8.A11 kept the 11.1.3 one.)
  Options `hpbdmac=off` (negative control), `hpbdmac-trace=on`,
  `sd-pwd-tofu=off`, `sd-start-locked=on`. `mkoverlay.py CARD.img OUT.qcow2`
  writes the qcow2 overlay without `qemu-img` (`build.sh` builds no tools).
  `tools/ze0_sdhost.py dmatrace LOG --card CARD.img` compares every block
  read with the card image. See
  [`EXP-2026-11-21-M8.C1b-hpb-dmac-model.md`](../../docs/experiments/EXP-2026-11-21-M8.C1b-hpb-dmac-model.md).
- `ze0-0010` (M8.C1c): `verinf=STR` and `mapdb=LO-HI` write the unit record
  the launcher reads at kernel image header `+0x60` (map code) and
  `+0x70`/`+0x72` (map-DB window, big-endian u16); `run.sh --verinf/--mapdb`.
  The card has zeros there, so without them the launcher logs an empty
  `VerInf:` and starts `FailSafe.exe`. For the EU 2011 card:
  `verinf=QSD-302-100,mapdb=16-16`.
- `ze0-0011` (M8.C2a): HPB-DMAC serial channels. Channel 10 (RAM → SCIF1
  FTDR) transmits and completes with its interrupt; receive channels 1/3/7
  stay armed (no peer). Interrupt sources for channels 1, 3, 7, 10
  (INTEVT `0xb80`/`0xbc0`/`0xc40`/`0xca0`, INT2 bit 19). Option
  `hpbdmac-serial=off` is the control. `hpbdmac-trace=on` logs each frame.
- `ze0-0012` (M8.C1d): `ipl-patch=FILE` writes the bytes an IPL would leave
  in RAM ("PHYS HEXBYTES" lines) into the loaded images, or as extra ROM
  blobs; `run.sh --ipl-patch`. `tools/ze0_ipl.py patch IMG -o FILE` makes
  the file that joins ROM image A (Navi.exe and the other applications) to
  the kernel: XIP chain, RAM end below A, compacted TOCs. Without it every
  application `CreateProcessW` fails with LastError 2.
  `tools/ze0_screenshot.py grab --monitor SOCK -o PREFIX` saves the VRAM
  (phys `0x0e700000`) as RGB565 800x480 PNGs; the display engine is not
  modelled yet, so it stays black. See
  [`EXP-2026-11-22-M8.C1d-multi-xip.md`](../../docs/experiments/EXP-2026-11-22-M8.C1d-multi-xip.md).
- `ze0-0013` (M8.C1e): device `ze0-gfx` for the display unit (DU, phys
  `0xfff80000`) and the 2D engine (2DG, phys `0xffe80000`), also at their
  area-7 aliases: 60 Hz DU vblank (INTEVT `0x3e0`, SYSINTR 33) and the 2DG
  display-list handshake (DLSAR `+0x48`, SCLR `+0x00` = 1 → SR.TRA,
  INTEVT `0x780`, SYSINTR 34). The lists are not executed yet (M8.C1f).
  Options `gfx=off` (control) and `gfx-trace=on` (every register access
  with the guest PC under `-d unimp`). The same patch adds SCIF stubs for
  channels 8-9 (`serial_scif.dll` spun on channel 8 and starved the UI
  threads) and lets `FLDI0`/`FLDI1` run with `FPSCR.PR = 1` on this board
  (`XGLDLL.dll` in Navi.exe). See
  [`EXP-2026-11-22-M8.C1e-display-engine.md`](../../docs/experiments/EXP-2026-11-22-M8.C1e-display-engine.md).
- `tools/selftest.py` discovers only `tools/*.py`, so this shell script's
  `--selftest` is not part of that registry; run it directly.

## Handy invocations after a successful build

```bash
# the machine the probe wants (M8.A2+)
QEMU=~/.cache/qemu-ze0/build/qemu-system-sh4
"$QEMU" -M help | grep ze0
"$QEMU" -M ze0 -cpu sh7785 -m 512M -nographic
# boot the EU2011 kernel + application images straight from the SD image (M8.A3)
"$QEMU" -M ze0 -kernel archive/head256.img -nographic -serial file:serial.log -monitor none

# stock QEMU for comparison: the probe already works with -M none
python3 tools/ce_qemu_probe.py --qemu "$QEMU" IMAGE
```
