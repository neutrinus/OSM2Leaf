# Which `SPEECH/<ll>` folder does a US unit ask for with the EU card?

Question raised by M1.54 ([EXP-2026-11-22-M1.54-eu-us-card-diff](../experiments/EXP-2026-11-22-M1.54-eu-us-card-diff.md)): the EU 2011 card carries `SPEECH/{BE,DU,FR,GE,IT,PT,SP}` and the US card `SPEECH/{US,CF}`, with no overlap. After the two map-code checks are patched, does a US unit ask for a folder the EU card lacks? Answer: [EXP-2026-11-24-M1.55-speech-folder](../experiments/EXP-2026-11-24-M1.55-speech-folder.md), claims C-8460–C-8469.

## Short answer

- The folder name `<ll>` is **not read from a card file and not from the area byte**. It is the two-letter name produced by `Speech.exe` from the **unit's** `OBJ_Setting_readExpLanguage` value, through two `braf` jump-table switches first located in M4.38 (C-3761) and re-confirmed here in both 2011 builds.
- A setting of **3004 (American English) → `US`**, **3005 (Canadian French) → `CF`** in both the EU2011 and US2011 `Speech.exe`. A US unit set to US English therefore opens `\SystemSD\SPEECH\US\GID\SUS00000.GID`, which the EU card does not have.
- **Practical answer:** copying `SPEECH/US` (and `SPEECH/CF` for Canadian French) onto the EU card is needed for voice guidance **if** the unit keeps a North-American language setting. The card-free alternative is to select one of the seven European languages the card carries. The setup list itself is in firmware, not on the card, so a US unit running the EU build still offers `US`/`CF`.
- Runtime fallback behaviour (silence vs error tone vs fallback) is **unknown** — static analysis only; no L3/L4/hardware run.

## Firmware chain (all VAs attributed with `tools/cerom.py`)

| Step | EU 2011 | US 2011 | How found / printed |
| --- | --- | --- | --- |
| Unit setting read | `OBJDLL!OBJ_Setting_getObjID` then `OBJDLL!OBJ_Setting_readExpLanguage`, called at `Speech.exe` `0x000a6e08` / `0x000a6e16` (fn `0x000a6dfc`) | same imports, `Navi.exe` `0x00401040` / `0x00401640` (fn `0x003ef04c`) | `sh4xref --calls` (§2 of the EXP) |
| Exp → internal speech value | switch `braf 0x000a6e36`, table `0x0003256c`, fn `0x000a6dfc` | `braf 0x000a7776`, table `0x00032e6c` | `lang_code_table.py firmware` |
| Speech value → dir name | switch `braf 0x000a6386`, table `0x00032340`, fn `0x000a62f0` | `braf 0x000a6cc6`, table `0x00032c40` | `lang_code_table.py firmware` |
| Language-name table | `CF US JP SP PT DU IT GE FR BE` at VA `0x00032354` (dump file offset `0x21354`) | present in the US build too | `speech_years.py langs` + `va_class.py` (CODE sec0) |
| Map-language code (for text) | `Navi.exe sdl_com_hdl_get_lang` fn `0x003c0228`, table `0x00045d90`, default `0x3f` | fn `0x003ef04c`, table `0x00051af8` | `lang_code_table.py firmware` |
| Path template | `\SystemSD\SPEECH\%@\GID\S%@00000.GID` at VA `0x0001d0e0`; TTS `0x0002be18`, VR `0x0002d398` | same GID VA `0x0001d0e0`; TTS `0x0002c718`, VR `0x0002dc98` | `ce_strfind --encoding utf-16le '\SystemSD\SPEECH'` |
| Path-building fn | `Speech.exe 0x0007237c` (stores template at request `+112`, speech value at `+104`, calls exp→speech helper) | `Speech.exe 0x00072ca8` | `sh4xref --to 0x0001d0e0` + `sh4dis` |
| File open | `Speech.exe 0x00098b0c` | `Speech.exe 0x0009944c` | `sh4xref --to 0x0001d0e0` + `--calls` |
| Missing-folder log | `[F-IFC-GID] Guide Data Set/Get Error` rva `0x0000f69d`/`0x0000f6b9`; `GuideData is not load` / `Guide data read Interrupt` rva `0x0001d6f0`/`0x0001d708` | — | `ce_strfind --encoding ascii` |

The unit-side area byte (`0xA021` `0x20` USA, M2.7) selects which launch records start; it does not enter the `SPEECH/<ll>` path. Running the EU card's applications on a USA-area unit therefore still uses the EU build's language table with `US`/`CF` available.

## Cards

| Card | `MMAIN001` `0x18c` codes | `SPEECH/` dirs |
| --- | --- | --- |
| EU 2011 (`QSD-309-101`) | `05 04 02 07 0a 06 08 14` | `BE DU FR GE IT PT SP` (7) |
| US 2011 (`QSD-301-103`) | `03 04` | `CF US` (2) |

`lang_code_table.py join` maps code `0x03 → US`, `0x04 → FR`/`CF` in the firmware of both builds and covers every dir on each card with the three negative controls failing as required. The `0x18c` list is a map-text language list (M4.38); it is not the source of the speech folder.

## Scope / trust

Static analysis only: build-A `Speech.exe` and `Navi.exe` uncompressed sec0 of the EU2011 and US2011 firmware heads (no compressed code sections exist on build A); card side is names/codes printed by `lang_code_table.py`. No L3/L4/hardware run — rule 13 acceptance unchanged. The runtime result of a missing folder is UNKNOWN (C-8467); the full setup-screen row list is OBSERVED from strings (C-8466).
