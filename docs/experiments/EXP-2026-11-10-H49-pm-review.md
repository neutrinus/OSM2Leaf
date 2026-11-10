# EXP-2026-11-10-H49: Twelfth product review — "compressed sec1" is import slots and BSS

- **Status:** done
- **Date:** 2026-11-10
- **Sample:** `archive/head256.img` (IMG256, first 256 MiB of
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (`tools/fetch_image.py --image IMG256` verified it). Build A at image start
  `0x200200`; ordinals resolved with build B at `0x3e00200`.
- **Tools:** python 3 (stdlib), `tools/cerom.py` (`sections`, `imports
  --resolve-with`, `exports`, `comphdr`), `tools/sh4xref.py --to`,
  `tools/va_class.py` (new here, `--selftest` 8 cases).
- **Claims:** C-3440–C-3445
- **Supersedes:** the diagnosis (not the observations) of
  EXP-2026-11-08-M3.15-lctbl-reader, -M9.17-reopen, -M9.14-reopen,
  -M3.11c-point-name-accessor and -M4.16b-rdstm-field-walk.
- **Superseded by:** none

## Question

Nine board tasks wait on M1.2f (the CE-LZXD codec port, itself blocked).
Their blockers cite addresses "in compressed `Navi.exe` sec1". What does the
CE loader actually put at those addresses — and would a working M1.2f unblock
any of them?

## Hypothesis

A CE `o32` section has a stored part (`psize`, here compressed) and a
`vsize` that the loader zero-fills past the stored bytes. Imports are bound by
the loader writing resolved addresses into the FirstThunk slots. If the cited
addresses are import slots or lie past the stored bytes, M1.2f is not their
gate. Falsifier: any cited address that `va_class.py` places in `INIT` (below
`uncompressed_len` and not an import slot).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| VAs | every `0x0055d…`, `0x00d53500`, `0x00e23cc0`, `0x00e99698`, `0x00ec3954`, `0x009cfd80`, `0x009e3e28` cited as a blocker in `TODO.md` and the 2026-11-08/09 EXPs |
| Repo tool | `tools/va_class.py`, `tools/cerom.py` |

## Method

1. **Sample and hash** as above.
2. **Commands:**

```bash
IMG=archive/head256.img
python3 tools/cerom.py --image-start 0x200200 $IMG sections Navi.exe
python3 tools/cerom.py --image-start 0x200200 $IMG comphdr Navi.exe
python3 tools/cerom.py --image-start 0x200200 $IMG comphdr --all --json > comphdr_all.json
python3 -c "import json; d=json.load(open('comphdr_all.json')); s=[x for x in d['sections'] if x['segment']==0]; print(len(s), sum(x['vsize'] for x in s), sum(x['uncompressed_len'] for x in s))"
python3 tools/cerom.py --image-start 0x200200 $IMG imports Navi.exe --resolve-with 0x3e00200
python3 tools/va_class.py --selftest
python3 tools/va_class.py $IMG --module Navi.exe --resolve-with 0x3e00200 \
  0x0041a438 0x0055d040 0x0055d8fc 0x0055d8f0 0x0055d924 0x0055d954 0x0055d8b4 \
  0x0055d100 0x00d53500 0x00e23cc0 0x00e99698 0x00ec3954 0x009cfd80 0x009e3e28 \
  0x0055e000 0x00570000 0x0154f100 0x0017a1f8
python3 tools/sh4xref.py $IMG Navi.exe --image-start 0x200200 --to 0x00d53500
grep -rhoE "0x0055[0-9a-f]{4}" TODO.md docs/experiments/*2026-11-0[89]* | sort | uniq -c
```

3. **Controls.** *Positive:* `0x0041a438` (M3.8 reader) and `0x0017a1f8`
   (`LCTBL001.DAT` string, C-2203) must come out `CODE`. `0x0055e000`,
   `0x00570000` (sec1 below 0x1801a) and `0x0154f100` (sec2) must come out
   `INIT` — the tool can say "needs M1.2f". *Negative:* the selftest's
   synthetic layout checks all six classes incl. `OUTSIDE` and an unparsed
   header (`UNKNOWN`).
4. **Scope.** Build A, 245 compressed sections (all `HOLDS` in `comphdr`),
   `Navi.exe` 3 sections / 846 import slots, 18 VAs. Every `0x0055dxxx`
   address cited in `TODO.md` and the 2026-11-08/09 EXPs (13 distinct).
5. **Falsifier** as stated: any cited blocker VA in `INIT`.

## Observations

`Navi.exe` sections (`va_class.py` header lines):

```
sec0 start=0x00011000 vsize=0x54bd16 init=0x54bd16 exec plain
sec1 start=0x0055d000 vsize=0xff16ae init=0x1801a COMPRESSED
sec2 start=0x0154f000 vsize=0xed60 init=0xed60 COMPRESSED
iat slots: 846
```

Build A total: 245 compressed sections, vsize 30,212,810 B, initialised
(`uncompressed_len`) **1,674,478 B = 5.54 %**.

| VA | Class | Detail | Cited by |
| --- | --- | --- | --- |
| `0x0055d040` | IAT | `COREDLL!memset` | M9.17 ("first data access, UNMAPPED") |
| `0x0055d8fc` | IAT | `OSMDLL!OSM_Malloc` | M9.14 ("UNMAPPED") |
| `0x0055d8f0` | IAT | `OSMDLL!taskIdSelf` | M3.11c ("HDLMAP indirect") |
| `0x0055d924` | IAT | `OSMDLL!OSM_isSender` | M3.15 ("sec1 helper") |
| `0x0055d954` | IAT | `OSMDLL!OSM_Printf` | M3.15 ("sec1 helper", 663 loads) |
| `0x0055d8b4` | IAT | `OSMDLL!OSM_SramSet` | M4.26 |
| `0x0055d100` | IAT | `COREDLL!wcsstr` | M9.14 negative control |
| `0x00d53500` | BSS | sec1 +0x7f6500 | M4.16b, M3.11c, M3.13 ("schema/HDLMAP table") |
| `0x00e23cc0` | BSS | sec1 +0x8c6cc0 | M9.17 (reader `dest` fallback) |
| `0x00e99698`, `0x00ec3954`, `0x009cfd80`, `0x009e3e28` | BSS | sec1 | M4.26 (RGD slot tables, flags) |
| `0x0055e000`, `0x00570000`, `0x0154f100` | INIT | control | — |
| `0x0041a438`, `0x0017a1f8` | CODE | control | — |

`sh4xref --to 0x00d53500`: 33 literal loads in about 20 functions; the most
frequent are `fn 0x00415fe8` (6), `fn 0x0040dfa8` (6), `fn 0x003fcbf0` (3),
`fn 0x003faf04` (2), plus the reader functions `0x003f5a1e…0x003f5fc2`.

Board contradiction: M1.10b (done, `TODO.md` line ~541) already confirmed
`0x0055d954` = `OSMDLL!OSM_Printf`, while M3.15 (blocked) still names the same
address as the "compressed sec1 helper" that hides the LCTBL walker.

## Interpretation

- **FACT (C-3440):** 94.5 % of the compressed bytes of build A are BSS. A
  decompressed sec1 of `Navi.exe` contains 98,330 stored bytes; the other
  16.6 MB are zero at load.
- **FACT (C-3441):** the first 0xd38 B of `Navi.exe` sec1 are the IAT; all
  seven `0x0055dxxx` blocker addresses are import slots (memset, OSM_Malloc,
  taskIdSelf, OSM_isSender, OSM_Printf, OSM_SramSet, wcsstr). Their stored
  values are irrelevant: the loader writes them.
- **FACT (C-3442):** every BSS blocker address (`0x00d53500`, `0x00e23cc0`,
  RGD tables) is above the initialised length; **M1.2f would return zeros
  there**. The `0x00d53500` table is built at run time.
- **FACT (falsifier):** no cited blocker VA is `INIT`. M1.2f gates none of
  M3.11c, M3.15, M4.16b, M9.14, M9.17, M9.24.
- **OBSERVED (C-3443):** M3.15's two "callees in compressed sec1" are a call
  to `OSM_isSender` and a debug `OSM_Printf`. The LCTBL walker is not behind
  them; the search has to continue from `fn 0x004125a8` in sec0.
- **OBSERVED (C-3444):** the M3.15 zlib-table negative was a weak signature:
  constant tables of `Navi.exe` would sit in sec2 (read-only, compressed,
  fully initialised), which the scan cannot read. Not evidence that no
  inflate exists in plain code.
- **HYPOTHESIS (C-3445):** with sec1 mapped zero-filled past 0x1801a and the
  846 slots bound to named stubs, the M9.17 and M9.14 runs proceed past
  their current fault to the first real stub call (`memset`, `OSM_Malloc`).
  Test: M9.35.

## Conclusion

The "compressed `.data`" premise was the second wrong premise of the same
shape as the "compressed code" one retracted by the ninth pass (C-2128).
The board now says so: M3.15 re-opened (rule 15), M9.14/M9.17/M9.24 depend
on a new harness task **M9.35** (zero BSS + bound IAT), M4.16b/M3.11c depend
on a new search task **M3.22** (who writes `0x00d53500`), M1.2f keeps only
real `INIT` reads (sec2 constants, M1.3/M1.4) and is no longer critical, and
**H50** puts the classifier into `l3_precond`/`reader_precheck` and audits the
remaining "sec1" blockers (M3.2b, M3.14, M3.16, M4.26). `AGENTS.md` carries
the rule; `tools/va_class.py` makes it a command.

## Reproduction

```bash
python3 tools/va_class.py --selftest                                         # OK (8 cases)
python3 tools/va_class.py archive/head256.img --module Navi.exe \
    --resolve-with 0x3e00200 0x0055d040 0x00d53500 0x0055e000                # IAT memset / BSS / INIT
```

## Follow-ups

- [ ] **M9.35** — sec1 load model in the L3 harness (zero BSS, IAT → stubs, `INIT` reads fail loudly).
- [ ] **M3.22** — the run-time writer of `0x00d53500` (HDLMAP/schema table).
- [ ] **H50** — `va_class` in `l3_precond`/`reader_precheck`; audit M3.2b, M3.14, M3.16, M4.26 blockers.
- [ ] M3.15 re-run from `fn 0x004125a8` with the import calls labelled (`sh4xref --resolve-with`).
