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

---

## Priorities (product review 2026-11-06, fourth pass)

Earlier passes and the two older "what changed" sections are frozen in
[`docs/research/todo-history-2026-11-06.md`](docs/research/todo-history-2026-11-06.md).

**Nearest milestone: Marek's US unit shows a name we wrote.** The US path
(Marek, 2026-11-06) stays ahead of the OSM compiler because it tests the
real accept → display → route loop on the only hardware we have, with the
unit's own map code `QSD-301-103` (the region lock is the unit, M2.7).

| Stage (`card-test-plan.md`) | Card | Built by | Status |
| --- | --- | --- | --- |
| S0 factory clone | `LEAF_2011-2012_US.img` as is (`53342430…c5383`) | `dd` | ready for Marek now (**M6.2**) |
| S1 no-op recompression | `POINT010` page `0x840ba0` recompressed unchanged | **M5.13** | open |
| S2 POI rename | `HANA HEALTH CENTER` → `OSM2LEAF TEST POI1` (Hana, Maui, HI) | M5.12 done; image via **M5.13** | edit done, image must be rebuilt |
| S3 geometry | one road vertex moved in a US tile | **M5.14** | open |

**Why the M5.12 image must not go on the unit as is (PM check on the real
US image).** The factory US root directory starts with a volume-label entry
`QSD-301-103` (attr `0x08`, root slot 0; the BPB label is `NO NAME`).
`mkcard.py`'s fresh-build path (used for any changed tree) never writes that
entry, which is why M5.12's `cardcheck` warned "no volume label"; it also
re-lays out the whole FAT. That card would test three variables at once
(label, FAT layout, changed file). **M5.13** writes the changed file into its
existing cluster chain in a copy of the factory image, so S1/S2 differ from
S0 only in that file. **M5.12b** fixes `mkcard.py` for the compiler path.

**What the last round established (verified on the files, 2026-11-06):**

- **Acceptance gates are now mostly named.** `DIFFERENT MAP CODE` is decided
  in `AppLaunch.dll` (B/C) by an 11-byte compare of the unit's target-info
  record (`KernelIoControl 0x0101302C` +0x60) against the card's
  `VER_INFO/HDD_INFO.TXT`, *not* the `0x06000000` copy (M2.5).
  `HDD_CHK.ATT` (CRC-16/KERMIT) is read only by `MapUpdate.exe`, the updater,
  not by `Navi.exe` at boot (M2.12). The `SD Import … is different` messages
  validate user data (`*.slc`/`*.hlc`), not the map (M2.2). `HDD_INFO.TXT`
  line→field table is in `validation.md` (M2.3). Consequence: a US card that
  keeps `VER_INFO` untouched should pass the map-code gate on a US unit; for
  Poland we still need the exact 11 bytes and the `MAP DATA BASE UNMATCH`
  input (**M2.15**).
- **The compiler spine has tools, not yet a real tile.** `mesh_split.py`
  (M5.2), `tilewriter.py` (M5.4, synthetic 48/48), `mkcard.py` (M5.10,
  EU no-op rebuild byte-identical), `tile_diff.py` (M5.9). M5.4 was marked
  blocked on "no vendor tile" — that is not a blocker under rule 11; it is
  **open again** with a provisional class table until M5.3.
- **Compression is still unsolved:** 0/245 sections decode (M1.3); XPRESS
  LZ77 is ruled out too (M1.2b). Next: read the kernel's own routine
  (**M1.2c**) and try public CE ROM decoders (**M1.2e**, non-Claude).
- **The `.ind` reader was not where we looked.** `MAL_DataVol_*` are
  disc/data-volume fingerprint helpers (M3.1), `fn 0x00418748` only builds
  `.IND` paths (M3.2). New angle: find zlib's `inflate` and walk up (**M3.2b**).
- **`RDSTM001` 16-byte framing is refuted** (M4.15, 0/10 reciprocity) and no
  join key places rows on the map (M4.16) → M4.16b/c/d stay open.
- **L3 runner works end to end** on a probe (M9.5, PySh4 + stubs); the first
  real target should now be the map-code compare that M2.5 found (**M9.6**,
  re-scoped), which unblocks **M2.4**. Ghidra (M9.2) cannot be installed in
  the Claude sandbox → `Runner: non-Claude`.
- **US `DRSTR001` does not round-trip** (`l2check` diff at `0x1ae0`, also on
  the untouched factory tree, M5.12) → **M4.20**; M5.6 must write DRSTR for
  generated cards, so the model has to be right on both markets.

**Take these first (critical, ready, unowned), in this order:**

1. **M3.11 → M9.10** and **M3.2b → M9.11 → M9.12**: the software gate for
   the US rename. In parallel **M5.13** (in-place image patch → S1/S2
   images), **M5.12c** and **M3.12** (other copies of the name). M6.2 (S0)
   is optional now; the edited cards wait for the gate.
2. **M5.14** (US vertex move, S3); M4.8c (coord on the US grid) is done, so it is ready.
3. **M2.15** + **M9.6** → **M2.4**: the exact map-code bytes, run on the real
   comparator.
4. **M5.4** (real tile, provisional classes) → **M4.20** → **M5.6** →
   **M5.12b** → **M5.11**: the Dolnośląskie spine.
5. **M1.2c** (+ **M1.2e** non-Claude) → M1.3/M1.4/M8.E1: compression.
6. **M3.2b** → M3.2 → M3.3: the `.cmp`/`.ind` reader.

**Software before the car (Marek, 2026-11-06).** A car test is expensive,
so every edited card first passes the firmware's own code in L3:
**M3.11** (find the `POINT` reader) → **M9.10** (it returns
`OSM2LEAF TEST POI1`, software S2) and **M3.2b** → **M9.11** (the firmware's
`.cmp` layer reads our recompressed pair, software S1) → **M9.12**
(`l3check.py --card`, the gate). **M3.12** says whether the name search
holds a second copy. M6.5/M6.6 depend on these; only S0 (the factory
clone) may go into the car before them.

**Every generated format is confirmed by the firmware (Marek, 2026-11-06,
rule 13).** Three levels, cheapest first: (1) the reader is located and the
format doc cites its VAs (M3.5, M3.10, M3.11–M3.16); (2) an L3 target runs
that reader on our file (M9.10, M9.11, M9.13–M9.15) and the map-load chain
runs on a whole tree (M9.16, the "mock `Navi.exe`"); (3) full `Navi.exe` in
the emulated unit (M8 → F4 → M8.E4). **H11** keeps the per-file matrix;
nothing goes into the car before its rows reach level 2. **M5.15** wires it into one
command: factory image + OSM → card image → L1/L2/L3 checks (+ M8.E4 when
the emulator reaches F4).

**Phase-2 milestone (unchanged):** one OSM-generated Dolnośląskie tile on a
card image that passes L1 + L2 + `realcheck.py` and every known gate (M5.11).
The OSM inputs (M4.2, M5.1b) still need a non-Claude runner (rule 12).

**Needs Marek:** S0 on the unit (M6.2); building the Pico `.uf2` locally if
the unit's own SD LOCK menu is not used (M6.11); running the non-Claude
tasks (M1.2e, M4.2, M5.1b, M9.2) on a machine with normal internet.

---

## Priorities (product review 2026-11-06, fifth pass)

Earlier passes are frozen in
[`docs/research/todo-history-2026-11-06.md`](docs/research/todo-history-2026-11-06.md).

**Nearest milestone:** Marek's US unit shows a name we wrote. Every tool it
needs is on `main`; the two card images still do not exist.

| Stage (`card-test-plan.md`) | Card | Built by | Status |
| --- | --- | --- | --- |
| S0 factory clone | `LEAF_2011-2012_US.img` as is (`53342430…c5383`) | `dd` | ready for Marek (**M6.2**) |
| S1 no-op recompression | `POINT010` pair recompressed unchanged, patched into a copy | **M5.13b** (tool: M5.13 done) | image open |
| S2 POI rename | `HANA HEALTH CENTER` → `OSM2LEAF TEST POI1` | **M5.13b** (edit: M5.12 done) | image open |
| S3 geometry | one road vertex moved in a US tile | **M5.14** | open |

**Fifth-pass finding: the S-chain stopped one step short.** `tools/imgpatch.py`
(M5.13) is verified on a synthetic FAT32 fixture (46 checks): a same-length
patch changes only the differing bytes, a cluster-count change re-links both
FATs and FSInfo, and every write is envelope-checked to the map partition plus
the 72-byte `0x06000000` window. What it has **not** done is run on the real US
image: EXP-2026-11-06-M5.13 records C-2027 as `UNKNOWN` and its own follow-ups
are the exact commands. The board line read `done (planning)`, which is why
S1/S2 looked ready. **M5.13b** is that one run (S1 and S2 images, SHA-256, diff
ranges, `cardcheck --image` with the label present), plus the real-image check
M5.12b still owes (`mkcard` fresh build reporting the label). It needs stock
zlib 1.3.1, not zlib-ng (H9).

**What the fifth pass verified (2026-11-06, on `main`):**

- `python3 tools/selftest.py` → 45 passed / 0 failed / 18 skipped over 63
  suites (was 61: `imgpatch` and `l3check` are discovered by their
  `--selftest`, and the M4.12 tool adds a third); `tools/claims_check.py` → 0
  duplicate IDs, 0 unregistered claims. Every claim block the ten merged
  tasks reserved (C-1230…C-1290, C-1700, C-2010–C-2039, C-2290–C-2299) has
  its rows, so the ledger is current.
- **H11 gives the first whole-project coverage number:** 30 file families —
  6 writers exist, 5 are partial, 10 have no writer at all, 9 are copy-only.
  **12 families have no record-walking reader** and 4 have only a
  filename/path anchor. No row has an L3 verdict. That is the real distance to
  a Poland card, and it is larger than the board suggested.
- **M8 went from a plan to a reproducible toolchain, with zero boots.**
  `tools/qemu-ze0/build.sh` pins QEMU 8.2.7 (tarball SHA-256, offline
  `--selftest` of 42 checks, a `-M ze0` gate that fails loudly); the CCN/MMU
  block is factored into a `sh4-ccn` device (applies, builds, instantiates,
  `-M r2d` still starts); a `ze0-stubs` device models the five boot-blocker
  windows and is qtest-checked; `run.sh` + `gdb-ze0.py` give logs and a
  PC→module map. **No kernel has been booted with any of it** — the three
  series were never applied and built together. M8.A1 saw `m8a4-0002/0003`
  rejected on 8.2.7 while M8.A4/M8.A5 report them applying; that conflict must
  die in one clean `build.sh --force` run inside **M8.A2**.
- **M8.E1 was "refuted" by an endianness error.** M8.E1b shows nk.exe SH-4 is
  little-endian, the flag-test pattern is present at `0x88038666` (1 hit) and
  the M1.2c VAs/pools are correct: `DECOMP_WRAP 0x88037590` → `DECOMP_SECT
  0x88037464` → `DECOMP_BLK 0x8803a384`. Compression is no longer an address
  problem but a codec problem, so two cheap routes now run in parallel:
  **M1.2f** (port the block codec to Python) and **M8.E1** (call the real
  function — a LE `qemu-system-sh4` can now be built from M8.A1).
- **L3 is a skeleton that refuses to lie.** `l3check.py` runs every target and
  reports 1 PASS (a synthetic pipeline probe) / 5 BLOCKED; a blocked target
  exits 3 and claims no verdict. Correct — and it still means no map file has
  ever been read by firmware code.
- M1.2c, M5.12b, M6.12 (planning), M9.8, M9.9 landed as claimed; M4.20 fixed
  the US `DRSTR001` round-trip at `0x1ae0` (stored entry-name case), so both
  markets rebuild byte-identically.

**Take these first (critical, ready, unowned), in this order:**

1. **M5.13b** — the only thing between the board and two test cards. Then
   **M6.2** (S0) and **M5.12c** (every other copy of the old name).
2. **M9.6** (map-code compare: the one L3 target whose address and corpus
   exist), **M3.11 → M9.10**, **M3.2b → M9.11 → M9.12**: the software gate.
3. **M1.2f** and **M8.E1** in parallel: 245 sections, `FILESentry`, F3/F4.
4. **M8.A2** → **M8.A3** → **M8.A6**: F0 on a real boot log.
5. **M5.12c → M5.14** (S3), then the compiler spine
   **M5.4 → M5.6 → M5.11**.
6. The writers H11 shows missing: **M5.18** (`POINT`/`ADDRE`), **M5.17**
   (`LCTBL001`), **M5.16** (`LEV3456R`), **M4.21** (tile section 4), **M5.19**
   (`RDSTM001`) — each after its M3 reader.

**Needs Marek:** S0 on the unit (M6.2); the Pico `.uf2` built locally (M6.11);
the non-Claude tasks (M1.2e, M4.2, M5.1b, M9.2) on a machine with normal
internet; and a host that holds the US image for M5.13b (it is on the allowed
host, `https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img`).

**Software before the car (Marek, 2026-11-06).** A car test is expensive, so
every edited card first passes the firmware's own code in L3: **M3.11** (find
the `POINT` reader) → **M9.10**, and **M3.2b** → **M9.11** (the firmware's
`.cmp` layer reads our recompressed pair) → **M9.12** (`l3check.py --card`,
the gate). M6.5/M6.6 depend on these; only S0 may go into the car before them.

**Every generated format is confirmed by the firmware (rule 13).** Three
levels, cheapest first: (1) the reader is located and the format doc cites its
VAs (M3.5, M3.10, M3.11–M3.18); (2) an L3 target runs that reader on our file
(M9.10, M9.11, M9.13–M9.18) and the map-load chain runs on a whole tree
(M9.16); (3) full `Navi.exe` in the emulated unit (M8 → F4 → M8.E4). **H11**
keeps the per-file matrix; nothing goes into the car before its rows reach
level 2. **M5.15** wires it into one command.

**Phase-2 milestone (unchanged):** one OSM-generated Dolnośląskie tile on a
card image that passes L1 + L2 + `realcheck.py` and every known gate (M5.11).
The OSM inputs (M4.2, M5.1b) still need a non-Claude runner (rule 12).
