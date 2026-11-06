# QEMU `ze0` patches: CPU control block (TODO M8.A4)

Out-of-tree QEMU patch series that factors the SH-4 **CCN/MMU control
block** out of `hw/sh4/sh7750.c` so a `ze0` machine can map it without
instantiating any SH7750 peripheral model. Basis: **QEMU 8.2.7**, the
8.2 LTS pin of [`../README.md`](../README.md).

Companion record: [`EXP-2026-11-06-M8.A4-cpu-control`](../../../docs/experiments/EXP-2026-11-06-M8.A4-cpu-control.md).
Context and the register work-list: [`docs/research/full-system-emulation.md`](../../../docs/research/full-system-emulation.md)
§1 (P4 table) and `EXP-2026-11-05-37`.

| | |
| --- | --- |
| Base tree | `qemu` tag **`v8.2.7`** (8.2 LTS; tarball `qemu-8.2.7.tar.xz`, SHA-256 `1f0604f296ab9acb4854c054764a1ba408643fc299bd54a6500cccfaaca65b55`, 132676368 bytes — the pin in [`../README.md`](../README.md)) |
| Base commit | `git rev-parse v8.2.7^{commit}` — **not resolvable here**: no QEMU object database on this machine, so no SHA is printed rather than an invented one. Record it (and `git hash-object` of the three touched files) in the pin table in §2 on first apply. |
| Target | `--target-list=sh4-softmmu` |
| Apply tool | `patch -p1` from the extracted tree root, which is what `tools/qemu-ze0/build.sh` runs, with `git apply --check` as the pre-flight; the patches have no `From:`/`Subject:` lines, so `git am` does not apply |
| Licence | patch text is original, GPL-2.0-or-later, same as the files it touches |
| Status | **patch text only — compilation and runtime UNVERIFIED** (no QEMU tree here) |
| Sibling series | `0002-sh4-ze0-boot-stubs.patch` (TODO M8.A5) is a different task in the same directory and is independent of this one. It also edits `hw/sh4/meson.build`, at a different offset; apply the two series in either order. |

The `m8a4-` prefix keeps the numbering distinct from the sibling series:
two tasks writing into one directory both produced a `0002-…` file.

## 1. Why

`EXP-2026-11-05-37` booted the ZE0 kernel in stock QEMU (`-M none`,
`-cpu sh7785`, RAM only) up to the first missing board feature: the MMU
control registers. The kernel writes `CCR`/`MMUCR` at `0xff00001c` /
`0xff000010`, flushes the cache arrays at `0xf0000000`–`0xf7ffffff`, then
calls a kernel-page stub at user VA `0x00005b90`; with no MMU model the
address resolves to empty RAM and QEMU raises `illegal_instruction`.

In 8.2 that register block lives inside `hw/sh4/sh7750.c`, which also
builds the SH7750 INTC, TMU012, SCI, RTC, PCI and GPIO models and aborts
on unknown P4 addresses. Linking the whole SH7750 SoC into `ze0` would
put a foreign peripheral map under the ZE0 kernel; the kernel's own
register accesses at `0xffe4*`/`0xffc*` would then land in SH7750
devices. Factoring the control block out gives `ze0` exactly the CPU
side and nothing else.

## 2. Apply order

```bash
git clone --branch v8.2.7 https://gitlab.com/qemu-project/qemu.git qemu-8.2.7
cd qemu-8.2.7
git rev-parse HEAD                     # record this as the base commit

P=/path/to/OSM2Leaf/tools/qemu-ze0/patches
git apply --check "$P/m8a4-0001-hw-sh4-add-sh4-ccn-device.patch"
git apply --check "$P/m8a4-0002-hw-sh4-build-sh4-ccn.patch"
git apply --check "$P/m8a4-0003-hw-sh4-sh7750-use-sh4-ccn.patch"
git apply         "$P/m8a4-0001-hw-sh4-add-sh4-ccn-device.patch"
git apply         "$P/m8a4-0002-hw-sh4-build-sh4-ccn.patch"
git apply         "$P/m8a4-0003-hw-sh4-sh7750-use-sh4-ccn.patch"
```

Expected `git apply --check`: **rc=0 for all three on a clean `v8.2.7`
checkout**. That expectation is *not* verified in this repository (there
is no QEMU tree); §5 shows what could be verified instead.

`m8a4-0003` is a de-duplication of `r2d`; it is **not needed for `ze0`**.
Patches `m8a4-0001`+`m8a4-0002` alone give the `ze0` machine the whole control
block.

Pin (fill on first apply; empty here because none could be resolved
offline):

| Item | Value |
| --- | --- |
| `git rev-parse v8.2.7^{commit}` | |
| `git hash-object hw/sh4/sh7750.c` | |
| `git hash-object hw/sh4/meson.build` | |
| `git hash-object hw/sh4/Kconfig` | |
| QEMU build (`qemu-system-sh4 --version`) | |

If `m8a4-0003` rejects on the real tree, keep the old inline model in
`sh7750.c` and continue with `m8a4-0001`+`m8a4-0002`.

`build.sh` applies every `*.patch` in the directory in **sorted order**,
so the sibling `0002-sh4-ze0-boot-stubs.patch` (M8.A5) runs before this
series. It appends at the end of `hw/sh4/meson.build` (after
`hw_arch += {'sh4': sh4_ss}`), so it shifts neither this series' hunk nor
its behaviour; the recorded sorted order is in the M8.A5 section below.

## 3. Hunk table

### `m8a4-0001-hw-sh4-add-sh4-ccn-device.patch` — new device, no QEMU file touched

| Hunk | File | Intent |
| --- | --- | --- |
| 1 | `include/hw/sh4/sh4_ccn.h` (new, 87 lines) | `TYPE_SH4_CCN`, `SH4CCNState`, the nine P4 offsets, `MMUCR.AT`/`MMUCR.TI`, window constants, `SH4CCNHooks` (read/write write-through to the CPU target), and the four exported functions. |
| 2 | `hw/sh4/sh4_ccn.c` (new, 242 lines) | 32-bit MMIO ops for `0xff000000`; a sink for the `0xf0000000`–`0xf7ffffff` IC/OC/UTLB/ITLB window (writes dropped, reads 0, same as the old inline model); register file with optional hooks; reset; vmstate v1; `type_init`. |

Design notes that matter for the kernel:

* The P4 page holds only the registers the kernel actually touches
  (`PTEH 0x000`, `PTEL 0x004`, `TTB 0x008`, `TEA 0x00c`, `MMUCR 0x010`,
  `TRA 0x014`, `CCR 0x01c`, `EXPEVT 0x024`, `INTEVT 0x028`). Anything
  else logs `LOG_UNIMP` and reads 0, replacing the old "invalid access"
  spam in the probe log with a named message.
* Access size is 4 bytes only, as in the old `sh7750_mmct_ops`.
* The array window is deliberately a sink. On SH-4 the TLB is software
  managed: the `0x100` (TLB miss) handler writes `PTEH`/`PTEL` and
  executes `LDTLB`; QEMU keeps the effective entry in its softmmu TLB.
  Nothing reads the UTLB arrays back, so modelling them would add state
  the kernel does not observe.
* With no hooks installed the device is a plain register file, so it can
  be unit-instantiated on `-M none` before the machine exists.

### `m8a4-0002-hw-sh4-build-sh4-ccn.patch`

| Hunk | File | Intent |
| --- | --- | --- |
| 1 | `hw/sh4/meson.build` | Compile `sh4_ccn.c` into `sh4_ss` when `CONFIG_SH4_CCN` is set. |
| 2 | `hw/sh4/Kconfig` | Define `CONFIG_SH4_CCN` (bool); `R2D` selects it so the de-duplicated `sh7750.c` still links. |

The `ze0` machine patch (TODO **M8.A1**) must add `select SH4_CCN` to
its own `config ZE0` stanza; this series cannot do that because the
machine does not exist yet. One line:

```kconfig
config ZE0
    bool
    select SH4
    select SH4_CCN
    ...
```

### `m8a4-0003-hw-sh4-sh7750-use-sh4-ccn.patch`

| Hunk | File | Intent |
| --- | --- | --- |
| 1 | `hw/sh4/sh7750.c` | Add `#include "hw/qdev-core.h"` and `"hw/sh4/sh4_ccn.h"`; add `SH4CCNState *ccn` to `SH7750State`; drop the `iomem_ff0`/`iomem_cache` regions; replace `sh7750_mmct_readl/writel` and `sh7750_mm_cache_readl/writel` + their `MemoryRegionOps` with two hook functions that read/write the same CPU-target fields (`s->cpu->pteh`…) the inline model used. |
| 2 | `hw/sh4/sh7750.c` | In `sh7750_init`, create/realize the CCN, install the hooks, and map its two regions at `0xff000000` and `0xf0000000`; delete the two `memory_region_init_io`/`add_subregion` pairs. |

Behavioural deltas of `m8a4-0003`, all intentional:

* The `0xff000000` region shrinks from `0x4000` to `0x1000`. The MMU
  registers end at `0x02c`; nothing in the old range was modelled.
* The "unimplemented MMU register" log line moves into the device and
  names the register offset instead of the absolute address.
* `CCR`, `EXPEVT` and `INTEVT` were not forwarded to the CPU target
  before and are not now: the hook does not claim them, so reads return
  zero exactly as they did.

## 4. What this series does **not** do

* No `ze0` machine (`-M ze0`), RAM map or loader — that is M8.A1 and the
  `ce_qemu_probe.py` loader logic.
* No boot-blocker stubs (`0xffe70000` with `+0x808 = 0xc0000000`, CPG,
  UBC, area 6) — M8.A5. Without them the unpatched kernel still spins
  before it ever reaches the `0x5b90` call.
* No INTC, TMU, SCIF, DMAC, SD host — M8.A6/M8.B*.
* No change to `target/sh4` (MMU translation, `LDTLB`, TB flags).

## 5. Verification performed here, and its limits

There is no QEMU tree in this repository and the environment is offline,
so `git apply --check` cannot run against `v8.2.7`. What was run:

1. `git apply --stat` on the series (syntax + hunk arithmetic) — passes.
2. A **synthetic pre-image fixture** (`/tmp`, not committed): the
   pre-image of every touched file is rebuilt from the patch's own
   context lines, then each patch is checked and applied against it.
   Result: rc=0 for all three, and the post-image is the intended code.
   This proves hunk offsets/context are self-consistent; it proves
   nothing about the real 8.2 file contents.

The patches were authored so that every hunk **ends on a context line**:
`git apply` 2.53 here rejects a hunk whose last line is an addition
(`patch -p1` accepts it with fuzz), so the Kconfig change is one merged
hunk rather than two.

Still to be checked on a machine with the tree:

* `git apply --check` result on `v8.2.7` (expected rc=0), then the
  `tools/qemu-ze0/build.sh --force` run that applies the series with
  `patch -p1` and builds `qemu-system-sh4`.
* Compilation (`ninja qemu-system-sh4`) — **UNVERIFIED**.
* Runtime (`-device sh4-ccn`, `info mtree` shows the two regions) —
  **UNVERIFIED**.
* The exact spelling of the CPU-state access in `sh7750.c`. The patch
  assumes `s->cpu->pteh` etc., matching the inline switch it replaces.
  If 8.2 spells it `s->cpu->env.pteh`, adapt the six lines in hunk 1 of
  `m8a4-0003`; `m8a4-0001`/`m8a4-0002` are unaffected.

The `hw/sh4/meson.build` hunk is the one piece of real 8.2 context that
could be cross-checked here: the M8.A5 patch in this directory shows the
file starts with a multi-line `sh4_ss.add(files(` block listing
`sh7750.c` and `sh7750_regnames.c`, followed (after a blank line) by the
`R2D`/`SHIX` lines. `m8a4-0002` therefore anchors on the `R2D`/`SHIX`
pair and inserts immediately before it, which does not depend on whether
the blank line is present. The `Kconfig` and `sh7750.c` contexts remain
reconstruction only.

## 6. Acceptance on a machine with QEMU 8.2.7

```bash
# the repository's own path: extract the pinned tarball, apply every
# patches/*.patch in sorted order with patch -p1, configure, build
tools/qemu-ze0/build.sh --force

QEMU=~/.cache/qemu-ze0/build/qemu-system-sh4
"$QEMU" -M none -device sh4-ccn,help        # the device exists

# once the ze0 machine (M8.A2) and the 0xffe70000 stub (M8.A5) exist:
"$QEMU" -M ze0 -cpu sh7785 -m 512M -nographic \
    -d unimp,guest_errors,int -D qemu.log
grep -c '0xff000010' qemu.log     # MMUCR now has a model, no 'Invalid write'
```

TODO M8.A4 is done when the kernel-page call to VA `0x5b90` no longer
faults. With this series that is expected to happen as: `MMUCR.AT` is
stored and reaches the CPU target → the access to `0x5b90` takes the
`0x100` TLB-miss exception instead of `illegal_instruction` → the kernel
handler writes `PTEH`/`PTEL` and executes `LDTLB` → the retry
translates. Two things must be confirmed on the real tree, in this
order:

1. **TLB invalidation on `MMUCR` writes.** If `target/sh4` bakes the
   `MMUCR.AT` bit into TB flags (as `cpu_mmu_index()` does), a write of
   `MMUCR.AT=1` through the hook must flush translation blocks, or the
   already-translated kernel code keeps running untranslated. The old
   inline model did not do this either (the probe never got far enough
   to tell), so this is a likely follow-up hunk in `sh7750_ccn_write()`
   or in the `ze0` CPU glue: `tlb_flush()`/`tb_flush()` when the AT bit
   changes.
2. **`LDTLB` reads the same values.** The helper uses the CPU target's
   `pteh`/`ptel`/`mmucr`; the hook writes those exact fields, so this
   should hold — verify with a breakpoint on `0x5b90` and
   `info registers` showing the expected `PTEH`/`PTEL`.

Record the result in the claim ledger under the M8.A4 block
(`C-1260`–`C-1269`); `C-1260` is the patch-level claim in the EXP.

---

# M8.A5 — boot-blocker register stubs

**Patch:** `0002-sh4-ze0-boot-stubs.patch` · **Task:** TODO **M8.A5** ·
**Record:** [`EXP-2026-11-06-M8.A5-boot-stubs`](../../../docs/experiments/EXP-2026-11-06-M8.A5-boot-stubs.md).
Evidence claims: C-532 (peripheral map), C-533 (boot probe). Model claim:
**C-1270**, EXP-only (the ledger row is the ledger owner's commit).

## B.1 Goal

The patch makes this invocation unnecessary:

```bash
python3 tools/ce_qemu_probe.py IMAGE --patch 0x88048b70=0900
```

`0x88048b70=0900` NOPs the branch that polls `0xffe70808`, i.e. it forces the
kernel past the first boot blocker. In the stub model `0xffe70808` reads
`0xc0000000`, so the kernel's own test `(value & 0xc0000000) == 0xc0000000`
succeeds and the unpatched kernel reaches the point the NOP patch reached
(then the `illegal_instruction` at user VA `0x5b90` from the still-unmodelled
MMU, and the idle loop at `0x8803d266`). The M8.A5 done-when is checked with
**no** `--patch` argument.

## B.2 Apply order

`build.sh` applies every `patches/*.patch` in **sorted order** with
`patch -p1 --forward --batch`. Sorted order today:

| # | File | Task | Touches |
| --- | --- | --- | --- |
| 1 | `0002-sh4-ze0-boot-stubs.patch` | M8.A5 (this) | `hw/sh4/meson.build` (last line), new `hw/sh4/ze0_stubs.c` |
| 2 | `m8a4-0001-hw-sh4-add-sh4-ccn-device.patch` | M8.A4 | new CCN device |
| 3 | `m8a4-0002-hw-sh4-build-sh4-ccn.patch` | M8.A4 | `hw/sh4/meson.build`, `Kconfig` |
| 4 | `m8a4-0003-hw-sh4-sh7750-use-sh4-ccn.patch` | M8.A4 | `hw/sh4/sh7750.c` |

`0` sorts before `m`, so this patch is applied first. It depends on nothing
from the other series and shares no file with it: its `hw/sh4/meson.build`
hunk inserts `sh4_ss.add(files('ze0_stubs.c'))` after `hw_arch += {'sh4':
sh4_ss}`, i.e. on the **last line**, so a top-of-file insert by another
series only shifts the offset.

Exact commands on a pristine pinned tree (8.2.7):

```bash
tar -xJf qemu-8.2.7.tar.xz && cd qemu-8.2.7
P=/path/to/OSM2Leaf/tools/qemu-ze0/patches
git apply --check -p1 "$P/0002-sh4-ze0-boot-stubs.patch"   # rc=0
git apply         -p1 "$P/0002-sh4-ze0-boot-stubs.patch"
./configure --target-list=sh4-softmmu --disable-werror --disable-docs
ninja -C build qemu-system-sh4        # or: make -j"$(nproc)"
```

`patch -p1 --forward --batch -i "$P/0002-sh4-ze0-boot-stubs.patch"` (the
`build.sh` invocation) was also checked: rc=0 on pristine 8.2.7 and rc=0
with a simulated CCN line inserted after line 1 (hunk applied at offset 1).

**Blocker for a full `build.sh` run (2026-11-06):** the sibling
`m8a4-0002-…` and `m8a4-0003-…` hunks were written against 8.2.0 and do
**not** apply to the pinned 8.2.7 tree — `patch --dry-run` fails both hunks
of 0002 and both hunks of 0003. `build.sh` stops at the first failed patch,
so M8.A4 has to rebase before a full run reaches this file. M8.A5 itself is
independent of that series.

## B.3 Device and invocation

`hw/sh4/ze0_stubs.c` adds `TYPE_ZE0_STUBS`, user-creatable as
`-device ze0-stubs`. It is a plain `TYPE_DEVICE` (no bus, no sysbus mmio) that
maps five `MemoryRegion`s into `get_system_memory()` at **priority 1**, so a
machine-wide unimplemented-device catch-all at priority 0 cannot shadow them.
Reasons for a device rather than machine code:

* it needs no `ze0` machine, so it is testable today on `-M none`;
* it does not edit `hw/sh4/ze0.c` (owned by M8.A2) and therefore merges in
  any order;
* `-device ze0-stubs` is explicit about what a run models.

It has **no side effects**: the CPG does not gate clocks, the UBC never
raises a break, area 6 never asserts status, and the `0xffe70000` block never
signals anything except the constant at `+0x808`.

Probe run today, without the machine and without `--patch`:

```bash
cat > /tmp/qemu-ze0-stubs <<'SH'
#!/bin/sh
exec /path/to/qemu-system-sh4 "$@" -device ze0-stubs
SH
chmod +x /tmp/qemu-ze0-stubs
python3 tools/ce_qemu_probe.py IMAGE --qemu /tmp/qemu-ze0-stubs
```

On `-M none -m 512M` the area-6 region (`0x19300000`) shadows DRAM; that is
intentional, because area 6 is external device space, not RAM. On the `ze0`
machine (M8.A2/A3) create the device once in the machine and do **not** add
`-device ze0-stubs` again.

## B.4 Register table

`Size` is the modelled slot width. The probe log does not record the access
size, so the model accepts 1-, 2- and 4-byte accesses and preserves byte
lanes; a 32-bit read of a register returns the 32-bit value shown. `Read-back`
means: a write stores the bytes, a read returns them, and nothing else
happens. All regions ignore accesses beyond their size.

### `ze0-stub-nk-ffe70000` — `0xffe70000`, 0x1000 bytes

| Address | Size | Reset | Access behaviour | Source claim |
| --- | --- | --- | --- | --- |
| `0xffe70094` | 4 | `0x00000000` | R/W read-back | C-533 (access), C-1270 |
| `0xffe7009c` | 4 | `0x00000000` | R/W read-back | C-533, C-1270 |
| `0xffe70800` | 4 | `0x00000000` | R/W read-back; kernel writes 1 | C-533, C-1270 |
| `0xffe70804` | 4 | `0x00000000` | R/W read-back; kernel writes 1, then 3 | C-533, C-1270 |
| **`0xffe70808`** | 4 | **`0xc0000000`** | **RO, constant; writes ignored; kernel polls bits 31:30** | C-533, C-1270 |
| `0xffe7080c` | 4 | `0x00000000` | R/W read-back | C-533, C-1270 |
| `0xffe7081c` | 4 | `0x00000000` | R/W read-back | C-533, C-1270 |
| `0xffe70858` | 4 | `0x00000000` | R/W read-back; kernel sets bit 7 | C-533, C-1270 |
| any other offset in the window | 1/2/4 | `0x00` per byte | R/W read-back, no side effects | C-1270 |

The register names/purpose are unknown (open question "what is at
`0xffe70000`"). Only offsets and offsets' behaviour are modelled.

### `ze0-stub-cpg-ffc80000` — `0xffc80000`, 0x100 bytes

| Address | Size | Reset | Access behaviour | Source claim |
| --- | --- | --- | --- | --- |
| `0xffc80030` | 4 | `0x00000000` | MSTPCR0, R/W read-back | C-532 (literal), C-1270 |
| `0xffc80034` | 4 | `0x00000000` | MSTPCR1, R/W read-back | C-532, C-1270 |
| `0xffc80038` | 4 | `0x00000000` | MSTPCR2, R/W read-back (offset inferred; not directly observed) | C-1270 |
| `0xffc8003c` | 4 | `0x00000000` | MSTPCR3, R/W read-back; R/W seen at boot | C-533, C-1270 |
| `0xffc80040` | 4 | `0x00000000` | plain read-back (unassigned; possibly another MSTPCR) | C-1270 |
| **`0xffc80044`** | 4 | `0x00000000` | **RO; reads the OR of `0xffc80030/34/38/3c` (MSTPACK)** | C-1270 |
| any other offset | 1/2/4 | `0x00` | R/W read-back | C-1270 |

`MSTPACK = OR(MSTPCR0..3)` is the model's reading of "MSTPACK mirrors
MSTPCR": a stopped module's bit shows up when read, and clearing the last
MSTPCR bit clears it. It is a **HYPOTHESIS**: no SH7772x manual is available.
If a real poll at `0xffc80044` ever disagrees, the fallback is last-written
value (see B.5). Reset 0 is chosen so MSTPCR and MSTPACK agree at power-on;
clocks are not gated, so a different reset value cannot change behaviour
except through a read.

### `ze0-stub-fff80000` — `0xfff80000`, 0x100 bytes

| Address | Size | Reset | Access behaviour | Source claim |
| --- | --- | --- | --- | --- |
| `0xfff80008`–`0xfff80018` (4 words) | 4 | `0x00000000` | R/W read-back | C-532, C-1270 |
| any other offset | 1/2/4 | `0x00` | R/W read-back | C-1270 |

Not touched in the 4 s boot log; present because `nk.exe` literal pools
reference `0xfff80008`–`0xfff80018` (C-532). Role unknown.

### `ze0-stub-ubc-ff200000` — `0xff200000`, 0x100 bytes

Register names follow the SH7750 UBC chapter; the names are **HYPOTHESIS**
for this part, the window is not (C-532).

| Address | Size | Reset | Access behaviour | Source claim |
| --- | --- | --- | --- | --- |
| `0xff200000` | 4 | `0x00000000` | BARA, R/W read-back | C-532, C-1270 |
| `0xff200004` | 4 | `0x00000000` | BAMRA, R/W read-back | C-532, C-1270 |
| `0xff200008` | 4 | `0x00000000` | BBRA, R/W read-back | C-532, C-1270 |
| `0xff20000c` | 4 | `0x00000000` | BARB, R/W read-back | C-532, C-1270 |
| `0xff200010` | 4 | `0x00000000` | BAMRB, R/W read-back | C-532, C-1270 |
| `0xff200014` | 4 | `0x00000000` | BBRB, R/W read-back | C-532, C-1270 |
| `0xff200018` | 4 | `0x00000000` | BDRB, R/W read-back | C-532, C-1270 |
| `0xff20001c` | 4 | `0x00000000` | BDMRB, R/W read-back | C-532, C-1270 |
| `0xff200020` | 4 | `0x00000000` | BRCR, R/W read-back; **enabling a channel is latched but never raises a break or exception** | C-532, C-1270 |

Not touched in the 4 s boot log. UBC registers are commonly read back by a
kernel that programs a breakpoint for its debugger; the stub satisfies such
a check without affecting execution.

### `ze0-stub-area6-19300000` — physical `0x19300000`, 0x100 bytes

The kernel reaches this through the uncached P2 alias `0xb9300000`
(`nk.exe` literals `b9300000`–`b9300024`, C-532); the CPU's P2 translation
makes the physical mapping cover it.

| Address | Size | Reset | Access behaviour | Source claim |
| --- | --- | --- | --- | --- |
| `0x19300010` | 4 | `0x00000000` | R/W read-back; kernel writes it | C-533 (`-m 256M`), C-1270 |
| `0x19300014` | 4 | `0x00000000` | R/W read-back; kernel writes it | C-533, C-1270 |
| `0x19300018` | 4 | `0x00000000` | R/W read-back; kernel writes it | C-533, C-1270 |
| `0x19300000`–`0x19300024`, others | 1/2/4 | `0x00` | R/W read-back, no side effects | C-532, C-1270 |

The writes were only logged in the `-m 256M` probe run; with `-m 512M` they
landed in plain RAM. The device roles are unknown. If the kernel later polls
one of these offsets for a ready bit, that becomes the next override.

## B.5 What is hypothesis, and what would falsify it

| Item | Status | Falsified by |
| --- | --- | --- |
| Which offsets the kernel touches | OBSERVED (C-533), 4 s window only | a longer run / `-m 256M` log showing other offsets |
| `0xffe70808 = 0xc0000000` fixes the blocker | HYPOTHESIS (C-1270) | unpatched run still spinning at `0x88048b70` |
| MSTPACK at `0xffc80044`, reset 0, OR of MSTPCR | HYPOTHESIS | a poll at `0xffc80044` that never changes; then switch to last-written value |
| MSTPCR offset/reset values | HYPOTHESIS (0x30/0x34/0x3c observed, 0x38 inferred) | a trace of the real writes (for example from the MMU-enabled run) |
| UBC register names/roles | HYPOTHESIS (SH7750 chapter names) | driver code naming the offsets differently |
| area-6 register roles | UNKNOWN | a firmware trace that waits on a bit |

If `MSTPACK` needs the fallback, replace the mirror descriptor with a plain
R/W register and have its read return the last value written to any MSTPCR
(`0xffc80030/34/38/3c`); that is a 10-line change in `cpg_regs` +
`ze0_reg_word()`.

## B.6 Verification performed here (2026-11-06)

**From the repository alone (no QEMU tree) this patch is UNVERIFIED: it cannot
be compiled.** The environment used for this record had the pinned 8.2.7
tarball cached, so the checks below were possible; a fresh checkout of this
repository needs `build.sh` (network) or a pre-seeded tarball first.

Against the locally cached pinned tarball
`qemu-8.2.7.tar.xz` (SHA-256
`1f0604f296ab9acb4854c054764a1ba408643fc299bd54a6500cccfaaca65b55`, same as
the M8.A1 pin), on Linux x86_64 (gcc 15.2.0, ninja 1.13.2):

1. `git apply --check -p1` on a pristine 8.2.7 tree: **rc=0**.
2. `patch -p1 --forward --batch --dry-run -i` : **rc=0**, also with a
   simulated `sh4_ss.add(when: 'CONFIG_SH4_CCN', …)` inserted after line 1
   (hunk at offset 1, still rc=0).
3. `./configure --target-list=sh4-softmmu --disable-werror --disable-docs`
   and `ninja qemu-system-sh4`: **compiles and links** (object
   `libqemu-sh4-softmmu.fa.p/hw_sh4_ze0_stubs.c.o`).
4. `qemu-system-sh4 -M none -device help` lists
   `name "ze0-stubs", desc "ZE0 (SH-4A nav unit) boot-blocker register stubs"`.
5. `-M none -cpu sh7785 -m 512M -device ze0-stubs -qtest` reads and writes:
   * `read 0xffe70808 4` → bytes `c0 00 00 00` (`0xc0000000`); a write of 0
     to it changes nothing (RO);
   * `write 0xffe70858 4 0x80000000` (bytes `80 00 00 00`) is read back;
   * `write 0xffc80030 4 0x01000000` (register value 1) and
     `write 0xffc8003c 4 0x00000080` (register value `0x80000000`) are read
     back unchanged, and `read 0xffc80044 4` returns bytes `01 00 00 80`,
     i.e. `0x80000001` (the OR);
   * after clearing `0xffc80030`, `0xffc80044` returns `0x00000080`.

**Not verified:** a boot of `nk.exe` with the stubs (no vendor image on this
machine) and therefore the M8.A5 done-when itself. Compilation/runtime of the
patch in `build.sh`'s tree is blocked by the M8.A4 rebase noted in B.2, not
by this file.

## B.7 Next step on a machine with the QEMU tree and the image

1. Rebase/apply M8.A4's 0002/0003 to 8.2.7 (or run with `--no-patch` and
   apply only this patch), then apply this patch and build.
2. Boot **unpatched** (no `--patch`) with
   `-device ze0-stubs -d unimp,guest_errors,int -D qemu.log` and compare the
   first-seen access list and the final PC with EXP-2026-11-05-37's patched
   run: expect `0xffe70800/04/08/58` to be absent from the invalid-access
   list, `0xffc8003c` present, and the run to continue to the same
   `illegal_instruction` at `0x5b90` / idle at `0x8803d266`.
3. If it still stops at `0xffe70808`, record the access size (add `size` to
   `summarize_log`); the model already slices the constant for 1/2-byte
   accesses, so a failure points at a second poll address, not at width.
4. Then continue with M8.A4 (MMU) and M8.B1/B2 (INTC, TMU).
