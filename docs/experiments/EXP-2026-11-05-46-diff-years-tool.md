# EXP-2026-11-05-46: cross-year differential tool (`diff_years.py`)

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** synthetic roots only (`--selftest`); no vendor data in this
  environment, so no image/file SHA-256 is pinned.
- **Claims:** C-544, C-545 (proposed; `claims.md` was not edited in this
  session)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can one standard-library tool compare two extracted ZE0 card roots (or two raw
images) across the tree census, `HDD_INFO.TXT` plus its `0x06000000` copy, the
common header, `DRSTR001.DAT`, the `MMAIN001.DAT` level table, the tile
inventory/descriptors and file hashes, while detecting deliberate changes and
suppressing only the cases selected by `--partial` and
`--ignore-dump-artifacts`?

## Hypothesis

Yes. Seven independent comparison categories cover the fields named in
`TODO.md` "Cross-year differential" and P10b. Synthetic roots can exercise the
root path without vendor data; the image path reuses
`cardcheck.Fat32Image`/`leafimg`, so only that path remains unexercised here.

## Inputs

| Item | Value |
| --- | --- |
| Tool | `tools/diff_years.py` |
| Tool SHA-256 | `e71af1e5a0e780c2480a44da83f8fbfd9c1e14cb30cab3b7dada703f38fb3931` |
| Python | 3.14.4 |
| Synthetic A/B | 6 files, 2 directories, 6,867 bytes each |
| Synthetic C | A with 2014 `HDD_INFO` lines and `0x2ac` lat 1920 → 1921 |
| Vendor data | none; real 2011/2014/2016 roots are outside this checkout |

The synthetic root contains:

```
MMAIN001.DAT            4096 B, header + 0x1ac level table
DRSTR001.DAT             376 B, 3 nodes + 8 entries, leading u32 0x0000002f
MAPAL001/B48R060R.DAT   1024 B, header + 0x1ac + 0x2ac tables
MAPAL001/LEV3456R.DAT   1280 B, same shape
VER_INFO/HDD_INFO.TXT     72 B, six CRLF lines, no trailing CRLF
CMP.LST                   19 B, `\SystemSD\REFER001\`
```

`DRSTR001.DAT` identity: `3*40 + 8*32 = 376`. `MMAIN` has one group,
section 1, levels 6 and 5. The header uses the documented UTF-16BE text slots
and the `ff ff 24 ff 12 c0 05 00 fb 50 0f f0` prefix at `0x180`.

## Method

```bash
python3 -m py_compile tools/diff_years.py
python3 tools/diff_years.py --selftest
python3 tools/selftest.py --only diff_years

# Build two copies of the synthetic root plus one mutated variant under /tmp.
python3 - <<'PY'
import sys, shutil
from pathlib import Path
sys.path.insert(0, "tools")
import diff_years as d
base = Path("/tmp/opencode/diff-years-demo/a")
d.synthesize_root(base)
shutil.copytree(base, "/tmp/opencode/diff-years-demo/b")
d.synthesize_root(Path("/tmp/opencode/diff-years-demo/c"),
                  hdd=d.HDD_2014, bbox_lat_top=1921)
PY

python3 tools/diff_years.py /tmp/opencode/diff-years-demo/a \
    /tmp/opencode/diff-years-demo/b
python3 tools/diff_years.py /tmp/opencode/diff-years-demo/a \
    /tmp/opencode/diff-years-demo/c
python3 tools/diff_years.py /tmp/opencode/diff-years-demo/a \
    /tmp/opencode/diff-years-demo/c --json > /tmp/opencode/diff-years-demo/report.json
```

## Observations

`py_compile` reported no errors. `--selftest` ran 29 checks and ended
`selftest: PASS`; the detected cases were:

- `HDD_INFO.TXT` line 2 changed → only `hdd_info` differs, line 1 stays equal;
- `DATA VERSION` changed → `headers` differs for `MMAIN001.DAT`;
- one byte in the `0x180` binary block changed → `headers` names the block;
- `DRSTR001.DAT` entry value changed → `drstr` differs and names
  `MMAIN001.DAT`;
- `DRSTR001.DAT` leading byte changed → `drstr` reports the leading u32;
- `MMAIN` level-6 count changed → `mmain` differs at section 1 level 6;
- `0x2ac` lat value changed → `tiles` differs for `B48R060R` at `0x2ac`;
- same-length `CMP.LST` change → only `hashes` differs;
- extra `._CMP.LST` → `tree` differs by default, same with
  `--ignore-dump-artifacts`;
- missing `VER_INFO/` → `tree` and `hdd_info` differ by default; both are
  suppressed with `--partial`, while an unrelated tile diff still fails;
- `--no-hashes` reports the hash section as `unavailable`.

`python3 tools/selftest.py` discovers the new tool and reports
`tool:diff_years PASS` (`passed=9 failed=0 skipped=19`, total 28 suites).

Two identical copies (`a` vs `b`, root mode):

```
[tree] SAME  A files=6 dirs=2 bytes=6867; B files=6 dirs=2 bytes=6867
[hdd_info] SAME  A 72 bytes, B 72 bytes
[headers] SAME  compared=3 differing=0
[drstr] SAME  A size=376 nodes=3 entries=8; B size=376 nodes=3 entries=8
[mmain] SAME  A groups=1 rows=2; B groups=1 rows=2
[tiles] SAME  A 2 tiles, B 2 tiles; descriptors compared=2 differing=0
[hashes] SAME  compared=6 identical=6 skipped(size mismatch)=0
RESULT: IDENTICAL (0 suppressed difference(s))
```

`a` vs mutated `c`:

```
[hdd_info] DIFFERENT
  - VER_INFO/HDD_INFO.TXT line 2: 'QSD-309-101' -> 'QSD-357-101'
  - VER_INFO/HDD_INFO.TXT line 3: '02-110100-00' -> '02-140300-00'
  - VER_INFO/HDD_INFO.TXT line 5: '11-05' -> '14-06'
  - VER_INFO/HDD_INFO.TXT line 6: '470323501005' -> '470516001006'
[tiles] DIFFERENT
  - MAPAL001/B48R060R.DAT: 0x2ac descriptor bytes differ in 1 byte(s);
    first at 0x2b3 (80 -> 81)
  - MAPAL001/B48R060R.DAT: 0x2ac section 1 level 2 ... lat 1685..1920 ...
    -> ... lat 1685..1921 ...
  ... same for LEV3456R.DAT
[hashes] DIFFERENT compared=6 identical=3
RESULT: DIFFERENT (3 categories, 11 difference(s), 0 suppressed)
```

The `--json` run produced valid JSON with
`summary = {"different_categories": ["hdd_info", "tiles", "hashes"],
"differences": 11, "suppressed": 0}` and exit code 1.

## Interpretation

- **FACT:** The tool imports `drstr.parse`, `cardcheck.header_fields`,
  `cardcheck.parse_level_table`, `cardcheck.RootSource`/`Fat32Image` and
  `leafimg.mbr_entries`; it does not re-implement those parsers.
- **FACT:** The synthetic `DRSTR` satisfies the documented identity
  `nodes*40 + entries*32 = file size` (3*40 + 8*32 = 376) and the tool reports
  the leading u32 as `0x0000002f`, the bytes of the root name `/`, not a count.
- **OBSERVED:** All seven categories are independently testable on a
  six-file synthetic root; a single-byte tile-descriptor change is reported
  both as a raw byte at `0x2b3` and as the decoded arc-minute row.
- **OBSERVED:** `--partial` suppresses only the missing `VER_INFO` subtree and
  the missing `HDD_INFO.TXT`; unrelated tile/descriptor differences still make
  the run `DIFFERENT`.
- **OBSERVED:** `--ignore-dump-artifacts` removes `._*` from the tree census
  but does not hide other differences.
- **UNKNOWN:** The raw-image path (`--image`, FAT32 walk, and the
  `0x06000000` copy comparison) is implemented through the existing helpers but
  could not be exercised here because no vendor image is present. The copy is
  read at absolute offset `0x06000000` for 72 bytes and compared with both the
  same image's file and the other input.
- **HYPOTHESIS:** On the archived 2011/2014/2016 set the tool will show
  `HDD_INFO` lines 2/3/5/6 and tile `0x2ac`/`0x1ac` changes while the tree,
  header model and `DRSTR` node shape stay stable, matching
  `image-versions.md`. This needs an actual run.

## Conclusion

Added `tools/diff_years.py` (stdlib only, read-only). No format knowledge
changed, so `docs/format/*.md` was not touched. Proposed ledger rows:

- **C-544** — `tools/diff_years.py` compares two ZE0 roots or raw images in
  seven read-only categories (tree census, `HDD_INFO.TXT` + `0x06000000` copy,
  common header, `DRSTR001.DAT`, `MMAIN001.DAT` level table, `MAPAL001`
  inventory/`0x1ac`/`0x2ac` descriptors, SHA-256 hashes) and emits human text
  or JSON. **VERIFIED** (synthetic selftest), confidence **H**.
- **C-545** — In `diff_years.py`, `--partial` suppresses only differences
  caused by an absent `VER_INFO` subtree/`HDD_INFO.TXT`, and
  `--ignore-dump-artifacts` suppresses only macOS dump artifacts; neither flag
  hides unrelated data differences. **VERIFIED** (synthetic selftest),
  confidence **H**.

## Follow-ups

- [ ] Run on the 2011 vs 2014 vs 2016 extractions and paste the category
      summaries into `docs/research/image-versions.md` (a new EXP, not this
      record).
- [ ] Run `--image` on one archived image pair to exercise the `0x06000000`
      copy comparison and pin its SHA-256.
- [ ] Decide whether `DRSTR` node-index shifts from a new top-level directory
      (`TFTBL001` in 2014) deserve their own summary instead of per-node rows.
- [ ] If the 2013-14 map tree is used, verify that its stale `VER_INFO` node
      plus `--partial` produces no false difference.
