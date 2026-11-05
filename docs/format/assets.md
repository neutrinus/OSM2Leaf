# Asset containers (`BICON001`, `OPNG`, `SPEECH`)

These are not map data, but they matter for POI icons and voice prompts.

> **Evidence status:** `BICON001` layout is `VERIFIED`; `OPNG`/`SPEECH` are
> `OBSERVED` and not needed for the first compiler milestone.

## `BICON001/BICON001.DAT` — POI icons

114,598 bytes. It is a PNG icon container, not a custom codec.

```
0x0000  512-byte common header
0x1000  header; u16 at 0x100a = 0x0067 = 103 icons
0x1016  u32 table (start, size), cumulative
0x1408  103 PNGs (32x32; five 30x30)
```

- `tools/point2.py bicon --out icons` extracts all 103.
- The POI `icon code` → PNG mapping is **UNKNOWN**. There is no icon-id table
  inside POINT, and `f0` is constant per file (0/3/16/20), i.e. a table id.
- `BICON001.DAT` is the only map file with a different data version
  (`11/04/08/01` vs `11/06/27/01`).

## `OPNG/` — images

`OPNG/MKR_OPNG/NISSAN/OIXXEVNI.001` starts with the `BASSW7C` container magic,
then a filename/part number and an 800×480 descriptor. It contains tiled image
data; the tile grammar is **not decoded**. Not needed for map correctness.

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

`TTS` payloads contain RIFF/WAV and zlib streams. These are out of scope for
the map compiler.

## Licensing

Icons, images and voice data are vendor assets. Do not commit or redistribute
them; use the factory files on the card.
