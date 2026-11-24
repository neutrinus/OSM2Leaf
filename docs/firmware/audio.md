# Audio stack (EU 2011, builds A and B)

Static decompile map of the head-unit audio stack: what the SH-4 does itself,
what it asks the audio microcontroller to do over `SCI1:` through `anwdrv.dll`,
the PCM path and the `anwdrv` / iNai message set. Read-only knowledge (M1.42);
nothing was run on hardware and no patch is built. The wire grammar of the
iNai frames is covered in [`anwdrv.md`](anwdrv.md) (M8.H43); the SSI/DMA
observations come from [`EXP-2026-11-22-M8.H46-ssi-audio`](../experiments/EXP-2026-11-22-M8.H46-ssi-audio.md).

Status tags: **VERIFIED** (a command reproduces it), **OBSERVED** (seen in
strings/disassembly, not executed), **HYPOTHESIS** (a reading, not proven).
Every VA is EU 2011; build A starts at `0x200200`, build B at `0x3e00200`.
VAs come from `tools/cerom.py` (never fitted deltas), function starts from
`tools/pdata.py`. SH-4 code is little-endian (`tools/sh4dis.py`).

## 1. Modules

Code size is the module `size` from `cerom.py modules`; exec section VAs from
`cerom.py sections`. All build-A modules are in the apps image, build-B
modules in the kernel/updaters image.

| Module | ROM | Code (bytes) | Role | Evidence | Status |
| --- | --- | --- | --- | --- | --- |
| `Audio.exe` | A | 228864 | source manager: volume, mute, guidance voice, radio (`TNR2:`), beeps; opens `AUD1:` | `cerom.py exports/imports Audio.exe`; `audio_diff.py drivers` | VERIFIED |
| `wavessi1.dll` | A | 41984 | WAV stream driver, SSI1 TX / SSI0 RX, HPB-DMAC ch 12/11 | `WAV_*` exports; `SSI_Init` strings | VERIFIED |
| `wavessi2.dll` | A | 41984 | second WAV stream driver, SSI2 TX, HPB-DMAC ch 13 | `WAV_*` exports | VERIFIED |
| `waveapi.dll` | A | 95744 | WinCE `waveOut` API above the WaveSSI drivers | `cerom.py modules` | VERIFIED |
| `audevman.dll` | A | 24576 | audio device manager | `cerom.py modules` | VERIFIED |
| `BtAudioCC.dll` | A | 52736 | Bluetooth audio UI COM control | `DllGetClassObject` export | VERIFIED |
| `UsbAudioCC.dll` | A | 86016 | USB audio UI COM control | `DllGetClassObject` export | VERIFIED |
| `anwdrv.dll` | B | 182784 | iNai protocol on `SCI1:`; 80 stream exports over `AUD`/`TNR`/`TMC`/`ANT`/`UPD`/`PDT`/`CEN` | `cerom.py exports anwdrv.dll` | VERIFIED |
| `DspDrv.dll` | B | 340992 | DSP stream driver (`DSP_*`), external audio processor | `cerom.py exports DspDrv.dll` | VERIFIED |
| `BeepDrv.dll` | B | 10240 | beep stream driver (`BEP_*`) | `cerom.py exports BeepDrv.dll` | VERIFIED |
| `MuteDrv.dll` | B | 5120 | mute stream driver (`MUT_*`) | `cerom.py exports MuteDrv.dll` | VERIFIED |
| `wavessi1.dll` | B | 41984 | kernel copy of the WaveSSI1 driver | `cerom.py modules` | VERIFIED |
| `AudioUpdateCC.dll` | B | 33280 | UI for audio/micon updates | `cerom.py modules` | OBSERVED |

`AudioMiconUpdate.exe` (84992 B, build B) is **excluded** by the task Stop
rule: its V850 payload is the microcontroller's own firmware.

## 2. Features

| Feature | String / export | Evidence | Status |
| --- | --- | --- | --- |
| Source switching | `CApi_AudioMainSourceSelect`, `CreateAvOsm1/2` | `Audio.exe` imports/strings | VERIFIED |
| Volume / mute | `SetVo` cmd 3, `SetAu` cmd 2, `MUT_*`, `CApi_SetLineMute`, `CApi_GuidanceVoiceMuteOn/Off` | `anw_msgs.py`, `Audio.exe` imports | VERIFIED |
| Guidance over media | `CApi_GetGuidanceVoiceAtt`, `CApi_SetGuidanceVoiceAtt`, `CSpeechGuideAccess` | `Audio.exe` strings | OBSERVED |
| Beeps | `BeepC` cmd 1, `BEP_*`, `CApi_SoundBeep` | `anw_msgs.py`, exports | VERIFIED |
| Radio (EU) | `TNR2:` open in `Audio.exe`, `TNR_*` exports | EXP-M1.58 O4/O5 | VERIFIED |
| USB / iPod | `UsbAudioCC.dll`, `iPodCC.dll`, `WAV1:` | `cerom.py modules` | VERIFIED |
| Bluetooth audio | `BtAudioCC.dll`, `BT_ENG!AudioEngine` | M1.41 | VERIFIED |
| Audio microcontroller link | `SCI1:`, 80 exports / 7 devices, DLE framing | `anwdrv.md` | VERIFIED |

## 3. Interfaces — PCM path diagram

```text
                              SH-4 (apps, build A)
  Navi/Speech/Vehicle/BT/USB ──> Audio.exe ──commondll CApi_*──> AUD1: (anwdrv, B)
             │                       │                              │
             │                       ├── SOURCE / VOLUME / MUTE ─────┤
             │                       └── guidance voice ─────────────┤
             │                                                       │ iNai frames
             v                                                       v
  waveapi.dll ──> wavessi1.dll (SSI1 TX, DMA ch12) ──> SSI ──> audio MCU / codec
             └──> wavessi2.dll (SSI2 TX, DMA ch13) ──> SSI ──> audio MCU / codec
                              │
                              └── PCM produced by the SH-4 wave drivers
                                  (wavessi1: PLAY_SSI=1/PLAY_CH=12,
                                   wavessi2: PLAY_SSI=2/PLAY_CH=13)

  anwdrv.dll (B) ──SCI1: (8N1, DLE STX/ETX + XOR BCC)──> audio microcontroller
       AUD / TNR / TMC / ANT / UPD / PDT / CEN(MMP)   (7 logical devices,
                                                       10 exports each = 80)
  DspDrv.dll (B) ── DSP_* stream ──> external DSP
  BeepDrv.dll (B) ── BEP_* ──> beep generator
  MuteDrv.dll (B) ── MUT_* ──> mute line
```

Evidence and limits:

- WaveSSI1/2 registry values (`PLAY_SSI=1`, `PLAY_CH=12`, `SysIntr=0x24`;
  `PLAY_SSI=2`, `PLAY_CH=13`, `SysIntr=0x25`) are quoted from EXP-M8.H46
  (L4 model). `wavessi1.dll` sec0 contains `SSI_Init, g_pSSI_TX_RegBase` at
  `0x0375281c` (build A); `sh4xref` resolves it to `fn 0x03757f28`.
- The **PCM producer** is the SH-4 wave driver, not the MCU: EXP-M8.H46 O3/O4
  shows a controlled DMA arm to the SSI block producing non-silent 48 kHz
  stereo S16 samples. The firmware's real sample rate/bit depth remain
  **UNKNOWN** (the 48 kHz/S16 are the QEMU model defaults).
- **Who mixes guidance over media**: `Audio.exe` has the
  `CApi_GuidanceVoiceMuteOn/Off` and `CApi_SetGuidanceVoiceAtt` imports and a
  `CSpeechGuideAccess` class, but no mixer VA was resolved statically and the
  mixing may happen in the audio MCU. **UNKNOWN** where the mix physically
  occurs; the SH-4 side only sends attenuation/mute requests.
- `Audio.exe` talks to the audio controller through the `AUD1:` device
  (`anwdrv.dll`); same device name EU/US (EXP-M1.58 O4).

## 4. Data — the `anwdrv` / iNai message set

`anwdrv.dll` is build-B module 42, vbase `0x03b80000`, code sec0 realaddr
`0x03b81000` (vsize `0x262db`, uncompressed). Its `IOCTL` dispatcher is
`fn 0x03b909b8`; each handler builds a `CInaiMsg` with a command byte in the
`mov #N,r6` delay slot of a `jsr @Rn` through vtable slot `0x310` and loads a
`[Msg:pInBuf]` / `[Msg:pOutBuf]` log literal. `tools/anw_msgs.py` derives the
table below from those bytes (98 literals, 80 with a code-derived command
byte). **Direction**: `TX` = SH-4 -> MCU (the handler sends a command,
`Set*`/`Req*`/`Beep*`/`Audio`), `RX` = MCU -> SH-4 (`Get*`/`RQ*`/`GTRTX`
read-back handlers waiting on the receive event). Meaning is assigned only
where a log string names a feature; otherwise `unknown`.

| Message id | Cmd | Handler VA (eu2011, build B) | Dir | Meaning | Status |
| --- | --- | --- | --- | --- | --- |
| BeepC | 1 | 0x03b91704 | TX | beep command (`BeepC:wBeepT`) | VERIFIED |
| ReqBe | 1 | 0x03b915a0 | TX | beep request (`ReqBe:byReqT`) | VERIFIED |
| GetBe | 1 | 0x03b91828 | RX | beep status read-back | VERIFIED |
| SetVo | 3 | 0x03b8efa8 | TX | volume set (`SetVo:byType`) | VERIFIED |
| SetAu | 2 | 0x03b8ee80 | TX | audio set (`SetAu:byType`) | VERIFIED |
| SetAt | 4 | 0x03b8ed90 | TX | attenuator set | OBSERVED |
| SetBa | 2 | 0x03b8f50c | TX | balance set | OBSERVED |
| SetFa | 2 | 0x03b8f5e8 | TX | fader set | OBSERVED |
| SetBs | 2 | 0x03b8f6c4 | TX | bass set | OBSERVED |
| BFDr | 2 | 0x03b8f87c | TX | (name only) | HYPOTHESIS |
| SetAo | 1 | 0x03b8f8ec | TX | audio output set (`SetAo:byVal`) | OBSERVED |
| SetLo | 1 | 0x03b8f9d0 | TX | loudness set | HYPOTHESIS |
| SetUs | 2 | 0x03b8fa60 | TX | user setting (`SetUs:byNum/byType`) | HYPOTHESIS |
| StEqO | 1 | 0x03b8ff38 | TX | equalizer on/off (`StEqO:OnOff`) | OBSERVED |
| StEqD | — | unknown | unknown | equalizer data | HYPOTHESIS |
| GetIn | 1 | 0x03b9000c | RX | input status read-back | OBSERVED |
| StDoT | 2 | 0x03b901c4 | TX | (name only) | HYPOTHESIS |
| GetAS | 1 | 0x03b91110 | RX | audio status read-back | OBSERVED |
| GetSy | 9 | 0x03b9117c | RX | system info (feeds CeNet System Information) | VERIFIED |
| GetLa | 9 | 0x03b912c8 | RX | language read-back | VERIFIED |
| SetFO | — | unknown | unknown | file operation set (`SetFO:CMD`) | OBSERVED |
| GetFO | 1 | 0x03b919a4 | RX | file operation read-back | VERIFIED |
| GetFl | 1 | 0x03b91a14 | RX | file list read-back | HYPOTHESIS |
| GetKS | 1 | 0x03b91b90 | RX | (name only) | HYPOTHESIS |
| GetEx | 1 | 0x03b91c10 | RX | extended info (`GetEx:byExt`) | OBSERVED |
| SetRd | — | unknown | unknown | RDS set (`SetRd:byData`) | HYPOTHESIS |
| Get2Z | 1 | 0x03b9257c | RX | (name only) | HYPOTHESIS |
| SetAB | — | unknown | unknown | (name only) | HYPOTHESIS |
| LedOn | — | unknown | unknown | LED on | HYPOTHESIS |
| SetIl | — | unknown | unknown | illumination set (`SetIl:Col`) | HYPOTHESIS |
| DtvRq | — | unknown | unknown | DTV request | HYPOTHESIS |
| GetDB | 1 | 0x03b92a74 | RX | (name only) | HYPOTHESIS |
| GetRB | 1 | 0x03b92ae0 | RX | (name only) | HYPOTHESIS |
| SndC | 12 | 0x03b92c38 | TX | sound command | OBSERVED |
| IsrUD | 4 | 0x03b94998 | TX | ISR update | HYPOTHESIS |
| SeekUd | 4 | 0x03b95834 | TX | seek (tuner) update | OBSERVED |
| SeekPA | 4 | 0x03b95894 | TX | seek preset/auto | HYPOTHESIS |
| AfOnf | 4 | 0x03b958f4 | TX | AF (alternative frequency) info | HYPOTHESIS |
| RegOnf | 4 | 0x03b95954 | TX | regional info | HYPOTHESIS |
| TaOnf | 4 | 0x03b959b4 | TX | TA (traffic announcement) info | HYPOTHESIS |
| IntCl | 1 | 0x03b95a14 | TX | interrupt clear (`IntCl:byCmd`) | OBSERVED |
| PtyCtl | 2 | 0x03b95b04 | TX | PTY control (`PtyCtl:Type`) | OBSERVED |
| PtClSt | 1 | 0x03b95c0c | TX | PTY clear status | HYPOTHESIS |
| ReqPT | 1 | 0x03b95c78 | TX | PTY request (`ReqPT:byCh`) | OBSERVED |
| GetPs | 1 | 0x03b95d58 | RX | PS (programme service) read-back | VERIFIED |
| ReqTx | 1 | 0x03b95e78 | TX | text request | HYPOTHESIS |
| GetTx | 10 | 0x03b95ed4 | RX | radio text read-back | VERIFIED |
| RdsTst | 3 | 0x03b95f94 | TX | RDS test | OBSERVED |
| GetPi | 8 | 0x03b960d4 | RX | PI (station id) read-back | VERIFIED |
| SetPi | 2 | 0x03b9616c | TX | PI set | OBSERVED |
| GetPL | 14 | 0x03b961e8 | RX | preset list read-back | HYPOTHESIS |
| SetFq | 4 | 0x03b962b0 | TX | frequency set | VERIFIED |
| ReqSt | 1 | 0x03b963b0 | TX | status request | HYPOTHESIS |
| GetSL | 60 | 0x03b9641c | RX | station list read-back | HYPOTHESIS |
| TuneUD | 4 | 0x03b97b30 | TX | tuning update | OBSERVED |
| SeekUD | 4 | 0x03b97c1c | TX | seek update | OBSERVED |
| Scan | 1 | 0x03b97cf0 | TX | scan start (`Scan:byType`) | VERIFIED |
| Ctrl | 4 | 0x03b97dbc | TX | control (`Ctrl:byType`) | HYPOTHESIS |
| CatCtl | 4 | 0x03b97efc | TX | category control (`CatCtl:byType`) | OBSERVED |
| ModCtl | 1 | 0x03b980a0 | TX | module control (`ModCtl:byType/CatNo`) | OBSERVED |
| PsCtl | 4 | 0x03b98188 | TX | preset control (`PsCtl`) | OBSERVED |
| Test | 1 | 0x03b98314 | TX | self test (`Test:byReq`) | VERIFIED |
| GetInfo | — | unknown | unknown | info read-back | HYPOTHESIS |
| GetText | 32 | 0x03b9848c | RX | text read-back (`GetText:byTy`) | VERIFIED |
| ReqDt | 12 | 0x03b9859c | TX | data request (`ReqDt:byType`) | OBSERVED |
| DBGOS / DBGSS / DBGOR / DBGR | 3/4/1/1 | 0x03b988cc / 0x03b98958 / 0x03b989f4 / 0x03b98c70 | TX/RX | debug read/write | OBSERVED |
| DBReq | — | unknown | unknown | database request | HYPOTHESIS |
| SeekSA | 4 | 0x03b99820 | TX | seek (category) | HYPOTHESIS |
| RQPNM / GetPNM | 1 / 10 | 0x03b99880 / 0x03b998dc | TX / RX | preset name request / read-back | OBSERVED |
| RQRTX / GTRTX | 1 / 10 | 0x03b99984 / 0x03b999f0 | TX / RX | radio text request / read-back | VERIFIED |
| ManUD / SekUD / ScaSe / ScnUD / FTune | 4 | 0x03b99cb0 / 0x03b99d10 / 0x03b99dd0 / 0x03b99ea0 / 0x03b99f00 | TX | manual/seek/scan tuning updates | OBSERVED |
| MnlNUD | 2 | 0x03b99e30 | TX | (name only) | HYPOTHESIS |
| PrCS / PrCll / PrUD | 1 / 1 / 4 | 0x03b99f7c / 0x03b99fd0 / 0x03b9a024 | TX | preset control/status/update | OBSERVED |
| SetBD | 4 | 0x03b9a0d4 | TX | band set (`SetBD:byType`) | OBSERVED |
| GetCrBd | 2 | 0x03b9a3ac | RX | current band read-back | OBSERVED |
| GetSt | 1 | 0x03ba3314 | RX | status read-back | HYPOTHESIS |
| GetPr | 11 | 0x03ba4164 | RX | preset read-back | OBSERVED |
| GetRes | 1 | 0x03ba41e8 | RX | (name only) | HYPOTHESIS |
| ReqFlp | 1 | 0x03ba4250 | TX | flip request (`ReqFlp:Ctrl`) | HYPOTHESIS |

The launch-phase subset (ReqMo, Audio, ReqMIr, ReqAIr, ReqAn, SetCS, …) and
the frame grammar are in [`anwdrv.md`](anwdrv.md); this page adds the rest and
does not duplicate its verified wire facts. The command byte 0x02 of the one
logged frame (`10 02 02 08 00 10 03 19`, EXP-M8.C2a O4) is `ReqMo`'s command;
the meaning of its parameter bytes remains **UNKNOWN**.

## 5. What could be changed

| Item | VA / constant (eu2011) | Change | Status |
| --- | --- | --- | --- |
| Audio source / volume policy | `Audio.exe` imports `CApi_AudioMainSourceSelect`, `CApi_SetGuidanceVoiceAtt` (slot table) | code patch in `Audio.exe` | OBSERVED |
| Guidance ducking | `CApi_GuidanceVoiceMuteOn/Off` imports in `Audio.exe` | code patch (or MCU side — unknown) | HYPOTHESIS |
| iNai command set | handler table in `anwdrv.dll` sec0, cmd byte in `mov #N,r6` at each `jsr @r3` | code patch; not attempted | VERIFIED |
| SSI channel / DMA mapping | WaveSSI1 SSI1/ch12, WaveSSI2 SSI2/ch13 (M8.H46 registry) | registry / driver data edit | VERIFIED |
| Radio (`TNR2:`) on a US unit | EU `Audio.exe` only opens `TNR2:`; US NK1 starts `TNR3:`/`TNR4:` | use the US `Audio.exe` (M1.58/M1.59) | VERIFIED |

No patch was built for any row. The audio microcontroller's own firmware is
out of scope (task Stop), so a change below the SCI1: protocol cannot be made
from this repo.

## 6. Differences between builds

`cerom.py modules` on `archive/eu2014-256.img` (build A) prints `Audio.exe`
size **347648** against **228864** in EU2011: **+118784 B = +51.9 %**
(arithmetic quoted from the two printed sizes). The task hint "+54 %" was
approximate; 51.9 % is the measured value. `wavessi1.dll`/`wavessi2.dll`
(41984 B), `waveapi.dll` (95744 B) and `audevman.dll` (24576 B) are the same
size in 2014; build B `anwdrv.dll` (182784), `DspDrv.dll` (340992),
`BeepDrv.dll` (10240) and `MuteDrv.dll` (5120) are all the same size in 2014
as in 2011. This is a size comparison, not a full binary diff; the 2014 code
was not disassembled here.

## Reproduction

```bash
python3 tools/anw_msgs.py --selftest
python3 tools/anw_msgs.py archive/head256.img        # literals=98 mapped=80
python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img exports anwdrv.dll
python3 tools/sh4xref.py archive/head256.img anwdrv.dll --image-start 0x3e00200 --to 0x3b833d0
python3 tools/sh4xref.py archive/head256.img anwdrv.dll --image-start 0x3e00200 --to 0x3b833d1
python3 tools/anw_frames.py --selftest
python3 tools/cerom.py --image-start 0x200200 archive/eu2014-256.img modules | grep ' Audio.exe '
```
