# `anwdrv.dll` — the iNai frame link to the audio microcontroller on `SCI1:` (M8.H43)

> Static, EU2011 (ROM B, `archive/head256.img`, SHA-256
> `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`,
> 268 435 456 B). **No L3/L4/L5 run** is claimed here; the one wire frame is
> the one logged in [`EXP-2026-11-22-M8.C2a`](../experiments/EXP-2026-11-22-M8.C2a-serial-dma.md)
> O4. Claims C-7400–C-7409, record
> [`EXP-2026-11-22-M8.H43-anwdrv-frame-protocol`](../experiments/EXP-2026-11-22-M8.H43-anwdrv-frame-protocol.md).
> SH-4 code is little-endian (`tools/sh4dis.py`).

All addresses come from `python3 tools/cerom.py --image-start 0x3e00200
archive/head256.img modules|sections|extract|exports|imports`; none are fitted
deltas. `fn 0x…` below is the module VA (`vbase 0x03b80000` + section RVA),
the same convention `docs/firmware/navdrv.md` uses; the runtime VA is
`module VA + 0x84944000` (module load `0x884c4000`). A `pdata` START is
marked `[pdata]`; everything else is a leaf reached from a vtable or a call.

## 1. Module and interfaces

| Item | Value | Status |
| --- | --- | --- |
| Module | `anwdrv.dll`, build B module 42, `attr=0007`, size `0x2ca00`, load `0x884c4000`, vbase `0x03b80000`, 3 objects | VERIFIED, `cerom.py modules` |
| Code | sec0 realaddr `0x03b81000`, vsize `0x262db`, stored `0x26400`, file `0x0415b200`; **all executable**, no compressed code (C-2128) | VERIFIED, `cerom.py sections` |
| Data | sec1 rva `0x28000` compressed (`0x560` B, realaddr `0x01f71000`), sec2 rva `0x29000` compressed (`0x1de0` B, realaddr `0x03ba9000`); both decode `OK` | VERIFIED, `cerom.py decompress --modules anwdrv.dll` |
| Exports | 80 stream entries for 7 logical devices: `AUD`, `TNR`, `TMC`, `ANT`, `UPD`, `PDT`, `CEN/MMP`, each `Init`/`IOControl`/`Open`/`Close`/`Read`/`Write`/`Deinit`/`Power*` | VERIFIED, `cerom.py exports` |
| `SCI1:` | opened with CreateFileW in `fn 0x03ba0020`; literal `0x03b890f8` (file `0x80f8`); 8 data bits, no parity, one stop bit in the same function | VERIFIED (string + xref), `sh4xref.py --to 0x03b890f8` |
| TX carrier | SCIF1 FTDR, HPB-DMAC channel 10, 8 bytes per frame (EXP-M8.C2a O1/O4) | OBSERVED (L4 log) |
| RX carrier | SCIF1 FRDR, HPB-DMAC channel 1, two-plane armed, **no peer in `-M ze0`** (EXP-M8.C2a O1/O4) | OBSERVED (L4 log) |
| Classes | `CInaiFuncs`, `CInaiProtocol`, `CInaiMsg`, `CInaiMsgRcv`, `CInaiFormat`, `CCeNetMsgFormat`; UTF-16 names in sec0 at file `0x69b0`, `0x6ad0`, `0x7bdc`, `0x7b58`, `0x7cf0`, `0x7474` | VERIFIED (strings + RTTI xrefs) |
| Threads | `ReadThread` (`fn 0x03b9ea10`), `ProtocolThread` (`fn 0x03b9eee4`), `WriteThread`, created by `fn 0x03b9f154` | VERIFIED (`sh4dis`, name strings at `0x7024`/`0x7030`/`0x7040`) |

## 2. Frame grammar (wire)

The one frame the guest sent 9 675 times during launch
(EXP-M8.C2a O4) is:

```
10 02 02 08 00 10 03 19
```

`fn 0x03ba23f4` builds it, byte for byte:

| Field | Bytes | Code | Status |
| --- | --- | --- | --- |
| Start | `10 02` = **DLE STX** | `mov #16,r3; mov #2,r0; mov.b r3,@r9; mov.b r0,@(1,r9)` at `0x03ba240a…0x03ba2410` | VERIFIED |
| Message body | DLE-stuffed bytes | `AddPutDleData` `fn 0x03ba4ab0` called at `0x03ba243a`; the in-module copy is `fn 0x03ba2260` | VERIFIED |
| End | `10 03` = **DLE ETX** | stores at `0x03ba2448` (`0x10`) and `0x03ba2450` (`0x03`) | VERIFIED |
| BCC | one byte, XOR | `fn 0x03ba2138` called at `0x03ba2462`, stored at `0x03ba246a` | VERIFIED |
| Start scanner | first `0x10` in the RX buffer | `CInaiFormat::GetStartDataPos` `fn 0x03ba1f10`, loop `0x03ba1f26…0x03ba1f3c` | VERIFIED |
| Unstuff | drop the second byte of `10 10` | `fn 0x03ba2334` (`DeletePutDleData`), check at `0x03ba2388…0x03ba239a`, "Illegal DLE" string at `0x03b8a870` | VERIFIED |

**Escaping.** The stuffing loop at `0x03ba22a4…0x03ba22c8` copies every
byte and appends a second `0x10` whenever the byte is `0x10`: a literal DLE
in a message is sent as `10 10`. BCC is computed **after** stuffing.

**BCC rule (verified).** `fn 0x03ba2138` is a leaf:

```
r3 = 0
for each byte b in buffer[0..len):
    r1 = b XOR r3
    r3 = extu.b(r1)          ; keep the low byte
return r3
```

`BccCheck` `fn 0x03ba0860` reads the received BCC from `frame[size-1]` and
calls that routine with `r5 = frame+2`, `r6 = size-3` (`0x03ba087a…0x03ba0896`),
i.e. over the stuffed body **plus the trailing `10 03`**, excluding DLE STX
and excluding the BCC itself. For the logged frame:

```
python3 tools/anw_frames.py frame 1002020800100319
# payload=020800 control=0 (0x02) BCC=19

python3 tools/anw_frames.py build 020800
# 1002020800100319
```

`02 ^ 08 ^ 00 ^ 10 ^ 03 = 19` reproduces the last byte. A mismatched BCC
is rejected by `BccCheck` with the log
`CInaiFormat::BccCheck! detected format error BCC = %02X / RecvBCC = %02X`
(string at `0x03b89568`). `tools/anw_frames.py --selftest` pins the vector
and four negative controls (wrong BCC, wrong ETX, wrong STX, undoubled DLE).

**Control / DT byte.** The first byte of the decoded message is the control
type. `fn 0x03ba1f5c` maps `0x02 → 0`, `0x06 → 1`, `0x15 → 2`, otherwise `3`
and logs `GetControlType! Data(0x%02X) ret DT_TYPE_ERR` (`0x03b8a580`).
`GetWriteResult` `fn 0x03ba07b4` requires an event result of `0x0102`
(`0x03ba07ce`); if the response byte at `this+40` is `0x15` it logs
`CInaiProtocol::GetWriteResult! recieve NAK!!!!` (`0x03b893c8`). So **0x02 is
ACK, 0x15 is NAK**; 0x06 is a third, non-NAK class (meaning UNKNOWN).

## 3. Launch-phase message catalogue

The driver's `IOCTL` dispatcher is `fn 0x03b909b8`: it subtracts
`0x7ff2e000` from the IOCTL code, bounds it to `< 0x90`, and dispatches
through the two-level table at `0x03b8333c`. The log
`[Ioctl:0x%08x]` (`0x03b828fc`) is loaded in this function and in
`fn 0x03b8ebb8`. Each handler builds a `CInaiMsg` with a command constant
(vtable slot `0x310`/`0x314` of `CInaiMsg`) and logs its name. Launch-phase
rows (all `[pdata]`):

| Message (log name) | Handler VA | Cmd | Wire payload sent |
| --- | --- | --- | --- |
| `ReqMo` (module request) | `fn 0x03b90bbc` | `0x02` | `02 …` — the logged frame starts with this command |
| `Audio` | `fn 0x03b90d40` | `0x04` | `04 …` |
| `ReqMIr` | `fn 0x03b90e98` | `0x02` | type/number form (`ReqMIr:T=%02x:N=%02x`) |
| `ReqAIr` | `fn 0x03b90fe4` | `0x01` | request form |
| `GetAS` | `fn 0x03b91110` | `0x01` | read-back |
| `GetSy` (system info) | `fn 0x03b9117c` | `0x09` | read-back; feeds `ANWDRV >> iNai recieve CeNet System Infomation` |
| `GetLa` | `fn 0x03b912c8` | `0x09` | read-back |
| `ReqAn` | `fn 0x03b91368` | `0x04` | `04 …` |
| `SetCS` | `fn 0x03b915f4` | — | type/number form `T[%02x]N[%02x]` |
| `BeepC` | `fn 0x03b91828` | `0x01` | beep command |
| `SetFO` / `GetFO` | `fn 0x03b91898` / `fn 0x03b919a4` | `0x01` | file-operation command |

The command byte is the `mov #N,r6` immediately before the call through
vtable slot `0x310` (e.g. `0x03b90bf2` for `ReqMo`). The logged body
`02 08 00` reads as command `0x02` with two parameter bytes; the mapping of
those parameter bytes to a named module is **UNKNOWN** (no firmware string
ties `0x08`/`0x00` to a module). The logical modules named in the driver are
`SelfDiagnosis`, `Antitheft`, `Update`, `Radio`, `MMP(MP3)`, `Visual`,
`Mode`, `Audio` (UTF-16 strings at file `0x7054`…`0x70b0`).

Other launch-path VAs:

| Function | VA | Role |
| --- | --- | --- |
| `CInterface::ConnectDiagCheck` | `fn 0x03b9ee20` | ACC-DET via `KernelIoControl(0x01013000)`, logs `detect ACC-DET` / `Audio connect OK` / `Audio connect NG retry[%d]` (`0x03b87f38`/`0x03b87f94`/`0x03b87ee8`) |
| `CInaiProtocol::GetWriteResult` | `fn 0x03ba07b4` | waits for the response event; ACK/NAK classification above |
| `CInaiProtocol::BccCheck` | `fn 0x03ba0860` | BCC validation |
| `CInaiProtocol::CreatePacket` | `fn 0x03ba0e38` | top-level frame builder |
| `CInaiProtocol::WriteProc` | `fn 0x03ba10f4` | TX worker; logs `write failed. Retry...` (`0x03b89d70`) |
| `CInaiProtocol::WaitLoopReq` | `fn 0x03ba1208` | loop command (`SetLoopCmd`) |
| `CApi_WaitModuleInitialize` | `commondll.dll fn 0x03c03584`, import slot `0x03ba82d0` | launcher wait (id in `r4`) |
| `CApi_ModuleInitializeComplete` | `commondll.dll fn 0x03c035a4`, import slot `0x03ba82cc` | launcher signal (id in `r4`) |

`anwdrv.dll` imports both CApi entry points but has **no literal pool with
their slot VAs**; the calls are made by `AppLaunch.dll`/`Audio.exe` (see
`tools/acm_id_scan.py`, which found 28 module-id calls in build B, none in
`anwdrv.dll`).

## 4. Minimal reply set for a launch peer

For a host peer on `sci1` (M8.H44), the minimum that follows from the code:

1. Answer every request with a frame of the same grammar: `10 02 <control
   <command <params>> 10 03 <BCC>` with **correct DLE stuffing and BCC**.
   A bad BCC is dropped with the `BccCheck` error above.
2. Use control `0x02` (ACK). `0x15` is explicitly NAK and is logged as a
   write failure; it must not be sent as a presence reply.
3. Echo the request command (`0x02` for `ReqMo`, `0x04` for `Audio`/`ReqAn`,
   `0x09` for `GetSy`/`GetLa`, `0x01` for `ReqAIr`/`GetAS`, …) — the request
   handler writes the command into the outgoing `CInaiMsg`, so the
   application correlates by command.
4. A module-presence reply is the body the launcher needs before
   `CApi_ModuleInitializeComplete(id, …)` is called; until it arrives,
   `CApi_WaitModuleInitialize(id, 30000)` times out (the ~27 timeouts of
   EXP-M8.C2a). **HYPOTHESIS** (not executed): replying to `ReqMo` with the
   active module mask is that trigger; the exact body bytes and the id
   mapping are still UNKNOWN.

`GetWriteResult` also logs `failed wait response` when its event wait
returns anything other than `0x0102` (EXP-M8.C2a O4: 9 674 occurrences with
9 675 transmits). A reply that is framed and BCC-valid but does not produce
that event will therefore still leave the retry loop running.

## 5. Falsifiers and limits

- The checksum rule fails if a second, independent logged frame has a last
  byte different from `bcc(body + DLE ETX)`. **Only one wire frame was
  logged** (all 9 675 were identical), so this falsifier is *not yet
  exercised*; the rule is verified on that frame and in the code, and the
  tool's wrong-BCC case is a negative control, not a second observation.
- No frames were injected: rule 13 accepts a generated format only after an
  L3/L4 run, and this is a static map.
- `0x06` control class, the meaning of the `ReqMo` parameter bytes, module
  IDs, timeouts/retry counters and the update/loader messages are out of
  scope and unknown here.
- Build C has the same module at a different base (`load 0x884d8000`,
  vbase `0x03b60000`); its VAs were not re-derived.

## Reproduction

```bash
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img sections anwdrv.dll
python3 tools/sh4dis.py --image-start 0x3e00200 --va 0x03ba23f4 --count 80 archive/head256.img anwdrv.dll
python3 tools/sh4dis.py --image-start 0x3e00200 --va 0x03ba2138 --count 12 archive/head256.img anwdrv.dll
python3 tools/sh4dis.py --image-start 0x3e00200 --va 0x03ba0860 --count 60 archive/head256.img anwdrv.dll
python3 tools/anw_frames.py --selftest       # 12/12 PASS
python3 tools/anw_frames.py frame 1002020800100319
# payload=020800 control=0 (0x02) BCC=19
```
