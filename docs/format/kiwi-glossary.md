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
