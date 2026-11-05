# Dynamic break guide (firmware reader)

Static analysis is closed for the NaviStateCC object vtable. This is the exact
capture plan for the first hardware/debug session.

## Primary — MAL volume accessor

Break on one of:

| Symbol | VA | File offset |
| --- | --- | --- |
| `MAL_DataVol_getOffset` | `0x03498d48` | `0x7f5f48` |
| `MAL_DataVol_getSize` | `0x03498d28` | `0x7f5f28` |

While opening a map page, capture:

- `pr` — return address; this is the `.ind`/volume wrapper,
- `r4` — the object/descriptor pointer,
- dump `[r4]`, `[r4+4]`, `[r4+8]` and the caller frame,
- the arguments (base/offset/size) and the eventual read length.

The first caller should be the `.ind` reader wrapper; from there the map
reader is one frame up.

## Secondary — fd methods

Break on the fd/IOB methods:

```
0xc42520   IOB/fd dump (type tag +0xC0)
0xc426a4   directory/disc dump (type tag +0xB4)
0xc438a4   stats formatter
```

At each break:

- `pr` = caller,
- `r4` = object,
- dump `[r4]` (vtable pointer) and slots `+0x00…+0xd0` (component methods are
  likely in `+0x70…+0xc0`, as in the reconstructed iPodCC object).

The slot that calls the MAL chain is the reader candidate.

## Tertiary — fd thunks / IAT

Break on the fd thunk targets / IAT slots to classify the real API even without
names:

```
0x2e07344 / 0x01ab9240
0x2e073c8 / 0x01ab902c
0x2e07350 / 0x01ab902c
0x2e076a4
```

Record the caller and the object argument for each.

## Offline — `.ind` mutation matrix

If no debugger is available, run `tools/ind_mutate.py` variants on a spare
card:

| Variant | Question |
| --- | --- |
| `size_8000` | is `chunk_size` compared to `0x10000` or used as a buffer size? |
| `size_20000` | same, larger value |
| `off_last_m1` | exact seek or `78 9c` scan? |
| `off_last_p1` | same, opposite direction |
| `count_p1` / `count_m1` | is the chunk count trusted or derived? |
| `off0_1` / `off_last_0` | is offset 0 special / validated? |

Each variant is paired with the original `.cmp`; the unit's accept/reject
behaviour is the oracle.

## Safety

- Original card read-only and hashed.
- Work on a spare card only.
- Keep an untouched rollback card.
- Stop at the first map-data/`SECURE`/black-map/reboot symptom.
