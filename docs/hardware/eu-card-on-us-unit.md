# EU map card on a US unit: change the card's map code

This guide is for a US 2011–2012 Leaf unit (QY7200ND class) and an EU map
card. The unit refuses the EU card because the map codes differ. The fix
is to give the EU card the unit's map code. Nothing on the unit changes. To
undo it, put the original card back.

**Status:** the change is tested in the emulator on Marek's unit data
(`-M ze0,flash=`): the EU card starts and Navi draws the map
(EXP-2026-11-22-M8.C1m-unit-flash-region, C-8356, C-8357). **It has not
been tested in a car yet.** The emulator has no GPS, no radio and no
vehicle bus. Before the car test, back up the unit's flash (M6.18).

## Why it works

At boot the launcher compares two strings:

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
   # NK1 at +0x0: map code (VerInf) QSD-301-100, map DB window 16-16
   python3 tools/card_mapcode.py unit --nk1 my_nand_dump.bin     # own unit
   ```

2. Read the card:

   ```bash
   python3 tools/card_mapcode.py show --image eu_card.img
   # map code (HddInf, launcher): QSD-302-100
   # raw copy at 0x06000000: same as the file
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
   # patched eu_card.img: map code QSD-302-100 -> QSD-301-100 (file and raw copy)
   # verify: ok
   ```

   `--code QSD-301-100` gives the code directly. The tool changes one
   character in the file's cluster and in the 72-byte raw copy at
   `0x06000000`. It does not rebuild the FAT. `--file-only` leaves the raw
   copy alone; the launcher reads only the file (C-8356).

5. Write the image to the SD card (`dd if=eu_card.img of=/dev/sdX bs=4M
   conv=fsync`), lock it with the unit's PIN, and put it in the car.

6. Check and note:
   - whether the map starts (or `DIFFERENT MAP CODE` / FailSafe appears);
   - whether the car's position shows in Wrocław and not Kentucky
     (M1.50/M1.51);
   - the menu languages, units and radio bands.

   Photos of the screens help.

To undo: put the original card back, or run `set --code QSD-302-100` on the
patched copy.

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
