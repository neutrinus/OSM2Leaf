# Antitheft / IMMO / `SECURE` path (M1.48)

> Static map, no L3/L4/L5 run is claimed. Sources: build A (apps,
> `archive/head256.img`, 134 217 728 B read, sha256 of the first 128 MiB
> `d3e5eac9cb5b4cbd…`, image start `0x200200`, va_base `0x8cae1000`) and build
> B (kernel/updaters, `archive/us256.img`, image start `0x3e00200`, va_base
> `0x88000000`). EU2011 = US2011 for build B at the ANT layer: the same
> strings, counts and module VAs appear in both images (falsifier tested).
> Every address comes from `python3 tools/cerom.py … modules|sections|exports|
> imports`; none are fitted deltas. SH-4 code is **little-endian**
> (`tools/sh4dis.py` pins this). ANT strings are UTF-16LE, not ASCII — an
> ASCII search is a false negative (M8.E1 trap for text).

## 1. Modules

| Module | Build | Load / vbase | Role | Status |
| --- | --- | --- | --- | --- |
| `anwdrv.dll` | B | `0x884c4000` / `0x03b80000`, 182 784 B | iNai frame link to the audio MCU on `SCI1:`, device `ANT1:`. Holds the `ANT_RCV_SECURITY_*` receive names. | VERIFIED — `cerom.py modules`, `ce_strfind --encoding utf-16le` |
| `UpdateMng.exe` | B | `0x88a0a000` / `0x00010000`, 69 120 B | `CUpManager::AntiTheftThreadMain`: the SH-4 side of the IMMO handshake. Holds both `ANT_RCV_*` and `ANT_SEND_SEC_*` names plus an import of `CApi_AntitheftUnlock`. | VERIFIED — `cerom.py modules/imports`, `ce_strfind` |
| `commondll.dll` | B | `0x88476000` / `0x03c00000`, 59 904 B | Exports `CApi_AntitheftRcvSecure` (ord 1, rva `0x3894`) and `CApi_AntitheftUnlock` (ord 2, rva `0x38b4`); holds the `ANTITHEFT_UNLOCKOK` event name. | VERIFIED — `cerom.py exports/imports`, `ce_strfind` |
| `AppLaunch.dll` | B | `0x88498000` / `0x03bb0000` | Launches `\windows\AntiTheft.exe` (UTF-16LE literal `0x03bc05e4`); imports both CApi anti-theft entry points. | VERIFIED — `cerom.py modules/imports`, `ce_strfind` |
| `VIN.dll` | B | `0x8869d000` / `0x03950000`, 46 080 B | Imports `CApi_AntitheftRcvSecure` and `CApi_ReadPrivateArea` (the PROD/private-area API): the bridge where a VIN/PROD-derived value can enter the decision. | VERIFIED — `cerom.py imports` |
| `AntitheftCC.dll` + `AntitheftCCWrapper.dll` | A | `0x8d5bf000` / `0x03600000` (98 816 B) and `0x8d5b8000` / `0x03620000` (7 168 B) | COM control and wrapper; exports `ANT_WRAP_runAntitheftCCWrapper` / `…stop…` / `…setCCWindowHandle`. No PRIVATE/IMMO string literals; the wrapper is driven by the app. | VERIFIED — `cerom.py modules/exports`, `antitheft_map` |
| `PhoneBTA.exe`, `Telema.exe`, `Usb.exe` | A | `0x8f3c1000`, `0x8fad4000`, `0x902e4000` | Waiters: each holds an `ANTITHEFT_UNLOCKOK` event name and a wait/log string. | VERIFIED — `antitheft_map`, `ce_strfind` |
| `ScreenStateCC.dll`, `EvNoticeCC.dll`, `InfoBarCC.dll` | A | `0x8f471000`, `0x903b7000`, `0x9041c000` | HMI `SRT_COLD_SECURE` / `POP_SRT_COLD_ANTI_THIEF_SECURE` screens and `_FNR_` / `_CAS_` status pairs (two vehicle variants). | VERIFIED — ASCII string scan |

pdata census (build A) lists `AntitheftCCWrapper.dll` 25 records and
`AntitheftCC.dll` 732 records (`tools/fixtures/pdata_census_2011.json`).
`AntiTheft.exe` is **not** a ROM module in either build; it is a file on the
card launched by `AppLaunch.dll` (`\windows\AntiTheft.exe` literal at
`0x03bc05e4`), so its body is outside this static map.

## 2. Who decides, and what is compared

The decision is made by the **audio microcontroller**, not by the SH-4 and not
by the car's BCM. The SH-4 side (`UpdateMng.exe` + `anwdrv.dll`) only relays
the protocol over the **iNai link on `SCI1:`** (DLE-stuffed frames, see
`anwdrv.md`): it *receives* `ANT_RCV_SECURITY_LOCK` from the audio side and
*answers* with `ANT_SEND_SEC_RESPONSE`, later `ANT_SEND_SEC_RELEASE`. The
compared value is the 4-byte IMMO code in PROD `+0xA0` together with the flag
at `+0x193`; `CApi_ReadPrivateArea` is the SH-4 API that reads that area, and
`VIN.dll`/`anwdrv.dll`/`AppLaunch.dll` import it. **No SH-4 code comparison of
the IMMO code was found**: the values live in the PROD private area/flash and
the comparison itself is performed on the audio MCU side, which is not in the
SH-4 firmware image. This is the task-permitted "comparison is not in SH-4
code" outcome.

Status of this item: **OBSERVED** for the message flow and API names (all
columns of the tables below are quoted from a command); **HYPOTHESIS** for the
attribution of the decision to the audio MCU — the audio MCU code is not in
this image, so the claim rests on (a) the SH-4 only sending/receiving protocol
messages and (b) `docs/hardware/unit-flash.md` / C-5202 describing the flag
and code. The PROD bytes of a real unit were **not** inspected here (M6.19 is
not on this machine); C-5202 is quoted from the existing claim, not re-derived.

## 3. Lock and release sequence (VA per send and receive)

Build B, module VAs (`+ 0x84944000` gives the runtime VA at the module load
`0x884c4000`/`0x884d3000`; convention of `anwdrv.md`). The string VA is where
the name literal lives; the code xref is the literal-pool load that uses it.

| Step | Direction | Message | Name VA (module) | Code / send-receive site | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | MCU → SH-4 | `ANT_RCV_SECURITY_LOCK` | `0x03b8b0ec` (`anwdrv.dll` sec0); also `0x00011124` (`UpdateMng.exe` sec0) | `anwdrv.dll` receives over `ANT1:`/`SCI1:`; `CUpManager::AntiTheftThreadMain` logs the event `UPM_ANT_EVENT_SECURE_LOCK` (literal `0x000114f0`) | VERIFIED (VA + xref via `antitheft_map`/`sh4xref`) |
| 2 | SH-4 → MCU | `ANT_SEND_SEC_RESPONSE` | `0x00011440` / `0x000114b8` (`UpdateMng.exe` sec0) | `CUpManager::AntiTheftThreadMain` log `ANT_SEND_SEC_RESPONSE OK/NG`; handler `fn 0x000189e8`, literal loads at `0x00018c34`/`0x00018c30` | VERIFIED |
| 3 | MCU → SH-4 | `ANT_RCV_SECURITY_RELEASE_OK` | `0x03b82c3c` (`anwdrv.dll`), `0x000110ec` (`UpdateMng.exe`) | event `UPM_ANT_EVENT_SECURE_RELEASE` (`0x00011578`); `WaitForMultipleObjects` log `0x00011608` | VERIFIED |
| 4 | SH-4 → MCU | `ANT_SEND_SEC_RELEASE` | `0x00011350` / `0x000113c8` (`UpdateMng.exe`) | `CUpManager::AntiTheftThreadMain` log `ANT_SEND_SEC_RELEASE OK/NG`; literals `0x00018c3c`/`0x00018c38` | VERIFIED |
| 5 | SH-4 internal | `CApi_AntitheftUnlock()` | `0x000116d8` / `0x00011750` (`UpdateMng.exe`) | imported slot `0x220d0` → `commondll.dll!CApi_AntitheftUnlock` (rva `0x38b4`); calls at `0x00018a7a`, `0x00018af0`, `0x00018bac` | VERIFIED (`cerom.py imports`, `sh4xref --calls`) |
| 6 | SH-4 internal | `ANTITHEFT_UNLOCKOK` event | `0x03c015c8` (`commondll.dll` sec0) | waiter `fn 0x03c068e4`, literal `0x03c0694c`, three close handles via import `0x01f7a048`; also loaded at `0x03c0126e` | VERIFIED (`sh4xref --to`) |

The `ANT_SEND_SEC_*` log names exist only in `UpdateMng.exe` (build B);
`ANT_RCV_*` exists in both `anwdrv.dll` and `UpdateMng.exe`. The alternative
`CApi_AntitheftRcvSecure` export is used by `AppLaunch.dll`, `anwdrv.dll`,
`VIN.dll` and the build-A waiters (`Audio.exe`, `CameraCC.dll`, `SystemEXE.exe`,
`TelemaAppWrapper.dll`, `UsbAudioCC.dll`, `Usb.exe`).

## 4. What each waiting process refuses while locked

Each waiter creates/waits on `ANTITHEFT_UNLOCKOK` before proceeding:

| Waiter | String / VA (build A) | Refused while locked | Status |
| --- | --- | --- | --- |
| `UpdateMng.exe` (updater) | `CUpManager::AntiTheftThreadMain` retries (`0x000112b0`); does not call `CApi_AntitheftUnlock` until release | update thread loops/retries, does not signal unlock | VERIFIED (log strings) |
| `Telema.exe` (telematics) | `[DCC]+dcc_AntiTheftProc ANTITHEFT_LOCKED` (`0x1600458`); `ANTITHEFT_UNLOCKOK` (`0x1222c`) | `dcc_AntiTheftProc` does not leave its locked state (no `DCC MESSAGEWAIT_OUT`) | VERIFIED (strings); OBSERVED (behaviour from M8.C1n) |
| `Usb.exe` (USB) | `UsbAntiTheftProc` (`0x11fd4`…); `ANTITHEFT_UNLOCKOK` (`0x120ec`) | `UsbConMngMainThread` does not report `Init Complete` | VERIFIED (strings) |
| `Audio.exe` (audio) | `CAudioAccessFunction::AntitheftFunc` (log name not a ROM literal; API import `CApi_AntitheftUnlock`/`CApi_AntitheftRcvSecure` verified) | audio path does not call `CApi_AntitheftUnlock`, so `NOTICE_AUDIO_SOURCE` never rises and the HMI stays on `SRT_COLD_SECURE` | HYPOTHESIS (API import VERIFIED; screen-join from M8.C1n) |
| `Vehicle.exe` (vehicle) | `[VCL]Antitheft Lock...` (`0x1c86c`) | vehicle HMI shows the anti-theft lock status | VERIFIED (string) |
| Touch guard | `kepdrv.dll` `m_byKeyGuardAllKey = 0xf1` (NK1, `ze0_uistart.py`) | every touch is dropped until `CApi_AntitheftUnlock` clears the guard | VERIFIED (M8.C1n, `ze0_uistart.py`; no code/PROD bytes committed) |

The HMI screens `SRT_COLD_SECURE` / `POP_SRT_COLD_ANTI_THIEF_SECURE` live in
`ScreenStateCC.dll` (`0x2ad5644` / `0x2ad5690`), `EvNoticeCC.dll`
(`0x24b5644` / `0x24b5690`) and `InfoBarCC.dll` (`0x2435644` / `0x2435690`);
the `_FNR_` / `_CAS_` status pairs are in `ScreenStateCC.dll` around
`0x2aad1e3` / `0x2aa1737` (two vehicle variants).

## 5. What could be changed / differences between builds

- The flag at PROD `+0x193` and code `+0xA0` are data in the private area, not
  SH-4 code; LeafSDTools "DISABLE IMMO" zeroes the flag (C-5202; do not use on
  a unit that is not one's own). No patch to firmware is proposed here.
- `CApi_AntitheftUnlock` is an import slot in every waiter; patching a call
  site would change behaviour but is out of scope and unsafe on a real unit.
- Build A has `AntitheftCC.dll` + wrapper and the app-side waiters; build B
  has `anwdrv.dll` + `UpdateMng.exe` + `commondll.dll` and `VIN.dll`. The ANT
  message strings and their module VAs are identical in EU2011 and US2011 for
  build B (falsifier: same hits in both images). Build C VAs were not derived.
- `docs/research/us-eu-region.md` C-082 calls `SECURE` a CAN/VIN check and
  `TEST_B1` a bypass; that is external/hearsay and not confirmed by this
  static map — `CAN.dll`/`VIN.dll` import the anti-theft API, but no CAN frame
  comparison was found in SH-4 code.

## Reproduction

```bash
python3 tools/antitheft_map.py --selftest
python3 tools/antitheft_map.py --image-start 0x3e00200 archive/us256.img
python3 tools/antitheft_map.py --image-start 0x200200 archive/head256.img
python3 tools/cerom.py --image-start 0x200200 archive/head256.img exports AntitheftCC.dll
python3 tools/ce_strfind.py --image-start 0x3e00200 archive/us256.img --encoding utf-16le ANT_RCV_SECURITY_LOCK
python3 tools/cerom.py --image-start 0x3e00200 archive/us256.img exports commondll.dll | grep -i Anti
python3 tools/sh4xref.py --image-start 0x3e00200 archive/us256.img commondll.dll --to 0x3c015c8
python3 tools/sh4xref.py --image-start 0x3e00200 archive/us256.img UpdateMng.exe --calls 0x189e8
```
