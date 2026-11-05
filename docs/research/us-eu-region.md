# US ZE0 unit in Europe: region gates

Question: can a US-market 2011–2012 Leaf head unit show/use European maps?

Short answer from current research: **the map card is not the region lock — the
head unit is.** A card swap can prove that the unit renders EU map data, but a
fully converted European navigation system needs the unit's region/firmware
layer, and the audio path is a separate risk.

> **Evidence status:** the two offsets marked `VERIFIED` below were checked on
> our EU 2011 image. Everything else comes from external research
> (teardowns, forums, issue trackers) and is `OBSERVED`/`HYPOTHESIS` until a
> spare unit confirms it. See [`claims.md`](claims.md).

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
  is the block external sources call the unit's map record/copy.

## External findings (not locally verified)

| Layer | Claim | Status |
| --- | --- | --- |
| SD lock | SD is locked with a CMD42 password, not encrypted files. PIN is 4 unit-specific bytes + ASCII `Clarion95321`; the unit stores it in flash around `0xA100` and unlocks the card at boot. | OBSERVED / HEARSAY |
| Version | `NAVI VERSION NG` compares the ASCII version at SD `0x0020001f` with the unit's `NAVI-1`. | HYPOTHESIS |
| Map code | `DIFFERENT MAP CODE` compares line 1 of `VER_INFO/HDD_INFO.TXT` with the unit's stored map record. | HYPOTHESIS |
| Unit region | The market is a NAND byte in the PROD block at `0xA022`: `0x10` JP/world, `0x20` US, `0x30` EU, `0x40` RU, `0x50` CN. `AppLaunch.dll` calls `CApi_GetModelArea` and compares against `0x10`. | HYPOTHESIS |
| Firmware | Navi app `NB00` on card / `NB04` in NAND are market builds. Audio CPU is separate: `70F3355` JP, `70F3356` US, `70F3357` EU. | HYPOTHESIS |
| Precedent | A US QY7210NN booted and drew European streets from an EU card (leafsdtools issue #3). | OBSERVED / HEARSAY |
| JP→EU teardown | PROD byte alone changed little and broke TV/hangs. PROD + EU loader + EU card gave EU languages, time zones and map, but killed all audio. | OBSERVED / HEARSAY |
| Anti-theft | `SECURE` is a CAN/VIN check. Clearing PROD `A0A0–A0A3` or grounding `TEST_B1` disables it. | OBSERVED / HEARSAY |
| Full US→EU | No published recipe. Commercial converters exist; success rate and audio survival are unproven. | UNKNOWN |

## Interpretation

There are three independent gates, in this order:

1. **Card lock** — the unit expects a card locked with *its* password. A plain
   FAT copy or an unlocked card is not necessarily accepted.
2. **Cosmetic version strings** — `NAVI VERSION NG` and
   `DIFFERENT MAP CODE` are checks against a card/unit record. They are
   reported to be easy to satisfy, but satisfying them does **not** enable EU
   maps by itself.
3. **Unit region + firmware** — the real blocker. Region byte, navi app build
   and audio CPU build are market-specific. Patching the region byte alone is
   reported to produce a half-converted unit.

The map database itself does not appear to be region-locked at file level: a
US unit reportedly rendered EU map files. The missing piece is the unit's
region/coordinate/firmware logic.

## Safest experiment order

Use a **spare card first, then a spare unit**. Never the owner's only card.

0. **Read-only:** unlock and image the US card; dump the unit NAND if possible.
   Record PROD `A022`, the unit's `NAVI-1` value, its map record, and whether
   the 2011 US card is tiled (`MAPAL001/*.DAT`) or monolithic like the JDM
   ~1 GB `MMAIN001.DAT`. This single fact decides whether a software patch is
   plausible or a donor EU firmware flash is unavoidable.
1. **Card only:** spare card from the US image; replace everything except
   `VER_INFO` with EU data; re-lock with the US password. Expect either EU map
   rendering or `MAP DATA BASE UNMATCH`/blank. Revert by swapping the original
   card back.
2. **Card only, single fields:** patch `0x0020001f` for `NAVI VERSION NG`;
   patch line 1 of `HDD_INFO.TXT` for `DIFFERENT MAP CODE`.
3. **Card only:** full EU `VER_INFO` — tests whether region is checked on the
   card at all.
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
