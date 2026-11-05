# EXP-2026-11-05-26: COM framework, relocation wall and the real breakpoint

- **Status:** done (reader still unknown; dynamic path identified)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-400…C-408
- **Supersedes:** `0x171ea2c` as the class-object target and `0x6faf30` as
  the reader breakpoint
- **Superseded by:** none

## Question

Can the COM class factory and the constructed vtable lead to the `.cmp`/`.ind`
reader?

## Hypothesis

`DllGetClassObject` at `0x171ea2c` installs a static vtable whose slots include
the fd/reader methods.

## Observations

### Correct class-object target

- `DllGetClassObject` (`0xc434cc`) loads `0x2e00eb8` and jumps; the real entry
  is the prologue at **file `0x171e9e8`**, not `0x171ea2c`.
- Its literal pool holds **link-time VAs `0x0260xxxx`**
  (`0x0260b018`, `0x0260105c`, `0x0260106c`, `0x0260ad54`, `0x0260acc4`), while
  the thunk table it calls is placed at runtime in `0x02e0xxxx`.
- So the `0x2e0xxxx` band is **not purely thunks**; it also contains framework
  code at a different section delta (`0x16e64d0` vs `0x16e248c`).

### `0x1d0f8a8` is a RAM global context

Used **23×** in NaviStateCC (`0xc43008`, `0xc434e0`, `0xc43b2c`, `0xc43ba4`,
`0xc43c44`, `0xc43ea8`, `0xc43eec`, `0xc44104`, `0xc44124`, `0xc44214`,
`0xc443a`, `0xc471a2`, …). No store to it exists in NaviStateCC, so the
framework/loader initializes it.

### The vtable is constructed, not static

- Scanning `0x1708000–0x1728000` finds **233 constructor stores** writing
  **175 distinct method VAs** (`0x0260xxxx–0x0262xxxx`) into object slots.
- Densest run: contiguous vtable build at `0x170f100–0x170f2b0`.
- **Relocation wall:** for every candidate file base, `D = 0x02600000 − Fb`
  gives at best **15/175** prologue hits (`Fb=0x1724000`). A correct
  single-section map would be ~80–90 %. The methods are spread over
  independently placed sections.

### `0x6faf30` is not the reader

It is a `jsr @r3` inside the Bluetooth/OPP state handler at `0x6faeb0`
(switch on values 2–6; `CMP_IND Status=%x` at `0x6c7e98` is
`OppAccess::msg_opp_comp_ind`). Negative lead.

### `chunk_size`

NaviStateCC has no `0x10000` pool literal, no `mov #1; shll16`, and no 4-dword
header read near the fd layer. `chunk_size` is likely an **output-buffer
size**, not a comparison. The data side still shows `0x10000` in all 194
`.ind` files.

## Still unknown

- `.cmp`/`.ind` reader address (likely a COM method, not proven).
- Whether `chunk_size` is compared, used as a buffer size, or ignored.
- Which of the six zlib copies the map loader uses.
- The 175 method VAs cannot be mapped without per-section relocation data.

## Highest-value action

Break on the exported **`MAL_DataVol_getOffset`** (VA `0x03498d48`, file
`0x7f5f48`) or `MAL_DataVol_getSize` (VA `0x03498d28`, file `0x7f5f28`) while
opening a map page. Its immediate caller is the `.ind` reader wrapper; the
return address gives the reader and the object slot gives its vtable index.

If no debugger is available, run the spare-card matrix:

- `size_8000` → buffer size vs `0x10000` compare;
- `off_last_m1` → exact seek vs `78 9c` scan.

Parallel static path: obtain the XIP/relocation records, then re-run the 175-VA
scoring with the exact per-section map.

## Follow-ups

- [ ] Dynamic break on `MAL_DataVol_getOffset`/`getSize`.
- [ ] Spare-card `.ind` matrix (`size_8000`, `off_last_m1`, …).
- [ ] Obtain per-section relocation/XIP records for the 175 method VAs.
