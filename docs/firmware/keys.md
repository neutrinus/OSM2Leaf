# Hard keys: where they arrive and what code the UI reads

> Evidence convention: **VERIFIED** = reproduced from the sample with the
> command shown; **OBSERVED** = seen in firmware but not executed; manual
> wording is marked as such and is never used as a raw code. Claims
> C-7340–C-7349; record
> [`EXP-2026-11-22-M8.H37-keys`](../experiments/EXP-2026-11-22-M8.H37-keys.md).
> Static, EU 2011 (`archive/head256.img`, SHA-256
> `d3e5eac9cb5b4cbdf2618e686fb3ed1b273d3c6b75753cfc14f31d35c79fd9be`),
> build B (kernel) image start `0x3e00200`. No L3/L4/L5 run: this is a
> static map of the dispatch, not an executed injection (rule 13).

All addresses below come from `python3 tools/cerom.py --image-start 0x3e00200
archive/head256.img modules` / `sections` / `extract` / `decompress`; none are
fitted deltas. SH-4 code is little-endian (`tools/sh4dis.py`).

## The short answer

> The navigation hard keys arrive as **serial frames from the display unit on
> `SCI3:`** (opened by `lcddrv.dll`) and as **frames from the audio micom on
> `SCI1:`** (opened by `anwdrv.dll`). Both are collected by **`kepdrv.dll`**
> (the "Key Pitcher" driver), which translates a `(KeyType, HardKeyCode)` pair
> into a Windows-CE virtual key through a `{u8 raw, u8 vk}` table, then posts
> `WM_KEYDOWN`/`WM_KEYUP` with `keybd_event`. Steering-wheel switches arrive as
> CAN `PUSH_SW` messages on `CAN1:`; the GPIO matrix is scanned inside
> `kepdrv.dll`. The table block is the initialised bytes of the compressed
> sec1 of `kepdrv.dll` at `0x01f42000` (648 B init, SHA-256
> `1084ed206bf41405138c58d010e68e2c01ee54fbc6b21828ffb28df211fc31fc`).

## 1. Where each source enters (one row per source)

| Key group ("name") | Physical source | Driver that receives it | Entry function (VA) | Status |
| --- | --- | --- | --- | --- |
| MAP, MENU, DEST, ZOOM, DAY/NIGHT (display-unit hard keys) | display unit, serial `SCI3:` | `lcddrv.dll`, module load `0x88621000`, `SCI3:` string VA `0x03a0272c`; `CLcdDrv::HardRemoconKey_notice` string VA `0x03a02bc8` | `kepdrv.dll` `KEPV:InputLcdKey` **0x03a18210**, fed by `KEPI:LcdKeyDataMain` **0x03a19080** via `IOCTL_LCD_GET_KEY` | source VERIFIED, key names OBSERVED (owner's-manual wording) |
| AUDIO / volume / source keys | audio micom, serial `SCI1:` | `anwdrv.dll`, module load `0x884c4000`, `SCI1:` string VA `0x03b890f8`; `RCV_FLAP_KEY_STATUS` event VA `0x03b82d68` | `kepdrv.dll` `KEPV:NotifyAudioCpuKey` **0x03a15fbc**, created through `AUD1:` (`KEPV:CreateAudioNetDrvObj`) | source VERIFIED, key names OBSERVED |
| Steering-wheel switches | vehicle CAN, `CAN1:` (`PUSH_SW` message) | `kepdrv.dll` `KEPI:McanReadMain`, `KEPV:InputCanData` string VA `0x03a12a68` | `KEPV:InputCanData` **0x03a17f94**, `KEPV:InputStconKey` **0x03a17f24** | source VERIFIED ("STCON"/steering in strings), per-key codes UNKNOWN |
| front-panel GPIO matrix (if any keys are hard-wired) | GPIO scan inside the key pitcher | `kepdrv.dll` `KEPV:GetMatrixKey` strings VA `0x03a11608`/`0x03a11634` | `KEPV:GetMatrixKey` **0x03a15f40**, matrix pointer installed at object `+0x8c` by fn **0x03a15d60** | code VERIFIED, which physical switches feed it UNKNOWN |

The `SCI3:` opener is reported in
[`docs/hardware/head-unit.md`](../hardware/head-unit.md) (port table); this
task starts there rather than from a guessed key string. `SCI1:` is the
audio-microcontroller link in the same table.

## 2. How a code reaches the UI

| Step | Function (VA) | What it does | Evidence |
| --- | --- | --- | --- |
| frame → key | `KEPV:InputLcdKey` **0x03a18210** | reads `byCmd` = packet byte 0 and params `[0..3]`; switch on `0x34`, `0x36`, `0x37`, `0x3f`; `0x3f` calls `GetMatrixKey` with `param0 & 0x7f` and uses bit 7 of `param0` to select the follow-up | log format `byCmd(0x%02x) Parameter([0]=0x%02x …)` at VA `0x03a12c10`, xref → fn `0x03a18210` |
| code → table | `KEPV:FindTable` **0x03a161dc** | `(KeyType 1..6)` → `{pointer, count}` from object fields `+0x94/+0x98`, `+0x9c/+0xa0`, `+0xa4/+0xa8`, `+0xac/+0xb0`, `+0xb4/+0xb8`, `+0xbc/+0xc0` | `sh4dis --va 0x03a161dc`, switch at `0x03a16212`–`0x03a16296` |
| code → VK | `KEPV:GetVkey` **0x03a16e60** | linear scan of 2-byte pairs: compare `u8 code`, return `u8 vk` at `+1`, else `0xff` | `sh4dis --va 0x03a16e60`, loop `0x03a16eb2`–`0x03a16ed0` |
| matrix code → key | `KEPV:GetMatrixKey` **0x03a15f40** | same scan over the matrix table at object `+0x8c` / count `+0x90` | `sh4dis --va 0x03a15f40` |
| VK → UI | `KEPV:KeybdEvent` **0x03a17528** → `KEPV:AuiKeyEvent` **0x03a16f20** | `keybd_event()` then `WM_KEYDOWN`/`WM_KEYUP` strings at `0x03a12138`/`0x03a1212c` | xrefs to those strings |

## 3. The code table the UI reads (one row per key code)

`tools/kep_tables.py archive/head256.img` reproduces every row below.
"Raw" is the first byte of a pair (the `HardKeyCode` compared by `GetVkey`),
"VK" the second byte returned to `KeybdEvent`. The **source** column is the
physical ingress deduced from the entry function and the table selector; where
the firmware does not name a key, the name column gives the owner's-manual
wording and is marked **OBSERVED**, and the VK is kept as a hex value.

### 3.1 Table at `0x01f421b4` (KeyType 3, 17 pairs) — display-unit hard keys

This table's VK set (`0x0d`, `0x06`, `0x07`, `0x17`–`0x20`, `0x05`) is the
navigation-function vocabulary. The raw codes are the values the SCI3 frame
parser hands to `GetVkey`.

| Name (OBSERVED, manual wording) | Source | Raw code | VK | Table VA |
| --- | --- | --- | --- | --- |
| confirm / ENTER | `SCI3:` display hard key | `0x0c` | `0x0d` | `0x01f421b4` |
| navigation function `0x07` | `SCI3:` | `0x11` | `0x07` | `0x01f421b4` |
| navigation function `0x06` | `SCI3:` | `0x12` | `0x06` | `0x01f421b4` |
| MAP (manual wording) | `SCI3:` | `0x23` | `0x17` | `0x01f421b4` |
| MENU (manual wording) | `SCI3:` | `0x2b` | `0x18` | `0x01f421b4` |
| DEST (manual wording) | `SCI3:` | `0x2c` | `0x19` | `0x01f421b4` |
| ZOOM (manual wording) | `SCI3:` | `0x31` | `0x1a` | `0x01f421b4` |
| DAY/NIGHT (manual wording) | `SCI3:` | `0x37` | `0x21` | `0x01f421b4` |
| function `0x20` | `SCI3:` | `0x38` | `0x20` | `0x01f421b4` |
| ESC / BACK | `SCI3:` | `0x3e` | `0x1b` | `0x01f421b4` |
| function `0x1c` | `SCI3:` | `0x44` | `0x1c` | `0x01f421b4` |
| function `0x1d` | `SCI3:` | `0x47` | `0x1d` | `0x01f421b4` |
| function `0x1e` | `SCI3:` | `0x48` | `0x1e` | `0x01f421b4` |
| function `0x00` | `SCI3:` | `0x49` | `0x00` | `0x01f421b4` |
| function `0x01` | `SCI3:` | `0x4a` | `0x01` | `0x01f421b4` |
| function `0x1f` | `SCI3:` | `0x4c` | `0x1f` | `0x01f421b4` |
| volume/rotary increment | `SCI3:` | `0xf0` | `0x05` | `0x01f421b4` |

The human-facing names (MAP/MENU/DEST/ZOOM/DAY-NIGHT) are **manual
wording**, not firmware strings; the raw↔VK pairs are VERIFIED. Any finer
assignment of `0x17`..`0x1a` to a particular one of those five keys is a
HYPOTHESIS and must not be used for injection without an L3/L4/L5 check.

### 3.2 Tables at `0x01f421d8` (KeyType 4, 18 pairs), `0x01f421fc` (7), `0x01f42210` (KeyType 5, 36), `0x01f42258` (KeyType 6, 13)

These carry the audio / steering-wheel vocabulary. Every raw code in them is
listed once per table; the full `raw:vk` strings are quoted verbatim from
`tools/kep_tables.py` in the EXP (§ Observations).

| Name (OBSERVED, manual wording) | Source | Raw code → VK | Table VA |
| --- | --- | --- | --- |
| audio function group A | `SCI1:` audio micom / CAN steering | `1c:4e 0f:4f 0c:50 0d:51 0e:52 12:29 13:2a 14:2b 15:53 1e:2d 1a:31 05:33 04:34 06:35 0b:36 44:37 43:3a 02:3b` | `0x01f421d8` |
| audio function group B | `SCI1:` / CAN steering | `1b:00 1d:01 05:d1 03:d2 0a:d3 17:d4 16:d5` | `0x01f421fc` |
| steering/audio extended group | `SCI1:` / CAN steering | `62:8c 63:8d 0f:8e 0c:8f 0d:90 0e:91 1e:92 51:93 52:94 53:95 54:96 55:97 56:98 57:99 58:9a 59:9b 50:9c 49:9d 5f:9e 1f:9f 48:a0 04:a1 08:a2 15:a3 47:a4 05:a5 1c:a6 61:a7 40:a8 14:a9 11:aa 18:ab 5d:ac 5c:ad 5e:ae 07:af` | `0x01f42210` |
| steering/audio top group | `SCI1:` / CAN steering | `32:bf 90:c5 91:c6 96:cd 21:c7 22:c8 97:ce 92:cc 93:c9 94:cb 95:ca 98:be 99:bf` | `0x01f42258` |

`VK 0xae`/`0xaf` are the standard Windows volume-down/up codes and both occur
in the table at `0x01f42210` (`5e:ae`, `07:af`); that reading is **OBSERVED**
from the VK value, not from a firmware key string.

### 3.3 Panel-dependent tables (the "mode" the table must show)

`KEPV:FindTable` selects KeyType 1/2 tables from the panel/maker word compared
at `fn 0x03a15d84`–`0x03a15d96`. The active word for the unit under test was
not read at runtime, so **all four variants are listed**; the active one is
UNKNOWN. These are *not* two functions for one code: the selector is visible
in the table installation code.

| Panel/maker word | KeyType 1 table VA (count) | KeyType 2 table VA (count) |
| --- | --- | --- |
| default (none of the three) | `0x01f42104` (9) | `0x01f4215c` (10) |
| `0x10100600` | `0x01f42118` (9) | `0x01f42170` (10) |
| `0x01101100` | `0x01f4212c` (9) | `0x01f42184` (10) |
| `0x10101100` | `0x01f42140` (13) | `0x01f42198` (10) |

## 4. Falsifier check

The falsifier was "one raw code maps to two functions depending on a mode the
table does not show". Result: **no such case in the installed tables**. Every
table is duplicate-free except `0x01f42140`, where raw `0x01` appears twice
(`0x01:0x02` at index 0 and `0x01:0x22` at index 12). `GetVkey` scans from
index 0, so the effective mapping in that one panel mode is `0x01 → 0x02`;
the later pair is shadowed. The mode *is* shown (§3.3), and the duplicate is
recorded as **OBSERVED** rather than hidden. `tools/kep_tables.py --selftest`
pins both the duplicate detection and the truncation behaviour.

## 5. What is not known

- Which physical switch each `0x17`..`0x1a` VK corresponds to (MAP vs MENU vs
  DEST vs ZOOM). Firmware has no key-name strings; manual wording is a label,
  not evidence.
- The runtime panel/maker word, hence which of the four KeyType 1/2 variants
  is active on the EU 2011 unit.
- Whether the GPIO matrix row is fed by steering-wheel switches, by the
  display unit, or by both; the matrix table pointer is installed at runtime.
- Any long-press/repeat rule. `KEPV:CheckKeyStatus` (string VA `0x03a12860`)
  and `KEPV:ForcedKeyUpKeySw` (VA `0x03a124c8`) exist, but their timing is not
  decoded here.
- Nothing here has been executed against a real or emulated unit (rule 13).
