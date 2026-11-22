# `navdrv.dll` — the GPS receiver on `SCI7:` (M8.H27)

Build: **EU2011** (ROM B, `--image-start 0x3e00200`). The `navdrv.dll`
sections are byte-identical in **US2011**, so every VA below is valid for both
builds (C-7252). SH-4 code is little-endian; `fn 0x…` labels are
`nk_decomp.py pdata` STARTs (checked), helpers without a pdata record are
written as `leaf at 0x…`.

## Modules

| Item | Value | Status |
| --- | --- | --- |
| Module | `navdrv.dll`, module 58 of ROM B, `attr=0007`, load `0x88635000`, virtual base `0x039e0000` | VERIFIED, `tools/cerom.py modules` |
| Code | sec0 at `0x039e1000`, `0x6b02` bytes (`0x6c00` stored); 27 394 executable bytes | VERIFIED, `tools/cerom.py sections` |
| Imports/exports | export `0x7a00+102`, import `0x7834+64`; stream-driver exports `NAV_Init`, `NAV_IOControl`, `NAV_Deinit`; `NAV_Open/Read/Write` are `rts; mov r4,r0` stubs | VERIFIED |
| PDB path | `C:\WINCE500\platform\CETUS\target\SH4\retail\navdrv.pdb` at `0x039e325c` | OBSERVED (string) |

## Interfaces

`navdrv.dll` opens `SCI7:` with Win32 `CreateFileW` (not a direct SCIF MMIO
access and not `serial_scif.dll` links). Imports resolved through
`cerom.py imports/thunks`:

| API | Import slot | Thunk | Used by |
| --- | --- | --- | --- |
| `CreateFileW` | `0x39e8014` | `0x39e6d94` | `fn 0x39e3ec0` (`CommInit`) |
| `SetCommState`, `SetCommTimeouts`, `PurgeComm` | `0x39e8040/44/3c` | `0x39e6e18/24/0c` | `fn 0x39e3ec0` |
| `WriteFile` | `0x39e8068` | `0x39e6e90` | `fn 0x39e44e8` (`SetGpsData`) |
| `ReadFile` | `0x39e8074` | `0x39e6eb4` | `fn 0x39e4a54` (RX assembler) |
| `WaitCommEvent`, `ClearCommError`, `SetCommMask` | `0x39e807c/78/80` | `0x39e6ecc/ec0/ed8` | `fn 0x39e4c50` (`GpsThread`) |
| `SetSystemTime` | `0x39e8070` | `0x39e6ea8` | `fn 0x39e4988` (date frame) |
| `DeviceIoControl` | `0x39e80b4` | `0x39e6e6c` | `fn 0x39e4324`, `fn 0x39e44e8`, IOCTL dispatch `fn 0x39e3598` |

Named functions (all pdata STARTs): `fn 0x39e3ec0` `CommInit`,
`fn 0x39e44e8` `SetGpsData`, `fn 0x39e4a54` RX assembler,
`fn 0x39e4c50` `GpsThread`, `fn 0x39e4700` frame walker,
`fn 0x39e4630` terminator search, `fn 0x39e4988` date decoder,
`fn 0x39e4324` `SetGpsDataBuff`, `fn 0x39e4f60` IOCTL read-back,
`fn 0x39e3598` IOCTL dispatch, `fn 0x39e6b70` `IprInit`,
`fn 0x39e6f74` `gyroAdc_Init`.

IOCTLs dispatched by `fn 0x39e3598`: `0x80102010` writes one raw GPS frame
(caller buffer ≤ 50 bytes, forwarded to `fn 0x39e44e8`); `0x8010200c` raw
data copy; `0x80102018/1c` `SetFilterConfig`/`GetFilterConfig`;
`0x80102020` event get; `0x80102028` another raw path. Frames received from
the receiver are published with `DeviceIoControl(0x800f2000, …)` and event
index 1 (`SckGpsCheck changed OK NotifyEvent`, string at `0x039e2190`).

### Line settings

`CommInit` (`fn 0x39e3ec0`) writes a DCB at `0x039e3f90…0x039e3fc8`:

| Field | Value | VA of the store | Status |
| --- | --- | --- | --- |
| `BaudRate` | `0x12c0` = **4800** (`mov.w @(0x39e4040,pc)`) | `0x039e3f94` → `0x039e3f98` | VERIFIED (static) |
| `fFlags` | `(old & 0x8003) \| 3`: binary, parity, abort-on-error | `0x039e3f9c…a2` | VERIFIED |
| `ByteSize` / `Parity` / `StopBits` | 8 / 1 / 0 (one stop bit) | GBR stores `0x039e3fac/3fb0/3fb4` | VERIFIED |
| Xon / Xoff / ErrorChar / Eof / Evt | `0x11` / `0x13` / 0 / `0x10` / `0x12` | `0x039e3fb6…3fc8` | VERIFIED |
| `ReadTotalTimeoutConstant` | 200 ms (`0xc8`) | `0x039e3f5a` | VERIFIED |
| `WriteTotalTimeoutConstant` | 1000 ms (`0x03e8`) | `0x039e3f62` | VERIFIED |

`0x4b00` (19200) does not occur in `navdrv.dll`. C-6425 and
`docs/hardware/head-unit.md:74,173` record `SCI7:` as 19200 from a table in
another module; the actual `SetCommState` write here is 4800. The two facts
are not reconciled yet — HYPOTHESIS: the receiver is reconfigured later by a
different component, or the hardware table documents a different mode.

## Data: the binary frame grammar

There is no NMEA `$GP`/GGA/RMC string anywhere in ROM B (C-8242). The format
is a 7-bit binary protocol with a 7-bit sum and `0xf0` terminator — the same
family as the TestMode `A0 00 … sum F0` frame of C-8244, but the chip/vendor
name is **UNKNOWN** (not UBX `b5 62`, not SiRF `a0 a2`).

| Field | Offset / token | Unit | Parser | Status |
| --- | --- | --- | --- | --- |
| Start byte | `frame[0]`, bit 7 set; RX scanner accepts `0xa0`, `0xa5…0xae`, `0xb4…0xbe`, `0xc1…0xff` | byte | `leaf at 0x39e41ec` (cmp constants at `0x39e41fe…0x39e4230`); TX check in `fn 0x39e44e8` at `0x039e4506` | VERIFIED |
| Length | from the start byte via table `0x39e17e4` (RX) / `0x39e1808` (TX) and a `braf` dispatch; e.g. `0xb0` → 6 | bytes | `leaf at 0x39e42a4` (RX), `leaf at 0x39e42e8` (TX) | VERIFIED |
| Command / payload | `frame[1..len-3]`; every byte must be 7-bit clean | bytes | `fn 0x39e44e8` (TX), `fn 0x39e4700` (RX) | VERIFIED (framing), command meaning HYPOTHESIS |
| Checksum | `frame[len-2] = (Σ frame[1..len-3]) & 0x7f` | 7-bit sum | `leaf at 0x39e4248`, compare at `0x039e429a` | VERIFIED |
| End marker | `frame[len-1] & 0xf0 == 0xf0` | byte | `fn 0x39e44e8` at `0x039e454a`, `fn 0x39e4630` | VERIFIED |
| Date/time | frame bytes `+16…+21` → `SYSTEMTIME`; 2-digit year `+1900` (`0x076c`) or `+2000` (`0x07d0`) | year/month/day/… | `fn 0x39e4988` → `SetSystemTime` at `0x039e4a14` | VERIFIED (call), field order HYPOTHESIS |
| Lat / lon / altitude / speed / heading / satellites / fix quality | **not decoded here**; whole frames go into a 24-slot × 100-byte ring (driver object `+0x980`) and out as 36-byte records | raw | `fn 0x39e4324`, `fn 0x39e4f60` | UNKNOWN in this module; M8.H29 follows the consumer |

The checksum leaf rejects a payload byte with bit 7 set (`and #0x80` at
`0x039e4272`, `bt` back to the false return), then sums bytes 1 through
`len-3` and compares `(sum & 0x7f)` with `frame[len-2]`.

### Hand-built example

`0xb0` maps to length 6 in the TX table. Command `0x20`, data `02 00`:

```python
f = bytearray([0xb0, 0x20, 0x02, 0x00, 0, 0xf0])
f[4] = sum(f[1:-2]) & 0x7f
print(f.hex())          # b020020022f0
assert (sum(f[1:-2]) & 0x7f) == f[-2]
```

`b0 20 02 00 22 f0` and `b0 23 02 00 25 f0` are exactly the two frames the
guest wrote to SCIF7 in EXP-2026-11-22-M8.H1 O7, so the parser and the live
traffic agree. The meaning of command bytes `0x20`/`0x23` is a HYPOTHESIS
(periodic status/version queries — the checksum differs only by the command
difference 3).

## RX path

`fn 0x39e4c50` sets `SetCommMask(EV_RXCHAR | EV_ERR)` (`0x81`), waits in
`WaitCommEvent`, clears errors and calls `fn 0x39e4a54`. The assembler uses
two 100-byte buffers, `ReadFile` four bytes at a time, the start scanner
above, the length table, a `0xf0` terminator search in `fn 0x39e4630`, and
the checksum leaf; valid frames go to `fn 0x39e4324` and `fn 0x39e4700`.
On serial error it logs
`NavDrv >> GPS:GpsThread GpsThread! detected serial error (%02x)` and calls
`PurgeComm(…, 12)`. This is the driver-side receive path exercised by M8.H1's
`sci7` injections (C-6984/C-6985); the "driver reads no serial data"
falsifier is refuted.

## MMIO at `0x19800000` and `0xffc5a000`

- `0xffc5a000` (gyro ADC) literal `0x39e720c` is loaded at `0x39e6fcc` in
  `fn 0x39e6f74`; `0xffc5b000` (speed pulse) literal `0x39e722c` at
  `0x39e70fa`. Mapped with `VirtualAlloc`/`VirtualCopy`; documented in
  `docs/firmware/kepdrv.md` (C-7250/C-7251). Not GPS.
- `0x19800000` is reached through the P2 uncached alias `0xb9800000`:
  literal `0x39e6d28`, load at `0x39e6bec`, `MmMapIoSpace` at `0x39e6bf8`
  inside `fn 0x39e6b70` (`IprInit`), 0x1000 bytes, result saved at driver
  object `+44/+48/+80`. Failure logs
  `NavDrv >> IPR:IprInit  Map register to address Failed` (`0x39e2800`).
  The device's physical role is UNKNOWN (C-1302).

## Differences between builds

`navdrv.dll` sec0 (file `0x4260200..0x4266c00`) SHA-256 is
`e920886fe16ebf02397cef143d534ad0a5e63359a5fea3779e20f36826b6b806` in both
EU2011 and US2011 heads; sec2 (pdata) is also identical. No build-specific
VA is needed.

## What could be changed

- The baud constant at `0x39e4040` (`mov.w` halfword) is a one-value patch,
  but the receiver expects 4800 on this path; changing it alone would break
  framing rather than speed up the link.
- The RX/TX length tables at `0x39e17e4`/`0x39e1808` define which start
  bytes are legal; a peer must use one of them.
- Command IDs and the fields after them are the remaining unknowns; M8.H30
  can encode the captured frames, M8.H29 must locate the lat/lon decoder in
  `Navi.exe` before a synthetic fix can be built.

Evidence: EXP-2026-11-22-M8.H27-navdrv-gps-protocol, claims C-7240–C-7249.
