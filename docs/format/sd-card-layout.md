# SD card and image layout

> **Evidence convention:** `VERIFIED` means reproduced from the sample bytes;
> `OBSERVED` means seen but not fully explained; `HYPOTHESIS` / `UNKNOWN` are
> marked explicitly. See [`../research/claims.md`](../research/claims.md).

Sample: `LEAF_2011-2012_QSD-309-101_navi158_eu.img`

- Size: 8,057,257,984 bytes (7.5 GiB)
- SHA-256: `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- Source: <https://files.viaaq.eu/sd-images/>

## Partition table

The image begins with a DOS MBR. The first 448 bytes are zero, the partition
entry starts at `0x1be`.

| Field | Value |
| --- | --- |
| Boot flag | `0x00` |
| Partition type | `0x0b` (W95 FAT32) |
| Start LBA | `204802` |
| Start byte offset | `0x06400400` = 104,858,624 |
| Sectors | `14,745,600` |
| Size | 7,549,747,200 bytes |
| Filesystem | FAT32 |
| Cluster size | 65,536 bytes |
| Volume label | `QSD-309-101` |
| Volume ID | `706622075` (0x2a1f5d7b) |
| Free space | 2,349,531,136 bytes |
| Last FAT modification | 2011-08-23 21:20:54 |

`fdisk -l` and `7z l` agree on the geometry. The FAT filesystem can be
extracted with:

```bash
7z x -y -o<dest> leaf2011.img
```

Result for the EU 2011 image: **39 directories, 480 files, 5,173,965,667
bytes**.

## Top-level contents

```
MMAIN001.DAT        4,096 B      master header / database manifest
DRSTR001.DAT       11,968 B      directory index
CMP.LST                19 B      "\SystemSD\REFER001\"
MAPAL001/          46 tiles      map geometry tiles + LEV3456R.DAT
REFER001/          194 pairs     compressed address/POI data (.DAT.cmp + .ind)
REFER002/           16 files     uncompressed EV/charging POI layer (.DAT)
RDSTM001/          2 files       road/street data + lookup table
BICON001/          1 file        icon data
OPNG/              1 file        PNG-like assets
SPEECH/            21 files      7 languages x (VR, TTS, GID)
TMC/               1 file        TMC reception parameters
VER_INFO/          1 file        version strings
```

## Pre-partition area (offset 0 .. 104,858,623)

The 100 MB before the FAT partition is not empty. It contains:

- At `0x000001c0` and `0x000003c0`: 512-byte records ending in `0x55 0xaa`,
  with partition-like entries. At `0x00000200`: ASCII `CLARION ID`.
- At `0x00200000`: a firmware container header:
  - `0x00200000`: `88 2c 75 01` (u32 `0x01752c88`, likely a size)
  - `0x00200014`: `\x82FX210ECNI.158` — Clarion part/version string
  - `0x0020002c`: `SUM4`
  - `0x00200034`: `470-2824-34`
  - `0x002001fc`: `NKOK`
  - a table of 32-bit values at `0x00200200`
  - `0x00200240`: `ECEC` (`43 45 43 45`) followed by more sizes
- Readable WinCE/navigation strings from `0x00470000` onward (screen-state
  names, DLL names, file names).
- Embedded PNG assets around `0x00df0000`.
- The same firmware payload appears to be duplicated several times:
  `0x00200000`, `0x02000000`, and partial copies at `0x03e00000`,
  `0x04800000`, `0x05200000`.
- Large `0xff` gaps between copies (`0x01a00000`–`0x02000000`,
  `0x03800000`–`0x03e00000`, etc.).

See [firmware.md](firmware.md) for the current hypothesis and blockers.

## Post-partition tail (offset 7,549,747,200 .. end)

The FAT partition ends at:

```
204802 + 14745600 = 14,950,402 sectors
14,950,402 * 512 = 7,654,605,824 bytes
```

The image is 8,057,257,984 bytes, so the tail is:

```
8,057,257,984 - 7,654,605,824 = 402,652,160 bytes
```

This region is almost entirely non-zero (400,365,370 of 402,652,160 bytes)
and contains `MZ`, gzip-looking and printable runs, but no validated PE files.
Its purpose is unresolved. It may be a second card image, an update payload,
padding written by the imager, or vendor data. **Open question.**
