# EXP-2026-11-05-24: No XIP table; module bases are wrong for most modules

- **Status:** done (negative; static VA reasoning exhausted)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-380…C-387
- **Supersedes:** the XIP-section-table lead and `module_scan`'s per-module
  `(file_base, va_base)` pairs
- **Superseded by:** EXP-2026-11-05-35 (the XIP/ROMHDR negative is retracted)

## Question

Can the XIP section table be decoded, and does it resolve the
`0x0367b180` VA collision?

## Hypothesis

The `ECEC`/`NKOK` block or the tail table gives `file ↔ VA ↔ size`, resolving
cross-module calls.

## Observations

### No XIP table in the image

- All five payloads contain **0 `B000FF`** and **0 `ROMHDR`**.
- `CECE` 1, `ECEC` 2, `NKOK` 1 in payload A — container fields or data
  coincidences.
- The `NKOK` + 15-dword + `ECEC` block at `0x2001fc–0x20024c` is **container
  metadata**: the 15 dwords are palindromic (`d108` first/last, `153a0` at
  8/14), sum to `0x180d8c` (far from the payload size); `ECEC` holds
  `0x8e232978` and `0x01751978` (container length − `0x1310`), then zero
  padding to `0x201204`.
- The tail table at `0x1951ee0`+ is **not** a VA→file map: 32-byte records
  whose pointers are all in kernel space `0x8C–0x8E`; no candidate base
  (`0x8BE00000`…`0x8DE00000`) maps them into the payload.

The exact candidate is the `ECEC` block at `0x200240`; it is **not** a section
table.

### `module_scan` bases are wrong for most modules

A content check mapped every `jsr`/`jmp` target in each module's VA band and
asked whether it lands on a code page/prologue:

| Module | Refs | Code page | Prologue |
| --- | --: | --: | --: |
| OLEAUT32 | 1243 | 38 % | **65 %** |
| TFAT | 73 | 100 % | 0 % |
| FATUTIL | 1403 | **9 %** | 3 % |
| commctrl | 1786 | **5 %** | 1 % |
| WAVEAPI | 396 | **3 %** | 4 % |

Only OLEAUT32-class deltas hold. The container stores **section groups**, not
full PE images at `base + RVA`. The `module_scan` per-module base claim is
**retracted**.

`VA 0x0367b180` is therefore still both a `jsr` target and the UTF-16 string at
`0xe7b180` — **unresolved**.

### What improved

- **148 `RSDS`/PDB records** give module identity at file offsets (tfat
  `0x28f668`, fatutil `0x2a3324`, commctrl `0x2bd588`, mspart `0x30a27c`,
  waveapi `0x30ece4`, OBJDLL `0x7ef678`, STDDLL `0x838be4`, VerInfoCC
  `0xa174c8`, …), plus 155 DLL names.
- **`scripts/rommap.py`** (`table`, `va`, `file`, `validate`) over the 26 known
  bands: `va 0x032560c3` → `TFAT.dll 0x2942c3`; `va 0x0369d400` → **UNKNOWN**.

### Readers

Unchanged and still blocked at the cross-module call:

```
obj+16 (mode) -> 0x6faeb0 builds \SystemSD\VER_INFO\HDD_INFO.TXT
              -> 0x0369d400(buf, fragment, value)   [UNMAPPED]
              -> status 2…6 -> obj+68/76/80
              -> 0x6fb05c reporter (Sys/SD, 0 <= v < 6)
```

Six-line mapping and card-vs-`0x06000000` remain unknown.

## Conclusion

Static VA reasoning is exhausted. Two ready paths:

1. **Dynamic:** break right after `0x6faf30`, read the resolved PC — one value
   unlocks the whole chain.
2. **Card matrix:** 89 length-preserving `HDD_INFO` variants, independent of
   the VA problem.

## Follow-ups

- [ ] Prepare the dynamic break/JTAG plan around `0x6faf30`.
- [ ] Keep `rommap.py` as the file-side module map.
- [ ] Run the 89-variant card matrix.
