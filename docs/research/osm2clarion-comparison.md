# osm2clarion vs OSM2Leaf: comparison, proposed contributions, and what it means for us

Status: discussion paper for the owner (H148, 2026-11-24). Nothing here has
been sent upstream: no issue, no pull request, no message. The list in §4 is a
proposal to agree on first.

Upstream: <https://github.com/albertbm/osm2clarion>, read at commit
`458f5f0da3466de704190f8b2778d2c85688be9e` (2026-11-23), cloned into an empty
directory outside this repository. Its code was read, not run. Record:
[`EXP-2026-11-24-H148-osm2clarion-comparison`](../experiments/EXP-2026-11-24-H148-osm2clarion-comparison.md).

## 1. What osm2clarion is today

| Item | Value (read off the clone) |
| --- | --- |
| History | 343 commits, 2026-10-06 to 2026-11-23, one author |
| Size | 165 files: `build.py`, 82 tools in `tools/`, 13 in `tools/diag`, 11 in `tools/addr`, 7 docs, 2 profiles |
| Tests | 36 test files, 742 `test_` functions, no CI workflow in the repository |
| Licence | GPL-3.0-or-later (same as this repository); built maps ODbL; factory data excluded |
| Units | QY8 (X08-03-00, ZENRIN, `CLA-NAVI06-01`): Leaf 2016–2019 and e-NV200, EU and US, tested in cars. QY7 (X08-02-00, HITACHI, `CLA-NAVI05-01`): one unit (QY7221NL) and an emulator |
| Regions | Iceland (QY8, "generate" mode: a country the card lacked, built from scratch). Finland (QY7, "area" mode: factory background kept, all roads stripped, the roads of one town or the whole country rebuilt from OSM) |
| Base cards | EU 2014 QY8 (`GEURX-30-100-100`), EU 2017 QY8 (`GEURX-30-105-100`), EU 2014 QY7 (`QSD-357-101`), one NA QY8 card for the index only |

What their README states as working: coast, land, roads and road names; route
guidance (long routes in an emulator only); roundabouts; speed-limit signs;
speed cameras; address search with house numbers; house numbers drawn along
streets; POI icons and POI search; slip-road codes and junction pictures;
the building-scale map (`HOUSE001`). Not built: signposts, lake and river
names. Not working: the card's own map version on screen. Open on QY7: a
destination near Oulu crashes the unit; street search not confirmed on a unit;
postcode search and the other countries' address search still read factory
data that points at removed roads.

Their QY7 support was added between 2026-11-11 and 2026-11-23, in parallel with
our M5.84–M5.103 work. `tools/clarion_format.py` holds the X08-02 differences
in one `Format` object (zlib window 15 and `78 9c`, 4-byte record padding,
mesh x stored minus 1024, Latin-1 labels, section table of 341 slots, section-2
level types `0x91`, two-way bit 13, no tail table, area codes in names items,
and a dozen graph rules).

Their code cites `Navi.exe` addresses (`0x34bf3c`, `0x34d2b8`, `0x34d3e4`,
`0x3545dc`, `0x3605a0`, `0x4de924`, `0x516604`), so they also read the
firmware. `0x3545dc` lies just past our premap reader `0x003534d4`; we did not
check whether it is the same build.

Their history was rewritten: the commit our `tools/ze0-viewer` pins
(`07fbf78d…`) is no longer in the repository, so `tools/ze0-viewer/setup.sh`
cannot re-create our vendored copy.

## 2. Side by side

| Subject | osm2clarion | OSM2Leaf |
| --- | --- | --- |
| Map container, grid, parcel codes, zlib records | Complete for QY8 and QY7, byte-identical rebuilds of factory tiles | Complete for QY7 (2011 EU and US), byte-identical header and relayout |
| Background (land, sea, land use) | From scratch on QY8, every zoom level 1–6; on QY7 the factory background is kept | From scratch on QY7, levels 1 and 2, one London tile (Z2–Z4, Z6) |
| Road drawing | Levels 1–5 on both formats, speed limits in the style word, link codes (slip road, roundabout), chains across OSM ways | Levels 1 and 2 on QY7, names and shields (Z3, Z5, Z6) |
| Routing graph | Levels 1, 2, 4, 5 on both formats with one-way bits, turn bans, cost words, edge triples; 300 long routes checked statically per card; driven on QY8 and on one QY7 | Levels 1, 2, 4, 5 on QY7, routes computed and drawn in QEMU for one tile (M5.57, M5.103); not driven |
| Whole country | Iceland (QY8), Finland (QY7, 7 cells) | One tile |
| Address, intersection, POI search | Writers for ADDRE, INTER, POINT, ICODE on both formats, from a national register or OSM | Readers and single-record edits (POI rename, move, add); no index writer |
| `HOUSE001`, cameras, speed limits, junction views | Built | Not started |
| Card indexes (`DRSTR001`, `MMAIN001`, `CMP.LST`) | Byte-identical regeneration | Byte-identical regeneration |
| Static card checks | `card_check.py` (about 30 factory-measured rules), `drive_check.py`, `card_verify.py`, resolvers for the three search files | `verify.py`, `l2check.py`, card ladder |
| Firmware as a check | Cited addresses only | `datask_l3.py` (the firmware's map client on a card), Ghidra recipe, 7,596 decompiled functions, claims ledger of about 5,200 rows |
| Emulator | "A QEMU-based emulator" is mentioned; none is in the repository | `-M ze0` in `tools/qemu-ze0`: boots the 2011 card to the map, touch, GPS frames, wheel pulses and gyro, gdb, deterministic screenshots |
| Unit side | DATA VERSION must match the unit; a 20°W position bound needs a NAND patch kept outside the repository; consent is an external hook | Unit flash map, PROD area, region and map code checks, EU card on a US unit driven in a car (M1.57), consent patch on the card (`tools/ze0_consent.py`), anonymous unit flash |
| SD card lock | Not mentioned | CMD42 mechanism, Pico lock tool, unit menu behaviour |
| Hardware documentation | None | Head unit, serial ports, CAN, audio, Bluetooth, camera, GPS, telematics pages |
| North American QY7 | None | US 2011 card (113 tiles) decoded with the same tools |
| Other card files | `COORD`, `ZIPFR`, `FRWAY` listed as unexamined; `RDSTM001`, `TFTBL001`, `BICON001` as not needed | `COORD001` verified, `FRWAY` census tool, `ZCODE` forms A and B, `RDSTM001`, `LCTBL` (TMC table), icons, skins, sounds |

Summary of the table: on the map compiler they are ahead of us on every row
except QY7 from-scratch background. On the unit, the firmware, the emulator
and the hardware we hold nearly everything and they publish nearly nothing.

## 3. What we can learn from them

1. **The full zoom ladder.** Level 3 lives in `LEV3456R.DAT` as one directory
   per tile cell, appended in (row, column) order; the unit addresses tile
   files by position in the `MAPAL001` index, and those positions come from
   the level-3 group. Levels 4 and 5 have fixed column counts (44 and 11) that
   the unit never reads, so a database is moved, not widened. We have not
   written level 3 at all.
2. **Speed limits and link codes.** The level-1 style word carries the posted
   limit (`((w & 0x1f) + 1) * 5`), bit 12 or 13 the two-way mark; shape word 3
   and graph w4 carry one link code (0 plain, 1 carriageway, 3 slip road,
   7 roundabout). We write none of these.
3. **Turn restrictions as regulation words**, including the cyclic order of a
   regulation list and the QY7 differences (`0x3ff` mask, no word at the
   arriving end of a one-way link).
4. **Search indexes.** `addre_io.py`, `inter_io.py`, `point_io.py`,
   `zcode_io.py`, `icode_io.py` write what our M4/M5 tasks only read.
5. **Whole-card discipline.** Step manifest (generated, edited, leftover per
   file), `.partial` until the checks pass, reuse of steps whose inputs did
   not change, `uv.lock` because another shapely moves a point.
6. **Factory-measured limits as tests.** `card_check.py` holds each rule to
   what the factory cards measure, with the counts in the docstring. Several
   of our crash findings appear there or in `rd_build.py` as rules (no junction on a parcel line,
   two links between one pair of nodes, level-2 links that walk into a dead
   end).
7. **Their QY7 list of differences** (`clarion_format.py`) is a ready checklist
   for our writers: every row is either something we already found or a gap.

## 4. What we could give them (proposal, not yet sent)

Ordered by value to them against cost to us. "Checked" means the gap was
confirmed in their tree at the commit above.

### A. Small, self-contained, ready to send

1. **`.ind` header fields.** Their `docs/FORMAT.md` and
   `tools/decompress_fast.py` read `0x08` as a `uint8` block count followed by
   "7 metadata bytes, unidentified". It is `uint32 LE` chunk count at `0x08`
   and `uint32 LE` chunk size (`0x10000`) at `0x0c`, verified on all 194 pairs
   of the EU 2011 card ([`cmp-ind.md`](../format/cmp-ind.md)). Their own
   `card_pack.py` already unpacks `<IIII`, so this is a doc and reader fix.
   Checked.
2. **zlib build guard.** Their byte-identical claims depend on the zlib that
   Python links; a zlib-ng build gives other bytes (our H9). Their tree has no
   guard (`grep -ri zlib-ng` finds nothing). Offer the check from
   `tools/zlibinfo.py` as a test or a build-time warning. Checked.
3. **`COORD001`, `FRWAY`, `ZCODE` on QY7.** They list `COORD`, `ZIPFR` and
   `FRWAY` as unexamined. We have `COORD001` as a table of region bounding
   boxes (EU 33, US 11), the `FRWAY` shard census and the two `ZCODE` forms
   ([`coord-zcode-icode.md`](../format/coord-zcode-icode.md),
   [`refer.md`](../format/refer.md)). A doc contribution. Checked that the gap
   is stated in their `FORMAT.md`.
4. **A second QY7 database.** Their X08-02 constants come from one card
   (`QSD-357-101`, 2014). We can confirm or correct each on EU 2011
   (`QSD-309-101`), EU 2016 (`QSD-390-100`) and US 2011 (`QSD-301-103`) by
   running their read-only checkers on our images, and send the counts. This
   also gives them the first North American QY7 measurements. Needs a run on
   our side first (follow-up task below).
5. **Non-canonical block address.** Factory tile `B30R048R` on the EU 2011
   card stores the address tag `0x00000060` where their writer would emit
   `0x00000c00` for the same offset (our C-941). A one-line note and a test
   for their byte-identical rebuild. Needs confirming against their current
   reader, which may already keep the raw tag.

### B. Larger, where we hold something they lack

6. **The QY7 emulator, with gdb, GPS and wheel pulses.** Their README says
   address search and the car position need a real GPS feed or a drive. On
   `-M ze0` the car follows injected GPS frames once wheel pulses agree (the
   tow test, M8.H32), and routes are computed and read from the serial log.
   Offer: a link from their "Try a card before the car" section and a short
   recipe for running a QY7 card they built.
7. **Help with the Oulu crash.** We can reproduce a QY7 routing crash under
   gdb and read the fault back to a card field; that is how the three
   section-2 crashes of M5.103 were found. Offer to run their Finland card
   (built by us from our own QY7 base) and report the faulting reader and
   record. Needs their build to run on our base card first.
8. **Generate mode for QY7.** Their `build.py` refuses generate mode for
   X08-02 because the background, coarse and POI steps write QY8 records only.
   Our Z1–Z6 work is the QY7 half of that: an empty container the firmware
   accepts, the empty-pair sentinels, background layers and types, place
   labels, shields, level-2 background. The useful form is a port of those
   rules into their `Format` object and `bg_encode.py`, not our own writers.
9. **Firmware-side facts for QY7** that explain what their cards must satisfy:
   which reader consumes which structure (reader coverage matrix), the record
   size limits (`0x8100` read length, `0x10000`-word records), the
   level-above bit, the `LEV3456R` record placement for levels 4 and 5. Most
   overlap with rules they already measured; send only the ones their
   `card_check.py` lacks, after a row-by-row comparison.
10. **Unit-side documentation for QY7**, as a linked document rather than code
    in their tree (their policy keeps firmware patching out of the
    repository): the card carries the operating system and `Navi.exe`, so
    consent and position limits are card-side on QY7; the map-code check that
    rejects a card from another market and how an EU card runs on a US unit;
    the SD card lock (a QY7 card cannot simply be read with `dd` until it is
    unlocked). No PIN, PROD or vendor bytes in any of it.

### C. Not worth sending

- Our tile writers (`tile_from_zero.py`, `sec2_writer.py`, `sec2_level2.py`):
  theirs cover more and are tested against more cards.
- Our claims ledger and task board: project-internal.
- Anything derived from the unit dump beyond layout facts.

## 5. Does our project still make sense?

**The map compiler part (stream M5) is overtaken.** The stated goal of this
repository, a Poland map from OSM for the ZE0 unit, is closer through
osm2clarion's area mode than through finishing our own writers: they already
build a whole country on the same format, with search, and have driven it on a
QY7 unit. Continuing M5 as a separate compiler would duplicate work that is
ahead of ours and better tested.

**Three parts keep their value, and osm2clarion does not replace them:**

1. The emulator and the firmware knowledge. Nobody else publishes a bootable
   QY7 unit with input, GPS and a debugger. It is the cheap test bench for any
   card, theirs included.
2. The unit side: region and map-code checks, EU card on a US unit, consent,
   SD lock, unit flash, audio and radio differences. This is what made the car
   test on 2026-11-24 work and it is specific to the 2011–2012 unit.
3. The 2011 databases and the US market, which they have not measured.

**Recommended direction** (owner's decision):

1. Run osm2clarion area mode for Poland (or Dolnośląskie first) on the EU 2011
   base card, boot the result in `-M ze0`, then on the car. This is one task
   and it decides the rest: if it works, Marek's goal is reached with their
   compiler plus our unit-side steps.
2. If it works: freeze M5 writers, keep them as the reference for the QY7
   generate-mode port (item 8), and put new compiler work upstream.
3. Keep M1, M2, M6, M8, M9 (firmware, unit, hardware, emulator, gates) as this
   project's own scope, with osm2clarion cards as the test input.
4. Replace the vendored `tools/ze0-viewer` copy (pin no longer exists upstream)
   with the current upstream as a dependency, since it now reads X08-02
   natively.

Known limits of that route, from their README: outside the built area the
card draws the map but has no roads and cannot route; other countries' address
search is likely to crash; street search on QY7 is not confirmed on a unit.
For a Poland-only card these are acceptable for a first test, and they are
places where our emulator can help them.

## 6. Follow-up tasks

- M5.104: build an osm2clarion area-mode card for Dolnośląskie on the EU 2011
  base and boot it in `-M ze0`.
- H149: `tools/ze0-viewer` pins an upstream commit that no longer exists.
- After the owner agrees on §4: prepare items A1–A3 as upstream pull requests.
