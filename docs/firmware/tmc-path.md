# The TMC path in EU2011: where a traffic message enters, and what it looks up

> Static + L3, EU2011 (build A `Navi.exe`, build B `fmmdrv.dll`/`anwdrv.dll`),
> `archive/head256.img` SHA-256
> `d3e5eac9cb5b4cbd…` (first 134,217,728 B). No L4/L5 run and no hardware.
> All VAs come from `tools/cerom.py` module/section headers and `fn 0x…` STARTs
> are confirmed with `tools/nk_decomp.py pdata`. SH-4 code is **little-endian**
> (`tools/sh4dis.py`). Findings and commands:
> [`EXP-2026-11-24-M8.H62-tmc-entry-point`](../experiments/EXP-2026-11-24-M8.H62-tmc-entry-point.md),
> claims C-7590–C-7599.

## 1. `fmmdrv.dll` is not the traffic receiver

`ce_strfind.py archive/head256.img --encoding all fmmdrv` finds **0 hits** in
build A and **2 hits** in build B (`0x3e00200`): module `fmmdrv.dll` (build B
module 52, `load=0x885f5000`, `vbase=0x03a40000`, size `0x5c00`,
`cerom.py modules`). Its PDB string is `CETUS\target\SH4\retail\fmmdrv.pdb`
and its export table names `FMM_Init`, `FMM_Open`, `FMM_IOControl`,
`FMM_Read`, `FMM_Write`, `FMM_Close`, `FMM_Deinit`, `FMM_PowerUp/Down`
(`cerom.py exports`). `fn 0x03a44e64` loads the literal `0xffc55000`
(`pool 0x03a44f28`, `sh4xref.py --to 0xffc55000`) and calls through the flash
controller's vtable. This is the **flash media driver** behind `FMD1:`
(`docs/hardware/generations.md`), i.e. the address the task brief quotes, not a
TMC entry. **The TMC traffic path is in `anwdrv.dll` + `Navi.exe`.**

## 2. Tuner path (`anwdrv.dll`, build B)

`anwdrv.dll` (build B module 42, `load=0x884c4000`, `vbase=0x03b80000`,
size `0x2ca00`) exports 80 stream entries for seven logical devices `AUD`,
`TNR`, `TMC`, `ANT`, `UPD`, `PDT`, `CEN/MMP`, each with `Init`/`IOControl`/
`Open`/`Close`/`Read`/`Write`/`Deinit`/`Power*` (`cerom.py exports`). The
frame grammar on `SCI1:` (DLE STX/ETX, BCC, control byte) is documented in
[`anwdrv.md`](anwdrv.md); the tuner receives RDS/TMC data over that link.

The decoded-message application side is **`Navi.exe`'s `TMC_ANDM`** group.
`ce_strfind.py` finds **41** UTF-16LE strings `TMC_ANDM…` in `Navi.exe`
sec0 (VA `0x00028008`…`0x00029b30`), including:

| String VA | Text | Meaning |
| --- | --- | --- |
| `0x00028008` | `TMC_ANDM:<f_HDL_TMC_ANDM> Rcv event=%d` | event entry |
| `0x00028120` | `TMC_ANDM:<GetTMCHandle> CreateFile OK` | opens `TMC1:` |
| `0x00028290` | `TMC_ANDM:<TMCSetMessage> ACQrslt rc_io=%d` | message acquisition |
| `0x00028358` | `TMC_ANDM:<TMCSetMessage> SET_SInfo data 0x%x,…` | station info |
| `0x000284b8` | `TMC_ANDM:<TMCSetMessage> SET_CountryCode data 0x%x` | country code |
| `0x00028520` | `TMC_ANDM:<TMCSetMessage> SET_SID data 0x%x,…` | service id |
| `0x00028620` | `TMC_ANDM:<TMCSetMessage> SET_AID data 0x%x,…` | event/AI id |
| `0x00028730` | `IOCTL_TMC_SET_MESSAGE Header[LS1=…,LS2=…,ST=…,CMD=…]` | message header |
| `0x000287e8` | `IOCTL_TMC_SET_MESSAGE unit=%d,len=%d,Header[MG=…,TL=…,LN=…]` | message grid/table/length |
| `0x00029b30` | `TMC_Ccm:<procCmdResp> MG=0x%x,TL=0x%x,LN=0x%x,LS1=0x%x,LS2=0x%x,ST=0x%x` | decoded command response |
| `0x00028a08` | `TMC_ANDM:<TMCGetMessage> IOCTL_TMC_GET_MESSAGE rcv_size=%d,MG=0x%x,DT=0x%x` | read-back |

## 3. The receive chain, with `pdata` STARTs

| Step | Function (`fn`, START) | Evidence |
| --- | --- | --- |
| Init: `CreateEvent(TMC_RCV_POWER_ON)` | `fn 0x003885a8` (len `0xcc`, end `0x00388674`) | `0x003885c0` loads `TMC_RCV_POWER_ON` VA `0x00027f08`; thunk `0x003d1490` → IAT `COREDLL.dll!CreateEventW` |
| Event receive loop / `Rcv event=` | `fn 0x003886f0` (len `0xd4`, end `0x003887c4`) | `0x00388754` loads string `0x00028008`; `sh4xref.py --to 0x003886f0` → called from task creator `fn 0x0032efa8` at `0x0032f564` |
| `TMC1:` handle + event->code mapping | `fn 0x003887c4` (len `0x8c`, end `0x00388850`) | `0x003887e0` loads `TMC1:` VA `0x00028200`; `0x0038880c`/`0x00388812` select `TMC_ANDM` error strings on failure |
| Decode one message into the ring | `fn 0x00388850` (len `0x2f4`, end `0x00388b44`) | `mov.b @(N,r8)` / `mov.w @(N,r8)` for N = 0…33 at `0x003888de`…`0x00388a4e`; each group ends `jsr @r9` = printf via `0x0032ef78`; returns a small code in `r0` |
| Command-response classifier (`MG`/`TL`/`LN`) | `fn 0x00389924` (len `0x1d4`, end `0x00389af8`) | `0x00389962`/`0x00389986` load `TMC_Ccm:<procCmdResp>` VAs `0x00029b30`/`0x00029ad0`; compares decoded byte with `0x10`, `0x11`, `0x70`, `0x80`, `0x81`, `0x82`, `0x83`, `0x7b`, 4, 100, 300, 500, `0x261` |
| Command dispatcher | `fn 0x0038a94c` (len `0x100`, end `0x0038aa4c`) | `0x0038a968` calls `fn 0x00388b44` (`TMCGetMessage` wrapper), then switches on the code: `0x10`→`fn 0x00389924`, `0x11`→`fn 0x00389798`, `0x70`→`fn 0x0038a5ac`, `0x80`→`fn 0x0038a668` |
| Event pump (state + dispatch to message handlers) | `fn 0x0038aa4c` (len `0x1ac`, end `0x0038abf8`) | reads 16 bytes into `r15+16`, calls `fn 0x0038a94c`, compares `r15+24/+26` words with 100/0x261/300/500 and dispatches `fn 0x0038a078`/`0x0038a0e4` |
| **Injection point: TMC search wrapper** | **`fn 0x003bcc7c`** (len `0xa4`, end `0x003bcd20`) | `0x003bccd6` loads `0x003bcac0` and calls it with `r4 =` the context pointer; this is the only static caller of the SDL search function (`callgraph.py callers`) |
| SDL location-record request builder | `fn 0x003bcac0` (len `0x104`, end `0x003bcbc4`) | reads three `u16` keys from the context at `+16/+20/+24` (`0x003bcaec`…`0x003bcafe`), stores `0x14e4` at `+8`, keys at `+32/+36/+40`, calls `fn 0x003c0e68` (`0x003bcb62`) |

The event table used by the pump has **u16 code → u32 handler word** rows at
`0x00039dc0…` (e.g. row `0x00039df0` = code `0x23` → `0x003bcc7c`, row
`0x00039df8` = `0x22` → `0x003bb21c`), read as code literals in
`fn 0x0038aa4c` (`0x0038ab20` `cmp/eq #100`, `0x0038ab3e` `0x0261`, etc.).
The mapping from an iNai/RDS message code to this table row is the part that
still needs tuner state; the table itself is static and readable.

## 4. Argument layouts — two different 64-byte buffers

**(a) The injection function's own argument** (`fn 0x003bcc7c`, `fn 0x003bcac0`)
is **not** a 64-byte message. The SDL search function reads a caller-owned
context through a single pointer argument:

| Offset in context | Width | Content | Instruction |
| --- | --- | --- | --- |
| `+0` | byte | sequence/guard (three inlets check this) | `fn 0x003895c0`: `0x003895ca mov.b @r8,r3; cmp/eq #1` |
| `+2` | `u16` | unit/index count (nonzero gate in `fn 0x00388850`) | `0x0038886e mov.w @(2,r8),r0`, `cmp/hs r3,r2` with `r2=64` |
| `+4` | `u32` | **pointer to the decoded message body** | `0x0038889e mov.l @(4,r8),r6` |
| `+8` | `u16` | message kind (1/2 branches in `fn 0x00388850`) | `0x0038890e mov.w @(8,r8),r0` |
| `+16`, `+20`, `+24` | `u16`, `u16`, `u16` | **country, location-database no., location code** — the three TMC keys consumed by `fn 0x003bcac0` | `0x003bcaec`/`0x003bcaf0`/`0x003bcaf6` |

The decoded message body at `+4` is itself up to 64 bytes: `fn 0x00388850`
reads bytes `0…33` as grouped halfwords/bytes (country at `0..2`, table at
`3..6`, SID/AID at `7..18`, message header `MG`/`TL`/`LN` at `19..33`) and
logs them via the `TMCSetMessage` strings. So the **message** carries
country/table/location/event/direction/extent as separate byte groups; the
**context** carries the three lookup keys at `+16/+20/+24`. Both are
distinct from:

**(b) The 64-byte data-layer request** built by `fn 0x003bcac0`
(`tmc_req_l3.py`'s `build_body`): `u16 id = 0x14e4` at `+8`, `u16 sub = 1`
at `+10`, and the three keys as `u32` at `+16/+20/+24`. This is the buffer
delivered to the data-access task at `0x004003f4`, **not** the argument of
`fn 0x003bcc7c`. Do not confuse them: injecting at `fn 0x003bcc7c` means
passing a context pointer in `r4`; injecting at the data layer means passing
the 64-byte message body.

## 5. Card reads caused by the injected message

The real L3 control (`tmc_req_l3.py run … --request 0x14e4:1:2,25,1203`) prints
`mount: both tasks idle, 31 reads, state 2, mesh_count 46` and for that one
request:

```
read RDSTM001/LCTBL001.DAT off=0x000000 len=0x1000 tag=0x0b61
read RDSTM001/LCTBL001.DAT off=0x001000 len=0x3600 tag=0x0b01
read RDSTM001/LCTBL001.DAT off=0x004600 len=0x1000 tag=0x0b02
read RDSTM001/LCTBL001.DAT off=0x005600 len=0x1000 tag=0x0b02
open \SystemSD\RDSTM001\LCTBL001.DAT
name builder 0x003fbed8: 57 calls; (ctx+104=0x14e4, ctx+124=1, …)
replies: 0x14fb to task 0x0
```

`lctbl_lookup_l3.py run … --lookup 2,25,1203 --lookup 2,25,60000` prints for
the present code `status 1` with reads `header 0x0/0x1000`,
`catalog 0x1000/0x3600`, `index page 0x4600/0x1000`,
`index page 0x7600/0x1000`, `page directory 0x721800/0x100`,
`record page 0x318138/0x2678` (twice), 2 table-task turns and 2 inflates;
the absent code answers `status 4` after two index pages and no inflate.
Both agree with `lctbl_build.parse` (2/2). Mutation control: `0x14f4:1` with
the same keys reads **only** `REFER001/POINT001.DAT` and answers `0x14b8`,
never LCTBL (C-5680/C-5682).

## 6. Inject recipe (L3)

1. Boot the `datask_l3` machine with
   `Runner("archive/head256.img", card)` from `tmc_req_l3.py` to get `m`,
   `dt`, and mount state 2.
2. Allocate a 64-byte context with `p = m.malloc(64)`; write the body at offset
   `+4`; write `u16` country/DB/code at `+16/+20/+24`, the message kind at
   `+8`, the nonzero guard at `+0` and a nonzero count at `+2`.
3. Call `m.call(0x003BCC7C, [p], max_insns=…)` (the engine passes `r4…r7`;
   this function needs `r4` only). Watch `dt.rows` from step 1: a successful
   call must append the `LCTBL001` reads above and the `0x14fb` answer.
4. Controls: the same call with an absent location code must take the status-4
   path; the `0x14f4:1` data-layer request must take the POINT path and no
   LCTBL read.
5. The full-system (L4) driver is out of scope here: the `TMC_RCV_POWER_ON`
   event is created in `fn 0x003885a8` and signalled by the `anwdrv` receive
   thread, which this L3 machine does not run. Rule 13 therefore leaves L4/L5
   acceptance open.

## 7. Relation to M4.51 / M4.62 and the falsifier

- `0x14e4` has exactly one static sender, `fn 0x003bcac0` (C-5404) — the
  **positive control** for this task, not the deliverable. The deliverable is
  the traffic-side injection point `fn 0x003bcc7c` whose call causes the
  `0x14e4` request and hence the `RDSTM001`/`LCTBL001` reads above.
- `0x14f4` has no static sender (C-5405) and reads REFER001 POINT/ADDRE/
  INTER files, not RDSTM (C-5680/C-5682). M4.62 studies its dynamic tag
  writer; this task does not duplicate it.
- **Falsifier** (task wording): "the traffic module takes location data only
  from the US `XMD` path in this build." Negative: EU2011 has `TMC1:` and
  41 `TMC_ANDM` strings, an iNai `TMC` device in `anwdrv.dll`, and the L3
  lookup that reads EU `RDSTM001/LCTBL001.DAT`. US 2011 uses `XMD` (C-070),
  but that is a different build. The static event-code→table-row step from
  the iNai frame to `fn 0x003bcc7c` is not proven here; it is the remaining
  UNKNOWN (C-7598), not a refutation.

## Reproduction

```bash
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img modules | grep -i fmmdrv
python3 tools/ce_strfind.py archive/head256.img --encoding all fmmdrv
python3 tools/ce_strfind.py archive/head256.img --image-start 0x200200 --module Navi.exe --encoding utf-16le 'TMC_ANDM'
python3 tools/nk_decomp.py pdata archive/head256.img --module Navi.exe 0x003bcc7c 0x003bcac0 0x00388850 0x003886f0 0x003885a8 0x00389924 0x0038a94c 0x0038aa4c
python3 tools/sh4dis.py archive/head256.img Navi.exe --image-start 0x200200 --va 0x003bcc7c --count 60
python3 tools/sh4dis.py archive/head256.img Navi.exe --image-start 0x200200 --va 0x003bcac0 --count 70
python3 tools/sh4xref.py archive/head256.img Navi.exe --image-start 0x200200 --to 0x003bcac0
python3 tools/tmc_req_l3.py run archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --request 0x14e4:1:2,25,1203
python3 tools/lctbl_lookup_l3.py run archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --lookup 2,25,1203 --lookup 2,25,60000
```
