# Firmware and pre-partition area

The 100 MB before the FAT partition contains the navigation firmware and
possibly update/recovery data. It is **not** a plain Windows CE image, and
classic PE carving does not work on it.

## What is there

### Clarion identification records

At `0x000001c0` and `0x000003c0` there are 512-byte records ending in
`0x55 0xaa`, with MBR-like partition entries:

```
0x01c0: 03 00 0b 00 02 00 02 20 03 00 00 00 e1 00 00 00 ...
0x01fe: 55 aa
0x0200: "CLARION ID"
```

```
0x03c0: 03 00 0b 00 02 00 02 20 03 00 00 00 e1 00 00 00
        03 00 0c 00 02 00 02 20 e4 00 00 60 09 00 00 00
0x03fe: 55 aa
```

These look like a Clarion-specific card/partition header, not standard MBR.

### Firmware container at `0x00200000`

```
0x00200000: 88 2c 75 01              u32 0x01752c88
0x00200014: "\x82FX210ECNI.158"       Clarion part/version string
0x0020002c: "SUM4"                    checksum marker?
0x00200034: "470-2824-34"             Clarion part number
0x002001fc: "NKOK"
0x00200200: table of 32-bit values
0x00200240: "ECEC" (43 45 43 45)
0x00200244: 78 29 23 8e
0x00200248: 78 19 75 01              u32 0x01751978 = 24,451,448
```

The value `0x01751978` is close to the size of one firmware copy
(`0x01800000` = 25,165,824 bytes), which supports the idea that this is an
uncompressed-size field.

### Repeated payloads

The region `0x00200000`–`0x03600000` (about 22 MB) repeats almost identically
at `0x02000000`–`0x03600000`. Partial copies appear around `0x03e00000`,
`0x04800000` and `0x05200000`. Between them are large `0xff` gaps.

This is probably a set of firmware slots (current + backup + update), but the
slot table has not been decoded.

### Readable content

The area contains lots of readable WinCE/navigation strings:

- `C:\WINCE500\PBWorkspaces\10eNavi_UpdateNK`
- `CETUS_SH4`
- `Navi.exe`, `NaviAPL`
- `NaviSearchCC.dll`, `NaviDrawCC.dll`, `NaviStateCC.dll`,
  `NaviRouteCC.dll`, `NaviSetCC.dll`, `NaviMapScrollCC.dll`,
  `NaviRegCC.dll`, `TelemaRouteCC.dll`
- `HCXCmpLib`, `hcxcmp`
- map file names: `REFER001`, `ICODE001.DAT`, `ZIPFR001.DAT`,
  `COORD001.DAT`, `INDEX001.DAT`, `RDSTM001`, `REFER002`, `MAPAL001`,
  `LEV3456R.DAT`, `BICON001.DAT`, `DRSTR001.DAT`, `MMAIN001.DAT`, `CMP.LST`,
  `.cmp`, `.ind`
- debug formats such as `MESHID[0x%08X] POI[%4d] Pre[%5d] Next[%5d]`,
  `Mesh[LV1:0x%08X LV2:0x%08X]`, `mesh=%08X x:y=%07d:%07d`

Embedded PNG assets (IHDR/IDAT/IEND) appear around `0x00df0000`, so at least
part of the payload is not encrypted.

## Why PE carving fails

A byte-by-byte scan for `MZ` with a valid `e_lfanew` / `PE\0\0` pair finds
**zero** PE files in the pre-partition area. The `MZ` and `PE` byte pairs that
do occur are coincidences inside compressed or structured data
(`"MZG etDV..."`, `"PMSG\0\0G2PE..."`, etc.).

The container is therefore either:

1. compressed with a custom algorithm (the `HCXCmp` / `ECEC` lead), or
2. a proprietary ROM/update image whose modules are not stored as normal PE
   files.

Until it is unpacked, `Navi.exe` cannot be analysed with `rizin`/Capstone.

## `HCXCmp` lead

Firmware strings `HCXCmpLib` and `hcxcmp` strongly suggest a custom
compression library. The `ECEC` marker at `0x00200240` may be its container
magic. The map `.DAT` payloads themselves turned out to use plain zlib, so
`HCXCmp` may apply only to firmware/update payloads.

## Next steps

1. Decode the container header at `0x00200000` (part number, sizes, slot
   table, checksum).
2. Determine whether `ECEC` is a compression magic and, if so, its block
   format.
3. Compare the container across other images (newer maps, other markets) to
   see which fields change.
4. If unpacking succeeds, extract `Navi.exe` and the `Navi*CC.dll` modules and
   analyse the SH-4 code with `rizin` (already installed).
5. Check the post-partition 402 MB tail; it may contain another copy or the
   update application.

## Safety note

Do **not** write a modified firmware container to a car. Firmware is a much
higher risk than map data. This project's scope is map data only.
