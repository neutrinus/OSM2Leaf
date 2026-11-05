# EXP-2026-11-05-01: Correct the DRSTR001.DAT node table

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** `DRSTR001.DAT`, SHA-256
  `2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6`,
  11,968 bytes, from the EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`.
- **Claims:** C-030, C-031, C-032, C-033, C-034, C-036
- **Supersedes:** earlier prose in `docs/format/drstr.md` (0x28-byte header,
  0x2f node count, one-node shift)
- **Superseded by:** none

## Question

Does `DRSTR001.DAT` have a header, how many node records does it contain, and
where does the node table end?

## Hypothesis

The earlier reading was wrong: `0x2f` is not a count but the ASCII `/` of the
root node, the table starts at `0x0000`, and there are 40 records (root + 39
directories).

## Inputs

| Item | Value |
| --- | --- |
| File | `DRSTR001.DAT` |
| SHA-256 | `2b7f2fb8…25f6` |
| Size | 11,968 bytes |
| Tools | `python3 tools/drstr.py`, `python3 tools/selftest.py` |

## Method

```bash
xxd -s 0x00 -l 0x100 -g1 DRSTR001.DAT
python3 tools/drstr.py parse DRSTR001.DAT
python3 tools/selftest.py
```

Cross-check: parse the 2014 and 2016 `DRSTR001.DAT` files and test the same
invariants (`next == index+1`, `parent+1` maps to an existing node, listings
are contiguous and end at EOF).

## Observations

- File-size identity: `40 nodes * 40 B + 324 entries * 32 B = 11,968` exactly.
- First bytes: `2f 00 00 00 00 00 00 00` = name `/` + zero padding.
- The parser finds 40 nodes; node 0 is `/`.
- Listings tile `0x0640..0x2ec0` with zero slack.
- `next_index == index+1` for all nodes; the last equals the node count.
- `parent_plus_1` maps every node to an existing node.
- Directory entry `value` equals the recursive subtree total.
- The same invariants hold on the 2014/2016 sets (59 nodes).

## Interpretation

- **FACT:** there is no header; the node table starts at `0x0000`.
- **FACT:** `0x2f` is the ASCII `/` of the root name.
- **FACT:** the 2011 file has 40 nodes and 324 entries.
- **OBSERVED:** `next_index` is always `index+1`; its purpose is unknown.
- **FACT:** node `+0x16` is `parent_index+1`, not a type.

## Conclusion

`docs/format/drstr.md`, `tools/drstr.py`, `tools/selftest.py`, `AGENTS.md` and
the claim ledger were corrected. The old “one-node shift” was a parsing
artefact and must not be reintroduced.

## Follow-ups

- [ ] Decode the remaining node fields at `+0x08..+0x13`.
- [ ] Test on a spare card whether renaming `DRSTR001.DAT` makes the unit fall
  back to the FAT.
- [ ] Keep the writer's byte-identical output as a regression test.
