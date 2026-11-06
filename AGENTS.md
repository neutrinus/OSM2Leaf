# AGENTS.md

Research repo for generating Nissan Leaf ZE0 (2011–2012) navigation maps from
OpenStreetMap. **Research only** — nothing here is validated in a car, and
hardware access is currently unavailable. All repo content (code, docs,
commits) is English; conversation may be Polish.

## Where the truth lives

| Question | File |
| --- | --- |
| Is this fact established? | `docs/research/claims.md` — canonical ledger, trust it over prose |
| What does this format look like? | `docs/format/*.md` — living pages |
| What is being done now? | `TODO.md` — the board, rules 1–16, task blocks |
| Can the firmware read our file? | `docs/research/reader-coverage.md` — 30-row matrix |
| What was tried and why did it fail? | `docs/experiments/EXP-*.md` — append-only |

Evidence flow: `format doc → claim ID → EXP record → tool command`. A claim
without a reproducible command is a hypothesis; mark it so.

## Taking a task (parallel agents)

~15 agents work from `TODO.md` at once. The full rules are in `TODO.md`
("How to take a task"); the ones that get broken:

1. Pick an `open` task whose `Depends` are `done` and whose ID appears in no
   open PR title.
2. **First commit claims it**: change only your task's line to
   `Status: in progress · Owner: <branch>`, then `git push -u origin <branch>`
   before any other work, and open a draft PR `[ID] short title`. An unpushed
   claim is invisible.
3. One task per PR; touch only your task's files, your EXP, your claim rows.
4. **Last commit**: the work plus `Status: done`, `[x]` and a `Result:` line
   naming the EXP. `done` requires the task's own `Done when` check to pass —
   if it did not, the status is `blocked`, never `done`.
5. **Merge to `main` yourself** (a task is done only when its commits are on
   `origin/main`), delete the branch, close leftover drafts. Never force-push
   `main`.
6. Blocked is a result: `Status: blocked` + a one-line blocker + `Unblock:`
   naming the task that re-opens it + a negative EXP. When the unblocking task
   merges, its PR sets you back to `open` (rule 15).

## Before you search firmware code

Two facts cost this project whole sessions:

- **SH-4 code in this image is little-endian.** A big-endian search finds
  nothing *and looks like a refutation* (M8.E1 vs M8.E1b). Decode halfwords LE.
- **56.2 % of build A's section bytes are compressed** (30.2 MB of 53.7 MB;
  245 of 527 o32 sections). `Navi.exe` is **75.1 % compressed** (16.7 MB in
  `sec1`, flagged `rw-`, not `r-x` — so "executable sections" excludes it).
  A "searched every uncompressed section, not found" negative describes ~44 %
  of the image and ~25 % of `Navi.exe`; it is expected, not informative.

So: run `cerom.py memmap --json` first and put the covered corpus in the EXP.
Compressed sections are undecodable until M1.2f (port `DECOMP_BLK`) or M8.E1;
the decompressor entry points are verified: `DECOMP_WRAP 0x88037590`,
`DECOMP_SECT 0x88037464`, `DECOMP_BLK 0x8803a384` (loader flag test
`0x88038666` in `fn 0x880385e4`).

## Commands

Vendor images are **not** required for most work, and "no image on this
machine" is never a blocker (rule 11): `https://files.viaaq.eu/sd-images/`
serves the EU 2011, US 2011 and 2014/2016 images (7.4–7.5 GB each; `curl -r
0-268435455` gets the 256 MiB firmware head in about a minute).

```bash
python3 tools/selftest.py                 # all tools that have --selftest
python3 tools/selftest.py --only imgpatch # one tool
python3 tools/claims_check.py             # ledger: duplicates, unregistered claims
python3 tools/realcheck.py IMG256         # pinned checks on real bytes (exit 2 = no image)
python3 tools/l3check.py --build-corpus   # L3 rung; exit 3 = nothing runnable, never a pass
```

Verification ladder for a data/code change, in order:

```bash
python3 tools/cmpind.py verify REFER001     # expect 194/194 OK
python3 tools/cardcheck.py --root <root>    # L1 structural
python3 tools/l2check.py --root <root>      # L2 round-trip + golden
cd tools/ze0-viewer && python3 harness.py verify <tile>   # byte-identical tiles
```

- `l2check.py --cmp-limit 20 --no-tiles` for a fast pass; `--update-golden`
  only after an intentional decoder change, never to make a failure pass.
- Recompression needs **stock zlib 1.3.1** (`python3.13`). zlib-ng (often
  Python 3.14) reproduces none of the factory streams; `tools/zlibinfo.py`
  reports the runtime and exits 3 when a byte-identical claim is unverifiable.
- Firmware image starts: A (apps, `Navi.exe`) `0x200200`, B (kernel/updaters)
  `0x3e00200`, C (kernel/test mode) `0x5200200`.

## Repo shape

- `tools/` — Python 3.10+, standard library only, entrypoints run directly.
  `tools/selftest.py` auto-discovers `--selftest`; new tools must have one.
- `tools/ze0-viewer/` — viewer plus a **checked-in** copy of the pinned
  `osm2clarion` tools in `tools_ze0/`; `setup.sh` only audits/regenerates it
  against a git-ignored `vendor/` clone (see `docs/format/ze0-tools.md`).
- `docs/format/` living format knowledge · `docs/experiments/` append-only
  records (`TEMPLATE.md` carries the required five-part Method) ·
  `docs/research/` claims, roadmap, protocols · `profiles/` build profiles.
- `archive/` — git-ignored vendor data. Working data lives outside the repo;
  on this machine the full EU 2011 image is
  `/home/marek/projekty/leafre-work/leaf2011.img` (SHA-256 `105e2032…76307`),
  extracted tree `leafre-work/root/`.

## Format facts agents get wrong

- Common header text is UTF-16 **big-endian**, only `0x000`–`0x17f`; `0x180`
  onward is binary.
- `REFER001/*.cmp` is **not** one zlib stream: `chunk_count` independent
  streams indexed by `.ind`.
- `.ind` = `u32 uncompressed, u32 compressed, u32 count, u32 chunk_size
  (0x10000), u32 offsets[count]`. Payloads keep the 512-byte header.
- `REFER002` has **16 files**, not 194; it is a separate EV/charging layer.
- `DRSTR001.DAT` has **no header**: root `/` at `0x0000`, 40-byte nodes, then
  32-byte entries. Entry `value` = logical size for `.cmp`, on-disk size for
  `MAPAL001` tiles, recursive total for directories. Entry case is preserved
  (US stores `ltntbl.dat`).
- `MAPAL001` has 45 `BxxRyyR.DAT` + `LEV3456R.DAT`; B/R are hex:
  `lat_min = int(B,16)*2/3`, `lon_max = 108-int(R,16)`, 5.333° × 8°. Stream
  keys `A = 32768 + lat*192`, `B = 52736 + lon*128`, plus a table tag.
- `COORD001` is a 33-entry region-bbox table at `0x1010`:
  `lat = (x-32768)/192`, `lon = (y-52742)/128`. The same formula covers
  `ADDRE`/`POINT` ids; `ADDRE`/`POINT` share ids (join is street + house no.).
- Tile **section 4 is an administrative/place-name index**, not geometry. Road
  names come from the odd partner record's names section.
- `REFER001/INDEX003.DAT` does **not exist** on EU/US 2011 cards; the firmware
  string exists but the path is conditional (M3.12).
- The `0..2047` coordinate bound is a runtime/bit-packed constraint, not a
  plain-u16 storage rule; raw payloads contain larger `u16` values.
- Prefer `tools/mesh_grid.py`, `tools/cmpind.py`, `tools/cmpind_writer.py`,
  `tools/coord.py` over re-deriving any of the above.

## Writing data back

- **Unchanged file:** preserve original streams (or copy the pair) —
  byte-identical on any machine.
- **Changed file:** recompress only 64 KiB chunks containing changed bytes,
  keep the rest verbatim, rebuild `.ind` offsets.
- **New/whole-file rewrite:** stock zlib 1.3.1, level 6, wbits 15, memLevel 8,
  default strategy.
- **One-variable test cards:** `tools/imgpatch.py` writes a file into its
  existing cluster chain (FAT layout, timestamps, root label untouched);
  `tools/mkcard.py` rebuilds the whole partition for generated trees.

## Firmware: use the CE ROM TOC, and do not redo these dead ends

Start every address with `tools/cerom.py` (never fitted deltas):

```bash
python3 tools/cerom.py --image-start 0x200200 IMG256 romhdr
# expect: nummods=149 numfiles=1 cpu=0x01a6 physfirst=0x8cae1000 physlast=0x8e233c88
```

`ROMHDR` sits at file `0x01951b78`; `tools/cerom.py` also does `sections`,
`va2file`, `file2va`, `extract`, `memmap`, `comphdr`, `imports`, `exports`,
`thunks`. `tools/sh4xref.py` answers "who loads this VA" and "what does this
function call" — use it instead of ad-hoc scanning.

Retired, with no re-run: the `0x6fab2c → 0x6faeb0 → 0x6fb05c` "map-code
check" (it is `BT_MGR.dll`, C-520); global VA / module-base / delta fitting;
"no XIP table" (C-380/381, retracted); "static is closed for the reader"
(EXP-29, wrong address model); `NaviStateCC` vtable hunting; `+0x02200000`
as a map-code delta. `docs/research/todo-history-*.md` keeps the details.

Map-code checks (M2.5, M2.15): 11 bytes of kernel target info
(`KernelIoControl 0x0101302C` `+0x60`) vs `HDD_INFO.TXT` line 1, and a
`MapDBVer` range check — **not** the `0x06000000` copy, and `HDD_CHK.ATT` is
read only by `MapUpdate.exe`, not by `Navi.exe` at boot.

## Method that this repo already paid for

- **Test the textbook structure before inventing a model.** CE ROMs, FAT, zlib
  and PE have public layouts; start from `ECEC`/`ROMHDR` with its documented
  field order. EXP-05…29 were ~20 rounds of fitted parameters that mostly
  retracted each other.
- **Addresses come from structure, not code literals.** `cerom.py` gives
  module/section/offset; literal scoring with prologue percentages never
  proves a base (and `V − S` matches are not injective here).
- **Prefer checks that can fail loudly** — a wrong hypothesis should give 0 %,
  not 40 %. "The name resolves", "physfirst equals the image base", "an
  independent anchor reproduces" are tests that can fail.
- **One module, one claim.** Attribute every VA through `cerom.py` and say so
  in the claim row.
- **Cheap before expensive.** The firmware is in the first ~100 MB, so use
  ranged reads, cross-year diffs and the offline validators before asking for
  hardware, a spare card or a full download.

## Evidence and retraction

- New experiment: copy `docs/experiments/TEMPLATE.md`, name
  `EXP-YYYY-MM-DD-<TASK>-slug.md`. Record sample SHA-256, runnable commands,
  controls (positive and negative), the counted corpus, and the falsifier —
  then observations, then interpretation. Never mix the two.
- A claim is never deleted: mark `RETRACTED` (keep the ID) and add a new claim
  with `Supersedes: C-xxx`.
- External links → `docs/research/sources.md`; unknowns →
  `docs/research/open-questions.md`; loose threads → `TODO.md`.
- Negative results are first-class; a negative without a positive control is
  not a result.
- Rule 13: a generated format is *confirmed* only when its firmware reader has
  a VA in `docs/format/`, and *accepted* only when an L3/M8 run reads our file.

## Data, license, safety

- Never commit vendor data: images, dumps, firmware, `.DAT`, `.cmp`, `.ind`,
  `.AGM`, `.TTS`, `.GID`. `.gitignore` also drops `*.img`/`*.7z`. Keep them in
  `archive/` or outside the repo; `git add -f` only for tiny synthetic
  fixtures.
- Code is GPL-3.0-or-later; OSM-derived data is ODbL-1.0. Link to
  incompatible projects instead of copying code.
- The original SD card is read-only: back up, verify the hash, test on a
  spare card.
- Commit only offsets, counts, hashes and short header bytes from vendor data.

## Commit style

Small, logical commits. Imperative subject ≤ ~72 chars, no trailing period;
prefixes `docs:`, `tools:`, `format:`, `fix:`, `chore:`. Explain *why* in the
body.
