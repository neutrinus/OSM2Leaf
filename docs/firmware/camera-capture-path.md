# Reversing-camera capture path: static verdict (M8.H61)

Static map of how the reversing-camera image reaches the display in the 2011
head unit, EU2011 build only (`head256.img`, SHA-256
`92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`).
Companion to [`camera.md`](camera.md), which maps the trigger and the `VIN1:`
IOCTLs; this page answers one question: **is a static test picture on reverse a
plane switch plus a frame-buffer fill, or does the path need a video-capture
model?** Evidence: `docs/experiments/EXP-2026-11-24-M8.H61-camera-capture-path.md`
(claims C-7580–C-7589). No QEMU patch, no video decoder modelling.

## Verdict

**B — needs a video-capture model.** The `VIN1:` interface (`VIN.dll`) is a
video-input *manager*: its IOCTLs select the input, set the overlay, mute the
video and set its size; its display side is a DirectDraw overlay surface into
which the captured frames are placed. A plane switch alone cannot supply camera
pixels, because nothing in the readable code copies a camera frame into a DU
plane buffer — the pixels arrive on a separate video-input path that reaches
the SoC (C-7584). The capture peripheral's **register list is UNKNOWN**: no
physical capture/DU register block is programmed in the readable sections of
`VIN.dll` (negative, C-7586), and the driver reaches the hardware only through
`DeviceIoControl` on `LCD1:`/`CEN1:`/`GPI1:` (C-7585).

Consequently, "patch a test image into a DU plane and flip a bit on reverse"
is **not** a supported mechanism here: it would bypass the capture path rather
than exercise it. A test picture on reverse requires modelling the video-input
capture (input selector + frame source + overlay compositing), which is out of
scope for this task (Stop: no video decoder model).

## 1. Reverse trigger (positive control)

The reverse signal is bit 0 of the packed nav sensor word, decoded in build-B
`navdrv.dll`:

| Item | VA (eu2011) | Evidence |
| --- | --- | --- |
| Event name `EVENT_NAV_SENSOR_BACK` | navdrv `0x039e13a0` | VERIFIED (`ce_strfind` 1 hit) |
| Sensor decode: new word XOR old word, `and #1`, jump to event getter with `r5=6`, `r6=1` | navdrv `fn 0x039e6690` (`0x039e669e–0x039e66b2`) | VERIFIED (`nk_decomp pdata` START, `sh4dis` LE) |
| Event getter / handle at object `+124` | navdrv `fn 0x039e3cec` | VERIFIED (`camera.md` §3.1) |

Falsifier check: the reverse bit does change the display path in principle —
it raises the kernel event that `SystemCC.dll` consumes to issue the `VIN1:`
IOCTL pair. Whether that consumer runs on `-M ze0` was not exercised (static
only, no L4 run). The camera-module side of the trigger is unchanged from
`camera.md`: `CameraCC.dll` opens no device and sends no IOCTL (negative
control, 0 device-string hits).

## 2. VIN.dll: the video-input manager

`VIN.dll` (build B, vbase `0x03950000`, image-start `0x3e00200`) sections:

| Section | VA | Size | Kind |
| --- | --- | --- | --- |
| sec0 | `0x03951000` | `0x881f` B (`psize 0x8a00`) | executable |
| sec1 (decoded) | `0x01f2e000` | `0xf40` B (`psize 0x214`) | compressed data (INIT bytes) |
| sec2 (decoded) | `0x0395b000` | `0x9f0` B (`psize 0x432`) | compressed data (INIT bytes) |

Exports include `VIN_IOControl` (rva `0x00003f24`, VA `0x03953f24`, pdata
START, length `0x68`). Its dispatch subtracts `0x80062000` from the incoming
IOCTL code (`add r1=0x7ff9e000`), bounds it to `0x68`, and uses a byte-indexed
jump table at `0x03951aac` — i.e. the VIN IOCTL codes are **built from a base
plus an index**, which is why they do not appear as literals in the binary.

The sec0 UTF-16 strings name the classes the manager instantiates and the
display operations it performs:

| String | VA (eu2011) | Meaning |
| --- | --- | --- |
| `IOCTL_VIN_SET_CAMERA_MODE_ON : PARAMETER_ERROR` | `0x03951750` | camera-mode ON is a distinct VIN IOCTL |
| `VIN: CVideoMute SetVideoMuteSh(Layer_4,VIN_VIDEO_MUTE_OFF) ERROR` | `0x03952588` | mute is operated on display **layer 4** |
| `VIN: CVideoSize CreateFile(LCD) [ERROR %d]` | `0x03952310` | video size via `LCD1:` |
| `VIN: CVideoMode CreateFile LCD/CEN/GPIO [ERROR %d]` | `0x03952970`/`0x039529c8`/`0x03952a18` | input mode via `LCD1:`, `CEN1:`, `GPI1:` |
| `VIN_PAL_NTSC_CHANGE` | `0x03952ac0` | input standard change |
| `VIN: CChangeSync CreateDisplaySurface ERROR` | `0x03952e98` | creates a DirectDraw surface |
| `VIN: CChangeSync DDCreateSurface [OverLay] ERROR(%x)` | `0x03953048` | the surface is a hardware **overlay** |
| `VIN: CChangeSync DrawSurf ERROR` | `0x03953000` | frames are drawn into that surface |
| `VIN: DDBeginTransaction/DDWaitForTransactionDone/DDEndTransaction ERROR` | `0x03953158`/`0x039530b8`/`0x03953110` | surface updates are transactions |

Each string has exactly one referenced pool word that points back to its
handler (e.g. `0x03951750` → `fn 0x03954180`; `0x03952588` → `fn 0x03955370`;
`0x03952e98` → `fn 0x03955ee8`; `0x03953048` → `fn 0x039561bc`), so these are
code paths, not orphan strings.

The capture input selector is answered by the same driver on `CEN1:`:
`fn 0x039564c0` owns literal `0x800d2054` (`IOCTL_CEN_VSEL_CONTROL`, pool word
`0x039565a0`) and builds a 7/8-entry selector table at `0x039531b4`, with
names from `VIN.dll`'s `ChangeDisplaySignal` group. This is the rear-video
input selector named in `camera.md` §3.2.

## 3. Why this is not a plane switch

A "simple plane switch + frame buffer" verdict would need (a) a DU plane that
holds a static image and (b) code that fills that plane from the reverse event.
The DU planes exist (phys `0x1ff80000`, plane `n` at `+0x100*n`,
`tools/ze0_screenshot.py`), but:

- `VIN.dll` does **not** address the DU plane registers or any capture /
  graphics physical block. `sh4literal find` reports 0 referenced and 0
  unreferenced occurrences of `0x1ff80000`, `0xffe80000`, `0xfff80000`,
  `0x19a00000`, `0x10000000` and `0x0e600000` in all three sections (sec0 and
  both decoded compressed sections). The decoded sec1/sec2 contain no
  physical address word in the `0x08000000`–`0xffffffff` range.
- Its only hardware access is via imports: `COREDLL`/`COMMONDLL` ordinals plus
  `CEDDK.dll` #8/#9 (no named `MmMapIoSpace`/`HalTranslateBusAddress`).
  Device access is `CreateFileW`/`DeviceIoControl` on `LCD1:`, `CEN1:`,
  `GPI1:` — all named as error strings, not direct register writes.
- The display side is a DirectDraw **overlay surface** (`DDCreateSurface
  [OverLay]`, `DrawSurf`, `DDBegin/EndTransaction`) on layer 4 — the video
  path composes the captured image into an overlay, not into a CPU-written
  frame buffer.

Therefore the camera pixels arrive through a video-input path that this
static read cannot reduce to a plane register write. The register list of that
capture path is not recovered: this is a stated UNKNOWN, not a guess. The
physical address map (`docs/research/full-system-emulation.md` §physical
memory) has no named capture block; `0x19a00000` (`Bolero`) and the graphics
area at `0x10000000` are HYPOTHESIS roles, not evidence of camera registers.

## 4. Honest limits

- Static read only, build EU2011. No L4 run changed the reverse signal, so the
  "reverse → consumer issues the IOCTL pair" step is inferred from the event
  path and `camera.md` §3.1, not observed on screen.
- `ce_strfind.py` marks VIN.dll sec1/sec2 `UNSUPPORTED`; all string claims in
  §2 are from sec0, and the compressed sections were decoded with
  `nk_decomp.py section` before the physical-address search (so the negative
  in §3 is a measured zero over all readable bytes, not a "compressed" excuse).
- The capture peripheral's register list remains an open item (new task), and
  no video decoder was modelled, per Stop.

## Claims

C-7580–C-7589 (see `docs/research/claims.md`).
