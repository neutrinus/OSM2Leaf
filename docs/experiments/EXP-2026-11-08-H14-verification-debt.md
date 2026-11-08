# EXP-2026-11-08-H14: Run the pinned checks the earlier EXPs promised

- **Status:** done (one recorded negative: B30R048R, see Observations)
- **Date:** 2026-11-08
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img` SHA-256
  `105e2032e480e8ba…` (full image, `archive/sd-images/`, not committed);
  extracted files in `leafre-work/root/MAPAL001/` (outside the repo):
  - `B28R070R.DAT` `0e4df38b659e99129c1e…`
  - `B30R060R.DAT` `8ca92bd5601e33bd97ab…`
  - `B58R070R.DAT` `f8aae7e4d0df35e45037…`
  - `B30R048R.DAT` `0916101547246d6c6ed2…`
  - `LEV3456R.DAT` `08a584feacf049cc3926…`
  - `IMG256` (`archive/head256.img`) SHA-256 `92aa525d0db2c167…`
- **Tools:** `python3 3.15.0` (zlib-ng 1.3.1) for `realcheck`, `harness`,
  `selftest`; `python3.13.17` in `~/.venvs/ze0` with stock zlib 1.3.2 for
  `lev3456` (zlib-ng run exits 3, see Method); `meson 1.12.1`, `ninja 1.13.2`,
  `gcc` (system) for `build.sh`.
- **Claims:** none (verification only; no new claim)
- **Supersedes:** none
- **Superseded by:** none

## Question

Do the pinned values that five earlier records rely on reproduce on the real
bytes, and do the offline selftests for the qemu-ze0 and Ghidra scripts pass
without a silent skip?

## Hypothesis

Every pinned check passes; the five tiles and LEV3456R verify byte-identically.
**Falsifier:** any tile or LEV3456 region that fails to rebuild byte-for-byte,
or a selftest that reports SKIP where the tool is present.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `IMG256`, EU 2011 full image, `MAPAL001/*.DAT` |
| SHA-256 | see Sample |
| Offset(s) / VA(s) | n/a (format checks) |
| Tool / version | see Tools |
| Repo tool | `tools/realcheck.py`, `tools/ze0-viewer/harness.py`, `tools/lev3456.py`, `tools/qemu-ze0/build.sh`, `tools/qemu-ze0/gdb-ze0.py`, `tools/l3_harness/ghidra_import.py`, `tools/selftest.py` |

## Method

1. **Sample and hash.** As in Sample. Hashes were checked with `sha256sum`.
2. **Commands.**

   ```bash
   python3 tools/selftest.py
   python3 tools/realcheck.py archive/head256.img
   cd tools/ze0-viewer
   for t in B28R070R B30R060R B58R070R B30R048R; do
     python3 harness.py verify ../../leafre-work/root/MAPAL001/$t.DAT
   done
   cd ../..
   python3.13 tools/lev3456.py verify leafre-work/root/MAPAL001/LEV3456R.DAT
   bash tools/qemu-ze0/build.sh --selftest
   python3 tools/qemu-ze0/gdb-ze0.py --selftest
   python3 tools/l3_harness/ghidra_import.py --selftest
   ```

   The `realcheck` run includes the extra `coredll.dll` ordinals 59, 65, 66,
   496 and 1047 (EXP-H7 list) in its `exports` check.
3. **Controls.** Positive: the pinned tiles and LEV3456 (expected identical).
   Negative: `realcheck` pins are exact values, so a wrong pin fails; the
   `build.sh` selftest includes a `network needed` case that must exit 3.
4. **Corpus.** 5 `MAPAL001` files (about 78 MB), 1 image head (256 MiB), 3
   selftest suites (65 checks in `selftest.py`, 42 in `build.sh`, 30 in
   `gdb-ze0.py`, 13 in `ghidra_import.py`).
5. **Falsifier.** As in Hypothesis; stated before the run.

## Observations

- `selftest.py`: passed 47, failed 0, skipped 18, total 65.
- `realcheck.py archive/head256.img`: 8 PASS, 0 FAIL, 0 SKIP. Exports
  `coredll.dll` lists 59 `wcschr`, 65 `wcsncmp`, 66 `wcsncpy`, 496 `Sleep`,
  719 `sprintf`, 1047 `memset`, all as pinned.
- `harness.py verify`:
  - B28R070R: records 7937/0 bad, background 7103/0, graph 455/0, roundtrip OK.
  - B30R060R: records 8539/0 bad, background 8465/0 (opaque 6), graph 37/0, roundtrip OK.
  - B58R070R: records 459/0 bad, background 459/0, graph 0, roundtrip OK.
  - **B30R048R: `AssertionError((6, 29))` on an opaque background record**
    (repeated per record). **Negative, not fixed here.**
- `lev3456.py verify` (stock zlib 1.3.2, `python3.13.17`): exit 0.
  Section 1 level 5 strict; levels 3/4 best-effort. Section 2 level 4 region
  identical 12794112 B; level 5 identical 1261568 B.
- Same command under zlib-ng 1.3.1 (`python3` 3.15.0): exit 3,
  "region DIFFERS … the compressor, not the data, differs". Expected: the
  tool's own exit-3 rule.
- `build.sh --selftest`: 42 passed, 0 failed (after `make`, `meson`, `ninja`
  and `gcc` were installed).
- `gdb-ze0.py --selftest`: 30 checks, 0 failures.
- `ghidra_import.py --selftest`: 13 checks, OK; prints that only a real
  `analyzeHeadless` run may claim an import.

## Interpretation

Four of five tiles and LEV3456R reproduce on the real bytes. B30R048R does
not: the harness's background rebuild raises on an opaque record, so its
round-trip is not verified. The pin for B30R048R must not be trusted until
the assertion is explained. The LEV3456 result is a stock-zlib result; the
zlib-ng result is not a data failure. The selftests run only where their
tools exist, so the qemu-ze0 check is meaningful only with `make`, `meson`,
`ninja` and `gcc` present.

## Next

- Open a follow-up task for B30R048R: find which opaque record raises
  `(6, 29)` and whether the harness or the file is wrong.
- Re-run `lev3456` levels 3 and 4 strictly once they are decoded.
