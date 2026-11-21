# Porting the `ze0` patch series from QEMU 8.2.7 to 11.1.3

> **M8.A11 (2026-11-21):** 11.1.3 is now the only supported version; the
> ported series moved to `tools/qemu-ze0/patches/` and the 8.2 one was removed.
>
> **Outcome (M8.A9, 2026-11-21):** the port is done — `tools/qemu-ze0/patches/11.1/` (since M8.A11 merged into `tools/qemu-ze0/patches/`, the only series),
> twelve patches, builds and boots (EXP-2026-11-21-M8.A9-qemu-11-port). This
> document stays as the pre-port inventory of the first five patches; §8 lists
> what it missed.

Measured inventory for TODO **M8.A9**. Every claim here is a file:line read
from a real tree, or a command whose output is quoted. Trees:

- `8.2.7` — `qemu-8.2.7.tar.xz`, SHA-256 `1f0604f2…65b55` (the pin).
- `8.2.10` — SHA-256 `37b4a643…ab2bb`; its `hw/sh4`,
  `configs/devices/sh4-softmmu` and `include/hw/sh4` trees are **byte-identical**
  to 8.2.7 (`diff -r` empty), so the whole series applies unchanged.
- `11.1.3` — `qemu-11.1.3.tar.xz`, SHA-256 `5a8289c7…84b22`; full source.

## 0. The two traps that produced wrong conclusions

1. **The UTLB/ITLB helpers are not removed.** They are spelled **`mmaped`**
   (one `p`): `cpu_sh4_{read,write}_mmaped_{itlb,utlb}_{addr,data}`, all
   eight at `target/sh4/helper.c:514-711`, declared `target/sh4/cpu.h:259-273`.
   A double-p `mmapped` grep finds nothing and *looks like* a refutation.
   The `sh4-ccn` device body is a **mechanical copy**, not a rewrite.
2. **`DeviceClass.reset` was removed.** The field is `legacy_reset`
   (`include/hw/core/qdev.h:173`), set with
   `device_class_set_legacy_reset()` (`:975`). This breaks the class init in
   both new devices.

A third correction: `hw/sh4/Kconfig` and `hw/sh4/meson.build` **still exist**
in 11.1.3 and their `R2D`/`SH7750` stanzas are unchanged. The rejections are
not "Kconfig moved"; they are fuzz against a deleted `CONFIG_SHIX` line, one
deleted context line, and include renames.

## 1. Two application columns, both true

`build.sh` runs `patch -p1 --forward --batch`; CI-style checks use
`git apply --check`. They disagree:

| Patch | `patch -p1` on 11.1.3 | `git apply --check` |
| --- | --- | --- |
| `0002-sh4-ze0-boot-stubs` | `rc=0`, 1 hunk succeeded (fuzz) | rejected (`hw/sh4/meson.build:7`) |
| `m8a4-0001` (new files) | `rc=0` | **applies** |
| `m8a4-0002` (build wiring) | `rc=0`, 3 hunks succeeded (fuzz) | rejected (`meson.build:3`, `Kconfig:1`) |
| `m8a4-0003` (`sh7750.c`) | `rc=1`, 4/7 hunks FAILED | rejected (`sh7750.c:28`) |
| `ze0-0001` (machine) | `rc=1`, 4 hunks FAILED | rejected (`default.mak:9`, `Kconfig:20`) |

Apply success is therefore **not** the gate; a compile is. Fuzz also hides
the `CONFIG_SHIX` deletion, so a fuzz-applied hunk can land in the wrong
place.

## 2. `0002-sh4-ze0-boot-stubs.patch` (M8.A5) — stub device

New file `hw/sh4/ze0_stubs.c` (312 lines) plus one meson line.

| Item | 8.2.7 | 11.1.3 | Action |
| --- | --- | --- | --- |
| `exec/address-spaces.h` | exists | gone; `get_system_memory()` in `include/system/address-spaces.h:25` | rename |
| `exec/memory.h` | exists | `include/system/memory.h` | rename |
| `hw/qdev-core.h` | exists | `include/hw/core/qdev.h` | rename |
| `memory_region_init_io` | — | `include/system/memory.h:1104`, same 6 args | none |
| `MemoryRegionOps` | — | `include/system/memory.h:292` | none |
| `dc->reset = …` | `DeviceReset reset` | `legacy_reset` + setter | replace |
| `qemu/module.h`, `qemu/bitops.h`, `qemu/bswap.h` | — | present | none |
| meson hunk | inserts after `hw_arch += …` | the preceding `CONFIG_SHIX` line was deleted, so apply by hand after `hw/sh4/meson.build:8` | hand insert |

`hw/sh4/meson.build` in 11.1.3 is 8 lines with no `shix.c`; `SHIX` is gone
entirely (no file, no Kconfig stanza), which is the sole reason both meson
hunks fail.

## 3. `m8a4-0001` + `m8a4-0002` — the `sh4-ccn` device (M8.A4)

`include/hw/sh4/sh4_ccn.h` (73 lines) + `hw/sh4/sh4_ccn.c` (323 lines) +
meson/Kconfig wiring. Applies cleanly; **does not compile** without:

| Item | Delta | Action |
| --- | --- | --- |
| `exec/memory.h` → `system/memory.h`, `hw/qdev-core.h` → `hw/core/qdev.h` | include renames | rename |
| `exec/exec-all.h` | gone; `tlb_flush()` in `include/exec/cputlb.h:127` | rename |
| `dc->reset` | `legacy_reset` | setter |

Everything the device *does* survives unchanged:

| Symbol | 11.1.3 |
| --- | --- |
| `cpu_sh4_invalidate_tlb` | `target/sh4/helper.c:496`, decl `cpu.h:258` |
| `cpu_sh4_{read,write}_mmaped_{itlb,utlb}_{addr,data}` | `helper.c:514-711`, decl `cpu.h:259-273` |
| `CPUSH4State.{mmucr,pteh,ptel,ptea,ttb,tea,tra,expevt,intevt}` | `target/sh4/cpu.h:175-183` |
| `MMUCR_TI` | `target/sh4/cpu.h:289` |
| `SuperHCPUClass.{pvr,prr,cvr}` | `target/sh4/cpu.h:229-244` |
| `CPUSH4State.ccr` | still absent (which is why the device owns `ccr`) |

`m8a4-0002` has no API change: both Kconfig stanzas and the `hw_arch` line
still exist. Its three hunks only need to land above `SH7750` (and the
obsolete "R2D and SHIX both select SH7750" note dropped, since `SHIX` is gone).

## 4. `m8a4-0003` — make `sh7750.c` reuse the device

`sh7750_mem_readl` (`:212`), `sh7750_mem_writel` (`:332`), `sh7750_init`
(`:713`), `mmct_iomem` (`:50`), `uint32_t ccr` (`:79`) and
`sh7750_mmct_{read,write,ops}` (`:627/671/707`) all still exist in 11.1.3.

| Hunk | State | Cause | Action |
| --- | --- | --- | --- |
| 1 includes | FAIL | expects `hw/sysbus.h`/`hw/irq.h`, now `hw/core/…` | insert `#include "hw/sh4/sh4_ccn.h"` by hand |
| 2 `mmct_iomem`→`ccn` | ok (−1) | — | — |
| 3 drop `ccr` | FAIL | context `devices[NB_DEVICES]` was deleted upstream; `ccr` remains at `:79` | delete by hand |
| 4 readl collapse (9 cases) | ok (−52) | cases intact `:231-247` | — |
| 5 writel collapse (10 cases) | ok (−52) | cases intact `:370-404` | — |
| 6 delete cache/TLB block | FAIL | 11.1.3 **removed** `abort()` after `cpu_sh4_write_mmaped_itlb_data` (`8.2.7:741` has it, `11.1.3:687` does not) | delete `MM_REGION_*`/`invalid_*`/`sh7750_mmct_*` (`:609-710`) by hand |
| 7 `sh7750_init` CCN create | ok (−53) | `object_new`, `qdev_realize` present | — |

**One real semantic divergence:** the copied block keeps `abort()` on an
ITLB-data write; 11.1.3 deliberately dropped it. Porting must choose, and say
which: reproduce 8.2.7 (keep the abort) or adopt 11.1.3. Not a compile error
either way, so silence would be a defect.

## 5. `ze0-0001` — the `ze0` machine (M8.A2)

| Hunk | State | Delta |
| --- | --- | --- |
| 1 `default.mak` | FAIL | **mechanism change:** 8.2.7 has `CONFIG_R2D=y`/`CONFIG_SHIX=y`; 11.1.3 has only comments. `CONFIG_ZE0=y` is still read (`meson.build:3400-3408`), but the idiom is `default y` in Kconfig |
| 2 `config ZE0` | ok (fuzz 2) | add `default y` + `depends on SH4` like `R2D` (`hw/sh4/Kconfig:1-4`) |
| 3 meson | FAIL | expects the deleted `CONFIG_SHIX` line; insert against `hw/sh4/meson.build:8` |
| 4 `ze0.c` (new) | applies, won't compile | includes below |

| Patch include | 11.1.3 |
| --- | --- |
| `"cpu.h"` | use `"target/sh4/cpu.h"` (what `r2d.c:30` uses) |
| `hw/boards.h` | `include/hw/core/boards.h` |
| `hw/loader.h` | `include/hw/core/loader.h` |
| `hw/qdev-properties.h` | `include/hw/core/qdev-properties.h` |
| `sysemu/sysemu.h` | `system/system.h` |

Body APIs all survive with the same use: `cpu_create`
(`include/hw/core/cpu.h:855`), `machine->cpu_type` (`boards.h:443`),
`memory_region_init_ram` (now returns `bool`, `system/memory.h:1355`),
`create_unimplemented_device` (`hw/misc/unimp.h:41`), `qdev_new`/
`qdev_realize_and_unref` (`hw/core/qdev.h:419/490`), `get_system_memory`
(`system/address-spaces.h:25`), `DEFINE_MACHINE` (`boards.h:537`),
`TYPE_SH7785_CPU` (`target/sh4/cpu-qom.h:29`), `default_ram_size/id`
(`boards.h:302/323`). `object_property_set_link` is not used.

Machine registration: `configs/devices/<target>/default.mak` is still read;
new machines are `default y` in `hw/sh4/Kconfig`, not a `CONFIG_*=y` line.
`hw_arch += {'sh4': sh4_ss}` still exists (`hw/sh4/meson.build:8`).

## 6. Porting order

1. **Decide first:** the ITLB-data `abort()` semantics; the Kconfig
   `default y` idiom; whether the pin becomes a tested range.
2. **Mechanical renames:** `exec/*`→`system/*`, `hw/{boards,loader,
   qdev-properties,sysbus,irq}.h`→`hw/core/…`, `hw/qdev-core.h`→
   `hw/core/qdev.h`, `sysemu/sysemu.h`→`system/system.h`, `"cpu.h"`→
   `"target/sh4/cpu.h"`; `dc->reset`→`device_class_set_legacy_reset()`.
3. **Feed as-is then fix:** `m8a4-0001`/`0002`, and hunks 2/4/5/7 of `0003`.
4. **Hand-edit:** meson/Kconfig hunks (the `CONFIG_SHIX` gap) and hunks 1,
   3 and 6 of `0003`.
5. **Judge by build and boot**, not by apply: `-M help` lists `ze0` and a
   10 s `-M ze0` run of `archive/head256.img` gives 0 exceptions and one
   `write 0x38` (C-4311).

## 7. Reproduce this document

```bash
mkdir -p ~/projekty/leafre-work/scratch/qemu-port && cd $_
curl -sSLO https://download.qemu.org/qemu-11.1.3.tar.xz
sha256sum qemu-11.1.3.tar.xz        # 5a8289c7940dc77d3873c81a6c29ba3afe1446fc9d36e77fa1658cdbecb84b22
tar xf qemu-11.1.3.tar.xz && cd qemu-11.1.3
P=/path/to/OSM2Leaf/tools/qemu-ze0/patches
for p in $(ls "$P"/*.patch | LC_ALL=C sort); do
  printf '%-46s ' "$(basename "$p")"
  patch -p1 --forward --batch --dry-run -i "$p" >/dev/null 2>&1 && echo OK || echo FAIL
done
# expect: OK OK OK FAIL FAIL (the two com/... columns in §1)
grep -n 'mmaped' target/sh4/cpu.h | head -2     # not "removed"
test -e include/exec/exec-all.h || echo 'exec-all.h gone'
grep -n 'legacy_reset' include/hw/core/qdev.h | head -2
```

The `8.2.7` side of the same loop prints five `OK`; 8.2.10 is byte-identical
for the patched files.

## 8. What the port found beyond this inventory (M8.A9)

The inventory above was read from headers and covers five patches; the
series had twelve by the time of the port, and compiling all of them on
11.1.3 found four more deltas (C-4324):

| Delta | Where it bites | Port |
| --- | --- | --- |
| `TypeInfo.class_init` takes `const void *data` | all five class-init functions; only a `-Wincompatible-pointer-types` warning, but a real signature mismatch | `const void *data` |
| `DEFINE_PROP_END_OF_LIST()` removed; `device_class_set_props()` takes a `const Property[]` sized by the compiler | `ze0_sdhi.c` (compile error) | `static const Property …[]`, no terminator |
| `sdbus_do_command()` takes the response buffer size and returns `size_t` | `ze0_sdhi.c`, four calls (compile error) | pass `sizeof(r)` |
| "Invalid read/write at addr" is logged under the new `-d invalid_mem`, no longer under `guest_errors` | not a build error: `run.sh`/`ce_qemu_probe.py` print an **empty** access list on 11.x | both scripts add `invalid_mem` when `-d help` lists it (C-4323) |

Decisions taken (§6 step 1): the ITLB data-array `abort()` is dropped, as
upstream did; `ZE0` is `default y` + `depends on SH4` in Kconfig; the pin is
a tested range with one series per API generation. Step 5's oracle ("0
exceptions and one `write 0x38`") describes the five-patch skeleton of
2026-11-17 and no longer holds on **either** version: the twelve-patch
machine boots Windows CE and takes about 29,000 exceptions in 10 s. The port
is judged against the 8.2.10 build of the same twelve patches instead.
