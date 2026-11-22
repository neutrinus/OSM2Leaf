# Touch input path (EU2011: `lcddrv.dll` → `kepdrv.dll` → AUI messages)

Static map of the touch path in the 2011 head unit, EU build (`eu2011`, image
`archive/head256.img`, full SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`,
first 128 MiB `d3e5eac9cb5b4cbdf2618e686fb3ed1b273d3c6b75753cfc14f31d35c79fd9be`).
Task M8.H36; method, commands and controls in
[`EXP-2026-11-22-M8.H36-touch-path`](../experiments/EXP-2026-11-22-M8.H36-touch-path.md).

**Short answer.** The unit does **not** use the CE `TouchPanel` DDI path.
Touch samples come from the **display unit over `SCI3:`** as serial frames,
are decoded by **`lcddrv.dll` (B)** into a 6-byte record, published through
`LCD1:` IOCTL `0x800b205c` plus the named event `EVENT_LCD_TOUCH_KEY`, and are
consumed by **`kepdrv.dll` (B)**, which posts ordinary Windows CE mouse
messages to the UI window: `WM_MOUSEMOVE`/`WM_LBUTTONDOWN`/`WM_LBUTTONUP`
(`0x0200`/`0x0201`/`0x0202`) with `x` in the low 16 bits and `y` in the high
16 bits of `lParam`. The sample coordinates are 16-bit values, clamped to
`x ≤ 800`, `y ≤ 480`, normalised to `0..65535`, Y-flipped and scaled back by
default factors `800`/`480` into screen pixels. This decides row **M8.C20**:
the candidate "display-unit frames on `SCI3:`" is true; "ADC behind
`kepdrv`" and "CE touch driver" are false for this build; the audio
microcontroller carries keys, not touch.

All addresses below are build B unless marked "A"; eu2011 module VA bases come
from `tools/cerom.py`, never from fitted deltas.

## 1. Modules

| Module | ROM | vbase | Role | Evidence |
| --- | --- | --- | --- | --- |
| `lcddrv.dll` | B | `0x03a00000` | `LCD1:` stream driver; owns `SCI3:`, decodes display-unit frames, raises the touch/key events | VERIFIED — `cerom.py sections lcddrv.dll`, strings `0x03a018d0` (`EVENT_LCD_TOUCH_KEY`), `0x03a0275a` (`SCIF3RcvThread`) |
| `kepdrv.dll` | B | `0x03a11000` | Key/touch aggregator; opens `LCD1:`, waits for the event, injects mouse/key messages into the UI | VERIFIED — strings `0x03a13be4` (`LCD1:`), `0x03a12ff8` (`EVENT_LCD_TOUCH_KEY`), `0x03a1363e` (`IOCTL_LCD_GET_TOUCH`) |
| `gwes.exe` | A | `0x00010000` | Contains the stock CE TouchPanel API names and `touch.dll`, but the driver is not configured (§5) | VERIFIED — `ce_strfind` hits at `0x00011ede`, `0x000120f0` |
| `DiagnosisCC.dll` | A | `0x03200000` | Calibration UI: sends `IOCTL_LCD_CALIBRATION_POINT` / `IOCTL_LCD_GET_CALIBRATION_STS` to `LCD1:` | VERIFIED — strings `0x03209ac4`, `0x03209eac` |
| `auiapp.exe` / `auirtdll.dll` | A/B | — | Consumers of the posted mouse messages; no touch-specific code was needed in them | OBSERVED — `PostMessageW` target HWND is stored in the `kepdrv` object (§4) |

## 2. The chain, with VAs

```
SCI3: (display unit)
  └─ lcddrv.dll  Scif3RcvThread                         (string 0x03a0275a)
     └─ RcvAnalysisData  fn 0x03a0664c                  (command dispatch at 0x03a0667a)
        └─ 6-byte payload copied from frame +0x113 to driver state +0x4be (0x03a066c0–0x03a066ee)
           ├─ named event EVENT_LCD_TOUCH_KEY created in fn 0x03a0467c (string 0x03a018d0)
           └─ LCD1: IOControl fn 0x03a04188, code 0x800b205c (literal 0x03a043c4)
              └─ kepdrv.dll LcdTouchDataMain fn 0x03a19150
                 ├─ CreateFileW("LCD1:") in fn 0x03a19748 (string 0x03a13be4)
                 ├─ IOCTL 0x800b205c → 6-byte output buffer (literal 0x03a191f8)
                 └─ WaitForSingleObject(EVENT_LCD_TOUCH_KEY) at 0x03a191bc
                    └─ InputLcdTouch fn 0x03a184e4
                       └─ NotifyTouchData fn 0x03a17d2c (type 2 = touch)
                          └─ NotifyKeyTouchCommon fn 0x03a17450
                             ├─ calibration defaults 800/480 at 0x03a17490–0x03a1749c
                             ├─ normalise + Y-flip fn 0x03a160dc (clamps 0x0320/0x01e0 at 0x03a16100/0x03a1610a)
                             └─ PostMessageW pump fn 0x03a17020
                                └─ COREDLL!PostMessageW thunk 0x03a1b154 (IAT 0x01f4204c)
                                   → AUI window handle stored at kepdrv object +0x64
```

`LCD1:` is loaded by `device.exe`: registry `Drivers\Launch\LCD` → `lcddrv.dll`
(`tools/ce_drivers.py archive/head256.img --image-start 0x3e00200 --markdown`).
`EVENT_LCD_TOUCH_KEY` is created **twice with the same name** — once by the
driver (`lcddrv.dll`) and once by its consumer (`kepdrv.dll`, fn `0x03a187bc`),
which is the standard CE way for a user-mode client to open the driver's event.

## 3. Wire / register format of one sample

### 3.1 On `SCI3:`

`lcddrv.dll` runs `Scif3RcvThread` (`0x03a0275a`) over `SCI3:` opened with
`CreateFileW` (string `SCI3:` at `0x03a02706` area), with `ReadFile`,
`WaitCommEvent`, `PurgeComm` and `ClearCommError` imported from COREDLL.
Frames are dispatched by a command byte at driver-state offset `0x1a0`
(`fn 0x03a0664c`, `mov.b @(r0+0x1a0)` at `0x03a0665c`–`0x03a0666a`); the
touch branch copies six payload bytes from frame offset `0x113` into driver
state at `0x4be` (`0x03a066c0`–`0x03a066ee`). The full SCI3 frame grammar
(preamble, length, checksum) is **not** reconstructed here — `M8.H35` owns
`lcddrv.dll`'s serial protocol. What M8.H36 needs is the decoded record below.

### 3.2 Decoded record returned by `IOCTL_LCD_GET_TOUCH` (`0x800b205c`)

`kepdrv.dll` passes a **6-byte output buffer** to `DeviceIoControl`
(`0x03a19184`–`0x03a19192`: `nOutBufferSize = 6`). `InputLcdTouch` reads it as:

| Offset | Type | Meaning | Evidence |
| --- | --- | --- | --- |
| `+0` | `u16` | raw x | `mov.w @r8,r3` at `0x03a18500`, logged at `0x03a184fe` |
| `+2` | `u16` | raw y | `mov.w @(2,r8),r0` at `0x03a184fa` |
| `+4` | `u8` | status, **ASCII** `0x30` = release, `0x31` = press | compares `#48`/`#49` at `0x03a18512`/`0x03a1851e`; other values take the error branch `0x03a18558` |
| `+5` | `u8` | unused by `InputLcdTouch` | no read of `+5` in `fn 0x03a184e4` |

The log format string is `KEPV:InputLcdTouch: x(%d) y(%d) STS=0x%x`
(`0x03a12cdd`), so a sample is observable on the debug serial as
`x(123) y(456) STS=0x31`.

## 4. Coordinate mapping and press/release/drag semantics

| Step | VA (eu2011) | Operation |
| --- | --- | --- |
| Clamp | `fn 0x03a160dc`, `0x03a16100`/`0x03a1610a` | `x = min(x, 0x0320)` (800), `y = min(y, 0x01e0)` (480) |
| Normalise | `0x03a16116`–`0x03a16132`, `0x03a16134`–`0x03a16150` | multiply by reciprocal constants `0x51eb851f` (x) and `0x88888889` (y − 480) and shift → 16.16 values in `0..65535`; the subtraction of 480 flips Y (panel origin bottom-left → screen origin top-left) |
| Scale to pixels | `fn 0x03a17020`, `0x03a17082`–`0x03a170a8` | when flags bit `0x8000` is set: `x_px = (norm_x * scale_x) >> 16`, `y_px = (norm_y * scale_y) >> 16` |
| Default scales | `fn 0x03a17450`, `0x03a17490`–`0x03a1749c` | if either factor is zero, set `scale_x = 0x0320` (800) and `scale_y = 120 << 2 = 480` |
| Pack | `fn 0x03a17020`, `0x03a170b6`–`0x03a170be` | `lParam = (y_px << 16) | x_px` |
| Message | `0x03a170d2` / `0x03a170f8` / `0x03a1711c` | `0x0200` `WM_MOUSEMOVE` (no button bits), `0x0201` `WM_LBUTTONDOWN` (flags `0x8002`), `0x0202` `WM_LBUTTONUP` (`0x8004`) |

`InputLcdTouch` maps status `'1'` → boolean 1 and `'0'` → 0
(`0x03a18512`–`0x03a18522`); `NotifyKeyTouchCommon` turns that into flags
`0x8002` (press) / `0x8004` (release) / `0x8001` (move) at
`0x03a174aa`–`0x03a174d2`. A drag is therefore *down → one or more moves →
up*; there is no separate drag frame. `PostMessageW` goes to the HWND held at
`kepdrv` object `+0x64` (`0x03a17048`–`0x03a1704c`), i.e. the AUI window
registered at start-up.

## 5. Calibration and the rejected CE path

- Calibration is a **display-unit handshake**, not a GWES touch calibration.
  `DiagnosisCC.dll` (A) opens `LCD1:` and uses `IOCTL_LCD_CALIBRATION_POINT`
  (`0x03209ac4`) and `IOCTL_LCD_GET_CALIBRATION_STS` (`0x03209eac`), and waits
  for `RCV_CALIBRATION_RESPONCE` / `EVENT_CALIB_REVINIT_END`, both created by
  `lcddrv.dll` (strings `0x03a01a8c`, `0x03a019b8`). The prompt sample format
  and the three point texts (`start`, `point`, `end`, `cancel`, `init`) are at
  `0x03209d0e`–`0x03209e2e`.
- `gwes.exe` (A/B) contains the stock strings `HARDWARE\DEVICEMAP\TOUCH`,
  `CalibrationData`, `TouchPanel*`, `touch.dll` (`0x00011ede`–`0x000120f0`),
  and `fn 0x00022cf0` loads `touch.dll`, but the loaded registry (`boot.hv`,
  `default.hv`, `user.hv`, 516 keys / 1,149 values in `default.hv`) has **no**
  `HARDWARE\DEVICEMAP\TOUCH` key (only `HARDWARE\DEVICEMAP\KEYBD` with
  `kbdmouse.dll`), and no module or file named `touch.dll` exists in builds A,
  B or C. Only `System\GWE\ThreadPriorities\TouchCalibrate = 0xa0`
  (`default.hv`) mentions touch. This path is present as code but unconfigured
  — a negative control for the "CE touch driver" candidate.
- `Drivers\HID\...\Mouse` → `MOUHID.DLL` exists for USB HID mice, but no HID
  touch-digitizer client is loaded; the `USBHID.DLL` rows are for keyboards,
  consumers and mice.

## 6. Cheapest injection point for an emulator

| Level | What to drive | Evidence | Use |
| --- | --- | --- | --- |
| **Message (cheapest)** | `PostMessageW(HWND, 0x0200/0x0201/0x0202, 0, (y<<16)|x)` into the AUI window; normalised coordinates already map to 800×480 | `fn 0x03a17020` + `fn 0x03a17450` | M8.H39 can change the screen without any serial/device model, once the AUI HWND is known (gdb/QMP breakpoint on `0x03a1b154` to read it) |
| **Device** | `lcddrv.dll` state at `+0x4be` (6 bytes) + set `EVENT_LCD_TOUCH_KEY`; or call `kepdrv` `fn 0x03a184e4` with the 6-byte struct | `fn 0x03a04188`, `0x03a19150` | M8.H38 `panel.py` behind `sci3` (M8.H1) |
| **Wire** | `SCI3:` frame whose payload byte block at `+0x113` holds the 6-byte record; command byte at `+0x1a0` | `fn 0x03a0664c` | full fidelity; needs M8.H35's frame grammar first |

## 7. What is still unknown

- The SCI3 frame's preamble/length/checksum and the command number for the
  touch payload — M8.H35.
- Where the calibration factors initially come from (display-unit reply vs
  stored flash/registry). The code only shows the defaults 800/480 and the
  `0x8000` "use calibration" flag; the runtime source is not in the ROM.
- Whether `lcddrv` state offset `+0x4be` is the *only* copy of the touch record
  (the copy at `0x03a066c0` is strongly implied by the IOCTL size and field
  layout, but no single instruction was traced from `+0x4be` to the IOCTL
  output buffer).
- No L3/L4 run was done: this is a static reader task (rule 13). Injection at
  L4 is M8.H39.
