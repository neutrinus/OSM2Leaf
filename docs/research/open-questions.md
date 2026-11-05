# Open questions

Unresolved technical questions, grouped by area. Actionable work is tracked in
[`../../TODO.md`](../../TODO.md); this page records *what we do not know yet*
and what evidence would settle it.

## Card and update mechanism

1. **Map activation / "different map code".** How does the unit decide that a
   card is valid? Is it a checksum, a signature, a version string, the SD
   card CID, or a combination? What changes when a newer map is installed?
2. **US vs EU layout.** Does the US 2011 card use the same
   `QSD-3xx` naming, the same `DRSTR001.DAT` schema and the same directory
   set? The US dump is the ground truth.
3. **Free space.** The EU image has ~2.35 GB free. Is free space required, or
   can a card be filled?
4. **Post-partition tail.** What are the 402,652,160 bytes after the FAT
   partition? Another image? Update payload? Padding?
5. **Pre-partition slots.** Are the repeated firmware copies selectable
  slots, and is there a slot table with checksums?

## Map database

6. **`MMAIN001.DAT`.** What does the 4,096-byte master file describe? It has
   the common header plus a descriptor at `0x180`, but no obvious pointers to
   the other databases.
7. **Tile grid.** How do `BxxRyyR` names map to latitude/longitude? Is it a
   JIS mesh code, a Clarion block/row grid, or something else?
8. **`LEV3456R.DAT`.** What is its role, and why is it 76 MB when the 46
   regional tiles are much smaller?
9. **Tile descriptor.** What is the structure at `0x2b0` and at `0x1ac` in
   each tile? How are the many zlib streams addressed?
10. **Record formats.** What are the records inside decompressed
    `REFER001`/`REFER002` payloads (addresses, POIs, street names,
    coordinates)? What are the ID spaces (`MESHID`, `POI`, `Pre`, `Next`)?
11. **`RDSTM001` / `LCTBL001`.** How are roads, street names and attributes
    split between these files and `MAPAL001`?
12. **Address/POI language model.** `REFER001/002` are split into many
    `ADDRE001..033`, `POINT001..033`, `INTER001..033`, `ZCODE`, `FRWAY`,
    `ICADM`, `ICODE`, `ZIPFR` files. Is the numeric suffix a region or a
    shard? How does it correlate with the tile mesh?
13. **`DRSTR001.DAT` header word.** What does the leading `u32` (`0x2f` = 47
    in the EU 2011 image) mean, given that the file contains 39 nodes? (See
    [drstr.md](../format/drstr.md).)

## Firmware

14. **Container format.** How is the firmware at `0x00200000` packed? What are
    `NKOK`, `ECEC`, `SUM4`, and the 32-bit table at `0x200200`?
15. **`HCXCmp`.** Is it a real compression algorithm, and does it apply to
    files other than firmware?
16. **Reader logic.** Which code opens `.cmp`/`.ind`, `DRSTR001.DAT` and the
    tiles? Confirming this from `Navi.exe` would remove most guesswork.
17. **SH-4 tooling.** Can the extracted modules be loaded in `rizin` with
    correct SH-4 segment mapping?

## Compiler design

18. **Round-trip fidelity.** Can a tile or database be decompressed and
    recompressed byte-identically? If not, which fields are non-deterministic?
19. **Checksums.** Are there checksums over files, directories or the whole
    card? Where are they stored?
20. **Minimum viable map.** What is the smallest synthetic change the unit
    will accept (for example one renamed POI or one added road segment)?
21. **Routing graph.** Is routing computed from `RDSTM001`, from tile
    geometry, or from both? What granularity is required?
22. **Address coverage.** Can OSM addresses be mapped onto the unit's
    address hierarchy without breaking search?
