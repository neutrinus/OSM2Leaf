# EXP-2026-11-05-02: Same-length POI rename in REFER001

- **Status:** done offline; hardware pending
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-145, C-146, C-147
- **Supersedes:** none
- **Superseded by:** none

## Question

Can we make a minimal, visible change to a `REFER001` database without changing
any size, pointer, `DRSTR001.DAT` entry or activation file — and validate it
offline?

## Hypothesis

Names are plain Latin-1 text inside inner zlib pages. Replacing one name with
another of the **same byte length**, recompressing one page and one outer
stream, should produce a valid file with no structural changes.

## Inputs

| Item | Value |
| --- | --- |
| `POINT032.DAT.cmp` | `1dac3ae6d330414686a69df6749b3bb8b563029ce00ecefad1bba02170f1bba7` |
| `POINT032.DAT.ind` | `5108c90b7d9aaab2dfe9b8486f59f1f99161937a6f92cb7a14e47e25a771ca9e` |
| `DRSTR001.DAT` | `2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6` |
| Logical size | 20,224 bytes |
| Page | `0x4200` |
| Old text | `VATICAN MUSEUM` |
| New text | `OSM2LEAF PROBE` (same 14 bytes) |

## Method

```bash
python3 tools/scan_refer_names.py REFER001/POINT032.DAT.cmp --min 8
python3 tools/mutate_refer_poi.py REFER001/POINT032.DAT.cmp \
    REFER001/POINT032.DAT.ind /tmp/mut \
    --page 0x4200 --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE"
python3 tools/validate_mutation.py REFER001 /tmp/mut POINT032.DAT \
    --page 0x4200 --drstr DRSTR001.DAT --inner-page 0x4200
python3 tools/cmpind.py verify /tmp/mut
```

No-op control: recompress the same page without changing bytes and compare
the decoded payload (expected 0-byte diff).

## Observations

| Check | No-op control | Rename |
| --- | --- | --- |
| logical `.DAT` | 20,224 → 20,224 | 20,224 → 20,224 |
| `.cmp` | 5,143 → 5,110 | 5,143 → 5,119 |
| inner payload diff | 0 bytes | 14 bytes |
| changes outside page `0x4200` | 0 | 0 |
| `DRSTR` entry | 20,224 | 20,224 unchanged |
| `cmpind.py verify` | 1/1 OK | 1/1 OK |

`validate_mutation.py` prints:
`PASS: same logical size, changes confined to one page, DRSTR untouched`.

## Interpretation

- **FACT:** REFER001 display names are plain Latin-1 inside inner zlib pages.
- **FACT:** a same-length rename keeps the logical size and DRSTR entry.
- **FACT:** the changed bytes are confined to one page.
- **UNKNOWN:** whether the unit accepts recompressed data or a changed name.

## Conclusion

The offline side is proven; the hardware side is not. The first hardware test
must be the no-op control, then the rename. The EU sample is not the owner's US
card, so a hardware test must run on the US dump (or an EU car) to be
interpretable.

## Follow-ups

- [ ] No-op recompression control on a spare US card.
- [ ] Same-length rename on a spare US card.
- [ ] If the unit rejects recompressed data, pivot to a byte-preserving edit
  in an uncompressed outer file (`REFER002`).
- [ ] See [`docs/research/minimal-change.md`](../research/minimal-change.md) for
  the full falsification matrix.
