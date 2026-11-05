# Full-system emulation of the ZE0 nav unit vs. module-level (L3) emulation

> **Status:** research record, 2026-11-05. Evidence from
> [`EXP-2026-11-05-37`](../experiments/EXP-2026-11-05-37-qemu-boot-probe.md)
> and `tools/ce_qemu_probe.py`; claims C-530…C-537. Effort figures are
> `HYPOTHESIS` (engineering estimates, not measured).
> Updates the "Option B" verdict in [`feedback-loop.md`](feedback-loop.md) and
> the "Emulation verdict" in [`../format/firmware.md`](../format/firmware.md),
> which were written before the CE ROM TOC was recovered.

## Short answer

- **The kernel already runs on stock QEMU.** With nothing but RAM and an
  SH-4A CPU (`qemu-system-sh4 -M none -cpu sh7785`), `nk.exe` from image B
  executes from its entry point through cache/MMU setup, clock gating,
  interrupt-controller and timer init, and into the scheduler. It stops at
  the first thing a real board model must provide (the MMU control registers).
  This is much further than the earlier "dies in `OEMInit`" estimate.
- **The SoC is a Renesas SH-4A car-navigation part, not the SH7750/SH7751
  that QEMU models.** The BSP name `R0P7772A00020S` (Renesas board-numbering
  scheme) and the peripheral map point to the SH-Navi/SH-NaviJ family
  (SH7772x). No public hardware manual for it was found; the peripheral
  layout looks like the SH7780/SH7785 generation (SCIF, TMU, CPG `MSTPCR`).
- **Booting to a shell-less idle kernel with a debug log is cheap** (days to
  two weeks). **Booting to `Navi.exe` reading the SD card is a multi-month
  board bring-up**, and getting the map onto an emulated screen depends on an
  undocumented graphics block and may not be feasible at all.
- **Recommendation:** build the module-level harness first (L3, extended to a
  "CE high-level emulation" harness that runs the real modules at their real
  VAs with stubbed `COREDLL`), using QEMU as a fast CPU and Ghidra for
  analysis. Run a **time-boxed full-system spike** (stages F0–F1, about one
  week) in parallel, because it is cheap, it gives a live kernel log, and the
  real kernel can serve as the decompressor/loader for the compressed module
  sections. Continue to F2/F3 only if L3 hits a wall that needs the running
  OS (runtime COM objects, threads, window messages). The bench (L4) remains
  the acceptance oracle.

## 1. What the hardware is

All addresses below come from `nk.exe` (image B, uncompressed `.text`) and
the uncompressed `.text` sections of the B drivers, via `tools/cerom.py`
section offsets and `sh4-linux-gnu-objdump` literal-pool loads. Code sections
are never `IMAGE_SCN_COMPRESSED`; only RW data is (C-530).

### CPU and BSP

| Fact | Evidence | Status |
| --- | --- | --- |
| Windows CE 5.0, "Windows CE Kernel for Hitachi SH Built on Oct 23 2008" | string in image B `nk.exe` | VERIFIED |
| OEM platform `CETUS` (`C:\WINCE500\platform\CETUS\target\SH4\retail\*.pdb`); OEM tree under `C:\fuji\WINCE500\PRIVATE\Automotive\…` | PDB paths in A, B, C | VERIFIED |
| Renesas reference BSP `R0P7772A00020S` (`SdCardLch.pdb`, image C) | PDB path | VERIFIED (string); SoC part = HYPOTHESIS |
| CPU core runs on QEMU's `sh7785` (SH-4A) model up to the scheduler | EXP-37 | VERIFIED |
| `ROMHDR.usCPUType = 0x01a6` (generic SH-4), so the CE build itself does not prove SH-4A | `cerom.py romhdr` | VERIFIED |

Renesas names evaluation boards `R0P<chip>…` (e.g. `R0P7785LC0011RL` for
SH7785). `R0P7772…` therefore points to an SH7772x part; the SH-NaviJ series
(SH77721 from 2008, SH77722 later) is the matching product line: SH-4A core,
2D/3D graphics, USB host, SD host, CAN, GPS baseband, FM multiplex decoder.
The firmware has drivers for exactly that set (`UsbOhci`, `SDHC`, `CAN`,
`navdrv`, `fmmdrv`, `gdisubdrv`). The exact part number is **not** proven.

### Physical memory map (observed)

| Physical range | Content | Evidence |
| --- | --- | --- |
| `0x08000000`–`0x086e18a4` | kernel image B (or C) as XIP, VA `0x88000000` | ROMHDR `physfirst/physlast` |
| `0x09980000`–`0x09e40000` | reserved RAM for driver DMA buffers (`serial_scif` `0x0999xxxx`, `SDHC` `0x09980a00`/`0x099c1000`, `wavessi1` `0x09981000`, `VSram` `0x09a40000`, `FlashManager` `0x09b40000`, `kepdrv` `0x09a01000`) | driver literals (uncached P2 `0xa99…`) |
| `0x09e40000`–`0x0cae1000` | CE RAM (`ulRAMStart`…`ulRAMEnd` of image A) | ROMHDR |
| `0x0cae1000`–`0x0e233c88` | application image A as XIP, VA `0x8cae1000` | ROMHDR |
| `0x0e600000`– | above `ulRAMEnd` of B; probably frame buffers / graphics | HYPOTHESIS |
| `0x10000000`– (area 4) | read by the kernel during init; heavy use of `0x10000000`-based constants in `gdisubdrv`, `ddddifull`, `DspDrv` | OBSERVED; role HYPOTHESIS (graphics/DSP block or more DRAM) |
| `0x19300000`, `0x19400000`, `0x19800000`, `0x19a00000`, `0x19b00000`–`0x19e00000` (area 6) | external devices: kernel (`0x19300000`, regs `0x00`–`0x24`), `GPIO`/`CAN` (`0x19400000`), `navdrv` (`0x19800000`), `Bolero` (`0x19a00000`), `serial_uat` (four external UARTs) | driver literals |

### On-chip peripherals (P4 area, `0xFFxxxxxx`)

| Address | User | Likely block | QEMU reuse |
| --- | --- | --- | --- |
| `0xff000000`–`0xff000024` | nk | CCN/MMU: `PTEH`, `PTEL`, `TTB`, `TEA`, `MMUCR`, `CCR`, `EXPEVT` | yes: `hw/sh4/sh7750.c` (needs to be factored out of the r2d SoC) |
| `0xf0000000`, `0xf4000000` | nk | IC/OC address arrays (cache flush) | yes: `sh7750.c` |
| `0xff200000` | nk | UBC (break controller) | stub |
| `0xff801000`, `0xff801418` | nk, `serial_scif`, `SDHC`, `wavessi1` | DMAC (shared by every DMA-using driver) | new model |
| `0xff802000`–`0xff802064`, `0xff804000`–`0xff804088` | nk (`0x40`/`0x44` written with `1<<n`) | interrupt controller (mask set/clear) | new model |
| `0xffc08000`, `0xffc0880c`–`0xffc08814` | nk, `serial_scif`, `SDHC`, `wavessi1` | DMA request mux or clock/reset control | new model / stub |
| `0xffc80030`–`0xffc80044` | nk | CPG `MSTPCR0/1`, `MSTPACK` (SH7780 layout) | stub (read-back) |
| `0xffc41000`–`0xffc43000` | `GPIO` | GPIO ports | stub |
| `0xffc55000` | `fmmdrv` | FM multiplex (RDS/TMC) decoder | stub |
| `0xffc5a000`, `0xffc5b000` | `navdrv`, `kepdrv`, nk | GPS/odometer pulse capture or timers | stub |
| `0xffc71000` | `I2C` | I²C master | stub |
| `0xffd80000`, `0xffd81000` | nk, `kepdrv` | TMU (`TSTR`, `TCOR`, `TCNT`, `TCR`) | yes: `hw/timer/sh_timer.c` (address/IRQ glue) |
| `0xffe00000` | `wavessi1` | SSI audio | stub |
| `0xffe40000`–`0xffe48000` | `serial_scif` | SCIF channels (8, stride `0x1000`) | yes: `hw/char/sh_serial.c` |
| `0xffe46000` | nk | **kernel debug serial**: polls `SCFSR` (`+0x10`) for `TDFE` (`0x20`), writes `SCFTDR` (`+0x0c`), clears `TDFE`/`TEND` | yes: `sh_serial.c` has the same layout |
| `0xffe4c000`, `0xffe4d000` | `SDHC`, nk | two SD host controllers | **new model** (no Renesas SD host in QEMU) |
| `0xffe70000`–`0xffe7081c` | nk | unknown; first boot blocker (reset, then poll `+0x808` until bits 31:30 set) | stub |
| `0xfff80000`–`0xfff80018` | nk | unknown | stub |

### Boot chain

The SD card holds **no bootloader**: sector 0 is a bare MBR (one FAT32
partition at `0x06400400`), and the pre-partition area holds only the CE images
(each with a `0x200`-byte header whose first `u32` is the image length,
`physlast − physfirst`), a `BASSB` blob at `0x05c00000` and the `HDD_INFO`
copy at `0x06000000`. The IPL is therefore in on-board flash
(`flash.dll`/`FlashManager.dll`, `UpdateNK.skn`), and it copies B or C plus A
into DRAM. For emulation this is good news: the emulator can play the
bootloader (copy the images, set the PC to the `nk.exe` entry `0x8800ebd0`);
no boot ROM dump is required. Which of B or C a real boot uses is still
unknown (C-529); both reach the same first blocker in QEMU.

## 2. What was tried (EXP-2026-11-05-37)

`tools/ce_qemu_probe.py` loads B at `0x08000000` and A at `0x0cae1000` into a
512 MB `none` machine with an `sh7785` CPU, sets the PC to `0x8800ebd0` and
logs every unmodelled register access:

1. Unpatched: the kernel sets up `CCR`/`MMUCR`, gates clocks via `0xffc8003c`,
   and spins forever on `0xffe70808` (expects bits 31:30 set).
2. With that branch NOPed (`--patch 0x88048b70=0900`): it continues through
   the interrupt controller (`0xff802000…`, `0xff804000…`), programs TMU0
   (`0xffd80004…0x1c`), flushes the cache arrays, copies its data, and enters
   the scheduler. It then calls the kernel-page interlocked stub at user VA
   `0x00005b90`. Because `MMUCR` writes went nowhere, the MMU is off, the
   address resolves to empty physical RAM, the CPU raises
   `illegal_instruction`, and the kernel ends in its idle `sleep` (PC
   `0x8803d266`) with no timer interrupt to wake it.

50 distinct register addresses were touched before that point. No debug
string was printed yet (the debug SCIF at `0xffe46000` was not reached).

Lesson: the CPU and memory side is not the problem. The next steps are
mechanical (MMU registers, interrupt controller, timer), and QEMU already has
models for three of them.

## 3. Emulator options

| Option | Fit | Notes |
| --- | --- | --- |
| **QEMU, new machine `ze0`** (C, out-of-tree or fork) | **best** | `sh7785` CPU runs the code (EXP-37); reuse `sh_serial`, `sh_timer`, the CCN/MMU part of `sh7750.c`; add RAM layout, INTC, DMAC, stubs. gdbstub, `-d` tracing, snapshots, TCG speed. Upstream SH-4 is in maintenance mode, so expect to carry patches. |
| QEMU `r2d` as is | no | SDRAM is fixed at `0x0c000000` (64 MB) and overlaps image A; `sh7750.c` aborts on unknown registers; peripheral addresses differ. |
| MAME SH-4 | possible | richer device framework, but SH-4 on-chip peripherals are incomplete and SH-4A is not the target there (C-511). No advantage over QEMU now that QEMU runs the kernel. |
| sh3-emu, CERF | reference only | SH-3/CE 1–2 and ARM/MIPS respectively (C-512, C-513). sh3-emu's Clarion AutoPC board model is a useful design reference. |
| Unicorn | no | no SH-4 target. |
| Ghidra P-code (SuperH4) | L3 only | good for single functions and for analysis; too slow and too limited for a whole OS. |

## 4. Full-system work breakdown

Stages are cumulative. Each has a stop condition, per AGENTS.md rule 6.

| Stage | Goal | Work | Effort (HYPOTHESIS) | Main risk |
| --- | --- | --- | --- | --- |
| **F0** | kernel debug log on stdout | `ze0` machine: RAM `0x08000000`+, CCN/MMU + cache arrays from `sh7750.c`, `sh_serial` at `0xffe46000`, read-back stubs for every address in §1, `0xffe70808` returns `0xc0000000`; loader = `ce_qemu_probe.py` logic | 3–5 days | debug output may be disabled in the retail build; then F0 = "MMU on, no fault" |
| **F1** | scheduler ticks, kernel idles stably | INTC model reverse-engineered from the OAL (`OEMInterruptEnable/Disable/Done`, ISR at `VBR+0x600`), TMU0 IRQ, `OEMIdle` | 1–2 weeks | INTC layout is custom; must be read from nk code |
| **F2** | `filesys.exe` + registry + `device.exe` load drivers | answer every driver's init path: stub or model (`GPIO`, `I2C`, `PowerMonitor`, `flash` NOR model for `FlashManager`, external UARTs) | 2–4 weeks | a driver that blocks boot on a missing micon/CAN answer |
| **F3** | the FAT partition of the SD image is mounted | SD host model for `0xffe4c000` (+ DMAC), backed by QEMU's `sd-card` device; alternative: trap `SDHC.dll` exports and serve sectors from the host (HLE block driver) | 2–4 weeks (HLE: ~1 week) | undocumented Renesas SD host; DMA |
| **F4** | `AppLaunch`/`Navi.exe` start and read map files (headless) | `gwes` + display driver (`lcddrv`, `ddddifull`, `gdisubdrv`) must not fail; vehicle micon via `serial_uat`/`CAN.dll` replayed or stubbed; `HDD_INFO` check observable in traces | 1–3 months | unknown micon protocol; graphics init; watchdogs |
| **F5** | map on an emulated screen, touch input | graphics/2D-3D engine model (area 4?), display unit, touch panel | open-ended; may be infeasible | no documentation for the graphics block |

What a full system gives that L3 cannot: the real loader (decompressed
sections, relocations, COM registration), real registry contents, threads and
messages, the order of file accesses at boot, and the `HDD_INFO`/map-code
decision in its real context. What it costs: the board model, which must be
kept faithful enough that a "pass" means something; for anything beyond F4 the
bench is cheaper.

## 5. L3 and its extension ("CE-HLE")

L3 as designed in [`l3-ghidra.md`](l3-ghidra.md) runs single reader functions
under Ghidra P-code with mocked file APIs. With the ROM TOC known, it can grow
into a high-level emulation (HLE) harness:

- map **all** A and B module sections at their `o32_realaddr` (the ROM is
  pre-bound, so cross-module calls already point at the right VAs);
- replace `COREDLL` exports (1651 named, C-527) with host-side stubs:
  `CreateFileW`/`ReadFile`/`SetFilePointer`/`CloseHandle` over a directory
  tree or the SD image, `LocalAlloc`/`malloc`, `sprintf`, critical sections,
  registry reads from a fixture, logging;
- run with QEMU (`-M none`, gdbstub breakpoints on the stub addresses) for
  speed, or Ghidra for single-stepping and P-code inspection.

| | L3 / CE-HLE | Full system (F0–F4) |
| --- | --- | --- |
| Answers M2 (map-code / `HDD_INFO`) | yes, once the functions are known (M2.1–M2.4) | yes, in context, at F4 |
| Answers M3 (`.ind`, `DRSTR`, tiles) | yes, per function | yes, at F4 |
| Needs compressed `.data` decoded (M1.2/M1.3) | **yes** (initial values of globals) | no: the kernel decompresses |
| Needs the board model | no | yes |
| Handles runtime-built COM objects, threads | only by hand | natively |
| Time to first useful result | days (after M1.5/M2.1) | weeks (F4 is months) |
| Fidelity risk | wrong stub semantics | wrong board model |

The two meet in the middle: the F1 kernel can be used as a tool for L3, for
example to run the kernel's own ROM decompressor on every compressed section
(an alternative route to M1.2/M1.3) or to dump a fully loaded process image
for the HLE harness.

## 6. Recommended path

1. **L3 first** (critical path unchanged): M1.5 Ghidra maps → M2.1–M2.3 find
   the `HDD_INFO` code → run it under the harness with
   `tools/hddinfo_variants.py`. Build the harness so that the engine is
   swappable (Ghidra now, QEMU-gdbstub when speed matters).
2. **Full-system spike, time-boxed to one week** (TODO M8.A–M8.B): reach F0,
   then F1. Deliverables: a `ze0` QEMU machine (out-of-tree patch in
   `tools/qemu-ze0/`), the kernel log, and a peripheral-register table in
   `docs/format/firmware.md`. Stop if F1 is not reached within the box and
   record why.
3. **Use the spike as a tool**: kernel decompressor for M1.2/M1.3; dump the
   real registry hives (`boot.hv`, `default.hv`) from RAM; this also tells
   us IRQ numbers and driver base addresses for free.
4. **F2–F4 only on demand**: continue if L3 stalls on runtime state (the
   `NaviStateCC` COM object, AGENTS.md "HDD_INFO parser sits behind a runtime
   COM object") or if we want an automatic regression loop before bench
   access exists. Re-estimate after F2.
5. **Do not plan for F5.** Visual acceptance stays on the bench (L4).

## 7. Open questions

- Exact SoC part (SH77721/SH77722 or a custom derivative) and whether a
  hardware manual is obtainable. A manual would cut F1–F3 effort by half.
- Is the retail kernel's debug output on `0xffe46000` enabled?
- What is at `0xffe70000` and at area 4 (`0x10000000`)?
- Which of B and C does the IPL boot, and does it pass boot arguments in RAM
  (the kernel reads `0x08000020…0x0800002b`)?
- Does the app layer require a vehicle micon handshake (`serial_uat`, `CAN`)
  before it touches the SD card?
