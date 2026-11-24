# GPS receiver setup from TestMode (M1.52)

This page is static firmware evidence only (rule 13, level L0): nothing here has
been sent to a real unit. The receiver itself is on `SCI7:` at 19200 baud
(binary 7-bit frames, `0xF0` end byte — `head-unit.md`), and the TestMode
screen writes configuration frames to it through the nav driver.

All VAs below are from `tools/cerom.py` on `TestMode.exe`, image C at
`0x5200200`, module #82, vbase `0x00010000`. They are identical in US2011
(`archive/us256.img`) and EU2011 (`archive/head256.img`); the image D source
of those VAs is the `0x00011000` section, realaddr `0x00011000`.

## Screen and entry

The call chain from pdata literal loads is:

| Step | VA | Evidence |
| --- | --- | --- |
| Screen/menu table slot holds the init-screen entry | table `0x0005c3e0` → `0x0002c04c` | `sh4xref … --to 0x2c04c` |
| Init-screen function (checks `OBJDLL`-style state at +0x0, then calls `WriteGpsData`) | `fn 0x0002c04c` | `sh4dis … --va 0x2c04c` (calls `0x3aa0c`, `0x53608`, `0x3ba08`, `0x3aae8`) |
| WriteGpsData caller | `fn 0x0003aae8` | `sh4xref … --to 0x3aa80` → `pool 0x3ac18 holds 0x3aa80 / load 0x3aba8 fn 0x3aae8` |
| Date parse, `Sleep(0xc8)` = 200 ms, position write | `fn 0x0003aa80` | `sh4xref … --calls 0x3aa80` |
| Date frame writer | `fn 0x00043da8` | `sh4dis … --va 0x43da8` |
| Position frame writer | `fn 0x00043f70` | `sh4dis … --va 0x43f70` |

The screen reached from the chain above is `fn 0x0003ac98`, whose strings are
`GPS_ANT` / `GPS_Status`, `CONNECTED` / `OPEN`, `1D`/`2D`/`3D`/`None` and
`SHORT` (VAs `0x00019964`, `0x00019984`, `0x00019978`, `0x00019998`–`0x000199a4`,
`0x00014534`). The technician-entry format strings are at `0x000199ac`
(`%02d000000-%04x-0000`, `%d.%d%d`) and the status/result string at
`0x000198f0` (`CTestModeGPSInit::WriteGpsData(FN) GpsDataSetLatLon(%d)`).

Test mode itself is entered per `EXP-2026-11-05-M2.10-testmode`: image C launch
table contains `\windows\TestMode.exe`, gated by `CApi_GetBootMode`; the exact
physical key sequence is not determinable statically.

## Text fields the technician enters

`GpsDataSetLatLon` (`fn 0x43f70`) reads two NUL-terminated text fields from the
object passed in `r4`:

| Field | Object offset | Decoded text | Meaning |
| --- | --- | --- | --- |
| Latitude | `+0x8c` | `DDMM.mmmm` | e.g. `5213.8` = 52°13.8′ = 52.23° N |
| N/S flag | `+0x84` | `N`/`n` or `S`/`s` (also `E`/`e`, `W`/`w` accepted by the decoder) | sign of latitude |
| Longitude | `+0x94` | `DDMM.mmmm` | e.g. `2100.6` = 21°00.6′ = 21.01° E |
| E/W flag | `+0x8c` | `E`/`e` or `W`/`w` | sign of longitude |

Offsets are from `mov #-116` / `mov #-108` (`0x8c` / `0x94`) at `0x43f82` /
`0x43fbc`; the hemisphere byte is at field-minus-8, which is why the source
also compares `N/n/S/s` and `E/e/W/w` (`cmp/eq #78/110/83/115`, `#69/101/87/119`).
The text parser is `fn 0x43f2c` (calls `COREDLL!atoi` at stub `0x3bf0c`) and
converts `DDMM.mmmm` to integer 1/1000 arc-minutes by a divide-by-100
reciprocal multiply, then `(DD*60 + MM.mmmm)*1000`.

## Frame table (all VAs US2011 = EU2011)

Each long frame is sent to the receiver with `DeviceIoControl` code
`0x80102010` through the helper `fn 0x43d6c`; a failed write logs one of the
`CNaviFunction::GpsDataSet* Fail.` strings (VAs `0x1d148`, `0x1d198`,
`0x1d1e8`, `0x1d230`).

| Name | VA | Bytes (hex) | Length | Checksum |
| --- | --- | --- | --- | --- |
| `GpsDataSetDate` | `0x43da8` | `A2 YY (MM-1) DD hh mm 00 00 CS F0` | 10 | `CS = sum(bytes[1..7]) & 0x7f` |
| `GpsDataSetLatLon` | `0x43f70` | `A0 00 lat3 lat2 lat1 lat0 lon3 lon2 lon1 lon0 00 00 CS F0` | 14 | `CS = sum(bytes[1..11]) & 0x7f` |
| `GpsDataSetB0_A3` | `0x4443c` | `B0 23 04 00 27 CS` | 6 | `CS = sum(bytes[1..4]) & 0x7f` |
| `GpsDataSetB0_A0` | `0x44494` | `B0 20 02 00 22 CS` | 6 | `CS = sum(bytes[1..4]) & 0x7f` |
| `GpsDataSetB3` | `0x444ec` | `B3 00 00 00 00 CS` | 6 | `CS = 0` |
| `GpsDataSetB4` | `0x4453c` | `B4 00 00 00 00 CS` | 6 | `CS = 0` |

Position payload derivation (`fn 0x43f70`, `0x44008`–`0x4409e`):

```text
lat_scaled = (DD*60 + MM.mmmm)*1000   (fn 0x43f2c)
N: lat = lat_scaled + 1 ; S: lat = ~lat_scaled
E: lon = lon_scaled + 1 ; W: lon = ~lon_scaled
lat3=(lat>>21)&0x7f ; lat2=(lat>>14)&0x7f ; lat1=(lat>>7)&0x7f ; lat0=lat&0x7f
lon3=(lon>>21)&0x7f ; lon2=(lon>>14)&0x7f ; lon1=(lon>>7)&0x7f ; lon0=lon&0x7f
```

The four `B0_A3`/`B0_A0`/`B3`/`B4` frames are constants: each function sets its
six bytes with literal `mov` instructions and calls `fn 0x43d6c`. What these
commands do inside the receiver is **unknown** from static code; they are
issued in sequence by `fn 0x44670` (calls at `0x44698`, `0x446a8`, `0x446b4`,
`0x446c0`), separated by `Sleep(0xc8)` = 200 ms.

## Hand-encoded example: 52.23 N, 21.01 E

Enter latitude `5213.8` N and longitude `2100.6` E. The tool reproduces the
frame and two deliberate corruptions:

```bash
python3 tools/gps_testmode_frames.py --selftest
python3 tools/gps_testmode_frames.py --check latlon 52 13.8 N 21 0.6 E
python3 tools/gps_testmode_frames.py --check date 26 11 22 11 36
python3 tools/gps_testmode_frames.py commands
```

Output:

```text
OK (10 checks)
A000013F2269004C7839000048F0
A21A0A160B24000069F0
B0_A3 0x4443c B0230400274E
B0_A0 0x44494 B02002002244
B3    0x444ec B30000000000
B4    0x4453c B40000000000
```

The negative mutations are in `--selftest`: XOR of the checksum byte and
setting bit 7 in a 7-bit payload byte both make `check_frame` raise
`FrameError`. Reaching the GPS screen from a button on the unit has **not**
been verified in hardware; that remains the falsifier of this task's claim
about physical steps.
