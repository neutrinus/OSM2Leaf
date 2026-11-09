# Reader coverage: every file the compiler writes

> **Snapshot:** 2026-11-06, EU 2011 sample
> `LEAF_2011-2012_QSD-309-101_navi158_eu.img`
> (SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`).
> **Status: survey only.** This page restates existing claims and task states;
> it creates no new fact and promotes nothing. A row may say "read by
> firmware" only where the claim ledger already has a located VA and an EXP.
> Task: H11. Experiment record:
> [`EXP-2026-11-06-H11-reader-coverage`](../experiments/EXP-2026-11-06-H11-reader-coverage.md).

The compiler is only as finished as the weakest cell in the chain:

```
writer exists  ->  offline L1/L2 proof  ->  firmware reader located  ->  L3 run
```

A file can round-trip byte-identically and still be read wrongly (or not read
at all) by `Navi.exe`; conversely a located reader without a writer does not
produce a card. The two sides are tracked separately below.

## How to read a cell

| Cell | Values |
| --- | --- |
| **Gen** | `copy` — never generated, byte-copied; `generate · exists` — writer reproduces factory bytes and/or writes a new file; `generate · partial` — writer covers only a slice (rename, one section, re-encode); `generate · none` — no writer |
| **Offline** | `L1` = `tools/cardcheck.py`; `L2` = `tools/l2check.py`; `tool` = a named tool plus its `--selftest`/real-sample run; `synthetic` = synthetic fixture only; `claim` = decoded outside the repo, not reproducible from a committed tool |
| **Reader** | `located` + VA + M3 task; `partial` = load/path located but not the record walk; `unlocated` + M3 task; `not needed` = copy-only, no format consumption |
| **L3** | a `targets.json` name with `blocked`/`synthetic`, or `planned` = an M9 task with no `targets.json` entry yet, or `—` |
| **L3 result** | `BLOCKED (4)` = the runner exits 4 and claims nothing; `—` = never run |
| **F4** | full `Navi.exe` on a generated card, `M8.E4`; every row is `—` until that EXP exists |

No cell below is a hardware result. The verification ladder stops at L2–L4
(firmware fragments/emulator where available);
the car is L5 (bench/car) and has not run (`docs/research/card-test-plan.md`).

## Matrix

| # | File type / path | Gen | Format doc | Offline proof | Firmware reader (M3) | L3 target (M9) | L3 result | F4 (M8.E4) | Cross-year / market | Evidence (claims, EXPs) | Next action |
| --: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Card image: MBR + FAT32 + firmware area + TFAT16 tail | generate · exists — `tools/mkcard.py` (full rebuild) and `tools/imgpatch.py` (in-place patch) | [sd-card-layout](../format/sd-card-layout.md) | `L1 --image`; `mkcard --selftest`; unchanged tree byte-identical | not a file reader; media-mount state machine `0x00419ca0` (M3.10) | M9.16 planned | — | — | 2011/2014/2016 L1 pass; 2019 QY8x unsupported | C-001–C-004, C-148, C-166, C-1910–C-1918, C-2020–C-2029; EXP-M5.10, EXP-M5.13, EXP-30 | M5.13b |
| 2 | Common 512-byte header (all map files) | generate · exists — copied by every writer; checked by `tools/header_block.py` | [file-header](../format/file-header.md) | `L1` magic; `header_block.py check`; 37/37 synthetic | no semantic check located; `MMAIN001` reader copies `0x1000` and byte-swaps, no label compare (M3.8) | — (covered by per-file rows) | — | — | `BICON001` carries a different data version; US/EU format family identical | C-010, C-011, C-025, C-167, C-548–C-553, C-1781–C-1789; EXP-H8, EXP-M3.8 | M5.6 |
| 3 | `MMAIN001.DAT` | generate · exists — `tools/mmain.py` | [drstr §MMAIN](../format/drstr.md#mmain001dat--the-4-kib-database-header) | `L1` level totals; `mmain.py` round-trip `240e7c97…` | located `0x0041a438` (open `0x0041b780`, read `0x0041b954`); exactly `0x1000` bytes, no label/count check (M3.8) | no target — gap (see G1) | — | — | record counts change with the tile set; US 2011 same class | C-037, C-164, C-550, C-1720–C-1724, C-1780–C-1789, C-1890, C-1026; EXP-M3.8, EXP-H8 | M5.6 |
| 4 | `DRSTR001.DAT` | generate · exists — `drstr_ze0.build` | [drstr](../format/drstr.md) | `L1` tree check; `L2` `drstr_rebuild`; byte-identical EU 11,968 B / US 7,456 B | located `0x00419684` → parser `sub_00419350`; size/read checks, no `0x2f`/40/324 compare (M3.4, M3.10) | `drstr_parser` — blocked | BLOCKED (4) | — | US stores lowercase `ltntbl.dat` while the file is `LTNTBL.DAT`; 2014/2016 L2 pass | C-030–C-039, C-194, C-850–C-859, C-1860–C-1869, C-1982, C-2100–C-2101; EXP-M3.4, EXP-M3.10, EXP-M4.20, EXP-H6 | M9.14 |
| 5 | `CMP.LST` | copy — constant 19 bytes; no writer needed | [drstr §related](../format/drstr.md#related-files) | `L1` exact-content check | located `0x0041ba90`; `fopen`/`fclose` only, no read/compare (M3.10) | — (existence-only; L3 adds nothing) | — | — | content `\SystemSD\REFER001\`; US/EU unmeasured | C-035, C-1866, C-1869; EXP-M3.10 | M5.6 |
| 6 | `REFER001` container `.cmp` + `.ind` | generate · exists — `tools/cmpind_writer.py` (preserve/recompress) | [cmp-ind](../format/cmp-ind.md) | `L1` 194/194; `L2` preserved 194/194; writer fixtures | partial — chunk engine `fn 0x41c7e8` + zlib `0x542256`/`0x54233c`/`0x54220c` (M3.2b); no *static* caller found — an indirect call through a `.data` pointer (C-2128 refutes the "sec1 code" reading) | `cmp_ind_reader` — **not registered** (runner lacks firmware-call kind, M9.11b); firmware path **PASS** byte-identical on factory/S1/S2 + controls via `chunk_decoder_l3.py` (M9.11) | BLOCKED (4, target unregistered) | — | EU 194 pairs, US 58; zlib-ng reproduces 0/194; factory inner pages reproducible by stock zlib L6/m8 (M1.13) | C-020–C-029, C-190–C-195, C-505–C-506, C-820–C-839, C-330, C-2060–C-2066, C-2150–C-2156, C-2570–C-2575; EXP-06, EXP-M3.1, EXP-M3.2, EXP-M3.2b, EXP-M9.11, EXP-M1.13 | M9.11b, M3.2b |
| 7 | `REFER001/COORD001` | **copy** for EU-base Poland (M3.17, G6: EU region set covers shard 021); generate only for a non-EU region set (layout known, no writer) | [coord-zcode-icode](../format/coord-zcode-icode.md) | `L1`/`L2` pair only; `coord.py` grid fit; no file writer | unlocated — M3.14 blocked on M1.2f (EXP-2026-11-08-M3.14-reader-layout) | M9.15 planned | — | — | 33 region boxes in `REFER001`; `REFER002/COORD001` has 15 | C-110, C-111, C-053, C-152, C-960, C-2228; EXP-M4.8, EXP-2026-11-08-M3.17 | M3.14 |
| 8 | `REFER001/ZCODE0nn` | **copy** for EU-base Poland (M3.17, G6: EU shard set kept); generate only for a non-EU region set | [coord-zcode-icode](../format/coord-zcode-icode.md) | `L1`/`L2` pair only; field decode is claim-only (no repo tool) | unlocated — M3.14 blocked on M1.2f (EXP-2026-11-08-M3.14-reader-layout) | M9.15 planned | — | — | 33 shards in the EU set; US shard set unmeasured | C-112, C-113, C-131, C-2228; EXP (ZCODE walk, not committed), EXP-2026-11-08-M3.17 | M3.14 |
| 9 | `REFER001/ICODE001` | **copy** for EU-base Poland (M3.17, G6: EU region set kept); generate only for a non-EU region set | [coord-zcode-icode](../format/coord-zcode-icode.md) | `L1`/`L2` pair only; field decode is claim-only | unlocated — M3.14 blocked on M1.2f (EXP-2026-11-08-M3.14-reader-layout) | M9.15 planned | — | — | `REFER002/ICODE001` appears from 2013 | C-114, C-115, C-122, C-1025, C-2228; EXP-M4.14, EXP-2026-11-08-M3.17 | M3.14 |
| 10 | `REFER001/POINT0nn` | generate · partial — `mutate_refer_poi.py` renames only; no page builder | [refer §POINT](../format/refer.md#point0nn--pois) | `L1`/`L2` pair; `L2` same- and different-length rename checks; `scan_refer_names.py` | walk located — `fn 0x003f5194(page, n)` (C-2540), access path `0x003fbed8`/`0x0040b358`/`0x004125a8`; name accessor open (M3.11c, lead `0x003d1150`) | walk runs on the US page in PySh4-LE (`point_walk_l3.py walk`, C-2541); `poi_record_decode` name check — M9.10 after M3.11c | — | — | rename framing holds 2011/2014/2016; US shard set differs | C-132–C-135, C-145, C-146, C-150–C-152, C-210–C-212, C-952–C-957, C-2120–C-2124, C-2540–C-2545; EXP-M4.7, EXP-M5.12, EXP-M3.11, EXP-M3.11-2 | M3.11c, M3.11b, M9.21 |
| 11 | `REFER001/ADDRE0nn` | generate · none | [refer §ADDRE](../format/refer.md#addre0nn--addresses) | `L1`/`L2` pair; `addre.py verify` 3 shards; 6-byte cells/TOC verified | partial — M3.13: access path + `fn 0x003f56bc` 0xc000-class header gate (C-973 tag-class); full token/grammar mapping open | M9.15 planned | — | — | 33 shards; US 11; street-name resize still UNKNOWN; 0xd53500→ADDRE binding HYP | C-153–C-156, C-970–C-979, C-1960–C-1969, C-957, C-2180–C-2187; EXP-M4.9, EXP-M4.19, EXP-M3.13-2 | M3.13 (partial) |
| 12 | `REFER001/INTER0nn` | generate · none | [refer §INTER](../format/refer.md#inter0nn--intersections) | `L1`/`L2` pair only; table decode is claim-only | access path confirmed, content reader unlocated (M3.16 blocked, 2 sig families 0 hits) | no target — gap (see G2) | shared REFER001 `0x14e8`/`fn 0x004125a8`/`fn 0x003fbed8`/`fn 0x0040b358` (C-2210); content fields UNKNOWN | — | 33 shards; `FRWAY` only 24 | C-135, C-140, C-1810–C-1812, C-2210–C-2214; EXP-M4.16, EXP-M3.16-r2 | M3.16 blocked |
| 13 | `REFER001/FRWAY0nn` | generate · none | [refer §FRWAY](../format/refer.md#frway0nn--freewaysroutes) | `L1`/`L2` pair only; table decode is claim-only | access path confirmed, content reader unlocated (M3.16 blocked, 2 sig families 0 hits) | no target — gap (see G2) | shared REFER001 `0x14e8`/`fn 0x004125a8`/`fn 0x003fbed8`/`fn 0x0040b358` (C-2210); content fields UNKNOWN | — | 24 shards vs 33 for other families | C-140, C-1810–C-1812, C-2210–C-2214; EXP-M4.16, EXP-M3.16-r2 | M3.16 blocked |
| 14 | `REFER001/ICADM0nn` | generate · none | [refer §ICADM](../format/refer.md#icadm0nn--administrative-country-data) | `L1`/`L2` pair only; field decode is claim-only | unlocated — no M3 task (see G2) | no target — gap (see G2) | — | — | 33 blocks; country terms verified | C-136, C-1799 | M3.18 |
| 15 | `REFER001/ZIPFR001` | generate · none | [refer §ZIPFR](../format/refer.md#zipfr001--postalfreeway-masks) | `L1`/`L2` pair only; field decode is claim-only | unlocated — no M3 task (see G2) | no target — gap (see G2) | — | — | 36,881 records, 119 masks; cross-year unmeasured | C-137 | M3.18 |
| 16 | `REFER001/INDEX003.DAT` | **absent on the EU 2011 and US 2011 stock images** (no FAT entry, no `DRSTR` entry) — nothing to generate or copy for those cards | [refer](../format/refer.md) (M3.12: no section, the file is not on these cards) | FAT/`DRSTR` census (`mkcard`, `drstr_ze0`) | load `0x004125a8` / string `0x0017a118`; the file it names is missing, so the path is conditional (M3.12) | no target — nothing to read | — | — | absent EU/US 2011; other versions unknown | C-880, C-2130–C-2134; EXP-M3.7, EXP-M3.12 | — (re-open only with an image that ships it) |
| 17 | `MAPAL001/BxxRyyR.DAT` container, level/box tables, section 1 roads | generate · partial — `tools/tilewriter.py` splices roads into a factory tile (one `0x2046` dir, level 1, provisional classes) | [map-tiles](../format/map-tiles.md) | `L2` five factory tiles byte-identical; `tilewriter` 48/48 synthetic; real-tile L2 **PASS (structural, no golden, DRSTR rebuilt)** on EU 2011 `B48R058R` (M5.4) | partial: VAs `0x0041f26c`, `0x004259bc`, `0x0042757a` (M3.5); no runnable entry | `tile_reader` — blocked; M9.13 planned | BLOCKED (4) | — | 2011/2014/2016 `B30R048R` identical; QY8x 2019 differs (52 tiles, layer 11); B30R048R rebuild assertion explained (M9.22) | C-050–C-053, C-120–C-129, C-171, C-250–C-256, C-860–C-869, C-943–C-944, C-1060–C-1066, C-2630–C-2639; EXP-04, EXP-12, EXP-M4.6, EXP-M5.4, EXP-M9.22 | M5.22, M5.23, M5.3, M5.6, M9.13 |
| 18 | `MAPAL001` tile section 2 (router graph) | copy — always preserved verbatim | [map-tiles](../format/map-tiles.md) | `L2` `tile_roundtrip` byte-identical; graph records not decoded | unlocated — M3.6 (which sections the renderer reads) | `tile_reader` — blocked; M9.13 planned | BLOCKED (4) | — | 2011/2014/2016 preserved; graph grammar unknown | C-998, C-923; EXP-M4.11, EXP-M4.4 | M3.6 |
| 19 | `MAPAL001` tile section 4 (admin/place-name index) | generate · partial — `section4.py preserve` verified; `build` refuses (exit 3); `sec4_write.py` unverified | [map-tiles §section 4](../format/map-tiles.md#section-4-road-names-and-streaming) | `L2` tile mutation with section 4 verbatim; payload hashes | unlocated — M3.6 (section 4 especially) | `tile_reader` — blocked; M9.13 planned | BLOCKED (4) | — | records/names 20/68, 24/126, 24/129 (2011/2014/2016) | C-126, C-546–C-547, C-920–C-929; EXP-M4.4 | M3.6; then see G3 |
| 20 | `MAPAL001/LEV3456R.DAT` | generate · partial — `tools/lev3456.py` re-encodes levels 3–6; no OSM writer | [map-tiles §LEV3456R](../format/map-tiles.md#lev3456rdat-coarse-levels-35) | `L2` byte-identical; `lev3456.py verify` + `cmp` silent (level 5 whole file) | partial: filename load `0x0040a014`/`0x0040a022` (M3.4); content reader unlocated — M3.6 | `tile_reader` covers `BxxRyyR` only — gap (see G8) | — | — | whole-database directory shape; 2014/2016 unmeasured | C-852, C-990–C-999, C-256; EXP-M4.11 | propose M5.16 (see G4) |
| 21 | `RDSTM001/RDSTM001.DAT` | **generate** for Poland/target region (M3.17: 12 TMC location fields, region-specific; no speed/one-way; record framing unresolved) | [rdstm](../format/rdstm.md) | `L1` header; `rdstm_record.py` 10-row round-trip; `rdstm_scan`/`schema`; no writer | located `0x003bc960` decoder, 12 getters, `0x003f61bc` field directory (M3.7) | no target — gap (see G2) | — | — | EU uses `TMC`; US uses `XMD` instead | C-104–C-106, C-880–C-889, C-1800–C-1812, C-070, C-2226; EXP-M3.7, EXP-M4.1, EXP-M4.15, EXP-M4.16, EXP-2026-11-08-M3.17 | M5.19 (after M4.16b) |
| 22 | `RDSTM001/LCTBL001.DAT` | **generate** for Poland/target region (M3.17: regional name DB; `lctbl_records.py` re-encodes records but no file/catalog builder) | [rdstm §LCTBL](../format/rdstm.md#lctbl001dat--catalog--compressed-name-database) | `L1` tree/header; `lctbl_records verify` all 517 streams; `lctbl_names verify`; no full-file rebuild | partial: load `0x004125a8`; record walk unlocated — M3.15 | M9.15 planned | — | — | 2011/2014/2016 framing identical, counts grow; US DRSTR name lowercase | C-880, C-1790–C-1799, C-1830–C-1839, C-2227; EXP-M3.7, EXP-M3.9, EXP-M4.18, EXP-2026-11-08-M3.17 | M5.17 (after M3.15) |
| 23 | `VER_INFO/HDD_INFO.TXT` (+ `0x06000000` copy) | generate · exists — `tools/hddinfo.py`; `mkcard.py` writes the image copy | [validation §HDD_INFO](../format/validation.md#hdd_infoTXT-text-layout-m21m23-verified-static) | `L1` 6 lines, ASCII, label match, image copy; `hddinfo.py` byte-identical round-trip | reader `0x004e7b8c` located (M2.1); comparator `0x03bd2ad8`/`0x03bd2ecc` located but runtime COM/unit state | `hddinfo_compare` — blocked; M9.6 ready: both checks byte-specified (M2.15) | BLOCKED (4) | — | US line 1 `QSD-301-100`, `SDC08-EVNAM`, label `QSD-301-103`; EU values differ | C-005, C-074, C-721–C-728, C-740–C-749, C-766, C-1710–C-1711, C-1770–C-1779, C-2080–C-2087; EXP-M2.1, M2.3, M2.5, M2.11, M2.15 | M9.6 (then M2.4) |
| 24 | `REFER002/*` (16 files, EV layer) | **copy** (EU-base, market-correct EU `REFER002`; M3.17). Cross-market: never copy US `REFER002` to EU/Poland — replace with EU; do **not** empty/omit without reader evidence (EV schema xy/plug/parking undecoded) | [refer §REFER002](../format/refer.md) | `L1` census; format decode is claim-only; no writer | not needed for copy; schema `OBSERVED`, no reader task | — | — | — | 15 POINT shards (2011) → 29 (2016); `ICODE001` from 2013 | C-138, C-143, C-152, C-156, C-1025, C-2224, C-2225; EXP-M4.14, EXP-2026-11-08-M3.17 | — (M3.17 done; cross-market recipe is a follow-up) |
| 25 | `BICON001/BICON001.DAT` | **copy** (verbatim; M3.17: vendor icon asset, no region-specific map content) | [assets §BICON](../format/assets.md#bicon001bicon001dat--poi-icons) | `L1` header; `poi_icons.py bicon` 103 icons | not needed for map correctness (icon display) | — | — | — | data version differs on 2011 but equals MMAIN on 2014/2016 (C-2497) | C-213, C-980–C-989, C-167, C-2220; EXP-M4.10, EXP-2026-11-08-M3.17 | — (M3.17 done) |
| 26 | `OPNG/*` | **copy** (verbatim; M3.17: vendor image assets, not map data) | [assets §OPNG](../format/assets.md#opng--images) | `L1` census; no parser | not needed | — | — | — | 2016 sample carries `OIXXEVNI.001`; US unmeasured | C-2221; `assets.md`; EXP-2026-11-08-M3.17 | — (M3.17 done) |
| 27 | `SPEECH/<lang>/…` | **copy** (verbatim EU set; M3.17: voice assets, out of map-compiler scope). EU 2011 base has no `PL`; adding Polish voice is an asset task, not map data | [assets §SPEECH](../format/assets.md#speech--voice-prompts) | `L1` census; archive shape `OBSERVED`; no parser | not needed | — | — | — | language sets grow in 2014/2016 (EU 2011 has 7 langs, no PL) | C-1027, C-2222; EXP-M4.14, EXP-2026-11-08-M3.17 | — (M3.17 done; PL voice is a separate asset follow-up) |
| 28 | `TMC/reception.dat` (EU) / `XMD/*` (US) | **copy** (market-correct; M3.17: EU-base Poland uses EU `TMC/reception.dat`). Cross-market: use the target market's traffic dir (`TMC`↔`XMD`), not a blind copy | [data-coverage §traffic](data-coverage.md) | `L1` census; no parser | not needed | — | — | — | EU `TMC` vs US `XMD` (C-070); content undecoded | C-070, C-2223; EXP (image matrix), EXP-2026-11-08-M3.17 | — (M3.17 done) |
| 29 | `TFTBL001/*` (2014+ only) | copy when present; not generated for 2011 | [image-versions](image-versions.md) | `L1` warns; no parser | not needed for 2011; function unknown | — | — | — | absent in 2011; present 2014/2016 | C-122, C-1027; OQ-31, OQ-36 | M3.17 |
| 30 | US `XMD/LTNTBL.DAT` (DRSTR stores `ltntbl.dat`) | copy | [drstr](../format/drstr.md) | `L2`/`drstr_ze0.build` case-insensitive rebuild byte-identical | not needed | — | — | — | only the US card; EU stores `LCTBL001.DAT` | C-1982, C-2100–C-2101; EXP-M4.20 | M5.6 |

**Row count: 30.** Of these, 21 are generated (a writer exists or is missing)
and 9 are copy-only (`CMP.LST`, tile section 2, `REFER002`, `BICON001`,
`OPNG`, `SPEECH`, `TMC`, `TFTBL001`, and the US `LTNTBL` spelling); the
per-status counts are in
[EXP-2026-11-06-H11](../experiments/EXP-2026-11-06-H11-reader-coverage.md).

## Unlocated readers

Rows where the record-walking reader has no VA (a load/path anchor does not
count as a reader):

| Family | What is missing | Task |
| --- | --- | --- |
| `.cmp`/`.ind` chunk reader | the caller of `inflate` that loops over `chunk_offset[]` | M3.2b |
| `COORD001` | the table reader | M3.14 |
| `ZCODE0nn` | the trie/leaf reader | M3.14 |
| `ICODE001` | the schema/name reader | M3.14 |
| `POINT0nn` | the name copy (walk found: `0x003f5194`) | M3.11c |
| `ADDRE0nn` | the directory/cell/record readers | M3.13 |
| `INTER0nn` | the 12-byte table and blob readers | M3.16 |
| `FRWAY0nn` | the table and route-ref readers | M3.16 |
| `ICADM0nn` | no M3 task at all | M3.18 (G2) |
| `ZIPFR001` | no M3 task at all | M3.18 (G2) |
| `INDEX003.DAT` | record layout and its consumer | M3.12 |
| Tile section 1/2/4 | which sections the renderer reads; section-4 consumer especially | M3.6 |
| `LEV3456R.DAT` content | reader beyond the filename load | M3.6 |
| `LCTBL001.DAT` | the record walk and name decode | M3.15 |
| `MMAIN001.DAT` | **not** unlocated: `0x0041a438` reads it, but no L3 target exists | M9.17 (G1) |
| `RDSTM001.DAT` | **not** unlocated: `0x003bc960` + `0x003f61bc` are located, but no L3 target exists | proposed G2 |

`HDD_INFO.TXT`, `DRSTR001.DAT` and `CMP.LST` have located readers; their L3
targets are blocked on engine/corpus work, not on address discovery.

**Why the reader list is long, and why it is not compression (corrected
2026-11-08).** M3.11, M3.13 and M3.2b each searched "every uncompressed
section", found the access path and not the record walker, and concluded that
the walker hides in `Navi.exe` sec1. C-2128/C-2129 refute that: build A has
**0 compressed executable sections** (22.8 MB of code, all readable); the 245
compressed sections (30.2 MB) are `.data`. The walker is `fn 0x003f5194` in
`sec0` and runs in L3 on the real US page.

| Measure (measured 2026-11-08, `cerom.py memmap --json`) | Value |
| --- | --- |
| Executable section bytes, build A | 22,767,466 B, **0 compressed** |
| All section bytes / compressed | 53,725,980 B / 30,212,810 B (`.data`) |
| Modules with a compressed section | 133 / 149 (data only) |

So a "not found" verdict here means the **signature** was wrong — M3.11's did
not test the packed `u16` the code actually uses. Rule 14 now asks for the
signature and its source, and the reopened tasks (M3.2b, M3.13, M3.14–M3.16,
M3.18) carry that requirement.

## L3 targets and what they actually prove

`tools/l3_harness/targets.json` currently has six entries. Only one is
runnable, and it is a pipeline fixture, not a firmware reader.

| Target | Kind | Reader | Corpus | Result | Matrix rows |
| --- | --- | --- | --- | --- | --- |
| `probe-zlib-cmf` | synthetic | `synthetic` | `REFER001/ADDRE001.DAT.cmp` | ACCEPT (pipeline only) | row 6 note only |
| `hddinfo_compare` | blocked | `hdd_info` | `VER_INFO/HDD_INFO.TXT` | BLOCKED (4) | 23 |
| `cmp_ind_reader` | blocked | `cmp_ind` | `REFER001/ADDRE001.DAT.cmp` | BLOCKED (4) | 6 |
| `tile_reader` | blocked | `tile` | `MAPAL001/B28R070R.DAT` | BLOCKED (4) | 17, 18, 19 |
| `drstr_parser` | blocked | `drstr` | `DRSTR001.DAT` | BLOCKED (4) | 4 |
| `mapcode_comparator` | blocked (retired) | `hdd_info` | HDD_INFO variant | BLOCKED (4) | 23 — must never be revived |

No row may say "read by firmware" on the strength of `probe-zlib-cmf`; the
target notes say so explicitly. The retired comparator chain
`0x6fab2c → 0x6faeb0 → 0x6fb05c` is `BT_MGR.dll` code (C-520, C-528) and is
kept blocked on purpose.

## Gaps: reader and L3 tasks that do not exist yet

H11's brief owns this document, the roadmap/README link lines and its own EXP
only; it does **not** edit `TODO.md`. H12 (fifth PM pass, 2026-11-06) inserted
the gaps below as real tasks and re-issued the claim blocks, because H11's
proposal handed G1 `C-2290–C-2299` while M8.E1b took that block first. The IDs
below are the ones now in `TODO.md`.

| Gap | Task | Scope | Claim block |
| --- | --- | --- | --- |
| G1 | **M9.17** — L3 `mmain_reader` target | run `0x0041a438` on the factory `MMAIN001.DAT` and on a rebuilt header; record the `0x1000` read and the absence of a label/count check | C-2370–C-2379 |
| G2 | **M3.18** — `ICADM`/`ZIPFR` readers | the two families with no M3 task; an L3 target for `INDEX003`, `INTER`, `FRWAY`, `RDSTM` follows under M9.15 | C-2380–C-2389 |
| G3 | **M4.21** — tile section-4 writer | turn `section4.py build` from "refuses" into a writer for a changed parcel set (C-929); needs the M3.6 consumer answer | C-2390–C-2399 |
| G4 | **M5.16** — `LEV3456R` generator | OSM → levels 3–5 writer; `lev3456.py` can already re-encode factory records, but the whole-database rebuild (44/11 columns) is unproven on 2014/2016 | C-2400–C-2409 |
| G5 | **M5.17** — `LCTBL001` writer | file-level builder (catalog + 500-record pages) after M3.15; `lctbl_records.py` only re-encodes streams | C-2410–C-2419 |
| G6 | **M5.18** — `POINT`/`ADDRE` writers | narrowed by H12: the region tables (`COORD`/`ZCODE`/`ICODE`) are copy-eligible for Poland (M3.17), so only the POI and address layers must be generated; `ADDRE` is the hard one (C-957) | C-2420–C-2429 |
| G7 | **M5.19** — `RDSTM001` writer | only after M4.16b resolves the per-record field directory; must carry the twelve TMC fields (C-889) | C-2430–C-2439 |
| G8 | **M9.18** — L3 targets for `LEV3456R` and tile sections | extend `tile_reader` beyond `B28R070R`; add the section-4 consumer once M3.6 names it (H11's EXP says `M9.18` in its conclusion and `M9.19` in its table; the ID used is **M9.18**) | C-2440–C-2449 |

G1/G2 are reader/L3 gaps; G3–G7 are writer gaps. G8 is the missing coverage for
rows 18–20.

## Notes on the card image (rows 1 and 6)

The image has two writers with different jobs. `mkcard.py` rebuilds the FAT32
partition from a tree (the compiler path; byte-identical on an unchanged tree;
a minimal-diff mode is M5.20). `imgpatch.py` writes one file into its existing
cluster chain, so a test card differs from the factory in exactly that file
(M5.13). `imgpatch.py` is verified on a synthetic fixture only — C-2027 stays
`UNKNOWN` until **M5.13b** builds the S1 and S2 images.

## How to keep this current

1. **Same PR rule.** A task that changes a writer, a reader VA, an L3 target or
   a corpus updates the matching row here in the same commit. A row change is
   part of that task's "Done when", not a follow-up.
2. **Promotion rule.** A reader cell may say `located` only with a claim ID and
   an EXP that gives the VA and the call path; an L3 cell may say `PASS/REJECT`
   only from a `runner.py run` verdict with the stub log in an EXP; a row may
   say "read by firmware" only when both exist. Otherwise use `partial`,
   `unlocated`, `BLOCKED` or `—`.
3. **New file family = new row.** Do not fold a new file type into "other";
   add it with mode, format doc, writer, offline proof, reader and L3.
4. **Copy set changes only with evidence.** Moving a file from `generate` to
   `copy` (or back) needs a claim and an EXP, because M5.6 and M3.17 depend on
   it.
5. **Freshness check.** At the start of any M5/M9 task run
   `python3 tools/claims_check.py` and `python3 tools/selftest.py`; at the end
   compare this page's row count and unlocated list with the current
   `targets.json` and `TODO.md`. H11 owns the refresh; a stale matrix is a bug.

## Sources and evidence key

Claim IDs refer to [`claims.md`](claims.md). This page adds no claim; the H11
block `C-2170–C-2179` is intentionally unused because `claims.md` is
read-only for this task.

| Short | Experiment record |
| --- | --- |
| EXP-04 | [`EXP-2026-11-05-04-tile-roundtrip`](../experiments/EXP-2026-11-05-04-tile-roundtrip.md) |
| EXP-06 | [`EXP-2026-11-05-06-cmp-writer`](../experiments/EXP-2026-11-05-06-cmp-writer.md) |
| EXP-12 | [`EXP-2026-11-05-12-tile-dense-roads`](../experiments/EXP-2026-11-05-12-tile-dense-roads.md) |
| EXP-29 | [`EXP-2026-11-05-29-l1-l2-validators`](../experiments/EXP-2026-11-05-29-l1-l2-validators.md) |
| EXP-30 | [`EXP-2026-11-05-30-image-matrix`](../experiments/EXP-2026-11-05-30-image-matrix.md) |
| EXP-M2.1 | [`EXP-2026-11-06-M2.1-hddinfo-fn-complete`](../experiments/EXP-2026-11-06-M2.1-hddinfo-fn-complete.md) |
| EXP-M2.3 | [`EXP-2026-11-06-M2.3-hddinfo-fields`](../experiments/EXP-2026-11-06-M2.3-hddinfo-fields.md) |
| EXP-M2.5 | [`EXP-2026-11-06-M2.5-different-map-code`](../experiments/EXP-2026-11-06-M2.5-different-map-code.md) |
| EXP-M2.11 | [`EXP-2026-11-06-M2.11-hddinfo-trigger`](../experiments/EXP-2026-11-06-M2.11-hddinfo-trigger.md) |
| EXP-M3.1 | [`EXP-2026-11-06-M3.1-ind-wrapper`](../experiments/EXP-2026-11-06-M3.1-ind-wrapper.md) |
| EXP-M3.2 | [`EXP-2026-11-06-M3.2-ind-handling`](../experiments/EXP-2026-11-06-M3.2-ind-handling.md) |
| EXP-M3.4 | [`EXP-2026-11-06-M3.4-drstr-parser`](../experiments/EXP-2026-11-06-M3.4-drstr-parser.md) |
| EXP-M3.5 | [`EXP-2026-11-06-M3.5-tile-reader`](../experiments/EXP-2026-11-06-M3.5-tile-reader.md) |
| EXP-M3.7 | [`EXP-2026-11-06-M3.7-router-rdstm`](../experiments/EXP-2026-11-06-M3.7-router-rdstm.md) |
| EXP-M3.8 | [`EXP-2026-11-06-M3.8-mmain-read`](../experiments/EXP-2026-11-06-M3.8-mmain-read.md) |
| EXP-M3.9 | [`EXP-2026-11-06-M3.9-name-collation`](../experiments/EXP-2026-11-06-M3.9-name-collation.md) |
| EXP-M3.10 | [`EXP-2026-11-06-M3.10-drstr-cmplst-fns`](../experiments/EXP-2026-11-06-M3.10-drstr-cmplst-fns.md) |
| EXP-M4.4 | [`EXP-2026-11-06-M4.4-section4-road-edit`](../experiments/EXP-2026-11-06-M4.4-section4-road-edit.md) |
| EXP-M4.6 | [`EXP-2026-11-05-M4.6-b30r048r-diff`](../experiments/EXP-2026-11-05-M4.6-b30r048r-diff.md) |
| EXP-M4.7 | [`EXP-2026-11-06-M4.7-poi-rename-resize`](../experiments/EXP-2026-11-06-M4.7-poi-rename-resize.md) |
| EXP-M4.8 | [`EXP-2026-11-06-M4.8-coord`](../experiments/EXP-2026-11-06-M4.8-coord.md) |
| EXP-M4.9 | [`EXP-2026-11-06-M4.9-addre-grammar`](../experiments/EXP-2026-11-06-M4.9-addre-grammar.md) |
| EXP-M4.10 | [`EXP-2026-11-06-M4.10-poi-icons`](../experiments/EXP-2026-11-06-M4.10-poi-icons.md) |
| EXP-M4.11 | [`EXP-2026-11-06-M4.11-lev-coarse`](../experiments/EXP-2026-11-06-M4.11-lev-coarse.md) |
| EXP-M4.14 | [`EXP-2026-11-06-M4.14-cross-year-archive`](../experiments/EXP-2026-11-06-M4.14-cross-year-archive.md) |
| EXP-M4.16 | [`EXP-2026-11-06-M4.16-rdstm-placement`](../experiments/EXP-2026-11-06-M4.16-rdstm-placement.md) |
| EXP-M4.18 | [`EXP-2026-11-06-M4.18-lctbl-framing`](../experiments/EXP-2026-11-06-M4.18-lctbl-framing.md) |
| EXP-M4.19 | [`EXP-2026-11-06-M4.19-addre-point-coords`](../experiments/EXP-2026-11-06-M4.19-addre-point-coords.md) |
| EXP-M4.20 | [`EXP-2026-11-06-M4.20-us-drstr-roundtrip`](../experiments/EXP-2026-11-06-M4.20-us-drstr-roundtrip.md) |
| EXP-M5.4 | [`EXP-2026-11-06-M5.4-tilewriter`](../experiments/EXP-2026-11-06-M5.4-tilewriter.md) |
| EXP-M5.10 | [`EXP-2026-11-06-M5.10-mkcard`](../experiments/EXP-2026-11-06-M5.10-mkcard.md) |
| EXP-M5.12 | [`EXP-2026-11-06-M5.12-us-poi-rename`](../experiments/EXP-2026-11-06-M5.12-us-poi-rename.md) |
| EXP-H6 | [`EXP-2026-11-06-H6-drstr-docs`](../experiments/EXP-2026-11-06-H6-drstr-docs.md) |
| EXP-H8 | [`EXP-2026-11-06-H8-mmain-fix`](../experiments/EXP-2026-11-06-H8-mmain-fix.md) |
| EXP-H11 | [`EXP-2026-11-06-H11-reader-coverage`](../experiments/EXP-2026-11-06-H11-reader-coverage.md) |
