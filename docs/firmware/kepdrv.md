# Dead-reckoning inputs: `kepdrv.dll` and `navdrv.dll` (EU 2011, build B)

Static map of how the head unit gets wheel pulses, gyro rate and illumination
between GPS fixes. Read-only knowledge (M8.H28): nothing here was executed on
hardware, and no chip was opened. **Every row says "the firmware says so" — the
physical device behind a register is unseen.** All VAs are kernel build B
(`--image-start 0x3e00200` of `archive/head256.img`); addresses come from
`tools/cerom.py` and `tools/sh4xref.py` (pdata function starts), never from
fitted deltas. SH-4 code is little-endian.

Status tags: **VERIFIED** (a command in
[`EXP-2026-11-22-M8.H28-kepdrv`](../experiments/EXP-2026-11-22-M8.H28-kepdrv.md)
reproduces the number), **OBSERVED** (decoded from assembly, not executed),
**UNKNOWN** (no reliable answer in the scanned sections).

## 1. Modules

| Module | ROM | Code (`vsize`) | Role | Evidence |
| --- | --- | --- | --- | --- |
| `kepdrv.dll` | B (`0x3e00200`) | `0xab12` (43,794 B) | maps the gyro/pulse registers and the on-chip TMU; starts the `TmuStconThread` | `cerom.py sections`, `KEPI:…` strings (C-7250) |
| `navdrv.dll` | B (`0x3e00200`) | `0x6b02` (27,394 B) | Gyro/ADC library (`gyroAdc_*`) and the sensor sample builder consumed by positioning | `cerom.py sections`, `gyroAdc_*` strings (C-7254) |

Both export only the CE stream-driver entry points (`KEP_*`, `NAV_*`); the
sensor API is internal to `navdrv.dll` (C-7254).

## 2. Register map

### 2.1 Physical pages mapped by software

Both modules map the **same two 4 KiB physical pages**, in the same order, in a
function whose start pdata gives as `0x03a1b244` (`kepdrv.dll`) and `0x039e6f74`
(`navdrv.dll`):

| Physical page | Role (from the library that reads it) | Literal pool VA · `kepdrv` | Literal pool VA · `navdrv` | Load site · `kepdrv` | Load site · `navdrv` | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `0xffc5a000` | gyro ADC data (read by `gyroAdc_GetAddData`) | `0x03a1b4dc` | `0x039e720c` | `0x03a1b29c` | `0x039e6fcc` | VERIFIED (C-7250) |
| `0xffc5b000` | speed-pulse capture (read by `gyroAdc_SP_GetINTcount`, `…Get100LatchData`, `…GetOffsetB`, `…GetObserveB`, `…Get500Kfreq`) | `0x03a1b4fc` | `0x039e722c` | `0x03a1b3ca` | `0x039e70fa` | VERIFIED (C-7251) |

The mapping is `VirtualAlloc(0, 0x1000, MEM_RESERVE=0x2000, PAGE_READWRITE=4)`
followed by `VirtualCopy(vaddr, physical, 0x1000, 0x204)`; `0x204` is
`PAGE_PHYSICAL|PAGE_READWRITE` (a `mov.w` halfword at `0x03a1b3de` / `0x039e710e`,
loaded at `0x03a1b298` / `0x039e6fc8`). The thunk at `0x03a1b664` is
`COREDLL!VirtualCopy` (IAT slot `0x01f420ac` ↔ import ordinal 560), and
`0x03a1b670` is `VirtualAlloc` (ordinal 524); `cerom.py --image-start
0x3e00200 … imports kepdrv.dll` lists these ordinals, and `exports coredll.dll`
resolves 560/524. **The `0x1000` length comes from `mov #16,r8; shll8 r8`, not
from a guessed page size** (C-7252).

Each page is described by a 120-byte struct allocated with `malloc(120)`
(`kepdrv.dll` global `0x01f422a8` for the gyro page, `0x01f422ac` for the pulse
page; `navdrv.dll` globals `0x01f3c114` / `0x01f3c118`). Its words `+4`, `+8`,
…, `+116` are pointers to mapped `base+4`, `base+8`, …, `base+112`, i.e. the
driver treats the first `0x74` bytes of each page as 4-byte register slots
(OBSERVED, C-7252). The getters below pick slots from this table.

**Earlier misreading corrected:** the halfwords `0x0204` and `0x1388` in the
mapping function are **not** timer reload values. `0x0204` is the `VirtualCopy`
flag just described; `0x1388` (5000) at `0x03a1b474` is the
`WaitForSingleObject(handle, 5000)` timeout in the key-timer thread
(`COREDLL` ordinal 497). No timer period was read out of these two literals
(C-7257).

### 2.2 On-chip timer (TMU)

`kepdrv.dll` also maps physical `0xffd81000` (literal `0x03a1aea4`, load at
`0x03a1ad4e`) with `MmMapIoSpace` (CEDDK ordinal 8; thunk `0x03a1b238`, IAT
slot `0x01f42004`) for `0x1000` bytes, in function `0x03a1ad04` (C-7253).
`TMURegisterInit` at `0x03a19a9c` then writes through four pointers held in
struct slots `+0x270`, `+0x274`, `+0x278`, `+0x27c` — which the init function
set to mapped `base+4`, `+8`, `+12`, `+16`:

| Register slot | Physical offset | Value written | Code VA of the write setup | Status |
| --- | --- | --- | --- | --- |
| `+0x270` | `base+0x04` | `byte = (byte & 0xfe) | 1` | `0x03a19ae8`–`0x03a19b08` | OBSERVED (C-7253) |
| `+0x274` | `base+0x08` | `u32 0x668a` | literal load `0x03a19af4`, store `0x03a19af8` | OBSERVED (C-7253) |
| `+0x278` | `base+0x0c` | `u32 0x668a` | store `0x03a19afc` | OBSERVED (C-7253) |
| `+0x27c` | `base+0x10` | `u16 0x0021` | `mov #33,r1` at `0x03a19aee`, `mov.w` store `0x03a19af2` | OBSERVED (C-7253) |

This is timer-capture code: a TMU block is mapped, initialised and served by
`TmuStconThread` (`InterruptInitialize` failure strings at `0x03a14408` and
`0x03a14440`). **Falsifier refuted:** the pulses need not arrive over CAN;
there is no `CAN.dll` import in `kepdrv.dll` (C-7259). M8.H49 remains the place
to document the separate vehicle-CAN speed frame.

## 3. Gyro / pulse API and sample rate

The strings are UTF-16LE, in `navdrv.dll` sec0. Each API name below is the
identifier in that function's own error string, and the VA is the function that
loads the string (pdata), so the names are read from the image, not guessed
(C-7254):

| Function (from its error string) | VA | What the name says |
| --- | --- | --- |
| `gyroAdc_Init` | `0x039e6f74` | maps GYRO and SPDPLS (speed pulse) pages, creates mutex |
| `gyroAdc_DeInit` | `0x039e7258` | frees both mappings and the mutex |
| `gyroAdc_GetAddData` | `0x039e734c` | 8-channel raw gyro/ADC read, `cmp/hi #7` bound |
| `gyroAdc_SP_SetCntClear` | `0x039e73e4` | clear the pulse counter |
| `gyroAdc_SP_Get100LatchData` | `0x039e744c` | read the "100" latch (the name implies a 100 ms sampling period, not proven) |
| `gyroAdc_SP_GetINTcount` | `0x039e7484` | read pulse interrupt count |
| `gyroAdc_SP_SetStsClear` | `0x039e74bc` | clear status |
| `gyroAdc_SP_GetOffsetB` | `0x039e7500` | gyro offset (bias) |
| `gyroAdc_SP_GetObserveB` | `0x039e7538` | gyro observed value |
| `gyroAdc_SP_SetWidthClear` | `0x039e7570` | clear pulse-width accumulation |
| `gyroAdc_SP_GetFilter` | `0x039e75d8` | filter setting |
| `gyroAdc_SP_Get500Kfreq` / `Set500Kfreq` | `0x039e7610` / `0x039e76c8` | 500 kHz reference-clock calibration |

The "100" latch and the "500K" clock pair are the library's own sample-rate
labels; the `Navi.exe` sample period was not executed (OBSERVED).

`GetAddData` uses an 8-entry `braf` jump table at `0x039e2d38`, bytes
`00 0e 16 1e 26 2e 36 3e`; channel 0…7 selects one of eight register pointers
at struct offsets `+52`, `+56`, `+60`, `+64`, `+68`, `+72`, `+76`, `+80`
(targets `0x039e7372`…`0x039e73b0`; C-7255). Values are masked with
`0x0fffffff` (28 bits) at `0x039e737a`.

## 4. Sample structure

`navdrv.dll` function `0x039e59e4` assembles the sample. Each getter is called
and its `-1` error sentinel checked before the value is stored; the field
offsets and sources below are decoded by `tools/kepdrv_scan.py` (C-7256):

| Offset | Width | Source (VA) | Meaning |
| --- | --- | --- | --- |
| `+0x00`, `+0x04`, `+0x08`, `+0x10` | u32 | `gyroAdc_GetAddData` `0x039e734c`, channels 0,1,2,3 | raw gyro/ADC channels |
| `+0x14` | u32 | `gyroAdc_SP_GetOffsetB` `0x039e7500` | gyro bias |
| `+0x18` | u32 | `gyroAdc_SP_GetObserveB` `0x039e7538` | gyro observation |
| `+0x1c` | u16 | `gyroAdc_SP_GetINTcount` `0x039e7484` | pulse count since last sample |
| `+0x22` | u16 | inline: `((new - old) & 15)` of global `0x01f3c0ec` (`0x039e5a66`–`0x039e5a78`) | 4-bit delta of a separate counter |

The caller of this builder and the IPC message that carries the struct to
`Navi.exe` are not yet located (UNKNOWN).

## 5. Units

| Quantity | Unit source | VA / status |
| --- | --- | --- |
| Pulses → distance | raw pulse count is `gyroAdc_SP_GetINTcount` (`0x039e7484`), stored at sample `+0x1c`. No pulses-per-metre constant appears as an immediate in the scanned uncompressed sections; the scale is a run-time calibration value (task stop rule: name, do not derive). | **UNKNOWN** — name only, C-7258 |
| Gyro rate | 28-bit raw ADC from `gyroAdc_GetAddData` (`0x039e734c`) with bias/observation from `0x039e7500` / `0x039e7538`; the deg/s-per-count scale is not a code literal here, so it is a run-time calibration. The 500 kHz reference is exposed by `0x039e7610` / `0x039e76c8`. | **UNKNOWN** name + OBSERVED clock, C-7258 |
| Illumination | imported `COMMONDLL!CApi_GetCurrentIlluminationMode` (IAT slot `0x01f3c0cc`, literal `0x039e68fc`), called in `navdrv.dll` fn `0x039e683c` and stored at struct `+0x72`/`+0x76` | VERIFIED (call path), C-7259 |
| Reverse signal | no reverse-signal input string or GPIO mask recovered in `kepdrv.dll`/`navdrv.dll`; likely reaches positioning through the CAN path documented in `vehicle.md` / M8.H49 | **UNKNOWN**, C-7259 |

The last two rows are the hardware-map boundary: **the firmware calling an
illumination API is verified; the physical pin and the reverse wire were never
seen.** `docs/hardware/head-unit.md` carries the same distinction.

## 6. What would be needed next

- Run `gyroAdc_GetAddData` / `GetINTcount` in an L3 fragment harness with a
  synthetic register image, then feed the sample struct to the positioning
  code — this is the acceptance path of rule 13, not yet attempted.
- Find the `Navi.exe` consumer of the `0x039e59e4` struct and the runtime
  calibration that supplies pulses/metre and gyro scale (L4 QEMU with a
  traced memory write, when hardware is still unavailable).

## 7. Builds

Only kernel build B (EU 2011 / US 2011, byte-identical — C-6281) was scanned.
The corresponding page appears twice in the image (a second copy at
`0x4b…`, build C), but no address here was fitted from a delta; every VA is
from `cerom.py` at `--image-start 0x3e00200`. Build A (`0x200200`) does not
contain `kepdrv.dll` — the negative control in the EXP.
