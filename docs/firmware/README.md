# Firmware module pages

One page per module group of the head unit's software (tasks M1.41–M1.46 in
`TODO.md`). These are side tracks: they do not block the map compiler.

Common template for a page:

1. **Modules** — name, ROM (A/B/C), code size, one-line role, evidence.
2. **Features** — what the user can do through this group, each with the
   string or export that shows it.
3. **Interfaces** — devices opened (`SCI8:`, `CAN1:` …), IOCTL codes, COM
   classes, messages to other processes.
4. **Data** — files, registry keys and flash areas read or written.
5. **What could be changed** — constants, tables and policies with their VA
   per build, and what a change would need (data edit, code patch, not
   possible).
6. **Differences between builds** — from M1.37 when it exists.

Rules: every row has a status (VERIFIED / OBSERVED / HYPOTHESIS); VAs name
the build (`eu2011`, `us2011`); no vendor code or data is committed, only
addresses, names and our descriptions. Hardware is described in
[`docs/hardware/head-unit.md`](../hardware/head-unit.md).
