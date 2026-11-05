# EXP-2026-11-05-28: Initializer found, vtable built at runtime

- **Status:** done (initializer located; reader still unknown)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-420…C-428
- **Supersedes:** the hope that a static NaviStateCC vtable exists in the
  payload
- **Superseded by:** none

## Question

Is there a ROM initializer for NaviStateCC class data at `0x1d0f8a8`, and does
a static vtable contain the fd methods?

## Hypothesis

A ROM initializer installs the class factory and a static object vtable
containing `0xc42520`, `0xc426a4`, `0xc438a4`.

## Observations

### Initializer at `0xc43430` (but dynamic invocation)

`0xc43430` is a real NaviStateCC function. It initializes the RAM block around
`0x1d0f8a8`:

```
0xc4343e  [obj+112] = 0x1d0f720
0xc43446  [0x1d0f898] = obj          ; object pointer
0xc4344a  [obj] = 0x84                ; type tag
0xc43452  [obj+88] = 0x300
0xc43456  jsr 0x2e00e18
0xc43464  [0x1d0f888] = id[0]         ; 16-byte class ID from r8
0xc43466  [0x1d0f88c] = id[1]
0xc4346c  [0x1d0f890] = id[2]
0xc4346e  [0x1d0f894] = id[3]
```

However:

- **`0x1d0f8a8` itself is never written by the ROM**; it is a separate field
  of the same block. The only direct store is a destructor at `0xc4ac6a`,
  which zeroes fields `+96`, `+100`, `+104`.
- **`0xc43430` has no static caller**: no `bsr` anywhere; its only pointer
  occurrence is the per-instruction/relocation table at `0x1302760`. The call
  is made through a RAM function pointer or by the loader.
- The RAM copy list at `0x1952b00` does **not** cover this block (it covers OS
  modules at `0x8D/0x8F` VAs).

Exact negative: the initializer is in the ROM, but its invocation and the
class-data population are dynamic. Searched all 2-/4-byte aligned dwords in the
full payload for `0x1d0f8a8`, `0x1d0f8a0`, `0x1d0f8b0` and the whole
`0x1d0f800–0x1d0fa00` window: 23 direct sites and 31 field sites, all in
NaviStateCC, none a store to the class-data base.

### No static vtable contains the fd methods

The fd method VAs under the recovered code delta `0x1f07d5c` are
`0x2b4a27c`, `0x2b4a400`, `0x2b4b600`. Each occurs **once**, in the
per-instruction table, never in a contiguous pointer run. A ≥8-pointer run scan
resolving to NaviStateCC prologues found **0 runs**.

The object vtable is therefore **built at run time** by the shared COM helper
at `0x171e9e8` (or the loader). The proven chain ends at:

```
DllGetClassObject (0xc434cc)
  -> shared COM helper 0x2e00eb8 / file 0x171e9e8
  -> class data 0x1d0f8a8 (RAM)
  -> initializer 0xc43430 (writes 0x1d0f898 / 0x1d0f888)
  -> vtable built at run time
```

## Remaining

- `.cmp`/`.ind` reader address: unknown; a method of the runtime-built object.
- Object vtable slot layout: not in the ROM.
- `chunk_size` compare vs buffer size: hypothesis.

## Next step

Static fallback is exact:

1. **Break on `MAL_DataVol_getOffset`** (VA `0x03498d48`, file `0x7f5f48`) or
   `getSize` (VA `0x03498d28`, file `0x7f5f28`); the immediate caller is the
   `.ind`/volume wrapper.
2. **Break on fd methods** `0xc42520`, `0xc426a4`, `0xc438a4`; read `pr` for
   the caller and `r4` for the object, then dump `[r4]` and slots
   `+0x00…+0xd0` (component slots likely `+0x70…+0xc0`).
3. **Break on fd thunks** (`0x2e07344`/`0x01ab9240`, `0x2e073c8`/`0x01ab902c`,
   …) to classify the real API.
4. Offline: `size_8000` and `off_last_m1` `.ind` variants.

**Hardware access is the only remaining route to the reader address.**

## Follow-ups

- [ ] Decompile the shared COM helper `0x171e9e8` for a slot template or
      construction map (static, still possible).
- [ ] Prepare the dynamic break guide and hardware kit.
- [ ] Run the `.ind` matrix when hardware is available.
