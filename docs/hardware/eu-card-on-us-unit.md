# EU map card on a US unit: change the card's map code

This guide is for a US 2011–2012 Leaf unit (QY7200ND class) and an EU map
card. The unit refuses the EU card twice: the build name of the card's
application image differs from the unit's, and so does the map code. The
fix is to give the EU card the unit's build name and map code. Nothing on
the unit changes. To undo it, put the original card back.

**Status:** tested in the emulator on Marek's unit data.

- With the unit's own kernel NK1 (`-M ze0,nk=…,flash=`), the EU card with
  both changes passes both checks and the launcher finishes
  (EXP-2026-11-22-M8.C1r-nk1-boot). With the map code alone it stops at
  `NK Version Error`.
- With the `ze0_ipl.py --nk` line added in M8.C1q, Navi.exe starts on NK1
  and draws the EU card's map (London), and the US card's map (Los Angeles)
  in the same setup (EXP-2026-11-22-M8.C1q-navi-on-nk1). Before that fix it
  failed on both cards: an emulator timing gap (deferred RAM), not the region.
- With the card's kernel B instead (M8.C1m), Navi drew the EU map.

**It has not been tested in a car yet.** The emulator has no GPS, no radio and no
vehicle bus. Before the car test, back up the unit's flash (M6.18).

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
check. It stays USA, which may affect languages, units and radio bands.
That is for the car test to show.

## What you need

- A copy of the EU card as an image file, made with `dd` from the card or
  taken from a backup. Work on a copy and keep the original.
- The unit's map code. Use the committed NK1
  (`firmware/unit-flash/nk1-QY7200ND.bin`, Marek's unit) or your own
  LeafSDTools NAND dump.
- Python 3 and this repository.
- A way to write the image to an SD card, then lock the card with the
  unit's PIN as before: [sd-blocker-pico.md](sd-blocker-pico.md) or
  LeafSDTools. **Without the password the unit does not read the card.**

## Steps

1. Read the unit's map code:

   ```bash
   python3 tools/card_mapcode.py unit --nk1 firmware/unit-flash/nk1-QY7200ND.bin
   # NK1 at +0x0: map code (VerInf) QSD-301-100, map DB window 16-16, build X110NBNI.147
   python3 tools/card_mapcode.py unit --nk1 my_nand_dump.bin     # own unit
   ```

2. Read the card:

   ```bash
   python3 tools/card_mapcode.py show --image eu_card.img
   # map code (HddInf, launcher): QSD-302-100
   # raw copy at 0x06000000: same as the file
   # image A build name (NKOK +0x16, NB00 / NB01): X210ECNI.158 / X210ECNI.158
   ```

3. See the plan without writing anything:

   ```bash
   python3 tools/card_mapcode.py set --image eu_card.img \
       --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --dry-run
   ```

4. Patch the copy, either in place or into a new file (about 7.5 GB):

   ```bash
   python3 tools/card_mapcode.py set --image eu_card.img \
       --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --in-place
   # setting: image A build name X210ECNI.158 / X210ECNI.158 -> X210NBNI.147 (both NKOK headers)
   # patched eu_card.img: map code QSD-302-100 -> QSD-301-100 (file and raw copy)
   # verify: ok
   ```

   `--code QSD-301-100` gives the code directly. The tool changes one
   character in the file's cluster and in the 72-byte raw copy at
   `0x06000000`. It does not rebuild the FAT. `--file-only` leaves the raw
   copy alone; the launcher reads only the file (C-8356). With
   `--from-nk1` the tool also writes NK1's build-name tail into both
   `NKOK` headers (12 bytes each). `--nk-name X210NBNI.147` sets the name
   by hand, and `--map-code-only` skips it (that card would stop at
   `NK Version Error`).

5. Write the image to the SD card (`dd if=eu_card.img of=/dev/sdX bs=4M
   conv=fsync`), lock it with the unit's PIN, and put it in the car.

6. Check and note:
   - whether the map starts (or `DIFFERENT MAP CODE` / FailSafe appears);
   - whether the car's position shows in Wrocław and not Kentucky
     (M1.50/M1.51);
   - the menu languages, units and radio bands.

   Photos of the screens help.

To undo: put the original card back, or run `set --code QSD-302-100
--nk-name X210ECNI.158` on the patched copy.

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
