# `CAN.dll`: the UART link to the VCAN microcontroller and the vehicle signals

Static read for M8.H49, EU 2011. It answers two different questions that are
often conflated: (1) what the SH-4 receives as a *decoded* CAN frame, and (2)
what bytes travel on `UAT3:`. The first is established; the second is **not**.
Nothing here was executed on hardware or in QEMU. All VAs: build A
(`--image-start 0x200200`) for `Vehicle.exe`, build B (`--image-start
0x3e00200`) for `CAN.dll`; SH-4 code is little-endian. Status tags:
**VERIFIED** (command reproduces), **OBSERVED** (assembly/string read),
**HYPOTHESIS**, **UNKNOWN**. Companion page: [`vehicle.md`](vehicle.md)
(17-frame table and consumer/unit analysis from M1.43).

## 1. The two layers

| Layer | Path | Data unit | Status |
| --- | --- | --- | --- |
| Application | `Vehicle.exe` → `CreateFileW("CAN1:")` → Device Manager → `CAN.dll` stream driver → `DeviceIoControl` | decoded object: `can_id` + 8 bytes | VERIFIED |
| Wire | `CAN.dll` → `serial_uat.dll` `UAT3:` at 230400 bps → VCAN sub-microcontroller | bytes on a 16550-like UART | transport VERIFIED, **frame grammar UNKNOWN** |

The SH-4 is **not** the CAN node; the sub-microcontroller is, and the SH-4
sees decoded frames (C-6416, now OBSERVED-for-structure). `Vehicle.exe` has no
CAN or UART imports; it only opens the `CAN1:` prefix.

Modules and entry points:

| Module | ROM | VA / code size | Role |
| --- | --- | --- | --- |
| `CAN.dll` | B | `0x03b40000`, 91 666 B code | `CAN1:` stream driver, owner of `UAT3:` |
| `Vehicle.exe` | A | `0x00010000`, 405 386 B code | VCAN dispatcher: subscribes to 17 frames |

`CAN.dll` has 11 exports: `CAN_Init 0x03b431f4`, `CAN_Open 0x03b43290`,
`CAN_Close 0x03b432d0`, `CAN_Read 0x03b43310`, `CAN_Write 0x03b43350`,
`CAN_Seek 0x03b43390`, `CAN_IOControl 0x03b43440`, `CAN_PowerUp 0x03b433d0`,
`CAN_PowerDown 0x03b43408`, `CAN_Deinit 0x03b43504`, `DllEntry 0x03b43194`.
The CE registry publishes `CAN1:` from key `Launch/default/CAN`
(`Dll=CAN.dll`, Order 1, AppLaunch id `0x16`). `Vehicle.exe` opens it in
`fn 0x00032120` with `GENERIC_READ|GENERIC_WRITE` (`0xc0000000`), share 3,
`OPEN_EXISTING`, and calls `DeviceIoControl` on that handle. No module imports
`CAN.dll` by name (C-6450).

## 2. Wire transport on `UAT3:` (established facts)

- `fn 0x03b4c1e0` opens `L"UAT3:"` (literal `0x03b41b44`) with
  `CreateFileW` (import stub `0x03b5461c`), `0xc0000000`, share 0,
  `OPEN_EXISTING`, flag `0x80` — VERIFIED.
- The default bit rate passed to that open is **230 400**: the u32
  `0x00038400` at `0x03b511f0` is written into the context at `0x03b51090`
  and reloaded at `0x03b5115a` before the call to `fn 0x03b4c1e0` at
  `0x03b51168` — VERIFIED. The debug menu also offers 115 200 and 57 600
  (strings `0x03b42484`, `0x03b4249c`); which value is selected at boot is
  UNKNOWN.
- Serial configuration uses `GetCommState`/`SetCommState`/`SetCommTimeouts`/
  `PurgeComm` in `fn 0x03b4bce8`; the DCB baud field is at struct `+64`,
  byte size/parity/stop bits at `+68/+72/+76` — OBSERVED (values not pinned).
- Raw RX is `COREDLL!ReadFile` called only from `fn 0x03b4b90c` into a ring
  buffer in the context (capacity `+96`, write pointer `+100`, total `+104`,
  flags `+112/+116`, overflow `+0x84`). Raw TX is `WriteFile` in
  `fn 0x03b4b9ec`. Event-driven RX uses `SetCommMask`/`WaitCommEvent`/
  `GetCommModemStatus` in `fn 0x03b4bbac` — OBSERVED.
- `fn 0x03b4c078` and `fn 0x03b4c15c` build the manager objects and store
  the read/write/event callbacks in their vtables (`read = fn 0x03b4b994`,
  `write = fn 0x03b4ba60`, `event = fn 0x03b4bbac`, dispatcher
  `fn 0x03b4bea0`, line config `fn 0x03b4bce8`) — OBSERVED.
- A debug read path in `fn 0x03b476b0` issues a request with command
  `0x01f5`, a variable `len`, and a 16-byte staging buffer, then prints
  `GDIC_DOCAN2[0x%x]:ReadReq[len=%d]` (literal `0x03b419f0`). Variable-length
  records and a command code therefore exist — OBSERVED.
- Named sub-CPU command classes in the debug menu: `SEQUENCE_CMD`,
  `RX_RESPONSE_CMD`, `TX_RESPONSE_CMD`, `DATA_RECV_CMD`, `LOADING_CMD`,
  `DEBUGGING_CMD` (literals `0x03b42944`–`0x03b429ac`); high-nibble switch
  values `0x2/0x4/0x5/0x6/0x7/0x9` in the debug display — OBSERVED.
- `CAN.dll` also opens `GPI1:` and sends IOCTL `0x80092064` (candidate:
  sub-CPU reset, not proven) — OBSERVED.

### What is NOT known about the wire

There is **no recovered start byte, length-field position, checksum
polynomial/algorithm, terminator or byte order** for the `UAT3:` stream. The
only `ReadFile` consumer is a ring-buffer filler; the parser consuming that
ring is reached indirectly through the vtables above and could not be pinned
statically in two sessions. Negative controls: the apparent `xor #0x92` /
`xor #0x89` near `0x03b42806`/`0x03b428b0` lie **inside string data**
(`nk_decomp.py pdata` → `BEFORE first record`), and searching `CAN.dll` for
`CHECKSUM`, `CHKSUM`, `FRAME` and `HEADER` gives 0 hits. **Do not invent a
framing or checksum in a peer and call it recovered.** A byte-exact peer needs
an L4 `uat3` trace (M8.H3) or the ring parser.

## 3. Decoded frame grammar (established)

`fn 0x03b4e194` lays out a CAN-message object; the format strings
`RecvData[0x%02x]…` (`0x03b41c68`) and `can_id = 0x%x` (`0x03b41cd8`) are
referenced from that function:

| Field | Offset in object | Width | Status |
| --- | --- | --- | --- |
| flags | `+0`, `+4` | u32 | OBSERVED |
| 8 data bytes | `+8`…`+0x0f` | 8 × u8 | VERIFIED |
| `recv_size` | `+0x10` | u32 | VERIFIED |
| `can_id` | `+0x14` | u32 | VERIFIED |
| `Filter[8]` | `+0x18`…`+0x2f` | 8 × u8 | OBSERVED |
| diag / power / cycle / notice | `+0x20`…`+0x23` | 4 bytes | OBSERVED |
| `recv_cnt` | `+0x58` | u32 | VERIFIED |

`fn 0x03b43bc0` builds a 60-byte (`0x3c` stride) application-facing record
from typed input records: a type byte selects cases 1/2/3/4, eight payload
bytes are written to `+16`…`+23`, and the output pointer advances by `0x3c`.
This is the shape `Vehicle.exe` consumes through `CAN1:` IOCTLs — OBSERVED.
It is a *decoded-layer* frame, not the `UAT3:` wire format.

## 4. Vehicle signals

`Vehicle.exe` subscribes to 17 frames; their id/name strings are the block at
VAs `0x022160`…`0x022408` (sec0) — VERIFIED. Full list and consumer analysis
are in [`vehicle.md`](vehicle.md) §3; summary:

`0x180 ECM_TorqueControl_RN1`, `0x260 VCM_HMI_GeneralData4`,
`0x280 CLUSTER_BasicInfo_1`, `0x354 Brake_GeneralData`,
`0x355 CLUSTER_BasicInfo_2`, `0x35D BCM_SystemControl`,
`0x421 ATCVT_to_MMI_RN1`, `0x50D VCM_HMI_GeneralData1`,
`0x510 VCM_HMI_GeneralData2`, `0x54A Aircon_GeneralStatus1_ITM`,
`0x54B Aircon_GeneralStatus2_ITM`, `0x5B3 VCM_HMI_GeneralData3`,
`0x5C0 LBCMSG5`, `0x5C5 CLUSTER_GeneralStatus`,
`0x5EB VCM_ChargeHistoryData1`, `0x60D BCM_GeneralStatus7`,
`0x625 USM_GeneralStatus`.

The five signals requested by M8.H49, with a VA per row:

| Signal | Frame / source | Setter / literal VA | Payload byte | Scale / kind | Consumer | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Speed | `0x280 CLUSTER_BasicInfo_1` | `0x00023b9c` (`Set VehicleSpeed_CLUSTER (copy)`), `u16` read at `0x00067be0`/`0x00067c2c` | **UNKNOWN** | `0.1[km/h]` (`0x000249dc`, also `1[km/h]`) | speedometer, `DriveComputerCC` | id/scale VERIFIED, byte OBSERVED |
| Reverse | no frame in the 17 carries a reverse name; `0x421 ATCVT_RangeIndication` is a gear-range enum | probe label `0x00021460` (`Navi Reverse`) only | UNKNOWN | UNKNOWN | positioning / probe | **negative**: no decoder found (agrees M8.H28, C-7259) |
| Ignition / ACC | not one of the 17; HVAC message `MSG_TYPE_VCAN_IGN_STATUS` | `0x0001a0e7`, `0x00015a5c` (`8:IGN_STATUS`), `0x000204ec`/`0x00020514` (`VPRB_EVT_IGN_ON/OFF`) | UNKNOWN | flag / enum | `EvTimerCC`, `HvacCC`, CRM | OBSERVED |
| Illumination / lights | `0x60D BCM_GeneralStatus7`, `0x35D BCM_SystemControl` | `0x00022430` (`Set LowBeamStatus`), `0x00022454` (`Set HighBeamStatus`), `0x00022408` (RearDefrost) | UNKNOWN | flag | `ComfortCC`, lamp screens | OBSERVED (arbitration with `kepdrv`'s `CApi_GetCurrentIlluminationMode` unknown) |
| State of charge | `0x5B3 VCM_HMI_GeneralData3` (`HiVoltBattery_Real_Capacity`), `0x5C0 LBCMSG5` | `0x00023024`, `0x000175c0` (`target_charge_soc = %d`), `0x0001bdd8` (`DrivengRange`) | UNKNOWN | unknown (`%d`) | `EvNoticeCC`, `DriveComputerCC` | OBSERVED |

Only **speed** has a verified unit/scale. No frame-byte offsets were
recovered for the other four; a peer must not claim them.

## 5. What a peer can and cannot do today

Can encode from this page: the 17 ids, the decoded object layout, the 60-byte
application record, the 230 400 bps default, the command-class nibbles.
Cannot encode: a byte-exact `UAT3:` stream (no start/length/checksum/endian),
periodic-vs-request scheduling, runtime bit-rate selection, or the five
signals' byte offsets. M8.H50 must label its wire encoding as a **model**, and
M8.H51 needs an L4 `uat3` trace before claiming the guest accepted a frame.

## 6. Reproduction

```bash
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img exports CAN.dll
python3 tools/sh4xref.py archive/head256.img CAN.dll --image-start 0x3e00200 --to 0x03b41b44
python3 tools/sh4dis.py archive/head256.img CAN.dll --image-start 0x3e00200 --va 0x3b4c1e0 --count 40
python3 tools/sh4dis.py archive/head256.img CAN.dll --image-start 0x3e00200 --va 0x3b51090 --count 8
python3 tools/sh4dis.py archive/head256.img CAN.dll --image-start 0x3e00200 --va 0x3b4e194 --count 100
python3 tools/sh4dis.py archive/head256.img Vehicle.exe --image-start 0x200200 --va 0x32120 --count 30
python3 tools/ce_drivers.py archive/head256.img --image-start 0x3e00200 --markdown | grep -i CAN
```

Claims: C-7460–C-7469. Experiment:
`docs/experiments/EXP-2026-11-22-M8.H49-can-uart.md`.
