# KIWI / Xanavi glossary (start)

Source: firmware strings of the pinned EU2011 `IMG256` (`92aa525d…a007f9`),
ROM A `0x200200`, plus the public `jharg/kiwiread` commit `74741c5b` used as a
field-name/chapter glossary only (GPL-3; no code copied). Evidence:
`EXP-2026-11-22-M4.64-kiwi-lineage` (C-7630–C-7636).

This page records **names the firmware itself uses**. It does not claim that
our card is a KIWI volume: M4.63, M4.69, M4.70 and M4.72 all found "common
vocabulary, different container".

| Term / string | Module, VA (EU2011 A) | Referencing code | Verdict |
| --- | --- | --- | --- |
| `XANAVI` | `Navi.exe` `0x0017abc8`; `NOT XANAVI` at `0x0017abc4` | no literal-pool xref found in executable sections | named in firmware, data-only |
| `xglXtpDrawXanaviCharacter` | `XGLDLL.dll` `0x03123b16` | not traced (font/draw module) | named in firmware |
| `MDP_draw`, `MDP_swin`, `MDP_ctrl`, `LOC_map`, `LOC_db`, `RAW_rec` | `Navi.exe` `0x00011190` (string table) | literal at `0x0032f4f4`, loaded at `0x0032f2e4`, function starting `0x0032efa8` (pdata START, length `0xa8c`) | named in firmware; the map-data tasks exist as code symbols |
| `MDP_pushRcvParcel`, `MDP_freeRcvParcel` | `Navi.exe` `0x00187f10`, `0x00187f78`, `0x00187f9f` | no literal-pool xref found | named in firmware, data-only |
| `Route Planning` | `Navi.exe` `0x000115c0` | no literal-pool xref found | named in firmware, data-only |
| `Multilink`, `Minimum Graphics`, `Display Class`, `Distribution Header` | not found in `Navi.exe` (ASCII or UTF-16) | — | not named in firmware |

The KIWI chapter titles quoted by `kiwiread` are **parcel**, **level**, **block
set**, **block**, **management record**, **distribution header**, **multilink**,
**display class**, **minimum graphics**, **name data**, **route planning**,
**route guidance**, **integrated information**. Only the generic words `Parcel`,
`Level`, `Block` and the phrase `Route Planning` occur in `Navi.exe`, usually as
parts of unrelated diagnostics; `Multilink`, `Minimum Graphics`, `Display Class`
and `Distribution Header` do not. So the lineage hypothesis keeps its *names*
but gets no structural confirmation from this vocabulary scan.

## M4.78 verdict: is KIWI a shortcut?

No. Across eleven KIWI family probes (M4.63–M4.73) exactly **one** byte-level
structure is adopted: the ch.1.2 `SWS` size word, already named in our format
docs (C-7651/C-7652). Three families give concept/name vocabulary only, and six
are unrelated. The public `kiwiread` reader (GPL-3, commit `74741c5b`) is a
field-name and chapter-number glossary, **not** a reader for ZE0 bytes. Every
number below is printed by the cited EXP's command; no GPL code and no vendor
bytes were copied. Rule 13 is unchanged: none of this confirms a firmware
reader VA or an L3/L4 run.

### Term → our name → file / offset → status

| KIWI term (chapter) | Our name | Our file / offset | Status |
| --- | --- | --- | --- |
| `SWS` size word (1.2) | `u16` size word (bytes = word × 2) | `docs/format/map-tiles.md:255,266,388`: tile directory header word 0 at `0x000`; slot `(ln, X)` pairs | ADOPT — informative fits on both cards (C-7651, C-7652) |
| `D` offset word (1.2) | `u32` byte offset | `.ind` `chunk_offset[]`, `DRSTR001` `listing_offset` (`docs/format/cmp-ind.md`, `docs/format/drstr.md`) | UNRELATED — 0 informative fits (C-7653, C-7654, C-7658) |
| `sectoraddress_t` / `getsector` (1.2.7) | slot tag `(tag>>8)*2048 + (tag&0xff)*256` | tile slot u32 address | UNRELATED — 24-bit sector + 6-bit word vs 16-bit sector + 8-bit page (C-7653) |
| `pid_t`, `geonum_t` (1.2.13) | tile grid + POI fine word | `docs/format/coord-zcode-icode.md` | UNRELATED — grid arithmetic compatible, not a coordinate rule (C-7670–C-7674) |
| `datavol_t` (5.1) | 512-byte common header | `docs/format/file-header.md`: `0x000..0x1ff` | UNRELATED — printable run 1 vs ≥8 on 3/3 files |
| management-header `mhr_t` / `dde[]` (5.1) | `DRSTR001` 40-B nodes + 32-B entries | `docs/format/drstr.md` | UNRELATED — 0/34 plausible names on 3/3 files |
| `pdmdh_t` distribution header (6.1) | coverage box + level descriptor | `MMAIN001 0x184`, tile `0x1ac` | UNRELATED — geonum 143.922° outside frame |
| `lmr_t` level management (6.1.1) | level rows `(level, kind, count u16)` | `MMAIN001 0x1ac`, tile `0x1ac` | UNRELATED — `lvl=0`, display word `0x6800001`, parcel count 145 |
| `bsmr_t` / `bmt_t` block management (6.1.2 / 6.2.1) | no counterpart; `nlmr=nbsmr=16191` constant | — | UNRELATED — absent |
| `roadhdr_t` / `dcmr_t` / `multilink_t` (7.2) | 22-word road record header | `docs/format/map-tiles.md:548-568` | UNRELATED — 0/6,000 records fit (C-7680) |
| `mingr_t` minimum graphics (7.3.2.2.1) | ZE0 background shape | `docs/format/map-tiles.md:570-587` | PARTIAL — concept only, 0/17,659 records fit |
| route planning (ch.10: node, link, cost) | section 2 node / link records | `docs/format/map-tiles.md` (section 2) | UNRELATED — no field named; r=0.1035/0.0363 |
| route guidance (8.4: toward/road/intersection names) | section 4 signpost, `INTER0nn` / `FRWAY0nn` | `docs/format/refer.md`, tile section 4 | PARTIAL — concept only (C-7720–C-7724) |
| map task names (`MDP_*`, `LOC_map`, `RcvParcel`, `XANAVI`) | same names in `Navi.exe` / `XGLDLL.dll` | firmware string table | PARTIAL — names only, no reader VA (C-7630–C-7636) |

### Decision table per family (machine-checked)

This table is the input contract of `tools/kiwi_verdict_check.py`; its
`--selftest` rejects a flipped verdict, a corrupted informative count and a
zero/sentinel-only row relabelled `adopt`. Run the checker after any edit:

```bash
python3 tools/kiwi_verdict_check.py docs/format/kiwi-glossary.md
```

| Family | Our name | File / offset | EU informative | US informative | Evidence note | Verdict | EXP / claims |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Basic types — SWS size word | Directory header word 0 / slot (ln, X) | docs/format/map-tiles.md:255,266,388; tile 0x000 / slot pairs | 4854/4854 | 4292/4292 | informative SWS fits; also dir 24/24 EU, 16/16 US | adopt | C-7651, C-7652; EXP-M4.66 |
| Basic types — D / sector address | .ind chunk_offset[], DRSTR listing_offset | docs/format/cmp-ind.md, docs/format/drstr.md | 0/300 | 0/269 | zero/sentinel-only raw fits 41/341 EU, 35/304 US; ZE0 sector+page | unrelated | C-7653, C-7654, C-7658; EXP-M4.66 |
| Volume / management headers (5.x, 6.1) | common header, MMAIN/tile 0x184, 0x1ac | docs/format/file-header.md, docs/format/map-tiles.md | 0/4 | 0/4 | 0/4 KIWI grammar checks on 3 files; geonum 143.922 outside frame | unrelated | EXP-M4.63, EXP-M4.67 |
| Level / block management (6.1.1, 6.1.2, 6.2.1) | MMAIN level totals, tile dirs | MMAIN001.DAT 0x1ac, tile 0x1ac | 0/4 | 0/4 | nlmr=nbsmr=16191 constant, not KIWI record counts; lvl=0 | unrelated | EXP-M4.67 |
| Parcel ID arithmetic (1.2.13) | tile grid, POI fine word | docs/format/coord-zcode-icode.md | 0 | 0 | grid-level arithmetic compatible; 15.625 arcsec unit not our fine step | unrelated | EXP-M4.68 |
| Road frame (7.2) | 22-word road record header | docs/format/map-tiles.md:548-568 | 0/3000 | 0/3000 | distribution header size word fails on 6,000 records on two cards | unrelated | EXP-M4.69 |
| Background frame (7.3) | odd background records, ZE0 shapes | docs/format/map-tiles.md:570-587 | 0/1416 | 0/12220 | concept-only: shared 11-bit count and i8 deltas; ZE0 shape one word shorter | partial | EXP-M4.70 |
| Route planning (ch.10) | section 2 node / link records | docs/format/map-tiles.md (section 2) | 0 | 0 | no field named; r=0.1035/0.0363 under 0.8; ch.10 names reference only | unrelated | EXP-M4.72 |
| Route guidance (8.4) | section 4 signpost, INTER/FRWAY shards | docs/format/refer.md, tile section 4 | 0 | 0 | concept-only: field kinds predicted, ZE0 stores verbatim text keyed by mesh | partial | EXP-M4.73 |
| Firmware vocabulary | Navi.exe string table, XGLDLL.dll symbol | docs/format/kiwi-glossary.md (firmware table) | 0 | 0 | concept-only: MDP_*/XANAVI/RcvParcel in ROM A; KIWI chapter terms absent | partial | EXP-M4.64 |

Counts: 1 adopt / 3 partial / 6 unrelated. The rule is strict: a zero or
sentinel-only raw fit (41/341, 35/304, 194/36581, 58/57152) is **not** an
adopt; `adopt` needs informative fits on **both** cards.

### Negative with controls (the falsifier did not fire)

The task's falsifier was "every family ends as unrelated". It did not fire:
the SWS family is adopted with informative non-degenerate fits on both cards.
The six `unrelated` families are still recorded as a first-class negative,
each with a synthetic KIWI *positive control* that passed (e.g.
`kiwi_probe.py --selftest`: 4 header positives, 4 negatives, road/shape ±1;
`kiwi_bg_probe.py --selftest`: synthetic KIWI frame FIT, 3 mutations REJECT;
`kiwi_road_probe.py`/`kiwi_route_concepts.py --selftest` pass), a ZE0-side
rebuild control (`harness.py verify B30R048R`: byte-identical 1,358,592 B,
`background rebuild ok 2958 bad 0`), and two independent cards (EU2011 and
US2011) with identical failure families. The real-KIWI-disc positive control
(M4.77, `ALLDATA.KWI`) is unavailable; a synthetic control cannot refute the
negative on real KIWI bytes.

### Follow-ups

The sole adopted structure (SWS) **already has** a committed clean-room decoder,
`tools/kiwi_types.py` (`--selftest` 10/10; `census ROOT` prints fits/total for
ten documented tables on both cards), and its three tables are already named
in `docs/format/map-tiles.md:255,266,388`. The task's "follow-up task per
adopted structure" Done-when is therefore satisfied by existing work: **no new
`board.py add-task` is required** (an SWS wide-row census extension remains a
hypothesis, not a committed task). No KIWI parser or GPL code is adopted — the
six unrelated families are closed, and the "KIWI is a reader for ZE0" lead is
listed under Retired leads in `TODO.md`. Rule 13: no L3/L4 acceptance is
claimed.

