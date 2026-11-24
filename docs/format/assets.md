# Asset containers (`BICON001`, `OPNG`, `SPEECH`)

These are not map data, but they matter for POI icons and voice prompts.

> **Evidence status:** `BICON001` layout and the 34-row category/brand →
> icon table are `VERIFIED`/`OBSERVED` (EXP-2026-11-06-M4.10-poi-icons);
> `OPNG` container framing and byte-identical round trip are `VERIFIED`
> (EXP-2026-11-22-M4.91-opening-picture), its pixel grammar is `UNKNOWN`;
> `SPEECH` is `OBSERVED`. None is needed for the first compiler milestone.

## `BICON001/BICON001.DAT` — POI icons

114,598 bytes. It is a PNG icon container, not a custom codec.

```
0x0000  512-byte common header
0x1000  header; u16 at 0x100a = 0x0067 = 103 icons
0x100e  103 * (u32 start, u32 size), big-endian, in 2-byte units
0x1408  first PNG; offset = 0x1408 + 2*start, length = 2*size
```

- 98 icons are 32×32 chain logos; the five 30×30 entries are the generic
  glyphs 0, 18, 19, 20 and 21.
- Four slots are byte-identical copies of the Holiday Inn logo (25/60/75/76)
  and two of Crowne Plaza (23/59); duplicate slots are not distinct brands.
- `tools/poi_icons.py bicon <BICON001.DAT>` lists the table and PNG sizes.
- `BICON001.DAT`'s `DATA VERSION` (`11/04/08/01`) differs from the other map
  files only on EU 2011 (`11/06/27/01`) and US 2011 (`10/06/24/01` vs
  `10/08/12/01`). On EU 2014 and EU 2016 it equals `MMAIN001.DAT`; the claim
  "the only map file with a different version" is retracted (C-2497).
- `BICON001.DAT` also carries the same `0x18c` code list as `MMAIN001.DAT`
  on each image (C-2494); its `0x1a0` run is `00`, not `ff`.

### POI category/brand code → icon

A `POINT0nn` facility name is bracketed by two 16-bit codes:

```
<tag> <category:u16> NAME \0 [house@street] <brand:u16>
```

The code before the name is the top-level category; the last two bytes of
the record are the brand sub-category. They are equal for brand-coded fuel
stations (`ARAL` → `0x01bc` both) and differ for a shop inside a fuel
station (`CORA` → category `0x0190`, brand `0x01e2`). For hotels the
category is always `0x0dac` and the brand code selects the chain logo.

Observed ranges: `0x01xx` fuel/shop, `0x03xx` restaurant, `0x0dxx`–`0x0exx`
hotel. The icons are not stored in code order (Comfort `0x0dd1` is icon 34,
Campanile `0x0dc3` is icon 35), so use this table rather than a rank.

| Code | Dec | Icon | Depicts | Rows in scan |
| --- | --: | --: | --- | --: |
| `0x0190` | 400 | 0 | fuel pump (generic) | 29,511 |
| `0x0391` | 913 | 18 | knife & fork (generic) | 48,147 |
| `0x0dac` | 3500 | 21 | bed (generic hotel) | 171,102 |
| `0x0193` | 403 | 1 | BP | 1,325 |
| `0x0195` | 405 | 2 | ASDA | 174 |
| `0x01a1` | 417 | 3 | Carrefour | 337 |
| `0x01bc` | 444 | 6 | Aral | 2,381 |
| `0x01be` | 446 | 7 | Intermarché | 1,533 |
| `0x01cf` | 463 | 8 | Preem | 383 |
| `0x01d9` | 473 | 9 | Tamoil | 2,520 |
| `0x01e2` | 482 | 12 | Cora | 61 |
| `0x0dad` | 3501 | 22 | Best Western | 1,055 |
| `0x0db1` | 3505 | 23 | Crowne Plaza | 48 |
| `0x0db7` | 3511 | 24 | Hilton | 117 |
| `0x0db8` | 3512 | 25 | Holiday Inn | 245 |
| `0x0dbb` | 3515 | 26 | InterContinental | 13 |
| `0x0dbe` | 3518 | 27 | balladins | 174 |
| `0x0dbf` | 3519 | 28 | Quality | 109 |
| `0x0dc6` | 3526 | 31 | Sheraton | 37 |
| `0x0dcc` | 3532 | 33 | Concorde | 18 |
| `0x0dc3` | 3523 | 35 | Campanile | 387 |
| `0x0dd1` | 3537 | 34 | Comfort | 140 |
| `0x0dda` | 3546 | 36 | Golden Tulip | 75 |
| `0x0dbc` | 3516 | 37 | B&B Hotels | 104 |
| `0x0df2` | 3570 | 39 | Mercure | 435 |
| `0x0e0d` | 3597 | 44 | Scandic | 100 |
| `0x0dbd` | 3517 | 62 | Marriott | 31 |
| `0x0dc0` | 3520 | 29 | Radisson (first block) | 15 |
| `0x0e2e` | 3630 | 57 | Radisson Blu (second block) | 82 |
| `0x0e2a` | 3626 | 53 | Radisson Edwardian | 11 |
| `0x0e24` | 3620 | 47 | Clarion | 51 |
| `0x0e29` | 3625 | 51 | Park Inn | 73 |
| `0x0e32` | 3634 | 61 | Andaz | 2 |
| `0x0e39` | 3641 | 65 | Citadines | 41 |

Counts are POINT records with that brand code and a name starting with the
chain name, over shards 002/004/005/008/011/018/020/021/022/025/026/029/030/033.
The generic glyphs 19 (pharmacy cross) and 20 (parking) exist but their codes
are not isolated yet.

Reproduce with:

```bash
python3 tools/poi_icons.py bicon BICON001/BICON001.DAT
python3 tools/poi_icons.py codes /tmp/poi
python3 tools/poi_icons.py verify /tmp/poi --bicon BICON001/BICON001.DAT
```

`/tmp/poi` holds `POINT0nn.DAT` files extracted with `tools/cmpind.py
extract`. The join is by logo identity; the runtime's static lookup table is
not stored in the map data (C-988). Full method and evidence:
`docs/experiments/EXP-2026-11-06-M4.10-poi-icons.md`.

## `OPNG/` — opening-image animation

One file per card: `OPNG/MKR_OPNG/NISSAN/OIXXEVNI.001` (EU2011/US2011) or
`OIXXNVNI.001` (US path spelling), 1,606,224 B. It is the animation the
launcher loads before `Navi.exe` (L4 log `Load Opening Image Data to
0x8c6e0000 (Size=4198400 Bytes)`, C-6875/C-6915). `tools/opng.py` reads it;
no decoded picture is committed. Evidence:
EXP-2026-11-22-M4.91-opening-picture.

### Container layout (all integers little-endian)

```
0x000  8  magic 'BASS' + 4 bytes (EU 57 37 43 d8; US 60 37 43 d2)
0x008  8  ASCII '00000000'
0x010  4  ASCII '0002'
0x014  u32 declared file size = 1606224 (0x188250)
0x018  u32 ffffffff
0x01c  36 ASCII identity, e.g. 'OIXXEVNI.001470-2827-00 '
0x040  u32 frame count = 35
0x044  u32 2
0x050  first of 35 frames, each:
         u32 prefix (0 on both cards)
         u16 width  = 800
         u16 height = 480
         u32 payload_len
         u32 duration_ms
         payload_len bytes of coded frame data
0x18824e  2-byte EOF trailer
```

- Frame 0: payload 1,504 B, duration 400 ms. Frames 1–33: payload
  22,212–37,948 B, duration 70 ms each. Frame 34: payload 34,632 B,
  duration 2,290 ms. **Durations sum to exactly 5,000 ms** (a 5-second
  animation). Total payload = 1,605,582 B.
- EU and US payloads are **byte-identical**. The files differ in only four
  header bytes: `0x04` (`57`→`60`), `0x07` (`d8`→`d2`), `0x20` (`E`→`N`)
  and `0x2f` (`7`→`1`). The bytes at `0x04`/`0x07` change by the same deltas
  (+9/−6) as the identity-string bytes at `0x20`/`0x2f`; they are
  checksum-like, but the algorithm is **UNKNOWN**.
- Each payload ends with a `u32` that is a multiple of `0x20` (frame 0
  `0x00005de0`, frame 34 `0x0000ca60`) followed by `u32 0`; its meaning is
  unknown and simple sum/xor/CRC-32 checks do not reproduce it.

### Pixel data is NOT decoded

The frame payload is **not** raw 800×480 pixels. Under RGB565 (LE/BE), RGBA,
BGRA, 8-bit gray and 1/4-bpp views the result is noise: payload entropy
5.2559 bit/byte, top `u16` values `0x00a0`/`0x0041`, no zlib/PNG/JPEG
signature, and horizontal-adjacency correlation −0.12…−0.03. The grammar is a
proprietary coded/display-list format (**UNKNOWN**), so a self-made opening
picture cannot yet be encoded. `tools/opng.py decode` therefore writes a PNG
carrier (byte-map view + verbatim bytes in a `zTXt` chunk) and `encode`
restores the file byte-identically — a **container** round trip, not a pixel
decode.

```bash
python3 tools/opng.py info OPNG/MKR_OPNG/NISSAN/OIXXEVNI.001
python3 tools/opng.py decode OPNG/MKR_OPNG/NISSAN/OIXXEVNI.001 -o /tmp/opng.png
python3 tools/opng.py encode /tmp/opng.png -o /tmp/opng-back.001
# cmp original and /tmp/opng-back.001 -> byte-identical on EU2011 and US2011
```

## `SPEECH/` — voice prompts

`SPEECH/<lang>/{VR,TTS,GID}/` hold `AGM`/`TTS`/`GID` archives. The common
archive shape is:

```
0x00  16 ASCII digits (serial)
0x10  u32 total size
0x14  u32 header size (0xf8 = 248 in the sample)
0x18  u32 ? (0)
0x1c  u32 entry count (9 in the sample)
0x20  entries: name[12] + u32 offset + u32 size + u32 size2
```

Language sets per image (M4.22, counted from the 7z FAT listings). The
`0x18c` code of each dir (M4.38, `file-header.md` Identity fields): BE `02`,
US `03`, FR/CF `04`, GE `05`, SP `06`, IT `07`, PT `08`, DU `0a`, DA `0d`,
SV `0c`, FI `15`, NO `16`; EL (`09`), PL, CS, HU, SK speak with map text code
`02` in the 2014/2016 firmware. The join holds on all four cards, EU 2016
included (M4.22 re-run, C-5282).

| Image | `SPEECH/` language dirs | Dirs with `VR`+`TTS`+`GID` |
| --- | --- | --- |
| US 2011 | `CF`, `US` | both |
| EU 2011 | `SP PT IT GE FR DU BE` (7) | all seven |
| EU 2014 | `BE CS DA DU EL FI FR GE HU IT NO PL PT SK SP SV` (16) | `BE DU FR GE IT PT SP` only; the other nine have `GID` |
| EU 2016 | as EU 2014 | as EU 2014 |

`TTS` payloads contain RIFF/WAV and zlib streams. These are out of scope for
the map compiler.

### Cross-year format check (M4.57, EXP-2026-11-24-M4.57-polish-voice)

The three kinds keep the **same archive framing** on EU 2011 and EU 2014; only
field values and entry sets change. `tools/speech_years.py` prints the numbers
(`describe`, `compare`, `langs`, `--selftest`):

| Kind | GID | TTS | AGM |
| --- | --- | --- | --- |
| Framing | same (16-digit serial, u32 size/hdr/flags/count, 24 B entries) | same | same |
| 2011 → 2014 | serial `0000102020100524`→`0000302420140919`, size 9,729,912→14,868,920, flags 46,104→0 | serial `0000200020100524`→`0000300720120423`, 9→10 entries (extra `TSP00500.BIN`), hdr 248→272 | 9→18 entries, hdr 248→464, names renumbered (`RSPA0001.ACM`→`RSP00000.ACM`) |
| Verdict | `same` framing | `same` framing | `same` framing |

The SVOX TTS stamp is identical across the years: `MAJVERS 5`, `MINVERS 0`,
`REV 0`, `SOFTWID 41003`, `LINGWID 0`, `TAVERS 4.3.0.0-2`; only `USRTIMESTAMP`
changes. The embedded `TSP00400.WAV` is a 44-byte RIFF/WAVE PCM mono 22,050 Hz
16-bit sample on both. Whether a 2011 `Speech.exe` actually *decodes* 2014
prompt bytes is `unknown` (no L3/L4 run).

The 2011 build's language list is a UTF-16LE name table in `Speech.exe` sec0
at VA `0x00032354` (10 names at 8-byte stride: `CF US JP SP PT DU IT GE FR BE`,
terminated by `ffff ffff` at `0x000323a4`); `PL` is absent. EU 2014's build
holds the same form at VA `0x00036cf0` with 20 names including `PL`. A stock
2011 `Speech.exe` therefore has no built-in selector for a 2014 `SPEECH/PL`
set.

## Licensing

Icons, images and voice data are vendor assets. Do not commit or redistribute
them; use the factory files on the card.
