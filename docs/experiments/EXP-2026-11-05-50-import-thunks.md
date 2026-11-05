# EXP-2026-11-05-50: Import thunks of Navi.exe, resolved to OBJDLL names (M1.6)

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, first 256 MiB, SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
- **Claims:** none changed
- **Supersedes:** none
- **Superseded by:** none

## Question

M1.6 done-when: a call in `Navi.exe` shows `OBJDLL!MAL_DataVol_getOffset`, not a raw VA.

## Hypothesis

CE import tables resolve through IAT slots. Each import has a stub that loads the slot and jumps through it. Names come from the OriginalFirstThunk (uncompressed), so they do not need the `.data` decompressor (M1.2).

## Inputs

| Item | Value |
| --- | --- |
| Image A | `--image-start 0x200200` |
| Module | `Navi.exe`, vbase `0x00010000`, import dir rva `0x548328` |
| Sections used | `.text` rva `0x1000` (uncompressed); `.rdata`/OFT uncompressed |

## Method

```bash
python3 tools/cerom.py --image-start 0x200200 IMG imports Navi.exe   # 846 slots
```

Then, for the two MAL_DataVol slots, find the stub, the literal-pool references
to the stub, and the `jsr` that loads it (SH-4 16-bit opcodes; `mov.l @(disp,PC),Rn`
is `0xD___`, `jsr @Rn` is `0x400B|n<<8`, `jmp @Rn` is `0x402B|n<<8`).

## Observations

- `imports` lists 846 slots. Almost all are `COREDLL.dll` ordinals. `OBJDLL.dll` names:
  - `slot=0055d38c MAL_DataVol_getSize`
  - `slot=0055d390 MAL_DataVol_getOffset`
- The stub at VA `0x003d1bb0` is `mov.l @(pc),R0 ; mov.l @R0,R0 ; jmp @R0 ; nop`, with the literal `0x0055d390`. It is the `getOffset` thunk.
- The stub at VA `0x003d1ba4` is the same with literal `0x0055d38c`. It is the `getSize` thunk.
- Literal-pool references to the thunks: `getOffset` at `0x0037796c` and `0x00377dd0`. `getSize` at `0x00377970` and `0x00377dd4`.
- Each literal is loaded and then called through a register:
  - `0x003778ae`: `mov.l @(pc),R3` ; `0x003778b2`: `jsr @R3` → `getOffset`
  - `0x003778b8`: `mov.l @(pc),R3` ; `0x003778bc`: `jsr @R3` → `getSize`
  - `0x00377b42`: `mov.l @(pc),R3` ; `0x00377b46`: `jsr @R3` → `getOffset`
  - `0x00377b4c`: `mov.l @(pc),R3` ; `0x00377b52`: `jsr @R3` → `getSize`
- No `BSR` reaches the thunks (checked: 0 callers).

## Interpretation

The call at `0x003778b2` calls the stub at `0x003d1bb0`, which jumps through
slot `0x0055d390`, which the OFT names `OBJDLL.dll!MAL_DataVol_getOffset`. The
done-when holds. Three more call sites (`0x00377b46`, `0x003778bc`, `0x00377b52`) use the same pair of stubs.

Negative control: the slot names come from the OFT (uncompressed). The
FirstThunk (`0x0054d000`) lives in a compressed section, so the resolution does
not depend on decompressing it. The `getSize` pair is the same method on a
second slot.

## Next

- Use the same stub pattern to resolve the other 845 slots (M1.6 full).
- Callers: list all `jsr` sites for each stub (M2.1 can use them).
