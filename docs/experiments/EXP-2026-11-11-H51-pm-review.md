# EXP-2026-11-11-H51: Thirteenth product review — the kernel decompressor runs in PySh4, `.pdata` gives the function starts, the US card has its own `Navi.exe`

- **Status:** done
- **Date:** 2026-11-11
- **Sample:** `IMG256` = first 256 MiB of `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
  SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (`tools/fetch_image.py --image IMG256`). `US256` = first 256 MiB of
  `LEAF_2011-2012_US.img` (`curl -r 0-268435455`), SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`.
- **Tools:** python 3.13 (stdlib), `tools/nk_decomp.py` (new here,
  `--selftest` 8 cases), `tools/l3_harness/engine.py` (`PySh4`, three fixes
  here, `--selftest`), `tools/cerom.py`, `tools/sh4dis.py`, `tools/sh4xref.py`.
- **Claims:** C-3480–C-3489
- **Supersedes:** the blocker diagnosis of EXP-2026-11-08-M1.2f-decomp-blk-python,
  EXP-2026-11-08-M8.E1-rom-decomp-retry-qemu11 and
  EXP-2026-11-08-M3.2b-cmp-chunk-reader-inflate-2 (their observations stand).
- **Superseded by:** none

## Question

Where is the project stuck, and is each "stuck" real? Three things were
tested: (1) can the compressed sections be decoded without a codec port, QEMU
or Ghidra; (2) why do reader searches end at "no static caller"; (3) does the
L3 gate for the US cards run the code the US unit runs.

## State of the board (2026-11-11, `main` at `116c826`)

- About 170 task blocks before this pass; last commit 2026-11-10 16:08; one open PR (#171, M5.29
  factory rerun, blocked).
- **Done and solid:** card image tooling (`mkcard`, `imgpatch`, S1/S2/S3
  images, L1/L2 checks), `.cmp/.ind` codec with factory-equal zlib, `DRSTR`,
  `MMAIN`, `HDD_INFO`, tile round-trip and a provisional road splice, POI
  rename, SD lock analysis and the Pico tool, CE ROM parsing, an L3 harness
  with two firmware fragments running (POINT walker, `.cmp` chunk engine).
- **Not done:** no card has been in the unit (M6.2 S0 is open since
  2026-11-06); the "Unlocated readers" table of
  `reader-coverage.md` still lists 14 families; the Poland one-tile run has not completed on
  factory data (M5.29).
- **Pattern of the last four days:** a reader task finds the access path,
  tries two byte signatures, gets 0 hits, and blocks on something it cannot
  read (compressed code — refuted 11-08; compressed data — refuted 11-10;
  the codec — this record). About half of the tasks closed on 11-09 were
  process or tooling tasks (H38–H48, M1.18), and M9.32–M9.34 are bookkeeping
  about one target.

## Hypotheses and falsifiers

- H-a: `DECOMP_SECT 0x88037464` is a self-contained function; M8.E1 failed on
  the QEMU memory map, not on kernel state. Falsifier: the run needs a global
  that only a booted kernel has, or returns lengths different from `comphdr`.
- H-b: "no reference to `0x0041c7e8` anywhere" means the address is not an
  entry. Falsifier: the function table lists `0x0041c7e8` as a start.
- H-c: the US card carries the same `Navi.exe` as the EU card. Falsifier:
  different section sizes or entry.

## Method

```bash
IMG=archive/head256.img ; US=archive/us256.img
python3 tools/fetch_image.py --image IMG256 -o $IMG
curl -sS -r 0-268435455 -o $US https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img
python3 tools/sh4dis.py $IMG nk.exe --image-start 0x3e00200 --va 0x88037464 --count 150
python3 tools/nk_decomp.py --selftest
python3 tools/l3_harness/engine.py --selftest
python3 tools/nk_decomp.py section $IMG --module NaviMapCC.dll --index 1   # EXP-49 sec1
python3 tools/nk_decomp.py section $IMG --module NaviMapCC.dll --index 2   # EXP-49 sec2
python3 tools/nk_decomp.py section $IMG --module Navi.exe --index 1 -o sec1.bin
python3 tools/nk_decomp.py section $IMG --module Navi.exe --index 2 -o sec2.bin
python3 tools/nk_decomp.py check $IMG --json check.json
python3 tools/nk_decomp.py pdata $IMG --module Navi.exe 0x41c7e8 0x41c7dc 0x3f5194 \
  0x412bee 0x542256 0x4125a8 0x3f632c 0x419350 0x41a438 0x3bc960 0x41c990
python3 tools/sh4xref.py $IMG Navi.exe --image-start 0x200200 --to 0x0041c7dc
python3 tools/sh4xref.py $IMG Navi.exe --image-start 0x200200 --to 0x0041c990
python3 tools/sh4xref.py $IMG Navi.exe --image-start 0x200200 --to 0x00412ac0
python3 tools/cerom.py --image-start 0x200200 $US sections Navi.exe
python3 tools/nk_decomp.py pdata $US --module Navi.exe 0x35d894
cmp <(dd if=$IMG bs=512 skip=126977 count=20480 2>/dev/null) \
    <(dd if=$US  bs=512 skip=126977 count=20480 2>/dev/null)   # build B, 0x3e00200..0x4800200
```

Controls. *Positive:* the two EXP-49 sections must give the M1.2a lengths
(`0x484`, `0xcc0`); `inflate_mask[17]` at `0x00574de0` in the decoded sec1
must equal `2^n-1` (the public zlib table M9.11b declared by hand). *Negative:*
without the three stack arguments the routine returns `0xffffffff` on all four
sections (observed before they were added); the selftest's synthetic pdata has
an `INSIDE`, a `GAP` and a `BEFORE` case. *Scope:* build A, 245 compressed
sections, 30,212,810 B vsize; `Navi.exe` of EU2011 and US2011. *Not covered:*
build C, the `FILESentry` payloads (M1.21), any module's pdata except
`Navi.exe` (M1.20).

## Observations

**1. The decompressor.** `DECOMP_SECT` reads three words above the four
register arguments: `@(60,r14)`, `@(64,r14)` (a 16-bit value that must be 1 or
2) and `@(68,r14)` (compared with `0x1000`); with the prologue's 44 bytes they
are `sp+16`, `sp+20`, `sp+24` at entry. Called as
`(src, psize, dest, vsize, 0, 1, 0x1000)`:

| Section | psize | vsize | r0 | SHA-256 of `dest[:r0]` |
| --- | --- | --- | --- | --- |
| `NaviMapCC.dll` sec1 (EXP-49) | `0x2c6` | `0x5b8` | `0x484` | `a764e221b39770b6…` |
| `NaviMapCC.dll` sec2 (EXP-49) | `0x68c` | `0xcc0` | `0xcc0` | `755d5100de36b4d3…` |
| `Navi.exe` sec1 | `0x457c` | `0xff16ae` | `0x1801a` | `1c73ad74ffafe397…` |
| `Navi.exe` sec2 | `0x8884` | `0xed60` | `0xed60` | `3cf39c97640599f5…` |

`step = 2` gives the same bytes on these four. `check`: **245 OK, 0 failed,
1,674,478 bytes decoded**; `r0` equals `comphdr`'s `uncompressed_len` for all
245 (0 mismatches). The total equals C-3440's figure. SHA-256 over the list of
`(module, section, r0, sha256)` rows: `ae03e1eef2e2f42f…` (python `json.dumps`
of the list, for a later run to compare). Run time about 10 minutes for the
check; `Navi.exe` sec1 16 s.

**2. Engine defects met on the way** (each stopped the run or sent a store to
a wild address):

| Opcode | Was | Is |
| --- | --- | --- |
| `0x80nd` `mov.b R0,@(disp,Rn)`, `0x81nd` `mov.w R0,@(disp,Rn)` | base register taken from bits 11–8 (always `r0`) | bits 7–4 |
| `0x0nm7` `mul.l Rm,Rn` | matched only when `m = 0` | any `m` |
| `0x0nC3` `movca.l R0,@Rn` | not modelled | plain 32-bit store |

The first one is silent whenever `r0 + disp` lands in a mapped region.

**3. `Navi.exe` sec2.** 7,596 eight-byte records, strictly ascending first
words, all inside sec0 (`0x0032ed9c … 0x00558300`); second word decodes as
prologue length (bits 0–7) and function length (bits 8–29) in instructions.

| VA (as cited on the board) | Class | Function record |
| --- | --- | --- |
| `0x0041c7e8` (M3.2b/M9.11 "chunk engine") | INSIDE | `0x0041c7dc`, prologue 30 B, length `0xe8` |
| `0x00412bee` (M3.22 "populate writer") | INSIDE | `0x00412ac0`, length `0x1a0` |
| `0x00542256` (zlib entry) | INSIDE | `0x00542250`, length `0xdc` |
| `0x003f5194` (POINT walker) | GAP | no record; called directly from `fn 0x003f5cdc` |
| `0x004125a8`, `0x003f632c`, `0x00419350`, `0x0041a438`, `0x003bc960`, `0x0041c990` | START | — |

`sh4xref --to 0x0041c7dc`: pool `0x0041caac`, one load at `0x0041ca58`, `jsr`
at `0x0041ca5a` in `fn 0x0041c990`. `--to 0x0041c990`: one caller, `fn
0x0041c044` (`jsr 0x0041c096`). `--to 0x00412ac0`: `fn 0x00413a6c` (`jsr
0x00413af4`). `0x00419350` + `0x334` = `0x00419684`.

Decoded sec1 (`0x1801a` bytes): 6,052 aligned words point into
`0x0032ed9c…0x00558300`; none of them is `0x0041c7e8` or `0x0041c7dc`. ASCII
strings include `Lv1_O`, `Lv2`, `Lv4`, `Lv1_D/TOP`, `Lv5`, `Dummy category`
and two character-set strings. `inflate_mask[17]` at `0x00574de0` equals
`2^n-1`.

**4. US card.**

| | EU2011 (IMG256) | US2011 (US256) |
| --- | --- | --- |
| Build A modules | 149 | 151 |
| `Navi.exe` vsize / entry | `0x0154e000` / `0x0032edd0` | `0x013bb000` / `0x0035d894` |
| sec0 vsize | `0x54bd16` | `0x56faa6` |
| sec1 vsize / psize | `0xff16ae` / `0x457c` | `0xe3a58e` / `0x4437` |
| pdata records | 7,596 | 7,520 |
| Build B bytes `0x3e00200…0x4800200` | identical | identical |

## Interpretation

- **FACT (C-3480):** `DECOMP_SECT` takes `(src, psize, dest, vsize, skip,
  step, block)`; with `skip=0, step=1, block=0x1000` it needs no kernel state
  and runs in PySh4. H-a holds.
- **FACT (C-3481):** all 245 compressed sections of build A decode; lengths
  equal `comphdr`. A pure-Python codec port (M1.2f), a QEMU oracle
  (M8.E1/M8.E1c), a Ghidra oracle (M9.29) and public decoders (M1.2e) are not
  needed for these bytes.
- **FACT (C-3482):** PySh4 had the three defects in the table; fixed, with
  selftest cases that use distinct registers.
- **FACT (C-3483):** `Navi.exe` sec2 is the function table. H-b holds:
  `0x0041c7e8` is 12 bytes inside `fn 0x0041c7dc`.
- **FACT (C-3484):** `fn 0x0041c7dc` has a static caller chain
  `0x0041c044 → 0x0041c990 → 0x0041c7dc`. M3.2b's "indirect call through a
  `.data` pointer" (C-2064, C-2066) is refuted.
- **FACT (C-3485):** `0x00412bee` and `0x00542256` are mid-function addresses
  too; `0x003f5194` is a leaf with no record.
- **FACT (C-3486):** the M9.11b assumption about `inflate_mask[17]` in sec1 is
  true on the image bytes.
- **FACT (C-3487):** H-c is false. The US card's `Navi.exe` is another build;
  no EU VA can be assumed valid in it. Build B (kernel, updaters, the
  decompressor) is the same.
- **OBSERVED (C-3488):** sec1 `INIT` holds 6,052 code pointers (dispatch
  tables) next to map-level names.
- **HYPOTHESIS (C-3489):** some recorded L3 stops (`UNMAPPED 0xfffffec6` in
  the M9.35 `drstr` probe) are products of the `mov.w R0,@(disp,Rn)` defect.
  Test: M9.36.
- **UNKNOWN:** which build Marek's unit runs (M6.15); whether the map-reader
  code differs between the EU and US builds or only moved (M1.22); what
  `step` means (1 and 2 agree on four sections).

## What was missed, in one list

1. The codec was treated as something to port or to run in QEMU; the project
   already had an SH-4 engine that runs the firmware's zlib. Nobody called the
   kernel routine in it, and M8.E1 stopped at a memory-map problem that was
   QEMU's, with the three stack arguments still unknown.
2. `fn` labels came from a prologue heuristic. The exact table was one
   decompression away.
3. The engine was trusted because its selftest passed; the selftest used
   register choices that hide a wrong operand field.
4. All firmware work used the EU image because it was first; the hardware
   path is US.
5. Rule 15 was not applied when M9.35 merged (M3.22 stayed blocked).
6. M5.29's factory rerun was read as a policy question (`0x2146`); it is a
   choice of test parcel (M5.34).
7. M5.27 (finish a scan) and M4.2 (road classes, non-Claude) have had no
   owner for three and five days while bookkeeping tasks were taken.

## Conclusion

The three software blockers that held the reader work (codec, "no caller",
suspect L3 stops) are removed or have a one-command check. The next blocker
is ordering: readers should now be found by call graph (M3.23) and read-watch
(M9.38) on exact function boundaries (M1.20), and the US path needs the US
build (M1.22) before its software gate means anything. Hardware remains the
largest unknown: S0 (M6.2) and the unit's build (M6.15).

## Follow-ups

H52, M1.19, M1.20, M1.21, M1.22, M3.23, M3.24, M5.34, M6.15, M9.36, M9.37,
M9.38 (all in `TODO.md` with hints); M3.2b and M3.22 re-opened.
