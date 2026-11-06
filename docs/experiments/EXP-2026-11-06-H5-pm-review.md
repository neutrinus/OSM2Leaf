# EXP-2026-11-06-H5: Board review and real-image checks of the synthetic-only results

- **Status:** done
- **Date:** 2026-11-06
- **Sample:** `IMG256` (first 256 MiB of `LEAF_2011-2012_QSD-309-101_navi158_eu.img`),
  SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (matches `TODO.md` "Shared inputs"). Downloaded into a scratch directory, not
  committed.
- **Claims:** C-1710–C-1716
- **Supersedes:** none
- **Superseded by:** none

## Question

Several tasks closed on 2026-11-05 as "synthetic only" or "blocked" because
the agent's checkout had no image (M1.2b, M1.6b, M2.1, M4.2). Do these
blockers hold when the shared `IMG256` input is fetched, and what do the
existing tools report on real bytes?

## Hypothesis

Exploratory. Expected: the M2.1 blocker is wrong, because `coredll.dll` lives
in kernel image B (C-525, C-527), not in image A.

## Inputs

| Item | Value |
| --- | --- |
| Image | `IMG256`, SHA-256 above |
| Download | `curl -r 0-268435455` from `files.viaaq.eu`: ~1 min from the cloud sandbox |
| Tools | `tools/cerom.py`, `tools/cecompress.py` at `main` `e8472bd` |

## Method

```bash
I=head256.img
# 1. Name the COREDLL ordinals that block M2.1 (coredll is in image B)
python3 tools/cerom.py --image-start 0x3e00200 $I exports coredll.dll \
  | grep -wE '59|65|66|496|719|1047|1118|1143|1145'
# 2. Compressed-section header hypothesis (M1.2a) on all sections of A
python3 tools/cerom.py --image-start 0x200200 $I comphdr --all | tail -1
# 3. Import-stub resolution (M1.6b) on the real image
python3 tools/cerom.py --image-start 0x200200 $I thunks Navi.exe
python3 tools/cerom.py --image-start 0x200200 $I thunks --all
python3 tools/cerom.py --image-start 0x200200 $I imports Navi.exe | wc -l
# 4. Decoder probe (M1.2b) on the two EXP-49 sections of NaviMapCC.dll
#    (file offsets from `cerom.py sections NaviMapCC.dll`, absolute in IMG256)
dd if=$I of=sec1.bin bs=1 skip=$((0x01580ce0)) count=$((0x2c6))
dd if=$I of=sec2.bin bs=1 skip=$((0x015aca7c)) count=$((0x68c))
python3 tools/cecompress.py probe --size 0x484 --offsets 0-40 sec1.bin
python3 tools/cecompress.py probe --size 0x5b8 --offsets 0-40 sec1.bin
python3 tools/cecompress.py probe --size 0xcc0 --offsets 0-40 sec2.bin
# 5. OSM ground truth reachability (M4.2, M5.1)
curl -sSI https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf
curl -sSI https://overpass-api.de/api/status
curl -sSI https://api.openstreetmap.org/api/0.6/capabilities
```

## Observations

1. `coredll.dll` exports (image B), ordinal → name:

   | Ordinal | Name | Used in |
   | ---: | --- | --- |
   | 59 | `wcschr` | `fn 0x004e7b8c` (twice) |
   | 65 | `wcsncmp` | `fn 0x004dd028` |
   | 66 | `wcsncpy` | `fn 0x004e7b8c` |
   | 496 | `Sleep` | `fn 0x004dd028` |
   | 719 | `sprintf` | control, matches C-527 |
   | 1047 | `memset` | `fn 0x004e7b8c` |
   | 1118 | `fclose` | `fn 0x004e7b8c` |
   | 1143 | `fgetws` | `fn 0x004e7b8c` |
   | 1145 | `_wfopen` | `fn 0x004e7b8c` |

2. `comphdr --all`: `245 compressed section(s) in 1 segment(s): 187 HOLDS,
   58 REFUTED, 0 UNPARSED`. Every REFUTED row checked has `flags` of the form
   `0x1000xxxx` whose low bits equal `psize` (e.g. `InfoBarCC.dll/sec2`
   `psize=0x977 flags=0x10000977`; `Vehicle.exe/sec2` `psize=0x1105
   flags=0x10001105`), and `uncompressed_len` equals `vsize` in most of them.
3. `thunks Navi.exe` → `error: no import stub matched (module Navi.exe, --all
   False)`; `thunks --all` → the same error for every module. `imports
   Navi.exe` lists 846 slots, the first at `0x0055d000` (TODO M1.3 says IAT
   `0x0054d000`).
4. Section 1 starts `84 04 00 c6 02 00 10 00 00 00 84 04 00 00 b0 02 00 00
   84 04 00 00 5b 80 80 8d …`, section 2 `c0 0c 00 8c 06 00 10 00 00 00 c0 0c
   00 00 76 06 00 00 c0 0c 00 00 5b 80 …` (identical to EXP-49). `probe`:
   `0 match(es) in 205 attempt(s)` for each of the three runs (41 offsets ×
   lzss, lzx, lznt1, xpress-lz77, xpress-huffman). `xpress-lz77` is
   `UNSUPPORTED` at every offset (match decode not implemented);
   `xpress-huffman` fails with an over-subscribed table.
5. All three OSM hosts: `CONNECT tunnel failed, response 403` (environment
   network policy; only `files.viaaq.eu` is on the allowlist).

## Interpretation

- **M2.1 is not blocked.** The COREDLL export table is in image B and names
  all six ordinals. `fn 0x004e7b8c` opens the file with `_wfopen`, reads it
  line by line with `fgetws`, splits lines with `wcschr` and copies fields with
  `wcsncpy`, then `fclose`. It is therefore also the text parser M2.3 looks
  for (OBSERVED calls; the field mapping is not traced).
- **M1.2a header model covers 76 %.** The 58 REFUTED sections look like a
  second header variant with a flag word `0x10000000 | psize`, not random
  failures (HYPOTHESIS; one variant check per section is needed).
- **`cerom.py thunks` does not work on the real image** (0 stubs on every
  module), although `sh4xref.py` reproduces the EXP-50 thunks. C-690 is a
  synthetic-only result; the real coverage is 0 %, not UNKNOWN.
- **M1.2b now has real input.** Three public decoders and XPRESS-Huffman fail
  at offsets 0…40; plain XPRESS LZ77 is the only candidate still untested,
  because its decoder is a skeleton.
- **M4.2 and M5.1 are blocked by the environment**, not by the method: no OSM
  host is reachable until one is allowed or an extract is placed on
  `files.viaaq.eu`.
- **Process finding:** "no image in the checkout" is not a valid blocker.
  `IMG256` downloads in about a minute; tasks must run their tool on it before
  they close as done or blocked.

## Conclusion

M2.1 and M1.2b are reopened with real inputs; M1.6b needs a fix task; M1.2a
needs a variant task for 58 sections; M4.2 and M5.1 wait on OSM access.
`TODO.md` updated accordingly (tasks H6–H7, M1.2d, M1.6c, M1.9, M2.11,
M3.8–M3.9, M4.15–M4.18, M5.1b, M5.9).
