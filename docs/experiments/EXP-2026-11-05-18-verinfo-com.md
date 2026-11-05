# EXP-2026-11-05-18: VerInfoCC is a version provider, not the HDD_INFO parser

- **Status:** done (class identified; parser link still missing)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-310…C-318
- **Supersedes:** the “property 17 carries the HDD_INFO path” and
  “VerInfoCC parses HDD_INFO” hypotheses
- **Superseded by:** none

## Question

Which COM class is behind the property-17 call, and is it the `HDD_INFO`
parser?

## Hypothesis

The unnamed COM class reached through property 17 opens and parses
`HDD_INFO.TXT`.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| `.rgs` | `0xa1e780` |
| Tool | `solve_data_delta.py`, `hddinfo_variants.py` |

## Observations

### `VerInfoCC.DLL` / CoClass `VerInfoCtrl`

- CLSID `{408BB0AC-A5FC-41C9-AE69-6707E82354A9}`, TypeLib
  `{878E9476-2E46-472E-A5E7-15C8DB704865}`, `ThreadingModel = Both`;
  OLE control (`Control`/`Insertable`/`Programmable`).
- PDB path `…\apps\Diagnosis\src\CC\VerInfoCC\…`.
- Export dir `0xa1d89c` (`NameRVA=0x86f0`) ⇒ **file base `0xa15200`**.
  Exports: `DllCanUnloadNow 0xa177bc`, `DllGetClassObject 0xa17dfc`,
  `DllRegisterServer 0xa1815c`, `DllUnregisterServer 0xa18170`.
- **Code delta `0x027cae00`, VA base `0x031e0000`**, proven by vptr identity:
  constructor `0xa18270` stores `vptr = 0x031e14e4`; file `0xa166e4` is the
  method table. 16 interface vptrs recovered.
- `DllGetClassObject` is a trampoline: `r4 = VA 0x01df12f8` (`_Module`),
  `jmp 0xa175e0`; the target walks `[this+16]`, compares 4 CLSID dwords,
  returns `E_POINTER` / `E_NOINTERFACE` or QIs a pre-created object.

### Embedded type library

At `0xa1ead0` (`MSFT`), name table `0xa1f0dc`: `VERINFOCCLib`,
`_IVerInfoCtrlEvents`, `VerInfoCtrl`, `IVerInfoCtrl`, `GetVersionInfo`,
`dwType`, `pVal`, `VerInfoCC 1.0`.

The entire public surface is:

```
GetVersionInfo(LONG dwType, VARIANT* pVal)
```

There is **no setter and no path parameter**. Implementation class
`CVerInfoMain` strings: `Type[%d] Version = %s`, `Get Version type = [%d]`,
`Common API Type Error[%d] = const[%d]` ⇒ selector checked against a
compiled-in constant table.

### Retractions

- **“Property 17 carries the HDD_INFO path” — retracted.** The callee has one
  2-arg method and no setter; the call site is
  `obj->method#1(17, 0, *(0x01f83368))` — 4 args on an object that is **not**
  `IVerInfoCtrl`. The SD → VerInfoCC link is not established.
- **“VerInfoCC has no inline strings” — retracted** (ASCII-only scan
  artefact; 30+ UTF-16 strings).
- **“VerInfoCC parses HDD_INFO” — refuted**: no path, no file-I/O string, no
  setter; data comes from a constant table.

### Comparator delta settled

The comparator module's pool `0x6fb000`+ under delta `0x02800000` resolves to
all three `SD Import: <field> is different Sys[0x%x] SD[0x%x]`,
`application type not correct.`, `finished not found.`,
`StatusData(): ERROR-HEADER.`; at `0x6fb0ce` the `manufacturer_id` string is
the format argument of a `sprintf`-like call (`jsr 0x6fb0d8`).

## Still unknown

- **Six-line ↔ field mapping** (ranked guess only). All three compared fields
  are numbers; the `Sys` side is almost certainly a compiled-in table
  (`GetVersionInfo(dwType)` + `const[%d]` pattern) — strong hypothesis.
- **Who opens the file.** Module U references only suffixes of the
  `HDD_INFO` path (`0x03653374` → `mSD\…`, `0x036533a0` → `TXT`), never the
  start; the start (`0x01f83368`) is used by the SD module
  (`0x30effa`, `0x31260e`, `0x312630`). Module U compares
  (`mov.w @(4,r12),r0` at `0x6fb0e6`), the SD module uses the path.
  **The missing link is the class behind `0x30f008`.**

## Tools

- `tools/solve_data_delta.py` — window-scored delta solver; recovers
  VerInfoCC's true `0x027cae00` (12 hits vs 8 next). A 0x1000-only grid would
  never find it.
- `tools/hddinfo_variants.py` — now also emits all pairwise line swaps and a
  reverse; **89 variants, all 72 bytes** for the EU 2011 file.

## Follow-ups

- [ ] Identify the class behind the SD module's `0x30f008` call (where `r8` is
      constructed; the wrapper `0x30efcc` has no direct callers).
- [ ] Decompile that class's file-open/split/parse path.
- [ ] Run the spare-card matrix to settle the six-line mapping empirically.
