# EXP-YYYYMMDD-NN: Short title

- **Status:** planned | running | done | inconclusive | failed | refuted
- **Date:** YYYY-MM-DD
- **Sample:** image/file name + SHA-256, **or** `none (tool-only task)` — a
  record with a sample and no hash is a defect, a record with no sample must say
  why
- **Tools:** every tool used with its version (`python3 3.13.1 / zlib 1.3.1`,
  `capstone 5.0.7`, `qemu 8.2.7`, `objdump` from `binutils-sh4-linux-gnu`), and
  for repo tools the path
- **Claims:** C-xxx, C-yyy
- **Supersedes:** EXP-... (or `none`)
- **Superseded by:** EXP-... (or `none`)

## Question

One sentence. What exactly are we trying to determine?

## Hypothesis

What do we expect, and why? Use `none / exploratory` if this is a probe.
State the **falsifier**: the observation that would prove the hypothesis wrong.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `...` |
| SHA-256 | `...` |
| Offset(s) / VA(s) | `0x...` |
| Tool / version | `...` |
| Repo tool | `tools/....py` (the one that produced the numbers) |

## Method

A **spec**, not a narrative. Five parts, in this order:

1. **Sample and hash.** The exact file, byte range and SHA-256 above.
2. **Commands.** Runnable as written, in one block. Either a committed tool
   (`python3 tools/x.py IMG --flag`) or the complete script pasted in. **No
   ellipsis** (`# ...`), no "and similar steps", no "see the session": an
   elided command means the result cannot be re-run, which is the same as no
   result. If the scan lived in a heredoc, the task that needed it commits it
   to `tools/` with a `--selftest` (AGENTS rule 7) before the EXP is closed.
3. **Controls.** *Positive*: the same method applied to a case that is known
   to exist and must be found (a string present in the image, a decoder that
   round-trips its own vector, a file the FAT walk does list). *Negative*: a
   case that must fail (a swapped field, a shuffled table, a truncated input).
   A negative claim without a positive control is not a result.
4. **Scope.** The bytes/files/modules actually covered, and what is excluded
   and why (e.g. "build-A uncompressed sections only; 56.2 % of build A is
   compressed, see rule 14"). Count the corpus (`527 sections / 23.6 MB`), do
   not say "all".
5. **Falsifier.** What would have refuted the claim; state it before the
   result so a reader can judge whether the test could fail.

## Observations

Raw results only: counts, hexdumps, error messages. No interpretation yet.
Every number that the Conclusion will rely on appears here.

## Interpretation

- **FACT:** ...
- **OBSERVED:** ...
- **HYPOTHESIS:** ...
- **UNKNOWN:** ...

## Conclusion

What changed in `docs/format/` and `docs/research/claims.md`? What is still
open? One paragraph that a reader could check against the Observations.

## Reproduction

One block that re-runs the headline result from the repository and the sample:

```bash
python3 tools/....py <sample> <flags>     # expected: <the number above>
```

## Follow-ups

- [ ] ...
