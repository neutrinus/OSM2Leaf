# EXP-2026-11-06-H6: `drstr.md` ↔ `MMAIN001.DAT` reconciliation and `tools_ze0` provenance

- **Status:** done
- **Date:** 2026-11-06
- **Sample:** EU 2011 card image
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
  SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-1720–C-1726 (block C-1720–C-1729; rows not added to
  `claims.md` here — H6 owns docs only)
- **Supersedes:** the FAT-root-directory interpretation of `MMAIN001.DAT` in
  `EXP-2026-11-05-M4.5` (claim block C-930–C-939, no ledger rows)
- **Superseded by:** none

## Question

`TODO.md` H6 asks for two contradictions to be removed: (a) `drstr.md` places a
per-language code list at `0x18c` and a three-table descriptor at `0x1ac` in
`MMAIN001.DAT`, while `EXP-2026-11-05-M4.5` reports those offsets inside FAT
directory records; (b) `tools/ze0-viewer/tools_ze0/PROVENANCE.md`, `setup.sh`
and the `AGENTS.md` sentence describe the vendored tile tools in three
incompatible ways. Which side of (a) do the bytes support, and what is the real
provenance/regeneration path for (b)?

## Hypothesis

None / exploratory for (a): the task text assumed `drstr.md` was the stale side.
For (b): the checked-in `tools_ze0/` directory is what `harness.py` imports and
`setup.sh` has never produced it.

## Inputs

| Item | Value |
| --- | --- |
| Image | `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (7.5 GiB) |
| Image SHA-256 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| Partition | FAT32, start byte `0x06400400` (LBA 204802), 512 B sectors, 128 sectors/cluster (64 KiB), 32 reserved sectors, 2 FATs × 900 sectors → data start `0x064e5400` |
| Root directory | cluster 2 = file offset `0x064e5400` |
| `MMAIN001.DAT` | logical size 4,096 B, live root entry at root offset `0x4e0`, first cluster `0x10002` → file offset `0x1064e5400` (4,400,763,904) |
| `DRSTR001.DAT` | logical size 11,968 B, live root entry at root offset `0x660`, first cluster 29686 → file offset `0x7a425400` (2,051,167,232) |
| Tools | `curl -r`, Python 3 stdlib, GNU patch 2.8, `git apply` |

File hashes (of the 4,096/11,968 bytes read from the ranges above):

| Object | SHA-256 |
| --- | --- |
| `MMAIN001.DAT` (cluster `0x10002`) | `240e7c9774197fff0ea85276d463658d1291f4147970ccd5fdec60ffd23e9a05` |
| FAT root directory, first 4,096 B | `fe24bbc82f20bd32633c08086baa3267a5761a6eae4c682f2a20fd668048a5aa` |
| `DRSTR001.DAT` (cluster 29686) | `2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6` |

The third hash equals the one published in `drstr.md`; the second equals the
"extracted file" hash quoted in `EXP-2026-11-05-M4.5`.

## Method

Ranged reads of the published image (no full download, no vendor bytes kept in
the repository; only offsets, hashes and short header bytes are recorded):

```bash
IMG=https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
# BPB and data start
curl -sS -r 104858624-104861183 -o bpb.bin "$IMG"        # 0x06400400 + 2560 B
# root directory (cluster 2)
curl -sS -r 105796608-105862143 -o root.bin "$IMG"       # 0x064e5400 + 64 KiB
# MMAIN001.DAT, cluster 0x10002
curl -sS -r 4400763904-4400767999 -o mmain.bin "$IMG"
# DRSTR001.DAT, cluster 29686
curl -sS -r 2051167232-2051179199 -o drstr.bin "$IMG"
```

```python
# BPB fields used (from bpb.bin)
#  0x0b 512 B/sector, 0x0d 128 sectors/cluster, 0x0e 0x0020 reserved sectors,
#  0x10 2 FATs, 0x24 900 sectors/FAT, 0x2c root cluster 2
# data_start = 0x06400400 + (32 + 2*900) * 512 = 0x064e5400

# FAT root directory: 32-byte entries from 0x00 to the 0x00 end marker
# first cluster = u16 at +0x1a | (u16 at +0x14) << 16   (FAT32: lo, then hi)

# MMAIN001.DAT container at 0x1ac: 00, n_tables, then per table
#   (id, n_entries) and n_entries * (level:u8, kind:u8, count:u16 BE)

# DRSTR001.DAT: 40-byte nodes from 0x0000, root listing offset at node+0x24
```

```bash
# tools_ze0 provenance checks
cd tools/ze0-viewer
ls tools_ze0/*.py | wc -l                     # 46
git apply --stat ze0-tools.patch              # 6 files, +296/-40
grep -n "sys.path.insert" harness.py          # inserts HERE/tools_ze0
# path-selection control for setup.sh's patch step, synthetic scratch repo:
#   tools/x.py = "a", patch headers --- a/tools/x.py / +++ b/tools_ze0/x.py
git apply -p1 p.patch                         # -> error: tools_ze0/x.py: No such file
patch -p2 < p.patch                           # -> patching file x.py (GNU patch 2.8)
```

## Observations

### FAT root directory (the object M4.5 read)

- `0x000`: volume-label entry `QSD-309-101`, attr `0x08`.
- `0x020`–`0x67f`: 51 further 32-byte entries; `0x680` holds the `0x00` end
  marker; zero fill follows.
- 12 entries are live (not `0xE5`), from `0x4e0` to `0x660`: `MMAIN001.DAT`,
  `BICON001`, `MAPAL001`, `OPNG`, `RDSTM001`, `REFER001`, `REFER002`,
  `SPEECH`, `TMC`, `VER_INFO`, `CMP.LST`, `DRSTR001.DAT`. 39 entries start
  with `0xE5`.
- Every number in `EXP-2026-11-05-M4.5` matches this object: label at `0x00`,
  "51 records of 32 bytes from `0x20`", 12 live, `DRSTR001.DAT` at `0x660`,
  39 deleted.
- `sha256(root.bin[0:4096])` = `fe24bbc82f20bd32633c08086baa3267a5761a6eae4c682f2a20fd668048a5aa`,
  exactly the hash M4.5 published as the extracted `MMAIN001.DAT`.

### The live `MMAIN001.DAT` entry and file

- Entry at root offset `0x4e0`: name `MMAIN001DAT`, attr `0x20`, cluster high
  word `0x0001` (at `+0x14`), cluster low word `0x0002` (at `+0x1a`) →
  first cluster `0x10002`; size 4,096.
- The file at `0x064e5400 + (0x10002-2)*0x10000` is 4,096 bytes,
  SHA-256 `240e7c97…`, and starts with UTF-16BE `CLARION`, `HITACHI`,
  `CLA-NAVI05-01`, `FORMAT VERSION X08-02-00`, `DATA VERSION 11/06/27/01`,
  `V05.00.00` (the common header, C-010).
- `0x180`: `ff ff 24 ff 12 c0 05 00 fb 50 0f f0` (C-011).
- `0x184` big-endian `i16` × 4: `0x12c0 0x0500 0xfb50 0x0ff0` = 4800, 1280,
  −1200, 4080; the same pair reappears at `0x5d0` as `05 00 fb 50 0b 0b`.
- `0x18c`: `05 04 02 07 0a 06 08 14`; `0x194`: `3f` × 12; `0x1a0`: `ff` × 12.
- `0x1ac`: `00 03` (lead byte, 3 tables), table `01` with 6 entries
  (`06 80 00 01`, `05 90 00 01`, `04 91 00 01`, `03 91 00 2d`,
  `02 91 00 8a`, `01 92 06 b5`), table `02` with 4, table `04` with 1;
  `00` terminator at `0x1e0`. 6 + 4 + 1 = 11 tuples.
- The published header sample in `docs/format/file-header.md` (`0x180`–`0x1b7`:
  prefix, `0x18c` list, `3f`/`ff` runs, `00 03 01 06 06 80 00 01 05 90 00 01`)
  reproduces byte-for-byte on this file, so the header work and the M4.5
  record were reading different objects.
- The tail is not described here; `0x3ae`–`0x4ac` is `ff`, `0x5cc` is `80`,
  and a 6-byte-slot table starts at `0x800`.

### `DRSTR001.DAT`, same card

- Read through its live root entry (cluster 29686, 11,968 B): SHA-256
  `2b7f2fb8…` as documented; node 0 name `/`, `u32` at `0x0000` = `0x2f`;
  root node `entry_count` 11 at listing offset `0x640`.
- Root listing values: `MMAIN001.DAT` = 4,096 (matches the file), `MAPAL001`
  directory entry count 46, `BICON001.DAT` 114,598.
- The FAT root directory has one live entry the DRSTR root node lacks:
  `DRSTR001.DAT` itself (C-163).
- The M3.4 raw-image "unrelated FAT/data hit" for `DRSTR` at `0x064e5a60` is
  this directory entry: root cluster `0x064e5400` + entry offset `0x660`.

### `tools_ze0`

- `tools/ze0-viewer/tools_ze0/` holds 46 `.py` modules plus `PROVENANCE.md`;
  `harness.py` inserts `HERE/tools_ze0` at `sys.path[0]` and imports
  `clarion_bg`, `clarion_rd`, `clarion_tile`, `tile_scan` from it.
- `git apply --stat ze0-tools.patch`: 6 files changed, 296 insertions,
  40 deletions (`bg_decode`, `clarion_bg`, `clarion_tile`, `inflate_tile`,
  `tile_grid`, `tile_scan`).
- `setup.sh` clones into `vendor/osm2clarion` (git-ignored) and creates the
  `tools_ze0` symlink only `if [ ! -e tools_ze0 ]` — false in a checkout.
- Its patch step `git apply -p1 ze0-tools.patch` targets the new-side path
  `tools_ze0/<file>` inside the clone. Reproduced with a three-line synthetic
  patch of the same shape: `git apply -p1` exits with
  `error: tools_ze0/x.py: No such file or directory`; `patch -p2` applies the
  same patch to `x.py`.
- `vendor/` is absent from the checkout; `git status` is clean with the real
  `tools_ze0/` present.

## Interpretation

- **FACT:** `EXP-2026-11-05-M4.5` read the **FAT32 root directory**, not
  `MMAIN001.DAT`: the published file hash equals the root directory's first
  4,096 bytes, and every record count matches. The root entry's first cluster
  is `0x10002`; "cluster 2" is the root directory, so taking only the low
  cluster word returns the root directory. That is the mechanism of the
  mis-read (C-1721, C-1722).
- **FACT:** the real `MMAIN001.DAT` is a 4,096-byte common-header file with the
  `0x180` descriptor block, the `0x18c` 8-byte code list and the `0x1ac`
  three-table descriptor (C-1720). `drstr.md`'s reading is therefore
  re-verified, not stale; the retraction belongs to the M4.5 interpretation.
- **FACT (control):** the same method reproduces `drstr.md`'s DRSTR SHA-256,
  its 11-entry root node and the `u32 0x2f` sentinel, so the ranged reads and
  cluster arithmetic are correct on a second file.
- **OBSERVED:** the `0x1ac` counts are the per-level sums over the tile set
  (C-164, 11/11) and an independent builder writes them that way
  (`tools_ze0/make_mmain.py`); the `0x184`/`0x5d0` bounds read as the EU
  extent (C-1724).
- **HYPOTHESIS:** `0x18c` is a language/volume code list (C-551). No code →
  language mapping exists in this repo; the card's list has 8 codes.
- **UNKNOWN:** `0x1e0`–`0x1000` of `MMAIN001.DAT` (constants at `0x3ae`,
  `0x5cc`, `0x5d0`, slot table at `0x800`); firmware handling of `MMAIN001.DAT`
  (no code reference recorded).
- **FACT:** `setup.sh` as shipped cannot produce `tools_ze0/`; the checked-in
  copy is authoritative and the patch is the audit trail (C-1725).

## Claims

Rows to add to `docs/research/claims.md` by the ledger task (H1); H6 does not
edit the ledger.

| ID | Claim | Status | Confidence | Evidence / Supersedes |
| --- | --- | --- | --- | --- |
| C-1720 | `MMAIN001.DAT` on the EU 2011 card is a 4,096-byte file at first cluster `0x10002` (SHA-256 `240e7c97…`) that starts with the common 512-byte header (UTF-16BE `CLARION` … `V05.00.00`) and carries the `0x180` descriptor block. | VERIFIED | H | EXP-2026-11-06-H6; ranged read of the published image; C-010/C-011 re-verified |
| C-1721 | The object `EXP-2026-11-05-M4.5` analysed as `MMAIN001.DAT` (SHA-256 `fe24bbc8…`) is the first 4,096 bytes of the FAT32 root directory: it starts with the volume-label entry `QSD-309-101` and holds 51 32-byte entries at `0x20`–`0x67f`. The `0x18c`/`0x1ac` "inside FAT records (`ER_INFO`)" observation applies to the root directory, not to the file. | VERIFIED (retraction) | H | EXP-2026-11-06-H6; supersedes the FAT-log interpretation of EXP-2026-11-05-M4.5 (block C-930–C-939, no ledger rows); C-037 unaffected |
| C-1722 | The live `MMAIN001.DAT` root entry is at root offset `0x4e0` with first cluster `0x10002` (high word `0x0001` at `+0x14`, low word `0x0002` at `+0x1a`), size 4,096; FAT32 cluster 2 is the root directory, so reading only the low cluster word returns the directory. | VERIFIED | H | EXP-2026-11-06-H6; control for C-1721 |
| C-1723 | `MMAIN001.DAT`'s `0x1ac` container holds three tables with ids `01`/`02`/`04` and 6/4/1 entries = 11 `(level, kind, count)` tuples, terminated at `0x1e0`; the `0x18c` list is `05 04 02 07 0a 06 08 14`. | OBSERVED (VERIFIED structure) | H | EXP-2026-11-06-H6; re-verifies C-548/C-550/C-551; counts per C-164 |
| C-1724 | `MMAIN001.DAT` `0x184` (and `0x5d0`) hold big-endian `i16` arc-minute bounds: 4800, 1280, −1200, 4080, i.e. the EU database extent; semantics OBSERVED, not tied to firmware. | OBSERVED | M | EXP-2026-11-06-H6; `tools_ze0/make_mmain.py` packs the same fields |
| C-1725 | `tools/ze0-viewer/tools_ze0/` is the authoritative copy imported by `harness.py` (46 modules, pin `07fbf78d…` + `ze0-tools.patch`, 6 files/+296/−40). `setup.sh` cannot regenerate it as written: its symlink step is guarded by the existing real directory and its `git apply -p1` targets the patch's `tools_ze0/…` new-side paths inside the clone. | VERIFIED (tool/process) | H | EXP-2026-11-06-H6; `docs/format/ze0-tools.md` |
| C-1726 | The FAT root directory has 12 live entries; the DRSTR root node has 11 (the same list without `DRSTR001.DAT`, C-163); the third `DRSTR` string in the M3.4 raw scan (`0x064e5a60`) is that directory entry. | VERIFIED | H | EXP-2026-11-06-H6; EXP-2026-11-06-M3.4 |

## Conclusion

- `docs/format/drstr.md`: the `MMAIN001.DAT` section now states the real
  4 KiB header layout with per-field status and claim IDs, and carries an
  explicit retraction of the FAT-log reading. Also corrected: the static
  filename-table range (`0x00179cf8`…`0x00179d18`), the raw `DRSTR` scan result
  (three strings, the third being the directory entry), the claim that
  `MMAIN001.DAT` is opened by the media-manager code (no reference recorded),
  and the root-listing note (11 DRSTR entries vs 12 FAT entries).
- New `docs/format/ze0-tools.md`: what `tools_ze0/` is, the pin and patch, which
  copy the harness imports, what `setup.sh` really does, the verified
  regeneration/audit recipe, and the keep-in-step rule. `PROVENANCE.md` and
  `setup.sh` were **not** edited (H6 owns docs only); the corrected process is
  in the new document.
- Not edited, reported to the coordinator: `AGENTS.md` ("`tools/ze0-viewer/`
  clones a pinned `osm2clarion` via `setup.sh`"), `tools/README.md` (same
  story), `tools/mmain.py` (parses the FAT root directory, not
  `MMAIN001.DAT`) and `TODO.md`.

## Follow-ups

- [ ] Re-scope `tools/mmain.py` (or add `tools/mmain_header.py`) to the real
      `MMAIN001.DAT`: header identity, `0x184`/`0x5d0` bounds, `0x18c` codes,
      `0x1ac` three-table sums; keep the root-directory parser under a name
      that says "root directory".
- [ ] Fix `setup.sh`'s patch step (new-side paths `tools_ze0/…`, `--directory`
      or a regenerated patch) and correct `PROVENANCE.md`'s "regenerate"
      sentence; optionally collapse the duplicate `vendor/` story.
- [ ] Correct the `AGENTS.md` and `tools/README.md` sentences (exact text in
      the H6 report).
- [ ] Map the `0x18c` codes to languages (needs speech/volume data or a
      mutation test) and decode `0x1e0`–`0x1000` of `MMAIN001.DAT`.
- [ ] Check `0x184`/`0x1ac` on 2014/2016 cards with `diff_years.py`
      (`MMAIN001` level-table row) to see whether only the bounds and counts
      move.
- [ ] Add C-1720–C-1726 rows to `claims.md` (ledger task H1) and mark the M4.5
      block with `Superseded by: C-1720/C-1721`.
