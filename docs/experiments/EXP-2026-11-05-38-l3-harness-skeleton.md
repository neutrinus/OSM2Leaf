# EXP-2026-11-05-38: L3 harness skeleton

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** none — synthetic files only; no vendor data was read. Reference
  image for later runs:
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-532, C-533 (proposed; ledger rows added by the parent session)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the L3 plan be made runnable and reviewable without vendor data or Ghidra,
and can the runner be made structurally incapable of reporting a pass it did
not get from a real Ghidra run?

## Hypothesis

Yes. The four inputs — corpus manifest, stub table, ROM section table and a
Ghidra result file — have narrow JSON contracts. Each can be validated
offline, and `run` can be gated on a detected `analyzeHeadless` plus a real
result file whose verdicts are compared with the manifest.

## Inputs

| Item | Value |
| --- | --- |
| Code | `tools/l3_harness/` (`manifest.py`, `stubs.py`, `rommap.py`, `runner.py`, `selftest.py`) |
| Input format | `ce_rom_parse.py` JSON with `segments[].modules[].sections[]` |
| Corpus | synthetic: `REFER001/ADDRE001.DAT.cmp`, `.cmp.bad-ind`, `MAPAL001/B28R070R.DAT`, `DRSTR001.DAT`, `VER_INFO/HDD_INFO.TXT` |
| Vendor data | none |
| Ghidra | not installed; `GHIDRA_INSTALL_DIR` unset |
| Tool version | Python 3.13.5, standard library only |

## Method

```bash
cd /home/krzesimir/PycharmProjects/OSM2Leaf.session-ZMxuBT
python3 -m py_compile tools/l3_harness/__init__.py tools/l3_harness/*.py
python3 tools/l3_harness/selftest.py

# synthetic manifest + memory map, then the runner
python3 tools/l3_harness/manifest.py build --root /tmp/opencode/l3-demo/corpus \
  --out /tmp/opencode/l3-demo/manifest.json \
  --case factory:cmp_ind:REFER001/ADDRE001.DAT.cmp \
  --case corrupt_ind:cmp_ind:REFER001/ADDRE001.DAT.cmp.bad-ind \
  --case tile_factory:tile:MAPAL001/B28R070R.DAT \
  --case drstr_factory:drstr:DRSTR001.DAT \
  --case hdd_info_factory:hdd_info:VER_INFO/HDD_INFO.TXT
python3 tools/l3_harness/rommap.py convert \
  --report /tmp/opencode/l3-demo/ce-rom-report.json \
  --segment 0 --out /tmp/opencode/l3-demo/rommap.json
python3 tools/l3_harness/runner.py check \
  --manifest /tmp/opencode/l3-demo/manifest.json \
  --rommap /tmp/opencode/l3-demo/rommap.json --root /tmp/opencode/l3-demo/corpus
python3 tools/l3_harness/runner.py plan \
  --manifest /tmp/opencode/l3-demo/manifest.json \
  --rommap /tmp/opencode/l3-demo/rommap.json
python3 tools/l3_harness/runner.py run \
  --manifest /tmp/opencode/l3-demo/manifest.json \
  --rommap /tmp/opencode/l3-demo/rommap.json --image /tmp/opencode/l3-demo/fake.img
```

The synthetic `ce-rom-report.json` used one segment (`0x200200`,
`phys_base 0x8cae1000`), `Navi.exe` with `.text`/`.rdata`, `STDDLL.dll` with a
BSS `.bss`, `image_size 0x10000`, `image_sha256 aaaa…` (64 chars).

## Observations

```
$ python3 tools/l3_harness/selftest.py
ok   manifest: build and validate
ok   manifest: bad sha256 rejected
ok   manifest: unknown verdict rejected
ok   manifest: unknown reader and case rejected
ok   manifest: duplicates and unknown keys rejected
ok   manifest: missing file and build errors rejected
ok   manifest: JSON schema is serialisable
ok   rommap: synthetic report converts
ok   rommap: overlapping sections rejected
ok   rommap: compressed section rejected
ok   rommap: zero-size, empty and out-of-range rejected
ok   stubs: table is complete and valid
ok   stubs: JSON schema is serialisable
ok   runner: check passes on valid inputs
ok   runner: check fails on a bad manifest
ok   runner: plan reports blockers
ok   runner: missing Ghidra exits 3, never 0
ok   runner: Ghidra without a harness script blocks (exit 4)
ok   runner: result comparison cannot fake a pass

selftest: OK (19 checks)
```

```
$ python3 tools/l3_harness/manifest.py validate \
    /tmp/opencode/l3-demo/manifest.json --root /tmp/opencode/l3-demo/corpus
RESULT: PASS (5 entries, files verified under /tmp/opencode/l3-demo/corpus)

$ python3 tools/l3_harness/rommap.py convert \
    --report /tmp/opencode/l3-demo/ce-rom-report.json --out …/rommap.json
wrote …/rommap.json (3 blocks, 0 skipped)
RESULT: PASS (3 blocks, segment 0x200200)

$ python3 tools/l3_harness/runner.py check … --root …/corpus
manifest: 5 entries, files verified under /tmp/opencode/l3-demo/corpus
rommap: 3 blocks, processor SuperH:BE:32:SH-4 (verified=False)
RESULT: PASS

$ python3 tools/l3_harness/runner.py run … --image …/fake.img
MISSING_GHIDRA: analyzeHeadless was not found.
…
RESULT: MISSING_GHIDRA (exit 3)
run exit: 3
```

`runner.py plan` printed `UNKNOWN (no runnable entry point)` for all five
readers, listed the map-code comparator chain as `located-file-offset` with
`role=helper`, and listed the missing `ghidra/l3_run.py` as a blocker.

## Interpretation

- **FACT:** `manifest.py` rejects a wrong SHA-256, an unknown verdict
  (`MAYBE`, `accept`, `true`), an unknown reader/case, a case/reader
  mismatch, a duplicate id or `(path, reader)` pair, an unknown key and a
  missing file. A syntactically valid but wrong hash is caught only with
  `--root`, which is the documented behaviour.
- **FACT:** `rommap.py` converts the documented `sections[]` shape, maps
  `R`/`W`/`X` from the CE flags, keeps a BSS section loadable with no file
  bytes, and rejects overlapping sections, zero-size sections, compressed
  sections, out-of-image file ranges and invalid segment indices.
- **FACT:** `runner.py run` exits `3` when `analyzeHeadless` is absent and
  `4` when it is present but the harness script is missing; it does not print
  `RESULT: PASS` on either path. The result comparator treats a missing case
  as a mismatch.
- **OBSERVED:** the stub table has 17 entries, 14 `modeled` and 3 `planned`
  (`sprintf`, `OSM_LogMsg`, `StatusData`); `StatusData` stays `unresolved`
  because no signature or caller is known.
- **UNKNOWN:** the Ghidra language id `SuperH:BE:32:SH-4` is not confirmed
  against a real project (recorded as `verified: false`), and no reader entry
  point exists to run.
- **UNKNOWN:** whether `tools/cerom.py` will emit exactly the accepted
  `sections[]` shape; the aliases cover the `o32_rom` field names but that is
  a design assumption, not a test against the real report.

## Conclusion

`tools/l3_harness/` makes the L3 plan executable up to the Ghidra boundary and
keeps the boundary explicit: the manifest, stubs and memory map are validated
offline, while `run` can only succeed through a real `analyzeHeadless` result.
No L3 reader is located, so the status remains **blocked**, not passed.

Changed: `docs/research/l3-ghidra.md` (interface contract, status table, first
run needs), `tools/l3_harness/README.md`. Proposed claims C-532/C-533 need
ledger rows; the parent session owns `claims.md`.

## Follow-ups

- [ ] Add the ledger rows for C-532/C-533 and point them at this record.
- [ ] Pick up `tools/l3_harness/selftest.py` from `tools/selftest.py`
      (discovery is `tools/*.py` only) or add a stable entry point.
- [ ] Write `tools/cerom.py` with the `sections[]` shape and re-run
      `rommap.py convert` on the real build A report.
- [ ] Confirm the Ghidra `-processor` id on the first real import.
- [ ] Record the corpus manifest hashes once vendor data is available again.
