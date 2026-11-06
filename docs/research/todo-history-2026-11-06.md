# TODO history (frozen 2026-11-06, fourth PM pass)

Verbatim copy of the review sections that headed `TODO.md` before the
fourth product review of 2026-11-06. Read-only; the live board is `TODO.md`.

## Priorities (product review 2026-11-06, third pass)

> **Near-term pivot (Marek, 2026-11-06): edit a tile that is already in the US
> map, not a freshly compiled Polish one.** Marek's only hardware is a US ZE0
> unit, so the first on-device proof should use the unit's own map. This is the
> lowest-risk first test on every axis and it moves ahead of the OSM compiler:
>
> - **Hardware + region match.** The region lock is the *unit*, not the card
>   (M2.7); a US card in a US unit trips no market gate. An edited US tile keeps
>   the native map code `QSD-301-103` / `X08-02-00`.
> - **Data is in hand.** The US 2011 image is on the allowed host
>   (`https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img`,
>   sha256 `53342430…c5383`, 113 tiles, N-America), so building and checking an
>   edited US card needs no new download permission and no card dump.
> - **Smallest proven change.** An in-place one-tile edit with section 4 kept
>   verbatim already passes L2 (M4.4, M5.8) — far less than the full
>   OSM→tile compiler (M5.2–M5.6).
> - **It exercises the real loop early:** accept → display → route on the actual
>   unit, which the EU/Poland path can never do on Marek's bench.
>
> So the new nearest milestone is **M5.12** (an edited US card image, built now
> against the US image) → **M6.2** (clone Marek's own card as the no-op
> baseline) → **M6.5/M6.6/M6.7** on the US card. The OSM→Poland compiler
> (M5.1→M5.11) stays the end goal and the US edit de-risks its accept path first.

**Where we are against the goal.** The two hard gates are now largely
answered. **Card identity is solved:** the SD lock is a 16-byte CMD42
password = 4 unit bytes + the 12-char ASCII tail, verified in `SDHC.dll`
(.text uncompressed), independent locking is feasible, and there is a tool to
set it (M2.13, M2.13b, M6.11). **The firmware is readable:** `cerom.py`
resolves 697/846 `Navi.exe` imports to names (M1.9), so every later firmware
read is cheaper. **The compiler has a front end:** `osm_ingest.py` turns a
`.osm`/`.pbf` into IMF (M5.1), and `coord.py` converts coordinates (M4.8).
Most on-card formats decode and round-trip.

What is still open splits into three fronts, none of them owned:

1. **Acceptance logic** — *why* a card is accepted, not just mounted:
   `HDD_INFO` parse and compare (M2.1→M2.3, M2.2→M2.5) and the `HDD_CHK.ATT`
   attestation (M2.12). Until these are read, a generated card might mount and
   still be rejected.
2. **The compiler spine** — IMF → tiles → card tree → image:
   M5.2 (mesh splitter, **now ready**: its deps M4.8 and M5.1 are done),
   M5.4 (tile writer), M5.6 (rebuild `DRSTR`/`MMAIN`/`.ind`), M5.10 (card
   image). This is the straight line to a card we can test.
3. **The L3 runner** — run the real firmware checks on our data: M9.2
   (Ghidra), M9.3 (stubs), M9.5 (runner). M9.4 (engine) and M9.7 (corpus)
   are done; M1.6c (thunks on the real image) feeds M9.2.

**Take these first (critical, ready, unowned), in this order:**

1. **M5.2 → M5.4 → M5.6 → M5.10**: the compiler spine. M5.2 can start now;
   each step feeds the next and ends at a card image. This is the shortest
   path to the Phase-2 milestone below.
2. **M2.1 → M2.3** and **M2.2 → M2.5**, then **M2.12**: acceptance. These
   decide whether the card from front 1 will be accepted, so they run in
   parallel with it.
3. **M9.2 + M9.3 → M9.5** (with **M1.6c** first): lets us run M2's checks
   and M3.3's `.ind` reader against real inputs instead of reasoning.
4. **M4.8b** (confirm `coord.py` on 10 real POIs — M5.2 depends on it) and
   **M4.15 → M4.16** (`RDSTM` framing and placement → feeds M5.3 road classes).
5. **M1.2b / M1.2d / M1.2c**: compression, which still gates M1.3/M1.4 (full
   module data, the registry hives for M2.7/M8.E2) and the compressed parts of
   `MapUpdate.exe`/`TestMode.exe`.
6. **M3.1 → M3.2 → M3.3**: the `.ind` reader contract.

**Phase-2 milestone (definition of done):** *one generated Dolnośląskie tile
on a card image the unit would accept.* Concretely: `osm_ingest` (M5.1) →
mesh split (M5.2) → one tile written (M5.4) → tree rebuilt with matching
`DRSTR`/`MMAIN`/`.ind` (M5.6) → `mkcard.py` image (M5.10) that passes L1 + L2
+ `realcheck.py`, **and** the acceptance facts (M2.3, M2.5, M2.12) say nothing
in that card trips a reject. The new integration task **M5.11** ties this
together. The earlier "S1 no-op card" is the first rung of M5.10 (rebuild the
factory tree unchanged, byte-identical) before any generated content.

**What changed since the second pass (verified on `IMG256` where checkable):**

- **M2.13b closed the card-identity gate.** The CMD42 password is 16 bytes
  (4 unit bytes as hex + the 12-char ASCII tail); `SDHC.dll` `.text` is *uncompressed*,
  so the IOCTL→CMD42 flag map was read directly. This **retracts my earlier
  C-1884** ("SDHC code compressed") — a good self-correction by that task.
- **M1.9** resolves cross-image imports (697/846 `Navi.exe` slots →
  `COREDLL!name`; 149 unresolved because their exporters are outside segment
  B). Verified: `COREDLL!_wfopen` resolves.
- **M5.1** `osm_ingest.py` (XML + PBF → IMF) passes its self-test; one real
  defect (PBF string-table index origin) was found and fixed.
- **M6.11** adds an RP2040 SD-lock tool (`tools/sdlock-pico/`, 580 host-test
  checks pass); the PIN is taken at run time, never committed (the committed
  `PASS="Changeme"` is an inert placeholder, refused at load — not a leak).
- **M2.7, M2.11, M3.7, M3.8, M3.9, M4.7, M4.9, M4.10, M4.11, M4.18** landed
  (market decision, `HDD_INFO` read trigger, router fields, `MMAIN` read,
  name collation, POI rename/resize, `ADDRE` grammar, POI icons, coarse
  levels, `LCTBL` framing). M3.9 replaces M4.13's ISO-8859-2 writer rule with
  CP1252 + transliteration (feeds the M5.7 name encoder).

**Process note.** M4.8 is still `done` with its 10-POI check unmet; that check
is M4.8b (open) and M5.2 should not trust the local scale until it passes.

## Review 2026-11-06 (what changed since PR #11)

Merged since the last board update: M1.2a, M1.2b (tool), M1.6b (tool), M1.8,
M2.9, M2.10, M4.1, M4.5, M4.6, M4.13, M5.8, H2, LZNT1. Checked against
`IMG256` in EXP-2026-11-06-H5:

- **M2.1 was not blocked.** `coredll.dll` is in kernel image B, and its export
  table names every ordinal: `fn 0x004e7b8c` calls `_wfopen`, `fgetws`,
  `wcschr`, `wcsncpy`, `memset`, `fclose` (C-1710). It reads `HDD_INFO.TXT`
  line by line, so it is also the parser M2.3 needs (C-1711). M2.1 is open
  again with the names in its input.
- **Compression:** the M1.2a header model holds for 187 of 245 sections; the
  other 58 look like a second form with flag `0x10000000 | psize` (C-1712,
  C-1713 → M1.2d). On the real `NaviMapCC.dll` sections, lzss, lzx, lznt1 and
  xpress-huffman give no match at offsets 0…40; plain XPRESS LZ77 is the one
  untested candidate (C-1715 → M1.2b reopened).
- **`cerom.py thunks` finds no stub on the real image** (C-1714 → M1.6c);
  `sh4xref.py` does. M1.6b stays done as a tool, its real coverage is 0 %.
- **Data side:** `RDSTM001` rows decode and round-trip, meanings unproven
  (M4.1 → M4.15, M4.16); `MMAIN001.DAT` is a FAT root-directory log, not a
  manifest, and contradicts `drstr.md` at `0x18c`/`0x1ac` (M4.5 → H6, M3.8);
  names are ISO-8859-2 with all Polish letters present, collation and length
  limits unknown (M4.13 → M3.9, M4.18); `tile_diff.py` and the vendored
  `tools_ze0` make one-tile edits measurable (M5.8 → M5.9).
- **OSM is unreachable from the sandbox** (C-1716): M4.2 and the region run of
  M5.1 (now M5.1b) wait for `download.geofabrik.de` to be allowed or an
  extract on `files.viaaq.eu`; they are marked `Runner: non-Claude` (rule
  12). M4.17 attacks link attributes without OSM.
- **Stale claims released:** PR #8 (`[M2.1]`, superseded). M1.7 is claimed by
  PR #15.

## State after EXP-35…51 (what changed)

- **The address model is solved.** `tools/cerom.py` parses `ROMHDR`, the
  module TOC, `e32`/`o32` and `FILESentry` for A, B and C (EXP-35, -36),
  with `exports`, `memmap`/`ghidra` (EXP-48) and a synthetic self-test
  (EXP-47). `imports` is in PR #5 (EXP-50, M1.6). Every old delta-based
  address is suspect until re-derived through `cerom.py`.
- **The old map-code chain was in the wrong module.** `0x6fab2c` →
  `0x6faeb0` → `0x6fb05c` and `0x0369d400` (`sprintf` thunk) are `BT_MGR.dll`
  code (C-520, C-528). The real `HDD_INFO.TXT` / `SD Import` literals are in
  `Navi.exe` (C-521): VA `0x004e7d28` (paths), `0x004e8584` / `0x004e995c`
  (comparator messages).
- **First reader entry is anchored.** `Navi.exe` calls
  `OBJDLL!MAL_DataVol_getOffset` at `0x003778b2` and `0x00377b46`, `getSize`
  at `0x003778bc` and `0x00377b52`, through thunks `0x003d1bb0` / `0x003d1ba4`
  (EXP-50).
- **Compression is the one firmware unknown.** Code is never compressed
  (C-530); RW data sections and some `FILESentry` payloads are. zlib, LZMA
  and bz2 fail from the stream start (EXP-49, EXP-51); `tools/cecompress.py` has LZSS/LZX candidates tested
  on synthetic streams only (EXP-52). The streams share a
  header (see M1.2a).
- **Full-system emulation is possible, not hopeless.** Stock QEMU
  `-M none -cpu sh7785` runs B's `nk.exe` into the scheduler (EXP-37). This
  supersedes the old "L5: full-system QEMU is not realistic" verdict.
- **B carries the updater set** (`UpdateMng.exe`, `MapUpdate.exe`,
  `PRGUpdate.exe`, …) and C carries `TestMode.exe` (C-526): new, direct
  sources for how the unit checks and installs map data.
- **Data-side tools landed:** `hddinfo.py` (EXP-41), `section4.py` (EXP-42),
  `rdstm_schema.py` (EXP-43), IMF v1 + `imf_check.py` (EXP-44),
  `profile_validate.py` + `build.py --dry-run` (EXP-45), `diff_years.py`
  (EXP-46), `header_block.py` (EXP-40), `tools/l3_harness/` (EXP-38).

## Workstreams at a glance

| Stream | Front | Ready now (no open deps) |
| --- | --- | --- |
| H | Housekeeping: ledger, docs, tool overlap | H8, H9 |
| M1 | Firmware tooling (decompression, disassembly, xrefs) | **M1.2b**, M1.2c, M1.2d (M1.9, M1.6c done) |
| M2 | Map code, activation, updater, error screens | **M2.1, M2.2, M2.12** (M2.7, M2.11, M2.13, M2.13b done) |
| M3 | Reader contract (what the unit reads from the card) | **M3.1**, M3.6, M3.10 (M3.7, M3.8, M3.9 done) |
| M4 | Data formats (no firmware needed) | **M4.8b, M4.8c, M4.15**, M4.3, M4.12, M4.19 (M4.7, M4.9, M4.10, M4.11, M4.18 done) |
| M5 | OSM compiler vertical slice (Dolnośląskie) | **M5.12 (US POI rename, nearest), M5.2, M5.10, M5.11**, M5.9; M5.1b non-Claude |
| M6 | Hardware and safety (planning now, tests later) | M6.9 (non-Claude runner); tests need hardware |
| M8 | Full-system emulation (QEMU `ze0`) | M8.A1, M8.A2, M8.A4, M8.A5, M8.E1 (after M1.2c) |
| M9 | L3 toolkit (run firmware functions on our data) | **M9.2, M9.3**, M9.1, M9.5, M9.8 (M9.4, M9.7 done) |

**Critical path to a first accepted card (updated):** card identity is
done (M2.13/M2.13b/M6.11). Two live strands now meet at M5.11:
· **acceptance:** M2.1 → M2.3 + M2.2 → M2.5 + M2.12 (why a card is accepted)
· **compiler spine:** M5.1 (done) → M5.2 → M5.4 → M5.6 → M5.10 → **M5.11**
(generated tile on an accepted card image) → hardware M6.5–M6.7.
Supporting: M3.1 → M3.2 → M3.3 (reader `.ind`) · M4.8b + M4.15 → M4.16 →
M4.2/M4.17 → M5.3 (road classes) · M1.2b/c/d → M1.3 (L3 data) ·
M1.6c → M9.2 → M9.5 → M2.4 / M3.3 (run the real checks). Every other task
widens knowledge or tooling in parallel and is equally welcome.
