# EXP-2026-11-06-H10: PM review, fourth pass — checks on the US image

- **Status:** done
- **Date:** 2026-11-06
- **Task:** H10
- **Sample:** `LEAF_2011-2012_US.img` from `https://files.viaaq.eu/sd-images/`
  (expected SHA-256 `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383`)
- **Claims:** C-2110–C-2119 (reserved; facts below are recorded here only)
- **Supersedes:** none

## Question

Do the M5.12 / M5.10 results hold on the real US image, and is the M5.12 card
image safe as the first hardware card?

## Method

Read the map partition of the US image with `tools/mkcard.py` helpers
(`open_map_partition`, `img_list_dir`, `read_chain`, `img_read`); extracted
only `REFER001/POINT010.DAT.cmp`/`.ind`; reran the M5.12 command
(`mutate_refer_poi.py … --page 0x840ba0 --old "HANA HEALTH CENTER" --new
"OSM2LEAF TEST POI1"`); decompressed both pairs with `cmpind.py extract`;
compared logical bytes; scanned every zlib page of the factory `POINT010.DAT`
for `HANA HEALTH`. Python `zlib.ZLIB_RUNTIME_VERSION` = `1.3`.

## Observations

- Partition 0: FAT32, LBA 204802, 64 KiB clusters, BPB label `NO NAME`.
  **Root slot 0 is a volume-label entry `QSD-301-103` (attr `0x08`).**
- `build_fresh_partition` in `mkcard.py` (used for every changed tree) writes
  no attr-`0x08` entry and rebuilds both FATs; M5.12's `cardcheck` reported
  "warnings: 1 (no volume label)". So the M5.12 image lacks the label and
  differs from the factory in FAT layout as well as in the edited pair.
- `POINT010.DAT.cmp`: 4,240,574 B, 65 contiguous clusters
  (sha256 `48812f8c…2d4657`); `.ind` 612 B (`7ac54e3b…0c326e`).
- Rerun of the rename: L6 recompression **fits** here (42,657 B into the
  42,848 B slot), outer `.cmp` 4,240,574 → 4,240,440 B
  (`01fb53a5…e368359`). M5.12 reported that L6 did not fit (L9 fallback,
  `.cmp` → 4,233,336 B). The compressed output depends on the zlib build;
  the logical result does not.
- Logical check: both `.DAT` are 9,715,200 B; the inner page `0x840ba0`
  decodes to 130,178 B in both, **17 bytes differ**, exactly the name;
  `HANA HEALTH CENTER` ×1 before, `OSM2LEAF TEST POI1` ×1 after. The
  record reads `…HANA HEALTH CENTER4590@HANA HWY…` (Hana, Maui, HI).
- In the whole factory `POINT010.DAT` only one other page (`0x89bcd0`) holds
  `HANA HEALTH`, inside a different POI (`OHANA HEALTH CARE CENTER`, Kilauea
  Rd). Other files (search indexes) were not scanned → M5.12c.

## Interpretation

- **FACT:** the M5.12 edit reproduces logically (17-byte name change, sizes
  and DRSTR unchanged).
- **FACT:** the M5.12 card image as built drops the root volume label and
  re-lays out the FAT, so it changes three things at once. It should not be
  the first edited card on the unit; build S1/S2 by in-place patch (M5.13).
- **FACT:** compressed bytes of a mutated pair differ between zlib builds;
  any card handed to Marek must be identified by its own SHA-256, not by the
  M5.12 sizes.
- **UNKNOWN:** whether the firmware reads the volume label at all.

## Follow-ups

M5.13, M5.12b, M5.12c (new tasks in `TODO.md`).
