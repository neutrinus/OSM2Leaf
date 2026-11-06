# EXP-2026-11-06-H7: `tools/realcheck.py`, a pinned real-image regression run

- **Status:** done (tool + synthetic self-test); the `IMG256` run is pending
  (the image is not on this machine)
- **Date:** 2026-11-06
- **Sample:** `IMG256`, the first 256 MiB of
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (`curl -r 0-268435455`), size
  268435456 bytes, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (the slice used by EXP-2026-11-06-H5; downloaded to scratch, not committed)
- **Claims:** C-1730–C-1739
- **Supersedes:** none
- **Superseded by:** none

## Question

Can one command replay the real-image observations of
EXP-2026-11-06-H5 and report `PASS`/`FAIL` per check against pinned values, so a
tool that still passes its synthetic self-test but has regressed on real bytes
fails the same day (C-1714)?

## Hypothesis

Every count in H5 is reproducible exactly, so each check can be pinned. The one
expected red result is `thunks Navi.exe`: the tool reports 0 stubs on real image
A (C-1714), so the run exits 1 until M1.6c fixes it. Without an image every
check is a `SKIP no image` and the exit code is 2, never a false pass.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `IMG256` (first 256 MiB), SHA-256 above, 268435456 bytes |
| Image A | image start `0x200200`, `ROMHDR` at file `0x01951b78` |
| Image B | image start `0x3e00200` (`coredll.dll` lives in B, C-525/C-527) |
| Pins | EXP-2026-11-06-H5 observations (ordinal names, 187/58, 846 slots, 0 probe matches) |
| Tools | `tools/cerom.py`, `tools/sh4xref.py`, `tools/cecompress.py` at `main` `17b950f` |
| New tool | `tools/realcheck.py` |

The tool imports the three tool modules and calls their report/parse functions;
it does not scrape CLI text. The `sh4xref` call sites are derived from the
module's own `pool_entries` / `loads_of` / `call_after` / `function_start`
helpers, the same primitives `query_to` uses, so no printed line is parsed.

## Method

Checks and pinned values (selector keys choose the image region; `expect` is
compared field by field):

| Check | Selector | Pinned `expect` |
| --- | --- | --- |
| `input` | the file itself | SHA-256 `92aa…07f9`, size 268435456 |
| `romhdr` | A `0x200200` | `nummods=149`, `numfiles=1`, `usCPUType=0x01a6`, `physfirst=0x8cae1000`, `physlast=0x8e233c88` |
| `exports` | B `0x3e00200`, `coredll.dll`, ordinal 719 | `names=1651`, `ordinals={"719":"sprintf"}` |
| `imports` | A `0x200200`, `Navi.exe` | `slots=846` |
| `comphdr` | A `0x200200`, `--all` | `sections=245`, `holds=187`, `refuted=58`, `unparsed=0` |
| `thunks` | A `0x200200`, `Navi.exe` | `stubs=846`, `import_slots=846` (today `stubs=0`, so FAIL) |
| `sh4xref` | A `0x200200`, `Navi.exe`, `--to 0x003d1bb0` and `--to 0x003d1ba4` | `jsr_sites` `0x003778b2`, `0x00377b46`, `0x003778bc`, `0x00377b52`; `fn_sites` `0x00377870`, `0x00377ae0` |
| `probe` | A `0x200200`, `NaviMapCC.dll`, offsets `0-40` | section rva `0x13000` vsize `0x5b8` psize `0x2c6`: 0 matches / 205 attempts; rva `0x14000` vsize `0xcc0` psize `0x68c`: 0 matches / 205 attempts |

The `thunks` pin is the pre-M1.6c expectation (one stub per import slot). It is
deliberately red: C-1714 measured 0 detected stubs. If M1.6c legitimately finds
a different number, the pin is changed only with `--update --write`, with the
reason recorded in a new EXP.

```bash
# tool checks (no vendor bytes)
python3 -m py_compile tools/realcheck.py
python3 tools/realcheck.py --selftest

# missing-image classification
python3 tools/realcheck.py /tmp/opencode/no-such-img256.img; echo $?
python3 tools/realcheck.py /tmp/opencode/no-such-img256.img --require-image; echo $?

# discovered by the repository runner
python3 tools/selftest.py --only realcheck

# the real run, once IMG256 is in the scratch directory (expected exit 1: thunks)
python3 tools/realcheck.py IMG256; echo $?

# deliberate re-pin: --update alone prints and exits 3, --write applies
python3 tools/realcheck.py IMG256 --update; echo $?
python3 tools/realcheck.py IMG256 --update --write
```

Self-test design: `cerom.build_synthetic_rom()` (two modules, three files, real
LZSS/LZX streams, 29696 bytes) supplies a CE ROM with no vendor bytes. The
self-test pins its `input`, `romhdr` and `exports` values, changes one
`physlast` pin to prove a single FAIL, runs a missing path to prove SKIP, runs
it again with `--require-image` to prove FAIL, and updates a temporary copy of
the tool to prove that `--update` without `--write` exits 3 and leaves the file
byte-identical.

## Observations

```
$ python3 -m py_compile tools/realcheck.py
$ echo $?
0
```

```
$ python3 tools/realcheck.py --selftest
pin table covers every real check                    ok
sh4xref helper finds the synthetic jsr site          ok
synthetic ROM: all three checks PASS                 ok
synthetic ROM: PASS detail names the measured values ok
--update proposal equals the run's measurements      ok
wrong pin: only that check FAILs                     ok
wrong pin: FAIL names the field                      ok
missing image: every check SKIPs                     ok
missing image: run carries the exit-2 error          ok
--require-image: every skip becomes FAIL             ok
--update without --write refuses (exit 3)            ok
refused update leaves the file byte-identical        ok
--update --write round-trips the pin table           ok
realcheck selftest: 13 checks OK (synthetic CE ROM, no vendor data)
$ echo $?
0
```

```
$ python3 tools/realcheck.py /tmp/opencode/no-such-img256.img
SKIP  input SHA-256                       no image
SKIP  romhdr build A                      no image
SKIP  exports coredll.dll (B)             no image
SKIP  imports Navi.exe (A)                no image
SKIP  comphdr --all (A)                   no image
SKIP  thunks Navi.exe (A)                 no image
SKIP  sh4xref EXP-50 call sites (A)       no image
SKIP  cecompress probe NaviMapCC.dll (A)  no image
realcheck: 0 PASS, 0 FAIL, 8 SKIP
$ echo $?
2
```

```
$ python3 tools/realcheck.py /tmp/opencode/no-such-img256.img --require-image
FAIL  input SHA-256                       no image: [Errno 2] No such file or directory: '/tmp/opencode/no-such-img256.img'
... (all eight checks the same)
realcheck: 0 PASS, 8 FAIL, 0 SKIP
$ echo $?
1
```

```
$ python3 tools/selftest.py --only realcheck
tool:realcheck  PASS  0.06s

passed=1 failed=0 skipped=0 total=1 time=0.06s
selftest: OK
$ echo $?
0
```

The `IMG256` run was not performed in this checkout: the image is not present
and vendor bytes must not be committed. Its expected outcome is 7 PASS and
`thunks` FAIL, i.e. exit 1, unless M1.6c has landed.

## Interpretation

- **FACT:** The runner classifies PASS, FAIL and SKIP deterministically. The
  synthetic CE ROM proves PASS and a one-field change proves FAIL; a missing
  path proves `SKIP no image` (exit 2) and `--require-image` proves the FAIL
  conversion (exit 1). `tools/selftest.py --only realcheck` discovers it.
- **OBSERVED (from H5):** The pins are H5's real-image counts: 149/1 modules,
  1651 `coredll.dll` names with ordinal 719 = `sprintf`, 846 `Navi.exe` slots,
  245 compressed sections (187 HOLDS / 58 REFUTED), four EXP-50 call sites, and
  0 probe matches in 205 attempts per `NaviMapCC.dll` section.
- **HYPOTHESIS:** On `IMG256` the run is 7 PASS + 1 FAIL (`thunks`), so the
  command exits 1 and names C-1714. The real-image result of the other seven
  checks is `UNKNOWN` until that run.
- **HYPOTHESIS:** The `thunks` gate turns green when M1.6c reports a stub for
  the 846 slots; if the fixed tool detects a different exact count, `--update
  --write` re-pins it deliberately, never automatically.
- **UNKNOWN:** Whether a full image (not the 256 MiB slice) should be a second
  named pin set; today the SHA-256 pin makes `IMG256` the only accepted input.

## Claims

The claim-ledger rows are reserved for this task; the text is recorded here
because `docs/research/claims.md` is outside the H7 file list.

| ID | Claim | Status | Evidence |
| --- | --- | --- | --- |
| C-1730 | `tools/realcheck.py` is a single-command real-image regression runner: it imports `cerom`, `sh4xref` and `cecompress`, runs eight checks, prints `PASS`/`FAIL` per check, and exits 0 all-PASS, 1 any-FAIL, 2 missing/unreadable image, 3 `--update` without `--write`. | VERIFIED (tool, synthetic) | this EXP; `python3 tools/realcheck.py --selftest` |
| C-1731 | The first check is the input itself: SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` and size 268435456 bytes for `IMG256`; a mismatch is a FAIL, not a skip. | VERIFIED (tool, synthetic); pin OBSERVED (H5) | this EXP; H5 "Sample" |
| C-1732 | The `romhdr` check reads image A at `0x200200` and pins `nummods=149`, `numfiles=1`, `usCPUType=0x01a6`, `physfirst=0x8cae1000`, `physlast=0x8e233c88`. | VERIFIED (tool, synthetic); pin OBSERVED (H5) | H5; `tools/cerom.py romhdr` |
| C-1733 | The `exports` check reads image B at `0x3e00200`, `coredll.dll`, and pins 1651 names with ordinal 719 = `sprintf`. | VERIFIED (tool, synthetic); pin OBSERVED (H5) | H5 observation 1; C-527 |
| C-1734 | The `imports` check reads image A `Navi.exe` and pins 846 import slots. | VERIFIED (tool, synthetic); pin OBSERVED (H5) | H5 observation 3; C-690 |
| C-1735 | The `comphdr --all` check reads image A and pins 245 compressed sections with 187 HOLDS, 58 REFUTED and 0 UNPARSED. | VERIFIED (tool, synthetic); pin OBSERVED (H5) | H5 observation 2 |
| C-1736 | The `thunks Navi.exe` check pins 846 stubs against 846 import slots; on the H5 real image the tool detects 0 stubs, so this check is FAIL until M1.6c lands (the C-1714 gate). | VERIFIED (tool, synthetic); real FAIL expected from C-1714 | H5 observation 3; C-1714 |
| C-1737 | The `sh4xref` check reproduces four EXP-50 call sites through the two thunk VAs: `jsr` at `0x003778b2`/`0x00377b46` (`--to 0x003d1bb0`) and `0x003778bc`/`0x00377b52` (`--to 0x003d1ba4`), with enclosing functions `0x00377870` and `0x00377ae0`. | VERIFIED (tool, synthetic); call sites OBSERVED (C-710) | EXP-2026-11-05-M1.8-sh4xref; C-710 |
| C-1738 | The `probe` check extracts the two `NaviMapCC.dll` compressed sections (`rva 0x13000` vsize `0x5b8` psize `0x2c6`; `rva 0x14000` vsize `0xcc0` psize `0x68c`) and pins 0 exact-length matches in 205 attempts (41 offsets × 5 methods) for each, at offsets `0-40`. | VERIFIED (tool, synthetic); pin OBSERVED (H5) | H5 observation 4; EXP-2026-11-05-49 |
| C-1739 | Pins are refuse-by-default: `--update` prints a table and exits 3, `--update --write` is the only writer; `--selftest` builds `cerom.build_synthetic_rom()` plus a missing-image case to prove PASS/FAIL/SKIP and `--require-image`, and `tools/selftest.py` discovers the suite. | VERIFIED (tool, synthetic) | this EXP; `python3 tools/selftest.py --only realcheck` |

## Conclusion

`tools/realcheck.py` exists and is wired into `tools/README.md` and
`tools/selftest.py` discovery. The synthetic proof is green; the H5 pins are
encoded with a single deliberate red check (`thunks`, C-1714). Running
`python3 tools/realcheck.py IMG256` is the remaining step; its expected exit is
1 with 7 PASS + 1 FAIL until M1.6c. No vendor bytes entered the repository.

## Follow-ups

- [ ] Run `python3 tools/realcheck.py IMG256` where the slice is available and
      record the eight lines and the exit code.
- [ ] After M1.6c, re-run; if the real stub count is not 846, re-pin with
      `--update --write` in an EXP that explains the change.
- [ ] Optional: pin the other H5 `coredll.dll` ordinals (59/65/66/496/1047/
      1118/1143/1145) as a second exports check for M2.1.
