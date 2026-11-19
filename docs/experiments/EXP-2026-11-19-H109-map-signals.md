# EXP-2026-11-19-H109: map_signals — the four rule-17 numbers as one command

- **Status:** done
- **Date:** 2026-11-19
- **Sample:** `none (tool-only task)` — the four signals read repo files
  (`docs/research/reader-coverage.md`) and host scratch trees
  (`~/projekty/leafre-work/m5.4/card-factory/MAPAL001/*.DAT`,
  `~/projekty/leafre-work/m5.34/report.json`); no vendor bytes are committed and
  the tool quotes the values the existing owners produce.
- **Tools:** `python3 3.13` (stdlib only), `tools/map_signals.py`,
  `tools/progress_report.py` (`parse_reader_coverage`),
  `tools/ze0-viewer/tools_ze0/clarion_tile.py` (`read_tile`), `awk`,
  `tools/mesh_grid.py` (P1 census, unchanged).
- **Claims:** C-4400–C-4409
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the four rule-17 map numbers be printed by one committed, portable command
that reuses the code that already owns each definition, reports `NOT RUN`
instead of crashing when an input is absent, and carries the same keys the PO's
Priorities block uses?

## Hypothesis

Yes: each number already has a committed owner (`progress_report` owns the
reader rows; the Priorities awk owns the L3 count; `clarion_tile.read_tile`
owns the tile spans; the M5.34 report owns the card-step booleans). A thin
`tools/map_signals.py` that imports/runs those owners and prints their numbers
reproduces the 2026-11-19 Priorities snapshot unchanged, and its text/JSON output
is stable enough for QA to quote.

**Falsifier:** any signal diverges from the Priorities snippet on the same host
(a different readers count, a different L3 count, a different tile percentage,
or a card step that disagrees with `cardcheck_ok and l2check_ok`); or the tool
crashes instead of printing `NOT RUN` when the factory tree or report is absent.

## Inputs

| Item | Value |
| --- | --- |
| Matrix | `docs/research/reader-coverage.md` (30 rows, parsed by `progress_report`) |
| Factory tiles | `~/projekty/leafre-work/m5.4/card-factory/MAPAL001/{B28R070R,B30R048R,B48R058R}.DAT` |
| Card report | `~/projekty/leafre-work/m5.34/report.json` |
| Tool / version | `python3 3.13` (stdlib only) |
| Repo tool | `tools/map_signals.py` |

## Method

1. **Sample and hash.** Tool-only: no image byte range is read; the matrix is a
   committed markdown file and the factory/report trees are host scratch. The
   two commands below are the whole method.
2. **Commands.** The full run and the absent-input run, verbatim:

   ```bash
   python3 tools/map_signals.py
   python3 tools/map_signals.py --json -
   python3 tools/map_signals.py --factory-root /nonexistent/factory
   python3 tools/map_signals.py --selftest
   python3 tools/selftest.py --only map_signals
   ```

   Each signal's machinery is the existing owner, not a fork:
   `readers` calls `progress_report.parse_reader_coverage`; `l3_rows` runs the
   Priorities `grep -E '^\| [0-9]+ \|' … | awk -F'|' '{gsub(/ /,"",$9); if
   ($9 ~ /PASS|REJECT/) c++} END{print "l3-running", c+0}'` pipeline as a
   subprocess; `tile_bytes` calls `clarion_tile.read_tile` and applies the same
   union-of-(directory + slot) spans over `d[0x1000:]`; `card_step` prints
   `cardcheck_ok`, `l2check_ok` and `counts.cardcheck_rc` side by side and sets
   `step` with the Priorities expression `"P0" if cardcheck_ok and l2check_ok
   else "none"`.
3. **Controls.**
   *Positive:* the full run on this host must print the Priorities snapshot:
   readers `located 6 partial 5 unlocated 7`, `l3-running 1`, tiles
   `B28R070R 99.98%`, `B30R048R 95.86%`, `B48R058R 76.28%`, `card_step P0`.
   *Negative:* `--factory-root /nonexistent/factory` must print
   `tile_bytes: NOT RUN (no factory tiles)` and exit 0; a stub report with
   `cardcheck_ok=True` and `counts.cardcheck_rc=1` must print `DISAGREE`, not a
   silent `P0`.
4. **Scope.** The committed reader matrix (30 rows / 12 columns), three named
   factory tiles and the one M5.34 report. Excluded: the P1 census (still
   `tools/mesh_grid.py`, unchanged, because it selects a profile, not a fixed
   number) and any metric that would need a new definition (a PO task; the tool
   deliberately redefines none).
5. **Falsifier.** Stated in Hypothesis: any divergence from the Priorities
   numbers, or a crash instead of `NOT RUN`.

## Observations

```
$ python3 tools/map_signals.py
readers: located 6 partial 5 unlocated 7
l3_rows: l3-running 1
tile_bytes: B28R070R 99.98%, B30R048R 95.86%, B48R058R 76.28%
card_step: P0 (cardcheck_ok=True l2check_ok=True counts.cardcheck_rc=0)
```

`--json -` carries `readers.{located,partial,unlocated}`, `l3_rows["l3-running"]`,
`tile_bytes.tiles.{B28R070R,B30R048R,B48R058R}` and
`card_step.{cardcheck_ok,l2check_ok,cardcheck_rc,step}`.

```
$ python3 tools/map_signals.py --factory-root /nonexistent/factory
readers: located 6 partial 5 unlocated 7
l3_rows: l3-running 1
tile_bytes: NOT RUN (no factory tiles)
card_step: P0 (cardcheck_ok=True l2check_ok=True counts.cardcheck_rc=0)
rc=0
```

```
$ python3 tools/map_signals.py --selftest
  ok   fixture matrix parses (readers LOCAL)
  ok   fixture matrix: located=1 partial=1
  ok   fixture matrix: only the REJECT row counts (1)
  ok   absent matrix is readers NOT RUN
  ok   absent matrix is l3_rows NOT RUN
  ok   synthetic tile explained percent in [0,100] (99.96%)
  ok   absent factory root is tile_bytes NOT RUN (no factory tiles)
  ok   stub report true/true rc=0 -> P0, no disagreement
  ok   booleans true but rc=1 prints DISAGREE and is not hidden
  ok   counts.cardcheck_rc is printed beside the booleans
  ok   any false boolean -> step none
  ok   absent report is card_step NOT RUN
  ok   main() with every input absent exits 0
  ok   text line 'tile_bytes: NOT RUN (no factory tiles)' is verbatim
  ok   all four signals report NOT RUN with no inputs
selftest: OK (0 failure(s))
```

```
$ python3 tools/selftest.py --only map_signals
tool:map_signals  PASS  0.20s
passed=1 failed=0 skipped=0 total=1 time=0.20s
selftest: OK
```

## Interpretation

- **FACT:** On this host `python3 tools/map_signals.py` prints the same four
  numbers as the 2026-11-19 Priorities snippets (readers 6/5/7, l3-running 1,
  the three tile percentages, P0), and exits 0 with `tile_bytes: NOT RUN (no
  factory tiles)` when the factory root is absent.
- **OBSERVED:** The M5.34 report's `cardcheck_ok`/`l2check_ok` and
  `counts.cardcheck_rc` agree today (all `True`/`0`); the tool still prints all
  three so a future disagreement is visible — a stub report with `rc=1` makes it
  print `DISAGREE`.
- **HYPOTHESIS:** none — the task was portability and honesty, and both hold.
- **UNKNOWN:** none for the four numbers; the P1 census stays on
  `tools/mesh_grid.py`.

## Conclusion

`tools/map_signals.py` prints the four rule-17 map numbers from one command,
delegating every definition to its existing owner (no metric redefined), and
reports `NOT RUN` (exit 0) for any absent input instead of crashing. The
Priorities block now cites it as the one command; QA can quote the four keys
from its text or `--json` output. No `docs/format/` page changed and no vendor
bytes were read into the repo.

## Reproduction

```bash
python3 tools/map_signals.py     # expected: located 6 partial 5 unlocated 7 / l3-running 1 / the three tile % / P0
python3 tools/map_signals.py --factory-root /nonexistent/factory   # expected: tile_bytes: NOT RUN (no factory tiles), rc 0
python3 tools/selftest.py --only map_signals                       # expected: PASS
```

## Follow-ups

- [ ] none — a metric that needs a new definition is a PO task, not this tool.
