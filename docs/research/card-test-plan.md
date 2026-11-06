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

> M6.4 checklist (C-1120–C-1129; claim text in
> [`EXP-2026-11-06-M6.4-recovery`](../experiments/EXP-2026-11-06-M6.4-recovery.md)).
> Nothing here has run on a unit. Scope: return a **spare** unit to the factory
> map by card swap. Unit-side NAND/settings repair is out of scope — caveat and
> do-not-attempt list below. Abort criteria above still apply.

### Before each test — all ticked, or do not start

- [ ] **Original card off-bench and hashed.** Write-protected, stored away from
  the bench, SHA-256 on file with the P1 record (US `53342430…c5383`, EU
  `105e2032…76307`). It is **never** inserted during a test, not even as a
  control.
- [ ] **Known-good clone kept aside.** A second card written from the same
  market-matched image, hash-verified
  (`cardcheck.py --image … --hash --expect-sha256 …`), locked, and booted once
  before the series. Labelled, untouched, never written by a stage.
- [ ] **Unit power baseline recorded.** No-card boot at a 2 A current limit:
  which screen appears and when, whether `SECURE` clears under `TEST_B1`
  (M6.8). Every later boot is compared against that baseline.
- [ ] **Run card identified.** The card in the unit is a run card with
  stage/run ID and its written hash logged; hash it again after power-off.
- [ ] **Recovery within reach.** Card slot reachable via the extender without
  dismantling, 12 V switch and camera in reach, spare unit only.
- [ ] **Stop rule agreed.** First unpredicted screen, first post-run hash
  change, or a second identical failed boot ends the run.

### Failure signatures and first action

Signatures are verbatim from the `AppLaunch.dll` block (C-800–C-809); "known"
is what static analysis actually established.

| Signature | What is actually known | First action |
| --- | --- | --- |
| `NAVI VERSION NG` | String + module + one dispatcher per build (C-803, C-804, C-805). That SD `0x0020001f` is compared with a unit-side `NAVI-1` value is **external hearsay** (C-076); the compared bytes are UNKNOWN. | Power off. Refit the hash-verified known-good clone and boot once. It boots → quarantine the run card, record the screen; still NG → step 3 of the ordered path. Do not edit version bytes on the run card first. |
| `DIFFERENT MAP CODE` | String + dispatcher (C-803, C-804). Three candidate inputs: `HDD_INFO` line 1, the `0x06000000` copy, a NAND-side record (C-165; M2.5). Which one decides is UNKNOWN; `hddinfo.py` model M0 is HYPOTHESIS. | Same: known-good clone, boot once. Do not "fix" the map code before the clone boots — the screen does not say which copy was read. |
| `SD UNLOCK NG` | String + dispatcher (C-790). No CID/CSD check and no FAT serial/label check was found in `SDHC.dll`, `AppLaunch.dll`, `SdCardLch.exe` (C-794, C-795). The gate is the SD security state, and "no security" is an error too (C-797, HYPOTHESIS). The CMD42 scheme itself is external (C-075); the four unit-specific
password bytes are not in this repo. | Power off. Re-seat the card and inspect the extender (intermittent NG is a contact fault first). Re-lock the run card with the unit's own flow and retry **once**. Same screen on the known-good clone → lock/reader/bench fault, not map data → step 3. |
| `MAP DATA BASE UNMATCH` | String + dispatcher (C-803, C-804). Launcher code carries `MapDBVer : %d <= [%d] <= %d` (string OBSERVED; range semantics HYPOTHESIS, `validation.md`). | Known-good clone. If the clone shows it too, the unit's accepted DB range and the card's map set disagree: a market/version mismatch, not a recovery fault (gates 2–3 in `us-eu-region.md`). Record, do not patch. |
| Blue screen / no boot (no map frame, black > 60 s, reboot loop, `SECURE`, `SD ACCESS NG`, `SD INIT NG`, `NO SD CARD`) | The listed error strings are in the same `AppLaunch.dll` block (C-800–C-809); causes UNKNOWN. `SECURE` is a separate anti-theft screen whose CAN/VIN cause and `TEST_B1` bypass are **external** (C-082). | Power off at once; keep the 2 A limit. Remove the run card and boot with **no card**: baseline screen → card fault → ordered path; no boot with no card → power/unit, stop and check supply, ground, `TEST_B1` and CAN ignition frames. Do not reinsert the same card. |

### Ordered recovery path

- [ ] **0 — Capture, then discard the run card.** Power off, remove it, hash
  it. Hash changed → the unit wrote to the card: mark it disposable, never
  reuse it in the unit. Photograph the screen with its exact text.
- [ ] **1 — Untouched known-good clone.** Insert the pre-test clone. Boot once.
  Map renders, no dialog → the unit and bench are healthy and the fault is the
  run card; quarantine it and stop. Record either outcome.
- [ ] **2 — Re-lock.** If step 1 gives `SD UNLOCK NG`, re-lock that clone with
  the target unit's own flow (or LeafSDTools; external, C-075) and retry
  **once**. Never re-lock the original. Still NG → step 3.
- [ ] **3 — Factory card.** Power off, refit the untouched original, boot once.
  Factory map renders → bench and unit are intact; the fault is in every clone,
  so revisit P4/P5 (clone hash, lock) before any further run. Original also
  fails → the unit or bench is at fault, not the map data: stop, edit no card.
- [ ] **4 — Updater path, only if the unit offers it.** If the unit shows a
  map-update/import prompt or menu, use a **disposable** clone of the
  market-matched factory image carrying the files `MapUpdate.exe` opens
  (`VER_INFO/HDD_INFO.TXT`, `HDD_ADM.TXT`, `HDD_CHK.ATT`,
  `ClarionUpdate.key`, `SystemSD/MapFinish.key`; C-775) exactly as the factory
  card ships them. Expect validation, then partition format and file copy
  (`MapUpSdCardFormat` `0x0001d57e`, `DeleteAndCreatePartition` `0x0001c74c`,
  `DriveFormat` `0x0001c58c`; C-774, C-776): the card is consumed. Capture every
  screen and the post-run hash. No prompt on this unit → this step does not
  exist; go to step 5.
- [ ] **5 — Stop line.** Step 3 failed and step 4 unavailable → leave the unit
  powered off. Unit-side repair (NAND/flash/settings) is out of scope: it needs
  a verified NAND dump taken **before** the first run, test-pin access and a
  known-good image, none of which exists today (hardware unavailable). Report
  `blocked`, do not improvise.

### Proven by static analysis (reproducible offline)

- [ ] Error strings, module, VAs, one dispatcher per build — C-790, C-800–C-809.
- [ ] No CID/CSD check and no FAT serial/label check in the three SD modules —
  C-794, C-795 (negative, limited to those modules; no hardware confirmation).
- [ ] `MapUpdate.exe` file list, validation/format functions and VAs, CRC16
  attestation over `HDD_CHK.ATT` — C-774, C-775, C-776, C-778.
- [ ] `HDD_INFO` is 72 bytes with a byte-identical copy at `0x06000000` —
  C-005, C-074.

These say where the strings live and which files the updater opens. None of
them says what the unit displays or accepts.

### External hearsay only (not reproduced here)

- [ ] CMD42 password scheme, 4 unit bytes + ASCII `Clarion95321`, stored near
  `0xA100`, unlock at boot — C-075.
- [ ] `SECURE` is a CAN/VIN check; clearing PROD `A0A0–A0A3` or grounding
  `TEST_B1` disables it — C-082.
- [ ] `NAVI VERSION NG` compares SD `0x0020001f` with the unit's `NAVI-1` —
  C-076.
- [ ] Market byte in the PROD block at `A022` (`0x10`/`0x20`/`0x30`…), `NB00`
  card vs `NB04` NAND builds — `us-eu-region.md` table.
- [ ] A US QY7210NN once drew European streets from an EU card — leafsdtools
  issue #3.
- [ ] Test-pin + NAND restore as the way back from a bad region/firmware flash.

Treat all of these as leads, not as procedure.

### Untested (no unit has run this)

- [ ] Every screen-to-cause mapping in the table above.
- [ ] Whether a host-side re-lock yields a card the unit accepts.
- [ ] Whether the unit offers any updater/import prompt at all.
- [ ] Whether `MapUpdate.exe` accepts a card we assembled rather than a factory
  one, and what it does to the card when it refuses.
- [ ] Whether the unit writes to the card during boot.
- [ ] Whether a card swap leaves unit NAND and settings untouched.

### NAND / settings-restore caveat

- [ ] The only recovery asset in this plan is a card. Nothing here backs up or
  restores unit-side state: PROD block (`A022` market, `A0A0–A0A3`),
  `NAVI-1`/map record, the SRAM/VSRAM complete flag
  (`GetVSramCompleteFlag`/`SetVSramCompleteFlag`, C-774), radio and other user
  settings (`CopyUserData`, `\UserSD2\PRIVATE`, C-776).
- [ ] `MapUpdate.exe` sets the VSRAM complete flag and formats partitions, so a
  card-side "recovery" can change unit state too. Record it; do not assume the
  unit is untouched.
- [ ] A real NAND/settings restore needs a dump taken before the first run,
  test-pin access and a known-good image. No dump exists and hardware is
  unavailable; until it does, NAND work is out of scope and must not be sold as
  recovery.
- [ ] A factory-card swap restores the map the unit **reads from SD**. It does
  not prove internal state is unchanged — confirm with the no-card baseline and
  the original-card boot.

### Do not attempt

- [ ] Do not reinsert, write, lock or unlock the original card after a failure.
- [ ] Do not run the updater/format path (`MapUpSdCardFormat`, `DriveFormat`,
  `DeleteAndCreatePartition`) on the original or on the only good clone.
- [ ] Do not edit NAND/flash/PROD bytes, write firmware, or restore a NAND image
  as a recovery step.
- [ ] Do not synthesise `HDD_CHK.ATT`, `ClarionUpdate.key` or `MapFinish.key`;
  they are factory attestation/install files (C-775, C-778), not card metadata.
- [ ] Do not spoof CID/CSD/FAT serial/volume label: nothing checks them
  (C-794, C-795) and it changes nothing.
- [ ] Do not bypass, brute-force or publish the CMD42 password.
- [ ] Do not power-cycle a reboot loop more than twice, and never with the
  original card.
- [ ] Do not probe test pins, JTAG/BDM or UART on a live unit without the M6.8
  kit and a confirmed pinout.
- [ ] Do not run any of this on the owner's only unit or only card.
- [ ] Do not report a successful recovery as a format result: it restores the
  baseline and proves nothing about card acceptance.
