# EXP-2026-11-19-H112: Fifteenth product review — a corrected call graph, file-name tables, next steps

- **Status:** done
- **Date:** 2026-11-19
- **Sample:** `IMG256` (first 256 MiB of the EU 2011 card image), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`;
  `US256` (first 256 MiB of the US 2011 card image), SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`.
- **Tools:** python 3.13 (stdlib), `tools/callgraph.py` (changed here,
  `--selftest` 8 cases), `tools/sh4xref.py`, `tools/sh4dis.py`,
  `tools/cerom.py`, `tools/nk_decomp.py`, `git log`.
- **Claims:** C-4620–C-4629
- **Supersedes:** claims C-4281, C-4282, C-4284, C-4285, C-4286 of
  EXP-2026-11-17-H101-pm-review
- **Superseded by:** none

## Question

Where is the project on 2026-11-19 (`main` at `c8e6d15`), what in the board
needs correcting, and what are the next steps without hardware?

## Method

```bash
git log --since=2026-11-17T17:51 --format=%s          # what merged since H101
ls docs/experiments | grep -E '2026-11-1[789]'          # one EXP per closed task
python3 tools/map_signals.py                            # the four rule-17 numbers
IMG=archive/head256.img ; US=archive/us256.img ; G=archive/work/navi_eu.json
python3 tools/callgraph.py --selftest
python3 tools/callgraph.py build $IMG -o $G
python3 tools/callgraph.py build $US  -o archive/work/navi_us.json
python3 tools/callgraph.py callers $G 0x0041b4f8 --depth 1
python3 tools/callgraph.py reach   $G 0x004266ec
python3 tools/callgraph.py reach   $G 0x00425f40
python3 tools/callgraph.py reach   $G 0x0040b850
python3 tools/callgraph.py callers $G 0x0040b358 --depth 1
python3 tools/sh4dis.py $IMG Navi.exe --image-start 0x200200 --va 0x41b2a4 --count 124
python3 tools/sh4xref.py --image-start 0x200200 $IMG Navi.exe --to 0x00179fa4
python3 tools/cerom.py --image-start 0x200200 $IMG exports OSMDLL.dll
```

The graph before the fix was kept (built from `026f498`) and the two edge sets
were compared. **Name census:** in `Navi.exe` sec0 below `0x0032ed9c`, every
NUL-terminated string that matches `[A-Z][A-Z0-9_]{2,10}\.(DAT|TXT|LST|ATT)`
or one of the directory names (`MAPAL001`, `REFER001`, `REFER002`, `RDSTM001`,
`BICON001`); for each, the aligned 32-bit words in sec0 equal to its VA, and
the graph function that contains each such word. The command is not in the
tree yet; M3.28 commits it with a selftest.

Controls. *Positive:* the H51 chain `0x0041c044 → … → 0x00542250` must
survive the fix (it does). *Negative:* a selftest function whose pool word
`0xbfba` decodes as `bsr` must have no edge; M3.26's hand-found false edge
`0x004180f0 → 0x00417924` and M3.27's `0x0041e5e4 → 0x0041f26c` must be gone
(both are). *Scope:* `Navi.exe`, EU2011 for everything, US2011 for the graph
totals only. *Not covered:* switch tables (`braf` offsets) are still decoded
as instructions; table edges (M3.24); other modules.

## Observations

**Board since H101 (2026-11-17 → 2026-11-19).** Done: M1.20, M3.26, M3.27,
M4.41, M5.30, M5.34, M5.41, M5.43, M5.44, M5.45, M5.46, M5.47, M5.48, M8.A2,
M8.A10, M9.28, M9.37, M9.42, M9.43, H91, H109 (21: 19 outside H, 2 H); H92 is
recorded as blocked on H111. `map_signals.py` in this sandbox: `readers:
located 6 partial 5 unlocated 7`, `l3_rows: l3-running 1`, `tile_bytes` and
`card_step` `NOT RUN` (no factory tree here; the PO block quotes them from the
host).

**Call graph, before and after skipping pool words.**

| | EU2011 before | EU2011 after | US2011 before | US2011 after |
| --- | --- | --- | --- | --- |
| Nodes (leaves) | 9,000 (1,404) | 8,920 (1,324) | 8,890 (1,370) | 8,828 (1,308) |
| Direct edges | 22,867 | 20,676 | 22,119 | 20,421 |
| Import edges | 7,721 | 7,721 | 7,609 | 7,608 |
| Unresolved `jsr @Rn` | 589 | 395 | 525 | 411 |
| No static caller | 956 | 1,167 | 970 | 1,182 |

Edges removed 2,201 (EU) and 1,705 (US); added 10 and 7. H101 printed the US
import edges as 6,858; the old tool gives 7,609. In `0x00417d00…0x0041cab0`:
117 nodes before and after, edges 354 → 235, 13 entries called from outside.
`0x0041b2a4`: the listing has `jsr @r9` calls only (to `0x00417a5c`); the word
at `0x0041b364` is `b0c4`, the low half of the literal `0x0017b0c4`.
Callers after the fix: `0x0041b3bc` ← `0x00419684`, `0x0041b780`, `0x0041ba90`;
`0x0041b470` ← `0x00418a10`, `0x00418b00`, `0x00419350`, `0x0041b8a4`,
`0x0041ba28`; `0x0041b4f8` ← `0x00418a10`, `0x00418b00`, `0x00419350`,
`0x0041b954`. `0x0032efa8`: 0 unresolved calls (25 before).

**Tile "readers".** `reach 0x004266ec` and `reach 0x00425f40` each print
`reaches 27 functions` (the root is counted: 26 others), 1 unresolved call (in `0x004b8c20`), 23 imports: `NKDbgPrintfW`,
`printf`, `GetLastError`, `OSM_SramSet`, `GetSystemTime`, `LocalAlloc`,
`LocalReAlloc`, `LocalSize`, `ReleaseMutex`, `WaitForSingleObject`,
`_snprintf`, `_vsnprintf`, `memcpy`, `DebugShellOutput`, `ErrorLogMsg`,
`OBJ_CarPos_initPrm`, `OBJ_CarPos_read`, `intContext`, `OSM_TaskSend`,
`taskIdSelf`, `STD_PntData_getL1MeshID`, `…MeshX`, `…MeshY`. Router only:
`0x00425c5c`, `0x00425cb0`, `0x00425cf4`; renderer only: `0x004258ec`,
`0x00425954`, `0x00425ab8`. `OSM_TaskSend` is imported by `0x0041ee14`.
`CreateFileMappingW`/`MapViewOfFile` users in the module: `0x003d2218`,
`0x0053b870`, `0x0053fc48`, `0x00545d68` — none in either subtree.

**File names.** 60 name strings, 56 with at least one loader. Outside the
tables: `LEV3456R.DAT` `0x00179fa4` ← `0x0040a014`; `DRSTR001.DAT` ←
`0x00419684`; `MMAIN001.DAT` ← `0x0041a438`; `ICODE001.DAT` ← `0x003f2cc0`;
`MSIZE001.DAT` ← `0x00403828`; `LCTBL001.DAT`, `INDEX003.DAT` ← `0x004125a8`;
`BICON001.DAT`, `BLND_MRK.DAT` ← `0x00413b90`; `REFER001` ← `0x003f1640`,
`0x003f2cc0`, `0x003f7b20`, `0x003fbed8`, `0x004011a0`, `0x004125a8`.
No loader: `CMP.LST`, `COORD001.DAT`, `ZIPFR001.DAT`, one `REFER002` copy.
Tables in rodata: `0x00179cf8…0x00179dd0`, 18 rows of three pointers
(directory, file, `CDROM.DAT`) — rows 0–2 `MAPAL001`/0, 3
`RDSTM001`/`RDSTM001.DAT`, 5 `HOUSE001`/0/0, 10–12 and 14–17 `REFER001` with
`POINT001`, `ADDRE001`, `ICODE001`, `POINT001`, `INTER001`, `ICADM001`,
`REFER001` `.DAT`, other rows zero; preceded by the words `0x000f0004`,
`0x0000f4ff`, `0x000f0005`, `0x0000f5ff`, `0x000f0006`, `0x0000f600` and
followed by `0x400`, `0x403`, `0x406`, `0x40f`. The one code literal into it
is `0x00179cf8` at pool `0x0040b48c` (`fn 0x0040b3e0`). Name-part table
`0x001792c4…0x00179338`: six rows of (prefix ×4, `.DAT`) for `POINT0`,
`ADDRE0`, `FRWAY0`, `INTER0`, `LCTBL0`, `ZCODE0`; all six row bases are
literals of `fn 0x003fbed8`. Table `0x0017a050`: `CHARA001`, `CRO00000`,
`ADD00000`, `FRWAY001`, `CRO00000`, seven `CHARA*.DAT`, `INDEX001`, seven
`INDEX00n.DAT`; literal `0x0017a098` in `fn 0x004125a8`.
Graph: `0x0040b850` → `0x0040b3e0` → `0x0040a108` → `0x0040a014`,
`0x004192c0`; `0x0040b358` has 13 callers; `reach 0x0040b850` prints 135
functions (134 others), 1 unresolved call, imports include `OSM_TaskSend`, `taskLock`,
`OBJ_DiscInfo_readDiscVol`, `strcat`, `strcpy`, `_modls`, and no `fopen`,
`fread` or `fseek`. `0x003fbed8`, `0x003f1640`, `0x004011a0` import `strcpy`,
`strcat`, `_modls`.

## Interpretation

- **FACT (C-4620):** the first `callgraph.py` reported about one false edge
  in ten; the cause is pool words decoded as `bsr`/`jsr`. Fixed and tested.
- **FACT (C-4621, C-4622, C-4623):** the H101 statements built on those edges
  are wrong and retracted: the fifth `fread` caller, "48 functions", "the
  tile is memory-mapped", "25 unresolved calls in `0x0032efa8`", "914 of 956".
- **FACT (C-4624):** ordinal imports have names in the exporter's table.
- **FACT (C-4625, C-4626):** the `MAPAL001` directory and `LEV3456R.DAT` are
  named in `0x0040b3e0` and `0x0040a014`, on one static path to the map-file
  layer entry `0x004192c0`.
- **OBSERVED (C-4627):** nine functions load the file names of the other
  families; three of them build names with `strcpy`/`strcat`/`_modls`.
- **HYPOTHESIS (C-4628):** `0x00425f40`/`0x004266ec` request tiles by message
  and do not parse them. Test: M3.25 (new route).
- **HYPOTHESIS (C-4629):** a client open is a message; the read is done by the
  map-file task's handlers. Test: M9.44.
- **UNKNOWN:** which function receives the tile bytes; what the id words
  around the directory table mean.

**How the swarm did.** Rule 17 changed the mix (19 of 21 outside H) and the
card side moved a full rung (P0). Both reader numbers stood still: the tasks
that would move them (M3.25, M9.44, M9.36) need a pair and had a wrong lead
from H101 (a parse target that is a request function). The lesson for this
role: a new tool's output went into task hints after one positive control and
no negative one on real bytes; two navigators paid for it.

## Conclusion

The card side is ahead of the firmware side. The next unit of progress is a
located reader per file family (M3.28, from the name tables) and an L3 run cut
at message boundaries (M9.44), not another card rung alone.

## Follow-ups

M3.28 (new); notes on M3.23, M3.24, M3.25, M4.40, M9.2, M9.44, H101; the
Priorities paragraph "PM fifteenth pass".
