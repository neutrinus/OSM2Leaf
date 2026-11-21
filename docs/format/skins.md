# Skins: where they live and the `.skn` (AUITK skin) layout

> **Evidence convention:** `VERIFIED` = reproduced from the sample bytes with
> the command shown; `OBSERVED` = seen but not fully explained; `HYPOTHESIS` /
> `UNKNOWN` are marked. Claims: C-6500–C-6509
> ([`../research/claims.md`](../research/claims.md)); evidence:
> [`../experiments/EXP-2026-11-21-M4.58-skins-tfat16.md`](../experiments/EXP-2026-11-21-M4.58-skins-tfat16.md).
> Everything here was read offline; no card was built and nothing ran on a unit
> (rule 13: the reader is located by strings/VA, not yet executed on our file).

Samples (vendor data, not committed). Full card SHA-256 are in the EXP; heads
(`archive/head256.img`, `us256.img`, `eu2014-256.img`, `eu2016-256.img`) and
full images (`archive/sd-images/*.img`) are named there.

The reader is **`auirtdll.dll`**, the AUITK skin runtime of build A. It prints
`Only SKN file format is supported in this version.(%s)`,
`Exceeded MAX skin size, 64MB` and `AUI SKN: Load Time = %d ms, Skins = %d,
Map Address = %08x-%08x` (UTF-16, sec0 file `0x5db5f0` → VA `0x8cebc3f0`), and
it carries the libpng error strings (`PNG file corrupted by ASCII conversion`,
`Missing IHDR before IDAT`, `inflate 1.1.4 Copyright 1995-2002 Mark Adler`,
ASCII, sec0 VA `0x8cec2f4c` … `0x8cec6d69`). `auirtdll.dll` imports
`rasterizer_dll.dll` (119 `COREDLL`, 10 `ole32`, 7 `OLEAUT32`, 5
`rasterizer_dll`, 3 `AstLogApi`, 2 `DebugShellDll`), whose exports are the
font/raster engine (`DCW_Create`, `DCW_Raster`, `DCWx_initFontCache`). The
`.skn` is therefore an **AUITK skin file**: a tree of named UI objects plus a
pool of image assets, not a plain bitmap.

## The short answer

> **A skin is selected by the skin id 1..4
> (`CApi_GetSkinID`/`CApi_SetSkinID` in `commondll.dll`), which maps to the
> directory `\SystemSD2\SkinChange\001` … `\004` on the TFAT16 tail volume
> (each holds `Substance.skn`); the startup layout is the ROM file
> `\windows\ReleaseMain.skn`. Its images come from section 3 of the selected
> `.skn` (PNGs plus a shared zlib blob set), and from PNG resources built into
> ROM A that the same `auirtdll.dll` decodes with its bundled libpng.**

Evidence, sentence by sentence:

- **What is drawn:** `multiskin.dll` is only a COM shim —
  `Multiskin.Loader` / `ILoader` with `Load` / `Unload` / `Fixup` /
  `Decommit`, ProgID `Multiskin.Loader.1`, CLSID
  `{5099533B-7DBA-48D4-89B2-48C25CA9674E}` (sec3 ASCII, `VERIFIED`). The layout
  engine is `auirtdll.dll` (AUITK, libpng strings above); the file-path logic
  lives in **`commondll.dll`**, not in `multiskin.dll` (`VERIFIED`).
- **Which of the four slots:** `commondll.dll` (build B sec0, UTF-16,
  `VERIFIED`) holds four literals
  `\SystemSD2\SkinChange\001\Substance.skn` (VA `0x88323fb0`), `…\002\…`
  (`0x88324000`), `…\003\…` (`0x88324050`), `…\004\…` (`0x883240a0`) and the
  exports `CApi_GetSkinID` (rva `0x3c18`), `CApi_SetSkinID` (`0x3bf8`),
  `CApi_IsAvailableSpecifiedSkin` (`0x3730`), so skin id **1..4 → directory
  `001`..`004`**. The same module holds `SystemSD2\SkinChange\` and
  `SystemSD2\` prefix literals and the block of TFAT driver strings (`TFAT
  Error >> Request Reboot`, `AST_ERROR_CATEGORY_TFAT`,
  `__TFAT_HIDDEN_ROOT_DIR__`), so **`\SystemSD2` is the TFAT16 tail volume**
  of [`sd-card-layout.md`](sd-card-layout.md) (C-166).
- **What is on the card now:** every card carries only **slot `001`**; slots
  `002`..`004` have no directory (the literal exists, the folder does not).
  `CApi_IsAvailableSpecifiedSkin` is the gate that reports a slot absent
  (`VERIFIED` for the literals and the four on-disk facts).
- **The startup skin:** `\windows\ReleaseMain.skn` (VA `0x88322580`) is an
  8,224-byte `FILESentry` of ROM A (C-3522) with an object tree but **zero**
  image assets — it decides *layout* (which object sits where), not pixels.
- **Which parts draw which pixels:** the per-object records reference image
  ids (AUITK `SKINOBJTYPE_ImageObj`, `…Chip_Bitmap`, `…BitmapSource`,
  `…Picture`; the enum strings are in `auirtdll.dll` sec3). The images
  themselves are the section-3 PNGs of the `.skn` or built-in ROM PNGs; the
  records and the path are the **index**, the image bytes are the **pixels**
  (`OBSERVED`: the grammar is located, not executed).

Status per sentence: what-is-drawn `VERIFIED` (literals + exports + imports),
which-slot `VERIFIED` (four literals + four on-disk facts), card-contents
`VERIFIED`, startup skin `VERIFIED`, index→pixel mapping `OBSERVED`.

## The TFAT16 skin volume

The volume starts at the end of the FAT32 partition, offset **`0x1C8400400`**
(all four full images; C-166). Boot sector: OEM `MSWIN4.1`, type `TFAT16`,
512 B/sector, 64 sectors/cluster (**32768 B/cluster**), 2 FATs, 512 root
entries. EU2011/US2011 have 614,400 sectors (300 MiB, volume
314,572,800 B); EU2014/EU2016 have 612,352 (299 MiB, 313,524,224 B). The tail
is zero/`0xff` past the used clusters.

The root has one directory, `__TFAT_HIDDEN_ROOT_DIR__` (short `__TFAT~1`,
C-166/M1.36b), and inside it `SkinChange/001/substance.skn`. The rest of the
tree is TFAT placeholder churn: **3066 files named `DONT_DEL.NNN`** (`NNN` =
`000`..`999` and `:00`..`:21`) of size 0 and no cluster chain — markers, not
data. So the real payload is a **single file**.

File list (long names; cluster chains from the FAT):

| Path | Type | Size (B) | Clusters | Bytes on disk |
| --- | --- | ---: | ---: | ---: |
| `/__TFAT_HIDDEN_ROOT_DIR__` | dir | 0 | 2 | 65,536 |
| `/__TFAT_HIDDEN_ROOT_DIR__/SkinChange` | dir | 0 | 2 | 65,536 |
| `/__TFAT_HIDDEN_ROOT_DIR__/SkinChange/001` | dir | 0 | 2 | 65,536 |
| `/__TFAT_HIDDEN_ROOT_DIR__/SkinChange/001/substance.skn` | file (0x20) | see below | see below | see below |

Per card (the `.skn` in the card's TFAT volume):

| Card | `substance.skn` size (B) | Clusters | SHA-256 |
| --- | ---: | ---: | --- |
| EU2011 | 8,724,512 | 267 | `69e101c68796d6e35f1cc507dc0d1c8f22ff77d5b7bb6d67ee3d838578d58621` |
| US2011 | 7,208,992 | 221 | `dbb95a1fa3953ae5d6a0fe7112bab86ac46713de3ced3f5e1d3db50649532d56` |
| EU2014 | 12,951,584 | 396 | `d5a6f54cebcb38e8419ea366746a610dc0306c13baa6ff4661c578c2433db5e7` |
| EU2016 | 12,951,584 | 396 | `b7d5b26b492248a052f34b138d2e807e15c47b92b23a028349f598fb6817fd9e` |

Counts are for the whole TFAT volume: **3070 entries**, **3066 placeholder
`DONT_DEL.*`**, **4 real (3 dirs + 1 file)**, real-file bytes = the one `.skn`.
`python3 tools/skn_info.py tfat archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img`
reproduces the table above on all four images (C-6500, C-6501).

## `.skn` layout (AUITK skin)

All words are **little-endian** (`auirtdll` is SH-4). Five samples were parsed
in full: the four card `substance.skn` and ROM A's `ReleaseMain.skn` (8,224 B,
the only `FILESentry` of build A, C-3522). Build B's `UpdateNK.skn` shares the
magic but is a different AUITK generation (C-6509) — see the last section.

The container is a header, then an object tree, then 4-aligned section markers
whose `u32` tag is `0x0402000N`:

| Byte range | Field | Status |
| --- | --- | --- |
| `0x00..0x03` | magic `0x04020001` (section 1 tag) | known |
| `0x04..0x07` | fixed word `0x05006298` on all five samples | known (constant) |
| `0x08..0x0b` | declared object count: 65 (`ReleaseMain`), 36,905 / 36,649 / 42,434 (player) | known |
| `0x0c..0x0f` | second count: 8 (`ReleaseMain`), 17,520 / 17,532 / 19,117 (player) | unknown (OBSERVED) |
| `0x10..0x2f` | constant run: `01e00320 80000087 003ee000 ffffffff 00000001 00000000 004e0400 0000ffff` (player) / `…00200400 0000003d` (`ReleaseMain`) | OBSERVED (constant per generation) |
| `0x30..section-2` | **object records**: `[u24 size][u8 type][payload]`, size includes the 4-byte header | known |
| object `type 1` | `[u32 flags][u32 namelen][UTF-16LE name]` — UI object (`Screen`, `lay_COM_LevelN`, `act_…`, `frm_…`, `ctl_…`, `tbl_…`) | known |
| object `type 0` | 4-byte word, low 16 bits an enumerator (`0x4001/0x5001/0xd001/0x1001/0x2004…`) | OBSERVED |
| other types | 2,4,6,12,14,17,21,23,31,128; per-type payload bounds not decoded | unknown (only size/type counted) |
| section 2 | tag `0x04020002`, `u32 count`, then `count` `u16` values, then zero fill to the section-3 tag (which sits on the next 4 KiB boundary) | count known, meaning of the values unknown |
| section 3 | tag `0x04020003`, `u32 payload_len`, then **image assets** `[u32 len][bytes]`, each padded to 4 bytes | known |
| asset `PNG` | bytes start `89 50 4e 47 0d 0a 1a 0a` | known |
| asset `zlib` | bytes start `78 9c`; each decompresses to a plain 16-bit buffer | known (method = zlib) |
| section 4 | tag `0x04020004`, immediately followed by the 32-byte trailer | known |
| trailer `+0x00..0x0f` (last 32 B) | **part number**: `470-2826-34` (EU2011), `470-2820-33` (US2011), `470-3321-12` (EU2014), `470-3954-08` (EU2016); placeholder `XxX-yYyY-Zz` in `ReleaseMain.skn` | known |
| trailer `+0x10..0x1f` (last 16 B) | tag + variant: `SKINSK10ECNI.158` (`SKIN`, `SK`, generation, family, version) | known |

Notes from the parse:

- In `ReleaseMain.skn` the object walk lands **exactly** on the section-2
  marker (65 records, `0x30..0xbf0`) and the walk count equals the declared
  count (65). In the player `.skn` the same flat `[u24 len][u8 type]` grid also
  walks to the section-2 marker without a bad record: 36,849 (EU2011) /
  36,593 (US2011) / 42,378 (EU2014/16) records, i.e. exactly 56 fewer than the
  declared count on each card. The 56 missing records' payloads do **not**
  parse as a nested record chain (0 of 36,849 records do), so they are
  embedded objects counted without their own record header — a hypothesis, not
  decoded.
- Section 2's `u16` table is `count` values (175 / 174 / 185 for the player,
  25 for `ReleaseMain`); the header's `0x0c` word is not that count
  (17,520 / 8). Their meaning is open.
- The asset framing was checked end-to-end on all five samples: every asset
  decodes, the PNG count equals the `89 50 4e 47` signatures inside section 3,
  the asset walk stops exactly on the last asset's padding, and the rest of
  the section is zeros up to the section-4 tag.

### Image assets (section 3)

| Card | assets | PNG | PNG `IEND` verified | zlib | other | sec3 payload | declared |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EU2011 | 3120 | 3004 | 3004 | 109 | 7 | 4,559,626 | 4,579,328 |
| US2011 | 3116 | 3000 | 3000 | 109 | 7 | 4,554,059 | 4,575,232 |
| EU2014 | 3496 | 3380 | 3380 | 109 | 7 | 5,640,149 | 5,660,672 |
| EU2016 | 3496 | 3380 | 3380 | 109 | 7 | 5,640,149 | 5,660,672 |

All the PNG assets verify complete (each ends with `IEND\xaeB`\x82`, checkable
by flipping one `IEND` byte, which drops `png_complete` by one without touching
the PNG count). The `other=7` assets are raw **RGB565-ish pixel runs** (16-bit
`RRRRRGGGGGGBBBBB` values such as `0xefbd`, `0x2404`, `0x03ff`, with
`0x80/0x00` in the high byte of the final pairs) — small gradient/line
patterns, not PNG and not zlib. The **109 zlib assets decompress on all four
cards to the same 2,536,494 bytes** (same SHA-256 of the concatenation), a
shared UI mask/colour resource.

On EU2011 the section-3 payload is 4.56 MB beside a 4.14 MB object tree
(section 3 starts at `0x3f4000`), and the first PNG's `IHDR` is 282×170.
`ReleaseMain.skn` has **no** assets (`assets=0`): its section 3 is 4,096
declared bytes of zeros — a manifest-only startup skin.

## How the reader finds its inputs (strings + imports)

| Evidence | Module / VA | Claim |
| --- | --- | --- |
| `\windows\ReleaseMain.skn` | `commondll.dll` build B sec0, VA `0x88322580` | C-6502 |
| `\SystemSD2\SkinChange\001..004\Substance.skn` | `commondll.dll` build B sec0, VAs `0x88323fb0`/`0x88324000`/`0x88324050`/`0x883240a0` | C-6503 |
| `CApi_GetSkinID` rva `0x3c18`, `CApi_SetSkinID` `0x3bf8`, `CApi_IsAvailableSpecifiedSkin` `0x3730` | `commondll.dll` build B exports | C-6505 |
| `Only SKN file format is supported…`, `Exceeded MAX skin size, 64MB`, `AUI SKN: Load Time` | `auirtdll.dll` sec0 VAs `0x8cebc3f0`/`0x8cebc4a8`/`0x8cec0b18` | C-6506 |
| libpng/zlib strings (`Missing IHDR before IDAT`, `inflate 1.1.4…`) | `auirtdll.dll` sec0 VAs `0x8cec2f18` … `0x8cec6d69` | C-6506 |
| `Multiskin.Loader` / `ILoader` / `Load` / `Fixup` / `Decommit`, CLSID `{5099533B-7DBA-48D4-89B2-48C25CA9674E}` | `multiskin.dll` sec3 ASCII, VA `0x8e1d5af4` | C-6507 |

`multiskin.dll` imports only `COREDLL` (64), `ole32` (7), `OLEAUT32` (9) and
exports `DllGetClassObject` — it is the COM loader
(`DllGetClassObject` → `Multiskin.Loader`), and the path/ID work lives in
`commondll.dll`. `commondll.dll` is in build B (kernel) and build C (test mode)
but **not** as a build A module — the apps import it from the kernel side,
which is why its strings must be searched with `--image-start 0x3e00200` /
`0x5200200`, not `0x200200`.

## Cross-card (same three places, sizes and hashes only)

**1. ROM A `ReleaseMain.skn`** — 8,224 B on every card (stored, not
compressed, extracted from `FILESentry`), trailer differs only by
part-number/variant:

| Card | SHA-256 | trailer | objects | assets |
| --- | --- | --- | ---: | ---: |
| EU2011 | `fae151ac7232bab189fb29769ac0fdc2813330de2652c10214f4136910b9129a` | `SKINSK10ECNI.158` | 65 | 0 |
| US2011 | `16c998d474458bba57f862e753da2fc827149bf075d64dbe1cf885f7fc61a1ab` | `SKINSK10NBNI.147` | 65 | 0 |
| EU2014 | `890f24c3e18ee2ecfb358f2539fc320fa33a8188ca617b0dd8a8ef0255a46181` | `SKINSK12ECNI.100` | 67 | 0 |
| EU2016 | `07c92ff986633092e46e4d41faa905ea6088b730062b917f8ebe539e35adafe9` | `SKINSK12ECNI.063` | 67 | 0 |

(`ECNI`/`NBNI` = EU/US family; `158`/`147`/`100`/`063` = version token; `SK10`
vs `SK12` = AUITK generation, matching the 3004 vs 3380 PNG counts.)

**2. TFAT16 `substance.skn`** — table above (8.7 / 7.2 / 13.0 / 13.0 MB).

**3. Build B `UpdateNK.skn`** — a *different* skin in all four (compressed
`FILESentry`): EU2011/US2011 real 1,966,080 B (comp 809,659, SHA-256
`6f17c91b…4b652`), EU2014/EU2016 real 2,105,344 B (comp 862,415; these two
decompress `FAIL` in `nk_decomp.py`, so only the sizes are known). It shares
the `0x04020001` magic and the `0x04020002/3/4` markers but has a zero
part-number/trailer field, `0x08 = 432`, and **0 PNGs** — an updater skin of a
different generation, not a sixth comparable sample (C-6509).

The FAT32 `OPNG/` folder (one file per card,
`OPNG/MKR_OPNG/NISSAN/OIXXEVNI.001` = `OIXXNVNI.001` on US, 1,606,224 B;
EU2016 also has a 4,096-byte `._OIXXEVNI.001` AppleDouble sidecar) is **not**
part of the `.skn`: its name (MKR = maker) and its FAT32 location put it
outside the skin container. ROM A holds **1,234** PNG signatures between
`0x200200` and `0x3e00200` of the head (1,228 `IEND` endings; 89 of them in
`0xdc0000..0xe20000`), i.e. the built-in images `auirtdll` decodes with its
bundled libpng (C-6506). Which object id maps to which ROM image is
`HYPOTHESIS` here; the correlation is shown, the mapping is not decoded.

## What this enables (and what it does not)

- The pixels of the **player** skin are the §3 PNGs inside `substance.skn`;
  same-size replacement is structurally possible (asset length is its own
  `u32`, so a same-length PNG keeps every offset). This is M4.59's input.
- `ReleaseMain.skn` is 8 KB of pure object tree: it decides *layout*
  (which object sits where, at which image id), not pixels; patching it changes
  placement, not appearance.
- **Not** verified: that `auirtdll`/`commondll` accept a regenerated `.skn` at
  runtime (L3/L4), the meaning of object types other than 0/1, the second
  header count and the section-2 `u16` table, the 56 counted-but-unrecorded
  objects, and whether the unit rejects a trailer whose part number differs
  from the card (the part number is the same string the version database
  reports).
