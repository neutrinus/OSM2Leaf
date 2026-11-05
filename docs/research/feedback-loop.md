# Feedback loop: testing a map change without driving to the car

> **Status:** analysis and decision record, 2026-11-05. No emulator was built.
> Facts about external tools are `VERIFIED` from their source or documentation;
> effort estimates are `HYPOTHESIS`. See [`claims.md`](claims.md) C-509…C-514.

## The problem

We need a loop: change map data → run a check → pass/fail. Today the only
real oracle is the car. That is too slow for compiler work, and it makes every
experiment expensive.

Three different questions are usually mixed together:

1. **Is the card structurally valid?** Containers, sizes, indexes, zlib
   streams, directory tree, cross-references.
2. **Is the map semantically correct?** Roads, names, addresses, POIs,
   geometry, routing graph.
3. **Does the unit accept it and behave correctly?** SD lock, map code,
   firmware version, rendering, search, routing.

No single tool answers all three. The loop has to be layered, with the cheap
layers doing most of the work and the expensive layer used only for
acceptance.

## What exists today

- `tools/selftest.py`, `tools/cmpind.py`, `tools/drstr.py` — primitive and
  structural checks.
- Byte-identical round-trips: 194/194 `.cmp`/`.ind` pairs, five target tiles,
  `DRSTR001.DAT`.
- `tools/ze0-viewer/` — decode tiles to GeoJSON/PNG and compare with OSM.
- `tools/validate_mutation.py` — same-length POI rename, page confinement,
  unchanged `DRSTR`.
- L1 `tools/cardcheck.py` and L2 `tools/l2check.py` — whole-card structure and
  semantic/golden round-trips; both pass on the EU 2011 sample
  ([`EXP-2026-11-05-29`](../experiments/EXP-2026-11-05-29-l1-l2-validators.md)).
- `tools/verify.py` — one cross-year wrapper: auto-detects 2011/2014/2016,
  applies the artifact/partial flags, and reports QY8x 2019 as unsupported.
- Firmware RE — readers are not located yet; full-system QEMU was re-evaluated
  by EXP-2026-11-05-37 (stock QEMU's SH-4A CPU reaches the scheduler) and is
  tracked as L5/M8, not as a rejected option.
- `TODO.md` P4b already defines layers L0–L5 for the feedback loop.

The missing piece is not another decoder. It is an **acceptance oracle** that
does not require the car, plus a **runner** that makes the loop cheap enough to
use after every change.

## Test pyramid

| Layer | What it checks | Speed | Fidelity | Cost | Catches | Does not catch |
| --- | --- | --- | --- | --- | --- | --- |
| L0 primitives | zlib, `.ind`, `DRSTR`, headers | ms | low | low | codec and parser bugs | anything about the unit |
| L1 whole-card validator | MBR/FAT, files, sizes, indexes, cross-links | seconds | medium | low | broken or inconsistent card | wrong content |
| L2 semantic/golden | decode → model → render → compare with OSM/golden | seconds–minutes | medium–high | low | wrong roads/names/POIs/geometry | unit acceptance |
| L3 firmware function emulation | run located reader functions against generated data | minutes | high for the data contract | medium | misread format, wrong field semantics | untouched code paths |
| L4 bench hardware-in-the-loop | real unit boots the real card | minutes | highest available | medium | SD lock, map code, rendering, routing | electrical/analog edge cases, long-term wear |
| L5 full-system emulation | whole firmware on an emulated board | minutes | model-dependent | very high | execution paths, instrumentation | anything the model gets wrong |

The rule should be: **L0–L2 after every change, L4 before calling a milestone
done, L3 when the readers are available, L5 only as a timeboxed spike.**

## Option A — Wine

Wine is a **Win32 API compatibility layer**, not a CPU emulator. It runs
Windows PE binaries on a compatible host CPU and translates Win32 calls to
POSIX; it does not execute SH-4 instructions and does not implement Windows CE.

The Leaf navigation software is not a Win32 program:

- the firmware is a Windows CE 5.0 ROM image, with no PE files and with modules
  in ROM/XIP form;
- the code is Hitachi SH-4, not x86 or ARM;
- it uses WinCE `coredll`, WinCE drivers and a board support package, not the
  Win32 desktop API.

Even if Wine could load the module, the CPU and the operating system would
still be missing. Making this work would require an SH-4 CPU emulator, a WinCE
kernel and driver model, and a loader for ROM modules. That is a full-system
emulator, not a compatibility layer.

**Verdict: reject.** Wine is the wrong abstraction level. It is useful for
building Windows CE tools (some projects do that), not for running this
firmware.

## Option B — Full-system QEMU fork

> **Update 2026-11-05 (EXP-2026-11-05-37):** the kernel runs on stock QEMU's
> SH-4A CPU without a board model up to the scheduler; see
> [`full-system-emulation.md`](full-system-emulation.md) for the SoC map,
> staged plan and the current recommendation (L3 first, one-week F0–F1 spike).

Upstream QEMU does not have a machine close to this board. The facts checked
against QEMU master:

- system-mode SH-4 has exactly one machine, `r2d` (SH7751R + SM501);
- the SH-4 device model covers the interrupt controller, SCI and timer, but
  not DMA, USB, LCD, CMT, ADC, WDT, NAND, SD host or CAN;
- `hw/sh4/sh7750.c` calls `abort()` on an unknown register, so an unknown BSP
  dies early in `OEMInit`;
- linux-user SH-4 exists (`qemu-sh4`), but it runs Linux ELF binaries, not
  WinCE.

A `cetus-sh4` machine would need at least:

- the board memory map and boot ROM;
- a loader for the Clarion firmware container at `0x00200000`;
- SH-4 MMU, exceptions, timers and interrupt routing;
- serial, LCD/display, touch/keys, SD host, NAND, GPIO/power, CAN;
- enough of the WinCE 5.0 kernel and drivers to reach the navigation app;
- a way to inject and capture the SD card image.

CAN itself is not the blocker: it is a simple peripheral and can be simulated
on a bench with a cheap adapter. The hard parts are the SH-4 board, the WinCE
kernel/drivers, and the storage/display path.

That is a board bring-up project with its own reverse-engineering budget. The
current blocker in firmware RE is not instruction semantics — it is module
placement and reader identification. QEMU does not solve that; it only gives a
place to run code once we already know what to run.

**Verdict: not now.** The old "full-system QEMU is not realistic" claim is
**Superseded by EXP-2026-11-05-37** (stock QEMU's SH-4A CPU runs B's `nk.exe`
into the scheduler); it remains a legitimate long-term research spike (M8), not
a prerequisite for the map compiler, and not the cheapest path to a yes/no
answer. If attempted, timebox it and stop if the kernel does not reach a stable
idle loop; do not let it crowd out the data work.

## Option C — MAME custom machine

MAME has a much richer device framework and an SH-4/SH7750-family CPU core
(`src/devices/cpu/sh/sh4.cpp`, BSD-3-Clause). It models the SH7750, SH7750R,
SH7750S, SH7751 and SH7751R, with MMU, FPU, DMA and timer files.

But:

- the SH-4 source header still lists on-board peripherals as TODO;
- no CETUS_SH4 board or Clarion navigation machine was found;
- MAME emulates boards, not Windows CE; the firmware is a complete OS image,
  so the same board devices and boot path are still needed.

MAME may be a better starting point than QEMU for a future board model because
its device models are more reusable, but it does not remove the hard part.

**Verdict: plausible fallback, not obviously cheaper.** Do not start there.

## Option D — sh3-emu / CERF fork

[`Gadgetoid/sh3-emu`](https://github.com/Gadgetoid/sh3-emu) is the closest
architectural prior art found:

- MIT-licensed;
- SH-3 CPU, Windows CE 1.0/1.01 and 2.0;
- board models, LCD, touch/keys, PC Card storage, serial PPP, GDB stub,
  headless mode and saved states;
- it even emulates a **Clarion AutoPC 310C** car stereo, including the
  Clarion GPS frame format.

That is the same vendor family and the same "Windows CE on SuperH" problem.
But the Leaf is SH-4 and Windows CE 5.0. Extending sh3-emu would mean a new
SH-4 core (MMU, FPU, exceptions, peripherals), a CE 5.0 kernel/driver model,
and the CETUS board. It is a fork-sized project, not a configuration change.

CERF is a universal Windows CE emulator, but its CPU support is
ARM/StrongARM/XScale/MIPS; there is no SH-4 core. Its current license is also
custom and non-commercial, which does not fit this GPL-3.0 project.

**Verdict: use sh3-emu as a design reference** (board model, headless mode,
GDB, card images), not as the base for the Leaf.

## Option E — Function-level SH-4 emulation

This is the middle ground: do not boot the OS; run the specific reader
functions.

- Extract a function from the ROM at its file offset.
- Map its code and data at the virtual addresses it expects.
- Provide stubs for the WinCE calls it uses: file open/read/seek, memory
  allocation, logging, maybe registry access.
- Run it under Ghidra P-code emulation (already works) or a small SH-4
  harness.
- Feed it a generated `.cmp`, tile or `DRSTR`; compare its outputs and return
  values with the Python reader.

This directly tests the data contract without a board. It is also a way to
generate test vectors: run both the firmware function and the Python decoder on
the same input, and require the same result.

This is the useful version of "intercept I/O and mock it": you mock the WinCE
file API around one function, not the whole board. `qemu-sh4` linux-user can
run a hand-built static SH-4 ELF harness, but it expects Linux syscalls; Ghidra
P-code is simpler for individual functions.

Prerequisites: locate the readers. Static VA recovery is exhausted; relative
call-graph tracing from `0xc438a4`, `0xc0ebf8` and `0xc48380` is the current
path. The map-code comparator at `0x6fafe4` is a good first target because it
is already located; the `HDD_INFO` parser is the missing piece.

**Verdict: recommended after L1/L2, in parallel with the bench.** It is high
value for format correctness and does not need the full board.

## Option F — Bench hardware-in-the-loop (recommended)

Take the unit out of the car once and put it on a bench. This is the only
option that tests the real firmware, the real SD lock, the real map-code check
and the real rendering.

A minimal bench:

| Part | Purpose |
| --- | --- |
| 12 V lab PSU | power the unit safely |
| `TEST_B1` grounded | bypass `SECURE` (see `us-eu-region.md`) |
| CAN simulator | replay ignition/speed/vehicle frames; a SocketCAN adapter or a Pi |
| SD card extension | reach the card without dismantling the unit every time |
| SD mux/switch | connect the card to either the unit or the host writer |
| host card reader/writer | write only changed files or a delta image |
| relay/USB switch | power-cycle the unit under script control |
| touch/button actuator | run scripted searches and taps; a servo/stylus or analog touch injection |
| camera or video capture | detect error dialogs, map screen, renamed POI |
| GPS simulator (optional) | give the unit a fixed position for map/route tests |
| small host | run the test sequence and store logs/screens |

The runner is a simple state machine:

1. build the card or apply a file delta;
2. power on;
3. wait for a stable screen;
4. capture and classify (error dialog, map screen, black screen, reboot);
5. optionally run a scripted key sequence (search for the renamed POI, open
   the map at a known position);
6. power off;
7. record the result and keep the screenshot.

Why this is the best acceptance loop:

- it is the real oracle, not a model of it;
- it directly removes the car trip;
- it supports the closure experiments in
  [`EXP-2026-11-05-16`](../experiments/EXP-2026-11-05-16-mapcode-tile-contract.md)
  (one `HDD_INFO` line per card);
- it can run unattended overnight.

Risks: unit variant and region mismatch, SD lock, CAN/VIN requirements,
display capture, input injection, boot time, card-slot wear, and the need for a
spare unit. Mitigations: buy a spare US 2011 unit, keep the original card
read-only, write delta images instead of full 8 GB clones, and document the
recovery path.

**Verdict: primary acceptance loop.** Build it in parallel with L1/L2.

## Option G — SD card emulation or switching

A true SD card emulator must present a 4-bit SDIO slave interface. That is
FPGA-level work; SPI-mode emulators are easier, but the unit may not use SPI.
Commercial automotive SD emulators exist but are expensive.

Simpler alternatives, in order:

1. **SD extension + host writer.** Power off, switch the card from the unit to
   a host writer (a simple mux or a manual swap), update files in place, switch
   back, power on. No card emulator; the card stays in the unit.
2. **Two-card mux.** Switch between a golden card and the device-under-test
   card with a relay; still needs a writer for the test card.
3. **FPGA SD emulator.** Only if the test volume justifies the hardware work
   and the unit's SD host is understood.

**Verdict: start with (1).** Revisit (3) only if the bench becomes the
bottleneck.

## Option H — Record/replay and golden traces

Capture a known-good card's boot on the bench:

- SD command/data trace through an interposer or logic analyzer;
- screen frames;
- debug output, if a console can be reached.

Use it as a golden reference. For a generated card, compare the file-access
pattern and the screen states. This can catch "the unit reads a different file
set" without building a full model.

Limitations: interpreting SD traces is work, a trace diff is not a semantic
pass/fail, and it still needs the bench. It is a regression aid, not the
primary oracle.

## Option I — Offline contract tests (baseline)

This is the fastest loop and should be strengthened first:

- **Whole-card validator:** MBR/FAT, `DRSTR` tree, file sizes, `.ind` offsets,
  zlib decode, tile inventory, `MMAIN` table, `HDD_INFO` copy consistency.
- **Semantic tests:** decode → intermediate model → render → compare with
  OSM/golden output.
- **Round-trip:** unchanged content byte-identical; changed content
  semantically equal, with stable chunking and valid sizes.
- **Mutation/fuzz:** corrupt one field; the validator must reject it with a
  useful message, not a traceback.
- **Golden corpus:** hashes and expected outputs for known-good cards and
  known mutations; no vendor data in git.

This does not prove acceptance, but it makes the bench loop rare and focused.

## Comparison

| Option | Fidelity | Effort | Cost | Main strength | Main weakness | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Wine | none for this target | low | low | familiar tooling | wrong CPU and OS | reject |
| QEMU board fork | high if complete | months–years | medium | execution-level control | missing board, OS, devices | timeboxed spike only |
| MAME board | high if complete | months–years | medium | reusable devices | no board, incomplete SH-4 peripherals | fallback |
| sh3-emu fork | high for CE 2.x | months | low | WinCE/SH design, Clarion prior art | SH-3, CE 2.x, not SH-4/CE5 | reference only |
| Function-level emulation | high for located code | weeks–months | low | tests the real reader contract | needs readers, stubs | recommended (L3) |
| Bench HIL | highest available | weeks | medium | real acceptance oracle | needs spare unit and wiring | recommended (L4) |
| SD emulator | high | weeks–months | medium–high | fast card switching | 4-bit SDIO is FPGA work | later |
| Record/replay | medium | weeks | medium | catches access-pattern drift | not semantic | optional |
| Offline contracts | medium | days–weeks | low | fast, deterministic, CI-friendly | cannot prove acceptance | do first |

## Recommendation

1. **Do not build Wine or a QEMU board fork now.** They are the most expensive
   way to answer a question we can answer more cheaply.
2. **Build the offline contract layer (L1/L2) first.** It is the loop that runs
   on every change and catches most mistakes.
3. **Build the bench HIL (L4) in parallel.** A spare unit on a desk is the
   acceptance oracle and directly solves the "repeated car trips" problem.
4. **Add function-level emulation (L3) when the readers are located.** It
   cross-checks the format contract and produces test vectors.
5. **Keep full-system emulation (L5) as a timeboxed research spike.** Revisit
   it only if the bench cannot answer a specific question, or if the test
   volume makes an emulator cheaper than hardware.

Decision triggers:

- no affordable spare unit → revisit L5;
- unknown rejection on the bench → L3, debug output or JTAG, not a full board
  fork;
- bench reliable but slow → improve card switching (delta writes, mux, FPGA);
- readers located → L3 becomes cheap and high-value.

## First concrete steps

- [ ] Define the first HIL pass criteria: boot to map screen with no error,
      then the no-op control, then the POI rename.
- [ ] Decide whether the first pass needs input injection (boot/map only) or
      already a scripted search (touch/keys).
- [ ] Acquire a spare US 2011 unit; record part number, PROD block, `NAVI-1`.
- [ ] Build the bench: PSU, `TEST_B1`, CAN, SD extension, relay, camera.
- [x] Write `tools/cardcheck.py` (L1) with a stable exit code and a
      machine-readable report.
- [x] Write `tools/l2check.py` (L2) with round-trip, golden and mutation checks.
- [ ] Write a minimal `tools/hil/run.py`: build → write → power-cycle →
      capture → classify → log.
- [ ] Capture one CAN log and one known-good screen sequence from the car.
- [ ] Try to reach the debug output (`OSM_Printf`, `OSM_LogMsg`,
      `StatusData`); exact field errors would replace screen OCR.
- [ ] Keep the original card read-only and test on a spare.

## Open questions

1. Which spare unit is the right one: US 2011 `CLA-NAVI05-01`, or a later
   ZE0-compatible unit? Does the part number matter for the map-code check?
2. Does the unit boot on the bench without CAN, or does it need a minimum
   frame set? Which IDs?
3. Can the SD lock be automated, or does every card need a manual CMD42 step?
4. Is there a service/diagnostic mode that validates the card and reports a
   result without the map UI?
5. Can the display be captured electrically (LVDS/composite) instead of with a
   camera?
6. Is `TEST_B1` enough to bypass `SECURE`, or is a VIN/CAN simulation needed?
7. Is the SD host SPI or 4-bit SDIO? This decides whether a cheap card
   emulator is possible.
8. Can the firmware's debug output be reached through a serial port, USB or a
   hidden service menu?
9. What is the minimum card size and free space the unit accepts?
10. How does the US unit react to an EU image at the card level, and does that
    change the bench test matrix?
11. How do we inject touch and key events reliably: a servo/stylus, an analog
    touch interface, or a service command?
12. Does the map screen need a GPS fix, or does it render from the card alone?
    Can a GPS simulator feed the antenna input?

## Sources checked

- QEMU SH-4 system machine list: `hw/sh4/Kconfig`, `hw/sh4/meson.build`;
  linux-user SH-4: `linux-user/sh4/target_syscall.h`.
- MAME SH-4 CPU: `src/devices/cpu/sh/sh4.cpp`, `sh4.h`, `sh4dmac.cpp`,
  `sh4fpu.cpp`, `sh4tmu.cpp`.
- sh3-emu: repository README, `docs/hardware.md`,
  `docs/machines/autopc.md`, `LICENSE` (MIT).
- CERF: repository tree (`src/cpu`, `src/boards`) and README; no SH core.
- SD card emulation: Hackaday/EEVblog/ZipCPU discussions; 4-bit SDIO slave is
  FPGA-level.
- Wine: Wine is a Win32 compatibility layer, not a CPU emulator; no SH-4 or
  Windows CE support.

## Legal and safety

Emulating firmware for interoperability is a different activity from
distributing it. Keep the rules from [`../legal.md`](../legal.md): do not
publish vendor images, patched firmware or unlock PINs; keep the original card
read-only; test on a spare card and, for destructive experiments, a spare
unit. A bench unit is also the safest place to make mistakes.
