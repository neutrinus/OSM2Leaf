# EXP-2026-11-05-35: US 2011 card validation and validator fixes

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** `archive/leaf_2011_usa_sddump.img`
  `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383`
- **Claims:** C-070, C-127
- **Supersedes:** none
- **Superseded by:** none

## Question

How does the current validator behave on the owner's US 2011 SD dump, and what
changes are needed for a valid North America card?

## Hypothesis

The US dump uses the same ZE0 format family as the EU 2011 image, but with
market-specific top-level data, shard counts and tile coverage. The validator
may fail on market-specific names or extraction order rather than on card
corruption.

## Inputs

| Item | Value |
| --- | --- |
| Image | `archive/leaf_2011_usa_sddump.img` |
| SHA-256 | `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383` |
| Size | 8,057,257,984 bytes |
| FAT label | `QSD-301-103` |
| Extracted root | `/tmp/opencode/us-root` |

## Method

```bash
python3 tools/cardcheck.py --image archive/leaf_2011_usa_sddump.img
python3 tools/l2check.py --root /tmp/opencode/us-root --no-golden \
  --ignore-dump-artifacts --no-tiles --skip-mutation
TMPDIR=/home/marek/.cache/l2tmp python3 tools/l2check.py \
  --root /tmp/opencode/us-root --no-golden --ignore-dump-artifacts \
  --no-tiles --skip-mutation
python3 tools/cmpind_writer.py verify /tmp/opencode/us-root/REFER001
```

## Observations

Initial `cardcheck.py --image` failed:

- missing top-level `TMC` (US has `XMD`);
- `DRSTR` listed `bsatbldata.da`, not on card;
- `LTNTBL.DAT` on card but not in `DRSTR`.

The failures are validator limitations:

- `XMD` is a market-specific top-level directory;
- `bsatbldata.dat` is 14 characters, but the DRSTR name field stores only 13
  bytes, so it is stored as `bsatbldata.da`;
- `ltntbl.dat` differs only in case from the FAT short name;
- filesystem extraction order differs from DRSTR order.

After validator updates:

- `cardcheck.py --image`: PASS
  (`files=248`, `dirs=19`, `bytes=5182407132`, `pairs=58`,
  `tiles=113`, `rows=11`);
- `l2check.py --no-golden --ignore-dump-artifacts --no-tiles --skip-mutation`:
  PASS (`drstr_roundtrip` OK, `cmp_roundtrip` 58/58);
- `cmpind_writer.py verify`: 58/58 OK, 3,743,680,000 logical bytes.

Tile checks use EU golden tile names, none of which exist on the US card, so
they are skipped with warnings. A direct byte-identical rebuild of
`B28R0C8R.DAT` succeeds, but the semantic decoder reports opaque-record
diagnostics; this is not a container failure.

## Interpretation

- **FACT:** the US dump is a valid ZE0-format North America card with SHA-256
  `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383`.
- **FACT:** its `HDD_INFO.TXT` uses the same six-line structure with market code
  `QSD-301-100`, region `SDC08-EVNAM`, and firmware version `X210NBNI.147`.
- **FACT:** the card has 11 shards, 113 tiles, 58 `.cmp` pairs and an `XMD`
  directory instead of `TMC`.
- **OBSERVED:** the original L1/L2 failures were caused by validator
  assumptions (case-sensitive names, exact 13-byte names, filesystem order),
  not by card corruption.
- **HYPOTHESIS:** `XMD` is a market-specific replacement for `TMC` or an
  additional North America data channel; its role is not yet decoded.

## Conclusion

The validator now handles the US card. `cardcheck.py --image` and the
structural L2 checks pass. The remaining tile work is market-specific: the EU
golden tiles do not exist on the US card, so tile checks must be run per
available tile rather than against the EU golden profile.

## Follow-ups

- [ ] Decode the `XMD` tables (`bsaidxtbl.dat`, `bsatbldata.dat`,
  `ltntbl.dat`).
- [ ] Compare US `REFER001`/`REFER002` schemas with the EU set.
- [ ] Run tile byte-identical rebuilds on representative US tiles.
- [ ] Keep `TMC`/`XMD` handling explicit in cardcheck.
- [ ] Keep DRSTR order recovery in `drstr_ze0.build`.
