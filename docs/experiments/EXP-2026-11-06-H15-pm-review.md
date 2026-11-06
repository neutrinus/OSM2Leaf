# EXP-2026-11-06-H15: Sixth product review — two predictable negatives moved the critical path to compression

- **Status:** done (review; no format fact created)
- **Date:** 2026-11-06
- **Sample:** `IMG256` (first 256 MiB of the EU 2011 card), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`, plus the
  EU 2011 and US 2011 full images cited by the audited records. Nothing was
  re-measured here; every number below is quoted from the record named with it.
- **Claims:** none — a review creates no format claim.
- **Supersedes:** none
- **Superseded by:** none

## Question

Do the three results merged after the fifth pass (M2.15, M3.2b, M3.11/M3.12)
change the order of work, and are there results whose method — not whose
subject — is what failed? Three tasks in two days ended in "not found"; that is
either three facts about the firmware or one fact about the method.

## Hypothesis

None / exploratory. The suspicion after the fifth pass was that the board keeps
sending agents to search the readable half of the firmware: 245 of build A's
527 o32 sections are `IMAGE_SCN_COMPRESSED` and undecodable (M1.3), so a
"searched every section" negative that skips them is predictable, not
informative.

## Inputs

| Item | Value |
| --- | --- |
| Board | `TODO.md` at `origin/main` `9a32863` |
| Audited records | EXP-2026-11-06-M2.15, -M3.2b, -M3.11, -M3.12 |
| Image host | `https://files.viaaq.eu/sd-images/` (listed 2026-11-06) |
| Tools | `cerom.py`, `sh4xref.py`, `selftest.py`, `claims_check.py` (no vendor bytes committed) |
| Vendor data | none read in this task |

## Method

```bash
git fetch origin && git log --oneline origin/main -8
grep -rn "IMAGE_SCN_COMPRESSED\|compressed" docs/experiments/EXP-2026-11-06-M3.{2b,11}*.md
grep -rln "no vendor image\|not available on this machine" docs/experiments/
curl -s https://files.viaaq.eu/sd-images/            # listing: names, sizes, dates
python3 tools/selftest.py                            # 45 passed / 0 failed / 18 skipped
python3 tools/claims_check.py                        # clean
```

For each record: does the `Result` state a scope, and does that scope cover the
place the object can live? For each "blocked": is the named blocker a task that
exists, or an environment fact that rule 11 already rejects?

## Observations

### 1. The three merged results

| Task | Result | Consequence for the board |
| --- | --- | --- |
| **M2.15** | both launcher checks byte-specified: card side `HDD_INFO` line 1 / `MapDBVer`; unit side `KernelIoControl(0x0101302C)` `+96`/`+112`/`+114`, not the `0x06000000` copy (C-2080–C-2084); unit values unknown statically (C-2087) | M9.6 gets exact inputs; **M2.4's blocker is invalid** (see §3) |
| **M3.2b** | Navi.exe zlib 1.1.3 `inflateInit2_ 0x542256`, `inflate 0x54233c`, `inflateEnd 0x54220c`, wrapper `0x542148`, chunked engine `fn 0x41c7e8` (20-byte stride, no seek, no `78 9c` scan); **no caller of `0x41c7e8` in any uncompressed section** | `.cmp` file layer still unknown, **but the chunk engine is directly callable** → M9.11 re-scope (§2) |
| **M3.11** | access path `0x003fbed8` → `0x0040b358` → `0x004125a8` (`0x14e8` → `REFER001`+`INDEX003.DAT`) confirmed; page walker **not** in any uncompressed section (0 aligned tag pairs, 0 mask walkers, 0 stride sequences, 49 tag sites inspected, `fn 0x003715a0` rejected with controls) | M9.10 has no VA; blocked behind the decoder |
| **M3.12** | `REFER001/INDEX003.DAT` **absent** on EU 2011 and US 2011 (no FAT entry, no `DRSTR` entry); the firmware string `INDEX003` exists | the POI name search cannot be shadowed by an on-disk index on these cards → M5.12c narrows |

### 2. Why M9.11 can move now

M3.2b records `fn 0x41c7e8` as a **random-access decompressor that receives its
chunk table from the caller**: table at `@(28,ctx)`, 20-byte entries, with
`+8` = uncompressed offset, `+12` = uncompressed extent, `+16` = compressed
source and `+4` passed to the inflate wrapper as `r7` (C-2063). S1 only has to
answer one question — does the firmware's own zlib accept our recompressed
chunk bytes and return the same page. The `.ind` parser that *builds* that
table lives in the compressed section and is only needed for M3.2's
seek-vs-scan question, not for S1.

So M9.11 needs: the located VAs, a harness-built chunk table from `.ind`, and
the three `POINT010` pairs. That is a normal L3 target. Re-scoping it removes
M9.11 from the compression queue while leaving M3.2b where it was.

The risk this introduces is that the table layout is *inferred* from one
disassembly. The task therefore requires a negative control — one deliberately
wrong field (swapped `+4`/`+8`) must fail — so the layout is proven by the run,
not assumed.

### 3. Blockers that were not blockers

| Task | Recorded blocker | Reality |
| --- | --- | --- |
| **M2.4** | "firmware verdicts require the real L3 target (M9.6), unavailable offline" | M9.6 runs the comparator **offline** with a stubbed `KernelIoControl`; M2.15 supplied its inputs. The task waits for M9.6 (a task, not an environment fact). Removed. |
| **M5.13** | "no vendor image on this machine" | `https://files.viaaq.eu/sd-images/` is reachable and rule 11 forbids this blocker. M5.13b now lists the download as an input. |
| **M5.12b** | same | folded into M5.13b |
| **M8.A4 / M8.A5** | "vendor image not present; no boot was run" | correct that no boot ran, but the image was downloadable; M8.A2 is the task that boots, and it is now unblocked |

`grep -rln "no vendor image\|not available on this machine"
docs/experiments/` returns 10 records, four of them from this round.

### 4. Image host listing (2026-11-06)

| File | Size | Last modified |
| --- | --- | --- |
| `LEAF_2011-2012_QSD-309-101_navi158_eu.img` | 7.5 G | 2025-11-03 |
| `LEAF_2011-2012_US.img` | 7.5 G | 2026-11-05 |
| `LEAF_2014_EU_QSD-357-101.img` | 7.4 G | 2025-09-17 |
| `ENV200_2016_EU_QSD-390-100.img` | 7.4 G | 2025-09-17 |

The US image was re-published on 2026-11-05, the day before this review.

### 5. Verification

```
$ python3 tools/selftest.py 2>&1 | tail -2
passed=45 failed=0 skipped=18 total=63
selftest: OK

$ python3 tools/claims_check.py
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
claims_check: OK
```

## Interpretation

- **FACT:** two of the three merged M3 tasks ended in a negative whose only
  escape is the CE compression codec (M1.2f / M8.E1). 245 of 527 build-A o32
  sections are compressed, so a search over uncompressed sections alone cannot
  refute a reader that lives in `Navi.exe` sec1 — and M3.11's own hypothesis
  says exactly that.
- **FACT:** M3.2b's negative is narrower than it looks: the chunk *engine* is
  located and callable, only the table *builder* is hidden. That is enough to
  test S1, which is why M9.11 moves ahead of M3.2 instead of behind it.
- **FACT:** one blocker (M2.4) named an environment limitation that does not
  exist, and four records cite an image that the allowed host serves. Both
  shapes waste a whole session when an agent acts on them.
- **OBSERVED:** the board rewards "found a VA" over "proved a scope". The two
  negatives are good work and were logged correctly; the planning layer is
  what failed, by ordering the searches before the decoder.
- **HYPOTHESIS:** with M1.2f done, M3.2b's `.ind` layer and M3.11's walker will
  both be findable in one session each, because the access path and the
  surrounding call graph are already mapped.
- **UNKNOWN:** whether the walker's absence from uncompressed code also holds
  for `ADDRE`/`ZCODE`/`LCTBL` readers (M3.13–M3.15). Rule 14 now forces the
  next agent to answer that *before* searching.

## Conclusion

The board now states the compression dependency up front, moves M9.11 ahead of
it, blocks M9.10 explicitly instead of leaving it "ready", removes M2.4's
invented blocker, and narrows M5.12c with M3.12. Two new rules/tasks close the
method gap: **rule 14** ("a scoped negative must name its escape") and **H16**
(`tools/fetch_image.py` with pinned URLs and SHA-256). No format doc changed
because the three audits produced no new format fact beyond what their own
records already claim.

## Follow-ups

- [ ] **M1.2f** — decode (or **M8.E1** — call the real decompressor); every
      software-side task in M3/M9 now waits here.
- [ ] **M9.11** in its new scope — the cheapest remaining proof that the unit
      will read a recompressed file.
- [ ] **M8.A2** — the single `build.sh --force` that reconciles the three M8
      patch series (carried over from H12).
- [ ] Re-run this audit as H17 after the next batch; the two checks that found
      everything here are `grep -rln "no vendor image" docs/experiments/` and
      "does every blocked task name a task or an environment fact?"