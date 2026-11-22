# Bluetooth module on `SCI8:` — wire protocol (M8.H55)

Build: **EU2011**. `BT_FW.dll` is in ROM B (`--image-start 0x3e00200`,
virtual base `0x035c0000`); `BT_MGR.dll` is in ROM A (`--image-start
0x200200`, virtual base `0x03640000`). SH-4 code is little-endian; all VAs
come from `tools/cerom.py` and function starts from `nk_decomp.py pdata`
(BT_FW sec2, 139 records). The same `BT_FW.dll` build is present in EU2011,
US2011, EU2014 and EU2016 (C-6284, M1.37), so the wire layer described here
is the same in all four cards.

## Verdict

The unit does **not** speak bare HCI H4 on `SCI8:`. The wire carries
**CSR BCSP (yabcsp) packets in SLIP-style byte stuffing** — `END 0xc0`,
`ESC 0xdb`, `ESC_END 0xdc`, `ESC_ESC 0xdd` — at **38400 8N1**, and a
**DFU firmware download** is attempted at start. The command layer above BCSP
uses vendor `HOST_GEN_*`/`BCCMD` messages, not standard HCI command packets.
Evidence is in §"Wire framing" and §"Modules"; the falsifier of this task
("the modules never write to the line during start") is addressed in §"Live
observation".

## Modules

| Module / role | VA (EU2011) | Evidence | Status |
| --- | --- | --- | --- |
| `BT_FW.dll` (B), 34 816 B sec0 — UART driver, BCSP framing, DFU download; exports `FWB_Init/Open/Read/Write/IOControl/Close/Deinit` | `0x035c1000` | `cerom.py sections/exports`; strings `DFU_CreatCOMBCSP`, `UartDrv_Start`, `ABCSP_DeInit`, `yabcsp_event: %S`, `abcsp_panic: %u` | VERIFIED |
| `BT_MGR.dll` (A), 383 488 B sec0 — BCSP command layer, device init, profiles, DUN | `0x03641000` | strings `[BCSP] cmdRecvEvent`, `HOST_GEN_*`, `services[SPP:HFP:OPP:A2DP:AVRCP:PBAP]`, `@@@ Bluetooth Ready @@@` | VERIFIED |
| `BT_ENG.dll` / `BT_WRPENG.dll` / `BT_DB.dll` / `BT_Modem.dll` (A) | — | higher layers; not on the wire path (M1.41) | out of scope |

The older `0x6fab2c → 0x6faeb0 → 0x6fb05c` chain is `BT_MGR.dll` OPP code,
not a map-code check (C-520, C-528, C-611); do not use it as a wire anchor.

## Interfaces and line settings

Both modules open the port by name with Win32 `CreateFileW`, not by direct
SCIF MMIO:

| Caller | String VA | Function |
| --- | --- | --- |
| `BT_FW.dll` | `0x035c2300` (`SCI8:`) | `fn 0x035c4714` (`DFU_CreatCOMBCSP`) → `fn 0x035c53a0` (`UartDrv_Start`) |
| `BT_MGR.dll` | `0x0365c4c4` (`SCI8:`) | `fn 0x03694364` (logs `[BCSP]UartDrv_Start error()`) |

`BT_FW.dll` imports (ordinals resolved against `coredll.dll` of build B):
`CreateFileW` #168, `GetCommState` #113, `SetCommState` #118,
`SetCommTimeouts` #119, `SetCommMask` #117, `WriteFile` #171, `ReadFile` #170,
`WaitCommEvent` #122, `ClearCommError` #108, `PurgeComm` #115,
`CloseHandle` #553, `NKDbgPrintfW` #545. RX and TX run in two threads
(strings `rxThread exit count = %d`, `txThread exit count = %d`).

`fn 0x035c7f94` is the DCB setup. It calls `GetCommState`, writes
`ByteSize=8`, `Parity=1`, `StopBits=0` with `fFlags = (old & 0xdf87) | 0x1004`,
sets `COMMTIMEOUTS` to `ReadIntervalTimeout=1`, `ReadTotalTimeoutConstant=1000`
(`0x03e8`) and `WriteTotalTimeoutConstant=3000` (`0x0bb8`), then
`SetCommState`, `SetCommTimeouts`, `SetCommMask`. On failure it logs
`[BtFW]::BaudRate=%d` with the selected value.

The baud is chosen by `fn 0x035c8438` from a 14-entry byte table at
`0x035c356c`: `4800, 9600, 10400, 14400, 19200, 28800, 38400, 57600, 76800,
115200, 230400, 460800, 921600, …`. `fn 0x035c53a0` maps the configured value
from global `0x01c0e83c` (`0x9600` → index 6) to that table. So **38400** is
the value on this path; the `38400` in the M1.39 hardware table agrees, but the
selected runtime default is still OBSERVED rather than fully proven static
(C-6413).

## Wire framing

`fn 0x035c9374` (BT_FW, length `0x1a0`) is the receive byte state machine
(states 1…5). It compares each received byte with:

| Byte | Meaning in the state machine | Instruction VA |
| --- | --- | --- |
| `0xc0` | frame END — closes the current frame, resets state 3, and on an empty frame sets state 3 | `0x035c93dc`, `0x035c93f0`, `0x035c9414`, `0x035c9440` |
| `0xdb` | ESC — fetch the next byte, state 4 | `0x035c9444`, `0x035c946a` |
| `0xdc` | ESC_END — store literal `0xc0` (`mov #-64,r12` at `0x035c9494`) | `0x035c947c`–`0x035c94b2` |
| `0xdd` | ESC_ESC — store literal `0xdb` (`mov #-37,r12` at `0x035c94aa`) | `0x035c9496`–`0x035c94b2` |

`fn 0x035c889c` starts an outgoing frame by emitting `0xc0`
(`mov #-64,r5` at `0x035c88d6`). The 0x80/0x100-byte working buffers live at
object offsets `+0x1090`, `+0x1094`, `+0x1005` (see `fn 0x035c9374`).

Above the byte stuffing the protocol is **BCSP**: strings `ABCSP_DeInit error.`
(`0x035c2b5c`→fn `0x035c5858`), `yabcsp_event: %S` (fn `0x035c4a8c`),
`abcsp_panic: %u`, `Tx buffer overrun` (fn `0x035c6334`), and in BT_MGR
`[BCSP] cmdRecvEvent NG::unknown opcode=%d` (fn `0x03693db0`),
`[BCSP] ### putCmd NG::… opcode=%04X, type=%d`, `send_BCCMD`,
`Tx:HOST_GEN_ENTER_DFU_MODE_REQ`. HCI H4 packet indicators (`01/02/04` as the
first wire byte) are **not** the framing here; they live, if at all, inside a
BCSP payload.

## Start-up exchange

Static order (BT_FW `fn 0x035c4558`, with the log string VA each branch
prints):

| # | Actor | Step | Evidence |
| --- | --- | --- | --- |
| 1 | BT_FW | `dfu_init` / Set DFU mode | `fn 0x035c54d0`, `fn 0x035c52e0`; `fail DFU_SetDFUMode` at `0x035c2270` |
| 2 | BT_FW | Open `SCI8:`, start UART driver (38400) | `fn 0x035c4714` → `fn 0x035c53a0` → `fn 0x035c7f94` |
| 3 | BT_FW | `dfu_ClrStatus` / `dfu_Detach` | `fn 0x035c5bc0`, `dfu_ClrStatus`/`dfu_Detach` strings at `0x035c2f34/0x035c2f64` |
| 4 | BT_FW | `DFU_StartDownload` (manifest, download, reconfigure) | `fn 0x035c4bd4`; `Download Success` `0x035c20e8`, `Manifest Success` `0x035c2064`, `Reconfigure Success` `0x035c21e0`, `DFU OK!` `0x035c1fa0` |
| 5 | BT_FW | Deinit BCSP / fall back to normal mode | `ABCSP_DeInit error.`; `fn 0x035c5858` |
| 6 | BT_MGR | Open `SCI8:`, start BCSP command layer | `fn 0x03694364` → `[BCSP]UartDrv_Start error()` |
| 7 | BT_MGR | `HOST_GEN_APP_INIT_REQ` / `APP_INIT_RES`, `HOST_GEN_SET_POWERMODE_REQ`, `HOST_GEN_SET_LOCAL_NAME_REQ` | log strings `0x0365d288`, `0x0365c798`, `0x0365ce38` (and `_RES` variants, needle VAs `0x0365d2be`, `0x0365c7cc`, `0x0365ce6c`) |
| 8 | BT_MGR | Ready, or bounded failure | `@@@ Bluetooth Ready @@@`; `Timeout awaiting initialization !!` (`fn 0x0369566c`); `device initialize failed, ignore(wait timeout)` |

A stock EU2011 boot puts **no bytes at all** on `SCI8:` (EXP O7): the table
below is a static call/log order, not a captured frame sequence. `PhoneBTA.exe`
fails to import `HCXMemory.dll` on this card/image combination, so the stack
never reaches the radio.

## Timeouts with a silent line

- BT_FW serial: read timeout constant 1000 ms, write 3000 ms (above);
  `download status failure!`, `DFU Failed, Error Code: %d` and the
  `manifest fail! Recovering…` / `Recover Success` branch show the failure is
  recovered, not fatal.
- BT_MGR: `Timeout awaiting initialization !!`, `state=%d retry=%d` with
  retries at 2 and 4 (`fn 0x0369566c`), then
  `device initialize failed, ignore(wait timeout)` — i.e. the stack settles
  with the module effectively absent.

## Recommended stub

**`absent`** for a stock boot (EXP O7: 0 bytes transmitted, boot unchanged).
Implementing a BCSP responder cannot settle a line the guest never writes;
M8.H56 must measure this and report a negative result if it holds. A
`minimal present` peer is only worth building once BT is actually activated
(ACC/VCAN up, `PhoneBTA.exe` loading); if built, it must speak
**BCSP-in-SLIP** and ignore/NACK `HOST_GEN_*` commands, never bare HCI H4.
A peer must not implement the full DFU download — the firmware recovers from
a failed DFU on its own.

## What could be changed

The baud selector table (`0x035c356c`) and the DCB constants in
`fn 0x035c7f94` are single-value data patches (changing them alone would break
framing). The DFU retry/recover policy is in `fn 0x035c4558`; BT_MGR's initial
timeout and retry counts are in `fn 0x0369566c`. The Bluetooth module's own
firmware (`BtUpdate.exe` payload) is **not** patchable from the head unit.

## Differences between builds

`BT_FW.dll` is function-identical in all four cards (C-6284, M1.37), so the
wire view above transfers unchanged. `BT_MGR.dll`/`BT_ENG.dll` changed from
2011 to 2014 (OPP/PBAP and trace strings) but not from 2014 to 2016; none of
those changes alters the transport (C-6305, C-6308).

Evidence: EXP-2026-11-22-M8.H55-bt-wire, claims C-7520–C-7529.
