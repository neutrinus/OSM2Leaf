# EXP-2026-11-05-21: Three-filter literal analysis and the HDD_INFO builder

- **Status:** done (builder located; parser one indirection away)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-350…C-357
- **Supersedes:** the `USR_Convert` module at `0x0101e408` and the “map module
  references `VER_INFO\HDD_INFO.TXT`” claims
- **Superseded by:** none

## Question

Can the `USR_Convert_*` / path-opening family locate the `HDD_INFO` parser?

## Hypothesis

`Set finished mark (file=%s)` at `0xe4dc18` leads to the parser.

## Observations

### Three-filter method (new, reusable)

Literal-pool work needs filters in this order:

1. **F1** — code pages only (≥4 prologues / 4 KiB);
2. **F2** — reject loads whose register is used as a `jsr`/`jmp` target within
   8 bytes;
3. **F3** — reject import thunks.

The index falls from 236,765 to **95,758** candidates.

### Retractions

- **“`USR_Convert` module at `0x0101e408`” — retracted.** Those sites are
  12-byte import stubs; the literal is an **IAT slot**
  (`0x1e6c020 − 0xe4dc18 = 0x0101e408`). A dense thunk table aligned against
  a dense string set manufactures an “11-string cluster”. Same for
  `0x01011478`.
- **“The map module references `VER_INFO\HDD_INFO.TXT`” — retracted.**
  `0xc0dbda`, `0xc1078c`, `0xc10800` are `mov.l …,r3 ; jsr @r3` — call
  targets, not data references.

### The only builder that touches the HDD_INFO path

Under data delta `0x02800000`, clean data references are exactly:

| Address | String |
| --- | --- |
| `0x6faf28` | `mSD\VER_INFO\HDD_INFO.TXT` |
| `0x6faf0e` | `TXT` |
| `0x6faf52` | `til.dll` |
| `0x6faeee` | `%u` |
| `0x6fb0ce` | `manufacturer_id` format |

The path **start**, `UserSD`, `userdata_type`, `destination_id`,
`application type` and `finished not found` have **zero** clean data
references.

**`0x6faeb0` builds the path from fragments**:

- `mode = *(obj+16)`;
- modes `0`/`10` append `"mSD\VER_INFO\HDD_INFO.TXT"` to a buffer already
  holding `"\Syste"`;
- other modes append `"TXT"`;
- the DLL branch appends `"til.dll"`;
- status `2…6` selects `obj+68/76/80`;
- `0x0367b180` logs `"Debug Common Version 0.1"`.

The `+12` literal is a **fragment**, not a suffix pointer. The builder does
**no I/O** — only `memset`, append, a status probe and a switch.

### Still unknown

- Six-line mapping; constraints only: numeric `Sys[0x%x] SD[0x%x]`,
  `0 ≤ v < 6`, field enum `0x00A2` at `*(r12+4)`.
- Card vs `0x06000000`: no code link; hypothesis stands.
- Parser location: one indirection away — the helper that receives the built
  path (`0x0369d400`, `0x036922cc`, `0x0367b180`, `0x0369d3dc`, module
  `0x0367–0x0369xxxx`).

## Follow-ups

- [ ] Pin the `0x0367xxxx–0x0369xxxx` module with the three-filter index and a
      cluster anchored on a string that module prints itself.
- [ ] Walk from the helper receiving the built path to the open/split/parse.
- [ ] If that stalls, run the 89-variant spare-card matrix (all 72 bytes).
