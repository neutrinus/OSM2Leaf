# Spare-card test plan

Status: **planning only**; nothing has run on a unit. This is the procedure for
M6.5–M6.7, recorded in
[`EXP-2026-11-06-M6.3-card-plan`](../experiments/EXP-2026-11-06-M6.3-card-plan.md).
Rule: **one variable per card**, each stage starting from the last accepted image.

## Prerequisites

- [ ] **P1 — Original card read-only.** Write-protect, image twice
  (`dd`/`ddrescue`), require identical SHA-256, keep one copy offline; never
  write the original. Sources: US 2011 `53342430…c5383` (C-070,
  EXP-2026-11-05-35), EU 2011 `105e2032…76307` (C-001); re-dump the physical
  card at test time if possible (M6.2).
- [ ] **P2 — Market match.** US image on the US unit (or EU on EU); a mismatch
  is a rejection that says nothing about the format (`us-eu-region.md`).
- [ ] **P3 — Spare card.** 16 GB SDHC, not SDXC (C-149). Whole-device clone:
  MBR, pre-partition area, FAT32 and the 402 MB TFAT16 tail stay (C-166);
  whole-card imaging is the only externally validated method (C-148).
- [ ] **P4 — Clone verified.** Source and read-back hashes equal, then
  `python3 tools/cardcheck.py --image CARD.img --hash --expect-sha256 <hash>`
  → PASS as on the US image (EXP-2026-11-05-35).
- [ ] **P5 — Lock.** Lock with the target unit's CMD42 password via its own
  flow or LeafSDTools; do not spoof CID/CSD/FAT serial/label (C-794, C-795,
  C-798). The scheme is external, `OBSERVED` (C-075), not repeated here.
- [ ] **P6 — Bench and log.** 12 V, `TEST_B1` grounded, card extender + host
  writer, fixed camera and GPS/ignition state (`feedback-loop.md` Option F);
  spare unit only. Log stage/run ID, part number, `PROD A022`, `NAVI-1`, map
  record, hashes, boot time. Cycle: write image → hash → lock → boot → capture
  → power off → hash the card again (a change means the unit wrote to it).

## Proven offline vs still to be shown

| Proven offline (reproducible) | The card test must still show |
| --- | --- |
| DRSTR/MMAIN/`.cmp` round-trip: 194/194 EU, 58/58 US (C-505, C-506, C-070) | A clone locked with the unit password boots at all (C-148, C-797) |
| No per-file checksum/signature found (C-147, C-162, C-168) — negative, limited scope | The unit accepts **non-factory zlib bytes**, then changed content |
| Same-length POI rename: size and DRSTR unchanged, one page (C-145, C-146) | The renamed string is what the display reads (EXP-2026-11-05-02: UNKNOWN) |
| One-vertex tile edit, section 4 preserved, L2 PASS (C-920–C-928) | The unit renders changed geometry at the changed place |
| Tile writer reproduces factory tiles byte-identically (C-943, C-944) | A generated tile (M5.4/M5.6) is accepted and routed over |
| `HDD_INFO` is 72 bytes with a byte-identical copy at `0x06000000` (C-005, C-074) | Which input decides `DIFFERENT MAP CODE` (C-077, C-165; M2.5) |
| Error screens catalogue: module, string VA, dispatcher (C-800–C-809) | Which screen each real rejection actually shows |

Nothing in the right column may be reported as a result before the run.

## Stages

### S0 — whole-card clone, no changes

- **Setup:** write the market-matched image byte-for-byte (P3/P4), lock (P5),
  insert, boot to a stable map, one power cycle. No file edited.
- **Record:** boot time to first map frame, every screen in order, dialog text
  verbatim, map at fixed coordinates/zoom, post-run card hash.
- **Pass:** same behaviour as the original card, no error screen, map renders,
  card hash unchanged.
- **Fail:** `SD UNLOCK NG` → lock (C-790, C-797); `NAVI VERSION NG`,
  `DIFFERENT MAP CODE`, `MAP DATA BASE UNMATCH` → clone or market mismatch;
  black screen/reboot → stop, do not run S1.
- **Rollback:** original card back; re-image the spare.

### S1 — no-op recompression control

- **Setup:** one single-chunk `REFER001` `.cmp` pair (EU `POINT032` page
  `0x4200`, C-146; confirm a US shard with `cmpind.py info`). Recompress the
  unchanged bytes with stock zlib 1.3.1, level 6, wbits 15, memLevel 8
  (`docs/format/cmp-ind.md`) and rebuild `.ind`; require payload diff 0 and
  `cmpind.py verify` 1/1. Only `.cmp` + `.ind` change; size may differ
  (control: 5,143 → 5,110, EXP-2026-11-05-02).
- **Record:** before/after hashes and sizes, verify output, boot time, map and
  POI list access, dialog text, post-run card hash.
- **Pass:** boots to the map, POI list opens, no dialog.
- **Fail:** rejection → factory-exact compressed bytes or an unknown container
  check; stop and pivot to a byte-preserving edit in an uncompressed file
  (`minimal-change.md` falsification table).
- **Rollback:** restore the pair from the accepted image and re-hash.

### S2 — same-length POI rename

- **Setup:** from S1, rename a POI visible in list/detail, byte length
  identical, `.cmp` + `.ind` only; pick a name that exists on this card (the
  EU `VATICAN MUSEUM` fixture is not on the US card). Require
  `validate_mutation.py` PASS and `cmpind.py verify` 1/1.
- **Record:** old and new text in search, list and detail, map at the POI,
  boot time, dialog text.
- **Pass:** new name displayed, old absent, no dialog, rest of the card works.
- **Fail:** both boot but no new text → wrong page/shard or wrong display
  source (EXP-2026-11-05-02); dialog → content check. Record which, stop.
- **Rollback:** restore the pair.

### S3 — one changed tile

- **Setup:** two variants, one card each. **3a** one-vertex change with
  `tools/ze0-viewer/harness.py mutate` (C-920–C-928). **3b** a generated
  roads-only tile once M5.4/M5.6 exist. Keep size, DRSTR entry and MMAIN rows
  consistent; require `harness.py verify` and `l2check.py` PASS first.
- **Record:** map at the tile, three zoom levels, the changed road/vertex,
  boot time, dialog text, post-run card hash. Routing is M6.7.
- **Pass:** map renders, change visible at the expected place, no blank tile,
  no dialog.
- **Fail:** tile unread or blank → container/section-4/DRSTR; dialog →
  acceptance check. Capture the area and screen.
- **Rollback:** restore the tile plus DRSTR/MMAIN if touched.

### S4 — `HDD_INFO` / map-code variants

Four single-variable runs, one card each (`validation.md`; `us-eu-region.md`
step 2): **4a** line 1; **4b** line 1 + the `0x06000000` copy; **4c** line 2
(label/map-set code); **4d** full foreign `VER_INFO`. Edit with
`tools/hddinfo.py`, record the exact 72 bytes; model M0 is `HYPOTHESIS`.

- **Record:** screen and verbatim text (`DIFFERENT MAP CODE`,
  `NAVI VERSION NG`, `MAP DATA BASE UNMATCH`), whether the map renders, boot
  time, version screen if reachable.
- **Pass:** each run gives an unambiguous recorded outcome; this stage passes
  on evidence, not on acceptance.
- **Fail:** 4a and 4b behave identically and 4c/4d do not move either → the
  decider is elsewhere (NAND, `0x20001f`, updater record); hand to M2.5.
- **Rollback:** restore the file(s), confirm the accepted image still boots.

## Photo and screenshot checklist

- [ ] Unit identity plate, card label front/back, card slot before insertion.
- [ ] S0: all boot screens, any dialog, map at fixed coordinates/zoom; S1: map
  and POI list open, no dialog.
- [ ] S2: list row, detail, map at the POI, search field with both names.
- [ ] S3: changed tile at three zooms, full screen and close-up.
- [ ] S4: each dialog full-frame **and** close-up of its text; version screen.
- [ ] Video each boot with a clock in frame; note the first-map-frame time.
- [ ] Name files `<date>-S<n>-<run>-<subject>.jpg`; store with the P6 log.

## Abort criteria

Stop at the first occurrence, power off, restore the original card, write the
observation into the EXP:

- any unpredicted error screen in S0 or S1;
- `SECURE`, `SD ACCESS NG`, `SD INIT NG`, `NO SD CARD`, a map-update prompt,
  black screen beyond 60 s, reboot loop, smoke, smell or unusual heat;
- the card no longer locks/unlocks with the expected password;
- the post-run card hash differs from the written hash (the unit wrote to it):
  treat the card as disposable and stop;
- the original card was inserted and may have been written;
- two consecutive runs with no interpretable difference.

## Recovery

> Placeholder — M6.4 (C-1120–C-1129) adds the full recovery checklist here.
> Until then: power off, remove the test card, refit the untouched original
> card, verify the unit boots the factory map. The original is never edited, so
> firmware/NAND recovery is out of scope for this plan.
