# KIWI public sources

The KIWI map format (KIWI-W Consortium / DRM, Japan) is the *conceptual* ancestor
of the ZE0 tile and parcel records we generate. This page is the source list for
that format: which editions exist, what each chapter covers, and where each
document can be reached. It is **not** a copy of the specification — only
chapter titles and short quotes appear here; every full document stays outside
this repository (downloaded to `~/projekty/leafre-work/scratch/m4.65/`, hashed,
then deleted). Re-download commands and SHA-256 are in
[`EXP-2026-11-23-M4.65-kiwi-sources`](../experiments/EXP-2026-11-23-M4.65-kiwi-sources.md).

Checked **2026-11-23** from a host with normal internet (rule 12). The
consortium's live site (`kiwi-w.org`) no longer serves the spec; the English
chapter PDFs survive in the Wayback Machine and are the documents cited below.

## Lineage

| Edition | Date | Where it lives | What it is |
| --- | --- | --- | --- |
| KIWI ver. 1.0–1.21 | ≤1999 | not retrieved | Earlier consortium editions; 1.21 added EU/US index data per Denso Technical Review. |
| **KIWI ver. 1.22** | **30 May 2000** | English chapter PDFs, Wayback Machine (see table) | The consortium edition whose chapter numbers `jharg/kiwiread` quotes. Header on every page: *"Input for ISO Physical Storage Format … V1.22"*. |
| **JIS D 0810:2004** | 2004-03 (published 2004-03-20) | JSA (sold); unofficial text mirror `kikakurui.com` | The Japanese Industrial Standard that adopted KIWI 1.22. Renumbers the clauses but keeps the frame names. |
| **ISO/TS 20452:2007** | 2007 | ISO (sold; 8-page preview at normsplash) | ISO technical specification: functional requirements and *logical data model* for a navigation PSF. Not the physical byte layout. |
| KIWI+ (ST2-ODS) ver. 0.73 | ~2001–2002 | `kiwiplus.jp` (live) | A separate extension combining KIWI with the DiMSIS space-time data model; its own format, not the map DVD layout. |

The consortium site states the specification "can be purchased from JIS", and
that JIS approval of KIWI ver. 1.22 came in March 2004 — so the public JIS text
and the archived English PDFs are the *same* format, in two numbering schemes.

## Documents

One row per document. "Chapters" lists the top-level chapter numbers that the
document actually contains (translated titles in the next section).

| Title | Version / date | URL | SHA-256 | Licence | Chapters |
| --- | --- | --- | --- | --- | --- |
| KIWI format, Chapter 1 — Document Rules | V1.22, 30 May 2000 | <https://web.archive.org/web/20150723090830if_/http://www.kiwi-w.org/format_english/pdf/0100122e.pdf> | `5181f2ddcf2190c52a8e624310c0aed800c0ac3c5ed0b40e5283eb22ae44c59e` | proprietary (Kiwi-W Consortium / DRM); free English PDF published on the consortium site | 1 |
| KIWI format, Chapter 5 — All Data Management Frame | V1.22, 30 May 2000 | <https://web.archive.org/web/20151009143254if_/http://www.kiwi-w.org/format_english/pdf/0500122e.pdf> | `e11d87d7d8b8bbf5a64cb695f61cbab5da8a50151cdd0cd1d2b35de9f1307bf3` | same | 5 |
| KIWI format, Chapter 6 — Parcel-related Data Management Frame | V1.22, 30 May 2000 | <https://web.archive.org/web/20151009154524if_/http://www.kiwi-w.org/format_english/pdf/0600122e.pdf> | `83eea16c6bf6af85b3f3c005179d825bd6d88fbfb179ac4b8feb028d72d780db` | same | 6 |
| KIWI format, Chapter 10 — Route Planning Data Frame | V1.22, 30 May 2000 | <https://web.archive.org/web/20151010144459if_/http://www.kiwi-w.org/format_english/pdf/1000122e.pdf> | `74ea5288af3d70256cccb35f62d90181a2c1da2d2c15d44c3176e0084a47b134` | same | 10 |
| KIWI format, chapter index (menu) | V1.22, archived 2008-11-20 | <https://web.archive.org/web/20081120235024if_/http://www.kiwi-w.org/format_english/menu.html> | n/a (HTML; not downloaded) | same | 1–15, 30, 32–34 |
| JIS D 0810:2004 — Road vehicles — Map data physical storage format for car navigation systems | 2004, published 2004-03-20 | <https://kikakurui.com/d0/D0810-2004-01.html> (unofficial mirror); official: JSA / JISC | n/a (HTML table of contents read; PDF not downloaded) | JIS copyright (JSA); the mirror is **not** a licence grant | 1–18 + Annexes 1–15 |
| ISO/TS 20452:2007 — Requirements and Logical Data Model for a PSF and API | 2007 | <https://www.normsplash.com/Samples/ISO/139386839/ISO-TS-20452-2007-en.pdf> (8-page preview only) | `1fbba055af8015cd7379cb7c10307df3490d7399a86765f666fd74b7383aae27` | ISO copyright; preview under ISO's sample terms | preview: scope + contents only |
| KIWI+ (ST2-ODS) | Ver. 0.73, English | <https://kiwiplus.jp/Eng/main.html> | n/a (HTML; not downloaded) | © Kyoto Univ. DRPI (site footer contact); no explicit licence stated | overview only ("prepared soon") |
| Denso Technical Review — カーナビ用地図データフォーマット KIWI | 2006, vol. 06-1 | <https://www.denso.com/jp/ja/-/media/Global/technology/review/06-1/06-1-doc-dissertation5-ja.pdf> | not obtained (Akamai 403 "Access Denied") | Denso copyright | abstract visible in the search index only |
| Wu & Li, *Extraction Main Map Data from KIWI Format* (ICC 2005 poster) | 2005 | <https://icaci.org/files/documents/ICC_proceedings/ICC2005/htm/pdf/poster/TEMA12/WU%20XUELING.pdf> | not obtained (connection reset by peer, 3 attempts) | conference proceedings (ICACI) | abstract: parses main map data, exports MapInfo MIF |

`n/a` means the object is an HTML page that was read but not archived as a file;
its content is quoted in the observations of the companion EXP.

## Chapter index of KIWI V1.22 (English edition)

Taken from the archived `format_english/menu.html` and the chapter PDFs'
headings. Titles are the document's own English wording.

- **1. Document Rules** — 1.1 terminology (field, record, table, list, frame,
  distribution header), **1.2 Data Type** (1.2.7 Sector Address, **1.2.13 Parcel
  ID**, 1.2.14 Manufacturer Identification), 1.3 how to read tables, 1.4
  expansion method.
- **2. Data Configuration on a Medium**
- **3. Hierarchical Structure of Maps**
- **4. Configuration of Data Management Frame**
- **5. All Data Management Frame** — **5.1 Data Volume**, 5.1.1 Level Management
  Information, 5.2 Management Header Table.
- **6. Parcel-related Data Management Frame** (Main Map and Route Guidance Data
  Management) — 6.1 Distribution Header, **6.1.1 Level Management Record**,
  **6.1.2 Block Set Management Record**, 6.2 Block Management Table, **6.2.1
  Block Management Record**, 6.3 Parcel Management Information, 6.A supplements.
- **7. Main Map Data Frame** — 7.1 Main Map Data Frame, **7.2 Road Data Frame**,
  **7.3 Background Data Frame**, **7.4 Name Data Frame**, 7.5 Additional Data
  Frame, 7.A description for road data. 7.2 sub-headings include 7.2.1 Road
  Distribution Header, 7.2.1.1 Display Class Management Record, 7.2.2 Road Data
  List, 7.2.2.1.1.1 MultiLink Header. Chapter 7 has no archived PDF, so the
  titles are taken from the archived table of contents (reproduce):
  ```bash
  curl -sSL "https://web.archive.org/web/20151009143714if_/http://www.kiwi-w.org/format_english/menu007.html" -o menu007.html
  sha256sum menu007.html   # 8dbdc45b502dcdc92dff8d60f231409bc0bad26e8b8697a9287f26dd51be172b, 2470 B
  python3 -c "import re;d=open('menu007.html','rb').read().decode('latin-1');print(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',d)).strip())"
  # prints: ...V. Main Map Data Frame 7.1 Main Map Data Frame 7.2 Road Data Frame
  #         7.3 Background Data Frame 7.4 Name Data Frame 7.5 Additional Data Frame 7.A ...
  ```
- **8. Route Guidance Data Frame** — 8.1 Distribution Header, 8.3 Extended Data
  Frame, 8.4 Guidance Data Frame (8.4.1.2 Intersection Name, 8.4.1.3 Road Name,
  8.4.1.4 Toward Name, 8.4.1.5 Spot Guidance, 8.4.1.6 Direction Indicator,
  8.4.1.7 Road Structure, 8.4.1.8 Building and Facility data lists).
- **9. Region Data Management Frame**
- **10. Route Planning Data Frame** — 10.1 Distribution Header, **10.6 Node Data
  Frame**, **10.7 Link Data Frame** (10.7.1.2 Regulation Records, 10.7.1.3
  Between-links Cost Records, **10.7.1.5 Upper Level Correspondence Table of the
  Boundary Link**), **10.8 Upper Level Correspondence Data Frame of the Node**,
  **10.9 Upper Level Correspondence Data Frame of the Link**, **10.10 Link Cost
  Data Frame**, **10.11 Passage Code Data Frame**, **10.12 Node Coordinate Data
  Frame**, 10.13 Road Reference Table.
- **11. Management Pattern of Index Data** — 11.1 Index Data Frame Structure …
  11.7 Category Codes, 11.8 Jump Table, 11.12 Search Method (Overseas).
- **12. Parameters**
- **13. Metadata**
- **15. Reference**
- **30. Loading Module Management Format**
- **32. Main Map Data Metadefinition Data**
- **33. Image Data Frames**
- **34. Voice Data Frame**

Chapters 14, 16–29 and 31 are absent from the English archive menu; they are
either reserved or not published in English (see the "not found" section).

## Which version do the `kiwiread.c` chapter numbers match?

**KIWI ver. 1.22 — exactly, and not JIS D 0810:2004.** `jharg/kiwiread`
(commit `74741c5b`) tags its structs with the chapter numbers `1.2.7` (Sector
Address), `1.2.13` (Parcel ID), `1.2.14` (Manufacturer ID), `5.1` (Data
Volume), `6.1` / `6.1.1` (Level Management Record) / `6.1.2` (Block Set
Management Record) / `6.2.1` (Block Management Record), and `7.2`–`7.4` (Road /
Background / Name Data Frame). Every one of those numbers and titles appears at
the *same* number and title in the archived V1.22 PDFs (positive control: the
matching headings were read out of chapters 1, 5, 6 and 10; see the EXP
observations). JIS D 0810:2004, by contrast, moves the same material into
clause numbers `8.1` (data types), `9.1` (data volume), `10` (parcel
management) and `11.1`–`11.5` (main map frames) — so a reader citing JIS
clauses would use different numbers for the same records. `kiwiread`'s numbers
therefore identify the consortium V1.22 text, not the JIS derivative.

## Other open readers / writers

One row per tool. Licences are taken from the repository's own licence file.

| Tool | What it reads/writes | Licence | Notes |
| --- | --- | --- | --- |
| [jharg/kiwiread](https://github.com/jharg/kiwiread) | Reader for KIWI map DVDs (`ALLDATA.KWI`/`LOADING.KWI`, Audi etc.); volume header, parcel data-management header, level/block-set/block records, road/background/name frames | **GPL-3.0-or-later** | The field-name source for M4.63/M4.67/M4.68/M4.72 and this page. Link and chapter/field names only; no code copied. Commit `74741c5b` (checked 2026-11-23). |
| [KarpelesLab/kwi](https://github.com/KarpelesLab/kwi) | Reader/**writer** for `LOADING.KWI` *program/OS images* (Panasonic/Aisin AW R-Car H1 head units), not the map data | **MIT** | Different object: the update-container wrapper (`PCRD`/`pmb`/`rootfs`), not KIWI map records. Its README points at `kiwiread` for the map data. Useful only as a second, independent KIWI-adjacent implementation and a reminder that "`.KWI`" names two formats. |
| Wu & Li (ICC 2005) | Parser: KIWI main map data → MapInfo MIF | academic paper, no code released | Describes KIWI map-display data structure; full PDF not obtained here. |
| Zhang et al. (2011, *Transportation Research Part C*) | Uses KIWI as the in-vehicle format in an intersection model | academic paper, no code | Cited for the format's role, not as a byte-layout source. |

No writer that emits KIWI map records (as opposed to the `LOADING.KWI` program
container) was found in the open-source search of 2026-11-23.

## What is citable, and what is not

- **Citable as the format definition:** the KIWI V1.22 chapter PDFs (as the
  consortium's own English edition) and JIS D 0810:2004 (as the standard
  edition). Chapter *numbers* must say which edition they come from — V1.22 and
  JIS differ (see above).
- **Citable as ISO context:** ISO/TS 20452:2007 for requirements and the
  logical data model; it is **not** a physical byte-layout reference.
- **Not citable as ZE0 evidence:** nothing on this page proves the Leaf's own
  container *is* KIWI. M4.63 already closed that as "common concepts, different
  container"; KIWI is a field-name and concept glossary, not a value oracle
  (rule 13 unchanged).
- **Do not commit the documents:** they are third-party, some sold by JIS/ISO.
  Only titles, chapter names, short quotes, URLs and hashes belong in the repo.

## Looked for, not obtained (negative results)

- The consortium's current live **`format_english/`** paths: `format_kihon.html`
  is 404 live (2026-11-23) and 401 over plain `http:`; only Wayback copies exist.
- **Chapter 7 PDFs** (`0702122e.pdf`, `0703122e.pdf`, `0704122e.pdf`): listed in
  the archived menu but no Wayback capture (CDX returns no rows; direct fetch
  404). Chapter 7 titles were read from `menu007.html` instead.
- **Denso Technical Review 06-1** (Denso's own KIWI article): Akamai returned
  `Access Denied` (403) to every UA tried; the abstract in the search index
  dates KIWI ver. 1.22 to May 2000 and says 1.21 added EU/US index data.
- **Wu & Li ICC 2005 poster PDF**: `connection reset by peer` from `icaci.org`
  on 3 attempts (HTTP/1.1 and default); no local copy.
- **KIWI+ download**: `kiwiplus.jp/Eng/download.html` names "KIWI+ Ver.0.73
  (English)" but exposes no file link (text only) — nothing to fetch.
- **A public *free* full text of JIS D 0810 or ISO/TS 20452**: not found. JIS is
  sold (≈US$868, 845 pages); ISO/TS 20452 is sold, with only an 8-page preview.
  The `kikakurui.com` JIS page is a full table of contents (used here for the
  clause map) but is an unofficial mirror, not a licence to redistribute.

## References used by this page

- `jharg/kiwiread` is already listed in [`sources.md`](sources.md); its row
  points here for the version identification.
- Task M4.65; companion record
  [`EXP-2026-11-23-M4.65-kiwi-sources`](../experiments/EXP-2026-11-23-M4.65-kiwi-sources.md).
- Chapter-10 availability is the lead that lets M4.72 (route-planning concepts),
  M4.40 and M5.57 look up the node/link/cost/upper-level-correspondence records
  by name; it does **not** prove the ZE0 route data uses them.
