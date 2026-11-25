# EXP-2026-11-25-H150-osm2clarion-pilot

- **Status:** done
- **Date:** 2026-11-25
- **Sample:** `none (tool-only task)` — the EU 2011 card image and the US 2011 card image from `files.viaaq.eu` (owner's images, not committed); the card built from them is not committed either
- **Tools:** osm2clarion `458f5f0d` (profile `poland`, area `dolnoslaskie`), `tools/card_mapcode.py`, `tools/ze0_consent.py`, `tools/audio_transplant.py`, `tools/ze0_launch.py --ui-start`, QEMU `-M ze0`
- **Claims:** C-10400–C-10401
- **Supersedes:** none
- **Superseded by:** none

## Question

Does a card built with osm2clarion's area mode (Dolnośląskie, EU 2011 base) boot in our `-M ze0` emulator, and what has to be changed on the unit-flash side?

## Hypothesis

It boots after the usual EU-on-US patches (map code, consent, audio). Falsifier: it does not reach `MAP_MAPOPERATION_NORMAL_MAP`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | EU 2011 card `LEAF_2011-2012_QSD-309-101_navi158_eu.img`; US 2011 card `LEAF_2011-2012_US.img` (control) |
| SHA-256 | EU `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`; US `53342430…c5383` (as in TODO "Shared inputs") |
| Offset(s) / VA(s) | flash `0x400000–0x45FFFF` (SRAM area 0) |
| Tool / version | osm2clarion `458f5f0d`; QEMU 11.1.3 `-M ze0` |
| Repo tool | `tools/card_mapcode.py`, `tools/ze0_consent.py`, `tools/audio_transplant.py`, `tools/ze0_launch.py` |

## Method

1. **Sample and hash.** The two images above; the pilot card is built from the EU image with osm2clarion area mode on `dolnoslaskie.osm.pbf` (openstreetmap.fr extract); their `card_check` rules all PASS.
2. **Commands.**
   ```bash
   python3 tools/card_mapcode.py set --image CARD --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --in-place
   python3 tools/ze0_consent.py patch CARD --in-place
   python3 tools/audio_transplant.py apply --in-place CARD US_CARD
   python3 tools/ze0_launch.py --card CARD --flash flash-eu.bin --peer panel --peer gps --gdb 1240 --ui-start
   ```
   `flash-eu.bin` is the anonymous flash with bytes `0x400000–0x45FFFF` set to `0xFF`.
3. **Controls.** Negative: the plain EU base with the same patches (no osm2clarion) on the unmodified anonymous flash. Positive: the unmodified US card on the same flash.
4. **Scope.** Boot to the map only. No driving, routing or zoom result is claimed.
5. **Falsifier.** The pilot card does not reach `MAP_MAPOPERATION_NORMAL_MAP` even with area 0 erased.

## Observations

- Anonymous flash as built: the pilot card and the plain patched EU base both stop after `Store Mgr Ready!`, with `ACM::WaitModule Timeout` lines and no `AUI Initialize Complete`; the panel never gets a touch guard to clear (uistart: "waiting for the first touch").
- Unmodified US card on the same flash: reaches `SRT_COLD_I_AGREE_NAM::CompleteShowScreen` (control passes).
- Pilot card on the flash with area 0 erased, US Audio.exe transplanted: reaches `MAP_MAPOPERATION_NORMAL_MAP`; the screen shows the factory London tile (consent text still drawn from a stale plane).
- Not reached: the car did not move to Wrocław in this session (the map stayed in scroll state), so Dolnośląskie roads were **not** seen on screen.

## Interpretation

- **FACT:** the pilot card is not what blocks the boot: the plain patched EU base fails the same way until area 0 is erased.
- **FACT:** with area 0 erased the card reaches the map.
- **UNKNOWN:** whether the osm2clarion roads draw near Wrocław (needs the car moved by GPS and wheel pulses, `docs/emulator/running.md` §5); routing on that card.

## Conclusion

Positive for boot, open for roads. The generator in this repository was removed in the same change (tools, `profiles/`, 36 dependent tasks closed as cancelled); see README.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/card_mapcode.py set --image CARD --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --in-place
python3 tools/ze0_consent.py patch CARD --in-place
python3 tools/audio_transplant.py apply --in-place CARD US_CARD
python3 - <<'PY'   # erase SRAM area 0 in a copy of the anonymous flash
b=bytearray(open('flash-anon.bin','rb').read()); b[0x400000:0x460000]=b'\xff'*0x60000; open('flash-eu.bin','wb').write(b)
PY
python3 tools/ze0_launch.py --card CARD --flash flash-eu.bin --peer panel --peer gps --gdb 1240 --ui-start
```

## Follow-ups

- [ ] Drive the car to 51.1079, 17.0385 and zoom in to see the Dolnośląskie roads.
- [ ] The whole-Poland build is not run here.
