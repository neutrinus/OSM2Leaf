# Tools

Small, standard-library Python 3.10+ scripts for inspecting Leaf ZE0 map data.
None of them need vendor files to be present unless you ask them to inspect
one. All are read-only by default.

## `cmpind.py`

Decode and verify `REFER001/*.DAT.cmp` + `*.DAT.ind` containers.

```bash
# Print the index header and chunk offsets
python3 tools/cmpind.py info REFER001/ADDRE001.DAT.ind

# Decompress one file
python3 tools/cmpind.py extract REFER001/ADDRE001.DAT.cmp -o /tmp/ADDRE001.DAT

# Verify every pair in a directory
python3 tools/cmpind.py verify REFER001
```

Expected output of `verify` on the EU 2011 image:

```
checked   194 pair(s)
ok        194
failed    0
logical   2390610176 bytes
stored    1421900190 bytes
```

## `leafimg.py`

Inspect a raw SD card image and the common 512-byte map-file header.

```bash
python3 tools/leafimg.py info /path/to/leaf2011.img
python3 tools/leafimg.py header MAPAL001/B28R070R.DAT
```

`info` reads the MBR, finds FAT partitions, and prints the volume label,
cluster size and root cluster. `header` decodes the UTF-16BE strings and the
binary block at `0x180`.

## `drstr.py`

Parse `DRSTR001.DAT` into nodes and directory listings.

```bash
python3 tools/drstr.py parse DRSTR001.DAT
python3 tools/drstr.py parse DRSTR001.DAT --json
```

The parser stops at the first listing, because the node table ends where the
first 32-byte entry begins.

## `lctbl_names.py`

Decode the `LCTBL001.DAT` catalog and compressed name database.

```bash
python3 tools/lctbl_names.py verify LCTBL001.DAT
python3 tools/lctbl_names.py catalog LCTBL001.DAT
python3 tools/lctbl_names.py names LCTBL001.DAT --sample 10
```

`verify` on the EU 2011 image prints `streams 517 / plain 11481060 /
records 328628 / OK`.

## `rdstm_scan.py`

Inspect `RDSTM001.DAT`: block layout, negative zlib result, and the 2-byte
codes shared with the LCTBL catalog.

```bash
python3 tools/rdstm_scan.py layout RDSTM001.DAT
python3 tools/rdstm_scan.py zlib RDSTM001.DAT --bruteforce
python3 tools/rdstm_scan.py codes RDSTM001.DAT --lctbl LCTBL001.DAT
```

## `mesh_grid.py`

Map `MAPAL001/BxxRyyR.DAT` names to latitude/longitude (B/R are hex).

```bash
python3 tools/mesh_grid.py list MAPAL001
python3 tools/mesh_grid.py matrix MAPAL001
python3 tools/mesh_grid.py cell B48R058
```

## `selftest.py`

Runs synthetic tests for `cmpind.py` and `drstr.py` without any vendor data:

```bash
python3 tools/selftest.py
```

## Conventions

- Read-only. Scripts that write require an explicit output path.
- No hard-coded absolute paths.
- Evidence and format notes live in [`../docs/format/`](../docs/format/); claim
  status lives in [`../docs/research/claims.md`](../docs/research/claims.md).
