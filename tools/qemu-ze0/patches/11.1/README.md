# `ze0` patch series for QEMU 11.x (TODO M8.A9)

The same twelve patches as [`../`](../README.md), ported to **QEMU 11.1.3**
(tag `v11.1.3`, tarball SHA-256
`5a8289c7940dc77d3873c81a6c29ba3afe1446fc9d36e77fa1658cdbecb84b22`,
141819712 bytes). File names are identical, so "patch N" means the same
thing in both series; what each patch does is documented in `../README.md`
and in the header of the 8.2 patch. This file only records what the port
changed. Evidence:
[`EXP-2026-11-21-M8.A9-qemu-11-port`](../../../../docs/experiments/EXP-2026-11-21-M8.A9-qemu-11-port.md).

`tools/qemu-ze0/build.sh --version 11.1.3` picks this directory by itself
(any version `>= 11.0`); `--version 8.2.10` (the default) keeps `../*.patch`.

```bash
tools/qemu-ze0/build.sh --check-version 11.1.3     # 12 applied, 0 failed
tools/qemu-ze0/build.sh --version 11.1.3           # fetch, verify, patch, build, -M help
```

## Status

| Check | Result |
| --- | --- |
| Applies to pristine 11.1.3 | all 12, `patch -p1 -F0` (no fuzz, no offset) and `git apply --check` |
| Builds | `qemu-system-sh4` 11.1.3 links; no warning in any file the series adds or edits |
| `-M help` | lists `ze0`; `r2d` still initialises and maps `sh4-ccn` |
| Boot of `archive/head256.img` | same kernel debug text, same API-trap sequence and same unmodelled-access list as the 8.2.10 build of `../*.patch` (EXP) |
| Not checked | each patch building on its own (only the whole series was compiled); QEMU 9.x and 10.x; runs longer than 10 s wall clock |

## What the port changed

Mechanical renames, applied to added lines and to context lines alike:

| 8.2 spelling | 11.1.3 spelling |
| --- | --- |
| `exec/address-spaces.h`, `exec/memory.h` | `system/address-spaces.h`, `system/memory.h` |
| `exec/exec-all.h` (for `tlb_flush`) | `exec/cputlb.h` |
| `hw/qdev-core.h` | `hw/core/qdev.h` |
| `hw/{sysbus,irq,boards,loader,qdev-properties,qdev-properties-system}.h` | `hw/core/…` |
| `sysemu/{sysemu,reset,blockdev}.h` | `system/{system,reset,blockdev}.h` |
| `"cpu.h"` | `"target/sh4/cpu.h"` |
| `dc->reset = f;` | `device_class_set_legacy_reset(dc, f);` |
| `…_class_init(ObjectClass *, void *data)` | `…_class_init(ObjectClass *, const void *data)` |
| `static Property p[] = { …, DEFINE_PROP_END_OF_LIST() }` | `static const Property p[] = { … }` |
| `sdbus_do_command(bus, &req, resp)` → `int` | `sdbus_do_command(bus, &req, resp, sizeof(resp))` → `size_t` |

The last three rows are **not** in
[`qemu-ze0-port-delta.md`](../../../../docs/research/qemu-ze0-port-delta.md)
§§2–5: that inventory was read from headers for the first five patches; these
were found by compiling all twelve.

Per patch, beyond the renames:

| Patch | Hand work |
| --- | --- |
| `0002-sh4-ze0-boot-stubs` | meson line re-anchored (the `CONFIG_SHIX` context line is gone) |
| `m8a4-0001` (`sh4-ccn`) | **the `abort()` after an ITLB data-array write is dropped** — see below |
| `m8a4-0002` | hunks re-anchored only |
| `m8a4-0003` (`sh7750.c`) | hunks 1 and 3 re-anchored; hunk 6 redone by hand: the block `MM_REGION_MASK` … `sh7750_mmct_ops` is deleted as it stands in 11.1.3 (which no longer has the `abort()` the 8.2 hunk expected) |
| `ze0-0001` (machine) | `config ZE0` gains `default y` + `depends on SH4` (the 11.x idiom, as `R2D`); `default.mak` gets the commented `# CONFIG_ZE0=n` line instead of `CONFIG_ZE0=y`; meson line re-anchored |
| `ze0-0002` … `ze0-0007` | renames and offsets only (`target/sh4/{cpu.h,helper.h,op_helper.c,translate.c}` hunks land unchanged) |
| `ze0-0008` (SD host) | `sdbus_do_command` and `Property` rows above; meson line re-anchored |

## The one semantic decision: ITLB data-array write

8.2's `sh7750_mmct_write` called `abort()` right after
`cpu_sh4_write_mmaped_itlb_data()`, and the 8.2 `sh4-ccn` device copied that.
Upstream removed the `abort()`; the helper itself is unchanged apart from a
type spelling. The 11.x port **follows upstream**: the write is performed and
the emulator keeps running. Reasons: (1) `r2d` on a patched 11.1.3 then
behaves exactly as `r2d` on stock 11.1.3, which is the purpose of
`m8a4-0003`; (2) no new MMU path is invented, the helper call is the one both
versions already make; (3) it is unobservable in the measured boot: the 8.2.10
build, which keeps the `abort()`, runs the same 10 s without aborting, so
the guest performs no such write there. A later boot stage that does write
the ITLB data array would kill an 8.2 build and continue on 11.x; that
difference is intended and recorded as C-4322.

## Regenerating the series

The series is the `git diff` of twelve commits on a pristine 11.1.3 tree.
To rebase it on a newer release: extract the tarball, `git init && git add -A
&& git commit`, apply each patch here with `patch -p1`, fix what rejects,
build (`configure --target-list=sh4-softmmu --disable-fdt`), commit per
patch and write `git diff C^ C` under the same file name with the four
header lines kept. Then `build.sh --check-version V` must print
`12 applied, 0 failed`.
