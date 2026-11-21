# Camera path (`CameraCC.dll`, `SystemCC.dll`, `VIN.dll`, `navdrv.dll`)

Static map of the reversing-camera path in the 2011 head unit, EU build only
(`eu2011`, image `head256.img`, SHA-256 `92aa525d…a007f9`). One page per module
group (M1.41–M1.46), scope and method in
[`README.md`](README.md).

Short answer to the M1.44 question: the **trigger is the `navdrv.dll` event
`EVENT_NAV_SENSOR_BACK`**, latched from a bit of the navigation sensor word;
the VIN video-in IOCTLs (`IOCTL_VIN_SET_VIDEO_MUTE`, …) are sent by
**`SystemCC.dll`**, not by `CameraCC.dll`. `CameraCC.dll` is a COM/overlay
client of `SystemCC`; it opens no device and sends no IOCTL (negative control,
§3).

## 1. Modules

| Module | ROM | vbase (eu2011) | Code size | Role | Evidence |
| --- | --- | --- | --- | --- | --- |
| `CameraCC.dll` | A | `0x03550000` | sec0 `0x11800` B + 2 compressed data sections | COM camera UI/overlay client (`CameraCC.CameraCCIF` class, `CCCameraCtrlWindow`); window + IPC only | VERIFIED, `cerom.py sections`; strings `0x03551ee4`, `0x035525d4` |
| `SystemCC.dll` | A | `0x02a70000` | sec0 `0x1a000` B + 2 compressed | System services COM server; opens `VIN1:`/`CEN1:` and sends the VIN/CEN IOCTLs | VERIFIED, `cerom.py sections`; strings `0x02a73a30`, `0x02a73b90` |
| `VIN.dll` | B | `0x03950000` | sec0 `0x8a00` B + sec1/sec2 compressed | `VIN1:` device driver; exports `VIN_IOControl`, and its strings name the devices it drives: `VIN1:`, `LCD1:`, `CEN1:`, `GPI1:` | VERIFIED, `cerom.py exports VIN.dll`; strings `0x03952ac0`, `0x0395236c`, `0x03952ad4` |
| `navdrv.dll` | B | `0x039e0000` | sec0 `0x6c00` B + sec2 compressed | Navigation device driver; owns the sensor word decode and the `EVENT_NAV_SENSOR_BACK` notification | VERIFIED, exports `NAV_IOControl`; `0x039e13a0`, `0x039e2368` |

`CameraCC.dll` is a build-A user-mode COM DLL — `DllGetClassObject` is its only
real export (`cerom.py exports CameraCC.dll` = 4 ATL exports). It has no
`VIN`/`LCD`/`CEN`/`GPI` string at all (see §3) and no device-open call site.

## 2. Features

| Feature | What shows it | Status |
| --- | --- | --- |
| Reverse camera shown on the display | `CameraCC.dll` camera COM class + `MSG_PROCESS_CAMERA` / `MSG_QUEUE_CAMERA` IPC; `navdrv` sensor event | OBSERVED |
| Superimposed guide overlay on the video | `SystemCC` `IOCTL_VIN_SET_SUPERIMPOSE` on `VIN1:` | VERIFIED (code string) |
| Video mute / sync mode on the input | `IOCTL_VIN_SET_VIDEO_MUTE`, `IOCTL_VIN_SET_SYNC_MODE` | VERIFIED (code string) |
| Superimpose source / video size | `IOCTL_VIN_GET_VIDEO_MUTE`, `IOCTL_VIN_GET_SYNC_MODE`, `IOCTL_VIN_SET_VIDEO_SIZE` | VERIFIED (code string) |
| Rear-video input selector | `IOCTL_CEN_VSEL_CONTROL` on `CEN1:` (name `SetVideoSelector` in `VIN.dll`) | VERIFIED (code string) |
| Camera connected / status | `IOCTL_CEN_GET_CAMERA_STS` (`CConnectStatus::VtrStatusRenew`) | VERIFIED (code string) |
| PAL/NTSC switch of the input | `VIN_PAL_NTSC_CHANGE` (`0x02a784b0`, `SystemCC`; `0x03952ac0`, `VIN.dll`) | OBSERVED |

`CameraCC` is an ATL COM control (`CCCameraCtrlWindow` at `0x03551ee4`,
`CAMERA_CC_EVENT_TIMEOUT` at `0x035525d4`) that talks to the rest of the unit
over named IPC queues (`MSG_QUEUE_CAMERA`, `MSG_QUEUE_CAMERA_CC`) and the
process message `MSG_PROCESS_CAMERA`, which `SystemEXE.exe` also names
(`0x14b4dec`, `0x14b4e18`). It paints, it does not drive the video hardware.

## 3. Interfaces

### 3.1 Trigger: reverse signal

| Item | VA (eu2011) | Status |
| --- | --- | --- |
| Event name `EVENT_NAV_SENSOR_BACK` (UTF-16) | navdrv `0x039e13a0` | VERIFIED |
| Event object created in the driver init | navdrv `fn 0x039e3a34` (`mov.l` load at `0x039e3a80`; `CreateEventW` via `0x039e6db8` = COREDLL ordinal 495) | VERIFIED (disasm) |
| Event handle stored (object `+124`) and read by the getter | navdrv `fn 0x039e3cec`: case `+124` → `0x039e3d28` (`add #124,r4`; `0x039e3d2a` loads the release stub) | VERIFIED (disasm) |
| Sensor word source `and #7` of `*(*(obj+44))` | navdrv `fn 0x039e6a24` (`0x039e6a56`–`0x039e6a5e`) | OBSERVED |
| Sensor decode → event: bit 0 of the new word vs the previous | navdrv `fn 0x039e6690` (`xor r1,r3` then `and #1` at `0x039e669e–0x039e66a4`; `jmp 0x039e3cec` with `r5=6` at `0x039e66aa–0x039e66b2`) | VERIFIED (disasm) |
| Word split into driver fields (+16 = bit 1, +20 = bit 2, +18 = bit 0) | navdrv `fn 0x039e5f58` (`0x039e5f62`–`0x039e5f7c`) | VERIFIED (disasm) |
| Consumer hook registered | navdrv `fn 0x039e6a24` calls `0x039e6690` at `0x039e6aa8` | VERIFIED (disasm) |
| Sensor thread entry / exception string | string `Navi Driver SensorThread Exception!!` `0x039e2340`; thread creation in `fn 0x039e6b70` | OBSERVED |

**Reading.** The reverse/back signal reaches `navdrv.dll` as one bit of the
packed sensor word: `fn 0x039e6a24` copies `*(*(obj+44)) & 7` into the sensor
object (`0x039e6a5a`–`0x039e6a5e`), `fn 0x039e5f58` splits that word into bit 1
(`obj+16`), bit 2 (`obj+20`) and bit 0 (`obj+18`), and the consumer
`fn 0x039e6690` compares the new and previous word and, when bit 0 changed,
jumps into the event getter `fn 0x039e3cec` with `r5=6`. The event object
itself is created once in `fn 0x039e3a34`; its handle sits at object `+124` and
is what `fn 0x039e3cec` releases to user mode, which is how a client outside
the driver can observe the reverse state.

Which physical wire supplies bit 0 is **not** proven by this static read. The
driver's `GPI1:` strings are for the GPS antenna only
(`IOCTL_GPIO_ACCESS_GPS_ANT_ON`, `0x039e23a4`), not for the reverse input, so
"GPIO" is not supported by the readable code; CAN vs GPIO stays open.

### 3.2 VIN1: IOCTLs (sent by `SystemCC`, not `CameraCC`)

`VIN1:` is opened in `SystemCC` `fn 0x02a83028` (`mov.l r5 = 0x02a73a30`;
`CreateFileW` through the import at `0x02a85fe8`), with `CEN1:`
(`0x02a73b90`) opened by the same class (`fn 0x02a8316c`, and
`fn 0x02a88090` for `CConnectStatus`). Each IOCTL code below is a literal in a
small wrapper function's pool; the function names live in the matching error
string in sec0.

| IOCTL code | Name (error string in `SystemCC`) | Sender function (eu2011) | Status |
| --- | --- | --- | --- |
| `0x80062000` | `IOCTL_VIN_SET_VIDEO_MUTE` | `fn 0x02a82c40` (load `0x02a82c94`, pool `0x02a82ce0`) | VERIFIED |
| `0x80062004` | `IOCTL_VIN_GET_VIDEO_MUTE` | `fn 0x02a82eb4` (load `0x02a82ef0`, pool `0x02a82f54`) | VERIFIED |
| `0x80062008` | `IOCTL_VIN_SET_SYNC_MODE` | `fn 0x02a82cf0` (load `0x02a82d86`, pool `0x02a82dec`) | VERIFIED |
| `0x80062014` | `IOCTL_VIN_GET_SYNC_MODE` | `fn 0x02a82f78` (load `0x02a82fb4`, pool `0x02a83018`) | VERIFIED |
| `0x80062018` | `IOCTL_VIN_SET_SUPERIMPOSE` | `fn 0x02a82dfc` (load `0x02a82e54`, pool `0x02a82ea4`) | VERIFIED |
| `0x8006201c` | `IOCTL_VIN_SET_VIDEO_SIZE` | `fn 0x02a830c8` (load `0x02a8310a`, pool `0x02a8315c`) | VERIFIED |
| `0x800d2054` | `IOCTL_CEN_VSEL_CONTROL` (on `CEN1:`) | `fn 0x02a8316c` (load `0x02a8328e`, pool `0x02a832f8`) | VERIFIED |
| `0x800d2044` | `IOCTL_CEN_GET_CAMERA_STS` (on `CEN1:`) | `fn 0x02a88090` (load `0x02a8812c`, pool `0x02a881a0`) | VERIFIED |

Every wrapper is in the same `0x02a82c40–0x02a83300` block; the IOCTL code is
the pool word loaded into `r6` right before the `DeviceIoControl` call, and the
matching UTF-16 error string is in sec0 (`0x02a73780`, `0x02a73800`,
`0x02a7387c`, `0x02a7390c`, `0x02a7399a`, `0x02a73a6e`, `0x02a73b00`,
`0x02a78986`, plus `VIN_PAL_NTSC_CHANGE` at `0x02a784b0`, 9/9 found).
`CameraCC` has **none** of these strings and **none** of these codes (negative
control, §EXP). Two other modules carry some of the same literals —
`TestMode.exe` (`0x80062000`, `0x80062008`, factory test) and `Audio.exe`
(`0x8006201c`) — so `SystemCC` is the sender on the normal path, not the only
sender in the image.

A literal-pool scan (`tools/sh4literal.py find`) over every section of every
module gives `CameraCC` = 0 hits for all eight codes (8/8 lines
`referenced pool words 0`); `SystemCC` = 1 referenced pool word for each, and
`VIN.dll` = 1 for `0x800d2054` only.

`VIN.dll` itself does not carry the `VIN1:` IOCTL codes as literals anywhere in
the module — not in its `0x8a00`-byte sec0 and not in the decoded sec1
(`0x310` B) / sec2 (`0x9f0` B). Its own sec0 takes the opposite side of the
same protocol: `fn 0x039564c0`, whose pool word `0x039565a0` holds
`0x800d2054`, answers `IOCTL_CEN_VSEL_CONTROL`. The function's `r5` is an index
into the name table at `0x039531b4` (`,\0\x04\x0c\x10\x1c\x08*` =
`0,4,12,16,28,8,42`; name 1 = `ChangeDisplaySignal`), and at `0x0395656a` it
sends `r5=0x17` (23) with `r6=1` and `r7=11` through `0x0395684c` when the
selector call returns 0. Other `0x800…` literals in sec0 are
`0x800b2034/38/3c/6c/74/7c/9c`, `0x8009202c`, `0x80042000/08` and
`0x80004005`; none is a `0x80062xxx` VIN code, so the VIN dispatch tags are
built in the compressed sections or via a base+index table.

The device node is declared elsewhere: `AppLaunch.dll` load table holds
`\Drivers\Launch\VideoIn` and `VIN1:` (`file 0x4140534`), and the launch table
in `docs/format/firmware.md` row 56 lists `VideoIn`/`VIN.dll`/`VIN1`/`0xa`/
`id 0x23`.

### 3.3 CameraCC interfaces

| Item | VA (eu2011) | Status |
| --- | --- | --- |
| COM class `CameraCC.CameraCCIF` | CameraCC `0x03551ee4` (`CCCameraCtrlWindow`) / sec3 registry strings | VERIFIED |
| IPC queue `MSG_QUEUE_CAMERA` / `MSG_QUEUE_CAMERA_CC` | CameraCC `0x03552604`; `SystemEXE` `0x14b32d4` | VERIFIED |
| Process message `MSG_PROCESS_CAMERA` / `_CC` | `SystemEXE` `0x14b4dec`/`0x14b4e18`; queue ids in `SystemEXE` `0x14b32c0` block | VERIFIED |
| Event timeout constant | CameraCC `0x035525d4` (`CAMERA_CC_EVENT_TIMEOUT`) | VERIFIED |
| Device-open / IOCTL wrapper (`fn 0x0355fa30`, `0x0355fa64`) | referenced only from the object's own 5-instance literal tables (`0x035514e8` …); no `CreateFileW` on a device path | OBSERVED |
| `VIN1:` / `LCD1:` / `CEN1:` / `GPI1:` string in module | none (0 hits over sec0 + decoded sec1/sec2 + sec3) | VERIFIED (negative) |

`CameraCC`'s only `CreateFileW` caller is `fn 0x0355fe40`, which builds the path
`\StoreMgr\` (`0x035533d0`) and opens it — a storage path, not a device — then
uses `CreateFileW` on an empty name (`0x0355fe9e`). There is no device path in
the module, so the wrappers at `0x0355fa30`/`0x0355fa64` are template vtable
entries that this build never exercises on `VIN1:`.

## 4. Data

| Item | Where | Status |
| --- | --- | --- |
| `VIN1:` device name | `SystemCC` `0x02a73a30`; `AppLaunch.dll` `file 0x4140534` | VERIFIED |
| `CEN1:` device name | `SystemCC` `0x02a73b90`; `VIN.dll` `0x03952ada` | VERIFIED |
| `LCD1:` device name | `VIN.dll` `0x0395236c` | VERIFIED |
| `GPI1:` device name | `VIN.dll` `0x03952ad4` (GPS antenna only) | VERIFIED |
| `VIN_PAL_NTSC_CHANGE` | `SystemCC` `0x02a784b0` (pool ref `0x02a87d3c`, loader `0x02a87cae`); `VIN.dll` `0x03952ac0` | VERIFIED |
| Reverse event object | kernel event named `EVENT_NAV_SENSOR_BACK` (`navdrv` `0x039e13a0`) | VERIFIED |
| Sensor word | `navdrv` sensor object `+20`; split fields at `+16`/`+18`/`+20` of the driver object | VERIFIED (disasm) |
| Registry / files | none found in `CameraCC`/`VIN.dll` (only `\StoreMgr\` in `CameraCC`) | VERIFIED (negative) |

No registry key or file under `CameraCC`/`VIN.dll` carries camera settings; the
camera state is transient (RAM object in `navdrv` + IPC messages).

## 5. What could be changed

| Change | Mechanism | Needs | Status |
| --- | --- | --- | --- |
| Show the camera image without reverse | force `EVENT_NAV_SENSOR_BACK` / call the `VIN1:` enable path | code patch of the `navdrv` sensor decode (`0x039e6690`) **or** a client that issues the `0x80062000`/`0x80062018` pair | HYPOTHESIS |
| Change guide-line overlay on/off | `IOCTL_VIN_SET_SUPERIMPOSE` (`0x80062018`) argument | data/IOCTL value; sender is `SystemCC fn 0x02a82dfc` | VERIFIED (code), value UNKNOWN |
| Change video size | `IOCTL_VIN_SET_VIDEO_SIZE` (`0x8006201c`) | argument in `fn 0x02a830c8` | VERIFIED (code), value UNKNOWN |
| Change PAL/NTSC | `VIN_PAL_NTSC_CHANGE` (`0x02a784b0`), `fn 0x02a87c54` | constant `0x02a784d8`/`0x02a784b0` in `fn 0x02a87c54` | OBSERVED |
| Replace `CameraCC` UI | COM class `CameraCC.CameraCCIF`, IPC `MSG_QUEUE_CAMERA` | new COM server that speaks `MSG_PROCESS_CAMERA(_CC)` | HYPOTHESIS |

The reverse trigger is the cheapest lever for "camera on demand": a
`SetEvent`-equivalent to `EVENT_NAV_SENSOR_BACK`, or a call into the same
`VIN1:` enable sequence `SystemCC` uses, would present the image without the
gear signal. Both stay untested (static only, no car).

## 6. Differences between builds

Not covered here: M1.37 (build differences) has not produced a camera row yet.
The US 2011 image (`us256.img`, SHA-256 `70d945d8…6a04da`) shares the path:
`EVENT_NAV_SENSOR_BACK` is at `navdrv.dll` va `0x039e13a0` (`file 0x42605a0`),
`VIN1:`/`IOCTL_VIN_SET_VIDEO_MUTE`/`IOCTL_CEN_GET_CAMERA_STS` are in
`SystemCC.dll` sec0 (`file 0x1508c30`, `0x1508980`, `0x150db86`; va
`0x02a43a30`, `0x02a43780`, `0x02a48986`), the `SystemCC` wrappers still take
their codes from pool words (`sh4literal find` → 1 referenced pool word each),
and the six literals `0x80062000`/`0x80062008`/`0x8006201c`/`0x800d2054`/
`0x800d2044` are present in the image. A full per-build comparison is open
(HYPOTHESIS).
