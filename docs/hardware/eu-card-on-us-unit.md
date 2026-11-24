# EU map card on a US unit: the whole procedure

This guide is for a US 2011–2012 Leaf unit (QY7200ND class) and an EU 2011
map card. The unit refuses the EU card twice, because the build name of
the card's application image and the map code both differ from the unit's.
The fix gives the EU card the unit's build name and map code. Three
further steps make it usable in the car: a navigation state reset on the
unit, an optional consent-screen skip, and an audio patch. To undo it, put
the original card back.

**Status: works in a car (L5), 2026-11-24.** Marek's unit is a US
QY7200ND with an EU 2011 card in Wrocław. Results:

- The EU map draws.
- After a few kilometres of driving, the car shows its real position in
  Wrocław. Standing still it stays in London, the card's default, because
  the navigation accepts a far GPS fix only from consistent moving samples.
- The clock is correct, with the GPS time fix.
- The consent screen is skipped.
- The equalizer and the key beeps work.
- **Not working yet:** FM radio is only partly working, and the service
  menu does not open.

Records: EXP-2026-11-23-M1.57-eu-card-unit-data-wroclaw (car tests 1
and 2), EXP-2026-11-22-M8.C1r-nk1-boot and EXP-2026-11-22-M8.C1q-navi-on-nk1
(emulator), M8.C1p (consent), M1.58/M1.59 (audio), M6.26 (LeafSDTools
flash writes). One unit has been tested so far. Another US unit with
another build of NK1 may need other values. Step 2 reads them from your
own unit.

## Overview

| # | Where | What | Tool |
| --- | --- | --- | --- |
| 1 | unit | back up the flash and `SRAM` | LeafSDTools |
| 2 | PC | read the unit's map code and build name | `card_mapcode.py unit` |
| 3 | PC | consent skip on the EU card (optional) | `ze0_consent.py` |
| 4 | PC | audio patch on the EU card | `audio_tnr_patch.py` or `audio_transplant.py` |
| 5 | PC | map code and build name on the EU card | `card_mapcode.py set` |
| 6 | unit | GPS time fix in NK1 (optional, fixes the clock) | LeafSDTools Companion + `Write NAND` → `ALL OS` |
| 7 | unit | erase area 0 of `SRAM`, **after** step 6 | LeafSDTools `RESTORE SRAM` |
| 8 | SD card | write the image and lock it with the unit's PIN | `dd`, LeafSDTools or the Pico locker |
| 9 | car | start, then drive a few km with sky view | |

Steps 3–5 change only the card image. Steps 6–7 write the unit's flash,
and that cannot be undone without the backup from step 1.

## Why it works

First, the unit's kernel NK1 reads the card's application image A ("NK2")
from the card and compares build names from the third character on
(AppLaunch.dll fn `0x03e52d80`, C-8401):

| side | where | Marek's unit / EU 2011 card |
| --- | --- | --- |
| unit | NK1 header `+0x20` (NAND `0x40020`) | `X110NBNI.147` |
| card | `NKOK` header `+0x16` of image A, both copies (`0x200016`, `0x2000016`) | `X210ECNI.158` (US card: `X210NBNI.147`) |

If they differ, the log shows `NK Version Error. Try Next Store Region.`
for both copies, then `AppLch >> Error Proc<00000042>!!` and FailSafe. The
name is not covered by the image checksum (`Sum Check NK2` passes with it
changed).

Then the launcher compares two strings:

| side | where | Marek's unit / EU 2011 card |
| --- | --- | --- |
| unit (`VerInf`) | header `+0x60` of NK1 in the unit's flash (NAND `0x40060`) | `QSD-301-100` |
| card (`HddInf`) | line 1 of `VER_INFO/HDD_INFO.TXT` in the card's map partition | `QSD-302-100` |

If they differ, the log shows `AppLch >> Error Proc<00000050>!!` and
`FailSafe.exe` starts. The screen shows `DIFFERENT MAP CODE`.

A second check compares the map-DB window (NK1 `+0x70`/`+0x72`) with the
card. It is 16–16 on both, so it passes.

The unit's area (PROD `+0x20`, `10 20 02 12` = USA) is not part of either
check. It stays USA. In the car the map scale is in miles, and FM radio
is only partly working (M1.58). Languages were not checked.

## What you need

- A copy of the EU 2011 card as an image file, made with `dd` from the
  card or taken from a backup. Work on a copy and keep the original.
- Python 3 and this repository.
- An SD card with [LeafSDTools](https://github.com/developerfromjokela/leafsdtools)
  for the unit's flash (steps 1, 6, 7). Optionally
  [LeafSDTools Companion](https://github.com/developerfromjokela/leafsdtools_companion)
  for the GPS time fix.
- For the audio transplant only: the first 100 MiB of the US 2011 card
  (`curl -r 0-104857599`, see `tools/fetch_image.py`).
- The unit's SD PIN and a way to lock the card with it:
  [sd-blocker-pico.md](sd-blocker-pico.md) or LeafSDTools. **Without the
  password the unit does not read the card.**

## Steps

1. **Back up the unit.** In LeafSDTools run `Read NAND` and `SRAM` →
   `DUMP TO SD`. Copy `nand_….bin`, `sram_….bin` and `vflash_….bin` to the
   PC and keep them. They hold the SD PIN, the serial number and personal
   data, so do not share them or commit them (M6.18).

2. **Read the unit's map code and build name** from your own NAND dump.
   The committed NK1 is Marek's unit:

   ```bash
   python3 tools/card_mapcode.py unit --nk1 nand_XXXXXXXX_XXXXXXXX.bin
   python3 tools/card_mapcode.py unit --nk1 firmware/unit-flash/nk1-QY7200ND.bin
   # NK1 at +0x0: map code (VerInf) QSD-301-100, map DB window 16-16, build X110NBNI.147
   python3 tools/card_mapcode.py show --image eu_card.img
   # map code (HddInf, launcher): QSD-302-100
   # image A build name (NKOK +0x16, NB00 / NB01): X210ECNI.158 / X210ECNI.158
   ```

3. **Skip the consent screen** ("Touch OK to accept"). This step is optional:

   ```bash
   python3 tools/ze0_consent.py patch eu_card.img --in-place
   python3 tools/ze0_consent.py verify eu_card.img     # verify: PASS
   ```

   It changes two 16-bit literals in each copy of image A and fixes each
   copy's SUM4 (EXP-2026-11-24-M8.C1p-eu-consent-l4). A card patched with a
   version before 2026-11-24 fails `verify`, so run `patch` again on it. The
   LeafSDTools Companion consent patch does not fit 2011 cards.

4. **Audio.** The EU `Audio.exe` opens the RDS tuner `TNR2:`, which a USA
   unit never starts. Without a patch the equalizer does not react. Pick
   one variant (M1.59):

   ```bash
   # small: point the EU Audio.exe at the RBDS tuner (4 bytes)
   python3 tools/audio_tnr_patch.py patch eu_card.img --in-place
   # or larger: append the US Audio.exe to image A
   python3 tools/audio_transplant.py apply eu_card.img us_card_head.img --in-place
   ```

   Run this after step 3 and before step 5. FM radio still does not fully
   work with either variant.

5. **Map code and build name.** Check the plan first, then patch:

   ```bash
   python3 tools/card_mapcode.py set --image eu_card.img \
       --from-nk1 nand_XXXXXXXX_XXXXXXXX.bin --dry-run
   python3 tools/card_mapcode.py set --image eu_card.img \
       --from-nk1 nand_XXXXXXXX_XXXXXXXX.bin --in-place
   # setting: image A build name X210ECNI.158 / X210ECNI.158 -> X210NBNI.147 (both NKOK headers)
   # patched eu_card.img: map code QSD-302-100 -> QSD-301-100 (file and raw copy)
   # verify: ok
   ```

   The tool changes one character in `VER_INFO/HDD_INFO.TXT` and in its
   72-byte raw copy at `0x06000000`, and NK1's build-name tail in both
   `NKOK` headers. It does not rebuild the FAT. `--code` and `--nk-name`
   set the values by hand. `--map-code-only` skips the name, and that card
   stops at `NK Version Error`.

6. **GPS time fix** (optional; without it the clock is 1024 weeks off). In
   LeafSDTools Companion, run "Fix GPS Time Rollover" on `nand_….bin`
   ([details](../research/leafsdtools-companion-patches.md)). Put the
   patched file back on the LeafSDTools card under the same name, then run
   `Write NAND` → `ALL OS`. **`ALL OS` also writes `SRAM` and `VFlash`
   from that file** (blocks 8–`0x86`, M6.26), so step 7 must come after
   it. Never use `ALL+EEPROM`, which rewrites the boot loader and `PROD`.
   Nothing is read back after the write, so keep the backup from step 1.

7. **Erase area 0 of `SRAM`**, after step 6. Without this the EU card
   crashed `Navi.exe` or did not draw the map in the emulator. See
   [Reset area 0](#reset-area-0-of-the-units-sram) below. In short: take
   `sram_….bin` from `DUMP TO SD`, set its first `0x60000` bytes to `FF`,
   and run `RESTORE SRAM`.

8. **Write the card and lock it:**
   `dd if=eu_card.img of=/dev/sdX bs=4M conv=fsync`. Then lock the card
   with the unit's PIN.

9. **In the car.** The EU map starts in London. Drive a few kilometres
   above 10 km/h with sky view, and the car moves to its real position.
   This is a one-time catch-up after the card change.

To undo: put the original US card back. For the unit, `RESTORE SRAM` with
the backup restores area 0; the US card also rewrites it on its own. To
undo step 6, write the original `nand_….bin` with `ALL OS`, then restore
`SRAM`. To turn the patched image back into the EU original, use the
original copy. `card_mapcode.py set --code QSD-302-100 --nk-name
X210ECNI.158` reverses only step 5.

## Removing the consent screen (optional)

`tools/ze0_consent.py patch CARD.img --in-place` retargets the cold-start
`SRT_COLD_I_AGREE` comparator to an event the skin raises without a tap
(M8.C1p). The tool identifies the card by the length of image A and by the
NB00 part number (`470-2824-34` EU, `470-2818-33` US), not by the build
name that `card_mapcode.py` rewrites. Run it before an audio transplant,
because the transplant changes image A's length. It is confirmed in the
emulator on Marek's flash (EXP-2026-11-24-M8.C1p-eu-consent-l4) and in the
car (2026-11-24).

## Reset area 0 of the unit's SRAM

**Why.** The unit keeps the navigation's own state in `SRAM` (LeafSDTools
name; flash `0x400000–0x4FFFFF`, the `VSram` stores). This is state the
navigation writes by itself, not destinations: on Marek's unit the
navigation was never used, and all navigation and personal data had been
cleared in the menus. With the unit's full `SRAM`, the patched EU card
crashed `Navi.exe` before the first map draw (2 of 2 runs). In other
variants it stopped before the first map draw, with
`CarPosCountry=255`. With only area 0 erased, the map drew, and with a
moving GPS fix the car went to Wrocław. The rest of the unit's data was
Marek's, unchanged. Details: EXP-2026-11-23-M1.57-eu-card-unit-data-wroclaw
(O6–O8).

**What area 0 is.** In the `SRAM` file it is the first `0x60000` bytes (the
`SMST` store at `+0x0` and its second copy at `+0x30000`; layout in
`tools/unitflash_anon.py`, `AREAS`). With it erased, the firmware loads its
defaults for six objects (`OBJ_BackUp_Load Error` ×5 in the log). The other
areas stay as they are: car position backup, history, Bluetooth, and VFlash
(phone books, the TCU/CARWINGS server URL). The only URL in the user areas is
the firmware default `http://biz.nissan-gev.com/…` in VFlash. Area 0 holds
no URL.

**Order matters.** LeafSDTools `Write NAND` → `ALL OS` also writes `SRAM`
and `VFlash` from the `nand_….bin` file (blocks 8–`0x86`, M6.26). If you
flash NK1 patches with `ALL OS`, do it **first**, and reset area 0 after it.
Otherwise erase area 0 in the NAND file as well: bytes `0x400000`–`0x45FFFF`
of that file.

**Tool.** LeafSDTools, menu `SRAM` (`LeafSDTools/UserSRAM.cpp`
upstream):

- `DUMP TO SD` writes `\SystemSD\sram_<productId>_<serial>.bin` (1 MiB)
  and `vflash_….bin`;
- `RESTORE SRAM` writes `sram_<productId>_<serial>.bin` from the card back
  to flash blocks `0x47–0x56`, which is the same 1 MiB.

**Steps.**

1. In LeafSDTools: `SRAM` → `DUMP TO SD`. Copy `sram_….bin` from the card
   to the PC and keep that copy as the backup. It also holds personal data,
   so do not share it or commit it.
2. Erase area 0 in the file on the card. Keep the file name, because
   `RESTORE SRAM` looks for that exact name:

   ```bash
   F=/media/sd/sram_XXXXXXXX_XXXXXXXX.bin       # the file on the card
   head -c 393216 /dev/zero | tr '\0' '\377' | dd of="$F" conv=notrunc
   ls -l "$F"                                   # still 1048576 bytes
   head -c 393216 "$F" | tr -d '\377' | wc -c   # 0 = area 0 is erased
   ```

   (`393216` = `0x60000`.)
3. In LeafSDTools: `SRAM` → `RESTORE SRAM`, and wait for
   `Wrote 1048576 bytes`.
4. Switch off, put in the patched EU card (step 8 above), and switch on.
   Expect the navigation's start-up as after a reset. Settings stored in area
   0 return to their defaults. Which settings those are is not known.

**Undo.** Put the backup copy back under the same name on the LeafSDTools
card and run `RESTORE SRAM`. When the US card goes back in, the
navigation writes area 0 again on its own. A US card with an erased area 0 was
not tested in the emulator.

**Risk.** This writes the unit's flash. It touches only the `SRAM` blocks,
the same ones LeafSDTools restores, and not NK1, PROD or the boot blocks.
The emulator has no vehicle bus, audio controller or real power-off, so the
car result is still to be seen.

## The other way round (not recommended)

You could instead write the EU code into NK1's header in the unit's flash.
That changes the unit, it can brick it, and NK1 has checksums (SUM2 at
`+0x30`, SUM4 at `+0x84`) that must be recomputed. LeafSDTools Companion's
patcher does that for its own patches (C-8358). The card route gives the
same result for the launcher.

## Related

- GPS date one rollover back (2007 instead of 2026): LeafSDTools Companion
  1.2.1, "Fix GPS Time Rollover". It patches `navdrv.dll` in NK1 and adds a
  `COREXLL.dll` shim that adds 1024 weeks (C-8358). It fixes the system
  clock. Whether it also fixes Navi's position is not known.
  Details of this and of the consent-screen patch (which does not fit the
  2011 card yet, M8.C1p): [leafsdtools-companion-patches.md](../research/leafsdtools-companion-patches.md).
- [us-eu-region.md](../research/us-eu-region.md): what else differs
  between US and EU units.
