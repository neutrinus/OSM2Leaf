# EXP-2026-11-09-H39: `ze0-viewer/harness.py info` tolerates opaque/unparseable records

- **Status:** done (synthetic crash path + wrapper; real vendor tile not available in this environment)
- **Date:** 2026-11-09
- **Sample:** synthetic tile generated in-process by `tile_diff.make_synthetic_tiles` (no vendor data). One section-1 shape record's compressed bytes were corrupted after the 2-byte zlib header so `clarion_tile.is_zlib` remains true but `zlib.decompress` fails. Corruption and test performed in a temp dir via `python3 tools/ze0-viewer/harness.py --selftest`. Prior real-tile evidence for the same crash class is EXP-2026-11-08-M9.25-harness-opaque-crash (factory `B48R058R.DAT` SHA-256 `e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52`, 80 unreadable zlib records, outside repo).
- **Tools:** `python3` 3.15.0; repo tools `tools/ze0-viewer/harness.py` (modified), `tools/tile_diff.py` + `tools/ze0-viewer/tools_ze0/clarion_tile.py` + `tile_scan.py` (synthetic fixture/corruption, unmodified).
- **Claims:** C-3180, C-3181, C-3182, C-3183
- **Supersedes:** none (M9.25 fixed the census crash; H39 hardens reporting/offsets and adds container-parse wrapper + synthetic fixture)
- **Superseded by:** none

## Question

Can `harness.py info` report opaque/bad/unparseable records with counts and locators without crashing, while leaving `verify` behavior unchanged for checked cases, and can the crash path be covered by a synthetic fixture when vendor tiles are unavailable?

## Hypothesis

M9.25 already catches zlib/classification failures in the `cmd_info` census. H39 can complete the task by (1) reporting a locator per unreadable record (byte offset when present in the parsed record, else `dir/slot/k` container locator — never a fabricated `0x0`), (2) wrapping `read_tile`/header/bbox parsing in `harness.py` so vendored container-parse failures are reported clearly with an optional `tile_scan` fallback instead of a traceback, and (3) adding a synthetic `--selftest` that corrupts a zlib record in a generated tile. Falsifier: `info` crashes on the synthetic bad-record tile, reports no unreadable count/locator, or `verify` changes on the clean synthetic tile.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | synthetic `BAD.DAT` (temp, no vendor data) derived from `tile_diff.make_synthetic_tiles` output |
| SHA-256 | not pinned (generated per run by `harness.py --selftest`; corruption is deterministic given the synthetic tile + first scanned zlib record) |
| Offset(s) / VA(s) | n/a (synthetic record corruption at scanned zlib record offset +2/+3/+10 bytes) |
| Tool / version | `python3` 3.15.0 |
| Repo tool | `tools/ze0-viewer/harness.py`, `tools/tile_diff.py`, `tools/ze0-viewer/tools_ze0/tile_scan.py` |

## Method

1. **Code change (`harness.py` only).** Refactor `cmd_info` census into `_print_tile_census`; collect unreadable/opaque records and report `unreadable/opaque N (at <locator>, ...)` where locator is `0x<off>` if `rec['off']` is available else `dir 0x<dir_off> slot <n> k <n>`. Wrap header/bbox parsing and `clarion_tile.read_tile` in `cmd_info`; on `read_tile` failure, report `container parse failed (vendored read_tile): ...` and attempt `cmd_scan` fallback, else report `no census available`. No changes to `cmd_verify` or vendored `tools_ze0`.
2. **Synthetic fixture / selftest.** Run:

```bash
cd /home/marek/projekty/OSM2Leaf-H39
python3 tools/ze0-viewer/harness.py --selftest
```

The selftest creates a clean synthetic tile, copies it, corrupts the first scanned zlib record payload while keeping the 2-byte zlib header valid (`is_zlib` true, `zlib.decompress` fails), runs `info` on the bad tile and asserts exit path reports `unreadable/opaque` with a locator, runs `info` on the clean tile and asserts no unreadable/opaque/container-parse failure, then runs `verify` (quiet) on the clean tile and asserts it still passes.

3. **Controls.** *Positive*: synthetic bad-zlib record triggers `zlib.decompress` failure in census and must be reported, not crash. *Negative*: clean synthetic tile must keep normal census and `verify` pass. *Regression guard*: `cmd_verify` source unchanged (confirmed by diff) — M9.25's real-tile verify cases (B30R048R/B28R070R/B30R060R/B58R070R) could not be rerun here because vendor tiles are unavailable outside this environment; the change is confined to `cmd_info`/helpers.
4. **Scope.** `harness.py` `cmd_info` path and new helpers/selftest. 1 synthetic bad tile + 1 clean synthetic tile. Not covered: real `B48R058R` rerun in this environment (covered by M9.25 EXP SHA-256/command transcript), `decode`/render paths, `tools_ze0` parser semantics.
5. **Falsifier.** Traceback/crash on synthetic bad tile; missing unreadable/opaque count or locator; clean-tile verify fails; or `git diff` touches `cmd_verify`/vendored `tools_ze0`.

## Observations

`harness.py --selftest` (2026-11-09, worktree `task/h39-ze0-viewer-info`):

```text
ok: info reports unreadable/opaque record with locator
ok: clean synthetic tile has no unreadable/opaque records
ok: verify unchanged on clean synthetic tile
harness H39 selftest: PASS
```

Manual synthetic `info` output (temp file, same corruption method):

```text
file    /tmp/.../bad.DAT
size    55040 bytes
sha256  bc8b5290e7cbec296a962f9cbd6e11c1b079c2ffb80d85eabbc4f4547cb6c2bc
...
section 1: table at 0x1000, 1 levels
  level 1 type 0x92 dirs 3: background 0, shape 2, graph 0, raw 0, unreadable/opaque 1 (at dir 0x1100 slot 0 k 0)
```

Process exited 0 (no traceback). The locator is container-relative (`dir/slot/k`) because the parsed `clarion_tile` record model does not carry a byte offset.

Malformed-input check: `harness.py info /dev/null` exits without traceback and reports `header/bbox parse error (reported, not fatal)`, `container parse failed (vendored read_tile)`, and `no census available (opaque/unparseable container)` after the scan fallback cannot read `/dev/null`.

Diff scope: `git diff` shows only `tools/ze0-viewer/harness.py` changed in this implementation commit; `cmd_verify` and `tools/ze0-viewer/tools_ze0/*` are untouched.

## Interpretation

- **FACT (VERIFIED):** `harness.py info` reports an unreadable/opaque census record with a count and a locator and exits without crashing on a synthetic tile whose record passes `is_zlib` but fails `zlib.decompress` (M9.25 crash class).
- **FACT (VERIFIED):** `harness.py info` reports vendored `read_tile`/header/bbox parse failures without traceback and attempts a `cmd_scan` fallback (wrapper in `harness.py`; vendored parser unchanged).
- **FACT (VERIFIED):** `cmd_verify` is unchanged and still passes on the clean synthetic tile under the H39 selftest.
- **OBSERVED (not re-verified here):** M9.25 already recorded factory `B48R058R` as `unreadable 80`, exit 0, with unchanged control-tile `verify` behavior (EXP-2026-11-08-M9.25-harness-opaque-crash, vendor tile outside repo). H39 does not contradict that evidence and preserves the census-failure handling.
- **LIMITATION:** Parsed `clarion_tile` records lack byte offsets in the current model, so locators are `dir/slot/k` unless a future reader/scan path supplies `off`. This is reported honestly (never `0x0`). Real-vendor-tile rerun was not possible in this environment.

## Conclusion

H39 makes `harness.py info` degrade gracefully on opaque/unparseable records: the census reports `unreadable/opaque N` with locators, and container/header parse failures are caught in `harness.py` with a scan fallback attempt. `verify` and vendored `tools_ze0` are unchanged. The known crash path is covered by `python3 tools/ze0-viewer/harness.py --selftest` (synthetic, no vendor data).

## Reproduction

```bash
cd /home/marek/projekty/OSM2Leaf-H39
python3 tools/ze0-viewer/harness.py --selftest
# expected: ok/info unreadable+locator, ok/clean, ok/verify, PASS

# optional malformed-container check (no traceback expected)
python3 tools/ze0-viewer/harness.py info /dev/null
```

Real-tile check from M9.25 (requires vendor data outside repo):

```bash
python3 tools/ze0-viewer/harness.py info /home/marek/projekty/leafre-work/m5.4/ex/MAPAL001/B48R058R.DAT
# expected by M9.25: exit 0, reports unreadable records (count format now includes locators)
```

## Follow-ups

- [ ] Rerun `harness.py info` on factory `B48R058R` in an environment with vendor tiles and record the exact post-H39 output/SHA-256 in a follow-up note if needed.
- [ ] If byte offsets for parsed records are useful, expose them from vendored/reader models in a scoped task (Stop condition path would apply).
- [ ] If `decode`/render paths crash on the same unreadable-record class, handle in a separate task (M9.25 follow-up note).
