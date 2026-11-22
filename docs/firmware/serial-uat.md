# `serial_uat.dll`: the two external UARTs (EU 2011, build B)

Static read of the stream driver that publishes `UAT3:` and `UAT4:`. `UAT3:`
is the link to the vehicle-CAN sub-microcontroller (`CAN.dll`, C-6413,
[`vehicle.md`](vehicle.md)); `UAT4:` has no known active user. Nothing here was
run on hardware or in QEMU. All VAs are build B (`--image-start 0x3e00200`)
unless marked otherwise; SH-4 code is little-endian. Status tags: **VERIFIED**
(a command reproduces it), **OBSERVED** (assembly/registry read, not executed),
**HYPOTHESIS** (a reading not proven), **UNKNOWN**.

## 1. Module and sections

| Module | VA range | Code section | File offset | Status |
| --- | --- | --- | --- | --- |
| `serial_uat.dll` | `0x039a0000`–`0x039acfff` (load `0x88665000`) | sec0 `rva 0x1000`, `realaddr 0x039a1000`, `vsize 0x80a2`, flags `0x60000020` | `0x0427f200` | VERIFIED |

Exports: `UAT_Init 0x039a3f38`, `UAT_Open 0x039a4260`,
`UAT_Close 0x039a28f4`, `UAT_Read 0x039a2c10`, `UAT_Write 0x039a45e8`,
`UAT_Seek 0x039a306c`, `UAT_IOControl 0x039a32e4`,
`UAT_PowerUp 0x039a3078`, `UAT_PowerDown 0x039a30dc`,
`UAT_Deinit 0x039a2a94`. All register work is in sec0; sec1
(`0x039aa000`) holds the IAT and compressed sec2 (`0x039ab000`, kernel decode
1576 B) is only `.pdata`, not configuration data.

## 2. Base addresses

The registry (decoded build-B `default.hv`) gives `Drivers\Launch\UART3`
`DeviceArrayIndex=2`, `Prefix=UAT`, `Index=3`, `Dll=serial_uat.Dll`,
`WaterMarker=0x40`, and `UART4` the same with index 3 / `Index=4` /
`WaterMarker=0x08`. `fn 0x039a4d98` and `fn 0x039a72b4` switch on
`DeviceArrayIndex` at `ctx+0x1e0`, then call `VirtualCopy` (stub
`0x039a8ca8`) with `0x204` and a P4 address:

| Index | Port | P4 VA in code | Physical base | Status |
| --- | --- | --- | --- | --- |
| 2 | `UAT3:` | `0xb9b00000` | `0x19b00000` | VERIFIED |
| 3 | `UAT4:` | `0xb9e00000` | `0x19e00000` | VERIFIED |
| 1 | not registered | `0xb9c00000` | `0x19c00000` | OBSERVED |
| 0 | not registered | `0xb9d00000` | `0x19d00000` | OBSERVED |

The earlier hardware-map wording "chips in the `0x19b00000`–`0x19e00000`
area" is refined by C-6992: only `0x19b00000` and `0x19e00000` are used by the
two registry entries. `tools/va_class.py` finds these addresses outside every
module section (real hardware addresses, not compressed `.data`).

## 3. Register block

The code at `0x039a48dc` (a short naked fragment between `.pdata` records,
called from `fn 0x039a4e70` and `fn 0x039a7364`) stores `base + offset` port
addresses in a 60-byte register object. Twenty-two accessors at
`0x039a4938`–`0x039a4a40` load those stored addresses and tail-call
`CEDDK!WRITE_PORT_USHORT` (stub `0x039a70b4`) or `CEDDK!READ_PORT_USHORT`
(stub `0x039a70c0`). **Every register access is 16-bit at a 2-byte stride.**

For UAT3 (`base 0x19b00000`; UAT4 = same offsets on `0x19e00000`):

| Offset | Port VA | Accessor W / R | Classic name | Evidence / status |
| --- | --- | --- | --- | --- |
| `+0x00` | `0x19b00000` | `0x039a4938` / `0x039a4944` | RBR / THR / DLL (DLAB=1) | divisor LSB write in `fn 0x039a4b84` — VERIFIED |
| `+0x02` | `0x19b00002` | `0x039a4950` / `0x039a495c` | IER / DLM (DLAB=1) | divisor MSB write in `fn 0x039a4b84` — VERIFIED |
| `+0x04` | `0x19b00004` | `0x039a4968` / `0x039a4998` | IIR / FCR | read selects baud table; FCR shadow cached at ctx+16 and read masked `& 0xfff9` at `0x039a498c` — OBSERVED |
| `+0x06` | `0x19b00006` | `0x039a49a4` / `0x039a49b0` | LCR | DLAB bit 7 in `fn 0x039a4b84` — VERIFIED |
| `+0x08` | `0x19b00008` | `0x039a49bc` / `0x039a49c8` | MCR | accessor + flush code `0x039a4b24` — OBSERVED |
| `+0x0a` | `0x19b0000a` | `0x039a49d4` / `0x039a49e0` | LSR | accessor + flush code — OBSERVED |
| `+0x0c` | `0x19b0000c` | `0x039a49ec` / `0x039a49f8` | MSR | accessor + flush code — OBSERVED |
| `+0x0e` | `0x19b0000e` | `0x039a4a04` / `0x039a4a10` | scratch | accessor — OBSERVED |
| `+0x1a` | `0x19b0001a` | `0x039a4a1c` / `0x039a4a28` | vendor-specific | in vtable at `0x039a1528`, no in-module caller found — UNKNOWN |
| `+0x1c` | `0x19b0001c` | `0x039a4a34` / `0x039a4a40` | vendor-specific | in vtable, no in-module caller found — UNKNOWN |

The register object also holds the physical base at `+4`, a flag word at `+8`
(the `r6` argument of the fragment), the FCR shadow at `+16` and the vtable
pointer at `+0`.

## 4. Baud and framing

`fn 0x039a4b84` is textbook 16550 DLAB sequencing: read `+0x04`, read LCR
`+0x06`, write `LCR | 0x80` to `+0x06`, write divisor LSB to `+0x00`, divisor
MSB (`divisor >> 8`) to `+0x02`, restore LCR, store the divisor at
`ctx+0x42`. It selects one of three u32 (baud, divisor) tables from bits
`0xe0` of `+0x04`:

| Table VA | Entries (baud / divisor) | Implied clock | Status |
| --- | --- | --- | --- |
| `0x039a1590` | 4800/313, 7200/208, **9554/157**, 9600/157, 19200/78, 38400/39, 57600/26, 115200/13 | ≈1.5 MHz × 16 = 24 MHz | VERIFIED (table), HYPOTHESIS (clock) |
| `0x039a15d0` | 4800/624, 7200/416, 9600/312, 19200/155, 38400/77, 57600/51, 115200/25, **230400/12** | ≈3 MHz × 16 = 48 MHz | VERIFIED (table), HYPOTHESIS (clock) |
| `0x039a1970` | 4800/24, 7200/16, 9600/12, 12800/9, 14400/8, 19200/6, 23040/5 | 115200 | VERIFIED (table) |

`CAN.dll` passes 230400 to its `UAT3:` open (`0x00038400` at `0x03b511f0`,
C-7463), consistent with table `0x039a15d0`. Which table the driver selects
at boot depends on bits `0xe0` of the chip register `+0x04`; no static
decision was pinned. FCR bits and the physical FIFO depth are UNKNOWN; the
registry watermark is 64 for UAT3 and 8 for UAT4. Word length, parity and
stop bits are read from the DCB in the serial IOCTL dispatch
(`UAT_IOControl 0x039a32e4` handles `IOCTL_SERIAL_*`), not pinned to an
immediate here.

## 5. Interrupt

`fn 0x039a3eb8` calls `InterruptInitialize(SYSINTR = *(ctx+0x2c), event =
*(ctx+0x30))` and starts thread `0x039a3e14`, which calls
`InterruptDone(*(ctx+0x2c))`; `fn 0x039a4c1c` does the same after
`DDKReg_GetIsrInfo` (stub `0x039a8c78`) and `RegQueryValueExW("WaterMarker")`.
Neither the UART3/UART4 registry keys nor the module contain a `SysIntr` or
`Irq` value, so **SYSINTR and INTEVT are UNKNOWN statically** (C-6998). The
kernel's 47-row `{INTEVT, ISR, IntrPrio, SYSINTR}` table at `0x88005bc8`
cannot be attributed to these lines without a runtime correlation. M8.H3
must not guess an interrupt binding.

## 6. Verdict for QEMU (M8.H3)

The core is functionally 16550-like (classic register positions, DLAB
divisor pair, FCR self-clearing bits), but QEMU's `serial-mm` is **not a
drop-in model**:

1. registers are 16-bit ports at a 2-byte stride, not an 8-bit register file;
2. two extra registers exist at `+0x1a` / `+0x1c`;
3. FCR reads are masked (`& 0xfff9`) and cached;
4. the divisor tables imply a 24/48 MHz reference clock and 230400 baud;
5. the watermark suggests a ≥64-byte RX FIFO for UAT3;
6. SYSINTR/INTEVT are unknown, so no INTC binding can be written yet.

The recommended model is a small dedicated `uat-mm` device (or `serial-mm`
behind a u16 / 2-byte-stride shim), with the interrupt left to a measured
follow-up. This is a HYPOTHESIS about integration (C-6999): no QEMU code or
run exists in this task.

## 7. What could not be determined

- SYSINTR/INTEVT (no registry value; needs a runtime correlation).
- Meaning of `+0x1a` / `+0x1c` (vtable only, no caller).
- Exact FCR trigger bits and FIFO depth; which baud table boots.
- Word length/parity/stop bits at runtime.
- Whether `0x19c00000` / `0x19d00000` back real chips (indices 1/0 unused).

## 8. Reproduction

```bash
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img modules | grep -i serial_uat
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img sections serial_uat.dll
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img exports serial_uat.dll
python3 tools/sh4dis.py archive/head256.img serial_uat.dll --image-start 0x3e00200 --va 0x39a4de2 --count 30
python3 tools/sh4dis.py archive/head256.img serial_uat.dll --image-start 0x3e00200 --va 0x39a48dc --count 72
python3 tools/sh4dis.py archive/head256.img serial_uat.dll --image-start 0x3e00200 --va 0x39a4bc0 --count 63
python3 tools/ze0_regs.py who archive/head256.img 0xb9b00000 0xb9c00000 0xb9d00000 0xb9e00000
```

Claims: C-6990–C-6999. Experiment:
`docs/experiments/EXP-2026-11-22-M8.H2-serial-uat.md`.
