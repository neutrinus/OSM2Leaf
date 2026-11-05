# AGENTS.md

Instructions for humans and AI agents working in this repository.

## What this project is

`OSM2Leaf` is a **research project** investigating whether map data for the
Nissan Leaf ZE0 (2011–2012) navigation unit can be generated from
OpenStreetMap and written back to the car's map SD card.

Current status: **reverse engineering / research only**. Nothing in this
repository is installed in a car. Do not present experimental output as
production-ready.

## Language

- All repository content — code, comments, documentation, commit messages,
  issue titles — is written in **English**.
- Conversation with the project owner may happen in Polish.
- Use metric units and ISO dates.

## Hard rules

1. **Never commit proprietary vendor data.**
   Original Nissan/Clarion/Hitachi map images, SD card dumps, extracted
   filesystems, firmware, `.DAT`/`.cmp`/`.ind` files, voice packs and icons
   belong in `archive/` (git-ignored) or outside the repository.
   Only commit scripts, documentation, hashes, tiny synthetic fixtures and
   analysis notes that do not reproduce vendor content.
2. **The original SD card is read-only.**
   Back it up first (`dd` / `ddrescue`), verify the hash, and test only on a
   spare card.
3. **Research before writing to hardware.**
   A change that cannot be validated offline must not be proposed as ready for
   the car.
4. **Keep the license clean.**
   Code is GPL-3.0-or-later. OSM-derived data is ODbL-1.0. Do not copy code
   from projects with incompatible licenses; link to them instead.
5. **Do not guess in documentation.**
   Mark verified facts and hypotheses separately. Cite the evidence (file
   offset, hash, external URL) for every non-obvious claim.

## Repository layout

```
README.md              project overview and documentation index
AGENTS.md              this file
TODO.md                backlog / open tasks
LICENSE                GPL-3.0
docs/format/           reverse-engineered on-disk formats
docs/research/         sources, market/version comparison, open questions
tools/                 small, dependency-light analysis scripts
archive/               git-ignored vendor data and work-in-progress extracts
```

## Code conventions

- Python 3.10+, standard library only unless a dependency is clearly justified.
- Scripts must be runnable directly (`python3 tools/foo.py ...`) and must not
  hard-code absolute paths from the author's machine.
- Read-only by default. Any script that writes or modifies an image gets an
  explicit output path argument and refuses to overwrite its input.
- Prefer `argparse`, type hints where they help, and small pure functions.
- Hex offsets in documentation use `0x` prefix and lower-case hex digits.
- Add a short module docstring explaining what was verified and against which
  sample.

## Commit conventions

Commits should look like a careful human's history: small, logical, and
self-contained.

- One concern per commit.
- Imperative subject line, max ~72 characters, no trailing period.
- Conventional-ish prefixes are welcome: `docs:`, `tools:`, `format:`,
  `fix:`, `chore:`.
- Explain *why* in the body when the change is not obvious.
- Never commit generated binaries, images, caches or vendor data.
- Example:
  - `docs: describe the REFER001 .cmp/.ind container`
  - `tools: add a verified cmp/ind decoder`
  - `chore: add license and data-handling policy`

## Testing

- There is no CI yet. Before committing, run the tool you touched against at
  least one real sample from `archive/` and record the result in the commit
  body or in `docs/`.
- For format decoders, prefer a `verify` command that checks every file in a
  directory and prints a summary.
- Never test modified map images in a car without a verified backup and a
  spare SD card.

## When adding findings

- Put format details in `docs/format/`.
- Put external references in `docs/research/sources.md`.
- Put unresolved questions in `docs/research/open-questions.md` and actionable
  work in `TODO.md`.
- Register every new claim in `docs/research/claims.md` with an ID and one of
  the statuses `VERIFIED`, `OBSERVED`, `HYPOTHESIS`, `UNKNOWN`.
- Add the sample's SHA-256 when a finding depends on a specific image.

## Evidence discipline

This rule exists so that other agents and researchers can help without
re-deriving everything or trusting guesses.

1. **Separate facts from interpretations in every document.** Use explicit
   headings such as `Verified facts`, `Observations`, `Hypotheses`,
   `Unknown`.
2. **Every non-obvious claim carries a pointer**: file offset, byte pattern,
   command, or URL. If there is no pointer, it is a hypothesis by definition.
3. **Do not promote a claim silently.** Changing `HYPOTHESIS` to `VERIFIED`
   requires a reproducible check and a note in the commit message.
4. **State the sample.** A finding is only valid for the image/hash it was
   checked against; say which one.
5. **Negative results matter.** "We scanned X and found no PE files" is a
   useful verified claim; record the method and the scope.
6. **Prefer small, runnable checks.** A verification script under `tools/` is
   better than a screenshot or a prose description.
7. **When unsure, say so.** An explicit `UNKNOWN` is more useful to the next
   agent than a confident wrong statement.
