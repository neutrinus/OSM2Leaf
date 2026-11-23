# UI texts: where they live and what a language change takes

> **Evidence convention:** `VERIFIED` = reproduced from the sample bytes with
> the command shown; `OBSERVED` = seen but not fully explained; `HYPOTHESIS` /
> `UNKNOWN` are marked. Claims: C-8090–C-8099
> ([`../research/claims.md`](../research/claims.md)); evidence:
> [`../experiments/EXP-2026-11-23-M1.49-ui-strings.md`](../experiments/EXP-2026-11-23-M1.49-ui-strings.md).
> Everything here was read offline; nothing was edited on a card and nothing
> ran on a unit (rule 13: the container is located, not yet exercised).

Samples (vendor data, not committed). Firmware head `archive/head256.img`
(EU2011 build A, SHA-256 `92aa525d…`), cards `archive/sd-images/…eu.img`
(EU2011), `…US.img` (US2011), `…QSD-357-101.img` (EU2014). The one file this
page is about is `substance.skn` from each card's TFAT16 tail (SHA-256
`69e101c6…` / `dbb95a1f…` / `d5a6f54c…`, the C-6500 pins).

## The short answer

> **The menus and prompts are not in the firmware's readable sections: they are
> one UTF-16LE string pool inside the player skin
> `\SystemSD2\SkinChange\001\substance.skn` on the card. The pool is a run of
> `[u32 len][UTF-16LE text]` frames, one block of ~35 frames per language, each
> block headed by the same language-selector list. The language is a user
> setting (`OBJ_Setting_readExpLanguage`) turned into a map code by `Navi.exe`
> `get_lang` (`0x003c0228`) and into a `SPEECH/` folder by
> `Speech.exe`; `commondll.dll` only forwards `CApi_*LangInfo` to a COM object.
> The UI font is the rasterizer FDL font (`0x03431020`), which has 8 of the 18
> Polish letters. So Polish is a card-data edit (replace one existing block),
> not a code patch; the 10 missing letters need transliteration or a new font.**

## Modules

| Module | ROM | Role in UI text | Evidence |
| --- | --- | --- | --- |
| `substance.skn` (card, TFAT16 `\SystemSD2\SkinChange\001`) | card | the UI string pool, one block per language | C-8090, C-8091, C-8092 |
| `auirtdll.dll` | A | AUITK runtime; draws the skin text | imports rasterizer `DCW_*` (C-8096) |
| `RASTERIZER_DLL.dll` | A | FDL font rasterizer (`DCW_Font_getNamFontAddr` `0x0344fb08` → `0x03431020`) | C-8096, C-8097 |
| `Navi.exe` | A | `sdl_com_hdl_get_lang` (`get_lang`, `0x003c0228`): setting → map code (table `0x00045d90`, 14 rows, default `0x3f`) | C-8095 |
| `Speech.exe` | A | setting → `SPEECH/<dir>` (switches `0x000a6e36`/`0x000a6386`) | C-8095 |
| `commondll.dll` | B | exports `CApi_*LangInfo` (thin COM forwarders) | C-8095 |

The control DLLs (`ScreenStateCC.dll` and the `…CC.dll` controls) carry
*state names* such as `SRT_COLD_I_AGREE`, not UI labels; those are screen/
event identifiers in a NUL-separated engineering blob (C-8099 O9), not text a
user reads.

## Format of the string pool

All words little-endian (the pool is UTF-16LE; the 512-byte card headers are
UTF-16**BE**, a different thing). A frame is:

| Field | Size | Meaning |
| --- | --- | --- |
| `length` | `u32` | byte length of the text (even) |
| `text` | `length` B | UTF-16LE; may contain `\u0080`/`\u0081` inline icon references and `\n` |
| `pad` | 0–3 B | `00 00`, then zeros to a 4-byte boundary |

Strings are laid out in runs; each language is one contiguous block that
starts with the selector list. Block frame counts (EU2011 `35×7`; US2011
`30×1, 41×1`; EU2014 `38×1, 44×13, 54×2`, printed as `frames_hist`) and the
block offsets are printed by
`python3 tools/aui_strings.py count … --anchor "English (mile)"`.

| Card | selector labels | text blocks | block frames |
| --- | ---: | ---: | --- |
| EU2011 | 8 (`English (mile)`, `English (km)`, `Français`, `Deutsch`, `Español`, `Italiano`, `Nederlands`, `Português`) | 7 | 35 each |
| US2011 | 3 (`English`, `Français`, `Español`) | 2 | 41, 30 |
| EU2014 | 17 (the EU2011 eight + `Svenska`, `Suomalainen`, `Dansk`, `Norsk`, `Polski`, `Čeština`, `Ελληνικά`, `Magyar`, `Slovenčina`) | 16 | 38, 44×13, 54×2 |

Two options map to one text set when a language has a mile and a km unit
(English) — that is why the block count is one less than the label count. The
language of a block is read from its own word (`Destino`/`Destination`/
`Destinazione`/`Bestemming`/`Zielort`); EU2011 order is PT, ES, IT, NL, DE, FR,
EN, and block 0 (PT) is the default text set.

## Selection path

| Step | Where | Evidence |
| --- | --- | --- |
| user setting | `OBJ_Setting_readExpLanguage` (`OBJDLL.dll`) | C-3760 |
| setting → map code | `Navi.exe` `sdl_com_hdl_get_lang` (`get_lang`, `0x003c0228`), table `0x00045d90` | C-3760 |
| setting → voice folder | `Speech.exe` `braf` `0x000a6e36`/`0x000a6386` | C-3761 |
| getter/setter API | `commondll.dll` `CApi_GetLangInfo` `0x03c03d20`, `CApi_SetLangInfo` `0x03c03cf0` (+ `Caution`) | C-8095 |
| setting → skin block | **not located** (a UI-layer selector reading `CApi_GetLangInfo`) | UNKNOWN, C-8094 |

The card's `0x18c` language list (`05 04 02 07 0a 06 08 14` on EU2011) is the
*voice* code list (C-2494/C-3763), not the skin block order — the skin carries
every text set, and the block order differs from `0x18c`. The list itself is
not compiled into code: it is a card header field plus a firmware table, and
the skin's selector labels name what is offered.

## The UI font and Polish

The AUI text and the map text use the same engine: `auirtdll.dll` imports only
`DCW_Font_getNamFontAddr`, `DCW_Raster`, `DCW_GetAw`, `DCW_Create`,
`DCWx_initFontCache`, and `DCW_Font_getNamFontAddr` returns the FDL font at
file `0x850220` (VA `0x03431020`). Its cmap (`U+0001..U+011F`, 285 distinct
code points) has:

| Letter | Code point | Glyph? |
| --- | --- | :---: |
| Ą ą | U+0104 / U+0105 | YES |
| Ć ć | U+0106 / U+0107 | YES |
| Ę ę | U+0118 / U+0119 | YES |
| Ó ó | U+00D3 / U+00F3 | YES |
| Ł ł | U+0141 / U+0142 | NO |
| Ń ń | U+0143 / U+0144 | NO |
| Ś ś | U+015A / U+015B | NO |
| Ź ź | U+0179 / U+017A | NO |
| Ż ż | U+017B / U+017C | NO |

This is the same 8-of-18 result as the map font (C-7880–C-7889, M4.87): a
Polish UI keeps 8 letters and must transliterate the other 10 (`L`, `N`, `S`,
`Z`, `Z`) or ship a wider font. The `FDL Font` magic inside `auirtdll.dll`'s
`%s` text (file `0x5df538`) is not a font and does not parse.

## What could be changed

| Change | What it needs | Verdict |
| --- | --- | --- |
| Polish UI by replacing a block | replace the UTF-16 texts of one EU2011 block in `substance.skn` (e.g. the English or Portuguese set), keep the frame length ≤ the original or rebuild the pool; transliterate the 10 uncovered letters | **feasible** (card-data edit, C-8098/C-8099) |
| Polish UI by adding a block | append a new ~35-frame block and add a selector label; the selector's writer is not located, so the label is a hypothesis until that is traced | **add** (needs the selector follow-up) |
| wide font for the full alphabet | new/edited FDL font in `RASTERIZER_DLL.dll` (code-resource edit) | not attempted; out of scope |
| change the language list in code | the list is the card `0x18c` + firmware tables, not a compiled string array; the skin labels are data | no code list to patch |

The block's frame lengths are their own `u32`, so a same-or-shorter replacement
text keeps every following offset — the safe one-variable edit used by the
`.skn` asset patch approach (C-6500 series). Longer text shifts the pool; that
needs a rebuild, not just an in-place splice.

## Differences between builds

| | EU2011 | US2011 | EU2014 |
| --- | --- | --- | --- |
| text blocks / labels | 7 / 8 | 2 / 3 | 16 / 17 |
| selector languages | EN, FR, DE, ES, IT, NL, PT | EN, FR, ES | + SV, FI, DA, NO, PL, CS, EL, HU, SK |
| skin size | 8,724,512 B | 7,208,992 B | 12,951,584 B |

EU2014 adds Polish (`Polski`) and nine other languages in the same container,
which is **HYPOTHESIS**-level evidence that one more language needs no firmware
change: the EU2014 build proves a 16-block skin works with *its* firmware, but
the 2011 selected-language → block selector is still unlocated (C-8094), so for
the 2011 build the open part is exactly that selector entry (subscenario "add"
above).
