# Where `Navi.exe` keeps the last vehicle position (M8.H19)

Static + L3 result for the two 2011 builds. All addresses were obtained from
`tools/cerom.py`, `tools/nk_decomp.py pdata` / `tools/fn_match.py` or
`tools/sh4xref.py`; none is a fitted delta. SH-4 code is little-endian.

| Build | Firmware head (SHA-256 prefix) | Position word (data VA) | `default_position_fn` (fn START) | VSram block pointer | VSram reader (fn START) |
| --- | --- | --- | --- | --- | --- |
| EU2011 A | `92aa525d…007f9` (`archive/head256.img`) | `0x00d940e4` | `0x0040b49c` | `0x00d8b080` | `0x00406ae4` |
| US2011 A | `70d945d8…04da` (`archive/us256.img`) | `0x00cc1ce4` | `0x0043359c` | `0x00cb8c80` | `0x0042ebe4` |

The US VAs are `fn_match match` pairs of the EU VAs with verdict `UNIQUE` and
`pdata=START` (`0x003eba78 → 0x00414598` is the one `DIFFERENT` pair; the
shift is not a single delta).

## The stored word

The position word is a `u32` with the two `COORD001` packed codes, latitude
high:

```
word = (lat_code << 16) | lon_code
lat_code = round(32768 + 192 * lat)
lon_code = round(52742 + 128 * lon)
```

`python3 tools/coord.py position 51.70 17.45` prints `0xa6c6d6c0`
(`lat_code 0xa6c6`, `lon_code 0xd6c0`); `position 51.505 -0.273` prints
`0xa6a1cde3`, the EU factory default. `tools/coord.py --selftest` checks five
words against `tools/datask_l3.py encode_position` (24/24 checks).

The same encoding is written by `datask_l3.py` into `build["position"]` for its
`--position LAT,LON` runs. The word is *not* a plain coordinate pair: one
packed unit is 1/192 deg latitude and 1/128 deg longitude (about 600 m).

## Writers of the word

`python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --to <VA>`
finds the following literal-pool loads; every enclosing function is a `.pdata`
START (`nk_decomp.py pdata`). The US column is the `fn_match` pair.

| Role | EU2011 fn START | US2011 fn START |
| --- | --- | --- |
| Init: load at start | `0x003eba78` | `0x00414598` |
| Object-store event sub 11 (state → 3) | `0x003f6b1c` | `0x0041f47c` |
| `OBJ_CarPos_setEventMesh` subscriber, sub 6 | `0x00403564` | `0x0042b664` |
| Destination/mesh accessor | `0x00407160` | `0x0042f260` |
| Tile-header drop check | `0x0040acb8` | `0x00432db8` |
| Per-area default lookup caller | `0x0040b5ac` | `0x004336ac` |
| Mesh-list/position consumer | `0x0040b6b0` | `0x004337b0` |
| Mesh decoder helper | `0x00415a3c` | `0x0043d80c` |

`0x003f6b1c` and `0x00403564` are the two event handlers that replace the word
with a fresh `OBJ_CarPos` value or the fallback `0xa6a1cde3`. They also call
`OSM_SramClear(0x8e)` / `OSM_SramSet(0x8e)` (see below).

## Load at start

`0x003eba78` (EU) / `0x00414598` (US) is the second init function. Its position
branch is:

```
EU 0x003ebbcc: call 0x00403504(buf[32])      ; OBJ_CarPos_initPrm + OBJ_CarPos_read
EU 0x003ebbda: [0x00d940e4] = ret == 0 ? buf[0] : 0xa6a1cde3
US 0x004146ec: call 0x0042b604(buf[32])      ; fn_match pair of 0x00403504
US 0x004146fa: [0x00cc1ce4] = ret == 0 ? buf[0] : 0x98d09737
```

`0x00403504` / `0x0042b604` is a thin wrapper: `OBJDLL!OBJ_CarPos_initPrm`
then `OBJDLL!OBJ_CarPos_read(-1, -1, out)` (imports `0x003d188c` / `0x003d1880`
in EU2011, `cerom.py thunks Navi.exe`). The read is an **in-process object-store
call**, not a direct VSram read. US fallback `0x98d09737` decodes to
33.083 N, 109.617 W (the US default area), EU fallback to 51.505 N, 0.273 W.

Only `Navi.exe` and `NaviSetCC.dll` import `OBJDLL!OBJ_CarPos_write`; the only
other readers are `Vehicle.exe` and `Telema.exe`. No message from another
process carries the word into `Navi.exe`'s init, so the task's Stop condition
does not fire; *who restores the object-store value from flash after a reboot
is UNKNOWN* (next task M8.H18/M8.H20).

## VSram record read at start (settings block, not the position)

At init the firmware also reads one persistent block from the `VSram` mirror
(`0x09a40000`, `docs/hardware/head-unit.md`):

| Item | EU2011 | US2011 |
| --- | --- | --- |
| Reader fn START | `0x00406ae4` | `0x0042ebe4` |
| `OSM_SramGet` id (`r4`) | `0x8e` (142) | `0x8e` |
| Requested size (`r5`) | `0x1f20` | `0x1f20` |
| Output pointer global | `0x00d8b080` | `0x00cb8c80` |
| Output size global | `0x00d8b084` | `0x00cb8c84` |
| `OSM_SramCheck` IAT | `0x0055d8bc` (#54) | `0x00581898` |

`OSMDLL!OSM_SramGet/Check/Set` are exports #53/#54/#55. Their implementation
(`OSMDLL.dll` `0x03523838`/`0x035238bc`/`0x03523930`) rejects ids outside
0…107 and forwards to `commondll!CApi_GetSramVirtualAddress{,i}` /
`CApi_CommitSram` (build B `0x03c03408` / `0x03c0342c` / `0x03c03450`).

### Layout and acceptance rule (verified in L3, EU2011)

From `0x00406ae4` (`sh4dis --va 0x00406ae4 --count 130`) and a direct call of
that function with a crafted block in the PySh4 machine
(`python3 tools/position_store_l3.py block archive/head256.img --build eu2011`,
same command with `archive/us256.img --build us2011`; both `controls: PASS (5
cases)`, `--selftest` 5/5):

| Offset | Width | Meaning |
| --- | --- | --- |
| `+0x000` | `u16` | record marker: `12` = valid, `5` = invalid (written on failure) |
| `+0x004` | `u32` | returned block size (`0x1f20` when accepted) |
| `+0x0c0`… | — | settings areas; first derived region starts at `+0x4b0` |
| `+0x4b0` | `0x34c × 8 B` | region covered by the size computation `(size − 0x4b0) >> 3 = 0x34c` (also stored at `0x009cfb5c`, start `0x00d53f00`) |
| `+0x330` | `u16` | must be non-zero for the record to be accepted |

Acceptance (positive control, crafted block; call returns `1`):

1. `OSM_SramCheck(0x8e, &out)` returns `0` **and** the `u32` it writes to its
   output buffer (`+0` of the 20-byte scratch) is `0`;
2. the `u16` at `block + 0x330` is non-zero;
3. the `u16` at `block + 0` is `12`.

Negative controls (each alone flips the call to return `9` and overwrites
`block + 0` with `5`): `OSM_SramCheck` return `1`; its output word `1`;
`block + 0x330 = 0`; `block + 0 = 5`. The validity byte written next to the
pointer (`0x00d8b08c`) is `1` on accept and `9` on reject.

**Checksum rule:** the checksum/validity decision is made by
`OSM_SramCheck(0x8e, …)` → `commondll!CApi_GetSramVirtualAddressi` (build B
`0x03c0342c`) in the `VSram` driver; `Navi.exe` imports no CRC function. The
caller-side acceptance rule above is VERIFIED; the driver-side checksum
polynomial/block bounds are **UNKNOWN** without the unit flash (M8.H18) and are
not guessed here.

**The position word is not in this block.** `python3 tools/position_store_l3.py
pattern archive/head256.img --build eu2011` (and the `us2011` variant) fills the
block with a distinct `u32` per 4-byte offset (`0x50000000 | offset`, with the
two validity markers kept) and runs init. The resulting position word is
`0x00d94280` / `0x00cc1e80` (the uninitialised OBJ_CarPos buffer in the L3
model), `from-pattern=False`, and the word appears at no offset in the block.
So the VSram block is the settings container, while the position travels
through the object store.

## Default table used when the stored value is absent

`0x0040b49c(kind)` / `0x0043359c(kind)` first call an area resolver
(`0x0040b114` / `0x00433214`, pair) and then scan **6 rows × 16 B** at:

| Build | Table VA | Row fields |
| --- | --- | --- |
| EU2011 | `0x00179ec0` | `{u32 area key, u32 fallback word, u32 list ptr, u32 flag}` |
| US2011 | `0x00160898` | same |

Rows read from the image (`nk_decomp`/PySh4 memory read) are identical in both
builds:

```
row 0: key 0         default 0x53393630  ptr 0          flag 0x1000
row 1: key 4         default 0x50240000  ptr 0          flag 0x1000
row 2: key 5         default 0x42480000  ptr 0x179e98 / 0x160870  flag 0x1000
row 3: key 5         default 0x997192c3  ptr 0x179eac / 0x160884  flag 0x2000
row 4: key 4         default 0xa6a1cde3  ptr 0          flag 0x2000
row 5: key 0xffffffff (sentinel)
```

The 10-`u32` lists start with `0x997192c3` (34.25 N, 118.5 W), then
`0x9d009f00`, `0x95009b00`, `0x9d00a700`, `0xffffffff`. Row 4 is the EU
factory fallback used by `0x003f6b1c`/`0x003eba78`. When no row matches,
`0x0040b49c` returns `-1` and the caller uses the word at the data VA above.

## L3 falsifier (both builds)

`tools/datask_l3.py mount IMG --card-image CARD --build BUILD --position LAT,LON
--max-reads 2` (firmware code, virtual card; no QEMU):

| Build | Position | Second read (first tile) |
| --- | --- | --- |
| EU2011 | `51.70, 17.45` | `MAPAL001/B48R058R.DAT` |
| EU2011 | `52.37, 4.90` | `MAPAL001/B48R060R.DAT` |
| US2011 | `40.689, -74.044` | `MAPAL001/B38R0B0R.DAT` |
| US2011 | `34.052, -118.244` | `MAPAL001/B30R0E0R.DAT` |

Changing the stored word changes the first map request, so the task's
falsifier ("the start position ignores the record") is **not** triggered.
Caveat: the harness writes the RAM word directly and stubs the
`default_position_fn`/object-store read; it does not yet feed a VSram record
into the object store.

## Scope / open

Covered: `Navi.exe` build A of EU2011 and US2011 (all readable sections);
the 8 writer/reader VAs above; VSram block `0x8e`; default tables in `Navi.exe`.
Not covered: the `OBJDLL` object-store persistence across reboot, the `VSram`
driver's checksum algorithm (needs M8.H18 flash), QEMU/L4/L5. The statement
"the position is stored in VSram block `0x8e`" is REFUTED by the pattern-fill
negative control; the settings block is, the position word is not.

Evidence: `docs/experiments/EXP-2026-11-22-M8.H19-position-store.md`,
claims C-7160–C-7169.

## From GPS fix to car position (M8.H78)

The car position follows the GPS only through map-matching in US Navi.
A fix passes four gates, in order:

| # | Gate | Where | Fails when |
|---|---|---|---|
| 1 | GPS history ring keeps the report | `0x0046fa60` (ring `0x00dbee60`) | A0 stat byte is not 0x00/0x10/0x20/0x30 |
| 2 | The fix converts to a map mesh | `0x00452f54` | the point is outside the map build (Poland on a US card) |
| 3 | A current road link exists | `*0x00dbdc30`, exit at `0x00456eb0` | no saved locator state (VSram backup not loaded) |
| 4 | Car mesh is in the loaded mesh table, distance > 13 sets bit 0x200 | `0x0049e08c`, `0x00dd48e8`, read in `0x0049fa44` | empty table |

Only with bit 0x200 of `*0x00dbd8ac` does `0x0049fa44` write the GPS
mesh/x/y to the state `0x00dbce00`. Evidence:
`docs/experiments/EXP-2026-11-23-M8.H78-locator-gps-gates.md`, claims
C-8640–C-8648.
