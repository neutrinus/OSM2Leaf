# EXP-2026-11-05-54: A scored, auditable B-vs-C kernel selection procedure

- **Status:** done (procedure; no real-image verdict by design)
- **Date:** 2026-11-05
- **Sample:** none. Every input below is built by
  `tools/kernel_select.py` from synthetic ROMHDR/TOC data, plus the B/C field
  values already recorded in EXP-2026-11-05-36. The reference image is named
  only for the still-open real run: `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
  SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`.
- **Claims:** C-572 (proposed, `VERIFIED (tool, synthetic)`); C-529 unchanged
  (`UNKNOWN`)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can TODO M1.7 ("decide which kernel, B or C, boots with A") be turned into a
reproducible, auditable procedure whose verdict is only emitted when the
evidence actually separates the two candidates - and does the evidence
recorded so far separate them?

## Hypothesis

The recorded B/C fields (EXP-36) differ only in the module set (B carries the
updater set, C the test mode), so the procedure must return `UNKNOWN`. Any tool
that answers `B` from `UpdateMng.exe` presence alone would be encoding a
heuristic as a verdict.

## Inputs

| Item | Value |
| --- | --- |
| Tool | `tools/kernel_select.py` (new, stdlib only, imports `cerom.py`) |
| Fixture builder | `build_synthetic_segment()` inside the tool's `--selftest` |
| Recorded fields | EXP-2026-11-05-36: `physfirst`/`physlast`, `nummods`, `numfiles`, `ulRAMStart`, `pExtensions`, `usCPUType`; module-name lists for B/C |
| Vendor data | none used (no image, no extracted card) |

## Method

```bash
python3 -m py_compile tools/kernel_select.py
python3 tools/kernel_select.py --selftest
python3 tools/selftest.py --only kernel_select
```

The synthetic fixtures are generated through the repo tool (no second
reimplementation). Clear-B/C pair: one segment has the five kernel modules, the
updater set and `ulRAMEnd` closing at A's image start; the other has only the
kernel modules and a non-closing `ulRAMEnd`.

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "tools")
import kernel_select as ks
b, _ = ks.build_synthetic_segment(0x200, 0x88000000,
                                  ks.SYNTH_KERNEL_MODULES + ks.SYNTH_UPDATERS,
                                  files=["UpdateNK.skn"])
c, _ = ks.build_synthetic_segment(0x200, 0x88000000, ks.SYNTH_KERNEL_MODULES,
                                  ram=ks.SYNTH_RAM_OPEN)
open("/tmp/opencode/kselect/b.img", "wb").write(b)
open("/tmp/opencode/kselect/c.img", "wb").write(c)
PY
python3 tools/kernel_select.py --segment B=/tmp/opencode/kselect/b.img@0x200 \
                               --segment C=/tmp/opencode/kselect/c.img@0x200
```

The "recorded values only" fixture is a JSON document with the EXP-36 numbers
and module names and no entry/payload data:

```bash
python3 - <<'PY'
import json
kernel = ["nk.exe", "coredll.dll", "filesys.exe", "device.exe", "gwes.exe"]
doc = {"segments": [
  {"label": "B", "segment_base": 0x03E00200,
   "romhdr": {"physfirst": 0x88000000, "physlast": 0x886E18A4, "nummods": 91,
              "numfiles": 11, "ulRAMStart": 0x89E40000,
              "pExtensions": 0x880030A4, "usCPUType": 0x01A6},
   "modules": [{"name": n} for n in kernel + ["UpdateMng.exe", "PRGUpdate.exe",
              "MapUpdate.exe", "BtUpdate.exe", "DisplayUpdate.exe"]]},
  {"label": "C", "segment_base": 0x05200200,
   "romhdr": {"physfirst": 0x88000000, "physlast": 0x886683D8, "nummods": 88,
              "numfiles": 10, "ulRAMStart": 0x89E40000,
              "pExtensions": 0x880030A4, "usCPUType": 0x01A6},
   "modules": [{"name": n} for n in kernel + ["TestMode.exe", "SdCardLch.exe"]]},
]}
json.dump(doc, open("/tmp/opencode/kselect/recorded-bc.json", "w"), indent=2)
PY
python3 tools/kernel_select.py --from-json /tmp/opencode/kselect/recorded-bc.json
```

## Observations

Build/self-test:

```text
$ python3 -m py_compile tools/kernel_select.py
(exit 0)

$ python3 tools/kernel_select.py --selftest
kernel_select selftest: 61 checks OK (synthetic segments, no vendor data)

$ python3 tools/selftest.py --only kernel_select
tool:kernel_select  PASS  0.09s

passed=1 failed=0 skipped=0 total=1 time=0.09s
selftest: OK
```

Synthetic clear-B run (0x0cae1000 A image, 0x09e40000-0x0cae1000 A RAM; ROM
span is physical, ROMHDR value is `0x88000000`). The A-plan line and the
per-criterion evidence block are trimmed; every criterion still shows its
status and score:

```text
kernel_select: 2 segment(s) evaluated: B@0x00000200, C@0x00000200
segments:
  #  label  base        rom_first   rom_last     score  decis  gates
  0  B      0x00000200  0x08000000  0x08040000     +13    7/7  ok
  1  C      0x00000200  0x08000000  0x08040000      +8    6/7  ok

criterion      weight  B                   C
ram_overlap         3  pass +3             unknown +0
ram_window          2  pass +2             pass +2
p_extensions        1  pass +1             pass +1
kernel_modules      3  pass +3             pass +3
updater_set         1  pass +1             fail -1
entry_point         3  pass +3             pass +3
duplicate           0  pass +0             pass +0

verdict: B
  B +13 vs C +8; discriminators: ram_overlap (pass/unknown), updater_set (pass/fail); structural: ram_overlap
```

The C row's `ram_overlap` evidence is `ulRAMEnd 0x8ca00000 (physical
0x0ca00000) does not close at A's image start 0x0cae1000`; the B row's is
`ROM span 0x08000000-0x08040000 sits below A's RAM 0x09e40000-0x0cae1000 and
ulRAMEnd 0x8cae1000 (physical 0x0cae1000) closes exactly at A's image start`.

Recorded B/C values only, no vendor bytes:

```text
segments:
  #  label  base        rom_first   rom_last     score  decis  gates
  0  B      0x03e00200  0x08000000  0x086e18a4      +5    3/7  ok
  1  C      0x05200200  0x08000000  0x086683d8      +3    3/7  ok

criterion      weight  B                   C
ram_overlap         3  unknown +0          unknown +0
ram_window          2  unknown +0          unknown +0
p_extensions        1  pass +1             pass +1
kernel_modules      3  pass +3             pass +3
updater_set         1  pass +1             fail -1
entry_point         3  unknown +0          unknown +0
duplicate           0  unknown +0          unknown +0

verdict: UNKNOWN
  only one criterion separates B from C (updater_set (pass/fail)); a single criterion is not enough for a verdict
```

The remaining self-test cases assert: `--segment` on a
`cerom.build_synthetic_rom()` image gives an incomplete kernel set and
`UNKNOWN`; the mirrored fixture gives `C`; two segments whose criterion
statuses are identical (payload bytes differ only in padding) give a score tie
and `UNKNOWN`; app-only module lists fail `kernel_modules` on both sides and
give `UNKNOWN`; a byte-identical B/B pair plus a C with a broken `nk.exe`
entry gives `B` with the copy's `duplicate` = `fail` naming the original; the
same pair copied twice inside one image (0x200 and 0x50200) is caught the same
way (`byte-identical to B at 0x00000200`), so the real A/A-copy and B/B-copy
pairs cannot look like extra opinions; the pair without C asks for C;
`--json` -> `--from-json` reproduces verdict, scores and statuses; a
`memmap`-shaped JSON infers the label from `segment_base` and leaves
`entry_point`/`duplicate` `unknown`.

## Interpretation

- **FACT:** the procedure is executable and deterministic: 61 synthetic
  checks pass, the whole suite is registered by `tools/selftest.py`, and the
  JSON report round-trips through `--from-json` with identical statuses.
- **FACT:** with only the EXP-36 values, exactly one criterion differs
  (`updater_set`), the tool refuses a verdict, and the reason string names
  that single difference. This is C-529 expressed as code.
- **OBSERVED:** on synthetic input a verdict appears only when a structural
  criterion (`ram_overlap` here) differs as well; the updater set alone is
  deliberately weight 1 and cannot decide.
- **HYPOTHESIS:** if B and C really share `physfirst`, `ulRAMStart`,
  `pExtensions` and the kernel module set (as EXP-36 suggests), then
  `ram_overlap`, `p_extensions` and `kernel_modules` will pass for both on the
  real image too, and the remaining honest discriminators are (a) `ulRAMFree`
  /`ulRAMEnd` if they differ, (b) the contents behind `pExtensions`, (c) the
  `e32_entryrva`/entry bytes of `nk.exe`, (d) an IPL/flash or
  `UpdateMng.exe` selection path. Only (a)-(c) are inside this tool.
- **UNKNOWN:** which build the IPL actually copies, and therefore the real
  verdict. No vendor data was read for this EXP.

## Conclusion

`tools/kernel_select.py` now exists: seven explicit criteria, per-criterion
`pass`/`fail`/`unknown` with an evidence string, gate criteria, a
discriminator rule that forbids name-only verdicts, and `--json`. The tool is
pinned by 61 synthetic checks (no vendor data) and documented in its module
docstring, which separates verified inputs from heuristics criterion by
criterion.

Nothing in `docs/format/` changed, because no new format fact was produced.
C-572 (proposed) records the tool and its refusal rule. C-529 stays `UNKNOWN`.
TODO M1.7 stays open: its "decide which kernel boots" is not done.

## Follow-ups

- [ ] Run the real pair once the image is available (read window 128 MiB
  covers all five segments):
  `python3 tools/kernel_select.py --segment A=IMG@0x200200 --segment B=IMG@0x3e00200 --segment C=IMG@0x5200200 --json --out /tmp/opencode/ks-real.json`.
  Also feed the B copy (`0x4800200`) as a second `B=` row: it must be reported
  as byte-identical to B, not as a third opinion.
- [ ] Record `ulRAMFree`/`ulRAMEnd` and `ulRAM*` for B/C (still *not recorded*
  in `docs/format/cerom.md`) - the fastest way to make `ram_overlap`
  decisive.
- [ ] Dump the `pExtensions` block (`0x880030a4`) of B and C and compare it;
  if it encodes a boot/update flag, that is a second structural discriminator.
- [ ] Read `UpdateMng.exe` (B) for the update/selection flow (TODO M1.7's
  third source); this is code, not ROMHDR, and the tool cannot see it.
- [ ] Only when one of the above yields a second structural difference should
  M1.7 be ticked; report the verdict together with the evidence strings from
  `--json`, not as a bare `B`/`C`.
