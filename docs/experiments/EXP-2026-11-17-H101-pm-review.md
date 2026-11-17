# EXP-2026-11-17-H101: Fourteenth product review — six days of board, a call graph of `Navi.exe`, directions without hardware

- **Status:** done
- **Date:** 2026-11-17
- **Sample:** `IMG256` (first 256 MiB of the EU 2011 card image), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`;
  `US256` (first 256 MiB of the US 2011 card image), SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`.
- **Tools:** python 3.13 (stdlib), `tools/callgraph.py` (new here,
  `--selftest` 6 cases), `tools/nk_decomp.py`, `tools/cerom.py`, `git log`.
- **Claims:** C-4280–C-4289
- **Supersedes:** claim C-3488 of EXP-2026-11-11-H51-pm-review (wrong count)
- **Superseded by:** none

## Question

How did the work go between 2026-11-11 (H51) and 2026-11-17 (`main` at
`fa27c11`, 218 commits), and what should research and development do while no
hardware is available?

## Method

```bash
git log --since=2026-11-11T08:00 --format=%s | grep -oE '^\[[A-Z0-9.a-z]+\]|task/[a-z0-9.]+-' \
  | sed 's#task/##; s#-$##; s/\[//; s/\]//' | tr a-z A-Z | sort -u      # tasks merged
IMG=archive/head256.img ; US=archive/us256.img ; G=archive/work/navi_eu.json
python3 tools/callgraph.py --selftest
python3 tools/callgraph.py build $IMG -o $G
python3 tools/callgraph.py build $US  -o archive/work/navi_us.json
python3 tools/callgraph.py path    $G 0x41c044 0x542250
python3 tools/callgraph.py users   $G fread,fseek,fopen,ReadFile,CreateFileW,MapViewOfFile
python3 tools/callgraph.py callers $G 0x41b4f8 --depth 2
python3 tools/callgraph.py callers $G 0x417924 --depth 1
python3 tools/callgraph.py reach   $G 0x4266ec
python3 tools/callgraph.py reach   $G 0x425f40
python3 tools/callgraph.py reach   $G 0x4125a8
python3 tools/callgraph.py callers $G 0x4259bc --depth 3
python3 tools/nk_decomp.py section $IMG --module Navi.exe --index 1 -o archive/work/navi_sec1.bin
```

The pointer census of sec1 (C-4283): for every 4-byte-aligned word `w` of the
first `0x1801a` bytes of `navi_sec1.bin`, count `0x00011000 ≤ w < 0x0055cd16`
(all of sec0), `0x0032ed9c ≤ w < 0x00558300` (function range, from pdata) and
`0x00011000 ≤ w < 0x0032ed9c` (strings and constants).

Controls. *Positive:* the graph must contain the chain H51 found by hand
(`0x0041c044 → 0x0041c990 → 0x0041c7dc`) and reach zlib. *Negative:* the
selftest has a register call with no literal (must stay unresolved, not
become an edge) and an import thunk (must not become a node). *Scope:*
`Navi.exe` only, EU2011 and US2011; direct calls, pool-literal calls and
import calls. *Not covered:* which function each of the 589 indirect calls
reaches; the map DLLs.

## Observations

**Board, 2026-11-11 → 2026-11-17.** Tasks merged (33): H52, H54, H55, H64,
H68–H76, H78–H81, H85, H87, H88, H90, H95 (22 H); M1.22, M1.22b, M1.23,
M1.25–M1.31 (10 M1); M9.39 (1). None in M2–M8. One further record, M3.13
pass 3, is negative. Open blocks 144, of them H 31. Of the twelve tasks H51
added, H52 and M1.22 are done; M1.20 is half done; M1.19, M1.21, M3.23,
M3.24, M5.34, M9.36, M9.37, M9.38 have had no owner. M3.2b and M3.22
(re-opened by H51) have had no owner.

**Call graph.**

| | EU2011 | US2011 |
| --- | --- | --- |
| Nodes (pdata functions + called leaves) | 9,000 (1,404 leaves) | 8,890 (1,370) |
| Direct edges | 22,867 | 22,119 |
| Import edges | 7,721 | 6,858 |
| Unresolved `jsr @Rn` | 589 | 525 |
| Functions with no static caller | 956 | 970 |

`path 0x41c044 0x542250`: `0x0041c044 → 0x0041c990 → 0x0041c7dc → 0x00542148
→ 0x0054232c → 0x00542250`.

File wrappers (EU2011): `fopen` in `0x0041b3bc` (5 callers), `fseek`+`ftell`
in `0x0041b470` (6), `fread`+`ferror`+`clearerr` in `0x0041b4f8` (5:
`0x00418a10`, `0x00418b00`, `0x00419350`, `0x0041b2a4`, `0x0041b954`). The
address range `0x00417d00…0x0041cab0` holds 117 nodes; 13 of them are called
from outside the range, nine only from `0x00417924`, whose one caller is
`0x0032efa8` (25 unresolved calls). `0x004192c0` is called from `0x0040b358`
and from `0x00409ba0`, `0x00409c28`, `0x00409cc8`, `0x0040a108`.

Tile readers: `0x004266ec` reaches 48 functions, 1 unresolved call, imports
include `CreateFileMappingW` and `MapViewOfFile`; `0x00425f40` reaches 48
functions, 1 unresolved; `0x004259bc ← 0x0042613c ← 0x00427144 ← 0x00427a34`.
`0x004125a8` reaches 223 functions with 47 unresolved calls.

**Pointers in sec1 `INIT`.** 6,052 words point into sec0; 281 of them into
the function range (163 distinct targets, 59 of them graph nodes); 5,771 into
the range below `0x0032ed9c`. Of the 956 functions with no static caller, 914
occur as a 32-bit word somewhere in sec0, 42 occur in sec1 `INIT`, 1 in
neither.

## Interpretation

- **FACT (C-4280):** in six days the board closed no task in M3, M4 or M5;
  two thirds of the closed tasks are housekeeping.
- **FACT (C-4281):** the static call graph of `Navi.exe` is small and almost
  fully direct (589 indirect calls in 9,000 functions, EU2011).
- **FACT (C-4282):** map-file stdio goes through three wrapper functions in
  one block of 117 functions; the `.cmp` engine, the `DRSTR` parser and the
  `MMAIN` reader are callers inside that block.
- **FACT (C-4283):** C-3488 was wrong. H51 counted pointers into all of sec0
  and called it "the function range". The right figures are 281 code
  pointers (163 targets) and 5,771 data pointers.
- **FACT (C-4284):** the router reader `0x004266ec` and the renderer reader
  `0x00425f40` each reach 48 functions and work on a memory-mapped file.
- **OBSERVED (C-4285):** function-pointer tables are mostly in sec0: 914 of
  the 956 caller-less functions appear there as a word (a table entry or a
  callback literal — the census does not tell which).
- **HYPOTHESIS (C-4286):** `0x0032efa8` is the task table and `0x00417924`
  the message dispatcher of the map-file task. Test: M3.26.
- **HYPOTHESIS (C-4287):** stubbing the three wrappers is enough to run the
  `DRSTR` and `MMAIN` readers on a card tree. Test: M9.44.
- **UNKNOWN:** whether section 2 is parsed inside the 48-function subtree or
  handed on by message (M4.40's `Stop`).

**Why the map tasks did not move.** The cycle is SM → PO → QA → SE → TL. QA
and SE each add tasks when they find a defect in a record; the TL takes "up
to ten tasks that qualify" and a repair task always qualifies (small, no
image needed, clear check), while a research task needs a pair, an image and
often a tool that does not exist yet. The PO's own pass of 2026-11-17 says
"the map signal is thin"; it could not change the outcome because nothing
limits the share of repair work. Rule 17 does.

## Directions without hardware

1. **Firmware as the format specification** — M3.26, M4.40, M3.25/M9.13,
   M3.23 + M9.38, and Ghidra on the host (M9.2).
2. **Emulation as the unit** — M9.36/M9.37, M1.19, M9.44 (the firmware's
   file layer reads a card tree, with negative controls), M9.45, then the
   mount state machine.
3. **Data against data** — M4.41 (three map editions), M4.2/M5.36 (OSM
   ground truth).
4. **A card in small steps** — M5.34 → M5.29 → M5.30 (step P0), M5.38 (the
   ladder P0–P4).

## Conclusion

The tooling and the evidence discipline are in good shape; the map is where
it was on 2026-11-11. The cheapest progress now is to read formats off the
reader code with the call graph, and to let the firmware's own file layer
read whole card trees in emulation. Both need no hardware.

## Follow-ups

M3.26, M4.40, M4.41, M5.38, M9.44, M9.45 (new); notes on M3.23, M3.24,
M3.25, M9.2, M9.24, M5.34; rule 17.
