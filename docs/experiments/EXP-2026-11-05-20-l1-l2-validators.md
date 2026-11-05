# EXP-2026-11-05-20: L1/L2 validators for the offline feedback loop

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-328, C-329, C-330, C-331
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the offline layers L1 (whole-card structure) and L2 (semantic/golden
round-trips) be implemented and made to pass on the reference sample without
any hardware?

## Hypothesis

Yes for structure, preserved-stream round-trips and decoded geometry.  These
layers cannot prove that the unit accepts the card; that remains L4.

## Inputs

| Item | Value |
| --- | --- |
| Image | `/home/marek/projekty/leafre-work/leaf2011.img` |
| SHA-256 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| Extracted root | `/home/marek/projekty/leafre-work/root` |
| Tools | `tools/cardcheck.py`, `tools/l2check.py`, `tools/selftest.py` |
| Viewer | pinned `osm2clarion` at `07fbf78`, patched by `tools/ze0-viewer` |

## Method

```bash
python3 tools/selftest.py
python3 tools/cardcheck.py --root /home/marek/projekty/leafre-work/root
python3 tools/cardcheck.py --image /home/marek/projekty/leafre-work/leaf2011.img \
    --hash --expect-sha256 105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307
python3 tools/l2check.py --root /home/marek/projekty/leafre-work/root
python3 tools/l2check.py --root /home/marek/projekty/leafre-work/root \
    --update-golden tools/golden/eu2011.json \
    --image /home/marek/projekty/leafre-work/leaf2011.img
```

## Observations

### L0

`tools/selftest.py` -> `selftest: OK`.  The new synthetic tests cover the level
table, common header, LFN directory entry, `.cmp` decode and logical listing.

### L1 on the extracted root

```
tree        files=480 dirs=39 bytes=5173965667
headers     files=66 ok=66
cmp         pairs=194 logical=2390610176 stored=1421900190 headers_ok=194
drstr       nodes=40 table_end=1600 entries=324 dirs=40 files=285
mmain       tiles=46 rows=11 ok=11
version     hdd_size=72
RESULT: PASS
```

Wall time: 8.2 s.

### L1 on the raw image

Same tree/cmp/DRSTR/MMAIN/version results, plus:

```
fat         partition_offset=104858624 partition_bytes=7549747200
            cluster_bytes=65536 reserved_sectors=32 fat_count=2
            fat_size_sectors=900 root_cluster=2 label=QSD-309-101
version     image_copy=identical
sha256      105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307
RESULT: PASS
```

Wall time: 17.8 s without hashing; 24.2 s with `--hash`.

### L2

```
census            files=480 dirs=39 bytes=5173965667
files             expected=17
drstr_roundtrip   size=11968
cmp_roundtrip     pairs=194 ok=194
tile_roundtrip    tiles=5
tile_semantic     B28R070R=7790, B30R060R=15844, B58R070R=480, B30R048R=16684
tile_mutation     removed=1 added=1 changed_vertices=1
refer_mutation    validate=PASS
RESULT: PASS
```

Wall time: 10.2 s.  The golden profile records the image hash, tree census,
`DRSTR`/`MMAIN` hashes, 17 file hashes and four geometry digests.

### LFN checksum observation

For 387 of 390 short directory entries in `REFER001`, the LFN checksum byte
does not match the standard FAT short-name checksum (`_lfn_checksum`).  The
sequence numbers are contiguous and the reconstructed names match the tree
extracted by `7z`/`mtools`.  `tools/cardcheck.py` therefore trusts a
contiguous LFN sequence and falls back to the short name when the sequence is
broken.

### Tile mutation regression

`tools/ze0-viewer/ze0_mutate.py` originally called `clarion_bg.build_record()`
in non-strict mode.  For the selected background record the builder returned
the source bytes, so the "mutation" was a no-op: `compare-tiles` reported zero
diff and `harness.py selftest` failed.  The tool now selects a record that the
builder reproduces exactly, sets `strict`, and refuses a mutation that does
not change the record.  After the fix, `tile_mutation` reports one removed and
one added feature with exactly one changed vertex.

## Interpretation

- **FACT:** L1 passes on both the extracted root and the raw image; the raw
  image also matches its reference SHA-256.
- **FACT:** L2 passes: DRSTR and all 194 `.cmp` pairs preserve-round-trip,
  five target tiles rebuild byte-identically, and the four geometry digests
  match the stored profile.
- **OBSERVED:** the card's LFN checksums differ from the standard algorithm;
  sequence-based names agree with independent extraction.
- **OBSERVED:** the tile mutation test was silently no-op until the builder was
  forced to strict mode.
- **HYPOTHESIS:** L1/L2 catch most structural and semantic mistakes, but they
  cannot prove unit acceptance, SD-lock handling, rendering or routing.

## Conclusion

The offline feedback loop now has a runnable L1 and L2.  The golden profile is
small (hashes/counts only) and contains no vendor data.  Nothing about the
on-disk format changed; the new claims describe the validators and the two
observations above.

Still open: an optional OSM comparison in L2, L3 function-level emulation and
L4 bench HIL.

## Follow-ups

- [ ] Add an optional OSM comparison to L2 (`compare_osm.py`).
- [ ] Run L1/L2 on the US 2011 dump when it arrives.
- [ ] Use the golden profile as the regression target for the OSM compiler.
- [ ] Keep the original card read-only; L4 remains the acceptance layer.
