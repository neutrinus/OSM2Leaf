# US ZE0 unit in Europe: region gates

Question: can a US-market 2011–2012 Leaf head unit show/use European maps?

Short answer from current research: **the map card is not the region lock — the
head unit is.** The unit reads its market/area from a kernel Target ID and uses
it to pick the launch table, UI/language resources and system settings; the card
cannot set it. An EU card can still supply map data to a US unit if the
unit-vs-card `HDD_INFO`/map-DB checks pass, but the navigation application and
UI remain the unit's US build.

> **Evidence status:** the firmware chain below (`Target ID` → `CApi_GetModelArea`
> → `AppLaunch` area switch) is `VERIFIED` statically on our EU 2011 image
> (EXP-2026-11-06-M2.7, C-780–C-789). The NAND address `0xA022`, the US/card
> behaviour and the audio path remain external (`OBSERVED`/`HYPOTHESIS`) until a
> spare unit confirms them. See [`claims.md`](claims.md).

## Verified on the EU 2011 image

- `0x00200014`: ASCII `\x82FX210ECNI.158`; the version digits `158` start at
  `0x0020001f`.
- `VER_INFO/HDD_INFO.TXT` is 72 bytes:
  ```
  QSD-302-100
  QSD-309-101
  02-110100-00
  SDC08-EVEUR
  11-05
  470323501005
  ```
- The same 72 bytes appear at image offset `0x06000000`, byte-identical. This
  is the block external sources call the unit's map record/copy. (The
  `AppLaunch` launcher checks below do **not** read it; they read a unit-side
  target-info record through a kernel IOCTL. Its role elsewhere is open.)

### Market/region chain (EXP-2026-11-06-M2.7)

`commondll.dll` exports `CApi_GetModelArea` (build B `0x03c0398c`, C
`0x03be3994`, ordinal 39). The API is a runtime dispatch to a model-info
object; it is not a compiled-in market table, and there is no setter.

The value comes from a 4-byte **Target ID** read by
`KernelIoControl(0x01013208, in = {1}, 4, out = 4 bytes)` in build B
`0x03c0c830` / C `0x03bec98c`. Byte `+4` must be non-zero and not `0xFF`;
byte `+5` is the area. The firmware logs `Target ID Code >> %02X%02X%02X%02X`
from these four bytes.

`AppLaunch.dll` (`0x03bb…` in B, `0x03b9…` in C) maps the area:

| Area | Name | Launch mask |
| --- | --- | --- |
| `0x10` | Japan | `0x00010000` |
| `0x20` | USA | `0x00020000` |
| `0x30` | Euro | `0x00040000` |
| `0x40` | Russia | `0x00080000` |
| `0x50` | China | `0x00100000` |
| other | WorldWide | `-1` (then a kernel "Env Variable" fallback, IOCTL `0x0101304C`) |

The area mask filters the launcher's process/driver table (B `0x03bcc5b0` /
`0x03bcc564`), so it selects what starts; the launcher name block contains a
JP-specific `NxJpNavi.exe` (its per-entry mask is in compressed `.data` and was
not decoded). The area does **not** select the map database. Navigation and map
modules (`Navi.exe`, `NaviMapCC`, `NaviSearchCC`, `NaviRouteCC`, `OBJDLL`, …)
do not import the area API; UI/audio/system modules do.

The same launcher reads the card's `\SystemSD\VER_INFO\HDD_INFO.TXT` and
compares it with unit-side target info fetched by
`KernelIoControl(0x0101302C)`: an 11-byte unit record (`+96` region of the
target info) and map-DB minimum/maximum (`+112`/`+114`). Those checks are
unit-vs-card; no area or region value from the card enters them.

## External findings (not locally verified)

| Layer | Claim | Status |
| --- | --- | --- |
| SD lock | SD is locked with a CMD42 password, not encrypted files. PIN is 4 unit-specific bytes + ASCII `Clarion95321`; the unit stores it in flash around `0xA100` and unlocks the card at boot. | OBSERVED / HEARSAY |
| Version | `NAVI VERSION NG` compares the card's version/record with the unit's `NAVI-1`; the launcher's unit-side record is read through `KernelIoControl` (see above), not from the card. | PARTLY VERIFIED (firmware path) / HYPOTHESIS (screen assignment) |
| Map code | `DIFFERENT MAP CODE` compares the card's `VER_INFO/HDD_INFO.TXT` with a unit-side target-info record (`manufacturer_id`, `userdata_type`, `destination_id`, map-DB range); the unit side cannot be supplied by the card. | PARTLY VERIFIED (firmware path) / HYPOTHESIS (field mapping) |
| Unit region | The market is a NAND byte in the PROD block at `0xA022` (`0x10` JP/world, `0x20` US, `0x30` EU, `0x40` RU, `0x50` CN). The firmware confirms the **values and the five-way switch**, but reads the byte as part of a 4-byte Target ID via `KernelIoControl(0x01013208)`; the `0xA022` address itself is external. The old "`AppLaunch` compares against `0x10`" wording is wrong: `0x10` is only the Japan branch. | VALUES VERIFIED / ADDRESS HYPOTHESIS |
| Firmware | Navi app `NB00` on card / `NB04` in NAND are build copies; the card's build is not executed while the unit runs its own. Audio CPU is separate: `70F3355` JP, `70F3356` US, `70F3357` EU. The EU image's `Navi.exe` is compiled `## COMPILE OPTION ## EUROPE FOR NISSAN ##`; the launcher name block also carries a JP-specific `NxJpNavi.exe`. | EU card image build OBSERVED; NB04/US build and audio mapping HYPOTHESIS |
| Precedent | A US QY7210NN booted and drew European streets from an EU card (leafsdtools issue #3). | OBSERVED / HEARSAY |
| JP→EU teardown | PROD byte alone changed little and broke TV/hangs. PROD + EU loader + EU card gave EU languages, time zones and map, but killed all audio. | OBSERVED / HEARSAY |
| Anti-theft | `SECURE` is a CAN/VIN check. Clearing PROD `A0A0–A0A3` or grounding `TEST_B1` disables it. | OBSERVED / HEARSAY |
| Full US→EU | No published recipe. Commercial converters exist; success rate and audio survival are unproven. | UNKNOWN |

## Interpretation

There are three independent gates, in this order:

1. **Card lock** — the unit expects a card locked with *its* password. A plain
   FAT copy or an unlocked card is not necessarily accepted.
2. **Card vs unit record** — the launcher reads `\SystemSD\HDD_INFO.TXT` and
   compares it with unit-side target info: an 11-byte unit record and a map-DB
   minimum/maximum. `NAVI VERSION NG` / `DIFFERENT MAP CODE` / `MAP DATA BASE
   UNMATCH` are the failure screens. These are *not* cosmetic in the sense of
   being generated by the card: the unit side comes from the kernel, and a card
   from another market will normally mismatch.
3. **Unit area + firmware** — the real blocker for a *converted* unit. The
   market/area (`0x10` JP, `0x20` US, `0x30` EU, `0x40` RU, `0x50` CN) comes
   from the unit Target ID, gates the launcher table, and drives UI/language/
   audio resources. It is not read from the card and has no setter. Patching a
   region byte alone is reported to produce a half-converted unit; the running
   navigation application is the unit's own market build.

The map database itself does not appear to be region-locked at file level: a
US unit reportedly rendered EU map files, and the map engine does not import
the area API. The missing piece for a full conversion is the unit's
area/UI/firmware layer, not the map files.

### What an EU card can and cannot do in a US unit

- **Can:** supply EU map files in the same packaging (FAT + `VER_INFO` +
  `REFER001`/`MAPAL001`/`RDSTM001`/…), if the SD lock is satisfied and the
  unit-vs-card record/map-DB checks pass. The map engine does not consult the
  market area.
- **Cannot:** change the unit's market/area, UI language set, launcher table or
  the running `Navi.exe` build. The card's firmware area is an update payload,
  not the code the unit executes.
- **Practical consequence:** an unmodified EU card in a US unit is expected to
  fail the launcher record/version checks before `Navi.exe` starts. Matching
  the card's `HDD_INFO` (and map-DB value) to the US unit's target info is the
  card-side experiment; whether the US unit's version window accepts the EU
  map data is a separate, unit-side question.

The audio CPU is a separate market component (external research: `70F3355` JP,
`70F3356` US, `70F3357` EU), so even a successful card/region conversion does
not by itself restore European audio. That part remains external and untested.

## Safest experiment order

Use a **spare card first, then a spare unit**. Never the owner's only card.

0. **Read-only:** unlock and image the US card; dump the unit NAND if possible.
   Record the target ID (`IOCTL 0x01013208` if a service tool can issue it),
   the unit's `NAVI-1` value, its target-info record and map-DB range, and
   whether the 2011 US card is tiled (`MAPAL001/*.DAT`) or monolithic like the
   JDM ~1 GB `MMAIN001.DAT`. This single fact decides whether a software patch
   is plausible or a donor EU firmware flash is unavoidable.
1. **Card only:** spare card from the US image; replace everything except
   `VER_INFO` with EU data; re-lock with the US password. Expect either EU map
   rendering or `MAP DATA BASE UNMATCH`/blank. Revert by swapping the original
   card back.
2. **Card only, record match:** copy the US unit's target-info record and
   map-DB value into the EU card's `HDD_INFO.TXT` (not blindly "line 1"), keep
   the EU map files, and re-test. This separates the record gate from the map
   data gate. Do not patch `0x0020001f` until the unit's `NAVI-1` value is
   known.
3. **Card only:** leave the EU `VER_INFO` untouched and test. This is now a
   negative control: the firmware does not read a market/region from the card,
   so the result should depend only on the record/version gates. If an
   untouched EU card passes, the unit's target-info values and map-DB window
   already accept EU data.
4. **Unit NAND, one byte (spare unit):** PROD `A022` `0x20→0x30` plus the PROD
   checksum. Expect the JP-class failure mode (wrong assets, hangs, black
   screen). Recover via test pin + NAND restore.
5. **Unit NAND, donor EU `NB04`/`NB00` (spare unit):** the commercial path.
   Expect EU UI/map, audio risk, `SECURE` risk, possible reboot on reverse
   camera.

Bench verification is enough for layers 1–3: 12 V, ground `TEST_B1` to bypass
`SECURE`, and the blue error screen appears before the map UI. Layers 4–5 need
the map screen and a GPS fix.

## Explicit speculation

- That the "edge of map" position seen on a US unit is a US coordinate clamp,
  rather than simply "Ukraine is outside the EU map".
- That a US `70F3356` audio MCU can accept EU audio firmware.
- That the 2011 US card uses the same packaging as the 2014 US unit that read
  EU maps.
- Commercial converter success rate, price stability, and whether audio
  survives.

## Legal and safety

Personal interoperability work on hardware you own, without distributing
images or patched firmware, is the defensible end. The CMD42 lock and the map
database sit awkwardly relative to DMCA/EU anti-circumvention and database
rights; treat forum "right to repair" claims with caution. Do not publish
vendor images, patched firmware or unlock PINs.

A failed region flash can leave the unit unusable. Do this only on a spare
unit, with a verified NAND backup and a recovery path.
