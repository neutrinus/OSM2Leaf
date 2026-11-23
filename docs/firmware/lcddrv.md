# `lcddrv.dll`: the display-unit link on `SCI3:` (M8.H35)

The head unit talks to its display unit over `SCI3:` besides the video
signal. This page gives the frame grammar, the start-up handshake and the
commands that carry touch and keys, read from the unit's own kernel image
(NK1, `firmware/unit-flash/nk1-QY7200ND.bin`, `lcddrv.dll` vbase
`0x03d10000`) and confirmed by running it under `-M ze0` against the host
peer `tools/ze0_peers/panel.py --sci3`. EU2011 build B has the same code at
vbase `0x03a00000` (the touch.md addresses such as `RcvAnalysisData` at
`0x03a0664c` are the NK1 addresses minus `0x310000`).

Record: [`EXP-2026-11-22-M8.H35-sci3-display-link`](../experiments/EXP-2026-11-22-M8.H35-sci3-display-link.md),
claims C-7320–C-7329 and C-8440–C-8449.

## 1. Frame grammar

The framing is the iNai framing of `anwdrv.dll` (`tools/anw_frames.py`):

```
10 02 | message, every 0x10 doubled | 10 03 | BCC
```

BCC is the XOR of the stuffed message plus `10 03`. Two-byte control
sequences stand alone between frames: `10 06` = ACK, `10 15` = NAK. The
driver ACKs every valid frame it receives and expects an ACK for every
frame it sends. The first message byte is the command.

Example (the touch press at 400,240 used in the EXP):
`10 02 51 01 90 00 f0 31 10 03 12`.

## 2. Start-up handshake

The link state is a phase byte at driver state `+0x448`; the event handler
at `0x03d15aa0` dispatches it to one of three functions.

| Phase | Handler | Driver sends | Display answers | Result |
| --- | --- | --- | --- | --- |
| 0 | `0x03d1522c` | `23` | ACK, then a `24` frame (14 bytes: `24` + 13 bytes; zeros are accepted) | phase 1 |
| 1 | `0x03d15288` | `25` | ACK | `LCD: Error history registration [SYS_DIAGLOG_F_DISP_CNCT(SYS_DIAGLOG_REG_OK) ACC-ON]`; the driver then sends `71` and `42 31 31 31 09 31` |
| 2 | `0x03d153a4` | `71` about once per guest second | ACK, then a `71` frame | link up; a `24` frame in this phase restarts the handshake |

Without answers the driver logs `ERR_MDL_LCD` errors and repeats `23`.

## 3. Commands from the display unit

`RcvAnalysisData` (`0x03d1664c`) takes the command at state `+0x110` and
the payload from `+0x111`; the switch table at `0x03d1320e` holds signed
byte offsets from `0x03d16688`.

| Command | Case | Meaning |
| --- | --- | --- |
| `06` | `0x03d16688` | ACK |
| `15` | `0x03d166b0` | NAK |
| `24` | `0x03d166c0` | identity (phase 0) / reconnect (phase 2) |
| `42` | `0x03d166f4` | not decoded |
| `43` | `0x03d16716` | not decoded |
| `34`, `36`, `37`, `3f` | `0x03d167a6` | **key** (§3.2) |
| `51` | `0x03d167ac` | **touch** (§3.1) |
| `53`, `54`, `55`, `70`, `78`, `79`–`7b`, `7d`, `82`–`84`, `41` | `0x03d167b2` … `0x03d16840` | not decoded |
| `71` | `0x03d167ec` | poll answer |
| anything else | `0x03d16844` | ignored |

### 3.1 Touch: `51 xh xl yh yl st`

The function at `0x03d16300` puts the sample in the first free slot of a
ten-entry queue (11 bytes per slot at state `+0x4dc`, type 2 = touch) and
signals `EVENT_LCD_TOUCH_KEY` through `0x03d15538`. `x` and `y` are
big-endian 16-bit values; `st` is ASCII `'1'` (press) or `'0'` (release).
The `IOCTL_LCD_GET_TOUCH` (`0x800b205c`) handler at `0x03d17258` returns
them as the 6-byte little-endian record of
[`touch.md`](touch.md) §3.2. A drag is a press, more presses at new
coordinates, then a release.

### 3.2 Keys: `34`/`3f` + 1 byte, `36` + 4 bytes, `37`

The function at `0x03d161dc` queues type 1 slots: the command byte, then
for `34`/`3f` one payload byte, for `36` four, for `37` none. Which byte is
which hard key is not decoded (`kepdrv.dll` `InputLcdKey`, see
[`keys.md`](keys.md)).

## 4. Rules a peer must keep

- Answer at once. Under `-icount` host delays become arbitrary guest time.
- Keep the backlog small. The receive thread copies one read of up to
  `0x80` bytes and records every frame and every lone ACK of it in a table
  of 20 entries of 32 bytes at state `+0x1b4`. The table ends at `+0x434`,
  which holds the pointer to the link object. More than 20 items in one
  read overwrite it, and both `Scif3RcvThread` and `TimerThread` fault at
  `0x03d18602` / `0x03d18708`. Seen when the emulated DMA reported a
  wrong write position (fixed in `ze0-h02`); a peer that floods ACKs
  can cause the same.

## 5. What happens upward

`kepdrv.dll` (NK1 vbase `0x03d20000`) waits for the event, reads the
record and calls `InputLcdTouch` (`0x03d284e4`), then
`NotifyKeyTouchCommon` (`0x03d27d2c`, `SwType` 2). On the running NK1 + A
system that call stops in `IsKeyControlNotify` (`0x03d27344`). For touch
it ORs the key-control bytes at kepdrv object `+0xc4`/`+0xc5` and masks
`0x0f`; a nonzero value drops the press (the firmware's log line for this
branch is `m_byKeyControl & KEP_KEY_TOUCH_ENABLE(ON)`). The release then
stops in `CheckKeyStatus` (`0x03d27a7c`) because no press was recorded.
The key-control bytes are written by the application side; while the UI
stays in `INI_STARTUP` touch is locked. Which process writes them, and
when, is the next step (M8.H39). Evidence: breakpoint hits in the EXP.
