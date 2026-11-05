# EXP-2026-11-05-29: Static is closed for the NaviStateCC vtable

- **Status:** done (static closed; dynamic guide ready)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-430…C-437
- **Supersedes:** the hope that `0x171e9e8` contains a vtable template
- **Superseded by:** none

## Question

Does the shared COM helper at `0x171e9e8` contain a vtable construction
template or the fd method slots?

## Hypothesis

`0x171e9e8` builds the NaviStateCC object vtable from a ROM template.

## Observations

`0x171e9e8` is a **COM type-library registration/lookup routine**, not a
class factory or vtable builder:

- data: OLE type-info GUIDs `44ec053b-400f-11d0-9dcd-00a0c90391d3` and
  `44ec053a-400f-11d0-9dcd-00a0c90391d3` at `0x170a25c`/`0x170a26c`;
- strings: `LoadTypeLib`, `RegisterTypeLib`, `UnRegisterTypeLib`,
  `REGISTRY`, `Module`, `oleaut32.dll`, `.tlb` (`0x170a27c–0x170a304`);
- callees: `oleaut32`/`ole32` import thunks (`0x1713f54` → IAT `0x01abb29c`,
  `0x1713ec4` → IAT `0x01abb0fc`) plus a registry/typelib helper at
  `0x1714218`;
- the `+4/+12/+20/+24/+44` indirect calls are OLE `ITypeLib`/`ITypeInfo`
  interface methods, not NaviStateCC methods.

There is **no slot table, no constructor table, no memcpy from a ROM
template**.

## No static vtable

- fd method VAs under delta `0x1f07d5c`: `0x2b4a27c`, `0x2b4a400`,
  `0x2b4b600`; each occurs **once**, in the per-instruction/relocation table,
  never in a contiguous pointer run.
- A ≥8-pointer run scan resolving to NaviStateCC prologues: **0 runs**.
- `0xc43430` installs an object pointer (`0x1d0f898`) and a 16-byte class ID
  (`0x1d0f888`), not method slots; it has no static caller.
- `0x1d0f8a8` is RAM BSS, never written by the ROM; COM resolution goes
  through the registry (`REGISTRY`/`Module`/`LoadTypeLib`).

## Conclusion

**Static is closed for the vtable and the reader.** The object vtable is a
run-time artifact; the reader address requires one dynamic observation or the
OS loader's registry/class-factory state.

## Dynamic guide

1. **Primary:** break on `MAL_DataVol_getOffset` (VA `0x03498d48`, file
   `0x7f5f48`) or `MAL_DataVol_getSize` (VA `0x03498d28`, file `0x7f5f28`).
   The return address in `pr` is the `.ind`/volume wrapper.
2. **Secondary:** break on fd methods `0xc42520`, `0xc426a4`, `0xc438a4`;
   dump `[r4]` (vtable pointer) and object slots `+0x00…+0xd0`.
3. **Tertiary:** break on fd thunk/IAT slots (`0x2e07344`/`0x01ab9240`,
   `0x2e073c8`/`0x01ab902c`, …) to name the real APIs.
4. **Offline:** `size_8000` and `off_last_m1` `.ind` variants settle
   `chunk_size` semantics and seek-vs-scan.

## Follow-ups

- [ ] Prepare the hardware/dynamic kit (JTAG/serial or equivalent).
- [ ] Run the dynamic guide when access is available.
- [ ] In parallel, build the compiler and offline validators so the first
      hardware session can test a real card.
