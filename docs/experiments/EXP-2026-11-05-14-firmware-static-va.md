# EXP-2026-11-05-14: Static VA recovery is exhausted

- **Status:** done (negative; method change)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-270…C-275
- **Supersedes:** the ROM-module-table, self-name and adjacency routes
- **Superseded by:** none

## Question

Can the ROM module table at `0x15271c8`, a self-name anchor, or
`.text`/`.rdata` adjacency recover the map module's VA base `Vt`?

## Hypothesis

One of the three routes gives a 64 KiB-aligned `Vt` that resolves the map
module's literals and call targets.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Tools | Ghidra, capstone, existing scripts |

## Observations

### Route 1 — `0x15271c8` is not a module table

The bytes are **4-byte-aligned packed module-name strings** in a
high-entropy resource blob:

```
0x15271c8  "NaviSearchCC.dll\0"   (17 B -> padded to 20)
0x15271dc  "NaviDrawCC.dll\0"     (15 B -> padded to 16)
0x15271ec  "NaviStateCC.dll\0"
0x15272b0  UTF-16 "LoadTypeLib" / "oleaut32.dll" / "REGISTRY"
```

The “16-byte stride” is just 4-byte padding. There is no `{name, VA, size}`
record; the names belong to a module at file `0x152xxxx`, not the map module.

### Route 2 — self-name anchor cannot apply

The only navi name strings live in that other module, so
`literal = 0x15271c8 − filebase + Vt` has two unknowns. Checked anyway: 12
scattered hits, no ≥4-pointer cluster.

### Route 3 — adjacency and shared-`.rdata` clusters fail

- No fourth `.rdata` delta exists beyond `0x01e00000`, `0x02000000`,
  `0x02200000`.
- `Vt = 0x02dab000` (adjacency) is wrong: the 830 literals in that VA range
  reference embedded PNG data (`IHDR/IDAT/tRNS`, file `0xdf103c–0xdf1d90`)
  under the data delta `0x02000000`; only 32/830 land on prologues.
- Call-target scan is flat: 1122 distinct targets in
  `0x02e00000–0x02e60000`; 644 map into the module's file range under
  `0x02200000`, but only 18/1122 are prologues. Best 1-D delta is 14–15 % and
  the two halves of the band disagree.

## Corrections

1. **`0x1952b00` field `+0x10` is a Unix timestamp**, not a checksum: it
   decodes to 2011-06-22 … 2011-07-29. The round-6 “checksum” is retracted.
2. **The round-2 “call-to-string paradox” is withdrawn.** Under delta
   `0x02200000`, `0x02e07344 → 0xc07344`, which is plausible code; the string
   at `0xe07344` is reached under the data delta `0x02000000`. The objection
   to `0x02200000` is withdrawn, though it is still not proven as a code delta.

## Interpretation

- **FACT:** all three static routes fail, with explained causes.
- **FACT:** the map module's placement metadata is not present in this
  container in a statically recoverable form.
- **UNKNOWN:** the module `Vt`, and therefore all four readers via address
  recovery.

## Conclusion

Static VA recovery from this image is exhausted. This does **not** end firmware
RE; it changes the method:

1. trace readers by **relative call graph** from known functions
   (`0xc438a4`, `0xc0ebf8`, `0xc48380`), not by absolute VA;
2. use Ghidra P-code / emulation on selected routines;
3. if a reader must be identified, use a hardware/dynamic path (JTAG/serial
   trace or a spare-card trial loop);
4. QEMU is out of scope here: the blocker is placement metadata, not
   instruction semantics.

## Follow-ups

- [ ] Continue the independent relative-trace track from the known functions.
- [ ] Use a hardware/dynamic trace if static relative tracing stalls.
- [ ] Keep the data-side format facts as the current contract; the reader
      cross-check is a parallel long-running task.
