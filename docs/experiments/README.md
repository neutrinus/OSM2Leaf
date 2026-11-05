# Experiments

This directory is the **append-only record of what we tried**. It exists so a
future researcher can reproduce a result, challenge it, or avoid redoing it.

The repo uses two layers:

| Layer | Location | Changes |
| --- | --- | --- |
| Current knowledge | `docs/format/*.md`, `docs/research/claims.md` | Updated continuously; reflects the best current answer |
| Experiment log | `docs/experiments/EXP-*.md` | Append-only; one record per experiment, not rewritten after completion |

If the current knowledge changes, update the format doc and the claim ledger.
Do **not** rewrite the old experiment; add a new one and link
`Supersedes: EXP-...`.

## Naming

```
EXP-YYYYMMDD-NN-short-slug.md
```

Example: `EXP-2026-11-05-01-drstr-node-table.md`.

## Status values

| Status | Meaning |
| --- | --- |
| `planned` | Question and method defined, not run |
| `running` | In progress |
| `done` | Ran to completion; conclusion recorded |
| `inconclusive` | Ran, but the result does not answer the question |
| `failed` | Could not run (missing sample, tool, hardware) |
| `refuted` | Ran and disproved the hypothesis |

## What every record must contain

Start from [`TEMPLATE.md`](TEMPLATE.md). At minimum:

1. **Question** — one question, not a topic.
2. **Hypothesis** — what you expect, or `none / exploratory`.
3. **Inputs** — sample name + SHA-256, file offsets, tool versions.
4. **Method** — exact commands, rerunnable by another person.
5. **Observations** — raw outputs, hexdumps, counts. Do not mix interpretation
   into this section.
6. **Interpretation** — `FACT` / `OBSERVED` / `HYPOTHESIS` / `UNKNOWN`.
7. **Conclusion** — which claims and format docs changed.
8. **Follow-ups** — new questions, with links to `TODO.md`.

## Reproducibility checklist

- Pin the input by SHA-256, not just a filename.
- Use a command that works from a clean checkout + the external sample.
- Prefer `tools/` over ad-hoc one-liners; add a small tool if needed.
- Record negative results; they prevent repeated dead ends.
- Never commit vendor data. Put images/extracts in `archive/` or `/tmp` and
  record only hashes, offsets and tiny non-vendor outputs.
- If the experiment depends on hardware (car/unit/card), say so and mark the
  status honestly.

## Linking

```
format doc  ->  claim ID  ->  EXP record  ->  tool command
```

- Format docs cite claim IDs, not experiment narratives.
- `claims.md` evidence should cite the `EXP-...` ID and/or a command.
- Experiment records list the claims they created or changed.

## Index

| ID | Title | Status |
| --- | --- | --- |
| [EXP-2026-11-05-01](EXP-2026-11-05-01-drstr-node-table.md) | Correct DRSTR001.DAT node table | done |
| [EXP-2026-11-05-02](EXP-2026-11-05-02-refer-poi-rename.md) | Same-length POI rename in REFER001 | done offline; hardware pending |
| [EXP-2026-11-05-03](EXP-2026-11-05-03-checksums.md) | Firmware checksums and per-file integrity | done |
| [EXP-2026-11-05-04](EXP-2026-11-05-04-tile-roundtrip.md) | ZE0 tile round-trip and viewer | done for clean tiles; dense tiles open |
| [EXP-2026-11-05-05](EXP-2026-11-05-05-firmware-crosscheck.md) | Firmware section table and reader cross-check | done (readers not located) |
