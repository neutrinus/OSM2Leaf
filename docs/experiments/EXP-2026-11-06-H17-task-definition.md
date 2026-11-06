# EXP-2026-11-06-H17: The ticket was under-specified, not the search

- **Status:** done (review; no format fact created)
- **Date:** 2026-11-06
- **Sample:** `IMG256`, first 256 MiB of the EU 2011 card, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (`/tmp/opencode/head256.img`, 268,435,456 B). The compression budget below is
  measured on this file with `cerom.py memmap --json`; nothing is quoted from
  another EXP.
- **Claims:** none — a review creates no format claim.
- **Supersedes:** the sixth-pass framing in `EXP-2026-11-06-H15` (which blamed
  the search method). The facts of H15 stand; its diagnosis was too kind to the
  board.
- **Superseded by:** none

## Question

Three tasks in a row ended the same way: M3.11 (`POINT` reader), M3.2b (`.cmp`
chunk reader) and M3.13 (`ADDRE` reader) each searched "every uncompressed
build-A o32 section", found the access path, and reported that the record
walker was not there. Is that three facts about the firmware, a repeated
mistake by three agents — or a task definition that asked for something the
readable bytes cannot give?

## Hypothesis

None / exploratory. Marek's correction after the sixth pass: it is the ticket.
The falsifiable part is cheap — if the readable fraction of the module is small
enough that a correct search must fail, then the ticket, not the search, is the
defect.

## Inputs

| Item | Value |
| --- | --- |
| Image | `/tmp/opencode/head256.img`, SHA-256 `92aa525d…007f9` |
| Build A | `--image-start 0x200200`, 149 modules, 527 o32 sections |
| Tool | `python3 tools/cerom.py --image-start 0x200200 IMG256 memmap --json` |
| Audited records | EXP-2026-11-06-M3.11, -M3.2b, -M3.13 |
| Vendor bytes committed | none (counts and sizes only) |

## Method

```bash
python3 tools/cerom.py --image-start 0x200200 /tmp/opencode/head256.img \
    memmap --json > /tmp/opencode/a.json
python3 - <<'PY'   # per module: sum vsize of compressed vs uncompressed sections
import json
m = json.load(open('/tmp/opencode/a.json'))
for mod in m['segments'][0]['modules']:
    u = sum(s['vsize'] for s in mod['sections'] if not s['compressed'])
    c = sum(s['vsize'] for s in mod['sections'] if s['compressed'])
    print(mod['module'], u, c)
PY
```

Then, for each of the three EXPs: does its `Scope` match the bytes it reported,
and did the ticket state that the readable set is 44 % of the image?

## Observations

### 1. The compression budget of build A (measured, 2026-11-06)

| Measure | Value |
| --- | --- |
| Section virtual size, all 149 modules | 53,725,980 B |
| Of which `IMAGE_SCN_COMPRESSED` | 30,212,810 B = **56.2 %** |
| o32 sections, total / compressed | 527 / 245 |
| Modules with at least one compressed section | **133 / 149** |
| `Navi.exe` readable / compressed | 5,553,430 B / **16,778,254 B = 75.1 %** |
| `Navi.exe` compressed sections | `sec1` 16.7 MB, `sec2` 0.1 MB |
| `OBJDLL.dll` | 30.2 % compressed |
| `XGLDLL.dll` | 77.9 % compressed |
| `STDDLL.dll` / `NaviMapCC.dll` / `NaviStateCC.dll` | 2.6 % / 5.4 % / 5.0 % compressed |

Two traps make this worse than the percentage suggests:

1. **The compressed sections are flagged `rw-`, not `r-x`.** A module's code can
   sit in a section the o32 table calls read-write, so a search that filters
   "executable sections" excludes the very place the walker lives — twice over.
2. **The module every reader task targets is the worst case.** `Navi.exe` is
   three quarters compressed; M3.11, M3.13 and M3.2b all aimed at it.

### 2. The three tickets, side by side

| Task | Ticket said | Search covered | Outcome |
| --- | --- | --- | --- |
| M3.11 | "find the `POINT` record walk function" (`Done when`: `firmware.md` names it) | all uncompressed build-A sections | correct negative; walker probably in `sec1` |
| M3.2b | "walk up from `inflate`; name the caller that loops over `chunk_offset[]`" | all uncompressed build-A sections | found zlib + chunk engine, could not find the caller |
| M3.13 | "confirm the `ADDRE` grammar against the code that reads it" | all uncompressed build-A sections (282 / 23.6 MB) | correct negative; same escape |

None of the three tickets carried: the decodable share of the module, a
`Depends` on the decoder, a bound on what "find" means, or a stop condition.
Each agent discovered the 56 % wall *inside* the session and wrote it up well;
the board then treated the result as a surprise. M3.13 began **after** M3.11 had
already published that `Navi.exe` sec1 is compressed — so the third session was
avoidable with the information the board already had.

### 3. What was decided

- **The blocked task keeps its result.** M3.13 stays `blocked`, not `done`: its
  `Done when` (a reader VA or a "field never read" statement) was not met. Its
  access-path work is real and is cited by later tasks.
- **It returns to the pool, but on a condition.** New `Unblock:` field; a
  blocked task names the task that re-opens it. **Rule 15**: the PR that lands
  that task sets the waiting ones back to `open` in the same commit. So M3.13
  (and M3.2b, M3.11, M9.10, and the precheck-gated M3.14–M3.16/M3.18) return the
  day M1.2f merges — with the negative EXP as their `Scope`.
- **The template grows three fields**: `Precheck` (the command that decides
  whether the task is possible), `Scope` (the bytes it covers) and `Stop` (when
  to report `blocked` instead of a fourth angle). Rule 14 is now a
  definition-of-ready rule, not advice to the EXP writer.
- **One command instead of a session**: **M1.12**
  (`tools/reader_precheck.py`) prints a module's compressed share, its
  compressed sections and whether an anchor has an xref in decodable bytes,
  with the counts above as its pinned self-test.

## Interpretation

- **FACT:** build A is 56.2 % compressed by section bytes; `Navi.exe` is 75.1 %
  compressed; 133 of 149 modules have a compressed section. A search of the
  uncompressed sections describes at most 43.8 % of the image and 24.9 % of
  `Navi.exe`.
- **FACT:** all three tasks reported exactly that scope, and none of their
  tickets mentioned it or depended on the decoder.
- **OBSERVED:** the failure is at the ticket level. The agents' EXPs are
  correct, bounded and use positive controls; the board asked them to search a
  quarter of a module and called the result unexpected.
- **HYPOTHESIS:** with `Precheck` in the template, M3.14–M3.16/M3.18 will mostly
  resolve to "blocked until M1.2f" in their first hour instead of after a
  session each — which makes M1.2f even more clearly the critical path.
- **UNKNOWN:** whether the walkers are in `sec1` at all. The hypothesis is
  plausible (16.7 MB of code we cannot read) but unproven until M1.2f or a
  dynamic break.

## Conclusion

Agreed with Marek: these were under-specified tasks, not bad searches. The
board now forces a precheck (compressed share + anchor xref) and a stop
condition into every search task, names the unblocking task, and re-opens the
waiting queue automatically when it merges. M3.13 comes back to the pool with
M1.2f, not before, and not with the same ticket This is a process change only:
no format doc changed, because the three audits produced no format fact beyond
what their own records already claim.

## Follow-ups

- [ ] **M1.12** — the precheck tool; every new M3 ticket quotes it.
- [ ] **M1.2f** — merging it must re-open M3.2b, M3.11, M3.13, M9.10 and the
      precheck-gated M3.14–M3.16/M3.18 (rule 15).
- [ ] When the first re-opened task runs, record in its EXP whether the precheck
      prediction ("compressed, therefore blocked") was right — that is the test
      of this whole change.
- [ ] Re-check the template against the next ten merges; if a task again spends
      a session on an impossible search, the `Precheck` field is wrong, not the
      agent.