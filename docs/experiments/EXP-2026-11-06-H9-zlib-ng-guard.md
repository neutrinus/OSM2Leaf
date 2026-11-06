# EXP-2026-11-06-H9: zlib runtime guard against false `FAIL` on zlib-ng

- **Status:** done (tool + docs; real-file replay not possible on this machine)
- **Date:** 2026-11-06
- **Sample:** none — this experiment adds a tool guard and uses only synthetic
  data. No vendor image, `.cmp`/`.ind`, `.DAT` or map tile was read or written.
  The observed interpreter is `Python 3.14.4` with `zlib 1.3.1` / runtime
  `1.3.1` (stock, see below).
- **Claims:** C-1970–C-1973 (recorded here only; `claims.md` is not edited by
  this task)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a tool that recompresses map data distinguish "my decoded payload/model is
wrong" from "this interpreter links zlib-ng", so a correct rebuild is never
reported as `FAIL` because of the compressor build?

## Hypothesis

zlib-ng inflates correctly and recompresses to a different (valid) stream, so
the payload, not the data, is what a zlib-ng machine gets wrong. Reporting the
runtime version (`zlib.ZLIB_VERSION` + `zlib.ZLIB_RUNTIME_VERSION`) and giving
an identity-only mismatch its own non-zero **`UNVERIFIABLE`** exit makes the
distinction explicit without weakening the real `FAIL`.

## Inputs

| Item | Value |
| --- | --- |
| Interpreter | `python3` = Python 3.14.4 (main, Aug 20 2026), GCC 15.2.0 |
| zlib | `zlib.ZLIB_VERSION` = `1.3.1`, `zlib.ZLIB_RUNTIME_VERSION` = `1.3.1` |
| Prior evidence | C-192 (zlib-ng reproduces 0/194 `.cmp`), C-997 (0 coarse streams), `docs/format/cmp-ind.md`, `AGENTS.md` zlib paragraph |
| Vendor data | none present on this machine (no `LEV3456R.DAT`, no `REFER001/`) |
| New tool | `tools/zlibinfo.py` (stdlib only) |

The TODO premise (H9 input) says "`python3` 3.14 (`zlib 1.3.1.zlib-ng`)".
**On this machine that is not true:** Python 3.14.4 links stock zlib 1.3.1, and
no `python3.13` exists under `/usr/bin/python3*`. The 3.13-vs-3.14 replay named
in the TODO done-when therefore cannot be run here; the classification path is
exercised with fake version strings instead (below). No zlib monkeypatching is
used anywhere: `classify()`/`guard()` take explicit version strings and a
`Runtime` value.

## Method

```bash
cd <repo>
python3 -c 'import sys,zlib;print(sys.version);print(zlib.ZLIB_VERSION, zlib.ZLIB_RUNTIME_VERSION)'
python3 -m py_compile tools/zlibinfo.py tools/lev3456.py tools/cmpind_writer.py tools/cmpind.py tools/ind_mutate.py
python3 tools/zlibinfo.py
python3 tools/zlibinfo.py --json
python3 tools/zlibinfo.py --require-stock-zlib
python3 tools/zlibinfo.py --selftest
python3 tools/lev3456.py --selftest
python3 tools/selftest.py

# guard behaviour on a synthetic pair (no vendor data)
mkdir -p /tmp/opencode/h9/pairs
python3 - <<'PY'
import pathlib, sys
sys.path.insert(0, "tools")
import cmpind_writer
dat = b"A"*0x10000 + b"test payload"*100
cmpind_writer.CmpFile.from_dat(dat).write(pathlib.Path("/tmp/opencode/h9/pairs"), "ADDRE001.DAT")
PY
python3 tools/cmpind.py verify /tmp/opencode/h9/pairs
python3 tools/cmpind.py verify /tmp/opencode/h9/pairs --json
python3 tools/cmpind_writer.py verify /tmp/opencode/h9/pairs
python3 tools/cmpind_writer.py recompress /tmp/opencode/h9/pairs/ADDRE001.DAT.cmp \
    /tmp/opencode/h9/pairs/ADDRE001.DAT.ind /tmp/opencode/h9/recomp ADDRE001.DAT
python3 tools/ind_mutate.py --ind /tmp/opencode/h9/pairs/ADDRE001.DAT.ind --out /tmp/opencode/h9/mut

# simulate zlib-ng through the public API (zlib untouched)
python3 - <<'PY'
import sys
sys.path.insert(0, "tools")
import lev3456, zlibinfo
ng = zlibinfo.classify("1.3.1.zlib-ng", "1.3.1.zlib-ng")
print(zlibinfo.describe(ng))
zlibinfo.guard(tool="cmpind_writer.py recompress", runtime=ng)
try:
    zlibinfo.guard(tool="lev3456.py verify", require_stock=True, runtime=ng)
except SystemExit as exc:
    print("SystemExit code:", exc.code)
print("verify exit:", lev3456.verify_verdict(ng, 0, 1))
print("rebuild exit:", lev3456.rebuild_verdict(ng, False, 62, 62))
PY
```

## Observations

Interpreter and runtime (stock, so the byte-identity claim is verifiable here):

```
3.14.4 (main, Aug 20 2026, 10:41:58) [GCC 15.2.0]
1.3.1 1.3.1
```

```
$ python3 tools/zlibinfo.py
zlib: zlib 1.3.1, runtime 1.3.1 (stock, reference build)
$ python3 tools/zlibinfo.py --require-stock-zlib ; echo $?
zlib: zlib 1.3.1, runtime 1.3.1 (stock, reference build)
0
$ python3 tools/zlibinfo.py --json
{
  "ok": true,
  "zlib_version": "1.3.1",
  "runtime_version": "1.3.1",
  "flavour": "stock",
  "reference": true,
  "message": "zlib 1.3.1, runtime 1.3.1 (stock, reference build)"
}
$ python3 tools/zlibinfo.py --selftest
zlibinfo selftest: OK (11 checks, fake zlib-ng strings, zlib untouched)
```

Stock path is unchanged (synthetic pair; `cmpind.py` prints no zlib line, the
recompressing tools do):

```
$ python3 tools/cmpind.py verify /tmp/opencode/h9/pairs
checked   1 pair(s)
ok        1
failed    0
logical   66736 bytes
stored    116 bytes             # exit 0

$ python3 tools/cmpind_writer.py verify /tmp/opencode/h9/pairs
zlib: zlib 1.3.1, runtime 1.3.1 (stock, reference build)
checked 1  ok 1  failed 0  logical 66736   # exit 0

$ python3 tools/cmpind_writer.py recompress ... ADDRE001.DAT
zlib: zlib 1.3.1, runtime 1.3.1 (stock, reference build)
recompressed: 66736 bytes in 2 chunk(s)   # exit 0

$ python3 tools/ind_mutate.py --ind .../ADDRE001.DAT.ind --out .../mut
wrote 8 variants + MANIFEST.txt to /tmp/opencode/h9/mut   # exit 0, no zlib line
```

`--json` carries the runtime: `cmpind.py verify --json` and
`cmpind_writer.py verify --json` both end with
`"zlib": {"ok": true, "flavour": "stock", "reference": true, ...}`; in JSON
mode the human-readable `zlib:` line goes to stderr so stdout stays parseable
(`json.load` succeeds on both).

Fake zlib-ng (no global patch; explicit version string + `Runtime`):

```
fake runtime: zlib 1.3.1.zlib-ng, runtime 1.3.1.zlib-ng (zlib-ng: not the reference compressor)
cmpind_writer.py recompress: zlib-ng cannot reproduce the factory streams, so a byte-identical result is UNVERIFIABLE here (exit 3). Re-run with stock zlib 1.3.1 (e.g. python3.13). Data-level checks still run and are reported normally.
lev3456.py verify: refusing to run: --require-stock-zlib needs stock zlib, this interpreter reports zlib-ng. Exit 3 (unverifiable), not a data failure.
SystemExit code: 3
UNVERIFIABLE: lev3456.py verify: 1 byte-identity check(s) differ while every payload re-encodes; the compressor, not the data, differs
zlib: zlib 1.3.1.zlib-ng, runtime 1.3.1.zlib-ng (zlib-ng: not the reference compressor)
This is not a data failure (exit 3). Re-run with stock zlib 1.3.1.
verify exit: 3
UNVERIFIABLE: lev3456.py rebuild: the rebuilt file differs although every decoded record re-encodes to its factory payload
rebuild exit: 3
```

Self-tests (stock machine; the zlib-ng assertions run on fake strings):

```
$ python3 tools/lev3456.py --selftest
selftest OK

$ python3 tools/selftest.py
... passed=34 failed=0 skipped=19 total=53 time=2.12s
selftest: OK
```

`python3 -m py_compile` over the five changed tools: no output, exit 0.

## Interpretation

- **FACT:** stock zlib 1.3.1 is what this machine links, so here the guard
  prints `(stock, reference build)` and every exit code is unchanged. The
  `zlib-ng` premise of H9 could not be reproduced in this environment.
- **FACT:** with fake `1.3.1.zlib-ng` strings the classifier returns
  `flavour=zlib-ng`, `ok=False`; `--require-stock-zlib` refuses with exit 3;
  `verify_verdict()`/`rebuild_verdict()` return 3 for an identity-only
  mismatch and 1 when a data check fails.
- **OBSERVED:** `cmpind.py verify` (decode only) prints nothing extra on stock
  zlib and only a note on a non-stock build, so the pinned "194/194 OK" output
  shape is preserved; `--json` adds the `zlib` object.
- **UNKNOWN:** whether a real zlib-ng interpreter reaches the same verdict on
  the real `LEV3456R.DAT` (SHA-256 `08a584fe…`) — no `python3.13`, no
  `zlib-ng` build and no vendor file exist on this machine.

## Conclusion

New `tools/zlibinfo.py` classifies the linked zlib from `ZLIB_VERSION` +
`ZLIB_RUNTIME_VERSION` and exposes `runtime_ok()`, `describe()`,
`describe_json()`, `guard()`, `note_if_nonstock()` and `unverifiable()`.
Exit **3** means *unverifiable*; **1** stays a data failure. Wired into
`lev3456.py verify/rebuild` (data vs identity counters, `--require-stock-zlib`),
`cmpind_writer.py verify/recompress` (`--require-stock-zlib`, `--json` on
verify), `cmpind.py verify` (non-stock note + `--json` `zlib` field) and
`ind_mutate.py` (note only; it never recompresses). `docs/format/cmp-ind.md`
gained a short "zlib runtime guard" section. Synthetic `--selftest` outcomes
are unchanged on stock zlib, and the zlib-ng path is asserted with fake version
strings.

## Claims (recorded here only)

C-1970–C-1979 are reserved for H9 by `TODO.md`; this task may not edit
`docs/research/claims.md`, so the claim text lives here and the ledger rows are
a follow-up.

| ID | Claim | Status | Confidence |
| --- | --- | --- | --- |
| C-1970 | `tools/zlibinfo.py` classifies the linked zlib from `zlib.ZLIB_VERSION` and `zlib.ZLIB_RUNTIME_VERSION`: both plain numeric and equal → `stock`; either containing `zlib-ng` → `zlib-ng`; anything else → `unknown`, with `ok` true only for `stock` and `reference` true only for the pinned 1.3.1. It exposes `runtime_ok()`, `describe()`, `describe_json()`, `guard()`, `note_if_nonstock()` and `unverifiable()`, and reserves exit **3 = unverifiable**, distinct from exit 1 = data/model `FAIL`. | VERIFIED (synthetic + stock run) | H |
| C-1971 | `lev3456.py verify`/`rebuild` print the zlib runtime, separate `data_bad` from `identity_bad`, and return 3 instead of 1 when the payload/model reproduces but the stream/region differs on a build that is not stock zlib; `--require-stock-zlib` refuses before doing any work with exit 3. On stock zlib 1.3.1 the verdicts and exit codes are unchanged. | VERIFIED (synthetic; stock path by construction) | H |
| C-1972 | `cmpind_writer.py verify`/`recompress` print the runtime and warn on a non-stock build (`--require-stock-zlib` refuses, exit 3); `cmpind.py verify` only decodes, so it prints a non-stock note and keeps its 194/194-PASS shape, with a `zlib` object in `--json`; `ind_mutate.py` never recompresses and gets an informational note only. | VERIFIED (synthetic) | H |
| C-1973 | The interpreter used here, Python 3.14.4, links stock zlib 1.3.1 (`ZLIB_VERSION` = `ZLIB_RUNTIME_VERSION` = `1.3.1`), so the TODO's `python3` 3.14 = `zlib-ng` premise does not hold on this machine and the 3.13-vs-3.14 replay cannot be produced here; the zlib-ng path is instead asserted with fake version strings, without monkeypatching `zlib`. | VERIFIED (observation) | H |

## Follow-ups

- [ ] Register C-1970–C-1973 in `docs/research/claims.md` (not owned by H9;
      this task may only add the claim text to the experiment).
- [ ] Add the zlib-runtime requirement sentence to `tools/README.md`
      (TODO H9 done-when names it; `tools/README.md` is not in H9's file
      ownership list).
- [ ] Re-run `lev3456.py verify` / `rebuild --level 5` on the 2011
      `LEV3456R.DAT` under a real zlib-ng interpreter and record the exit-3
      vs exit-0 contrast with the same SHA-256 (`08a584fe…`).
